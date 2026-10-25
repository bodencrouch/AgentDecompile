# Agent bootstrap

You are an AI agent that has just been pointed at AgentDecompile. Follow this file top to
bottom once per session. It is short on purpose; it links to the authority instead of
restating it.

## 0. Read, in this order

1. [../AGENTS.md](../AGENTS.md): operational authority. Recovery runs through the existing
   8080 catalog, one writer per corpus/project/toolchain, no systemctl, no alternate ports,
   no filesystem tests or builds for documentation validation during the current mission.
2. [../STRATEGY.md](../STRATEGY.md): matcher order, acceptance, the whole-image finish line.
3. [RECOVERY_LOOP.md](RECOVERY_LOOP.md): the method you will execute and its fallbacks.
4. [../METHODOLOGY.md](../METHODOLOGY.md) §4: the claim tiers you must never blur.
5. The skills catalog in [../skills/README.md](../skills/README.md). `tiered-re-analysis`
   before opening anything; `source-recovery` for C and objdiff; `bsim-corpus` for
   cross-build names; `re-planner`/`re-worker`/`re-critic`/`re-aggregator` for multi-agent
   roles; `lfg` to continue authorized work.

## 1. Attach, do not start

- MCP endpoint: `http://127.0.0.1:8080/mcp`. Actions: `GET /api/v1/actions`. Health: `/health`.
- If it is unreachable, diagnose ownership (process owner, PID and start time, command,
  cwd) and report the blocker. Do not start a server, switch ports or kill anything.
- Ghidra Server is RMI over SSL. Its credentials do not authenticate the MCP listener, and
  session IDs are not authentication.

## 2. Discover before you analyze

An empty UI is not permission to analyze again. Before any Ghidra mutation:

- Inspect `db/kotorxid.sqlite` (`recovered_function`, `reuse_candidate`, `identity`), the
  Ghidra knowledge cache, verified source and audit receipts.
- Bind loaded projects through `program_binding` when a known recovered binary appears empty.
- Reuse valid analysis and receipts; label reused evidence as reused. Regenerate only what
  is missing, invalid or explicitly requested.
- Run `python3 entrypoint/setup/doctor.py` to learn which engines are present and therefore
  which evidence tiers are reachable on this machine.

## 3. Pick the cheapest sufficient tier

| Tier | Use |
|---|---|
| 0 | Existing metadata, file triage, strings, static witnesses |
| 1 | Stored batch decompilation, BSim, export evidence |
| 2 | Read-only queries against existing analyzed Ghidra state |
| 3 | Missing deep analysis or authorized mutations, only after ownership checks |

Do not re-run `analyze-program` on a program that already has analysis.

## 4. Treat the corpus as one object

Register every build and platform variant. Mark the STABS/DWARF build as the donor.
Identity is a `logical_id`, never an address. One address can carry several logical
entities; the same `logical_id` never implies source interchangeability or ABI/layout
compatibility. Keep ambiguous, absent, folded, inline and split cases visible.

## 5. Match with layered evidence, in STRATEGY's order

Authoritative debug and provenance first; unique exact evidence; rare references and
neighborhood propagation; structure and BSim; then applicable second opinions on diagnosed
residue. A proposed match transfers and compares knowledge. It is not proof. Confidence and
provenance stay attached to anything carried.

## 6. Recover, verify, fall back

Per function the target is readable C that compiles under the identified toolchain and
matches the original bytes under the project's objdiff and proof rules. Where that is not
yet possible, export a clearly labeled `.S` that preserves the machine code and calling
boundary and stays replaceable by C. C++ is a parallel aspiration where evidence and
compiler behavior support it; never infer it from a C-level match. Compile after every
change and keep exact error and attempt receipts.

## 7. Write with the project's names

| Identifier kind | Convention | Example |
|---|---|---|
| Local, global, parameter | `camelCase` | `itemCount`, `gameState`, `charIndex` |
| Class, type | `CapitalCase` | `SaveGameHeader` |
| Struct field | `snake_case` | `save_version` |
| Enum constant | `COBRA_CASE` | `SAVE_SLOT_EMPTY` |

Prefer a conventional name over a raw placeholder when the category is clear
(`slotIndex` over `local_8`). Never let a placeholder replace a better name.

## 8. Report in claim tiers

| Say | Only when |
|---|---|
| Verified | Compile plus objdiff 0 against the validated target, with receipts |
| Readable / compiling | Assembly-free C compiles; parity not shown |
| Advisory | Inferred, decompiled, generated, unproven |
| Context hint | Symbols, notes, names, debug info |
| Byte-authoritative | Exact target bytes, not recovered source |
| Insufficient evidence | Two explanations fit the observations and nothing available separates them |

Never count a finished job, compiling C, copied bytes, a runtime call or a screenshot as
verified recovery. Keep C+assembly-floor and max-C results separate. The terminal claim
needs a fresh whole-image compile plus objdiff zero-difference receipt, and current evidence
says that route is not implemented end-to-end.

## 9. Before you change code

Corroborate the serving process PID, start time and cwd against the loaded module's
`__file__` and source revision. Editing another checkout is not activation. Python updates
use the in-process reloader ([../docs/PYTHON_HOT_RELOAD.md](../docs/PYTHON_HOT_RELOAD.md));
rejected edits do not trigger a restart. Preserve dirty work; never blindly sync or
overwrite.

## 10. Before you publish

Continue authorized work without unnecessary confirmation, but a vague "continue" does not
authorize publication. Do not open PRs automatically; public, high-visibility or
third-party upstream PRs require explicit approval in the current conversation. Report
exactly what was and was not verified.
