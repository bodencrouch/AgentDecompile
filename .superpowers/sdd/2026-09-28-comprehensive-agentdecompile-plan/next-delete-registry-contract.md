# U2/U22: bounded per-binary deletion contract

Source-only contract, 2026-10-02. No database was opened or queried; no deletion,
test, build, import, runtime inspection or Git mutation was performed. Owns this
report only. This is an implementation proposal, not evidence that deletion is
safe in an installed store. It does not close U2/U22 or the all-DDL ledger work.

## Smallest deliverable and public route

Implement one declarative deletion registry and atomic executor for **corpus
schema version 9 with no surviving unqualified identity dependencies**, with
explicitly recognized optional corpus tables below. The conservative dependency
gate below is part of admission; schema compatibility alone is insufficient.
Refuse other versions and unrecognized shapes before the first data write.
Do not turn this slice into migration, evidence garbage collection, logical
identity reconstruction, or removal of files/Ghidra programs.

Current source routing is:

- `store.remove_binary(con, *, repo_path=None, slug=None)` (`store.py:243`):
  nonempty `repo_path` takes precedence over `slug`; neither raises `ValueError`;
  no match raises `SystemExit`; success returns `{id, slug, repo_path, deleted}`.
  It currently deletes only 10 named tables and unconditionally commits.
- CLI `remove-binary` (`cli.py:318,924`) is marked dangerous/mutating with
  `identity_scope="database"`; its success JSON is the store result and exit 0.
  Missing selectors return exit 2. Its existing call opens through `connect`.
- `DELETE /dashboard/api/workbench/binaries/{slug}` (`dashboard/router.py:586`)
  calls `remove_registered_binary` directly. That wrapper requires confirmation,
  trims/validates the slug, opens through `_open_store`, catches `SystemExit` and
  `Exception`, closes the handle, and clears `_CACHE` only after success
  (`dashboard/workbench.py:321,580`). HTTP returns 200 with
  `{ok:true, removed:<store result>}`, otherwise 400 with `{ok:false,error}`.
  The direct route is not catalog-job admission; this contract does not claim
  otherwise or authorize exercising it during the current recovery mission.

Retain these selector, return and status contracts. Registry refusal raises a
specific `ValueError` subclass with a stable reason prefix and object name; CLI
must make it a nonzero error, never success JSON. Keep missing binary an error,
including repeat removal. Every successful result must remove exactly one
`binary` row. A caller-owned transaction result is provisional until its caller
commits; preserve the dict shape and document that fact in the function docstring.

**Route opening must also be covered:** `connect` is writable initialization and
can migrate/backfill before `remove_binary` executes. A deletion-only opener in
the new registry module must use SQLite URI `mode=rw`, establish the expected row
factory/timeout, and perform no schema initialization, journal-mode change,
backfill or directory/file creation. Use it in the CLI removal branch and in
`remove_registered_binary` only; preserve other `_open_store` callers. Catch open
errors inside the wrapper's error boundary and close owned handles on all paths.
Do not change the other lane's `store.connect`, `db.py`, or its read consumers.

## Exhaustive ownership inventory for this bounded corpus profile

Paths below are relative to `src/agentdecompile_recovery/corpus/` unless prefixed
otherwise. `B` is the selected integer `binary.id`; `S` its exact stored slug.
`L` is the pre-write set of `identity.logical_id` where `binary_id=B`.
`P` is the pre-write set of `(program,name)` from `recovered_function` rows with
`binary_id=B`. SQL values are always parameters; identifiers come only from the
static registry. These are ownership predicates, not basename/digest inference.

| Table | Ownership / action | Source authority |
|---|---|---|
| `binary` | Delete `id=B`, last; exactly one row | `store.py:24,243` |
| `func` | Delete `binary_id=B` after dependent function rows | `store.py:43` |
| `calledge` | Delete `binary_id=B`; caller/callee addresses alone confer no ownership | `store.py:92` |
| `identity` | Delete `binary_id=B`; retain every other member | `store.py:115` |
| `stabs_type` | Delete `binary_id=B` | `store.py:127`; duplicate DDL `stabs_link.py:18` |
| `match` | Delete `src_binary=B OR dst_binary=B`; each row once, including self-pairs | `store.py:141` |
| `func_param` | Delete `binary_id=B` before `func`; `(binary_id,addr)` FK may cascade | `migrations.py:180` |
| `ghidra_field` | Delete `binary_id=B` before `binary` | `migrations.py:194` |
| `bsim_hit` | Delete `src_binary=B OR dst_binary=B` | `migrations.py:220` |
| `bsim_query` | Delete `src_binary=B OR dst_binary=B` | `migrations.py:213` |
| `decomp` | Optional; delete `binary_id=B` | `decompile.py:96,118` |
| `ghidra_type` | Optional; delete `binary_id=B` | `export_types.py:17`; writes in `propagate_types.apply_adoptions` |
| `ghidra_type_origin` | Optional; delete recipient `binary_id=B`; **preserve another recipient's row whose `donor_slug=S`** | `propagate_types.py:15,108` stores copied layout provenance |
| `func_convention_derived` | Optional; delete `binary_id=B` | `propagate_conventions.py:99`, `derive_conventions` |
| `recovered_function` | Optional; delete only non-NULL `binary_id=B`; preserve NULL/unbound and other-build rows, even with equal program/name/path/source digest/target digest/logical id | `ingest_recovered.py:31,443` |
| `reuse_candidate` | Optional; delete `dst_binary_id=B`. Additionally delete source proposals whose `(src_program,src_name)` is in `P` **only if no surviving `recovered_function` row has that program/name**. Never globally prune unrelated existing orphans | `ingest_recovered.py:54,457-486` explicitly gives proposals coarse source identity and retains them while any candidate remains |
| `binary_source_alias` | Optional; delete `binary_slug=S`. This column is the explicitly written registration target, unique via `binary.slug`, not a guessed program name. Preserve every other target slug even if `sha256` is equal | `dashboard/workbench.py:468-469,485-486` |
| `logical_name` | Optional derived cache; invalidate rows with `logical_id IN L OR from_binary_id=B`; do not select a new winner | `name_precedence.py:154,172-216` derives name, member count and runners-up from membership |
| `logical_function` | Preserve all rows, including newly empty groups; update **only** `n_members` for `id IN L` to exact remaining `COUNT(identity rows)` | `store.py:100`; `logical.py:189-201`; explicit existing no-drop contract in `remove_binary` |
| `match_review_revision` | Delete-trigger-owned: `kind='match' AND entity_id` in deleted match IDs, and `kind='binary' AND entity_id=B`. Do not independently reset/reseed revisions | `match_review_schema.py:27,67-98` |
| `match_review_control` | Preserve incarnation; canonical delete triggers advance `next_revision` transactionally | `match_review_schema.py:22,67-98` |
| `match_review_audit` | Preserve **all** rows, including `match_id` of removed matches; append-only history intentionally lacks a cascading FK | `match_review_schema.py:35,99-108` |
| `eval` | Preserve run-level `run,metric,value,detail`; a shared run is not a binary owner | `store.py:158` |
| `schema_migration` | Preserve ledger | `migrations.py:44` |
| `basis_supersession` | Preserve old/new basis and receipt history | `migrations.py:132` |
| `binary_content_identity` | Optional; preserve all `source_path,sha256` rows. It protects source-path byte identity independently of registration | `dashboard/workbench.py:457-462` |
| `program_binding` | Optional; preserve all `(source_path,locator,program,updated)` rows. Program import exists independently of corpus registration and can be reused | `dashboard/workbench.py:640-663`; `dashboard/preparation.py:2027` |

The 17 mandatory tables are the eight `store.SCHEMA` tables, the ledger,
supersession, three review tables, `func_param`, `ghidra_field`, and both BSim
tables. Missing any is corrupt v9, not a zero count. The ten optional corpus
tables are `decomp`, `ghidra_type`, `ghidra_type_origin`,
`func_convention_derived`, `recovered_function`, `reuse_candidate`,
`binary_source_alias`, `logical_name`, `binary_content_identity`, `program_binding`.
If `reuse_candidate` exists, require recognized `recovered_function` too; if
`ghidra_type_origin` exists, require recognized `ghidra_type`. Missing optional
tables need no DDL and produce zero deleted counts where applicable.

Other current source DDL is explicitly outside this deletion profile. Do not
open those stores. If one of these user tables occurs on the supplied corpus
connection, refuse the whole deletion as an unsupported mixed store, even if
empty; a later profile needs separate ownership qualification:

| Tables | Keys/evidence and distinct owner | Source |
|---|---|---|
| `decomp_part` | `(repo_path,addr)` in an independent part file | `decompile.py:75,157` |
| `ctext` | `(repo_path,addr)` in `connect_ctext`'s separate text store | `decompile_text.py:9,20` |
| `func_knowledge`, `ingest_status`, `knowledge_attempt` | `(program,entry_hex)` / `program`; knowledge-cache identity is not corpus binary ownership | `ingest_ghidra_knowledge.py:15,31`; `dashboard/workflow.py:573-575` |
| `activity_event`, `activity_observation` | `revision` / `job_id`; independent `workbench-activity.sqlite` journal | `dashboard/entity_activity.py:289-300` |
| `grid_view_position`, `grid_tasks`, `grid_results`, `grid_view_events` | partition/sequence/task/result replay state | `src/agentdecompile_grid/view/applier.py:165-203` |
| `grid_match_score` | `task_id`, text `src_binary,dst_binary`, scored object ref; not integer corpus FKs | `src/agentdecompile_recovery/grid_lanes/cascade.py:303-330` |
| `grid_compile_receipt`, `grid_parity_receipt`, `grid_verb_receipt` | `task_id`, content/toolchain/basis/store refs; shared evidence | `src/agentdecompile_recovery/grid_lanes/{compile.py:441,parity.py:775,verbs.py:427}` |
| `recovered_function_candidate_migration` | Transient rebuild table, never a completed supported schema | `ingest_recovered.py:184-187` |

`sqlite_sequence` and SQLite's own autoindexes/statistics are engine bookkeeping,
not owned corpus data. Do not reset them. Planned `logical_signature`,
`func_bsim`, and `vtable` appear in the requirement but have no current corpus
CREATE TABLE source in this inventory; their presence is unsupported, not a
license to invent predicates. Unknown tables are refused, not silently preserved
while reporting exhaustive deletion.

## Required dependency refusal: different binary IDs are not independence

Source establishes a real cross-build deletion hazard:

- `propagate.bind_identities` (`propagate.py:167-333`) joins a source identity,
  copies its logical ID and match evidence to the destination, and labels the row
  `match:<run>:<status>`. Its fixed-point quarantine only governs the current
  binding pass; it is not a global persisted-descendant invalidator.
- `match_store.dependency_token` (`match_store.py:48`) uses
  `<content_sha256[:16]>:<decimal_addr>`; callgraph writers persist `dependencies`
  and `dependency_ancestry` (`match_store.py:727-751`). These tokens are not
  full-digest immutable root witnesses and may be ambiguous across builds.
- The dashboard writer uses a different envelope: `source`, `target`, `run`,
  nested string `witness`, plus component score/status
  (`dashboard/workflow.py:495-530`). Shared group membership can depend on edges
  beyond the single first witness saved for a node.
- `logical.resolve_ambiguous` chooses a reference build for `name-reference`,
  `name-disambiguated`, `name-weak`, `name-ambiguous`, and `name-unplaced` rows;
  `_emit_scored` persists only `canon_key` and `origin`, without the full reference
  provenance (`logical.py:231-311`). Absence of dependency tokens is not proof of
  independence. `func_convention_derived` likewise keeps `same_game`/`cross_game`
  class provenance without donor IDs (`propagate_conventions.py:170-220`).
- `cross_place_admission.identity_state` (`cross_place_admission.py:151-188`)
  fingerprints a bounded traversal of top-level token dependencies. It neither
  invalidates descendants nor handles every writer envelope above. Calling it
  does not establish global deletion safety, and invoking full admission would
  exceed this source-only deletion scope.

There is therefore **no qualified existing transitive invalidator to call and no
complete immutable root ledger to retain instead of the deleted rows**. Preserved
review audit alone cannot supply that missing proof. General deletion of A while
retaining a root/descendant identity on B is unsupported in this slice.

Use this deliberately conservative, mechanically decidable first profile:
before the first write, refuse with `binary_delete_dependency_unsupported:<table>`
if the planned survivor set contains **any** of:

1. An `identity` row with `binary_id<>B` (or invalid/unknown owner storage).
2. A `match` row not selected for deletion by either endpoint predicate, including
   unknown/NULL-endpoint rows. These can carry lineage used by later binding.
3. A `recovered_function` row not owned by B with non-NULL `logical_id`, including
   NULL binary owners: current ingest stores this as inherited advisory identity.
4. A `func_convention_derived` row not owned by B: its donor closure is unavailable.

This blanket gate intentionally refuses some unrelated evidence that a later
qualified dependency graph could prove safe. Do not weaken it to a JSON substring
search, shared `logical_id` check, method-prefix check, or empty dependencies list.
It avoids inventing provenance or running an identity reconstruction pipeline.
Other binaries' raw functions, local decompilation/type data, unbound recovered
source, reuse **proposals**, copied type-layout witnesses and immutable audit
history may survive under the listed registry rules. Reuse proposals are not
accepted identity, and their existing coarse-source survivor policy still applies.

There are real positive deletions: removal of the sole identity-bearing build,
or deletion from a corpus of unbound build/function/source records, while another
build's independent raw rows remain. Shared logical IDs with surviving identity
members now explicitly **refuse unchanged**, rather than passing the earlier
overbroad preservation assumption. Zero-member logical rows are still retained.
Future support for shared identity groups requires an independently reviewed
complete provenance/invalidator or immutable-root model; this is the precise
remaining ownership premise, not a schema migration performed during deletion.

## Preflight and atomic execution

1. Establish transaction scope **before target selection and all preflight**.
   With no active transaction, own `BEGIN IMMEDIATE`, then commit only on success.
   With an active transaction, use a unique savepoint; release on success without
   committing the caller's work. Lock/snapshot-upgrade failure is a failure,
   never a retry which replays part of the deletion.
2. Require v9 and the matching complete migration ledger. Require the mandatory
   table shapes and all present optional shapes against an explicit allowlist.
   Restrict this profile to the main store: refuse attached application databases
   and temporary schema objects that can shadow or intercept registered tables;
   qualify registry statements with `main` rather than discovering targets across
   connections or attached schemas.
   Validate ownership column types, nullability, keys, FKs and delete actions;
   reject views/virtual tables impersonating tables. Recognize source-declared
   additive columns only: `store.ensure_*`, migrations 1–9, STABS additions,
   `binary.code_func_count`, `ghidra_type.origin`, `decomp.ast_fingerprint`.
   Do not require optional additions absent in a recognized old optional layout.
   For `recovered_function`, initially support only the current six-column PK
   `(program,name,binary_id,addr,path,source_sha256)` and full current columns;
   older report/three-key/additive legacy shapes refuse even at corpus v9.
   No inference from table name or `user_version` alone.
3. Validate canonical match-review schema and singleton with the existing
   read-only `match_review_schema.require`; validate revision coverage of the
   selected binary and matches. Reject additional/modified triggers, unexpected
   foreign-key actions, unknown columns/objects on mutation surfaces, and unknown
   user tables. This prevents hidden cascading writes to preserved evidence.
   Do not disable foreign keys or triggers. The same contract must work with
   foreign keys enabled or disabled. Unknown views/indexes must be classified
   against the reviewed schema profile before admission; do not execute their
   expressions to discover their meaning.
4. Resolve exactly one binary using existing selector precedence. Capture `L`,
   `P`, selected match IDs, and intended counts within this same transaction.
   Refuse dangling affected `identity.logical_id` references or invalid owner-key
   storage rather than coercing ambiguous legacy values into deletion ownership.
   Preflight every applicable operation before the first DELETE/UPDATE. Optional
   table absence alone is allowed; malformed presence is not. No catch-and-skip
   SQL errors and no `executescript`, `ensure_*`, migration, ingest, logical-build,
   rebaseline or pruning helper call (several commit or perform broader writes).
   Apply the dependency refusal above to the planned survivor sets in this same
   transaction; failure leaves all roots, descendants, rows and revisions intact.
5. Delete in this fixed order: `reuse_candidate` destination rows; source-orphan
   proposals restricted to `P` using a survivor query excluding `binary_id=B`
   **but retaining NULL binary IDs**; `recovered_function`; `logical_name`;
   `bsim_hit`; `bsim_query`; `match`; `calledge`; `func_param`;
   `func_convention_derived`; `decomp`; `ghidra_field`; `ghidra_type_origin`;
   `ghidra_type`; `stabs_type`; `identity`; `func`; `binary_source_alias`.
   Update affected logical counts, then delete `binary` last. Both proposal
   passes aggregate into one `reuse_candidate` count without double-counting.
   Review triggers own revision cleanup/clock advancement.
6. Verify intended affected rows are absent and required counts agree, including
   exactly one binary, before commit/release. Unexpected constraint/trigger/I/O
   errors or count disagreement abort the entire operation. Owned transaction:
   rollback on any `BaseException`, including commit failure. Caller transaction:
   `ROLLBACK TO` then `RELEASE` only this savepoint; preserve earlier caller work.
   Do not close a caller-owned connection. If SQLite itself invalidates the outer
   transaction or rollback fails, report that failure; do not promise preservation
   SQLite could not provide and never return a success receipt.

## Counts, shared logical state and deliberate boundaries

Keep all ten existing `deleted` keys. Add every newly explicitly deleted table
and `match_review_revision`. Use actual direct DELETE rowcounts; aggregate the
two proposal passes. For review revisions, count the selected revision keys
before deletion and verify their absence afterward, because trigger changes
are not included in parent DELETE rowcounts. Validate canonical triggers first.
Use zero for absent optional deletion tables. Include `logical_function:0` and
`match_review_audit:0` to make preservation visible. Do not count logical count
updates, clock increments, artifacts, or unrelated trigger operations as deletes;
do not use `total_changes` as the public deleted count. Result ordering follows
the registry and is stable. Build the result only after successful commit/release.

For admitted deletions, logical IDs, canon keys, descriptive metadata, audit history and surviving
recovered candidates remain intact. `logical_function.n_members` becomes the
remaining physical identity-row count, including zero; `logical_name` is invalidated
only where membership/provenance changed. No replacement winner, new identity,
proof, determinism basis or `previous_keys` history is fabricated. Retained
descriptions are historical metadata, not revalidated membership evidence.
Separate U2 stable-entity-key/previous-key work remains open; deletion cannot
claim that export identity stability is solved by a count update.

Files named by recovered rows, uploads, source binaries, compiled artifacts,
object-store receipts, knowledge caches, source-path digest protections, program
bindings and Ghidra projects/programs remain unchanged. An operator wishing to
forget those independent objects needs another explicitly scoped operation.

No new migration is required for this v9 registry slice. Supporting old recovered
shapes, a future schema version, mixed grid stores, or finer reuse-source ownership
needs a separately reviewed profile/migration; currently each has a visible
refusal. The all-DDL ownership consolidation remains a separate U22 obligation.

## Exact implementation ownership and regressions to AUTHOR ONLY

Future slice owns new `src/agentdecompile_recovery/corpus/delete_registry.py`,
only `store.remove_binary` and its docstring, only the `cli.py` removal branch,
only `dashboard/workbench.remove_registered_binary`, and new
`tests/test_corpus_delete_registry.py`. No `connect`/`db.py` changes. Author tests
only when separately assigned; do not execute/collect them under current rules.

- Positive: populate every registered owned table for the selected binary and
  another binary's raw, unbound rows within the explicit survivor profile;
  delete either selector and verify exact counts, all owned rows removed, every
  unrelated row unchanged, one binary removed. Cover self-match/BSim pairs.
- Shared evidence: same program/name with two builds and NULL-bound candidates;
  same digest/path across candidates; donor provenance copied to surviving build;
  reuse destination deletion and last-source disappearance versus surviving-source
  retention; unrelated preexisting orphan proposals untouched; exact alias target
  removal while digest registry/program bindings survive.
- Logical state: newly empty logical groups persist; only affected
  member counts change; affected/donor-derived logical-name caches invalidate;
  no logical builder/proof recomputation is called; audit rows remain byte-equal.
- Dependency refusal: A→B→C matched identity chains; dashboard component-envelope
  witnesses; ancestry tokens including truncated-digest ambiguity; name-disambiguated
  identities without explicit parents; inherited recovered logical IDs; derived ABI
  rows without donor IDs; and shared logical groups all refuse before first write.
  Assert exact preservation of A/B/C and review clocks/audits. Also assert the
  declared conservative refusal for unrelated surviving identity/match rows so a
  later change cannot silently claim broader lineage support. No transitive bind,
  logical rebuild, fingerprint recomputation or root-proof replacement is called.
- Schema: full v9 and every recognized optional-table absence; no creation on
  absent tables; missing mandatory table, damaged ledger, old/future version,
  malformed optional table, old recovered PK, unknown table/column/trigger/view,
  unsupported mixed stores and stray migration table all refuse before first
  data write. Missing path in route opener must not create a store or directory.
- Atomicity: inject failure at every delete/update, trigger failure, final binary
  count mismatch, commit failure and lock error. Verify complete rollback for an
  owned transaction. With prior caller writes, verify savepoint rollback preserves
  them; success remains uncommitted and caller rollback restores removal too.
  Exercise FK ON/OFF and snapshot-upgrade failure without partial replay.
- API: no-selector and missing-target remain errors; repo precedence retained;
  CLI emits no success on refusal; confirmation failure never opens the store;
  HTTP open/refusal errors return existing error envelope, success uses actual
  deletion result, and cache clears only on committed route success. Route removal
  cannot invoke `connect`, migration/backfill, filesystem deletion, or Ghidra.

Verification for this report: read-only DDL, writer and caller inspection plus
document inspection only. The source inventory bounds the proposed supported
profile; it makes no assertion about any actual installed database's contents.
