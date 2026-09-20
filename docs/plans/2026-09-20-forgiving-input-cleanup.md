# Simplify AgentDecompile around shared, composable capabilities

## Spec

The latest user correction supersedes both file-count and CLI-only objectives:
there is no required number of files, and spelling aliases are only one example.
Infer the broader intent from current canonical VISION, STRATEGY, AGENTS, design
and brainstorm records, and actual git changes over time. Remove duplicated
hardcoded machinery across capability discovery, workflow policy, ownership,
resume, presentation and inputs where evidence identifies a shared owner.
The whole-source aggregation is
complete and remains useful evidence, not a mandate to merge unrelated modules.
Preserve forgiving inputs,
implicit normal defaults and explicit customization. Do not replace duplication
with permutation frameworks, giant concatenations, exec-based hidden modules or
moving Python outside src to game the count.

Full canonical aggregation: 456 files, 218515 lines, 9262819 bytes; the former
91-file target is withdrawn. The isolated branch contains the full source
snapshot at 64d768c. Canonical dirty and untracked files are included in
the aggregate and must survive future migrations. Current live runtime differs
again (444 files). Source moves require a fresh complete snapshot and import,
entrypoint, process/state and packaging preservation, not blind deployment.

Tasks 1-3 are completed input-path deduplication. Task5 is completed; finish
Task6's accepted-path evidence correction because it removes actual duplication.
Task4 remains a candidate, not the automatic next priority. Complete the parallel
charter/history/documentation/implementation investigation before choosing the
next slice. Choose by duplicated behavior and maintenance burden, never physical
file-count quotas or the easiest isolated spelling cleanup.

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
Collapse redundant normalized-equivalent long option declarations when native
normalization makes them unnecessary; preserve the first public spelling, explicit
destination, every short option and genuinely different semantic alias.
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
and typed lookups. Share registry-owned candidate and spelling lookup machinery;
do not delegate wholesale to parse_arguments because its None, unknown-key and
alias-priority behavior differs. Retain executor-specific coercion, short semantic aliases, defaults and
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

## Task 4: Derive convenience commands and keep backend defaults implicit

User refinement: reduce hardcoded command machinery through dynamic reuse;
normal use should need no flags and custom behavior should be explicit opt-in.
Own cli.py, registry.py's redundant builtin alias registrations only, and the
defaults section of docs/INPUT_NORMALIZATION.md. Read Global
Constraints. Limit this slice to symbols, strings, datatypes and structures.
Replace their four repeated convenience-command factories with one small helper
that derives options from the existing run Command and invokes its callback via
native Click. Preserve command names, exposed option sets, meaningful customization,
selector safety and validation; don't create a metadata framework or depend on a
live backend for CLI help. Copy Option objects if reuse would share mutable state.
Keep semantic choices explicit once in each owning run command's click.Choice;
derive shortcut names from those choices, retaining genuine exclusions only.
Missing run-only inputs must not inject new workflow defaults into shortcuts.
Fix Click destination names that disagree with callback parameter names in these
families as part of sharing the actual callbacks. Preserve public flag spellings.
Make only proven redundant provider-owned defaults implicit (None/absent payload);
retain positive and negative boolean overrides, false, zero and explicit empty
values. Preserve intentional CLI policy defaults and mutation safety flags.
Keep validation: do not replace all typed options with permissive string options.
Do not globally strip defaults in _call or normalize arbitrary nested values.
Read task-4-preflight.md in this plan workspace. It records exact excluded options,
symbols mutation-mode exclusions, destination mismatches and provider-default evidence.
Native ctx.invoke(Command) fills missing values: explicitly suppress omitted
run-only options so shortcuts do not acquire new defaults. Use native Click's
kebab-to-snake destination inference instead of a destination translation table.
Only filterDefaultNames=True and includeReferencingFunctions=False are proven
provider-owned defaults for omission in this slice. Preserve other CLI policies.
Retain explicit negative boolean overrides, tuple and JSON handling. Explicit empty
ordinary string inputs are retained; whitespace-only program selection remains absent.
In registry._add_builtin_param_aliases remove only the nine later normalized-
equivalent registrations: binary_path, shared_mode, ghidra_server_host,
ghidra_server_port, ghidra_server_username, ghidra_server_password,
ghidra_server_repository, server_repository, repository_name. Keep first spellings,
semantic synonyms and all existing normalization/precedence algorithms. Inline
old/new replay must prove the resulting normalized maps identical, including
replace=True behavior; no second normalization algorithm in production.
Characterize native Click parsing and callbacks entirely in memory with _call
replaced by a capture coroutine; never invoke real backend/process/filesystem
callbacks or CliRunner filesystem isolation. Assert public option sets, no-flag
payload omissions, explicit positive/negative overrides, selectors, false/zero,
tuple and JSON transformations, invalid JSON rejection, and no new injection of
run-only options into shortcuts. Compile source in memory. Report any deliberate
behavior changes and exact code reduction. Self-review, commit, independent review.

## Task 5: Consolidate container parsing at its package boundary

Own only src/agentdecompile_recovery/containers/ and the task report. Read Global
Constraints above. BASE is 64d768c. Merge the existing five files into the existing
__init__.py, deleting detect.py, models.py, nds.py and registry.py. Preserve the
seven-name public __all__, function signatures, NDS validation, byte extraction,
metadata and errors. Deduplicate imports and replace internal module dispatch
with direct functions; keep the existing parser registry, not a new framework.
Use dataclasses.replace for the repeated frozen-image copy with extract_path changed,
preserving every other field instead of manually copying the same field list twice.
Inspect all package code and caller imports before editing. No known consumer
uses the removed internal paths; do not add compatibility shims or sys.modules
aliases. Qualified class module identities change; report that limitation.
Do not touch languages: its internal imports need a separate compatibility decision.
Do not run or write filesystem tests, fixtures or temporary input files. Use
python -B inline, memory-only assertions with BytesIO/path stubs where needed;
exercise valid/truncated NDS headers, invalid ranges, detection, registry routing,
metadata and extraction bytes without real writes. Compile changed code in memory,
check deleted-module references statically, and include the runnable inline check
in the report. Record physical file count and LOC before/after; expected net four
fewer source files is an incremental reduction, not the 91-file target achieved.
Use apply_patch, self-review, commit only production changes with hooks disabled,
and report commands/results and limitations. Preserve all unrelated changes.

## Task 6: Share the dependency-closed x86-64 decoder implementation

Own sourcegen.py, source_parity_synthesize.py and new decode_x86.py under
src/agentdecompile_recovery/, plus the task report. Read Global Constraints.
Use the exact 38-function/18-table manifest in this plan workspace's
decoder-preflight.md; read that artifact before editing. Consolidate only those
AST-identical functions and assignments into decode_x86.py with ordinary explicit
imports preserving existing producer-level names. Do not change algorithm bodies,
literal table values, candidate construction, _GEN, compilation, receipts, profile
selection or verified/unverified promotion. Do not merge the differing
X86_64_RETURN_SECOND_ARG_OPS table. No dynamic loaders, exec-based production code,
new dependency, wrappers or generic decoder framework. Preserve existing signatures,
return dictionaries, padding rules and immediate interpretation, even where an
algorithm's pre-existing semantics could be improved independently.
Inspect actual dependency closure and all table mutations/import consumers before
editing. Keep import-time code dependency-light: stdlib typing only if sufficient.
Use AST source extraction in an inline check to load old baseline helpers/tables
into isolated memory namespaces; never execute full producer modules or callbacks.
Compare both old implementations with the new shared implementation using deterministic
opcode-table cases, immediate/displacement variants, malformed/truncated bytes,
padding, and seeded byte inputs. Assert shared function/table AST equality,
complete global dependency closure, and unchanged AST for non-owned definitions.
Compile the three sources in memory with bytecode disabled. No filesystem tests,
fixtures, temporary files, compiler processes or backend imports. Include the full
runnable check and output in the report. Count the added physical module honestly
against deleted duplication; this improves code ownership, not file count by itself.
Self-review and commit only task production files with hooks disabled; independent
spec/quality review follows. No production changes before Task 5 review passes.

## Task 7: One owner for MCP provider enrollment

History fd1d660 establishes derived capability surfaces instead of parallel stale
catalogs; May's analysis-coordinator simplification establishes one behavior owner.
Current provider enrollment repeats class imports/exports and a manager-local class
tuple. Own only src/agentdecompile_cli/mcp_server/providers/__init__.py and
src/agentdecompile_cli/mcp_server/tool_providers.py, plus the task report.
Read Global Constraints. Keep the existing providers package as enrollment owner:
explicit provider imports, one PROVIDER_CLASSES tuple in the exact current manager
registration order, and __all__ derived from that tuple. Preserve the same exported
provider-name set; its introspection order may follow registration order and must
be disclosed. Do not export PROVIDER_CLASSES through wildcard imports. Manager
imports the tuple lazily inside register_all_providers and iterates it; remove
its duplicated class import list and tuple. Preserve constructor arguments,
registration order, tool collision behavior, and per-provider exception/logging
continuation exactly. No filesystem scanning, subclass auto-discovery, plugin
loader, new dependency, or change to import failure boundaries. Update misleading
package docstring about registration ownership. Inspect actual consumers first.
Use pure inline AST extraction with fake provider classes and an import stub;
do not import real providers or start JVM/backend. Assert exact pre/post provider
sequence and public-name set, all names resolve to imported classes, no duplicated
enrollment list in manager, and that inserting one stub provider into the package
tuple automatically reaches manager registration without manager changes. Verify
one constructor failure still permits later providers to register with the same
warning. Compare actual manager registration method's behavior, not a reimplemented
loop. Compile both sources in memory, diff-check, write full runnable check/output,
self-review and commit only owned production changes with hooks disabled. This is
the first capability-ownership slice, not completion of catalog/resource/resume
consolidation or runtime activation.

## Acceptance

Each task receives independent spec/quality review, then the complete branch gets
one broad review. Evidence is inline parser/normalization equivalence, not live
Ghidra behavior. Integration must preserve canonical edits and not restart or
structurally reload the active recovery server. No whole-repository perfection or
live activation claim follows from a clean source diff.
