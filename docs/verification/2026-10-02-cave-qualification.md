# Cave qualification and recursive input policy — October 2, 2026

This bounded U25/U28 slice implements a trusted acceptance seam and input refusal
policy. Its verification is source inspection only. It establishes no real
whole-image decode producer, successful export, installed consumer, runtime
mutation or complete U25/U28 delivery.

`build_hookpack_v2`, the v2 branch of `export_hookpack`, `export_bundle` and
`validate_export_set` accept keyword-only `verify_cave_receipt=None`. The caller
must supply trusted process code from the acceptance owner. No JSON value, CLI
flag, decoder label, sealed pack digest or serialized verifier result grants this
authority. V1 does not call the verifier. A validator with `require_caves=False`
continues to report artifact consistency and `runtime_verification=not_run`.

The proposed complete receipt binds `build`, registered `image_sha256`, `arch`,
canonical `basis_sha256`, `evidence_sha256`, the unchanged request `decoder`,
`candidate_count`, and `candidates_sha256`. The candidate digest covers the sorted
per-build cave records, ordered by build, anchor key, decreasing capacity, offset
and cave id, using the existing canonical JSON bytes (including their newline).
Only a literal `True` result on an unchanged detached receipt accepts. Candidates
are emitted only after acceptance. Independently qualified discovery with zero
candidates remains a complete negative observation; no live allocation is granted.

The request must contain `qualification` with a lowercase 64-hex
`producer_reference_sha256`, nonempty `policy_revision` and nonempty `generation`.
The trusted provider must resolve the reference against its independently held
immutable producer/audit object and compare the exact image, build, architecture,
export basis, evidence, full decoder identity and revision, and exact candidate
content. That object must establish complete executable instruction ranges,
relocations, data-reference targets, decoded function ends and uniqueness/anchor
evidence for this image. The provider must recheck current policy and dependency
generation at each consumption point. Restoring retired bytes does not revive a
retired generation. A legacy decoder string is acceptable only if independently
resolved provenance establishes its exact identity and revision; none is guessed.

Absent evidence keeps the existing discovery blocker. Valid evidence without a
callable verifier produces `independent_cave_verifier_unavailable`, with no cave
records or qualified count. False, null, `1` and other non-True callback results
produce `independent_cave_qualification_refused`. An unavailable provider explicitly
raises local `CaveEvidenceError("independent_cave_verifier_unavailable")`; no other
exception class is guessed to mean unavailable. Unexpected exceptions raise
`cave_verifier_failed` with their cause preserved. Mutation of the detached input
raises `cave_verifier_input_changed`, including mutation to non-JSON values or an
excessively nested object. No such path seals a complete receipt.

`validate_export_set(require_caves=True)` verifies these local bindings and exact
count again, then invokes the trusted provider again. Previously serialized
complete receipts need a newly supplied provider and current authority. The
existing CLI and dashboard bundle listing have no such provider, so independent
qualification remains unavailable there. Mounting a real provider is separate
work. All three bundle validation calls forward the same provider. Initial checks
precede root/staging creation; later failures retain savepoint rollback and private
staging cleanup. No failed recheck permits publication.

The fixed JSON stack-safety policy is **64 simultaneously active dict/list
containers**, including the root and empty containers. Entering container 65
raises local `CaveEvidenceError` with code
`cave_evidence_nesting_limit_exceeded`, build slug when known, and details
`{"limit":64,"depth":65}`. A defensive parser/encoder/copy recursion refusal uses
null depth when the actual depth is unknown. The acceptance owner's exact cave
policy revision must state this bound. A deeper schema requires a reviewed policy
revision; the limit is not caller configurable. This policy is not decoder
qualification or a node/performance budget. Large flat evidence and shared acyclic
JSON subtrees remain admissible; cycles, tuples, subclasses, non-string keys and
nonfinite floats remain refused. Generated tuple member fingerprints still work
with `canonical_bytes`. Complete v2 packs have their own 64-container budget,
including wrappers around evidence fragments, before recursive copying.

Regression sources in [test_corpus_cave_qualification.py](../../tests/test_corpus_cave_qualification.py)
cover positive and zero-candidate synthetic observations, unavailable/refused/failed
providers, currentness changes, exact target and result binding, mutable evidence
and callback input, JSON depth/exactness, serialized consumption, v1/v2 forwarding
and later bundle refusal/cleanup. Their independently held observation is a
**synthetic verification-seam fixture**, not an actual qualified whole-image
producer. These tests were written and AST-inspected, **not run** in this mission.
Later authorized execution must separately record exact source identity, provider
origin, results and production versus synthetic scope. Runtime allocation,
protection/alignment, lifetime/reclaim, native adapters, installed/live consumers
and fresh whole-image recovery acceptance remain open.
