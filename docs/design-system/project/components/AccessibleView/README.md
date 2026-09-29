# AccessibleView

A modal plain-text snapshot of what the operator is reading: a read-only, soft-wrapped text area holding the exact text of the current function, range, log, Peek or receipt, with its ProvenanceStamp line, diff words and Copy all.

**Purpose.** It is the screen-reader path to character-exact code text, the reflow path for code at 320 CSS px (WCAG 1.4.10), and everyone's path to exact copyable text: virtualized rows cannot be drag-selected, this can. It is also the reading path where screen-reader punctuation settings would otherwise change what is spoken.

**Invokers.** `view.accessible` (Alt+F2) anywhere; the **Accessible View** button in a pane header (Listing, DecompileView, HexStrip, ObjectDiff, SourceRepairDiff, log tails, Peeks and receipt cards); "Open in Accessible View" on log tails; the palette and the Help menu. GNOME and KDE take Alt+F2 (`keymap.json` `platformCautions`), so the palette, the Help menu and the pane-header button always remain.

**Consumer provides** the source kind and its title (view, entity, build); every row already read for that source, in display order and exactly as displayed (operands, labels as their own lines, flow restated as words, diff lines with their kind); the focused line; which ranges are not read; the source's ProvenanceStamp text and read time; whether the source is a Held pane, a Kept card or historical evidence, with its target and age; and the viewer's global screen-reader verbosity value from View settings.

- **A modal dialog.** `role="dialog"` with `aria-modal="true"` on `dialog-bg`, 1px `line-control`, `shadow-popup`, over the `overlay` scrim, square corners, at most the center pane's width. Title in `type-pane-title`: "Accessible View · Listing · ResourceRef::Resolve · build-b". One sentence under it says what the text is, how much, and where Esc returns.
- **A text area, not markup.** The text is a labelled `<textarea readonly>` in a `well` with `shadow-inset`, `type-code` 12/18 mono, `ink`. It soft-wraps (`wrap="soft"`), so it reflows at 320px. A text area cannot draw a hanging indent, so every source line starts with its address, label or diff word and a continuation line starts with neither; that is how a reader tells them apart. It is plain text: no color, no glyph that is not also a word, no hidden markup. Browser find works because this is ordinary text.
- **Buttons.** **Copy all** copies the text exactly as shown and says "Copied 17 lines" in the polite region. **Close**, and the 24px ✕ named "Close Accessible View", close it.
- **It shows what was already read.** Every row already read for the current function, range, log, Peek or receipt is included; virtualization affects the DOM, not this text. Anything not read is one line of words ("Lines 1 to 411: not read yet · load them in the pane (Enter), then reopen this view"). It never fetches, decompiles, opens a program or starts work.
- **It is a snapshot.** The first line is the ProvenanceStamp text with "as read ‹time›" ("reused · existing analysis · build-b gen 42 · as read 13:58:07"); the second names the source, range and count ("Listing, build-b, ResourceRef::Resolve, 0041b2c0 to 0041b2f7, 23 instructions"). If the basis moves while it is open, a note under the header says "◷ Basis changed since opened · Refresh". The text never changes under the caret; Refresh re-reads on request.
- **Held, Kept and historical sources are labelled.** Opened on a Held pane, a Kept card or historical evidence, the first line reads "Held · ResourceRef::Resolve @ build-c · 4 min", "Kept · receipt 7c21 · 12 min" or "historical · gen 41 · fenced; not current acceptance", followed by the ProvenanceStamp line.
- **Code rows** follow the global screen-reader verbosity value (address full, last 4 or off; bytes off by default). Operands are exactly as the Listing renders them ("mov eax, dword ptr [ebp + 0x8]"); a plain-words form of an operand belongs to the well row's `aria-description` (with an `aria-describedby` fallback), never to this text. Labels are their own lines ("label ResourceRef::Resolve, 12 xrefs"); flow glyphs become words ("label LAB_0041b2e0, jump target from 0041b2c8"). Hex rows are an offset, 16 bytes and the ASCII column.
- **Verbosity has one home.** The dialog shows the current value in words ("Verbosity: address full, bytes off") and a **View settings…** button that opens the one per-viewer group in the View menu. It has no private toggles.
- **Diff words.** Every changed line starts with a word: "+ added", "− removed", "≠ differs" (a differing pair shows "target:" and "candidate:" lines); unchanged lines are indented to the same column. Claim boundaries keep their words ("Local zero ≠ full-image or behavior proof").
- **Logs** are exact; verbosity does not rewrite them. Only the retained, loaded tail is shown, with its run stamp.
- Both surfaces build the text from the same row-name templates and diff words; the static 8080 surface renders the same dialog.

**Linking**

- **Publishes:** nothing. It never moves the primary location, holds or keeps, and it pushes no history stop.
- **Follows:** nothing while open: it is a snapshot of the source captured when it opened. A basis change shows "◷ Basis changed since opened · Refresh"; it never refreshes by itself. Not holdable.
- **Targets rendered:** none; the text area is plain text and View settings… is a button. The header names the source, and Esc returns to it.
- **Peek source:** none; it reads only the already-read text of its source (the listing rows, diff, log tail, Peek or receipt in memory).
- **Absent copy:** "Lines 1 to 411: not read yet · load them in the pane (Enter), then reopen this view" · "∅ Nothing read in this view yet" · "Basis at hold time not recorded" on a held source without a basis token.
- **Target-size exception:** none; buttons are 24px or larger, 44px below 700px and with a coarse pointer.

**Keyboard**

- Alt+F2 (or its fallbacks) opens it on the focused view. Focus starts in the text area with the caret on the line of the focused row, cell or Peek line.
- In the text area: arrows, Home/End, PageUp/PageDown and Ctrl/Cmd+Home/End move the caret; Shift extends the selection; Ctrl/Cmd+A selects all; Ctrl/Cmd+C copies.
- Tab and Shift+Tab cycle through the text area, View settings…, Copy all, Close and ✕ inside the dialog; focus does not leave the modal and F6 does not cycle regions while it is open.
- Esc follows the one Esc order in the Keymap section: the dialog is the topmost modal, so Esc closes it and returns focus to the same row in the source view, or to the same index if that row is gone, never to `body`.
- Alt+F2 is listed in Keyboard shortcuts and can be remapped.

**Accessibility**

- `role="dialog"` with `aria-modal="true"`, `aria-labelledby` the title and `aria-describedby` the one-sentence summary. The text area has a `<label>` naming the source ("Text of Listing, build-b, ResourceRef::Resolve").
- The text is the exact displayed text, so screen-reader line navigation and braille read the characters a sighted operator sees; nothing is summarized or paraphrased.
- Diff meaning is carried by the words "added", "removed" and "differs", not by color or position.
- Identifiers carry `translate="no"`; the text area isolates direction with `unicode-bidi: isolate`.
- Controls are at least 24px; 44px below 700px, where the dialog fills the viewport width. Focus is a 2px `focus` outline; inside the text area it is inset.
- Opening and closing announce nothing beyond the dialog's own name; Copy all confirms once.

**Removes switching:** no ledger credit. Reading an off-screen or virtualized range in browse mode becomes one modal read, and copying an exact range becomes one action, for every operator. J38 (4 → 2) is credited to U188 through `g j`; this view only reads the log or receipt in place. J04 and J39 read log excerpts and diagnostics without opening the Logs tab line by line.

## Behavior

- Accessible View is text by design: its text area holds the words.
- Invokers: a pane-header button, Alt+F2, the palette or the Help menu (GNOME and KDE take Alt+F2).
- Esc from the Accessible View returns focus to the focused row in the invoking pane.
- Verbosity is one per-viewer setting, not this dialog's.
- When the basis changes since opened, the text stays as read; nothing changes under the caret.
