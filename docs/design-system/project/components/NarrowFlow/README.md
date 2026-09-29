# NarrowFlow

The one narrow contract: the single-pane flow below 700px (`bp-single-pane`), checked at 598×912 and 320×256 CSS px and with a coarse pointer at 768×1024. A bottom rail bar (Navigate, Code, Inspect, Events) switches panes; each pane keeps its memory; Peek becomes a bottom sheet; a pick advances to Code only on explicit activation; and the NavigationBar collapses. Other components point here for their narrow form instead of restating it.

**Use it** for every view below 700px, including 400% zoom at 320 CSS px. It is the Workstation's regions shown one at a time, not a separate mobile app: same selection owner, same links, same keymap, same backend, same location schema.

**Consumer provides** the four panes' content (Navigate: the Functions list and other navigator scopes; Code: the Code Browser's views and References; Inspect: the evidence rail; Events: the dock, opening on its Events tab), each pane's remembered state for this viewer (scroll, cursor or caret, active view, expanded rows, focused element), the location for the breadcrumb, the history stack, the latest activity transition with counts of other running and failed work, the Peek projection, and the viewer's View settings.

- **One pane at a time.** The rail bar is an APG tablist of four tabs across the full width, each an icon (1.5px line, 16px) plus a word plus a one-line memory in mono (`row 212`, `0041b216`, `Facts`, `5 problems`). The current tab uses `selection`, a 3px top `tab-active-rule` and bold `ink-strong`; never color alone. The rail bar and the status line respect `env(safe-area-inset-*)`.
- **Targets.** 24px (2.5.8) is met everywhere; 44px (`touch-h`) is the house rule (2.5.5) for rail tabs, NavigationBar buttons, the Code views tabs, list and listing rows, sheet buttons and menu items. Any coarse pointer gets 44px at every width.
- **Per-pane memory.** Leaving a pane stores its scroll position, cursor or caret, active view, filter and expanded rows; returning restores them and the focused element. Memory is per viewer in durable workspace state. The URL carries the location, never scroll, and `views` and `hold` are never rewritten at narrow widths.
- **Update panes is On Enter below 700px.** The collapsed NavigationBar says "Update panes: On Enter" in words. This is the documented reason arrows and j/k move focus and the list's own highlight without changing the selection or the Code pane.
- **Advance on a code pick.** Enter or a tap on a pick that resolves to a code location (an entity, address, symbol, string or import use site) makes it the selection, pushes one history stop and shows Code. Focus lands on the Listing row at the target address (the Linked views table); the grid's label supplies the context, and one polite message says "Code: ‹entity›, ‹build›". Other picks do not advance: a project item goes through the cross-project StateNotice ("Switch to ‹project›" armed and confirm-gated, beside "Stay"); a tree container expands; a checkbox cell checks. Focus alone never switches panes or changes the selection (WCAG 3.2.1). Advancing can be turned off with "Advance to Code after a pick" in View settings.
- **Back is history.** Alt+← and Back restore the previous stop and its pane from the stored focus region. The rail's Navigate tab returns to the list without changing the selection.
- **Code** has one composite header, the Views toolbar row: the function with its NameProvenance tier word, the fact strip as one Peek button, the build and the cursor. Wells keep only their view name and follow word ("Follows · on Enter", "Held · ‹entity› @ ‹build› · ‹age›" or "Counterpart of ‹entity› · derived"). The views sit behind an APG tablist named "Code views" (Listing · Decompile · Hex · Graph · References), with the line "Cursor 0041b216 · line 7 · kept when you switch views". Switching views never moves the cursor. Code wells contain horizontal overscroll.
- **Open beside** is the second segment of an APG tablist in Code: "build-a · primary | Held · #88 @ build-c · ‹age›" for a held pane, or "build-a · primary | Counterpart of #88 · derived" for a derived split (the segment's description names its build). A derived segment follows the selection's counterpart on its build and Enter in it is Go; Follow again returns a held segment to derived. The Held segment is read-only, with the footer "Read-only. Actions apply to the primary selection, build-a ‹addr›". On 8080 without split panes Open beside opens a new window instead ("Open beside (new window)").
- **Counterparts** stay one wrapping line with a 44px "Counterparts (n) ▾" disclosure. Builds ▾ shows, per build, the counterpart address, the divergence class and the edge word (NavigationBar).
- **Peek is a bottom sheet.**
  - Triggers: Alt+↓, "Peek" in the row's 44px row-menu button, and the Inspect tab. Focus rest never opens it below 700px.
  - The sheet is non-modal and at most `sheet-h` (64%) of the pane. The pane scrolls so the triggering line stays visible above the sheet (2.4.11). It shows up to `peek-lines-card` (6) cached lines, then **Open**, **Open beside** and **Keep**, plus **Full height** and **Close**. Dragging is never required (2.5.7).
  - **Full height** makes it a modal dialog with focus inside; Close or Esc returns focus to the trigger.
  - Below `bp-short-h` (480px of viewport height) the Peek opens as the full-height Inspect pane. That is one extra switch, counted in J37.
  - Inside Inspect, a Peek replaces the section's content with "‹ back" at the top, never a second sheet.
  - It reads cached evidence only; unloaded evidence says "Not loaded. Open to read it."
- **Events is a full pane** on the rail bar: the dock, opening on its Events tab, with Objectives, Logs, Jobs and Problems beside it. Every other pane shows a one-line status above the rail bar with the latest transition and the counts of other running and failed work ("a3f9 finished · 2 running, 1 failed elsewhere"). The Events pane opens with "Selection only" on; **Show all** is one activation. There is no dock strip.
- **Header and NavigationBar.** The header keeps the project name and a wrapping scope sentence; only search moves into Go to. The WorkflowControl collapses to its state glyph and word, with its scope in its disclosure. The NavigationBar collapses to **Back** (named for its destination), **Go to…** (the palette engine as a full-height sheet), a **breadcrumb menu button** (build and section on a small line, the function in mono), and the "Worklist 4 of 12" chip when a worklist is active. The breadcrumb menu is flat: Project, Section, Function, then one item per build as in Builds ▾, then Forward, Recent…, Reload and Copy link.
- **Short viewports.** Below 480px of viewport height the header and status line are not sticky; only the NarrowFlow bars stick, and the Peek opens as the full-height Inspect pane.
- **Build-column grids.** Below a 480px container, FrameLayout, ToolchainEvidence, PointerWalk, VTableBrowser, VariantRelation and MatchExplain become one list item per row, with each build as a labelled line ("build-c: +0x18 · hypothesis"); nothing scrolls sideways and no build column is dropped. CompilerLayer tags wrap under their row. Those components point here instead of restating it.
- Held and kept items appear in Inspect with their "Held" or "Kept" word and age. Following panes still follow the one selection when they are shown.
- Motion: none. Panes and the sheet appear in place; reduced motion changes nothing.
- Both surfaces use the same breakpoint, panes and memory keys. The static 8080 surface may render the sheet as an inline panel under the line; it keeps 44px targets and explicit advance.

**Linking**

- **Publishes:** the primary location on an advancing pick in Navigate, on Open in the sheet, on crumb and Builds ▾ picks, and on Make primary (one history stop each). Open beside publishes `hold=` (replaceState) and Keep publishes `keep=`. Switching rail tabs or Code views publishes nothing.
- **Follows:** Code and Inspect follow the one selection, committing on Enter below 700px; Navigate and Events follow nothing. The Held segment is holdable; the panes themselves are not.
- **Targets rendered:** every typed link at 44px (inline code links grow their hit area to the row height); the breadcrumb menu's project, section, function and per-build links; the Events status line's job link.
- **Peek source:** the same cached projection as Peek: listing lines, facts, locator rows, stored job records, the node's model text.
- **Absent copy:** "absent" as a disabled Builds ▾ item, never a link · "Not loaded. Open to read it." · "Read-only. Actions apply to the primary selection, build-a ‹addr›" · "Update panes: On Enter".
- **Target-size exception:** none. 24px (2.5.8) is met; 44px is the house rule (2.5.5).

**Keyboard**

- The rail bar is an APG tablist with one tab stop: ←/→ move, Home/End, and Enter or Space activates. F6 and Shift+F6 still cycle regions: NavigationBar, the current pane, the sheet when open, the rail bar.
- Alt+← goes back, restoring the pane that was showing and its memory. Ctrl/Cmd+P opens Go to; Alt+↓ peeks; Shift+Enter opens beside as the second segment. Esc follows the one Esc order in the Keymap section: a full-height sheet is a modal, a non-modal sheet is its second layer.
- Keys come from `keymap.json` unchanged; single keys stay focus-scoped. `g l`, `g d`, `g h` and `g r` also switch the visible Code view.

**Accessibility**

- Reflow (WCAG 1.4.10): at 320 CSS px only code rows and matrices scroll horizontally, each in its own focusable, labelled container. Accessible View soft-wraps code for reading at that width.
- The non-modal sheet is `role="dialog"` with `aria-modal="false"`, named by its title; Full height switches it to `aria-modal="true"` with focus inside. The trigger carries `aria-expanded` and `aria-controls` only while the sheet is open. The selected rail-bar tab has `aria-controls` to its pane (unrendered panes are not referenced); each tab's name includes its memory ("Code, 0041b216").
- Announcements follow Linked views: an advancing pick says "Code: ‹entity›, ‹build›" once; switching panes is announced by the tab itself; opening the sheet adds no live-region message.
- The sheet never covers the focused element (2.4.11).

**Removes switching:** J37 (any cross-view journey at 598×912) goes from 6 switches to 2: Enter from Navigate, then Peek the counterpart as a sheet instead of switching to Inspect and back. It is 1 if the counterpart is only peeked, 3 if a job record must be opened, and 1 more below 480px of viewport height. The ledger credits J37 to U191.
