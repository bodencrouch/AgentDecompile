---
name: bsim-corpus
description: "Use this skill when ingesting a Ghidra repository into BSim, asking what a bsim_datadir holds, matching names across related builds, or when BSim found nothing might mean createdatabase never ran (issue 169). Apply even if they only say the 24 programs or odyssey repo."
license: AGPL-3.0-or-later
compatibility: Requires GHIDRA_INSTALL_DIR/support/bsim; optional running BSimControl PostgreSQL
metadata:
  author: AgentDecompile
  version: "1.0"
---

# BSim corpus (issue 169)

Read [AGENTS](../../../AGENTS.md) and [STRATEGY](../../../STRATEGY.md) first.
Current recovery operations use the existing 8080 catalog; CLI, test and startup
recipes below are implementation references subject to the mission restrictions.


BSim supplies one identity witness under STRATEGY's field-level propagation gates. Starting PostgreSQL is not ingest.

**REQUIRED SUB-SKILL:** `tiered-re-analysis` (this is Tier 1 — no open MCP program required)

## Implementation command reference

| Goal | CLI | MCP |
|---|---|---|
| Create DB | `agentdecompile-corpus bsim-createdatabase --datadir DIR --name NAME` | `bsim-createdatabase` |
| Ingest repo | `agentdecompile-corpus bsim-ingest --repository REPO --datadir DIR --name NAME` | `bsim-ingest` |
| Report | `agentdecompile-corpus bsim-report --datadir DIR` | `bsim-report` |

Workbench: **Analyze → Ingest repository into BSim** / **Report BSim database**.

## Report states (do not invent others)

- `missing_datadir` / `no_postgres` / `no_bsim_database` — datadir has no BSim database (initdb templates only is this)
- `empty_database` — schema exists, 0 executables
- `populated` — N executables by name and arch
- `database_unreachable` — extra cluster DBs but `bsim` did not answer

Never infer a corpus from `du` of `base/<oid>`.

## Ingest rules

- Discover programs from the Ghidra project / shared-fs locator.
- Skip programs already in `listexes` or the receipt (`agentdecompile-bsim-ingest.json`) unless specific invalid evidence requires authorized regeneration.
- Per-program progress in the JSON `results` list. A 24-program failure must resume, not restart.
- Default URL: `AGENT_DECOMPILE_BSIM_URL` or `postgresql://127.0.0.1:<port from postgresql.conf>/<name>`.

## After ingest

Functions in the workbench can list from BSim (`listfuncs --name <program>`). Matching across builds: `match-function` or BSim queries — not objdiff. Byte-match stays `run-decomp-match`.
