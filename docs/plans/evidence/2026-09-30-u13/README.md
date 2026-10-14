# U13 reconciliation, 2026-09-30

The serving tree `/home/brunner56/agentdecompile-nvme` is not a git repository. Its
`scm_version.json` names `4167d4f0`, but the tree was synced later; 523 of 603 files
match `64d768ca` (`find_base.py`). Per-file sync points still differ, so a single-base
merge reverts later git work. The first attempt (a reset commit) did exactly that and was
discarded.

What decided each file:
1. `novel_lines.py`: NVMe lines that no git version of the same path ever contained.
   Zero novel lines means the NVMe copy is an older git state: git is kept.
2. For files with novel lines, the NVMe file's mtime against git's last commit to the path.
   Git newer (16 files, including every verification module): git is kept. NVMe newer
   (16 files, edited through 2026-09-28): the NVMe edits are ported.
3. Ported files were merged against their nearest git base (`true_base_merge.py`,
   `selective_merge.py`), then reviewed. `preparation.py` and `workbench-app.js` were
   merged by hand (both sides changed within a day).

Checks: every changed Python file compiles; all 503 modules import; `tsc --noEmit` is
clean; `node --check` passes. For `workbench-app.js`, 777/782 novel NVMe lines are
kept, and no removed name is still referenced.

Not ported: the two NVMe-only modules `agentdecompile_recovery/{catalog,introspect}.py`
(nothing imports them; `corpus/dashboard/actions/` holds the live versions),
`recovery-prototype.html` (not served or linked), and the NVMe build output under
`static/react/assets/` (regenerate from the Vite source).
