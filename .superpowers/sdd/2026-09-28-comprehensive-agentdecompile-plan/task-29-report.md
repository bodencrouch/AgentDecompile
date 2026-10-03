# Task 29 implementation report — slice 29.1

Date: 2026-10-02. Status: source implementation complete; behavioral acceptance
unexecuted under the controller's current source-only authorization.

## Scope and provenance

Implemented the exact residual compatibility-dispatch slice from
`task-29-brief.md`, starting from worktree HEAD
`6e4b313d740380ea4d7af7389ce5dc0b5312643a`. Read the SDD
`implementer-prompt.md`; its test-running defaults do not override the brief or
repository mission restrictions. Other workers own cave/export and grid compile
verification. This worker made no changes to their paths or the controller's
master/living/todo/progress documents, and spawned no subagents.

Serving provenance is the controller's previously corroborated evidence, not a
fresh check by this worker: PID2697197/start1790595674.5226107, cwd
`/home/brunner56/agentdecompile-nvme`, retained catalog module `__file__` paths
under the canonical MyBook checkout HEAD753d7fce. This implementation worktree
is separate. No source sync, reloader operation, restart, or live-state change
was attempted.

## Implementation

Removed the compatibility branch's `self.set_program_info(effective_program_info)`
from `ToolProvider.call_tool`. Handlers accepting `program_info` or `**kwargs`
still receive the explicit resolved context. Argument-only pure control handlers
still receive their normalized arguments; their response injection and
prerequisite paths retain the resolved local context. Intentional lifecycle
activation and manager fan-out remain available.

No sentinel, explicit-None, routing/alias/normalization, manager precedence,
analysis-gate, prerequisite, conflict replay, auto-match, auto-checkin, nested
handler, project/import activation, wrapper, or cache implementation changed.
No provider/manager lock, ContextVar, temporary shared override/reset, or
`CONTEXT_LOCK` change was introduced.

Updated regression source:

- The interleaving acceptance retains real `asyncio.to_thread`. A patched synchronous
  `wait_for_program_analysis_ready(program, info, *, program_path)` pauses A using
  a five-second bounded `threading.Event`, with thread-safe notification to the
  event loop and three-second bounds around async waits. Its `finally` block
  releases A before awaiting completion. Four parameter combinations cover probe
  and real `FunctionToolProvider` dispatch, with/without deliberate lifecycle
  activation to B during A's pause. Actual JSON responses must remain A/B;
  future omitted calls must use the resulting intentional lifecycle default.
  The real function provider executes its normal handler/filter/response path;
  only function collection is patched to provide synthetic program-specific rows.
- The gate-invocation acceptance now patches the actual analysis helper, checks
  its program/info/path arguments and verifies execution on a different thread.
  It no longer asserts the private closure's name or mocks its obsolete call shape.
- Same-provider prerequisite acceptance retains the real thread boundary and
  bounds completion, preserving the scoped program in the actual nested response.
- A real `PromptToolProvider.call_tool("list-prompts", ...)` acceptance checks the
  unchanged prompt metadata/argument payload, explicit B response context, explicit
  None absence of borrowed context, and subsequent normalized omitted-context
  dispatch using A. Setter spies and program/wrapper identity assertions surround
  every response.
- An argument-only dummy control handler covers exception and cancellation with
  both B and None overrides, bounded synchronization, cleanup, setter-spy refusal,
  and retained lifecycle identities. It admits no workflow/recovery work.
- The existing direct-provider fallback acceptance now also asserts the lifecycle
  context survives the explicit None call.

The documented solution's bounded Current status section records this residual
fix and the current evidence boundary. The September 10 historical pass count is
preserved as history and explicitly does not qualify this source version; the
historical linked report is absent in this checkout.

## Files changed

- `src/agentdecompile_cli/mcp_server/tool_providers.py`
- `tests/test_tool_providers_analysis_gate.py`
- `tests/test_canonical_tool_parity.py`
- `docs/solutions/mcp-ghidra-integration/program-info-toctou-race.md`
- `.superpowers/sdd/2026-09-28-comprehensive-agentdecompile-plan/task-29-report.md`

## Verification performed

Only source parsing/review and Git diff checks ran. The inline Python check used
standard-library `ast` and `pathlib`; it did not import repository code or execute
any test source.

Exact source-check results:

```text
AST parse OK: src/agentdecompile_cli/mcp_server/tool_providers.py
AST parse OK: tests/test_tool_providers_analysis_gate.py
AST parse OK: tests/test_canonical_tool_parity.py
Source dispatch contract OK: ToolProvider.call_tool; sentinel retained; no lifecycle writes
Source dispatch contract OK: ToolProviderManager.call_tool; sentinel retained; no lifecycle writes
Source compatibility dispatch OK: explicit-keyword and argument-only handler branches retained
Regression source boundary OK: test_call_scoped_program_survives_two_program_interleaving; real to_thread retained
Regression source boundary OK: test_analysis_gate_invoked_for_non_exempt_tool; real to_thread retained
Regression source boundary OK: test_prerequisite_recursion_preserves_call_scoped_program; real to_thread retained
Source handler audit: 20 no-keyword HANDLERS entries; no direct self.program_info/self.ghidra_tools reads
```

The handler audit parsed provider modules' declared `HANDLERS` maps and inspected
matched handler signatures/AST without importing them. The 20 entries include
batch analysis (7), context substrate (2), decomp-match (1), prompts (1), recovery
(3), static analysis (2), suggestion aliases (2), and workflow (2). This is a
static direct-read check, not a complete dynamic reachability proof.

`git diff --check -- src/agentdecompile_cli/mcp_server/tool_providers.py
 tests/test_tool_providers_analysis_gate.py tests/test_canonical_tool_parity.py
 docs/solutions/mcp-ghidra-integration/program-info-toctou-race.md` exited 0
with no output. The final report is also included in the final owned-path diff
check before handoff.

Read-only call-site review confirmed explicit forwarding at base handler dispatch,
response injection, prerequisite build/run, nested mode binding, requested-path
failure prerequisite, manager provider dispatch, conflict replay (`:100`),
auto-match, and auto-checkin. Manager resolution remains requested path → explicit
override → session active → guarded lifecycle default. Explicit None still blocks
auto-selection, and an unresolved requested path still returns the existing
resolution failure without borrowing session active context. Existing source
refusal tests in both owned test modules remain present.

## Verification not performed / TDD evidence

No tests, test collection, suites, builds, proof scripts, project/repository
imports, Ghidra work, runtime/catalog operations, service/process operations,
`systemctl`, live consumer probes, activation, reload, or restart ran. There is
no RED/GREEN execution receipt and no fresh passing-test count. Regression
source is written and statically reviewed; its dynamic acceptance remains open.

## Self-review

Reviewed the owned diff against the brief and package routing rules. The
production edit is limited to removing the setter and replacing its obsolete
migration comment. Argument normalization still runs once at the provider
boundary and retains last-spelling-wins semantics. Direct omitted calls retain
the lifecycle fallback; explicit None remains distinct from the sentinel.
Lifecycle activation is exercised as a deliberate operation in regression source
and not simulated by request dispatch. Thread handshakes are bounded and release
paused work in cleanup; cancellation cleanup cannot leave the dummy call pending.

The real prompt regression would detect the removed branch immediately via
setter-spy and identity assertions. Function interleaving acceptance uses actual
response payloads rather than schema listings or provider singleton state as the
request target. Analysis warning collection is patched only to keep these scope
acceptance fixtures independent of unrelated analysis-failure metadata.

No correctness issue remains known from source review. Tests cannot establish
that conclusion dynamically until their separately authorized execution.

## Remaining full-U29 predicates and concerns

- Execute the updated regression source under separate authorization; no current
  behavioral, cancellation, thread-boundary, or lifecycle-oracle receipt exists.
- Reconcile/activate the source with the serving root via its documented in-process
  reloader only when authorized, then verify the real unchanged consumer process
  and state identities. This local source slice is not installed/live acceptance.
- Full session-capability and actual tools/call response-path acceptance remains
  unqualified beyond the regression source and inherited provider coverage.
- Dashboard two-project versus direct-single-peer comparison, same-pair
  serialization, and never-registered-pair refusal still need authorized live
  acceptance; pair-keyed transport source is retained, `CONTEXT_LOCK` unchanged.
- Provider context isolation does not prove arbitrary concurrent Ghidra mutation,
  disposal, project switching, session inventory safety, or permission to narrow
  dashboard locks.
- The large existing provider module remains unchanged structurally; no unrelated
  refactor was introduced for this narrow repair.

## Commit handoff

Per the controller's revised shared-index protocol, this worker does not stage
or commit. All local Git index/commit operations belong to the controller. The
owned paths above are ready for its review/integration; no external PR or
publication action is requested or performed.
