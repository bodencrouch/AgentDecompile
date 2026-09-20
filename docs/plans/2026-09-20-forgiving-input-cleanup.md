# Forgiving input without spelling boilerplate

## Spec

The user's 2026-09-20 request is the binding spec: retain forgiving command and
argument input while making AgentDecompile's implementation readable, modular
and less repetitive. Investigate the full input path; do not replace lists of
spellings with another spelling-permutation framework.

## Global Constraints

- No filesystem tests, test suites, test fixtures, server launches, recovery runs,
  process signals, systemctl, or ports other than the existing 8080 dashboard.
  Pure inline Python checks with bytecode disabled are allowed; report commands
  and outputs. Do not import modules that start a JVM or server.
- Implement only in /home/brunner56/agentdecompile-worktrees/forgiving-inputs-20260920.
  Preserve the canonical dirty checkout and live NVMe runtime. No push or PR.
- Reuse registry.normalize_identifier: lowercase alphabetic core; do not change
  this established contract or normalize arbitrary argument values/nested keys.
- Retain canonical public command names, output/schema names, semantic aliases,
  unknown forwarded arguments, meaningful diagnostics and False/0/empty handling.
- Prefer canonical exact argument names over fallback spellings. Preserve current
  boundary-specific conflict precedence unless an explicit reviewed decision is
  necessary. No global semantic path/file/program alias expansion.
- No subagents from implementers or reviewers. Use apply_patch for source edits.
  Commit only your task changes and write a concise report with check evidence.

## Task 1: Normalize Click tokens at the actual CLI boundary

Own src/agentdecompile_cli/cli.py and one small cli_input.py helper if needed.
Read this plan's Global Constraints as binding. The existing Click group rejects
noncanonical command spellings before registry resolution, and generated flags
only expose snake_case. Reuse Click's native token_normalize_func for long option
names instead of enumerating camel/snake/kebab/Pascal spellings or rewriting argv.
Inspect its installed implementation first. Preserve case-sensitive short options
(-p vs -P etc.) and pass-through commands' opaque tokens; keep help names stable.
Use a small Group resolver: exact registered commands first, normalized registered
command names second, registry semantic aliases only to existing commands last.
Never invoke a backend to resolve a name, and detect ambiguous command matches.
Use registry.normalize_identifier for _is_cli_result_limit_param too.
Inline checks: native Click parsing of representative canonical/camel/Pascal/snake/
kebab/uppercase long flags and command names, unchanged path/JSON values, boolean
flags, exact curated command precedence, semantic aliases, short-option casing,
unknown command failure and opaque passthrough. Exercise pure Click/parser objects
without filesystem runners or starting actual CLI application callbacks.
Remove obsolete comments claiming aliases are individually registered. Self-review
and commit. Report exact changes, commands, outputs, boundaries and concerns.

## Task 2: Consolidate registry and executor argument lookup

Own src/agentdecompile_cli/registry.py and src/agentdecompile_cli/executor.py.
Read this plan's Global Constraints as binding. Registry parsing already handles
canonical keys, normalized names, tool-specific semantic aliases, natural-language
input and forwarded unknown arguments. Executor reimplements variation generation
and typed lookups. Route executor schema argument selection through registry and
retain necessary executor-specific coercion, short semantic aliases, defaults and
unknown-key compatibility. Remove its duplicate spelling generator and repeated
normalization loops. Inspect every caller before changing helper signatures.
Separate semantic alias data from mechanical spelling normalization. Simplify the
registry's extraction/generation implementation without silently dropping existing
short forms or changing documented selection priority. Keep compatibility wrappers
where public imports require them; do not add a new registry framework.
Inline old/new behavior comparison or explicit characterization: all known parameter
spellings; address/program/limit/start/signature semantic forms; None, false, zero,
empty string, nested opaque payloads, unknown forwarded args, explicit-canonical
precedence and conflicting spellings. Check natural-language and tool forwarders
remain wired. Avoid importing executor if it starts JVM machinery: AST extraction
with pure dependencies is permitted, and report that coverage boundary precisely.
Self-review, commit, and report line reduction and any intentionally changed cases.

## Task 3: Remove redundant provider spelling lists and document the boundary

Own src/agentdecompile_cli/mcp_server/providers/*.py, provider-related sections in
src/agentdecompile_cli/mcp_server/tool_providers.py, and docs/INPUT_NORMALIZATION.md.
Read this plan's Global Constraints as binding. All provider _get/_require helpers
already normalize requested names. Across the package, collapse literal names in
one getter call that have identical normalize_identifier results (retain the first
spelling and argument order). Preserve genuinely different semantic aliases and
keyword arguments. Also simplify equivalent repeated direct getter fallbacks only
when the normalized-boundary contract proves equivalence; no blanket truthiness
rewrites. Do not change data-field names in returned JSON or nested user payloads.
Inspect existing shared pagination/address helpers before extracting anything new.
Keep provider last-spelling-wins normalization unchanged; document its distinction
from registry canonical-first precedence instead of broadening scope silently.
Correct misleading recursive-normalization documentation: only top-level keys.
Document the resulting one-normalizer/semantic-alias/input-boundary architecture
and a small runnable inline compatibility check; no new test files.
Inline AST/source checks over all changed provider calls: before/after normalized
lookup sequences and keyword values are equivalent; compile edited files in memory.
Do not import provider modules/JVM. Self-review, commit, report exact file count,
removed redundancy and residual intentional semantic cases.

## Acceptance

Each task receives independent spec/quality review, then the complete branch gets
one broad review. Evidence is inline parser/normalization equivalence, not live
Ghidra behavior. Integration must preserve canonical edits and not restart or
structurally reload the active recovery server. No whole-repository perfection or
live activation claim follows from a clean source diff.
