"""The verifier loop: independent-key machine checks of proposals, VERIFIED/REFUTED records, proposal caps.

Same step machine as the work loop (``worker.loop.StepMachine``): one action per ``step()``,
injected clocks and RNG, jobs in the sandbox with the kind's kill deadline.  What differs is the
candidate set and what a collected outcome means:

* candidates come from ``frontier.awaiting_verification``; the task's spec is looked up
  (``task_lookup``), its proposals are read from RESULT records in the partition log
  (``records.read_results``; a body whose ``producer_key`` is not the record's signer is not a
  proposal), capped at ``proposal_cap`` in seq order (later ones are ignored as ``over-cap``),
  reduced to claims (status OK) without a verdict, whose signer is not this key, not revoked, and
  **independent** under the configured policy (lineage-disjoint by default; the lineage comes
  from ``lineage_lookup`` when the fabric attests it, else from the body — see ``records``);
  a candidate with several proposals verifies the higher-weight producer first (penalties lower
  weight; they never gate).
* the check is the kind's own ``verify()`` (op ``verify``) or a ``VERIFIERS`` method chosen by
  ``methods_by_kind`` / the kind's ``verify_method`` attribute (op ``method``).
* VERIFIED and REFUTED become records; REFUTED also penalises the producer key (weight only).
  UNVERIFIABLE, a verifier timeout or an error write a NOTE (never load-bearing) and put the
  proposal in a local cool-off; **a slow or failing verifier never refutes**.

Ordering: the node-level tick (``worker.agent.LocalAgent.tick``) steps the verifier before the
work loop, so verification is offered before generation on every node; the frontier itself does
the same ordering globally (design §2.6).  A donor-role identity cannot construct this loop
(design §9.2 T4: donor keys are never verifier keys) — refused by name.

Acceptance tests named for the final verification phase (U127):
  * ``test_never_self_verifies``: a VERIFIED record is never produced by the producing key or by
    a key sharing its lineage; the candidate is counted under ``not-independent``.
  * ``test_fifth_proposal_ignored``: with five proposals for one task only the first four are
    candidates and the fifth is counted ``over-cap``.
  * ``test_refuted_penalises_weight_only``: a REFUTED record halves the producer's weight and
    changes nothing else; the task stays offered to other keys.
  * ``test_verifier_timeout_is_not_refutation``: a verify job killed at its deadline yields a
    NOTE and no REFUTED record.
  * ``test_donor_cannot_verify``: constructing the loop with a donor identity raises ``Refused``.
  * ``test_byte_emitter_refuted``: (with the parity lane) an object equal to the target with junk
    source is refuted by recompute.
"""
from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Mapping, Sequence

from ..core import TASK_KINDS, VERIFIERS, Frontier, GridError, LogStore, NodeIdentity, RecordType, Refused, TaskSpec, VerificationOutcome, canonical_json, check_basis_projection
from ..worker.identity import ROLE_MAY_VERIFY
from ..worker.loop import Candidate, Slot, StepEvent, StepMachine, WorkerConfig
from ..worker.outbox import PendingRecord
from ..worker.records import Proposal, read_results, read_verdicts, task_result_from_record, verification_body, verification_from_record
from ..worker.sandbox import DEFAULT_LIMITS, JobOutcome, SandboxJob, deadline_for
from ..tasks.results import verification_name, verification_to_record
from .policy import DEFAULT_INDEPENDENCE_POLICY, PenaltyLedger, RevocationList, check_independence

DEFAULT_PROPOSAL_CAP = 4              # design §2.6 / Q8
INLINE_EVIDENCE_LIMIT = 8 * 1024      # larger evidence becomes an object referenced by evidence_ref


@dataclass(frozen=True)
class VerifierConfig:
    proposal_cap: int = DEFAULT_PROPOSAL_CAP
    verifier_roles: tuple[str, ...] = tuple(sorted(ROLE_MAY_VERIFY))
    independence_policy: str = DEFAULT_INDEPENDENCE_POLICY
    methods_by_kind: Mapping[str, str] = field(default_factory=dict)     # kind -> VERIFIERS name; absent = the kind's own verify()
    default_method: str = ""                                            # "" = kind.verify(); else a VERIFIERS name for kinds without one
    worker: WorkerConfig = field(default_factory=lambda: WorkerConfig(cores=1))
    max_tasks_per_pull: int = 256

    @classmethod
    def from_grid_config(cls, cfg: Any, *, lanes: Sequence[str] | None = None, import_modules: Sequence[str] = (),
                         admitted_bases: Sequence[str] | None = None) -> "VerifierConfig":
        """``verifier.*`` plus the worker knobs the step machine shares (``WorkerConfig.from_grid_config``, one core)."""
        v = cfg.verifier
        return cls(
            proposal_cap=int(v.proposal_cap), independence_policy=str(cfg.worker.independence_policy),
            methods_by_kind=dict(v.methods_by_kind), default_method=str(v.default_method),
            worker=WorkerConfig.from_grid_config(cfg, lanes=lanes, import_modules=import_modules, cores=1, admitted_bases=admitted_bases),
            max_tasks_per_pull=int(v.max_tasks_per_pull),
        )


class VerifierLoop(StepMachine):
    scope = "verify"

    def __init__(self, *, identity: NodeIdentity, task_lookup: Callable[[str], TaskSpec | None], log: LogStore, config: VerifierConfig | None = None,
                 penalties: PenaltyLedger | None = None, revocations: RevocationList | None = None, **kwargs: Any) -> None:
        self.vconfig = config or VerifierConfig()
        if identity.role not in self.vconfig.verifier_roles:
            raise Refused(f"verifier-role-refused:{identity.role}", candidates=[{"allowed_roles": list(self.vconfig.verifier_roles)}])
        super().__init__(identity=identity, log=log, config=self.vconfig.worker, **kwargs)
        self.task_lookup = task_lookup
        self.penalties = penalties or PenaltyLedger()
        self.revocations = revocations or RevocationList()
        self._verdicts_local: set[tuple[str, str]] = set()     # (task_id, result_ref) verdicts this node wrote (outbox may not be flushed yet)

    # -- candidates
    def _candidates(self, frontier: Frontier, now: float) -> list[Candidate]:
        assert self.log is not None
        kinds = self._served_kinds()
        running = {(s.spec.task_id, str(s.candidate.payload.result_ref)) for s in self.slots if isinstance(s.candidate.payload, Proposal)}
        out: list[Candidate] = []
        partition_cache: dict[str, tuple[dict[str, list[Proposal]], dict[str, set[str]]]] = {}

        def partition_view(partition: str) -> tuple[dict[str, list[Proposal]], dict[str, set[str]]]:
            if partition not in partition_cache:            # one pass over the partition per pull, however many tasks await
                by_task: dict[str, list[Proposal]] = {}
                for proposal in read_results(
                    self.log, partition, trust_unsigned=self.config.trust_unsigned_records,
                    lineage_lookup=self.lineage_lookup, keyring=self.keyring,
                ):
                    by_task.setdefault(proposal.task_id, []).append(proposal)
                decided_by_task: dict[str, set[str]] = {}
                for body in read_verdicts(
                    self.log, partition, task_id=None, keyring=self.keyring,
                    trust_unsigned=self.config.trust_unsigned_records,
                ):
                    decided_by_task.setdefault(str(body.get("task_id")), set()).add(str(body.get("result_ref")))
                partition_cache[partition] = (by_task, decided_by_task)
            return partition_cache[partition]

        for task_id in list(frontier.awaiting_verification)[: self.vconfig.max_tasks_per_pull]:
            spec = self.task_lookup(task_id)
            if spec is None:
                self._skip("unknown-task")
                continue
            if spec.kind not in kinds:
                self._skip("kind-not-served")
                continue
            if not set(spec.capabilities) <= set(self.identity.capabilities):
                self._skip("capability-missing")
                continue
            if self.config.admitted_bases and spec.basis_hash not in self.config.admitted_bases:
                self._skip("basis-not-admitted")
                continue
            try:
                check_basis_projection(kinds[spec.kind], spec)          # U158: verify refuses a projection mismatch by name
            except Refused as exc:
                self._skip(exc.reason.split(":", 1)[0])
                continue
            try:
                deadline = deadline_for(spec, self.config.deadlines_s)
            except Refused:
                self._skip("budget-unbounded")
                continue
            try:
                by_task, decided_by_task = partition_view(spec.partition_key)
            except Exception:
                self._skip("log-read-error")
                continue
            proposals = by_task.get(task_id, [])
            decided = set(decided_by_task.get(task_id, set())) | {ref for tid, ref in self._verdicts_local if tid == task_id}
            method = self._method_for(spec)
            choices: list[tuple[float, int, Proposal]] = []
            for index, proposal in enumerate(proposals):
                ref = str(proposal.result_ref)
                if index >= self.vconfig.proposal_cap:
                    self._skip("over-cap")
                elif not proposal.is_claim:
                    self._skip(f"not-a-claim:{proposal.status.value}")
                elif ref in decided:
                    self._skip("decided")
                elif (task_id, ref) in running:
                    self._skip("running-here")
                elif self._cooloff.get(f"{task_id}:{ref}", 0.0) > now:
                    self._skip("cooloff")
                elif self.revocations.is_revoked(proposal.producer_key):
                    self._skip("producer-revoked")
                else:
                    verdict = check_independence(self.identity.key_id, self.identity.invite_lineage, proposal.signer_key, proposal.producer_lineage, policy=self.vconfig.independence_policy)
                    if not verdict.ok:
                        self._skip(f"not-independent:{verdict.reason.split(':', 1)[0]}")
                        continue
                    choices.append((-self.penalties.weight(proposal.producer_key), proposal.seq, proposal))
            if not choices:
                continue
            choices.sort(key=lambda c: (c[0], c[1]))
            proposal = choices[0][2]
            out.append(Candidate(spec, deadline, payload=proposal, intent_extra={"result_ref": str(proposal.result_ref), "method": method}))
        for key, until in list(self._cooloff.items()):
            if until <= now:
                del self._cooloff[key]
        return out

    def _method_for(self, spec: TaskSpec) -> str:
        if spec.kind in self.vconfig.methods_by_kind:
            return self.vconfig.methods_by_kind[spec.kind]
        kind = TASK_KINDS.get(spec.kind) if spec.kind in TASK_KINDS else None
        declared = getattr(kind, "verify_method", None)
        if declared:
            return str(declared)
        return self.vconfig.default_method or "kind"

    # -- jobs
    def _make_job(self, candidate: Candidate, now: float) -> SandboxJob:
        proposal: Proposal = candidate.payload
        method = str(candidate.intent_extra.get("method", "kind"))
        raw = self.objects.get(proposal.result_ref) if self.objects.exists(proposal.result_ref) else self.upstream.objects.get(proposal.result_ref)
        result = task_result_from_record(json.loads(raw.decode("utf-8")))
        if method != "kind" and method not in VERIFIERS:
            raise Refused(f"verification-method-unknown:{method}")
        return SandboxJob(
            job_id=f"verify-{candidate.spec.task_id[:12]}-{proposal.result_ref.hex[:8]}-{secrets.token_hex(3)}", op="verify" if method == "kind" else "method", spec=candidate.spec,
            key_id=self.identity.key_id, lineage=tuple(self.identity.invite_lineage), deadline_s=candidate.deadline_s, store_locator=self.store_locator,
            import_modules=tuple(self.config.import_modules), result=result, method=None if method == "kind" else method, grace_s=self.config.kill_grace_s,
            limits=dict(self.config.limits) if self.config.limits is not None else dict(DEFAULT_LIMITS), env_extra=dict(self.config.env_extra),
        )

    # -- outcomes
    def _collect(self, slot: Slot, outcome: JobOutcome, now: float) -> StepEvent:
        spec = slot.spec
        proposal: Proposal = slot.candidate.payload
        method = str(slot.candidate.intent_extra.get("method", "kind"))
        key = f"{spec.task_id}:{proposal.result_ref}"
        detail: dict[str, Any] = {"task_id": spec.task_id, "kind": spec.kind, "result_ref": str(proposal.result_ref), "producer_key": proposal.producer_key, "method": method, "elapsed_s": round(outcome.elapsed_s, 3)}
        self._intent(slot.candidate, slot.intent_nonce, slot.intent_ttl_s, "release")
        if slot.aborted:
            self._bump("aborted")
            return StepEvent("aborted", {**detail, "status": outcome.status})
        if outcome.status != "ok" or outcome.payload is None:
            note = "verify-timeout" if outcome.status in ("timeout", "kill-failed") else "verify-error"
            self._cooloff[key] = now + self.config.cooloff_s
            self._note(spec, note, {**detail, "status": outcome.status, "error_class": outcome.error_class, "kill_action": outcome.kill_action})
            self._bump(note.replace("-", "_"))
            return StepEvent(note, {**detail, "status": outcome.status})
        try:
            verification = verification_from_record(outcome.payload)
        except (KeyError, ValueError, GridError):
            self._cooloff[key] = now + self.config.cooloff_s
            self._note(spec, "verify-error", {**detail, "error_class": "verification-unparseable"})
            return StepEvent("verify-error", {**detail, "status": "unparseable"})
        verification = replace(verification, result_ref=proposal.result_ref, verifier_key=self.identity.key_id, task_id=spec.task_id)
        if verification.outcome == VerificationOutcome.UNVERIFIABLE:
            self._cooloff[key] = now + self.config.cooloff_s
            self._note(spec, "unverifiable", {**detail, "reason": str(verification.evidence.get("reason", ""))})
            self._bump("unverifiable")
            return StepEvent("unverifiable", {**detail, "reason": str(verification.evidence.get("reason", ""))})
        record_type = RecordType.VERIFIED if verification.outcome == VerificationOutcome.VERIFIED else RecordType.REFUTED
        evidence_ref = None
        objects: list[Any] = []
        if len(canonical_json(dict(verification.evidence))) > INLINE_EVIDENCE_LIMIT:
            evidence_ref = self.objects.put(canonical_json(dict(verification.evidence)))
            objects.append(evidence_ref)
        body = verification_body(verification, proposal.producer_key, self.identity, nonce=slot.intent_nonce, evidence_ref=evidence_ref)
        # the verdict is also an object with a named pointer (tasks.results.verification_name), so
        # "done" stays an existence check on the object store (design 1.1) and publish's cache-hit
        # branch (tasks.results.is_done) sees it; the log record stays the authority for the frontier
        verdict_ref = self.objects.put(canonical_json(verification_to_record(verification)))
        objects.append(verdict_ref)
        self.outbox.enqueue(objects=objects, named=[(verification_name(spec.task_id, self.identity.key_id), str(verdict_ref))],
                            record=PendingRecord(spec.partition_key, record_type, body, spec.basis_hash))
        self._verdicts_local.add((spec.task_id, str(proposal.result_ref)))
        if record_type == RecordType.REFUTED:
            self.penalties.penalize(proposal.producer_key, reason=f"refuted:{spec.kind}:{method}", now=self.wall())
            self._bump("refuted")
            return StepEvent("refuted", {**detail, "weight": self.penalties.weight(proposal.producer_key)})
        self._bump("verified")
        return StepEvent("verified", detail)

    def status(self) -> dict[str, Any]:
        base = super().status()
        base.update({"proposal_cap": self.vconfig.proposal_cap, "independence_policy": self.vconfig.independence_policy, "penalised_keys": len(self.penalties.to_record()), "revoked_keys": len(self.revocations.key_ids())})
        return base


__all__ = ["DEFAULT_PROPOSAL_CAP", "INLINE_EVIDENCE_LIMIT", "VerifierConfig", "VerifierLoop"]
