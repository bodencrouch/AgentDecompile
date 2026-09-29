# VariantRelation

How the project's builds relate, pair by pair: what differs in toolchain, flags and link settings, and how many entities fall into each variance class (compile, entropy, source, unknown), each count with its evidence level and a drill-down to the entities behind it. This is the "which differences are the compiler and which are the source" overview.

**Use it** as the corpus view `ws=compare&panel=variants` (a registered `panel` value), with `cmp=build-x..build-y` selecting one pair. It is reached from ToolchainEvidence's pair list, from a build header, and from CounterpartMatrix ("How do these builds relate?"). Rows and counts are corpus-level. The drill-down lands on entities, and every entity opens in Compare with the same `cmp`.

**Consumer provides** for each pair of builds: the toolchain, flag and link differences taken from ToolchainEvidence, each with its level; whether source, toolchain and flag identity are recorded for each build (PDB source checksums, command lines, toolchain registry); and the stored per-entity comparison result for the pair. That result has the class, the evidence level, the basis (the transformations checked, or the recorded digests that decided it), and the addresses on both builds. It also has the similarity opinions, each with the tool that produced it. Pairs whose bodies were never compared have no per-entity result.

- **Four variance classes**, each a glyph and a word (guideline 20, Variance class), plus "identical":

  | Class | Glyph | Meaning |
  |---|---|---|
  | compile variance | ≈ | Same source; different toolchain, flags or link settings (register choice, frame shape, inlining, cookie or EH scaffolding, ICF, ILT or padding). |
  | entropy variance | ∼ | Same source and same declared toolchain and flags; incidental build state differs: paths, declaration or object order, link order, timestamps. |
  | source variance | ≠ | The source changed: control flow, call set, constants or field set. |
  | unknown | ? | Cannot tell yet: source identity is missing on one side, source and flags both differ, or the evidence conflicts. |
  | identical | ≡ | Byte-identical after relocation normalisation. This is not a variance class and not a match claim. Its count is plain text, never a drill link, because ≡ is not an `f=vrel:` value. |

- **Evidence level of a class.** A class is **solid** only when source, toolchain and flag identity are recorded for both builds (source checksums, command lines, the toolchain record). In every other case it is a **dashed "hypothesis (heuristic)"** with its basis ("no checked transformation explains it: inlining, /Oy, LTCG, ICF, hotpatch"). This holds even when the bytes strongly suggest a class. Individual facts beside it (a Rich header entry, a differing constant) keep their own witness level, but they do not make the class solid. Where bodies were not compared, the word **unknown** is written and nothing is counted.
- **The map** (top) is a small overview, not a claim. The four builds sit in the corners, and each pair's label sits on its connector; the two diagonal pairs are stacked in the centre.
  - Each node says what is recorded for its build ("x64 · VC 14.38 · PDB: source and flags recorded", "source identity not recorded").
  - Each label names its pair as a link, then the toolchain, flag and link difference as an evidence value, then the class counts.
  - The connectors are decorative `line-node` lines in an `aria-hidden` SVG. They carry no certainty; certainty lives on each value. Below a 520px container the map stacks into one column and the connectors are dropped.
- **The pair table** carries the same information as a grid, one row per pair:
  - **Pair**: a `cmp` link.
  - **Toolchain · flags · link**: evidence values.
  - **Entities by variance class**: each count with its glyph, its class word as a link that drills in, and its level word. The ≡ identical count follows as plain text. For one pair the counts add up to the entities compared on that pair ("271 + 15 + 0 + 902 = 1,188 on build-a × build-b").
  - **Reading**: one or two plain sentences composed from the stored counts ("Mostly the compiler. Same source, compiled differently, is plausible; 15 bodies change in ways no checked transformation explains."). The reading's own level is shown when it goes beyond the counts.

  A pair with no comparison reads "unknown · nothing is counted until the bodies are compared". When no pair has source, toolchain and flag identity recorded on both builds (corpus-alpha today: only build-d has them), the view says so once under the legend, and every count is a hypothesis.
- **Never merged, never averaged.** Counts are per pair. They are never summed across pairs or turned into a similarity score. A report is never merged across builds with different recorded source revisions. Where per-build results differ, the other views say "varies across builds".
- **Drill-down.** Activating a class count is a Go that applies a FilterChip (`f=vrel:source` with the pair's `cmp`; `vrel` is a registered axis) and shows the entities behind it. Each row has the entity (a link that opens Compare with the pair), the address on each build (or "absent"), the evidence value that decided the class, and **Opinions**: each score with its own source ("0.81 BSim similarity", "38 bytes differ objdiff"). Scores from different tools are shown side by side and are never compared, ranked or averaged. The footer says "…and N more" and "opening one decides nothing".
- **Rail form** (the Explain build difference preset, LayoutPresets 6). In the evidence rail the view shows only the current `cmp` pair, scoped to the selected entity, as a rail section headed "For ResourceRef::Resolve · build-a ↔ build-c":
  - **This pair**: the toolchain, flag and link differences as evidence values, and whose source identity is recorded ("recorded on neither build, so no class here can be solid"). A value links to ToolchainEvidence for that build.
  - **This entity**: its stored class with glyph, word and evidence level, and the basis ("≠ Source changed · hypothesis (heuristic), basis: vftable slot 1 → 2 …"), then "One of 28 entities with source variance for this pair."
  - **Differences**: a list, one item per stored difference of the entity (frame shape, vftable slot, field offset, registers), each with its own class and level. A difference never inherits the entity's class.
  - **Opinions**: each tool's score with its tool, never combined.
  - Footer: **Show all pairs**, a Go to `ws=compare&panel=variants` with the same `cmp` and `entity`.
  - Layout: one column at the rail width (`evidence-w`, 200–480px); values wrap, nothing scrolls sideways, and there is no table or map. With no stored comparison for the pair it reads "unknown · nothing is counted until the bodies are compared" and names what is missing; with no `cmp` it reads "No pair selected · choose a counterpart in the CounterpartStrip".
  - It follows the selection and the `cmp` pair after the settle, like other rail sections, and is kept as a card, never held.
- Read-only by construction. It reads stored toolchain evidence, recorded identities and comparison results. It never compares bodies, runs a matcher or binds a program. A pair with no comparison names what is missing and arms nothing.

**Linking**

- **Publishes:** `cmp` on Enter on a pair row, or on a pair link (a Go, one stop). `f=vrel:‹class›` when a count is activated (a Go; replaceState when the chip is removed). An entity link is a Go to Compare with `entity` and `cmp`. Nothing else.
- **Follows:** `project` and `cmp`; commit-on-Enter (an expensive corpus view). Arrows move focus only. The selected pair carries the selection shape. Not holdable; a drill list can be collected with `w` as a worklist of entity × pair. The rail form follows `entity` and `cmp` after the settle, because it reads one stored row.
- **Targets rendered:**
  - pair → this view with `cmp`;
  - class count → the filtered entity list;
  - entity → Compare with the pair (logical id);
  - address → the Code Browser at that build (always with `build`);
  - build node → the Navigator program row;
  - an evidence value's witness → its address;
  - its record → the receipt card;
  - rail form: Show all pairs → this view with `cmp` and `entity`; a toolchain value → ToolchainEvidence for that build.

  Link names read "27 entities, source variance, build-c and build-d, hypothesis (heuristic)".
- **Peek source:** Alt+↓ on a count reads the stored comparison summary for that class (the basis and the first rows). On an entity, it reads the stored per-entity result and its opinions. Nothing is compared on peek.
- **Absent copy:** "unknown · bodies not compared" · "absent" (no counterpart on that build, plain word) · "no opinion · nothing to compare" · "source identity not recorded" · "nothing is counted until the bodies are compared".
- **Target-size exception:** none. Count links, pair links and entity links are at least 24px tall, and 44px below 700px or with a coarse pointer.

**Keyboard**

- The map is a group in Tab order with one stop per link. The pair table is a row-focus APG Grid with one tab stop: ↑/↓ move between pairs, and ←/→ move to the links in a row.
- The rail form is an APG disclosure (an h3 holding a button); inside it Tab moves through its links in reading order, and F6 leaves the rail.
- Enter on a row selects the pair (`cmp`). Enter on a count drills in, and Shift+Enter opens the drill beside. Alt+↓ peeks, and Shift+F10 opens the link menu.
- The drill's FilterChip toolbar comes before its grid. Delete removes the chip. `w` collects the rows as a worklist.

**Accessibility**

- The map is a `role="group"` named "Builds and how each pair differs; the pair table below is the same information as a grid". The SVG is `aria-hidden`, and every label is real text.
- The pair grid is named, and `aria-describedby` points to the class legend. Class glyphs are `aria-hidden` beside their words. Every count's accessible name carries count, class, pair and level.
- Dashed versus solid is a second cue: the level word is always visible. Forced colors map the frames to `CanvasText`.
- Below a 480px container the pair grid and the entity rows follow NarrowFlow's build-column grid rule: one list item per row, each build a labelled line ("build-c: +0x18 · hypothesis"), with nothing scrolling sideways.
- The announcement comes on the drill only, debounced: "Filter applied: source variance. 27 of 1,201 entities, build-c and build-d."

**Removes switching:** telling compiler differences from source changes no longer means opening each pair's toolchain headers, diff report and entity list separately. One view gives the classes and their evidence, and a class opens its entities in place.

## Behavior

- The view reads stored toolchain evidence and body comparisons; nothing is compared from here.
- A class is solid only when source, toolchain and flag identity are recorded for both builds. When only one build has them, every class is a dashed hypothesis (heuristic) with its basis, and no pair can show entropy variance yet.
- Counts are never averaged across pairs, and a report is never merged across different source revisions.
- Enter on an entity opens it in Compare with this pair (cmp=build-c..build-d); opening one decides nothing.
- Scores from different tools are shown side by side and never combined.
