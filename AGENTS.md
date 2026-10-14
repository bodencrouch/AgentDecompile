# AGENTS.md

Operational authority for this repository. [docs/USER_INTENT.md](docs/USER_INTENT.md)
is the consolidated current user contract; [VISION.md](VISION.md) is the charter;
[STRATEGY.md](STRATEGY.md) is the single recovery pipeline and proof policy.
Product shorthand: AgentDecompile is a **higher-level reverse-engineering
workbench built around Ghidra**, not merely an MCP/decompiler wrapper. It joins
related builds, recovers C/C++ that can match their bytes, and makes the
resulting identity, ABI, event and runtime knowledge usable for supported
WASM/graphics, Lua, shim/DLL, hook/cave and memory workflows. Ghidra remains an
analysis engine; runtime success is not source-parity proof. See the user
contract for exact inputs, outputs, capability limits and proof distinctions.
Start with [README.md](README.md), [USAGE.md](USAGE.md), the
[plans hub](docs/plans/README.md) and [runtime reuse assessment](docs/RUNTIME_REUSE.md).
Search [documented solutions](docs/solutions/README.md) by module or tag before
changing MCP/Ghidra integration.

Frontend requirements remain documented in [FRONTEND_INTENT.md](docs/FRONTEND_INTENT.md)
and [DELIVERY_STATUS.md](docs/DELIVERY_STATUS.md), but both frontend recovery
surfaces (static 8080 and Vite 5174) are deferred by the current user direction.
Do not implement, start, restart, test, or route recovery through either UI until
the user reopens that work. This does not erase the product intent; a later
frontend effort must be planned anew against the current user contract.

When documents disagree, follow the authority order in `docs/USER_INTENT.md`.
Historical plans and skill/plugin wrappers are references, not independent
product authorities; canonical project skills should link back to this contract
instead of copying pipeline policy.

## Recovery operations

- AgentDecompile is the only active recovery checkout. The
  [upstream donor](docs/UPSTREAM_DONOR_ARCHIVE.md) is read-only.
  Keep session data on NVMe (`/home/brunner56/...` or `/tmp`), not MyBook.
- Run authorized recovery through the checkout-pinned
  `/home/brunner56/agentdecompile-nvme/AgentDecompile/.venv/bin/agentdecompile-cli`
  frontdoor. The global `agentdecompile-cli` may be an older, incompatible
  install; check the executable path/version and never silently substitute it.
  Use its `corpus` commands for multi-binary recovery and its project-aware
  Ghidra commands to reuse analyzed programs. Do not use either deferred frontend
  as a recovery surface; do not start another UI server or switch ports.
- Treat a local/shared Ghidra project as a valid source of target bytes, symbols,
  types and analysis when those facts are present there. Extract from the
  selected project through AgentDecompile/Ghidra; do not require a detached
  executable merely because a workflow needs bytes. If required bytes or identity
  are absent from the project, state the exact missing evidence before choosing
  an alternate source.
- Discover and reuse first: inspect `db/kotorxid.sqlite` (`recovered_function`,
  `reuse_candidate`, `identity`), the Ghidra knowledge cache, verified source
  and audit receipts. Corroborate binary/source/toolchain identity and provenance.
  Bind loaded projects through `program_binding` when a known recovered binary
  appears empty. An empty UI is not permission to analyze again.
- Reuse existing Ghidra analysis and valid receipts. Resume/import is valid for
  agents too. Regenerate only missing, invalid or explicitly requested work.
  Label reused evidence as reused; do not backfill a fresh-run claim. A requested
  fresh final rebuild must actually compile and compare the current source.
- A missing or incomplete historical toolchain basis limits what a receipt can
  prove; it does **not** make its contents disposable. Preserve the checkpoint
  and salvage each independently useful tier: validate source/cache identity,
  artifact digest and target binding; retain exact-region bytes as historical
  byte-equality evidence, readable max-C as non-exact output, and compiler
  failures/mismatches as diagnostic priors. Re-run only the claims whose
  dependencies changed or cannot be independently validated. If a toolchain
  uncertainty matters, use a small discriminating fresh probe before widening
  work. Never promote salvaged evidence to fresh compiler or whole-image proof.
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
- Goal continuations resume the recovery objective, not the last completed UI
  request. Reuse its acceptance receipt unless new failure evidence or changed
  source/runtime invalidates it; do not repeatedly verify unchanged controls.
  If compilation is blocked, work on the concrete admission or compiler-feedback
  blocker rather than substituting unrelated cleanup. Report fresh compilation,
  accepted matching C and full-image proof separately from implementation work.

## Implementation references

Recovery package: `src/agentdecompile_recovery/`; companion `scripts/` and
root-relative `target/` layouts remain compatibility contracts. The current
operational entry point is the checkout-pinned `agentdecompile-cli`; its `corpus`
subcommands expose the multi-binary pipeline and `reconstruct` is the integrated
single-target path. `agentdecompile-corpus`, `agentdecompile-recover`, and
`scripts/decomp-cli.sh` remain implementation/compatibility references unless
the active contract explicitly selects one. See [corpus contract](docs/CORPUS_PIPELINE.md)
and [single-binary reference](docs/CRITICAL_PATH.md).

Preserve format/stem-derived profiles; do not hardcode product binaries in
generic defaults. Use MCP tools when available, markdown output by default,
and header/CLI Ghidra authentication where supported. Naming, tool routing,
session semantics, JPype, transactions and modification conflicts are documented
in [src/agentdecompile_cli/CLAUDE.md](src/agentdecompile_cli/CLAUDE.md).
Ghidra Server is RMI over SSL, not HTTP.

[Skills catalog](skills/README.md) lists the skills present in this checkout.
Do not link to or advertise a skill whose canonical body is absent. Preserve
public behavior, fix underlying causes, and keep references synchronized when
names change.
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
