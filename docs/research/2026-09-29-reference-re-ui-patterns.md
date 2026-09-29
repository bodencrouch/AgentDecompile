# Reference RE and compiler UI patterns for a multi-build workbench

Date: 2026-09-29. Status: design research only. Nothing here was implemented, and
nothing here was verified at runtime.

This note pulls reusable interaction and visual patterns out of published
reverse-engineering, matching-decompilation and compiler-inspection tools. It covers
four concerns:

- (a) walking pointers and memory layouts;
- (b) showing what a compiler or optimizer did;
- (c) comparing one function across builds;
- (d) presenting project outputs.

It adds to the reference table in [FRONTEND_INTENT.md §7](../FRONTEND_INTENT.md#7-reference-projects-what-belongs-in-this-product)
and does not replace it.

## Method and evidence limits

**Upstream source, read directly.** Shallow clones of the repositories below were
read without running them. Citations give a path relative to the clone root, such as
`objdiff/objdiff-core/src/diff/code.rs`, plus a GitHub link. Short commit and commit
date for each clone:

| Clone | Commit | Date |
|---|---|---|
| ReClass.NET | `a02fcb9` | 2023-07-03 |
| cheat-engine | `ec45d5f` | 2025-04-19 |
| compiler-explorer | `e37d928` | 2026-09-28 |
| reccmp | `e91a51b` | 2026-09-21 |
| objdiff | `fba10a6` | 2026-08-29 |
| objdiff-web | `17e4b37` | 2026-07-10 |
| decomp.me | `4ab701a` | 2026-09-27 |
| decomp.dev | `e9c086a` | 2026-09-06 |
| decompiler-explorer | `3873107` | 2026-09-28 |
| capa | `f3765cd` | 2026-09-08 |
| revng | `9a62385` | 2026-09-25 |
| rzweb | `a60cb74` | 2026-09-02 |
| mizuchi | `25eaef4` | 2026-08-17 |
| ghidra (help topics) | `9d9b5de` | 2026-09-28 |
| idarem | `0bb38f5` | 2026-08-04 |
| ai-reverse-engineering | `741520f` | 2026-07-25 |
| apkman | `8abc6e6` | 2026-03-06 |
| r2web | `06baecd` | 2026-07-16 |
| grapefruit | `d16322f` | 2026-08-11 |

**Web sources.** These were used for tools whose UI is closed or documented only on
the web: IDA, Binary Ninja, BinDiff, LLVM, the Cheat Engine help pages, and the
ReproBit docs. Some web pages were read through a summariser, so short quotes may be
paraphrased; the cited URL is the authority.

**Sources skipped.** AI-generated wikis about these repositories were not used.

**Inference.** Anything marked **inference** is a design proposal without an upstream
source.

**Not read or run.** Nothing under this repository's `src/`, static, React or Vite
frontend code was read. No tests, builds or servers were run.

**Names.** Examples use generic names: `build-a`…`build-d`,
`ResourceRef::Resolve`, `CacheEntry.name_len` and `FUN_0041c880`. Some upstream URLs
contain organisation names. They appear only as links.

## Premise the patterns are judged against

The project holds several builds, `build-a`…`build-d`, that are variants of one
application. They can differ in four ways:

- toolchain;
- flags;
- link settings;
- source revision (older, newer or modified).

So every view is keyed by a **logical entity**, and a build is a column or facet of
that entity, never the page's root. A logical entity is one of:

- a function, such as `ResourceRef::Resolve`;
- a type, such as `CacheEntry`;
- a field, such as `CacheEntry.name_len`;
- a global.

An address like `FUN_0041c880` is an attribute of *(entity, build)*.

Every cross-build difference should end up in one of four variance classes:

| Class | Meaning | Typical evidence |
|---|---|---|
| **compile variance** | Same source, different toolchain, flags or link settings | Register choice, instruction order, relocation targets, padding from packing flags, inlining, frame layout, cookie or EH scaffolding, identical-code folding. Recorded source identity is equal and toolchain or flags differ. |
| **entropy variance** | Same source, same declared toolchain and flags, but incidental build state differs | Paths, declaration or object order, debug state, link order. See B8. |
| **source variance** | Source changed | Different control flow, call set, constants or field set. Recorded source revision or file digest differs. |
| **unknown** | Cannot tell yet | Source identity is missing for one side, or the evidence conflicts. |

**Inference, applied throughout:** machine code alone cannot always tell these
classes apart. A reliable split needs recorded provenance for each build:

- source digest;
- toolchain identity;
- flags;
- link inputs.

The UI should show the class together with its evidence. A class inferred only from
instruction patterns should be labelled *heuristic*.

---

## (a) Walking pointers and memory layouts

### A1. The address as an editable expression; each hop as one row that expands in place

**Source.**

- ReClass.NET accepts a formula in a class's address field:
  - `<Program.exe> + 0x123` adds an offset to a module base;
  - `[addr]` dereferences;
  - `[<Program.exe> + 0xDE] - AB` reads a pointer and then subtracts;
  - reads can nest, with integer `+ - * /`.

  [README, Tips](https://github.com/ReClassNET/ReClass.NET#tips).
- ReClass.NET draws a pointer row, in order, as:
  - an open/close icon;
  - a pointer icon;
  - a 4-hex-digit offset and an absolute address;
  - `Ptr`, the name, and a *change-type* icon;
  - `-> 0x<value>`, a `//` comment, and an invalid-memory indicator.

  When the row is expanded, the target node is drawn **inline and indented**, with the
  context address rebased to the pointer value.
  `ReClass.NET/ReClass.NET/Nodes/PointerNode.cs`, helpers in `Nodes/BaseNode.cs`
  (`AddAddressOffset`, `AddComment`, `DrawInvalidMemoryIndicatorIcon`)
  ([GitHub](https://github.com/ReClassNET/ReClass.NET/blob/master/ReClass.NET/Nodes/PointerNode.cs)).
- ReClassEx accepts `module+0x40` in address nodes
  ([ReClassEx](https://github.com/ajkhoury/ReClassEx)).

**Generalising to N builds.** Write the chain in logical terms, for example
`[cacheRoot] -> CacheEntry[+i] -> .name_len`. Keep the row grammar
(offset | type | name | `->` value | comment), but give each build its own
offset/value cell. Expansion follows the *logical type*; each build's column rebases
to its own pointer value.

**Telling the classes apart.** Suppose a hop's offset differs between builds and the
field sequence is the same:

- if the builds' packing or alignment flags differ, suspect compile variance;
- if they do not, the difference is unexplained.

A field inserted before the hop means source variance. Show the reason next to the
differing cell (**inference**).

**Pitfalls.** A single address box and single value column make the design revolve
around one binary. Integer-only arithmetic truncates silently, so show the width of
each dereference.

### A2. Layout table with one row per component and filler shown

**Source.** Ghidra's structure editor has these features:

- component rows with *Offset, Length, Mnemonic, DataType, Name, Comment*;
- in non-packed mode, "all bytes are accounted for by the displayed components";
- a bit-level view whose colours separate defined bitfields, conflicts and undefined
  bits, with dotted padding bits;
- packing and alignment controls, and a read-only *Alignment* field;
- a hex/decimal toggle (Shift-H);
- text search across columns.

`ghidra/Ghidra/Features/Base/src/main/help/help/topics/DataTypeEditors/StructureEditor.htm`
([GitHub](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DataTypeEditors/StructureEditor.htm)).

**Generalising to N builds.** Keep one row set keyed by field identity. Add an offset
or size column for each build, and collapse them into one when all builds agree.
Padding rows are per build, because the same source pads differently under
`/Zp1…/Zp16`.

**Telling the classes apart.** Equal field lists with different padding, size or
alignment are compile variance. A field present in only some builds is source
variance.

**Pitfalls.** Hiding filler hides the evidence that matters most.

### A3. Gaps as markers, plus "create a member where code accesses it"

**Source.**

- Binary Ninja:
  - shows gaps as `??`;
  - annotates code accesses to unmapped offsets as `__offset(0x8).q`;
  - *S* creates the member at that offset;
  - right-clicking the struct name creates members at every accessed offset;
  - *Show Inherited Members* displays base-class members.

  [Binary Ninja types](https://docs.binary.ninja/guide/types/basictypes.html)
- Ghidra's *Auto Create Structure* and *Auto Fill in Structure* stop at offset 0x1000.
  [issue #4879](https://github.com/NationalSecurityAgency/ghidra/issues/4879),
  [FillOutStructureHelper](https://ghidra.re/ghidra_docs/api/ghidra/app/decompiler/util/FillOutStructureHelper.html)
- rev.ng pins fields with `_STARTS_AT(N)` and `_SIZE(N)`. Its decompiled output
  changes from `argument_0->offset_8` to named fields.
  `revng/share/doc/revng/user-manual/tutorial/editing-types-in-c.md`
  ([GitHub](https://github.com/revng/revng/blob/develop/share/doc/revng/user-manual/tutorial/editing-types-in-c.md))

**Generalising to N builds.** Combine accesses from every build into one gap map. Each
offset gets per-build chips showing which builds access it and at what width.

**Telling the classes apart.** An offset accessed only in `build-c`:

- with the same source revision, is probably exposed by inlining (compile variance);
- with a newer revision, may be a new field (source variance).

**Inference.**

**Pitfalls.** Auto-created members turn guesses into facts; mark them *inferred* until
corroborated. Width conflicts at one offset should show as conflicts.

### A4. Interior pointers and this-pointer adjustment written explicitly

**Source.**

- IDA declares a shifted pointer as `int *__shifted(mystruct,20)` and renders the
  access as `ADJ(p)->field`.
  [Igor's tip #54](https://hex-rays.com/blog/igors-tip-of-the-week-54-shifted-pointers)
- Cheat Engine's pointer scanner exposes *Also scan for negative offsets* and *First
  element of pointerstruct must point to module (e.g vtable)*. Negative offsets and
  vtable-first objects are routine in adjusted or base-class pointers.
  `cheat-engine/Cheat Engine/PointerscannerSettingsFrm.lfm`
  ([GitHub](https://github.com/cheat-engine/cheat-engine/blob/master/Cheat%20Engine/PointerscannerSettingsFrm.lfm))

**Generalising to N builds.** Put a per-build delta badge (`this - 0x10 → Base`) on
thunks and adjusted calls. Link a differing delta to the A2 base-layout row that
explains it.

**Telling the classes apart.** A different delta with the same base list and sizes is
compile variance. A changed base list is source variance.

**Pitfalls.** Raw `p - 0x10` arithmetic in pseudocode hides a base-object address.
Always name the containing type.

### A5. The frame as a pseudo-structure with signed offsets

**Source.**

- IDA shows the stack frame as a nameless structure:
  - offsets are relative to the frame pointer, positive and negative;
  - the special members `r` and `s` stand for the saved return address and saved
    registers.

  [Igor's tip #65](https://hex-rays.com/blog/igors-tip-of-the-week-65-stack-frame-view)
- Binary Ninja has a *Stack* panel and a *Variables* panel that tags variables R, S, F
  or D.
  [Binary Ninja guide](https://docs.binary.ninja/guide/index.html)

**Generalising to N builds.** Show the frame as an A2 table. Rows are locals keyed by
logical name (for example `slotIndex`), with the slot and the R/S tag per build.

**Telling the classes apart.** Frame size and slot order depend on the compiler, so
treat them as compile variance by default. A local that exists in only one build,
with no inlining explanation, suggests a source change.

**Pitfalls.** Frame-pointer-relative and stack-pointer-relative offsets cannot be
compared directly. Normalise them and state the base.

### A6. Vtable, array and instance nodes; typed guesses in the comment gutter

**Source.** ReClass.NET node rendering:

- `VTable[n]` (`Nodes/VirtualMethodTableNode.cs`);
- `Instance <Type>` for embedded instances (`Nodes/ClassInstanceNode.cs`);
- arrays as `Type Name[Count](CurrentIndex) <Size=N>`, stepping through one element at
  a time (`Nodes/BaseWrapperArrayNode.cs`);
- hex nodes whose comment shows *guesses* as float, integer, pointer, RTTI,
  `module!symbol`, string or plugin info, each switchable
  (`ShowCommentFloat…ShowCommentPluginInfo`, `Nodes/BaseHexCommentNode.cs`).

All paths are under `ReClass.NET/ReClass.NET/`
([GitHub](https://github.com/ReClassNET/ReClass.NET/tree/master/ReClass.NET/Nodes)).
The README also lists *Pointer Preview*, *Highlight changed memory*, PDB types and C++
or C# code generation
([README](https://github.com/ReClassNET/ReClass.NET#features)).

**Generalising to N builds.** Key vtable slots by *logical method*; slot index and
target are per build. The array index cursor is shared across build columns, so row
*i* lines up.

**Telling the classes apart.** A reordered slot usually means a source change
(declaration order). The same order with different targets is relocation
(**inference**).

**Pitfalls.** *Highlight changed memory* is a live-process signal. A static "differs
across builds" signal is different and must not share its colour. Typed guesses must
stay visually distinct from declared types.

### A7. Compare instances in groups with a three-state match colour

**Source.** Cheat Engine's *Dissect data/structures* places several addresses side by
side and lets the user sort them into groups
([help](https://cheatengine.org/help/dissect-datastructures.htm)).
The source defines exactly three comparison colours
(`cheat-engine/Cheat Engine/StructuresFrm2.pas`, `fNoMatchColor`,
`fAllMatchColorSame`, `fAllMatchColorDiff` and their *highlighted* variants,
configured as `differentText`, `groupequalText` and `groupDifferentText`):

- **NoMatch**: "not all elements have the same" value within a group;
- **AllMatchSame**: "all groups have matching elements AND the same value";
- **AllMatchDiff**: "all groups have matching elements but different values between
  groups".

([GitHub](https://github.com/cheat-engine/cheat-engine/blob/master/Cheat%20Engine/StructuresFrm2.pas))

**Generalising to N builds.** This is the closest precedent for the premise. Make each
build an instance, and group builds by recorded source revision.

**Telling the classes apart.** With groups = source revision, the three colours map
directly to the variance classes (**inference**, a mapping of the source):

- *AllMatchSame* = invariant;
- *NoMatch* = compile or entropy variance inside a same-source group;
- *AllMatchDiff* = source variance.

**Pitfalls.** The mapping only holds when groups really are source revisions. Show the
grouping key in the legend.

### A8. Pointer-path robustness through rescan and intersection

**Source.** Cheat Engine's pointer scanner:

- result columns are *Base Address*, *Offset 0…n* and *Points to*
  (`cheat-engine/Cheat Engine/pointerscannerfrm.pas`, `rsBaseAddress`, `rsOffset`,
  `rsPointsTo`);
- options include *Compare results with other saved pointermap(s)*, *Pointers must end
  with specific offsets*, *No looping pointers*, *Only find paths with a static
  address*, *Max level* and *Maximum offset value*
  (`PointerscannerSettingsFrm.lfm`);
- a rescan filters out paths that no longer resolve
  ([help](https://cheatengine.org/help/pointer-scan.htm)).

**Generalising to N builds.** Resolve each candidate chain in every build, and keep
chains that are "valid in k/N builds". *Must end with specific offsets* maps onto
"must end at field `CacheEntry.name_len`", written by field identity rather than by
number.

**Telling the classes apart.** Chains that break exactly in the builds sharing a flag
point to compile variance. Chains that break at a source boundary point to source
variance.

**Pitfalls.** Candidate explosion. Show counts, and virtualise the list.

### A9. Field-level cross-references with direction, kind and coverage

**Source.**

- IDA xrefs have the columns *Direction, Type, Address, Text* and the kind letters `r`,
  `w`, `o`, `j` and `p`; they also work on struct and stack members
  ([tip #16](https://hex-rays.com/blog/igor-tip-of-the-week-16-cross-references),
  [#17](https://hex-rays.com/blog/igor-tip-of-the-week-17-cross-references-2)).
  Decompiler global xrefs (Ctrl-Alt-X) list uses as pseudocode lines. The list "may
  be empty or include only recently decompiled functions" until refreshed
  ([tip #18](https://hex-rays.com/blog/igors-tip-of-the-week-18-decompiler-and-global-cross-references)).
- Binary Ninja filters xrefs by direction, category and regex, and reports
  `Filter (<filtered>/<total>)`
  ([guide](https://docs.binary.ninja/guide/index.html)).
- RzWeb's `XrefsView` row shows the address, the uppercase type and click-to-seek
  (`rzweb/src/components/views/XrefsView.tsx`,
  [GitHub](https://github.com/IndAlok/rzweb/blob/main/src/components/views/XrefsView.tsx)).

**Generalising to N builds.** Group xrefs to `CacheEntry.name_len` by referencing
*logical function*, with a build-presence strip on each row. Show filtered/total per
build.

**Telling the classes apart.** A reader present in only some builds of the same source
usually comes from inlining.

**Pitfalls.** An incomplete set shown as complete. Show coverage, for example
"decompiled 812/1 204 functions in build-b".

### A10. Entity addresses as a location grammar; one model with provenance and sync state

**Source.**

- rev.ng's PTML defines typed *locations* for navigation:
  - `/function/<MetaAddress>`;
  - `/type-definition/<Kind>-<ID>`;
  - `/struct-field/<Kind>-<ID>/<Offset>`;
  - `/local-variable/<Function>/<Index>`;
  - `/instruction/<Function>/<Block>/<Insn>`;
  - and others.

  It also defines *actions* (`rename`, `comment`, `codeSwitch`, `editType`) and which
  actions each location supports. PTML "degrades into plain text by stripping all the
  XML elements".
  `revng/share/doc/revng/references/ptml.md`
  ([GitHub](https://github.com/revng/revng/blob/develop/share/doc/revng/references/ptml.md))
- In rev.ng, artifacts are cached, and "making changes to the model automatically
  invalidates the parts of the cache affected by the change"
  (`user-manual/key-concepts/artifacts-and-analyses.md`).
- rev.ng's `MetaAddress` carries an `Epoch`, for "different code at different points
  in time" at the same address (`user-manual/key-concepts/metaaddress.md`).
- Ghidra's Data Type Manager tags types with their source archive. It tracks
  *Update / Commit / Revert* sync state and renames colliding types with `.conflict`.
  `ghidra/…/DataTypeManagerPlugin/data_type_manager_description.htm`
  ([GitHub](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DataTypeManagerPlugin/data_type_manager_description.htm))

**Generalising to N builds.**

- Copy the location grammar, but key it by *logical id plus an optional build facet*:
  `/struct-field/CacheEntry/name_len@build-b`.
- An `Epoch`-like build component on addresses is a direct precedent for
  "same number, different thing".
- Action sets per location carry over: a `codeSwitch` becomes "same entity, other
  build or other view".

**Telling the classes apart.** A per-build *layout override* ("`/Zp1` in build-d") is
compile variance. A per-revision *definition fork* is source variance. Keep the two
mechanisms separate (**inference**).

**Pitfalls.**

- PTML keys `struct-field` by offset. Across builds, offsets change under packing, so
  key by field identity and keep offset as a per-build attribute (**inference**).
- Automatic `.conflict` renames multiply types silently.

---

## (b) What the compiler or optimizer did

### B1. Source-line ↔ output correlation by colour and by live hover-linking

**Source.** Compiler Explorer:

- "each line is highlighted with a different colour, and … the resulting assembly … is
  highlighted with the same colour"
  ([WhatIsCompilerExplorer](https://github.com/compiler-explorer/compiler-explorer/blob/main/docs/WhatIsCompilerExplorer.md));
- colour schemes are declared with a count and theme, including *Earth tones
  (colourblind safe)* and *Greens and blues (colourblind safe)*
  (`compiler-explorer/static/colour.ts`);
- moving the cursor in the source editor emits `panesLinkLine`
  (`static/panes/editor.ts` `tryPanesLinkLine`; `static/event-map.ts`);
- the compiler pane then adds `linkedCode` decorations, separating *directly linked*
  lines (column-precise) from *linked* lines (`static/panes/compiler.ts`);
- filters hide unused labels, library functions, directives and comments
  ([godbolt.org](https://godbolt.org/)).

([GitHub](https://github.com/compiler-explorer/compiler-explorer/tree/main/static/panes))

**Generalising to N builds.** One source pane, with the link event fanned out to one
output column per build. Each source line gets a per-build strip of instruction
count. Zero in `build-b` but non-zero in `build-a` means the line was inlined
elsewhere or eliminated.

**Telling the classes apart.** This needs line tables for each build. Inferred
mappings must be labelled.

**Pitfalls.** Hue alone does not scale; keep the link-on-hover channel. Offer the
colourblind-safe schemes.

### B2. Optimization remarks as inline rows under source lines, with kind filters

**Source.**

- LLVM remarks come in *Passed, Missed* and *Analysis* kinds. `opt-viewer.py` writes an
  index (*Source Location, Hotness, Function, Pass*) and source pages with remark rows
  inserted under their line. `opt-diff.py` compares two runs.
  [LLVM Remarks](https://llvm.org/docs/Remarks.html),
  [opt-viewer.py](https://github.com/llvm/llvm-project/blob/main/llvm/tools/opt-viewer/opt-viewer.py),
  [style.css](https://github.com/llvm/llvm-project/blob/main/llvm/tools/opt-viewer/style.css)
- Compiler Explorer renders each remark as an editor *view zone* inserted after
  `DebugLoc.Line`, with the CSS classes `opt-line` and `missed`, `passed` or
  `analysis`. Checkboxes filter `filter-missed`, `filter-passed` and
  `filter-analysis`. `compiler-explorer/static/panes/opt-view.ts`
  ([GitHub](https://github.com/compiler-explorer/compiler-explorer/blob/main/static/panes/opt-view.ts))

**Generalising to N builds.** Key remarks by *(logical function, line, pass, remark
name)*. The inline row reads "inlined: build-a, build-b · missed: build-c
(cost)". The index gains a builds column.

**Telling the classes apart.** Remarks on the same source are compile variance by
definition.

**Pitfalls.** Many legacy toolchains emit no remarks. Show "no compiler-reported
remarks for this toolchain", not a blank pane. Label effects reconstructed from the
binary (B5–B7) *observed*, apart from *reported* remarks (**inference**).

### B3. Pass-by-pass pipeline with before and after, hiding passes that changed nothing

**Source.** Compiler Explorer's *Opt Pipeline* pane:

- a pass list where each entry gets class `changed` when `irChanged`, and
  `firstMachinePass` marks the boundary between IR passes and machine passes;
- a *group* selector (per function);
- a before/after diff editor;
- the filter *filter-inconsequential-passes*;
- the options `filter-debug-info`, `dump-full-module`, `-fno-discard-value-names`,
  `demangle-symbols` and `library-functions`.

`compiler-explorer/static/panes/opt-pipeline.ts`
([GitHub](https://github.com/compiler-explorer/compiler-explorer/blob/main/static/panes/opt-pipeline.ts)).

LLVM's `-print-changed` modes include `diff`, `cdiff` and `dot-cfg` (a website of
colourised CFG changes)
([DebuggingLLVM](https://llvm.org/docs/DebuggingLLVM.html),
[D87202](https://reviews.llvm.org/D87202)).

**Generalising to N builds.** One pipeline strip per build, aligned by stage
(front end → IR → machine → link) rather than by pass name. Only toolchains that
dump IR get this view.

**Pitfalls.** Default to consequential passes and show "N hidden".

### B4. Flags as structured, sectioned, diffable presets

**Source.** decomp.me:

- models flags as typed `FlagSet`s (mutually exclusive options) and `Checkbox`es. The
  MSVC set includes `/Od…/Ox`, `/Ob0–2`, `/Zp1–16`, `/Gd /Gr /Gz`, `/GR`, `/GX`,
  `/Gs`, `/GS-` and `/GZ`.
  `decomp.me/backend/coreapp/flags.py`
  ([GitHub](https://github.com/decompme/decomp.me/blob/main/backend/coreapp/flags.py))
- splits the options UI into separate sections: *Preset*, *Compiler options*,
  *Libraries*, *Diff options*, and *Other options* (which holds *Match override*: "this
  scratch will be considered matching (100%)").
  `decomp.me/frontend/src/components/compiler/CompilerOpts.tsx`
  ([GitHub](https://github.com/decompme/decomp.me/blob/main/frontend/src/components/compiler/CompilerOpts.tsx))

**Generalising to N builds.** Give each build a profile card with the same sections.
The cross-build view is a flag matrix (flag groups × builds) with differing cells
emphasised. Every compile-variance explanation links to its cell:

- `/Zp` → A2;
- `/Ob` → B1;
- `/GS-` → B6.

**Telling the classes apart.** The flag matrix is the main evidence for compile
variance.

**Pitfalls.** Flags recovered heuristically from a binary must be labelled *inferred*,
unlike flags taken from a build log. Keep compiler flags and diff settings in separate
sections, as decomp.me does, so comparison settings never masquerade as build
properties.

### B5. Frame-layout comparison with bijective and non-bijective mapping

**Source.** reccmp `stackcmp` pairs stack offsets between original and recompiled
code. It prints the pairs "ordered by original stack" and "ordered by recomp stack",
and marks each as exact, bijective, non-bijective or "not seen".
`reccmp/reccmp/tools/stackcmp.py`
([GitHub](https://github.com/isledecomp/reccmp/blob/master/reccmp/tools/stackcmp.py)).

**Generalising to N builds.** A slot-mapping matrix per logical local.

**Telling the classes apart.** A non-bijective mapping on the same source is usually
compile variance (allocation). Missing locals point towards source variance.

**Pitfalls.** It needs alignment that already holds. Show "insufficient alignment"
rather than a wrong mapping.

### B6. Compiler scaffolding and compiler-generated entities kept apart from user logic

**Source.**

- objdiff has a dedicated exception-table diff view.
  `objdiff/objdiff-gui/src/views/extab_diff.rs`
  ([GitHub](https://github.com/encounter/objdiff/blob/main/objdiff-gui/src/views/extab_diff.rs))
- reccmp's `assert_fixup` replaces assert filename and line immediates before diffing.
  `reccmp/reccmp/compare/asm/fixes.py`
  ([GitHub](https://github.com/isledecomp/reccmp/blob/master/reccmp/compare/asm/fixes.py))
- reccmp annotations split `TEMPLATE`, `SYNTHETIC` (for example scalar deleting
  destructors) and `LIBRARY` from `FUNCTION`.
  `reccmp/docs/annotations.md`
  ([GitHub](https://github.com/isledecomp/reccmp/blob/master/docs/annotations.md))
- capa hides *library rules* behind a settings toggle.
  `capa/web/explorer/src/components/SettingsPanel.vue`

**Generalising to N builds.** Fold these into labelled bands in function views,
expandable, with per-build presence (for example "cookie: build-a, build-c"):

- prologue and epilogue;
- security-cookie checks;
- EH state updates;
- SEH frames.

Link each band to its B4 flag (**inference**).

**Telling the classes apart.** Scaffolding that differs under different flags is
compile variance. Synthetic and template entities are excluded from source-level
totals.

**Pitfalls.** Collapsed scaffolding must still show its diff status.

### B7. Switch tables and branches as structure

**Source.**

- reccmp never "relocates" jump-table or data-table entries, because they "most likely
  influence the behaviour" (`reccmp/reccmp/compare/asm/fixes.py`).
- objdiff colours each branch arrow `Rotating(branch_idx)`.
  `objdiff/objdiff-core/src/diff/display.rs`
  ([GitHub](https://github.com/encounter/objdiff/blob/main/objdiff-core/src/diff/display.rs))
- objdiff can show pooled data references as fake relocations
  (`ppc.calculatePoolRelocations`, `objdiff/objdiff-core/config-schema.json`).

**Generalising to N builds.** Decode a switch into *case value → target block* and diff
the case sets per build.

**Telling the classes apart.** The same cases with a different dispatch shape is
compile variance. Different cases is source variance (**inference**).

**Pitfalls.** Diffing a jump table as raw bytes turns relocations into noise.

### B8. Compiler entropy as declared, costed interventions

**Source.** ReproBit defines *compiler entropy*: "source paths, declaration order,
object order, debug history, temporary filenames, library scan order" can change the
bytes of equivalent source. Every intervention is typed and has a fixed cost class,
from 0 for native output up to 10,000 for direct installation of reference bytes.
[concepts](https://github.com/isledecomp/reprobit/blob/main/docs/concepts.md),
[costs](https://github.com/isledecomp/reprobit/blob/main/docs/costs.md).

**Generalising to N builds.** Each build profile lists its interventions and cost.
Entity views show the interventions that affected them.

**Telling the classes apart.** This is the source of the *entropy variance* class in
the premise. Do not collapse it into compile variance (**inference**).

**Pitfalls.** Cost must never disappear into a percentage.

---

## (c) Comparing the same function across builds

### C1. A fixed diff-kind taxonomy with weighted scores

**Source.**

- objdiff:
  - `InstructionDiffKind` is `None, OpMismatch, ArgMismatch, Replace, Delete, Insert`,
    and `DataDiffKind` is `None, Replace, Delete, Insert`
    (`objdiff/objdiff-core/src/diff/mod.rs`);
  - the penalties are immediate 1, register 5, replace 60, insert or delete 100, with a
    maximum of instructions × 100 (`objdiff/objdiff-core/src/diff/code.rs`);
  - an identical disassembly with a different encoding length becomes `OpMismatch`
    (same file).

  ([GitHub](https://github.com/encounter/objdiff/blob/main/objdiff-core/src/diff/code.rs))
- objdiff's symbol list uses three colour bands: exactly 100%, at least 50%, and
  below 50% (`match_color_for_symbol`,
  `objdiff/objdiff-gui/src/views/symbol_diff.rs`).

**Generalising to N builds.** Show a stacked strip of kind counts per build in the
entity header, and an N×N similarity matrix.

**Telling the classes apart.** A result that is mostly `ArgMismatch` or `OpMismatch`
leans compile variance. `Insert`, `Delete` or `Replace` clusters with changed calls
lean source variance (**heuristic**).

**Pitfalls.** One percentage hides the kind.

### C2. Register-rename-aware highlighting through stable per-value colours

**Source.**

- For each mismatched argument, objdiff's `diff_instruction` assigns every distinct
  argument string on each side a stable index (`left_args_idx`, `right_args_idx`),
  rendered as `Rotating(i)`. A consistent rename therefore shows up as one repeated
  colour pair (`objdiff/objdiff-core/src/diff/code.rs`).
- `HighlightKind` is `Opcode`, `Argument`, `Symbol` or `Address`, so clicking
  highlights every equal token on both sides (`objdiff/objdiff-core/src/diff/display.rs`).
- decomp.me defines `.rotation0…8` classes for both themes.
  `decomp.me/frontend/src/components/Diff/Diff.module.scss`

**Generalising to N builds.** Tie the colour to the *logical value* (`slotIndex`), not
to the register. The legend reads `slotIndex = esi (build-a) / edi (build-b)`.

**Telling the classes apart.** A consistent bijective rename is strong evidence of
compile variance.

**Pitfalls.** Around nine colours run out. Pair each hue with an index.

### C3. Relocation-aware normalisation; relocations shown by entity, not number

**Source.**

- reccmp turns addresses into names or `<OFFSETn>` placeholders, numbered "so the
  number will be consistent across the diff". It replaces immediates only when the
  relocation table confirms they are addresses.
  `reccmp/reccmp/compare/asm/parse.py`
  ([GitHub](https://github.com/isledecomp/reccmp/blob/master/reccmp/compare/asm/parse.py))
- objdiff's `functionRelocDiffs` setting has four modes: `none`, `name_address`,
  `data_value` and `all` (`objdiff/objdiff-core/config-schema.json`).
- objdiff's relocation hover lists *Name*(+addend), *Demangled*, *Section*, *Address*,
  *Size* (suffixed "(inferred)" when inferred), *Alignment* and *Virtual address*
  (`objdiff/objdiff-core/src/diff/display.rs`).
- decomp.me offers a diff algorithm choice (Levenshtein or difflib),
  `diff_function_symbols` and `--adjust-vma` (`decomp.me/backend/coreapp/flags.py`).

**Generalising to N builds.** Resolve each relocation through the cross-build identity
map. `build-a:0x0041c880` and `build-b:0x0041d1a0` then both render as
`ResourceRef::Resolve`, and the hover lists the per-build address.

**Telling the classes apart.** The *same entity at a different address* is layout or
link variance. A *different entity* is a real difference.

**Pitfalls.** "Unresolved" is not "different". Show it as its own state. Copy
objdiff's "(inferred)" suffix for any derived attribute.

### C4. "Effective match" as its own status, between exact and partial

**Source.**

- reccmp's `find_effective_match` asks whether two sequences "differ only by
  instruction order or register selection". It allows jump swaps paired with swapped
  `cmp` operands (`ALLOWED_JUMP_SWAPS`) and never relocates table entries.
  `reccmp/reccmp/compare/asm/fixes.py`
- reccmp's sort key orders results as exact, then effective, then accuracy, with stubs
  last. Effective matches keep a grouped diff; exact matches show none.
  `reccmp/reccmp/compare/report.py`
  ([GitHub](https://github.com/isledecomp/reccmp/blob/master/reccmp/compare/report.py))
- The report UI mirrors this in `reccmp/reccmp/assets/state.js` and
  `components/listingTable.js`.
- A downstream fix records that the HTML viewer mis-rendered effective matches as
  partial after a field changed.
  [agluszak/reccmp#18](https://github.com/agluszak/reccmp/pull/18)

**Generalising to N builds.** A status enum per *(entity, build pair)*:
`exact · effective(reg) · effective(order) · reloc-only · partial · unmatched · stub`.
The matrix cells show glyphs, not numbers.

**Telling the classes apart.** Every `effective*` and `reloc-only` status is compile
variance by construction.

**Pitfalls.** A boolean plus a percentage causes mis-sorting. An effective match must
never count as byte-exact.

### C5. Three-way diff: target, current and previous attempt

**Source.** decomp.me's diff has the columns `base`, `current` and `previous`.
`ThreeWayDiffBase` is `saved` or `prev`, and it drives an interdiff.
`decomp.me/frontend/src/components/Diff/Diff.tsx`,
`decomp.me/frontend/src/lib/settings.ts`,
`decomp.me/frontend/src/components/Diff/CompilationPanel.tsx`
([GitHub](https://github.com/decompme/decomp.me/blob/main/frontend/src/components/Diff/Diff.tsx)).

**Generalising to N builds.** Two uses:

- target build vs candidate vs previous candidate;
- reference build vs build-x vs build-y, to see which differences are shared across
  variants.

**Telling the classes apart.** Differences shared within one toolchain family, and
absent from another, point to compile variance.

**Pitfalls.** Three columns at phone width need a stacked mode.

### C6. Cross-compiler diff of any output kind

**Source.** Compiler Explorer's *Diff* pane compares two compiler panes. Its
`DiffType` can be `ASM`, `CompilerStdOut`, `CompilerStdErr`, `ExecStdOut`,
`AstOutput`, `IrOutput`, `DeviceView` and others.
`compiler-explorer/static/panes/diff.interfaces.ts`, `static/panes/diff.ts`
([GitHub](https://github.com/compiler-explorer/compiler-explorer/blob/main/static/panes/diff.ts)).

**Generalising to N builds.** The same builds × artifact-kind picker, applied to
disassembly, pseudocode, compiler logs and type layout.

**Pitfalls.** Diffing unnormalised text across toolchains. Apply C3 normalisation
first.

### C7. Multiple samples merged, with an explicit "varies" state

**Source.** reccmp's `combine_reports` (`reccmp/reccmp/compare/report.py`):

- keeps each entity's best sample;
- sets `recomp_addr_varies` when addresses differ;
- takes `function_count` as the maximum, because "some functions may have been inlined
  in some reports";
- rejects reports from different source files (`ReccmpReportSameSourceError`).

**Generalising to N builds.** This is a direct precedent: an entity-keyed merge, a
*varies* flag, the maximum denominator, and a same-source guard.

**Telling the classes apart.** Refuse to aggregate across source revisions; show those
builds as separate groups (**inference**).

**Pitfalls.** "Best of" is optimistic. Show the best, the worst and which build
achieved each.

### C8. One source annotation, many targets; folded (ICF) entities

**Source.** reccmp annotations take the form `// <TYPE>: <target> <address>`, "since it
is possible to build different targets from the same source code".
`// FUNCTION: <target> 0x… FOLDED` marks functions that `/OPT:ICF` combined at one
address. The parser keeps folded duplicates instead of rejecting them.
`reccmp/docs/annotations.md`, `reccmp/reccmp/parser/codebase.py`
([GitHub](https://github.com/isledecomp/reccmp/blob/master/docs/annotations.md)).

**Generalising to N builds.** This is the premise expressed in source: one logical
entity carries one address per target.

- The identity map must allow **many entities → one address** in a build that folds.
  Such a cell renders as "folded with 3 others".
- It must also allow **one entity → no address** where the entity was inlined away.

**Telling the classes apart.** Folding present in only some builds, with the same
source, is compile or link variance (`/OPT:ICF`).

**Pitfalls.** Treating an address as a unique key breaks on folded builds.

### C9. Correlation tables with opinions, score, confidence, votes and status

**Source.**

- Ghidra Version Tracking's matches table (`ghidra/…/VersionTrackingPlugin/providers/VT_Matches_Table.html`):
  - there can be "multiple matches (opinions) for the same association" from different
    correlators;
  - status is *Available, Accepted, Rejected* or *Blocked*;
  - *Score* and *Confidence Score* "should NOT be compared between different correlator
    algorithms";
  - further columns are *Votes*, *Length Delta*, *Source Label Type* (Imported,
    Analysis, User Defined) and a *Markup Status* row of orbs;
  - accepting a match creates *implied matches*.

  ([GitHub](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/VersionTracking/src/main/help/help/topics/VersionTrackingPlugin/providers/VT_Matches_Table.html))
- BinDiff shows similarity, confidence and change flags `G I O J E L C`, colours rows
  green to red, and colours flow-graph nodes green, yellow or red.
  [BinDiff manual](https://www.zynamics.com/bindiff/manual/)
- Diaphora ports structs and enums, diffs pseudocode and microcode, and supports
  compilation units.
  [README](https://github.com/joxeankoret/diaphora)
- objdiff supports manual symbol mapping (`SetMapping`, *show mapped symbols*).
  `objdiff/objdiff-gui/src/views/symbol_diff.rs`

**Generalising to N builds.** The identity table is keyed by entity, with one cell per
build. Each cell holds the address, the opinions (correlator plus its own score), the
status, and the label provenance.

**Telling the classes apart.** BinDiff flags `O` or `I` alone lean compile variance.
`G`, `C` or `L` lean source variance (**heuristic**).

**Pitfalls.**

- Merging identity confidence with code equality.
- Comparing scores across correlators, which Ghidra explicitly warns against.

### C10. Side-by-side named, versioned witnesses with rerun

**Source.** Dogbolt shows the output of several decompilers for one binary:

- each panel header shows name, version and revision;
- the tooltip gives "Analysed <date> / Analysis took N seconds";
- a per-decompiler *rerun* button appears when the cached result came from an older
  version;
- line anchors are kept in the URL hash.

`decompiler-explorer/static/js/index.js`, `static/js/queue.js`
([GitHub](https://github.com/decompiler-explorer/decompiler-explorer/blob/master/static/js/index.js)).

**Generalising to N builds.** Witness × build. Default to one witness across builds, or
several witnesses for one build.

**Telling the classes apart.** If every witness shows the difference, it is real. If
witnesses disagree, it may be a decompiler artefact.

**Pitfalls.** An unversioned witness, or a stale result with no age shown.

### C11. "Why doesn't this match": explainers per entity kind

**Source.** reccmp tools:

- `vtable` always shows the full diff for vtables;
- `datacmp` compares globals;
- `stackcmp` compares frames (B5);
- `roadmap` reports how "far off" a symbol is from its original place.

The HTML report search has the modes *Name/address*, *Asm output* and *Asm diffs only*.
`reccmp/reccmp/tools/`, `reccmp/reccmp/assets/components/searchOptions.js`
([GitHub](https://github.com/isledecomp/reccmp/tree/master/reccmp/tools)).

**Generalising to N builds.** An *Explain* panel runs a fixed checklist over the
entity, and each item gives an answer and its evidence:

1. flags (B4);
2. rename (C2);
3. relocation or layout (C3);
4. folding (C8);
5. frame (B5);
6. scaffolding (B6);
7. switch (B7);
8. placement (`roadmap`);
9. entropy (B8);
10. source identity.

The panel ends in a variance class (**inference**, assembled from the sources above).

**Pitfalls.** Explanations without links back to evidence.

---

## (d) Presenting project outputs and exports

### D1. A typed report with fuzzy, matched and linked measures kept apart

**Source.** objdiff's report schema:

- `report.proto` `Measures`: `fuzzy_match_percent`; matched code, data and functions;
  complete ("linked") code, data and units;
- per-unit metadata: complete, module, source path, progress categories,
  auto-generated;
- `changes.proto` pairs `from` and `to` reports per unit and item.

`objdiff/objdiff-core/protos/`
([GitHub](https://github.com/encounter/objdiff/tree/main/objdiff-core/protos)).

**Generalising to N builds.** Key rows by *(build, unit, entity)*. Give each build its
own `Measures` block, plus an across-builds block built with C7 rules.

**Pitfalls.** Fuzzy percent looks like progress. Keep fuzzy, matched and linked
labelled separately and never sum them.

### D2. A treemap where "done" is a categorical colour

**Source.** decomp.dev's `unit_color` returns a distinct green only at exactly 100%.
Below that it mixes grey towards blue by fuzzy percent.
`decomp.dev/crates/images/src/treemap.rs`, `decomp.dev/js/treemap.ts`
([GitHub](https://github.com/encounter/decomp.dev/blob/main/crates/images/src/treemap.rs)).

**Generalising to N builds.** Small multiples, one per build, all with the same unit
layout.

**Pitfalls.** A continuous ramp that ends in the "done" colour.

### D3. Reports keyed by commit × version

**Source.** decomp.dev keys reports by *(project, commit sha, version)*, using
`report_versions` and `default_version`, and draws a history chart.
`decomp.dev/crates/web/src/handlers/project.rs`, `decomp.dev/js/history.ts`
([GitHub](https://github.com/encounter/decomp.dev/blob/main/crates/web/src/handlers/project.rs)).

**Generalising to N builds.** Version = build. Draw one line per build. The default
build is a user preference.

**Pitfalls.** A single-version default that hides the others.

### D4. Change summaries: new, broken, improved, regressed; missing reports stated

**Source.** decomp.dev's change comment:

- groups changes as *new match*, *broken match*, *improvement in an unmatched item* and
  *regression in an unmatched item*;
- shows each group as a collapsible table (*Unit, Item, Bytes, Before, After*),
  truncated with "…and N more";
- states missing reports explicitly: "Base report not found…" and "PR report not
  found…";
- joins several versions into one comment.

`decomp.dev/crates/github/src/changes.rs`
([GitHub](https://github.com/encounter/decomp.dev/blob/main/crates/github/src/changes.rs)).

**Generalising to N builds.** Produce the four groups per build, and surface a broken
match in any build first.

**Telling the classes apart.** A match broken only in one toolchain family points to
compile or entropy variance. One broken in every build points to a source edit.

**Pitfalls.** Reporting "no changes" when a report is actually missing.

### D5. A self-contained HTML report with honest client-side filters and score text

**Source.**

- reccmp's report is one template with web components (`reccmp/reccmp/assets/`):
  - `search-bar` and `search-options`;
  - `hide-perfect`, which also hides effective matches;
  - `hide-stub` and `show-recomp`;
  - pagination and click-to-copy.

  The diff table has orig and recomp address columns and `-`/`+` rows
  (`components/diffDisplay.js`).
  ([GitHub](https://github.com/isledecomp/reccmp/tree/master/reccmp/assets))
- decomp.me's `ScoreBadge` rounds any value between 99.99 and 100 *down* to "99.99%"
  and shows "(override)" when a match is manual.
  `decomp.me/frontend/src/components/ScoreBadge.tsx`
  ([GitHub](https://github.com/decompme/decomp.me/blob/main/frontend/src/components/ScoreBadge.tsx))

**Generalising to N builds.** One export per run covering all builds, with a build
filter. Rows are entities, with a status glyph per build.

**Pitfalls.**

- Filters that hide more than their name says.
- Rounding that shows 100%.
- Manual overrides that are not labelled.

### D6. The accuracy report is separate from the certification report

**Source.** ReproBit reports three independent claims:

- **byte exact**;
- **logic certified**;
- **toolchain origin**.

Its supporting rules:

- the producer cannot read the reference;
- `verify` never uses the build cache;
- the report shows the intervention cost.

A matching-decomp project that uses it publishes reccmp *accuracy* reports and ReproBit
*verification* reports side by side for each binary.
[README](https://github.com/isledecomp/reprobit#readme),
[concepts](https://github.com/isledecomp/reprobit/blob/main/docs/concepts.md).

**Generalising to N builds.** One acceptance row per build, with the three claims shown
separately. A build at 100% accuracy without fresh whole-image verification is
visibly *not accepted*. This matches STRATEGY, which keeps accuracy and whole-image
acceptance apart.

**Pitfalls.** One green check that merges accuracy, exactness and provenance.

### D7. Re-browsable run artifacts: attempts, plugin flow and evidence trees

**Source.**

- Mizuchi writes `run-results-{timestamp}.json` and `run-report-{timestamp}.html`
  ([README](https://github.com/macabeus/mizuchi)). The report UI has:
  - *Summary*;
  - *PluginFlow*, where each plugin in each attempt is `success`, `failure` or
    `skipped`;
  - *TimelineChart* (a Gantt of attempts and background tasks);
  - *AttemptsChart*;
  - *BestResultCode*;
  - separate setup, programmatic and post-match phases;
  - a warning when the provider that served an attempt differed from the one
    requested.

  `mizuchi/src/ui/run-report/components/`
  ([GitHub](https://github.com/macabeus/mizuchi/tree/main/src/ui/run-report/components))
- capa Explorer loads saved JSON (from a file, a URL or gzip) and works offline. Its
  rule-match *TreeTable* has the columns *Rule, Address, Namespace, ATT&CK, MBC*. Rule
  nodes show "(N matches)", and statement and feature nodes are styled differently.
  There are column filters, a library-rules toggle and a namespace chart.
  `capa/web/explorer/src/components/RuleMatchesTable.vue`, `columns/RuleColumn.vue`,
  `SettingsPanel.vue`
  ([GitHub](https://github.com/mandiant/capa/tree/master/web/explorer))
- APKMan caches by SHA-256 and exports a ZIP
  ([apkman](https://github.com/jiusanzhou/apkman)).
- RzWeb exports snapshots and project bundles
  ([rzweb](https://github.com/IndAlok/rzweb)).

**Generalising to N builds.** Key artifacts by *(input digest, build profile, run id)*.
Show per-build attempt timelines, and reuse the plugin-flow grid with builds as rows.
A reloaded run is labelled *reused*, with its date.

**Pitfalls.**

- An old run that looks fresh.
- A tool or provider substitution that goes unmentioned. Mizuchi surfaces it; copy
  that.

### D8. Claims that cite evidence, with a verification state

**Source.** Rev·Deck cites `[function:0xADDR]`, `[string:0xADDR]` and `[import:name]`,
and flags claims whose citations do not match retrieved evidence as "(unverified)".
Sub-investigations return a summary card to their parent.
[ai-reverse-engineering](https://github.com/biniamf/ai-reverse-engineering).

**Generalising to N builds.** Citations name entity and build, for example
`[fn:ResourceRef::Resolve@build-b]`. An "all builds" claim cites each build, or names
the builds it was not checked against.

**Pitfalls.** Build-less addresses.

### D9. Navigation that follows the user, with writes gated

**Source.**

- idarem has *Follow IDA* (over SSE) and a *Drive* mode. Writes need
  `IDAREM_ALLOW_WRITE=1`, and panes are virtualised.
  [idarem](https://github.com/xsslize/idarem)
- RzWeb's views share a single `currentAddress` and `selectedFunction` in one store.
  `rzweb/src/stores/uiStore.ts`
  ([GitHub](https://github.com/IndAlok/rzweb/blob/main/src/stores/uiStore.ts))
- r2web offers goto, search in large outputs, and a graph view
  ([r2web](https://github.com/radareorg/r2web)).

**Generalising to N builds.** Adopt the connected-views store, but make its cursor
*(entity, optional build)* rather than a bare address. Selecting
`CacheEntry.name_len` moves every build column to its own address.

**Pitfalls.** RzWeb's global numeric `currentAddress` is correct for one binary and
wrong for N. Following a raw address across builds lands on unrelated code.

---

## Patterns to adopt, adapt or avoid

| # | Pattern | Verdict | How it applies to build-a…build-d | Grounding |
|---|---|---|---|---|
| A1 | Address expression; pointer row expands inline with rebased address | **Adapt** | Logical chain; per-build offset and value cells | `ReClass.NET/ReClass.NET/Nodes/PointerNode.cs` |
| A2 | Component table with filler, bit view, alignment | **Adopt** | One row set; per-build offset and padding | Ghidra `StructureEditor.htm` |
| A3 | Gap markers and create-at-accessed-offset | **Adapt** | Merge accesses from all builds; mark auto members inferred | Binary Ninja docs; `revng/…/editing-types-in-c.md` |
| A4 | Shifted pointer `ADJ()`; negative-offset scanning | **Adopt** | Per-build this-delta badge | IDA tip #54; CE `PointerscannerSettingsFrm.lfm` |
| A5 | Frame as a pseudo-struct with `r`/`s` | **Adopt** | Locals keyed by name; slot and R/S per build | IDA tip #65 |
| A6 | VTable, Instance and Array nodes; typed-guess comments | **Adapt** | Slots by logical method; shared array index | `ReClass.NET/…/Nodes/*.cs` |
| A7 | Grouped dissect with NoMatch / AllMatchSame / AllMatchDiff | **Adopt** | Groups = source revision; colours = variance class | `cheat-engine/Cheat Engine/StructuresFrm2.pas` |
| A8 | Rescan, intersect, must-end-with-offsets | **Adapt** | "Valid in k/N builds"; end condition by field identity | CE `pointerscannerfrm.pas` |
| A9 | Xrefs with direction, kind, filtered/total and coverage | **Adopt** | Grouped by logical function; build-presence strip | Binary Ninja; IDA tip #18; `rzweb/…/XrefsView.tsx` |
| A10 | Typed location grammar plus actions; cache invalidated by the model | **Adapt** | `/struct-field/CacheEntry/name_len@build-b`; key by id, not offset | `revng/share/doc/revng/references/ptml.md` |
| — | Automatic `.conflict` renaming | **Avoid** | Conflicts become open decisions | Ghidra DTM help |
| B1 | Line colour correlation plus `panesLinkLine` hover link; colourblind-safe schemes | **Adopt** | Fan out to per-build columns | `compiler-explorer/static/panes/{editor,compiler}.ts`, `static/colour.ts` |
| B2 | Remarks as inline view zones with kind filters | **Adopt where emitted** | Per-build remark row; "none reported" state | `compiler-explorer/static/panes/opt-view.ts`; LLVM Remarks |
| B3 | Pass list with `changed` and `firstMachinePass`, plus before/after diff | **Adapt** | Only for IR-dumping toolchains; align by stage | `compiler-explorer/static/panes/opt-pipeline.ts` |
| B4 | Sectioned options (preset, compiler, libraries, diff, override) | **Adopt** | Build profile card and flag matrix | `decomp.me/…/CompilerOpts.tsx`, `backend/coreapp/flags.py` |
| B5 | Bijective stack-slot mapping | **Adopt** | Slot matrix per local | `reccmp/reccmp/tools/stackcmp.py` |
| B6 | Scaffolding bands; synthetic, template and library tags; library toggle | **Adapt** | Collapsed but status-visible; linked to flags | `reccmp/docs/annotations.md`; `objdiff/…/extab_diff.rs` |
| B7 | Switch as case → target | **Adopt** (inference) | Diff case sets | `reccmp/…/asm/fixes.py` |
| B8 | Costed entropy interventions | **Adopt** | Separate *entropy variance* class | ReproBit `docs/costs.md` |
| C1 | Diff-kind taxonomy, penalties, three-band symbol colour | **Adopt** | Kind strip per build; N×N matrix | `objdiff/objdiff-core/src/diff/{mod,code}.rs` |
| — | A single % as the only indicator | **Avoid** | Always show kinds and denominator | — |
| C2 | Stable rotating colour per differing argument; click-highlight | **Adapt** | Colour the logical value | `objdiff/…/code.rs` `diff_instruction` |
| C3 | `<OFFSETn>` placeholders; reloc modes; hover with "(inferred)" | **Adopt** | Resolve through the entity map | `reccmp/…/asm/parse.py`; `objdiff/…/display.rs` |
| C4 | Effective match as its own status | **Adopt** | Status enum per build pair; never byte-exact | `reccmp/…/compare/report.py`, `asm/fixes.py` |
| — | Status as boolean + percentage | **Avoid** | Caused a mis-sort ([reccmp#18](https://github.com/agluszak/reccmp/pull/18)) | — |
| C5 | Three-way diff (base, current, previous) | **Adopt** | Reference vs two variants | `decomp.me/…/Diff/Diff.tsx` |
| C6 | Diff pane over any output kind | **Adopt** | Builds × artifact-kind picker | `compiler-explorer/static/panes/diff.interfaces.ts` |
| C7 | Multi-sample merge with `varies`, max denominator, same-source guard | **Adopt** | N-build aggregation per source revision | `reccmp/…/compare/report.py` |
| C8 | Per-target annotations; `FOLDED` (ICF) | **Adopt** | Many-to-one and one-to-none identity cells | `reccmp/docs/annotations.md`, `parser/codebase.py` |
| C9 | Opinions, score vs confidence, votes, status, label provenance | **Adopt** | Identity table; never compare scores across correlators | Ghidra `VT_Matches_Table.html`; BinDiff |
| C10 | Versioned witnesses with analysed-at and rerun | **Adapt** | Witness × build; show staleness | `decompiler-explorer/static/js/index.js` |
| — | Auto-upload to public witness services | **Avoid** | See the FRONTEND_INTENT §7 boundary | — |
| C11 | Explainer tools per entity kind | **Adopt** | Checklist ending in a variance class | `reccmp/reccmp/tools/` |
| D1 | Fuzzy, matched and linked measures kept apart; from/to changes | **Adopt** | Per build plus across builds | `objdiff/objdiff-core/protos/` |
| D2 | Categorical "done" colour | **Adopt** | Small multiples per build | `decomp.dev/crates/images/src/treemap.rs` |
| D3 | Commit × version keys; history | **Adopt** | Version = build | `decomp.dev/…/handlers/project.rs` |
| D4 | New, broken, improved, regressed; explicit missing report | **Adopt** | Per build; broken-anywhere first | `decomp.dev/crates/github/src/changes.rs` |
| D5 | Self-contained report; honest filters; no rounding up; labelled override | **Adapt** | All builds in one export | `reccmp/reccmp/assets/`; `decomp.me/…/ScoreBadge.tsx` |
| D6 | Accuracy separate from certification (three claims) | **Adopt** | Acceptance row per build | ReproBit README and concepts |
| — | One check merging accuracy and acceptance | **Avoid** | Conflicts with STRATEGY | — |
| D7 | Re-browsable runs: attempts, plugin flow, evidence tree | **Adopt** | Keyed by digest, profile and run; *reused* badge | `mizuchi/src/ui/run-report/`; `capa/web/explorer/` |
| D8 | Citations with an "(unverified)" state | **Adopt** | `entity@build` citations | Rev·Deck README |
| D9 | Connected-views store; follow and drive with gated writes | **Adapt** | Cursor = (entity, build), not an address | `rzweb/src/stores/uiStore.ts`; idarem |
| — | Any view rooted in one binary's address space | **Avoid** | Build is a facet of the entity | premise; RzWeb `currentAddress` shows the trap |

## Not covered or not verified

- **Grapefruit.** Its dynamic views ([grapefruit](https://github.com/ChiChou/grapefruit))
  belong to an optional runtime provider. None of the four concerns needs them, so no
  pattern was taken.
- **objdiff-web.** It reuses objdiff-core through WASM
  (`objdiff-web/README.md`). Its patterns are cited from objdiff-core and objdiff-gui
  instead of its webview.
- **Proprietary tool UIs.** Details for IDA, Binary Ninja and BinDiff come only from
  public docs. The tools were not run.
- **What was checked.** Nothing here was rendered or executed. Line-level claims about
  upstream code come from reading the cloned source at the commits listed above.
- **Licensing.** No licence review was done for reusing upstream code. This note
  borrows interaction patterns only.
