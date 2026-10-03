# U4 direct acceptance: same-build contribution contract

Source-only contract, 2026-10-02, against controller-supplied source base
`1f29d91dad54999db2f12e7af9ac8eba51f754bb`. This investigation owns only this
document. It consumes `next-reconstruction-prerequisite.md`, U4, U33 and
STRATEGY's whole-image rules; it does not repeat the broader source audit or
reopen historical receipts. Source reads below answer only producer-interface
and action-ownership questions. No test, import, build, proof script, database,
compiler, Ghidra, runtime/catalog/process inspection, service, Git mutation or
publication was performed. Memory was used only for the source/live distinction.

## Decision and dispatch boundary

**The smallest ready implementation is a refusal-only honesty correction in
`verify_direct_full_image.py`.** Generic link success and a separately compiled
masked local receipt cannot establish same-build compiled replacement ownership.
Keep their diagnostic results and the exact full-file comparison, but refuse
terminal `verified` and `compilerProducedWholeImage` while the owned direct
producer has no qualified linked-contribution observation. This corrects an
acceptance claim; it is not a completed positive recovery producer, U4 closure,
U33 closure or permission to activate/run the route.

**An independent, narrow catalog metadata/parameter correction is ready. Full
compiler/Wine/output admission wiring is not ready merely by adding the action
to the external-contract map.** That map also qualifies release after session
clearance. The current arbitrary wrapper and Wine route lacks an audited actual
resource and process-lifetime boundary. An action-local qualification/refusal
slice can be dispatched independently of terminal acceptance and parity/matrix,
but its current supported admission result must remain refusal until those
specific premises exist. Do not change generic job-store admission, reservation,
release, reconciliation or worker-slot policy to accommodate this action.

## Owned producer and consumer interfaces

All source paths in this document are under
`src/agentdecompile_recovery/corpus/` unless stated otherwise.

The existing direct producer is
`compile_link.compile_and_link_tree(src_dir, output, *, compiler, sample,
obj_dir, workers, entrypoint, vcroot, wineprefix) -> dict`.
Its returned `ok`, `units`, `objects`, `failed`, `failures`, `skipped`,
`linkSkipped` and `link` describe generic compilation/linking. The direct caller
owns `work/candidate.exe`, `work/objects`, `work/function-objdiff.json` and
`work/receipt.json`, with a newly created work directory. The direct consumer
is the acceptance assignment in `verify_direct_full_image.main` immediately
after the whole-file comparison (`:99–116` in the prerequisite source).

For the ready refusal correction:

1. Preserve the invocation and the diagnostic local verification path, existing
   fresh-work refusal, complete candidate/target size plus SHA-256 comparison,
   negative receipt persistence, and public CLI arguments. Avoid changing the
   generic meaning of `compile_and_link_tree.ok` for its other callers.
2. Add an explicit diagnostic field, e.g. `linkedContribution`, with
   `status: "unsupported"`,
   `reason: "same_build_linked_contribution_unavailable"`, and a stable list of
   missing bindings described below. This field is an exported explanation,
   never an authority-bearing input. No new receipt import, callback, CLI trust
   flag or caller-provided `complete` boolean is allowed.
3. Append the missing-contribution refusal to `errors`; set terminal `verified`
   to false and return nonzero. Set `compilerProducedWholeImage` to false. A
   generic successful link remains visible in `build.compileLink`; the stronger
   flag cannot be recovered from its `ok` value. Leave `wholeFileByteIdentical`
   as the independently measured whole-file fact, including when it is true.
4. Make the module description and receipt claim boundary accurately describe
   the diagnostic direct build and unavailable terminal contribution proof.
   Existing schema fields remain present. Corrected booleans are deliberate
   tightening of acceptance, not an incompatible removal of diagnostics.
5. Do not consume `source_contribution.ReconstructionObservation` as a substitute
   for direct linking. Do not flip `finish_binary` flags or implement
   `dashboard.byte_parity._full_image_receipt` from exported JSON. Dashboard
   consumer integration belongs to a later producer-backed slice.

This patch does not need a dormant generalized trust framework or an injectable
"trusted evaluator." There is no current positive object to pass through such
a seam. If a private decision helper is extracted for clarity, it must derive
the unavailable direct producer result internally; callers cannot select its
truth value by passing a success-shaped dict.

## The positive predicate that is actually missing

For one explicitly selected variant and one fresh owned build invocation,
terminal acceptance requires the conjunction below. Failure or unavailability
of any term refuses terminal acceptance; an empty required inventory cannot
pass vacuously.

`freshCompleteBuild AND boundCurrentIdentity AND admittedToolchain AND
 sameBuildLinkedContribution AND exactWholeFileEquality`

The future concrete direct producer must own compilation, linking and
observation. The direct consumer must receive its process-local result directly
from that producer invocation and revalidate it before reporting success.
Serialized copies and reconstruction of a record from fields confer no trust.
Use a narrow typed result for that one supported backend only when it exists;
do not expose arbitrary observation registration or external authentication
callbacks. Its minimum consumed bindings are:

| Binding | Producer must establish; consumer must check |
| --- | --- |
| Build and selection | One invocation identity; fresh owned workspace; chosen executable hash/size, selected corpus/project identity and function inventory digest; variant `byte-accurate-c-floor` or `max-c`; recovery method kept distinct from original-style rebuild. No borrowing across variant, binary or inventory. |
| Complete source capture | Enumerated expected TU/group set and complete source/dependency closure captured before compiling; source bytes, generated preamble, headers, startup, associated data/resources and build inputs included or explicitly unsupported. Re-enumerate/recheck current source and inventory before publication/consumption. Missing, added, changed, duplicate or silently excluded required units refuse; counts alone do not establish completeness. |
| Toolchain | Repository-supported exact compiler, linker, wrapper if any, runtime/loader dependencies, headers/libraries, options, environment and platform/group scope, with hashes and observed effective invocation. A supplied wrapper path or version string is insufficient. |
| Same-build objects and image | Every required unit compiles freshly and cleanly from that capture. Preserve full unit-to-object identities and hashes, actual ordered linker inputs/response-file content, link argv/environment, diagnostics, and the exact candidate image hash. No partial success, cached object/link substitution, unexplained input or forced unresolved link. |
| Linked replacements | For every required compiled replacement, map the same invocation's object section/range to the final checked image region and independently verify placement, symbol/fixup targets and reconstructed addends, associated data and required metadata. Local relocation-aware checks and linked checks refer to these same objects. Link maps are evidence to check against emitted bytes, not self-authenticating truth. |
| Final ownership and accounting | Replacements must actually own their required compared output after all final writes/link transformations. Discard, identical-code folding into another owner, collision, overlap or preserved fallback cannot confer that replacement's C credit. Floor remains explicit and excluded from C counts; `max-c` receives no floor credit. A required replacement losing ownership refuses the claimed complete build even if equal floor bytes remain. |
| Final equality and currency | Reopen the final candidate and target; compare entire sizes/hashes and retain the fresh work isolation. Validate source, inventory, toolchain, object and candidate currency at consumption. Exact equality alone is insufficient, but remains necessary. |

These are required observations, not fields that an arbitrary caller can assert.
A positive fixture exercising a private decision function would test a decision
only; it would not establish that the real producer exists.

## What the existing producer can and cannot supply

`compile_link.py:165–229,240–305,310–416` can establish subprocess return status,
paths, the enumerated unit count, failure count, and generic linked output. The
owned fresh work directory prevents intentional reuse of its prior objects in
the ordinary route. That is useful diagnostic evidence. It does not return a
complete captured source/inventory, authenticated toolchain closure, all object
hashes, observed final placement/fixups or replacement final ownership.

Concrete barriers to upgrading the current result include recursive filtered
`*.c` enumeration, injected preamble, generated trivial `main`, partial-success
object linking, `/FORCE`, arbitrary compiler wrapper behavior and the separate
local verifier's different temporary objects. Keeping successful object counts
or disabling one linker optimization does not solve these barriers. U33's real
startup/semantic source and original-game launch are additional unresolved
premises, not fabricated by this contract.

The retained positive bounded producer is
`source_contribution.compile_observation(...) -> CompileObservation`, followed
by `reconstruct(...) -> ReconstructionObservation` and
`evaluate_reconstruction(...)`. Its weak-reference registrations distinguish
real process-local observations from imported records; its writer records final
ownership. It supports only the explicit native-clang, self-contained,
relocation-free region backend. Its reconstruction explicitly records
`compilerProducedWholeImage: False`. Preserve that producer and its boundary;
do not widen it to VC7, relocation-bearing objects or a clean semantic engine
build by assertion.

**Next actual positive producer:** a repository-owned exact-placement link
adapter for one corroborated target/toolchain/variant that freshly compiles a
captured required source set, consumes its exact objects, observes and verifies
their emitted ranges and reconstructed fixups in its final image, and returns
the bound observation above. Its first positive acceptance case must include a
real compiled replacement whose linked relocation/addend and final writer are
verified; an unchanged floor round trip remains infrastructure evidence. The
current direct wrapper/link helper and bounded native-clang backend supply no
such adapter. Selecting its supported target/toolchain, usable layout/fixup
inputs and complete real source project remains unresolved. Implementation of
that adapter is therefore **not dispatched by this contract**. Do not invent
engine sources, an assumed link oracle or a generic provider interface to make
this dependency appear complete.

## Exact action ownership and independent work

The existing action is `corpus.verify-direct-full-image`, generated from
`cli.py`'s `verify-direct-full-image` subparser through
`dashboard/actions/introspect.py`. Catalog parameter names are hyphenated
(`work-dir`, `src-dir`, `binary-id`); argparse attributes use underscores. The
correct catalog work key is **`work-dir`**, not `workDir` or `work_dir`.

An independently dispatchable metadata/parameter correction may own only the
vdfi parser block in `cli.py` and action-specific handling in
`dashboard/actions/jobs.py:_active_duplicate` and `_external_pipeline_owner`:

- Set `vdfi.mutating = vdfi.long_running = True`; no need to change introspection
  globally. Do not classify it as a Ghidra writer or infer database mutation.
- Resolve `work-dir` for this action in duplicate lookup (both new/existing
  rows) and external-owner lookup, using the same canonical execution-root
  path semantics as its eventual resource keys. Preserve existing keys and
  behavior for other actions. The current `/proc` substring lookup is only an
  exclusion hint; it does not corroborate PID/start/cwd or prove clearance.
- This source correction alone neither qualifies the action for execution nor
  releases compiler/Wine/output ownership. Live manual corroboration remains
  required by AGENTS.md, and was not performed here.

The intended minimum explicit resource tuples for a *qualified* direct route
are `(compiler, canonical compiler)`, `(compiler, canonical vcroot)` (covering
the linker/toolchain tree), `(wineprefix, canonical wineprefix)` and
`(output, canonical work-dir)`, sorted under `resourceKeys.external`. Freeze
these paths against `executionRoot` before building argv; reject aliases that
conflict with protected input/output roles. The two compiler paths do not imply
that the wrapper's actual executable/toolchain closure has been verified.

Those four tuples are **not currently a complete audited write/lifetime set**:

- `compile_unit_script` stages source siblings when a preamble is injected;
  this route always passes the preamble. Until staging is moved into the owned
  snapshot/work tree, `src-dir` is also a mutable area and needs an exclusive
  `(output, canonical src-dir)` claim. Do not silently treat source as read-only.
- The wrapper runs as `bash script source object name` without an explicit
  sanitized environment or `wineprefix`/`vcroot` binding. It can use a different
  compiler or Wine prefix from the declared link parameters. The local verifier
  invokes the wrapper separately with the same deficiency. Both invocations
  must be covered by the same audited action-local profile.
- Wine is invoked via inherited `PATH`, and existing/shared or escaped Wine
  processes are not proven owned by the Linux session. `supervision.py`'s
  `session_clearance` explicitly excludes external writers and children that
  escape into another session. A clear session cannot prove this premise.
- `_EXTERNAL_ACTION_CONTRACTS` is a qualification allowlist as well as a
  resource map: `_external_contract_matches`, `_bound_clearance`, executor
  callbacks and completion/reconciliation consume it. Adding this action
  unconditionally would confer release authority without the missing audit.

Therefore **do not dispatch a bare allowlist addition**. A separately owned
action-local guard may refuse the current unsupported wrapper/Wine profile
before spawning; support can be enabled only after its actual command/resource
closure and full child/writer lifetime are established. This does not require
rewriting generic admission policy. If that qualification needs broader policy
changes, return it as a separate blocked prerequisite rather than widening this
slice. Do not register caller-supplied "audited" JSON or let terminal receipt
success confer ownership clearance.

## Required cases for a later authorized implementation/verification run

These are regression specifications only; none were executed in this source-only
investigation. Source review can trace the branches now; executable checks need
separate authorization under the current mission constraints.

| Case | Required result |
| --- | --- |
| Generic link succeeds, local masked counts all match, exact candidate hash equals target | Ready refusal patch still emits `verified=false`, `compilerProducedWholeImage=false`, explicit unavailable contribution reason; preserves measured `wholeFileByteIdentical=true`. |
| Partial compilation or stub-main-only link succeeds | No terminal success; diagnostic failures/stub remain visible. |
| Forged or reloaded success-shaped JSON; manually constructed typed object; bounded reconstruction observation supplied as direct evidence | No direct terminal authority or C credit. |
| Pre-existing work directory; missing candidate; whole-file mismatch; stale candidate/local receipt | Existing negative behavior and work isolation retained, plus unavailable contribution boundary. |
| Qualified future adapter, complete same-build objects, verified fixups/final writers, exact equality and matching variant | Positive terminal decision only for that supported adapter and selected variant; actual producer execution required to establish positive recovery. |
| Wrong addend; removed/folded replacement; floor overwrite; object substitution after link; changed source/header/inventory/toolchain/candidate; omitted TU; variant swap | Refuse terminal acceptance; exclude lost/floor contribution from C counts even if output bytes equal target. |
| Catalog metadata and serialized parameter inspection | Exact action ID and hyphenated fields retained; action is mutating/long-running; no global introspector/admission policy changes. |
| Same/parent/child or symlink-equivalent work-dir, compiler/toolchain or prefix resource paths | Existing overlap semantics apply after canonicalization; same work-dir duplicate found using `work-dir`; unrelated nonoverlapping work remains independent. |
| Wrapper effective prefix/compiler differs from declared paths; external/escaped Wine writer; source staging outside owned work | Action-local qualification refuses before spawn, or retains unresolved ownership if discovered after launch. Never infer clearance from job status, output JSON or leader exit. |
| Queued cancellation, failed launch, unknown descendant clearance, persisted unqualified record, custom executor | Preserve existing conservative reservation/reconciliation behavior; no new allowlist-derived clearance authority. |

## Ownership and completion report

The ready refusal patch owns `verify_direct_full_image.py` only; focused
regression specifications may be added in an authorized implementation run.
The independent metadata/parameter patch owns only the named vdfi parser block
and action-specific work-dir lookup hunks. A future qualification patch must
coordinate ownership of `jobs.py` and any direct producer wrapper with the
controller before editing. Neither patch owns parity/matrix, `finish_binary`,
`source_contribution`, generic job-store policy, plan/progress, or dashboard
terminal evaluation. This investigation writes this document only.

Missing real premises remain: complete actual source/startup/inventory capture;
supported exact effective toolchain; observed same-build placement/fixup/final
writer producer; separately bound variants; safe action-specific compiler/Wine
lifetime/resource admission; later producer-backed terminal consumer integration;
fresh whole-image acceptance and U33 original-game launch. The refusal correction
and source metadata correction can be finished honestly while all of these
remain open. No positive recovery, safe current live admission, activation or
runtime outcome is claimed.
