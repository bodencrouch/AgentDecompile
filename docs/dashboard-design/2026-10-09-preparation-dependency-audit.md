# Preparation dependency audit — October 9

Read-only audit by /root/views_action_audit. No recovery jobs were started,
resumed, cancelled or rewritten. Evidence is source/history and retained state,
not new compilation, matching or publication proof.

## Historical facts-reuse failure

Run 9c2b894874f863c4896585e388bc1109 retains analysis partial17/31, facts
blocked15/17, BSim blocked16/31 and matching blocked0/0. Its currentStage label
is analysis, but that label does not identify the exception's origin. Comparison
inputs/targets were not established.

In historical commit bf6d8c2d, preparation.py:1465–1471 stored item[:5] from
seven-column inventory rows. The facts-reuse loop then read existing[5] and
existing[6] at1484–1489, necessarily raising IndexError on that path. This is a
high-confidence source-and-state diagnosis; the coordinator kept only the
error string, not a stack trace. Current preparation.py:2209–2215 retains full
rows. Confirm live source/basis before resuming; do not rerun usable analysis,
facts or the16 signature checkpoints just because the old coordinator failed.

## Optional indexing delays independent matching

Current preparation.py:2298–2362 performs serial optional BSim indexing before
ordinary matching at2363–2510. match_store.py:367–418 explicitly separates
signature indexing from pair-query hits: absent optional hits do not block
ordinary matching. The pair action uses persisted SQLite facts, not a fresh
Ghidra analysis call (preparation.py:2488–2496).

Smallest repair: run eligible deterministic matching before optional indexing,
reorder the stage presentation consistently, preserve _BSIM_LOCK and native
writer admission. Signature checkpoints at2322–2334 are reusable when their
fingerprint/database identity still agrees. Do not infer fused pair evidence
from an indexing receipt.

Pair reuse basis at2935–2993 covers frozen inventory; its digest at2878–2921
does not cover subsequently acquired BSim hits. Later explicit pair-hit changes
must re-evaluate the affected pair and descendants, not invalidate unrelated
work or promote an earlier deterministic match to fused evidence.

Remaining: source dependency edit, independent review, live activation receipt,
ownership-safe resume and observed matching progress. Preserve failed members
as actionable partial states and permit independently eligible peers. Capture
coordinator tracebacks on future errors so the next failure can be localized
without another historical archaeology pass.
