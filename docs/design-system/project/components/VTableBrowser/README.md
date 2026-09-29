# VTableBrowser

VTableBrowser shows a class hierarchy with its vftables per build. Each slot is keyed by logical method and shows its target on every build. It labels added slots, differing overrides, shifted slots, folded targets, adjustor thunks, and scalar and vector deleting destructors, and names the RTTI provenance behind each fact.

**Use it** from a type (`type=ResourceRef`), from a PointerWalk vftable step, and as a rail section for a virtual method. It follows the logical class, never one build's vftable address.

**Consumer provides**

- per build: the RTTI parse (Complete Object Locator, TypeDescriptor, class hierarchy and base class descriptors) or its absence (/GR-), the vftable extents, the slot targets, the adjustor thunks with deltas, and the ICF alias map (every entity at a folded address);
- the logical method for each slot, with its identity edge per build;
- the recorded source digest, toolchain and flags per build.

## Anatomy

- **Hierarchy tree** (left; stacked below 700px): classes with their bases, each with its RTTI presence per build ("RTTI a b c · d unknown"). A class with several vftables lists each sub-object ("second vftable, this − 4").
- **Slot table** (right): one row per logical method, in the inspected build's slot order.
  - The row header carries a kind label: `scalar deleting destructor ??_G`, `vector deleting destructor ??_E`, `override`, `inherited`, `new in Base`, `adjustor thunk`.
  - One cell per build holds the slot index and the target address, a counterpart link with its edge word, or a word: "slot added in build-c", "absent", "unknown".
  - "slot shifted: hypothesis, base class gained a virtual" and "override differs: hypothesis, …" are dashed cells with their basis.
- **Summary lines:** the cross-build word ("± differs: consistent pattern · build-c slots from 1 onward are +1"), then each difference class with its evidence.
- **RTTI provenance panel:**
  - COL → TypeDescriptor → hierarchy, with the evidence chip and the builds it covers;
  - builds without RTTI, whose names come only from identity edges (dashed);
  - adjustor thunks with the delta per build;
  - deleting destructors (scalar present, vector absent, and why);
  - **folded targets**: "0041c880 (build-d) belongs to 4 logical functions", each listed. One address never picks one name.

## States

- Cells: target (solid: RTTI and vftable bytes) · candidate target (edge word "candidate") · hypothesis (dashed; basis named) · "slot added in build-x" · "absent" · "unknown" (no RTTI and no edge) · "Not loaded. Open build-d to read it."
- Cross-build: `≡` same in all builds · `±` differs: consistent pattern (uniform slot shift) · `±` differs · `−` absent in build-x.
- Difference classes:
  - slot order changed is **source changed** (declaration order; hypothesis unless source digests are recorded);
  - equal order with different targets is relocation, which is not a difference;
  - a folded slot on the same source is **same source, compiled differently** (/OPT:ICF);
  - otherwise **unknown**.

Difference classes use VariantRelation's glyphs and words: `≈` same source, compiled differently (compile variance) · `∼` same source and flags, build state differs (entropy) · `≠` source changed · `?` unknown · `≡` identical. Evidence words are shared with ToolchainEvidence: **witness** or **record** (solid frame), **hypothesis (heuristic)** (dashed frame, basis named), **unknown** (italic word, no frame). A build-wide cause (a flag, LTCG, /GS, /Oy, EH model, ICF) links to ToolchainEvidence (`ws=evidence&panel=toolchain&build=…`) instead of restating its evidence.

## Linking

- **Publishes:** Enter on a slot target is Go to that build's function (a counterpart link, with the position-keeping build switch when the build differs). Enter on a class in the tree is Go to that type (`type=Base`). Shift+Enter holds the slot target beside.
- **Follows:** the primary type or the class of the selected method, after the settle. Holdable (registered hold kind `vtable`).
- **Targets rendered:** counterpart (slot targets on other builds, with edge words) · address and symbol (thunk and destructor targets) · logical id (folded entities) · type (classes in the tree; registered typed-link target) · receipt (RTTI parse receipt in the Peek).
- **Peek source:** the stored RTTI parse, the vftable extents and the ICF alias map for the slot on every build.
- **Absent copy:** "absent" · "unknown" · "slot added in build-c" · "no RTTI (/GR- recorded)" · "folded with N functions" (never one chosen name) · "contested · no winner" for a slot with two evidenced targets.
- **Target-size exception:** address links in cells are inline in 24px grid rows; tree items are 24px, and 44px below 700px or with a coarse pointer.

## Keyboard

- The tree is an APG Tree view (→ opens, ← closes or moves to the parent, `*` expands siblings). The slot table is an APG Grid with cell focus: ↑/↓ slot, ←/→ build.
- Enter goes; Alt+↓ peeks the slot on every build; Shift+F10 opens the link menu (Reveal in: Code Browser, PointerWalk, CompilerLayer).
- `g then v` (registered `code.vtables`) moves focus to VTableBrowser from a code well.

## Accessibility

- The tree and table are named ("Class hierarchy"; "ResourceRef vftable for Base, slot by logical method, target per build"). Cells read the slot index, target and state in words ("slot 2, 0041c8f0, slot shifted, hypothesis, base class gained a virtual").
- Kind labels are text; dashed outlines repeat the word "hypothesis".
- Identifiers and mangled names carry `translate="no"`.

**Research:** [MSVC transformations §6, T6, §9.7](../../../../research/2026-09-29-msvc-optimization-for-decomp.md#6-c-object-model-msvc-abi); [reference UI patterns A4, A6, C8, C11](../../../../research/2026-09-29-reference-re-ui-patterns.md).

**Prior art:** ReClass.NET `ReClass.NET/ReClass.NET/Nodes/VirtualMethodTableNode.cs`, `Nodes/VirtualMethodNode.cs` (vtable node, slot rows) · reccmp `reccmp/tools/vtable.py` (full vtable diff), `docs/annotations.md` (VTABLE, SYNTHETIC, FOLDED) · ghidra `Ghidra/Features/Base/src/main/help/help/topics/DataTypeEditors/StructureEditor.htm`.
