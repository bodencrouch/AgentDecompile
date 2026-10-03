## Task 25: Cave discovery and safe injection plans

- **Requirements:** R14–R15; assigned named obligations and applicable source details are mandatory; cross-cutting clause coverage does not add unrelated prerequisite edges.
- **Dependencies:** U5. These denote consumed predicates, not a requirement to finish every unrelated child of a predecessor.
- **Files and interfaces:** Existing backend/provider, static workbench and Vite modules named below; no duplicate root. Preserve existing public routing and inspect current symbols before changes; paths in archived contracts are version-specific leads.
- **Execution:** reconcile retained implementation and evidence first; implement the missing vertical slice, exercise the named positive and refusal cases, then integrate the real consumer and capture the required proof.

- Image-bound cave discovery with evidence for candidate occupancy,anchor+offset+capacity requirements,region alignment/protection and relocations; cave fallback,allocation policy and refusal outcomes explicit. Empty list is not discovery evidence. Call/install/removal,lifetime and reclaim proof separate.
- frontend-plan-2026-09-28:U34 with external image producers; acceptance exact build/bytes,overlap/insufficient capacity/unsupported dynamic code and stale discovery; no installed hook proof from serialization.

- **Completion:** close assigned named child obligations and unit-specific predicates against the exact input/version scope; discharge owned source-clause coverage through explicit child evidence or contextual disposition; record changed paths, verification receipts and any remaining blocked predicates in the living plan. Commit only owned, reviewed changes during a separately authorized implementation run.



## Bounded slice 25.1: cave qualification and recursive-input safety

# Bounded U25/U28 cave qualification slice

Prepared 2026-10-02. This is an implementation brief and source inspection report. It adds no source implementation or executable proof. Scope is review findings **V5/R6** named in `source-reconciliation-report.md:100–108`, rather than the master plan's separately numbered runtime verification axis or whole-image R6 requirement.

Source baseline: frozen donor commit `2595ef42efc04df9869d81b3f6e4f090729fe4bc`, inspected with `git show`. Active code and index belong to the implementation merge owner; their in-progress contents were not used as the baseline and were not modified. Rebase this brief's locators against the reconciled source before implementation.

## Required result and bounded ownership

Only independently qualified, exact-image cave evidence may produce a `status=complete` discovery receipt. Evidence that is absent or cannot be qualified produces an explicit blocked result. Excessive nesting must refuse with a stable code before recursive serialization or copying. Qualified complete discovery with zero candidates remains a valid negative observation. It grants no placement, install, call, restoration, or live-allocation permission.

Implement in `corpus/hookpack_v2.py`, plus the existing `corpus/export_hookpack.py`, `corpus/export_bundle.py`, and `corpus/export_validation.py` forwarding/gating seams described below. All paths here are beneath `src/agentdecompile_recovery/`. Preserve `corpus/cave_discovery.py` as the existing consistency scanner; a clarifying docstring is sufficient if needed. No new decoder, producer service, receipt framework, trust registry, root exporter, CLI flag, dashboard feature, dependency, database migration, or alternate port belongs to this slice.

U25 consumes image/exclusion/anchor evidence. U28 consumes its qualified discovery result before staging/publishing a bundle. Neither entire unit closes from this change. Existing runtime allocation, protection/alignment, lifetime/reclaim, adapter and installed-consumer predicates remain separate.

## Source-established defect

At the pinned revision:

- `hookpack_v2.py:25–57` walks JSON-native evidence iteratively and rejects active cycles, Python-only values, non-string keys and nonfinite floats. It has no depth limit. `canonical_bytes` uses recursive JSON encoding; `seal_pack` and `read_hookpack` copy recursively.
- `hookpack_v2.py:215–235` binds evidence to the registered raw-image digest and architecture, but creates a complete receipt after calling `discover_caves` without an independent verifier. A caller supplies both `complete=True` and decoder/exclusion assertions.
- `cave_discovery.py:21–32` explicitly assigns independent producer qualification to its caller. Its byte/range checks remain useful, but cannot establish complete whole-image decode/exclusion coverage. Its module documentation says `asm_extent.decode` is bounded PE32 i386 extent decoding; do not relabel it as the missing producer.
- `export_validation.py:78–95` checks exact per-build receipt coverage, image/evidence hashes, nonempty decoder and actual candidate count. A sealed, internally consistent fabricated receipt still passes these identity-only gates.
- `export_bundle.py:100–112,151` calls the builder once and the validator three times before publication. `export_hookpack.py:182–202` is the existing v2 forwarding seam. CLI `export-bundle` supplies no evidence/verifier. `dashboard/export_listing.py:145–146` reopens and validates serialized bundles without an independent producer provider.

These are control-flow findings from source inspection. No exploit fixture, decoder, exporter or verifier was executed in this run.

## Existing trust pattern to reuse

`corpus/objdiff_report.py` already implements `build_report(..., receipts=(), verify_receipt=None)` and `export_report(..., receipts=(), verify_receipt=None)`. It checks local target/source/version/claim eligibility, then requires `callable(verify_receipt)` and `verify_receipt(receipt) is True`. The acceptance owner supplies the callback. It does not restore trust from receipt JSON. Reuse that injection pattern here; do not reuse its byte-exact claim scope for caves.

`corpus/recipient_acceptance.py` separately demonstrates producer/verifier separation and generation rechecking, but its only provided generation reader is an identity-graph lane and it grants no recovery credit. Do not pretend that reader qualifies cave evidence. `source_revalidation.py` also keeps process-local authority separate from JSON diagnostics; serialization alone is not a trust source.

## Exact minimal public API

Add one keyword-only optional callback, named `verify_cave_receipt`, defaulting to `None`:

```python
build_hookpack_v2(con, *, site_policy=None, adapter_map=None,
                 operation_contract=None, cave_evidence=None,
                 verify_cave_receipt=None) -> dict

export_hookpack(con, out, *, site_policy=None, adapter_map=None,
                operation_contract=None, cave_evidence=None, format="v1",
                verify_cave_receipt=None) -> dict

export_bundle(con, out, *, site_policy=None, adapter_map=None,
              operation_contract=None, cave_evidence=None,
              verify_cave_receipt=None) -> dict

validate_export_set(pack, *, lua_source=None, headers=(), readiness=None,
                    require_caves=False, verify_cave_receipt=None) -> dict
```

Callback contract: `verify_cave_receipt(receipt: dict) -> bool`. Invoke only after local binding/shape/depth checks. Only the singleton `True` accepts; `False`, `None`, `1`, strings or other truthy values refuse. The callback must be supplied by the acceptance owner as trusted process code, never loaded from submitted JSON, a caller-named executable, or a policy flag. A callback that simply returns `True` is a synthetic seam stub, not independent production qualification.

Keep existing positional arguments and defaults. `export_hookpack(format="v1")` retains its existing branch and output behavior; do not call the cave callback in that branch. The bundle's existing independent v1 operation binding stays unchanged. The low-level `discover_caves` signature and candidate algorithm stay unchanged.

The v2 forwarding chain passes the callback without substituting a permissive fallback. `export_bundle` forwards it to the builder and every `require_caves=True` validation call. A standalone validator with `require_caves=False` continues to advertise only artifact consistency and does not claim independent cave qualification.

The existing CLI and bundle listing remain callable with these defaults. Their qualification remains unavailable until their owners connect a real acceptance provider. Previously serialized complete receipts cannot satisfy `require_caves=True` without the trusted callback. This is an intentional acceptance tightening; document it instead of preserving the defect with an implicit trust exception. Wiring the mounted dashboard/catalog provider belongs to its owner and requires separate scope.

## Independent qualification basis

Retain the receipt's existing `build`, `image_sha256`, `evidence_sha256`, `decoder`, `candidate_count` fields. Add `arch`, `basis_sha256` (digest of the declared pack basis using the existing canonical bytes), and a `qualification` object with these exact string fields:

```json
{
  "producer_reference_sha256": "<immutable producer/audit object digest>",
  "policy_revision": "<exact cave acceptance policy revision>",
  "generation": "<exact producer/dependency generation token>"
}
```

The three qualification values are supplied in `cave_evidence[build]["qualification"]` and included in its canonical evidence hash. Require a lowercase 64-hex producer reference, nonempty policy revision and nonempty generation; a missing field never receives an accepted default. Retain the existing complete decoder value in the request; avoid renaming existing decoder keys. The independently resolved producer object must establish the exact decoder identity **and revision**, even where a legacy string decoder cannot do so. An unqualified decoder shape refuses through the callback rather than gaining a guessed revision.

The trusted callback must resolve the producer reference using an independently held immutable object/observation and current acceptance authority. Its comparison must bind:

1. Registered exact raw image digest, build and architecture; declared export basis digest.
2. Canonical evidence digest and full decoder identity/revision.
3. Producer qualification for complete executable instruction ranges, relocation exclusions, data-reference targets, decoded function ends and uniqueness/anchor evidence for this exact image.
4. Current cave-policy revision and producer/dependency generation, with currentness rechecked at acceptance. Restoring identical bytes after retirement does not silently revive an old generation.
5. The emitted result, including candidate count and candidate content. Bind a `candidates_sha256` field computed from the canonical per-build plans in their existing deterministic order. Count alone does not prevent a caller replacing candidates while resealing the pack. The consumer reconstructs the same sorted per-build list and checks its digest before calling the verifier.

The additional `candidates_sha256` is a required lowercase 64-hex receipt field. The callback receives the complete proposed receipt, including that digest; it resolves/verifies the audited producer result for those exact candidates. A producer-reference hash or `qualified=True` in caller JSON is a proposal, not qualification. Comparing only evidence/image digests and accepting any decoder/policy/generation fails this contract.

No suitable whole-image producer is established by the inspected modules. A real callback can reuse a qualifying external immutable producer receipt if one already exists. If that independently held basis is unavailable, the correct result is blocked. This slice must not fabricate a producer or expand the bounded PE extent decoder to claim completeness.

## Builder and consumer control flow

Preflight the exact build-map coverage and bounded JSON evidence first. Canonicalize and capture a detached evidence snapshot after successful preflight; hash that snapshot and pass the same snapshot to the scanner. Preserve raw-image availability, registered hash equality and architecture checks before qualification. This avoids hashing one mutable object and scanning another state of it.

Without evidence, retain `discovery_blocker(build)` and empty caves. With valid evidence but no callable verifier, emit one blocked receipt per affected build, reason `independent_cave_verifier_unavailable`, and emit no candidates for that build. The supplied evidence digest may be retained as diagnostic identity; omit `candidate_count` or use null because qualified discovery did not occur. Never record complete-zero for missing qualification.

With a callable verifier, compute proposed plans using the unchanged scanner and build the exact bound proposed receipt above. Pass a detached copy to the verifier; never allow it to modify the receipt or candidates that will be sealed. Compare the verification-input copy's canonical bytes before/after to detect mutation and refuse as `cave_verifier_input_changed`. Grant `status=complete` and append plans only after literal `True`, unchanged input and exact local basis checks. If qualification returns anything else, retain a blocked receipt, reason `independent_cave_qualification_refused`, and no plans. An expected provider-unavailable exception maps to blocked, reason `independent_cave_verifier_unavailable`; unexpected callback errors fail closed with `cave_verifier_failed`, preserving the cause rather than being swallowed as success. No complete receipt is sealed on any such path.

Use the same exact basis/candidate-digest checks in `validate_export_set(require_caves=True)`. Require the callback again after the existing coverage/status/hash/count checks. Preserve actual-count equality, including `type(count) is int` so a boolean count refuses. Reopening a serialized pack is a new consumption point; its trusted provider must verify the immutable reference against current policy/generation. A serialized verifier label, callback result, complete status or pack digest never bypasses that check. Keep the validator's receipt scope explicit; runtime verification remains `not_run`.

Existing bundle preflight occurs before `root.mkdir` and staging creation. Keep this order so unavailable/false qualification cannot publish or create a new bundle. Preserve rollback/savepoint behavior and existing complete outputs. Revalidation later in the bundle path must also refuse any changed authority; no publication follows a failed recheck.

## Depth refusal and compatibility details

Choose a documented fixed bound **64 simultaneously active JSON containers**, counting the root dict/list as depth 1. An empty nested container counts. Depth 64 is accepted by the walker; entering container 65 refuses before canonical JSON or `deepcopy`. This is a stack-safety policy, not a whole-image size/node budget. Large flat instruction/reference arrays remain admissible; keep the walk iterative with depth-sized active state, retain branch-local cycle detection, and allow shared acyclic JSON subtrees.

The source establishes the need for a finite bound because subsequent operations recurse; it does not establish a universal Python recursion threshold. The proposed 64 is deliberately conservative for the shallow schema and recursive-copy frame overhead. It must be stated in the cave acceptance policy revision. Do not reinstate the historical 100,000-node cap or advertise this constant as decoder qualification/performance proof. A future legitimate deeper schema needs an explicit reviewed policy revision, not a caller-controlled limit or `sys.setrecursionlimit` change.

Extend the existing iterative walk to track container depth. Preserve exact JSON-native rejection of tuples, subclasses/coercible values, non-string keys, nonfinite floats and cycles on evidence. Do not globally change `canonical_bytes` to require JSON-native input: the builder already hashes generated tuple member fingerprints there, so that would introduce unrelated caller breakage.

Guard v2 full-pack dict inputs before recursive copying in `seal_pack`/`read_hookpack` and validation; the complete pack also has the 64-container limit, so added wrappers can make an otherwise depth-64 fragment exceed the complete-pack bound. Keep the v1 return path compatible. Convert parser/encoder/copy `RecursionError` into the same stable refusal as a final defensive boundary, including path-loaded v2 packs; do not rely only on catching it after expensive copying. Ensure the existing broad canonical-evidence wrapper does not erase the specific depth reason.

For structured refusals, add only a local `CaveEvidenceError(ValueError)` with attributes `code`, `build` and `details`, and a stable string representation. Depth uses `code="cave_evidence_nesting_limit_exceeded"`, build slug when known, and details `{ "limit": 64, "depth": 65 }` (unknown observed depth may be null for a parser-level recursion refusal). Keep existing canonical JSON error prefixes for the existing invalid-type cases and retain their causal reason. Blocker dictionaries already supply the structured unavailable/refusal channel. The export validator continues to raise `ExportValidationError`; preserve the specific stable code when wrapping a cave exception. No shared error framework is needed.

## Source-only regression specification

These are required review cases and future execution expectations, **not tests run or written here**. Review implementation branches/signatures and fixture specifications without importing source, creating databases, running proofs/suites/builds, or touching services under the current mission.

| Case | Required visible outcome / source predicate |
|---|---|
| Independently qualified positive fixture | Trusted seam verifies exact producer object/image/evidence/decoder/policy/generation/candidate digest; deterministic cave order, actual count, complete receipt; static/live prohibition retained. Label any callback stub synthetic. |
| Independently qualified zero | Real scanner returns zero under complete qualified exclusions; count 0, digest of empty plans, complete negative receipt, no usable cave. |
| Missing evidence / missing callback | Ordinary blocker retained / explicit verifier-unavailable blocked receipt; no complete-zero substitution; required bundle fails before staging. |
| False/nonboolean verifier | False, null, 1 and other truthy non-True values produce refusal, no cave output or bundle publication. |
| Changed or unknown producer | Refuse missing/forged reference; changed producer object, decoder revision, generation or policy cannot reuse old qualification, even if the pack is resealed. |
| Wrong registered target | Wrong image digest, build or arch refuses before qualification; per-build unaffected controls keep their scoped behavior. |
| Scanner safety controls | Instruction/relocation/reference overlap removes candidates; insufficient capacity removes candidates; unsupported complete producer refuses; deterministic largest-first ordering unchanged. |
| Tampered result | Resealed wrong count, bool count, changed cave bytes/anchor/capacity or missing candidate digest refuses locally or via the independent result binding; matching count alone cannot accept substituted candidates. |
| Excessive nesting | Depth 64 walker boundary specified; entering 65 (including empty containers) raises structured depth code before encoder/copy/verifier. Full-pack wrapper depth checked independently. Defensive parser recursion maps to stable refusal. |
| Existing JSON exactness | Tuple, non-string key, float NaN/Inf, container subclass and cycle continue to refuse. Shared acyclic subtrees and large flat arrays do not acquire a node-count refusal. |
| Mutable callback / evidence | Scanner consumes captured canonical snapshot; callback mutation refuses, original caller input stays unchanged, no mismatched hash/scan receipt is sealed. |
| Compatibility / serialized reopen | v1 API/output unchanged; existing v2 keywords preserved; all three bundle checks receive callback; no-callback CLI/listing stays blocked; serialized status/hash cannot restore current qualification. |
| Stale publication boundary | Provider currentness changes at later validation: no bundle publication, savepoint/staging cleanup retained, existing completed artifacts remain readable. |

Later authorized execution must exercise these positive/refusal cases against the reconciled implementation and record exact source identity, callback/provider origin, synthetic versus real producer scope, and consumer outcome. It cannot claim whole-image decode production, runtime mutation acceptance or full U25/U28 closure from an injected fixture.

## Verification performed for this brief

Read the U25 and U28 requirement boundaries, source reconciliation's V5/R6 queue, pinned source definitions and call sites, and existing independent acceptance patterns. Historical memory was used only to retain the JSON-native/cycle and source-versus-live boundaries; every concrete defect above was checked against the pinned source. The brief's written content and links were checked read-only. No Python imports, source edits, tests, proof scripts, builds, service commands, catalog calls, process changes, index changes or subagents were used.


## Controller rulings and execution boundaries

The master plan remains authoritative; this is an implementation slice, not closure of U25/U28. The active 64-container bound is adopted as an explicit stack-safety policy at this shallow JSON boundary, never a flat whole-image evidence limit. Preserve arbitrarily large flat arrays subject to existing resource constraints. No suitable producer is established: implement the trusted verification seam and truthful blocked default; never create a synthetic provider and represent it as production qualification. Tests may be written/updated for future execution but must not be run in this mission. Do not import project code or run proof scripts, suites, builds, compilers, Ghidra, services, catalog actions, process mutations or systemctl. Source-only AST, diff and call-site checks are allowed. The controller has corroborated serving PID2697197, cwd /home/brunner56/agentdecompile-nvme, retained loaded module paths under the MyBook checkout; this feature checkout is not live and this slice does not activate it.

Own only the specified cave/export source paths, their existing focused test sources, and a narrow verification document if needed. Other agents share this checkout; do not revert anyone's work. Do not modify the master/living/todo/progress files; controller owns those. Preserve v1 behavior and existing unrelated safety changes. Use the implementer template, no subagents. Commit only owned paths locally. Write a full self-review/validation/remaining-gates report to task-25-report.md beside this brief. Return only status, commit(s), one-line validation summary and concerns.

Provider exception clarification: a trusted callback may explicitly raise the local CaveEvidenceError with code `independent_cave_verifier_unavailable` to report expected unavailability. Unexpected callback exceptions map to `cave_verifier_failed` and retain their cause; do not classify arbitrary OSError/LookupError failures as expected absence. This settles the previously unspecified exception type without adding a separate framework.
