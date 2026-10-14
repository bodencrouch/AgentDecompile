# PR 260 remaining failure source triage

Compared exact base 32f7dc366abf401e0dd301dbe0a3cfe9265f97d1 with head ba4e. No tests/imports/runtime ran locally. Excludes determinism_surfaces, assigned separately.

All 29 failing test cases have unchanged test-file blobs. Exact traceback-module hashes are in ad-other29-triage.json; expanded implementation/doc hashes in ad-other29-module-blobs.json. No PR-caused regression identified among these 29 by source inspection. This is source attribution, not an executed base-run comparison.

- Agent docs (2) and user docs (1): GEMINI.md absent at both commits; README/.cursorrules and registry are byte-identical, existing tool-count drift 75 versus77 unchanged.
- Block inline (4): identical implementation/test fixtures; direct int(addr) fails on helper or hexadecimal string in both versions. New optional backfill path is not involved.
- Callgraph (2), channel confidence (1): unchanged match_engine/callgraph/block_inline/propagate. persist_status still applies channel admission before preserving verify, causing review. Changed channel_confidence removes an unused ch local; its output logic is unchanged for dict test inputs. Missing inline result is governed by unchanged matching/inline logic.
- CParser (1): unchanged structures.py invokes FakeCParser.getComposites; fake lacks method in unchanged test. Added _collectors helper import does not supply methods on FakeCParser.
- Corpus match status (2): unchanged propagate queries match.evidence and accesses row by key. Tests build raw SQLite tables/connections, not store.connect; missing column and tuple row factory are unchanged contracts. Store timeout change cannot affect these direct fixtures.
- Determinism basis (1): implementation's literal ALGORITHM_VERSION phase0.3+key:content_sha256+dep:content_sha256_16 and test's phase0.2 expectation are unchanged. Backfill cap cannot change constant.
- Explorer (1): explorer/router/workbench blobs identical; normalization replaces submitted assembly-floor with inspect stage in existing policy. Backfill timeout introduces no preparation stage policy.
- External validation CLI (1): build_parser unchanged; main changes only expand six one-line if statements in close-near-misses dispatch after parse_args. normalize-validation-report absent before/after, so rejection occurs before modified dispatch.
- Identical image (1): fixture abc*20 supplies60 hex characters; unchanged function requires64. No store access.
- Versioned import context (2): import_export/session_context/tool_providers blobs identical; same response lacks expected context. _collectors import addition only resolves previously undefined datatype formatter and does not alter context attachment.
- Auth contract (2): auth.py identical and explicitly rejects unconfigured dynamic host with403 before credential validation; test expects401. Preserve this security policy rather than changing authorization order to satisfy stale expectation.
- Program-analysis exports (1): program_analysis.__all__ and exact-set test unchanged; three added APIs were already present at base.
- Secondary docs (2): same missing historical plan-name expectation and wrapper-versus-canonical skill equality expectation; all relevant docs blob-identical.
- Tool analysis gate (1): unchanged tool_providers/program_analysis uses _run_analysis_gate; test expects wait_for_program_analysis_ready exactly.
- Unified pages (4): unchanged unified_pages/router/workbench markup/route contracts; old tests expect atlas link, donor text, legacy function-page element IDs, and report contents while current routes serve workbench shell. Store backfill cap does not modify reads, rows, markup, or route composition; initial clean fixture writes complete normally.

These are strong source-level baseline attributions with direct unchanged causes or identical relevant contract code. A base CI run is still needed for empirical baseline comparison and potential suite-global/environment effects.
