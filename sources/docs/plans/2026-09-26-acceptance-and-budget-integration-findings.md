# Acceptance and objective-budget implementation findings — 2026-09-26

Status: source inspection; implementation and acceptance remain open. This refines
P0.4/P1.1 in the [session audit](2026-09-22-session-obligation-audit.md), without
changing the full scope or declaring either priority complete.

## Current acceptance paths requiring one shared policy

`corpus/ingest_recovered.py:load_seed_promotions` admits identity-linked,
byte-exact real-C seeds when their logical IDs agree with the destination identity.
Agreement with the existing assignment is not an independent semantic witness.
`parse_recovered` separately pairs a current file with historical byteExact coverage
by program/name without checking a current source digest. Both feed recovered-function
insertion; fixing only seeds leaves the other route open.

`package_authoritative.build` consumes those rows and corroborates placement through
address or unique byte matching. Placement does not prove the named entity or linked
source contribution. `finish_binary.load_byte_exact` unions truthy receipt results
by address without checking enclosing currentness/source/basis. These consumers must
not strengthen a local comparison into semantic or final-image claims.

Producer tracing found that `rebuild_ledger.rebuild` parses textual byte-identical
messages from a caller-supplied generator into coverage JSONL without source, target
or toolchain digests. `collect_source.collect` independently selects source by
program/name and labels it VERIFIED using that key. This permits source/receipt
mispairing. `verify_legacy_recovered.coverage_row` and `recover_named_ghidra` have
compiled source available but omit its digest. `restore_recovered_tree` recreates
coverage flags from database rows without a fresh compilation. `recovered_function`
has no candidate/accepted state, and consumers treat real-C rows as recovered.

The implementation therefore must update producers and consumers together; merely
requiring an invented new field downstream would quarantine everything without
providing a usable evidence path. Introduce a shared evaluator at the real promotion and
consumer boundaries, with producer-bound current source/target/dependency evidence.
Preserve unaccepted candidates and expose failed predicates. Independent semantic
binding requires a target-side discriminating witness; existing logical IDs, filenames,
byte equality and compilation are insufficient by themselves. Anonymous local matching
must remain a separate useful claim. Linked contribution requires emitted-region
selection evidence; an equal image made from fallback bytes earns no replacement credit.

Required negatives: Foo-labelled Bar rejected for named acceptance despite equal bytes;
source edited under same filename invalidates its prior comparison; discarded compiled
replacement receives zero linked contribution; unrelated valid evidence survives each.
Do not weaken `verify_full_image_receipt`'s current refusal to certify arbitrary build
command provenance. No new accepted receipt may be created by trusting producer labels.

## Persist objective allowance with existing command intent

Preparation hashes action arguments, basis and context into action identity. Supervisor
basis changes archive/reset local failure counters. Both are valid local retry rules,
but neither enforces the required objective ceiling across new hypotheses/wrappers.

The existing preparation row and `_LOCK`/`_write` predispatch intent are the first
integration seam. Persist an objective identity, allocation revision, cumulative
admissions and dispatch-keyed reservations there. Reserve atomically with the submitting
intent before `jobs.start_job`; count successful as well as failed dispatched attempts.
Repeated acknowledgments cannot charge twice, cached reuse cannot spend, and ambiguous
post-intent crashes keep their charge. Resume/basis/action-name changes preserve spending.
Malformed or historically incomplete accounting is unknown, never fabricated zero.
An explicit allocation revision may add future allowance without erasing prior spending.

Then propagate trusted parent objective/reservation identity through JobStore and all
nested dispatch paths. Caller parameters cannot mint budget authority. A preparation-only
limit is not global enforcement: standalone supervisors, wrappers and nested compiler
attempts need the same parent accounting contract or an explicitly separate objective.
Provider incident circuits and resource-class limits remain distinct required ceilings.

Required checks: changed hypothesis cannot replenish a spent objective; concurrent
candidates cannot both claim the last unit; failed intent persistence prevents dispatch;
crash/resume keeps ambiguous charges; child/wrapper attempts share parent spending;
independent objectives continue; malformed accounting refuses explicitly; authorized
allocation increases retain old usage. Budget exhaustion names an allocation change as
its wake condition, not merely a different input basis.

## Additional inspected boundaries — 2026-09-27

`finish_binary` now has a producer/consumer raw-observation correction under review;
this does not close independent symbol identity. Existing `identity.method` strings
are not sufficient witnesses: `logical.build` groups supplied canon keys; matching
propagates existing logical IDs; corpus symbol-authenticity permits manual/analysis
origins. A usable next positive route is exact embedded PE export identity bound
to the required image digest, with explicit RVA-to-VA conversion, forwarded/ambiguous
export rejection and independent target-side resolution. PDB name proximity is not
GUID/age binding. Implementation briefs and review records are retained outside the
codebase following the user's removal of the local mission runtime.

The existing inventory parser needs strengthening before supplying this witness.
`build_binary_inventory` reads the file separately from `identify_binary`'s hash,
so copying the identity digest into its output does not bind the parsed bytes.
`pe_exports` overwrites name aliases by ordinal index and silently stops at truncated
tables. Exact-name uniqueness cannot be inferred from that partial representation.
Reuse the parser with a frozen-byte digest, complete name-row preservation and
explicit table/string/mapping integrity; retain exploratory inventory compatibility.
Distinguish synthesized ordinal labels from actual names by name-table provenance,
not a prefix. Alias, duplicate-name, malformed/truncated-table and changed-snapshot
cases are prerequisites alongside the Foo-labelled-Bar rejection fixture. These are
now implemented and recorded in the target PE export identity receipt. That receipt
closes the embedded PE-export lane only; other identity roots, current-at-consumption
checks and linked-source contribution remain open.

`dashboard/byte_parity.py:byte_parity_state` separately adds text-permuter closure
counts and can override the reconciliation report with `variants_state` totals.
Therefore correcting the report alone cannot claim all UI coverage is accepted or
current. That consumer path needs its own source/target/contribution assessment;
its current behavior is an open acceptance boundary, not validated by report tests.
