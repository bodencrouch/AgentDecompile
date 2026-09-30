# Activating the reconciled source on 8080

The 8080 server runs `/home/brunner56/agentdecompile-nvme/src`, an unversioned copy. Branch
`feat/u13-reconcile` holds that copy's newer edits merged into git, plus the 2026-09-30
U2/U9 work. Nothing on the branch is live until these owner steps run. Each step names its
check. None of them is automatic: `AGENTS.md` forbids routine restarts, alternate ports and
systemctl, so the owner decides when to take the server down.

## 1. Land the branch

Merge `feat/u13-reconcile` into the delivery branch once that checkout has no one else's
uncommitted work. On 2026-09-30 `feat/cockpit` had another writer's uncommitted cockpit
rework, so it was not merged there.

Check: `git log --oneline feat/cockpit..feat/u13-reconcile` lists the reconciliation, U2 and U9
commits, and the merge has no conflicts outside the cockpit files.

## 2. Serve from a git checkout, not a copy

Point the server at a git worktree so the next divergence cannot be silent. For example:

```bash
git -C /run/media/brunner56/MyBook/Workspaces/ai-projects/AgentDecompile worktree add /home/brunner56/agentdecompile-serve <delivery-branch>
```

Then start the owner's usual command with `--root /home/brunner56/agentdecompile-serve/src`,
keeping the NVMe `.venv` and project path. The old copy stays on disk untouched, as a rollback.

Check: `curl -s localhost:8080/health` reports the new pid and root, and `/api/v1/actions` still
lists the catalog.

## 3. Backfill the live store through the catalog

The live store has no `content_sha256` or analyzer basis for any of its 49 builds. The new
cascade and hook-pack export refuse such a store by design. The old copy has no `backfill.py`
even though its catalog advertises `corpus.backfill`, so this step must follow step 2.

The backfill reads each build's raw image. Stage images whose md5 matches `binary.md5`, as
listed in [image-manifest.json](image-manifest.json) (24 of 49 builds, built read-only on 2026-09-30). Do not trust build id 26 until its identity is resolved (see the living plan, E-0930-9). Then submit
`corpus.backfill` through `/api/v1/actions` with passes `content_sha256`, `analyzer_identity`
and `reloc_table`, and a receipts directory. Builds without an image are skipped with
`no_raw_image`, never guessed.

Check: the job receipt lists updated or skipped counts per pass, and
`SELECT count(*) FROM binary WHERE content_sha256 IS NULL` falls to the number of builds
without an image.

## 4. Re-establish the basis

With hashes and analyzer identity present, `corpus.verify-determinism` runs on the live store.
If the basis hash drifted, run `corpus.rebaseline`, which records the supersession. Changing
`ANALYZER_TIMEOUT_POLICY` (U65) is a separate, deliberate re-baseline.

Check: `verify-determinism` returns `{"identical": true}`.

## 5. What changes for operators

- Job submission can answer 503 with `nextAction: wait` in two cases: the job-event store
  cannot be written (FP-18), or the action's measured memory need can never fit this worker
  (`capacity_prerequisite`). Otherwise a job waits in the queue with `admissionWait` explaining
  why. Set `AGENTDECOMPILE_RESOURCE_ADMISSION=off` to disable resource admission.
- Long-running jobs keep running while they report new completed checkpoints, up to
  `AGENT_DECOMPILE_JOB_MAX_SECONDS` (default 24 h).
- The launcher no longer deletes a Ghidra project on a stale-owner lock. The operator resolves
  ownership.

## Rollback caveat

The live store is at schema version 3 and the reconciled code is at 4 (`match_review`). The
first writing connection from the new code migrates the store to 4. The new code refuses to
write into a store newer than itself (`SchemaTooNewError`, U9 FP-20), but the old serving copy
has no such guard. Before rolling back to the old copy after activation, restore the store from
a pre-activation backup, or keep the old copy read-only.
