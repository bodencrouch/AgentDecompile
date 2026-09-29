# Listing

The continuous instruction listing: flow, address, bytes, mnemonic, operands and xref hints, with one reflected cursor shared with the DecompileView (DecompilePane in the plan), HexStrip and Graph.

**Consumer provides** rows from existing analysis and the current address; the decompile token ↔ instruction mapping when one exists; the function's name, name tier, facts and inspected build for the sticky header; xref counts per label; and any rows changed by a job since the last navigation.

- Sits in a `code-bg` well with `shadow-inset`, `type-code`. Addresses `address`, mnemonics `ink-strong`, bytes and xrefs `ink-muted`, symbol operands `lane-identity-ink`.
- **Sticky function header** per well: the name with its NameProvenance tier, the FactStrip as one Peek button, and the inspected build. It stays visible while the rows scroll; the scroll well sets `scroll-padding` so the focused row is never hidden under it.
- The current line uses `row-selected-bg` plus the 3px bar. **Reflection** is different: focusing or hovering a decompile token marks the mapped set of listing rows with a 2px `line-control` gutter bar and an `ink-strong` underline, without changing the selection. Focus, current line and reflection each look different (outline; fill plus bar; gutter plus underline), never color alone.
- **No instruction mapping**: when a statement or token maps to no row, say "No instruction mapping for this statement." and stay where you are; never jump to the function start and never fabricate a mapping.
- **Highlight all** (`h`) on a register, variable or constant marks every occurrence in every visible view with an underline style (solid, double, dashed, wavy for A–D); legend chips ("A eax · 3 in view") are buttons that remove it. Keyed by variable identity where known, otherwise by text, and the chip says which.
- **XREF[n] hints are links** to the XrefPanel for that label; call and jump targets are address links. Rows changed by a job carry a "changed by a3f9" gutter mark (a job link) until the next navigation.
- Bytes and processor context stay visible: the listing is interpreted evidence, not ground truth.
- Opening a listing never reanalyzes; an empty listing is a StateNotice, not permission to analyze again.

**Linking**

- **Publishes:** `addr` as the cursor moves inside one function (replaceState); Go on an operand, flow target or xref link pushes one history stop with `build` and `addr`.
- **Follows:** `entity`, `build`, `addr` and `views`, after the settle (a cached pane: it follows by default); reflection follows the other code views' focused token. Holdable: Hold freezes it to entity × build × address with its own Back/Forward.
- **Targets rendered:** call or jump target and symbol operand → the Code Browser at that build and address · XREF[n] → the XrefPanel for that label (`f=xref.dir:in`) · "changed by a3f9" → the dock Jobs record · the sticky header's name → NameProvenance ("Why this name"), its fact strip → a facts Peek · an indirect or unresolved operand stays plain text. Link names read "Address 0041c460, build-a, String::CStr".
- **Peek source:** Alt+↓ on an operand opens the inline peek under the line from the cached listing of the target; nothing is decompiled.
- **Absent copy:** "No instruction mapping for this statement." · "indirect · unresolved" for a computed target · "not indexed here" for xrefs · "Not loaded. Open build-c to read it."
- **Target-size exception:** spacing: operand and xref links sit in 18px code rows with one link per cell; rows remain reachable by row focus and Alt+↓.

**Keyboard**

- Virtualized read-only grid: ↑/↓ rows, ←/→ cells, PageUp/PageDown, Home/End. Enter on a row with a target goes; Shift+Enter opens beside; Alt+↓ peeks inline.
- Focus-scoped, remappable: `r` moves focus to the reflected row in the other code view ("Decompile, line 7"); `h` toggles highlight-all on the focused register or constant; `x` focuses the XrefPanel; `]` / `[` step the cursor through the panel's rows while focus stays here.

**Accessibility**

- `role="grid"`, `aria-readonly="true"`, named "Listing, build-a, ‹function›", absolute `aria-rowindex` with `aria-rowcount="-1"` when continuous; columns Address, Label, Bytes, Instruction, Operands, Xrefs/Comment. Flow glyphs are `aria-hidden` and restated as words. Reflection is silent on cursor moves and announced only on `r` ("Decompile, 3 rows mapped" or "No instruction mapping").

**Removes switching:** flipping between the Disassembly, Decompile and Xrefs tabs to relate an instruction to its statement and references (J09, J10, J13, J15).
