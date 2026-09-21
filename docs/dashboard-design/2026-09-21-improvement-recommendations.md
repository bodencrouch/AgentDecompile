# AgentDecompile — improvement recommendations (concurrency + navigation)

Date: 2026-09-21
Status: read-only audit + recommendations. No code changed. Every item is
evidence-anchored to file:line in the runtime tree
`/home/brunner56/agentdecompile-nvme/src/agentdecompile_recovery/` (abbreviated
`REC/`; dashboard `DASH/ = REC/corpus/dashboard/`).
Companion: [`2026-09-21-consolidated-design-plan.md`](2026-09-21-consolidated-design-plan.md).

## The one lever

Both questions the user asked — "run more concurrently?" and "fewer clicks by
unifying pages?" — reduce to the same underlying fix: **arbitrate on real
owner/lock state at the finest genuine resource boundary, not on coarse caution.**
Admission today keys off two hardcoded name-sets, never real ownership
(`DASH/actions/jobs.py:379`; `mutating = command in _DANGER_CMDS`,
`REC/corpus/introspect.py:128-129,36-39`) — so `corpus.ghidra-bulk` advertises
`mutating:false` while it writes compile receipts and recovered source. That coarse
signal is why locks and page boundaries are conservative. Fixing it (P0 below)
unblocks the gated concurrency and makes page-collapse safe from wrong-context
writes. **But the highest-leverage concurrency wins do not need it** — they act on
resources that are already disjoint today.

Confirmed substrate: the store is **SQLite in WAL mode**, `busy_timeout=30000`
(`REC/corpus/store.py:17,166-167`) — unlimited concurrent readers, one writer,
contention absorbed by the timeout. Ghidra program mutation is already correctly
keyed per-program (`ghidra_lock_key`, `DASH/actions/jobs.py:1054-1056`).

---

## Part A — Recovery pipeline concurrency

### Safe now (disjoint resources today; no owner-arbitration needed)

**C1 · Lane the global worker cap.** `MAX_CONCURRENT = 4`
(`DASH/actions/jobs.py:35`, enforced `:369`) is one counter for *every* job. The
four long lanes (`ghidra-bulk`, `verify*`, `cross-place`, `permuter` — `_LONG_CORPUS`,
`REC/corpus/introspect.py:20-30`) saturate all four slots, after which cached
reads / index queries / searches queue — the class STRATEGY says always overlaps.
Fix: reserve slots for `not action.long_running` (the flag already exists on
`ActionSpec`), or cap by resource class instead of one `self._running`. High
leverage, high safety.

**C2 · Per-WINEPREFIX compile pool for `ghidra-bulk`; raise `--workers`.** The
compile pool is capped at 2 solely because Wine is shared —
`--workers default=2`, comment "Wine is shared; 2 is the safe default"
(`REC/corpus/ghidra_bulk.py:1463-1464`). Object outputs are already disjoint
(`g_{entry_hex}.obj`, `:1306-1307`) and `_run_cl` calls `subprocess.run([...])`
with **no `env=`** (`:986-988`), so all workers inherit one prefix.
`compile-msvc71.sh:40` already honors a per-call `WINEPREFIX`, so pass
`env={**os.environ, "WINEPREFIX": prefix[worker]}` and prewarm N prefixes — a
change in `_run_cl` only, no script edit. **This is the throughput core**
(24k+ functions).

**C3 · Parallelize `_compile_snapshot_c`.** The `corpus.run` compile path is a
plain nested `for binary / for row` loop calling `compile_unit` one at a time
(`REC/pipeline.py:342-389`), native `cc`, disjoint `{binary_id}_{name}.o` outputs,
no shared mutable state. Wrap in a `ThreadPoolExecutor.map` (mirroring
`ghidra_bulk`); collect rows after. Also overlaps the network-bound LLM-cleanup
calls inside. Cleanest safe win.

### Gated (need the finer-ownership work first)

**C4 · Parallelize pairwise compare in `bind_store_cascade`; keep the single bind
serial.** Today `REC/pipeline.py:87-104` runs `run_pair` sequentially on one shared
connection. Distinct directed pairs are independent — the dashboard already
overlaps this exact granularity (`match_pair_lock_key`, `DASH/actions/jobs.py:1045-1051`)
and each pair writes distinct `match` rows (`REC/corpus/propagate.py:112-117`), safe
under WAL. Fix: pool the pairs, each with its own read connection, then do the one
serialized `bind_identities` + commit. Needs the candidate/read vs bind/write
separation made explicit.

**C5 · Re-key `corpus.apply-stabs` per `(db, binary-id)`.** All seven
`IDENTITY_WRITERS` mutually exclude on the whole DB path (`identity_lock_key`,
`DASH/actions/jobs.py:1035-1042,370-378`). Six of them genuinely scan-then-rewrite
the global `logical_id` namespace and must keep the DB-wide lock. But
`corpus.apply-stabs` writes STABS names for **one** binary (`--binary-id`,
`REC/cli.py:168-171`) and does not need it. Split out an apply-stabs lock key —
after confirming no incidental global-table touch.

**C6 · Scale `verify_workers` (objdiff).** objdiff runs Node on isolated COFF pairs
with no shared state (`REC/corpus/objdiff_check.py:39-42`); the orchestrator caps it
at 2 (`REC/corpus/recovery_orchestrator.py:101`). Raise it — but only after C2,
since the verify compile step may reuse the same single Wine prefix.

### Do not parallelize (real shared resource named)

- **Global identity bind/commit** — `bind_identities` / `merge-parts` /
  `propagate-source` scan-then-rewrite the shared `logical_id` namespace on the
  single SQLite writer (`REC/corpus/propagate.py:142-222`). Keep the whole-DB lock.
- **Multi-binary cross-place output-tree race** — `cross_place.place_one` does a
  lock-free read-then-write to a **shared sibling tree**
  `out_root/dst_prog/…_{dst_hex}.c` (`REC/corpus/cross_place.py:46-52,70-77`). Two
  orchestrators cross-placing onto a sibling bound to the same `logical_id` race on
  one path. Cross-binary fan-out must gate on disjoint destination trees or a
  per-destination-program lock — a *fix-first* item, not a free win.
- **One live Ghidra program / one live runtime target** — already correctly
  serialized; do not loosen.

Note: the process-level orchestrator already runs 7 watcher lanes per binary as
separate subprocesses (`REC/corpus/recovery_orchestrator.py`) — genuine concurrency
exists; the coarseness is in dashboard job admission (C1) and two in-process compile
loops (C2, C3). There is **no supervisor-level cross-binary fan-out** today; adding
one depends on the cross-place fix above.

---

## Part B — Navigation / page unification (fewer clicks)

The static 8080 workbench is already ~90% "one page": 23 surfaces in one SPA
(`DASH/static/workbench-app.js:41-63`) with context-preserving in-place tab switches
(`setCenterTab` + `scrollToSurface`, `:3762-3769`, `:3147-3149`), and every legacy
browse route is already a 302 redirect into `/dashboard?window=wb-*`
(`DASH/router.py:212-253,793-840`). The remaining work is folding the last separate
pages and bringing **React 5174 to parity**.

**N1 · Parse the static surface vocab in React `navigation.ts` (highest ROI, small).**
`readRoute` (`DASH/frontend/src/workstation/navigation.ts:6-16`) ignores
`window=wb-*` and the `BROWSE_ANCHOR_WINDOW` hash anchors, so every static→React
link lands on the fallback tab. Map `wb-fnbrowse / wb-review / wb-logical / wb-graph
/ wb-corpus …` onto the React tab enum (mirror `DASH/router.py:212-218`). (Correction
to an earlier premise: snake_case `binary_hash`/`function_id` are emitted nowhere;
the genuinely-unparsed vocab is the `window=` / hash-anchor surface selector.)

**N2 · Compose `<CodeBrowser>` into the mounted React shell — the #1 correctness
gap.** `AnalysisView.tsx:5` imports only the `useTool` hook; the real synchronized
listing `<CodeBrowser>` renders only in the **dead, unmounted** `App.tsx:1015`, so
Disassembly/Decompiler in the live shell are flat `SourceEditor` text
(`AnalysisView.tsx:29`). Swap that branch for the existing CodeBrowser — this is
**wiring, not new build** — to get the continuous navigable Listing + shared
listing↔decompiler back/forward the design plan calls the highest-value missing
piece.

**N3 · Add a corpus-first Compare / counterparts surface in React.** Selection
already carries `logicalId` (`navigation.ts:8`) but nothing renders siblings; Open
is flat-by-binary (`WorkstationApp.tsx:194`). Add a Compare view keyed on
`logicalId` (static `wb-compare-table`, `workbench-app.js:981`, is the reference
shape). Turns "function → cross-build counterparts" from unreachable in React into
one tab switch — the design plan's "Compare is a fundamental workspace interaction."

**N4 · Collapse the last three separate HTML pages to redirects.** `/atlas`,
`/report`, `/dashboard/explorer` are still full-page documents
(`REC/unified_pages.py:103-144`; `DASH/router.py:128-135`) whose top-nav hops unload
the SPA and its selection. Replace the `HTMLResponse(render_*())` handlers with the
existing `_workbench_redirect` pattern already used by `/dashboard/review`
(`DASH/router.py:826-828`) → into `wb-atlas` / `wb-report` / `wb-sidebar`. Removes
three context-losing navigations and demotes the separate top-nav bar as a primary
switcher.

**N5 · Delete/quarantine the dead React roots.** `App.tsx`, `AtlasApp.tsx`,
`AtlasAnalysis.tsx` are unmounted (`main.tsx:6` renders only `WorkstationApp`); they
strand `CodeBrowser` and `Surfaces` and create "which surface is real?" ambiguity.
Remove after N2 lands. (Note: there is **no** duplicate Functions list in either
mounted shell — that rule is already satisfied.)

**Keep separate (correct as-is):** `/docs` (Swagger API contract);
`/dashboard/settings/notifications` (config + write-gated Discord webhook secret,
`DASH/router.py:137-171`); all JSON/`/api/*`/fragment endpoints; and the deliberate
static-8080 vs React-5174 delivery split — unify *within* each surface, align their
query vocab (N1), do not merge the two.

---

## Part C — The shared prerequisite

**P0 · Admission arbitrates on real owner/lock state.** Replace the two-name-set
admission (`mutates_ghidra` off `GHIDRA_MUTATE`/backend, `DASH/actions/jobs.py:379`;
`mutating` off `_DANGER_CMDS`, `REC/corpus/introspect.py:128-129,36-39`) with real
backend owner/lock/resource-claim arbitration. This is the prerequisite the design
plan already names for pause/resume (drain-not-kill) and for the finer locks in C4/C5.

**P0b · Selection-scoped request invalidation in the merged views.** As Compare /
Review / Relationships collapse into the one shared-entity workspace (N2/N3), the
mutation-context guard — not the page boundary — becomes load-bearing. "Selection
changes invalidate obsolete requests and never silently choose another target," and
Review's accept/reject is a hard-serial identity write (bind/accept against the
candidate pool), not a free read. Unify the *reading*; keep each build's concrete
program/`logical_id` distinct for any *write*.

---

## Suggested sequence

1. **C1, C2, C3, N1, N2** — safe now, no prerequisite, highest leverage (throughput
   core + React reaches usable parity).
2. **P0** (real-ownership admission) — unblocks the rest and hardens pause/resume.
3. **C4, C5, C6, N3, N4, N5** — the finer locks, cross-binary fan-out (with the
   cross-place output-tree fix), and the page collapses that ride P0/P0b.

Operational guard: the canonical AGENTS.md/STRATEGY constraints for the active
recovery mission (no 5174 start, no server restart, in-process reload only, no
filesystem test suites) still bind. These are code-shape changes; land them under
those guards, not by starting new services during live recovery.
</content>
