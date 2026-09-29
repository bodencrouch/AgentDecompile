# AccessibleView

A modal plain-text mirror of what the operator is looking at, opened with Alt+F2: a read-only text area holding the exact text of the current function, range, log, peek or receipt, with its ProvenanceStamp, verbosity settings, diff words and Copy all.

**Use it** from any code well (Listing, DecompileView, HexStrip, ObjectDiff, SourceRepairDiff), log tail, Peek or receipt card: Alt+F2 anywhere, a pane-header **Accessible View** button, "Open in Accessible View" on log tails, and the palette. It is the screen-reader path to exact code text and the everyone path to exact copyable text; virtualized rows cannot be drag-selected, this can.

**Consumer provides** the source kind and its title (view, entity, build); the already-loaded text lines in display order, exactly as displayed (operands, labels as their own lines, flow restated as words, diff lines with their kind); the focused line; which ranges are not loaded; the source's ProvenanceStamp text; and the viewer's verbosity settings.

- Modal dialog on `dialog-bg`, 1px `line-control`, `shadow-popup`, over the `overlay` scrim, square corners, at most the center pane's width. Title in `type-pane-title`: "Accessible View · Listing · ResourceRef::Resolve · build-b". One sentence under it says what the text is, how much, and where Esc returns.
- The text area is a `<textarea readonly wrap="off">` in a `well` with `shadow-inset`, `type-code` 12/18 mono, `ink`. It is plain text: no color, no glyph that is not also a word, no hidden markup. It scrolls in two dimensions inside itself and can be resized vertically.
- **First lines** are the ProvenanceStamp text ("reused · existing analysis · build-b gen 42 · read 13:58:07") and a title line naming the source, range and count ("Listing, build-b, ResourceRef::Resolve, 0041b2c0 to 0041b2f7, 23 instructions").
- **Code rows** follow the verbosity settings: Address **Full | Last 4 | Off**, Bytes **On | Off** (off by default). Operands are exactly as displayed ("mov eax, dword ptr [ebp + 0x8]"). Labels are their own lines ("label ResourceRef::Resolve, 12 xrefs"); flow glyphs become words ("label LAB_0041b2e0, jump target from 0041b2c8"). Hex rows are an offset then 16 bytes.
- **Diffs** prefix every changed line with a word: "+ added", "− removed", "≠ differs" (a differing pair shows "target:" and "candidate:" lines); unchanged lines are indented to the same column. Claim boundaries keep their words ("Local zero ≠ full-image or behavior proof").
- **Logs** are exact; verbosity does not rewrite them. Only the retained, loaded tail is shown, with its run stamp.
- **Not loaded** ranges are one line of words ("Lines 1 to 411: Not loaded. Open to read it."). The view never fetches beyond what is already loaded or cached, never decompiles and never opens a program.
- The verbosity toggles are the viewer's own settings (the same ones code-well row names use); a change applies at once, keeps the caret on the same source line, and is remembered per viewer. They are `ad-seg` toggle buttons with `aria-pressed`, bold `ink-strong` plus a 2px `tab-active-rule` when pressed, never color alone.
- **Copy all** copies the text exactly as shown and says "Copied 17 lines" in the polite region. **Close** and ✕ (24px, "Close Accessible View") return focus.
- The text is a snapshot of the source when opened. If the source changes underneath, a note under the header says "◷ Source changed since opened · Reload text"; it never refreshes by itself.
- Both surfaces build the text from the same row-name template and diff words; the static 8080 surface renders the same dialog.

**Linking**

- **Publishes:** nothing. It never moves the primary location, holds or keeps, and it pushes no history stop.
- **Follows:** nothing while open: it mirrors the source captured when it opened. A change underneath shows "◷ Source changed since opened · Reload text"; it never refreshes by itself. Not holdable.
- **Targets rendered:** none inside the text area, which is plain text. The header names the source, and Esc returns to it.
- **Peek source:** none; it reads only the already-loaded text of its source (the listing rows, diff, log tail, peek or receipt in memory).
- **Absent copy:** "Lines 1 to 411: Not loaded. Open to read it." · "∅ Nothing loaded in this view".
- **Target-size exception:** none; buttons and toggles are 24px or larger, 44px below 700px.

**Keyboard**

- Alt+F2 opens it on the focused view (and closes it again). Focus starts in the text area with the caret on the line of the focused row, cell or peek line.
- In the text area: arrows, Home/End, PageUp/PageDown and Ctrl/Cmd+Home/End move the caret; Shift extends the selection; Ctrl/Cmd+A selects all; Ctrl/Cmd+C copies; browser find works because this is ordinary text.
- Tab and Shift+Tab cycle through the text area, the verbosity toggles, Copy all, Close and ✕ inside the dialog; focus does not leave the modal and F6 does not cycle regions while it is open.
- Esc closes and returns focus to the same row in the source view, or to the same index if that row is gone, never to `body`.
- Alt+F2 and Esc are listed in Keyboard shortcuts and can be remapped (WCAG 2.1.4 does not require it for modifier keys; the keymap still shows them).

**Accessibility**

- `role="dialog"` with `aria-modal="true"`, `aria-labelledby` the title and `aria-describedby` the one-sentence summary. The text area has a `<label>` naming the source ("Text of Listing, build-b, ResourceRef::Resolve").
- The mirror is the exact displayed text, so screen-reader line navigation and braille read the same characters a sighted operator sees; nothing is summarised or paraphrased.
- Diff meaning is carried by the words "added", "removed" and "differs", not by color or position.
- Identifiers carry `translate="no"`; the text area isolates direction with `unicode-bidi: isolate`.
- Controls are at least 24px; 44px below 700px, where the dialog fills the viewport width. Focus is a 2px `focus` outline; inside the text area it is inset.
- Opening and closing announce nothing beyond the dialog's own name; Copy all confirms once.

**Removes switching:** reading an off-screen or virtualized range in browse mode (scroll-and-hunt through rows) becomes 1 key, and copying an exact range (drag-select across virtualized rows) becomes 1 action, for every operator. J38, from a job-transition announcement to the result and back, goes from 4 to 1 together with regions and the keymap: the log or receipt is read in place with Alt+F2 and Esc returns to the row. J04 and J39 read log excerpts and diagnostics without opening the Logs tab line by line.
