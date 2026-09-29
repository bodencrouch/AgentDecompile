# PipelineBreadcrumb

Where one entity stands on one concrete build: one crumb per stage 1–8, each showing the fact that governs that stage and, when the entity waits there, the gate it waits at.

**Use it** as the Pipeline section of the evidence rail (second, after Kept), in its compact one-line form under the Code Browser's Views toolbar, and at the top of the Recovery workspace, always for the selected logical entity on the inspected build. Stage 0 is not a crumb: it gates writes only (`gate-0`) and belongs to WorkflowControl.

**Consumer provides** the entity, the concrete build and address, and for each stage: the governing fact state or states with the receipt that decided each, the gate text when the entity waits there, or the reason the stage does not apply; plus the revision of the served `pipeline-model.json`.

- One crumb per stage, in order, titled as in `pipeline-model.json` (`stage-1`…`stage-8`): Identity · Incremental calibration · Validated linkable regions · C/C++ candidates · Propagation (cross-place) · Targeted AI (leftovers only) · Continuous parity · Whole-image byte identity. There is no ninth.
- Each crumb shows its governing fact as glyph + word from that fact's own vocabulary: the IdentityEdge state (1), the calibration profile check (2), the region round trip (3), Compilation and ABI checks (4), the transfer or recipient acceptance (5), the leftover candidate (6), Local match and Linked match (7), and Whole-file equality per variant (8). Never a percentage, bar, score, ratio or "done".
- **Each crumb is one pipeline-node link**, `?project=…&entity=…&build=…&node=‹id›`, whose whole cell is the target. It goes to that PipelineMap node and its live view filtered to this entity and build; the primary location does not change, and focus lands on the map node. The crumb where the entity waits links its gate (`node=gate-4`); the others link their stage. Ids come only from `pipeline-model.json`.
- **The deciding evidence is one Peek away.** Alt+↓ on a crumb reads the receipt, identity edge, transfer, diff summary or ledger cell that decides the stage, from cache. Per-fact receipt links live in that Peek and in the rail's Facts section, never as a second link in the crumb.
- Stage 8 keeps **C+floor** and **max-C** as two separate glyph + word lines and names the method (reconstruction or original-style rebuild). It is image-level for the build and says so. One variant never borrows the other's receipt.
- **Waiting**: a `gate` ◇ glyph, the words "waiting at gate:" and the gate text from the model. The crumb where the selection waits has `aria-current="step"`, a 2px `ink-strong` frame and the words "Selection waits here". The accent is not a status, so the current step never takes the accent bar.
- A stage that does not apply says why, in italic `ink-muted` ("not applicable: not a leftover"), as plain words that are not a link. A build with no counterpart shows one StateNotice instead of eight empty crumbs; nothing is inferred for an absent counterpart.
- A 3px top rule in the stage's family `-fill` (identity, recovery, verify) ties the crumb to the diagram. It is decorative: the stage name carries the meaning.
- The breadcrumb is per concrete build. The header names the build and offers an explicit "Builds ▾" menu (the NavigationBar's Builds ▾). A new selection never switches the build silently.
- Layout by container width: 8 columns at 1040px or more, 4 at 520px or more, one column below. It fits the 260px evidence rail and the full center pane. Crumb text is `type-ui` 12 and `type-kicker` 11.
- Motion: a crumb changes only when its receipt or acceptance event exists.
- Crosswalks from lifecycle states to stages are interpretations. Where one is shown it says "(interpretation)"; it is never presented as a recorded fact.

**Linking**

- **Publishes:** nothing that moves the selection. Enter on a crumb pushes one history stop to its `node=` and the node's filtered live view; the header's Builds ▾ menu is a Go (one stop).
- **Follows:** the primary selection (entity and inspected build) after the settle. It is a rail section, so it is kept as a card, never held.
- **Targets rendered:** pipeline node (`stage-1`…`stage-8`, and the gate where the entity waits) → the PipelineMap node, filtered to this entity and build · the header's build → the Navigator program row. Link names read "4, C/C++ candidates: Compilation passed, ABI checks not run, waiting at gate: compile admits candidate, not replacement".
- **Peek source:** the stored receipt, identity edge, transfer, diff summary or VariantLedger cell that decides the stage, plus the node's model text headed "From the pipeline design · model rev ‹8 hex›". Nothing is fetched.
- **Absent copy:** "not applicable: ‹reason›" (plain words) · "No pipeline for #88 on build-d" with "root unresolved on this build; members tried: 7" · "absent" and "unresolved" for counterparts, never a link.
- **Target-size exception:** none. Each crumb is a whole-cell target well above 24px; 44px below 700px and with a coarse pointer.

**Keyboard**

- A list of links in Tab order. Enter goes to the node; Shift+Enter opens it beside; Alt+↓ peeks the deciding evidence; Shift+F10 opens the one link menu, whose Reveal in lists Pipeline map and the Evidence rail's Pipeline section. Browser modifiers keep their meaning.
- The "Build ▾" menu follows APG Menu Button: Enter, Space or ↓ opens, ↑/↓ move, Enter picks. Esc follows the one Esc order in the Keymap section.

**Accessibility**

- `<nav aria-label="Pipeline for ‹entity› on ‹build›">` around an ordered list of eight crumbs. Each link reads as one sentence. Glyphs are `aria-hidden` beside their words.
- `aria-current="step"` marks where the selection waits; the words "Selection waits here" say the same visibly.
- Amber touches only the ◇ glyph and the "waiting at gate:" label; text stays `ink` on `pane`.
- A stage change for the selected entity is announced once in the polite region after its acceptance event ("ResourceRef::Resolve on build-a passed gate 4"). Polls announce nothing.
- Each crumb reflows to one column at 320px.

**Removes switching:** opening the Recovery workspace, the Corpus workspace or the Jobs dock only to learn where one entity stands on one build. It supports J03 and J04, which the ledger credits to U180 and U182.

## Behavior

Moved from the preview's tips and chips (Guideline 25).

- 0 writes only (chip removed): "Stage 0 gates writes only; see the workflow control."
- Key (moved text): "Each crumb is one node link, filtered to this entity and build; the primary selection does not move. Alt+↓ peeks the receipt that decides the stage."
- Visible "Selection waits here" is shortened to "selection here"; the crumb's accessible name keeps "Selection waits here".
- Keycap Key rows (removed; keycaps are not drawn encodings): "Alt+↓ · peek receipt".
