# MatchExplain

MatchExplain explains why a recompiled candidate does not match its target bytes. It classifies every residual difference in the style of reccmp and objdiff, gives each class its evidence and a next step in words, and keeps "effective match", local match and whole-image claims separate.

**Use it** in the Recovery and Compare workspaces beside ObjectDiff, and as a rail section for a function with a failed or near local match. It explains a stored comparison receipt; it never compiles or compares to draw itself.

**Consumer provides**

- the target (entity @ build, address range) and the candidate (revision, its compile recipe: compiler, flags, TU, pragma overrides);
- the stored relocation-aware diff rows;
- the classifier output per row, with evidence;
- the stack-layout comparison;
- the toolchain evidence for the target build (Rich header, linker version) and the pinned recipe;
- the separate fact states: Local match, Linked match, Whole-file equality;
- the identity opinions for the target: each matcher and its own score.

## Anatomy

- **Claim line:** "local ≠ whole-image proof · effective ≠ byte match · aligned ≠ equivalent", then the receipt stamp (fresh or reused, receipt, recipe, time).
- **Status row:** separate items, never summed.
  - FactBadges for Local match, Linked match and Whole-file equality.
  - An **Effective match** state of its own. "no · 3 rows are not register-only" has a solid frame; "yes (register allocation only)" has a dashed frame. It is listed between exact and partial and never counted as byte-identical.
  - An optional objdiff fuzzy percentage, labelled "truncated, never rounded up · not a claim". It never shows 100% unless the rows are byte-identical.
- **Class table:** one row per class, with the row count, the evidence and a **Next** step in words. Zero-count classes stay listed in `ink-muted`, and uncounted classes show "—" with a hypothesis or the word unknown.

| Class | Next step (example) |
|---|---|
| Register allocation only (effective-match class; not byte-identical) | try declaration order, or a named temporary |
| Instruction scheduling or reordering | split or join the expression; check where the value is first used |
| Stack slot or local ordering | try declaration order; open FrameLayout |
| Relocation or address only (not a code difference; inferred sizes labelled "(inferred)") | none; resolved through the identity map |
| Constant or immediate differs | check the source constant and its signedness |
| Different branch structure | try loop form, ternary against if, case order |
| Missing or extra inlining | check /Ob and where the helper is defined |
| Toolchain or flags mismatch | compare the recipe in ToolchainEvidence before editing source |
| Source difference | resolve the classes above first |

- **Rows:** a read-only grid (target address, target, candidate, class word). Consistent register renames use objdiff's stable pairing, drawn as a lettered, framed pair (`esi A ↔ edi A`) with the words, never color alone. Differing immediates are bold with the `fact-stale` underline.
- **Identity opinions:** "Is the target this entity?", with each matcher and its own score and evidence ("BSim · 0.91 · its own scale"; "rare-ref anchors · 3 shared"). Scores from different matchers are never compared, averaged or merged into one number.

## States

- Local match: passed, failed, stale, unknown or not run (FactBadge). Effective match: yes (register allocation only) · yes (order only) · no, with the count of rows that block it · not applicable (exact).
- Class rows: counted · zero · hypothesis (dashed chip, basis named) · unknown.
- Receipt: fresh · reused · historical ("◷ compiled from r14; source is r15"; the rows are marked historical, never current).
- No receipt: "No comparison receipt for this pair. Nothing is compiled from here." The one armed fix comes from the catalog and is never run.

Difference classes use VariantRelation's glyphs and words: `≈` same source, compiled differently (compile variance) · `∼` same source and flags, build state differs (entropy) · `≠` source changed · `?` unknown · `≡` identical. Evidence words are shared with ToolchainEvidence: **witness** or **record** (solid frame), **hypothesis (heuristic)** (dashed frame, basis named), **unknown** (italic word, no frame). A build-wide cause (a flag, LTCG, /GS, /Oy, EH model, ICF) links to ToolchainEvidence (`ws=evidence&panel=toolchain&build=…`) instead of restating its evidence.

## Linking

- **Publishes:** nothing on focus. Enter on a class filters the rows to it (`f=diffclass:regalloc`, registered; replaceState). Enter on an address is Go to the Listing at that build. The ToolchainEvidence link is a Go to that build's column in ToolchainEvidence. Open beside holds the pair (`hold=receipt:3e10@build-b`).
- **Follows:** the entity and the object pair recorded for it, on Enter (derived pane). Holdable.
- **Targets rendered:** address (target rows) · receipt and job (stamp) · fact (badges open their Peek) · FrameLayout (kept card, `keep=frame:88@build-b`) · ToolchainEvidence (`ws=evidence&panel=toolchain&build=build-b`) · research section.
- **Peek source:** the stored comparison receipt, classifier record and stack comparison.
- **Absent copy:** "not run" · "No comparison receipt" · "none found" · "unknown: no row is explained only by source" · "(inferred)" on relocation sizes.
- **Target-size exception:** address links sit one per 24px grid row (the inline exception); row focus and the 44px row-menu button apply.

## Keyboard

- F7 / Shift+F7 next and previous difference, in both the class table's filtered rows and the full rows. The class table and the rows are APG Grids with row focus.
- Enter on a class filters; Enter on an address goes; Alt+↓ peeks the classifier record; Shift+F10 opens the link menu (Reveal in: ObjectDiff, FrameLayout, CompilerLayer).
- `g then i` (registered `code.explain`) moves focus to MatchExplain from a code well.

## Accessibility

- Status items are separate named elements, never one "verified" badge. The effective-match state reads its full words ("Effective match: no, 3 rows are not register-only").
- Row names follow the ObjectDiff template plus the class word: "0041b2c3, target mov esi, candidate mov edi, differs, register allocation, pair A".
- Register pairs are framed and lettered; the first pair is solid and the second dashed, so colour is never needed.
- Accessible View lists the classes, then every row with its class word.

**Research:** [MSVC transformations I6, §8.3, §9.4](../../../../research/2026-09-29-msvc-optimization-for-decomp.md#83-why-matching-is-not-the-same-as-functionally-equivalent); [reference UI patterns C1–C4, C9, C11](../../../../research/2026-09-29-reference-re-ui-patterns.md).

**Prior art:** reccmp `reccmp/compare/report.py` (effective match as its own status), `reccmp/compare/asm/fixes.py` (register swaps and reorderings), `reccmp/compare/asm/parse.py` (consistent placeholders), `reccmp/tools/stackcmp.py` · objdiff `objdiff-core/src/diff/code.rs` (diff kinds; stable per-argument pairing), `objdiff-core/src/diff/display.rs` · decomp.me `frontend/src/components/Diff/Diff.tsx`, `backend/coreapp/flags.py` (recipe as typed flags) · ghidra `Ghidra/Features/VersionTracking/src/main/help/help/topics/VersionTrackingPlugin/providers/VT_Matches_Table.html` (opinions never compared across correlators).
