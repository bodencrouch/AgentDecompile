## Task 29: Explicit MCP program dispatch

- **Requirements:** R23–R30; assigned named obligations and applicable source details are mandatory; cross-cutting clause coverage does not add unrelated prerequisite edges.
- **Dependencies:** U13. These denote consumed predicates, not a requirement to finish every unrelated child of a predecessor.
- **Files and interfaces:** Existing backend/provider, static workbench and Vite modules named below; no duplicate root. Preserve existing public routing and inspect current symbols before changes; paths in archived contracts are version-specific leads.
- **Execution:** reconcile retained implementation and evidence first; implement the missing vertical slice, exercise the named positive and refusal cases, then integrate the real consumer and capture the required proof.

- Preserve September10 five units: manager/base optional keyword-only program_info with omitted sentinel distinct explicitNone; precedence requested programPath→supplied override→session→lifecycle. No dispatch-time singleton writes; direct2argument compatibility only lifecycle fallback. Thread value through prerequisites,conflict replay,auto-match/check-in and helpers/wrappers.
- Migrate all dispatch reachable provider handlers/bookmarks/comments/constants/data/dataflow/types/decompiler/dissect/enums/functions/getfunction/memory/strings/structures/symbols/vtable/xrefs. Key callgraph/decompiler caches to explicit program. Project/import activation explicitly changes handler-local context for subsequent work while lifecycle fan-out remains future-call default.
- No ContextVar/provider/manager lock substitute, no CONTEXT_LOCK changes. Acceptance deterministic A-paused/B-dispatched/A-resumed isolation; reentrant prerequisite/cancellation; lifecycle activation concurrent caller unaffected; full actual response paths not tools/list schema only. Keep source TOCTOU completion distinct from arbitrary Ghidra concurrent-mutation safety.

- **Completion:** close assigned named child obligations and unit-specific predicates against the exact input/version scope; discharge owned source-clause coverage through explicit child evidence or contextual disposition; record changed paths, verification receipts and any remaining blocked predicates in the living plan. Commit only owned, reviewed changes during a separately authorized implementation run.



## Slice29.1: residual dispatch compatibility state

# U29 next dispatch slice: remove residual compatibility writes

Source examined: merged HEAD `b871b8450d4f8ea02da6dbae6fd6a5429fec787c`, 2026-10-02.
This report owns no source changes. It follows `unit-29-requirements.md`,
`named-obligations-U29.md`, repository `AGENTS.md`, package `CLAUDE.md`, and the
documented solution `docs/solutions/mcp-ghidra-integration/program-info-toctou-race.md`.

## Ranked confirmed gaps

1. **Residual dispatch-time lifecycle mutation, not a wholesale missing migration.**
   `src/agentdecompile_cli/mcp_server/tool_providers.py:993-1004` inspects the root
   handler signature. For a handler without `program_info` or `**kwargs`, it calls
   `self.set_program_info(effective_program_info)` before invoking that handler.
   This violates U29's explicit no-dispatch-time-singleton-writes contract and
   changes both `self.program_info` and `self.ghidra_tools` (`:928-931`). It is
   reachable through enrolled pure control providers: `PromptToolProvider`
   (`providers/prompts.py:45`) and `WorkflowToolProvider`
   (`providers/workflow.py:56,60`), among others. Both are in
   `providers/__init__.py:PROVIDER_CLASSES`; manager registration is at
   `tool_providers.py:1997-2007`. Prompt's handler only obtains prompt metadata and
   creates a response; it does not need shared program state. An explicit B call
   changes its future omitted-context fallback from lifecycle A to B; an explicit
   None call clears that fallback and its wrapper. Those effects follow directly
   from source, and were not executed in this audit.
2. **Inherited deterministic acceptance fixture is stale at this HEAD.**
   `tests/test_tool_providers_analysis_gate.py:133` defines
   `gate_wait(_func, _program, info, **_kwargs)`, but current production calls
   `asyncio.to_thread(_run_analysis_gate)` with one positional argument
   (`tool_providers.py:2889-2898`). The patched side effect cannot bind that call.
   The same file's `:289` asserts the callable name is
   `wait_for_program_analysis_ready`, whereas the current callable is the closure
   `_run_analysis_gate`. This is a static contract mismatch, not an executed test
   failure. The historical solution's 254-pass claim cannot qualify this merged
   source. Its linked `.superpowers/sdd/2026-09-10-program-info-call-scoped-refactor/task-5-report.md`
   is absent in this checkout.

## One executable implementation slice

Production ownership: **only** `src/agentdecompile_cli/mcp_server/tool_providers.py`.
Remove the setter from the compatibility branch at `:999-1004`; retain its
two-argument `await handler(norm_args)` dispatch for statically verified pure
control handlers. Keep explicit-keyword dispatch for program-consuming handlers.
No migration of the already explicit program providers or control-handler
signatures is needed for this slice. Do not introduce locks, ContextVars, a
temporary shared override/reset, changes to manager lifecycle fan-out, or changes
to dashboard `CONTEXT_LOCK`.

Acceptance source ownership: `tests/test_tool_providers_analysis_gate.py` and
`tests/test_canonical_tool_parity.py`. Repair the gate fixture for the current
call shape. Prefer pausing a patched `wait_for_program_analysis_ready` with a
bounded thread-event handshake while retaining the real `asyncio.to_thread`
boundary, rather than coupling assertions to the private closure's name or
reading provider singleton state as the request target. Add a real
`PromptToolProvider.call_tool("list-prompts", ...)` regression with a sentinel
lifecycle program/wrapper: explicit B and explicit None must produce actual
responses without calling `set_program_info` or changing those lifecycle
identities; the next omitted call must still use A for context injection. Keep
the prompt payload and normalization behavior unchanged. A no-keyword dummy
handler may cover exception/cancellation branches without introducing workflow
admission or actual recovery work.

Review documentation ownership: only the bounded current-status section in
`docs/solutions/mcp-ghidra-integration/program-info-toctou-race.md`, if needed to
record this residual fix and its separately authorized acceptance. Do not copy
the historical pass count into a fresh receipt.

Required positive and refusal contracts for the implementer:

- Omitted `program_info` uses lifecycle fallback for a direct provider call;
  explicit None remains empty and leaves lifecycle fields untouched.
- Manager precedence remains requested path, explicit override, session active,
  then the existing guarded lifecycle default (`:2752-2798`). A missing requested
  path returns the existing resolution failure (`:2814-2868`) without borrowing
  an active program. Explicit None prevents auto-selection (`:2803-2807`).
- Deterministic A-paused/B-dispatched/A-resumed must exercise tools/call responses,
  not tools/list: A reports A and B reports B. Add lifecycle activation to B while
  A is paused: A remains A, future omitted calls receive the deliberate lifecycle
  default B. Exception/cancellation must leave no request override in shared
  fields. Same-provider prerequisite recursion must complete and retain scope.
- A program-dependent real response (existing function listing, strings wrapper,
  datatype nested dispatch, or comment mutation coverage) must use the passed
  program even when lifecycle state changes. Keep conflict replay, auto-match,
  and auto-checkin forwarding intact.

The current mission forbids filesystem test runs/builds for this documentation
audit. These are implementation acceptance requirements, not permission to run
them now. Before production Python edits, a separately authorized implementer
must corroborate the serving PID/start time, cwd, loaded module path, revision,
and dirty-source ownership as required by `AGENTS.md`. Activate through the
documented in-process reloader and verify the unchanged live consumer identities;
never restart to make this edit effective.

## Current A/B source trace and retained coverage

For `list-functions`, A resolves `effective_program_info=A` at `:2790-2798`,
captures `prog=A.program`, and pauses at `:2898`. B resolves its own B, runs its
gate, and dispatches with `program_info=B` at `:2904`. Base dispatch recognizes
`FunctionToolProvider._handle_list`'s keyword (`providers/functions.py:122`),
passes B at `:998`, and the handler reads B at `functions.py:141,148`. When A
resumes, the same path passes its retained A. Therefore the original wrong-program
interleaving is **not established in the currently migrated function handler**.
The residual setter is reached by the separate pure-control compatibility branch;
removing it closes the explicit lifecycle contract without inventing a broader
program-read defect.

Retained source also explicitly forwards prerequisite context (`tool_providers.py:1174`),
conflict replay (`providers/conflict_resolution.py:100`), auto-match (`:2994`), and
auto-checkin (`:3022-3025`). Nested dispatch threads the explicit value where
accepted (`:1433-1440,1461-1467`). Wrappers are built per supplied program
(`providers/_program_context.py:13-22`); callgraph renderers are per call
(`providers/callgraph.py:45-52`); decompiler leasing receives the supplied program
(`providers/decompiler.py:277-302`). Project activation returns its new context
(`providers/project.py:4150-4170`), and imports retain their newly created context
for subsequent work (`providers/import_export.py:1771-1774`). Script execution
calls `_build_namespace(..., fallback_to_provider=False)` (`providers/script.py:396`),
so its standalone compatibility helper's shared fallback is not the request path.

Static AST inspection found 91 HANDLERS mapping entries in provider modules;
20 entries lack an explicit keyword/kwargs signature, including two aliases of
the suggestion stub. A text search of program-consuming helper calls found no
actual call lacking `program_info=` in those provider modules. This supports a
narrow compatibility-branch slice; it is not a complete dynamic reachability proof.

## Remaining acceptance and frontend child disposition

Existing tests are **inherited source**, including interleaving/explicit None/
prerequisite cases in `test_tool_providers_analysis_gate.py` and real wrapper,
datatype, function-listing, comment mutation, and decompiler cases in
`tests/test_provider_call_scoped_context.py`. None ran in this audit. No live
server, session-capability, cancellation, lifecycle-oracle, or real Ghidra
concurrent-mutation result was established.

The frontend per-call locator child already has a pair-keyed peer pool and peer
transport/lock state (`src/agentdecompile_recovery/corpus/dashboard/mcp_bridge.py:30-45`).
It intentionally retains `CONTEXT_LOCK` and emits explicit queued/serialized,
concurrency-unverified responses (`:53-112`), matching the permitted unsupported
concurrency fallback in the named obligation. Leave it unchanged in this slice.
The required two-project versus direct-single-peer comparison, same-pair
serialization, and never-registered-pair refusal still need authorized live
acceptance. Provider dispatch completion does not establish arbitrary concurrent
Ghidra mutation/disposal safety or authorize lock narrowing.

Verified here: read-only source/link inspections and standard-library AST parsing
without importing repository code. Not performed: source/index changes, test
execution, builds, service probes, recovery jobs, server launches/restarts, or
process management. This report is the only owned written artifact.


## Controller scope and precedence

Implement this exact local source slice. The scout's future activation paragraph is an acceptance requirement, not authorization to modify the serving source. Current serving provenance was corroborated by controller: PID2697197/start1790595674.5226107, cwd /home/brunner56/agentdecompile-nvme, retained catalog module __file__ paths under canonical MyBook checkout HEAD753d7fce; this worktree is separate. Do not activate, sync, reload, restart or touch live state. No tests/builds/proof scripts/project imports/Ghidra/catalog operations/systemctl. Write regression source; only source AST/diff checks now.

Own only production tool_providers.py, the two specified test sources, bounded documented solution current-status section if needed, and task-29-report.md in this directory. You are not alone in this checkout; preserve others, no subagents. Do not edit master/living/todo/progress; controller owns those. Preserve normalization and all other passing-scope source paths. Commit only owned changes locally. Include exact self-review/source verification, unexecuted acceptance and remaining full-U29 predicates in report. Return status, commits, one-line checks and concerns.
