# KotORXID dashboard capability inventory

Date: 2026-09-20  
Purpose: preserve the useful KotORXID interaction surface while redesigning the existing AgentDecompile workbench on port 8080.  
Claim boundary: this is a read-only source inventory. Source presence and historical dogfood receipts do not establish the current live state or acceptance of the 8080 deployment.

## Operating boundary

The canonical `AGENTS.md` makes AgentDecompile the only active recovery checkout and treats the KotORXID repository as a read-only donor. Live operation must use the existing 8080 workbench and `GET /api/v1/actions`; it must not start an alternate dashboard, restart the server, invoke `systemctl`, or duplicate recovery work.

Consequently, this redesign should port KotORXID's analysis semantics and interaction contracts into the existing 8080 application. It should not transplant the donor's standard-library HTTP server, process lifecycle, ports, or obsolete Atlas link.

## Source map

The donor is `/home/brunner56/biodecompwarehouse/kotorxid`.

There are no first-party standalone HTML documents in the donor application. HTML is rendered by Python:

- `scripts/dashboard.py` — HTTP dispatch, application shell, overview, drill-down routing, artifact policy, inline CSS, and inline progressive-enhancement JavaScript.
- `scripts/panels/*.py` — domain renderers and data collection.
- `scripts/dashboard_app/models.py` — typed entity references.
- `scripts/dashboard_app/routes.py` — canonical URL builders and compatibility parsers.
- `scripts/dashboard_app/responses.py` — response helpers.
- `scripts/static/dashboard.css` — external responsive/accessibility styling.
- `scripts/static/dashboard.js` — external accessibility and navigation enhancement.

The only other HTML found under the donor outside generated/vendor trees was a Visual C++ toolkit `README.htm`; it is not part of the dashboard.

The documents under `docs/dashboard-design/` and `docs/plans/2026-08-24-0136-feat-binary-analysis-workspace-plan.md` are design history and proposals, not executable UI. Several describe the older implementation that replaced the whole page every five seconds. The current donor patches individual sections and lazy-loads panels instead.

## Implemented routes and user workflows

### Application shell and navigation

The shell is server-rendered with a responsive viewport, title, inline and external styles, skip link, `main` landmark, external enhancement script, and inline live-update script (`scripts/dashboard.py:1083-1099`). Primary navigation links Overview, Builds, Functions, Logical functions, Recovery, Review, Relationships, and Operations (`scripts/dashboard.py:642-667`).

`Handler.do_GET` implements the following surface (`scripts/dashboard.py:2416-2467`):

| Route | Implemented purpose |
|---|---|
| `/` | Live corpus overview |
| `/builds` | Generic build comparison |
| `/binary/<slug>` | One build and its measured state |
| `/functions` | Corpus-wide or build-scoped concrete-function search |
| `/function/<slug>/<addr>` | Concrete-function evidence workspace |
| `/logical` | Searchable logical-identity index |
| `/logical/<id>` | Cross-build logical-identity workspace |
| `/recovery`, `/report` | Recovery summary and recent verified artifacts |
| `/review` | Candidate identity/reuse review worklist |
| `/graph` | Bounded local call graph and relationship view |
| `/operations` | Processes and logs |
| `/artifact` | Confined text-evidence browser/viewer |
| `/evidence/database` | Database metadata/query summary without raw download |
| `/fragment` | Overview refresh fragment |
| `/panel` | Lazy domain-panel fragment |
| `/healthz` | Plain health response |

Path-identity dispatch validates build, function, and logical-identity segments before rendering (`scripts/dashboard.py:2390-2407`).

### Overview and pipeline state

The donor deliberately separates readable C from byte identity and refuses to sum those properties (`scripts/dashboard.py:2-24`). The overview presents an honest headline, pipeline rail, aligned per-build bars, current priority, and a folded group of detailed domain panels (`scripts/dashboard.py:584-641`, `776-876`, `947-1058`).

Mounted subjects are defined at `scripts/dashboard.py:205-255`:

- corpus and per-build step ladders;
- mission contract and filesystem evidence;
- binary inventory and scope;
- cross-build matching;
- readable-source recovery;
- rebuild/round-trip proof;
- merged Ghidra knowledge;
- STABS and original source names;
- running processes and recent logs.

The pipeline collector reads the corpus database plus export, STABS, coverage, queue, package, and reconstruction artifacts (`scripts/panels/steps.py:241-356`). It derives corpus and per-binary stages (`scripts/panels/steps.py:377-818`) and renders both overview and per-build ladders (`scripts/panels/steps.py:840-959`).

### Builds

The builds index is data-driven rather than KotOR-specific. It lists scope, platform, architecture, format, function/name counts, duplicate copies, and canonical status (`scripts/dashboard.py:1644-1675`).

Build details are rendered at `scripts/dashboard.py:1601-1625`. They combine database metadata, evidence links, filtered function counts, graph navigation, and the per-build pipeline ladder. The shared binary lookup reads the `binary` table and caches a bounded 24-row-style snapshot for 30 seconds (`scripts/dashboard.py:1319-1348`).

The richer binary panel visualizes function coverage, duplicate relationships, exclusions, and inventory artifacts (`scripts/panels/binaries.py:108-352`).

### Concrete functions

The functions workspace supports both corpus-wide and selected-build views. It provides filter chips, address and name search, scoped SQL filtering, result paging, and links from each result to the concrete function, logical identity, and call graph (`scripts/panels/entities.py:204-248`, `337-788`).

The concrete-function workspace (`scripts/panels/entities.py:861-1051`) exposes:

- build and exact address;
- resolved/raw naming and provenance;
- logical-identity membership and confidence;
- cross-build sibling instances;
- Ghidra knowledge and pseudocode where available;
- recovery evidence;
- caller/callee navigation.

Function routes are mounted at `scripts/dashboard.py:1626-1642` and `1675-1704`.

### Logical identities and cross-build reuse

Logical identities are first-class. The index performs a name or canonical-key search and pages by logical ID (`scripts/dashboard.py:1819-1866`). A logical detail page links directly to its graph (`scripts/dashboard.py:1805-1816`).

The entity renderer lists members across builds, names and tiers, confidence/provenance, concrete-function and graph links, recovery state, and possible source-transfer candidates (`scripts/panels/entities.py:1052-1230`).

Cross-corpus summaries include logical-function coverage, identity methods and confidence, database/file match evidence, BSim status and logs, reuse summaries, and dense relationship matrices (`scripts/panels/crossmatch.py:203-798`).

### Relationships and call graphs

The graph view supports focus by canonical build slug and address, legacy numeric binary ID, or logical ID. Canonical URL builders are in `scripts/dashboard_app/routes.py:40-89`; compatibility parsing and conflict checks are in `scripts/dashboard_app/routes.py:131-162`.

The call-graph panel provides:

- build/address/name selection;
- depth one or two;
- bounded caller/callee queries;
- node and edge rendering;
- click-to-recenter links;
- cross-build sibling relationships;
- explicit truncation/omission notes;
- a structured-list fallback for accessibility.

Evidence: `scripts/panels/callgraph.py:208-375`, `433-678`, `757-976`, and `1000-1045`.

### Recovery and rebuild proof

The recovery report aggregates artifact state and shows recent byte-identical recovered rows without treating copied bytes or assembly wrappers as recovered C (`scripts/dashboard.py:1705-1791`).

The recovery panel independently computes `real_c` and `byte_exact`, and reads chosen-run JSON, compile tallies, and experiment manifests (`scripts/panels/recovery.py:164-177`, `177-456`).

The round-trip panel consumes image reconstruction receipts, universal coverage, separate assembly and C/C++ package manifests, reconstructed-build manifests, and bounded log tails (`scripts/panels/roundtrip.py:136-443`). These are distinct evidence classes; the UI should preserve that separation.

### Review queue

`/review` is a paged, read-only worklist (`scripts/dashboard.py:1794-1802`). The underlying renderer distinguishes tiers and links source and destination concrete functions (`scripts/panels/entities.py:1231-1350`). No accept, reject, edit, or other mutation control was found in the donor surface.

### Evidence and traceability

The artifact viewer restricts access to named evidence roots, text-like suffixes, a maximum file size, and a maximum directory entry count (`scripts/dashboard.py:92-113`, `1193-1308`). Database evidence uses a metadata/query-summary page rather than offering the SQLite file (`scripts/dashboard.py:542-579`).

The mission panel reads `.mission/directives.json`, resolves declared evidence, and visibly reports missing paths (`scripts/panels/directives.py:12-70`).

The database helper opens SQLite with URI `mode=ro` and a timeout (`scripts/panels/common.py:299-315`). Shared helpers also provide bounded JSON/JSONL reads, relative age, local TCP probes, process discovery, and bounded log tails (`scripts/panels/common.py:219-252`, `319-351`).

### Ghidra knowledge and original-symbol evidence

The knowledge panel reports server visibility, knowledge-database scale, per-program coverage, live cached records, and missing-program gaps. It reads the separate `ghidra_knowledge.sqlite` store (`scripts/panels/knowledge.py:90-544`).

The STABS panel covers extraction indexes, record types, files, provenance, logical-identity reach, top original source paths, and symbol-table storage (`scripts/panels/stabs.py:200-632`).

### Operations

The operations view classifies processes under the repository cwd and shows bounded recent log information (`scripts/panels/processes.py:95-290`). It is monitoring only. The donor exposes no job submission, pause, resume, shutdown, restart, or process-kill HTTP operation.

## Implemented browser behavior

The inline client at `scripts/dashboard.py:2151-2336`:

- persists disclosure, element-scroll, and window-scroll state in `sessionStorage`;
- loads opened domain panels from `/panel`;
- refreshes the overview from `/fragment`;
- replaces only changed sections by ETag;
- avoids replacing a section containing focus or a live text selection;
- pauses while the tab is hidden;
- retries failures with exponential backoff up to 60 seconds;
- periodically refreshes open lazy panels;
- leaves drill-down pages stable except for explicitly pending blocks.

The external `scripts/static/dashboard.js:1-204` adds or improves:

- skip-to-content behavior;
- responsive navigation, Escape closing, and `aria-current`;
- polite live announcements and busy state;
- keyboard-focusable regions for horizontally scrollable tables;
- unique accessible names for repeated graph actions.

The core disclosure interaction uses native `<details>`, so it remains useful without JavaScript.

## Existing 8080 capabilities to reuse

Historical production dogfood records the canonical 8080 workbench as already providing a Ghidra-style tool strip, binary dock, windowed function list, inspector, typed `/docs` operations, shared job runner, path registration, copy-in upload, confirm-remove, role/label editing, stage bars, and same-process `/mcp` (`docs/dogfood-reports/2026-08-31-feat-corpus-kotorxid-library-dogfood.md:3-18`, `57-66`). These receipts are historical, so current source and runtime still require read-only corroboration before making a current claim.

The same report says the leftover port 5173 is unused and that `/atlas` and `/docs` on 8080 are the product links (`docs/dogfood-reports/2026-08-31-feat-corpus-kotorxid-library-dogfood.md:101-105`). The donor's generated `:5173` Atlas link (`scripts/dashboard.py:667`, `2155-2158`) must not be ported.

The canonical outcome ledger describes the interaction obligations whose acceptance remains unreassessed: corpus and per-binary ladders, actionable counts, one-click function/sibling/identity navigation, subject-grouped visualizations, raw output on demand, source and age on figures, honest real-C versus byte-exact counts, and preserved selection/deep-link/refresh state (`docs/PROTOTYPE_OUTCOMES.md:24-26`).

## Important implementation gaps

1. **No global search or unified command surface.** Search exists inside function, logical-identity, and graph pages, but the donor does not implement the plan's global search or context tabs (`docs/plans/2026-08-24-0136-feat-binary-analysis-workspace-plan.md:159-171`).
2. **No donor mutation API.** The donor handler implements GET only. Binary management, job submission, recovery continuation, review decisions, and safe operational actions must use the existing 8080 catalog and job infrastructure.
3. **No dedicated large-decompilation endpoint was found.** The plan calls for on-demand source loading with truncation metadata (`docs/plans/2026-08-24-0136-feat-binary-analysis-workspace-plan.md:186-197`), while the current function renderer can include Ghidra C in the page.
4. **Review is observational.** Candidate rows have no decision controls. Any decision workflow must be catalog-backed, authorized, auditable, and separated from merely viewing a candidate.
5. **Operations is observational.** Do not add ad hoc process controls. Existing 8080 ownership, admission, and job-state contracts remain authoritative.
6. **Graph interaction is deliberately bounded but basic.** Search, recentering, depth, links, and accessible fallback exist; no client pan/zoom or interactive layout controls were found.
7. **Several design-document features remain proposals.** Rich input fingerprints, persisted first-seen-broken evidence, filterable directive workspaces, comprehensive freshness tiers, and a visible dashboard I/O budget appear in `docs/dashboard-design/` but were not found as complete executable behavior.
8. **The full metric contract is not mechanically enforced.** The plan requires entity, scope, measure, numerator, denominator, freshness, and evidence before a percentage renders (`docs/plans/2026-08-24-0136-feat-binary-analysis-workspace-plan.md:118-127`). Individual panels follow much of this discipline, but there is no single enforced metric object across the donor.
9. **Source does not prove complete or indexed sets.** The plan requires count-to-set reconciliation and query-plan gates (`docs/plans/2026-08-24-0136-feat-binary-analysis-workspace-plan.md:145-157`). Those properties need current data and query evidence before claims are made.
10. **Live product acceptance remains open.** The plan's link crawl, state coverage, responsive/a11y screenshots, and real-port verification (`docs/plans/2026-08-24-0136-feat-binary-analysis-workspace-plan.md:212-223`) and the canonical outcome ledger both explicitly leave acceptance incomplete or unreassessed.
11. **The donor has duplicated shell concerns.** It carries large inline CSS/JS plus external assets and creates skip-link behavior in both the server shell and external JS. The 8080 redesign should reuse its established design system and components while preserving semantic behavior, not copy the donor markup wholesale.

## Porting recommendation

Use the existing 8080 workbench as the sole shell and operational boundary. Reuse existing binary, function, inspector, action-catalog, jobs, `/docs`, and `/mcp` components first. Add only the missing read-only KotORXID capabilities:

- honest overview and per-build step ladders;
- scoped, actionable metric-to-set navigation;
- logical-identity and cross-build sibling workspaces;
- bounded graph plus structured fallback;
- recovery, rebuild, knowledge, STABS, and evidence views;
- source/freshness provenance and explicit stale, missing, failed, and excluded states;
- stable deep links and preserved navigation/selection state.

Do not bring over the donor server, alternate ports, its 5173 link, process discovery as an authority mechanism, or any implied recovery control. Mutating actions belong behind the existing 8080 action catalog, ownership checks, and durable job state.
