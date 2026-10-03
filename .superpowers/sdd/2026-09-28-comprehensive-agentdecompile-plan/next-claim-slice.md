# Next U1 slice: bind selected corpus contribution to target content

Research basis: committed donor `2595ef42efc04df9869d81b3f6e4f090729fe4bc`, inspected through `git show` and `git ls-tree` while source integration owns the working files. This is a source review and implementation brief, not an executed acceptance receipt. No Python imports, tests, builds, services, corpus writes or recovery operations were performed.

## Concrete defect and existing claimed contract

`corpus/source_contribution.py:231–239` implements `_db_row(db, binary_id, address, size)`. Its entire database predicate is `SELECT addr,size FROM func WHERE binary_id=? AND addr=?`, requiring the singleton result `[(address, size)]`. The returned binding records the database path, numeric binary ID, address and size. It never reads `binary.content_sha256` or compares that content identity to the producer's observed target digest.

Consequently a genuine process-local compile and exact-placement observation for image A may receive selected-function credit when the same database path and binary ID actually describe image B, provided its address/size row is identical. Changing only `binary.content_sha256` after production is likewise invisible to revalidation. This is a physical corpus-target binding defect; it is not a claim that the current semantic identity lane accepts a wrong name.

The violated claim already exists: `docs/verification/2026-09-27-source-contribution.md:21–24` says selected-function coverage requires the exact producer database, binary, address and size. `dashboard/byte_parity.py:117–122,166–171` says standalone regions do not prove a complete function in a selected corpus and calls the shared evaluator to derive `qualifiedCorpusFunctions`. The existing positive fixture `tests/test_matching_contribution_consumers.py:78–100` creates only a `func` table, then expects two qualified functions: it demonstrates that even absent binary content identity is currently accepted by that contract. This finding is inferred directly from committed control flow; no counterexample was executed in this research run.

## Retained implementation and boundaries

The donor already implements the relevant lanes; do not replace them:

- `ingest_recovered.py:277–322` checks exact source digest, target snapshot/region and recorded original bytes. `semantic_identity.py` separately qualifies the bounded embedded PE export witness. These are retained local/identity lanes.
- `source_contribution.py:242–307` produces a registered native compiler observation, fingerprints source/target/toolchain/implementation dependencies and rechecks input currentness before capability publication. `validate_compile:310–335` reopens those artifacts. Imported JSON cannot mint credit.
- `source_contribution.py:344–364,396–425` derives final-writer contribution; discarded or later floor-overwritten objects get zero. `reconstruct:432–522` owns actual writes. Preserve these predicates.
- `matching_status.py:101–103,118–121,142–159` and `dashboard/byte_parity.py:113–153` already consume the same evaluator. Their existing function counts must now require a physically matching corpus target. Anonymous region observations, compilation, semantic name proof, selected function contribution and whole-image equality remain distinct.
- `cross_place_admission.py:191–215` already supplies the right policy precedent: it refuses missing binary content identity and rejects an image whose observed hash differs from `binary.content_sha256`. Reuse that narrow digest validation policy; importing its complete identity graph would wrongly require semantic identity for this anonymous contribution lane.
- `_full_image_receipt()` in `dashboard/byte_parity.py:94–96` intentionally grants no terminal receipt. `compilerProducedWholeImage` remains false for preserved-floor reconstruction even when whole-file bytes are equal.

## Relevant task requirements only

These are scoped increments of the obligations in `named-obligations-U1.md`, not completion of those obligations or all U1:

| Obligation | Owned predicate for this slice |
|---|---|
| R1, R2, R5; U1 requirements | Bind selected corpus input to exact target identity; reevaluate affected evidence; compilation alone is candidate admission. |
| `session-contract-2026-09-22:D07` and `RC-02` | Preserve real final-writer source contribution, and strengthen the existing RC-02 evidence note's exact DB/binary/address/size qualification. |
| `session-contract-2026-09-22:D09` | Report anonymous placement, qualified function coverage and image equality separately. |
| `session-contract-2026-09-22:D13`, `D21` | A changed selected target-content dependency invalidates the old qualified claim before publication/consumption. |
| `session-contract-2026-09-22:D22` | An unrelated binary-row edit preserves this local claim; do not hash the whole mutable database as an acceptance dependency. |

The plan's R1 and U1 exact target-snapshot requirement determine acceptance. Unknown/missing content identity earns no selected-function credit. The plan retains `binary.content_sha256`, never rowid/slug, with `NULL refuses` in its inherited binding decisions; those decisions address ordering as well, so they are corroborating policy rather than the sole authority for this new gate. The existing `cross_place_admission.physical()` is the concrete implementation precedent. Missing `binary` table/column, missing/ambiguous selected binary, NULL/empty/malformed content digest, or a well-formed digest unequal to the observed target all refuse qualification. Keep artifacts/candidates available for later revalidation; never fill an unknown digest from current target bytes and call it historical evidence.

## Bounded implementation scope and compatibility

Own `src/agentdecompile_recovery/corpus/source_contribution.py` and the single preflight call in `source_revalidation.py`. Adjust the existing synthetic fixtures/specifications in `tests/test_matching_contribution_consumers.py` and `tests/test_source_revalidation.py`; add focused helper cases in the existing contribution test file only if later verification is authorized. Consumer source edits are unnecessary unless an explicit refusal field needs correction.

Keep all public signatures and routing unchanged:

```python
compile_observation(*, source, target, address, size, workspace,
                    compiler="/usr/bin/clang", program="", name="",
                    binary_id=None, db=None, execution_fds=())
validate_compile(observation)
evaluate_reconstruction(observation, *, target_path=None, output_path=None,
                        db=None, binary_id=None)
revalidate(*, recipe, target, db, binary_id, workspace)
byte_parity_state(*, reconstruction_observation=None, db=None, binary_id=None)
```

The existing `compile_link.compile_source_contribution(**kwargs)` delegation remains valid. A compatible internal helper shape is `_db_row(db, binary_id, address, size, *, target_sha256=None)`: preserve the four positional arguments, but refuse a non-None database call without a valid expected target digest. The `db is None` standalone path still returns `None` and makes no corpus claim.

Read selected binary content and function extent in one explicit read transaction/snapshot, require exact singleton rows, validate the digest, and compare it to `target_sha256`. Record the selected content digest in `selectedRow` (for example `binarySha256`), alongside the existing path/ID/address/size fields. Do not record the entire database file hash or unrelated logical/name state. Proposed stable refusals: `missing_or_invalid_selected_binary_content_identity`, `selected_binary_content_mismatch`, and the existing `selected_database_row_changed_or_ambiguous`; missing schema/unreadable SQLite must remain an explicit zero-credit refusal rather than a crash in consumers.

Update every internal call, verified exhaustively by committed `git grep '_db_row('`:

1. `source_contribution.py:264`: pass `digest(target_raw)` from the captured producer target bytes.
2. `source_contribution.py:302`: repeat the same selected physical binding immediately before registering `_COMPILES`; compare the selected binding with the initially captured one rather than discarding a changed return value.
3. `source_contribution.py:326`: pass `record['target']['sha256']` and compare the current selected binding to retained `selectedRow`.
4. `source_contribution.py:403`: pass `item['target']['sha256']`; retain the existing equality check against the exact producer `selectedRow` and binary ID.
5. `source_revalidation.py:161`: pass `doc['target']['sha256']` during preflight. Its later producer and recipe checks remain intact.

Registered observations are process-local and imported records already fail closed, so adding a field to newly produced `selectedRow` must not become a migration that restores old audit JSON as authority. Old records lacking content binding cannot receive qualified corpus function credit. No change to semantic name admission, recipient-policy framework, whole-image linker acceptance, corpus schema, catalog routes, or generic target/toolchain profiles belongs in this slice.

## Exact positive and refusal specification

These are future executable specifications. The current mission forbids tests/builds for documentation validation, so none were run here.

1. **Positive physical binding.** Synthetic PE target A has two supported six-byte function spans. A read-only synthetic corpus has one binary row with the SHA-256 of the complete A image, and exact function extents. Genuine supported producer observations bound to that database/ID yield two placed regions, twelve bytes and two qualified functions through both existing matching-status and byte-parity consumers. Semantic proof remains false, preserved-floor whole-image compiler production remains false, and byte equality remains its own observation.
2. **Wrong selected image, equal spans.** Image B differs only outside those two spans, so addresses, sizes and machine bytes are the same but its whole-image digest differs. With B's digest recorded under the selected database ID, compilation against A refuses the selected binding before compiler invocation/capability publication. A never earns qualified function credit for B. Independently produced A evidence for a correctly bound A row remains usable.
3. **Unknown identity.** Parameterize missing binary table/column, no selected row, duplicate selected rows in a deliberately unconstrained fixture, NULL/empty/uppercase/malformed digest. Each produces an explicit refusal and zero qualified functions; it does not backfill a digest, delete the candidate or promote a filename/ID match. A no-DB standalone observation still qualifies anonymous region bytes only.
4. **Selected basis changes before publication or consumption.** Begin with correct A binding. Change the selected row's digest to B while retaining ID/address/size: before `_COMPILES` registration, producer recheck refuses; after production, `validate_compile` refuses and matching-status/byte-parity qualified count becomes zero. Raw image equality may remain true and must not override that refusal. A content-bound observation for an unrelated selected binary remains valid.
5. **Unrelated change survives.** Add/edit another binary row or another unrelated function row without changing A's selected binary content and exact function extent. A's retained observation and qualified contribution stay valid. A whole-database fingerprint would incorrectly fail this case.
6. **Existing gates remain separate.** Same-file source edit still withdraws only that source-dependent candidate; discarded/floor-overwritten A gets zero contribution while independent B survives; imported/forged audit records get zero; size/address mismatch refuses; compiler/toolchain change refuses. Correct physical target binding never sets `semanticIdentityVerified=True` or terminal whole-image acceptance.

For the later implementation run, review the diff and call-site coverage first, then execute only the specifically authorized verification and record its source revision, producer/consumer origin and observation class. Synthetic installed/source results cannot close catalog/game-target or full U1 acceptance.

## Adjacent findings intentionally deferred

`rebuild_ledger.py:156–174,212–228` reconstructs positive rows from legacy verifier text without the new source/target binding fields; current ingress rejects those unbound rows, so this is a producer compatibility gap rather than the selected target-content credit defect. `package_authoritative.py:64–65,113–114` still calls now-required `load_coverage_index`/`parse_recovered` arguments without supplying them, and its later reread/copy selection needs its own provenance review. `recipient_acceptance.py` has an identity-generation-only record lane with `recoveryCredit=False`; policy-currentness and production-event wiring remain separate incomplete work. Do not combine these independent changes with the selected corpus physical binding fix.
