## Task 11: Reusable donated compute foundation and adapters

- **Requirements:** R21–R22; assigned named obligations and applicable source details are mandatory; cross-cutting clause coverage does not add unrelated prerequisite edges.
- **Dependencies:** U1, U9. These denote consumed predicates, not a requirement to finish every unrelated child of a predecessor.
- **Files and interfaces:** agentdecompile_grid package, exchange and corpus task-kind adapters. Preserve existing public routing and inspect current symbols before changes; paths in archived contracts are version-specific leads.
- **Execution:** reconcile retained implementation and evidence first; implement the missing vertical slice, exercise the named positive and refusal cases, then integrate the real consumer and capture the required proof.

Implement content-addressed immutable objects, per-partition signed logs and conditional heads, bounded ready/verification frontier and replayed materialized SQLite views. Publish/work/verify/materialize locally first, then S3 conditional PUT, static mirror, peer HTTP, outbound HTTPS presigned write-once transport. Ed25519 identities/invites/revocation/rate limits and capability canaries determine actual eligible lanes; every result is a proposal, even fleet-owned. Independent verifier keys and acceptance rules reject bad hashes/receipts. Task IDs use per-kind basis projections; compaction/pruning preserves required history and durable outcomes.

Reconcile portable-plan-2026-09-21:U125 integration names before expansion: task-kinds entrypoint, vocabulary and actual landed interfaces. Include toolchain manifests/canaries, analyzer packed-program canaries, parity canaries, sandbox and idle policy, cloud fleet verbs, compile/group/parity/analyzer/import/decompile/identity/delta-bind/BSim/residue/export/window/relink/attestation adapters, browser module-worker contribution, similarity applier and bundle manifest. Preserve all51 Phase15 records and shared acceptance. Performance numbers labeled measured versus estimates, report two compile-pass populations, and never assume donated node role grants correctness.

Acceptance: grid-of-one actual cycle; stale heads/CAS starvation, stopped peer/provider, duplicate events, bad output, verifier overload/frontier, resume and compaction tested under bounded contracts; worker canary determines supported architecture; incomplete packed-program/library input refuses; adapters consume real task contracts; offline/replayed view deterministic. A successful skeleton historical receipt does not qualify all adapters/fleet.

- **Completion:** close assigned named child obligations and unit-specific predicates against the exact input/version scope; discharge owned source-clause coverage through explicit child evidence or contextual disposition; record changed paths, verification receipts and any remaining blocked predicates in the living plan. Commit only owned, reviewed changes during a separately authorized implementation run.



## Proposed slice11.2: bounded target-object producer

# Next accepted-source producer and dashboard adapter

Date: 2026-10-02. Source basis: `b871b845`, with unrelated concurrent jobs-only integration work excluded. This is a read-only architectural finding, not a recovery, producer, installed-consumer, or live acceptance receipt.

## Decision

There is no complete trusted persisted accepted-source producer in the inspected path that the dashboard can safely adapt today. Retain `not_connected` and null verified counts. The next implementation must close a real producer prerequisite before connecting an adapter; adding a permissive verifier, reading an `accepted` JSON field, or restamping contribution diagnostics would manufacture proof.

The smallest concrete producer prerequisite is an independently recomputable **raw-image-to-target-object binding for one bounded physical function**, using the existing `mkobj.write_object` execution path and grid immutable-object/verification machinery. `parity-check` already expects a pinned target object “from mkobj-target,” but there is no such registered task kind in the inspected lane package. Existing `mkobj.write_object` writes an object from a raw file offset without a corpus/address/content-bound immutable receipt. That missing causal edge prevents a parity object from establishing which binary/function it represents.

Completing that prerequisite alone does not connect accepted-source progress. The complete first adapter slice additionally needs the compile/source binding, independently accepted parity result, and current admission basis described below. Those are explicit completion conditions, not defaults to be filled by the caller.

## Existing source interfaces and limits

| Interface | Retained behavior | What it cannot establish |
|---|---|---|
| `corpus/objdiff_report.py:18`, `build_report` | Inventories physical `(binary_id, addr)` rows; accepts a receipt only for current target/source/version, accepted byte-exact claim and `verify_receipt(receipt) is True`; rejects multiple qualifying receipts per address. | Does not discover, authenticate or revalidate a producer. Its normalized receipt contract does not itself check `binary_id`; the adapter must do so before invoking it. Candidate hashes are a set per address, not a unique retained row identity. |
| `corpus/dashboard/progress_reports.py:112`, `progress_report` | Reads one corpus snapshot, checks content-hash version, calls `build_report` without receipts/verifier. | No accepted-source loader or verification configuration. |
| `progress_reports.py:14`, `logical_tier_projection`; `:87`, `_finish_group` | Reconciles physical member sets and groups by logical identity. Provider is explicitly `not_connected`; verified functions/bytes are null. | Cannot become connected merely because some JSON was loaded. `freshness=current` currently concerns this report projection, not independent acceptance currentness. |
| `corpus/source_contribution.py:242`, `compile_observation`; `:310`, `validate_compile`; `:367`, `evaluate_reconstruction` | Owned clang invocation, pinned toolchain closure, source/object/target/dependency rereads; process-local capabilities; final-writer contribution credit. | Exported JSON is deliberately unauthenticated after process loss. Contribution is anonymous source-to-target placement, not full target-object objdiff or whole-image compiler reconstruction. The separately queued target-content binding fix remains separate ownership. |
| `corpus/source_revalidation.py:121`, `revalidate` | Bounded recipe creates fresh owned compile observations and reconstruction; returns live capability separately from diagnostics. | Reading `revalidation.json` cannot restore authority. Revalidation is active compilation, never a dashboard read operation. |
| `corpus/semantic_identity.py`, `observe_target` / `evaluate_candidate` | Target PE export-name identity only. | Semantic acceptance is not byte-exact source acceptance; non-export/non-PE identity remains separate scope. |
| `artifact_layout.py:46`, `publish_verified_artifact` | Copies source/metadata and creates a sidecar with tier, status, differences, name/address. | Sidecar lacks mandatory complete target/source/version/dependency/policy binding and is mutable run-local output. `source_export.py:202` supplies insufficient metadata for this join. |
| `grid_lanes/compile.py:212`, `CompileAttempt` | Immutable input TU reference; emits TU/object hashes, toolchain identity, flags and basis; verifier recompiles and compares timestamp-masked COFF identity. | TU may include headers/preamble beyond a recovered source file. A TU hash is not automatically that candidate's source hash. The report chain must authenticate the actual object bytes as well as the receipt fields. |
| `grid_lanes/parity.py:200`, `ParityCheck` | Immutable named target/candidate object refs, checker identity, grade, differences and basis; verifier recomputes the receipt. | Target hash is an **object** digest, not the binary image digest; candidate hash is an **object** digest, not source digest. No physical address/source/report-version join. |
| `grid_lanes/parity.py:291`, `apply_parity_receipt` | Materializes a useful eight-column query table. | `grid_parity_receipt` is not the complete immutable acceptance authority. No source/image/address/version tuple or current policy/dependency evidence. |
| `agentdecompile_grid/objects/local.py`, `LocalDirStore`; `verify/loop.py:233`; `view/applier.py:491`, `_trust_reason` | Content-addressed write-once objects; independently signed VERIFIED records; view checks signer/producer independence. | Existence or a materialized row is not current source acceptance. A stored verdict must be checked against current trusted key lineage, revocations, supported implementation/policy and admitted basis. Never infer currentness from the string `basis_hash` alone. |
| `corpus/mkobj.py:256`, `write_object` | Reads raw bytes, bounds a file-offset region, discovers external references and produces relocation-aware COFF. | No admitted raw-image/address/corpus binding receipt, independent persisted verification, or consumer-currentness contract. |

Paths in the table are under `src/agentdecompile_recovery/` unless explicitly prefixed `agentdecompile_grid/`, which is under `src/`. Line numbers are locators in the inspected source, not a promise about concurrent edits.

## Smallest local producer implementation to queue now

Implement one `mkobj-target` producer kind, with its independent recomputation method, in a narrow new recovery lane module, registered alongside the existing compile/parity lanes. This uses existing execution and immutable storage interfaces; it is not a new general acceptance framework.

Suggested ownership is `src/agentdecompile_recovery/grid_lanes/target.py` (new), the necessary kind registration in `grid_lanes/__init__.py`, and the narrow existing planner registration only if required by the lane contract. Reuse `corpus/mkobj.py`, `corpus/verify_recovered_byteexact.py:file_region_offset`, grid task validation, content-addressed objects and `verify_by_recompute`; modify those helpers only for a concrete demonstrated requirement. Do not own `source_contribution.py`, its queued target-binding fix, jobs modules, report/UI files, generic grid trust infrastructure or recovery catalog in this producer slice.

The producer's complete local contract is:

1. Consume an immutable raw-image object and a bounded, versioned selection input identifying corpus scope, `binary_id`, `addr`, size, report version and admitted generation/basis. Resolve the selection from the authoritative corpus snapshot when producing the task; arbitrary task parameters are requests, not proof of a DB association. Retain that snapshot/selection digest so the future adapter can compare against its current snapshot. Require raw-image digest equal to the selected `binary.content_sha256` and version. Refuse missing/ambiguous inventory membership or unsupported spans.
2. Start with one raw-backed contiguous PE function and the existing i386/amd64 COFF formats. Derive machine and file offset from the image and address; do not accept caller-provided offset, architecture or target-object bytes as authority. Refuse unsupported mappings, multi-range functions, zero/negative/invalid size and ambiguous boundaries. This does not broaden semantic-identity support.
3. Invoke the retained `mkobj.write_object` path in an owned bounded workspace, preserving its refusal when external references cannot all be found/relocated. Pin the generator, mapper and decoder implementation/dependency identities that influence those bytes. `find_call_targets` can invoke objdump: pin the executable/dependency basis and treat missing/changed decoder as refusal; do not rely on an unversioned PATH result as accepted producer identity.
4. Store the actual generated object and a canonical bounded receipt in the existing object store. Bind the input raw-image ref, corpus selection digest, binary/address/size, derived offset/machine, target-object ref, generator/dependency basis, task/kind revision and requested generation. Hash the actual retained bytes. No caller `complete`, `accepted` or decoder-name field grants authority.
5. Independently regenerate from the immutable raw image and selection and compare **both object and receipt** references. Reuse the existing verification result/log path; an object without a current independently admitted VERIFIED record is unavailable. The task's successful `run` result alone is not acceptance.

This is executable producer work, not merely a schema. Its output establishes only “this bounded target object was derived from this raw-image function under this basis.” It does not claim the recovered source compiles, matches, has qualified semantic identity, or rebuilds the image.

### Concrete runtime inputs still needed

The subsequent authorized execution needs one selected corpus identity and binary row with content hash, one physical function with a supported raw-backed contiguous extent, access to matching raw target bytes, an owned workspace, a pinned working objdump dependency basis, an object store and admitted independent producer/verifier identities. No particular live binary, raw-image path, key pair, object-store root or decoder installation was inspected or established in this investigation. These are unverified runtime inputs, not asserted absent files.

Completing source-to-report acceptance additionally needs one source whose actual bytes match exactly one retained candidate, a supported pinned compiler/toolchain, and a pinned working objdiff checker. Existing implementations provide two leads, not availability proof: `CompileAttempt` resolves its registered toolchain identity and wrapper/Wine environment; `source_contribution` has a fixed native clang 22.1.8 closure pin and rejects other compilers. `ParityCheck.resolve_checker` supports an explicitly pinned native objdiff or script/wasm bundle. Neither native clang contribution credit nor a successful `CompileAttempt` may substitute for independent objdiff acceptance.

For the first complete source slice, restrict the compile input to a self-contained TU whose bytes are exactly the retained candidate source bytes. Then `tu_sha256 == source_sha256` is a checked identity rather than a guessed relationship. Candidates requiring added preamble/headers are explicitly unsupported until that dependency transformation is independently bound. This keeps the next adapter narrow without mislabeling an arbitrary generated TU as the recovered source.

The operating route still must be the existing 8080 action catalog. Source availability or lane registration is not catalog admission. No matching current catalog action was queried here. If the catalog lacks an owned action capable of producing/independently verifying this exact chain, that action integration is a separately identified execution prerequisite; do not use a recovery CLI, launch grid workers or start a server to bypass it.

## Complete producer-to-dashboard slice, conditional on that evidence

The first complete adapter should support one bounded qualified chain per physical candidate:

`raw image + selected physical member → independently accepted target object`

`exact candidate source/TU + pinned toolchain → independently accepted candidate object`

`those exact two objects + pinned checker → independently accepted full target-object parity`

`current corpus/policy/dependency/generation checks → normalized report receipt → existing report/projection → both existing consumers`.

Read and authenticate original immutable task, result, receipt, object and verification-record content. Do not start compilers/checkers, materialize views, replay log writers or mutate object stores from the dashboard. A read adapter must also avoid `LocalDirStore` default corruption quarantine writes: use a noncreating, nonmutating read configuration and surface integrity failure.

Require exactly one candidate row at `(binary_id, addr, target_sha256, source_sha256)` in the current corpus and `version == binary.content_sha256`. Duplicate rows or competing eligible receipts are refusal; one matching hash in `build_report`'s deduplicated set is insufficient evidence of a unique row. A physical inventory member must exist. Join logical identity only after physical acceptance; preserve unbound members in reconciliation.

The compiler-result object must authenticate the exact source/TU input and actual output object digest. Inspect the current `CompileAttempt.verify` boundary carefully: it compares a proposal receipt's masked-COFF hash to a recomputation; the adapter/producer must also verify that the proposed object bytes, receipt object digest and independently verified masked identity agree. Never turn independently accepted receipt fields into unverified output-object authority.

Require supported full target-object parity at the named scope, zero differences, successful objdiff exit and no fallback. Weaker code-slice/source-shape receipts remain weaker claims. Bind both sides to the authenticated target/compile outputs and retain checker identity. A bare grid `VERIFIED` record can describe diagnostic/error output, so require the correct successful result and parity grade as well as independent verification.

Compare against a current admission basis obtained from owned configuration/authority, not a receipt's own assertion: allowed producer/kind and verifier implementations; pinned mapper/generator/compiler/checker dependencies; trusted key lineage and revocation state; acceptance policy revision; corpus/selection generation and report version. A known historical basis may be reused only if current policy explicitly still admits it. Missing basis resolution is `unavailable`; changed/disallowed basis is `stale`; failed loading/authentication is `failed`. Do not map any of these to observed numeric zero.

Emit the existing `addr`, `target_sha256`, `source_sha256`, `version`, `status=accepted`, `claim=byte_exact_source` fields only after those checks, plus immutable receipt/verification refs and provider/dependency/policy/generation basis. Supply a closed verifier over the already authenticated exact receipt content, rejecting different or mutated inputs; never install `lambda receipt: True` or a caller-selected verifier in the route.

Use `build_report` once as classifier and `logical_tier_projection` once as aggregator. Make provider state and `_finish_group` availability conditional on a successful complete provider read. Distinguish a connected, fully read provider with zero accepted receipts from a disconnected/failed/stale provider. Keep advisory evidence usable when acceptance is unavailable. Include provider basis in the report/projection digest/cache identity so policy/generation changes cannot reuse former acceptance. All inventory membership/extent accounting remains under the existing report gate.

The existing consumers already require `provider.status == connected` for available verified counts: static `staticMatrixCell` in `dashboard/static/workbench-app.js:3220`, Vite `matrixTierCell` in `dashboard/frontend/src/workstation/coverageMatrix.tsx:10`, and the two tier progress renderers. Integrate those actual consumers; do not add a third report producer or duplicate their tier classification. Runtime activation and live observation are separate authorized work.

## Required acceptance and refusal evidence (not run)

- Positive target producer: one admitted raw-image/function selection yields independently reproduced identical target-object and receipt references. Its emitted image/address/size/offset binds exactly to the authoritative snapshot. This proves only the target-object prerequisite.
- Positive full slice: one independently accepted source/compile/target/parity chain promotes exactly one inventory member; an adjacent `real_c=1` member stays advisory. Both surfaces show the same exact version/report basis and count-to-member sets.
- Refuse missing or false verification; self/same-lineage verification; revoked/disallowed producer or verifier; absent immutable object; tampered object/receipt/spec/result; wrong successful grade; objdiff error/empty output/nonzero diff/fallback; object/source/TU mismatch; mismatched image/address/size/version; missing/duplicate candidates; multiple eligible receipts.
- Refuse unsupported target format/span/mapping, unqualified decoder, changed generator/compiler/checker closure, unsupported preamble/header source transformation and arbitrary target-object input.
- Mark changed policy/generation/corpus selection or target/source/dependency basis stale. Removing the provider or losing evidence produces unavailable/null verified values. A complete connected empty acceptance set can produce zero, explicitly scoped to the current checked basis.
- Preserve unknown extents, unbound identities and split/merged physical membership. Accounting failure blocks publication. Source acceptance never claims semantic identity, whole-image fresh compilation, runtime readiness or publication.

## Priority and ownership boundary

Do not duplicate or alter the separately queued source-contribution target-content binding slice. It is a necessary retained-producer correction, not a durable accepted-source adapter. The target-object prerequisite above concerns `mkobj`/grid parity provenance and has different ownership.

Filtered or batched logical-tier reads remain a separate lower-priority scaling gap: the current route accepts only slug, version and corpus identity and builds a full per-binary report before projecting all logical groups. Narrow filtering/batching may reduce matrix cost but supplies no acceptance authority. Do not hide the missing producer by doing that optimization first.

Only this report was written. No Python/source/index changes, tests, builds, proof executions, project imports, service/catalog/process actions, live database/object-store inspection or upstream donor dirt were performed. Same-plan `acceptance-seam.md` was read as historical context; all implementation conclusions above were checked against current source. The result is a concrete implementation boundary and unrun acceptance contract, not U1/U21 completion.


## Controller preparation: unresolved design before implementation dispatch

This packet is PREPARED, not yet dispatched. The architectural report above establishes the missing producer edge. The remaining bounded design decision is how the existing write_object path receives an independently pinned decoder/execution closure without process-global PATH mutation or a permissive verifier. An architect must resolve that seam against retained source before a source implementation is dispatched. Do not start implementation from this preparation note alone.

Current source checks: grid_lanes/parity.py documents target objects from mkobj-target but no registered kind/planner exists. grid_lanes/__init__.py and splitter.py are its narrow registration points. splitter.snapshot_store already creates an immutable read-only-source VACUUM snapshot and derives the basis from that exact copy. TaskSpec identity includes inputs, params and basis; require the immutable store snapshot as an input and rederive the selected binary/function association from it during run/recompute. A JSON selection supplied by the task is not DB membership authority. The future acceptance reader must still compare the immutable snapshot with current owner-authorized corpus scope, policy/generation and current selected rows.

Existing corpus.verify_recovered_byteexact.file_region_offset derives one unambiguous raw-backed PE mapping; retain its whole-region refusal contract. Derive machine from the same raw bytes and bind PE optional-header width to i386/amd64 rather than trusting a task-provided format. Require singleton function membership and an explicitly single contiguous extent; ranges, size, address and IDs need exact integral checks, not bool/int coercion. No copied bytes, arbitrary offset or caller object is an accepted target object.

Existing mkobj._run_objdump uses an unpinned PATH executable and no timeout; find_call_targets has a safe fast path for bytes with no possible PC-relative reference; write_object takes file paths and invokes that discovery. The producer must preserve all reference/relocation refusals while supplying a pinned, bounded decoder path. If a new backwards-compatible keyword is necessary in mkobj.py, that narrowly scoped extension may be owned alongside a future producer. Do not temporarily mutate module globals or PATH. Reuse grid deadline and owned-workspace semantics. Pin actual code/executable/dependency identities rather than merely a caller label. Never invoke ldd against untrusted images during verification or claim a caller-provided closure manifest is complete without a trusted resolver.

Existing verify_by_recompute compares named output refs and status/reason; it does not itself verify proposal task_id/basis or authenticate every advertised object. The producer's verification must validate its own result/spec association and actual immutable refs and compare both generated object and receipt. Compiler-output binding is separately owned by Task11.1 and must not be changed by this slice. No grid framework-wide refactor, report/UI adapter, schema migration, live catalog registration or fake accepted-source provider belongs here.

Suggested eventual source ownership: new grid_lanes/target.py; narrow grid_lanes/__init__.py and splitter.py registration; minimal keyword-only mkobj injection if required; new focused target-producer regression source and narrow verification note. No source writer currently owns these files. Exact implementation ownership and API values must be added here after the decoder/snapshot contract decision. No tests, builds, source imports, project/database execution, recovery CLIs, process/service changes, systemctl, catalog submissions or live activation are permitted. Regression sources may be prepared, not executed. Controller alone stages and commits in this shared worktree.
