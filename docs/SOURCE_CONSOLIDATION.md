# AgentDecompile source consolidation

Status: whole-source inventory and conditional target architecture reviewed; implementation in progress. This is not a claim that 91 files have been achieved.

The 2026-09-20 canonical snapshot contains **456 Python files, 218,515 lines and 9,262,819 bytes** recursively under src, including dirty and untracked source. The full source aggregate and per-file SHA/import/definition inventory are preserved in the isolated worktree at `.superpowers/sdd/2026-09-20-forgiving-input-cleanup/source-aggregate/`.

| Area | Current files | Proposed physical files |
|---|---:|---:|
| CLI / MCP | 103 | 20 |
| Recovery core | 141 | 31 |
| Corpus | 160 | 24 |
| Dashboard | 52 | 16 |
| Total | 456 | 91 |

Independent static review accounted for every original module exactly once. These are physical-file budgets, not directories or hidden generated modules. File deletion and actual code deletion are separate measurements. The architecture removes repeated execution, metadata, schema, rendering and receipt mechanics; it does not move Python into data files or combine whole files merely to satisfy a count.

Defaults belong to the owning operation and apply implicitly. Frontends pass explicit customizations, preserving false, zero and empty values. Existing ActionSpec/FieldSpec/Section and native Click machinery are reused. Stale or ambiguous target/database state must be validated, never guessed.

All implementation remains in the isolated worktree. Canonical user edits, live 8080 jobs and runtime ownership remain untouched. No filesystem tests/suites/fixtures, systemctl, new servers or recovery runs are permitted. Inline static/pure checks are not live backend, resume or byte-parity proof.

The detailed source accounting and design prerequisites follow. The core's second-pass 31-file target supersedes its intermediate 42-file map; the intermediate map remains as traceable source accounting.

## Implemented increments

- `25a9c6b`: container parsing uses one package implementation instead of five
  modules; repeated frozen-dataclass copying uses `dataclasses.replace`. Four
  files and 54 lines removed. Current source count: **452**, pending the next slice.
  Memory-only behavior checks passed; independent task review is pending.
- Language consolidation is deferred: existing callers import internal modules,
  and whole-module aliases would change introspection and patching semantics.
  Container class qualified module names changed; no repository pickle contract
  was found, but external old pickles are not supported by this change.

These source changes have not been applied to the live recovery runtime.

## CLI/MCP whole-package consolidation design

Canonical snapshot: 103 Python files, 66239 lines. All module responsibilities,
definitions and imports were inventoried; focused body reads traced registration,
schema/default duplication, clients/server entrypoints, native-runtime ownership,
resource dispatch, utilities and batch wrappers. This is not a claim to have
semantically audited every line. The target below is 20 physical Python files,
not 20 directories containing the original files. Nothing has been moved yet.

## Complete ownership map

Source names are relative to src/agentdecompile_cli, without .py. These are
primary owners: mixed existing modules need function-level extraction, not blind
concatenation. Provider schema literals move into the dependency-light catalog;
their actual handlers move to the domain below. Compatibility files count until
deleted and their callers migrated.

| Destination | Existing modules |
|---|---|
| `__init__.py` | `__init__`, `_version`, `mcp_server/providers/__init__`, `mcp_utils/__init__` |
| `__main__.py` | `__main__` |
| `cli.py` | `cli`, `cli_agent_help` |
| `catalog.py` | `registry`, `tool_registry`, `tools_schema`, `models`, `mcp_utils/schema_util`, `mcp_utils/tool_reference` |
| `settings.py` | `app_logger`, `env_compat`, `config/__init__`, `config/config_manager`, `mcp_utils/debug_logger`, `mcp_server/constants`, `mcp_server/profiling` |
| `client.py` | `bridge`, `executor`, `utils` |
| `server.py` | `server`, `mcp_server/__init__`, `mcp_server/server`, `mcp_server/proxy_server`, `mcp_server/auth` |
| `runtime.py` | `launcher`, `context`, `local_backend`, `project_manager`, `mcp_utils/program_analysis`, `mcp_utils/program_lookup_util`, `mcp_utils/service_registry` |
| `session.py` | `mcp_server/session_context`, `mcp_server/conflict_store`, `mcp_utils/async_native` |
| `workers.py` | `mcp_server/auto_match_worker` |
| `functions.py` | `mcp_server/providers/decompiler`, `mcp_server/providers/dissect`, `mcp_server/providers/functions`, `mcp_server/providers/getfunction`, `mcp_server/providers/guide_function`, `mcp_utils/decompiler_util`, `tools/decompile_tool` |
| `graphs.py` | `mcp_server/providers/callgraph`, `mcp_server/providers/dataflow`, `mcp_server/providers/vtable`, `mcp_server/providers/xrefs`, `tools/callgraph_tool` |
| `metadata.py` | `mcp_server/providers/symbols`, `mcp_server/providers/comments`, `mcp_server/providers/bookmarks`, `mcp_server/providers/strings` |
| `types.py` | `mcp_server/providers/data`, `mcp_server/providers/datatypes`, `mcp_server/providers/enums`, `mcp_server/providers/structures` |
| `memory.py` | `mcp_server/providers/memory`, `mcp_server/providers/constants`, `mcp_server/providers/_collectors`, `mcp_utils/address_util`, `mcp_utils/memory_util`, `mcp_utils/symbol_util`, `tools/wrappers` |
| `project.py` | `mcp_server/providers/project`, `mcp_server/program_metadata`, `mcp_server/domain_folder_listing`, `mcp_server/repository_adapter_listing` |
| `files.py` | `mcp_server/providers/import_export`, `mcp_utils/container_import` |
| `operations.py` | `mcp_server/tool_providers`, `mcp_server/providers/batch_analysis`, `mcp_server/providers/context_substrate`, `mcp_server/providers/decomp_match`, `mcp_server/providers/recovery`, `mcp_server/providers/script`, `mcp_server/providers/static_analysis`, `mcp_server/providers/workflow`, `mcp_server/providers/conflict_resolution`, `mcp_utils/batch_bsim`, `mcp_utils/batch_decompile`, `mcp_utils/batch_gzf`, `mcp_utils/batch_sast`, `mcp_utils/decomp_match`, `mcp_utils/external_re_scan`, `mcp_utils/static_triage` |
| `resources.py` | `mcp_server/resource_providers`, `mcp_server/resources/__init__`, `mcp_server/resources/analysis_dump`, `mcp_server/resources/capabilities`, `mcp_server/resources/debug_info`, `mcp_server/resources/mermaid_flowchart`, `mcp_server/resources/programs`, `mcp_server/resources/static_analysis`, `mcp_server/resources/tool_resources`, `mcp_server/prompt_providers`, `mcp_server/providers/prompts`, `mcp_server/providers/suggestions` |
| `presentation.py` | `mcp_server/response_formatter`, `mcp_server/providers/search_everything`, `webui` |

## Why 103 files accumulated

- One provider class/file per tool family, separate provider export lists and
  manager registration, followed by schemas, name-only TOOL_PARAMS, CLI wrapper
  options and response rendering that repeat facts about the same operation.
- Compatibility mergers happened without retiring their wrappers: tool_registry,
  tools_schema and utils explicitly say they re-export implementations now owned
  by registry/executor. Deleting those files requires updating public consumers,
  not manufacturing an invisible sys.modules compatibility layer.
- Java-style utility and service classes retain layers of one-purpose methods.
  For example SchemaUtil has optional/string/with-default wrappers over one
  property builder, plus a separate fluent SchemaBuilder. Keep useful validation
  and schema data; use direct schema records instead of wrapping a dictionary
  repeatedly (mcp_utils/schema_util.py:18-216).
- Batch BSim/GZF/decompile/SAST wrappers repeat dependency checks, namespace
  construction, path/default handling, external execution, artifact discovery,
  count envelopes and next-step responses. Their capability and artifact types
  differ; one execution adapter with explicit per-operation metadata can own the
  common work without pretending BSim availability and GZF output are identical.
- Sourcegen/decoder-style pure algorithms are not the CLI's largest issue; the
  problem here is repeated transport and operation metadata plus adapters.

## What dynamic means here

1. Enrich the existing registry's operation metadata with its actual provider
   schema and ordinary defaults. Keep it importable without Java, server startup
   or filesystem discovery. Move existing schema literals; do not infer types,
   requiredness or defaults from parameter substrings. Runtime handler bindings
   remain explicit ordinary functions resolved lazily by stable operation ID.
2. Derive Click options, MCP tool advertisements and dashboard ActionSpec fields
   from those facts. Reuse the dashboard's existing ActionSpec/FieldSpec rather
   than add a parallel operation framework. A protocol adapter remains where
   argparse, Click and MCP genuinely differ; a new operation should not require
   editing all three independent schemas and a fourth enum switch.
3. Convenience commands derive from the base Click command with a fixed semantic
   selector and the existing public option surface. Native Click invocation
   fills callback inputs. No hand-copied callback or option decorator forest.
4. Provider domains retain explicit domain functions. Shared dispatch owns target
   resolution, contextual aliases, validation, transactions/conflict gates and
   response envelopes. Do not implement name-based reflection over arbitrary
   method names or turn every call into a configurable mini-language.
5. Resources backed by tools already use ToolOutputResource: reuse it where
   appropriate rather than add one resource/provider class per read projection.
   Debug/session and other specialized resources stay explicit functions.
6. Ordinary defaults apply automatically in the owning operation. CLI/UI omit
   redundant echoes; explicit overrides use presence, not truthiness, so false,
   zero and empty values survive. No useDefaults switch. Required destructive
   selectors, target identity, opt-in side effects and validation stay explicit.

## Genuine boundaries and large-module caveats

- `server.py` must retain local server versus proxy entrypoints. Proxy/offline
  catalog import must never start or eagerly require the JVM. FastAPI route
  mounting may share protocol glue; runtime initialization remains separate.
- `runtime.py` is the sole native context/project owner; session locks and
  cancellation-safe native awaits remain in session.py, and auto-match child
  process entry functions remain top-level in workers.py. Fewer files does not
  mean shared mutable worker state or removing subprocess isolation.
- Metadata mutations keep their two-phase conflict contract; response envelopes
  and transaction rollback are not expendable boilerplate.
- The file maps for project, functions, operations and presentation are ONLY
  credible after common metadata/adapter code is removed. Concatenating their
  current contents would create several 6k-9k-line modules and is not this plan.
  Mixed existing managers move domain helpers to their actual owners: e.g.
  tool_providers native function/memory helpers move to functions/memory, while
  operations retains dispatch. Search query execution uses domain handlers;
  presentation retains only query/result composition and formatting.
- Installed commands in pyproject.toml:72-87 and python -m package execution must
  continue to resolve. Old internal dotted imports, script/module argv strings,
  provider monkeypatch consumers and any documented external imports must be
  inventoried before deletions. Versioned compatibility policy is necessary if
  external module imports cannot be preserved without keeping shim files.

## Honest measurements and first slice

103 -> 20 is a design target (80.6% fewer physical files), not an achieved count.
No credible full-package LOC reduction is measured yet. Current narrow cleanup
removed 107 repeated provider argument literals and 46 registry/executor lines,
but that cannot justify this architecture-wide target. Count code deletion
separately from moves, and count every compatibility or new helper file.

First substantive slice: consolidate batch adapter mechanics and canonical
operation metadata for the four existing batch operations, preserving capability
checks and result envelopes. Derive their CLI/MCP/dashboard fields from existing
schemas; then remove obsolete wrappers after internal consumers migrate. This
proves the dynamic design without editing native project ownership. In parallel
read-only review, map the public entrypoints/imports for later moves.

Allowed validation: parse/compile changed source in memory; compare before/after
schemas, parser metadata, command names and pure command/result builders using
inline inputs. No filesystem tests, fixtures, actual subprocesses, Java import,
server starts, recovery jobs or deployment. Such checks do not establish live
Ghidra/backend or recovery equivalence.


---

## Recovery core: consolidation investigation

Read-only source investigation, 2026-09-20. Scope: all 141 Python files directly in `agentdecompile_recovery`, `containers`, `ghidra_db`, and `languages`; no `corpus/` implementation review. Canonical source: `/run/media/brunner56/MyBook/Workspaces/ai-projects/AgentDecompile`. Inventory snapshot: 91,226 lines. All assigned modules were inventoried by module docstring, definitions/import manifest and responsibility; deeper body inspection was focused on duplicated generators, orchestration, compiler ownership, database isolation and entrypoints. This is not an exhaustive semantic audit of 91k lines.

## Why so many files?

1. Several independently useful products accumulated under one package: generic reconstruction, profile-driven one-shot parity, prompt/plugin matching, acquisition, pure Ghidra database reading, Unity reconstruction and browser authoring. File count is not evidence that these are interchangeable.
2. Upstream TypeScript module boundaries were ported individually: assembly/indexer, prompt builder, background scheduler, plugin pipeline, integrator and HTML report. Their module docstrings explicitly record this provenance. Some small wrappers can be folded into their owning domain.
3. Feature-by-feature stages became files: policy, budget, checkpoint, proof tier, claim/status, vacuum, readability, context proposal/application. These share receipt and queue concepts but not identical success semantics.
4. The largest duplication is inside two already enormous modules, not in tiny files. `sourcegen.py` has 17,876 lines; `source_parity_synthesize.py` has 23,317. Together 41,193 lines (45.2% of this core). Only 11 of 141 files are below 60 lines. Combining arbitrary files misses the dominant cost.
5. Compatibility wrappers and entrypoints preserve old module/CLI contracts. They can eventually disappear only after caller migration, not through hidden import rewriting.

## Complete old-file to domain map

Paths below are relative to `src/agentdecompile_recovery`; `.py` is omitted. Every one of the 141 current files appears exactly once. Names in the source column retain the more granular module responsibility; the manifest supplies each original docstring and definition list. The destination column is a proposed ownership/file grouping, not permission to concatenate bodies. Consolidation requires one public domain API, shared models/helpers, and caller migration.

| Domain / responsibility | Proposed destination files | Every current source module |
|---|---|---|
| Package identity | `__init__.py` | `__init__` |
| User entrypoints and dispatch; retain distinct parsers/protocol handlers | `cli.py` | `cli`, `frontdoor`, `acquisition_mcp`, `vacuum_runner` |
| Target-bound acquisition, discovery, bundle registry | `acquisition.py` | `acquire`, `acquisition_bundle`, `acquisition_registry`, `discovery` |
| Context extraction, batch export, ingest | `context_io.py` | `context_export`, `context_batch`, `context_pack` |
| Context evidence application and MCP/Ghidra export adapters | `context_actions.py` | `context_apply`, `context_propose`, `agent_closure`, `ghidra_context`, `mcp_tool_seq` |
| Binary identity, format inventory, function bounds and target slices | `binary.py` | `targets`, `inventory`, `functions`, `elf_target`, `eh_frame_inventory`, `inventory_slice` |
| ROM envelopes, NDS extraction and typed image resolution | `containers.py` | `containers/__init__`, `containers/detect`, `containers/models`, `containers/nds`, `containers/registry` |
| Recovery language/profile/defaults/validation | `languages.py` | `languages/__init__`, `languages/profile`, `languages/registry`, `languages/sourcegen_defaults`, `languages/validators` |
| Pure database public API; preserve no-JVM import boundary | `ghidra_db/__init__.py` | `ghidra_db/__init__` |
| Binary database codecs, buffers, packed representation | `ghidra_db/codec.py` | `ghidra_db/address_map`, `ghidra_db/buffer_file`, `ghidra_db/chained_buffer`, `ghidra_db/fields`, `ghidra_db/packed` |
| Database table traversal and catalogue | `ghidra_db/tables.py` | `ghidra_db/btree`, `ghidra_db/master_table` |
| Program access and project resolution | `ghidra_db/program.py` | `ghidra_db/program`, `ghidra_db/project` |
| Locked item-filesystem mutations | `ghidra_db/store.py` | `ghidra_db/store` |
| Deliberately separate JVM process entrypoint | `ghidra_db/isolated_annotation_dump.py` | `ghidra_db/isolated_annotation_dump` |
| Curated/live enrichment and durable analysis session | `enrichment.py` | `curated_enrichment`, `curated_project`, `pyghidra_enrich`, `reconstruct_enrich`, `ghidra_analysis` |
| Symbol/reference identity and module attribution | `symbols.py` | `symbol_map`, `symbol_provenance`, `rtti_recover`, `reference_corpus`, `module_resolver` |
| Assembly parsing/features and difficulty | `assembly.py` | `asm_utils`, `asm_metrics`, `asm_embedding`, `logistic_regression`, `map_file` |
| Retrieval, function corpus/index and optional embedding | `retrieval.py` | `decomp_atlas`, `decomp_function_corpus`, `decomp_indexer`, `semantic_embedder` |
| Prompt/context construction and AST tool adapter | `prompts.py` | `ast_grep_cli`, `ast_grep_context`, `c_function_scan`, `codebase_context`, `craft_prompt`, `prompt_builder`, `prompt_loader`, `prompt_design`, `c_rendering` |
| Run plans: generic stages, profile stages and window scheduler | `pipeline.py`, `source_parity_one_shot.py`, `windows.py` | `pipeline`, `source_parity_one_shot`, `windows`, `strategy` |
| Attempt/plugin orchestration and concurrent background work | `plugin_pipeline.py`, `plugin_workers.py` | `plugin_pipeline`, `source_plugin_runner`, `source_plugins`, `get_context_plugin`, `run_pipeline_command`, `background_task_coordinator`, `permuter_background` |
| Verified integration, external plugin seam and git handoff | `integration.py` | `integrator_plugin`, `integrator_helpers`, `integrator_build_fix`, `integrator_worktree` |
| Candidate generation versus synthesis/promotion, shared pure decoders | `sourcegen.py`, `source_parity_synthesize.py`, `decode_x86.py`, `decode_forwarders.py` | `sourcegen`, `source_parity_synthesize` |
| Tool capability/execution and compile/diff/cache contracts versus search versus workers | `verification.py`, `compiler_search.py`, `verify_pool.py` | `tools`, `gnu_c_compiler`, `compile_cache`, `match_cache`, `objdiff_verification`, `package_verify`, `package_sweep`, `source_parity_profile_corpus`, `slice_verify`, `verify_pool` |
| Proof selection/budgets/checkpoints versus reported claims | `proof.py`, `claims.py` | `proof_campaign`, `proof_ladder`, `proof_target`, `proof_tier_router`, `autonomous_policy`, `autonomy_budget`, `campaign_checkpoint`, `critical_path`, `claim_report`, `recovery_status`, `vacuum_queue` |
| Repair classification/policy versus locked rewrite fulfillment | `repair.py`, `rewrite.py` | `mismatch_classify`, `near_miss_repair`, `pattern_memory`, `playbook_config`, `readability_repair`, `readability_rewrite`, `rewrite_queue`, `rewrite_context`, `rewrite_provider`, `dual_agent_advisory` |
| Source cleanup, layered dump/export and packages | `source_export.py` | `source_cleanup`, `source_dump`, `source_export`, `export_package`, `batch_decompile_facts` |
| Durable receipts, artifacts, snapshots and reports | `receipts.py` | `state`, `stage_timings`, `artifact_layout`, `snapshot`, `work_dir_diagnostics`, `run_report` |
| Unity facts/composition, exporter ownership, Editor validation | `unity_project.py`, `unity_export.py`, `unity_editor.py` | `unity_probe`, `unity_assets`, `unity_compose`, `unity_export`, `unity_managed`, `unity_editor` |
| Browser authoring and mount adapters | `views.py` | `atlas_server`, `unified_pages` |
| Retired compatibility-only module; migrate consumers to corpus owner | No new file | `corpus_archive` |

This is 31 ownership rows, with 42 proposed physical files including initializers and the isolated JVM entrypoint: 141 → 42, a 70.2% file-count reduction. A literal one-fifth target is 28–29 files. I do not recommend claiming that target for this core: it would require merging several already multi-thousand-line, semantically different engines, or counting hidden/generated modules as gone. Even this aggressive 42-file map needs size review after shared-code deletion; it is a design direction, not an implementation estimate or proof that all those merges are valuable.

## Concrete duplication and global hazards

AST-only analysis of top-level functions in the current canonical files found **102 same-name AST-identical pairs**, totaling **2,709 lines** in one copy (sum of definition line spans, including comments within spans). This includes small functions below the aggregate duplicate report's size threshold. It ignores formatting differences; it does not prove global dependencies equivalent. Independently, 94 same-name top-level assignments occur in both files: 93 have identical AST values; `X86_64_RETURN_SECOND_ARG_OPS` differs. Its sourcegen values are four-tuples, while synthesis adds a register-list fifth item. Do not unify that table by name.

Examples: `sourcegen.py:4977` / `source_parity_synthesize.py:1566` (`decode_x86_64_three_args_bitwise`); `sourcegen.py:1156` / synthesis `:22218` (`probable_context_dependent_fragment`); `sourcegen.py:4074` / synthesis `:557` (`strip_alignment_padding`). Many exact decoder bodies load opcode tables, shared formatters and padding helpers by global name. Extract the full validated dependency closure. Neither a blanket AST mover nor aliasing one giant module to the other is safe.

The producers are intentionally different: sourcegen builds task dictionaries, writes unverified candidates and target slices; synthesis uses `GeneratedCandidate` (`:36`), compiler profiles and objdiff-gated promotion. Share decoding facts, not their acceptance boundary. `sourcegen.py:21,82` keeps per-run `_GEN` global language state; merging it into shared decoders would spread a cross-run concurrency hazard. Pass generation settings explicitly as a later change. Synthesis `ROOT = Path.cwd()` differs from pipeline/one-shot `Path(__file__).resolve().parents[2]`; moving files/package depth can change executable/script discovery even with unchanged function bodies.

## Boundaries that must survive fewer files

- Generic `RecoveryRunner._build_stages` (`pipeline.py:142`) owns durable receipt outputs and configuration fingerprints; profile `STAGES` (`source_parity_one_shot.py:39`) has different stage names, legacy aliases, matching and coverage stages. PluginPipeline (`plugin_pipeline.py:140`) is a setup/programmatic/retry/post-match engine. Share services and receipt primitives before considering one runner. Do not erase stage names or reinterpret old resume receipts.
- `verify_pool.py:43` is a **thread** pool, not a process/pickle pool. It preserves input result order and waits for siblings before surfacing an error. `_call_with_worker_env` (`:103`) mutates process-wide `os.environ`, despite worker-local indices; consolidation must not introduce overlapping env ownership. `source_parity_synthesize.py:243` owns compiler subprocess session/timeout cleanup. `package_verify.py` duplicates tree-signaling helpers; consolidate later only with matching launch/cancellation contracts.
- `ghidra_db/isolated_annotation_dump.py:1` explicitly exists because an embedded MCP JVM cannot safely open both old and replacement projects. Keep the separate process entrypoint. Pure database import must remain usable without PyGhidra/JVM; database store mutation/locking is not a parsing helper.
- The registry/language/container merges require static import rewrites across CLI, corpus and scripts. `pyproject.toml:75–78` fixes recover/reconstruct/acquisition-query module paths. `scripts/source-parity-synthesize.py:12` and recompile/matcher scripts import synthesis directly. Temporary thin compatibility wrappers count as files until removed; no `sys.modules` trick or dynamic `exec` to hide them.
- The inspected core has an intentional external Python-file plugin seam, `integrator_plugin.py:98` (`spec_from_file_location` / `exec_module`). Preserve its interface; do not use it as a module-consolidation mechanism. No direct core pickle/ProcessPool use was found by the scoped textual/static inventory. That is not proof that third-party users do not pickle public dataclasses/enums: moving their defining modules changes `__module__` and potential serialized import identity.
- Optional dependencies remain lazy (embedding/Unity/Java imports). `rewrite_queue` exclusive lock and state transitions, verified/advisory artifact segregation, semantic/byte-exact claim gates, and Unity export-versus-Editor proof are genuine boundaries, not boilerplate to flatten.

## Smallest valuable first slice

Extract only the pure padding/frame/fragment helpers and a bounded family of exact arithmetic decoders into the shared decoder owner; retain ordinary explicit imports under existing public names in both producers. Begin with `strip_alignment_padding`, `has_standard_frame_prologue`, `has_ebp_relative_access`, `probable_context_dependent_fragment`, plus pure affine formatters. Their dependencies are tiny and inspectable; no compiler, task writer, mutable `_GEN`, JVM, or promotion code needs to move. Expand family by family after global-table equality and caller contracts are established. This initially **adds one file** while deleting duplicate implementations: that is meaningful consolidation despite a worse first-step file count.

Validation permitted without filesystem tests: AST parse/compile source in memory; confirm extracted global-name closure; compare old/new pure functions in isolated in-memory namespaces using inline byte strings and opaque metadata; enumerate static imports/entrypoint targets; assert old/new returned facts and candidate source strings are identical. No source module import with side effects, tmp fixtures, compiler invocation, JVM, recovery job or service action. Inline validation is evidence for pure-function equivalence only—not compiler parity, resume correctness or a deployed recovery outcome.

Measured LOC opportunity is 2,709 duplicate function-body lines before imports/shared glue (~3.0% of core). Additional duplicate tables and near-identical emitters may raise that after dependency-aware measurement; no credible 80% LOC reduction is established. The 42-file destination does not imply 70% code deletion. Prefer extracting/deleting verified duplication first, then group the small cohesive adapters, then simplify redundant orchestration only with explicit receipt and behavior contracts.

## What would be needed to approach 30 physical files?

The user's one-fifth goal remains a physical-file goal, not a count of conceptual domains. This investigation establishes a concrete 42-file map, not completion of a 28–30-file goal. A smaller design needs real algorithm/template reduction first:

1. Replace repeated simple expression emitters with a shared typed expression renderer and explicit rule records (argument/return C types, expression, rule ID, ABI registers, evidence). For example `sourcegen.py:4934–5048` and synthesis `:1525–1626` repeat arithmetic/bitwise source construction around the same decoder facts. Keep the two task/promotion metadata adapters. Preserve header text, integer signedness/width, calling convention, explicit candidate order and source-quality flags; no generic textual substitution or target-byte-success claim. Complex x87, forwarder and multi-statement rules should remain explicit until a measured common grammar exists. This is the next major LOC hypothesis, not measured savings.
2. Unify resumable stage execution mechanics only after listing each runner's receipt keys, stage IDs, fingerprints, cancellation and retry semantics. A shared execution loop plus separate declarative stage plans could eliminate repeated orchestration control, while maintaining the generic/profile/window workflows. A single physical pipeline module becomes reasonable only after that duplication is actually removed; current concatenation would exceed 5k lines.
3. Collapse proof-policy and claim rendering, repair and rewrite orchestration, or plugin engine/worker wrappers only if shared state transitions and result models remove duplicate control—not merely because their names sound related. The lock, provider and background ownership boundaries remain explicit APIs even within one module.

A measurable intermediate milestone is **134 physical files**: the first shared decoder file adds one; consolidating the five-file `containers` package to one and five-file `languages` package to one removes eight, after static caller migration and compatibility-wrapper removal. The containers/languages-only slice, with no new decoder file, instead takes core **141 → 133** and the canonical whole-source baseline **456 → 448**. Those are target counts for that slice, pending actual recount, distinct from the 134-file core milestone that includes the additional decoder. These packages are respectively 418 and 618 existing lines, so their consolidation does not create a giant module. The next checkpoint is the 42-file domain map above, subject to actual source size and dependency review. Reaching ~30 requires demonstrating the additional mechanisms above and selecting roughly twelve further physical merges; this investigation does not justify precommitting to those merges or a LOC percentage. Temporary wrappers and any new decoder modules must remain included in every reported count.

## Second design pass: exact 31-physical-file target

The following supersedes the first pass's 42-file stopping point as the **redesign target**, not as an achieved result or an LOC estimate. Together with the other investigators' allocations (CLI 20, corpus 24, dashboard 16), 31 gives the requested **91 physical Python files**. It requires eleven additional removals from the 42-file intermediate design. The original complete 141-file mapping remains above; this table applies deterministic further mappings to those destinations, so no old modules disappear from accounting.

| Further transformation | Files removed | Current source mass involved, before deletion | Required shared mechanics, and preserved boundary |
|---|---:|---:|---|
| `context_io.py` + `context_actions.py` → `context.py` | 1 | 3,756 lines | One target-bound context-item representation with provenance, source path, content kind, placement and proposed action; one ingestion/export traversal and receipt serialization path, followed by explicit proposal/application adapters. `context_apply.py:20,43` already consumes ready proposal rows and emits MCP steps/receipt. Do not equate export success with permission to mutate Ghidra; proposal remains pure and application remains an explicit call. Delete repeated path/provenance/receipt plumbing, not the format decoders. |
| Database `codec.py` + `tables.py` → `binary.py`; `program.py` + `store.py` → `project.py` | 2 | 1,843 and 1,822 lines | One binary reader owns buffer acquisition, schema decoding and record/table traversal; one project repository owns path resolution, item identity and typed program access. `store.py:26` imports fourteen project constants/types/resolvers, so this is a concrete shared model, not just a name match. Keep read-only access versus locked mutation as separate methods/classes; opening a reader must not acquire write capability. Retain package init and isolated JVM entrypoint. Packed-file temporary ownership remains scoped. |
| `assembly.py` + `retrieval.py` → `retrieval.py` | 1 | 2,754 lines | A single normalized function-feature record carries assembly body, calls, metrics, content hash and optional vector. `decomp_indexer.py:46–60` already coordinates these modules. Parse assembly once, derive metrics/embedding from that representation, share index/query scoring, retain architecture-specific parsing. Lazy embedding construction prevents optional chromadb/ML load on plain assembly import. |
| `plugin_pipeline.py` + `plugin_workers.py` → `plugin_pipeline.py` | 1 | 2,344 lines | One attempt result/event envelope for foreground and background completions; one coordinator owns abort and finalization. `BackgroundTaskCoordinator` remains an object with its own thread-pool/lock, not a second pipeline runner. Keep its five-second bounded shutdown (`background_task_coordinator.py:29`) and distinguish first-success abort from proof acceptance. Replace duplicated event/result adaptation, not concurrent execution with sequential execution. |
| `proof.py` + `claims.py` → `proof.py` | 1 | 3,368 lines | One receipt-backed coverage model drives target selection, budget decisions and rendered claims. Existing `proof_ladder.py:12,37` imports the claim report's private verified-count function; consolidate that evidence query and denominator selection once. Separate evaluation from filesystem writing and retain each legacy receipt schema/field. No bare artifact or completed rewrite may increment verified coverage. |
| `repair.py` + `rewrite.py` → `repair.py` | 1 | 2,411 lines | A shared attempt request/result model and explicit mechanism dispatch (shape search, permuter, rewrite) remove repeated context/hint/receipt conversion. **Reject a single undifferentiated state machine:** near-miss planning is not the pending/claimed/completed/failed file queue. Keep `RewriteQueue` as a locked transport adapter within the module; hold its lock only for read/check/write, never while running a provider/compiler. `near_miss_repair.py:31,65` selects/runs repairs; `rewrite_queue.py:62` owns cross-process claim locking. Queue completion supplies a candidate, not a verified match. |
| `unity_project.py` + `unity_export.py` → `unity_project.py` | 1 | 2,124 lines, excluding 1,219-line Editor gate | One installation/export manifest owns player paths, assembly inventory, scene/GUID mappings, dependency evidence and emitted-project paths; both probe/composition and AssetRipper/ILSpy adapters consume it. Current `unity_compose.py:1–35` explicitly says compose existing exports rather than synthesize them again. Delete repeated discovery/materialization and let adapters emit manifest updates. Keep AssetRipper launch/readiness/finally cleanup as a scoped owner; no implicit export during probing. Editor validation remains separate. |
| `source_export.py` + `receipts.py` → `artifacts.py` | 1 | 3,076 lines | One artifact resolver/publisher owns embedded-source versus path resolution, digest verification, advisory/verified classification, atomic metadata writes, snapshots and export projection. `source_export.py:44` already performs source hash integrity checking; `state.py:17` owns collision-safe atomic publication. Retain typed proof authority rather than one generic success flag. Report rendering consumes snapshots and must not add recursive publication. |
| `pipeline.py` + `source_parity_one_shot.py` → `pipeline.py`; retain `windows.py` | 1 | 3,989 lines plus unchanged window scheduling, before deleting shared control | One stage executor with explicit generic/profile plan records (IDs, receipt locations, fingerprint/skip policy, callable) replaces duplicated resume/save/event/dispatch loops. Plan-specific stage handlers and legacy aliases remain explicit; no string eval or dynamically generated Python. Window scheduling remains separate because it coordinates bounded binary partitions and aggregates their evidence, rather than being another stage plan. Cancellation and exit behavior are compatibility requirements. |
| `verification.py` + `compiler_search.py` → `verification.py`; retain `verify_pool.py` | 1 | 4,130 lines excluding worker pool | One compile/diff request (toolchain identity, target/source digest, language, flags, environment, timeout) and typed result/cache key. Search yields ordered requests; verifier executes them. `package_sweep.py:12,82–112` already imports the verifier and reconstructs nearly the same argument/cache tuple per attempt. Unify this plumbing and synthesis compilation adapters, but keep package text/code/slice comparison modes distinct. Explicit environment travels with subprocess requests; never expand the current process-global worker-env mutation. |

Arithmetic: 1 + 2 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 = **11 fewer files**, so **42 → 31**, and **141 → 31** is a **78.0% physical-file reduction**. This is not an 80% LOC reduction. The raw source masses deliberately expose where the design would create a large file if implemented as concatenation; those rows require the stated shared-model/mechanics rewrite before being counted complete.

### Exact destination list (31; including initializers)

1. `__init__.py`
2. `cli.py`
3. `acquisition.py`
4. `context.py`
5. `binary.py`
6. `containers.py`
7. `languages.py`
8. `ghidra_db/__init__.py`
9. `ghidra_db/binary.py`
10. `ghidra_db/project.py`
11. `ghidra_db/isolated_annotation_dump.py`
12. `enrichment.py`
13. `symbols.py`
14. `retrieval.py`
15. `prompts.py`
16. `pipeline.py`
17. `windows.py`
18. `plugin_pipeline.py`
19. `integration.py`
20. `sourcegen.py`
21. `source_parity_synthesize.py`
22. `decode_x86.py`
23. `decode_forwarders.py`
24. `verification.py`
25. `verify_pool.py`
26. `proof.py`
27. `repair.py`
28. `artifacts.py`
29. `unity_project.py`
30. `unity_editor.py`
31. `views.py`

### Credibility and acceptance conditions

This is a credible **conditional target architecture**, not a source-equivalence proof or an established lower bound. No inspected boundary requires all its current files: most require distinct ownership, classes or functions, while the isolated JVM genuinely requires a separate entrypoint/process. No unconditional physical-file lower bound above 31 was found. Conversely, the investigation has not measured the LOC savings of the proposed shared models; that work cannot be reported as accomplished.

Implement by mechanics, not table row order: (1) exact pure-decoder dependency extraction and renderer dedup; (2) context/artifact/compile request models with existing APIs adapting to them; (3) static caller migration and small-package merges; (4) shared receipt/attempt/stage loops; (5) delete dead adapters and recount actual files. The checkpoints remain measured current 141, bounded intermediate 134, first-pass allocation 42, and final target 31. A failed compatibility check blocks that slice, not permission to weaken proof or concurrency semantics to meet the number.

For inline-only validation, compare old/new pure decoder/renderers and state reducers in memory, including malformed/unknown input, candidate order, fingerprints, explicit null/false fields and legacy receipt projections. AST-import/entrypoint closure checks cover physical moves. Runtime operations (compiler termination, repository writes, Unity/JVM behavior, service job continuation) cannot be proved by those checks; preserve their implementation ownership and make runtime acceptance an explicit later authorization, rather than silently exercising them during this redesign investigation.


---

## Corpus package consolidation plan (dashboard excluded)

## Scope and inventory

The aggregate contains exactly 160 non-dashboard modules and 34,130 lines under
`src/agentdecompile_recovery/corpus`. Every module is assigned below. The target
is 24 files including `__init__.py` (an 85% file-count reduction). This is a
domain merge, not concatenation: repeated CLI registration, operation runners,
receipt writing, store access, watch loops, and materialization traversal should
be reduced while public corpus functionality is retained.

Static inventory found 38 standalone `main()` functions, 34 argparse users, 33
subprocess users, 30 sqlite users, and two dynamic file imports. Those numbers
explain the proliferation: features arrived as individually runnable scripts,
then `cli.py`, `kx_cli.py`, and `mizuchi_tools_cli.py` wrapped many of the same
scripts without removing their private parsers or execution glue.

## Complete 160 -> 24 module map

Each line names the target module followed by every original module it owns.

- `__init__.py`: `__init__`
- `config.py`: `contract`, `corpus_config`, `corpus_env`, `io`, `registry`
- `storage.py`: `store`, `db`, `correspondence`, `match_store`
- `cli.py`: `cli`, `kx_cli`, `mizuchi_tools_cli`
- `pipeline.py`: `pipeline`, `work_queue`, `donor_schedule`, `calibrate`, `channel_confidence`
- `inventory.py`: `archive`, `inventory`, `program_inventory`, `identical_image`, `fingerprint_hashes`, `advisory_evidence`
- `ghidra.py`: `ghidra_env`, `ghidra_project`, `ghidra_url`, `ghidra_import`, `apply_annotations`, `ghidra_verify`, `ingest_ghidra_knowledge`, `dump_func_bytes`, `export_bytes`, `decompile_text`, `binexport`, `shared_project_pair`
- `extraction.py`: `extract`, `decompile`, `decompile_shape`, `features`, `ctxtypes`, `callgraph`, `cfg_signature`, `mnemonic_spp`, `fuzzy_fingerprint`, `block_inline`, `high_emit`
- `matching.py`: `match`, `match_engine`, `match_islands`, `callgraph_propagate`, `bsim_ops`, `bsim_eval`, `second_opinion`, `evaluate`, `evaluate_fid`
- `identity.py`: `canon`, `naming`, `name_precedence`, `logical`, `identity`, `propagate`, `propagate_conventions`, `propagate_types`, `sibling_conflicts`, `review_sibling_conflicts`, `review_cross_game_conflicts`, `symbol_provenance`, `stabs_link`
- `stabs.py`: `machostabs`, `stabs_manifest`, `stabs_report`, `stabs_types`, `asm_seed`
- `source.py`: `source_claims`, `realc`, `ingest_recovered`, `collect_source`, `harvest_shards`, `restore_recovered_tree`, `consolidate_corpus`
- `normalize.py`: `normalize_pipeline`, `ghidra_sanitize`, `clang_scribe`, `llm_cleanup`, `ghidra_llm_cleanup`
- `compile.py`: `compile_link`, `build_project`, `build_types_header`, `mkobj`, `objdiff_check`, `compile_tally`
- `recovery.py`: `genproject`, `ghidra_bulk`, `recover_named_ghidra`, `permuter_harness`, `prompt_evidence`, `exact_corpus`, `rescue_symbol_mismatch`, `close_near_misses`, `experiment_real_c`, `measure_ghidra_c_yield`, `text_permuter_watch`, `recovered_c_preamble`, `leftover`
- `verification.py`: `seed_validation`, `verify_recovered_byteexact`, `verify_direct_full_image`, `verify_full_image_receipt`, `verify_built`, `verify_legacy_recovered`, `verify_packages`, `verify_periodic`, `rebuild_ledger`, `whole_image_relink`, `roundtrip`, `emulate_verify`
- `exact.py`: `exact_asm`, `exact_universal`
- `packaging.py`: `package_authoritative`, `package_binaries`, `package_project`, `package_readable`, `package_readable_index`, `package_recovered`, `package_unified`, `export_packages`, `workspace`, `workspace_skeleton`, `materialize_binaries`, `materialize_identified_data`, `materialize_mizuchi_output`, `materialize_old_recovered`, `materialize_recovery_candidates`
- `exports.py`: `export_atlas_db`, `export_mizuchi_db`, `export_hookpack`, `export_run_report`, `export_types`, `export_c`
- `reports.py`: `report`, `corpus_report`, `coverage_report`, `report_propagation`, `matching_status`, `fix_func_counts`, `ui`
- `bridges.py`: `external_bridge`, `mizuchi_bridge`, `discord_notify`
- `operations.py`: `cross_place`, `finish_binary`, `merge`
- `orchestration.py`: `recovery_orchestrator`, `matching_watch`, `runtime_dump`, `unpack`, `unpack_emulate`
- `platforms.py`: `nds_extract`, `nds_import`

`exact.py` remains separate from `recovery.py`: exact assembly/universal emitters
are terminal byte-authority mechanisms used by verification and packaging, not
ordinary source-recovery strategies. `platforms.py` remains separate because NDS
container extraction/import is format-specific and crosses external-tool/Ghidra
boundaries. Those two small boundaries keep the 24-file target honest rather than
forcing unrelated code into giant modules.

## Evidence and proliferation causes

1. **Script-first CLI duplication.** `corpus/cli.py:78-348` builds the public
   parser, while 34 specialized modules still build private argparse parsers and
   38 define `main()`. `kx_cli.py` explicitly says it mirrors former `kx/*.py`
   scripts, and `mizuchi_tools_cli.py` does the same for Mizuchi tools. Several
   watcher/orchestrator commands launch `python -m agentdecompile_recovery.corpus.*`
   instead of calling operations (`recovery_orchestrator.py:26-102`). One operation
   consequently has a parser, a wrapper registration, a subprocess command builder,
   and an implementation spread across files.

2. **Repeated process execution without one result contract.** At least 33 modules
   call subprocesses. `compile_link.py:20-65`, `seed_validation.py:300-370`,
   `rescue_symbol_mismatch.py:35-80`, `llm_cleanup.py:185-235`, and
   `prompt_evidence.py:160-180` independently choose timeout handling, captured
   output, error representation, and command receipts. Consolidation should create
   a small `OperationResult` plus `run_operation(argv, *, cwd, timeout, env)` in
   `operations.py`; compilation-specific interpretation stays in `compile.py` and
   verification fail-closed decisions stay in `verification.py`.

3. **Two stores plus direct sqlite usage.** `store.py` and `db.py` both describe
   the cross-build identity store; 30 modules mention sqlite directly. Read-only
   knowledge databases are legitimately distinct, but corpus-store connection,
   row conversion, transactions, schema upgrades, and program lookup belong in
   `storage.py`. Do not hide transaction boundaries behind a generic repository
   class; shared functions are enough.

4. **Matching grew by algorithm phase.** `match_engine.py` (682 lines) owns the
   in-memory evidence fusion; `match_store.py` (878) repeats a store-backed cascade;
   `match.py`, `match_islands.py`, `callgraph_propagate.py`, `block_inline.py`,
   `cfg_signature.py`, `mnemonic_spp.py`, `fuzzy_fingerprint.py`, and BSim modules
   expose individual phases. A single `matching.py` should retain named pure phase
   functions but share candidate filtering, evidence recording, confidence bands,
   and cascade execution. This is the largest real code-reduction opportunity,
   not merely a file merge.

5. **Packaging/materialization is one catalog expressed as scripts.** Five
   `materialize_*` modules are 44-126 line one-shot movers. They import common
   `package_binaries` constants and repeat path-to-binary resolution, destination
   checks, directory creation, moves, and counts. `materialize_binaries.py` already
   contains an operation list (`operations` around lines 60-105); promote that into
   a declarative artifact catalog in `packaging.py`, with specialized discovery
   callables only where necessary. The package/readable/unified modules similarly
   share source-authority selection and tree traversal.

6. **Watchers repeat the same control loop.** `matching_watch.py:75-102`,
   `verify_periodic.py`, `text_permuter_watch.py`, and `cross_place.py` each implement
   interval/error/watch behavior. `recovery_orchestrator.py:105-145` adds a second
   restart loop and launches module paths. `orchestration.py` should own one explicit
   `WatchSpec`/`SupervisorSpec` runner. This is not dynamic execution: the catalog is
   typed, finite, and maps stable command ids to ordinary functions or explicit
   subprocess argv when isolation is required.

7. **Compatibility modules and one-line variants became permanent files.**
   `realc.py` and `ghidra_llm_cleanup.py` are compatibility re-exports;
   `evaluate_fid.py` is a thin evaluation variant; `recovered_c_preamble.py` is a
   16-line constant module; many export/package variants differ only by policy.
   Move these names/constants into their owning domain and update internal imports.
   Do not keep 135 shim files: that defeats the requested file-count reduction.

## Side-effect and compatibility boundaries

- The installed entry point is only `agentdecompile-corpus =
  agentdecompile_recovery.corpus.cli:main` (`pyproject.toml:77`). Keep that path.
- `agentdecompile_recovery/frontdoor.py:1149` and recovery CLI archive commands
  import `corpus.cli`; keep `cli.main`, `run_list_archive_command`, and
  `run_check_extraction_command` stable.
- Dashboard actions construct `python -m agentdecompile_recovery.corpus.cli` and
  also refer to historical module command ids. Migrate its finite action catalog
  in the same slice as command relocation; never leave strings pointing at deleted
  modules.
- `recovery_orchestrator.py` currently launches `corpus.cli`,
  `text_permuter_watch`, and other old module paths. Convert its specs to canonical
  `agentdecompile-corpus <command>` argv or call functions for safe in-process
  one-shots. Retain subprocess isolation for compiler/Wine/long-lived watchers.
- `permuter_harness.py:506-579` dynamically imports `exact_universal.py` and
  `exact_corpus.py` by file location. Replace these with direct imports before
  deleting the files. File-location import is not a plugin contract here.
- Multiprocessing/pickling audit must precede moving worker callables in
  `ghidra_bulk.py` and verification/recovery workers. Workers must remain top-level
  importable functions under their new module path. Do not nest them in catalogs or
  closures.
- Preserve Ghidra imports lazily. `ghidra.py`, extraction, and recovery contain
  Java/PyGhidra imports that cannot move to package import time. `__init__.py` must
  remain small and must not import side-effectful domains.
- Preserve SQLite transaction ownership and subprocess isolation. Consolidation
  is not permission to turn one-writer boundaries into a shared global connection
  or to run unsafe compiler/Ghidra work in-process.
- Direct `python -m old.module` paths are compatibility surfaces in docs/scripts.
  Inventory and update repository consumers in the migration that deletes each
  module. External consumers should be supported through equivalent stable corpus
  CLI subcommands; if an external module import is documented as public, defer that
  deletion or explicitly version the break rather than silently shipping a shim
  forest.

## Estimated reductions

- **File count:** 160 -> 24 (136 files removed, 85%). This is exact for the map.
- **Mechanical CLI/parser/main duplication:** 1,800-2,800 lines removable across
  the 34 argparse/38 main surfaces once commands register directly in `cli.py`.
- **Operation/subprocess/watch glue:** 700-1,200 lines removable by shared explicit
  runners and watch/supervisor loops.
- **Matching/evidence cascade duplication:** 900-1,500 lines removable after
  comparing `match_engine` and `match_store` phase-by-phase and retaining one phase
  implementation with store adapters.
- **Packaging/materialization/export traversal:** 600-1,000 lines removable via
  the artifact catalog and shared authority/tree emitters.
- **Compatibility re-exports, repeated constants, JSON/receipt helpers, store
  plumbing:** 350-700 lines removable.
- **Total realistic code reduction:** approximately 4,350-7,200 lines (13-21%),
  yielding roughly 26,900-29,800 lines. The other ~27k lines implement real binary
  parsing, matching, recovery, verification, and packaging logic and should move,
  not be deleted. File count and line count are therefore reported separately.

## Migration order

1. **Smallest valuable slice: packaging materialization catalog.** Merge
   `materialize_identified_data`, `materialize_mizuchi_output`,
   `materialize_old_recovered`, and `materialize_recovery_candidates` into
   `packaging.py` behind explicit `MaterializationRule` data and one fail-closed
   move executor. Register their existing CLI names directly. This removes four
   old files while adding `packaging.py` (net three fewer physical files), and an
   estimated 120-200 lines without touching matching, Ghidra, or live
   recovery. Keep `materialize_binaries` behavior as the acceptance owner.
2. Merge compatibility/pure helpers: config, source, normalize, inventory, reports,
   STABS, and platform domains. Update imports and CLI registrations per domain.
3. Consolidate storage before matching. Establish one corpus DB API while retaining
   explicit read-only knowledge-DB connections and transactions.
4. Consolidate extraction/features, then matching/identity phase functions. Use
   old/new deterministic corpus snapshots and SQL output comparisons before deleting
   old modules.
5. Consolidate compile/recovery/verification/exact with worker-pickling and lazy
   Ghidra boundaries intact.
6. Consolidate orchestration last, after every command has a stable `cli.py`
   operation id. Replace old module argv strings, then delete old launch modules.
7. Reduce `cli.py` last by registering domain command descriptors rather than
   copying 34 parsers into one file. A descriptor names a command, its ordinary
   callable, and argparse configuration; it is not dynamic execution.

## Validation without filesystem tests

Allowed pure-inline/static checks for each slice:

1. Parse all changed Python with `compile(source, path, 'exec')`; do not import
   Ghidra/process-owning modules.
2. AST inventory: assert every old public function/class name is either mapped to
   a new top-level definition or deliberately internalized; assert all 160 source
   modules occur exactly once in the migration manifest.
3. Import-edge rewrite check: `rg` old module paths across `src`, `scripts`,
   `pyproject.toml`, docs, and dashboard action catalogs; deletion is blocked while
   executable consumers remain.
4. Parser-only comparison by AST or isolated parser construction: command names,
   option strings, requiredness, defaults, destinations, and choices must match.
   Do not dispatch commands.
5. Static side-effect scan: imports of `ghidra`, `pyghidra`, `jpype`, subprocess
   launch, sqlite writes, and environment mutation must not newly appear at module
   top level.
6. Worker audit: every multiprocessing target remains a top-level symbol and all
   argv module paths resolve to surviving modules/CLI commands.
7. For later authorized validation, deterministic fixture-free checks can compare
   pure canonicalization, matching signatures, manifest generation, and command
   construction in memory. Runtime/Ghidra/compiler acceptance remains a separate
   authorization and must not be inferred from these static checks.


---

## Dashboard Python consolidation proposal

## Scope and evidence

Canonical scope is the read-only checkout at
`/run/media/brunner56/MyBook/Workspaces/ai-projects/AgentDecompile`, not the
smaller isolated branch. The aggregate inventory records 52 dashboard Python
files and 26,920 lines. This proposal covers every one of those files.

The current file count arose from useful incremental boundaries that later
overlapped:

- The static dashboard has one module per panel, while `pages.py` dynamically
  imports those modules (`pages.py:92-125`) and also contains page assembly,
  caches, status probes, JSON projections, and entity routing. This made adding
  a panel locally easy but duplicated link/render helpers. The aggregate found
  exact `_clink` copies in six panel modules.
- React and static delivery grew alongside each other: `router.py` imports both
  `pages` and `react_api`, while `react_api.py` imports `pages`, `router`, and
  action/state modules. The result is late imports used as cycle breakers rather
  than a clear transport-to-domain dependency direction.
- `actions/catalog.py` says the browser never sends freeform argv and
  `actions/introspect.py` generates rows from public parsers, but catalog,
  introspection, context defaults, OpenAPI mounting, execution, receipts, and
  matching were each split into separate modules. They are one operation system
  with two distinct ownership domains: specification and durable execution.
- Compatibility packages add three nearly empty files: `app/__init__.py` and
  `panels/__init__.py` are empty, while `panels/common.py` re-exports the root
  helpers. `actions/__init__.py` and the root `__init__.py` mainly re-export.
- Stateful code was correctly separated but then called through cross-imports:
  `actions/jobs.py` owns the in-process `JobStore`, receipt persistence,
  cancellation and ownership locks; `preparation.py` owns durable missing-only
  preparation; `mcp_bridge.py` owns the live MCP session/context lock. These must
  remain explicit owners.

The target is 16 files including `__init__.py`. That is slightly below one third
of the current count and is aggressive enough to remove navigation overhead,
without creating a router, job, or rendering god-file.

## Complete 52-to-16 map

| Destination | Original modules | Responsibility |
|---|---|---|
| `__init__.py` | `__init__.py`; `actions/__init__.py`; `app/__init__.py`; `panels/__init__.py` | Stable public exports only. Temporary module aliases may live here during migration, then be deleted. |
| `contracts.py` | `app/models.py`; `app/responses.py`; `app/routes.py`; `workspace_state.py` | Dependency-light route/value/page-result contracts plus durable UI-state schema and atomic patching. |
| `common.py` | `common.py`; `panels/common.py`; `function_choices.py` | Filesystem/DB/query/escaping/link primitives and bounded function selection. Removes the wildcard re-export layer. |
| `catalog.py` | `actions/catalog.py`; `actions/context.py`; `actions/introspect.py`; `actions/openapi.py` | The existing generated `ActionSpec`/`FieldSpec` catalog, validation, implicit deterministic defaults, command construction, and OpenAPI projection. |
| `jobs.py` | `actions/jobs.py`; `actions/job_history.py`; `actions/matching.py` | Sole durable job owner: records, receipts, cancellation, locks, bounded execution, atomic candidate matching, history compatibility. |
| `transport.py` | `router.py`; `react_api.py`; `server_control.py`; `settings_page.py` | FastAPI/static/React route mounting, HTTP adaptation, notification settings, and local control hooks. No domain computation. |
| `mcp.py` | `mcp_bridge.py` | Sole MCP session/context-lock owner and live 8080 client adapter. Kept separate because session serialization is a runtime boundary. |
| `preparation.py` | `preparation.py`; `workflow.py`; `target_image.py`; `protection.py` | Sole missing-only preparation coordinator, workflow continuation, original-target authority and protected-image derivation. |
| `evidence.py` | `activity_receipts.py`; `analysis_view.py`; `entity_activity.py`; `function_evidence.py`; `recovery_status.py`; `source_archive.py` | Read models and receipt-bound evidence/archive projections. Archive worker entry remains top-level and name-addressable. |
| `inventory.py` | `workbench.py`; `binary_coverage.py`; `library_identity.py`; `variant_groups.py` | Binary/program/function inventory, registrations/imports, library presentation identity, coverage annotations and workbench data projections. HTML composition moves out. |
| `pages.py` | `pages.py`; `explorer.py` | Page shell, cache, status, explorer, JSON/page projections and catalog-driven page/panel dispatch. |
| `panels_overview.py` | `panels/directives.py`; `panels/steps.py`; `panels/binaries.py`; `panels/processes.py` | Mission, ladder, binary inventory and process/log overview renderers. |
| `panels_evidence.py` | `panels/crossmatch.py`; `panels/knowledge.py`; `panels/stabs.py` | Cross-build identity, Ghidra knowledge and original-symbol evidence renderers. |
| `panels_recovery.py` | `panels/recovery.py`; `panels/roundtrip.py`; `byte_parity.py` | Recovery, roundtrip/package and whole-image parity renderers, keeping their proof claims distinct. |
| `panels_entities.py` | `panels/entities.py`; `panels/callgraph.py` | Function/logical/review drill-downs and call graph routes/renderers. |
| `viz.py` | `panels/viz.py` | SVG/chart primitives shared by all render modules. |

All 52 originals occur exactly once in this table.

## Catalog-driven dispatch

Reuse the existing immutable catalog, not another specification hierarchy.
`actions/catalog.py` already defines frozen `ActionSpec` and `FieldSpec` values;
`ActionSpec.backend` plus `ActionSpec.command` is the current dispatch identity,
while `fields`, `pages`, `danger`, `mutating`, and `long_running` already carry the
metadata a second `OperationSpec` would duplicate. If name-addressable execution
later needs more information than `backend` plus `command`, add only that field to
`ActionSpec` rather than creating a parallel operation type.

The page side also already has `pages.Section`, with ID, title, explanation,
loaded module/error, lazy/open behavior, TTL, and heavy-work metadata. Move or
extend that type into a dependency-light catalog and replace its live module
reference with a renderer target string:

```python
@dataclass(frozen=True)
class Section:
    id: str
    renderer: str          # importable "module:function"
    route: str
    ttl: float = 0.0
    window: str = "wb-overview"
    lazy: bool = False
    open_default: bool = False
    heavy: bool = False
```

Each operation has one authoritative metadata owner, consumed by its CLI, MCP,
and dashboard adapters. Existing argparse/Click/MCP introspection is transitional
for legacy operations until their metadata moves to that owner; it must not create
circular CLI/dashboard authority or a second catalog framework. The dashboard
projects those facts into its existing `ActionSpec`/`FieldSpec` values. `pages.py`
owns `Section` entries for pages and panels.
Only if the existing section metadata proves unable to represent non-section
routes should a separate view type be introduced. A small resolver
uses `importlib.import_module` only in the web process and validates that the
resolved object is callable. Routes mount from the catalog; they do not contain a
second switch statement. This replaces `pages._load`/`_late_module`, repeated
router imports, `PANEL_WINDOW`, and per-panel link registries with one source of
truth.

Do not store callbacks or imported modules in durable state. Jobs persist only
the operation ID, validated parameters, timestamps, ownership/lock keys and
receipt paths. On resume, the current catalog resolves the operation ID again.

### Defaults are implicit; changes are explicit

Ordinary deterministic backend defaults apply automatically when a parameter is
absent. The CLI/UI catalog and request payload should not echo those defaults or
require a separate defaults-control knob; customizations are explicit parameters.
At the merge boundary, test key presence rather than truthiness so explicit
`false`, `0`, and empty-string values override a default instead of being replaced.

Context-derived target identity is not an ordinary convenience default. Database,
program, repository, and slug values must be checked against the current selected
target before dispatch. A stale selection, ambiguous slug, missing database, or
database/program mismatch must produce a validation error rather than silently
choosing another database or target. The current code already recognizes part of
this boundary by resolving a slug through the active corpus and by rejecting a
shared-filesystem directory where a program file is required; consolidation should
make those checks explicit and complete before applying safe backend defaults.

## Runtime ownership and worker constraints

- `jobs.py` remains the only owner of `JobStore`, durable receipts, cancellation
  files, duplicate admission, target/match/Ghidra locks and job state transitions.
  UI routes may query or submit; they never mutate job dictionaries directly.
- `preparation.py` remains the only owner of durable stage/resume state. Job code
  calls its public operation functions and records returned receipts; it does not
  reproduce preparation transitions.
- `mcp.py` remains the only owner of the MCP session and `CONTEXT_LOCK`. The web
  app continues to use the existing 8080 service; consolidation does not create,
  restart or bind a server.
- Thread callbacks may be callables, but durable/process worker targets must be
  top-level functions addressed by `module:function`. No lambda, nested closure,
  bound module object or catalog dataclass containing a callable crosses a
  multiprocessing boundary. `source_archive._worker_main` and any future process
  targets stay top-level so spawn-mode pickling works.
- Lazy `importlib` resolution is allowed only at dispatch boundaries. Resolvers
  cache successful targets by catalog ID and raise a precise startup/dispatch
  error for missing or non-callable targets. They never execute source strings.
- Compatibility imports should be temporary forwarding modules only during a
  staged migration. They count against the file target until deleted.

## Realistic line reduction

File consolidation alone does not remove logic: concatenating 26,920 lines into
16 files would be a file-count trick. A realistic first target is 22,500-24,000
lines (about 11-16% reduction), obtained from:

- deleting package/re-export boilerplate and repeated imports;
- one catalog-driven route/page/panel dispatcher;
- shared panel links, tables, safety wrappers and section composition;
- removal of exact `_clink` copies and similar repeated presentation helpers;
- one static/React transport adapter over shared projections;
- removal of compatibility modules after consumers migrate.

The large domain algorithms, SQL projections, proof distinctions and durable
state transitions should not be compressed merely to hit a line goal.

## First value slice

Start with the presentation/catalog seam, not durable execution:

1. Move/extend the existing `Section` metadata into the dependency-light catalog
   and add a renderer resolver; do not add a parallel `ViewSpec` unless current
   section metadata cannot represent a required non-section route.
2. Move the six exact `_clink` copies and common file/count link helpers into the
   existing shared panel helper, preserving rendered URLs byte-for-byte.
3. Express the current `pages.SECTIONS`, panel windows, route paths and renderer
   targets as one catalog. Make existing pages/router consume it while old panel
   modules remain in place.
4. Migrate one low-risk panel family (`directives`, `binaries`, `processes`) into
   `panels_overview.py`; retain thin forwarding imports temporarily.
5. Once every internal consumer uses the catalog, delete the three old modules
   and forwarding shims. This proves real file deletion and dispatch reuse before
   touching `JobStore`, preparation or MCP session ownership.

Acceptance for this slice is structural and pure: all old public renderer names
resolve to the same callables, every catalog route/ID is unique, every target is
an importable top-level function, and old/new render output matches for injected
in-memory rows. Because filesystem tests are forbidden, validate with an inline
`python -B` AST/catalog script that:

- parses all changed files in memory;
- checks unique operation/view IDs and routes;
- resolves targets without invoking renderers or providers;
- compares the old and new catalog tuples;
- verifies no lambda/nested function is registered as a worker target;
- scans imports to ensure transport depends on catalog/projections, not vice versa.

This does not prove live 8080 behavior, durable job recovery, database correctness
or rendered browser parity. Those require separately authorized runtime evidence.
