# Task 25.1 implementation report

Status: DONE_WITH_CONCERNS. The bounded source change is implemented and checked
by AST/diff/source inspection. All executable regression and consumer acceptance
remain deferred under the current mission; this is not U25/U28 closure.

Base: `6e4b313d740380ea4d7af7389ce5dc0b5312643a` in
`/home/brunner56/.codex/worktrees/6e95/AgentDecompile`. Requirements came from
`task-25-brief.md`, including the controller's explicit local provider-unavailable
exception ruling. The SDD implementer prompt was read. No subagents were dispatched.
Other agents' progress/brief/source changes were preserved and excluded from staging.

## Implemented behavior

- Added keyword-only `verify_cave_receipt=None` to the exact four public APIs in
  the brief. V2 forwards the callback without a default accepting provider. V1
  does not call it; v1 operation binding and bundle transaction/publication flow
  stay in their existing branch.
- Exact build-map/type/depth preflight covers every submitted evidence object
  before evidence canonicalization. The builder hashes canonical bytes and
  parses those same bytes into the detached snapshot used by the unchanged
  scanner. Registered raw bytes/hash/architecture and submitted target fields
  are checked before qualification.
- Proposed receipts add architecture, canonical export basis digest, exact
  qualification fields, and a digest of sorted per-build candidate records.
  The local shared check verifies exact image/build/architecture/basis/candidate
  binding, actual integer count (booleans refuse), digest shapes, and the three
  required qualification fields. It makes no guessed decoder revision claim.
- Missing evidence keeps the ordinary blocker. Missing/noncallable authority
  yields unavailable, with no candidates or qualified count. False/null/1/other
  non-True verifier results yield refused, with no candidates or qualified count.
  Missing qualification fields refuse before the callback. Qualified zero
  candidates remains complete negative evidence with the empty-list digest.
- The verifier receives a detached receipt. Before/after canonical comparison
  detects changes; malformed/non-JSON/cyclic/deep changes also refuse as
  `cave_verifier_input_changed`. Explicit provider-unavailable CaveEvidenceError
  maps to a blocked unavailable result. Every other provider exception raises
  `cave_verifier_failed` with its original cause preserved. These paths never
  seal a complete receipt.
- Required validation checks the same receipt basis and candidate-content
  digest and re-invokes trusted authority. Serialized status/digests cannot
  restore trust. The validator retains ExportValidationError and specific cave
  error codes; runtime verification remains `not_run`. Optional validation
  advertises only consistency. All three bundle required validation calls
  forward the callback; initial refusal precedes root/staging creation, and
  later refusal retains rollback/staging cleanup.
- Added fixed 64-active-container JSON stack policy, root/empty containers
  counted. The iterative walker retains exact JSON types, branch-local cycle
  detection, shared acyclic subtrees and arbitrary flat node counts. Entering
  65 returns stable code/build/details before encoding/copying. Complete v2
  payloads have their own wrapper-inclusive bound, including before verifier
  invocation. Parser/encoder/copy RecursionError boundaries yield the same
  stable refusal with unknown depth null. Generated tuple member fingerprints
  remain supported by canonical_bytes.
- Clarified only the cave scanner module docstring; its signature, exclusion
  checks and deterministic candidate algorithm are unchanged.

## Source checks performed

No project source was imported or executed. No tests, proof scripts, databases,
builds, compilers, Ghidra, action catalog, live probes, process inspection/mutation,
services or systemctl were run. No activation, publication or external PR occurred.
Python commands used only stdlib AST/filesystem operations to read/edit/parse source.

Recorded check output:

```text
AST parse: 6/6 files accepted; no project imports or execution
Bundle validation forwarding: 3 calls
line 115: lua_source=lua, readiness=readiness, require_caves=True, verify_cave_receipt=verify_cave_receipt
line 155: lua_source=lua, headers=headers, readiness=readiness, require_caves=True, verify_cave_receipt=verify_cave_receipt
line 105: require_caves=True, verify_cave_receipt=verify_cave_receipt
All four APIs: verify_cave_receipt keyword-only, default None; prior defaults retained
Document test-source link exists: True
git diff --check: exit 0, no output
```

Checks used `ast.parse(path.read_text(), filename=str(path))` over the five owned
corpus modules and the new focused regression source, then inspected API keyword
arguments and bundle call AST nodes. `rg -n` inspected CLI/listing/default consumer
call sites without changing them. The v1 exporter diff was limited to its public
signature and the v2-only branch. The cave scanner diff changes one docstring line.

TDD RED/GREEN: **not run**. The controller explicitly allows writing regression
sources but forbids executing them in this mission. No passing test claim is made.

## Regression sources prepared, not executed

`tests/test_corpus_cave_qualification.py` contains a separately captured immutable
**synthetic** observation and currentness flag. The test owner compares the full
proposed receipt to that observation, rather than a permissive True stub. This
exercises trusted acceptance plumbing only; the synthetic decoder is not a real
qualified whole-image producer, and neither it nor synthetic exporter helpers
close any producer/export/runtime gate.

Sources specify positive serialized reopening/currentness refusal, qualified zero
under instruction/relocation/reference/capacity controls, missing evidence/callback,
False/null/1/truthy refusals, changed reference/decoder revision/policy/generation,
missing qualification fields, wrong registered hash/image/build/architecture,
resealed count/boolean-count/offset/anchor/byte/capacity/basis/digest tampering,
callback mutation/errors/unavailability, caller mutation after snapshot capture,
64/65 and full-pack wrapper limits, JSON exactness/cycles/subclasses/shared/100001
flat elements, defensive parser recursion, v1 callback exclusion, v2 forwarding,
and later bundle recheck refusal with staging cleanup/existing artifact preservation.

Remaining future review/execution cases include multi-build unaffected controls,
reordered/multi-candidate largest-first observations, stale anchors, unsupported
production decoder provenance, and encoder/copy defensive recursion injection.
Their source branches remain visible, but no execution is claimed.

## Files owned and changed

- `src/agentdecompile_recovery/corpus/hookpack_v2.py`
- `src/agentdecompile_recovery/corpus/export_hookpack.py`
- `src/agentdecompile_recovery/corpus/export_bundle.py`
- `src/agentdecompile_recovery/corpus/export_validation.py`
- `src/agentdecompile_recovery/corpus/cave_discovery.py` (docstring only)
- `tests/test_corpus_cave_qualification.py`
- `docs/verification/2026-10-02-cave-qualification.md`
- `.superpowers/sdd/2026-09-28-comprehensive-agentdecompile-plan/task-25-report.md`

## Self-review findings and corrections

1. Moved preflight ahead of entity construction and split it into all-build
   native/depth checks followed by canonical snapshots, preserving exact evidence
   prefixes and causes while allowing structured depth errors through unchanged.
2. Added complete-payload depth precheck before verifier invocation so decoder or
   qualification wrappers cannot exceed the pack budget after a callback accepts.
3. Kept noncallable unavailable separate from malformed qualification refusal;
   invalid qualification never reaches independent authority.
4. Added callback availability check for empty receipt/build collections so no
   callback-free required-validation result advertises independent qualification.
5. Added defensive recursion handling for captured v2 type JSON parsing and the
   pretty v2 exporter encoder; v1 output code remains unchanged.
6. Inspected the synthetic SQLite fixture against store/migration/schema source;
   inspected staging/header helper requirements against the existing bundle flow.
   This is source review, not fixture execution or a passing result.

No known source defect remains from this self-review. Execution is unverified.
Fresh independent review belongs to the controller; no reviewer was spawned here.

## Concerns and remaining gates

No suitable real whole-image producer has been established. This slice intentionally
ships a blocked default. Acceptance owners must independently resolve immutable
producer provenance and enforce decoder revision, complete coverage/exclusions,
exact candidate result, policy and current generation at every callback invocation.
The mounted catalog/dashboard/CLI consumer owners still need an actual provider;
old serialized complete receipts are intentionally tightened and cannot qualify
without one. The verification document records this compatibility boundary.

Focused sources require later authorized execution. Serving provenance was supplied
by the controller as separate orientation; this checkout is not activated, and no
unchanged-process hot reload/installed-consumer result is claimed. Runtime allocation,
protection/alignment, lifetime/reclaim, native adapter, installation/call/restoration,
platform and fresh whole-image recovery predicates remain open.

Historical memory was used only for JSON exactness/large-flat and source-versus-live
boundaries, then rechecked against current source. Memory references:
`MEMORY.md:274-277` and
`rollout_summaries/2026-09-28T14-41-47-PiD0-agentdecompile_comprehensive_plan_implementation_review_hand.md:114-130`,
rollout id `01a0e876-fcbe-7041-af54-f4c9fc9eb102`.

## Fix round 1 — Q25-1 snapshot regression coverage

Status: **READY_TO_COMMIT**. Read `task-25-review.md` and its nonblocking Q25-1
finding against reviewed source head `f059c0bb7dc3d7f4412eb8e23764f26d48425dfd`.
The shared checkout had subsequently advanced to
`d966fefcaeef5cc185de4ac6bdaa371a5ab28301`; the two owned paths had no intervening
diff before this correction. Concurrent changes were preserved. The controller
alone owns staging and committing this round; neither action was performed here.

Changed `test_scanner_uses_captured_snapshot` to monkeypatch the scanner module's
`discover_caves` with a wrapper that delegates to the separately retained real
scanner function. The wrapper asserts that its evidence argument, nested decoder
and data-reference list are detached from the original caller object, and that
its input equals the captured synthetic evidence. Immediately before delegation,
it mutates the caller's decoder revision and adds a data reference inside the
candidate region. Consuming that changed caller state would eliminate the cave.

The regression source now asserts the wrapper's captured input hash, visible
caller mutations, complete receipt with the original evidence digest and decoder,
and retained one-candidate count/content digest, offset, capacity and original
bytes. The existing independently held **synthetic** receipt verifier additionally
binds the full captured receipt/result. The fixture remains synthetic acceptance
plumbing and establishes no actual qualified whole-image producer.

Source-only checks performed:

```text
Focused regression AST parse: accepted, no project import/execution
Scanner wrapper final statements:
caller_evidence['decoder']['revision'] = 'later-caller-state'
caller_evidence['data_references'].append(8)
return discover_caves(image, build=build, arch=arch, evidence=scanner_evidence)
git diff --check -- <two owned paths>: exit 0, no output
```

Manually reviewed the focused diff and its scanner-call order. No project imports,
tests, builds, proofs, databases, runtime operations, subagents, production-source
changes, staging or commits were performed. **The regression was not run**; this
correction addresses the source-visible coverage weakness only, and no passing
fixture or successful execution is claimed. Deferred execution and all real
producer/provider, installed-consumer and runtime gates remain unchanged.

Exact paths ready for controller review/staging:

- `tests/test_corpus_cave_qualification.py`
- `.superpowers/sdd/2026-09-28-comprehensive-agentdecompile-plan/task-25-report.md`
