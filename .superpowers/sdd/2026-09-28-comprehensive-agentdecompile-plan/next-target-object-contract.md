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
