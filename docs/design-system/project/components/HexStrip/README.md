# HexStrip

A compact hex and ASCII strip for the current region, synchronized with the shared cursor, whose byte selection maps back to listing rows.

**Use it** under the Listing and DecompileView in CodeBrowser (the Hex view toggle) and as the Hex view of the single-view layout below 700px. It replaces opening the Hex analysis tab to see the bytes under the cursor.

**Consumer provides** the build, section and region bounds (the current function plus a row of context); bytes read from the loaded program, with undefined bytes marked; the instruction boundaries in the region (start address and length per listing row, with its decompile line); the shared cursor and the reflection set (the bytes of the cursor's statement); and the follow state (following, held, not loaded).

- Rows of 16 bytes: the row address in `address`, bytes in `type-code` mono grouped 8 + 8, then ASCII (printable 0x20–0x7e, otherwise "."). Column offsets head the strip in `ink-muted`. Undefined bytes, which have no listing row, are `ink-muted`.
- **Reflection** follows 35 and keeps the existing shape. Marks, always with the key under the strip and never color alone: statement bytes (reflection) on `raised`; cursor instruction bytes bold with a 2px `ink-strong` under-bar; selected bytes on `selection` with a 2px `accent` under-bar; the rest of a partly selected instruction on `raised` with a 2px `ink-muted` under-bar. ASCII cells mirror the byte marks.
- **Selection maps back.** Selecting bytes moves the shared cursor to the instruction that holds the first selected byte (replaceState inside one function) and lists every listing row the selection touches: an `address` link, the instruction, "whole instruction" or a dashed PARTIAL tag with "bytes 3–5 of 5", and the decompile line. The Listing marks those rows. An instruction is never split, re-disassembled or redefined from the strip.
- Undefined bytes map to nothing and say so: `fact-unknown` ∅ "No listing row. 0041b254–0041b25f are undefined bytes after ResourceRef::Resolve." The cursor stays where it was. Data bytes map to their data label's row.
- **Find matches byte patterns** and says so: Ctrl/Cmd+F in the strip takes hex bytes ("8b 4d 08"), not text, and reports "2 of 5 matches · byte pattern". Its field label and placeholder say "Byte pattern".
- The status line names the cursor instruction and its length, the statement's byte range and the read basis ("read from the loaded program · gen 42").
- It reads memory of the program that is already open. An unopened program shows `fact-unknown` ○ "Not loaded. Open to read it." with an explicit Open; follow, hover and peek never fetch it. There is no patch mode: the strip never writes bytes.
- Below a 600px container the ASCII column hides; each row's accessible name still carries its bytes. The strip scrolls horizontally inside its own well if it must.
- Both surfaces render the same rows and marks from the same memory read. The static 8080 surface may render a table with the same row names.

**Linking**

- **Publishes:** the cursor (from a byte selection) to `addr` with replaceState. The byte selection itself is view state and never in the URL. Open beside on a mapped row publishes a `hold` for the new Held pane.
- **Follows:** the primary location after the settle, as a cached pane (it reads the loaded program only); under Update panes: On Enter it commits on Enter. Holdable with Hold this pane; a held strip follows nothing.
- **Targets rendered:** row addresses and the mapped listing rows as `address` links (the Code Browser at that build and address, focus on the Listing row).
- **Peek source:** Alt+↓ reads the cached listing row of the instruction that holds the cursor byte. Nothing is disassembled or fetched.
- **Absent copy:** "No listing row" for undefined bytes; "Not loaded. Open to read it." for an unopened build.
- **Target-size exception:** byte cells are 18px cells inside a grid reached by roving focus (the inline exception for code wells); header controls are 24px, 44px below 700px, and with a coarse pointer each row has one 44px row-menu button carrying the link menu.

**Keyboard**

- APG Grid, one tab stop. ←/→ move by byte, ↑/↓ by row (16 bytes), Home/End to the row's first and last byte, Ctrl+Home/Ctrl+End to the region's start and end, PageUp/PageDown by a page.
- Shift+←/→/↑/↓ extend the byte selection. Esc follows the one order in `keymap.json` `escapeOrder`; here its transient-extent step collapses the selection to the cursor.
- **Enter** goes to the first mapped listing row: one history stop, focus moves to the Listing. **Shift+Enter** opens that row beside (a Held pane). **Alt+↓** peeks the instruction that holds the cursor byte.
- **Shift+F10** opens the one link menu (35), flat with separated groups: Open · Open beside · Peek; Reveal in (only the destinations an address resolves to: Compare, Evidence, Navigator); Copy link · Copy address · Copy bytes. Bytes are not editable, so there is no Edit group.
- Code-scope keys from `keymap.json` apply inside the strip, remappable (WCAG 2.1.4): `r` focuses the reflected row in the Listing, `x` focuses References for the cursor address, Ctrl/Cmd+F finds a byte pattern.

**Accessibility**

- `role="grid"` named "Bytes, ‹build› ‹section›, ‹start› to ‹end›", with an offset row header, 16 byte cells and an ASCII cell per row, the region's `aria-rowcount`, `aria-readonly="true"`, `aria-multiselectable` and column headers. Each row reads, under the one per-viewer **Screen-reader verbosity** value in View settings, as "0041b210: 55 8b ec 51 56 8b f1 8b 4d 08 e8 41 12 00 00 89"; the ASCII cell is its own named cell.
- **Accessible View** (Alt+F2, or the palette, the Help menu and the pane-header button, because GNOME and KDE take Alt+F2) opens the region's rows as exact text, one row per line, following the verbosity value.
- A selection change announces its mapping once in the polite region ("3 bytes selected, maps to 0041b21f"); find announces "2 of 5 matches"; moving the cursor by following announces nothing (WCAG 4.1.3).
- WCAG 3.2.1: focusing the strip or moving within it never navigates; only Enter goes.
- WCAG 1.4.1: every mark has a shape (under-bar, frame) and a key with words. Under `forced-colors` selected bytes map to Highlight, the reflection to a dashed CanvasText outline, and the cursor bar to an underline.
- The well carries `translate="no"` and isolates direction.

**Removes switching** (the plan ledger is authoritative; this strip contributes to journeys credited elsewhere):

- J15 diagnose a decompile artifact: 6 → 4, credited to the Code Browser composite (U173); the strip supplies the bytes.
- J36 from strings, imports or sections to use sites and bytes: 3 → 1, credited to typed links (U171); the strip removes the Hex-tab step.
- J34 from an image delta region to its bytes: a partial contribution only (the strip shows the differing bytes under the Listing at the range start); the journey's 4 → 1 is credited to typed links.

**Parity extensions (2026-09-29)**

Rows from the [Ghidra Code Browser parity specification](../../../../dashboard-design/2026-09-29-ghidra-code-browser-parity.md): N10, N11, L23, I03.

- **Formats (N10).** Beside hex and ASCII, the strip can show hex short, int, long and long long, signed and unsigned integer, octal, binary, chars, address and disassembled columns. The pane-header menu lists the formats; which ones appear is a per-viewer choice in OptionsPanel's Byte viewer section. Each extra format is one more column group with its own column header, and the row name reads the enabled formats in order. Formats are presentation only; the bytes and their build do not change.
- **Byte viewer options (N11).** Bytes per line, group size, alignment offset, charset and char width come from OptionsPanel (per viewer, stored as a diff, never in the URL). The pane-header menu has **Byte viewer options…**, which opens that section; the strip has no private option controls.
- **Select Bytes (L23).** The link menu on a byte has **Select bytes…** with a count field ("Select 240 bytes from 0041c880 on build-a"). The result is the same transient extent as a drag, mapped back to Listing rows, and Esc collapses it (Esc order step 5). A count that runs past the region or section end is clipped and says so.
- **Checksums (I03).** On a byte selection, the link menu's **Checksums** opens a Peek with checksum-8, -16 and -32, Adler-32, CRC-16 and CRC-32, MD5 and the SHA family over the selection, each value in mono with its algorithm, the range and the build. It is read-only and computes nothing until a catalog read action exists; until then it says "Checksums need a catalog read action; not computed". **On every build** hashes the anchor-mapped range on each build, one row per build naming the anchor used; an absent anchor reads "no anchor on build-d". Differing checksums are divergence evidence whose class is unknown unless a record states it.
- Keymap ids (registered): `hex.selectCount` (no keys; link menu and palette), `hex.checksums` (no keys). The preview is unchanged: every addition is in the pane-header or link menu.
