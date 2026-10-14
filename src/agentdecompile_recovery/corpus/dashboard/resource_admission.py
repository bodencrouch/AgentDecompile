"""Resource admission, aging reservations and backfill (task-acceptance design, admission section).

Pure decisions over declared inputs, plus a Linux host probe and a persisted aging ledger.

Memory admission uses the task's measured process-tree peak plus uncertainty and headroom
against current available memory minus live reservations, and it consults pressure
trends, recent resource-limit events and enforcement. Swap occupancy is telemetry,
never a universal veto: a near-full swap does not refuse a qualified task, and spare
swap does not prove capacity. An unknown profile gets a bounded profiling attempt,
not an admission. Required enforcement that is unavailable blocks the class.

Ranking inside a scheduling class: requested-capability dependency contribution,
then aging credit, then stable task id. Aging grows per declared interval up to a
cap; at the cap the oldest feasible task holds the next compatible capacity
reservation ahead of ordinary priority. Backfill runs only when it cannot delay
that reservation. An urgent override defers a reservation only through a recorded
event, never resets waiting age, and stays visible in the fairness report.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable

MIB = 1024 * 1024


@dataclass(frozen=True)
class ResourceProfile:
    """Declared needs of one task class. ``peak_bytes`` None means never measured."""
    peak_bytes: int | None
    uncertainty: float = 0.25          # fraction added to the measured peak
    enforcement_required: bool = False  # needs a process-tree memory limit (cgroup, job object)
    scratch_bytes: int = 0


@dataclass(frozen=True)
class HostState:
    mem_total: int
    mem_available: int
    swap_total: int = 0
    swap_free: int = 0
    pressure_full_avg10: float = 0.0    # PSI "full" stall percentage, 10 s window
    pressure_full_avg60: float = 0.0
    scratch_available: int | None = None
    enforcement_available: bool = False
    recent_limit_events: int = 0        # OOM kills / limit hits inside the policy window


@dataclass(frozen=True)
class AdmissionPolicy:
    headroom_bytes: int = 512 * MIB
    pressure_full_refuse: float = 10.0   # PSI full avg10 at or above this: the host is stalling
    pressure_rising_refuse: float = 5.0  # avg10 above this and above avg60: pressure climbing
    limit_events_refuse: int = 1         # any recent limit event for the class refuses more of it
    class_concurrency: dict[str, int] = field(default_factory=dict)  # class -> max running
    aging_interval_s: float = 300.0
    aging_cap: int = 12


@dataclass(frozen=True)
class Decision:
    outcome: str        # admit | refuse | profile_first | blocked
    reason: str
    need_bytes: int | None = None
    available_bytes: int | None = None
    basis: dict = field(default_factory=dict)


def need_bytes(profile: ResourceProfile, policy: AdmissionPolicy) -> int | None:
    if profile.peak_bytes is None:
        return None
    return int(profile.peak_bytes * (1.0 + max(0.0, profile.uncertainty))) + policy.headroom_bytes


def decide(profile: ResourceProfile, host: HostState, *, task_class: str, running_in_class: int = 0,
           reserved_bytes: int = 0, policy: AdmissionPolicy = AdmissionPolicy()) -> Decision:
    """Admit, refuse, ask for profiling, or block one task. Swap never decides alone."""
    basis = {"swap_used_fraction": (1 - host.swap_free / host.swap_total) if host.swap_total else None,
             "swap_role": "telemetry", "pressure_full_avg10": host.pressure_full_avg10,
             "pressure_full_avg60": host.pressure_full_avg60, "recent_limit_events": host.recent_limit_events,
             "running_in_class": running_in_class, "reserved_bytes": reserved_bytes, "task_class": task_class}
    if profile.enforcement_required and not host.enforcement_available:
        return Decision("blocked", "required process-tree enforcement is unavailable on this worker", basis=basis)
    need = need_bytes(profile, policy)
    if need is None:
        return Decision("profile_first", "no measured process-tree peak; run a bounded profiling attempt "
                        "on an eligible isolated worker first", basis=basis)
    available = host.mem_available - reserved_bytes
    limit = policy.class_concurrency.get(task_class)
    if limit is not None and running_in_class >= limit:
        return Decision("refuse", f"class {task_class!r} is at its concurrency limit ({limit})", need, available, basis)
    if host.recent_limit_events >= policy.limit_events_refuse:
        return Decision("refuse", "recent resource-limit events: the class is overloaded", need, available, basis)
    if host.pressure_full_avg10 >= policy.pressure_full_refuse:
        return Decision("refuse", "memory pressure is stalling the host", need, available, basis)
    if host.pressure_full_avg10 >= policy.pressure_rising_refuse and host.pressure_full_avg10 > host.pressure_full_avg60:
        return Decision("refuse", "memory pressure is rising", need, available, basis)
    if need > available:
        return Decision("refuse", "measured need exceeds available memory after reservations "
                        "(spare swap does not count as capacity)", need, available, basis)
    if profile.scratch_bytes and host.scratch_available is not None and profile.scratch_bytes > host.scratch_available:
        return Decision("refuse", "scratch capacity is insufficient", need, available, basis)
    return Decision("admit", "complete admission basis satisfied", need, available, basis)


# --------------------------------------------------------------------------- ranking, aging, backfill

@dataclass(frozen=True)
class Task:
    task_id: str
    task_class: str
    profile: ResourceProfile
    capability_priority: int = 0      # requested-capability dependency contribution
    ready_since: float = 0.0          # persisted eligible-since time (survives retries and restarts)


@dataclass(frozen=True)
class Override:
    """A recorded, policy-authorized urgent deferral of one reservation."""
    override_id: str
    requester: str
    authority: str
    reason: str
    reservation_task_id: str
    expires_at: float
    rescheduling: str


def aging_credit(task: Task, now: float, policy: AdmissionPolicy) -> int:
    waited = max(0.0, now - task.ready_since)
    return min(policy.aging_cap, int(waited // policy.aging_interval_s))


def rank(tasks: Iterable[Task], now: float, policy: AdmissionPolicy = AdmissionPolicy()) -> list[Task]:
    """Ordinary same-class ranking: capability contribution, then aging credit, then stable id."""
    return sorted(tasks, key=lambda t: (-t.capability_priority, -aging_credit(t, now, policy), t.task_id))


@dataclass
class Plan:
    dispatch: list[str]
    reservation: str | None
    reservation_need: int | None
    deferred_by: list[dict]
    refused: dict[str, str]
    backfill_blocked: list[str]


def plan(tasks: Iterable[Task], host: HostState, now: float, *, running: dict[str, int] | None = None,
         overrides: Iterable[Override] = (), policy: AdmissionPolicy = AdmissionPolicy()) -> Plan:
    """Choose what to dispatch now. The capped-age reservation outranks ordinary priority."""
    running = dict(running or {})
    tasks = list(tasks)
    active_overrides = [o for o in overrides if o.expires_at > now]
    capped = [t for t in tasks if aging_credit(t, now, policy) >= policy.aging_cap
              and need_bytes(t.profile, policy) is not None
              and need_bytes(t.profile, policy) <= host.mem_total - policy.headroom_bytes]  # feasible at all
    capped.sort(key=lambda t: (t.ready_since, t.task_id))
    holder = capped[0] if capped else None
    deferred = [asdict(o) for o in active_overrides if holder and o.reservation_task_id == holder.task_id]
    if deferred:
        holder = None  # deferred by a recorded override; its age is untouched and the deferral is reported
    out = Plan([], holder.task_id if holder else None, need_bytes(holder.profile, policy) if holder else None,
               deferred, {}, [])
    reserved = 0
    order = ([holder] if holder else []) + [t for t in rank(tasks, now, policy) if not holder or t.task_id != holder.task_id]
    for t in order:
        d = decide(t.profile, host, task_class=t.task_class, running_in_class=running.get(t.task_class, 0),
                   reserved_bytes=reserved, policy=policy)
        if holder and t.task_id == holder.task_id:
            if d.outcome == "admit":
                out.dispatch.append(t.task_id)
                running[t.task_class] = running.get(t.task_class, 0) + 1
                reserved += d.need_bytes or 0
                out.reservation = None  # satisfied now
            else:
                # Hold its capacity: nothing may consume memory the reservation needs.
                reserved += out.reservation_need or 0
                out.refused[t.task_id] = f"reserved, waiting: {d.reason}"
            continue
        if d.outcome != "admit":
            out.refused[t.task_id] = d.reason
            if holder and out.reservation and d.outcome == "refuse" and "exceeds available" in d.reason:
                out.backfill_blocked.append(t.task_id)
            continue
        out.dispatch.append(t.task_id)
        running[t.task_class] = running.get(t.task_class, 0) + 1
        reserved += d.need_bytes or 0
    return out


# --------------------------------------------------------------------------- host probe (Linux)

def _meminfo(path: str = "/proc/meminfo") -> dict[str, int]:
    out: dict[str, int] = {}
    with open(path) as handle:
        for line in handle:
            key, _, rest = line.partition(":")
            parts = rest.split()
            if parts:
                out[key] = int(parts[0]) * (1024 if len(parts) > 1 and parts[1] == "kB" else 1)
    return out


def _psi_full(path: str = "/proc/pressure/memory") -> tuple[float, float]:
    try:
        with open(path) as handle:
            for line in handle:
                if line.startswith("full"):
                    fields = dict(kv.split("=") for kv in line.split()[1:])
                    return float(fields.get("avg10", 0)), float(fields.get("avg60", 0))
    except OSError:
        pass
    return 0.0, 0.0


def probe_host(*, scratch_dir: str | None = None, enforcement_available: bool | None = None,
               recent_limit_events: int = 0) -> HostState:
    info = _meminfo()
    avg10, avg60 = _psi_full()
    scratch = None
    if scratch_dir:
        stat = os.statvfs(scratch_dir)
        scratch = stat.f_bavail * stat.f_frsize
    if enforcement_available is None:
        enforcement_available = Path("/sys/fs/cgroup/cgroup.controllers").is_file() and \
            "memory" in Path("/sys/fs/cgroup/cgroup.controllers").read_text()
    return HostState(mem_total=info.get("MemTotal", 0), mem_available=info.get("MemAvailable", 0),
                     swap_total=info.get("SwapTotal", 0), swap_free=info.get("SwapFree", 0),
                     pressure_full_avg10=avg10, pressure_full_avg60=avg60, scratch_available=scratch,
                     enforcement_available=bool(enforcement_available), recent_limit_events=recent_limit_events)


# --------------------------------------------------------------------------- persisted aging ledger

class AgingLedger:
    """Persists each task's eligible-since time and override history across retries and restarts.

    ``ready_since`` is set once, when a task first becomes eligible, and is kept through
    unrelated retries; only completion (``retire``) removes it. Writes are atomic.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.data = {"schema": 1, "ready_since": {}, "overrides": []}
        if self.path.is_file():
            loaded = json.loads(self.path.read_text())
            if loaded.get("schema") != 1:
                raise ValueError(f"{self.path}: unsupported aging ledger schema")
            self.data = loaded

    def mark_ready(self, task_id: str, now: float | None = None) -> float:
        since = self.data["ready_since"].setdefault(task_id, now if now is not None else time.time())
        self._save()
        return since

    def ready_since(self, task_id: str) -> float | None:
        return self.data["ready_since"].get(task_id)

    def retire(self, task_id: str) -> None:
        if self.data["ready_since"].pop(task_id, None) is not None:
            self._save()

    def record_override(self, override: Override) -> None:
        if not all([override.requester, override.authority, override.reason, override.rescheduling]):
            raise ValueError("an urgent override must name requester, authority, reason and rescheduling")
        self.data["overrides"].append(asdict(override))
        self._save()

    def overrides(self) -> list[Override]:
        return [Override(**o) for o in self.data["overrides"]]

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=self.path.name, suffix=".tmp")
        with os.fdopen(fd, "w") as handle:
            json.dump(self.data, handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, self.path)
        dir_fd = os.open(self.path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)


# --------------------------------------------------------------------------- measured profiles and the dispatch gate

def session_rss_bytes(session_id: int) -> int:
    """Summed resident memory of every process in one session (a job's process tree)."""
    page = os.sysconf("SC_PAGE_SIZE")
    total = 0
    for entry in os.scandir("/proc"):
        if not entry.name.isdigit():
            continue
        try:
            with open(f"/proc/{entry.name}/stat") as handle:
                fields = handle.read().rsplit(")", 1)[1].split()
            if int(fields[3]) != session_id:  # field 6 (session) after the comm field
                continue
            with open(f"/proc/{entry.name}/statm") as handle:
                total += int(handle.read().split()[1]) * page
        except (OSError, IndexError, ValueError):
            continue
    return total


class ProfileStore:
    """Measured process-tree peaks per action. The profile is the max of the last few runs."""

    KEEP = 5

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._lock = __import__("threading").Lock()

    def _load(self) -> dict:
        if self.path.is_file():
            data = json.loads(self.path.read_text())
            if data.get("schema") == 1:
                return data
        return {"schema": 1, "peaks": {}}

    def record(self, action_id: str, peak_bytes: int) -> None:
        if peak_bytes <= 0:
            return
        with self._lock:
            data = self._load()
            peaks = data["peaks"].setdefault(action_id, [])
            peaks.append(int(peak_bytes))
            del peaks[:-self.KEEP]
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=self.path.name, suffix=".tmp")
            with os.fdopen(fd, "w") as handle:
                json.dump(data, handle, sort_keys=True)
            os.replace(tmp, self.path)

    def profile(self, action_id: str) -> ResourceProfile:
        peaks = self._load()["peaks"].get(action_id) or []
        return ResourceProfile(peak_bytes=max(peaks) if peaks else None)


def default_profile_store() -> ProfileStore:
    configured = os.environ.get("AGENTDECOMPILE_RESOURCE_PROFILES", "").strip()
    if configured:
        return ProfileStore(configured)
    base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    return ProfileStore(base / "agentdecompile" / "resource_profiles.json")


def gate_enabled() -> bool:
    return os.environ.get("AGENTDECOMPILE_RESOURCE_ADMISSION", "on").strip().lower() not in {"0", "off", "false", "no"}


def dispatch_gate(action_id: str, running_action_ids: list[str], *, store: ProfileStore | None = None,
                  host: HostState | None = None, policy: AdmissionPolicy = AdmissionPolicy()) -> Decision:
    """Decide one dispatch against the live host and the reservations of running jobs.

    An action never measured runs only as a lone profiling attempt for its class.
    """
    store = store or default_profile_store()
    host = host or probe_host()
    reserved = sum(need_bytes(store.profile(a), policy) or 0 for a in running_action_ids)
    same = running_action_ids.count(action_id)
    decision = decide(store.profile(action_id), host, task_class=action_id, running_in_class=same,
                      reserved_bytes=reserved, policy=policy)
    if decision.outcome == "profile_first":
        if same:
            return Decision("refuse", "a profiling attempt for this action is already running",
                            basis=decision.basis)
        return Decision("admit", "unmeasured action admitted as a lone profiling attempt",
                        basis={**decision.basis, "profiling_attempt": True})
    return decision


# --------------------------------------------------------------------------- runtime admission in the job queue

_HOST_CACHE: tuple[float, HostState] | None = None


def _cached_host(max_age: float = 1.0) -> HostState:
    global _HOST_CACHE
    now = time.monotonic()
    if _HOST_CACHE is None or now - _HOST_CACHE[0] > max_age:
        _HOST_CACHE = (now, probe_host())
    return _HOST_CACHE[1]


def queue_policy() -> AdmissionPolicy:
    def number(name: str, default: float) -> float:
        try:
            return float(os.environ.get(name, default))
        except ValueError:
            return default
    return AdmissionPolicy(aging_interval_s=number("AGENTDECOMPILE_AGING_INTERVAL_S", 60.0),
                           aging_cap=int(number("AGENTDECOMPILE_AGING_CAP", 10)))


def never_feasible(action_id: str, *, store: ProfileStore | None = None, host: HostState | None = None,
                   policy: AdmissionPolicy = AdmissionPolicy()) -> str | None:
    """A reason when the action can never fit this worker; waiting would not help."""
    store = store or default_profile_store()
    host = host or _cached_host()
    need = need_bytes(store.profile(action_id), policy)
    if need is not None and need > host.mem_total - policy.headroom_bytes:
        return (f"measured need {need // MIB} MiB exceeds this worker's memory "
                f"({host.mem_total // MIB} MiB); a capacity prerequisite, not a wait")
    return None


def runtime_admit(job_id: str, action_id: str, *, running: list[str], queued: list[tuple[str, str, float]],
                  now: float | None = None, store: ProfileStore | None = None, host: HostState | None = None,
                  overrides: Iterable[Override] | None = None, policy: AdmissionPolicy | None = None) -> tuple[bool, str, str | None]:
    """Whether one queued job may start now: ``(ok, reason, reservation_holder)``.

    ``running`` lists running jobs' action ids; ``queued`` lists ``(job_id, action_id, created_at)``.
    The oldest queued job past its age cap that can ever fit holds a reservation; another job may
    start only if the reservation still fits after it. A recorded urgent override defers the
    reservation without resetting the holder's age.
    """
    policy = policy or queue_policy()
    store = store or default_profile_store()
    host = host or _cached_host()
    now = time.time() if now is None else now
    if overrides is None:
        ledger_path = os.environ.get("AGENTDECOMPILE_AGING_LEDGER", "").strip()
        overrides = AgingLedger(ledger_path).overrides() if ledger_path and Path(ledger_path).is_file() else []
    deferred = {o.reservation_task_id for o in overrides if o.expires_at > now}
    reserved = sum(need_bytes(store.profile(a), policy) or 0 for a in running)
    holder = None
    for other_id, other_action, created in sorted(queued, key=lambda q: (q[2], q[0])):
        waited = int(max(0.0, now - created) // policy.aging_interval_s)
        need = need_bytes(store.profile(other_action), policy)
        if waited >= policy.aging_cap and need is not None and need <= host.mem_total - policy.headroom_bytes \
                and other_id not in deferred:
            holder = (other_id, need)
            break
    extra = holder[1] if holder and holder[0] != job_id else 0
    same = running.count(action_id)
    decision = decide(store.profile(action_id), host, task_class=action_id, running_in_class=same,
                      reserved_bytes=reserved + extra, policy=policy)
    if decision.outcome == "profile_first":
        if same:
            return False, "waiting: a profiling attempt for this action is running", holder and holder[0]
        if holder and holder[0] != job_id:
            return False, f"waiting: reservation held by {holder[0]}; an unmeasured job could delay it", holder[0]
        return True, "admitted as a lone profiling attempt", holder and holder[0]
    if decision.outcome == "admit":
        return True, decision.reason, holder and holder[0]
    prefix = f"waiting behind reservation {holder[0]}: " if extra else "waiting: "
    return False, prefix + decision.reason, holder and holder[0]
