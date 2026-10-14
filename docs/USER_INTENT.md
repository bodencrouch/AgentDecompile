# AgentDecompile: user intent and product contract

This document consolidates direct user intent recovered from the local AI-conversation archive and current instructions. It resolves scope conflicts; it does not claim that every historical brainstorm was accepted or implemented.

## Active recovery directive (2026-10-10)

For the current recovery effort, operate through the checkout-pinned
`.venv/bin/agentdecompile-cli` and its corpus commands. The static dashboard on
8080 and the Vite frontend on 5174 are deferred and must not be used as recovery
surfaces until the user resumes frontend work. This execution choice does not
narrow AgentDecompile's product scope or remove either frontend from its future
design requirements.

The selected Ghidra project or shared-project repository is a valid source of
target program bytes and existing metadata. A detached executable is not a
prerequisite when the project's program image can be read and materialized;
bind extracted bytes to the exact program/build identity and preserve their
project provenance. Reuse existing Ghidra analysis, labels, types, debug/source
metadata and prior receipts where their evidence remains valid.

For functions without accepted matching C, retain an explicit architecture-
qualified `.S` assembly floor (or the target toolchain's equivalent assembly or
object representation where `.S` is not supported). Replace that floor only
after matching C is available and passes the relevant compile and comparison
gates. Code-cave work produces deterministic, build- and architecture-bound
candidate plans only where image identity, decode/exclusion, relocation,
capacity, ABI and runtime safety evidence supports them. Missing evidence must
fail closed; no universal or issue-free cave is promised for every function.

## Current user-directed product definition (2026-10-09)

This section records the user's latest correction and outranks older, narrower descriptions elsewhere in this document. AgentDecompile is a **higher-level reverse-engineering workbench built around Ghidra**: Ghidra and other analysis engines supply powerful low-level analysis; AgentDecompile coordinates that evidence across related builds, recovers C/C++ that can be compiled to match the real binaries, and turns the resulting code, data, types, ABI and runtime knowledge into an actionable workspace. It must go well beyond exposing a decompiler pane or MCP wrapper. “Higher level” describes the product and workflow built on those engines; it does not claim that AgentDecompile replaces Ghidra's analysis engine or that every capability works on every target.

The central working model is a **family of concrete binaries treated together as one evolving codebase**, never as one fictitious merged executable. Each build retains its own addresses, bytes, ABI, layouts, behavior, evidence and gaps. The product links logical functions, data, types, call sites and runtime events across builds, shows where they correspond or diverge, and lets a useful recovery or discovery in one build inform the others without silently transferring an unsafe address or assumption.

The primary recovery output is readable C whose fresh compile can reproduce the target bytes. “Matching C” means source whose compiled machine code matches the selected function or image—not a claim that the historical authored source text has been uniquely reconstructed. C++ reconstruction is conditional: pursue it only when source/build/debug evidence supports recovering the original C++ form and a bounded feasibility check shows that this form can produce the matching C/object bytes. If the authored C++ form is underdetermined or physically unrecoverable from available evidence, do not fabricate C++ merely to fit target bytes; stop that lane and prioritize readable C plus the explicit assembly/original-byte floor. A byte-matching C++ hypothesis is not original-source recovery. Keep byte-accurate source plus its floor, max-C readable source, and their proof receipts distinct. The workbench also needs to expose the recovered program as something people can understand and act on: callable functions, events and callbacks; argument/parameter locations and types; returns, state and memory; graphics/GL behavior where present; and build-specific identity and ABI facts.

Those facts power first-class runtime-research and modding workflows inside AgentDecompile: inspect live behavior; prepare supported Lua integrations, native shims or DLLs; resolve and call existing functions; plan hooks, detours and code caves; and inspect or modify supported memory and event arguments/parameters. Every proposed action stays tied to the exact binary/build, prototype, storage, runtime and permission evidence. Discovering or observing an operation is distinct from being able to call, hook or modify it; unsupported, ambiguous or unsafe cases must be visible and refuse cleanly. These workflows share the corpus with source recovery, but runtime behavior is not source equivalence and never substitutes for byte proof.

WebAssembly and graphics APIs are part of this higher-level capability surface where the concrete operation can run there: browser-local analysis, comparison, interactive visualization, suitable emulation or other specifically supported work. Target-side graphics/GL inspection and browser-side rendering of analysis are different claims and must not be conflated. Lua and native C/C++ adapters are ways to consume the same evidence-backed operations, not separate authorities. AI can operate the tools and propose names, source or repairs; deterministic observations, compilers and comparisons establish claims. The user's intent is maximum useful capability with the least repeated reverse-engineering work, while preserving these evidence boundaries.

## Purpose, in input/output terms

AgentDecompile takes related compiled binaries and their existing analysis as input, builds an evidence-backed model of what each release shares and how it differs, and produces matching source plus practical analysis/runtime-modification outputs. It is not an AI asked to guess source from pseudocode. A model is optional; a model's confidence is never proof.

## Expected inputs and outputs

| | Contract |
|---|---|
| **Inputs** | Each actual executable or supported binary, available either as a detached file or from its related Ghidra project/shared-project implementation; existing analysis; optional symbols/debug data, source/build/toolchain fragments and prior receipts; and, for runtime workflows, an explicitly selected and supported process/build. A multi-binary project is one family of real targets, not one fictitious merged executable. |
| **Shared program model** | Per-build functions, data, types, memory/layout, signatures, names, call/event relationships, argument/parameter storage, returns, ABI facts, graphics/GL observations where supported, identity links, provenance, ambiguity and divergence. Reused evidence keeps its origin and is revalidated against the relevant binary, process and toolchain identity. |
| **Useful partial outputs** | Navigable analysis, cross-match candidates, readable C/C++, compilable candidates, diagnostics, and explicit unresolved/unsupported outcomes. These are useful progress, but are not whole-target completion. |
| **Recovery outputs** | Per-target matching C/C++; separate byte-accurate source plus an explicitly counted assembly/original-byte floor and a max-C readable variant. Keep source manifests, compiler results, and receipts separate. |
| **Runtime/modding outputs** | Where the selected target supports them: inspectable function/event/callback catalogs; typed arguments, parameters, returns and state; portable locators and divergence; Lua/native shim/DLL bindings; and preflighted call, hook, detour, code-cave candidate or memory-change plans with observable activation, failure and undo state. Each artifact carries its concrete build, ABI and evidence basis; cave plans fail closed when required evidence is missing. |
| **Completion proof** | A fresh build of the current source and a full-image comparison with zero differing bytes for each target claimed complete. Function-slice matches, matching C presence, a successful compile, a cached/historical receipt, a copied byte range, or an assembly floor do not establish this claim. |

### Runtime workflow and evidence states

The runtime path begins with a concrete binary/build and eligible process, then
discovers the widest supportable set of functions, call sites, events/callbacks,
arguments, parameters, returns, state and memory regions. Each observation should
show its type, storage/location, mutability, capture method and confidence; the
catalog must expose coverage and explicit unsupported/ambiguous cases instead of
implying that its current list is exhaustive. A requested change is authored as a
Lua/native shim or DLL, call/hook/cave/memory plan, or supported WASM/graphics
operation; it is bound to the selected build and inspected before execution.

The common path is **discover → inspect → stage → preflight → activate → observe
→ disable or undo → retain provenance**. Show real operations and resulting state,
not a generic running indicator. Keep states distinct: discovered, eligible,
prepared, active, observed, disabled/rolled back, failed, ambiguous, unsupported
or refused. Runtime observations may enrich shared identity, ABI, type and
behavior evidence, but they do not authorize an unrelated target, silently change
another build's source, or establish source/whole-image parity.

The current BioWare recovery sequence starts with K1 GOG, then K2 Aspyr, while importing and analyzing the other available BioWare binaries/projects so cross-matching can inform the pilot and siblings. That is a starting order, not a permanent product limit. A later multi-platform study of another game family is a separate expansion after the BioWare corpus is made useful and measurable.

## Core pipeline and feedback

```text
binary family + existing analysis
        ↓
identify targets and reuse valid state (P0)
        ↓
inventory each build ── calibrate compiler / ABI / layout
        ↓                         ↕
cross-match functions, data, types, names, and signatures
        ↓
generate/recover readable source and keep an explicit build floor
        ↓
compile → compare with objdiff → classify the actual mismatch
        ↓                                      ↘
propagate only compatible candidates       repair / re-match / defer
        ↓
fresh full-image build + zero-difference receipt per completed target

cross-build identities + ABI + event/memory evidence
        ↓
runtime inspection → Lua/native adapter or shim → call/hook/cave/memory plan
        ↓
target-bound preflight → observe/disable/undo → provenance-bearing feedback
```

Cross-matching is the center of the multi-binary workflow, not a late optional report. It should run as soon as the required inventories and identities exist, feed source recovery, and continue as new evidence arrives. Identity is not proof that two implementations are interchangeable: retain ambiguity, absence, inlining, ABI/layout differences, and per-build divergences.

### P0: safe continuity, not a global gate

P0 answers only: what project/target is selected, what durable work already exists, what is actually running, and which resource would be mutated next? Reuse only evidence whose target, source, dependency, and toolchain identity still match. Resume compatible jobs; invalidate only affected descendants; never overwrite or duplicate an active writer. An unrelated stale item or unavailable tool must not prevent independent eligible P1–P9 work. P0 must be a short shared ownership/resume mechanism—not a second preparation pipeline, a full corpus rescan on every click, or a requirement to repair every project before useful work can start.

The user separately refers to product priorities 1–9. The numbered recovery stages
in STRATEGY.md are a dependency sequence, not a complete transcription of that
product-priority map; do not infer that priority 9 does not exist or that one
numeric sequence can replace the other. Keep P0 small and allow the main mission
to proceed. The original detailed P1–P9 definitions were not recoverable as a
deduplicated, direct-user list from this archive snapshot, so this document does
not fabricate a mapping.

The dashboard’s ordinary browse/select behavior is read-only. One project-scoped start/pause/resume/stop control governs pipeline work; individual automatic stages are not presented as competing start buttons. The UI should animate the real operation/evidence being produced and show the target and failure state, not substitute spinners or aggregate counts for task detail.

## Concurrency and failover

Parallelize independent work, not shared mutable state:

- **Can overlap:** read-only inventory across binaries; cross-match of independent target pairs; compiler calibration; source recovery for independent translation units; isolated compile/objdiff shards; evidence review and dashboard rendering. They exchange versioned evidence and local receipts.
- **Must serialize or lease:** writes to the same Ghidra project/corpus rows; mutation of the same function/translation unit; a shared mutable compiler/PDB/temp or Wine environment; final materialization/selection of a replacement. One writer owns each mutable project/resource at a time.
- **Admit work by actual resources:** memory, CPU, swap, disk, compiler/runtime ownership, and Ghidra writer state. Worker count is not a success metric. More workers are wrong when contention reduces accepted recovery throughput or threatens the host.

On a stage failure, keep the last valid evidence and report the exact failed operation. Continue independent branches. Use this order where applicable: reuse a valid receipt → deterministic/local method → alternate supported analysis method → isolate and retry a diagnosed transient failure → bounded model assistance for a concrete residue → named defer/blocker. A failed provider, model, Ghidra connection, or worker does not justify fake success, duplicate work, wiping state, or lowering the proof bar. The dashboard must make the next actionable fallback visible and resume from durable checkpoints.

## Analysis engines, WASM/graphics, and runtime integration

- **AI/agents:** Agents make the powerful tool surface usable and can propose source/repairs. The deterministic pipeline must still work without model availability. Candidate generation can be AI-assisted; acceptance is external compile/comparison evidence.
- **Ghidra and other analyzers:** They provide analysis engines and evidence. AgentDecompile is the higher-level system that coordinates those engines across a binary family, preserves shared identity/provenance, drives matching-source recovery, and exposes analysis and intervention workflows. Reuse loaded projects and analysis; do not rebuild a parallel analyzer merely to claim a higher-level product.
- **WASM and graphics:** Treat browser-executable analysis, comparison, visualization, and suitable emulation as first-class implementation options, not as a decorative add-on. Name the exact operation, consumer and target it supports. The latest user prompt says “GL” without expanding the acronym; context suggests target-side graphics instrumentation, but this is an inference. Preserve that as a requested graphics area and distinguish target graphics observations from browser-side rendering; do not claim a specific API/provider from the acronym alone. WASM does not automatically host Ghidra's JVM, native MSVC, or arbitrary process injection, and neither WebAssembly nor graphics visualization establishes source parity or whole-image proof.
- **Lua and native runtime adapters:** They are first-class interfaces for supported calls, events and modifications. Use target-specific ABI, argument storage, memory, thread/lifetime, permission and preflight evidence. KotorPhasor is an important implementation/reference consumer and source of prototype behavior, not a boundary that relegates these workflows outside AgentDecompile. Runtime traces and successful hooks feed provenance-bearing observations back into the shared corpus; they remain separate from recovered-source and byte-parity claims.
- **Merged engine / patch manager:** They may consume recovered source and cross-match/runtime artifacts, but they are not substitutes for AgentDecompile's own high-level discovery, analysis and evidence-backed operation surface.

## Authority and conflict resolution

For current work, apply this order:

1. The user’s latest direct instruction in the active conversation.
2. Repeated, direct user intent corroborated across conversations, deduplicated by authored request rather than export count.
3. This document’s input/output and proof contract, then [STRATEGY.md](../STRATEGY.md) for the current pipeline and acceptance.
4. [AGENTS.md](../AGENTS.md) for operational/safety rules; task-specific product requirements and current measured status.
5. [VISION.md](../VISION.md) and [METHODOLOGY.md](../METHODOLOGY.md) for durable principles.
6. Historical brainstorms, design plans, copied prompts, screenshots, assistant summaries, and old progress marks as evidence only. They become binding only when a direct user instruction adopted them and they have not been superseded.

When a historical proposal conflicts with a later direct instruction, keep it as history and mark the supersession; do not silently delete it or let it redefine the current product. Treat every AgentDecompile-related message as design evidence, regardless of speaker, platform, format, or whether it looks like a polished prompt. For Discord in particular, relevance is message-level: include related messages even when they are standalone, routine bot posts, status updates, or not part of a genuine assistant turn-taking exchange. Preserve surrounding thread context where available, because mundane exchanges can expose workflow, assumptions, and failure modes. Use context to establish project relevance, not author identity or conversational form, as a filter. Keep attribution precise: peer and bot messages can illuminate design intent and evolution, but only a direct user instruction—or a proposal the user explicitly adopts—counts as the user's requirement.

## Archive evidence and limits

The NVMe-only archive snapshot used for this consolidation is `research/agentdecompile-intent-archive-snapshot-20261009` under `/home/brunner56/agentdecompile-nvme`. Its SHA-256 manifest verified. The parsed snapshot contains 19,926 JSONL records/lines across 52 conversation files; the archive stamp’s 20,005-record claim is stale by 79. Dense local retrieval selected 73,797 non-empty self-authored turns across 14 AI-chat platform partitions; 180 audio transcript segments are separate, not AI prompts. The full pass produced 2,888 unique candidate turns (100 per each of 16 broad categories, with overlap); a domain-targeted set held 473 rows but only 243 exact text bodies. Literal-term discovery found 3,142 candidate rows and 2,079 distinct bodies. The Discord supplement scanned all 353 conversation records and 1,516,243 archived messages for exact AgentDecompile/KOTORPhasor terms. It found 180 owner-authored matching turns in 27 conversations (171 normalized bodies); these are exact-term retrieval counts, not the number of relevant exchanges or requirements. Those 27 source conversations contain 95,659 messages and 57,704 owner-authored turns. A peer-context review of all 27 records identified additional project-relevant discussion that the self-authored hit count does not represent; examples are cited below. Treat every AgentDecompile-related Discord message as evidence, and preserve available surrounding conversation context—including routine bot posts and status updates; author role is provenance, never a relevance filter. A semantic ranking pass on Discord previously covered only five selected conversations; a later attempt to expand it across all 353 records was terminated at 71 records and 1,609 owner turns. It is incomplete and must not be cited as full-corpus semantic coverage. The direct-term set and reviewed contexts are evidence, not a claim that every implicit Discord reference has been found. Across sources, these are retrieval counts, not requirements: rank precision was poor, duplicate exports were common, and the automatic quote/paste flag missed obvious embedded prompts. An independent reviewer checked authorship, source, chronology, scope and context before synthesis. Semantic ranks and lexical matches are discovery aids, never proof of relevance.

The most direct archived scope statement is the five-binary plan below. The short table gives stable snapshot locators; paths are relative to the verified archive snapshot. Discord and other non-AI platforms remain separate source partitions for provenance and retrieval, but their AgentDecompile-related evidence belongs in the same design synthesis as AI-platform conversations:

| Intent | Source locator |
|---|---|
| K1 GOG first, then K2 Aspyr; recover C/C++ across five KOTOR binaries; import Ghidra labels/types; cross-match functions, instructions, and STABS | Cursor conversation `urn:upar:conversation:34d6134bbf1c37a6add2b88d0dbe7d7e`, message `decf8d3b-3b28-4c0f-971b-bda4f96c1b69`, `archive/corpus/records/kind=conversation/platform=cursor/part-00007.jsonl:56` (2026-08-22). Duplicate/expanded copies were deduplicated, not counted as separate votes. |
| Prefer 90% recovery proof and especially whole-binary parity over bounded source-slice claims | Codex conversation `urn:upar:conversation:89739df67cc65da92a7ae291799e97bd`, message `019e9a6d-7086-7d43-adb4-5816f970ab03:386`, `archive/corpus/records/kind=conversation/platform=codex/part-00002.jsonl:1` (2026-07-06). Later current instructions raise the completion bar to fresh full-image zero-difference proof. |
| Automatically recover C/C++ from arbitrary binaries rather than manually writing source as the core workflow | Codex conversation `urn:upar:conversation:106c66270342c0e130b285680628d3bc`, message `rollout-2026-06-05T19-55-24-019e9a6d-7086-7d43-adb4-5816f970ab03:19134`, `archive/corpus/records/kind=conversation/platform=codex/part-00001.jsonl:31` (2026-06-29). Treat arbitrary binaries as the horizon; the BioWare family is the active corpus priority. |
| Use AgentDecompile/Ghidra rather than a new custom Java extension for every workflow | Codex conversation `urn:upar:conversation:89739df67cc65da92a7ae291799e97bd`, message `019e9a6d-7086-7d43-adb4-5816f970ab03:184–185`, `archive/corpus/records/kind=conversation/platform=codex/part-00002.jsonl:1` (2026-06-29). |
| Deterministic workflow, multi-binary cross-match, and readable/signature outputs; AI creates/operates the workflow but is not required to use it | Discord conversation `urn:upar:conversation:9ad42c74f3f2e99c3f5898fce898560b`, messages `1551756296582078575`, `1551758306635415725`, and `1555452205186809938`, in `archive/corpus/records/kind=conversation/platform=discord/part-00009.jsonl:67` (2026-09-22 to 2026-10-02). |
| Agent-facing Ghidra MCP, guided multi-path workflow, and design concerns | Discord conversation `urn:upar:conversation:cd3e3ac6711c7012afc7e5534331d41f`, message `1468199495065014323`, `archive/corpus/records/kind=conversation/platform=discord/part-00001.jsonl:102` (2026-02-03); plus the record-level review of all 27 exact-hit Discord conversations. |
| Peer feedback exposed entry-point and workflow failures: patch discovery could miss intended targets and break existing patches; peers asked for broader Ghidra, binary-matching, and patching capability. The user's reply asked for full functionality inside AgentDecompile's tools, adopting the capability-coverage concern. | Discord conversation `urn:upar:conversation:0838daf05bb3d775326b6d2a9f941b97`, messages `1471759218272112926`, `1471760716603199498`, and user reply `1471761232309518452`, `archive/corpus/records/kind=conversation/platform=discord/part-00009.jsonl:23`. Peer reports are evidence of observed failure modes; the user's reply is the adoption signal. |
| A peer explicitly distinguished analysis-quality pseudocode from output precise enough for recompilation. The user's early reply that C/C++ was premature applied to a traversal-efficacy pilot; later recovery instructions supersede that phase-specific sequencing. | Discord conversation `urn:upar:conversation:0c2f12f56fa7d0e0ef0a9efb2dfcaa80`, messages `1477753919324033185` and `1477754504064532722`, `archive/corpus/records/kind=conversation/platform=discord/part-00009.jsonl:35`. |
| Peer feedback that the AI-assisted tool found some missed material while remaining imperfect supports useful discovery, not correctness proof; a separate peer warned that fast AI output can invite rubber-stamping. | Discord conversation `urn:upar:conversation:6fcb7982cb7f868a0d0eecf433cf39a8`, messages `1469964336251404455` and `1470125091214856355`, `archive/corpus/records/kind=conversation/platform=discord/part-00002.jsonl:3`; and conversation `urn:upar:conversation:cd3e3ac6711c7012afc7e5534331d41f`, message `1468199458364854342`, `archive/corpus/records/kind=conversation/platform=discord/part-00001.jsonl:102`. These are peer observations, not independent acceptance requirements. |
| Peer discussion notes that compiler optimization can merge duplicate functions/constants and erase source-level intent; this is a limitation to expose when interpreting cross-matches and recovery results, not a reason to weaken byte-level proof. | Discord conversation `urn:upar:conversation:d3e5db3420c76d0819715f7039405338`, messages `1544064285276381255` and `1544066517367525377`, `archive/corpus/records/kind=conversation/platform=discord/part-00009.jsonl:38`. |
| Any AgentDecompile-related Discord message is design-context evidence, including human-peer and assistant/bot posts, standalone status updates, routine messages, and corrections/outcomes; retain available original context without misattributing non-user statements as user requirements | Current exact-hit set: `/home/brunner56/agentdecompile-nvme/research/agentdecompile-intent-archive-snapshot-20261009/retrieval-results/semantic-int8-complete-20261009-v2/discord-supplement/discord_all_exact_record_exact_candidates.jsonl`; source conversations are identified by `record_path` and `record_line` in the verified NVMe snapshot. This exact-hit set is not a complete contextual/semantic corpus. |

The archived conversation set does not establish an earlier requirement that WASM replace Ghidra or perform all recovery in the browser. That historical limit does not constrain the broader, later user direction recorded at the start of this document: AgentDecompile must be a higher-level system and should use WASM/graphics capabilities wherever the concrete operation supports them. Discord evidence retrieval remains incomplete: the unfinished semantic pass and exact-term candidate set are discovery aids, not grounds to exclude other AgentDecompile-related messages or routine bot posts. Continue by classifying relevant messages across the full Discord archive and preserving provenance/context; do not limit the corpus to assistant-style exchanges.
