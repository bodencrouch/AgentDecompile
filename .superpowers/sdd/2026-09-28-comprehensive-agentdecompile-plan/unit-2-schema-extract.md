## U22

- **U22. Schema migration, versioning, and backfill.** New tables/columns (`func_param`,
  `logical_signature`, `func_bsim`, `vtable`, `match.divergence` + components,
  `func.mask_pattern`, re-based `func.block_hashes`). **Landed at `f5f6a88`:** `PRAGMA user_version` + a `schema_migration` ledger, strict
  migrations (any error raises), lock-tolerant data backfill (`store.py:291-298` keeps the
  lock/readonly tolerance for the concurrent-watcher case), and the `corpus.backfill` frame.
  **Remaining:** the ledger owns every DDL site (`store.py`, `db.py` until U82,
  `export_types.py`, `propagate_types.py`, `stabs_link.py`, `decompile.py`); a per-table
  per-binary delete registry so `remove_binary` (`store.py:209`) removes every per-binary
  row; migration 2 adds `binary.basis_hash`, `decoder_revision`, `analyzer_version` and
  makes `content_sha256` a cascade precondition. **Backfill is a raw-image re-extraction pass, and it must be scheduled and
  costed:** masked patterns, decode-based block hashes, and storage are computable from
  *existing* Ghidra state + the raw image in a read-only pass (no re-analysis — STRATEGY
  holds), but over the full corpus it is a real job: a cataloged, resumable, receipted verb
  (`corpus.backfill-signatures`). **Pre-fix identity data is not grandfathered silently:**
  `identity`/`logical_function` rows produced under the pre-D1/D3 nondeterministic cascade
  are, by this plan's own verdict, not reproducible — re-baseline them via U25 on the first
  run under the new basis and record the supersession.

## U82

- **U82. Schema unification** (prerequisite for every new `binary` column). Two `binary`
  DDLs exist (`AD/corpus/store.py:19-36` vs `AD/corpus/db.py:19-34`); `db.py` has a
  product-named default path and one importer (`name_precedence.py:45`). `db.py` is deleted
  and the importer repointed to `store.connect`; existing stores need no DDL change; the
  `role` column keeps one documented vocabulary in `store.py`.

## U21a

- **U21a. Scrub `src/`.** 57 files; 8 file renames with import shims; the `db.py` default
  path; the exporter docstring.
