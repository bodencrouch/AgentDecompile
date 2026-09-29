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

## Identity edges (IdentityEdge)

candidate (dashed `lane-identity-ink`) · accepted (solid) · rejected (struck, `fact-failed`) · unresolved (dotted, `fact-unknown`). An edge animates from candidate to accepted only after its acceptance event exists.

## Divergence and correspondence

Divergence classes: **1↔1** structural match · **1↔N** split-or-inlined candidate · **≠** diverged, no confident counterpart. Copy: "diverged — counterpart structurally different, possibly inlined/split". Relation kinds: one_to_one, clone, inline, thunk, split, fold, region, unroll. Split, inlined and diverged go to review, never silent auto. Struct field correspondence: same · shifted · resized · retyped · added · removed · reordered.

## Waiting at a gate

◇ (the gate diamond) plus "waiting at gate: ‹gate text›" in `gate` amber marks work held at a stage gate. It is distinct from ◷ stale (changed dependencies) and never shares its glyph.

## Named non-success outcomes (OutcomeTag)

absent · inlined_only · ambiguous · unsupported · insufficient_evidence · budget_exhausted · contested · unresolved · no_placement · unsupported_dynamic_code · missing_adapter. Each is a terminal reason, not a forced match and not a claim of exhaustive failure. Unresolved data roots "refuse, never zero".

## Activity dimensions (ActivityRecord)

**Liveness** (heartbeat, last event time) · **execution progress** (durable completed units) · **goal progress** (accepted outcomes). Three separate readouts. `progress_unknown` is legitimate for uninstrumented external jobs. PID churn increments nothing.

## Task lifecycle (TaskLifecycle)

proposed → waiting → ready → admitted → running → awaiting_acceptance → accepted. Terminals: ✕ negative, ⊘ unsupported, ⊗ cancelled. Side states: ↻ retry_wait, ∅ budget_exhausted. Resource occupancy is not a negative result. Terminal task counts never define objective completion.

Acceptance outcomes: accepted · rejected · stale · insufficient evidence · unsupported · contested ("arrival order is not a tie-breaker").

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
