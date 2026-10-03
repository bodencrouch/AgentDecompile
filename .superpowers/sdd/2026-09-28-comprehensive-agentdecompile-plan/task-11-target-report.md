# Task 11.2 implementation report

Status: READY_TO_COMMIT for controller review and source integration; runtime and
independent acceptance remain unverified. No commit was created or staged.

## Implemented

`grid_lanes/target.py` implements the bounded `MkobjTarget` producer and planner,
using the real retained `mkobj.write_object` path. It consumes exactly one
immutable SQLite snapshot and one immutable PE image. Planning and every run
materialize and authenticate both inputs, enforce singleton physical membership,
rederive the existing corpus basis, compare the exact selection and image/report
identity, and derive machine/format/whole-region offset from PE bytes.

The implementation enforces SMALL/60-second policy and the supplied snapshot,
image, function and canonical receipt caps. Chunked copies/hash checks and SQL
progress cancellation support the existing outer worker deadline. Every run owns
a unique temporary subdirectory. No decoder runs in this mode.

A fixed implementation manifest covers loaded source paths, 59 explicit loaded
function fingerprints including nested code constants, relevant machine/branch/
relocation/policy constants, Python compatibility facts and SQLite version. The
source check compiles captured bytes without execution and compares code and
literal defaults with loaded functions. Checked function/module aliases cannot
reuse former identities after replacement. Source/binding/constant identity is
checked again around generation/publication. The manifest explicitly declares
no external decoder and does not purport to attest the whole Python/native
runtime or grant admission.

The producer emits a deterministic timestamp-zero COFF object with symbol
`F_<addr>` and a canonical bounded receipt naming the exact input selection,
implementation basis, derived mapping, region digest and actual output digest.
It rehashes scratch inputs after the writer and checks both CAS publication refs.
A run is only a proposal about raw-image/function derivation.

Verification first checks the proposal's task/basis/status/output association,
fetches and independently hashes both advertised outputs under bounds, rejects
duplicate/noncanonical receipt JSON, and checks exact receipt/content binding.
It then uses the retained `verify_by_recompute` with both `target` and `receipt`.
Recomputation gets a distinct owned scratch directory and repeats all validations.
Unavailable infrastructure remains UNVERIFIABLE; malformed/contradictory proposal
bytes are REFUTED. The generic verifier, trust policy and view schema are unchanged.

`mkobj.py` now conservatively screens C7 (XBEGIN) and accepts an exact-boolean,
backwards-compatible `reference_free_only` keyword. True refuses possible
references before objdump; false retains the legacy path. Narrow package and
splitter registrations expose the lane through existing task planning and
snapshot-subject partitions; it is not a repair kind and has no target view hook.

## Ownership

Only these implementation/test/note files were changed by this implementer:

- `src/agentdecompile_recovery/grid_lanes/target.py` — new producer/planner.
- `src/agentdecompile_recovery/grid_lanes/__init__.py` — narrow registration/docs.
- `src/agentdecompile_recovery/grid_lanes/splitter.py` — narrow planner registration.
- `src/agentdecompile_recovery/corpus/mkobj.py` — C7 predicate and keyword forwarding.
- `tests/test_grid_target_binding.py` — 42 regression functions, many parametrized.
- `.superpowers/sdd/2026-09-28-comprehensive-agentdecompile-plan/task-11-target-verification.md`.
- This report.

Other owners' frontend, parser/packaging and progress changes were preserved.
No controller plan, compiler/parity producer, dashboard, generic grid trust/store
module or recovery catalog was edited. No subagent was dispatched.

## Checks and TDD status

All verification was source-only as explicitly required. Five Python files passed
`ast.parse`. The fixed-closure AST audit located all 59 qualified functions and
confirmed checked defaults are literal. A call-site AST audit found one writer
call with `reference_free_only=True` and empty prefix, and no subprocess call in
the lane. Narrow `git diff --check` returned exit 0 with no diagnostics.

Exact check descriptions, commands/results, source coverage and unrun gates are
recorded in [task-11-target-verification.md](task-11-target-verification.md).
There was no red/green TDD run: tests/builds/project imports were prohibited by
the controlling mission. The regression file is authored evidence, not passing
behavior. No database was created/queried and no compiler/decoder/runtime/catalog
operation was performed during implementation.

## Self-review and refinements

- Bounded transport was narrowed with explicit controller agreement to local CAS.
  The ObjectStore protocol's unbounded `get()` is not used as a purported safe
  fallback. Local paths use containment/no-follow checks and copying, not links;
  unsupported adapters are unavailable. Future adapters need qualified bounded IO.
- The loaded-source checker includes corpus policy dependencies actually consumed
  by `determinism_basis`, not merely its top-level function. Functions inspected
  only for signature defaults (`evaluate_pairs`, `unique_window`) are fingerprinted;
  their unrelated executable bodies are never invoked by the basis path.
- Literal defaults are reconciled as well as code, closing source-only default
  edits that would otherwise leave a stale imported callable undetected.
- Scheduler budget/capabilities are checked explicitly because they are outside
  the retained task-ID projection. Caller selection/output/decoder extras refuse.
- Receipt verification authenticates actual output bytes before symmetric
  recomputation; receipt claims alone do not authorize an output object.
- SQLite is opened only from the authenticated owned snapshot with read-only and
  immutable URI flags, extensions disabled, trusted schema disabled, and deadline
  progress cancellation. Ordinary required tables/columns are checked first.
- The lane is a substantial single focused module (roughly 680 lines), largely
  boundary validation and a fixed manifest; no general attestation or adapter
  registry was introduced. Review should focus on this explicitly enumerated
  dependency boundary and resource/refusal semantics.

## Remaining concerns and acceptance gates

No behavioral assertion is established by the AST review. Runtime import,
manifest/receipt size, deadline behavior, actual output reproducibility and the
regression expectations must be verified in the separately authorized execution
phase. Python/grid runtime, standard library and native SQLite remain owner-admitted
execution boundaries; this is not a hermetic native dependency attestation.

Independent key lineage, revocation/current implementation admission, persisted
verification, actual snapshot/raw-image availability and an owned 8080 catalog
action remain integration gates. The implementation creates no acceptance keys,
permissive resolver or dashboard connection. General reference-bearing regions
remain unsupported. Source/compile/full-object parity and current report admission
are separate unfinished prerequisites for accepted-source progress.
