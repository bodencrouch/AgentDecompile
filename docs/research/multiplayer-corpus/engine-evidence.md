# the corpus engine evidence (read-only inspection, 2026-09-15)

## Outcome

Existing artifacts contain substantial function recovery work and a real internal client/server message boundary. They do **not** establish a standalone C/C++ engine build, a dedicated multiplayer server, or an existing remote transport. Copying these `.c` files into a project and naming an executable `swkotorserver.exe` would not deliver the requested game server.

No recovery jobs, builds, game processes, or source changes were made in this investigation. Historical receipt counts below were read, not freshly reproduced.

## Binary identity: two different inputs

| Path | Bytes | SHA256 |
|---|---:|---|
| `/home/brunner56/agentdecompile-nvme/k1gog-target/the corpus.exe` | 4395008 | `34e6d971c034222a417995d8e1e8fdd9f8781795c9c289bd86c499a439f34c88` |
| `/home/brunner56/agentdecompile-nvme/agentdecompile_projects/extract/raw/build_a__build_a_win_gog.exe` | 4042752 | `9c10e0450a6eeca417e036e3cde7474fed1f0a92aab018446d156944dea91435` |
| `/home/brunner56/agentdecompile-nvme/agentdecompile_projects/corpus_work/k1_gog_from_source.exe` | 4042752 | `9c10e0450a6eeca417e036e3cde7474fed1f0a92aab018446d156944dea91435` |
| `/home/brunner56/agentdecompile-nvme/agentdecompile_projects/corpus_work/build_a_win_gog_built.exe` | 4042752 | `9c10e0450a6eeca417e036e3cde7474fed1f0a92aab018446d156944dea91435` |

Both inputs have PE timestamp 1076609753 and identical `.data`/`.rsrc` section hashes. The first has an additional `.bind` section at RVA 0x46d000 and entry RVA 0x46d2ed. The corpus input has four sections and entry RVA 0x2fb38d. Their `.text` and `.rdata` hashes differ. This supports related builds/wrapping, not an exact receipt match. A directory called `k1gog-target` is insufficient provenance.

The first binary imports OPENGL32, KERNEL32, USER32, GDI32, ole32, binkw32, mss32, DINPUT8, GLU32, VERSION, IMM32. Its import table has no Winsock DLL. This alone does not rule out dynamically loaded networking, but the actual transport evidence below is local memory.

## Recovered source truth

Source directory: `/home/brunner56/agentdecompile-nvme/agentdecompile_projects/corpus_work/build_a_win_gog.exe/`.

It contains 24276 `.c` files plus a benchmark JSON and failure logs. No project build file or shared header exists directly in that directory. Files mix semantic candidates, compiled Ghidra output, and original-byte `_emit` assembly functions.

Adjacent `build_a_win_gog.exe.matching.json` and `.variants.json` report:

- 24242 code functions, 1956 byte-exact C, 16926 compiling-but-not-exact C, 5358 asm floor, 2 absent C; `receiptsPartial: true`.
- Byte-accurate variant: 1956 C + 22286 shims, 8.1% C.
- Maximum-C variant: 18882 C + 5360 shims, 77.9% C, explicitly not byte-identical.
- A separate `.byteexact.json` reports 2169 byteExact out of 24276. An older `k1gog_matching_manifest.json` reports only 98 exact. These are different snapshots and must not be combined into a fresh completion claim.
- `compile-receipt.json` lists 18094 successful entries but does not establish successful full-engine linking or runtime behavior.

`ProcessReceivedFrames_005d57d0.c` replaces the key application callback with `ghidra_call();`. `CNetLayer_005d54a0.c` contains generic `GhidraBlob`, surrogate types and recovered ABI declarations. These are useful analysis artifacts, not proof that the engine can be linked unchanged.

Repository `scripts/pe-code-roundtrip.py` explicitly copies the original PE and patches verified candidates (lines 162-163); lines 261-262 state that other bytes are carried from the original and are not semantic C/C++ recovery. Identical executable hashes are therefore not sufficient source-build proof.

## Actual internal transport evidence

All filenames below are relative to the source directory above; addresses apply to the 4042752-byte corpus binary unless independently verified elsewhere.

| Function | Address | Existing artifact |
|---|---|---|
| `CNetLayer` constructor | 0x005d54a0 | Ghidra C, explicitly not byte-verified |
| `SendMessageToPlayer` | 0x005d4cb0 | original-byte `_emit` substrate |
| `ProcessReceivedFrames` | 0x005d57d0 | Ghidra C with unresolved `ghidra_call()` dispatch |
| `StartConnectToSession` | 0x005d5040 | Ghidra C creating `BNCSU` messages |
| `StartServerMode` | 0x005d4fb0 | original-byte `_emit` substrate |
| `EndServerMode` | 0x005d5020 | small readable C with historical zero-diff claim |
| `CreateServer` | 0x00401380 | original-byte `_emit` substrate |
| `SendServerToPlayerMessage` | 0x00567e60 | original-byte `_emit` substrate |
| `SendPlayerToServerMessage` | 0x00677410 | Ghidra C, not byte-verified |
| `HandleBNCSMessage` | 0x005d5180 | original-byte `_emit` substrate |
| main-menu constructor/initialization candidates | 0x0067b500, 0x0067c4c0 | original-byte `_emit` substrate |

`CNetLayer` recovered layout has `message_frames[0x20000]`, offsets `frame_offset` at 0x20000, `frame_tail` at 0x20004, `base_exo_app` at 0x20008, `destination_net_layer` at 0x2000c, one `player_info` at 0x20014 and `server_mode` at 0x2003c. `GetPlayerInfo_005d5170.c` returns that one inline record. This suggests single-player assumptions that must be investigated for multi-client ownership.

Fresh disassembly of the corpus executable directly corroborates `SendMessageToPlayer`:

```asm
005d4ccb mov 0x2000c(%ebp),%eax    ; destination net layer
005d4cf1 mov 0x20004(%eax),%edx    ; destination queue tail
005d4f68 mov %edi,(%edx,%eax,1)    ; write payload length
005d4f73 lea 0x4(%edx,%eax,1),%edi ; payload destination
005d4f7c rep movsl
005d4f83 rep movsb
005d4f90 mov %ebx,0x20004(%eax)    ; publish new tail
```

`ProcessReceivedFrames` reads length-prefixed queue entries, routes `BN` control messages to `NonWindowMessages`, and dispatches other messages to client/server app handlers (annotated addresses 0x005ed790 and 0x004ae840). `StartConnectToSession` sends an internal `BNCSU` frame via the same local SendMessageToPlayer path. Names like StartConnectToSession and ServerMode do not demonstrate a remote session implementation.

## Smallest justified next slice

1. Bind one exact unwrapped executable hash and its analyzed database; do not mix the two inputs above.
2. Freshly decompile `SendMessageToPlayer`, `ProcessReceivedFrames`, `Initialize` 0x005d5550, `CreateServer`, and the main-menu event handler into an isolated output with fresh receipts. Existing files are investigation inputs only.
3. Recover and validate the message transport/dispatch boundary first, including queue wrap semantics, application callback ABI, and player identity. A narrow byte-proven C module is useful and honest; a standalone copied corpus is not.
4. Only after live dispatch is validated, a binary-integrated transport shim could carry real serialized game messages between two instances. That would be an experiment toward multiplayer, not source-engine recovery. Multi-player ownership, authority, pause/dialog policy, save transitions, headless initialization and dependency removal remain separate proof obligations.
5. An external server-list mockup or unrelated socket service is technically easy but does not satisfy an in-game browser and dedicated the corpus simulation. Do not present it as the requested product.

No live multi-client gameplay, headless server, in-game browser, original source recovery, or clean C/C++ full-image link was established by this inspection.

## Memory provenance used only to locate the artifacts

`/home/brunner56/.codex/memories/MEMORY.md` lines 585-586 identified the prior K1 GOG run and declaration-collision blocker. All binary hashes and source/receipt observations in this report were checked live. If citing memory in the parent response, include those lines; otherwise cite the current artifact evidence directly and disclose that this investigation used memory for navigation.

## Follow-up: exact native ABI and remote-boundary blockers

Fresh `objdump -d` inspection was run against the 4042752-byte raw corpus executable, SHA256 `9c10e0450a6eeca417e036e3cde7474fed1f0a92aab018446d156944dea91435`. Complete SendMessageToPlayer disassembly is saved at `/tmp/corpus-send-disasm.txt`; contexts for **all 26 direct calls discovered in the full executable disassembly** are saved at `/tmp/corpus-send-callers.txt`. Indirect calls were not exhaustively enumerated.

### SendMessageToPlayer has FOUR explicit stack arguments

Native x86 ABI: ECX is `this`, stack arguments are `playerId, payload, payloadLength, unusedFourth`, return value in EAX, callee cleanup `ret 0x10`. Proposed descriptive declaration (not a compiled artifact):

```cpp
int __thiscall CNetLayer::SendMessageToPlayer(
    unsigned long playerId, const char* payload,
    unsigned long payloadLength, unsigned long unusedFourth);
```

The exact semantic name/type of the fourth parameter is not established; do not assume it is a reliable-delivery flag. The K1 body does not read it. The call at 0x0067746a explicitly supplies zero; other excerpts push registers whose reaching definitions are not all included in the retained contexts. No claim that every caller passes zero is needed for the four-argument ABI finding. It likewise does not use playerId to select its destination: the queue destination is always the pointer at `this+0x2000c`.

Representative complete call setup in `SendPlayerToServerMessage`:

```asm
00677460 push 0          ; fourth argument
00677462 push edi        ; length
00677463 push esi        ; payload
00677464 push eax        ; destination player identifier
00677465 call [edx+0x10] ; GetNetLayer, no explicit arguments
00677468 mov ecx,eax     ; this = returned CNetLayer
0067746a call 0x005d4cb0
```

`StartConnectToSession` at 0x005d50dc similarly pushes zero, length, payload, zero before the call. Both send exit paths, 0x005d4cee and 0x005d4fa8, use `ret 0x10`.

The existing declaration `extern int __fastcall CNetLayer__SendMessageToPlayer(CNetLayer *, ulong, char *, int);` is doubly unsuitable for hooking/linking to this binary: it omits the fourth stack parameter and passes its second C argument in EDX. A fastcall hook adapter needs an explicit dummy EDX parameter **plus all four stack arguments**, yielding six C parameters total. Compile-only success cannot establish ABI correctness.

### ProcessReceivedFrames callback is recoverable, not an unknown magic function

Raw evidence: [receiver](evidence/receive-disassembly.txt), [server wrapper](evidence/server-handle-message-disassembly.txt), [server internal handler](evidence/server-internal-handle-message-disassembly.txt), and [client wrapper](evidence/client-handle-message-disassembly.txt). Each export records the input SHA256 and exact objdump command.

At 0x005d5841 the receiver loads `base_exo_app` from `this+0x20008` into ECX, loads its vtable, and invokes slot 1 (`[vtable+4]`). Setup is:

```asm
005d5849 push 0       ; fourth argument
005d584b push edx     ; payload length
005d584c push edi     ; payload pointer
005d584d push 0       ; playerId
005d584f call [eax+4]
```

Thus the callback ABI is `HandleMessage(appThis, playerId=0, payload, payloadLength, flagsOrMode=0)` with four explicit stack arguments. The server wrapper at 0x004ae840 loads the internal object from `this+4` and tail-jumps to 0x004b15d0. That handler explicitly reads argument 4 at entry `[esp+0x10]`, rejects nonzero, and returns `ret 0x10`. The client wrapper at 0x005ed790 similarly tail-jumps to 0x005ee700. The existing `ghidra_call()` discards recoverable argument and dispatch information; replacing it with an untyped zero-argument call would be incorrect.

For BN control messages the receiver calls 0x005d5690 (`NonWindowMessages`) using ECX=this and three stack args `(0,payload,length)`.

### Concrete assumptions that break when crossing a remote boundary

The [GetPlayerInfo export](evidence/player-info-disassembly.txt) establishes the single-record behavior. The [server internal handler export](evidence/server-internal-handle-message-disassembly.txt) shows the payload-byte reads and player/admin field checks. The [receiver export](evidence/receive-disassembly.txt) shows framing and callback argument handling.

1. **No sender identity survives the queue.** Send ignores its destination playerId; receive hardcodes sender 0. `GetPlayerInfo` at 0x005d5170 is exactly `lea eax,[ecx+0x20014]; ret 4`: it accepts and ignores one player argument, always returning the same inline record. A second connection cannot obtain separate identity/permission merely by substituting a TCP socket for the queue.
2. **Server privilege checks consult that shared record.** Handler 0x004b15d0 reads payload byte 0 before checking length. For `s` messages it tests inline player-info offset 0x24 (admin), for `p` it tests offset 0x1c (player). A remote bridge reusing the local record would need authenticated per-peer identity/authorization before these calls; changing the outer packet alone is insufficient.
3. **Receive trusts frame lengths and queue integrity.** It reads uint32 length at the queue cursor, advances by `length - (length & 3) + 8`, reads payload bytes 0 and 1 without checking the length, and loops until cursor equals tail. No checked arithmetic, remaining-frame validation, or malformed-cursor termination exists in this function.
4. **Send's capacity diagnostic is not a rejection.** The function compares calculated tail with read cursor +0x10000. If too large, it formats a diagnostic around 0x005d4f39, destroys the temporary string, and falls through at 0x005d4f5e into the same unchecked length write and `rep movs` copy. No maximum payload guard precedes that copy. A remotely supplied length must never enter this routine directly.
5. **Execution context remains local.** The queue has ordinary stores and direct virtual dispatch; no synchronization is visible in these functions. A network worker must not call them concurrently with engine update. Preserve engine-thread ownership with validated bounded handoff.

These observations give specific next implementation work: preserve the verified native ABI, recover the typed vtable callback, validate/bound messages before any engine queue operation, and replace the single shared player identity model before claiming multi-client support. They do not by themselves require rewriting the whole engine, but they prevent a safe/correct socket-only substitution.
