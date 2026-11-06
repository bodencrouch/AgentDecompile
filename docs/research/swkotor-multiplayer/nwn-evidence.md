# NWN/NWN2 dedicated-server evidence (bounded MCP inspection)

Checked 2026-09-15 against the already-open local Ghidra project `/home/brunner56/agentdecompile-nvme/workspace/Workspace.gpr`. Every successful query supplied an explicit program path. No project was opened or switched, no analysis was started, and no program was modified.

## What is currently established

| Program | Ghidra language | Compiler family | Current function count | Analysis state |
|---|---|---|---:|---|
| `/nwserver.exe` | `x86:LE:32:default` | `windows` | 0 | incomplete |
| `/nwn2server.exe` | `x86:LE:32:default` | `windows` | 1 | incomplete |

The MCP session reported both programs open in local-GPR mode. The targeted `get-current-program` replies also showed the requested program becoming the active program during that call, so explicit `program_path` routing worked; this inspection did not issue `open`, `open-project`, or any project mutation.

## Import/function inspection boundary

The requested import and named-function evidence is not available yet. `list-imports` for both explicit paths returned `analysis-timeout` with `analysisComplete: false`. After a bounded 25-second wait, the retry produced no response for more than 90 seconds and was terminated. A separate `list-functions` query on `/nwserver.exe`, restricted to likely server/network/init names, likewise produced no response in more than 60 seconds and was terminated. No further retries were made because concurrent callers were already observing shared-lock contention.

Consequently, this run does **not** establish Winsock, DirectPlay, GameSpy, master-server, socket/bind/listen, password, player-count, or particular initialization-function imports in either executable. It also does not establish the behavior of any apparent `CreateServer` name mentioned by another concurrent caller; no completed function response was received here.

## Architectural contrast that the binaries could test once analysis is ready

The useful NWN/NWN2 question is whether each dedicated executable owns a headless authoritative-server lifecycle—network startup, bind/listen, module/game-state initialization, client admission, periodic master-server advertisement, and shutdown—separately from the player client. Imports and a few entry/init decompilations can confirm that shape once Ghidra has produced functions.

KotOR already has an in-process client/server message queue; remote multiplayer would require a new transport integrated with that existing boundary. Its discovery layer should therefore remain a separate, minimal concern: advertise endpoint, server name, current/max players, build/protocol version, and only a password-required boolean; then authenticate and join through the KotOR transport. NWN/NWN2 may offer a lifecycle and product-design precedent, but no protocol compatibility should be inferred without completed import and function evidence.

## Smallest follow-up

After the existing auto-analysis completes, make one read-only pass per explicit path:

1. `list-imports` grouped by library, looking for networking/runtime libraries.
2. `list-functions` filtered to entry, init, server, network, master, socket, listen, and connect names.
3. Decompile at most two high-confidence initialization/server functions per executable.

Do not rerun analysis merely to answer this comparison; the current auto-analysis gate is the only blocker recorded here.

