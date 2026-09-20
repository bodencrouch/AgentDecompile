# AGENTS.md

Operational authority for this repository. [VISION.md](VISION.md) is the charter;
[STRATEGY.md](STRATEGY.md) is the single recovery pipeline and priority policy.
Start with [README.md](README.md), [USAGE.md](USAGE.md), the
[plans hub](docs/plans/README.md) and [runtime reuse assessment](docs/RUNTIME_REUSE.md).
Search [documented solutions](docs/solutions/README.md) by module or tag before
changing MCP/Ghidra integration.

Frontend requirements are consolidated in [FRONTEND_INTENT.md](docs/FRONTEND_INTENT.md)
with source locators and supersession decisions; [DELIVERY_STATUS.md](docs/DELIVERY_STATUS.md)
separates implementation from observed outcomes. The optional full Vite application
(default5174, packageable at /react/) and the static8080 alternative share backend
capabilities/state. The recovery-operation port restriction below does not turn
Vite into a development-preview-only product or replace static /dashboard.

## Recovery operations

- AgentDecompile is the only active recovery checkout. The
  [upstream donor](docs/UPSTREAM_DONOR_ARCHIVE.md) is read-only.
  Keep session data on NVMe (`/home/brunner56/...` or `/tmp`), not MyBook.
- Use the existing **8080** workbench and `GET /api/v1/actions`; inspect current
  action parameters and submit recovery through that catalog. Do not bypass it
  with a direct recovery CLI, start alternate ports (including 8767 or 5174),
  or treat implementation CLI examples as operating instructions.
- Discover and reuse first: inspect `db/kotorxid.sqlite` (`recovered_function`,
  `reuse_candidate`, `identity`), the Ghidra knowledge cache, verified source
  and audit receipts. Corroborate binary/source/toolchain identity and provenance.
  Bind loaded projects through `program_binding` when a known recovered binary
  appears empty. An empty UI is not permission to analyze again.
- Reuse existing Ghidra analysis and valid receipts. Resume/import is valid for
  agents too. Regenerate only missing, invalid or explicitly requested work.
  Label reused evidence as reused; do not backfill a fresh-run claim. A requested
  fresh final rebuild must actually compile and compare the current source.
- Before admitting work, manually corroborate catalog jobs against process
  owner, PID/start time, command, cwd, target, workspace and logs. Job labels alone
  do not establish ownership. Never duplicate compiler/Wine work or Ghidra
  writers; do not kill or restart another owner's process to make room.
- Before Python edits, corroborate the serving process PID/start time and cwd
  against the loaded module's `__file__` and source revision. The canonical repo
  and executing checkout may differ; editing another checkout is not activation.
  Reconcile source roots and changes explicitly, preserving dirty work. Do not
  blindly sync, overwrite files or restart processes to make an edit take effect.
- Python updates use the standalone in-process reloader; inspect `/health` and
  verify the real consumer with unchanged process/state identities. See
  [hot reload and live receipt](docs/PYTHON_HOT_RELOAD.md). Rejected edits do not
  trigger a restart. The former deferred-replacement supervisor is retired.
- **Do not use systemctl for any reason.** Do not restart the server as routine
  documentation/UI verification or click Restart/Shutdown. If 8080 is unavailable,
  diagnose ownership and report the blocker; do not switch ports or kill on-port.
- **Current recovery mission: no filesystem tests, test suites or builds for
  documentation validation.** Use read-only diff/link/source checks; authorized
  live recovery verification uses 8080. Historical test recipes are reference,
  not permission to run them. Report exactly what was and was not verified.
- Concurrency and matcher order follow STRATEGY; inspect memory, swap and existing
  ownership before adding workers. Keep one writer per corpus/project/toolchain.
- Never count a finished job, compiling C, copied bytes, runtime calls or a
  screenshot as verified recovery. Keep byte-accurate C+assembly-floor and max-C
  results separate; terminal recovery requires the fresh whole-image acceptance
  described in STRATEGY. Runtime readiness follows RUNTIME_REUSE.
- Continue authorized work without unnecessary confirmation. A vague “continue”
  does not authorize publication. Do not automatically open a PR; public,
  high-visibility or third-party upstream PRs require explicit approval in the
  current conversation.

## Implementation references

Recovery package: `src/agentdecompile_recovery/`; companion `scripts/` and
root-relative `target/` layouts remain compatibility contracts. Entry points
`agentdecompile-corpus`, `agentdecompile-recover`,
`agentdecompile-reconstruct` and `scripts/decomp-cli.sh` are implementation
references; operations use the catalog. See [corpus contract](docs/CORPUS_PIPELINE.md)
and [single-binary reference](docs/CRITICAL_PATH.md).

Preserve format/stem-derived profiles; do not hardcode product binaries in
generic defaults. Use MCP tools when available, markdown output by default,
and header/CLI Ghidra authentication where supported. Naming, tool routing,
session semantics, JPype, transactions and modification conflicts are documented
in [src/agentdecompile_cli/CLAUDE.md](src/agentdecompile_cli/CLAUDE.md).
Ghidra Server is RMI over SSL, not HTTP.

[Skills catalog](skills/README.md): environment setup reference is
[server environment](.agents/skills/agentdecompile-server-env/SKILL.md); its generic startup/test recipes
do not override the current mission constraints above. Preserve public behavior,
fix underlying causes, and keep references synchronized when names change.
[CONTRIBUTING.md](CONTRIBUTING.md) covers general development outside this mission.

## Naming Conventions

When generating or suggesting names for symbols, variables, parameters, fields, types, or constants during reverse engineering work, apply these conventions consistently:

| Identifier kind | Convention | Example |
|---|---|---|
| Local variables | `camelCase` | `itemCount`, `saveBuffer` |
| Global variables | `camelCase` | `gameState`, `playerStats` |
| Function parameters | `camelCase` | `charIndex`, `saveFilePath` |
| Classes and types | `CapitalCase` (PascalCase) | `SaveGameHeader`, `ItemRecord` |
| Structure fields | `snake_case` | `save_version`, `char_name` |
| Enum constants | `COBRA_CASE` (SCREAMING_SNAKE) | `SAVE_SLOT_EMPTY`, `ITEM_TYPE_WEAPON` |

Apply these conventions in:
- Decompiled pseudocode variable and parameter names produced by `decompile-function` or `execute-script`
- Symbol rename suggestions from `rename-function`, `rename-variable`, `rename-data-label`
- Structure and field names in `create-structure` / `edit-structure` tool calls
- Enum members defined via `create-enum` / `edit-enum`
- Documentation, comments, and analysis summaries that reference named symbols

When a name is ambiguous or cannot be inferred, prefer the convention that matches the identifier category above rather than leaving it in a raw mangled/numbered form (e.g., prefer `slotIndex` over `local_8` for a loop counter).
