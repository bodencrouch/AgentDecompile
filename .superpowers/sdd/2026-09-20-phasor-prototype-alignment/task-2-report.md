# Task 2 report — active guidance and unfinished intent

Status: implemented for review; no runtime completion claimed. Delivery is limited
to the 61 paths in `task-2-manifest.json`. The controller owns reviewed canonical
integration. No canonical file, runtime code, test, frozen plan, historical proof
report, global plugin or external KotorPhasor file was changed.

## Inventory and preservation

- `task-2-inventory.json` enumerates 147 active entrypoints/references with changed
  or unchanged disposition and rationale. Inventory includes all project skill
  trees, Copilot roles, Cursor commands/prompts, local plugin configuration,
  root documentation, docs hubs, source instructions and mission root files.
- `task-2-manifest.json` gives every delivery path, exact baseline commit,
  canonical-originally-present flag, expected canonical SHA-256 and final SHA-256.
  The sole newly absent canonical path is `docs/PROTOTYPE_OUTCOMES.md`.
- `9a38358` preserved ignored canonical server-env/rewrite-worker bodies and the
  first per-file baseline inventory before editing. Other files listed there
  were already byte-identical to canonical.
- `d074563` preserved the three untracked migrated source-command bodies exactly.
- `6303813` recorded additional per-file baseline SHA-256 values; those files
  were already identical to canonical at `d074563`.
- `387a2e5` preserved the five ignored canonical mission entrypoint files exactly,
  before adding dated current-routing notes.
- Task 1 overlap is only AGENTS (corrected server-env link) and STRATEGY
  (per-target recurrence/failover/name precedence). Their expected canonical
  baseline remains `2fca6bb`, not the later Task 1 implementation. Both baseline
  byte comparisons against canonical returned true. Task 1 at `8f3d6281` is
  preserved in the branch.
- All baseline commits used `-c core.hooksPath=/dev/null`. No hooks/tests ran.
  The implementation commit follows this report; its ID is reported to controller.

## Reconciliation

Canonical procedures now live in `.agents/skills/`; human/client skill loaders
route there. Fixed self-referential tiered-analysis and MCP-debugging stubs,
restored missing tracked server-env/rewrite-worker bodies, consolidated four RE
roles, removed confidence-based promotion and the mandatory separate analysis
store, and made artifact identities fingerprint/build/logical-instance aware.
The project lfg command continues authorized work rather than automatically
shipping or running a restart-heavy historical harness. Migrated commands route
to the same current entrypoints.

MCP debugging references no longer assert invented installed tools or automatic
permission repair/reconnect. BSim and skill-authoring preserve useful reference
material under current operational restrictions. Ralphy prompts respect scope
and authorized verification; Kilo/Roo rules no longer mandate another memory
service or automatic context publication. No global configuration changed.

The plugin now uses native HTTP `http://127.0.0.1:8080/mcp`, with no spawned
command. `docs/mcp.example.json` contains one connection instead of eight aliases.
Shared-auth use cases remain documented. Actual proxy source was inspected:
`server.py:proxy_main` does not launch a JVM but does attempt a web UI sidecar;
`webui.py:launch_webui_sidecar` honors `AGENT_DECOMPILE_WEBUI_ENABLED=false`.
That existing proxy is documented only for stdio-only clients. Native HTTP plugin
support was checked against Anthropic's official plugin reference and integration
examples:
https://code.claude.com/docs/en/plugins-reference
https://github.com/anthropics/claude-plugins-official/blob/main/plugins/plugin-dev/skills/mcp-integration/SKILL.md
No plugin was activated and no connection outcome is claimed.

METHODOLOGY points at STRATEGY rather than duplicating an obsolete matcher/recovery
ladder. STRATEGY preserves the Task 1 runtime/full-image contract and explicitly
maps the repeated per-target loop, helper/compile/cross-place failover and name
precedence. Docs/skills/prototype hubs link the new outcome ledger.

The ledger uses archive reports with 2–3 distinct original user answers for each
inferred recurring theme. It separates inspected implementation gaps, historical
runtime evidence and unreassessed requests, including both source variants,
fresh whole-image proof, runtime binding/calls/caves/feedback, quest/softlock,
client/server/browser/master lobby, dashboard continuity, hot reload, KotorXID
interaction obligations, K1 ZIP delivery, corpus exceptions and Discord reporting.
It does not resume the paused goal. The audit locator names this isolated worktree
explicitly; private research files are not added to canonical delivery.

Mission root documents were read in full from canonical. Their September 8–9
content remains verbatim below a dated supersession/routing note; old role labels
do not establish current ownership. Mission notes, decisions and verification
history remain unchanged.

## Unchanged surfaces and limits

The inventory records every unchanged path individually. In particular:

- Task 1 source-recovery/workbench skills and operational docs already passed
  their review; no duplicate rewrite.
- Claude/Cursor role loaders and Copilot role metadata already point to the
  canonical skills; four roles are changed at the shared source.
- Vendored web-design guidance/SYNC, authoring reference, marketplace metadata,
  empty VS Code MCP map and Cursor plugin enablement do not establish conflicting
  recovery authority.
- Detached lfg shipping helper references are retained but no active project lfg
  procedure routes to them. They are not permission to publish.
- General technical/API/import/security/Unity/E2E references remain under AGENTS
  rather than rewriting their implementation examples. Historical solution,
  verification, prototype decision and frozen-plan records remain unchanged.
- This is an active-entrypoint and contradiction audit, not proof that every
  external link or historical technical claim throughout the repository is current.

## Checks performed

- Read-only `git diff --check` passed repeatedly after edits.
- Scoped contradiction search found only prohibitions/current claim boundaries,
  detached shipping references, and explicitly historical mission snapshots.
- Inline Node checks across the 61 delivery files: no missing local Markdown
  links, no missing skill name/description frontmatter, valid plugin/example JSON,
  exactly one example connection and a native-HTTP-only plugin configuration.
  Frontmatter check is structural, not a full YAML/schema certification.
- SHA-256 checks across all delivery files: canonical bytes still match recorded
  expected snapshots; final bytes match the manifest. Earlier Task 1 overlap
  was independently compared against `2fca6bb`.
- Read actual canonical hookpack exporter, workflow admission/resume paths,
  server restart controls, proxy and web UI startup; inspected donor design
  00/09/10 and controller hot-reload investigation. These establish source
  behavior/requirements, not successful runtime operation.
- No tests, test files, builds, package installs, game launches, dashboard actions,
  server startup/restarts, process signals, service-manager writes or systemctl.
  No push, PR, merge, global edits, memory updates or subagents.

## Remaining concerns

True Python hot reload remains unimplemented. The controller's live cgroup and
supervisor findings rule out assuming a safe parent-only adoption transition;
Python 3.14 watcher compatibility and actual retained-state proof remain open.
Full corpus, source deliveries, whole-image parity, runtime adapter integration,
quests and multiplayer remain precisely bounded in the outcome ledger.

Storage made some local Git operations take more than ten seconds despite the
NVMe worktree because Git metadata is shared with the mounted checkout. Every
completed baseline commit is identified above. Do not terminate unrelated Git
or recovery processes; the byte manifest supports direct reviewed integration.
