# HexStrip

A compact hex and ASCII strip for the current region, synchronized with the shared cursor, whose byte selection maps back to listing rows.

**Use it** under the Listing and DecompileView in CodeBrowser (the Hex view toggle) and as the Hex view of the single-view layout below 700px. It replaces opening the Hex analysis tab to see the bytes under the cursor.

**Consumer provides** the build, section and region bounds (the current function plus a row of context); bytes read from the loaded program, with undefined bytes marked; the instruction boundaries in the region (start address and length per listing row, with its decompile line); the shared cursor and the reflection set (the bytes of the cursor's statement); and the follow state (following, held, not loaded).

- Rows of 16 bytes: the row address in `address`, bytes in `type-code` mono grouped 8 + 8, then ASCII (printable 0x20–0x7e, otherwise "."). Column offsets head the strip in `ink-muted`. Undefined bytes, which have no listing row, are `ink-muted`.
- Marks, always with the key under the strip and never color alone: statement bytes (reflection) on `raised`; cursor instruction bytes bold with a 2px `ink-strong` under-bar; selected bytes on `selection` with a 2px `accent` under-bar; the rest of a partly selected instruction on `raised` with a 2px `ink-muted` under-bar. ASCII cells mirror the byte marks.
- **Selection maps back.** Selecting bytes moves the shared cursor to the instruction that holds the first selected byte (replaceState inside one function) and lists every listing row the selection touches: an `address` link, the instruction, "whole instruction" or a dashed PARTIAL tag with "bytes 3–5 of 5", and the decompile line. The Listing marks those rows. An instruction is never split, re-disassembled or redefined from the strip.
- Undefined bytes map to nothing and say so: `fact-unknown` ∅ "No listing row. 0041b254–0041b25f are undefined bytes after ResourceRef::Resolve." The cursor stays where it was. Data bytes map to their data label's row.
- The status line names the cursor instruction and its length, the statement's byte range and the read basis ("read from the loaded program · gen 42").
- It reads memory of the program that is already open. An unopened program shows `fact-unknown` ○ "Not loaded. Open to read it." with an explicit Open; follow, hover and peek never fetch it. There is no patch mode: the strip never writes bytes.
- Below a 600px container the ASCII column hides; each row's accessible name still carries its bytes. The strip scrolls horizontally inside its own well if it must.
- Both surfaces render the same rows and marks from the same memory read. The static 8080 surface may render a table with the same row names.

**Linking**

- Publishes the cursor (from a byte selection) to the location `addr`. The byte selection itself is view state and is not in the URL.
- Follows the primary location while Following; a held strip follows nothing.
- Renders row addresses and the mapped listing rows as `address` links (Code Browser at that address).
- Absent: undefined bytes say "No listing row"; an unopened build says "Not loaded. Open to read it."

**Keyboard**

- APG Grid, one tab stop. ←/→ move by byte, ↑/↓ by row (16 bytes), Home/End to the row's first and last byte, Ctrl+Home/Ctrl+End to the region's start and end, PageUp/PageDown by a page.
- Shift+←/→/↑/↓ extend the byte selection; Esc collapses it to the cursor.
- **Enter** goes to the first mapped listing row: one history stop, focus moves to the Listing. **Alt+↓** peeks the instruction that holds the cursor byte.
- **Shift+F10** opens the menu: Copy bytes, Copy address, Go to listing row, Peek, Find references to this address, Reveal in.
- Code-scope keys from `keymap.json` apply inside the strip, remappable (WCAG 2.1.4): `r` focuses the reflected row in the Listing, `x` focuses References for the cursor address.

**Accessibility**

- `role="grid"` named "Bytes, ‹build› ‹section›, ‹start› to ‹end›", with `aria-rowcount`, `aria-multiselectable` and column headers. Each row reads as "0041b210: 55 8b ec 51 56 8b f1 8b 4d 08 e8 41 12 00 00 89"; the ASCII cell is its own named cell.
- A selection change announces its mapping once in the polite region ("3 bytes selected, maps to 0041b21f"); moving the cursor by following announces nothing (WCAG 4.1.3).
- WCAG 3.2.1: focusing the strip or moving within it never navigates; only Enter goes.
- WCAG 1.4.1: every mark has a shape (under-bar, frame) and a key with words. Under `forced-colors` selected bytes map to Highlight, the reflection to a dashed CanvasText outline, and the cursor bar to an underline.
- The well carries `translate="no"` and isolates direction. Header controls are 24px, 44px below 700px.

**Removes switching:** J36 from strings, imports or sections to use sites and bytes, 3 → 1 (the bytes are beside the Listing instead of behind Sections → Hex → Disassembly; the program-wide list is still one switch). J15 diagnose a decompile artifact loses its "Listing bytes" step, one switch fewer (6 → 5 from the strip alone). J34 from an image delta region to its bytes, 4 → 3 (the strip shows the differing bytes under the Listing at the range start).
