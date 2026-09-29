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

- **Upstream source read directly.** Shallow clones of these repositories were read,
  without running them:
  - `isledecomp/reccmp` at `e91a51b` (2026-09-21);
  - `encounter/objdiff` at `fba10a6` (2026-08-29);
  - `encounter/decomp.dev` at `e9c086a` (2026-09-06);
  - `decompme/decomp.me` at `4ab701a` (2026-09-27).

  Claims that cite a file path in these repositories come from reading that source.
- **Upstream docs and READMEs.** These were fetched from the web. Some fetches went
  through a summariser, so short quotes may be paraphrased. The cited URL is the
  authority.
- **Not used as sources.** AI-generated wikis about these repositories were skipped.
  Their summaries were not checked against source.
- **Inference.** Anything marked **inference** is a design proposal without an
  upstream source.
- **Not read.** Nothing under this repository's `src/`, static, React or Vite
  frontend code was read. No tests, builds or servers were run.
- **Names.** Examples use generic names: `build-a`…`build-d`,
  `ResourceRef::Resolve`, `CacheEntry.name_len` and `FUN_0041c880`. Some upstream
  URLs contain organisation names. They appear only as links.

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

Every cross-build difference should end up in one of two variance classes:

| Class | Meaning | Typical evidence |
|---|---|---|
| **compile variance** | Same source, compiled differently | Register choice, instruction order, relocation targets, alignment or padding from packing flags, inlining decisions, frame layout, security-cookie or EH scaffolding, link order. Recorded toolchain or flags differ while source identity is equal. |
| **source variance** | Source changed | Different control-flow structure, call set, constants or field set. The recorded source revision or file digest differs. |
| **unknown** | Cannot tell yet | No source identity is recorded for one side, or the evidence conflicts. |

**Inference, applied throughout:** machine code alone cannot always tell these
classes apart. A reliable split needs recorded provenance for each build:

- source revision or digest;
- toolchain identity;
- flags;
- link inputs.

The UI should show the class together with the evidence behind it. A class inferred
only from instruction patterns should be labelled *heuristic*.

---

## (a) Walking pointers and memory layouts

### A1. The address as an editable expression, not a number

- **Source:** In ReClass.NET a class address field accepts a formula:
  - `<Program.exe> + 0x123` adds an offset to a module base;
  - `[addr]` dereferences;
  - `[<Program.exe> + 0xDE] - AB` reads a pointer and then subtracts;
  - nested reads are allowed, with integer `+ - * /`.

  [ReClass.NET README](https://github.com/ReClassNET/ReClass.NET#tips).
  ReClassEx also accepts `module+0x40` in address nodes
  ([ReClassEx](https://github.com/ajkhoury/ReClassEx)).
- **Generalising to N builds:** write the chain in logical terms, for example
  `[cacheRoot] -> CacheEntry[+i] -> .name_len`. Resolve it per build into a column
  that shows each hop's numeric offset and final address. The chain is the entity;
  the numbers belong to each build.
- **Telling the classes apart:** suppose a hop's offset differs between builds and
  the field sequence is the same. If the builds' packing or alignment flags differ,
  suspect **compile variance**; otherwise the difference is unexplained. If a field
  was inserted before the hop, the change is **source variance**. Show the reason
  next to the differing offset (**inference**).
- **Pitfalls:** a single-number address box encourages designs built around one
  binary. Integer-only arithmetic silently truncates, so show the width of each
  dereference (4 or 8 bytes).

### A2. Layout table with one row per component and filler shown

- **Source:** Ghidra's structure editor lists each component with *Offset, Length,
  Mnemonic, DataType, Name, Comment*. In a non-packed structure "all bytes are
  accounted for by the displayed components", so undefined filler is visible. The
  editor also has:
  - a bit-level view whose colours separate defined bitfields, conflicts and
    undefined bits;
  - packing and alignment controls with a read-only *Alignment* field;
  - a hex/decimal toggle (Shift-H);
  - text search across columns.

  [StructureEditor help](https://raw.githubusercontent.com/NationalSecurityAgency/ghidra/master/Ghidra/Features/Base/src/main/help/help/topics/DataTypeEditors/StructureEditor.htm).
- **Generalising to N builds:** keep a single row set keyed by field name. Add an
  offset or size column for each build, or collapse those columns into one when every
  build agrees. Padding rows are per build, because the same source can pad
  differently under different `/Zp` values.
- **Telling the classes apart:** equal field lists with different padding, size or
  alignment are **compile variance** (packing). A field present in some builds only
  is **source variance**.
- **Pitfalls:** hiding filler hides the layout evidence that matters most. A single
  global hex/dec toggle is fine; mixed radix per column is not.

### A3. Gaps as first-class markers, plus "create a member where code accesses it"

- **Source:**
  - Binary Ninja shows unfilled bytes as `??`. It annotates code accesses to
    unmapped offsets, such as `__offset(0x8).q`; pressing *S* creates the member.
    Right-clicking the struct name creates members at every accessed offset, and
    *Show Inherited Members* displays base-class members.
    [Binary Ninja types](https://docs.binary.ninja/guide/types/basictypes.html)
  - Ghidra's *Auto Create Structure* and *Auto Fill in Structure* build or extend a
    struct from the references the decompiler finds. Fill-in stops after offset
    0x1000.
    [Ghidra issue #4879](https://github.com/NationalSecurityAgency/ghidra/issues/4879),
    [FillOutStructureHelper](https://ghidra.re/ghidra_docs/api/ghidra/app/decompiler/util/FillOutStructureHelper.html)
  - rev.ng pins fields with `_STARTS_AT(N)` and `_SIZE(N)` when a type is edited as
    C. Its decompiled output changes from `argument_0->offset_8` to named fields.
    [rev.ng editing types in C](https://github.com/revng/revng/blob/develop/share/doc/revng/user-manual/tutorial/editing-types-in-c.md)
- **Generalising to N builds:** combine the observed accesses from every build into
  one gap map. Each offset gets per-build chips showing which builds access it and
  with what width.
- **Telling the classes apart:** suppose an offset is accessed only in `build-c`.
  With the same source revision, the likely cause is inlining that exposed the access
  (**compile variance**). With a newer revision, the likely cause is a new field
  (**source variance**) (**inference**).
- **Pitfalls:** auto-created members turn guesses into facts. Mark them as inferred
  until they are corroborated. Width conflicts at one offset may be a union or a
  mistake, so show them as a conflict rather than picking one.

### A4. Interior pointers and this-pointer adjustment written explicitly

- **Source:** IDA declares a shifted pointer as `int *__shifted(mystruct,20)`, and
  its decompiler renders the access as `ADJ(p)->field`. Two uses are documented:
  interior pointers in loops, and headers stored before the data.
  [Igor's tip #54](https://hex-rays.com/blog/igors-tip-of-the-week-54-shifted-pointers)
- **Generalising to N builds:** show a delta badge (`this - 0x10 → Base`) for each
  build on thunks and adjusted calls. Deltas under multiple inheritance depend on the
  layout of the bases, so a delta that differs across builds should link to the
  base-layout row in A2 that explains it.
- **Telling the classes apart:** a different delta with an identical base list and
  identical sizes is compile variance, from packing or vtable-pointer placement. A
  changed base list is source variance.
- **Pitfalls:** raw `p - 0x10` arithmetic in pseudocode hides that the value is a
  base-object address. Always name the containing type.

### A5. The frame as a pseudo-structure with signed offsets

- **Source:**
  - IDA shows a function's stack frame as a nameless structure. Offsets are relative
    to the frame pointer, both positive and negative, and special members stand for
    the saved return address (`r`) and saved registers (`s`).
    [Igor's tip #65](https://hex-rays.com/blog/igors-tip-of-the-week-65-stack-frame-view)
  - Binary Ninja has a *Stack* sidebar and a *Variables* panel that tags variables as
    Register (R), Stack (S), Flag (F) or Data (D).
    [Binary Ninja guide](https://docs.binary.ninja/guide/index.html)
- **Generalising to N builds:** show the frame as an A2 table with one column per
  build. Rows are keyed by the local's logical name (for example `slotIndex`), with
  the frame offset per build. A local that is a register variable in one build and a
  stack slot in another shows R or S per column.
- **Telling the classes apart:** frame size and slot order depend heavily on the
  compiler, so treat them as compile variance by default. A local that exists in only
  one build, with no inlining explanation, suggests a source change.
- **Pitfalls:** frame-pointer-relative and stack-pointer-relative offsets cannot be
  compared directly. Normalise and state which base is used.

### A6. Inline pointer preview, drill-down, vtable and array nodes

- **Source:**
  - ReClass.NET has *Pointer Preview*, arrays and pointers to any node type, a
    *Virtual Tables* node, function-pointer nodes, RTTI display, PDB-typed display,
    *Highlight changed memory*, and C++/C# code generation.
    [ReClass.NET README](https://github.com/ReClassNET/ReClass.NET#features)
  - Cheat Engine's structure dissector offers "Memory browse this pointer".
    [Cheat Engine dissect](https://cheatengine.org/help/dissect-datastructures.htm)
- **Generalising to N builds:** a vtable node lists slots keyed by *logical method*.
  The slot index and the target address are per build. Expanding a slot jumps to that
  function entity, not to one build's address.
- **Telling the classes apart:** in matching-decomp tooling, a reordered slot almost
  always means source changed (declaration order). An equal slot order with
  different targets is ordinary relocation (**inference**; reccmp keeps a dedicated
  vtable comparison, see C9).
- **Pitfalls:** auto-expanding pointers without cycle and depth limits.
  "Highlight changed memory" is a live-process idea. For static builds, the
  equivalent is *differs across builds*, which is a different signal and must not
  share the same colour.

### A7. Compare many instances side by side, in groups

- **Source:** Cheat Engine's *Dissect data/structures* puts several addresses
  side by side and lets the user sort them into groups, "to compare the values in
  every structure and also see if the values are the same in the same group".
  [Cheat Engine dissect](https://cheatengine.org/help/dissect-datastructures.htm)
- **Generalising to N builds:** this is the closest existing precedent for the
  premise. Instances become builds, and groups become toolchain families, or older
  and newer source. Cell colour answers two questions: is this value the same within
  the group, and is it the same across groups?
- **Telling the classes apart:** group builds by recorded source revision. A
  difference inside a same-source group is compile variance. A difference only
  between groups is a candidate source variance.
- **Pitfalls:** a colour meaning "different" without the dimension stated. Label the
  comparison scope, for example "vs group" or "vs all".

### A8. Pointer-path robustness through re-resolution and intersection

- **Source:** Cheat Engine's pointer scanner produces many candidate paths
  (base plus an offset chain, with max level and max offset settings). A *rescan*
  against a new target address filters out paths that no longer resolve. The scanner
  can also "compare results with other saved pointermap(s)".
  [Pointer scan help](https://cheatengine.org/help/pointer-scan.htm),
  [CE wiki](https://wiki.cheatengine.org/index.php?title=Help_File%3APointer_scan)
- **Generalising to N builds:** resolve a candidate chain in every build and keep
  the ones that resolve in all of them. The result reads "valid in 4/4 builds" or
  "valid in build-a, build-b only".
- **Telling the classes apart:** a chain that breaks in exactly the builds sharing a
  flag or toolchain points to compile variance. One that breaks at a source-revision
  boundary points to source variance.
- **Pitfalls:** candidate explosion. Show counts and let the user narrow them; do
  not render thousands of rows unvirtualised.

### A9. Field-level cross-references with direction and kind

- **Source:**
  - IDA xref lists show *Direction, Type, Address, Text*, with type letters `r`, `w`,
    `o`, `j` and `p`. Xrefs work on struct and stack members.
    [Igor's tip #16](https://hex-rays.com/blog/igor-tip-of-the-week-16-cross-references),
    [#17](https://hex-rays.com/blog/igor-tip-of-the-week-17-cross-references-2).
    The decompiler's *global xrefs* (Ctrl-Alt-X) list a field's uses as pseudocode
    lines and are refreshed by decompiling everything.
    [Igor's tip #18](https://hex-rays.com/blog/igors-tip-of-the-week-18-decompiler-and-global-cross-references)
  - Binary Ninja's cross-reference pane filters by direction, category (code, data,
    variable, type) and regex. It reports `Filter (<filtered>/<total>)` and offers
    tree and table layouts.
    [Binary Ninja guide](https://docs.binary.ninja/guide/index.html)
- **Generalising to N builds:** xrefs to `CacheEntry.name_len` are grouped by
  referencing *logical function*, with a build-presence strip for each row. The
  counter shows filtered/total both per build and in aggregate.
- **Telling the classes apart:** a reader or writer present in only some builds of
  the same source usually means inlining. Across source revisions it may be new
  code.
- **Pitfalls:** an incomplete xref set presented as complete. IDA's list "may be
  empty or include only recently decompiled functions" until refreshed. Show
  coverage ("decompiled 812/1 204 functions in build-b").

### A10. One model as the source of truth, with provenance and sync state

- **Source:**
  - rev.ng keeps a single YAML *model* of loading information, functions and types.
    Artifacts are derived from it, and user type edits "show up everywhere the struct
    is used".
    [rev.ng model](https://github.com/revng/revng/blob/develop/share/doc/revng/user-manual/key-concepts/model.md)
  - Ghidra's Data Type Manager tags types with their source archive (shown in
    parentheses). It tracks out-of-sync state with *Update / Commit / Revert* and
    renames colliding types with a `.conflict` suffix.
    [DTM help](https://raw.githubusercontent.com/NationalSecurityAgency/ghidra/master/Ghidra/Features/Base/src/main/help/help/topics/DataTypeManagerPlugin/data_type_manager_description.htm)
- **Generalising to N builds:** a shared type library is the "source archive", and
  each build's analysis is a client. Every type shows per build whether it is in
  sync, updated or conflicting.
- **Telling the classes apart:** a per-build *layout override* ("`/Zp1` packing in
  build-d") is compile variance. A per-revision *definition fork* is source variance.
  Keep the two mechanisms separate (**inference**).
- **Pitfalls:** automatic `.conflict` renames multiply types without anyone
  noticing. Show them as open decisions.

---

## (b) What the compiler or optimizer did

### B1. Source-line ↔ assembly colour correlation

- **Source:** In Compiler Explorer, "each line is highlighted with a different
  colour, and … the resulting assembly code corresponding to that line of source code
  is highlighted with the same colour". Output filters hide *Unused labels, Library
  functions, Directives, Comments* and whitespace.
  [WhatIsCompilerExplorer](https://github.com/compiler-explorer/compiler-explorer/blob/main/docs/WhatIsCompilerExplorer.md),
  [godbolt.org](https://godbolt.org/)
- **Generalising to N builds:** show one source pane with a column of assembly per
  build, or a picker. Each source line gets a per-build strip showing instruction
  count or bytes. A line with zero instructions in `build-b` but some in `build-a`
  was inlined elsewhere or eliminated.
- **Telling the classes apart:** needs recorded line tables or debug info per build.
  Without them, line mapping is inferred and must be labelled as such.
- **Pitfalls:** there are only so many distinguishable colours. Cycle colours by
  proximity and add hover-linking, rather than relying on hue alone.

### B2. Optimization remarks inline under source, with an index

- **Source:**
  - LLVM remarks have three kinds: *Passed*, *Missed* and *Analysis*. Each carries
    pass, name, function, an optional debug location, hotness and arguments.
    `opt-viewer.py` produces HTML with remarks as rows under their source line, and
    an index with the columns *Source Location, Hotness, Function, Pass*. It supports
    `--filter` and `--max-hottest-remarks-on-index`.
    `opt-diff.py` compares two runs.
    [LLVM Remarks](https://llvm.org/docs/Remarks.html),
    [opt-viewer.py](https://raw.githubusercontent.com/llvm/llvm-project/main/llvm/tools/opt-viewer/opt-viewer.py)
  - opt-viewer's CSS colours entries green, red and yellow.
    [style.css](https://raw.githubusercontent.com/llvm/llvm-project/main/llvm/tools/opt-viewer/style.css)
  - Compiler Explorer's *Opt Remarks* pane is a source view modelled on opt-viewer,
    with hover remarks.
    [llvm-dev 2017](https://lists.llvm.org/pipermail/llvm-dev/2017-May/112578.html)
- **Generalising to N builds:** the index gains a *builds* column. Remarks are keyed
  by *(logical function, source line, pass, remark name)*, so the view can say, for
  example, "inlined in build-a, build-b; missed in build-c (cost threshold)". An
  opt-diff-style comparison of builds is the natural cross-build view.
- **Telling the classes apart:** remarks describe compilation, so a differing remark
  on the same source is compile variance by definition.
- **Pitfalls:** many legacy toolchains emit no remarks. Never leave the pane blank
  as if nothing happened. Show "no compiler-reported remarks for this toolchain"
  instead. **Inference:** effects reconstructed from the binary (B5–B7) must be
  labelled *observed* and kept apart from *reported* remarks.

### B3. Pass-by-pass pipeline with before and after, hiding passes that changed nothing

- **Source:**
  - Compiler Explorer's *Opt Pipeline* pane shows a before/after diff for each pass.
    *Filters › Hide Inconsequential Passes* hides passes that made no change.
    [CE issue #4169](https://github.com/compiler-explorer/compiler-explorer/issues/4169),
    [Android Developers blog](https://android-developers.googleblog.com/2024/09/become-better-android-developer-compiler-explorer.html)
  - LLVM's `-print-changed` modes are `quiet`, `diff`, `cdiff` (colour) and
    `dot-cfg`. The last creates "a website of DOT files showing colourized changes".
    [DebuggingLLVM](https://llvm.org/docs/DebuggingLLVM.html),
    [D87202](https://reviews.llvm.org/D87202)
- **Generalising to N builds:** show a pipeline strip per build. Where toolchains
  expose different pipelines, align them by stage (front end → IR opt → codegen →
  link), not by pass name. Only toolchains that can dump IR get this view.
- **Telling the classes apart:** the pipeline is by definition a compilation effect
  on fixed input.
- **Pitfalls:** listing every pass by default is noise. Default to consequential
  passes only, and show "N hidden".

### B4. Flags as structured, diffable presets

- **Source:** decomp.me describes compiler flags as typed `FlagSet`s (mutually
  exclusive options) and `Checkbox`es. The MSVC set includes:
  - `/Od /O1 /O2 /Os /Ot /Og /Ox`;
  - `/Ob0 /Ob1 /Ob2`;
  - `/Zp1…/Zp16`;
  - `/Gd /Gr /Gz`;
  - `/GR`, `/GX`, `/Gs`, `/GS-`, `/GZ`.

  Diff options (`-DIFF…`) sit in the same schema.
  [flags.py](https://github.com/decompme/decomp.me/blob/main/backend/coreapp/flags.py)
- **Generalising to N builds:** each build has a *build profile card*. The cross-build
  view is a flag matrix (rows are flag groups, columns are builds) with differing
  cells emphasised. Every compile-variance explanation elsewhere should link to the
  flag cell that explains it, for example `/Zp` → A2 padding, `/Ob` → B1 inlining,
  `/GS-` → B6 cookies.
- **Telling the classes apart:** this is the main evidence source for compile
  variance.
- **Pitfalls:** flags recovered from binary heuristics must be labelled inferred,
  unlike flags recorded from a build log.

### B5. Frame-layout comparison with bijective and non-bijective mapping

- **Source:** reccmp's `stackcmp` pairs stack offsets between original and recompiled
  code. It prints the pairs twice ("ordered by original stack" and "ordered by recomp
  stack") and marks each pair as exact, bijective, non-bijective or "not seen".
  [stackcmp.py](https://github.com/isledecomp/reccmp/blob/master/reccmp/tools/stackcmp.py)
- **Generalising to N builds:** show a slot-mapping matrix per logical local. One
  local mapping to two slots in some build is a split live range or a reused slot.
- **Telling the classes apart:** a non-bijective mapping on the same source is almost
  always compile variance (allocation). Missing locals point towards source variance.
- **Pitfalls:** it only works on diffs that already align, so show "insufficient
  alignment" rather than a wrong mapping.

### B6. Compiler scaffolding kept apart from user logic

- **Source:**
  - objdiff has a dedicated exception-table diff view (`extab_diff.rs`, currently for
    one architecture).
    [objdiff views](https://github.com/encounter/objdiff/tree/main/objdiff-gui/src/views)
  - reccmp's `assert_fixup` replaces assert filename and line immediates with macros
    before diffing.
    [fixes.py](https://github.com/isledecomp/reccmp/blob/master/reccmp/compare/asm/fixes.py)
  - reccmp annotations separate `TEMPLATE`, `SYNTHETIC` (for example scalar deleting
    destructors) and `LIBRARY` from `FUNCTION`.
    [annotations.md](https://github.com/isledecomp/reccmp/blob/master/docs/annotations.md)
- **Generalising to N builds:** in function views, fold prologue and epilogue,
  security-cookie checks, EH state updates and SEH frames into labelled scaffolding
  bands that can be expanded. Band presence is per build (for example "cookie:
  build-a, build-c"), which links to B4 (`/GS-`, `/GX`) (**inference**).
- **Telling the classes apart:** scaffolding differences under different flags are
  compile variance. Synthetic or template entities should not count as source-level
  entities in progress totals.
- **Pitfalls:** hiding scaffolding by default can hide a real mismatch. Collapse it,
  but keep its diff status visible on the collapsed band.

### B7. Switch tables and branches as structure, not only text

- **Source:**
  - reccmp refuses to "relocate" jump-table and data-table entries when it looks for
    moved instructions, because they "most likely" influence behaviour.
    [fixes.py](https://github.com/isledecomp/reccmp/blob/master/reccmp/compare/asm/fixes.py)
  - objdiff draws branch arrows in rotating colours per branch
    (`DiffTextColor::Rotating(branch_idx)`).
    [display.rs](https://github.com/encounter/objdiff/blob/main/objdiff-core/src/diff/display.rs)
  - objdiff has an option to show pooled data references as fake relocations.
    [config-schema.json](https://github.com/encounter/objdiff/blob/main/objdiff-core/config-schema.json)
- **Generalising to N builds:** decode a switch as *case value → target block*. Show
  a per-build table and diff case sets rather than raw table bytes.
- **Telling the classes apart:** the same case set with a different dispatch method
  (jump table, binary search or compare chain) is compile variance. A different case
  set is source variance (**inference**).
- **Pitfalls:** diffing a jump table as data bytes turns every relocation into noise.

### B8. Build inputs outside the source ("compiler entropy") as declared interventions

- **Source:** ReproBit documents *compiler entropy*: "source paths, declaration
  order, object order, debug history, temporary filenames, library scan order" can
  all change output bytes. Every intervention is typed and assigned a fixed cost
  class, from 0 for native output up to 10,000 for direct installation of
  reference bytes.
  [ReproBit concepts](https://github.com/isledecomp/reprobit/blob/main/docs/concepts.md),
  [costs](https://github.com/isledecomp/reprobit/blob/main/docs/costs.md)
- **Generalising to N builds:** each build profile lists its declared interventions
  and their cost. Entity views show the interventions that affected them.
- **Telling the classes apart:** entropy is a third category, next to compile
  variance and source variance. The source is the same and the flags are nominally
  the same, but the bytes differ because of incidental state. Record it explicitly;
  do not collapse it into "compile variance" (**inference**).
- **Pitfalls:** hiding interventions inside a match percentage. Cost must stay
  visible.

---

## (c) Comparing the same function across builds

### C1. A small, fixed taxonomy of instruction-diff kinds with weighted scores

- **Source:**
  - objdiff's instruction diff kinds are `None, OpMismatch, ArgMismatch, Replace,
    Delete, Insert`, and its data diff kinds are `None, Replace, Delete, Insert`.
    Scoring uses weighted penalties: immediate diff 1, register diff 5, replace 60,
    insert or delete 100. The maximum is instructions × 100.
    [diff/mod.rs](https://github.com/encounter/objdiff/blob/main/objdiff-core/src/diff/mod.rs),
    [diff/code.rs](https://github.com/encounter/objdiff/blob/main/objdiff-core/src/diff/code.rs)
  - objdiff's display colours are normal, dim, bright, data-flow, replace (blue),
    delete (red), insert (green) and rotating.
    [display.rs](https://github.com/encounter/objdiff/blob/main/objdiff-core/src/diff/display.rs)
- **Generalising to N builds:** pick one reference per comparison, either a chosen
  build or the recovered-source compile. Show kind counts per build as a stacked
  strip in the entity header. For N builds, show the N×N similarity as a small
  matrix, not N−1 separate pages.
- **Telling the classes apart:** a result that is mostly `ArgMismatch` or
  `OpMismatch` usually means compile variance. `Insert`, `Delete` or `Replace`
  clusters with changed calls usually mean source variance (**heuristic**).
- **Pitfalls:** one percentage hides the kind. Always show the kind breakdown next to
  the score.

### C2. Register-rename-aware highlighting through stable per-value colours

- **Source:**
  - When arguments differ, objdiff gives each distinct differing argument string on
    each side a stable index and colours it `Rotating(i)`. A consistent rename (the
    same pair every time) shows up as one repeated colour pair.
    [code.rs `diff_instruction`](https://github.com/encounter/objdiff/blob/main/objdiff-core/src/diff/code.rs)
  - objdiff also has "click-to-highlight values and registers".
    [objdiff README](https://github.com/encounter/objdiff)
  - decomp.me defines `.rotation0…8` colour classes for light and dark themes.
    [Diff.module.scss](https://github.com/decompme/decomp.me/blob/main/frontend/src/components/Diff/Diff.module.scss)
- **Generalising to N builds:** assign the colour to the *logical value* (for example
  the variable `slotIndex`), not to the register name. The legend then reads
  `slotIndex = esi (build-a) / edi (build-b)`.
- **Telling the classes apart:** a consistent bijective rename is strong evidence of
  compile variance.
- **Pitfalls:** rotating palettes run out (around nine colours). Pair hue with a
  subscript index for accessibility.

### C3. Relocation-aware normalisation with consistent placeholders

- **Source:**
  - reccmp sanitises disassembly. Addresses that can be matched become names; the
    rest become `<OFFSETn>` placeholders numbered "so the number will be consistent
    across the diff". Immediates are replaced only when the relocation table confirms
    they are addresses.
    [parse.py](https://github.com/isledecomp/reccmp/blob/master/reccmp/compare/asm/parse.py)
  - objdiff's *Function relocation diffs* option has four modes: *None*, *Name or
    address*, *Data value*, and *Name or address, data value*.
    [config-schema.json](https://github.com/encounter/objdiff/blob/main/objdiff-core/config-schema.json)
  - decomp.me exposes a diff algorithm choice (Levenshtein or difflib),
    `diff_function_symbols` and `--adjust-vma`.
    [flags.py](https://github.com/decompme/decomp.me/blob/main/backend/coreapp/flags.py)
- **Generalising to N builds:** resolve each relocation to a logical entity (function
  or global) through the cross-build identity map. `build-a:0x0041c880` and
  `build-b:0x0041d1a0` then both render as `ResourceRef::Resolve`.
- **Telling the classes apart:** a relocation that resolves to the *same entity at a
  different address* is layout or link variance. A relocation to a *different
  entity* is a real difference.
- **Pitfalls:** an unresolved address shown as raw hex looks like a mismatch. Mark it
  "unresolved" and keep that distinct from "different".

### C4. "Effective match" as its own status, sorted between exact and partial

- **Source:**
  - reccmp checks whether two sequences "differ only by instruction order or register
    selection". It allows jump-mnemonic swaps paired with swapped `cmp` operands, and
    relocates moved instructions but never jump-table or data-table entries.
    [fixes.py](https://github.com/isledecomp/reccmp/blob/master/reccmp/compare/asm/fixes.py)
  - reccmp's sort order is exact, then effective, then accuracy, with stubs last
    ([report.py](https://github.com/isledecomp/reccmp/blob/master/reccmp/compare/report.py)).
    Effective matches still show a grouped diff; exact matches show none.
  - A downstream reccmp fix records that the HTML viewer mis-rendered effective
    matches as partial after the report field changed. It fixed this with a status
    helper that stays compatible with older reports.
    [agluszak/reccmp#18](https://github.com/agluszak/reccmp/pull/18)
- **Generalising to N builds:** use a status enum per *(entity, build pair)*:
  `exact · effective(reg) · effective(order) · reloc-only · partial · unmatched ·
  stub`. The build matrix cell shows the status glyph, not a number.
- **Telling the classes apart:** every `effective*` and `reloc-only` status is compile
  variance by construction.
- **Pitfalls:** encoding status as a boolean plus a percentage. Consumers will
  mis-sort, as the fix above shows. Never let an effective match count as byte-exact
  in acceptance totals.

### C5. Three-way diff: target, current and previous attempt

- **Source:** decomp.me's diff has `base`, `current` and `previous` columns.
  `ThreeWayDiffBase` is either the *saved* version or the *previous* compile, and
  the interdiff shows what the last edit changed relative to the target.
  [Diff.tsx](https://github.com/decompme/decomp.me/blob/main/frontend/src/components/Diff/Diff.tsx),
  [settings.ts](https://github.com/decompme/decomp.me/blob/main/frontend/src/lib/settings.ts)
- **Generalising to N builds:** there are two uses.
  - For recovery work: target build versus current candidate versus previous
    candidate.
  - For variant analysis: reference build versus build-x versus build-y. This shows
    which differences are shared across variants and which are unique to one.
- **Telling the classes apart:** differences shared by all variants of one
  toolchain, and absent from another, point to compile variance.
- **Pitfalls:** three columns at phone width. Offer a stacked mode with a column
  picker.

### C6. Combining multiple samples, with an explicit "varies" state

- **Source:** reccmp's `combine_reports` merges reports from several builds of the
  same target. It keeps each entity's best result and sets `recomp_addr_varies` when
  the address differs across samples. `function_count` is the maximum across samples
  "since some functions may have been inlined in some reports". Reports built from
  different source files are rejected (`ReccmpReportSameSourceError`).
  [report.py](https://github.com/isledecomp/reccmp/blob/master/reccmp/compare/report.py)
- **Generalising to N builds:** this is a working precedent for N-build aggregation.
  It has three parts:
  - an entity-keyed merge;
  - a *varies* flag instead of a fake single value;
  - a denominator taken as the maximum across builds.
- **Telling the classes apart:** reccmp enforces "same source" at the aggregation
  boundary. The equivalent here is to refuse to aggregate across source revisions,
  and to show those as separate groups (**inference**).
- **Pitfalls:** "best across samples" is optimistic. Show the best, the worst and the
  build that achieved each.

### C7. Correlation tables with score, confidence, status and change flags

- **Source:**
  - Ghidra Version Tracking runs *correlators* over two programs. Its matches carry a
    score, and users *accept* or *reject* them; accepting blocks conflicting matches.
    Accepting also creates *implied matches* for callees, and *markup items* (names,
    comments, types) can be ported to the other program.
    [VT intro](https://raw.githubusercontent.com/NationalSecurityAgency/ghidra/master/Ghidra/Features/VersionTracking/src/main/help/help/topics/VersionTrackingPlugin/Version_Tracking_Intro.html)
  - BinDiff's matched-functions table carries similarity, confidence and change flags
    `G I O J E L C` (graph, instruction, operand, jump, entry point, loop, call).
    Rows are coloured from green to red. Flow-graph nodes are green (identical),
    yellow (changed) or red (unmatched).
    [BinDiff manual](https://www.zynamics.com/bindiff/manual/)
  - Diaphora ports structs and enums, diffs pseudocode and microcode, and supports
    manual matches and compilation units.
    [Diaphora README](https://github.com/joxeankoret/diaphora)
  - objdiff lets the user map a left symbol to a right symbol by hand when names
    differ.
    [symbol_diff.rs](https://github.com/encounter/objdiff/blob/main/objdiff-gui/src/views/symbol_diff.rs)
- **Generalising to N builds:** the identity table is keyed by logical entity, with
  one cell per build. Each cell holds the address, the correlator that proposed it,
  the score and the status (accepted, rejected, blocked or implied). Change flags
  become per-pair chips.
- **Telling the classes apart:** BinDiff-style flags are a useful classifier:
  - `O` or `I` only suggests compile variance;
  - `G`, `C` or `L` suggests source variance (**heuristic**).
- **Pitfalls:** identity confidence and code equality are separate axes, but they are
  often merged into one colour. Keep one axis for identity ("is this the same
  function?") and another for code ("does it compile the same?").

### C8. Side-by-side named witnesses

- **Source:** Dogbolt shows the output of several decompilers for one binary, side by
  side.
  [decompiler-explorer](https://github.com/decompiler-explorer/decompiler-explorer)
- **Generalising to N builds:** the axes are witness × build. Default to one witness
  across builds, or several witnesses for one build. Never show the full grid at
  once.
- **Telling the classes apart:** if every witness shows the same difference between
  builds, the difference is real. If witnesses disagree, it may be a decompiler
  artefact.
- **Pitfalls:** unnamed or unversioned witnesses. Always show the tool name and
  version.

### C9. "Why doesn't this match": specialised explainers for each entity kind

- **Source:** reccmp includes:
  - `vtable`, which always shows the full diff for vtables;
  - `datacmp`, for globals;
  - `stackcmp`, see B5;
  - `roadmap`, which reports "how far off" a symbol is from its original place.

  The HTML report search offers *Name/address*, *Asm output* and *Asm diffs only*
  modes.
  [tools/](https://github.com/isledecomp/reccmp/tree/master/reccmp/tools),
  [searchOptions.js](https://github.com/isledecomp/reccmp/blob/master/reccmp/assets/components/searchOptions.js)
- **Generalising to N builds:** an entity's *Explain* panel runs a fixed checklist,
  and each item gives an answer and its evidence:
  - flag differences (B4);
  - register rename (C2);
  - relocation/layout (C3);
  - frame (B5);
  - scaffolding (B6);
  - switch lowering (B7);
  - placement (roadmap);
  - entropy interventions (B8);
  - source identity.

  The panel ends in a variance class (**inference**, assembled from the sources
  above).
- **Pitfalls:** free-text explanations without evidence links. Every item needs a
  jump to the rows or bytes behind it.

---

## (d) Presenting project outputs and exports

### D1. A typed report schema with explicit measures and progress categories

- **Source:**
  - objdiff's `report.proto` `Measures` defines:
    - `fuzzy_match_percent`;
    - total and matched code, with `matched_code_percent`;
    - total and matched data;
    - total and matched functions;
    - *complete* ("linked") code, data and units.

    Units carry `ReportUnitMetadata` (complete, module, source path, progress
    categories, auto-generated).
  - `changes.proto` pairs a `from` report with a `to` report for each unit and item.

  [protos/](https://github.com/encounter/objdiff/tree/main/objdiff-core/protos)
- **Generalising to N builds:** key report rows by *(build, unit, entity)*. Keep
  `matched` (compared equal) separate from `complete/linked` (actually in the final
  image). A per-build `Measures` block, plus an across-builds block made with C6
  rules, lets users compare builds without flattening them.
- **Pitfalls:** `fuzzy_match_percent` looks like progress, but it counts partial
  matches. Label fuzzy, matched and linked separately and never add them together.

### D2. A treemap of units where "done" is a categorical colour

- **Source:** decomp.dev draws units as a treemap sized by bytes.
  `unit_color` returns a distinct green only at exactly 100%. Otherwise it mixes grey
  towards blue by fuzzy percent, so "almost" never looks like "done".
  [treemap.rs](https://github.com/encounter/decomp.dev/blob/main/crates/images/src/treemap.rs),
  [treemap.ts](https://github.com/encounter/decomp.dev/blob/main/js/treemap.ts)
- **Generalising to N builds:** show small multiples, one treemap per build with the
  same unit layout. Alternatively, use one treemap whose cells are split into N
  slivers.
- **Pitfalls:** a continuous colour ramp ending in the "done" colour. Keep "done"
  categorical.

### D3. History and versions: reports keyed by commit × version

- **Source:** decomp.dev stores reports per *(project, commit sha, version)*, with
  `report_versions` and `default_version`, and draws a history chart over commits.
  [project.rs](https://github.com/encounter/decomp.dev/blob/main/crates/web/src/handlers/project.rs),
  [history.ts](https://github.com/encounter/decomp.dev/blob/main/js/history.ts)
- **Generalising to N builds:** "version" maps directly onto build-a…build-d. The
  history chart has one line per build, and the default build is a user preference,
  not a hard-coded binary.
- **Pitfalls:** a single-version default that hides the others. Show every build's
  latest value in the legend.

### D4. Change summaries: new, broken, improved, regressed

- **Source:** decomp.dev's GitHub comment groups changes into *new match*, *broken
  match*, *improvement in an unmatched item* and *regression in an unmatched item*.
  - Each group is a collapsible `<details>` table with the columns *Unit, Item,
    Bytes, Before, After*, truncated with "…and N more".
  - When a report is missing, the comment says so explicitly: "Base report not
    found…", "PR report not found…".
  - Several versions are combined in one comment.

  [changes.rs](https://github.com/encounter/decomp.dev/blob/main/crates/github/src/changes.rs)
- **Generalising to N builds:** each run produces the four groups per build. A
  *broken match* in any build is surfaced first.
- **Telling the classes apart:** a broken match in only one toolchain family suggests
  compile or entropy variance. One broken in every build suggests a source edit.
- **Pitfalls:** reporting "no changes" when a report is actually *missing*. The
  explicit missing-report message is the pattern to copy.

### D5. A self-contained HTML report with client-side filtering

- **Source:** reccmp's HTML report is one template with small web components:
  - `search-bar`, whose modes are name or address, asm output, and asm diffs only;
  - `hide-perfect`, which also hides effective matches;
  - `hide-stub`;
  - `show-recomp`;
  - pagination;
  - click-to-copy.

  The inline diff table has orig and recomp address columns, with `-`/`+` rows.
  [assets/](https://github.com/isledecomp/reccmp/tree/master/reccmp/assets),
  [diffDisplay.js](https://github.com/isledecomp/reccmp/blob/master/reccmp/assets/components/diffDisplay.js),
  [state.js](https://github.com/isledecomp/reccmp/blob/master/reccmp/assets/state.js)

  A downstream matching-decomp project publishes per-binary SVG progress badges that
  link to these HTML reports.
  [ReproBit README, reference case](https://github.com/isledecomp/reprobit#readme)
- **Generalising to N builds:** the export is one file per run containing all builds,
  with a build filter. Rows are keyed by entity, with a status glyph per build.
- **Pitfalls:** "Hide 100%" that also hides effective matches, without saying so.
  Name the filter after what it hides.

### D6. The accuracy report is separate from the certification report

- **Source:**
  - A matching-decomp project publishes two reports for each binary: a reccmp
    *accuracy* report and a separate *verification* report from a cold rebuild.
  - ReproBit reports three independent claims:
    - **byte exact**;
    - **logic certified** (every adjustment passed its preservation checks in this
      run);
    - **toolchain origin** (the output traces back to declared compiler and linker
      outputs, not copied reference bytes).
  - The producer cannot read the reference.
  - `verify` never uses the build cache.
  - The report shows the intervention cost (see B8).

  [ReproBit README](https://github.com/isledecomp/reprobit#readme),
  [concepts](https://github.com/isledecomp/reprobit/blob/main/docs/concepts.md)
- **Generalising to N builds:** every build gets its own acceptance row with the
  three claims shown separately. A build with 100% function accuracy but no fresh
  whole-image verification is visibly *not accepted*. This matches the project's
  STRATEGY rule, which keeps accuracy and whole-image acceptance apart.
- **Pitfalls:** one green check that merges accuracy, exactness and provenance.

### D7. Run artifacts that can be browsed again without re-running

- **Source:**
  - Mizuchi writes `run-results-{timestamp}.json` and
    `run-report-{timestamp}.html` for each run.
    [mizuchi](https://github.com/macabeus/mizuchi)
  - capa Explorer Web loads saved JSON from a file or URL (gzip included) and works
    offline. It shows a rule-match tree that can be expanded, and it groups results
    by function or by process.
    [capa explorer](https://github.com/mandiant/capa/tree/master/web/explorer)
  - APKMan caches by SHA-256 of the input, groups search results by category, and
    exports a ZIP.
    [apkman](https://github.com/jiusanzhou/apkman)
  - RzWeb supports snapshots and project-bundle export.
    [rzweb](https://github.com/IndAlok/rzweb)
- **Generalising to N builds:** key artifacts by *(input digest, build profile, run
  id)*. The report viewer loads any past run and labels it as reused, with its date
  and origin.
- **Pitfalls:** a reloaded old run that looks identical to a fresh one. Show the run
  timestamp and a *reused* badge.

### D8. Claims that cite evidence, with a verification state

- **Source:** Rev·Deck cites evidence as `[function:0xADDR]`, `[string:0xADDR]` or
  `[import:name]`, and flags any claim whose citation does not match retrieved
  evidence as "(unverified)". A sub-investigation's conclusion goes back to its
  parent as a tagged summary card.
  [ai-reverse-engineering](https://github.com/biniamf/ai-reverse-engineering)
- **Generalising to N builds:** citations name the entity and the build, for example
  `[fn:ResourceRef::Resolve@build-b]`. A claim about "all builds" must cite each
  build, or say which builds it was not checked against.
- **Pitfalls:** citations that name addresses with no build. The same address means
  different things in different builds.

### D9. Navigation that follows the user, with writes gated

- **Source:**
  - idarem offers *Follow IDA* (the browser tracks the native tool over SSE) and a
    *Drive* mode. Writes need explicit opt-in (`IDAREM_ALLOW_WRITE=1`), and panes
    are virtualised.
    [idarem](https://github.com/xsslize/idarem)
  - r2web offers goto, search in large outputs, and a graph view.
    [r2web](https://github.com/radareorg/r2web)
- **Generalising to N builds:** "follow" is keyed by entity. Selecting
  `CacheEntry.name_len` in any pane moves every build column to its own address for
  that field.
- **Pitfalls:** following raw addresses across builds lands on unrelated code.

---

## Patterns to adopt, adapt or avoid

| # | Pattern | Verdict | How it applies to build-a…build-d | Source |
|---|---|---|---|---|
| A1 | Address as an editable expression (module + offset, `[deref]`) | **Adapt** | Write the chain in logical names and resolve it per build into columns | [ReClass.NET](https://github.com/ReClassNET/ReClass.NET#tips) |
| A2 | Component table (offset, length, type, name, comment) with filler visible | **Adopt** | One row set, per-build offset and size columns, per-build padding | [Ghidra StructureEditor](https://raw.githubusercontent.com/NationalSecurityAgency/ghidra/master/Ghidra/Features/Base/src/main/help/help/topics/DataTypeEditors/StructureEditor.htm) |
| A3 | Gap markers and create-member-at-accessed-offset | **Adapt** | Merge accesses from all builds; auto members are marked inferred | [Binary Ninja](https://docs.binary.ninja/guide/types/basictypes.html), [rev.ng](https://github.com/revng/revng/blob/develop/share/doc/revng/user-manual/tutorial/editing-types-in-c.md) |
| A4 | Shifted pointer / `ADJ()` for this-adjust | **Adopt** | Per-build delta badge linked to the base-layout row | [IDA tip #54](https://hex-rays.com/blog/igors-tip-of-the-week-54-shifted-pointers) |
| A5 | Frame as a pseudo-struct with signed offsets and `r`/`s` | **Adopt** | Locals keyed by logical name, slot per build, R/S per build | [IDA tip #65](https://hex-rays.com/blog/igors-tip-of-the-week-65-stack-frame-view) |
| A6 | Pointer preview; vtable, array and RTTI nodes | **Adapt** | Slots keyed by logical method; no live-memory "changed" colour | [ReClass.NET](https://github.com/ReClassNET/ReClass.NET#features) |
| A7 | Grouped multi-instance dissect | **Adopt** | Instances become builds; groups become toolchain or source revision | [CE dissect](https://cheatengine.org/help/dissect-datastructures.htm) |
| A8 | Rescan and intersect pointer paths | **Adapt** | "Valid in k/N builds" for chains and signatures | [CE pointer scan](https://cheatengine.org/help/pointer-scan.htm) |
| A9 | Field xrefs with direction, kind and filtered/total count | **Adopt** | Grouped by logical function, build-presence strip, coverage shown | [Binary Ninja](https://docs.binary.ninja/guide/index.html), [IDA tip #18](https://hex-rays.com/blog/igors-tip-of-the-week-18-decompiler-and-global-cross-references) |
| A10 | Single model; type archives with Update/Commit/Revert | **Adapt** | Shared type library with per-build sync state; layout override kept apart from definition fork | [rev.ng model](https://github.com/revng/revng/blob/develop/share/doc/revng/user-manual/key-concepts/model.md), [Ghidra DTM](https://raw.githubusercontent.com/NationalSecurityAgency/ghidra/master/Ghidra/Features/Base/src/main/help/help/topics/DataTypeManagerPlugin/data_type_manager_description.htm) |
| — | Automatic `.conflict` renaming | **Avoid** | Show conflicts as open decisions instead | same |
| B1 | Source-line ↔ asm colour correlation | **Adopt** | Per-build instruction strip per line; inferred line maps labelled | [CE docs](https://github.com/compiler-explorer/compiler-explorer/blob/main/docs/WhatIsCompilerExplorer.md) |
| B2 | Remarks inline and indexed, plus opt-diff | **Adopt where emitted** | Index gains a builds column; "no remarks for this toolchain" state | [LLVM Remarks](https://llvm.org/docs/Remarks.html) |
| B3 | Pass pipeline, hiding passes that changed nothing | **Adapt** | Only for toolchains that dump IR; align by stage | [CE #4169](https://github.com/compiler-explorer/compiler-explorer/issues/4169), [DebuggingLLVM](https://llvm.org/docs/DebuggingLLVM.html) |
| B4 | Typed flag presets | **Adopt** | Build profile card plus a flag matrix across builds | [decomp.me flags.py](https://github.com/decompme/decomp.me/blob/main/backend/coreapp/flags.py) |
| B5 | Bijective stack-slot mapping | **Adopt** | Slot-mapping matrix per local | [reccmp stackcmp](https://github.com/isledecomp/reccmp/blob/master/reccmp/tools/stackcmp.py) |
| B6 | Scaffolding bands (EH, cookie, assert) and synthetic/library tags | **Adapt** | Collapsed but status-visible bands, linked to flags | [reccmp annotations](https://github.com/isledecomp/reccmp/blob/master/docs/annotations.md) |
| B7 | Switch as a case→target table | **Adopt** (inference) | Diff case sets, not table bytes | [reccmp fixes.py](https://github.com/isledecomp/reccmp/blob/master/reccmp/compare/asm/fixes.py) |
| B8 | Declared entropy interventions with cost | **Adopt** | A third variance class next to compile and source variance | [ReproBit costs](https://github.com/isledecomp/reprobit/blob/main/docs/costs.md) |
| C1 | Fixed diff-kind taxonomy and weighted score | **Adopt** | Kind strip per build; N×N matrix | [objdiff code.rs](https://github.com/encounter/objdiff/blob/main/objdiff-core/src/diff/code.rs) |
| — | A single % as the only indicator | **Avoid** | Always show kind breakdown and denominator | — |
| C2 | Stable rotating colour per differing value | **Adapt** | Colour the logical value, not the register | [objdiff display.rs](https://github.com/encounter/objdiff/blob/main/objdiff-core/src/diff/display.rs) |
| C3 | `<OFFSETn>` placeholders and relocation-diff modes | **Adopt** | Resolve through the cross-build entity map; "unresolved" is not "different" | [reccmp parse.py](https://github.com/isledecomp/reccmp/blob/master/reccmp/compare/asm/parse.py), [objdiff schema](https://github.com/encounter/objdiff/blob/main/objdiff-core/config-schema.json) |
| C4 | Effective match as its own status | **Adopt** | Status enum per build pair; never counted as byte-exact | [reccmp report.py](https://github.com/isledecomp/reccmp/blob/master/reccmp/compare/report.py) |
| — | Status as boolean + percentage | **Avoid** | Caused the mis-sort fixed in [reccmp#18](https://github.com/agluszak/reccmp/pull/18) | — |
| C5 | Three-way diff (base, current, previous) | **Adopt** | Reference vs two variants, or target vs candidate vs previous | [decomp.me Diff.tsx](https://github.com/decompme/decomp.me/blob/main/frontend/src/components/Diff/Diff.tsx) |
| C6 | Multi-sample aggregate with a `varies` flag, max denominator, same-source guard | **Adopt** | N-build aggregation; refuse to aggregate across source revisions | [reccmp report.py](https://github.com/isledecomp/reccmp/blob/master/reccmp/compare/report.py) |
| C7 | Correlator table (score, status, implied matches, markup porting, change flags) | **Adopt** | Identity table keyed by entity; identity and code axes kept separate | [Ghidra VT](https://raw.githubusercontent.com/NationalSecurityAgency/ghidra/master/Ghidra/Features/VersionTracking/src/main/help/help/topics/VersionTrackingPlugin/Version_Tracking_Intro.html), [BinDiff](https://www.zynamics.com/bindiff/manual/) |
| C8 | Named decompiler witnesses side by side | **Adapt** | Witness × build; never the full grid | [Dogbolt](https://github.com/decompiler-explorer/decompiler-explorer) |
| — | Auto-uploading to public witness services | **Avoid** | See FRONTEND_INTENT §7 boundary | — |
| C9 | Explainer tools per entity kind (vtable, data, stack, placement) | **Adopt** | "Explain" checklist ending in a variance class, with evidence links | [reccmp tools](https://github.com/isledecomp/reccmp/tree/master/reccmp/tools) |
| D1 | Typed report with fuzzy, matched and linked measures kept apart | **Adopt** | Measures per build plus an across-builds block | [objdiff protos](https://github.com/encounter/objdiff/tree/main/objdiff-core/protos) |
| D2 | Treemap with a categorical "done" colour | **Adopt** | Small multiples per build | [decomp.dev treemap.rs](https://github.com/encounter/decomp.dev/blob/main/crates/images/src/treemap.rs) |
| D3 | Reports keyed by commit × version | **Adopt** | Version = build; one line per build | [decomp.dev project.rs](https://github.com/encounter/decomp.dev/blob/main/crates/web/src/handlers/project.rs) |
| D4 | New, broken, improved, regressed groups with an explicit missing-report message | **Adopt** | Per build; broken-in-any-build first | [decomp.dev changes.rs](https://github.com/encounter/decomp.dev/blob/main/crates/github/src/changes.rs) |
| D5 | Self-contained HTML report with client filters | **Adapt** | One export covering all builds; filters named for what they hide | [reccmp assets](https://github.com/isledecomp/reccmp/tree/master/reccmp/assets) |
| D6 | Accuracy separate from certification (exact, logic, origin) | **Adopt** | Acceptance row per build with three claims | [ReproBit](https://github.com/isledecomp/reprobit/blob/main/docs/concepts.md) |
| — | One green check that merges accuracy and acceptance | **Avoid** | Conflicts with STRATEGY acceptance | — |
| D7 | Re-browsable run artifacts keyed by input digest | **Adopt** | *Reused* badge and run timestamp | [capa explorer](https://github.com/mandiant/capa/tree/master/web/explorer), [APKMan](https://github.com/jiusanzhou/apkman) |
| D8 | Evidence citations with an "(unverified)" state | **Adopt** | Citations name entity@build | [Rev·Deck](https://github.com/biniamf/ai-reverse-engineering) |
| D9 | Follow/drive navigation with gated writes | **Adapt** | Follow by entity, not by address | [idarem](https://github.com/xsslize/idarem) |
| — | Any view whose root is one binary's address space | **Avoid** | Build is a facet of the entity, not the page root | premise |

## Not covered or not verified

- **Grapefruit.** Its runtime, hook and backtrace views
  ([grapefruit](https://github.com/ChiChou/grapefruit)) belong to an optional dynamic
  provider. None of the four concerns here needs them, so no pattern was taken.
- **Proprietary tool UIs.** Details for IDA, Binary Ninja and BinDiff come from their
  public docs only. The tools themselves were not run.
- **Compiler Explorer.** The pane names come from its docs, issue tracker and site
  menu. Its source code was not read.
- **Licensing.** No licence review was done for reusing any upstream source. This note
  borrows interaction patterns only.
