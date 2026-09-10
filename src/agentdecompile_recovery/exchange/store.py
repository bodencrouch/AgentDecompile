"""Capability-labeled work exchange: leases recovery work units to remote fulfillers.

This is `rewrite_queue.py` generalized. Same lifecycle (`pending -> claimed ->
awaiting-verification | failed`), same lease-and-stale-reclaim semantics, same
trust boundary -- but the unit is any lane's work rather than one rewrite
request, and the fulfiller may be a browser tab on someone else's machine.

**A submission is a proposal, never a commit.** Nothing here writes SQLite,
writes an artifact directory, or mutates corpus state; a submission records an
artifact plus a *self-reported* verdict and parks the unit at
`awaiting-verification` for the coordinator's own compile-verify gate. That is
why the terminal state is not called `completed`: this module has no means of
deciding that anything completed. See `CLAIM_BOUNDARY`, which mirrors
`rewrite_queue.CLAIM_BOUNDARY`.

Three defects of the file queue are fixed deliberately, because each only
starts to matter once the queue is shared:

- **`import fcntl` is guarded.** Unconditional, it makes the module
  unimportable on Windows -- and a Windows contributor is exactly the
  contributor who owns `cl.exe`. Absent `fcntl` the cross-process lock degrades
  to a no-op, which is safe here because the authoritative state is in memory
  behind an `asyncio.Lock` in a single server process; the file lock only keeps
  an out-of-process reader from seeing a torn write.
- **A corrupt state file is quarantined, never silently emptied.** The file
  queue returns an empty queue on a bad read and the next write persists it,
  destroying every live entry. Here a bad read renames the file aside and, if
  even that fails, latches read-only so no empty snapshot can land on top of
  live work.
- **Every lease carries a fencing token.** Stale-claim takeover without fencing
  lets two workers execute the same unit. Any lease invalidation -- expiry,
  takeover, submit, restart -- increments the unit's fence, so a submit
  carrying an old fence is rejected instead of overwriting a newer worker's.

Authoritative state lives in memory; disk is written on mutation only, off the
event loop thread. Claims return immediately (the router's 204 when there is no
work) rather than parking a connection: donated compute is a fan-in problem
before it is a compute problem, and the dashboard runs one uvicorn worker on
one event loop.
"""

from __future__ import annotations

import asyncio
import errno
import hashlib
import json
import logging
import os
import re
import secrets
import threading
import time

from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:  # pragma: no cover - platform dependent
    import fcntl
except ImportError:  # Windows. See module docstring: the lock is advisory here.
    fcntl = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

SCHEMA = "agentdecompile.work-exchange.v1"
CLAIM_BOUNDARY = (
    "work-exchange submissions are advisory proposals only; the coordinator's "
    "objdiff compile-verify gate is the sole proof mechanism for any artifact "
    "a remote fulfiller reports"
)

STATUS_PENDING = "pending"
STATUS_CLAIMED = "claimed"
STATUS_AWAITING_VERIFICATION = "awaiting-verification"
STATUS_FAILED = "failed"

LANES = ("rewrite", "permute", "compile", "search", "objdiff", "match", "ghidra")

# Baseline capability demand per lane, unioned with whatever a unit declares.
# A `compile` unit is not offerable to a contributor without the 2003 toolchain
# no matter what the unit's author remembered to write down.
LANE_CAPABILITIES: dict[str, frozenset[str]] = {
    "rewrite": frozenset({"llm"}),
    "permute": frozenset(),
    "compile": frozenset({"msvc-vc7", "wine"}),
    "search": frozenset({"msvc-vc7", "wine"}),
    "objdiff": frozenset({"objdiff"}),
    "match": frozenset({"python"}),
    "ghidra": frozenset({"ghidra-12"}),
}

# A self-reported verdict in this set parks the unit at `failed` instead of
# `awaiting-verification`: there is nothing for the coordinator to verify.
FAILURE_VERDICTS = frozenset({"failed", "error", "abandoned", "unsupported"})

DEFAULT_LEASE_SECONDS = 300
THROUGHPUT_WINDOW_SECONDS = 300.0
# The HTTP model enforces this too, but direct in-process callers must not be
# able to bypass the same snapshot-growth bound.
MAX_ARTIFACT_BYTES = 64 * 1024

# An absolute path in a payload is R1's failure mode: the unit stops being a
# value and becomes a reference into the coordinator's filesystem. Match only
# unambiguous path spellings, so source text is not caught by accident.
_ABSOLUTE_POSIX_PATH = re.compile(r"^(/[^/\s]+){2,}/?$")
_ABSOLUTE_WINDOWS_PATH = re.compile(r"^[A-Za-z]:[\\/]")


class ExchangeError(RuntimeError):
    """Base for exchange refusals; carries the HTTP status the router returns."""

    status = 400
    code = "exchange-error"


class UnknownWorker(ExchangeError):
    status = 404
    code = "unknown-worker"


class LeaseRejected(ExchangeError):
    """The lease is expired, superseded, or fenced out by a newer one."""

    status = 410
    code = "lease-rejected"


class IdempotencyConflict(ExchangeError):
    status = 409
    code = "idempotency-conflict"


class RateLimited(ExchangeError):
    status = 429
    code = "rate-limited"


class CapacityExceeded(ExchangeError):
    status = 503
    code = "capacity-exceeded"


class InvalidSubmission(ExchangeError):
    """A result that cannot enter the coordinator's verification queue."""

    code = "invalid-submission"


def default_state_path() -> Path:
    """Where the exchange keeps its snapshot when the router is not given a store."""

    override = os.environ.get("AGENTDECOMPILE_EXCHANGE_STATE")
    return Path(override) if override else Path.cwd() / "state" / "work-exchange.json"


def derive_unit_id(lane: str, payload: dict[str, Any]) -> str:
    """Content address of a unit, shaped like `rewrite_queue.derive_request_id`.

    The digest covers the payload alone, so the same work offered twice
    collapses to one entry regardless of who offered it or which capability
    labels were spelled out alongside it.
    """

    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
    return f"{lane}:{digest}"


def required_capabilities_for(lane: str, declared: Any = None) -> frozenset[str]:
    return frozenset(LANE_CAPABILITIES.get(lane, frozenset())) | {str(cap) for cap in declared or ()}


def assert_portable_payload(payload: Any, *, _depth: int = 0) -> None:
    """Reject a payload that references the coordinator's filesystem (R1).

    Units are values: inputs travel inline or by content hash. A payload that
    embeds `live_root()` or `live_db()` output is unusable on a volunteer's
    machine, and that is a bug at the moment the unit is offered rather than at
    the moment some stranger fails to open the path.
    """

    if _depth > 8:
        raise ValueError("work unit payload nests too deeply to be a value")
    if isinstance(payload, dict):
        for key, value in payload.items():
            # Keys too, not just values. The design doc's R1 names path-keyed
            # maps (identity_lock_key) as exactly the thing that makes state
            # machine-local, so a path as a dict key is the likely spelling,
            # not a contrived one.
            assert_portable_payload(key, _depth=_depth + 1)
            assert_portable_payload(value, _depth=_depth + 1)
        return
    if isinstance(payload, (list, tuple)):
        for value in payload:
            assert_portable_payload(value, _depth=_depth + 1)
        return
    if isinstance(payload, str) and (_ABSOLUTE_POSIX_PATH.match(payload) or _ABSOLUTE_WINDOWS_PATH.match(payload)):
        raise ValueError(f"work unit payload must not carry an absolute path: {payload!r}")


@contextmanager
def _file_lock(path: Path) -> Iterator[None]:
    """Cross-process advisory lock around a snapshot write; a no-op without fcntl."""

    if fcntl is None:
        yield
        return
    with path.open("a+") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _sync_directory(path: Path) -> None:
    """Persist directory entries where the platform/filesystem supports it."""

    if os.name == "nt":  # Windows cannot open directories for os.fsync.
        return
    unsupported = {errno.EINVAL, errno.ENOTSUP, errno.EOPNOTSUPP}
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError as exc:
        if exc.errno in unsupported:
            return
        raise
    try:
        try:
            os.fsync(descriptor)
        except OSError as exc:
            if exc.errno not in unsupported:
                raise
    finally:
        os.close(descriptor)


@dataclass(slots=True)
class WorkUnit:
    unit_id: str
    lane: str
    payload: dict[str, Any]
    required_capabilities: frozenset[str]
    offered_at: float
    status: str = STATUS_PENDING
    fence: int = 0
    claimed_by: str | None = None
    lease_token: str | None = None
    lease_expires_at: float | None = None
    submission: dict[str, Any] | None = None
    # Set only on the pending -> {failed, awaiting-verification} transition in
    # submit(). Only failed units use it for retention: an awaiting proposal
    # must survive forwarding until a coordinator proves or rejects it.
    resolved_at: float | None = None

    def offer_view(self) -> dict[str, Any]:
        """The unit as shipped to a fulfiller: a value, and nothing about the lease."""

        return {
            "unitId": self.unit_id,
            "lane": self.lane,
            "requiredCapabilities": sorted(self.required_capabilities),
            "payload": self.payload,
        }

    def state_view(self) -> dict[str, Any]:
        return {
            "unitId": self.unit_id,
            "lane": self.lane,
            "payload": self.payload,
            "requiredCapabilities": sorted(self.required_capabilities),
            "offeredAt": self.offered_at,
            "status": self.status,
            "fence": self.fence,
            "claimedBy": self.claimed_by,
            "leaseExpiresAt": self.lease_expires_at,
            "submission": self.submission,
            "resolvedAt": self.resolved_at,
        }


@dataclass(slots=True)
class Worker:
    worker_id: str
    agent: str
    capabilities: frozenset[str]
    enrolled_at: float
    last_seen: float
    window_started: float = 0.0
    window_calls: int = 0
    submissions: int = 0

    def state_view(self) -> dict[str, Any]:
        return {
            "workerId": self.worker_id,
            "agent": self.agent,
            "capabilities": sorted(self.capabilities),
            "enrolledAt": self.enrolled_at,
            "lastSeen": self.last_seen,
            "submissions": self.submissions,
        }


class ExchangeStore:
    """In-memory work exchange with a durable, quarantine-safe JSON snapshot.

    Every mutation snapshots under an `asyncio.Lock` and writes off-thread, so
    no request path blocks on disk while holding the loop. Enrollment is open
    per the project's stated posture; the caps and the per-worker rate limit
    exist so one broken client cannot drain or flood the queue, and are not
    authentication.
    """

    def __init__(
        self,
        state_path: Path,
        *,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        max_workers: int = 512,
        max_units: int = 4096,
        rate_limit_calls: int = 120,
        rate_limit_window: float = 60.0,
        enroll_limit_calls: int = 60,
        terminal_retention_seconds: float = 3600.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.state_path = Path(state_path)
        self.lease_seconds = int(lease_seconds)
        self.max_workers = int(max_workers)
        self.max_units = int(max_units)
        # Failed work can be retried or inspected for a bounded interval.
        # Awaiting-verification proposals are deliberately retained until a
        # future coordinator acknowledgement/resolution path exists.
        self.terminal_retention_seconds = float(terminal_retention_seconds)
        self.rate_limit_calls = int(rate_limit_calls)
        self.rate_limit_window = float(rate_limit_window)
        self.enroll_limit_calls = int(enroll_limit_calls)
        self._enroll_window_started = 0.0
        self._enroll_calls = 0
        self.clock = clock
        self.quarantined_path: Path | None = None
        self.read_only = False
        self._lock = asyncio.Lock()
        self._loaded = False
        self._units: dict[str, WorkUnit] = {}
        self._workers: dict[str, Worker] = {}
        self._receipts: dict[str, dict[str, Any]] = {}
        self._fence = 0
        # Monotonic snapshot ordering. _snapshot_text bumps it under the
        # asyncio lock so a write's generation is fixed at the moment its text
        # is built, not at the moment it reaches the disk.
        self._generation = 0
        self._committed_generation = 0
        self._pending_directory_sync: list[Path] = []
        self._directory_ready = False
        # _write_snapshot runs off the event loop via asyncio.to_thread, so
        # concurrent mutations reach it on separate OS threads of the default
        # executor. fcntl.flock (see _file_lock) only keeps a second *process*
        # from seeing a torn write -- it does nothing for two threads inside
        # this one process, and nothing at all on Windows where fcntl is
        # absent. This lock is what actually serializes the generation
        # check/write/commit sequence for local threads.
        self._write_lock = threading.Lock()
        self._recent: deque[tuple[float, str]] = deque(maxlen=1024)

    # -- durability ---------------------------------------------------------

    def _load(self) -> None:
        """Read the snapshot once, quarantining anything unreadable.

        Never degrades to "empty queue, then persist it" -- that is the file
        queue's data-loss bug. A file that will not parse is moved aside
        intact, and if even the move fails the store latches read-only so no
        empty snapshot can land on top of live work.
        """

        if self._loaded:
            return
        path = self.state_path
        if not path.exists():
            self._loaded = True
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = None
        if not isinstance(raw, dict) or raw.get("schema") != SCHEMA or not isinstance(raw.get("units"), dict) or not isinstance(raw.get("workers"), dict):
            self._loaded = True
            self._quarantine(path)
            return

        # Hydrate into locals and commit only on success. Assigning to self as
        # we go, with _loaded already latched, is how a single bad field type
        # turns into data loss: the raise leaves the store half-populated but
        # "loaded", and the next mutation persists that truncated state over an
        # intact file. A schema-valid file with an ISO-string timestamp -- the
        # shape rewrite_queue itself writes -- is enough to trigger it.
        try:
            fence = int(raw.get("fence") or 0)
            sync_depth = raw.get("pendingDirectorySyncDepth", 0)
            if type(sync_depth) is not int or not 0 <= sync_depth < len(path.parents):
                raise ValueError("invalid pending directory sync depth")
            pending_directory_sync = list(reversed(path.parents[1 : sync_depth + 1]))
            receipts = {str(key): value for key, value in (raw.get("receipts") or {}).items() if isinstance(value, dict)}
            workers: dict[str, Worker] = {}
            for worker_id, row in raw["workers"].items():
                if not isinstance(row, dict):
                    continue
                workers[str(worker_id)] = Worker(
                    worker_id=str(worker_id),
                    agent=str(row.get("agent") or ""),
                    capabilities=frozenset(str(cap) for cap in row.get("capabilities") or ()),
                    enrolled_at=float(row.get("enrolledAt") or 0.0),
                    last_seen=float(row.get("lastSeen") or 0.0),
                    submissions=int(row.get("submissions") or 0),
                )
            units: dict[str, WorkUnit] = {}
            restored: list[WorkUnit] = []
            for unit_id, row in raw["units"].items():
                if not isinstance(row, dict):
                    continue
                status = str(row.get("status") or STATUS_PENDING)
                unit = WorkUnit(
                    unit_id=str(unit_id),
                    lane=str(row.get("lane") or ""),
                    payload=row["payload"] if isinstance(row.get("payload"), dict) else {},
                    required_capabilities=frozenset(str(cap) for cap in row.get("requiredCapabilities") or ()),
                    offered_at=float(row.get("offeredAt") or 0.0),
                    status=status,
                    fence=int(row.get("fence") or 0),
                    submission=row["submission"] if isinstance(row.get("submission"), dict) else None,
                    resolved_at=float(row["resolvedAt"]) if isinstance(row.get("resolvedAt"), (int, float)) else None,
                )
                if status == STATUS_CLAIMED:
                    # A lease cannot survive the process that granted it: the
                    # token is gone, so fence the old holder out and re-offer.
                    unit.status = STATUS_PENDING
                    restored.append(unit)
                units[unit.unit_id] = unit
        except (TypeError, ValueError, AttributeError):
            logger.warning("exchange: state at %s failed to hydrate; quarantining", path, exc_info=True)
            self._loaded = True
            self._quarantine(path)
            return

        self._fence = fence
        self._receipts = receipts
        self._workers = workers
        self._units = units
        self._pending_directory_sync = pending_directory_sync
        # Fence every restored lease out, now that the counter is authoritative.
        for unit in restored:
            unit.fence = self._next_fence()
        self._loaded = True

    def _quarantine(self, path: Path) -> None:
        # Random suffix, not a second-granular timestamp: Path.replace
        # overwrites silently, so two quarantines in the same second would
        # destroy the first preserved copy -- in the code whose whole purpose
        # is not losing those bytes.
        target = path.with_name(f"{path.name}.corrupt-{int(self.clock())}-{secrets.token_hex(4)}")
        try:
            path.replace(target)
        except OSError:
            # Latch read-only so no snapshot can land on top of live work, and
            # say so: silent permanent non-durability is the worst outcome here.
            logger.error("exchange: could not quarantine %s; store is now read-only", path, exc_info=True)
            self.read_only = True
            return
        self.quarantined_path = target

    def _snapshot_text(self) -> str:
        """Serialize under the lock; the write itself happens off-thread.

        Handing live dicts to a worker thread would let the next coroutine
        mutate them mid-serialization.
        """

        state = {
            "schema": SCHEMA,
            "claimBoundary": CLAIM_BOUNDARY,
            "fence": self._fence,
            "units": {unit_id: unit.state_view() for unit_id, unit in self._units.items()},
            "workers": {worker_id: worker.state_view() for worker_id, worker in self._workers.items()},
            "receipts": self._receipts,
        }
        # Called only under the asyncio lock, so this ordering stamp is fixed
        # against the state it describes.
        self._generation += 1
        return json.dumps(state, indent=2, sort_keys=True, default=str) + "\n"

    def _prepare_state_directory(self) -> None:
        """Anchor automatic mkdir before snapshots, recovering interrupted setup.

        An existing, unmarked hierarchy is operator-provisioned. For directories
        we create, persist an intent in the nearest existing ancestor *before*
        mkdir: a process can die before it ever writes a snapshot. Exact-name
        probes recover that intent without opening unrelated ancestors for sync.
        """

        if self._directory_ready:
            return
        directory = self.state_path.absolute().parent
        marker_name = ".exchange-init-" + hashlib.sha256(os.fsencode(self.state_path.absolute())).hexdigest() + ".pending"
        ancestors = (directory, *directory.parents)
        anchor = next((parent for parent in ancestors if (parent / marker_name).exists()), None)
        if anchor is None:
            anchor = next(parent for parent in ancestors if parent.is_dir())
            if anchor == directory:
                self._directory_ready = True
                return
        marker = anchor / marker_name
        with marker.open("a", encoding="utf-8") as handle:
            handle.flush()
            os.fsync(handle.fileno())
        _sync_directory(anchor)
        directory.mkdir(parents=True, exist_ok=True)
        for parent in ancestors:
            _sync_directory(parent)
            if parent == anchor:
                break
        marker.unlink()
        _sync_directory(anchor)
        self._directory_ready = True

    def _write_snapshot(self, text: str, generation: int) -> None:
        path = self.state_path
        # Unique tmp name per writer, as in state.atomic_write_json: concurrent
        # writers must not replace each other's in-progress temporary file.
        tmp = path.with_name(f"{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
        # self._write_lock is the OUTER guard and _file_lock the inner one: a
        # thread must win the local lock before it may even attempt the
        # cross-process file lock, so no thread ever blocks on flock() while
        # holding nothing, and no two threads in this process ever race each
        # other for it. Reversing the order -- taking _file_lock first --
        # would let one thread hold the OS-level lock while waiting on
        # self._write_lock for a peer thread, serializing nothing extra and
        # adding a needless cross-process hold time for no benefit, since only
        # one thread here can be inside _file_lock at a time either way.
        with self._write_lock:
            self._prepare_state_directory()
            with _file_lock(path.with_name(f"{path.name}.lock")):
                # Snapshot text is built under the asyncio lock but written
                # outside it, so two mutations can reach this point in either
                # order. fcntl.flock only excludes *other processes*; it does
                # not order these two local threads (and is a no-op entirely
                # on Windows), so without self._write_lock above, both threads
                # could pass this check before either commits, and the one
                # carrying the older generation could write last and silently
                # revert the snapshot -- the exact hazard this check exists to
                # prevent, arriving through the thread scheduler instead of
                # through disk ordering. self._write_lock makes the check,
                # write, and commit atomic with respect to every thread in
                # this process; _file_lock is what still matters for a
                # hypothetical second process on the same host.
                if generation <= self._committed_generation:
                    return
                if self._pending_directory_sync:
                    # The replacement can survive a process restart even when
                    # an ancestor fsync fails. Carry that retry obligation in
                    # the snapshot; the next successful write drops it. Store
                    # a bounded depth instead of trusting paths from disk.
                    state = json.loads(text)
                    state["pendingDirectorySyncDepth"] = max(path.parents.index(directory) for directory in self._pending_directory_sync)
                    text = json.dumps(state, indent=2, sort_keys=True) + "\n"
                try:
                    with tmp.open("w", encoding="utf-8") as handle:
                        handle.write(text)
                        handle.flush()
                        os.fsync(handle.fileno())
                    tmp.replace(path)
                    _sync_directory(path.parent)
                    for directory in reversed(self._pending_directory_sync):
                        _sync_directory(directory)
                    self._pending_directory_sync.clear()
                finally:
                    # A failed file sync leaves an uncommitted temporary file.
                    # Cleanup must not mask the original persistence error.
                    try:
                        tmp.unlink(missing_ok=True)
                    except OSError:
                        logger.warning("exchange: could not remove temporary snapshot %s", tmp, exc_info=True)
                self._committed_generation = generation

    async def _persist(self, text: str | None, generation: int | None = None) -> None:
        if text is None:
            return
        if self.read_only:
            raise OSError("exchange store is read-only; snapshot not persisted")
        if generation is None:
            self._generation += 1
            generation = self._generation
        await asyncio.to_thread(self._write_snapshot, text, generation)

    # -- housekeeping -------------------------------------------------------

    def _next_fence(self) -> int:
        self._fence += 1
        return self._fence

    def _reap(self, now: float) -> bool:
        """Return expired leases to `pending`, fencing the vanished holder out,
        and prune failed units past their retention window.

        Called at the top of every mutating path, not just `claim`: a submit
        arriving after its lease expired must be rejected even when nobody
        claimed the unit in the interim.

        Pruning lives here rather than a separate call site because every
        mutating path already runs this unconditionally. Without it, nothing
        ever removes a unit from self._units -- max_units would cap units
        ever offered for the life of the state file, not units concurrently
        pending. Awaiting-verification proposals intentionally remain until a
        future coordinator acknowledgement/resolution path can retain their
        artifacts elsewhere.
        """

        changed = False
        stale_units = []
        for unit_id, unit in self._units.items():
            if unit.status == STATUS_CLAIMED:
                if unit.lease_expires_at is not None and unit.lease_expires_at > now:
                    continue
                unit.status = STATUS_PENDING
                unit.claimed_by = None
                unit.lease_token = None
                unit.lease_expires_at = None
                unit.fence = self._next_fence()
                changed = True
                continue
            if (
                unit.status == STATUS_FAILED
                and unit.resolved_at is not None
                and now - unit.resolved_at >= self.terminal_retention_seconds
            ):
                stale_units.append(unit_id)
        for unit_id in stale_units:
            del self._units[unit_id]
            # Receipts are tied to the unit they accepted. Retaining one after
            # pruning a failed unit would turn a stale delivery into a false
            # acknowledgement with no surviving proposal behind it.
            for receipt_id, receipt in list(self._receipts.items()):
                if isinstance(receipt, dict) and receipt.get("unitId") == unit_id:
                    del self._receipts[receipt_id]
            changed = True
        return changed

    def _require_worker(self, worker_id: str, now: float) -> Worker:
        worker = self._workers.get(worker_id)
        if worker is None:
            raise UnknownWorker("enroll before claiming work")
        if now - worker.window_started >= self.rate_limit_window:
            worker.window_started = now
            worker.window_calls = 0
        worker.window_calls += 1
        if worker.window_calls > self.rate_limit_calls:
            raise RateLimited(f"worker exceeded {self.rate_limit_calls} calls per {self.rate_limit_window:g}s")
        worker.last_seen = now
        return worker

    # -- coordinator side ---------------------------------------------------

    async def offer(self, *, lane: str, payload: dict[str, Any], required_capabilities: Any = None) -> str:
        """Publish a unit of work. Idempotent by content address."""

        if lane not in LANES:
            raise ValueError(f"unknown lane: {lane!r}")
        if not isinstance(payload, dict):
            raise ValueError("work unit payload must be an object")
        assert_portable_payload(payload)
        unit_id = derive_unit_id(lane, payload)
        async with self._lock:
            self._load()
            now = self.clock()
            self._reap(now)
            if unit_id not in self._units:
                if len(self._units) >= self.max_units:
                    raise CapacityExceeded(f"exchange already holds its cap of {self.max_units} units")
                self._units[unit_id] = WorkUnit(
                    unit_id=unit_id,
                    lane=lane,
                    payload=payload,
                    required_capabilities=required_capabilities_for(lane, required_capabilities),
                    offered_at=now,
                )
            text = self._snapshot_text()
            generation = self._generation
            # An initial write can fail after it mutates memory. Do not let a
            # content-addressed replay acknowledge the offer until it makes
            # the current state durable; keeping the lock prevents a later
            # mutation from overtaking this snapshot.
            await self._persist(text, generation)
            return unit_id

    async def unit_state(self, unit_id: str) -> dict[str, Any] | None:
        """Coordinator-side read of one unit, including any proposal against it."""

        async with self._lock:
            self._load()
            self._reap(self.clock())
            unit = self._units.get(unit_id)
            return unit.state_view() if unit is not None else None

    async def acknowledge_forwarded(self, unit_id: str, *, fingerprint: str, destination: str) -> bool:
        """Record durable queue delivery; this never asserts verification.

        Keep the proposal awaiting verification even after every current
        destination is forwarded: future producers may add another destination.
        """

        async with self._lock:
            self._load()
            unit = self._units.get(unit_id)
            if unit is None or unit.status != STATUS_AWAITING_VERIFICATION or unit.lane != "rewrite":
                return False
            submission = unit.submission
            if submission is None or submission.get("fingerprint") != fingerprint:
                return False
            forwarded = submission.setdefault("forwarded", {})
            if destination in forwarded:
                return True
            forwarded[destination] = {"state": "forwarded", "forwardedAt": self.clock()}
            try:
                await self._persist(self._snapshot_text(), self._generation)
            except BaseException:
                # A failed acknowledgement must remain retryable in this
                # process too. The queue receipt makes redelivery harmless.
                del forwarded[destination]
                raise
            return True

    async def roster(self) -> dict[str, Any]:
        async with self._lock:
            self._load()
            now = self.clock()
            changed = self._reap(now)
            by_status: dict[str, int] = {}
            by_lane: dict[str, int] = {}
            for unit in self._units.values():
                by_status[unit.status] = by_status.get(unit.status, 0) + 1
                by_lane[unit.lane] = by_lane.get(unit.lane, 0) + 1
            window = [lane for stamp, lane in self._recent if now - stamp <= THROUGHPUT_WINDOW_SECONDS]
            per_lane: dict[str, int] = {}
            for lane in window:
                per_lane[lane] = per_lane.get(lane, 0) + 1
            snapshot = {
                "claimBoundary": CLAIM_BOUNDARY,
                "workers": [worker.state_view() for worker in self._workers.values()],
                "units": {"byStatus": by_status, "byLane": by_lane, "total": len(self._units)},
                "throughput": {"windowSeconds": THROUGHPUT_WINDOW_SECONDS, "submissions": len(window), "byLane": per_lane},
            }
            text = self._snapshot_text() if changed else None
            generation = self._generation
        await self._persist(text, generation)
        return snapshot

    # -- fulfiller side -----------------------------------------------------

    async def enroll(self, *, capabilities: Any, agent: str) -> dict[str, Any]:
        """Register a fulfiller.

        Metered globally, not per worker. The per-worker limiter cannot bound
        enrollment by construction: a client that hits 429 just enrolls again
        and gets a fresh budget, so without this the effective ceiling is
        max_workers * rate_limit_calls from a single unauthenticated client,
        and each of those enrollments writes a full snapshot to disk.
        """

        async with self._lock:
            self._load()
            now = self.clock()
            self._reap(now)
            if now - self._enroll_window_started >= self.rate_limit_window:
                self._enroll_window_started = now
                self._enroll_calls = 0
            self._enroll_calls += 1
            if self._enroll_calls > self.enroll_limit_calls:
                raise RateLimited(
                    f"exchange exceeded {self.enroll_limit_calls} enrollments per {self.rate_limit_window:g}s",
                )
            if len(self._workers) >= self.max_workers:
                self._evict_idle_workers(now)
            if len(self._workers) >= self.max_workers:
                raise CapacityExceeded(f"exchange already holds its cap of {self.max_workers} workers")
            worker_id = secrets.token_hex(8)
            self._workers[worker_id] = Worker(
                worker_id=worker_id,
                agent=str(agent or "anonymous")[:200],
                capabilities=frozenset(str(cap) for cap in capabilities or ()),
                enrolled_at=now,
                last_seen=now,
                window_started=now,
            )
            text = self._snapshot_text()
            generation = self._generation
        await self._persist(text, generation)
        return {"workerId": worker_id, "leaseSeconds": self.lease_seconds, "lanes": list(LANES)}

    def _evict_idle_workers(self, now: float) -> None:
        """Drop workers unseen for several lease periods, unless one holds a lease.

        A volunteer who closes the tab never says goodbye, so without this the
        roster grows until it hits the cap and locks new contributors out.
        """

        held = {unit.claimed_by for unit in self._units.values() if unit.status == STATUS_CLAIMED}
        idle_after = self.lease_seconds * 4
        stale = [w.worker_id for w in self._workers.values() if w.worker_id not in held and now - w.last_seen > idle_after]
        for worker_id in stale:
            del self._workers[worker_id]

    async def claim(self, *, worker_id: str, lanes: Any = None) -> dict[str, Any] | None:
        """Lease the oldest pending unit this worker is actually able to run.

        Returns `None` (the router's 204) rather than waiting for work: one
        parked request per idle volunteer is the fan-in hazard this exchange
        must not create.
        """

        wanted = {str(lane) for lane in lanes} if lanes else None
        async with self._lock:
            self._load()
            now = self.clock()
            worker = self._require_worker(worker_id, now)
            changed = self._reap(now)
            candidate: WorkUnit | None = None
            for unit in self._units.values():
                if unit.status != STATUS_PENDING:
                    continue
                if wanted is not None and unit.lane not in wanted:
                    continue
                if not unit.required_capabilities <= worker.capabilities:
                    continue
                if candidate is None or unit.offered_at < candidate.offered_at:
                    candidate = unit
            lease: dict[str, Any] | None = None
            if candidate is not None:
                candidate.status = STATUS_CLAIMED
                candidate.claimed_by = worker_id
                candidate.lease_token = secrets.token_hex(16)
                candidate.lease_expires_at = now + self.lease_seconds
                candidate.fence = self._next_fence()
                lease = {
                    "unit": candidate.offer_view(),
                    "leaseToken": candidate.lease_token,
                    "fence": candidate.fence,
                    "leaseExpiresAt": candidate.lease_expires_at,
                }
            # An empty claim is the common case for a polling worker; only a
            # real state change is worth a disk write.
            text = self._snapshot_text() if changed or lease is not None else None
            generation = self._generation
        await self._persist(text, generation)
        return lease

    async def heartbeat(self, *, worker_id: str, lease_token: str) -> dict[str, Any]:
        async with self._lock:
            self._load()
            now = self.clock()
            self._require_worker(worker_id, now)
            changed = self._reap(now)
            unit = self._unit_for_lease(worker_id, lease_token)
            if unit is None:
                raise LeaseRejected("lease expired or superseded; claim again")
            unit.lease_expires_at = now + self.lease_seconds
            result = {"unitId": unit.unit_id, "fence": unit.fence, "leaseExpiresAt": unit.lease_expires_at}
            # Heartbeats are the hottest endpoint and a lease deadline does not
            # survive a restart anyway (a reloaded claim is re-offered), so only
            # a reclaim is worth persisting here.
            text = self._snapshot_text() if changed else None
            generation = self._generation
        await self._persist(text, generation)
        return result

    def _unit_for_lease(self, worker_id: str, lease_token: str) -> WorkUnit | None:
        for unit in self._units.values():
            if unit.status == STATUS_CLAIMED and unit.lease_token == lease_token and unit.claimed_by == worker_id:
                return unit
        return None

    @staticmethod
    def _receipt_id(worker_id: str, idempotency_key: str) -> str:
        """A v2 receipt key that cannot collide across workers.

        v1 stored receipts directly under a client-selected idempotency key.
        Keep those rows loadable, but never look them up as replay receipts:
        they do not bind a worker or lease safely enough to acknowledge work.
        """

        identity = json.dumps([worker_id, idempotency_key], separators=(",", ":"))
        return "v2:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()

    @staticmethod
    def _valid_receipt(receipt: Any, *, worker_id: str, idempotency_key: str) -> bool:
        """Whether a persisted v2 receipt can safely answer a replay."""

        return (
            isinstance(receipt, dict)
            and receipt.get("workerId") == worker_id
            and receipt.get("idempotencyKey") == idempotency_key
            and isinstance(receipt.get("unitId"), str)
            and isinstance(receipt.get("leaseToken"), str)
            and isinstance(receipt.get("fence"), int)
            and isinstance(receipt.get("fingerprint"), str)
            and isinstance(receipt.get("response"), dict)
            and receipt["response"].get("unitId") == receipt["unitId"]
        )

    @staticmethod
    def _validate_submission(unit: WorkUnit, artifact: Any) -> None:
        """Reject unusable lane-specific proposals before retiring a lease."""

        if not isinstance(artifact, dict):
            raise InvalidSubmission("submission artifact must be an object")
        try:
            artifact_size = len(json.dumps(artifact).encode("utf-8"))
        except (TypeError, ValueError, UnicodeEncodeError) as exc:
            raise InvalidSubmission("submission artifact must be portable JSON") from exc
        if artifact_size > MAX_ARTIFACT_BYTES:
            raise InvalidSubmission(f"artifact exceeds {MAX_ARTIFACT_BYTES} bytes when serialized")
        if unit.lane != "rewrite":
            return
        source = artifact.get("source")
        if not isinstance(source, str) or not source.strip() or "\x00" in source:
            raise InvalidSubmission("rewrite completion requires a non-empty source artifact")

    async def submit(
        self,
        *,
        worker_id: str,
        lease_token: str,
        fence: int,
        idempotency_key: str,
        artifact: dict[str, Any],
        verdict: str,
    ) -> dict[str, Any]:
        """Record a proposal against a leased unit. Commits nothing.

        Idempotency copies `react_api.submit_batch`: the client chooses the key,
        the server derives the fingerprint from the content. A receipt is scoped
        to that worker and bound to its original lease/unit, so duplicate
        delivery is harmless but key reuse cannot acknowledge different work.
        The receipt is consulted before the active lease is validated, so an
        exact retry that outlived its lease reports its original outcome.
        """

        fingerprint = hashlib.sha256(json.dumps({"artifact": artifact, "verdict": verdict}, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        async with self._lock:
            self._load()
            now = self.clock()
            worker = self._require_worker(worker_id, now)
            self._reap(now)
            receipt = self._receipts.get(self._receipt_id(worker_id, idempotency_key))
            if receipt is not None:
                if not self._valid_receipt(receipt, worker_id=worker_id, idempotency_key=idempotency_key):
                    # v1 rows are intentionally not idempotent: their global,
                    # key-only identity cannot prove which lease created them.
                    receipt = None
            if receipt is not None:
                if receipt.get("fingerprint") != fingerprint:
                    raise IdempotencyConflict("submission key already belongs to different work")
                if receipt["leaseToken"] != lease_token or receipt["fence"] != int(fence):
                    raise IdempotencyConflict("submission key already belongs to a different lease")
                # The initial write may have failed after mutating memory. A
                # replay must make the current state durable before confirming
                # success, while holding the lock so no later mutation races
                # this submission's snapshot.
                text = self._snapshot_text()
                generation = self._generation
                await self._persist(text, generation)
                return dict(receipt["response"])
            unit = self._unit_for_lease(worker_id, lease_token)
            if unit is None or unit.fence != int(fence):
                raise LeaseRejected("lease expired or fenced out by a newer claim; the result was discarded")
            self._validate_submission(unit, artifact)
            unit.status = STATUS_FAILED if str(verdict) in FAILURE_VERDICTS else STATUS_AWAITING_VERIFICATION
            unit.resolved_at = now
            unit.submission = {
                "workerId": worker_id,
                "verdict": str(verdict),
                "artifact": artifact,
                "fingerprint": fingerprint,
                "idempotencyKey": idempotency_key,
                "submittedAt": now,
                "claimBoundary": CLAIM_BOUNDARY,
            }
            # Retire the lease. A raw replay now lands on the receipt above
            # instead of being accepted a second time.
            unit.lease_token = None
            unit.lease_expires_at = None
            unit.fence = self._next_fence()
            worker.submissions += 1
            self._recent.append((now, unit.lane))
            response = {"accepted": True, "state": unit.status, "unitId": unit.unit_id, "verdict": str(verdict)}
            self._receipts[self._receipt_id(worker_id, idempotency_key)] = {
                "workerId": worker_id,
                "idempotencyKey": idempotency_key,
                "unitId": unit.unit_id,
                "leaseToken": lease_token,
                "fence": int(fence),
                "fingerprint": fingerprint,
                "response": response,
            }
            text = self._snapshot_text()
            generation = self._generation
            # Submission success is an external acknowledgement. Do not return
            # it until this exact snapshot reaches disk; lock scope also keeps
            # another mutation from overtaking it while the write runs off-loop.
            await self._persist(text, generation)
            return dict(response)
