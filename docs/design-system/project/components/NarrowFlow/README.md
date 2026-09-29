# NarrowFlow

The single-pane flow below 700px, accepted at 598×912: a bottom rail bar (Navigate, Analyze, Inspect, Activity) with 44px targets, per-pane memory, Peek as a bottom sheet, list selection that advances to Analyze only on explicit activation, and a NavigationBar collapsed to Back, Go to and a breadcrumb menu.

**Use it** for every view below `bp-single-pane` (700px), including 400% zoom at 320 CSS px. It is the Workstation's regions shown one at a time, not a separate mobile app: same selection owner, same links, same keymap, same backend.

**Consumer provides** the four panes' content (Navigate: the Functions list and other navigator views; Analyze: listing, decompile, xrefs; Inspect: the evidence rail; Activity: the dock), each pane's remembered state for this viewer (scroll, cursor or caret, active tab, expanded rows), the location for the breadcrumb, the history stack, a count for Activity, and the Peek projection.

- **One pane at a time.** The rail bar is a tablist of four 60px tabs across the full width, each an icon (1.5px line, 16px) plus a word plus a one-line memory in mono (`row 212`, `0041b216`, `Facts`, `5 problems`). The current tab uses `selection`, a 3px top `tab-active-rule` and bold `ink-strong`; never color alone.
- **Every target is `touch-h` (44px)**: rail tabs, NavigationBar buttons, analysis tabs, list rows, listing rows, sheet buttons and menu items.
- **Per-pane memory.** Leaving a pane stores its scroll position, cursor or caret, active tab, filter and expanded rows; returning restores them and the focused element. Memory is per viewer in durable workspace state. The URL carries the location, not scroll.
- **Explicit advance only.** In Navigate, arrows and j/k move focus and the list's own highlight; the Analyze pane does not change. Enter or a tap on a row makes it the selection and switches to Analyze, pushing one history stop. Focus alone never switches panes or changes the selection (WCAG 3.2.1). The rail bar's Analyze memory says what Analyze still shows.
- **Peek is a bottom sheet.** Alt+↓, focus rest on a link, or on touch **Peek** in the row's menu opens a non-modal sheet above the rail bar: grab bar, kind and build kicker, mono title, ProvenanceStamp, facts in words, up to six cached code lines in a `code-bg` well, then **Open**, **Open beside** (which opens in Inspect as a held view, since there is no split) and **Keep**. At most 64% of the pane; **Full height** is a button, so dragging is never required (WCAG 2.5.7). The pane scrolls so the triggering line stays visible above the sheet (2.4.11). Esc or ✕ closes it and returns focus to the trigger. It reads cached evidence only; unloaded evidence says "Not loaded. Open to read it."
- **NavigationBar collapses to three controls**: **Back** (named for its destination, Alt+←), **Go to…** (opens go to anything as a full-height sheet, Ctrl/Cmd+P), and a **breadcrumb menu button** showing the build and section on a small line and the function in mono, which opens a menu: Project, Build (with the count of builds and their locator glyphs), Section, Function (current), then Forward, Recent… and Copy link. Reload and the sync toggle move into that menu's overflow; nothing is lost.
- **Dock and rails become panes.** The dock becomes the Activity pane, a full pane rather than a 23dvh strip; the evidence rail becomes Inspect. Activity's memory shows problems and transitions as words, and a job transition is announced once, never by switching panes.
- Held and kept items appear in Inspect with their "Held" or "Kept" word and age. Following panes still follow the one selection when they are shown.
- Motion: none. Panes and the sheet appear in place; reduced motion changes nothing.
- Both surfaces use the same breakpoint, panes and memory keys. The static 8080 surface may render the sheet as an inline panel under the line; it keeps 44px targets and explicit advance.

**Linking**

- Publishes: the primary selection on Enter or tap in Navigate, on Open in the sheet, and on crumb menu picks; each pushes one history stop.
- Follows: Analyze and Inspect follow the one selection; Navigate and Activity follow nothing.
- Renders: every typed link at 44px (inline code links grow their hit area to the row height); the breadcrumb menu's project, build, section and function links.
- Absent: a build without a counterpart in the Build submenu is "absent", not a link; an unloaded peek says "Not loaded".

**Keyboard**

- The rail bar is an APG Tabs tablist with one tab stop: ←/→ move, Enter or Space activates, Home/End. F6 and Shift+F6 still cycle regions: NavigationBar, the current pane, the sheet when open, the rail bar.
- Alt+← goes back, restoring the pane that was showing and its memory. Ctrl/Cmd+P opens go to; Alt+↓ peeks; Shift+Enter opens beside into Inspect; Esc closes the sheet first (keymap Esc order).
- Keys come from `keymap.json` unchanged; single keys stay focus-scoped.

**Accessibility**

- Reflow (WCAG 1.4.10): at 320 CSS px only code rows and matrices scroll horizontally, each in its own container.
- The sheet is `role="dialog"` with `aria-modal="false"`, named by its title; the trigger has `aria-expanded` and `aria-controls`. The rail bar tabs have `aria-controls` to their panes; each tab's name includes its memory ("Analyze, 0041b216").
- Switching panes is announced by the tab itself; opening the sheet with Alt+↓ is announced once ("Peek: FUN_0041c880, reused peek cache"); nothing else speaks.
- Targets are 44px (2.5.8 and the narrow rule); the sheet never covers the focused element (2.4.11).

**Removes switching:** J37 "any cross-view journey at 598×912" goes from 6 switches (Navigate → Analyze → Inspect → counterpart → Analyze → Activity) to 2: Enter from Navigate, then Peek the counterpart as a sheet instead of switching to Inspect and back, with Activity's count visible on the rail bar. Counts before come from the journeys table; after counts are design targets.
