# KotOR multiplayer recovery investigation

Integration provenance: these notes and retained evidence were ported from
commit `0b7305bb6ee1b9dee31311a6dec8623256766627` on September 28, 2026 (UTC).
Evidence described below as fresh was collected during the original investigation,
not this integration. No binary hashes, live MCP results, compilation, or gameplay
claims were revalidated during the port. The worktree-specific `.codex` environment
file was deliberately excluded.

Status: investigation in progress. This directory does not contain a buildable
replacement game or a dedicated game server. No multiplayer, lobby, in-game menu,
or full-image C/C++ recovery acceptance criterion has passed.

## Request and binding requirements

Produce source-based builds of `swkotor.exe` and `swkotorserver.exe`, retain the
recovered engine, add public server discovery and password-protected joins, and
add a main-menu server browser styled like Halo Combat Evolved PC. Unmodified
recovered functions should preserve original behavior and pursue zero-difference
machine-code verification. New networking and UI necessarily introduce code
absent from the original executable.

An unrelated socket daemon, a launcher renamed `swkotor.exe`, a static browser
mockup, and an executable reconstructed by copying original machine code do not
meet those requirements.

## Evidence collected in this investigation

- [Engine evidence](engine-evidence.md): exact input hashes, recovered source
  limitations, historical receipt discrepancies, and local transport evidence.
- [Lobby research](lobby-research.md): current public master-server options,
  registration constraints, and password metadata handling.
- [NWN/NWN2 investigation](nwn-evidence.md): analyzed-program availability and
  bounded MCP failures; no donor protocol compatibility is claimed.
- [Fresh function inventory](evidence/netlayer-inventory.json): MCP enumeration
  of the transport region in the analyzed Ghidra program.
- [Fresh sender decompilation and disassembly](evidence/send-message-to-player.json):
  direct MCP result including callers, callees, source, and disassembly.
- [Readable sender pseudocode](evidence/005d4cb0_SendMessageToPlayer.cpp.txt):
  advisory decompilation with its raw incomplete signature retained and a header
  pointing to the corrected ABI; deliberately excluded from any build.
- [Binary binding receipt](evidence/binary-binding.json): all 150 exported
  instructions match the exact corpus binary. This is a sample comparison, not
  source compilation or a full-function zero-diff receipt.
- [All direct sender callers](evidence/send-callers.txt) and
  [full sender disassembly](evidence/send-disassembly.txt): fresh static evidence
  for the corrected four-stack-argument ABI.
- [Receiver disassembly](evidence/receive-disassembly.txt),
  [player-info getter](evidence/player-info-disassembly.txt),
  [server wrapper](evidence/server-handle-message-disassembly.txt),
  [server internal handler](evidence/server-internal-handle-message-disassembly.txt),
  and [client wrapper](evidence/client-handle-message-disassembly.txt):
  hash-bound exports supporting dispatch and shared player-permission findings.

The analyzed project is
`/home/brunner56/agentdecompile-nvme/workspace/Workspace.gpr`, program
`/K1/k1_win_gog_swkotor.exe`. Its program path alone is not a hash receipt.
The corpus raw executable has SHA-256
`9c10e0450a6eeca417e036e3cde7474fed1f0a92aab018446d156944dea91435`.
The separate `k1gog-target/swkotor.exe` has SHA-256
`34e6d971c034222a417995d8e1e8fdd9f8781795c9c289bd86c499a439f34c88`.
They must not share proof receipts without an explicit transformation record.

## Findings that determine implementation

`CNetLayer::SendMessageToPlayer` at `0x005d4cb0` gets its destination from
`this+0x2000c`, writes a length followed by payload bytes into that destination's
memory, and updates the destination's tail at `+0x20004`. That is a real
client/server message boundary, but the observed path is within one process.
It is not an existing Internet server implementation waiting to be enabled.

The local queue cannot safely become a public packet handler as-is. The sender's
overflow path formats a diagnostic and then proceeds to the copy. Its recovered
declaration also disagrees with `RET 0x10`. The retained 26 direct-call contexts
and callee disassembly establish four stack arguments: player ID, payload,
length and a fourth argument unused by this body. The call at `0x0067746a`
explicitly supplies zero for that argument; not every register-valued argument
has its reaching definition retained, so universal zero values are not claimed.
The raw recovered signature remains incomplete in both the unchanged MCP result
and pseudocode body; the corrected ABI is documented in [engine evidence](engine-evidence.md).
Decompiler-generated
types and names are analysis hypotheses, not source provenance or ABI proof.

The source corpus contains byte-emitter shims and unresolved surrogate calls.
In particular, its receive dispatcher substitutes `ghidra_call()` for application
dispatch. Historical per-function compile/match counts do not prove a complete
semantic engine link. Identical round-trip PE output can preserve original bytes
without recovering their C/C++ implementation.

## Gameplay scope confirmed by the user

Support both shared co-op campaigns and persistent worlds with independent
characters, sessions and player progress. Implement them as explicit server modes
sharing the engine and transport. Co-op needs shared story/dialogue progress;
persistent worlds need per-player state and session ownership. Character control,
dialogue/cutscene policy, pause, module transitions, save authority, late join and
reconnect must be validated in each mode. This is a scope requirement, not a
claim that the original executable already implements either multiplayer mode.

## Required implementation sequence

1. **Source baseline and identity.** Bind the chosen executable, Ghidra database,
   compiler/toolchain, function inventory, source files and receipts to hashes.
   Recover necessary declarations, data, globals, RTTI/vtables, imports, resources
   and startup. Establish a clean C/C++ link and an actual original-game launch.
   Keep unverified code and substrate separate; never count `_emit` or copied PE
   regions as semantic source recovery.
2. **Local transport and dispatch.** Recover initialization, send, receive,
   connection control and application callbacks. Correct calling conventions and
   all arguments from disassembly/callers. Validate queue wrap, framing, object
   identity and lifecycle against the original process before changing transport.
3. **Remote gameplay.** Add a versioned, bounded, authenticated transport with
   reliable ordering where engine messages require it. Validate packet lengths
   and message kinds before dispatch. Assign server-owned player identities;
   never trust client-provided ownership. Prove two real clients see the same
   authoritative world, then implement both required gameplay modes, reconnect,
   disconnect cleanup and content/build compatibility checks.
4. **Dedicated executable.** Separate simulation startup/tick/shutdown from the
   rendering/audio/window path. Prove module loading, scripts, AI, combat and
   saves run without a local player or rendering context. Build
   `swkotorserver.exe` from the shared recovered engine and new server entrypoint.
5. **Directory.** Implement register, heartbeat, list and expiry against a
   provisioned provider. OpenSpy is a plausible GameSpy replacement, but no
   automatic new-game provisioning was verified. EOS is a free hosted candidate
   requiring a developer product/credentials/SDK. A self-hosted directory can be
   a fallback, but does not satisfy the requested free public default on its own.
   Verify public discoverability from another network before claiming success.
6. **In-game browser.** Add a real button to the recovered main menu and enter a
   game UI screen with server rows, selection highlight, sortable server/map/
   players/ping columns, a password lock icon, Internet/LAN choice, filters,
   refresh, direct connect, join and back. Use a restrained blue/translucent
   science-fiction visual treatment matching Halo CE PC's density and navigation.
   Implement loading, empty, timeout, incompatible-version, full-server and
   incorrect-password states. Route Join to the proven remote gameplay path.
7. **Release proof.** Build both Windows executables from a clean source checkout;
   record toolchain and artifact hashes. Run one headless server plus two clients,
   verify gameplay/joins/disconnects and the real main-menu browser, capture
   evidence, and measure unchanged recovered code with objdiff. Whole executable
   byte identity is not an acceptance criterion for newly added functionality.

## Directory metadata contract

Public metadata should contain a server identifier, display name, reachable game
endpoint, current and maximum player counts, module/map, gameplay mode, protocol
version, content/build identity and `passwordRequired`. Counts must come from
active authenticated game sessions rather than manually entered configuration.
The directory should expire stale servers and verify endpoint ownership before
listing; clients should measure their own ping and reject incompatible builds.

The actual join password, its reusable hash, and admin credentials must not be
published. The public password field is only a lock indicator. Password
verification belongs to the authenticated/encrypted game join exchange.

## Acceptance ledger

| Requirement | Current evidence |
|---|---|
| Locate engine/source artifacts | Observed; mixed recovery quality |
| Identify exact binary variants | Two distinct hashes recorded |
| Confirm internal transport | Fresh sender decompilation/disassembly; local memory queue |
| Full C/C++ engine link | Not established |
| Byte-accurate source build | Not established; historical partial receipts only |
| Dedicated headless simulation | Not implemented or demonstrated |
| Remote multi-client gameplay | Not implemented or demonstrated |
| Co-op shared story/dialogue progress | Not implemented or demonstrated |
| Persistent-world independent characters, sessions and progress | Not implemented or demonstrated |
| Public master registration | Not provisioned or tested |
| In-game Halo-style browser | Not implemented or demonstrated |
| Both requested executables | Not built |

No game files, running game processes, recovery jobs, or public services were
modified to manufacture a completion claim.

The first focused MCP sender export succeeded. A subsequent focused CreateServer
export stalled and its orchestration was terminated; no output from that call is
counted as evidence and its remaining queued exports were not run. NWN/NWN2
inspection encountered separate analysis-gate/timeouts documented above. No
shared MCP service was restarted and no existing recovery was interrupted.
