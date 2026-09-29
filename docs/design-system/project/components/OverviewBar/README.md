# OverviewBar

A vertical navigation margin beside the Listing that shows one build's whole view at a glance. It has lanes for address type, byte entropy, markers (bookmarks, marks, selection, highlights, changed bytes and search hits) and cross-build divergence. Every lane is repeated in a text key with values, and in Compare the per-build bars stand side by side, never merged.

**Use it** at the inline end of the Listing well, where it replaces Ghidra's navigation margin and overview bars, and in the Compare workspace as one bar per build. Below 700px it moves above the Listing as a horizontal strip, with the key under it. It is optional: the Listing header's **Overview** toggle (`aria-pressed`) shows or hides it per viewer.

**Consumer provides**
- The view: the inspected build's whole image, or the ProgramTreeView restriction, with its address range and the bytes per pixel row.
- Memory blocks from the existing memory read.
- Per address-range run, the code-unit type, when a catalog read provides the type map.
- Byte entropy per chunk (chunk size 256, 512 or 1024 bytes), when a catalog read provides it.
- The markers:
  - program bookmarks by category, read-only;
  - the viewer's marks;
  - the Listing's address-set selection;
  - highlights A–D;
  - rows changed by a job, with the job id;
  - hits of the active ResultsTable.
- For Compare: each build's divergence ranges from ImageDeltaMap and ObjectDiff receipts, each with its variance class and evidence level, and the recorded anchor pairs.

## Anatomy

1. **Header.** "Overview · build-a · whole image 00401000–0046ffff · about 1.5 KB per row". When the view is restricted: "Overview · build-a · view: .text, io (ProgramTreeView)". It has a lane menu, **Show key**, and the Following word.
2. **Lanes**, 16px wide each, separated by 2px `chassis` gaps. Each lane has a one-letter head that is restated in words in the key.
   - **T · Address type** (row L17). Precedence as in Ghidra: function, external reference, instruction outside a function, defined data, undefined bytes, uninitialized. Graphite steps plus patterns (solid, stripes, diagonal hatch, dots, outline) carry the kinds. A family or fact color is never used, because these are not states. The type map is an approximation: each pixel row shows one sample, and the key says so ("one sample per row; a mostly-data region can show as undefined").
   - **E · Byte entropy** (row L18). A graphite ramp from 0.0 (dark) to 8.0 (light) per chunk. The value is measured from bytes, so it is solid. A range label such as "machine code" or "compressed or encrypted" is a hypothesis: it names its basis ("entropy 7.6–8.0; range heuristic") and never becomes a claim. The chunk size and the configured ranges live in lane settings, per viewer.
   - **M · Markers** (row L16).
     - Point ticks: a left-half tick for a program bookmark, a centered tick for a search hit, a right-half tick for "changed by job", and the letter for a mark.
     - Area bars: selection (the accent, which is the selection color), highlight A–D (with the letter), and "differs" from an open diff.
     - The cursor is a 2px `ink-strong` rule across all lanes.
   - **D · Divergence** (Compare only, or with **All builds** on). These are ranges where this build differs from its counterparts, each with its variance-class glyph and word (State vocabularies): ≈ compile variance, ∼ entropy variance, ≠ source variance or ? unknown. ≡ identical is not a divergence and draws nothing. The lane and key filter with the registered `f=variance:` axis.
     - Solid frame: the class is recorded, which means source, toolchain and flag identity are recorded for **both** builds of the pair.
     - Dashed frame, labelled "hypothesis (heuristic)" with its basis: any other case, however strongly the bytes suggest the class.
     - Dotted frame with the word "unknown": there is no evidence either way.
     - A "not read" hatch marks ranges whose divergence has not been computed.
3. **Key** (always present, `aria-describedby` from the bar).
   - Every kind with its pattern swatch, word and count.
   - For entropy, the ramp with its numbers and each configured range.
   - A **ranges list**: a grid of the view's regions in address order, each a typed address link (start, end, kind, value).
   - The ranges list is the accessible and keyboard form of the bar. The graphic is never the only carrier.
4. **Side-by-side builds** (row L17 in Compare). One bar per build, build-a…build-d, each in its own address scale and each labelled with its range. Bars are never aligned by offset. A cursor position is drawn on another build's bar only through a recorded anchor pair ("▸ via anchor 0041c880 ↔ 0041b210"). Without an anchor pair nothing is drawn, and the key says "no anchor; not drawn on build-d".

**Terms.** *Byte entropy* is the statistic of this lane. *Entropy variance* is the build-state variance class (paths, declaration or link order). They are unrelated and never abbreviated to "entropy" together. Equal byte entropy across builds is cheap divergence evidence only; it is advisory (NP) and never a match.

## States

| State | Shown as |
|---|---|
| Loading | the previous bar dimmed with "Loading overview · build-b"; `aria-busy` on the bar only when it does not hold focus |
| Not read | a lane whose read has not run shows the hatch and "Byte entropy not read for build-c · Enter to read"; following never reads |
| Unavailable | "⊡ Code-unit type map: catalog action needed" in the lane head and key; the lane is omitted from the bar and listed in the key |
| Partial | "◐ 3 of 5 blocks read" with the unread blocks hatched |
| Stale | "◷ build-b changed since read by job a3f9 · Refresh"; the old bar stays, marked stale |
| Empty markers | "No markers in this view" in the key; the lane stays |
| Program not loaded | "Not loaded. Open build-c to read it." for that build's bar in Compare; the other bars stay |

## Linking

- **Publishes:** Go from the ranges list, a key row, or a click on a pixel row moves the primary location to that build and address and pushes one stop. With the pointer, the click lands on the first address of that pixel row, and the key says "row covers about 1.5 KB; lands on 0041c800". A click on another build's bar in Compare goes to that build explicitly and is announced.
- **Follows:** the inspected build, the view (whole image or the ProgramTreeView restriction), the cursor (drawn as the rule), the Listing selection, highlights, the active ResultsTable and marks, after the settle. It is a cached pane; reads that are not cached wait for Enter. It can be held with the Listing (a held Listing's bar freezes with it).
- **Targets rendered:** address (range starts and ends, markers) → the Code Browser at that build · job id ("changed by job a3f9") → the dock Jobs record · search result set → its ResultsTable · divergence range → ImageDeltaMap region (the Listing at the range start in that build, with the ObjectDiff pair) · receipt id for a classified range → its receipt card.
- **Peek source:** Alt+↓ on a key row peeks the cached Listing lines at the range start, and for a divergence range the receipt that classified it. Nothing is fetched.
- **Absent copy:** "Not loaded. Open build-c to read it." · "Byte entropy not read · Enter to read" · "catalog action needed" · "no anchor; not drawn on build-d" · "unknown · no source identity for build-d" · "No markers in this view".
- **Target-size exception:** the lanes are a 16px-wide graphic. Pointer clicks on it are an enhancement only. The ranges list and key rows (28px, 44px below 700px and with a coarse pointer) reach every destination, which is the 2.5.8 Equivalent exception.

## Keyboard

- The bar itself takes no focus. **Show key**, or the palette command `overview.focus` (no default key; `g then v` belongs to VTableBrowser), moves focus to the ranges list, an APG Grid with row focus: ↑/↓ move by region, PageUp/PageDown by a screenful, Home/End go to the first and last region, Enter goes, Shift+Enter opens beside, Alt+↓ peeks, Shift+F10 opens the link menu.
- Proposed composite-scope ids (where "Overview ranges list"; not yet in `keymap.json`):
  - `overview.nextMarker` and `overview.prevMarker`: `]` and `[` move to the next or previous region of the lane in focus.
  - `overview.lane`: no default key, because `m` is `list.mark` in lists. The lane menu and the key's lane rows filter the list to one lane, and Esc clears the filter.
  - `]` and `[` match the typed character.
- From the Listing, the existing Listing next/previous commands (row N03, extend) and F8 (the active worklist) step markers without leaving the code well.

## Accessibility

- The bar is `role="img"` named "Overview, build-a, whole image, 4 lanes", with `aria-describedby` to the key. The key is a real list, not a tooltip.
- The ranges list is `role="grid"` named "Overview regions, build-a". Each row reads "0041c000 to 0041cfff, function, byte entropy 6.1, 2 search hits".
- Kinds are words and patterns, never color alone. Adjacent segments are separated by 2px `chassis` gaps. Hypothesis ranges are dashed and say "hypothesis" with their basis.
- In forced colors the lanes keep their patterns (`forced-color-adjust: none`) because the key carries every value, and lane frames use CanvasText. Under Increase contrast, segment separators are `ink-strong`.
- No motion. A new hit or change redraws in place without animation.

## Parity rows covered

- **L16**: the navigation margin, with the bookmark, selection, highlight, changes and search-hit markers, and click-to-navigate through the ranges list. The in-row marker margin is configured in ListingFieldLayout.
- **L17**: the address-type overview, with its legend as the key and its colors as patterns plus words. It includes side-by-side bars per build in Compare.
- **L18**: the byte-entropy overview, with calculation settings (chunk size), the palette legend with values, configured ranges as labelled hypotheses, and the window restricted by ProgramTreeView.
- **Q09**: the marker-margin and navigation-margin parts of the search results window.

## Prior art

- Ghidra help `OverviewPlugin/Overview.htm`: address-type precedence and its approximation note, entropy calculation per chunk, palette and ranges, click-to-navigate and the legend popup. Also `CodeBrowserPlugin/CodeBrowser.htm`: navigation markers with point and area areas kept apart. Ghidra's per-type colors and black-to-white palette become graphite patterns and a key with values here.
- Research: the variance classes and their evidence (Premise and B8 in `docs/research/2026-09-29-reference-re-ui-patterns.md`), and view 8, the placement map (`docs/research/2026-09-29-msvc-optimization-for-decomp.md` §9).
- Existing components: ImageDeltaMap (the rebuild-versus-target analog and the owner of divergence regions), MarksList (marks and worklists), LocatorGlyph (anchor words).
