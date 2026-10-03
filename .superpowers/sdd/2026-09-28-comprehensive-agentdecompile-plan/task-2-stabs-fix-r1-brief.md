# Task2.3 fix round1

Reviewed base325ec899ac1535c2413ea6534f6346be1a48f328. Read original task-2-stabs-brief.md, adopted next-schema-ddl-contract.md, report and task-2-stabs-review.md. Address sole Important P1 case-sensitive TEMP shadow bypass. Use SQLite ASCII case-insensitive identifier comparisons in both new guards, review new reserved-name comparisons for same root cause without broad schema redesign. Keep baseline/migrations1–9/runner unchanged.

Own only corpus/store.py, corpus/migrations.py, tests/test_corpus_stabs_migration.py and append task-2-stabs-report.md; additional originally owned focused test may be changed only if necessary for direct writer refusal coverage, report exact path. No other source changes.

Author mixed-case TEMP tables/views for func, stabs_type and schema_migration: actualv9 migration refuses before DDL; currentv10 public writers refuse before persistent or TEMP mutation; main/TEMP contents, version/ledger and pending caller work preserved. No tests/collection/DB execution/import/build/typecheck/crypto/runtime/live/provisioning/Git/subagents. AST parse/diff/text checks allowed. Original implementer retains ownership, not alone; preserve concurrent work. Return READY_TO_COMMIT with exact paths and limitations.
