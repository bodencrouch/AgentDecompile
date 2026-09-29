# KeymapSettings

The editor for the one shared keymap: every command from `keymap.json` with its keys, scope and status, conflicts, turn off, remap and reset, plus the which-key hint after a leader key and the keyboard shortcuts sheet.

**Use it** as Keyboard settings on both surfaces, reached from the settings menu, the palette ("Keyboard settings") and **Edit in Keyboard settings** in the shortcuts sheet. The which-key hint and the shortcuts sheet are its two runtime faces and read the same data.

**Consumer provides** `keymap.json` (commands with `id`, `label`, `keys`, `scope`, `where`, `note`; `scopes`; `profiles`; `escapeOrder`; `browserReserved`; `conflictPolicy`; `altGrCaution`), the viewer's override diff and chosen profile, the platform (to print Ctrl or Cmd), and for the sheet and which-key the current focus scope and region. Nothing else: labels, keys and ids are never hand-written in a component.

- **One source.** Rows render from `keymap.json` in its own terms: the `label` as the command name, the `id` in mono `ink-muted` beneath it, the `keys` as `ad-kbd` chips (resolved for the platform: "Ctrl/Cmd+K" prints as Ctrl K or Cmd K), `where` as the scope detail. Menus, tooltips, `aria-keyshortcuts`, the shortcuts sheet (`help.keys`, Ctrl/Cmd+/) and Accessibility help (`help.a11y`, Alt+F1) read the same file plus the viewer's diff, so help never drifts from behavior.
- **Grouped by scope** with counts, in the file's order: Global (20; always a modifier or a function key), Region (6), Composite (20; lists, grids, trees, listboxes), Code (10; code wells; off in edit mode), Edit (0). Long groups show their first rows and "Show N more"; the filter searches label, id and key, and pressing keys in it finds their binding.
- **Profiles** are a segmented control: Default, IDA (adds focus-scoped n, y, ; and g in code wells) and Off (every single-character key off; modifier globals and menus remain). Commands owned by an inactive profile are listed with dashed key chips and "profile IDA only · inactive in Default".
- **Status per row**, glyph plus word, never color alone: "default"; "remapped by you, default w"; ⇄ `fact-failed` "Conflict with ‹label›" when two commands share keys in overlapping scopes; ⇄ `fact-stale` for a caution the platform can predict (`altGrCaution`: a remap that uses Ctrl+Alt types characters on AltGr keyboards; F8 may need Fn on macOS); an **Off** chip (dashed frame) with "turned off by you · menu keeps it"; "native browser behavior · not remappable" for `link.newTab`.
- **Conflicts never guess** (`conflictPolicy`). Two commands bound to the same key in the same scope do nothing until the conflict is resolved, and the status line says which binding is blocked and why; the row menu explains both meanings and offers **Remap…**, **Add another key…**, **Turn off**, **Reset to default** and "Take ‹key› from ‹other command›".
- **Recording** puts the keys field in a 2px `ink-strong` frame with "Recording. Press other keys; Esc cancels." The result is checked live against the keymap and `browserReserved`: a reserved key is refused with ✕ and "Ctrl/Cmd+D is browser-reserved and is never bound", and Save stays disabled. Esc always cancels recording; it is never recorded.
- **Esc order**, the **conflict and AltGr** rules and the **browser-reserved** list are shown under the grid exactly as the file states them. Esc never clears the checked set or held panes.
- **Which-key hint.** After a leader (`leader`, g) in a focused composite, and after the viewer's delay (Off, 500 ms, at once), a `dialog-bg` panel with `shadow-popup` anchors below the focused row, grouped as the `leader` note groups them: Regions (n navigator, m main, e evidence, w work view, j dock), Views (l listing, d decompile, h hex, r graph), Panels (x references, c counterparts, ' marks) and Layouts (1 Read, 2 Compare, 3 Review, 4 Triage, 5 Verify rebuild), then Esc cancel, naming the entity it will act on. It waits for the next key with no timeout (WCAG 2.2.1), never covers the focused row, and a wrong key closes it and says "g x: no such jump" in the status line. Where the browser takes F6, g then n, m, e, w or j gives the same region jumps.
- **Keys the other components rely on**, as the file states them: Keep is Shift+K (`link.keep`, only inside a Peek or evidence card, never on list rows where k moves); layouts are g then 1…5 (`layout.preset`, composite; Ctrl/Cmd+Alt+digit was rejected for AltGr keyboards, and `aria-keyshortcuts` cannot express the sequence, so menus show it as text); marks are m and ' then a lowercase letter, named marks through the palette; worklists step with F8 and Shift+F8.
- **Shortcuts sheet** (`help.keys`, Ctrl/Cmd+/; also Ctrl/Cmd+P then ?): a modal dialog with a filter and three sections — "Here · ‹current scope›" first, then Any link, then Global — showing the viewer's keys and conflicts, and **Edit in Keyboard settings**. Alt+F1 (`help.a11y`) opens accessibility help for the current view; Alt+F2 (`view.accessible`) the Accessible View.
- Keys only navigate or arm. No key posts or admits work; mutating verbs always go through the ActionStrip and ConfirmDialog, whatever a viewer binds.
- Settings are per viewer, stored as a diff against `keymap.json` in durable workspace state; they are never in a link. **Reset all overrides…** confirms and names how many overrides it removes.
- Surfaces: `pane` panel, `chassis` rows with `line` rules, sticky `pane` header row, selection shape on the focused row. Rows are 32px and edit buttons 24px; below 700px both are `touch-h`, and rows reflow to name, keys and scope, then status.

**Linking**

- Publishes: nothing. Changing a key never navigates, changes the selection or reloads a view.
- Follows: the sheet and which-key follow the current focus scope ("Here · Functions list"); the settings grid follows nothing.
- Renders: no entity links. Command ids are plain mono text; "Edit in Keyboard settings" is a button.
- Absent: a command with no keys says "no keys · menu only".

**Keyboard**

- The grid is an APG Grid with one tab stop: ↑/↓ rows, ←/→ cells, Home/End, Enter or Space on the ▾ button opens the row menu (APG Menu Button). The toolbar and filter come first in Tab order.
- In recording, the next chord is captured; Esc cancels; Tab leaves recording without saving.
- The which-key panel takes the next key only; Esc cancels and focus never moves.
- The sheet opens with Ctrl/Cmd+/ from anywhere; its filter has focus; Esc closes it and returns focus to where it was.

**Accessibility**

- WCAG 2.1.4 is met three ways, all visible here: every single-character key is focus-scoped (composite, code or region), the Off profile turns them all off, and any key can be remapped to include a modifier.
- Each row reads as one sentence: "Collect into worklist, list.worklist: x, any result set. Conflict with Check row. Remapped by you, default w." Glyphs are `aria-hidden`.
- A saved, refused or conflicting change is announced once in the polite region; nothing is announced per keystroke except the recording result.
- The which-key panel is `role="status"` and is read once when it appears; the sheet is a labelled modal dialog.
- Targets are 24px, 44px below 700px (2.5.8). Nothing here changes context on focus (3.2.1).

**Removes switching:** J38 "from an announcement to the result and back" goes from 4 switches to 1 with the documented region and dock keys (F6, Ctrl/Cmd+J) that the sheet surfaces in place. Learning a key no longer needs the docs or a settings page: the sheet and which-key show the viewer's own keys where the key is used (2 switches to 0). Counts before come from the journeys table; after counts are design targets.
