# AgentDecompile — Consolidated Design Plan

Date: 2026-09-21
Status: consolidated design plan (research synthesis). Not a completion or recovery
receipt. Nothing here marks any requirement delivered.
Scope: the three axes the user asked to consolidate — the **pipeline**, the
**priority order**, and how the product should **look, feel, and behave** —
gathered from every reachable prior conversation and design doc and reconciled
into one reading.

## How to read this file

This is a distillation, not a replacement. Where a canonical document already
governs, this plan cites it and does not fork it:

- **Recovery ordering authority:** [`STRATEGY.md`](../../STRATEGY.md) (the eight
  named stages, "do not reorder").
- **Charter / intent authority:** [`VISION.md`](../../VISION.md).
- **Consolidated intent + frontend contract (2026-09-20):**
  [`FRONTEND_INTENT.md`](../FRONTEND_INTENT.md) — this plan builds on it, verifies
  it against the raw transcripts, and extends it with the design-history timeline,
  the origin quotes, and the grill-resolved control/feedback decisions below.
- **GUI spec (2026-09-20):**
  [`2026-09-20-unified-workstation-spec.md`](2026-09-20-unified-workstation-spec.md).

A prior consolidation (`FRONTEND_INTENT.md`, commit `8a89c28`, 2026-09-20 11:56)
already gathered the user's intent with a full source ledger. Independent
re-verification against the raw Codex/Cursor/Claude/Copilot transcripts found it
accurate, and found **no human design requirement decided after 2026-09-20** —
everything later is implementation-fix commits or subagent automation. So this
document's new value is: (1) the three axes pulled out cleanly and reconciled,
(2) the dated evolution/supersession history with verbatim origin quotes, and
(3) two design questions sharpened past what the docs settle — the actual-work
feedback model and the single pipeline control.

---

## 1. The product in one paragraph

Open compiled software as naturally as a source repository. Treat a project's
binaries as comparable **implementations of one shared codebase**: see packages,
resources, code, types and relationships; compare related builds; recover
understanding once and reuse eligible knowledge across every build. Browse, edit,
recover, compile, compare and inspect runtime behavior in one coherent workspace,
and **watch the actual evidence and transformations as work happens** — never a
spinner, never a statistics strip standing in for the work. Every name,
relationship, candidate, source file and proof keeps its origin and exact scope.
The immediate recovery target is the current corpus, its first target build first; the design must
generalize to another game's builds and to non-game compiled software.
(`VISION.md` §§1–7; `FRONTEND_INTENT.md` §1.)

---

## 2. The pipeline

### 2.1 Canonical stage order (recovery)

The authority is `STRATEGY.md` §"Priority ladder → Stages", implemented by the
active living plan
[`docs/plans/2026-09-08-0156-feat-recovery-pipeline-ladder-plan.md`](../plans/2026-09-08-0156-feat-recovery-pipeline-ladder-plan.md).
Eight named stages, "do not reorder":

| # | Stage | Catalog verb | What it does |
|---|---|---|---|
| 1 | **Identity** | `corpus.extract-stabs` → `corpus.match-pair` | Extract facts once; short-circuit identical images; bind `logical_id` by independent evidence channels (below). Candidate generation is not acceptance. |
| 2 | **Global calibration** | `corpus.calibrate-global` | Compiler versions, flags, ABIs, global struct layouts — before per-function recovery. |
| 3 | **Scaffolding (assembly floor)** | `corpus.workspace` | Donor workspace, one file per function, exact inline asm where no C exists yet; must link. |
| 4 | **Readable C** | `corpus.ghidra-bulk` | `ghidra-bulk` replaces asm when the C compiles; keep asm on failure. |
| 5 | **Propagation** | `corpus.cross-place` | Only after compile succeeds: place the compiling `.c` on siblings sharing the `logical_id`. |
| 6 | **Targeted AI** | `corpus.genproject` (leftovers) | Leftovers only, leaves before callers; never before stages 4–5 for functions whose Ghidra C already compiles. LLM output never creates a trusted identity edge alone. |
| 7 | **Parity** | `corpus.objdiff-check` | objdiff-0 per function when claiming verified readable C; isolated toolchain. A rebuild-validation stage, not a cross-architecture identity oracle. |
| 8 | **Whole-image byte identity (exact placement)** | — | Terminal goal: relink into a file bit-identical to the shipped image. Verify by whole-file hash, not per-function diff. Open engineering problem; core scope, not a stretch. |

Goal-capsule shorthand (`STRATEGY.md`; `CONCEPTS.md` "Corpus pipeline"):
*extract → `logical_id` → global calibration → assembly floor → compiling Ghidra C
→ cross-place → targeted AI on leftovers → objdiff last → fresh whole-image rebuild
and identity.* **Never decompile the same logical function twice. Skip a step when
its receipt or Ghidra analysis already exists.**

Identity evidence cascade (stage 1, cheap-first): authentic symbols/provenance →
unique exact / relocation-normalized hashes → rare refs / C++ metadata →
neighborhood propagation → CFG/SPP → BSim significance → ABI checks → optional
BinDiff/BinExport → optional emulation on unresolved residue. Require uniqueness
and a margin; keep ambiguity and one-to-many/split/inlined relations; quarantine
bad seeds. (`STRATEGY.md`; `FRONTEND_INTENT.md` §6.)

### 2.2 The compile-gated "cross-match" tier

The single most-repeated invariant in the whole corpus. `STRATEGY.md`
§"Corpus recovery pipeline" is the authoritative definition:

> `ghidra-bulk` → compile check → **(pass)** propagate that `.c` onto every sibling
> bound to the same `logical_id`, then byte-exact verify in order → permuter →
> LLM last; **(fail)** sanitizer/preparse helpers retry compile, then one bounded
> LLM cleanup pass on that Ghidra body, then retry.

Two hard rules: **cross-place copies only compiling C** (the assembly-floor link
receipt is *not* that gate; enforcement refuses bodies without a
`compile-receipt.json`), and **a `logical_id` bind alone never authorizes copying
types, layouts, or source** — identity binding is a separate, already-run layer.
Knowledge cross-match (labels, comments, structs/types, STABS names) runs
concurrently and is **bidirectional per field**: the strongest source for each
field wins, so a build is the donor for a *field*, not for everything. A weaker
build never overwrites a stronger one.

### 2.3 What runs concurrently vs must serialize

| Can overlap (subject to measured memory/swap + ownership) | Must serialize / isolated ownership |
|---|---|
| Browsing, searches, cached-evidence reads | Writes to the same Ghidra project/program or `logical_id` store |
| Independent extraction and indexing | Shared corpus mutation and conflict resolution |
| Field-level knowledge fusion vs source recovery when transactions don't collide | The same compiler/Wine environment or generated output tree |
| Independent compile/objdiff in distinct proven toolchains | One live game/harness target + saves + cave state |
| Runtime-reuse branch after sufficient identity/ABI evidence | Central acceptance of results and authoritative receipt/identity writes |
| Optional distributed workers on leased independent units | |

A configured worker count is not permission for overlapping writers. Resource
admission uses **actual ownership and measured memory/swap.** (`STRATEGY.md`;
`FRONTEND_INTENT.md` §6 "What can run together".)

### 2.4 Failover

The affected branch **visibly stops at its real unmet dependency while eligible
branches continue.** Show the named owner/resource/provider failure, last evidence,
chosen fallback, and retry eligibility. No silent retry storm, stale-state reset,
or server restart. (`FRONTEND_INTENT.md` §4.3, §6.)

### 2.5 The reconcile preamble ("priority zero") — reframed

Opening a known project reconciles existing program bindings, corpus records,
analysis, source and valid receipts, and **reuses valid work** before doing
anything new (`FRONTEND_INTENT.md` §4.1 F01, §6:217). This is the step the user
calls "priority 0." It is **not a ninth stage** (see §3.2).

The user reported it "too convoluted" and "causing problems getting back to
priority 1/2/…". The correct reframe (see the grill in §6.2):

- **It is a scope-of-gate error, not a serialize-vs-parallelize error.** Priority-
  zero must gate only the **mutation-admission boundary**, never read-only
  hydration or the independent safe lanes. "Read-only hydration is not the same
  thing as mutation admission" (`FRONTEND_INTENT.md` §6:265). Browsing, searches,
  cached reads and independent indexing must never wait on it.
- **It stays cheap and checkpoint-trusting.** Resume "validates identity and
  reuses only valid work"; it must not fire a heavy reconcile on every reopen
  (`FRONTEND_INTENT.md` §6:264–265: "merely selecting or reopening known material
  must not reimport/reanalyze it"). Escalate to repair only on **actually-detected
  breakage**, not as a mandatory full pass.
- **It never accretes.** "Priority-zero repair is the minimum needed to safely
  resume useful work, not a new recurring bureaucracy" (`FRONTEND_INTENT.md` §6).
- Do **not** model it as a fully concurrent lane: the reconcile-for-mutation piece
  is a genuine precondition for writes (same rule as "serialize writes to one
  Ghidra project"). It precedes *writes*, not *reads*.

### 2.6 Terminal deliverable — a live contradiction to know about

`STRATEGY.md` and the 2026-09-08 ladder plan set the terminal deliverable as a
**whole-image byte-identical rebuild** (stage 8), maintained as **two separately
measured variants**: byte-accurate C + assembly-floor (every original-byte
contribution counted) and max-C (assembly-free readable C). Never count floor
bytes as recovered C; never borrow one variant's receipt for the other.

The 2026-09-08 plan carries a **2026-09-20 reconciliation note** that supersedes
its own body: per-function objdiff parity is *necessary but not the endpoint*; the
endpoint is the two whole-image variants, and runtime reuse branches off before
whole-image recovery. **The note wins by date**, but the plan's body was left
intact as decision history — a reader hitting the plan mid-file could mistake the
superseded "objdiff-per-function endpoint" ordering for current. Flagged so the
plan can state the current endpoint unambiguously: **two whole-image variants,
per-function objdiff is a gate on the way there.**

---

## 3. Priority order

Three distinct priority axes keep getting conflated. Keeping them separate is
itself a requirement.

### 3.1 Axis A — the eight recovery stages (governing)

The §2.1 stage list is the sole recovery-ordering authority, "do not reorder"
(`STRATEGY.md`). Everything else defers to it.

### 3.2 Axis B — the user's "priorities 1–9" shorthand

Origin (verbatim, Codex D2 session 2026-09-16, restated 2026-09-20 01:00):

> "Priority 0 needs significant rework as it's causing significant problems getting
> back to priority 1/2/3/4/5/6/7/8/9 … Priority zero doesn't seem right or at least
> it's too convoluted atm."

Governing ruling (`STRATEGY.md`; `FRONTEND_INTENT.md` §9): *"The user's 'priorities
1–9' describes continuing the complete mission. This stage list has eight named
stages; no ninth stage is inferred from that shorthand."* The "1–9" counting is an
artifact of splitting *extract facts* and *`logical_id` bind* (both inside stage 1)
and of counting priority-zero as a rung. **Do not invent a ninth stage or a literal
"priority 9."** Do minimize priority-zero friction (§2.5).

The earliest priority statement (Cursor, 2026-08-31, verbatim) — coarser, and
reconciled *into* the eight stages, not competing with them:

> "First priority is getting one with stems [STABS] to compile to a complete
> executable file, second priority is cross matching to the other binaries, third
> is binary accuracy, other priorities are fourth and continuing."

### 3.3 Axis C — the P0–P5 frontend delivery roadmap

A **different axis**: what to *build in the UI/adapter layer*, not how to recover a
binary. Source:
[`docs/plans/2026-09-09-0630-feat-local-first-re-workbench-plan.md`](../plans/2026-09-09-0630-feat-local-first-re-workbench-plan.md)
(deepened 2026-09-10), itself derived from the AIO deep-research doc
([`/home/brunner56/Documents/idek.md`](file:///home/brunner56/Documents/idek.md)).

- **P0** — unified data types + capability API; React/Vite IDE shell; secure
  artifact ingestion.
- **P1** — local analysis adapter + disasm/hex/xref/CFG views + local search/index.
- **P2** — objdiff integration; Ghidra headless adapter; multi-decompiler results;
  matching-decomp workspace. *(P0–P2 = first shippable release gate.)*
- **P3** — capa/semantic findings; similarity/embeddings; APK/DEX provider;
  evidence-first AI assistant.
- **P4** — collaboration; plugin SDK; Git/CI progress.
- **P5** — dynamic mobile (Frida) provider; hardening/enterprise controls.

Two cautions the sources attach to this axis:

1. **It is not a recovery priority.** `PROTOTYPE_OUTCOMES.md` / `DELIVERY_STATUS.md`:
   these delivery IDs "track delivery dependencies, not recovery priorities.
   STRATEGY remains the sole recovery ordering authority."
2. **Its Rizin-first ordering is explicitly rejected for AgentDecompile.** The
   research DAG puts Rizin WASM at P1 and Ghidra at P2, but AgentDecompile already
   *starts* from Ghidra. `FRONTEND_INTENT.md` §9: retain the browser-local provider
   *direction* and capability coverage, but "existing useful Ghidra analysis must
   not be replaced/recomputed for architectural uniformity." The idek.md
   person-week estimates are also non-authoritative (`FRONTEND_INTENT.md` §11 [A1]).
   Treat P0–P5 as **direction, not a schedule or a reordering of STRATEGY.**

A mandatory product checkpoint sits between P0–P2 and P3–P5: don't open
provider-breadth units until ingest/navigation/evidence/objdiff flows pass on real
corpus projects.

---

## 4. Look, feel, and behave

### 4.1 Visual direction

A **dense, legible graphite IDE.** Dark base, panels a step lighter, thin
separators, code-native text and controls, a single restrained blue accent used
for selection/focus, monospace for code/hex/addresses. **No card-grid marketing
treatment, no statistic strips, no ornamental gradients, no giant blank upper
workspace, no green "success" celebration.** Project/program selection and one
pipeline control stay visible; Listing and Decompile own the primary workspace;
inspectors and activity are resizable and collapsible. At narrow widths, one
primary pane at a time replaces crushed side-by-side content.
(`2026-09-20-unified-workstation-spec.md` §"Visual direction"; `workstation.css`.)

> Provenance note: "graphite" and "restrained blue selection" are a **design
> synthesis** derived from the 2026-09-16 generated reference images, not literal
> user words. The user's own words were "dense / legible / intuitive," "no
> spinner," "draw the work," and "think Qt / x64dbg / IDA / Ghidra." The synthesis
> is faithful; the vocabulary is ours.
>
> Deep-archive corroboration: a full sweep of the ~1.5GB of searchable
> conversation text in `boden_wizard_chat_context` found the dashboard look/feel
> vocabulary ("graphite", "workstation", "command palette", "activity dock",
> "corpus-first") **unattested before September 2026** — the keyword hits trace to
> *other* projects (a DAW, a qBittorrent "Control Shell", `libgraphite2.so`
> strings). The bespoke analysis dashboard is a **recent (Sept 2026) synthesis**;
> the earlier UI intent on record is only a dark-mode landing/Web-UI surface and a
> once-planned OpenCode-based agent frontend. Treat the graphite dashboard as
> current direction, not long-standing design canon.

Concrete geometry (implemented; `frontend/src/workstation/workstation.css`,
`WorkstationApp.tsx`): navigator rail ~240px (resizable 180–480, collapsible),
evidence rail ~260px (200–480), activity dock ~170px (100–420, `max-height:46dvh`),
1px separators, per-tab accent underline, `100dvh` shell. The 2026-09-09 design
contract states the same intent in prose: "graphite surfaces, stable geometry,
compact controls, monospace evidence, and color reserved for address, focus,
lifecycle, and proof semantics."

### 4.2 Shell and layout

A vertical stack (live in `WorkstationApp.tsx`):

```
Active project / related-build scope · search / goto · one workflow control
┌────────────────────┬────────────────────────────────────┬──────────────────┐
│ Project/artifacts  │ Shared entity: actual code/graph    │ Evidence / types │
│ Variant groups     │ Build counterparts and divergences  │ Origin/conflicts │
│ Containers/files   │ Synchronized assembly / hex / diff   │ Contextual edits │
├────────────────────┴────────────────────────────────────┴──────────────────┤
│ Actual-work view: compare / change / propagate / verify / runtime events    │
├─────────────────────────────────────────────────────────────────────────────┤
│ Activity dock: Activity · Recovery · Logs · Jobs · Problems                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

- **Header:** brand, Open binary, New scratch, search (Ctrl+P), Commands (Ctrl+K).
- **Session tabs:** sticky, per-binary; active tab accent-underlined; renameable;
  color-coded by project kind (http shared server vs shared-folder vs local `.gpr`
  vs raw binary — a 2026-08-31/09-01 user request); auto-create one if none open.
- **Analysis tablist:** Disassembly, Decompiler, Hex, Strings, Graph, Xrefs,
  Imports, Exports, Sections, Info, Matching; overflow collapses into a "More…"
  select.
- **Navigation bar:** Back/Forward, address-or-symbol jump, reload, copy-share-URL.
- **Three panes:** one Functions rail (a single Functions surface — the duplicate
  sidebar widget is removed), center analysis pane, evidence inspector rail.
- **Activity dock** at the bottom carries Jobs, logs, diagnostics, notifications
  together; relevant active work stays perceptible while reading code; historical
  unrelated jobs do not dominate; refreshes never steal focus, scroll, or editor
  drafts.
- **Command palette (Ctrl+K)** is the universal entry — actions + go-to surfaces +
  recent jobs. Toolbar search filters *functions only* (must not conflate "jump to
  a surface" with "find a function"). "Less chrome": resizable persistent panes,
  dense readable rows, context menus, keyboard alternatives — no cards of internal
  commands, no redundant "Explore" buttons, no raw JSON as the default result.

Origin feel (Cursor, 2026-08-31 → 09-01, verbatim fragments): "think Qt or
wxwidgets"; "ida pro / ghidra / x64dbg especially the generated graph"; "ideally
everything should be on one page … refrain from using tabs unless you have to";
menu bar for File/Edit/View/Help with save/save-as migrated into it; "all toasts
should be part of a logging widget at the bottom, all widgets on the page should be
resizeable … jobs should be a tab of the logging widget"; remove hardcoded page
limiters so lists default to "all" with a combobox to limit; realtime function
search; "5 different accessible ways to access any and all functionality including
context menus and top menus." The 2026-08-31 `feel.md` names the metaphor: **"an IDE
fused with a flight deck"** — project tabs as open files, function list as project
tree, inspector/graph as the editor, jobs as engine readouts.

### 4.3 Status feedback — "draw the work, not a status report"

The primary feedback is a **live, inspectable visualization of the actual work**,
not a spinner and not a statistics sentence. The user's words (2026-09-16):

> "a 'running' piece of text next to a circle spinning isn't very informative,
> don't do stuff like that." / "Actually animate/draw shit so it's actually showing
> WHAT is being done rather than useless statistics."

Four work verbs get first-class visualization (`FRONTEND_INTENT.md` §4.3;
`2026-09-20-unified-workstation-spec.md` §"Show the work"):

- **Matching** — candidate implementations brought together; the actual blocks,
  references and evidence under comparison highlighted; candidate / accepted /
  rejected / unresolved edges distinguished; alternatives shown without pretending
  all builds are one-to-one.
- **Source recovery** — before/after source edits beside the actual compiler
  diagnostic or semantic evidence each change addresses.
- **Verification** — original/generated instruction/byte regions aligned; residual
  differences and relocation-aware interpretation revealed; fresh comparisons
  distinct from historical receipts.
- **Propagation** — the specific eligible field change animated from evidenced
  donor to concrete recipient builds, with compatibility gates, conflicts and
  recipient validation. No animation of a successful transfer before its
  receipt/event exists.

Rules: motion **follows observed events only** — no simulated packet travel, random
graph motion, or timer-driven "compiling" decoration. Unknown internals stay
explicitly **unobserved** rather than a looping pretend-work animation. Keep
freeze/step/history so fast changes are inspectable; never auto-pan away from the
operator. Reduced-motion and keyboard-accessible presentations convey the same
information. Counts, timestamps, logs and ETAs are **secondary detail**, never the
primary experience. "A spinner and the word Running alone are not an acceptable
status."

**Honest current state (do not mark delivered):** the anti-slop half is
implemented — `PreparationActivity.tsx` renders a per-stage rail
(queued/running/waiting/cancelling), a `workMeasured` flag, a donor→recipient pair,
>10s staleness detection, and invents no percentage/ETA. The **affirmative half**
(candidate lanes aligning, donor→recipient field animation) exists only as a
self-labeled **simulated mock**, `dashboard/static/recovery-prototype.html`
("No recovery jobs, compiler calls, database writes"). The spec pre-admits this:
"Backend event instrumentation is part of this scope where current receipts lack
the necessary operation/entity/artifact evidence."

**Design decision (grill-resolved, §6.1):** the affirmative visualization is a
**committed target gated on a new backend event stream**, not shipped capability.
Frame it in delivery as **one shared backend instrumentation deliverable with two
rendering consumers** — the static 8080 surface renders a truthful *lighter* form
(inline row changes, stage details, expandable causal explanations, navigable
evidence), the React surface renders the rich animated form — **both replaying the
same accepted-event receipts.** Do not build it per-frontend (that violates "no
providers copied into either frontend"). Do not presume a push transport: today
both surfaces **poll** (the static donor lineage polls via ETag fragment refresh
with backoff and hidden-tab pause; the React dock polls jobs), so build "real-time"
as **replaying recorded event deltas over the existing poll** — which also yields
the required freeze/step/history for free. Gate every animated edge on its
accepted/rejected receipt on **both** surfaces.

Distinguish the three honest dimensions separately, never merged into one accuracy
score (2026-08-31 `feel.md`, 2026-09-08 F07): **activity** (is work happening),
**evidence/decomp posture** (none / asm / C), and **proof/validate posture**
(none / objdiff / linked/whole-image). A **third combined "byte-accuracy bar" was
explicitly and repeatedly rejected.** Repeated honest copy: "A finished job is not
a match"; "Real C and a complete executable are separate facts."

### 4.4 The single pipeline control

One context-aware start/pause/resume control. The user's words (2026-09-16): "one
button representing start/pause/resume … individual parts of the pipeline (like
ghidra bulk or veriff-cross) should not be buttons anywhere." Pipeline steps are
**observable, not a manual checklist of Run buttons.** Expert low-level tools stay
available (VISION forbids a compulsory recovery funnel), just not as normal
per-stage workflow buttons.

**Design decision (grill-resolved, §6.2): the control is one *scope*, not one
master switch.**

- It owns the **active project/program's serialized mutation-admission boundary**
  and *explicitly disclaims* the separately-owned lanes — the runtime-reuse
  observation branch, distributed workers on leased units, and independent
  read-only extraction/indexing. It **surfaces** those in the dock but does not
  start/stop them.
- **Start/resume** admits eligible work from checkpoints. Resume revalidates
  source/target/toolchain/dependency identity and reuses only valid work; a stale
  durable "running" record is not a live owner.
- **Pause** means *stop admitting new work into this mutation context and drain
  what this context already accepted* — it is **not** cancel, and makes no claim
  over lanes it doesn't own. A pre-existing standalone live job it didn't start
  stays visible and prevents duplicate admission. Cancellation is a separate verb.
- **Prerequisite, not polish:** admission must arbitrate on **real backend
  owner/lock state and resource claims, not the catalog `mutating` flag.** The spec
  records the live bug: `corpus.ghidra-bulk` advertises `mutating:false` despite
  `write=true`. Until admission reads real ownership, pause's drain is unscoped
  (it would miss the mis-flagged writer and falsely report "safe-paused" while a
  compiler writes) and admission is unsafe (it could admit a second writer onto the
  one Ghidra project). Sequence this arbitration **before** the pause/resume
  contract can be met.

### 4.5 Responsive behavior

Implemented breakpoints (`workstation.css`): ~1100px (rails shrink, keyboard hints
hide) and ~700px (44px touch targets; Functions/Evidence become full-screen
overlays; a mobile rail bar appears; dock capped at ~23dvh). "One primary pane at a
time replaces crushed side-by-side content." Acceptance requires desktop **and**
`598×912`; note that 598 falls under the 700px breakpoint, so it inherits the full
mobile treatment — and it is **untested** (the React verification covered
1440/390/768, never 598). Reduced-motion is honored everywhere.

### 4.6 Delivery contract — two surfaces, one backend

Confirmed directly by the user on 2026-09-20 ("the sept 8 thing is correct"):

| Surface | Role |
|---|---|
| **MCP HTTP server, `8080/dashboard`** (required) | A **complete useful static HTML/CSS/JS workbench**, served without a Node runtime, including every relevant capability deliverable this way. Static assets may still be interactive and **receive live updates.** |
| **Optional React/TypeScript Vite app, default `5174`, packaged `/react/`** | A rich, desktop-like AIO workspace that can run alongside AgentDecompile. Not development-preview-only; not a cosmetic copy of the static dashboard. |
| **Shared backend/catalog** | One project identity, catalog capabilities, durable state, jobs, mutation policy and proof semantics across both frontends and agent clients. No competing recovery implementations; no providers copied into either frontend. |

The two UIs may differ in layout and richness; they must not disagree on selected
target identity, saved work, actual jobs, or proof. Everything the CLI/MCP can do
must be reachable from the UI (and the Swagger/API). **Operational guard:** recovery
operations and live acceptance stay exclusively on 8080; the delivery requirement
does **not** authorize starting 5174 during a live recovery mission.

> Chronology note: `verification/2026-09-11-react-aio-redesign.md` records checks on
> port 5174 and a final PASS at `8767/react`; the "no 5174 process" guard is
> 2026-09-20, so that acceptance *predates* the guard. Port **8767** appears in
> acceptance evidence but in neither delivery-contract surface — an unexplained
> third port worth reconciling.

### 4.7 Cross-cutting behavior requirements

- **State vocabulary is explicit and never color-alone:** loading, empty,
  disconnected, unavailable, stale, unsupported, partial, conflict, reconnecting,
  approval-required, failed, recovered — each rendered distinctly (implemented as a
  lifecycle matrix in the shell; see design-system doc). Transient read errors
  (408/429/5xx/timeout) demote to reassuring info, not alarms, and keep the last
  received content.
- **Real-time, crash-safe persistence:** everything the frontends do saves back to
  the project in real time; force-killing the server never loses work; durable
  acknowledgement is observable (never promise arbitrary unsaved RAM survives).
- **Nonblocking admission:** validate and durably accept an import, then close the
  modal and show the work in the workspace; long jobs offload and the dialog closes
  instantly — no application-wide "Working…".
- **Selection vs batch scope:** one inspectable primary item plus a separately
  visible checked set with range/select-all; changing the active program never
  silently carries checked addresses into another binary.
- **Corpus-first navigation:** the primary selected object is a logical entity in
  the corpus, not an isolated binary/address; Compare is a fundamental workspace
  interaction, not a secondary destination. Concrete build/address is a drill-down;
  build-specific bytes/ABI/edits stay explicitly distinct.
- **Guide coverage (the open GUI gaps):** one synchronized Code Browser (single
  selected program+address as state owner); a **continuous navigable Listing**
  (address/bytes/mnemonic/operands/labels/flow/xref) — the highest-value missing
  piece, since the current UI is assembly text + one-instruction inspector; shared
  listing↔decompiler back/forward; local-variable rename/type gestures; **genuine
  parameter custom-storage editing** (the current button is a no-op that resubmits
  unchanged storage — flagged defective); never hard-code guide-example ABI sizes
  or register assignments.

---

## 5. Design-history timeline

| Date | Document / event | Axis |
|---|---|---|
| 2026-06/07 | Codex history: compiler round-trip goal; integrate Mizuchi; "context puzzle pieces"; ASM only as intermediary | origin |
| 2026-07-13 | `plans/2026-07-13-feat-unified-source-parity-recovery.md` | pipeline (single-binary parity origin) |
| 2026-07-17 | `plans/2026-07-17-feat-phase5-proof-ladder.md` — first formal proof ladder **1%→5%→20%**, bans "≥90% recovered" marketing | priority |
| 2026-07-17…30 | 13 `brainstorms/*-requirements.md` (context fusion, agent-loop closure, readability repair, mismatch-class routing, relocation-evidence) | pipeline |
| 2026-07-24 | perf-recovery ladder P0–P3 | priority |
| 2026-08-30 | `plans/2026-08-30-corpus-semantic-pipeline-living-plan.md` — first corpus pipeline (10-node) + "Priorities (do not reorder) 1–4" — now **historical/superseded** | pipeline/priority |
| 2026-08-31 | Cursor: the canonical pipeline+priority contract quote (S-955d idx 42); "extract, identify, merge knowledge, generate projects, recover source, apply cross-build knowledge, compile, verify byte accuracy" | pipeline/priority origin |
| 2026-08-31 | `plans/2026-08-31-0041-feat-workbench-aio-plan.md` + AIO ingest→UI flow | look/feel |
| 2026-08-31 | `prototypes/dashboard-operator-feel/feel.md` — **operator-feel canon** (IDE + flight deck; dual bars; no third accuracy bar; Phase A/B/C) | look/feel |
| 2026-09-08 | `plans/2026-09-08-0156-feat-recovery-pipeline-ladder-plan.md` — **canonical 8-step ladder** (active living plan) | pipeline/priority |
| 2026-09-08 | Dual-surface delivery request (static 8080 + optional Vite) — later reconfirmed | look/feel |
| 2026-09-09/10 | `plans/2026-09-09-0630-feat-local-first-re-workbench-plan.md` — **P0–P5 roadmap** + graphite design contract | priority/look-feel |
| 2026-09-09 | Copilot: "replace the vite design with inspirations from RzWeb, objdiff-web, radare2, decomp.me, decompiler-explorer, rev.ng"; AIO deep-research verdict fed back | look/feel |
| 2026-09-09 | [`idek.md`](file:///home/brunner56/Documents/idek.md) — AIO deep-research doc (P0–P5, source hierarchy, security model) | reference |
| 2026-09-11 | `verification/2026-09-11-react-aio-redesign.md` — React WorkstationApp redesign receipt | look/feel |
| 2026-09-16 | Codex D2 recovery/redesign session — corpus-first, "draw the work," one control, remove duplicate Functions, priority-0 rework, runtime-reuse branch in-scope | all three |
| 2026-09-20 | `dashboard-design/2026-09-20-{kotorxid,ghidra-guide}-capability-inventory.md` | look/feel |
| 2026-09-20 | `dashboard-design/2026-09-20-{unified-workstation-spec,delivery-reconciliation}.md`; `plans/2026-09-20-unified-reversing-workstation.md`; **`FRONTEND_INTENT.md` consolidation** | all three |
| 2026-09-20/21 | Post-consolidation git commits — implementation fixes consistent with intent (pause-drains-safely, bound stage progress to measured facets, keep draft tab, honor configured roots). **No new human requirements.** | — |

### Supersessions / reversals (all confirmed against primary sources)

| Earlier | Current (wins) |
|---|---|
| "make it ALL react, why is the folder named static" (angry, 2026-09-08) | Deliberate **two-surface split**: static 8080 workbench (control-dense) + optional Vite (visual pipeline view). Static can still be interactive. |
| Vite "just a dev server" | Required optional application ("the sept 8 thing is correct"). |
| "No assembly whatsoever" | Honest **assembly-floor intermediary** allowed (stabs→asm→c); never counts as recovered C. Interim exception the user forced to reach a compiling exe. |
| Cross-match as a secondary panel | The **organizing relationship** of the workspace (corpus-first). |
| Two left trees including Functions | **One** Functions surface; duplicate sidebar removed. |
| Numeric bars / ETA / "Running" as primary feedback | **Draw the actual work**; numbers secondary. |
| 24-hour default workflow budget | **Unlimited** default (bounded per-attempt behavior remains). |
| "priorities 1–9" as a literal 9-rung ladder | Reconciled into the **8 named stages**; no ninth inferred; minimize priority-0 friction. |
| Global metadata donor / forced 1↔1 matching | **Strongest per field**; ambiguity and split/merged regions first-class. |
| Runtime-reuse branch excluded (older task) | **Included** as the runtime-reuse branch. |
| Mandatory local-Rizin-first order (pasted roadmap) | Keep browser-local direction; **don't replace existing Ghidra** for uniformity. |
| Per-function objdiff endpoint (2026-09-08 body) | **Two whole-image variants**; per-function objdiff is a gate, not the endpoint (2026-09-20 note). |

---

## 6. Sharpened design decisions (grill of the prototype model)

Two load-bearing questions the docs leave ambiguous, resolved by interrogating a
model built from all sources. These are the crux additions.

### 6.1 The actual-work feedback model

- The affirmative "draw the work" visualization is a **committed target, gated on a
  backend event stream that does not yet exist**; the static
  `recovery-prototype.html` is a *promissory design reference*, not delivered
  capability. Putting it in the live root today would force exactly the
  timer/phase-name fabrication the spec bans.
- Build it as **one shared backend instrumentation deliverable** (per-entity
  operation/artifact/accepted-edge events) with **two rendering consumers** — 8080
  truthful-inline, React rich-animated — not as a per-frontend UI item.
- **Both** surfaces must be *event-truthful*; only rendering fidelity differs. 8080
  showing *less* is honest; 8080 showing a *spinner* is not.
- **Transport is poll/replay, not push.** Neither surface has a live socket; build
  "real-time" as replaying recorded event deltas over the existing poll (this also
  gives freeze/step/history for free).
- Gate every animated edge on its **accepted/rejected receipt** — never animate a
  transfer before its event exists.

### 6.2 The single pipeline control + priority-zero

- **Priority-zero is not a stage.** It is the reconcile/reuse-valid-work preamble.
  Its friction is a **scope-of-gate error**: it must gate only the mutation-
  admission boundary, never read-only hydration or independent lanes. Make it
  cheap, checkpoint-trusting, and repair-on-detected-breakage — not a full pass on
  every resume, and not a concurrent lane (the reconcile-for-mutation piece is a
  real precondition for *writes*).
- **The single control is one *scope*, not one master switch.** It owns the active
  project's serialized mutation-admission boundary and **disclaims** the separately-
  owned lanes (runtime-reuse, distributed workers, independent reads), which it
  surfaces but does not start/stop. Pause = stop admitting + drain *this* context's
  accepted work; it is not cancel and claims nothing over lanes it doesn't own.
- **Real owner/lock admission arbitration is a prerequisite for pause/resume**,
  because the `mutating:false`-despite-write bug makes the drain unscoped and
  admission unsafe until fixed.

### 6.3 Other open tensions to resolve during implementation

1. **CodeBrowser is not composed in the active Workstation root** (`AnalysisView`
   imports only the `useTool` hook; the `<CodeBrowser>` component renders only in
   the older `App.tsx` root the spec says not to nest). The guide inventory's
   highest-value gaps (continuous Listing, shared back/forward, variable
   rename/type gestures, real parameter-storage editing) remain **open** in the
   shipped shell.
2. **The unified-workstation-spec is visibly mid-edit** (a bare `## Pipeline
   control` heading with no body before `## Show the work`; real content later
   under `## Pipeline control semantics`).
3. **Three accent hues ship simultaneously** across the CSS layers (see the
   design-system doc) — a single reconciliation decision is required.
4. **Static-vs-React capability line** is asserted ("must agree on semantics") but
   not concretely partitioned; §6.1 gives the partition principle
   (event-truthful-both, fidelity-differs).

---

## 7. Source ledger

This plan triangulated the prior consolidation against the raw transcripts. Full
per-message provenance lives in `FRONTEND_INTENT.md` §11; the primary roots are:

- **Canonical docs:** `STRATEGY.md`, `VISION.md`, `CONCEPTS.md`,
  `FRONTEND_INTENT.md`, `DELIVERY_STATUS.md`, `PROTOTYPE_OUTCOMES.md`,
  `docs/dashboard-design/2026-09-20-*`, `docs/plans/2026-09-08-0156-*`,
  `docs/plans/2026-09-09-0630-*`, `docs/prototypes/dashboard-operator-feel/*`,
  `docs/verification/2026-09-{08,11}-*`.
- **Codex sessions:** `~/.codex/sessions/2026/09/08/rollout-…01a080d3….jsonl` (D1,
  dashboard/delivery), `~/.codex/sessions/2026/09/16/rollout-…01a0aca5….jsonl` (D2,
  recovery/redesign — the "draw the work" / one-control / priority-0 turns), and the
  2026-09-20 handoff. No human design session exists after 2026-09-20.
- **Cursor:** `~/.cursor/chats/**/prompt_history.json` — the 2026-08-31 canonical
  contract (project `b3ef1b8d…` session `955d2c64…` idx 42), the frontend-
  architecture message (`74f6348d…` idx 11), and the one-page/menu-bar/project-tab
  feel requests. 28 of 235 sessions mention the project; the design-bearing ones are
  cited above.
- **Copilot:** `~/.copilot/session-store.db` `turns` — the "replace the vite design
  with RE-tool inspirations" turn and the fed-back deep-research verdict.
- **Claude:** `~/.claude/projects/-run-media-…-agentdecompile/*.jsonl` (through
  2026-09-13) and `~/.claude/history.jsonl`.
- **Reference:** [`/home/brunner56/Documents/idek.md`](file:///home/brunner56/Documents/idek.md)
  (AIO deep research; direction only, estimates non-authoritative).

Coverage honesty: the ~64GB `boden_wizard_chat_context` archive and the full Codex
corpus were sampled by recency + design-vocabulary co-occurrence, not read
end-to-end; the 2026-09-17/18 "personal branding / mental-health" thread that
keyword-matches "pipeline/priority" is **not** AgentDecompile and was excluded. The
companion design-system extraction is in
[`2026-09-21-design-system.md`](2026-09-21-design-system.md).
</content>
</invoke>
