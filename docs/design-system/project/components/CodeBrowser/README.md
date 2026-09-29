# CodeBrowser

The composite center pane: Listing and DecompileView side by side on one cursor, an optional HexStrip beneath them, a function Outline popup that follows the cursor, and the XrefPanel docked beside, so reading code never means flipping analysis tabs.

**Use it** as the center of the Code Browser workspace on both surfaces. It is the one place code is read: the Functions list drives it, the evidence rail follows it, and the dock stays below it.

**Consumer provides** the primary location (project, entity, build, address); the co-visible views (`v=listing,decompile,hex`); the link state (Linked, or Unlinked with the held pane's entity × build × address, its age and basis); Listing rows, decompile lines and bytes from existing analysis, with the listing ↔ decompile mapping; the Outline projection of the current function (basic blocks with line ranges, locals and parameters, calls, strings); and the XrefPanel rows for the token under the caret.

- Layout: a toolbar (function, build, cursor address and line; Listing · Decompile · Hex view toggles as `aria-pressed` buttons; the chain-link sync toggle; Outline), then Listing | splitter | DecompileView, the HexStrip spanning both beneath, and the XrefPanel docked beside at 228px when the Code Browser is at least 880px wide, under the code otherwise. At most two code panes; Graph is not co-visible here.
- **Co-visible, not tabs.** Listing and Decompile are both mounted and both visible. Hiding one is a view toggle recorded in `v`, never a tab flip, and it leaves the cursor unchanged.
- **One cursor.** Listing, Decompile and Hex share it. The focused pane draws the selection shape (`selection` fill plus 3px `accent` bar); the others draw the reflection (`raised` plus a 3px `ink-muted` bar, "↔ line 7", `▸` at the exact address). In the HexStrip the statement bytes sit on `raised` and the cursor instruction carries a 2px `ink-strong` under-bar.
- While the HexStrip is shown, the Listing's bytes column moves into it; the docked XrefPanel carries the Listing's xref column.
- **Linked / Unlinked.** The sync toggle is a button with `aria-pressed`, an icon and the word: "Linked" (chain) or "Unlinked" (broken chain in `fact-stale`). Unlinking holds the decompile pane: a 2px `ink-strong` frame, the word **Held**, what it holds and its age, its own Back and Forward, and **Make primary**. A held pane never refreshes by itself; a basis change shows `fact-stale` ◷ "Basis changed since held" with Refresh. The Listing keeps following. Linking again makes the pane follow the primary selection and drops the held location; Make primary instead moves the selection to it.
- **Following an xref moves both.** Enter on a callee or data token in the Decompile, on a symbol operand or flow target in the Listing, or on an XrefPanel row moves the one cursor: Listing, Decompile and Hex land on the target together and one history stop is pushed. Focus stays in the pane where Enter was pressed. Alt+← (Back) restores both panes' cursor, scroll row and caret token together, and the landing is announced once.
- **Outline popup** on `dialog-bg` with `shadow-popup`, non-modal: Blocks (entry address, name, line range), Locals (type, storage, tier; they open InlineRename and never go anywhere), Calls, Strings. The block that holds the cursor carries the selection shape and "· cursor" and moves as the cursor moves. It reads the already-loaded function; nothing is analyzed to fill it. An empty section says "none" instead of disappearing.
- **Below 700px** one view shows at a time. A tablist (Listing · Decompile · Hex · Xrefs, 44px targets) replaces the view toggles, and the line under it states the kept cursor: "Cursor 0041b229 · line 7 · kept when you switch views". Switching changes only which view is visible; cursor, scroll row and caret token stay.
- Splitters are `.ad-split-h` separators (APG Window splitter); the View menu offers the same sizes and collapse without dragging (WCAG 2.5.7).
- **Read-only by construction.** Browsing, following, the Outline, Hex and references read cached or already-loaded evidence and never start analysis, import, compile or any mutation. The only mutation path in the pane is InlineRename's Save.
- Both surfaces implement it over the same location, cursor and reads; there is no new backend or state owner. The static 8080 surface may stack the views as panels with the same cursor and reflection; no field exists on only one surface.

**Analysis-tab flips it removes.** Disassembly, Decompiler and Hex stop being mutually exclusive analysis tabs: they become co-visible views of this pane (`v=listing,decompile,hex`), and the Xrefs tab becomes the docked XrefPanel. Strings used by the current function move into the Outline. Their tab entries survive only as shortcuts that move focus to the pane, never as page swaps. Strings (program-wide), Graph, Imports, Exports, Sections, Info, Matching and More… remain analysis tabs.

**Linking**

- Publishes `a` (the cursor), `v` (co-visible views) and `hold` (the held pane) to the location. pushState on Go, Back target and link-state change; replaceState for cursor moves inside one function.
- Follows the primary location; a held pane follows nothing until it is linked again or made primary.
- Renders every link of Listing, DecompileView, HexStrip and XrefPanel, and the Outline's block, call and string links.
- Absent targets: an unopened build shows "Not loaded. Open to read it." in every view with one Open button; an unmapped line says "no mapping" in its own pane and leaves the others unmarked; a callee with no symbol is written "unresolved import".

**Keyboard**

- Each view is one tab stop: Tab goes Listing → splitter → Decompile → Hex → XrefPanel toolbar → XrefPanel grid. F6 and Shift+F6 still cycle the workstation regions.
- Enter goes, Shift+Enter opens to the side, Alt+↓ peeks and Shift+F10 opens the token or row menu, in every view (see DecompileView and XrefPanel).
- Alt+← and Alt+→ move both panes back and forward together.
- `O`, while focus is inside the Listing or Decompile grid, opens the Outline: ↑/↓ move, Enter goes, F2 on a local renames it, Esc closes and returns focus. Remappable and off outside the grids (WCAG 2.1.4).
- The view toggles and the sync toggle are buttons: Space or Enter toggles.
- Below 700px the view tablist follows APG Tabs: ←/→ and Home/End move, the cursor stays.

**Accessibility**

- The composite is a `section` named "Code Browser"; each view is a named grid ("Listing, ResourceRef::Resolve, build-a", "Decompiled C, ResourceRef::Resolve, build-a", "Bytes, build-a .text, …").
- The sync toggle is `aria-pressed` with a visible word and an `aria-describedby` sentence. Held is a word and a frame, never color alone.
- After Go or Back the new place is announced once in the polite region ("Back to ResourceRef::Resolve, line 7"); cursor moves inside a function announce nothing (WCAG 4.1.3).
- WCAG 3.2.1 and 3.2.2: toggling a view, the link state or the single-view tab never moves the cursor or switches the build.
- WCAG 1.4.10: below 700px one view at a time; only code rows scroll horizontally, each inside its own well.
- The Outline is a non-modal `role="dialog"` named "Outline · ‹function›" with grouped lists; `aria-current` marks the cursor's block. It opens on request only, never on focus.

**Removes switching:** J10 relate an instruction row to its decompiled statement, 6 → 0 (no Disassembly ⇄ Decompiler flips). J09 follow a cross-reference and return, 4 → 0 (XrefPanel beside the code; Enter moves both panes; Alt+← returns both). J36 from strings to use sites and bytes, 3 → 1 (the Outline lists the function's strings, the HexStrip shows the bytes; the program-wide Strings tab is still one switch). J37 cross-view work below 700px keeps the same number of view switches but no longer loses the place: the cursor survives every switch.
