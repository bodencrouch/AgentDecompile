# CompilerLayer

CompilerLayer is a toggleable annotation layer over Listing, DecompileView and SplitCompare that shows what the compiler and linker did to the code under the cursor. Each annotation is a gutter tag plus a word with its evidence level. Where builds differ, it says which builds show the transformation and how the difference is classed.

**Use it** as a layer, never as a separate view: the Views toolbar's **Compiler layer** toggle (`c` in a code well) turns it on for every visible code well of the Code Browser and for SplitCompare. It reads only stored detector output, so it follows the cursor like the well it decorates.

**Consumer provides**, per build and address range:

- the detector id and the transformation kind;
- the evidence: witness (PDB inline-site record, FuncInfo, scope table, jump-table parse, relocation, Rich header) or heuristic, with its basis;
- the kind's parameters: the inlinee entity, the folded entities, the divisor, the EH state number and object, the switch cases, the intrinsic;
- the cross-build presence of the same logical transformation (keyed by entity and kind, not address);
- the recorded source digest, toolchain and flags per build, so a presence difference can be classed;
- the research section id for each kind.

## Anatomy

- **Layer bar** above the well: the `Compiler layer` toggle (`aria-pressed`), FilterChips for **Kind** (a multi-select of the kinds below) and **Presence** ("varies across builds" is the Compiler Explorer–style "changed anything" filter), and the count "9 of 14 annotations shown · 5 hidden by Kind". Hidden annotations are counted, never silently dropped.
- **Gutter column** in the well, before the address: a bracket (`┌ │ └` for ranges, `▪` for one row) and the kind **tag** in bold mono (`INL`, `ICF`, `GS`, `EH`, `SEH`, `DIV`, `TAIL`, `SW`, `FPO`, `ILT`, `HP`, `STR`, `LOOP`, `INTR`, `CC`). The tag is the word; the bracket is `aria-hidden`.
- **Annotation band** on the first row of a range: tag, a plain phrase ("inlined ResourceRef::Resolve", "folded with 3 functions", "FH3 state 0: tmp is live", "÷ 10 (signed)", "switch · cases 0, 1, 2, 5 · default"), the evidence chip, a **presence** strip ("b c inlined · a call · d unknown: ResourceRef::Resolve is unresolved on build-d"), and a link to the research section. A band is framed solid when its evidence is solid and dashed when it is a hypothesis.
- **Cross-build note** under a range whose presence varies: the difference class and cause, for example "Same source, compiled differently · inlined in build-b, build-c; call in build-a → LTCG on build-b and build-c, none on build-a · hypothesis (heuristic), basis: …".
- **Remarks under the source line** in DecompileView (after Compiler Explorer's opt remarks): a row under the decompiled line with the tag and a readable rewrite ("÷ 10 · write n / 10 with a signed n"; "/GS cookie scaffolding, not user logic"). Scaffolding (GS, EH, SEH, RTC, HP) stays visible but is labelled as scaffolding, and its diff status is never hidden.
- **SplitCompare:** each side carries its own gutter tags, and the note between rows classes the pair.
- **Legend** (a `<dl>` described by the well): every kind with its tag, meaning, count in this function and research section, plus the three evidence levels.

## States

**Kinds** (tag · word · research section):

| Tag | Annotation | Research |
|---|---|---|
| INL | inlined callee range, "inlined ‹callee›", out-of-line twin linked | T3 |
| ICF | "folded with N functions", every entity listed | T6 |
| GS | /GS cookie prologue and epilogue | T8 |
| EH | EH registration; "FH3 state N: ‹object› is live" per state write (the handler generation is named from the build's evidence: "state N" under `__CxxFrameHandler`, "FH3 state N" under `__CxxFrameHandler3`, "FH4 tables" on x64) | T9 |
| SEH | SEH scope, try level, filter and handler blocks | T10 |
| DIV | magic-number divide, "÷ 10", signedness | I2 |
| TAIL | tail call | I4 |
| SW | switch table with its case set and dispatch (table, byte index, compare tree) | I1 |
| FPO | ESP frame, FPO; EBP used as data | T2 |
| ILT | incremental-link thunk | T12 |
| HP | hotpatch prologue and padding | T13 |
| STR | string-pooled constant, "one copy for N uses" | T7 |
| LOOP | loop rotation and unrolling; strength reduction | I5 |
| INTR | intrinsic expansion, "rep movsd = memcpy, 64 bytes"; "repne scasb = strlen" | T4 |
| CC | calling convention: "__thiscall · this in ecx"; "LTCG custom convention · this in esi" | §4, T5 |

`/RTC` fills, `__chkstk` probes and bool idioms (`neg/sbb`) use the same band with the tags `RTC`, `PROBE` and `BOOL` when their detectors exist (T11, I8, I3).

**Evidence:** witness or record (solid; a PDB record, FuncInfo, table parse or an unambiguous byte pattern) · hypothesis (heuristic) (dashed; basis named: clone similarity, pattern match without a witness) · unknown (the word; nothing drawn in the gutter).

**Presence across builds:** each build is written as present, absent, or with its alternative form ("call", "call memcpy", "call + ret"), or as "unknown" when that build has no detector output. The presence line is classed as one of four:

- same source, compiled differently, with the cause (/Ob, LTCG, /GS, /Oy, EH model, register allocation, scheduling);
- same source and flags, build state differs (entropy);
- source changed;
- unknown.

**Layer states:** off (the wells render as usual) · on · filtered ("5 hidden by Kind") · "No detector output for build-c · Not loaded" (the build's gutter is empty with that notice, never a guess) · stale ("◷ detectors ran on basis b7e2; program changed since").

Difference classes use VariantRelation's glyphs and words: `≈` same source, compiled differently (compile variance) · `∼` same source and flags, build state differs (entropy) · `≠` source changed · `?` unknown · `≡` identical. Evidence words are shared with ToolchainEvidence: **witness** or **record** (solid frame), **hypothesis (heuristic)** (dashed frame, basis named), **unknown** (italic word, no frame). A build-wide cause (a flag, LTCG, /GS, /Oy, EH model, ICF) links to ToolchainEvidence (`ws=evidence&panel=toolchain&build=…`) instead of restating its evidence.

## Linking

- **Publishes:** the layer toggle and Kind filter replace `layers=compiler` and `f=xform:inline,eh…` (both registered) in the URL after the settle. Enter on a band is Go to the transformation's subject (the inlinee entity, a folded entity, the switch table), with one history stop. Enter on a tag highlights its range (reflection marks) without moving history.
- **Follows:** the well it decorates. It is on whenever the toggle is on, and holdable with that well.
- **Targets rendered:** logical id (inlinee, folded entities) · address and symbol (twin body, table, thunk target) · counterpart (presence cells for other builds, with edge words) · receipt (detector receipt in the Peek) · research section (native `/docs` link).
- **Peek source:** the stored detector record (detector id, version, evidence, parameters) and the per-build presence row. Nothing is re-detected.
- **Absent copy:** "absent in build-a" · "unknown: no detector output for build-d" · "Not loaded. Open build-c to read it." · "folded with 3 functions" never picks one name as the function's name.
- **Target-size exception:** research and entity links inside 16px bands use the code-well inline exception; band rows are reached by row focus and the 44px row-menu button with a coarse pointer.

## Keyboard

- `c` (registered `code.compilerLayer`, code scope) toggles the layer. It only changes view state and posts nothing.
- `a` / Shift+A (`code.annotationNext` / `code.annotationPrev`; `{`/`}` stay with ListingFieldLayout's flow arrows) move the cursor to the next or previous annotation of the visible kinds and announce it ("Annotation 3 of 9: inlined ResourceRef::Resolve, hypothesis").
- Enter on a band's subject is Go; Enter on a tag highlights its range; Alt+↓ peeks the detector record; Shift+F10 opens the link menu (Reveal in: TransformTimeline, MatchExplain, Evidence).
- The FilterChips follow FilterChip's keys. Esc follows `keymap.json` `escapeOrder`.

## Accessibility

- Bands and remark rows are rows in the well's grid. Each is named in words: "Annotation start: inlined ResourceRef::Resolve, hypothesis, present in build-b, build-c; call in build-a; unknown on build-d".
- An annotated instruction row appends the tag word to its name ("…, inlined ResourceRef::Resolve"). The bracket glyphs are `aria-hidden`.
- The legend is a `<dl>` tied to the well with `aria-describedby`. Counts are text.
- Screen-reader verbosity "off" drops bands to the tag word only; Accessible View lists every annotation as text.
- Forced colors: band frames stay solid or dashed in `CanvasText` (dashed only for a hypothesis), and highlighted ranges use the solid 1px reflection outline.

**Research:** [MSVC transformations §2–§5, §9.2](../../../../research/2026-09-29-msvc-optimization-for-decomp.md#9-ui-implications); [reference UI patterns B1, B2, B6, B7, C8](../../../../research/2026-09-29-reference-re-ui-patterns.md).

**Prior art:** compiler-explorer `static/panes/opt-view.ts` (remarks under source lines, filtered by kind), `static/line-colouring.ts` (source↔asm correlation) · reccmp `docs/annotations.md` (FOLDED, SYNTHETIC, LIBRARY), `reccmp/compare/asm/fixes.py` (jump tables kept as structure) · objdiff `objdiff-core/src/diff/display.rs` (branch and relocation marks) · ghidra `Ghidra/Features/Decompiler/src/main/help/help/topics/DecompilePlugin/DecompilerAnnotations.html`.
