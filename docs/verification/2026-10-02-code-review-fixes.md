# Local code-review fixes, 2026-10-02

Scope: the ten confirmed findings from review `20261002-175256-f380b37d`,
implemented against `a8b6d2faf8a71b633fd5dedfd07cc493ee250536` on
`codex/review-identity-workbench-fixes`. This record describes local source
changes and source inspection, not installed or live acceptance.

## Changes

| Original finding | Local correction |
| --- | --- |
| 1 | Remove histogram and mnemonic-block hashes from identity anchors and relocation code-equality claims; preserve genuine `B_raw:` anchors. |
| 2 | Retain quarantine through structural, P-code, BSim, fuzzy and inline residue stages. |
| 3 | Invalidate descendants of newly discovered identity conflicts to a fixed point before inserting identities. |
| 4 | Retain target admission and the worker slot until the exact unresolved subprocess handle reports exit. Expose unresolved ownership and worker PID. |
| 6 | Commit additive corpus schema upgrades and backfill before returning a connection; close on failure. |
| 7 | Clear the active project on Home/hide without clearing it during unscoped member navigation. |
| 8 | Ignore older session-save responses after a newer optimistic session save. |
| 9 | Include `currentStage` in public preparation state. |
| 10 | Maintain destination membership instead of rebuilding its set for each anchor proposal. |
| 11 | Encode exchange snapshots off the event loop and cache unchanged record encodings. Preserve snapshot generations and durable writes. |

Original finding 5 was rejected as pre-existing and is outside this batch.

## Independent review and follow-up

Fresh `ce-code-review`, mode `agent`, explicit base above, completed as run
`20261002-184128-ed885b68`. Ten local review lenses returned; an independent
validator confirmed three follow-up defects and two coverage gaps. External
cross-model review was disabled by repository configuration.

The follow-up corrections keep deadline/cancellation escalation active when a
live child closes stdout, retain the project guard through unscoped navigation,
and restore the exchange's prior outside-state-lock disk-write boundaries for
claim, enrollment, roster and heartbeat. Offer, submission and forwarding
acknowledgements retain their existing lock-through-durability behavior.
Cancellation drains an active serialization worker before releasing mutable
state. Full-snapshot assembly and disk writes still scale with stored data;
this is not a constant-time persistence design or a measured throughput claim.

Regression source covers weak versus actual-byte hash evidence, early stdout
closure, unresolved-owner admission, slow claim persistence alongside another
worker's heartbeat, and repeated cancellation during serialization.

Review artifacts are local scratch receipts under
`/tmp/compound-engineering-1000/ce-code-review/20261002-184128-ed885b68/`;
`review.json`, `validator-verdicts.json` and `full.diff` preserve the pre-follow-up
review snapshot. Those artifacts are not deployed assets.

A bounded independent follow-up source review found no actionable defects in
the corrected lifecycle, lock boundaries, navigation guard and regression
fixtures. Its receipt is `followup-review.md` in the same run directory.
The final hide check uses the current active project, including during
unscoped browsing, and preserves a different project opened during the save.

## Verification boundary

- Python source was parsed with `ast.parse`, without importing project modules.
- `git diff --check` passed. Changed control flow and existing callers were
  inspected; test source was reviewed.
- No tests, suites, builds or frontend type-check were run under the current
  mission constraints in `AGENTS.md` and `src/CLAUDE.md`. Added regressions are
  unexecuted; this record makes no passing-test claim.
- No service restart, alternate server, recovery duplication, push or pull
  request occurred.

Before Python edits, the healthy 8080 process was corroborated as PID 2697197,
started 2026-09-28, cwd `/home/brunner56/agentdecompile-nvme`. Read-only catalog
job `564ff3819ece` reported loaded module paths under
`/run/media/brunner56/MyBook/Workspaces/ai-projects/AgentDecompile/src`, whose
checkout was at `753d7fcea7580335e33533bf9aad693f6c5fe9b0`. The reloader watched
the NVMe source root with zero watched files. This local review worktree is a
different source tree. These edits were not copied into either live root or
claimed as activated. Existing process owners and jobs were preserved.

Runtime acceptance remains open: tests, database reopen/snapshot round trips,
browser navigation/save ordering, and live ownership behavior were not exercised.
Identity source checks do not establish byte-identical recovery. Existing
source-archive log-marker parsing remains a review-noted simplification concern;
its marker-spoofing behavior predates this change and was not expanded here.
