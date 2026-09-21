# User requirements ledger — everything the user asked for, in one place

Date: 2026-09-21. Scope: every user-authored directive relevant to the design of the
recovery pipeline, the frontends, and the cross-build memory-mod / code-injection
workflows — from this session and from prior conversations (Codex, Cursor, Claude,
Copilot, chat archive; see the source ledger at the end). This file is the input to the
goal statement and the acceptance basis for
[`2026-09-21-portable-signatures-codecaves-generic-plan.md`](2026-09-21-portable-signatures-codecaves-generic-plan.md).

Rendering rule: the user's original messages name specific products, binaries and
projects. Per the user's own later directive, **no product, binary or project name
appears in any AgentDecompile document**, so each directive below is rendered
generically ("the current corpus", "another program with several versions", "sibling
builds of one engine family"). Verbatim wording is in the cited transcripts. Directives
are grouped by theme; later directives supersede earlier ones where they conflict, and
the supersession is stated.

## 1. The product and its bar

- **The bar is a level above conventional RE tools.** Those give a human *analysis data*
  to infer from; this pipeline is the inference engine: it reverses as much as is
  physically possible **itself**, deterministically, and when analysis finishes there are
  **usable exports ready to go** for every workflow — not a database to query. (This
  session, 2026-09-21; Codex/Discord origin 2026-02 → 2026-06: "one tool … suggests the
  next flow to keep the agent going"; "one-shot decompile … any program.")
- **Charter (prior, standing):** work with compiled binary data as context an agent
  understands almost as seamlessly as source; no hardcoded gates or privileged funnels;
  everything authoritative to the assembly and the bytes; partial implementations always
  usable; "ground first, code second." (Vision conversations, 2026-02 → 2026-08.)
- **Exhaustive, not fast-pathed:** "I don't want a fast path — I want it to simply *be*
  fast while still comprehensive and deep"; 100% exhaustive authoritative source that
  recompiles to byte parity. (2026-07.)

## 2. The recovery pipeline (order and rules)

- **Terminal goal:** complete, semantic, corpus-wide decompilation of every in-scope
  binary into readable, buildable C/C++ whose compiled output is **byte-accurate to each
  shipped binary** — a whole-image identical rebuild, not per-function parity. (2026-08-31
  contract; STRATEGY stage 8.)
- **Stage order (do not reorder):** extract → identify → global calibration → scaffolding
  (assembly floor) → readable C → propagation (compile-gated cross-place) → targeted AI
  on leftovers → parity (objdiff) → whole-image byte identity. The user's informal
  "priorities 1–9" maps onto these eight stages; no ninth stage exists. (2026-08-31;
  2026-09-08; 2026-09-16.)
- **First priority** was getting one debug-info-bearing build to compile to a complete
  executable; second, cross-matching to the other binaries; third, byte accuracy; the rest
  follow. (2026-08-31.) **Priority-zero** (reconcile/repair on resume) must be minimal —
  "too convoluted, blocking the path to 1–8." (2026-09-16.)
- **Cross-match is compile-gated:** propagate only compiling C; a shared identity never
  authorizes copying source that hasn't compiled. Knowledge (names, comments, types,
  debug-info names) merges **bidirectionally per field**, strongest source wins; never a
  wholesale donor. Naming precedence: human → debug info → symbols → analysis names →
  placeholders. (2026-08-31; STRATEGY.)
- **Assembly is an honest intermediary floor, never counted as recovered C**; earlier
  "no assembly whatsoever" was superseded by the user's own interim exception. (2026-08-31
  → 2026-09-15.)
- **Never redo completed work**; never re-analyze a program that already has analysis;
  compile-back must never block other tasks (it is a validation loop). (2026-08-31.)
- **Run as much concurrently as ownership allows**; the user asked directly "can anything
  run more concurrently?" — with the correct answer being finer, real ownership locks,
  not coarse caution. (2026-09-21.)
- **Generic language support:** C/C++ is one supported language, not a hardcoded
  assumption. (2026-09-09.)

## 3. Cross-build unification — the memory-mod / code-injection substrate

- **Portable signatures for every function** so a function is found across **all**
  builds without absolute addresses, unifying logical functions; "ideally the signature
  should be the same for all the binaries." (2026-09-08 origin; 2026-09-21.)
- **When the surrounding call-graph/CFG is too different, point it out and display it
  properly** — never silently force a match. (2026-09-21.)
- **Auto-export codecaves + parameters/ABI**, signature-keyed and grouped so they work on
  as many builds as possible, **implementable in Lua**. "As much as physically possible,
  as organized/grouped as physically possible." (2026-09-21.)
- **Not just functions — every entity:** structures and their fields, vtables, globals,
  strings, constants, data tables, imports/exports, dispatch tables, instruction-level
  patch points — "any and all other things we could be cross-matching so we can work with
  them in our memory-mod / code-injection workflows." (2026-09-21.)
- **Structs persist across builds even when addresses don't** (the user's reference
  script for another program: a static per-build offset registry with hardcoded absolute
  roots, no fallbacks, no caching, silent zeros on failure — the anti-pattern). Therefore:
  cross-match and identify **all structs**, and **all ways to acquire data, with plenty
  of fallbacks** when a build cannot support a lookup; **idempotent / deterministic
  lookups**; functions, structures, lookup pipelines — "anything and everything relevant
  to working with the binaries in memory — unified across the binaries as comprehensively
  and exhaustively as possible." (2026-09-21.)
- **Works across different binaries *and platforms*** — sibling builds of one engine
  family and unrelated engines, formats and architectures alike. (2026-09-21.)
- **Pursue universality exhaustively:** the user rejected "coverage recorded, universality
  never asserted" as stopping early; every miss must trigger the next strategy in an
  exhaustive ladder, and the residue must be the remainder after every physically
  possible strategy — then determine feasibility honestly. (2026-09-21.)
- **Portable runtime signatures / hook-pack export** as a pipeline output, abstracted
  away from any one product and binary-agnostic. (2026-09-08.)

## 4. Determinism and engineering standard

- **Deterministic:** same inputs → byte-identical signatures, matches, caves, exports;
  "most RE tools can't achieve this but I believe we can." (2026-09-21.)
- **Widely adopted, known-to-work practices** (objdiff-class methods), with each
  practice's known issues addressed in the plan up front "so we don't create issues down
  the road." Everything relevant to the goal that must be implemented or modified must be
  in the plan. (2026-09-21.)
- **Optimal, robust, intelligent;** implement away every issue and remnant discovered;
  assign expert roles to subagents and grill them. (2026-09-21.)
- **No gaps allowed**; completely comprehensive; "are we certain my criteria is possible
  and the plan covers all the requirements?" (2026-09-21.)

## 5. Genericity and naming

- **Not specific to the current project.** The user will upload another program with many
  versions and expects signatures, caves, byte-accurate compiling source, etc.; same-engine-
  family siblings are in scope. (2026-09-21.)
- **No hardcoded product, binary or project names — anywhere in AgentDecompile, code or
  docs, "absolutely nowhere."** (2026-09-21, twice, escalating.)

## 6. Process and safety rules

- **Research first, meticulously**, across all past conversations, before designing;
  fan out subagents; collaborate; grill a prototype expert. (2026-09-21.)
- **Plan first; do not begin implementation early**; "we haven't even finished building
  the plan." Build the plan until it covers all requirements, then implement via
  **subagent-driven development**. (2026-09-21.)
- **Resume from the most comprehensive existing work; never overwrite a large amount of
  effort.** (2026-09-21.)
- **Live-recovery operational guards are lifted** ("we don't care about disrupting live
  recovery anymore"); engineering rigor (revertability, determinism, temp-store
  verification) remains. (2026-09-21.)
- Earlier "just the audit for now" applied to the concurrency/navigation optimizations
  only; the cross-build substrate is a requested capability to build. (2026-09-21.)

## 7. Frontends (context for the export/visualization surfaces)

- **Two surfaces, one backend:** a complete static workbench served by the MCP server
  (a code-browser IDE "more or less what a conventional RE GUI is"), and an optional rich
  app that "shows all the stuff that's happening in real time dynamically," designed after
  the browser-RE reference projects. Both agree on identity, jobs, mutations and proof.
  (2026-09-08; reconfirmed 2026-09-20.)
- **Draw the work, not a status report:** "a 'running' piece of text next to a spinning
  circle isn't informative — actually animate/draw what is being done." One
  start/pause/resume control; no per-stage buttons; corpus-first ("all the binaries as
  one"); one Functions surface. (2026-09-16.)
- **Feel:** dense, legible, intuitive; think desktop RE tools; ideally one page, minimal
  tabs; menu bar; resizable widgets; a bottom logging widget with jobs as a tab; no
  hardcoded list limiters; realtime function search; reduce clicks; several ways to reach
  any function; everything the CLI/MCP can do reachable from the UI; real-time crash-safe
  saving; long jobs offload and the dialog closes. (2026-08-31 → 2026-09-09.)
- The interactive frontend mockup produced this session uses illustrative sample names
  and lives outside the repo; genericize before landing.

## 8. Supersessions (later wins)

| Earlier | Current |
|---|---|
| "make it all React" | deliberate two-surface split |
| "no assembly whatsoever" | honest assembly floor, never counted as C |
| numeric bars / "Running" as feedback | draw the actual work |
| cross-match as a side panel | the organizing relationship of the workspace |
| two Functions trees | one Functions surface |
| 24-hour default budget | unlimited default, bounded per attempt |
| "priorities 1–9" as a 9-rung ladder | eight named stages; minimize priority-zero friction |
| functions-only cross-matching | every entity kind |
| "coverage recorded, universality never asserted" | exhaustive ladders; residue is what remains after every strategy |
| operational guards protecting live recovery | lifted; rigor retained |

## Source ledger

- This session's transcript (Claude, 2026-09-21) — all §3–§6 directives verbatim.
- Codex sessions: 2026-09-08 dashboard/delivery session; 2026-09-16 recovery/redesign
  session (draw-the-work, one control, priority-zero, corpus-first); 2026-09-20 handoff.
- Cursor: 2026-08-30 → 2026-09-09 sessions (the 2026-08-31 pipeline/priority contract;
  the frontend-architecture message; feel/one-page/menu-bar directives).
- Copilot: 2026-09-09 (replace the frontend design from browser-RE references).
- Claude: 2026-08 → 2026-09-13 project transcripts.
- Chat archive (Discord/Codex/Cursor, 2026-01 → 2026-08): the charter, origin and
  "one-shot decompile anything" directives.
- Consolidated earlier in `docs/FRONTEND_INTENT.md` (§11 has message-level line
  citations) and `docs/dashboard-design/2026-09-21-consolidated-design-plan.md` (§5–§7).
</content>
