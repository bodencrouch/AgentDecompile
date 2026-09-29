# FrameLayout

FrameLayout shows one function's stack frame per build as a vertical strip with higher addresses at the top. It covers arguments, the return address, saved registers, the EH registration node, the /GS cookie, buffers, locals, spill slots and alignment, with offsets from EBP (or normalised ESP) in one column per build, and locals linked to their decompiler variables. It flags /GS buffer ordering, slot reuse and FPO.

**Use it** as a rail section for the selected function, in the Code Browser's secondary pane, and from MatchExplain's "Stack slot or local ordering" class. Rows are keyed by logical slot (a named local, a parameter, a structural slot such as "EH node state"), never by offset.

**Consumer provides**

- per build: the prologue parse (frame base, frame size, push order), the stack-reference analysis with live ranges, the EH and SEH metadata (registration node, state slot, scope table), the GS cookie slot and buffers, and FPO data when a PDB or DBG exists;
- the logical name of each local and its decompiler variable;
- the recorded source digest, toolchain and flags per build.

## Anatomy

- **Header:** entity, the frame base in words ("offsets from EBP after the prologue").
- **Provenance line:** each build's recorded source, and "An ESP frame is shown normalised to entry ESP and says so."
- **Frame table (the strip):** higher addresses first, and a 2px `line-control` rule under the saved frame pointer. Each row has a slot-kind tag: `arg`, `return`, `saved`, `EH node`, `cookie`, `buffer`, `local`, `spill`, `align`. Then comes one offset cell per build. A cell holds the offset, a short note ("next to the cookie", "register esi", "shared with entry"), or the absence word. GS-related rows carry a 3px `ink-muted` bar at the inline start plus the `cookie` or `buffer` tag.
- **Flags** under the table, each a difference-class line with its evidence and research link:
  - **/GS buffer ordering**: buffers moved under the cookie, above scalars;
  - **Slot reuse**: two locals share a slot, with non-overlapping lifetimes;
  - **FPO**: an ESP frame, or "not applied: the C++ EH frame keeps EBP";
  - register-resident locals ("build-d keeps slotIndex in esi").
- **Second form:** a compact table for a frameless (FPO) function that shows the raw ESP offset beside the normalised one ("entry ESP+0x4 (raw [esp+0x8] after push esi)"). Frame-pointer-relative and stack-pointer-relative offsets are never compared raw.

## States

- Cells: offset (solid, from prologue bytes and references) · hypothesis (dashed outline, basis named: "shared with entry") · "register ‹reg›" · "absent in build-a" · "none" · "unknown · not decompiled".
- Frame base per build: EBP frame · ESP frame (FPO) · x64 RSP frame with home space · unknown.
- Difference classes on flags:
  - same source, compiled differently (/GS, /Oy, register allocation);
  - same source and flags, build state differs (entropy);
  - source changed (a local exists in one revision only);
  - unknown.
- Pane: follows as I move (stored prologue and reference analysis) · "Not decompiled in this session · Enter to decompile" for a build without references.

Difference classes use VariantRelation's glyphs and words: `≈` same source, compiled differently (compile variance) · `∼` same source and flags, build state differs (entropy) · `≠` source changed · `?` unknown · `≡` identical. Evidence words are shared with ToolchainEvidence: **witness** or **record** (solid frame), **hypothesis (heuristic)** (dashed frame, basis named), **unknown** (italic word, no frame). A build-wide cause (a flag, LTCG, /GS, /Oy, EH model, ICF) links to ToolchainEvidence (`ws=evidence&panel=toolchain&build=…`) instead of restating its evidence.

## Linking

- **Publishes:** Enter on a local or parameter is Go to its decompiler variable (`views=decompile`, `addr` of its first use, same build). Moving across cells replaces nothing (focus only). Keep adds the frame as a kept card (`keep=frame:‹entity›@‹build›`, registered kind `frame`).
- **Follows:** the primary entity after the settle. Holdable.
- **Targets rendered:** local and parameter (decompiler variable at a build) · address (the prologue instruction of a slot via the row menu) · research section.
- **Peek source:** the stored stack-reference analysis for that slot and build: references with their instructions and live range.
- **Absent copy:** "absent in build-a" · "none" · "register esi" · "unknown · not decompiled" · "insufficient alignment to pair slots" (after reccmp stackcmp; never a wrong mapping).
- **Target-size exception:** local links sit inline in 24px row headers; the rows are grid rows reached by focus.

## Keyboard

- An APG Grid with cell focus: ↑/↓ slot, ←/→ build column, Home/End, Ctrl+Home/End.
- Enter on a local goes to its decompiler variable; `r` moves to the reflected Listing row (the slot's first reference); Alt+↓ peeks the slot's references; Shift+F10 opens the link menu (Rename… on locals where the catalog offers it; Reveal in: DecompileView, MatchExplain).
- `g then f` (registered `code.frame`) moves focus to FrameLayout from a code well.

## Accessibility

- A table named "Stack frame of ‹entity› by logical slot, offset per build, higher addresses first". Row headers read the slot tag as words ("buffer nameBuf, 64 bytes").
- Cells read offset plus note ("minus 0x54, shared with entry, hypothesis"). The GS bar is `aria-hidden`; the tag carries the meaning.
- Flags are text lines after the table and are included in the table's description.

**Research:** [MSVC transformations T2, T8, T9, T10, I6, I8, §9.5](../../../../research/2026-09-29-msvc-optimization-for-decomp.md#9-ui-implications); [reference UI patterns A5, B5](../../../../research/2026-09-29-reference-re-ui-patterns.md).

**Prior art:** ghidra `Ghidra/Features/Base/src/main/help/help/topics/StackEditor/StackEditor.html` (the frame as a structure with signed offsets) · reccmp `reccmp/tools/stackcmp.py` (bijective and non-bijective slot pairing) · cheat-engine `Cheat Engine/StructuresFrm2.pas` (instances as columns).
