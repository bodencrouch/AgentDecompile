# U2 decomp schema contract — independent review

Reviewed `decomp-schema-contract-brief.md`, the complete proposed `next-decomp-schema-contract.md`, the complete adopted `next-schema-ddl-contract.md`, U2 requirements/extract, STABS implementation and both review reports, and the named current source seams. References below use current source/report line numbers. This is contract and source reasoning, not implementation or SQLite acceptance.

**Adoption verdict: ready for controller adoption as the bounded next source slice. Spec verdict: pass. Quality verdict: pass with one Minor inventory correction.** No Critical or Important issue was established. The metadata table and affected reader/cache/deletion changes form a coherent dependency boundary; a smaller DDL-only patch would break existing observable behavior. No wider schema framework or prerequisite rewrite is justified by the inspected source.

## Findings

### Critical

None identified.

### Important

None identified at the required confidence threshold.

### Minor M1 — include the physical-schema inventory reader in the caller accounting

- Contract references: `next-decomp-schema-contract.md:16–35,140–152`.
- Source reference: `src/agentdecompile_recovery/corpus/dashboard/panels/stabs.py:595–617`, `_render_symbol_tables`.
- Confidence: 100; autofix class: manual.

The table inventory also reads decomp directly: it enumerates actual SQLite tables and counts all decomp rows when physically present. This production reader is absent from the proposed complete bounded inventory. It does not measure source availability or choose a fingerprint, so it should remain a physical inventory: after migration it may correctly display the newly installed empty decomp table and the metadata table. Routing this panel through logical absence would misdescribe the physical schema.

Suggested correction: add this as an explicitly unaffected physical-schema reader, with no implementation change required. Distinguish its total row count from `corpus_status`'s successful distinct-address witness count. This omission does not block adoption or require a larger implementation scope.

## Source-contract assessment

1. **Historical selector and NULL behavior are correctly characterized.** `match_store.py:138–150,297–313` chooses the first available column once for the table, including AST when every AST value is NULL/empty. It does not fall back per row. `:214–220,280–287` separately indexes skeleton and selected fingerprints by truthiness. The contract's skeleton/AST modes preserve both channels for admitted historical shapes, while explicitly refusing unsupported P-code extension columns instead of assigning them invented provenance. The same-ID receipt count is correctly counted once. ASTv1 tokenization and skeleton remain distinct algorithms in `decompile.py:15–72` and `decompile_shape.py`; neither becomes recovery or P-code proof.

2. **The compatibility row has a necessary and internally consistent meaning.** Contract `:46–60,87–106,118–125` records global installed-schema behavior, not observed source. A fresh physical table with logical absent retains the old per-build None and aggregate zero. A formerly installed empty table retains per-build zero. The absent/no-rows and skeleton/all-AST-NULL checks prevent contradictory current states from silently hiding evidence. AST mode deliberately permits historical NULL, empty and arbitrary text. Explicit ensure/attach/write transitions recreate the old global column-installation effect; migration alone does not erase skeleton availability.

3. **Admission and history are bounded.** Contract `:64–93` requires exact ledger and supported shapes before mutation, main-qualified object inspection, mixed-case TEMP refusal, occupied-name refusal and exact current state. The current `migrations.py:267–285` direct-v10 repeat really does call a moving current-version guard; freezing that branch to v10 ledger plus STABS shape is necessary when appending11. Keeping its forward path unchanged is sufficient. The report also correctly distinguishes raw historical readers from strict canonical read-only connect and tolerated old writable handles. Its supported v9/v10 fixtures must remain independently authored, not latest-schema relabels.

4. **Migration rollback and durable recovery are honestly separated.** The proposal leaves baseline and earlier forward steps intact, adds only nullable AST/index/new metadata, preserves old rows and NULL ledger basis values, and uses the existing per-step owned transaction. It forbids executescript/internal commit and does not claim a durable v11 can be safely relabeled10. A failed pending step and a committed but unacknowledged step have different outcomes. No destructive data transform or unplanned downgrade is proposed. Rails dump-drift review does not apply to this report-only SQLite contract.

5. **Writer ownership is explicit without changing successful public return behavior.** `decompile.py:118–157` currently commits successful writes and precommits through executescript. Contract `:114–125` deliberately removes the hidden precommit, retains successful-call commit of caller work, and places selector transition and one-key replacement in one operation scope. The ensure helper remains an explicitly documented compatibility mutator, distinct from pure admission. Independent part initialization stays outside the corpus ledger, with mixed/destination refusal before part DDL. These are specified behavior changes rather than accidental promises of validation-only ensure semantics.

6. **Cache scope is necessary and limited.** `preparation.py:2244–2284` hashes successful metrics/skeleton but omits selected AST; comparison receipts compare the inventory at `:2293–2327`. Contract `:108,149,160` adds the actual selector and selected value to a versioned projection. This is required when explicit transitions change the matching input. A selector transition is global, so it legitimately invalidates every affected binary projection, including binaries whose own rows were not rewritten. The unrelated-binary fixture should hold the global mode fixed. Controller serialization of preparation.py with U9 is established task context, not a missing ownership policy.

7. **Frozen deletion remains independent.** Current `delete_registry.py:348–383,447–502,509–514` explicitly supports9/10, with decomp optional and AST optional. Contract `:129–138` preserves those maps and adds only the explicit11 delta: mandatory decomp/AST/index and singleton state; retained global state is not a binary deletion row. The stated28 known/19 mandatory/9 optional totals follow from the prior27/17/10 inventory. Last-binary deletion must retain mode because an emptied installed table was still installed historically. Unknown/future/TEMP/attached refusal and survivor/count semantics stay unchanged.

8. **Authored acceptance scope is meaningful.** Contract `:154–165` specifies actual previous-registry fixtures, paired absence/empty and skeleton/AST counterexamples, real matcher/receipt/status projections, unchanged NULL/row identity, transition failures, independent part behavior, frozen deletion and future refusal. It explicitly catches the old deletion fixture's AST extraction of the MAIN_SCHEMA literal. These requirements support bounded implementation; none establishes passed behavior until separately authorized execution occurs.

## Limitations and acceptance risks

- Historical CREATE-versus-ALTER SQL spelling, shape allowlists, transaction/savepoint cleanup, commit acknowledgement, lock tolerance and mixed-domain refusal are source requirements only. This review ran no SQLite operation. In particular, caller-pending-work preservation must not be advertised as universal recovery from an engine/connection failure that destroys the outer transaction; future failure qualification must distinguish a surviving savepoint from transaction loss, propagate cleanup errors, and never reconstruct lost caller work or report success. No such engine-failure acceptance is established here.
- The skeleton consistency probe can scan all rows; the report explicitly acknowledges that cost. This review supplies no performance measurement or warrant to add an index.
- Old reader-recognized P-code extension columns intentionally refuse. No current producer was identified for those shapes; their external compatibility remains outside the admitted historical declarations.
- Preserving successful helper signatures is not installed-consumer qualification. A current guard can deliberately reject raw/unledgered handles previously repaired by helpers; the contract documents that tightening.
- U2/U22/U82 and the other persistent DDL owners remain open. Neither adoption nor future source implementation establishes live recovery, fresh rebuild, installed service, or all-schema completion.

## Performed work

Read AGENTS.md and repository entry references; inspected the assigned reports and current declaration, migration, writer, matcher, status, preparation, deletion and direct caller text. A bounded memory-registry search supplied no task-specific fact used in this review. Wrote only this review file and preserved concurrent work.

No source or Git changes, subagents, tests/collection, builds/typechecks, project imports, database open/query/migration, cryptographic computation, process/runtime/live/catalog inspection, provisioning, service/port operations or publication occurred. The source checks establish the review verdict above only.
