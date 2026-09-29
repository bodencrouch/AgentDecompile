# EntityBuildCard

One entity on one concrete build, gathered as a single evidence-rail section when the operator presses Enter on a matrix cell: the locator and observed status on separate axes, runtime capabilities in words, the ladder residue, what can be done on that build, and its export-readiness row, with a back-link to the cell it came from.

**Use it** at the top of the evidence rail after Enter on a ReadinessMatrix or CounterpartMatrix cell (and after Enter on a build header's entity row). It answers "can I use this entity on build-c, and if not, why?" in one place. It follows the primary selection like every rail section; K keeps it as a Kept card.

**Consumer provides** the entity (logical id and name) and the concrete build now in the primary selection; where the card was entered from (matrix, row index, build column, and the location to return to); the locator pack status with member and kind and the separate `observed_status`; for contested cells, both evidenced hits with their members; the RuntimeCapabilities rows (located, readable, callable, detourable, writable) as on, unknown or refused with the named refusal and the ladder node and member that produced it; the resolution ladder as it ran on that build (members tried in order, per-member reason, members not tried and why, member used, terminal OutcomeTag); the one catalog action that would move a refusal forward, if any; and the readiness-report row for this entity × build with its publication state, plus the export targets that include it. Each with its ProvenanceStamp.

- Header: a back-link in `type-kicker`-sized `ink-muted` text, "← from ReadinessMatrix · row 12 · build-c"; the title in `type-pane-title`, "ResourceRef::Resolve · build-c" (symbol mono, `translate="no"`); the logical id as a link; the ProvenanceStamp ("reused · readiness report · basis 9f3c…a1e0 · 13:41"); **Keep** (`aria-pressed`, K). Entered by any other path, the back-link is absent, never invented.
- Sections, in this order, each an h4 in `type-kicker` with 1px `line` rules between: **Locator**, **Runtime capabilities on ‹build›**, **Ladder ‹letter› · as run on ‹build›**, **What you can do on ‹build›**, **Export readiness**. The order is fixed so the card reads the same for every cell.
- **Locator** is a two-row `<dl>`: pack status as LocatorGlyph plus word ("◎ pinned(module_rva) · non-portable") and **Observed** as its own FactBadge word. `observed_status` never overwrites pack status and is never folded into it. Contested lists both hits with their members and addresses under a 2px `fact-failed` rule and the words "two verified hits disagree · no winner"; **Open both, held** opens two held panes labelled "contested · no winner". Arrival order is not a tie-breaker.
- **Runtime capabilities in words**: one row per capability with the L R C D W chip (`aria-hidden`), the capability word and its state: "yes · ABI and lifetime checked", "unknown · not checked", "refused: not_detourable · ladder B · member 5". Readable never implies writable; callable never implies detourable. A refused row strikes the word in `fact-failed` and names the refusal; the refusal is a link to the ladder member that ended it, and Alt+↓ peeks its reason from the stored ladder run. Without an accepted binding (contested, unresolved) the section says "Capabilities are not evaluated without an accepted binding" instead of five unknowns.
- **Ladder residue**: the ladder as it actually ran on this build, same numbering and order as ResolutionLadder, with 20px numbered circles in the ladder's family fill (decorative; the numbers and member slugs carry the meaning). Tried members show their reason in `ink-muted`; untried members are dashed and say "not tried (budget)" or "not applicable", never implying exhaustive failure; an annotation is "a claim, never resolved". "Open the ladder run" goes to the full EvidenceRail.
- **What you can do on ‹build›**: plain sentences from the capabilities and locator ("Read and call … at module_rva 0x1b210. Detours are refused. Writing is not checked."), always ending with "Runtime calls never count as recovered source." when anything is callable. At most one button arms the catalog action that could move a refusal forward ("Arm cave discovery"); it arms the ActionStrip bound to this entity × build and never runs. An unresolved or contested cell arms nothing.
- **Export readiness**: the exact readiness-report row this entity × build ships as (mono), its publication state ("current · basis …" or "◷ stale · basis changed …"), and each export target that includes it with how ("hookpack v2: included as pinned, non-portable"). Ambiguous and contested rows ship as structured outputs that refuse unsafe use.
- Surfaces: `pane` card, 1px `line`, square corners; fits `evidence-w` 260px up to `rail-max` 480px. Addresses `address`, refusals and slugs mono, glyph colors from LocatorGlyph, FactBadge and OutcomeTag only.
- Read-only by construction: the card reads the stored readiness report, ladder runs and capability receipts. It never opens a program, runs a ladder or probes a live process. Unstored evidence says "Not loaded. Open to read it."
- Both surfaces render the same sections from the same readiness JSON; the static 8080 surface renders the refusal peek as an expandable detail.

**Linking**

- Publishes nothing; the selection was written once by Enter on the cell. Make primary is not needed because the card always shows the primary entity × build; a Kept copy is read-only and says "Kept".
- Follows the primary selection (entity × build). Moving the selection replaces the card; the back-link is kept only while the selection still equals the cell it names.
- Renders: the back-link (the matrix location with `focus=cell:‹row›:‹build›`, restoring focus to that cell), the logical id (Compare), addresses (Code Browser on that build), ladder nodes and members (`node=ladder-B-5`, with `entity` and `build`), the basis digest (ProvenanceStamp detail), export nodes (`node=export-readiness`) and the armed action.
- Absent: "absent" for a build with no counterpart, "unresolved" with the ladder for an unresolved locator; never an address guessed from a neighbour build.

**Keyboard**

- Enter on a matrix cell writes entity and build once and moves focus to the card's heading; the polite region says "ResourceRef::Resolve, build-c: pinned, module_rva; observed not run". Arrowing across cells binds nothing and announces nothing (WCAG 3.2.1).
- The back-link returns to the same cell with focus on it; Alt+← does the same through history.
- Inside the card: Tab moves through links and buttons in section order. Alt+↓ on a refusal opens its peek; Esc closes it and returns to the refusal. K (focus-scoped, remappable) toggles Keep. Shift+F10 on any link opens Reveal in.
- F6 leaves the evidence rail; returning restores the last-focused element in the card.

**Accessibility**

- The card is a `section` labelled by its h3; sections are h4s, so screen-reader users jump by heading. Capabilities are a list whose rows read "Detourable, refused: not_detourable, ladder B member 5"; chip letters and locator glyphs are `aria-hidden` beside their words.
- The ladder is an `<ol>`; numbers are drawn in circles and are also the list order, and "4–10 not tried (budget)" is one item with a hidden "Members" prefix.
- Never color alone: refused is a word plus a strike, contested is ⇉ plus the word plus "no winner", and the family fill of ladder circles is decorative.
- The back-link names its target fully ("Back to ReadinessMatrix, row 12, build-c"); every target is at least 24px, 44px below 700px.
- The refusal peek follows Peek's WCAG 1.4.13 rules; it never covers the refusal it explains.

**Removes switching:** J33, why an entity is not runtime-usable on a build and whether other builds are, goes from 4 views (capabilities, ladder, "what you can do" line, export) to 1 card, with the other builds one arrow away in the matrix. J06, from a readiness cell to its ladder and any contested pair, goes from 4 to 1, and a contested pair opens as two held panes in one step. J14's per-build vtable loop drops from 6 to 2 with the slots mode, and J26 picks a build for the entity from its row in 1.
