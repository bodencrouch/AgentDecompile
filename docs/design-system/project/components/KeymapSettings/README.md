# KeymapSettings

The editor for the one shared keymap, and its two runtime faces: every command from `keymap.json` with its keys, scope and status (conflicts, platform cautions, turn off, remap and reset), the which-key hint after the leader, and the keyboard shortcuts sheet. It is the one component for all three; there is no separate KeymapEditor, ShortcutSheet or ChordHint.

**Use it** as Keyboard settings on both surfaces, reached from the settings menu, the palette ("Keyboard settings") and **Edit in Keyboard settings** in the shortcuts sheet.

**Consumer provides** `keymap.json` (commands with `id`, `label`, `keys`, `scope`, `where`, `note`; `scopes`; `precedence`; `typeahead`; `punctuationKeys`; `profiles`; `escapeOrder`; `browserReserved`; `boundOnPurpose`; `conflictPolicy`; `altGrCaution`; `platformCautions`), the viewer's override diff and chosen profile, the platform (to print Ctrl or Cmd) and keyboard layout, and for the sheet and which-key the current focus scope and region. Nothing else: labels, keys and ids are never hand-written in a component.

- **One source.** Rows render from `keymap.json` in its own terms: the `label` as the command name, the `id` in mono `ink-muted` beneath it, the `keys` as `ad-kbd` chips (resolved for the platform: "Ctrl/Cmd+K" prints as Ctrl K or Cmd K), `where` as the scope detail. Menus, tooltips, `aria-keyshortcuts`, the shortcuts sheet (`help.keys`, Ctrl/Cmd+/) and Accessibility help (`help.a11y`, Alt+F1) read the same file plus the viewer's diff, so help never drifts from behavior.
- **Grouped by scope** in the file's order, each group with its command count as the file states it: Global (always a modifier or a function key), Region, Composite (lists, grids, trees, listboxes), Code (code wells; off in edit mode), Edit. Long groups show their first rows and "Show N more"; the filter searches label, id and key, and pressing keys in it finds their binding.
- **Precedence** is shown with the groups: edit > code > composite > region > global. A key bound in an inner active scope shadows the outer binding and is **not** a conflict; the row says "shadows ‹command› in ‹scope›" in `ink-muted`. Inside a code well `x` focuses References; in a grid `x` checks the row.
- **Profiles** are a segmented control: Default, the second profile (focus-scoped n, y and ; in code wells) and Off (every single-character key off; modifier globals and menus remain). Go to address is `g then g` from the leader in every profile. Commands owned by an inactive profile are listed with dashed key chips and "profile only · inactive in Default".
- **Status per row**, glyph plus word, never color alone:
  - "default"; "remapped by you, default w";
  - ⇄ `fact-failed` "Conflict with ‹label›" when two commands share a key in the same scope;
  - ⇄ `fact-stale` for a caution the platform can predict: `altGrCaution` (a binding that uses Ctrl+Alt types characters on AltGr keyboards), and each `platformCautions` entry (F6 taken by some browsers and screen readers; F7 caret browsing; F8 behind Fn on many macOS keyboards; Alt+F1 and Alt+F2 taken by GNOME and KDE), with its fallback path from the file;
  - a layout hint on `]`, `[` and `'`: "matches the typed character; AltGr and dead keys accepted";
  - an **Off** chip (dashed frame) with "turned off by you · menu keeps it"; "no keys · menu only" (for example `tabs.move`); "native browser behavior · not remappable" for `link.newTab`.
- **Conflicts never guess** (`conflictPolicy`). Two commands bound to the same key in the same scope do nothing until the conflict is resolved, and the status line says which binding is blocked and why; the row menu explains both meanings and offers **Remap…**, **Add another key…**, **Turn off**, **Reset to default** and "Take ‹key› from ‹other command›".
- **Recording** puts the keys field in a 2px `ink-strong` frame with "Recording. Press other keys; Esc cancels." The result is checked live against the keymap, `browserReserved` and the platform cautions: a reserved key is refused with ✕ and "Ctrl/Cmd+D is browser-reserved and is never bound", and Save stays disabled. Esc always cancels recording; it is never recorded.
- **Under the grid**, rendered from the file: the `escapeOrder`, the conflict and AltGr rules, the browser-reserved list and the platform cautions with their fallbacks. Esc never clears the checked set, releases held panes, removes kept cards, discards drafts or goes Back, in any profile.
- **Which-key hint.** After the leader (`leader`, g) in a focused composite or code well, and after the viewer's delay (Off, `chord-hint-delay` 500ms, or at once), a `dialog-bg` panel with `shadow-popup` anchors below the focused row. It is grouped as the `leader` note groups it: Regions (n navigator, m main, e evidence, w work view, j dock at the last announced transition), Views (l listing, d decompile, h hex, r graph), Panels (o outline, x references, c counterparts, ' marks), Dock (p Problems), b build menu, g go to address, and Layouts (1 Read, 2 Compare, 3 Review, 4 Triage, 5 Verify rebuild), then Esc cancel, naming the entity it will act on. It waits for the next key with no timeout (WCAG 2.2.1), never covers the focused row, and a wrong key closes it and says "g q: no such jump" in the status line. Where the browser takes F6, g then n, m, e, w or j gives the same region jumps.
- **Keys the other components rely on**, as the file states them: Keep is the Keep button, or Shift+K only while focus is inside a Peek or evidence card, never on list rows where k moves; layouts are g then 1…5 (`layout.preset`; Ctrl/Cmd+Alt+digit was rejected for AltGr keyboards, and `aria-keyshortcuts` cannot express the sequence, so menus show it as text and in `aria-describedby`); marks are m and ' then a lowercase letter, named marks through the palette; worklists step with F8 and Shift+F8.
- **Shortcuts sheet** (`help.keys`, Ctrl/Cmd+/; also the Help menu and the palette words "keys" and "shortcuts"): a modal dialog with a filter and three sections, "Here · ‹current scope›" first, then Any link, then Global, showing the viewer's keys, conflicts and cautions, and **Edit in Keyboard settings**. Accessibility help (`help.a11y`, Alt+F1) opens help for the current view; Accessible View (`view.accessible`, Alt+F2). Where the desktop takes Alt+F1 or Alt+F2, the palette, the Help menu and the pane-header button remain.
- Keys only navigate or arm. No key posts or admits work; mutating verbs go through the catalog action path (inline editors confirm in place with Enter; the ActionStrip's Run posts; ConfirmDialog for batch, destructive and cross-build changes), whatever a viewer binds.
- Settings are per viewer, stored as a diff against `keymap.json` in durable workspace state beside the View settings; they are never in a link or in browser storage. **Reset all overrides…** confirms and names how many overrides it removes.
- Surfaces: `pane` panel, `chassis` rows with `line` rules, sticky `pane` header row, selection shape on the focused row. Rows are 32px and edit buttons 24px; below 700px and with a coarse pointer both are `touch-h`, and rows reflow to name, keys and scope, then status.

**Linking**

- **Publishes:** nothing. Changing a key never navigates, changes the selection or reloads a view. Overrides are a per-viewer diff in durable workspace state.
- **Follows:** the sheet and which-key follow the current focus scope ("Here · Functions list"); the settings grid follows nothing. Not holdable.
- **Targets rendered:** no entity links. Command ids are plain mono text; "Edit in Keyboard settings" is a button.
- **Peek source:** none.
- **Absent copy:** "no keys · menu only" · "turned off by you · menu keeps it" · "not remappable" · each platform caution's fallback ("the palette, the Help menu and the pane-header button").
- **Target-size exception:** none; edit buttons are 24px and rows 32px; 44px below 700px and with a coarse pointer.

**Keyboard**

- The grid is an APG Grid with one tab stop: ↑/↓ rows, ←/→ cells, Home/End, Enter or Space on the ▾ button opens the row menu (APG Menu Button). The toolbar and filter come first in Tab order. The grid binds no single letters, so typeahead needs no `/` prefix.
- In recording, the next chord is captured; Esc cancels; Tab leaves recording without saving.
- The which-key panel takes the next key only; Esc cancels and focus never moves.
- The sheet opens with Ctrl/Cmd+/ from anywhere; its filter has focus; Esc closes it and returns focus to where it was (the one Esc order, `escapeOrder`).

**Accessibility**

- WCAG 2.1.4 is met three ways, all visible here: every single-character key is focus-scoped (composite, code or region), the Off profile turns them all off, and any key can be remapped to include a modifier.
- Each row reads as one sentence: "Collect into worklist, list.worklist: x, any result set. Conflict with Check row. Remapped by you, default w." Glyphs are `aria-hidden`.
- A saved, refused or conflicting change is announced once in the polite region; nothing is announced per keystroke except the recording result.
- The which-key panel is `role="status"` and is read once when it appears; the sheet is a labelled modal dialog.
- Targets are 24px, 44px below 700px (2.5.8). Nothing here changes context on focus (3.2.1).

**Removes switching:** J38 ("from an announcement to the result and back") goes from 4 switches to 2 with "Go to last announcement" (`g j`) to the job row, Go and Back, credited to U188; Ctrl/Cmd+J only shows or hides the dock. For J22 the keymap is error prevention, not fewer switches: a stray Esc no longer drops the checked set. Learning a key no longer needs the docs or a settings page: the sheet and which-key show the viewer's own keys where they are used.
