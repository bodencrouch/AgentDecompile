# Task 3 report: completed CLI source integration

## Recorded pre-merge state

- Authorized target worktree: `/home/brunner56/ad-wt/consolidation-20260928`
- Target branch: `codex/branch-consolidation-20260928`
- Original target BASE, recorded before merge: `c470052e2f5f9e65d5bd30caa429834130118ddb`
- Frozen CLI source tip: `f1c911a42138c0a24868021ed048200d50bb2d35`
- Frozen CLI source tree: `35e9589bc9c0a8e5cb22e7248ac2544fd285b7d7`
- Frozen source receipt: `.superpowers/sdd/branch-consolidation-plan/cli-frozen-tip.json`
- Source-integration merge HEAD: `6af077cfad03970dde1dd79540f65e8aec059264`
- Source-integration merge tree: `e120a803c802449d45262858a82417c72128755e`
- Merge parents, in order: `c470052e2f5f9e65d5bd30caa429834130118ddb f1c911a42138c0a24868021ed048200d50bb2d35`

Before integration, `git status --short --branch` reported only
`## codex/branch-consolidation-20260928`, and `git rev-parse HEAD` matched the
recorded BASE. The frozen tip's tree matched the controller-supplied tree. This
section was written before invoking the merge.

## Result

`6af077cfad03970dde1dd79540f65e8aec059264` is a true two-parent merge of the
recorded target BASE and frozen CLI source. It integrates the frozen owner
result while retaining the current native batch, recovery catalog, evidence,
ownership, migration, and packaging contracts. It does not claim actual `uvx`,
installed, JVM/Ghidra, backend, recovery, native-build, or whole-image
acceptance.

The frozen source changed 164 paths relative to merge base
`a8b6d2faf8a71b633fd5dedfd07cc493ee250536`. Final-index blob comparison
classified 150 paths as the exact incoming blob, 13 as coherent resolutions
combining newer target behavior with incoming behavior, and one incoming-only
test as deliberately discarded because a newer current-schema suite supersedes
its assumptions. No incoming product path was discarded.

## Merge and conflict dispositions

The merge was started with:

```text
git merge --no-ff --no-commit f1c911a42138c0a24868021ed048200d50bb2d35
```

The twelve conflicted paths were resolved as follows:

| Path | Disposition |
|---|---|
| `.gitignore` | Combined the incoming recursive grid-source inclusion with the current ignore structure. |
| `pyproject.toml` | Kept the incoming `s3`/`signing` extras and grid packaging. Retired the standalone `agentdecompile-reconstruct` and `agentdecompile-acquisition-query` scripts because current authority exposes them through `agentdecompile-cli reconstruct` and `agentdecompile-cli acquisition-query`. |
| `src/agentdecompile_cli/cli.py` | Took the completed incoming CLI implementation, including `responseFormat`, typed output choices, lazy recovery bridges, backend routing, and alias handling. The later focused contract repair changed tests only. |
| `src/agentdecompile_grid/cli.py` | Took the incoming `prog` override used by the embedded CLI bridge. |
| `src/agentdecompile_grid/objects/s3.py` | Took the corrected package extra `agentdecompile[s3]`. |
| `src/agentdecompile_grid/worker/identity.py` | Took the corrected package extra `agentdecompile[signing]`. |
| `src/agentdecompile_recovery/corpus/cli.py` | Preserved the current native `decompile-batch` selection, registration, and dispatch plus current recovery verbs; added the incoming `DEFAULT_PROG`/`prog` embedding contract. |
| `src/agentdecompile_recovery/corpus/export_run_report.py` | Kept the current richer report/provenance fields and replaced its private narrow table creator with the shared incoming recovered-table helper. |
| `src/agentdecompile_recovery/corpus/ingest_recovered.py` | Kept the current source/target hashes, semantic evidence, and expanded candidate key; ported the incoming order-independent canonical creation, additive legacy upgrade, caller-transaction savepoint, and read-only fast-path behavior. |
| `src/agentdecompile_recovery/corpus/store.py` | Kept the current forward-only migration ledger, content-hash recovery families, and read-only behavior. Repair `91b7183a9e4a068e9ee38c14c9e91e809b637636` then restored two independent incoming guarantees: a failed initializer closes its owned connection, and transient backfill failures use primary SQLite result-code classification. |
| `tests/test_cli_contract.py` | Kept unconditional `adgrid` coverage because this final tree includes the package, then aligned bridge callbacks/byte-exact `-f` forwarding and `responseFormat` assertions with the integrated CLI. The bridge resolution matches the separately reviewed PR207 conflict fix without importing unrelated PR content. |
| `tests/test_recovered_function_schema.py` | Rewrote the add/add test for the current expanded schema. It verifies report/bridge order independence, reuse-table separation, exact empty-table rebuild, preservation of nonconforming historical rows, caller rollback, and the no-write-lock canonical fast path. |

The first merge omitted `tests/test_store_connect_transactions.py` because its
fixtures asserted the old row-ID `unclassified:<id>` family. Independent review
showed that this blanket disposition also dropped useful behavior unrelated to
the obsolete fixture. Repair `91b7183a9e4a068e9ee38c14c9e91e809b637636`
restores a focused version using current content-hash fixtures. It covers
initializer interruption and close ownership, rollback-failure closure,
unrelated `SQLITE_ERROR` text containing `busy`/`locked`, Python 3.10 message
fallback, actual busy/read-only failures, and caller-owned transactions.

The first focused run also exposed one fixture drift in
`tests/test_cli_live_regressions.py`: the integrated structure provider now
collects all CParser composites/enums/types and validates with a scratch
`StandAloneDataTypeManager` plus a JPype `JArray`. The fake now supplies those
interfaces. No JVM was started.

## Per-CLI-ref disposition

The audit used the exact ref names and SHAs in `ref-audit.json`. For each ref it
first ran `git merge-base --is-ancestor <sha> f1c911...`; for non-ancestors it
used bounded `git diff-tree --name-status -r` path enumeration and batched
`git cat-file --batch-check=%(objectname)` blob comparison against the frozen
tree. The classification here is per ref, not an aggregate branch count.

| Disposition | Explicit refs |
|---|---|
| Ancestor of frozen result | `cli-contract-fixes`, `cli-integration`, `cli-live-fixes`, `cli-sweep`, `origin/cli-contract-fixes`, `origin/cli-integration`, `origin/cli-live-fixes` |
| Tip-changed paths have exact frozen blobs | `cli-api-names`, `cli-auth-routing-off`, `cli-batch`, `cli-c1`, `cli-c45`, `cli-dtcompare`, `cli-t12`, `cli-t12-preview`, `cli-t15`, `cli-t17`, `cli-t18`, `cli-t2`, `origin/cli-t2`, `origin/cli-t8` |
| Present and evolved by frozen follow-ups | `cli-callgraph`, `cli-live-review`, `cli-persist`, `cli-providers-misc`, `cli-render`, `cli-server-list`, `cli-session`, `cli-t10`, `cli-t11`, `cli-t13`, `cli-t13-f6be055`, `cli-t16`, `cli-t20`, `cli-t3`, `cli-t4`, `cli-t6`, `cli-t7`, `cli-t8`, `cli-t9`, `origin/cli-t13`, `origin/cli-t3`, `origin/cli-t4`, `origin/cli-t6`, `origin/cli-t7`, `origin/cli-t9`, `origin/optimize/fast-program-analysis-wait`, `origin/snapshot/cli-t7-20260927`, `origin/snapshot/cli-t8-20260927`, `origin/snapshot/cli-t9-20260927` |

The evolved set had four paths absent from the frozen tree; each was inspected:

- `tests/test_store_transaction_hygiene.py` from `cli-t20` contains obsolete
  row-ID fixtures. Its useful connection cleanup and error-classification
  guarantees are adapted to the current content-hash schema in
  `tests/test_store_connect_transactions.py` by repair `91b7183`.
- `tests/test_cli_generated_commands.py` from the `cli-t9` family was folded
  into `tests/test_cli_contract.py`; frozen follow-up history contains the
  generated-command and response-format repairs.
- `tests/test_cli_mode_aliases.py` from the t8 snapshot was folded into
  `tests/test_cli_contract.py` and subsequent frozen registry/alias commits.
- `tools/eval/measure_unit_gate.py` from
  `origin/optimize/fast-program-analysis-wait` is an evaluation harness that
  shells a broad `uv run pytest`; it has no production consumer and is outside
  this bounded source merge. The production wait implementation is present and
  evolved in `mcp_utils/program_analysis.py`.

After repair `91b7183`, no meaningful CLI source residue identified by this
audit remains unported; fixture-specific row-ID expectations stay retired.

## Verification

Static verification after the final repairs:

```text
python [AST parse of every src/tests .py plus tomllib.load(pyproject.toml)]
AST_OK files=971 TOML_OK pyproject.toml

python [AST import census for internal agentdecompile* imports]
INTERNAL_IMPORT_PATHS_OK checked=837 modules=574

rg -n '^(<<<<<<<|=======|>>>>>>>)' [all conflicted paths]
# no output

git diff --cached --check
# no output

git diff --name-only --diff-filter=U
# no output
```

The controller admitted this side-effect-bounded command with a 180-second
outer timeout:

```text
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src \
/run/media/brunner56/MyBook/Workspaces/ai-projects/AgentDecompile/.venv/bin/python -m pytest -q \
-p pytest_asyncio.plugin \
--basetemp=.superpowers/sdd/branch-consolidation-plan/task-3-pytest/attempt-4-final/tmp \
-o cache_dir=.superpowers/sdd/branch-consolidation-plan/task-3-pytest/attempt-4-final/cache \
-o log_file=.superpowers/sdd/branch-consolidation-plan/task-3-pytest/attempt-4-final/log/pytest.log \
-o timeout= -o timeout_method= \
tests/test_cli_contract.py tests/test_cli_input_errors.py \
tests/test_cli_live_regressions.py tests/test_cli_server_parsers.py \
tests/test_canonical_tool_parity.py tests/test_recovered_function_schema.py \
tests/test_corpus_decompile_batch_selection.py
```

Final result: exit `0`, duration `7.004277s`, `104 passed, 1 skipped, 2
warnings`. The warnings say the disabled plugin set does not recognize the two
pytest-timeout ini keys; the external `/usr/bin/timeout` remained the enforced
180-second bound. Before pytest, the same `PYTHONPATH=src` environment proved
both package origins were under this worktree and exited `0`.

Raw retained receipts:

- `.superpowers/sdd/branch-consolidation-plan/task-3-pytest/attempt-1/`:
  initial `99 passed, 4 failed, 1 skipped`; preserved diagnosis input.
- `.superpowers/sdd/branch-consolidation-plan/task-3-pytest/attempt-2/`:
  `102 passed, 1 failed, 1 skipped` after CLI contract alignment.
- `.superpowers/sdd/branch-consolidation-plan/task-3-pytest/attempt-3-focused/`:
  fixture spelling diagnosis, exit `1`.
- `.superpowers/sdd/branch-consolidation-plan/task-3-pytest/attempt-3b-focused/`:
  repaired structure fixture, `1 passed`, exit `0`.
- `.superpowers/sdd/branch-consolidation-plan/task-3-pytest/attempt-4-final/`:
  final argv, source origins, stdout, stderr, exit, duration, and pytest log.

The tests wrote only their recorded basetemp/cache/log directories and pytest
`tmp_path` fixtures under this owned NVMe worktree. They used in-memory or
temporary SQLite databases and fake/monkeypatched CLI providers. They did not
start a server, JVM, Ghidra, compiler, Wine, network service, or recovery job.

## Known remaining defects and unperformed gates

This source-integration gate is `DONE_WITH_CONCERNS`, not a CLI safety or runtime
acceptance verdict. The following confirmed defects deliberately remain for the
separately scoped Task 3b/Task 5 owners:

- `mcp_server/providers/import_export.py` and
  `mcp_server/providers/project.py` still contain generic transaction drains
  that feed `TransactionInfo.getID()` metadata into `endTransaction()`. The
  exact affected helpers/callers and ownership-safe correction are recorded in
  `transaction-audit.md` for Task 3b.
- `mcp_server/providers/_collectors.py` uses `data_type_label` at module-level
  collector sites while importing it only inside a later function; actual local
  list-functions qualification observed `NameError`.
- `mcp_utils/program_analysis.py` imports
  `ghidrecomp.utility.analyze_program`; its progress prints can contaminate
  strict JSON stdout.
- `mcp_server/providers/data.py` still passes a Python `bytearray` to Java
  `Memory.getBytes`, producing a copy-back failure under JPype. The bounded
  one-file repair and byte-level assertions are in `task-5-byte-read-audit.md`.
- The always-failing `delete` convenience stub, `gen_callgraph` alias conflict,
  GUI-only command boundary, and unavailable positive 8080 transport gate remain
  listed in `task-5-defects.md`.

No full suite, build, installed entrypoint, `uvx --with-editable`, live backend,
Ghidra/JVM, compiler, recovery, or external-client test ran here. Task 5 owns the
exhaustive actual CLI matrix on a separately frozen final source revision.
