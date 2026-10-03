# U13/U29 Reconciliation Report (read-only)

A = MyBook checkout, git HEAD 0532da9b, branch feat/cockpit (scm_version.json: tag 2.0.0, distance 552, node g622944b0, node_date 2026-09-22, dirty=false)
B = /home/brunner56/agentdecompile-nvme (NOT git; live 8080 server root via inplace_hotreload --root B/src). B/src is directly under B/src/ (not B/AgentDecompile/src). B/AgentDecompile is a separate, older sibling clone containing pyproject.toml, docs, etc.
B scm_version.json: tag 2.0.0, distance 257, node g4167d4f0, node_date 2026-09-09, branch feat/evidence-fusion-matcher, dirty=true.
No REVISION/VERSION marker file in B; no "revision" string found in agentdecompile_cli/server.py.

pyproject.toml: A's pyproject.toml == B/AgentDecompile/pyproject.toml byte-identical (0 diff lines); B/src has no pyproject.toml of its own (package install lives in B/AgentDecompile).

## Counts (rsync -rcn, A/src <-> B/src, excl __pycache__/node_modules/dist/*.pyc)
- Only in A (not in B): 184 files + 12 new directories — dominated by whole new package `agentdecompile_grid/` (fleet orchestration, not present in B at all) and `agentdecompile_cli/mcp_server/providers/_program_context.py` (new provider-context module, U29-relevant, absent from B).
- Only in B (not in A): 18 files — `agentdecompile_recovery/catalog.py`, `introspect.py`, `containers/{detect,models,nds,registry}.py`, and 12 built Vite assets under `corpus/dashboard/static/react/assets/*` + `static/recovery-prototype.html`. These are real B-only source/build artifacts A has not received.
- Differ on both sides: 174 files.
  - B-newer (mtime): 17 files — these are the live-edited hot-reload set: `agentdecompile_cli/{cli.py,launcher.py,mcp_utils/program_analysis.py}`, `agentdecompile_recovery/corpus/{ghidra_project.py,dashboard/preparation.py,dashboard/workbench.py}`, `agentdecompile_recovery/corpus/dashboard/frontend/src/ProjectDialog.tsx`, `agentdecompile_recovery/corpus/dashboard/static/{dashboard.css,workbench-app.js,workbench-chrome.css,workbench-editor.css,workbench-sidebar.css,workbench.css}`, `agentdecompile_recovery/ghidra_db/{btree.py,master_table.py,project.py,store.py}`.
  - A-newer (mtime): 157 files — everything else that differs; A is the actively-committed checkout and has moved on from most of B's tree.

## Top differing .py files by diff line count (B vs A, `diff B A | grep -c '^[<>]'`)
1434 agentdecompile_recovery/corpus/dashboard/actions/jobs.py
1416 agentdecompile_recovery/source_parity_synthesize.py
1246 agentdecompile_recovery/sourcegen.py
1052 agentdecompile_cli/cli.py (B-newer mtime, but large diff — likely diverged both ways)
 917 agentdecompile_recovery/corpus/verify_recovered_byteexact.py
 715 agentdecompile_recovery/corpus/cross_place.py
 661 agentdecompile_recovery/corpus/dashboard/preparation.py (B-newer)
 513 agentdecompile_cli/mcp_server/providers/project.py
 417 agentdecompile_recovery/corpus/cli.py
 354 agentdecompile_recovery/containers/__init__.py
 338 agentdecompile_recovery/source_plugin_runner.py
 330 agentdecompile_cli/mcp_server/providers/import_export.py
 299 agentdecompile_recovery/corpus/ghidra_bulk.py
 295 agentdecompile_cli/mcp_server/tool_providers.py
 285 agentdecompile_recovery/corpus/dashboard/entity_activity.py
 258 agentdecompile_recovery/corpus/dashboard/panels/entities.py
 255 agentdecompile_recovery/corpus/ingest_recovered.py
 245 agentdecompile_recovery/corpus/seed_validation.py
 243 agentdecompile_recovery/corpus/match_store.py
 243 agentdecompile_recovery/corpus/dashboard/workbench.py (B-newer)
 223 agentdecompile_recovery/corpus/verify_direct_full_image.py
 221 agentdecompile_recovery/corpus/export_hookpack.py
 201 agentdecompile_recovery/corpus/recovery_orchestrator.py
 191 agentdecompile_cli/mcp_server/providers/getfunction.py
 183 agentdecompile_recovery/corpus/extract.py

Full lists: /tmp/adplan/u13-a-to-b.txt (rsync A->B), /tmp/adplan/u13-b-to-a.txt (rsync B->A), /tmp/adplan/u13-classify.txt (mtime + A/B-newer per differing file), /tmp/adplan/u13-diffcounts.txt (all .py diff-line counts), /tmp/adplan/differing_files.txt.

## Revision finding
A is a proper git checkout at 0532da9b (feat/cockpit); B is not a git repo and carries no REVISION/VERSION file and no "revision" string in server.py. The only revision proxy is B/src/agentdecompile.egg-info/scm_version.json, itself stale relative to B's live-edited files (node g4167d4f0 / distance 257 / node_date 2026-09-09 / dirty=true, vs A's g622944b0 / distance 552 / 2026-09-22) — i.e. B's own package metadata doesn't reflect the 17 hot-reloaded files that are newer than everything else in B.

## U29 finding (explicit MCP program dispatch)
B already has the scaffolding named in the plan unit but not the final explicit-dispatch shape:
- `agentdecompile_cli/context.py` has a `ProgramInfo` class with `current_program` property/setter, a `PyGhidraContext.programs` dict keyed by path/name, `get_program_info(binary_name)`, `_init_program_info`.
- `agentdecompile_cli/executor.py` already threads a `program_info` value through `context` dict (`"program_info" in context`, `_execute_with_program_info`, priority comment "ghidra_tools (full in-process) → program_info (program only) → placeholder"), and recognizes `programPath` as a parameter alias.
- `agentdecompile_cli/mcp_server/tool_providers.py` (B, live) has `_optional_program_norm = frozenset({"programPath","program_path","binaryName","binary_name"})` — i.e. per-call optional program identifiers are recognized at the dispatch layer already.
- **A has a file B lacks entirely**: `agentdecompile_cli/mcp_server/providers/_program_context.py` (only-in-A, new). This is very likely the actual explicit-dispatch implementation the plan unit wants, not yet reconciled into B's live tree — B is running the pre-U29 provider code.
- Conclusion: explicit per-call program dispatch is partially wired (context/executor/tool_providers all reference program_info/programPath) but the dedicated `_program_context.py` module that the plan's "manager/base optional keyword-only program_info" architecture implies exists only in A and has not reached B/the live server.

## Recommended reconciliation order
1. Canonical source of truth for *committed, reviewed* code is A (git, HEAD 0532da9b) — it should win for the 157 A-newer files and for anything A has that B lacks (`agentdecompile_grid/` package, `_program_context.py`).
2. B's 17 B-newer files are live, hand-edited-via-hot-reload and represent in-progress work not yet synced back to A — these must be diffed and merged into A (not blindly overwritten) before any A->B sync, especially `agentdecompile_cli/cli.py`, `mcp_utils/program_analysis.py`, `corpus/dashboard/{preparation,workbench}.py`, `ghidra_db/*.py`, and the CSS/TSX under dashboard frontend — treat these as "dirty owner changes to preserve" per AGENTS.md.
3. B's 18 only-in-B files (`catalog.py`, `introspect.py`, `containers/*`, built react `assets/*`) need a decision: `containers/*` and `catalog.py`/`introspect.py` look like real untracked source additions in B that A does not have — reconcile into A's git tree (do not discard); the built `static/react/assets/*` files are Vite build output and should be regenerated from A's `WorkstationApp`/vite.config.ts rather than copied.
4. B/AgentDecompile (the sibling, non-serving clone with matching pyproject.toml) is redundant with A for packaging metadata — no action needed there; A's pyproject.toml is already canonical (0 diff).
5. Do not copy/overwrite in either direction under this read-only mandate — this ordering is for the follow-up authorized reconciliation pass.
