# MarksList

Lettered and named marks on any entity or address, and named worklists collected from any result set, stepped with F8 and Shift+F8 without leaving the current view.

**Use it** as a navigator section ("Marks and worklists"), as the target of `g '` and of the `'` prefix in go to anything, and as the stepper bar under the NavigationBar while a worklist is active. It replaces hand-kept lists of addresses and the habit of returning to a result list after every item.

**Consumer provides** per mark: its lowercase letter or its name, the target (logical entity across builds, or a concrete build and address), an optional note, the basis it was made against and whether that basis changed, and whether the target still resolves. Per worklist: id, name, the source it was collected from (review queue page and match-id cursor, Problems filter, xref results, readiness cells or any other result set) with its link and snapshot time, the ordered items with their targets, each item's done state, the current position, and whether an item was decided elsewhere. Both come from durable workspace state for this viewer.

- **Quick marks are lowercase a–z, per viewer** (`list.mark`: m then a letter; `list.jumpMark`: ' then a letter), in lists, grids and code wells. The letter is a 20px `ink-strong` framed mono glyph with the accessible name "Mark a". Setting a letter that is taken moves it and says so in the polite region ("Mark a moved from FUN_0041c880 to ResourceRef::Resolve").
- **Named marks go through the palette** ("Set mark…", also in the row menu). They carry a name instead of a letter, shown after a dashed `ink-strong` NAMED chip, and have no single key; ' then a letter reaches only lettered marks, and Ctrl/Cmd+P then ' finds both.
- **Marks carry build scope.** A scope chip (`badge-frame`, mono) says `build-a`, `build-b 0041a4a0` or `logical #88 · 4 builds`. Marks resolve per build through the locator: a logical mark jumps to the entity on the inspected build, using its LocatorGlyph status, and says so when that build has no counterpart; a build mark never silently changes the inspected build — jumping to it is an explicit build switch, announced.
- **Marks survive reload and basis changes.** They live in durable workspace state, not in the URL. A mark whose basis changed shows ◷ `fact-stale` "basis changed since marked"; one whose target no longer resolves shows ◌ "unresolved on build-d · mark kept, nothing guessed" and is not a link.
- **Worklists are collected, not typed.** `w` (`list.worklist`) on any focused result set, or **Collect into worklist…** in its toolbar, opens a small dialog: name, source link, snapshot time, and the sentence "It changes nothing in the project and starts no work." A worklist is a snapshot of that result set in its order; new rows at the source are reached through the source link, never merged in silently.
- **One active worklist** at a time, carried in the location as `wl=`. Its row in the list shows the selection shape and an **Active · F8** word chip with a 2px `ink-strong` frame.
- **Progress is position plus done, in words and units.** "4 of 12 · 3 done", never a percentage. The unit strip uses `progress-unit-done` for done items and a 2px `ink-strong` outline for the current one (it is a list position, not running work, so it does not use `progress-unit-now`). A finished list says "16 of 16 checked off", never "complete" or a celebration.
- **The stepper bar** (a toolbar with a 2px `ink-strong` top rule) names the worklist, "4 of 12 · 3 done", the current item as a typed link with its short context, and **Previous (Shift+F8)**, **Done** (`aria-pressed`), **Next (F8)** and **Stop**. Stepping moves the one primary selection and pushes one history stop; the workspace, analysis tab, split, held panes, dock and layout stay as they are.
- Items decided elsewhere (for example moved to verification by another view) stay in the list, marked "decided elsewhere · skipped by F8". At either end F8 and Shift+F8 stop and say so ("End of worklist · 12 of 12 · 9 done. F8 stops here and never wraps."). Nothing wraps or reorders silently.
- **Done** is the viewer's own checklist state. It never records a review decision, never admits work and never changes a fact. An option "mark done when stepping past" exists per viewer and is off by default.
- Rows are 28px, 44px below 700px; the item grid's done column is a 24px `ad-check` (44px below 700px). Done items keep their link, in `ink-muted`.
- Both surfaces read and write the same workspace records. The static 8080 surface may render the stepper in the status line instead of under the NavigationBar; it keeps F8, the position words and the stop at the ends.

**Linking**

- Publishes: the primary selection when a mark, item or the stepper goes (Enter, F8, Shift+F8); `wl=` for the active worklist.
- Follows: nothing. Marks and worklists are per viewer and independent of the selection; the current item follows the stepper, not the other way round. Selecting an entity that is in the active worklist moves the position to it and says so.
- Renders: symbol and address (Code Browser at that build), logical id (Compare), counterpart (entity @ build), and each worklist's source as the link that reopens that exact result set (review queue page and match-id cursor, Problems filter, xref filter, readiness cells).
- Absent: an unresolved mark target and a deleted source are words ("unresolved on build-d", "source no longer available"), never links to a guess.

**Keyboard**

- From `keymap.json`: `list.mark` m then a letter; `list.jumpMark` ' then a letter; `list.worklist` w; `worklist.next` F8 and `worklist.prev` Shift+F8 from anywhere; `leader` g then ' opens this list; Ctrl/Cmd+P then ' searches marks. Single keys act only in lists, grids and code wells and follow the viewer's profile and overrides.
- The marks and worklists grids are APG Grids with one tab stop: ↑/↓ rows, ←/→ cells, Enter goes, Shift+Enter opens beside, Alt+↓ peeks, Shift+F10 reveals in. On a worklist row Enter makes it active; on an item Space or x (`list.check`) checks Done. Removing a mark or a worklist is in the row menu (Shift+F10) and offers undo in the status line; it has no single key.
- The stepper is an APG Toolbar with one tab stop; ←/→ move between its controls. Esc from the stepper returns focus to the view it came from.

**Accessibility**

- The mark letter, scope and state are words: "Mark a, ResourceRef::Resolve, logical 88 across 4 builds". Glyphs and the bookmark shape are `aria-hidden`.
- The unit strip is `role="progressbar"` with `aria-valuetext` in words ("3 of 12 done; at item 4"). The current item row has `aria-current="true"` and the word "current".
- Each step is announced once in the polite region ("Item 4 of 12, ResourceRef::Resolve on build-a. 3 done."). Marking, moving a letter and reaching an end are announced once; nothing is announced per poll.
- Stepping changes the selection only on the key or button press (WCAG 3.2.1); focus stays where it was unless the operator goes. Targets are 24px, 44px below 700px (2.5.8). The collect dialog is a labelled modal dialog; focus returns to the invoking result set.

**Removes switching:** J17 "walk every member of a logical identity" goes from 6 switches (logical window, member, back, next member…) to 1: collect the members once, then F8. J22 "run a verb on a checked set and verify each result" goes from 7 to 2: collect the set, step with F8 while the dock stays open. J36 "bookmarks lack a jump" goes from 3 to 1 (' then the letter). Counts before come from the journeys table; after counts are design targets.
