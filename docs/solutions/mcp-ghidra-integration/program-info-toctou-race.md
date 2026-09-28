---
title: ToolProviderManager.program_info is a shared mutable field racing across an await
date: 2026-09-08
category: mcp-ghidra-integration
module: agentdecompile_cli.mcp_server.tool_providers
problem_type: race_condition
component: mcp-server
symptoms:
  - not yet observed in production; found via targeted concurrency investigation
  - would manifest as a tool call silently resolving against the wrong program under concurrent same-session requests
root_cause: shared_mutable_state
resolution_type: code_fix
severity: high
tags:
  - concurrency
  - toctou
  - program-resolution
  - donated-compute
---

# ToolProviderManager.program_info is a shared mutable field racing across an await

## Problem

Before the 2026-09-10 refactor, `ToolProviderManager.call_tool` resolved `effective_program_info`
correctly as a **local variable** per call, but then mutated a **shared field on a
long-lived provider singleton** (`provider.set_program_info(effective_program_info)`,
`tool_providers.py:2748`), awaits `wait_for_program_analysis_ready`
(`tool_providers.py:2762-2768`), and only then dispatches
(`provider.call_tool(...)`, `tool_providers.py:2780`) — whose internal handlers read
`self.program_info.program`, the shared field, not the local variable.

The line references in this diagnosis describe the original 2026-09-08 tree.
If a second request targeting a **different program** on the **same provider**
interleaves during that `await`, it silently redirects the first request's
dispatch to the wrong program. No exception, no log line — the tool call just
resolves against the wrong `Program` object.

This was found while investigating whether `mcp_bridge.CONTEXT_LOCK` (a single
global lock serializing every dashboard-originated MCP call) is safe to narrow
for concurrent multi-program work
([`docs/plans/2026-09-08-donated-compute-work-exchange.md`](../../plans/2026-09-08-donated-compute-work-exchange.md)).
Before the fix, `CONTEXT_LOCK` prevented this race from being triggered by
dashboard-originated traffic, as a side effect of never letting the dashboard
have two calls in flight at once. It remains load-bearing for other lifecycle
and mutation concerns; the provider-context fix alone does not justify narrowing it.

## Why the obvious fix (a per-provider lock) does not work

A per-provider `asyncio.Lock` around the resolve→set→await→dispatch sequence
was scoped and then ruled out by two independent, verified findings:

1. **The mutation has a second entry point that bypasses the locked region
   entirely.** `ToolProviderManager.set_program_info` (`tool_providers.py:1909-1924`)
   fans out to **all 31 registered providers** in one synchronous pass. It is
   also called directly from `_set_active_program_info`
   (`providers/project.py:3745`), a plain sync function run via
   `asyncio.to_thread` (`mcp_utils/async_native.py:8`) — reachable without ever
   going through `ToolProviderManager.call_tool`. A lock scoped inside
   `call_tool`'s dispatch has zero visibility into this path: it can land on a
   *different* provider that is mid-flight inside its own separate lock, and
   two distinct per-provider locks provide no mutual exclusion against each
   other.

2. **A real, concrete self-deadlock.** `ToolProvider._run_prerequisite_call`
   (`tool_providers.py:1071`, shared base class, every provider) calls back into
   `self._manager.call_tool(...)` from *inside* a handler's exception path —
   while the outer `await provider.call_tool(...)` (the exact region a lock
   would hold, `tool_providers.py:2746-2780`) has not returned. Concretely:
   `ProjectToolProvider` owns both `manage-files` (`providers/project.py:326`)
   and `list-project-files` (`providers/project.py:278`); a `manage-files`
   failure's prerequisite-retry recurses into `list-project-files` on the
   **same provider instance**, mid-flight. A non-reentrant lock there would try
   to reacquire itself and hang the request — turning a currently-working
   error-recovery path into a permanent freeze.

Both are structural (base-class and manager-wide), not confined to one
provider that could be carved out of the fix.

## Fix alternatives considered

Threading `program_info` as an explicit call-scoped parameter through provider
dispatch, so handlers read a passed-in value instead of shared mutable state —
eliminating the TOCTOU at its root. This touches every one of the ~31 provider
classes and their handler methods (the pattern at
`tool_providers.py:1355,1408,1491,1510,1524,1538,1552` and equivalents across
every `providers/*.py` file). It was a real architectural refactor, not a
contained patch; the implementation is described below.

A narrower alternative exists but does not solve the problem that motivated
this investigation: a manager-wide, reentrancy-safe lock (tracking the owning
asyncio task to permit the same task to re-enter, since `asyncio` has no
built-in `RLock`) covering both the fan-out write and the dispatch sequence
would close the race, but it reintroduces full serialization at the server
layer — the same shape as today's `CONTEXT_LOCK`, just relocated. It would be
a genuine correctness improvement in its own right (the race is real today
even without any donated-compute work, exploitable by ordinary concurrent
dashboard usage), but it delivers no concurrency gain, so it does not unlock
anything `CONTEXT_LOCK` doesn't already prevent.

## Implemented fix (2026-09-10)

The manager passes its resolved `effective_program_info` explicitly to provider
dispatch after the analysis wait. Per-call dispatch no longer calls
`provider.set_program_info`. Handlers, nested modes, native callbacks,
prerequisite retries, conflict replay, persistence, and cleanup carry the same
context through explicit arguments. Wrappers and graph renderers are built for
the supplied context. Activation and shared checkout return their newly opened
context so callers can retain it across lifecycle changes.

Manager-wide `set_program_info` fan-out remains for activation/startup, including
the resource callback. Direct two-argument `provider.call_tool(name, args)` keeps
its lifecycle fallback. An explicit `program_info=None` stays empty. No dispatch
lock or `ContextVar` was added, and `CONTEXT_LOCK` is unchanged.

Static review covered the base/manager module and all 35 provider-directory
modules. No provider handler reads `self.program_info` or `self.ghidra_tools`.
Remaining base reads belong to lifecycle initialization, guarded omitted-context
compatibility, and the unused `_require_ghidra` helper. The unused
`_handle_paginated_search` also retains its legacy guard; neither helper has a
caller in the current source tree. The manager's default context read remains
at initial resolution, before dispatch; it is not reread after the analysis wait.

Focused verification: **254 passed, 2 integration cases deselected**, across 23
test files with `-m 'not integration and not e2e and not slow'`. This includes
deterministic two-program interleaving, lifecycle fan-out during a paused call,
same-provider prerequisite recursion, explicit None, real provider payloads,
shared-checkout return propagation, and persistence argument coverage.
The execution report records the exact command and audit findings at
`.superpowers/sdd/2026-09-10-program-info-call-scoped-refactor/task-5-report.md`.

## Current status

**Fixed in the source tree, with focused non-server verification.
`CONTEXT_LOCK` stays as-is.** No live server, e2e, integration, or slow tests were
run for this verification. This resolves the identified provider-context TOCTOU;
it does not establish concurrent safety for Ghidra mutation, program disposal,
project switching, session inventory changes, or dashboard lock narrowing.
Those require their own lifecycle review and live validation.

## Related

- [`docs/plans/2026-09-08-donated-compute-work-exchange.md`](../../plans/2026-09-08-donated-compute-work-exchange.md) — R6 records `CONTEXT_LOCK` as the reason stages 2,3,4,5,7,9 cannot fan out; this finding is why that constraint should not be relaxed on the dashboard side without the server-side fix above.
