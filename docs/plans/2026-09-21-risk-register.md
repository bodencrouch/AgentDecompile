---
title: Risk register — time, energy, single points of failure, performance, data loss, ambiguity
date: 2026-09-21
applies-to: 2026-09-21-portable-signatures-codecaves-generic-plan.md; the design docs; the loop
status: living; every loop iteration runs a risk grill and updates this file
---

# Risk register

The standing rule for the loop: each iteration grills for anything that costs time or energy,
any single point of failure (a slow I/O device counts), any performance drag, any path to
data loss, and any ambiguity in the plan or design — and either fixes it as a unit, schedules
it, or records why it is accepted. Rows are removed only when the mitigation is verified.

## Open

| # | Risk | Class | Evidence | Mitigation | Owner / when |
|---|---|---|---|---|---|
| R1 | Canonical repo and its object store live on a rotational USB drive at 93 % full; every git op, test and agent read goes through it (worktree creation > 5 min; routine commands hit the 120 s timeout). | bottleneck / SPOF | session timings 2026-09-21 | Full clone on the fast disk as the working canon; the USB copy becomes a synced remote; the existing off-machine remote is the backup. Do it between worker waves so no worktree is orphaned. | orchestrator, after the current three units land |
| R2 | Fast disk at 97 % (19 GB free): a full disk kills builds, tests and worktrees mid-write. | SPOF | `df` 2026-09-21 | Measure the large consumers; move caches/venvs/fixtures off or prune; alert threshold in the loop's risk grill. | loop, next iteration |
| R3 | `preparation.py` calls `upsert_binary` with no digest; `ON CONFLICT … SET content_sha256 = excluded.content_sha256` **overwrites a backfilled hash with NULL** on the next prepare. The audited plan makes that hash the tie-break key and a cascade precondition. | data loss | U22 worker report; `extract.py` upsert | Unit: `upsert_binary` never clears a non-NULL `content_sha256` with NULL (COALESCE); the backfill is the only writer of a computed digest; test both. | next dispatch wave |
| R4 | The loop is bound to one session and one orchestrator context; if the session ends the loop stops. | SPOF | `/loop` semantics | All state is durable (branch, plan with ✔ marks, audit files, this register); each iteration writes a resume line under "Resume point" below; restart is `/loop` with the same prompt. | continuous |
| R5 | Full test suite exceeds ten minutes; one test reads a real image from the USB drive and times out; 7–18 pre-existing failures hide regressions; workers therefore run slices. | time / masking | worker reports | Triage unit: mark/skip the environment-bound test, fix or quarantine the pre-existing failures with receipts, keep fixtures on the fast disk, define the `unit` slice every worker must run. | dispatch after R1 |
| R6 | CI name gate fails closed without the repository secret `AGENT_DECOMPILE_NAME_DENYLIST`. | blocked CI | U21c design | The user adds the secret (contents of the out-of-repo denylist). | user |
| R7 | The plan has no units for the 5174/8080 surfaces ("draw the work", one control, corpus-first); "done" would exclude the UI. | ambiguity / scope | design docs vs Recommended order | Grill 6 (design vs plan) adds a surfaces phase with units and acceptance; the loop's "done" includes it. | grill 6, this iteration |
| R8 | Shared `refs/stash` across worktrees: a `git stash pop` in one worktree popped another branch's stash (happened once). | data loss | worker incident 2026-09-21 | Worker packets forbid stash; baselines via `git show <base>:<path>`. Keep the rule in every packet. | continuous |
| R9 | `raw_image_path` falls back to a cwd-relative path when the env var is unset, so pack bytes depend on the operator's working directory. | ambiguity / determinism | U1–U3 worker report; `ghidra_bulk.py` | Unit: refuse when the env var is unset and no absolute root is configured; record the root in the basis. | Phase 2 wave |
| R10 | Each grill round costs ~120–290 k tokens; the loop is deliberately expensive. | energy | session usage | Accepted for now; one grill per iteration, targeted by "oldest audit or most code change". | accepted |
| R11 | Slow-disk contention when many agents read the tree at once (five grills made simple commands take minutes). | bottleneck | session timings | R1 removes most of it; until then cap concurrent agents at four. | orchestrator |

## Resume point

- Branch `feat/portable-signatures-codecaves-generic`; last docs commit records audit 2 and the
  ten resolved decisions. Landed: Step 0, Phase 0 D1–D7, U5c, U7/U7b, U22, U1–U3/U1b. In
  flight: U21c (gate), D8/D9 + harness (o), 3b basis hardening; grill 6 (design vs plan).
  Next: R3 unit, R1 disk move, U21a/U21b, U19a, U82/U69/U20/U70.
