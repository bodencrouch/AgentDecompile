---
artifact_contract: "ce-unified-plan/v1"
artifact_readiness: "implementation-ready"
execution: "code"
title: "Make MCP provider program context call-scoped"
date: "2026-09-10"
---

# Make MCP provider program context call-scoped

## Goal Capsule

Eliminate the verified same-session TOCTOU in `ToolProviderManager.call_tool` by
threading the resolved `ProgramInfo` explicitly through provider dispatch and
program-dependent helper paths. A concurrent request for program B must not
change a request already in flight for program A.

This is an architectural refactor, not a lock change. The manager-wide
`set_program_info()` fan-out remains lifecycle state for activation/startup;
per-call dispatch must not write it. `CONTEXT_LOCK` in the dashboard remains
unchanged.

## Evidence and boundaries

- The defect and rejected lock design are recorded in
  `docs/solutions/mcp-ghidra-integration/program-info-toctou-race.md`.
- `ToolProviderManager.call_tool()` resolves a correct local
  `effective_program_info`, writes it to a singleton provider, awaits analysis,
  then dispatches. Both `ToolProvider.program_info` and its coupled
  `ghidra_tools` wrapper are currently mutable provider state.
- Do not use a `ContextVar`, a per-provider lock, or a manager-wide lock as a
  substitute. The required design is explicit parameter threading through
  dispatch and handlers, including subhandlers and helpers.
- Do not modify dashboard `CONTEXT_LOCK`, Ghidra locking, resource-provider
  lifecycle fan-out, or source-recovery/exchange code in this change.
- Preserve direct provider construction and two-argument direct
  `provider.call_tool(name, arguments)` compatibility for existing unit tests
  and callers; it may use lifecycle fallback only when no manager-provided
  call-scoped value exists.

## Technical design

Add an optional keyword-only call context to `ToolProvider.call_tool`, such as
`program_info: ProgramInfo | SimpleNamespace | None`. The manager passes the
locally resolved value at the final dispatch boundary. The base dispatcher
passes that value to handlers and its own program-dependent helpers. Every
program-dependent provider handler and subhandler accepts the same keyword-only
value and uses it rather than `self.program_info`; helpers receive it explicitly
when they need a program, decompiler, or `GhidraTools` wrapper.

Create the `GhidraTools` wrapper from the passed `ProgramInfo` at the
call-scoped boundary (or pass it explicitly beside the program information).
No program-dependent handler may obtain a wrapper derived from the mutable
lifecycle field. Keep `set_program_info()` for activation/default lifecycle
state only.

Use an internal sentinel in `ToolProviderManager.call_tool` to distinguish an
omitted override from explicit `None`. Resolution precedence is requested
`programPath`, then supplied call override when present, then session-active
program, then the manager lifecycle default. Recursive calls (prerequisite,
conflict replay, auto-match, and auto-checkin) propagate their parent effective
value.

Project/import lifecycle handlers are the exception to a simple frozen value:
when a handler itself opens, checks out, or activates a program, it must use the
newly created `ProgramInfo` explicitly for work after that transition while the
manager lifecycle update continues to serve future calls. Do not silently read
the shared provider field to achieve this.

## Implementation Units

## Task 1: Establish the explicit dispatch contract (U1)

**Files:** `src/agentdecompile_cli/mcp_server/tool_providers.py`,
`tests/test_tool_providers_analysis_gate.py`,
`tests/test_canonical_tool_parity.py`

**Approach:** Change manager and base-provider dispatch signatures, remove the
two dispatch-time writes to singleton providers, and make base response-context
injection plus prerequisite recursion use the explicit value. Preserve lifecycle
`set_program_info()` fan-out and callbacks. Add the sentinel semantics for an
explicit override and forward the effective value through auto-match and
auto-checkin recursion.

**Test scenarios:**

- Two concurrent calls to the same dummy provider target different programs.
  Pause call A at the existing analysis-gate `asyncio.to_thread` seam, allow B
  to dispatch, then resume A; each response must report its own program.
- A direct two-argument provider call still uses its lifecycle fallback.
- Explicit `None` does not borrow another call's program.
- An exception/cancellation resets no global dispatch state because no global
  dispatch state was written.

## Task 2: Thread program context through shared dispatch helpers (U2)

**Files:** `src/agentdecompile_cli/mcp_server/tool_providers.py` and every
provider using base `_dispatch_handler`, `_require_program`, `_resolve_function`,
`_resolve_address`, `_get_function_manager`, `_get_listing`, `_get_memory`, or
`_get_symbol_table`.

**Approach:** Propagate the explicit keyword through root handlers, nested
mode/action dispatch, and the shared helper layer. Group signature-only
providers separately from program-dependent providers so each migration commit
is reviewable. Do not retain a hidden shared-state fallback in a
program-dependent code path.

**Verification:** static search shows program-dependent dispatch paths receive
the value, and focused provider tests cover the updated handler contracts.

## Task 3: Migrate direct program and wrapper consumers (U3)

**Files:** providers under `src/agentdecompile_cli/mcp_server/providers/`,
particularly `bookmarks.py`, `comments.py`, `constants.py`, `data.py`,
`dataflow.py`, `datatypes.py`, `decompiler.py`, `dissect.py`, `enums.py`,
`functions.py`, `getfunction.py`, `memory.py`, `strings.py`, `structures.py`,
`symbols.py`, `vtable.py`, and `xrefs.py`.

**Approach:** Replace direct `self.program_info` and `self.ghidra_tools` reads
on dispatch-reachable paths with passed context/wrappers. Migrate nested
subhandlers in the same unit as their root handler. Leave pure control-plane
providers on the compatibility signature only when a static audit proves they
do not consume program state.

**Verification:** focused tests for strings, data types, functions, and direct
mutation handlers continue to exercise the real tool-call response path.

## Task 4: Resolve stateful and lifecycle-sensitive providers (U4)

**Files:** `providers/callgraph.py`, `providers/search_everything.py`,
`providers/script.py`, `providers/conflict_resolution.py`,
`providers/import_export.py`, `providers/project.py`, and related tests.

**Approach:** Make cached call-graph/decompiler/wrapper state keyed by passed
program context or construct it per call. Preserve `ScriptToolProvider`'s
existing explicit namespace seam. Pass the effective value during conflict and
prerequisite replay. For project/import operations, name each activation point
and explicitly thread the newly activated value for the remainder of that
operation; retain `set_program_info()` only as future-call lifecycle state.

**Test scenarios:** same-provider prerequisite recursion completes without a
lock; a program activation inside a handler affects that handler deliberately
but does not redirect a concurrent request; manager lifecycle callback/fan-out
remains unchanged after a scoped override.

## Task 5: Verify whole-server parity and document the resolved finding (U5)

**Files:** `tests/test_tool_providers_analysis_gate.py`,
`tests/test_canonical_tool_parity.py`, relevant `tests/test_provider_*.py`,
`docs/solutions/mcp-ghidra-integration/program-info-toctou-race.md`.

**Approach:** Run focused unit tests first, then the package MCP smoke suite.
Update the solution record from “unfixed” only after the deterministic
interleaving regression, prerequisite-reentrancy case, and existing provider
contract tests pass. Keep the claim bounded: this removes provider dispatch
TOCTOU; it does not assert Ghidra itself supports arbitrary concurrent mutation.

## Verification Contract

1. A deterministic two-program interleaving test fails on the old shared-field
   behavior and passes with call-scoped dispatch.
2. A same-provider prerequisite recursion test completes and retains its outer
   program context.
3. Lifecycle activation fan-out and server resource-provider callback behavior
   remain covered without relying on a dispatch-time provider write.
4. Targeted provider tests for each migrated group pass, followed by
   `tests/test_e2e_standalone_proxy_cli.py` and the available exhaustive tool
   contract suite using the project’s normal environment.
5. No change is made to `CONTEXT_LOCK`; the final diff contains no new lock
   intended to serialize provider dispatch.

## Risks and execution notes

- This refactor spans roughly 31 providers and must be executed in small,
  dependency-aware commits. Do not parallel-edit providers that share base
  dispatch signatures in the same shared checkout.
- The source tree has many direct handler tests; update them only where an
  explicit program argument is required, preserving their real tools/call
  coverage over tools/list shape tests.
- `self.program_info` may remain as lifecycle fallback for non-dispatch code,
  but it is prohibited as a dispatch-time source after U2.
