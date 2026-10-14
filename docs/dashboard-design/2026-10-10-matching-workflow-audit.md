# Matching-workflow audit — 2026-10-10

Scope: the static 8080 correspondence workspace, evidence explanation and shared
analysis cursor. This is a bounded audit receipt, not a new pipeline or living
plan. Existing dirty changes and the current matching/acceptance contracts were
preserved. No test files, test suites, recovery jobs or restarts were performed
by the auditor.

Authority: [STRATEGY.md](../../STRATEGY.md#one-catalog-two-surfaces) and the
[evidence-fusion contract](../plans/2026-09-09-0334-feat-evidence-fusion-matcher-plan.md)
R1–R18/F2–F5. Unique anchors and distinguishing call neighborhoods can establish
correspondence; score ranking alone cannot. Conflict, inline/split/fold relations,
identity, source interchangeability and byte parity retain their separate gates.

Status legend: **Source-only** means the current implementation was inspected,
not browser-verified. **Read-verified** means a worker reported a real read-only
database receipt for that narrow path, not a recovery outcome. **Deferred** is
not implemented by this slice. **Live-verified** means the root session reported
the particular rendered behavior below on 8080; it is not complete regression
coverage. No item below claims full product completion.

## Fifty specific targets

| # | Observed omission and repair target | Status |
|---|---|---|
| 1 | Typed legacy structural comparisons disappeared; expose actual recorded shape signals. | Source-only |
| 2 | Mnemonic-frequency similarity could look like an instruction-byte hash; retain its weaker label without H-channel inflation. | Source-only |
| 3 | Zero-valued comparisons disappeared; retain executed disagreements. | Source-only |
| 4 | `_content=0` was invisible; explain absence of distinguishing content. | Live-verified |
| 5 | Competing destinations for one source were hidden; inspect the full recorded pair/run. | Source-only |
| 6 | Many sources competing for one destination were hidden; report destination collisions. | Source-only |
| 7 | Producer ambiguity sets were buried; expose bounded producer alternatives and truncation. | Source-only |
| 8 | Quarantined evidence looked like an ordinary candidate; expose a blocked state. | Source-only |
| 9 | Calling-contract/shadow evidence was not explained; expose recorded compatibility/conflict. | Source-only |
| 10 | Missing execution receipts implied unavailable tools; say execution is unknown. | Source-only |
| 11 | Shortlist uniqueness could sound target-wide; distinguish retrieval uniqueness from proof. | Source-only |
| 12 | Derived anchors looked like independent votes; expose dependency lineage. | Source-only |
| 13 | Ranking could be mistaken for identity probability or parity; state its claim boundary. | Source-only |
| 14 | Full corpus candidate COUNT delayed bounded reads; return unknown totals honestly. | Read-verified |
| 15 | Status/score sorting delayed a tiny page; use bounded cursor/indexed focused retrieval. | Read-verified |
| 16 | Flat candidates lacked a source/build grouping; group alternatives for inspection. | Live-verified |
| 17 | Excessively precise score strings hid meaning; format bounded retrieval metrics. | Source-only |
| 18 | Default focus was arbitrary; prefer permitted existing matcher/identity selections, otherwise inspect the strongest proposal without browser acceptance. | Live-verified |
| 19 | Current function did not scope review requests; use server-side project/function reads. | Live-verified |
| 20 | Loaded candidates had no immediate filter; add an explicitly page-local text filter. | Source-only |
| 21 | Decision rationale lived in nested raw receipts; show headline, recommendation and reasons directly. | Live-verified |
| 22 | Method checklists overwhelmed every row; show selected-candidate checks and one unknown-receipt summary. | Source-only |
| 23 | Source/counterpart locations were inert text; provide shared-cursor inspection callbacks. | Source-only |
| 24 | Alternatives lacked keyboard navigation; support arrows, Home and End. | Source-only |
| 25 | Manual review sounded like actual verification; describe the status-only review action precisely. | Source-only |
| 26 | Contradictory/ambiguous candidates could be advanced casually; block that browser promotion. | Live-verified |
| 27 | Batch selection could contain conflicting one-to-one assignments; disable competing batch promotion. | Source-only |
| 28 | Refresh could unlock a pending decision; retain token and selection/match-ID locks. | Source-only |
| 29 | Page snapshots and missing totals implied complete inventory; label bounded pages and unknown totals. | Source-only |
| 30 | Dense horizontal review failed small screens; add stacked responsive layout and visible focus. | Source-only |
| 31 | Review was hidden after analysis in a disclosure; mount it visibly in the analysis workspace. | Live-verified |
| 32 | One selected function did not control the review cursor; connect exact binary/address focus. | Source-only |
| 33 | Reviewing an endpoint required a separate lookup; route it through project/program ownership. | Source-only |
| 34 | Code and calls were exclusive; retain a compact call neighborhood alongside source/listing. | Source-only |
| 35 | Inspecting alternatives discarded the reference; pin the source cursor while inspecting counterparts. | Source-only |
| 36 | Review menu navigation landed at Compare top; target the correspondence-analysis anchor. | Source-only |
| 37 | Cross-build menu navigation had the same dead-end; target the same shared workspace. | Source-only |
| 38 | Listing menu incorrectly selected decompile mode; set listing explicitly. | Source-only |
| 39 | Review scope changes could leave stale page/filter interaction; reset/disable stale interaction by cursor scope. | Source-only |
| 40 | Endpoint routing relied on slug alone; prefer exact binary ID and unambiguous program binding. | Source-only |
| 41 | Counterpart-map identity rationale is still behind receipt disclosures; expose useful rationale in build lanes. | Deferred |
| 42 | Accepted/candidate map states lack distinguishing witnesses; render the relevant anchor/uncertainty inline. | Deferred |
| 43 | Empty graph instructed selecting a program even for missing evidence; distinguish unavailable context from absence. | Source-only |
| 44 | Graph read errors were discarded; expose caller/callee failures. | Source-only |
| 45 | Graph truncation flags were discarded; identify bounded neighborhoods. | Source-only |
| 46 | Array lengths implied full graph totals; label them as shown counts. | Source-only |
| 47 | Graph nodes lack shared/distinctive counterpart witnesses; recorded neighbor-identity links are implemented, but broader distinguishing evidence remains unfinished. | Deferred |
| 48 | Missing-peer map lanes did not connect directly to unresolved alternatives; remove the duplicate unknown lanes and show counterparts/proposals in the same comparison workspace. | Source-only |
| 49 | Matching stage failures remain separate from affected correspondence; surface the recorded operation/next fallback locally. | Deferred |
| 50 | Pair-level method receipts remain a separate disclosure; provide one truthful pair-level evidence strip. | Deferred |

## Evidence and limits

Backend ownership: `corpus/match_review.py` (`explain_candidate`, `_review_page`,
`list_review_scoped`) and `corpus/matching_availability.py` (`recorded_signals`,
`project_channels`). Static UI ownership: `ReviewReact`, `CallGraphView`,
`comparisonWorkspace`, `focusProjectFunction`, `inspectMatchEndpoint`, and
`jumpTo` in `corpus/dashboard/static/workbench-app.js`. The loopback read adapter
is `agentdecompile_recovery/project_api.py`; mutations still use the existing
catalog-owned exact-basis decision adapter and durable audit.

The backend worker reported: generic three-row read 622 ms; focused source read
1.387 s cold; focused destination read 78 ms for four rows; project 50-row read
3.404 s. Existing source/destination match indexes were confirmed by EXPLAIN.
These are narrow observations, not a general latency guarantee or browser proof.
The worker subsequently reported that same-snapshot basis caching reduced the
project 50-row read to 1.640 s, preserved exact tokens across scoped/unscoped
reads for three real rows, and returned HTTP 200 in 494 ms for a live scoped
four-way destination collision. These receipts do not validate UI interactions.

The root session subsequently reported a focused four-candidate live request
returning HTTP 200 in 1,094 ms, a screenshot with grouped function names and
`GetMusicVolume` visibly ambiguous with zero distinguishing content and disabled
review advancement, and no observed console errors or desktop overflow in that
inspection. The serving PID remained 1761367, with zero restarts. These support
the original six narrow Live-verified statuses, not every keyboard, mutation, scope-switch
or mobile path. A later root receipt reported 100 function rows, 34 project
memberships and no displayed alerts. This validates that narrow inventory/search
render, not every cohort, paging or graph interaction. At that earlier stage,
syntax highlighting and family-graph rendering had not yet been live-proven.
The root subsequently reported the real `GetMusicVolume` paired graph rendering
four nodes, two actual directed call arrows, zero invented neighbor-identity
links, a competing-correspondence badge and no displayed alerts. Typing the
function search returned 11 results and triggered only the lightweight
`/api/v1/projects/functions` route. This is a narrow live receipt for that graph
and search path, not positive proof of all identity alignments or peer navigation.
Later root browser observations established seven automatically selected stored
peer correspondences, a paired graph with 16 nodes and one actual recorded
neighbor-identity link, without requiring manual review decisions. These support
the narrow stored-preference behavior in target 18; they do not independently
revalidate the underlying identity. After reload, `GetDialogModel` displayed
49 source lines with computed `pre-wrap` on both `<pre>` and `<code>` and was not
showing pinned prior source. Clicking the displayed-source download produced
the advisory filename in a browser download event; that download was deliberately
cancelled, so no saved-file contents or build were verified. Root observed no
document overflow at 390- and 1920-pixel viewport widths. Clearing the cohort
removed its graph nodes; restoration used only functions/correspondence/call
reads, not expensive background aggregation. These are particular live
interaction receipts, not universal accessibility or responsiveness coverage.
The root also reported a separate hot-reload diagnostic partial failure;
continued serving without restart does not establish that every Python edit
was admitted successfully.

Adversarial review caught two integration issues: absent focus parameters were
initially passed as zero (making project-only reads fail), and distinct-run
enumeration needed an explicit bound because many tiny SQLite seeks can evade a
VM-operation progress-handler deadline. The former was repaired in source;
the latter received an explicit 256-run/five-second bound with a named failure.
Pending-decision locking and manual-alternative focus preservation were also
strengthened during review. Runtime activation must still be corroborated by the
root session before any of these source-only statuses are upgraded.
Database-selection changes require fencing inventory binary IDs against the
review database basis; a fresh decision token alone is insufficient. Source
inspection now confirms expected corpus identity is checked under the selection
guard, response membership/focus is validated, stale rows are hidden synchronously
and confirmations are scope-bound. Cohort exclusion of the current function
now suppresses the out-of-cohort fallback focus and labels the inspected function
as outside the cohort. This repair was inspected in source, not browser-proven.
Review of the later event-driven function-query integration also identified that
explicit project refresh must invalidate an equal database/member/query key,
and that repeated Search submissions need an intentional refresh mechanism.
These refresh repairs are now source-inspected: the request key includes
`corpusRevision` and an explicit `functionRefresh`, equal Search submissions
increment the latter, and replies validate the trimmed query, offset and limit.
Recorded names differing from the winning display name are visible. The
remaining minor provenance gap is a human display name matched via a different
logical alias: `matchedNames` is returned but that alias is not yet displayed.
The compact family map replaces duplicate inventory/unknown-counterpart tables;
recorded counterpart cards now sit beside source, calls and candidate review.
Their detailed identity rationale still resides in receipt disclosures, so
targets 41/42 remain Deferred. The whole-program export button now requires a
nonempty current slug equal to `detail.resolvedSlug`, live function text and a
project/program locator. No source-export job was launched or verified here.
Root subsequently centralized focused-address equality across graph, listing
and C-source guards, accepting padded/case-varied hexadecimal strings and safe
numeric addresses. Source `<code>`/token spans now inherit their parent's
preserved whitespace instead of collapsing its real line breaks. This is
source-reviewed repair; the remaining assembly fallback equality was reported
and the root subsequently confirmed it now uses the same normalization. The
later browser download-event receipt above does not imply source-build proof.
The subsequent comparison rewrite removes the duplicate counterpart-card table
and puts paired calls before source, side-by-side on sufficiently wide screens.
`list_correspondence_scoped` provides installed identity-only records and
permitted stored matcher selections, not just unresolved review candidates.
Review controls accept only current `review` rows with a decision token;
inspection of an installed mapping is not a mutation. No focused function means
no correspondence read, not a fallback global queue.

Latest source-review follow-ups: peer tabs must identify the endpoint opposite
the focused function, including reverse-direction stored rows; keying every
peer by destination collapses those rows onto the focused build. Paired graph
responses should retain the exact membership fence used by other scoped reads.
Locally blocked/nonunique identities are excluded from graph links. The backend
owner subsequently applied the bounded stored-lineage gate to graph centers and
neighbors before creating cross-build links; this repair is source-inspected,
not separately live-proven. The root subsequently repaired reverse-peer
navigation using the endpoint opposite the focused function and added exact
response-membership validation; both were source-inspected. Central paired-graph
identity links render only for the backend's lineage-gated `recorded-identity`
relation, and node highlighting uses only displayed real neighbor links plus
that central relation. The footer counts neighbor links separately. These later
additions have no separate browser receipt in this audit.

The family map now also receives typed stored-identity relationship observations
from the project's pinned read snapshot. Source review confirms at most 256
donor identities per binary, 4,096 examined peer rows per donor binary and two
distinct logical witnesses per build pair, with a five-second local budget and
explicit sampled/partial/unknown-total metadata. Both endpoint-to-identity and
identity-to-endpoint membership must be unique and their stored lineage must
pass the existing gate. The caller's read deadline is restored; a final corpus
basis/selection mismatch clears builds, relationships and usable corpus identity.
The worker reported a real read-only 27-binary cohort in 238 ms, 68 observed pair
edges and 189 validated endpoint bindings. This is a bounded observation receipt,
not a total match count or proof that the displayed source is exact. A subsequent
worker warm read reported 61 ms with the same 68 edges/189 validated bindings.
The final helper caps SQL-projected evidence at 8,193 characters and rejects
records above the 8,192-character admission limit or malformed/nonobject JSON,
marking the sample partial instead of treating invalid provenance as empty.

Family projection omits ambiguous project memberships, deduplicates build pairs,
renders sampled identity links dashed and labels their count as a lower bound.
An overlapping external accepted-run receipt retains its own count/path; the
sample is not added to that count and no receipt path is invented. The central
hub is explicitly the most connected build in this observed snapshot, not a
proven corpus-wide optimum. Overlapping sampled witnesses now appear separately
beside the external receipt, with binary IDs, logical identity, addresses and
methods, explicitly excluded from its accepted-match count.

Final root live receipts: family rendering showed 17 nodes and 68 observed edges;
390- and 1,920-pixel viewports had document widths of 390 and 1,920 respectively
and no displayed alerts. `GetDialogModel` showed 16 paired-call nodes, 14 real
call arrows, one center-identity link, one neighbor-identity link and four
corresponding highlighted nodes; its source remained 49 lines with `pre-wrap`,
not pinned prior source. These establish the particular rendered views, not
every graph path, underlying identity's correctness or fresh source parity.
Final source hashes reviewed were `match_review.py`
`61c5afd030414c01558042dd38b33dd321cc2c13c206c21b469ab2e326f7d430`
and `workflow.py`
`7b48bed5d59c29295ccee3ef7c80e0b307a6a774e69e23d0c5f6d86de63f7fa0`.
No additional production edits or application mutations were made by the auditor.
Root's final health receipt reports the four changed Python owners
`workflow.py`, `project_universe.py`, `match_review.py` and `project_api.py` as
applied, with each current source SHA equal to its applied SHA. PID 1761367
remained unchanged with zero restarts. Root also reported scoped whitespace
diff checks and JavaScript syntax checks passing. These receipts establish
admission of those owners, not resolution of the separate server-diagnostic
quarantine or a guarantee that arbitrary future edits reload successfully.

## Automation remains incomplete

The normal automatic correspondence path already exists:
`dashboard/preparation.py` dispatches `corpus.match-pair`, which runs
`propagate.run_pair` and `match_store.match_binaries`. Unique authentic/exact
anchors feed the automatic caller/callee-neighbor fixpoint; subsequent strong
seeds can propagate further. `persist_status` preserves the confidence and
ambiguity gates. Preparation subsequently invokes `workflow.merge_evidence`
automatically for permitted `auto`/`verify` one-to-one rows. Manual browser
review is therefore not a required step for safe automatic identity binding.
Structural identity is still not matching C or whole-image parity.

`dashboard/preparation.py` ingests BSim signatures before its matching dispatch,
but does not call `match_store.query_bsim_pair`; `_fuse_bsim` can consequently
report `bsim_pair_not_queried`. Indexing is not pair evidence. Optional BinDiff
and emulation residue paths still report `no_pairwise_bindiff_adapter` and
`residue_path_not_configured`. Cheap stored-feature matching should not wait
for optional expensive similarity preparation. This slice explains those limits;
it does not claim to have implemented or run those missing automation paths.
The bounded improvement order is cheap stored-feature comparison and allowed
binding first, then catalog/resource-admitted BSim queries for unresolved pairs,
then incremental fusion/propagation and binding. Expensive optional methods
must not block the cheap lane or imply that a missing receipt is an installation
failure.

Adversarial review found that `workflow.merge_evidence` skipped component
conflicts without quarantining their graph-dependent descendants, and that its
score-only ordering lacked a deterministic tie-break. The backend owner replaced
that resolution with `_merge_identity_components`, sharing the existing
dependency token/identity gate and rebuilding components until no new
quarantines remain. Existing logical memberships outside the proposed component
are included, existing identities are preserved and ordering is deterministic.
Independent execution of the actual helper in memory observed: a conflicting
seed discovered after its higher-scoring descendant left zero nontrivial groups
and rejected the seed plus two dependency generations; reversed input produced
the same rejection result; a valid chain retained one three-node component;
an already-occupied peer outside the candidate component was rejected. No real
database mutation, filesystem test or job was performed. This supports only
those in-memory cases, not live binding proof. Historical already-installed
unsafe identity groups are not automatically retracted or fresh-proven by this
repair; preservation-aware invalidation remains separate work.

The whole-image compiler/objdiff terminal acceptance, source-download variants,
complete multi-build relationship layout and wider Ghidra-level capability
coverage remain separate unfinished work. Fifty audit targets are not fifty
completed capabilities.

## Paired-call workspace interaction receipt

The static 8080 comparison now aligns recorded caller/callee identities before
bounding the visible neighborhood. Unpaired nodes are not connected across builds.
Distinct call ports and hover/keyboard-focus tracing distinguish actual calls from
the dashed cross-build identity links. Zoom, fit and center controls operate on
the graph viewport. Provisional centers use dashed amber frames and a triangle;
peer choices and the correspondence selector consistently distinguish recorded,
provisional, competing and conflicting evidence. The evidence badge opens a
keyboard/touch-accessible, viewport-clamped explanation rather than a metrics card.

Optional inspection choices persist in browser-local storage, bounded to 128
scopes, with corpus identity, selected membership, focused function, concrete
endpoints and current decision token checks. A missing or changed choice falls
back to the automatic choice in the loaded bounded snapshot. Reset to automatic
uses the same ranked choice and follows its source cursor. This is an inspection
preference, not a committed identity correction or an operator approval gate for
automatic matching. Durable identity correction/invalidation remains unfinished.

Playwright CLI observed the real K1 GOG `GetDialogModel` cursor: seven recorded
peer mappings, one provisional AmazonGames proposal, 16 displayed graph nodes,
one aligned neighbor pair and one center identity link. Keyboard focus traced
both incident call edges without dimming their centers. The provisional proposal
rendered two marked centers. Its inspection choice survived snapshot refresh and
page reload; reset restored the ARM64 correspondence and captured source at
`0x54b064`. The badge explanation stayed inside a 390-pixel viewport. These are
bounded browser observations, not proof of every graph or match decision.

Ordinary `function_detail` reads now preserve cached/stored source and existing
request status without enqueuing acquisition. Explicit acquisition remains a
catalog/pipeline operation. Browser reload, function selection, counterpart
inspection, preference refresh and reset retained the same 1,562 job IDs with
zero new jobs. The serving PID remained 1761367; `/health` reported the current
workbench source/applied SHA-256 as
`1314a583b8cf6d6517d0ba22aff7411d65f9ddb438a66ea49c4175d906639987`.
Existing 56 queued jobs and retained reservations were untouched. No filesystem
tests, recovery builds, server restart or whole-image acceptance occurred.
