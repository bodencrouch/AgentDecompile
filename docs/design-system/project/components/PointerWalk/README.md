# PointerWalk

A pointer walk turns the value or expression at the code cursor, such as `this->cache->entries[i].next->name_len`, into an ordered chain of logical steps: base register or parameter, then offset, dereference, index, type and field. Each step shows the address arithmetic, the typed reading, the evidence level of that type, and every build's offset in its own cell.

**Use it** from any code well (Listing, DecompileView, SplitCompare): `p` on an operand or expression opens the walk for the cursor. It opens as a rail section scoped to the selection ("For ResourceRef::Resolve · build-b"), or in the secondary pane of the Code Browser. It is keyed by the logical entity and the logical field chain, never by one binary's address. The inspected build supplies the instruction the expression was read from, and the other builds are columns.

**Consumer provides**

- the entity, the inspected build and the cursor instruction (address, decoded operand: base, index, scale, displacement);
- the register-origin dataflow back to a parameter, `this` or a global, per build;
- for each step, the logical field or slot and its type;
- for each build, the step's offset, stride or slot, with its evidence (PDB or type record, bytes, access-pattern inference) and basis;
- the recorded source revision or digest, toolchain and flags per build, so a difference can be classed;
- the layout of the struct at the current step, per build, with padding.

## Anatomy

- **Expression line.** The chain in logical names, mono in a code well, with the current hop underlined in `ink-strong` and bold (a shape, not a color).
- **Build provenance line.** Each build with its architecture, toolchain family and whether its source identity is recorded ("build-d x86-64, another toolchain, source recorded (PDB)"), whether the entity resolves there ("ResourceRef::Resolve is unresolved on build-d"), and the rule "Offsets are keyed by logical field, never by position."
- **Steps** (an ordered list). Each step has:
  - its number;
  - an operation tag: `root`, `+offset · deref`, `index · stride`, `+offset · field`, `this-adjust thunk`, `vptr · vftable[slot]`, `deref · deref`, `union`;
  - the address arithmetic in the inspected build (`[ecx+0x14]`);
  - the typed reading (`ResourceCache* cache at +0x14`) as a typed link to the type or field;
  - the evidence chip for the type (below);
  - the cross-build comparison word;
  - the per-build cells, in corpus order. Each cell holds the build, its offset or target, and a short evidence line ("moved +8 in build-c", "+0x18, 8-byte pointer · witness · pointer width 8", "unresolved · ResourceRef::Resolve is unresolved on build-d"). The inspected build is marked "inspected", with the selection fill and bar.
  - a difference-class line when builds differ (below).
- **Other chain shapes**, drawn with the same step anatomy:
  - this-adjustor thunks: `sub ecx,N; jmp`, with the delta per build and the containing type named;
  - vtable dereference: vptr → vftable[slot] → target per build, with its identity-edge word;
  - arrays: stride per build, with the instruction that proves it;
  - pointer to pointer: two dereference hops in one step;
  - unions: both readings listed as hypotheses, and neither is picked;
  - an unresolved base: the word "unknown" and why, with nothing typed.
- **Layout strip** for the struct at the current step, in ReClass style: one lane per build, byte columns, fields as spans. The current field has a 2px `ink-strong` frame, hypothesis fields are dashed, padding is hatched and labelled "pad", bytes outside the walk read "not walked" (no frame), and "ends at 0x18" marks size. Offsets and sizes follow the shared fixture table (CacheEntry 0x18 · 0x18 · 0x1c · 0x20). The strip is `role="img"`. The **key table** under it is the accessible form: one row per logical field, one offset column per build, and the cross-build word.
- **Peek** on a step (Alt+↓) shows the type definition with a per-member provenance comment, its ProvenanceStamp (reused or fresh, which build's witness) and the name's tier.

## States

**Evidence level of a step's type** (one chip, level word first):

| Level | Drawn | Example |
|---|---|---|
| witness or record | solid frame | "WITNESS · bytes at 0041b2c3"; "WITNESS · pointer width 8"; "RECORD · type record, build-d (reused)" |
| hypothesis (heuristic) | dashed frame, basis named | "HYPOTHESIS (HEURISTIC) · access pattern: movzx of 16 bits at 4 sites" |
| unknown | no frame, italic word | "UNKNOWN · base eax is the return of call [edx+0xC]; no type" |

**Cross-build comparison** (word plus glyph, never color alone): `≡` same in all builds · `±` differs: consistent pattern (for example +8 in build-c) · `±` differs · `−` absent in build-x. The grouping key (recorded source revision) is shown on the provenance line.

**Difference class** of a differing step (four classes, each with its own evidence level):

- `≈` **Same source, compiled differently.** The cause is named: LTCG custom convention, /Zp packing, register allocation. It is solid only when source digest, toolchain and flags are recorded for both builds.
- `∼` **Same source and flags, build state differs.** This is entropy: paths, object or link order.
- `≠` **Source changed.** What changed is named: "field added", "member added before +0x10".
- `?` **Unknown.** Source and flags both differ, or no source identity is recorded.

A class inferred from instructions alone is dashed, labelled "hypothesis", and names its basis. A witnessed shift does not make its class solid: build-d's `next` at +0x18 is a witness (pointer width 8), and its class stays a hypothesis until source identity is recorded on both sides.

**Per-build cell states:** value (solid or dashed frame) · "moved ±N in build-x" · "absent in build-x" (solid `line` frame on `chassis`, italic word, and the witness for the absence when there is one; dashes stay reserved for hypotheses) · "unknown" · "unresolved · ‹entity› is unresolved on build-x; nothing is read from code" · "Not loaded. Open build-d to read it." · "slot shifted: hypothesis, ‹basis›".

**Pane states:** following · "Selection is not an address expression; nothing to walk" · "Not decompiled in this session · Enter to decompile" (the walk never decompiles on its own) · stale ("◷ types changed by job ‹id› since read").

Difference classes use VariantRelation's glyphs and words: `≈` same source, compiled differently (compile variance) · `∼` same source and flags, build state differs (entropy) · `≠` source changed · `?` unknown · `≡` identical. Evidence words are shared with ToolchainEvidence: **witness** or **record** (solid frame), **hypothesis (heuristic)** (dashed frame, basis named), **unknown** (italic word, no frame). A build-wide cause (a flag, LTCG, /GS, /Oy, EH model, ICF) links to ToolchainEvidence (`ws=evidence&panel=toolchain&build=…`) instead of restating its evidence.

## Linking

- **Publishes:** Enter on a step's type or field is Go to that type (`type=CacheEntry.name_len`), and it keeps `entity`, `build` and `addr`. Moving between steps replaces `walk=this.cache.entries[i].next.name_len:5` (registered) after the settle. Shift+Enter holds the step's type as a Held pane or kept card (`keep=type:CacheEntry.name_len@build-b`, registered kind `type`). A counterpart target in a vtable step is a counterpart link and switches the build by the position-keeping rule.
- **Follows:** the primary cursor after the settle. It follows as I move because it is cheap: it reads stored operand decomposition, dataflow and layouts only. Holdable.
- **Targets rendered:** type and field (registered typed-link target; below) · address and symbol (vtable targets, thunk targets) · counterpart (vtable slot target on another build, with its edge word) · receipt and job (in the Peek provenance) · research section (a native `/docs` link).
- **Peek source:** the stored type record and layout store for that build, the recorded witness (PDB type record, RTTI), and cached access sites. Nothing is re-typed or re-analyzed.
- **Absent copy:** "absent in build-a" (plain word, `.ad-absent`, never a link) · "unknown" · "unresolved: no dataflow origin for eax at 0041b2d4" · "Not loaded. Open build-d to read it." · union: "Conflicting uses at one offset. Neither is picked." · contested vtable target: "2 addresses · contested · no winner", with both as candidate links.
- **Target-size exception:** type links in step headers are inline text inside a 24px step row (the inline-link exception). Steps are reached by row focus. With a coarse pointer, each step has the 44px row-menu button.

## Keyboard

- `p` (registered `code.walk`, code scope) opens the walk for the cursor's expression and focuses the current step.
- The step list is a composite with one tab stop. ↑/↓ or j/k step back and forward through the chain (`list.move`), and Home/End go to the root and the last step.
- **Enter** on a step follows its dereference: Go to the step's type or field, one history stop. On a vtable step it goes to the inspected build's slot target. Shift+Enter opens it beside; Alt+↓ peeks the type definition; Shift+F10 opens the link menu (Reveal in: Code Browser, Corpus › Types, VTableBrowser, FrameLayout for stack bases).
- Tab moves from the steps to the layout key table (an APG Grid). `r` in a step moves focus to the reflected Listing row of that hop's instruction.
- Esc follows `keymap.json` `escapeOrder`.

## Accessibility

- The step list is an `<ol>` with `aria-current="step"` on the current step. Each step's accessible name is a sentence: "Step 4, offset and dereference: plus 0x10 is next, CacheEntry pointer; moved plus 8 in build-c, hypothesis; plus 0x18, 8-byte pointer, in build-d, witness".
- Evidence levels and comparison states are words; frame style and glyphs are `aria-hidden` repeats. The layout strip is `role="img"` described by the key table.
- Per-build cells are a group named "‹field› offset, per build". The inspected cell also says "inspected" in text.
- Below a 480px container the per-build columns follow NarrowFlow's build-column grid rule: one list item per step, each build a labelled line ("build-c: +0x18 · hypothesis"), with nothing scrolling sideways.
- Identifiers carry `translate="no"`. Arithmetic is spoken as rendered, and a plain-words form goes in `aria-description`.
- Forced colors: solid, dashed and none survive as border styles, and hatching becomes a dotted outline plus the word "pad".

**Research:** [MSVC transformations §9.1, §6, T6, I7](../../../../research/2026-09-29-msvc-optimization-for-decomp.md#9-ui-implications); [reference UI patterns A1, A2, A4, A6, A7](../../../../research/2026-09-29-reference-re-ui-patterns.md).

**Prior art:** ReClass.NET `ReClass.NET/ReClass.NET/Nodes/PointerNode.cs`, `Nodes/VirtualMethodTableNode.cs`, `Nodes/BaseWrapperArrayNode.cs`, `Nodes/UnionNode.cs`, `AddressParser/Parser.cs` (chain as an expression; inline expansion) · cheat-engine `Cheat Engine/StructuresFrm2.pas` (instances as columns, grouped comparison), `Cheat Engine/pointerscanworker.pas` (offset chains) · ghidra `Ghidra/Features/Base/src/main/help/help/topics/DataTypeEditors/StructureEditor.htm` (component rows, filler visible) · revng `share/doc/revng/user-manual/tutorial/editing-types-in-c.md` (fields pinned at offsets).
