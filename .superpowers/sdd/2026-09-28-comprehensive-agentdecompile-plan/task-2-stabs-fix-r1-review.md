# Task2.3 fix round 1 independent review

Reviewed the exact `task-2-stabs-fix-r1-review.diff`, base `325ec899ac1535c2413ea6534f6346be1a48f328`, head `34b7287f123cff90c36eeac08f287db8833aeea0`, with the fix brief, original review, and appended implementation receipt. The original adopted contract remains the scope boundary.

**Spec verdict: pass for this bounded source correction. Quality verdict: pass for this bounded source correction.** The sole original Important P1 is addressed. No new Critical or Important finding was identified. This does not establish executed SQLite behavior or full Task2.3/U2 acceptance.

## Addressed original finding

The TEMP checks at `src/agentdecompile_recovery/corpus/store.py:200–203` and `src/agentdecompile_recovery/corpus/migrations.py:329–330` now apply `COLLATE NOCASE` to the schema-name operand. Mixed ASCII-case table/view names therefore reach the existing shadow-refusal path instead of passing case-sensitive text comparison.

The placement preserves the intended boundary: migration10 calls ledger and shape admission before its first ALTER/index statement (`migrations.py:277–284`), and the existing public STABS writers reach these same checks before their writes. In particular, a mixed-case TEMP ledger is refused before the unchanged runner can insert its migration row into that shadow. No schema repair, transaction commit, rollback, or fallback is introduced by either guard.

## Additional reserved-main-name check

The new loops at `store.py:210–230` translate ASCII A–Z only and reject noncanonical spellings of the bounded declared STABS object names and attribution/owner column names. They do not normalize arbitrary SQL or rename objects. Canonical lowercase historical declarations continue through the existing admission path, and unrelated func extensions do not match the reserved-name set.

This is consistent with the adopted strict observed-shape policy: unsupported mixed-case reserved indexes/columns now refuse before DDL instead of being mistaken for missing additive objects and failing after an attempted install. Mixed-case reserved triggers cannot evade the existing occupied-name policy through SQLite's separate trigger namespace. No Important compatibility regression was identified within the supported historical shapes. Main-ledger lookup remains exact and refuses a noncanonical table spelling; no broader admission was added.

## Preservation and authored regression assessment

- The exact supplied diff changes only the two admission helpers in production source. Baseline declarations/SCHEMA, migration1–9 bodies and identities, migration10 body/registry, and the runner have no changed hunks. No deletion profile or writer transaction code changes. This is a diff-level preservation check; the implementer's reported AST comparison was not rerun.
- `tests/test_corpus_stabs_migration.py:316–359` authors actual-v9 runner and caller-owned direct-body refusal cases across three mixed-case names and both TEMP tables/views. Shadows contain observable data from main; main/TEMP snapshots, the v9 ledger, transaction state, and pre-DDL traces are checked.
- `:362–396` authors current-v10 direct ensure/replacement/manifest/propagation/link refusals with pending caller work. Assertions cover main/TEMP preservation, exact ledger, absence of mutation/commit/rollback/release/temp-store operations, and caller rollback of its provisional marker. The link sentinels prevent unnoticed filesystem continuation if admission is bypassed.
- `:399–419` authors pre-DDL refusal for mixed-case reserved index, trigger, and optional column names. These cases exercise the added main-name checks without adding a new schema compatibility policy.
- The new cases supplement the original lowercase and positive admission cases; they do not replace them. All remain authored and unexecuted. No test result is inferred from their source.

## Findings and limits

Critical: none. Important: none remaining in this correction scope. Minor: none identified requiring a separate note.

Read only the assigned correction artifacts and bounded guard/migration/test source ranges. No broad schema or branch re-review was performed. Wrote only this review document; concurrent edits were preserved.

No source or Git changes, subagents, tests/collection, project imports, database opens/queries/migrations, builds, typechecks, runtime/live/process inspection, provisioning, or publication were performed. Actual SQLite acceptance, historical-database compatibility, installed behavior, and broader U2/U22 completion remain unverified. The original review's source-only qualification limits still apply.
