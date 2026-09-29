# PipelineBreadcrumb

Where one entity stands on one concrete build: one crumb per stage 1–8, each showing the fact that governs that stage and, when the entity waits there, the gate it waits at.

**Use it** at the top of the evidence rail and of the Recovery workspace, for the selected logical entity on the inspected build. Stage 0 is not a crumb: it gates writes only (`gate-0`) and belongs to WorkflowControl.

**Consumer provides** the entity, the concrete build and address, and for each stage: the governing fact state or states, the gate text when the entity waits there, the link to the deciding evidence, or the reason the stage does not apply.

- One crumb per stage, in order, titled as in pipeline-model.json (`stage-1`…`stage-8`): Identity · Incremental calibration · Validated linkable regions · C/C++ candidates · Propagation (cross-place) · Targeted AI (leftovers only) · Continuous parity · Whole-image byte identity. There is no ninth.
- Each crumb shows its governing fact as glyph + word from that fact's own vocabulary: the IdentityEdge state (1), the calibration profile check (2), the region round trip (3), Compilation and ABI checks (4), the transfer or recipient acceptance (5), the leftover candidate (6), Local match and Linked match (7), and Whole-file equality per variant (8). Never a percentage, bar, score, ratio or "done".
- Each crumb is one link to the evidence that decides it: 1 → IdentityEdge; 2 → the calibration receipt; 3 → the region round-trip receipt; 4 → the compile receipt and SourceRepairDiff; 5 → PropagationTransfer; 6 → the leftover candidate's SourceRepairDiff; 7 → ObjectDiff; 8 → VariantLedger. Following it opens that evidence in place and pushes history; the link carries `entity`, `build` and `node`.
- Stage 8 keeps **C+floor** and **max-C** as two separate glyph + word lines and names the method (reconstruction or original-style rebuild). It is image-level for the build and says so. One variant never borrows the other's receipt.
- Waiting: a `gate` ◷ glyph, the words "Waiting at gate:" and the gate text from the model. The crumb where the selection waits has `aria-current="step"`, the selection shape (`selection` fill plus a 3px `accent` bar) and the words "Selection waits here".
- A stage that does not apply says why, in italic `ink-muted` ("not applicable: not a leftover"). A build with no counterpart shows one StateNotice instead of eight empty crumbs; nothing is inferred for an absent counterpart.
- A 3px top rule in the stage's family `-fill` (identity, recovery, verify) ties the crumb to the diagram. It is decorative: the stage name carries the meaning.
- The breadcrumb is per concrete build. The header names the build and offers an explicit "Build ▾" menu. A new selection never switches the build silently.
- Layout by container width: 8 columns at 1040px or more, 4 at 520px or more, one column below. It fits the 260px evidence rail and the full center pane. Crumb text is `type-ui` 12 and `type-kicker` 11.
- Motion: a crumb changes only when its receipt or acceptance event exists.

**Keyboard**

- A list of links in Tab order. Enter opens the deciding evidence in place; browser modifiers keep their meaning.
- Alt+↓ opens a Peek of the deciding evidence (receipt, diff summary or ledger cell) without leaving the view.
- The "Build ▾" menu follows APG Menu Button: Enter, Space or ↓ opens, ↑↓ move, Enter picks, Esc closes.

**Accessibility**

- `<nav aria-label="Pipeline for ‹entity› on ‹build›">` around an ordered list of eight links. Each link reads as one sentence, for example "4, C/C++ candidates: Compilation passed, ABI checks not run, waiting at gate: compile admits candidate, not replacement". Glyphs are `aria-hidden` beside their words.
- `aria-current="step"` marks where the selection waits; the words "Selection waits here" say the same visibly.
- Amber touches only the ◷ glyph and the "Waiting at gate:" label; text stays `ink` on `pane` and `ink-strong` on `selection`.
- A stage change for the selected entity is announced once in the polite region after its acceptance event ("ResourceRef::Resolve on build-a passed gate 4"). Polls announce nothing.
- Each crumb is a whole-cell target well above 24px; 44px below 700px. It reflows to one column at 320px.

**Removes switching:** the Recovery workspace, Evidence workspace and Jobs dock, opened only to learn where one entity stands on one build and which receipt decided it.
