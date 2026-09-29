# Keymap

One keymap, `keymap.json` beside `tokens.json`, drives both surfaces. Menus, tooltips, `aria-keyshortcuts`, the shortcut sheet (Ctrl/Cmd+/), Accessibility help (Alt+F1) and the KeymapSettings editor all read it, so help can never drift from behavior. Per-viewer overrides are stored as a diff against it. Keys only navigate or arm; no key posts or admits work, and mutating verbs always go through the ActionStrip and ConfirmDialog.

## Scopes

| Scope | Active when | Rule |
|---|---|---|
| global | always | always uses a modifier (WCAG 2.1.4) |
| region | focus is in one region | navigator, center, evidence, work view, dock |
| composite | focus is in a list, grid, tree or listbox | single keys allowed; never in text fields |
| code | focus is in a code well | single keys allowed; off in edit mode |
| edit | an editable well or inline editor is in edit mode | Tab indents; Esc leaves; other single keys off |

Profiles: **default**; **ida** adds focus-scoped n, y, ; and g in code wells; **off** turns every single-character key off while modifier globals and menus remain.

## The keys that remove the most clicks

| Keys | Does | Replaces |
|---|---|---|
| Enter · Shift+Enter · Alt+↓ · K · Shift+F10 | Go · open beside · peek · keep · reveal in, on every link | opening tabs and pages to look, then coming back |
| Ctrl/Cmd+P | go to anything, with scope prefixes | choosing the right list view before searching |
| Alt+← / Alt+→ | back and forward across workspaces, restoring focus | re-navigating after every reference |
| F6 / Shift+F6, Ctrl/Cmd+B, Ctrl/Cmd+Alt+B, Ctrl/Cmd+J | move between regions; show or hide rails and dock | Tab travel and pointer trips between panes |
| F8 / Shift+F8 | next or previous item of the active worklist, from anywhere | returning to a list after every item |
| r · h · x · ] · [ | reflected row · highlight all · references · step references | flipping between Disassembly, Decompile and Xrefs tabs |
| Alt+PageDown / Alt+PageUp | next or previous build with a counterpart | switching build tabs to compare |
| F7 / Shift+F7 | next or previous difference | scrolling diffs by hand |
| . | repeat the armed action on the focused row | reopening the palette for the same verb |
| Ctrl/Cmd+Alt+1…5 | layout presets | dragging splitters for each task |

## Esc order

Esc closes the innermost thing first: the open peek or menu; then edit mode (restoring the text); then the dialog (focus returns to its invoker); then a transient filter typed in this view. Esc never clears the checked set or held panes.

## Browser-reserved keys

Never bound: Ctrl/Cmd+W, T, N, L, D, E and I; Ctrl/Cmd+F outside a code well; Ctrl+1…9; F5, F11, F12. Where a browser or screen reader takes F6, the `g` leader in a composite offers the same region jumps with which-key hints.

## Superseded

feel.md Essay AC ("Enter opens the action strip with the last action") and the single-letter global shortcuts S, O, N and G are superseded: Enter means Go, `.` repeats the armed action, and globals carry a modifier.
