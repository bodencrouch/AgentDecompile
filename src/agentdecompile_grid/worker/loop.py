"""The work loop: pull frontier → filter by proven capability and budget → INTENT → run under a kill
deadline → result objects + RESULT record through the outbox → release the intent.

``WorkLoop.step()`` is a state machine, not a thread: one call does **one** action in a fixed
priority order and returns a named ``StepEvent`` — reap a finished or expired job, renew an
intent, flush the outbox, pull the frontier, launch one task — or ``idle`` with ``next_due_s`` so
a driver can sleep exactly that long.  The clock (monotonic, for deadlines), the wall clock (for
intent expiry, comparable across nodes) and the RNG (candidate choice, jitter) are injected, so a
harness can drive the loop deterministically and step through kill deadlines with a fake clock
and a fake sandbox.  Nothing in a step blocks: kills are two-phase (``sandbox``), flushes carry a
deadline (``outbox``), and a job whose group survives SIGKILL is parked as an orphan and polled,
never waited for.

Selection is RNG-shuffled among eligible tasks (every free slot on every node picking the same
advert is the thundering herd the mesh review named).  Poison = at least ``poison_timeouts``
*distinct keys* timing out across at least ``poison_min_lineages`` independent lineages (a slow
node counts once, however often it times out); keys are the records' authenticated signers, never
a body's claim (``records``); the node that observes the threshold appends the POISON record;
duplicates are harmless.  A task the node itself timed out or errored on is put in
a local cool-off so the same node does not immediately retry it.

``--idle-only`` is admission control: while the idle policy says busy no new task launches
(``idle(reason=policy:busy)``); running tasks finish inside their budgets; ``preempt_on_busy``
aborts running tasks of MEDIUM and above without recording a result.

Acceptance tests named for the final verification phase (U124):
  * ``test_sleep_forever_killed_and_recorded``: a kind that sleeps forever is killed at its class
    deadline; a RESULT(status=timeout) record and a released INTENT are in the outbox within
    deadline + 5 s of fake clock.
  * ``test_three_independent_timeouts_poison``: timeouts from three keys across two lineages
    yield one POISON record; three timeouts from one lineage do not.
  * ``test_duplicate_execution_one_object``: two loops running the same task produce the same
    result object and the second upload is a no-op.
  * ``test_step_priority_order``: with a finished job, a due flush and a ready task, three steps
    return collected, flushed, launched in that order.
  * ``test_unbounded_refused_by_name``: an UNBOUNDED task is never launched and is counted under
    ``budget-unbounded`` in the pulled event.
  * ``test_idle_only_admission``: a busy idle policy yields ``idle(policy:busy)`` and launches
    nothing; running tasks are left to finish.
"""
from __future__ import annotations

import os
import random
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence

from ..core import TASK_KINDS, BudgetClass, Frontier, LogStore, NodeIdentity, NotConfigured, ObjectRef, ObjectStore, RecordType, Refused, ResultStatus, TaskResult, TaskSpec
from ..verify.policy import DEFAULT_INDEPENDENCE_POLICY, KeyRateLimiter, TokenBucket, independent_groups
from .outbox import Outbox, PendingRecord, RecordWriter
from .records import LineageLookup, has_poison, intent_body, note_body, poison_body, read_timeouts, result_body, results_pointer, task_result_from_record, task_result_to_bytes
from .sandbox import DEFAULT_GRACE_S, DEFAULT_LIMITS, JobOutcome, RunningJob, Sandbox, SandboxJob, deadline_for

DEFAULT_BUDGETS_ALLOWED: tuple[BudgetClass, ...] = (BudgetClass.MICRO, BudgetClass.SMALL, BudgetClass.MEDIUM)
FLEET_BUDGETS_ALLOWED: tuple[BudgetClass, ...] = (*DEFAULT_BUDGETS_ALLOWED, BudgetClass.LARGE)
STEP_ORDER = ("reap", "renew", "flush", "pull", "launch")


# --------------------------------------------------------------------------- config and events
@dataclass(frozen=True)
class WorkerConfig:
    """Everything the loop needs from ``GridConfig`` (the config slice embeds/produces this)."""

    cores: int = 1
    lanes: tuple[str, ...] = ()                       # kind names or kind ``lane`` attributes; empty = every registered kind
    budgets_allowed: tuple[BudgetClass, ...] = DEFAULT_BUDGETS_ALLOWED
    deadlines_s: Mapping[str, float] = field(default_factory=dict)   # by budget value or kind name (basis ``timeout_policy``)
    kill_grace_s: float = DEFAULT_GRACE_S
    intent_margin_s: float = 15.0                     # ttl = deadline + grace + margin
    intent_renew_fraction: float = 0.5
    frontier_ttl_s: float = 5.0
    flush_interval_s: float = 5.0
    flush_batch: int = 64
    flush_deadline_s: float = 30.0
    cooloff_s: float = 300.0
    poison_timeouts: int = 3
    poison_min_lineages: int = 2
    independence_policy: str = DEFAULT_INDEPENDENCE_POLICY
    admitted_bases: tuple[str, ...] = ()              # empty = any basis
    import_modules: tuple[str, ...] = ()
    launch_rate_per_minute: float = 120.0
    preempt_on_busy: bool = False
    preempt_budgets: tuple[BudgetClass, ...] = (BudgetClass.MEDIUM, BudgetClass.LARGE)
    limits: Mapping[str, int] | None = None
    env_extra: Mapping[str, str] = field(default_factory=dict)
    max_frontier_candidates: int = 4096
    done_memory_s: float = 3600.0                     # remember own results this long so an unflushed RESULT is not re-run here
    trust_unsigned_records: bool = False              # NullSigner laptop grids only: accept RESULT bodies with no signer

    @classmethod
    def from_grid_config(cls, cfg: Any, *, lanes: Sequence[str] | None = None, import_modules: Sequence[str] = (),
                         cores: int | None = None, admitted_bases: Sequence[str] | None = None) -> "WorkerConfig":
        """The loop's config from a ``GridConfig`` (``worker.*``, ``budgets.*``, ``outbox.*``, ``keyring.*``, ``tasks.*``)."""
        w, b = cfg.worker, cfg.budgets
        return cls(
            cores=int(cores if cores is not None else (w.cores or max(1, (os.cpu_count() or 2) // 2))),
            lanes=tuple(lanes if lanes is not None else w.lanes),
            budgets_allowed=tuple(cfg.budgets_allowed()),
            deadlines_s=dict(cfg.deadlines_s()),
            kill_grace_s=float(b.kill_grace_s),
            intent_margin_s=float(w.intent_margin_s),
            frontier_ttl_s=float(w.frontier_ttl_s),
            flush_interval_s=float(cfg.outbox.flush_interval_s),
            flush_batch=int(cfg.outbox.max_batch),
            flush_deadline_s=float(cfg.outbox.flush_deadline_s),
            cooloff_s=float(w.cooloff_s),
            poison_timeouts=int(w.poison_threshold),
            poison_min_lineages=int(w.poison_min_lineages),
            independence_policy=str(w.independence_policy),
            admitted_bases=tuple(admitted_bases if admitted_bases is not None else cfg.admitted_bases),
            import_modules=tuple(import_modules),
            launch_rate_per_minute=float(w.launch_rate_per_minute),
            preempt_on_busy=bool(w.preempt_on_busy),
            done_memory_s=float(w.done_memory_s),
            trust_unsigned_records=bool(cfg.keyring.allow_null),
        )


@dataclass(frozen=True)
class StepEvent:
    name: str
    detail: Mapping[str, Any] = field(default_factory=dict)
    next_due_s: float | None = None

    def to_record(self) -> dict[str, Any]:
        return {"name": self.name, "detail": dict(self.detail), "next_due_s": self.next_due_s}


class IdlePolicy(Protocol):
    name: str

    def should_run(self, now: float, *, running: int) -> bool: ...
    def describe(self) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class Upstream:
    """Where the outbox flushes to: the fabric's object store plus the log append path."""

    objects: ObjectStore
    writer: RecordWriter | None = None


@dataclass(frozen=True)
class Candidate:
    spec: TaskSpec
    deadline_s: float
    payload: Any = None                                # a Proposal for the verifier
    intent_extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class Slot:
    job: RunningJob
    candidate: Candidate
    deadline_at: float
    intent_nonce: str
    intent_ttl_s: float
    intent_expires_wall: float
    renew_at: float
    launched_at: float
    aborted: bool = False

    @property
    def spec(self) -> TaskSpec:
        return self.candidate.spec


@dataclass(frozen=True)
class PoisonVerdict:
    poisoned: bool
    keys: tuple[str, ...]
    lineages: int
    reason: str


class PoisonDetector:
    def __init__(self, *, threshold: int = 3, min_lineages: int = 2, policy: str = DEFAULT_INDEPENDENCE_POLICY) -> None:
        self.threshold = threshold
        self.min_lineages = min_lineages
        self.policy = policy

    def evaluate(self, timeouts: Iterable[tuple[str, Sequence[str]]]) -> PoisonVerdict:
        distinct: dict[str, tuple[str, ...]] = {}
        for key, lineage in timeouts:
            distinct.setdefault(key, tuple(lineage))
        groups = independent_groups(distinct.items(), policy=self.policy)
        keys = tuple(sorted(distinct))
        if len(keys) < self.threshold:
            return PoisonVerdict(False, keys, len(groups), f"timeouts:{len(keys)}<{self.threshold}")
        if len(groups) < self.min_lineages:
            return PoisonVerdict(False, keys, len(groups), f"lineages:{len(groups)}<{self.min_lineages}")
        return PoisonVerdict(True, keys, len(groups), "poison")


# --------------------------------------------------------------------------- the step machine
class StepMachine:
    """Shared skeleton of the work loop and the verifier loop: slots, intents, flush, pull, launch."""

    scope = "run"

    def __init__(self, *, identity: NodeIdentity, sandbox: Sandbox, outbox: Outbox, objects: ObjectStore, upstream: Upstream, frontier: Callable[[], Frontier],
                 store_locator: Mapping[str, Any], config: WorkerConfig | None = None, log: LogStore | None = None, idle_policy: IdlePolicy | None = None,
                 limiter: KeyRateLimiter | None = None, clock: Callable[[], float] = time.monotonic, wall: Callable[[], float] = time.time, rng: random.Random | None = None,
                 lineage_lookup: LineageLookup | None = None) -> None:
        signer_key = getattr(getattr(upstream.writer, "signer", None), "key_id", None)
        if signer_key is not None and signer_key != identity.key_id:
            # the producer/verifier identity *is* the record signer (log.records binds body key == signer_key)
            raise Refused(f"identity-not-signer:{identity.key_id[:12]}!={str(signer_key)[:12]}")
        self.identity = identity
        self.sandbox = sandbox
        self.outbox = outbox
        self.objects = objects
        self.upstream = upstream
        self.frontier = frontier
        self.store_locator = dict(store_locator)
        self.config = config or WorkerConfig()
        self.log = log
        self.idle_policy = idle_policy
        self.lineage_lookup = lineage_lookup           # key id -> attested lineage (signed enrolment record); None = trust the body's claim
        self.limiter = limiter
        self.clock = clock
        self.wall = wall
        self.rng = rng or random.Random()
        self.slots: list[Slot] = []
        self.orphans: list[RunningJob] = []
        self.cores = max(1, int(self.config.cores))
        self._frontier: Frontier | None = None
        self._frontier_at: float | None = None
        self._eligible: list[Candidate] = []
        self._skipped: dict[str, int] = {}
        self._cooloff: dict[str, float] = {}
        self._launch_bucket = TokenBucket(max(self.config.launch_rate_per_minute, 1e-6) / 60.0, max(1.0, self.config.launch_rate_per_minute / 6.0), clock=clock)
        self.events: list[StepEvent] = []
        self.counters: dict[str, int] = {}
        self.stopping = False
        self._idle_reason_override = ""
        self._last_policy_error = ""

    # -- public
    def step(self) -> StepEvent:
        now = self.clock()
        self._poll_orphans(now)
        for phase in STEP_ORDER:
            event = getattr(self, f"_{phase}")(now)
            if event is not None:
                self._note_event(event)
                return event
        event = StepEvent("idle", {"reason": self._idle_reason, "running": len(self.slots), "outbox": self.outbox.depth()}, next_due_s=self._next_due(now))
        self._note_event(event)
        return event

    def drive(self, *, stop: Callable[[], bool] = lambda: False, sleep: Callable[[float], None] = time.sleep, poll_s: float = 0.25, max_steps: int | None = None) -> int:
        """Real-time driver: step until ``stop()``; sleep only on ``idle`` and only until ``next_due_s``."""
        steps = 0
        while not stop() and (max_steps is None or steps < max_steps):
            event = self.step()
            steps += 1
            if event.name == "idle":
                sleep(max(0.0, min(poll_s, event.next_due_s if event.next_due_s is not None else poll_s)))
        return steps

    TERMINAL_EVENTS = frozenset({"collected", "timeout", "poison", "verified", "refuted", "unverifiable", "verify-timeout", "verify-error", "aborted", "launch-failed", "frontier-error"})

    def run_once(self, *, sleep: Callable[[float], None] = time.sleep, poll_s: float = 0.05, max_wall_s: float | None = None) -> dict[str, Any]:
        """``adgrid work --once`` / ``verify --once``: pull the frontier, launch at most one task, wait for
        it under its own kill deadline, collect it, flush the outbox; or stop as soon as nothing is
        eligible.  Bounded by the task's deadline (every job has one) and ``max_wall_s``."""
        started = self.clock()
        events: list[dict[str, Any]] = []
        launched = False
        stopped_by = ""
        was_stopping = self.stopping
        try:
            while True:
                event = self.step()
                events.append(event.to_record())
                if event.name == "launched":
                    launched = True
                    self.stopping = True            # one task per run_once: no second launch
                if event.name in self.TERMINAL_EVENTS and not self.slots and (launched or event.name == "frontier-error"):
                    stopped_by = event.name
                    break
                if event.name == "idle":
                    if self.slots:
                        sleep(max(0.0, min(poll_s, event.next_due_s if event.next_due_s is not None else poll_s)))
                    elif launched or (self.counters.get("pulls", 0) and not self._eligible):
                        stopped_by = f"idle:{event.detail.get('reason', '')}"
                        break
                if max_wall_s is not None and self.clock() - started >= max_wall_s:
                    stopped_by = "max-wall"
                    break
        finally:
            self.stopping = was_stopping
        flush = self.force_flush()
        return {"stopped_by": stopped_by, "launched": launched, "events": events, "flush": flush.to_record(), "status": self.status()}

    def release_all(self, reason: str = "leave") -> int:
        """Abort every running job (two-phase kill) and mark them so no RESULT is recorded."""
        now = self.clock()
        self.stopping = True
        n = 0
        for slot in self.slots:
            if not slot.aborted:
                slot.aborted = True
                slot.job.request_kill(now)
                n += 1
        return n

    def set_cores(self, cores: int) -> None:
        self.cores = max(1, int(cores))

    def next_due(self, now: float | None = None) -> float:
        """Seconds until something needs attention (deadline, renewal, flush, frontier refresh)."""
        return self._next_due(self.clock() if now is None else now)

    def force_flush(self, *, deadline_s: float | None = None) -> StepEvent:
        report = self.outbox.flush(self.objects, self.upstream.objects, self.upstream.writer, deadline_s=deadline_s or self.config.flush_deadline_s, max_records=self.config.flush_batch, limiter=self.limiter, key_id=self.identity.key_id)
        self._bump("flushes")
        return StepEvent("flushed", report.to_record())

    def status(self) -> dict[str, Any]:
        now = self.clock()
        return {
            "scope": self.scope, "key_id": self.identity.key_id, "role": self.identity.role, "capabilities": list(self.identity.capabilities),
            "cores": self.cores, "running": [{"task_id": s.spec.task_id, "kind": s.spec.kind, "remaining_s": round(s.deadline_at - now, 1), "aborted": s.aborted} for s in self.slots],
            "orphans": len(self.orphans), "eligible": len(self._eligible), "skipped": dict(self._skipped), "cooloff": len(self._cooloff),
            "outbox": self.outbox.depth(), "counters": dict(self.counters), "stopping": self.stopping,
            "last_event": self.events[-1].to_record() if self.events else None,
        }

    # -- phases (each returns an event or None)
    def _reap(self, now: float) -> StepEvent | None:
        for slot in list(self.slots):
            state = slot.job.poll(now)
            if state == "running" and now >= slot.deadline_at:
                slot.job.request_kill(now)
                state = slot.job.poll(now)
            if state in ("exited", "kill-failed"):
                self.slots.remove(slot)
                outcome = slot.job.collect(now)
                if state == "kill-failed":
                    self.orphans.append(slot.job)
                event = self._collect(slot, outcome, now)
                if state != "kill-failed":
                    slot.job.cleanup()
                return event
        return None

    def _renew(self, now: float) -> StepEvent | None:
        for slot in self.slots:
            if not slot.aborted and now >= slot.renew_at:
                slot.renew_at = now + slot.intent_ttl_s * self.config.intent_renew_fraction
                slot.intent_expires_wall = self.wall() + slot.intent_ttl_s
                self._intent(slot.candidate, slot.intent_nonce, slot.intent_ttl_s, "renew")
                return StepEvent("renewed", {"task_id": slot.spec.task_id, "expires_at": slot.intent_expires_wall})
        return None

    def _flush(self, now: float) -> StepEvent | None:
        if not self.outbox.due(now, interval_s=self.config.flush_interval_s, batch=self.config.flush_batch):
            return None
        report = self.outbox.flush(self.objects, self.upstream.objects, self.upstream.writer, deadline_s=self.config.flush_deadline_s, max_records=self.config.flush_batch, limiter=self.limiter, key_id=self.identity.key_id)
        self._bump("flushes")
        return StepEvent("flushed", report.to_record())

    def _pull(self, now: float) -> StepEvent | None:
        stale = self._frontier_at is None or now - self._frontier_at >= self.config.frontier_ttl_s
        if not stale:
            return None
        try:
            frontier = self.frontier()
        except Exception as exc:
            self._frontier_at = now
            self._bump("frontier_errors")
            return StepEvent("frontier-error", {"exception": exc.__class__.__name__})
        self._frontier = frontier
        self._frontier_at = now
        self._skipped = {}
        self._eligible = self._candidates(frontier, now)
        self._bump("pulls")
        return StepEvent("pulled", {"ready": len(frontier.ready), "awaiting_verification": len(frontier.awaiting_verification), "poisoned": len(frontier.poisoned), "eligible": len(self._eligible), "skipped": dict(self._skipped)})

    def _launch(self, now: float) -> StepEvent | None:
        if self.stopping or len(self.slots) >= self.cores or not self._eligible:
            return None
        if self.idle_policy is not None:
            try:
                may_run = self.idle_policy.should_run(now, running=len(self.slots))
            except NotConfigured as exc:                  # a declared policy: named idle, never a dead driver
                self._idle_reason_override = f"policy:not-configured:{getattr(self.idle_policy, 'name', '?')}"
                self._bump("policy_not_configured")
                self._last_policy_error = str(exc)
                return None
            except Exception as exc:
                self._idle_reason_override = f"policy:error:{exc.__class__.__name__}"
                self._bump("policy_errors")
                return None
        else:
            may_run = True
        if not may_run:
            self._idle_reason_override = "policy:busy"
            if self.config.preempt_on_busy:
                aborted = [s for s in self.slots if not s.aborted and s.spec.budget in self.config.preempt_budgets]
                for slot in aborted:
                    slot.aborted = True
                    slot.job.request_kill(now)
                if aborted:
                    return StepEvent("preempted", {"tasks": [s.spec.task_id for s in aborted]})
            return None
        if not self._launch_bucket.take(1.0):
            self._idle_reason_override = "throttled:launch-rate"
            return None
        self._idle_reason_override = ""
        index = self.rng.randrange(len(self._eligible))
        candidate = self._eligible.pop(index)
        spec = candidate.spec
        if self._cooloff.get(spec.task_id, 0.0) > now:
            return StepEvent("skipped", {"task_id": spec.task_id, "reason": "cooloff"})
        try:
            job = self._make_job(candidate, now)
        except Exception as exc:                      # a missing result object, an unknown method: named, cooled off, never fatal to the loop
            self._cooloff[spec.task_id] = now + self.config.cooloff_s
            self._note(spec, "launch-failed", {"exception": exc.__class__.__name__, "message": str(exc)[:200]})
            self._bump("launch_failures")
            return StepEvent("launch-failed", {"task_id": spec.task_id, "kind": spec.kind, "exception": exc.__class__.__name__})
        ttl = candidate.deadline_s + self.config.kill_grace_s + self.config.intent_margin_s
        nonce = secrets.token_hex(8)
        self._intent(candidate, nonce, ttl, "hold")
        try:
            running = self.sandbox.launch(job)
        except Exception as exc:                      # SandboxError, NotConfigured, OSError: the intent is released and the task cooled off
            self._intent(candidate, nonce, ttl, "release")
            self._cooloff[spec.task_id] = now + self.config.cooloff_s
            self._note(spec, "launch-failed", {"exception": exc.__class__.__name__, "message": str(exc)[:200]})
            self._bump("launch_failures")
            return StepEvent("launch-failed", {"task_id": spec.task_id, "kind": spec.kind, "exception": exc.__class__.__name__})
        slot = Slot(job=running, candidate=candidate, deadline_at=running.started_at + candidate.deadline_s, intent_nonce=nonce, intent_ttl_s=ttl,
                    intent_expires_wall=self.wall() + ttl, renew_at=now + ttl * self.config.intent_renew_fraction, launched_at=now)
        self.slots.append(slot)
        self._bump("launches")
        return StepEvent("launched", {"task_id": spec.task_id, "kind": spec.kind, "deadline_s": candidate.deadline_s, "op": job.op, "job_id": job.job_id})

    # -- hooks for subclasses
    def _candidates(self, frontier: Frontier, now: float) -> list[Candidate]:
        raise NotImplementedError

    def _make_job(self, candidate: Candidate, now: float) -> SandboxJob:
        raise NotImplementedError

    def _collect(self, slot: Slot, outcome: JobOutcome, now: float) -> StepEvent:
        raise NotImplementedError

    # -- shared helpers
    @property
    def _idle_reason(self) -> str:
        if self._idle_reason_override:
            return self._idle_reason_override
        if self.stopping:
            return "stopping"
        if len(self.slots) >= self.cores:
            return "slots-full"
        if not self._eligible:
            return "nothing-eligible"
        return "waiting"

    def _next_due(self, now: float) -> float:
        dues = [max(0.0, self.config.frontier_ttl_s - (now - (self._frontier_at or now)))]
        for slot in self.slots:
            remaining = slot.deadline_at - now
            dues.append(remaining if remaining > 0 else 0.05)    # a kill in flight is polled, not spun on
            dues.append(max(0.0, slot.renew_at - now))
        if self.outbox.depth():
            dues.append(max(0.0, self.config.flush_interval_s - (now - self.outbox.last_flush_at)))
        if self._idle_reason_override.startswith("throttled"):
            dues.append(self._launch_bucket.retry_after_s(1.0))
        return min(dues) if dues else self.config.frontier_ttl_s

    def _skip(self, reason: str) -> None:
        self._skipped[reason] = self._skipped.get(reason, 0) + 1

    def _bump(self, counter: str, n: int = 1) -> None:
        self.counters[counter] = self.counters.get(counter, 0) + n

    def _note_event(self, event: StepEvent) -> None:
        self.events.append(event)
        del self.events[:-64]

    def _intent(self, candidate: Candidate, nonce: str, ttl_s: float, action: str) -> None:
        spec = candidate.spec
        body = intent_body(spec, self.identity, action=action, ttl_s=ttl_s, now_wall=self.wall(), nonce=nonce)
        body["scope"] = self.scope
        body.update(candidate.intent_extra)
        self.outbox.enqueue(record=PendingRecord(spec.partition_key, RecordType.INTENT, body, spec.basis_hash))

    def _note(self, spec: TaskSpec, note: str, detail: Mapping[str, Any]) -> None:
        self.outbox.enqueue(record=PendingRecord(spec.partition_key, RecordType.NOTE, note_body(spec.task_id, spec.kind, self.identity, note=note, detail=detail, nonce=secrets.token_hex(8)), spec.basis_hash))

    def _poll_orphans(self, now: float) -> None:
        for job in list(self.orphans):
            if job.poll(now) == "exited":
                self.orphans.remove(job)
                job.cleanup()
                self._bump("orphans_reaped")

    def _served_kinds(self) -> dict[str, Any]:
        kinds: dict[str, Any] = {}
        for name, kind in TASK_KINDS.items():
            lane = getattr(kind, "lane", name)
            if not self.config.lanes or name in self.config.lanes or lane in self.config.lanes:
                kinds[name] = kind
        return kinds


# --------------------------------------------------------------------------- the work loop
class WorkLoop(StepMachine):
    scope = "run"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.poison = PoisonDetector(threshold=self.config.poison_timeouts, min_lineages=self.config.poison_min_lineages, policy=self.config.independence_policy)
        self._local_timeouts: dict[str, dict[str, tuple[str, ...]]] = {}
        self._poisoned: set[str] = set()
        self._done_local: dict[str, float] = {}

    def _candidates(self, frontier: Frontier, now: float) -> list[Candidate]:
        kinds = self._served_kinds()
        proven = set(self.identity.capabilities)
        running = {s.spec.task_id for s in self.slots}
        out: list[Candidate] = []
        for spec in list(frontier.ready)[: self.config.max_frontier_candidates]:
            if spec.kind not in kinds:
                self._skip("kind-not-served")
            elif spec.budget == BudgetClass.UNBOUNDED:
                self._skip("budget-unbounded")
            elif spec.budget not in self.config.budgets_allowed:
                self._skip(f"budget-not-allowed:{spec.budget.value}")
            elif not set(spec.capabilities) <= proven:
                self._skip("capability-missing")
            elif self.config.admitted_bases and spec.basis_hash not in self.config.admitted_bases:
                self._skip("basis-not-admitted")
            elif spec.task_id in running:
                self._skip("running-here")
            elif self._done_local.get(spec.task_id, 0.0) > now:
                self._skip("done-here")
            elif spec.task_id in self._poisoned or spec.task_id in set(frontier.poisoned):
                self._skip("poisoned")
            elif self._cooloff.get(spec.task_id, 0.0) > now:
                self._skip("cooloff")
            else:
                try:
                    deadline = deadline_for(spec, self.config.deadlines_s)
                except Refused as exc:
                    self._skip(exc.reason.split(":", 1)[0])
                    continue
                out.append(Candidate(spec, deadline))
        for memory in (self._cooloff, self._done_local):
            for task_id, until in list(memory.items()):
                if until <= now:
                    del memory[task_id]
        return out

    def _make_job(self, candidate: Candidate, now: float) -> SandboxJob:
        spec = candidate.spec
        return SandboxJob(
            job_id=f"run-{spec.task_id[:16]}-{secrets.token_hex(4)}", op="run", spec=spec, key_id=self.identity.key_id, lineage=tuple(self.identity.invite_lineage),
            deadline_s=candidate.deadline_s, store_locator=self.store_locator, import_modules=tuple(self.config.import_modules), grace_s=self.config.kill_grace_s,
            limits=dict(self.config.limits) if self.config.limits is not None else dict(DEFAULT_LIMITS), env_extra=dict(self.config.env_extra),
        )

    def _collect(self, slot: Slot, outcome: JobOutcome, now: float) -> StepEvent:
        spec = slot.spec
        if slot.aborted:
            self._intent(slot.candidate, slot.intent_nonce, slot.intent_ttl_s, "release")
            self._bump("aborted")
            return StepEvent("aborted", {"task_id": spec.task_id, "kind": spec.kind, "status": outcome.status})
        result = self._result_for(slot, outcome)
        result_ref = self.objects.put(task_result_to_bytes(result))
        self.outbox.enqueue(
            objects=[*result.outputs.values(), result_ref], named=[(results_pointer(spec.task_id, self.identity.key_id), str(result_ref))],
            record=PendingRecord(spec.partition_key, RecordType.RESULT, result_body(spec, result, result_ref, self.identity, deadline_s=slot.candidate.deadline_s, nonce=slot.intent_nonce), spec.basis_hash),
        )
        self._intent(slot.candidate, slot.intent_nonce, slot.intent_ttl_s, "release")
        self._bump(f"results_{result.status.value}")
        if result.status in (ResultStatus.OK, ResultStatus.REFUSED):
            self._done_local[spec.task_id] = now + self.config.done_memory_s
        detail: dict[str, Any] = {"task_id": spec.task_id, "kind": spec.kind, "status": result.status.value, "result_ref": str(result_ref), "elapsed_s": round(result.elapsed_s, 3), "reason": result.reason}
        if result.status in (ResultStatus.TIMEOUT, ResultStatus.ERROR):
            self._cooloff[spec.task_id] = now + self.config.cooloff_s
        if result.status == ResultStatus.TIMEOUT:
            verdict = self._poison_check(spec)
            detail["poison"] = {"keys": list(verdict.keys), "lineages": verdict.lineages, "reason": verdict.reason}
            if verdict.poisoned:
                return StepEvent("poison", detail)
            return StepEvent("timeout", detail)
        return StepEvent("collected", detail)

    def _result_for(self, slot: Slot, outcome: JobOutcome) -> TaskResult:
        spec = slot.spec
        key = self.identity.key_id
        metrics: dict[str, Any] = {"stderr_digest": outcome.stderr_digest, "exit_code": outcome.exit_code}
        if outcome.status == "ok" and outcome.payload is not None:
            try:
                result = task_result_from_record(outcome.payload)
            except (KeyError, ValueError):
                return TaskResult(spec.task_id, ResultStatus.ERROR, {}, key, spec.basis_hash, outcome.elapsed_s, reason="result-unparseable", metrics=metrics)
            if result.task_id != spec.task_id or result.basis_hash != spec.basis_hash or result.producer_key != key:
                return TaskResult(spec.task_id, ResultStatus.ERROR, {}, key, spec.basis_hash, outcome.elapsed_s, reason="result-mismatch", metrics=metrics)
            missing = [name for name, ref in result.outputs.items() if not self.objects.exists(ObjectRef(ref))]
            if missing:
                return TaskResult(spec.task_id, ResultStatus.ERROR, {}, key, spec.basis_hash, outcome.elapsed_s, reason=f"missing-output:{sorted(missing)[0]}", metrics=metrics)
            return result
        if outcome.status in ("timeout", "kill-failed"):
            reason = f"deadline:{spec.budget.value}:{slot.candidate.deadline_s:.0f}" + (";kill-failed" if outcome.status == "kill-failed" else "")
            metrics["kill_action"] = outcome.kill_action
            return TaskResult(spec.task_id, ResultStatus.TIMEOUT, {}, key, spec.basis_hash, slot.candidate.deadline_s, reason=reason, metrics=metrics)
        return TaskResult(spec.task_id, ResultStatus.ERROR, {}, key, spec.basis_hash, outcome.elapsed_s, reason=outcome.error_class or f"exit:{outcome.exit_code}", metrics=metrics)

    def _poison_check(self, spec: TaskSpec) -> PoisonVerdict:
        local = self._local_timeouts.setdefault(spec.task_id, {})
        local[self.identity.key_id] = tuple(self.identity.invite_lineage)
        seen: dict[str, tuple[str, ...]] = dict(local)
        if self.log is not None:
            try:
                for key, lineage in read_timeouts(self.log, spec.partition_key, spec.task_id, trust_unsigned=self.config.trust_unsigned_records, lineage_lookup=self.lineage_lookup):
                    seen.setdefault(key, tuple(lineage))
            except Exception:
                self._bump("log_read_errors")
        verdict = self.poison.evaluate(seen.items())
        if verdict.poisoned and spec.task_id not in self._poisoned:
            already = False
            if self.log is not None:
                try:
                    already = has_poison(self.log, spec.partition_key, spec.task_id)
                except Exception:
                    already = False
            self._poisoned.add(spec.task_id)
            if not already:
                self.outbox.enqueue(record=PendingRecord(spec.partition_key, RecordType.POISON, poison_body(spec, self.identity, timeouts=verdict.keys, lineages=verdict.lineages, threshold=self.poison.threshold, nonce=secrets.token_hex(8)), spec.basis_hash))
                self._bump("poison_records")
        return verdict


__all__ = [
    "Candidate", "DEFAULT_BUDGETS_ALLOWED", "FLEET_BUDGETS_ALLOWED", "IdlePolicy", "PoisonDetector", "PoisonVerdict", "STEP_ORDER", "Slot", "StepEvent",
    "StepMachine", "Upstream", "WorkLoop", "WorkerConfig",
]
