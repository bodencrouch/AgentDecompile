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


## Historical preparation: design resolved by the adopted contract below

The following paragraph records the initial discovery question. It is superseded by the adopted reference-free-only contract below: the first bounded producer executes no external decoder. General decoder closure remains a separate open predicate.

Current source checks: grid_lanes/parity.py documents target objects from mkobj-target but no registered kind/planner exists. grid_lanes/__init__.py and splitter.py are its narrow registration points. splitter.snapshot_store already creates an immutable read-only-source VACUUM snapshot and derives the basis from that exact copy. TaskSpec identity includes inputs, params and basis; require the immutable store snapshot as an input and rederive the selected binary/function association from it during run/recompute. A JSON selection supplied by the task is not DB membership authority. The future acceptance reader must still compare the immutable snapshot with current owner-authorized corpus scope, policy/generation and current selected rows.

Existing corpus.verify_recovered_byteexact.file_region_offset derives one unambiguous raw-backed PE mapping; retain its whole-region refusal contract. Derive machine from the same raw bytes and bind PE optional-header width to i386/amd64 rather than trusting a task-provided format. Require singleton function membership and an explicitly single contiguous extent; ranges, size, address and IDs need exact integral checks, not bool/int coercion. No copied bytes, arbitrary offset or caller object is an accepted target object.

Existing mkobj._run_objdump uses an unpinned PATH executable and no timeout; find_call_targets has a safe fast path for bytes with no possible PC-relative reference; write_object takes file paths and invokes that discovery. The producer must preserve all reference/relocation refusals while supplying a pinned, bounded decoder path. If a new backwards-compatible keyword is necessary in mkobj.py, that narrowly scoped extension may be owned alongside a future producer. Do not temporarily mutate module globals or PATH. Reuse grid deadline and owned-workspace semantics. Pin actual code/executable/dependency identities rather than merely a caller label. Never invoke ldd against untrusted images during verification or claim a caller-provided closure manifest is complete without a trusted resolver.

Existing verify_by_recompute compares named output refs and status/reason; it does not itself verify proposal task_id/basis or authenticate every advertised object. The producer's verification must validate its own result/spec association and actual immutable refs and compare both generated object and receipt. Compiler-output binding is separately owned by Task11.1 and must not be changed by this slice. No grid framework-wide refactor, report/UI adapter, schema migration, live catalog registration or fake accepted-source provider belongs here.

Suggested eventual source ownership: new grid_lanes/target.py; narrow grid_lanes/__init__.py and splitter.py registration; minimal keyword-only mkobj injection if required; new focused target-producer regression source and narrow verification note. No source writer currently owns these files. Exact implementation ownership and API values must be added here after the decoder/snapshot contract decision. No tests, builds, source imports, project/database execution, recovery CLIs, process/service changes, systemctl, catalog submissions or live activation are permitted. Regression sources may be prepared, not executed. Controller alone stages and commits in this shared worktree.


## Adopted implementation contract for slice11.2

The controller adopts next-target-object-contract.md in full below. Its reference-free-only mode supersedes the earlier discovery proposal to solve general objdump closure in this first producer. Implement this concrete bounded producer; do not stop at schema/stub/refusal-only scaffolding.

# Bounded mkobj target producer contract

Date: 2026-10-02. Design only; no producer execution or acceptance receipt.

## Decision and scope

Implement `mkobj-target`, kind version 1, in **reference-free-only** mode. It binds an immutable corpus snapshot and raw image to exactly one selected physical function and generates the actual COFF object through `mkobj.write_object`. It never resolves or executes an external decoder. A region that might contain a PC-relative reference deterministically refuses with `mkobj_target_decoder_required`. This is a real, deliberately narrow producer for supported regions, not a claim that the objdump prerequisite is solved.

The retained no-decoder shortcut needs a conservative correction before reuse: `_BRANCH_BYTES` omits `0xC7`, while `XBEGIN` uses `C7 F8` followed by a relative displacement. For example, `c7 f8 01 00 00 00` contains none of the currently screened i386 bytes. This is a source-established omission, not an observed runtime failure. Add C7 to the conservative opcode exclusion and prepare a regression. False refusals from opcode bytes appearing in operands are acceptable; false acceptance is not.

The predicate must exclude every byte in the existing branch set **plus C7**, and, for AMD64, every byte satisfying `(b & 0xC7) == 0x05`. Preserve the existing unsupported-machine check. This covers the possible opcode/ModRM starts regardless of instruction boundaries, including prefixes. This predicate only establishes absence of supported x86 PC-relative forms; it does not validate every instruction, discover absolute references, prove semantic equivalence, or reconstruct a whole image. Receipt claim is exactly `raw_image_function_target_object`, scoped to the retained mkobj semantics.

General decoder-dependent production remains a distinct open predicate. Do not use PATH, `shutil.which`, compiler/linker/assembler identities, a caller-declared dependency list, a callback returning empty relocations, or module-global monkeypatching as a substitute.

## Source ownership and APIs

A future implementation worker may own only:

- New `src/agentdecompile_recovery/grid_lanes/target.py`.
- Narrow registration in `grid_lanes/__init__.py` and `grid_lanes/splitter.py`.
- The keyword extension and C7 predicate correction in `corpus/mkobj.py`.
- Focused target-lane/mkobj regression source and its verification note, at a path coordinated with the controller.

No compiler/parity receipt edits, dashboard provider, view schema, trust framework, live action catalog, process changes, or publication are part of this scope. Other workers own packaging/parser and frontend publication. Controller alone stages/commits.

Proposed signatures, preserving current callers:

```python
# corpus/mkobj.py
find_call_targets(code: bytes, machine: int, *,
                  reference_free_only: bool = False) -> dict[int, int]
write_object(*, binary: Path | str, offset: int, size: int, name: str,
             output: Path | str, symbol_prefix: str = "_",
             format: str = "coff-i386",
             reference_free_only: bool = False) -> Path
```

Require `type(reference_free_only) is bool`; an arbitrary truthy value is invalid. `find_call_targets` checks machine, then the corrected conservative predicate. If the predicate passes, return `{}`. Otherwise, if the keyword is true, raise `MkobjRefusal("decoder_required")` **before** `_run_objdump`. Only legacy false calls retain the existing decoder path and refusal handling. `write_object` forwards the keyword. Do not accept a decoder callable, arbitrary command, fabricated discovery result, or caller-selected relocation map.

```python
# grid_lanes/target.py: signatures use existing grid types
class MkobjTarget(PlannableKind):
    name = "mkobj-target"
    version = 1
    budget = BudgetClass.SMALL
    def run(self, spec: TaskSpec, objects: ObjectStore,
            scratch: str) -> TaskResult: ...
    def verify(self, spec: TaskSpec, result: TaskResult,
               objects: ObjectStore, scratch: str) -> Verification: ...

# registered in splitter; implementation can delegate to target.py
plan_mkobj_target(objects: ObjectStore, snapshot: Snapshot,
                 basis_hash: str, shard_size: int, **options) -> list[TaskSpec]
```

One explicit selector per planning invocation; no corpus-wide implicit scheduling. Required options are `binary_id`, `addr`, `image_ref`, `corpus_scope_sha256`, `generation_sha256`, `report_version`; optional `timeout_s`. `shard_size` does not multiply or widen the selected extent. Derive size and `func.id` from the snapshot; reject caller-supplied offset, machine, symbol, size override, decoder, output-object, or unknown options. The integration owner supplies scope/generation tokens from admitted current configuration; they are bound labels, not self-authenticating authority.

Use `plan_tasks` and `snapshot_store` as retained. A store snapshot reference must materialize and be independently hashed before selection; do not accept a manifest in place of a SQLite snapshot. For the object-reference route, derive corpus basis from that same materialized snapshot and require equality to `basis_hash`; the general planner's caller basis is insufficient. Do not add the kind to `REPAIR_KINDS`, replace the normal corpus basis, or add a second global planning framework.

## Exact TaskSpec and selection contract

Required input names, with no additional inputs: `store` (immutable SQLite snapshot), `image` (immutable raw PE image). Use restricted object roles for snapshot, image, target and receipt in this first scope. No live raw-image path or database filename belongs in the spec or receipt.

Require `spec.budget == SMALL` and exactly one capability, `mkobj-target-reference-free:<implementation_sha256>`, derived by `required_capabilities(spec)`. These scheduler fields are outside the retained task-ID projection, so validate them explicitly instead of assuming task-ID equality authenticates them. Register that capability only through existing owned canary/admission machinery; the task string itself does not qualify a node. Use the existing snapshot-subject partition assignment and no target-specific materialized view hook in this slice.

Required params, with no unknown fields:

| Field | Exact requirement |
|---|---|
| `selection` | Object with exactly the fields listed below, all rederived/checkable |
| `selection_sha256` | Lowercase SHA256 of grid `canonical_json(selection)` |
| `implementation_basis` | Closed manifest below, generated by owned implementation, not supplied as a resolver |
| `implementation_sha256` | SHA256 of canonical implementation manifest |
| `decoder_mode` | Exactly `reference-free-only-v1` |
| `timeout_s` | Finite positive int/float, excluding bool; at most 60 seconds |

`selection` fields: `schema="agentdecompile.mkobj-target-selection/v1"`, `store_ref`, `image_ref`, `corpus_scope_sha256`, `generation_sha256`, `binary_id`, `func_id`, `addr`, `size`, `ranges=1`, `report_version`, `image_sha256`. Ref fields use `sha256:<64 lowercase hex>`; digest fields use 64 lowercase hex. `binary_id`/`func_id` are exact positive Python/SQLite integers; `addr` is exact nonnegative integer; `size` is exact positive integer; bool/float/string coercion is forbidden. The first scope supports addresses representable in signed SQLite INTEGER. `addr + size` must remain within the derived PE address width. Generation/scope hashes are required opaque authority tokens, never silently synthesized from a caller path.

During both planning and **every** run/recompute:

1. Materialize both CAS inputs into a newly owned scratch subdirectory; stream-hash actual bytes and compare to refs. Do not rely on `exists`, store naming or `get_path` success. Bound materialization, including stores without streaming support; refuse an adapter lacking a bounded read/size route rather than allocating unbounded input.
2. Open only the verified snapshot with SQLite `mode=ro&immutable=1`; no migrations, schema repair or live-store fallback. Require ordinary `binary` and `func` tables with the required columns, no view replacements. Disable extension loading, enable `trusted_schema=OFF` where supported, and do not call recovery store initialization. Use bounded SQL and a progress handler tied to the lane deadline.
3. Query `binary WHERE id=?` and `func WHERE binary_id=? AND addr=?`, retrieving at most two rows to establish singleton membership even for malformed snapshots lacking expected uniqueness. Require exactly one of each. Require DB values `binary.id`, `func.id`, `func.binary_id`, `func.addr`, `func.size`, `func.ranges` to have exact integer types and `ranges == 1`. Derive `func_id/size` from those rows and compare the full selection; do not query only by attacker-supplied `func_id` or trust a JSON extent.
4. Require well-formed lowercase `binary.content_sha256 == image_ref.hex == selection.image_sha256 == report_version`. Do not use slug, repo path, MD5, logical identity or caller name to infer the association. Recompute corpus basis from this connection/snapshot and require `spec.basis_hash` equality; unsupported/incomplete basis refuses.
5. Read machine and optional-header magic from the same verified raw bytes. Allow only PE machine `0x014c` with magic `0x10b`, or `0x8664` with magic `0x20b`. Derive COFF format from that pair. Require whole-region `file_region_offset(raw, addr, size)` to return an offset, preserving its raw-backing, overlap, virtual-padding and cross-section refusals. Never trust DB architecture/image-base fields to override bytes.
6. Regenerate the exact selection JSON and hash; compare every field. The snapshot content digest is the immutable scope authority for this operation. Current live membership, scope admission and generation are later acceptance-reader checks, never inferred from immutability alone.

Use existing SMALL budget (60 s maximum), with explicit v1 limits: snapshot <=256 MiB; raw image <=128 MiB; function size <=64 KiB; canonical receipt <=32 KiB. These are admission caps, not performance promises. Larger cases refuse, never quietly change budget. Check monotonic deadline between bounded stages; hash/copy in chunks, enforce SQLite progress cancellation, and rely on the retained worker deadline as the outer kill boundary. No new subprocess is needed for this mode. On infrastructure/deadline failure, return no successful output pair.

## Loaded implementation basis; no external decoder identity

Keep a lane-local fixed manifest and checker; no resolver registry or acceptance callback. Manifest schema is `agentdecompile.mkobj-target-implementation/v1`, containing:

- `kind`, `kind_version`, `decoder_mode`, `selection_schema`, `receipt_schema`.
- Relative source-path -> SHA256 for the actual loaded `target.py`, `corpus/mkobj.py`, `corpus/verify_recovered_byteexact.py`, `corpus/determinism_basis.py`, and the grid canonicalization/core helper source files actually used. Resolve each from the loaded module's `__file__`, not cwd or a guessed canonical checkout. Source absent or unreadable means unavailable.
- A fixed list of qualified function names -> normalized **loaded code-object** fingerprints, including the lane validation/run/verify and basis helpers, mkobj's predicate/discovery/writer/object builder/symbol helper, `file_region_offset`, consumed corpus-basis functions, and consumed grid canonicalization/hash functions. Include nested code constants recursively. Hash deterministic code fields and typed constants; exclude filename/line-table location noise. Include actual loaded machine/branch/relocation constants and lane limits in the manifest. Require the expected helper bindings to reference those exact checked functions; a monkeypatched function/global cannot inherit a former identity.
- Python implementation/cache tag/version/optimization mode and SQLite version as compatibility facts, plus `external_decoder=null` and `external_decoder_dependencies=[]`. These null/empty fields explicitly mean none executes in this supported path; they do not describe the legacy objdump path.

Prevent the disk/loaded-code mismatch trap: compile captured source bytes **without executing/importing them**, extract the expected function code objects, and compare normalized fingerprints against the loaded functions. A source edit under an old imported function refuses `mkobj_target_loaded_source_mismatch`. Hold the captured bytes/function references for this run, check the fixed relevant globals before and after generation, and reread/hash source files before publishing outputs. Any changed source or binding refuses. This is a fixed source consistency check within target.py, not a general environment attester. Static checker review must enumerate helper dependencies actually reached; adding a new byte-affecting helper without manifest coverage requires revision.

Manifest equality to a task proves matching implementation identity, **not** that a caller has authority to admit that identity. Planning derives it from the installed lane; run/recompute independently derive and require exact equality. Existing worker/verifier admission must authorize this exact kind/policy/implementation basis. Owner-admitted Python/grid runtime remains the execution trust boundary; these fingerprints are not an assertion of an exhaustive hermetic Python/SQLite/native-library closure. No new trusted runtime or generic deployment framework is being invented here.

The future independent acceptance reader must check this basis against owned current admission configuration, trusted verifier lineage and revocation state. Missing admission is unavailable; a previously accepted but now disallowed implementation is stale. Merely supplying an `implementation_sha256` matching a newly generated manifest cannot create acceptance.

## Generation, canonical receipt and verification

Use fixed symbol `F_<addr in lowercase hexadecimal, no fixed-width truncation>` with `symbol_prefix=""`; it is a deterministic object identity, not a recovered semantic name. Format is derived above. Invoke:

```python
write_object(binary=owned_image_path, offset=derived_offset, size=derived_size,
             name=derived_symbol, output=owned_target_path, symbol_prefix="",
             format=derived_format, reference_free_only=True)
```

Reread/re-hash scratch input files after generation to detect changes; never resolve a mutable original path again. Hash the actual generated output bytes, store them, and confirm the returned ref equals that hash. Write no target result if mkobj refuses. Hash-check CAS publication responses for both named outputs. Local unreferenced partial CAS writes after a publication failure confer no authority.

Successful result has `status=OK`, `reason=""`, exact outputs `{"target": object_ref, "receipt": receipt_ref}`, and exact task ID/basis. Elapsed time and diagnostics belong only in metrics. Canonical receipt contains exactly:

- `schema="agentdecompile.mkobj-target/v1"`, `claim="raw_image_function_target_object"`, `status="produced"`.
- `kind`, `kind_version`, `task_id`, `basis_hash`.
- Complete `selection`, `selection_sha256`, `implementation_basis`, `implementation_sha256`, `decoder_mode`.
- `mapping={"file_offset": int, "machine": int, "optional_magic": int, "format": str}`.
- `symbol`, `target_ref`, `target_sha256`, `target_size`, `region_sha256`, `relocation_count=0`.

The embedded selection names both immutable inputs, exact physical row/extent, image/report version and requested corpus/generation scope. No `accepted`, source hash, parity grade, target-image recovery percentage, host path, wall-clock time, producer name or verifier key belongs in this content receipt. Those identities/signatures are handled by the existing grid records.

`verify` must first validate the TaskSpec shape and proposal association: exact `result.task_id == spec.task_id`, exact basis, OK/empty reason, and exactly the two output names. Fetch and independently hash actual advertised bytes, enforce bounds, parse receipt with duplicate-key rejection, and require its bytes equal canonical serialization. Validate the exact receipt schema/fields, embedded target ref/hash/size, selection/task/kind/basis/implementation binding and successful produced claim. Do not trust an unauthenticated receipt's stated target hash.

Then call the existing `verify_by_recompute(self, spec, result, objects, scratch, compare=("target", "receipt"), method="mkobj-target-reference-free-v1")`. Recompute must use a distinct owned scratch subdirectory and all the same input/selection/loaded-basis validation. No proposal object can be passed as a generation input. Require byte-exact object refs, not a masked-COFF hash. The fixed generator already writes timestamp zero; do not introduce masking.

A positive Verification is signed/admitted through the retained independent grid verifier path. Lane verification neither signs with fabricated keys nor bypasses signer/producer independence. Successful `run`, successful deterministic recompute, and current independently admitted persisted acceptance are separate predicates.

## Stable refusal and availability semantics

Prefix every lane reason `mkobj_target_`; details must not contain host paths/slugs. Do not add grid enum values.

| Condition | Run/planning reason and behavior | Verify handling |
|---|---|---|
| Wrong kind/version/shape/unknown fields, bool/string/float integer spoof | `invalid_spec`; raise Refused | Invalid proposal binding is REFUTED; invalid/unrunnable spec is UNVERIFIABLE |
| Missing required immutable bytes | `input_unavailable` | UNVERIFIABLE, without claiming producer dishonesty |
| Hash differs from requested CAS ref | `input_integrity_failed` | UNVERIFIABLE for corrupted input transport; proposal output/receipt digest contradiction is REFUTED |
| Unsupported/malformed snapshot schema | `snapshot_unsupported` | UNVERIFIABLE |
| Missing or multiple selected rows | `selection_missing` / `selection_ambiguous` | UNVERIFIABLE for unsupported spec; proposal claim disagreement is REFUTED |
| Selection/version/image/declared corpus basis disagreement | `selection_mismatch` / `image_mismatch` / `basis_mismatch` | UNVERIFIABLE when task cannot execute; REFUTED for proposal contradiction |
| Invalid/multirange/unknown extent or cap exceeded | `extent_unsupported` / `input_limit_exceeded` | UNVERIFIABLE |
| PE machine/header mismatch or non-PE | `format_unsupported` | UNVERIFIABLE |
| No unique whole raw-backed mapping | `mapping_unsupported` | UNVERIFIABLE |
| Any possible PC-relative reference | `decoder_required` | UNVERIFIABLE; no attempt to discover objdump |
| Unknown decoder mode/any requested external decoder | `decoder_unsupported` | UNVERIFIABLE |
| Loaded source unavailable/mismatched/changed during run | `implementation_unavailable` / `loaded_source_mismatch` / `implementation_changed` | UNVERIFIABLE |
| Task requests a different implementation manifest | `implementation_mismatch` | UNVERIFIABLE; consumer may label prior acceptance stale |
| Proposal wrong task/basis/output names/schema/content binding | N/A | REFUTED with `proposal_binding_invalid` |
| Proposal objects cannot be fetched | N/A | UNVERIFIABLE with `proposal_unavailable` |
| Independently regenerated output or receipt differs | N/A | REFUTED by existing recompute comparison |
| Deadline or I/O/SQLite execution failure | Infrastructure failure; no OK pair | UNVERIFIABLE with `execution_unavailable` or `deadline_exceeded` |

Preserve any reachable MkobjRefusal by mapping its stable name, e.g. `mkobj_target_decoder_required`; never downgrade a refusal to an empty relocation map. Catch infrastructure exceptions at the lane verify wrapper because `verify_by_recompute` only catches Refused today; do not modify the generic helper. Do not turn unavailable/stale/failed admission into observed numeric zero or a dashboard connection.

## Regression source cases to prepare, not execute in this mission

1. Minimal raw-backed i386 and AMD64 PE fixtures, one `ranges=1` function using safe bytes (e.g. NOP/RET), deterministic two-output result; independent verifier reproduces both references through the actual write_object path.
2. Instrument forbidden `_run_objdump` in regression source: supported regions never reach it; C7/XBEGIN, E8/E9, short branches, 0F escape, AMD64 possible RIP-ModRM all refuse before it. A C7 byte in immediate data may refuse conservatively. Existing default callers still take the legacy decoder path when required; corrected C7 screening prevents the old fast-path omission.
3. Snapshot selection spoof, wrong func_id/binary/address/size/ranges/version/image hash; zero/multiple rows in deliberately non-unique schema; missing/null/multi-range extent; exact-integer checks reject bool/string/float; caller offsets and output-object extras rejected.
4. Wrong machine/magic pair; truncated PE; virtual-only region; raw padding; cross-section/overlap; zero/negative/overflow address/size; size/resource cap boundaries.
5. Missing/corrupt input and output objects, CAS adapter lying about materialization or returned ref, changed scratch bytes, malformed or duplicate-key receipt, forged task/basis, extra/missing output, valid receipt naming wrong actual object, changed object with unchanged receipt, changed receipt with unchanged object.
6. Generator/mapper/policy loaded code changes; source modified without reimport; helper monkeypatch; changed branch/machine constants; another cwd/source root; implementation manifest self-asserted by task; unavailable source; hash/selection/report changes force a new task ID and never reuse the old result.
7. Planner from immutable ref rederives basis; snapshot membership changes selection/task ID; timeout/SQLite cancellation/storage error yields no successful result; verifier inability is UNVERIFIABLE, deterministic recompute disagreement is REFUTED.
8. Existing independent-verifier policy rejects same producer lineage, revoked/disallowed identities and unadmitted implementation. These are runtime/integration cases if existing fixtures cannot represent authority; do not implement a permissive callback to make the source test pass.

## Separate decoder and real runtime gates

A future broader mode needs an owner-qualified decoder artifact and execution closure. The smallest plausible external scope is one exact, audited static objdump build with plugins/NLS/optional module loading disabled, a retained build recipe/source/dependency manifest, and a pinned artifact SHA256 admitted by the owner. Check ELF static properties without executing the candidate, but absence of PT_INTERP/DT_NEEDED alone is insufficient proof that code cannot load files/modules. Existing system objdump and an arbitrary caller-built static file are not qualified. A dynamic decoder additionally needs a trusted resolver for loader/search paths/transitive libraries/modules/data; there is no such established resolver in the inspected lane. Neither path is implemented by this design.

That future invocation must use the fixed admitted absolute artifact in an owned directory, bounded input/output and process-group deadline, deterministic explicit environment, rechecked artifact/dependency bytes, and retained mkobj parse/relocation refusal behavior. An API for that future mode is deliberately not prebuilt into this slice.

Remaining real gates: controller authorization for source implementation; source review of the explicit loaded closure; separately authorized regression execution; an actual admitted snapshot/raw image with supported extent; actual object store and worker/verifier capability/admission; independent persisted verification; and an owned action exposed by the existing 8080 catalog. No catalog availability or runtime artifact was inspected. If no catalog action exists, action integration remains separate work; direct CLI/alternate port execution is not a fallback. A reference-free producer can be completed without claiming general target-object coverage. Dashboard provider remains `not_connected` until target + exact source/compile + full parity + current admission chain is independently satisfied.

Only this design note was written. No source/index/Git edits, imports, tests, builds, proofs, runtime/database/process/service/catalog/network actions were performed.


## Controller execution authority

Source implementation is now authorized in this isolated worktree, including the exact owned source paths and API/refusal/manifest/resource-limit values above. Start base2590e25a5926d195f34e88b0675095cf1891e6c2. Own new grid_lanes/target.py, narrow grid_lanes/__init__.py/splitter.py registration, mkobj.py conservative C7 predicate and backwards-compatible reference_free_only forwarding, new tests/test_grid_target_binding.py, existing focused mkobj regression source only if necessary, one narrow verification note and task-11-target-report.md here. Do not edit compiler/parity/grid core/object store/other producers or the current dashboard. Task8 owns ingest/package; Task42 owns frontend assets. You are not alone: preserve every other owner's changes. No subagents, staging or commits; controller owns Git.

The explicit limits are policy admission caps, not measured throughput or established runtime availability. Keep separate unsupported general decoder coverage and actual admitted worker/verifier/catalog execution. Source manifests and scope/generation tokens do not self-authorize acceptance. Keep the loaded-source checker fixed to this lane's byte-affecting helpers/constants and owned runtime boundary, not a generic code attestation framework. Existing ObjectStore protocol exposes size(ref); LocalDirStore also exposes stat/get_path. Validate size before bounded materialization, copy rather than hard-link mutable scratch inputs to CAS, and authenticate actual bytes afterward. Known trusted adapter methods do not grant an untrusted adapter permission to ignore byte limits; failure is unavailable.

All verification is source-only in this mission. Do not run imports, tests, suites, builds, compiler/decoder/Ghidra/proof scripts, database creation/query, recovery CLIs, workers, services, systemctl, catalog actions or process mutation. Regression source may be authored but not executed. AST/diff/call-site/source-shape checks are allowed. Parent has refreshed healthy8080 PID2697197/start1790595674.5226107/cwdNVMe/startticks68973313/restarts0; retained matching-process module paths are MyBook source revision753d7fce. Isolated source is not activation. Report self-review, exact check commands/results, authored/unrun positive/refusal cases, ownership and all remaining real consumer/independent acceptance gates; return READY_TO_COMMIT and stop editing.
