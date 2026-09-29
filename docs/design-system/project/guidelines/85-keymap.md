# Keymap

One keymap, `keymap.json` beside `tokens.json`, drives both surfaces. Menus, tooltips, `aria-keyshortcuts`, the shortcut sheet (Ctrl/Cmd+/), Accessibility help (Alt+F1) and the KeymapSettings editor all read it, so help can never drift from behavior. Per-viewer overrides are stored as a diff against it. Keys only navigate or arm; no key posts or admits work. Mutating verbs go through the catalog action path: inline edits commit with Enter in their own named editor, everything else through the ActionStrip, with ConfirmDialog for batch, destructive or cross-build changes.

## Scopes

| Scope | Active when | Rule |
|---|---|---|
| global | always | always uses a modifier (WCAG 2.1.4) |
| region | focus is in one region | navigator, center, evidence, work view, dock |
| composite | focus is in a list, grid, tree or listbox | single keys allowed; never in text fields |
| code | focus is in a code well | single keys allowed; off in edit mode |
| edit | an editable well or inline editor is in edit mode | Tab indents; Esc leaves; other single keys off |

**Precedence:** edit > code > composite > region > global. A key bound in an inner active scope shadows the outer binding and is not a conflict. Inside a code well `x` focuses References; in a grid `x` checks the row. Code wells have no checked set.

**Typeahead.** In composites that bind single-letter commands (the Functions grid, ProblemsList, the MarksList grids, OutputsCatalog, TypeManager, TypeEditor and StackFrameEditor), typeahead starts with `/` into a visible filter field, and plain letters are commands. Elsewhere typeahead needs no prefix.

Profiles: **default**; **ida** adds focus-scoped n (rename), y (set type), ; (opens the comment editor) and d (disassemble; arms only) in code wells; **off** turns every single-character key off while modifier globals and menus remain. Go to address is `g then g` from the leader in every profile. Ghidra-style and VS Code-style profiles are deferred until each is specified against `keymap.json`.

## The keys that remove the most clicks

| Keys | Does | Replaces |
|---|---|---|
| Enter · Shift+Enter · Alt+↓ · Shift+K · Shift+F10 | Go · open beside · peek · keep (inside a Peek or card) · link menu, on every link | opening tabs and pages to look, then coming back |
| Ctrl/Cmd+P · Ctrl/Cmd+G · Ctrl/Cmd+K | the NavigationBar go-to field · the same field with `:` typed and the last address jump first · the modal palette with `>` typed. Below 1100px, where the field is collapsed, P and G open the same engine in the palette dialog | choosing the right list view before searching |
| Alt+← / Alt+→ | back and forward across workspaces, restoring focus | re-navigating after every reference |
| F6 / Shift+F6, Ctrl/Cmd+B, Ctrl/Cmd+Alt+B, Ctrl/Cmd+J | move between regions (header, navigator, center, evidence, work view, dock) with focus memory; show or hide rails and dock. Hiding the region that holds focus moves focus to its collapse strip | Tab travel and pointer trips between panes |
| F8 / Shift+F8 | next or previous item of the active worklist, from anywhere. With none, it says "No active worklist" and names the collect paths; there is no implicit default. It does nothing while an inline editor is open or the ActionStrip holds unsent edited fields | returning to a list after every item |
| F2 | rename in place: session tabs, function and label rows, and locals, parameters and labels in code wells | opening a rename dialog |
| r · h · x · ] · [ | reflected row · highlight all · references · step references | flipping between Disassembly, Decompile and Xrefs tabs |
| Alt+PageDown / Alt+PageUp | next or previous build with a counterpart | switching build tabs to compare |
| F7 / Shift+F7 | next or previous difference | scrolling diffs by hand |
| . | rebind the armed action to the focused row and focus Run; it never posts | reopening the palette for the same verb |
| g then 1…5 | layout presets (Read, Compare, Review, Triage, Verify rebuild) | dragging splitters for each task |
| Ctrl/Cmd+Z · Ctrl/Cmd+Shift+Z (Ctrl+Y on Windows and Linux) | undo or redo the build's top program transaction through the catalog (EditHistory). Never in text fields or edit mode. A single-target undo confirms in place; a batch, cross-build or multi-step undo arms ConfirmDialog; nothing posts silently | opening the edit history to take back one edit |
| p · c · a / Shift+A | walk the pointer expression at the cursor · compiler layer on or off · next or previous compiler annotation (code scope; view state only) | reading offsets and optimizer idioms by hand in each build |

**Editor-scoped keys.** TypeManager (f favourite, a scope, u uses, / find), TypeEditor (Alt+Shift+↑/↓ move, u insert undefined, d duplicate, [ array, c clear, Delete, o go to offset, Shift+H hex; Ctrl/Cmd+Z and Ctrl/Cmd+Shift+Z undo the draft only), SignatureEditor (Alt+Shift+↑/↓ move a parameter) and StackFrameEditor (Insert, c, [, Delete, Shift+H, o) bind single keys only inside their own grid, under scope precedence; the same letter in two editors' grids, or `c` in a grid and in a code well, is not a conflict. No single key ever writes: keys open, arm or change a draft, and Save or the confirm posts. `code.editSignature`, `signature.editStorage`, `code.references` (Ctrl+R reloads the page), `refs.flowOverride`, `refs.fallthrough`, `registers.*`, `code.patchInstruction`, `code.patchBytes`, `code.clear` (a single key never destroys) and `code.createData` have no default key; `code.disassemble` is `d` in the ida profile only.

**Menu and palette only.** Scripts (`scripts.open`, `scripts.runLast`), Export (`export.open`; Ctrl/Cmd+E is browser-reserved), Tool options (`options.open`; Cmd+, is the browser's on macOS), Version control (`vcs.open`), `hex.selectCount` and `hex.checksums` have no default key. Next and previous instruction, data, undefined, label, function, non-function, bookmark and brace (`code.next…` / `code.prev…`) have ids but no default keys; each is remappable.

**Compiler-aware keys (2026-09-29).** `p` (`code.walk`) and `c` (`code.compilerLayer`) were checked against precedence, the leader map, `browserReserved`, the ida profile and every code-scope single key: neither is bound in code wells, and `c` in the OutputsCatalog, TypeEditor and StackFrameEditor grids is composite scope inside those grids. IDA users know c and p as mutating commands; here they only change the view. Annotation stepping was proposed as `}` / `{`, which are also proposed in code scope for arrow source and target, so it is `a` / `Shift+A`. VTableBrowser keeps `g then v`; version control (`vcs.open`), which also proposed it, is menu and palette only, and OverviewBar's proposed `g then v` is not registered and needs another key. Every new command has a palette path.

## Leader and conflicts

`g` inside a list, grid, tree or code well shows which-key hints: regions (g n navigator, g m main, g e evidence, g w work view, g j dock at the row of the last announced transition), views (g l, g d, g h, g r), panels (g o outline, g x references, g c counterparts, g ' marks), compiler-aware panes (g t transformation timeline, g i match explanation, g f stack frame, g v vtable slots), g a the AnalyzerPanel, g p the dock's Problems tab, g b the build menu, g g go to address, and layouts (g 1…5). Leader chords work only in the composite and code scopes, never globally or in text fields. Two commands on one key in one scope do nothing until resolved, and the status line says why; shadowing by an inner scope is not a conflict. Ctrl+Alt remaps warn about AltGr keyboards. The punctuation keys `]`, `[` and `'` match the typed character, not the physical key, and accept AltGr and dead-key input.

## Esc order

Esc acts on the innermost layer that holds focus. An open modal is always that layer, because everything under it is inert. In order:

1. the topmost modal (palette, go-to list, ConfirmDialog, a full-height sheet): it closes and focus returns to its invoker;
2. the which-key hint, open Peek, sheet or menu;
3. edit mode, restoring the text;
4. the armed ActionStrip, only when focus is inside it: disarmed, with its fields kept as a draft;
5. a transient extent such as a byte range, collapsed to the cursor;
6. a transient filter typed in this view;
7. in a secondary or held pane, focus returns to the primary pane.

Esc never clears the checked set, releases held panes, removes kept cards or discards drafts. Esc never goes Back.

## Browser-reserved keys

Never bound: Ctrl/Cmd+W, T, N, L, D, E and I; Ctrl/Cmd+Shift+O (bookmarks manager); Ctrl/Cmd+F outside a code well; Ctrl+1…9; Ctrl+Tab and Ctrl+PageUp/PageDown; Ctrl+Shift+PageUp/PageDown; F5, F11, F12. Ctrl/Cmd+P and Ctrl/Cmd+F inside a code well are bound on purpose: browser print stays in the browser menu, and a second Ctrl/Cmd+F in the well's find field passes to browser find. Session tabs move from their context menu or the palette.

**Platform cautions.** Some bound keys are taken by the operating system, the browser or the keyboard on some setups. Each stays remappable, and each command stays reachable without it. KeymapSettings shows each caution beside the binding.

- F6: some browsers and screen readers take it. The `g` leader offers the same region jumps.
- F7: caret browsing in some browsers. The toolbar's difference buttons and the palette's "Next difference" do the same.
- F8: needs Fn on many macOS keyboards. The stepper buttons and the palette's "Next worklist item" do the same.
- Alt+F1 and Alt+F2: GNOME and KDE take them. Accessibility help and Accessible View stay on the palette, the Help menu and the pane-header button.
- Alt+F8: GNOME and KDE take it. It is not bound.
- Ctrl+Alt combinations: they type characters on AltGr layouts. Every such command stays on the palette and the View menu.

## Superseded

feel.md Essay AC ("Enter opens the action strip with the last action") and the single-letter global shortcuts S, O, N and G are superseded: Enter means Go, `.` rebinds the armed action to the focused row without posting, and globals carry a modifier. The ida profile's single `g` for go to address is superseded by `g then g`. Ctrl/Cmd+Alt+digit presets and the Ctrl/Cmd+Alt+0 size reset are superseded because they type characters on AltGr layouts: presets are `g then 1…5`, and Reset is in the pane-header size menu. Ctrl/Cmd+Shift+O for the outline is not bound; the outline is `g then o`, the Views toolbar's Outline button and the palette.
