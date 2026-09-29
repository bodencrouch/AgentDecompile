# State vocabularies

Every closed set below is drawn on its own axis, with its own glyph and word. Two axes are never folded into one badge. Glyphs are DejaVu Sans Mono characters; color touches only the glyph.

## Independent facts (FactBadge, FactStrip)

Facts: Compilation · ABI checks · Tested behavior · Local match · Linked match · Replacement contribution · Whole-file equality.

| State | Glyph | Token | Meaning |
|---|---|---|---|
| passed | ✓ | `fact-passed` | Observed positive under a valid check, with a receipt |
| failed | ✕ | `fact-failed` | Observed negative under a valid check (not a crash) |
| stale | ◷ | `fact-stale` | Relevant dependencies changed |
| unknown | ? | `fact-unknown` | An attempt or legacy record cannot establish it |
| unsupported | ⊘ | `fact-unknown` | The provider cannot perform the check |
| not_run | ○ | `fact-unknown` | No observation attempted |

Legacy `real_c=1` is a compile indicator only. Old receipts stay legacy or unknown and are never silently upgraded. The old none/asm/C and none/obj/linked posture bars are display shorthand at most and cannot authorize anything.

## Claim tiers (ClaimTier)

| Tier | Frame | Token | Meaning |
|---|---|---|---|
| Verified | solid | `claim-verified` | Survived the caller-selected hard proof |
| Advisory | dashed | `claim-advisory` | Lifted or inferred; never proof |
| Context hint | dotted | `claim-hint` | Names, notes, debug-info witnesses |
| Byte authoritative | double | `claim-bytes` | Copied target bytes; never recovered source |

## Representation (RepresentationBar)

Exhaustive and mutually exclusive: every inventory member appears exactly once. Totals are disjoint; capabilities overlap. Facts are never summed into representation.

`rep-accepted` accepted source · `rep-candidate` candidate source · `rep-preserved` preserved region · `rep-unclassified` unclassified (dashed edge) · `rep-excluded` excluded with reason (hatched).

## Binding predicates and runtime capability (RuntimeCapabilities)

`accepted_binding = presence AND identity AND current dependencies`; `runtime_ready(op) = accepted_binding AND operation(op, live state)`. These are predicates, not a confidence score or a ladder. Draw them as three separate rows: **BYTES** (are these bytes here?), **IDENTITY** (is this the intended entity?), **OPERATION** (is this use supported?).

Runtime capabilities are independent and may overlap: **located · readable · callable · detourable · writable** (chips L R C D W). Readable does not imply writable; callable does not imply detourable. Named refusals: `unsupported_dynamic_code`, `not_detourable`, `unrelocatable`, `decoder_mismatch`, `missing_adapter`.

Readiness chain (kept as separate states): discovered → identity-supported → resolved → installable/installed → call-observed → behavior-observed.

## Locator per entity × build (LocatorGlyph, ReadinessMatrix)

Display order: contested, unresolved, ambiguous, pinned, degraded, resolved.

| Status | Glyph | Token |
|---|---|---|
| resolved(member) | ● | `ink-strong` |
| pinned(member) | ◎ | `address`, labelled `module_rva` or `section_offset` (non-portable) |
| degraded(member, reason) | ◑ | `fact-stale` |
| ambiguous | ⋯ | `fact-stale` |
| unresolved | ◌ | `fact-unknown` |
| contested | ⇉ | `fact-failed`: two locator arrows to different addresses in one build lane, both evidenced, no winner |

`observed_status` is a separate axis and never overwrites pack status. The word "contested" is reserved for this set; merges say "conflicting".

Call trees reuse these words for per-build reachability (resolved, absent, unresolved, ambiguous, contested) plus "not loaded". There is no present/absent pair.

**Presence words (SymbolTree, ResultsTable).** A per-build presence cell uses the locator glyph and word above, or one of these words. They are words, not new glyphs, and each is a separate reading, never a locator status:

- **absent**: the plain word; never an empty cell.
- **folded**: identical-code folding, where one address carries several symbols ("folded with Actor::Release at 0041d2a0"). Every symbol at that address is listed; none is chosen as the name. It is the `ICF` compiler annotation seen from the symbol side.
- **inlined only**: the OutcomeTag `inlined_only`, where the function has no out-of-line body on that build ("inlined only on build-b"). It is not absent and not unresolved.
- **namespace differs**: the namespace path differs between builds; each build's path is shown, never merged.

## Defined state and result joins (ResultsTable, SearchWorkbench)

**Defined state** of a string or data hit, from the build's own listing: **defined** · **not defined** · **partially defined** · **conflicts** (with an instruction or other defined data; the row names which). The words are evidence, not a quality, and are never shortened to a check mark. Filter values (`f=results.defined:`): `defined`, `not-defined`, `partial`, `conflicts`.

**Join rules.** A result table spanning builds joins rows into one logical row only by its kind's stated rule, and the header states it in these words:

| Rule | Words | Kinds |
|---|---|---|
| identity | joined by accepted identity edge (candidates show their edge word and are not joined) | symbols, functions, tags, comments on entities |
| content or name | joined by content ≠ same entity | strings, equates by name, types by name |
| none | never joined · grouped per build | memory, instruction, scalar, direct-reference and address-table hits |

- A hit inside an anchored function says "in ‹entity› on build-a, build-c · via anchor". Nothing is aligned by offset or order.
- **Per-build hit cells** read a LocatorGlyph word with its address, or: **absent** (searched, no hit) · **not searched** (not loaded or excluded; never 0) · **not indexed** (no index for this kind) · **no anchor** (the join needs an anchor and none is recorded).

## Identity edges (IdentityEdge)

candidate (dashed `lane-identity-ink`) · accepted (solid) · rejected (struck, `fact-failed`) · unresolved (dotted, `fact-unknown`). An edge animates from candidate to accepted only after its acceptance event exists.

## Divergence and correspondence

Divergence classes: **1↔1** structural match · **1↔N** split-or-inlined candidate · **≠** diverged, no confident counterpart. Copy: "diverged — counterpart structurally different, possibly inlined/split". Relation kinds: one_to_one, clone, inline, thunk, split, fold, region, unroll. Split, inlined and diverged go to review, never silent auto. Struct field correspondence: same · shifted · resized · retyped · added · removed · reordered.

## Waiting at a gate

◇ (the gate diamond) plus "waiting at gate: ‹gate text›" in `gate` amber marks work waiting at a stage gate. It is distinct from ◷ stale (changed dependencies) and never shares its glyph. "Held" is reserved for held panes.

## Work-view events (WorkTimeline)

| Event | Mark | Word |
|---|---|---|
| accepted | tall tick plus ✓ | accepted |
| rejected | short tick plus ✕ | rejected |
| observed | plain tick | observed |

The cursor is a 2px `ink-strong` frame, never the accent. A text list of the events is the accessible form. ◇ and ◆ are reserved for gates and never mark an event.

## Alignment markers (SplitCompare, diffs)

Row markers in aligned views, always with a word for assistive tech: ↔ anchor (matched anchor), ± differs, − only on the left, + only on the right, and a hatched filler for "no line". Aligned is not equivalent: every split header shows the divergence class (1↔1, 1↔N, ≠) and the identity-edge state, and equal rows say "local; ≠ whole-image proof". Alignment markers compare two sides row by row; the Cross-build comparison words below compare one logical value across N builds. The two sets share ± and −, with the same meaning, and never share a cell.

## Evidence level (ToolchainEvidence, PointerWalk, CompilerLayer, TransformTimeline, FrameLayout, VTableBrowser, VariantRelation)

Every inferred or observed value about the compiler, a layout or a cross-build difference carries one evidence level. The level word is always visible text; the frame is only the second cue.

| Level | Frame | Token | Meaning |
|---|---|---|---|
| witness | solid 1px | `evidence-solid-frame` | Bytes in this image prove it (Rich header entries, a FuncInfo record, a jump-table parse, an unambiguous byte pattern). The basis names the witness and links its address, always with its build. |
| record | solid 1px | `evidence-solid-frame` | A recorded toolchain, PDB, type or command-line record says so. The basis names the record. |
| hypothesis (heuristic) | dashed 1px (`dash-hypothesis`) | `evidence-hypothesis-frame` | Inferred from code-generation idioms, access patterns or similarity. The basis is always named with its sample and says what was not checked. |
| unknown | none; the italic word | none | No evidence. Nothing guessed is drawn in. |

- A hypothesis never becomes a witness by repetition, by agreeing with its neighbours, or by being high-scoring. Only a witness or a record makes a value solid.
- A solid absence is written as what was checked ("the Rich header lists no LTCG entries"), never as a bare "no". An unchecked absence is unknown ("no Rich header in the image; absence is not proof").
- Frames stay 1px `line-control` (3.2:1); 2px under Increase contrast; `CanvasText` in forced colors, where solid, dashed and none survive as border styles.
- These levels are not claim tiers. A witnessed toolchain fact is not a verified recovery claim, and a claim tier is never drawn as an evidence level.

## Variance class (VariantRelation; difference class in PointerWalk, CompilerLayer, TransformTimeline, FrameLayout, VTableBrowser)

Builds are variants of one application: compiled differently, or built from older or newer source. Each difference between two builds of one logical entity, field, slot or transformation gets one class, each a glyph and a word.

| Class | Glyph | Word in views | Meaning |
|---|---|---|---|
| compile variance | ≈ | same source, compiled differently | Same source; different toolchain, flags or link settings (register choice, frame shape, inlining, cookie or EH scaffolding, ICF, ILT or padding). The cause is named. |
| entropy variance | ∼ | same source and flags, build state differs | Same source and declared toolchain and flags; incidental build state differs (paths, declaration or object order, link order, timestamps). |
| source variance | ≠ | source changed | Control flow, call set, constants or the field set changed. What changed is named ("field added"). |
| unknown | ? | unknown | Cannot tell: source identity is missing on one side, or source and flags both differ, or the evidence conflicts. |
| identical | ≡ | identical | Byte-identical after relocation normalisation. **Not a variance class and not a match claim.** |

- **A class is solid only** when source, toolchain and flag identity are recorded for **both** builds (source checksums or digest, command lines, the toolchain record). Otherwise it is a dashed "hypothesis (heuristic)" with its basis ("no checked transformation explains it: inlining, /Oy, LTCG, ICF, hotpatch"), however strongly the bytes suggest it. Facts beside it keep their own level and do not make the class solid.
- Where bodies were never compared, the word is **unknown** and nothing is counted.
- Counts per class are per pair of builds. They are never summed across pairs, averaged, or turned into a similarity score.
- A build-wide cause (a flag, LTCG, /GS, /Oy, EH model, ICF) links to ToolchainEvidence for that build instead of restating its evidence.
- Filter values (`f=variance:` and, for a pair drill, `f=vrel:`): `compile`, `entropy`, `source`, `unknown`. ≡ is not a filter value.
- ≠ is also the divergence-class glyph ("≠ diverged") and the claim-boundary sign in copy. The word always travels with it, and a variance class and a divergence class never share a cell.

## Cross-build comparison (PointerWalk, CompilerLayer, TransformTimeline, VTableBrowser)

How one logical value (a field offset, a slot, a transformation) compares across the builds shown. Always written as words, with the glyph as a repeat.

| Glyph | Words | Meaning |
|---|---|---|
| ≡ | same in all builds | The same value on every build shown (with two builds, "same in both builds"). |
| ± | differs: consistent pattern | Differs, with one stated pattern ("+4 in build-c", "build-c slots from 1 onward are +1"). |
| ± | differs | Differs with no single pattern; each build's value is shown. |
| − | absent in build-x | Not present on that build; the build is always named. Plain word, never a link to a guess. |

- The grouping key (the recorded source revision) is shown on the view's provenance line.
- ≈ now means compile variance only. It is not used for "consistent pattern"; that is `±` plus the words "differs: consistent pattern".
- Relation to Alignment markers: ± means differs and − means absent on one side in both sets. ↔ (anchor) and + (only on the right) belong to two-sided aligned rows only; ≡ belongs to N-build comparison only.

## Artifact status (OutputsCatalog, ArtifactCard)

One closed set per artifact × build, each a glyph and a word, never a score.

| Status | Glyph | Token | Meaning |
|---|---|---|---|
| delivered | ▣ | `artifact-delivered` | A receipt records bounded evidence for this scope (a bounded source or installed run, or a historical observed run). **Delivered means only that a bounded receipt exists**: not live, not current, not accepted. |
| partial | ◐ | `fact-stale` | Some source or synthetic evidence exists; the ledger names what is missing. |
| stale | ◷ | `fact-stale` | Delivered, but its basis changed since the receipt. |
| future | ▷ | `fact-unknown` | Design, plan or contract only; no producer yet. |
| never run | ○ | `fact-unknown` | A producer exists; nothing has run for this build. |
| no report | ∅ | `fact-unknown` | A run is recorded, but its report is missing. Never "no changes". |
| reference | □ | `fact-unknown` | An implementation-CLI artifact; a reference, not an operating instruction. |

- **Observed on 8080** is a separate axis: ⊡ "not observed on 8080", or "observed ‹time›" with its ProvenanceStamp. It never changes the status, and the status never implies it. Today every artifact is not observed.
- A never-produced artifact shows "tier when produced: ‹tier›" as muted text, never a ClaimTier chip.
- A run whose serving provider differed from the requested one says "⇄ ‹build›: provider differed" beside the status.
- Glyphs shared with other sets (◐, ◷, ○, ∅, ⊡) keep their word; the artifact word always appears.

## Compiler annotation tags (CompilerLayer, TransformTimeline)

A gutter tag in bold mono is the word; brackets (`┌ │ └`, `▪`) are `aria-hidden`. Every annotation also carries its evidence level and, where builds differ, its presence per build and its variance class.

| Tag | Word | Filter value (`f=xform:`) | Research |
|---|---|---|---|
| INL | inlined ‹callee› | `inline` | T3 |
| ICF | folded with N functions (every entity listed; never one chosen name) | `icf` | T6 |
| GS | /GS cookie scaffolding | `gs` | T8 |
| EH | C++ EH registration; "state N: ‹object› is live", naming the handler generation from the build's evidence (__CxxFrameHandler on 7.x, FH3 on 8.0–14.x x86, FH4 on x64) | `eh` | T9 |
| SEH | SEH scope, try level, filter and handler | `seh` | T10 |
| DIV | magic-number divide ("÷ 10", signedness) | `div` | I2 |
| TAIL | tail call | `tail` | I4 |
| SW | switch table (case set and dispatch) | `switch` | I1 |
| FPO | ESP frame, frame-pointer omission | `fpo` | T2 |
| ILT | incremental-link thunk | `ilt` | T12 |
| HP | hotpatch prologue and padding | `hotpatch` | T13 |
| STR | string-pooled constant ("one copy for N uses") | `strpool` | T7 |
| LOOP | loop rotation, unrolling, strength reduction | `loop` | I5 |
| INTR | intrinsic expansion ("rep movsd = memcpy, 64 bytes") | `intrinsic` | T4 |
| CC | calling convention ("__thiscall · this in ecx"; "LTCG custom convention") | `cc` | §4, T5 |

`RTC`, `PROBE` and `BOOL` join the set only when their detectors exist (T11, I8, I3). Scaffolding (GS, EH, SEH, RTC, HP) stays visible, labelled scaffolding, and its diff status is never hidden. Research ids refer to `docs/research/2026-09-29-msvc-optimization-for-decomp.md`.

## Match explanation classes (MatchExplain)

Every residual difference between a recompiled candidate and its target bytes is one of nine classes, each with a count, its evidence level and a next step in words. Zero-count classes stay listed in `ink-muted`; uncounted classes show "—" with a hypothesis or the word unknown.

| Class | Filter value (`f=diffclass:`) | Note |
|---|---|---|
| register allocation only | `regalloc` | The effective-match class; not byte-identical |
| instruction scheduling or reordering | `schedule` | |
| stack slot or local ordering | `stack` | Opens FrameLayout |
| relocation or address only | `reloc` | Not a code difference; inferred sizes say "(inferred)" |
| constant or immediate differs | `constant` | |
| different branch structure | `branch` | |
| missing or extra inlining | `inline` | |
| toolchain or flags mismatch | `toolchain` | Compare the recipe in ToolchainEvidence before editing source |
| source difference | `source` | Resolve the classes above first |

- **Effective ≠ byte match.** "Effective match" is its own state: yes (register allocation only) · yes (order only) · no, with the count of rows that block it · not applicable (exact). It sits between exact and partial and is never counted as byte-identical, as Local match, or as any of the seven facts.
- An optional fuzzy percentage is labelled "truncated, never rounded up · not a claim", and never reads 100% unless the rows are byte-identical.
- Identity opinions (each matcher with its own score) are shown side by side and never compared, averaged or merged.

## Named non-success outcomes (OutcomeTag)

absent · inlined_only · ambiguous · unsupported · insufficient_evidence · budget_exhausted · contested · unresolved · no_placement · unsupported_dynamic_code · missing_adapter. Each is a terminal reason, not a forced match and not a claim of exhaustive failure. Unresolved data roots "refuse, never zero".

## Activity dimensions (ActivityRecord)

**Liveness** (heartbeat, last event time) · **execution progress** (durable completed units) · **goal progress** (accepted outcomes). Three separate readouts. `progress_unknown` is legitimate for uninstrumented external jobs. PID churn increments nothing.

## Task lifecycle (TaskLifecycle)

proposed → waiting → ready → admitted → running → awaiting_acceptance → accepted. Terminals: ✕ negative, ⊘ unsupported, ⊗ cancelled. Side states: ↻ retry_wait, ∅ budget_exhausted. Resource occupancy is not a negative result. Terminal task counts never define objective completion.

Acceptance outcomes: accepted · rejected · stale · insufficient evidence · unsupported · contested ("arrival order is not a tie-breaker").

## Job outcome (OutcomeCell, ActivityRecord)

The words a submitted job shows on the row that invoked it and in the dock. One word per state; a job's words never replace the task's acceptance outcome or the seven facts.

| Word | Glyph | TaskLifecycle | Meaning |
|---|---|---|---|
| pending | — | before admitted | HTTP 202 arrived and the job record exists. Nothing is shown optimistically. |
| admitted | — | admitted | Admitted under ownership; not yet running. |
| waiting | — | waiting | Names the blocking owner and resource. Resource occupancy is not a negative result. |
| running | — | running | Measured durable units, or "Progress unknown · last event ‹time›". |
| checking | — | none (ambiguous command outcome) | "Checking whether the operation completed". Mutation of that operation on that target is disabled until reconciled. |
| finished | — | awaiting_acceptance, or a terminal the record names | The job ended. The facts its receipts wrote are listed separately. A finished job is not a match. |
| failed | ✕ | none (the job's own failure; see FailureRecord) | The job itself failed ("worker exited 1"). It is not a failed fact and not ✕ negative. |
| cancelled | ⊗ | cancelled | Names who cancelled and what was kept. Never claims a rollback. |

Terminal words are finished, failed and cancelled. Batch copy uses the same words: "4 runs: 1 running · 2 finished · 1 failed". The job's submitter is a separate word: by you, by agent or external.

## Failure lifecycle (FailureRecord)

observed → classified → contained → recovery_pending → reconciling → eligible. Branches: waiting_external, budget_exhausted, unsupported. `detector_unknown` is never inferred as healthy or failed. Classifications: mismatch · transient · resource · policy.

## Resources (ResourceState)

Two separate machines. Access: ○ free · ● owned · ⊠ quarantined. Publication: current · revoked (struck). Owner: managed · external. Kinds: program, corpus-writer, output, PDB, Wine, save, display, port, channel, storage. A byte match, elapsed timeout, changed PID or new lock file never clears quarantine. A lease countdown is never shown as a release time.

Prepared bundle: preparing → verified → launchable. Incomplete closure is never launchable.

## Surface lifecycle (StateNotice)

| State | Glyph | Variant |
|---|---|---|
| loading | … | info |
| not loaded | ○ | info ("Not loaded. Open to read it."; never auto-fetched from hover or peek) |
| empty | ∅ | info |
| disconnected | ⌁ | fault |
| unavailable | ⊡ | unknown |
| stale | ◷ | caution |
| unsupported | ⊘ | unknown |
| partial | ◐ | caution |
| conflict | ⇄ | fault |
| reconnecting | ↻ | info |
| approval-required | ⚑ | caution |
| failed | ✕ | fault |
| recovered | ↺ | info |

Transient read errors (408, 429, 5xx, timeout) are info, not alarms, and keep the last content.

## Delivery and claim status (MilestoneCard, ClaimBanner)

Diagram and doc status labels: **IMPLEMENTED FOUNDATION · PARTIALLY VERIFIED**, **FUTURE DELIVERY**, **FUTURE QUALIFICATION**, **FUTURE FEASIBILITY → DELIVERY**, **DESIGN ONLY**, **NOT RUN**, **FUTURE / NOT RUN**. Claim-status lines use `status-claim`. Evidence provenance: reused vs fresh, historical vs current, legacy, MEASURED vs ESTIMATE (ProvenanceStamp).

## Merge and import

Merge result per binary, name, type, comment and relationship: **added · reused · skipped · conflicting**. Import: validated → durably accepted → dialog closes; duplicates alias an existing SHA-256 identity. Context pieces: placed · unplaced · conflict · skipped; proposed labels: ready · conflict (never auto-picked).

## Project kinds

`kind-gpr` local .gpr · `kind-shared-fs` shared folder · `kind-shared-http` Ghidra Server · `kind-bin` raw binary · `kind-draft` draft.

## Version control, history and read-back (VersionControlPanel, EditHistory, PatchEditor, OptionsPanel)

- **Version control:** ● latest · ↓ update available · ● checked out (an exclusive checkout is the writer lock) · ⇄ hijacked (conflict). "Stay checked out" and "Save a private copy" are the action words; "Keep" and "Kept" stay reserved for cards.
- **Edit history:** ↶ undoable · ↷ redo available · ⊘ cannot be undone here. An executed job's side effects are always ⊘, even when the byte journal can roll bytes back.
- **Read-back:** ✓ "read back · matches preview" after a write is re-read; ✗ "read back · differs from preview" when it is not. "Restored to defaults" is a word, never ↺, which means recovered.
- **Option state:** "not default" as a word beside a changed option. ≠ is never used for this, because it means source variance.

## Validator results (ProgramValidation)

Each build shows one of these per validator, always as the word, with the glyph beside it:

| Result | Glyph | Meaning |
|---|---|---|
| no findings | ✓ | The validator ran on this build's current receipt and reported nothing. |
| warnings | △ | Advisory findings. They are never unmet predicates, and reach a worklist only when collected. |
| errors | ✗ | Findings the validator marks as errors. They are still not recovery claims. |
| not run | ○ | No validation receipt exists for this build. |
| stale | ◷ | The receipt predates the build's current basis. |
| not applicable | — | The validator does not apply to this build's language or format. |

△ is used for validator warnings only.

## Name sub-tiers from analysis (NameProvenance)

- **analysis · Function ID**: a name from a Function ID hash match. It ranks below debug info and authentic symbols and above placeholders, and is always a candidate.
- **analysis · imported SARIF**: names from a SARIF file whose hash matches the build. They rank below debug info.
- A PDB whose identity (GUID and age) does not match the build is a hypothesis, and its names rank with analysis names, not debug info.
