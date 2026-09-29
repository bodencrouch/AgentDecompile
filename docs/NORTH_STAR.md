# AgentDecompile: North Star

Read this first. It ranks above every plan, ledger and design note in this repository. If a plan disagrees with this page, the plan is wrong. `AGENTS.md` still governs how you operate. This page governs what you build and why.

## 1. The product

**Drop in every build of a program. Get back one program: source that rebuilds each build byte for byte, a Lua API over every function and event that survives every patch, and the whole program playing in a browser tab.**

*Machine-made. Byte-proven.*

- Drop in anything: builds, patches, installers, archives, notes, dumps. There is no Start button.
- The machine does the reverse engineering a human would do by hand, across the whole program and every version.
- You get products, not a database: source, signatures, a Lua bridge, headers, a browser build, and the proof behind each.

## 2. What AgentDecompile is

AgentDecompile is a reverse build system: shipped binaries go in, and a buildable, scriptable, portable program comes out. Ghidra hands a human raw analysis and makes the human the inference engine. AgentDecompile is the inference engine. The analysis is not the product. The exports are.

Five words define it.

- **Whole-program.** The unit of success is the program, not the function. "Done" means the shipped file rebuilds byte for byte from readable source, and every function, struct, global, string and vtable is located without an absolute address.
- **Corpus-first.** Several builds of one program are one program. Windows, Mac and console builds, old and new patches, and storefront variants form one corpus. More builds means more evidence, not more work: what one build hides, another reveals.
- **Autonomous.** It flows on its own from upload to exports. Deterministic machinery does the bulk. AI agents take only the measured leftovers and drive the machine over MCP. Humans override afterwards and never gate progress.
- **Byte-proven.** A result counts when a hash says so. "Compiles", "passes tests" and "looks right" do not count. That is what lets it run unattended and be trusted.
- **Visual.** You watch the program being understood. Pictures carry the meaning; words live in tooltips. If a result cannot be seen within one click, it has not reached the user.

The user's TL;DR, in their own words:

> "treat ghidra high level decomp analysis as mid, be a perfectionist and achieve everything humans would typically have to manually do as standard reverse engineering procedures e.g. following pointers observing call graphs binary similarity etc. Achieve the actual high level, that just functions and flows on its own based on whatever you upload into the project."

And on presentation:

> "the text is fine but they should almost exclusively only be tooltips for explanation of what the user is seeing. Which should be predominantly provided as visual ui. Image says a thousand words."

## 3. What the user considers too obvious to say

**You upload; it does the rest.** Opening a project or adding a file starts all eligible work. Reopening known material redoes nothing that already has a valid result.

**The program is the unit.** Per-function scores are internal gauges. The headline is how much of the program is recovered, portable, scriptable and playable.

**Every output falls out of understanding.** Once code is recovered and every entity is located by signature, the Lua API, headers, port and multiplayer research follow from it. They are not separate projects with separate plans.

**Versions are one thing.** A mod written once runs on every build the corpus knows, and on builds that did not exist when it was written.

**Addresses are a cache.** Every absolute address is replaced by a signature or a relationship. A script never contains a literal address.

**The machine is the reverse engineer.** Pointer chains, call graphs, cross-references, similarity, struct and vtable recovery, version diffs, live tracing and compiler identification all run automatically, exhaustively and deterministically.

**Ghidra is the floor, not the ceiling.** Code Browser functionality is table stakes. It lives in the drill-down. It is never the home screen.

**Byte identity is the judge.** A result counts when bytes or a hash say so. That makes every claim checkable and lets the machine run unattended.

**Generic by construction.** Any program, format, architecture or engine. Product specifics live in data packs and fixtures, never in code, defaults or docs.

**Watching it should be thrilling.** The screen shows the program being taken apart and put back together.

**Honesty is structural, not verbal.** A solid bar segment, a hash row, a frame style or a glyph carries the truth. Disclaimers in every panel are a defect.

## 4. The products it hands back

The user named four products outright: rows 1–4, the headline. "And like 8 other things" is rows 5–12: the rest of the unattended one-shot list (export bundle, readiness and divergence reports, learn-the-build, headers, codecaves and ABI) plus the editor, multiplayer and native ports. Rows 13–16 are the platform underneath.

Status is one word. **done**: works today at its stated scope. **partial**: real pieces exist, not end to end. **next**: in build-order steps 1–4 below. **future**: designed or requested, not built.

| # | Product | What the user gets | Why it matters | Nearest analog and its human cost | Status | Source |
|---|---|---|---|---|---|---|
| 1 | Byte-accurate source | Readable C/C++ for the whole program that rebuilds each shipped build to an identical hash; a C+assembly-floor variant and a max-C variant, measured separately | The strongest possible claim of understanding; the base of every port | Community matching decompilations: 18 months and 1,500+ hours for one PC game, then 808 costed fixes to reach whole-image identity; console games took 21 months to 6 years | partial | STRATEGY.md:208-214; docs/PROTOTYPE_OUTCOMES.md:19 |
| 2 | Runtime scripting bridge (Lua over DLL injection) | Inject into the running original; every function and event is hookable and callable from Lua by name | Modding without a decade of hand-built extender work | Hand-built script extenders: 10+ years and several core authors per game; our own 2015 ancestor had ~122 hand-found signatures, ~35 hand-written caves, ~80 functions and ~26 events for two builds | partial | docs/RUNTIME_REUSE.md:36-38; docs/research/2026-09-29-exports-and-outputs-inventory.md:80; donor source survey (session notes, not committed) |
| 3 | Portable signatures | Every entity located on every build by signature, relationship or anchor; no absolute addresses anywhere | Mods and tools stop breaking on every patch | Hand-curated address-ID databases: one maintainer, split per edition because builds were "too different to match"; each compiler change cost the community weeks | partial | docs/research/2026-09-29-exports-and-outputs-inventory.md:78-79 |
| 4 | Browser build (WASM) | The whole program running in a browser tab from your own copy; first via emulation, then from recovered source; proven faithful by replay | Preservation and distribution with zero install | Static recompilers where each port is "its own project"; hand reimplementations 12 to 18 years in | future | docs/RUNTIME_REUSE.md:155-163 |
| 5 | Export bundle | One deterministic, content-addressed tree holding everything below | The single artifact every workflow consumes | None; every piece is hand-assembled today | next | STRATEGY.md:39-42 |
| 6 | Readiness and divergence reports | Entity × build grid of what you can do on each build; a 3-way classification of what changed between builds | The first thing a user reads; patch-day answers in minutes | Startup logs and hash checkers that print misses; pairwise differs with a manual Accept per match | next | docs/research/2026-09-29-exports-and-outputs-inventory.md:82-83 |
| 7 | Learn-the-build | Compiler, version, flags, ABI and link order identified and reproduced | Byte identity is impossible without the era-correct toolchain | Toolchains prescribed by hand in community READMEs; one compiler switch reset years of extender work | next | STRATEGY.md:198 |
| 8 | Headers and SDK | Per-build C/C++ headers with exact layouts, prototypes, vtable enums and size asserts | Native mods and tools compile against the real program | Hand-maintained community header libraries | partial | docs/research/2026-09-29-exports-and-outputs-inventory.md:81 |
| 9 | Codecaves and ABI | Signature-anchored cave plans and per-site calling contracts, ready for Lua | Safe injection without hand-written assembly | Naked-assembly caves written by hand per event | future | docs/plans/2026-09-21-user-requirements-ledger.md:87-89 |
| 10 | Live F12 editor and playback | In-game inspector: pick an object, edit a field, run Lua, undo, copy as Lua; owned pause, save, restore, branch replay, and saved scenes and captures that reopen in a fresh session | See and change the running program by name | Managed-engine inspectors that work only when names survive; memory scanners plus guesswork | future | docs/plans/2026-09-22-autonomous-capability-product-roadmap.md:146-148 |
| 11 | Multiplayer | Source-built client and server, in-game server browser, lobby; per-build state maps and sync candidates | Networked play for single-player classics | Co-op mods: three years from reboot to 1.0, one build only | future | docs/PROTOTYPE_OUTCOMES.md:23 |
| 12 | Native platform ports | The recovered program on Windows, Linux and Mac, with a generated subsystem-substitution checklist | Runs anywhere, not only where it shipped | Hand ports built on a finished decompilation | future | docs/plans/2026-09-22-autonomous-capability-product-roadmap.md:149 |
| 13 | Agent MCP server | 77 tools (73 advertised) over live analysis that any agent can drive, plus an advisory context export | Any agent becomes a competent reverse engineer | Vendor and community disassembler bridges; the agent still does manual RE | done | TOOLS_LIST.md:3 |
| 14 | Context fusion (v1, bounded) | Notes, dumps and archives placed by address as advisory puzzle pieces; label proposals never auto-applied | Prior human work is reused, not retyped | Hand-merging notes into a database | done | docs/CONTEXT_FUSION.md:9-55 |
| 15 | Managed-engine project reconstruction | A shipped managed-runtime game turned back into an editable engine project | The same promise for games that are not native code | Running asset extractors and IL decompilers by hand, then repairing the project | future | docs/research/2026-09-29-exports-and-outputs-inventory.md:137 (E14, "reference") |
| 16 | Distributed compute | A local grid-of-one runs; idle machines and cloud nodes via one join command are planned | Community scale instead of one workstation | Volunteer grids that show a percentage, not the work | partial | docs/plans/2026-09-21-distributed-compute-design.md:447-474 |

## 4b. Proof demos

Every headline claim needs a demo someone can watch. Each maps to a product row.

| Demo | What is seen | Row | Status |
|---|---|---|---|
| Ancestor regenerated | The 2015 ancestor's ~122 signatures, ~35 caves, ~80 functions and ~26 events regenerated for build-a…build-d, side by side with the hand-written originals | 2, 3 | next |
| One mod, four builds | Split screen: the same `.lua` runs on build-a and build-d; a resolved-count strip per build (n/n) | 2, 3 | next |
| Patch day | Upload build-d; the readiness board fills in minutes; the divergence treemap ranks what changed | 6 | next |
| Siblings converge | Builds b…d climb toward build-a's curve in hours, beside the ~50%-for-years baseline | 1, 3 | partial |
| Hash row | SHA-256 original = rebuilt, one row per build, with the toolchain chip | 1, 7 | future |
| Play in a tab | The original in a browser tab, a replay-verified badge, a "recovered C share" meter rising | 4 | future |
| Day-one interop | The signature pack exported as address-ID databases and common debugger and scanner patterns | 3 | future |
| Deterministic scale | The hook pack re-exports 74,205 sites byte-identically in 122-200 s | 5 | done |

## 5. Ghidra is mid

A human in Ghidra performs dozens of procedures by hand, one program at a time. AgentDecompile performs them across every build, records the evidence, and draws the result. Now: status today.

| What a human does by hand | What AgentDecompile does instead | What the user sees | Now |
|---|---|---|---|
| Follows a pointer chain hop by hop | Derives chains from p-code, verifies each hop on every build | PointerWalk: base → deref → field, one offset cell per build | future |
| Pointer-scans and asks "what writes this address" in a memory scanner | Injected host counts live field accesses and binds them to recovered structs on every build | "Who writes this" counters on live typed rows | future |
| Maps the embedded script engine's native-call table by hand | Decodes the dispatch table and binds every native action to a Lua name | Action catalogue, one dot per build | partial |
| Steps in a debugger to learn what a function does | Records calls and arguments from the running original and attaches them to the function | Call-trace lanes beside the listing | future |
| Walks call graphs and cross-references | Reads callers, callees and refs from live analysis over MCP; corpus-wide neighbourhood view planned | Neighbourhood graph, status ring per node, hatched where absent | partial |
| Runs binary similarity (BSim) | Fuses symbols, hashes, strings, call graph, CFG and similarity; accepts only unique matches with a margin | Similarity galaxy; a match ripples to near-duplicates in every build | partial |
| Tracks versions pairwise and clicks Accept | Matches N builds at once; compile gating replaces the click | Builds × entities matrix; a landed match pulses across the row | partial |
| Recovers struct layouts by reading accessors | Decodes accessors and constructors, then checks the layout against every access site | Struct offset drift grid: same, moved, missing per build | future |
| Reconstructs vtables by hand | Maps slots to logical methods by identity; decodes constructor vtable stores | VTableBrowser: slots × builds, reorders drawn | future |
| Hunts globals and data roots | Ordered locator family per root: symbol, xref, anchor, masked window, pointer chain | Readiness board cell per root × build | future |
| Greps strings and constants | Reads strings, constants and imports over MCP; indexing them as identity channels is planned | Hits painted on the byte map and the graph | partial |
| Makes a sigscan signature (wildcard, grow until unique) | Derives unique 8-24 byte windows today; operand+reloc masking with cross-build uniqueness is planned | Signature card: masked bytes, one match-count dot per build | partial |
| Diffs two versions of a patch | Classifies each entity: 1↔1, split or inlined, diverged; never forces a match | Per-build diff treemap; divergence timeline | next |
| Guesses the compiler and flags | Reads toolchain evidence, calibrates against known library code | Toolchain chip on every claim; a short compiler story timeline | next |
| Recognizes optimizer idioms | Tags inlining, folding, stack cookies, switch tables, magic division | CompilerLayer gutter tags beside the listing | future |
| Identifies library functions | Matches library code and removes it from uniqueness | Provenance swatch per function row | future |
| Renames and retypes, then re-does it on the next build | Edits one build, propagates per field to compatible siblings with provenance | Name-provenance ladder; a field flowing donor → recipient | partial |
| Decompiles, fixes, compiles, diffs, tweaks | Deterministic repair first, one bounded AI attempt, permuter, cheap before expensive | Attempt tape: diff lines flip red → green, score pill falls | partial |
| Relinks and hashes the whole image | Exact-placement link, whole-file hash, delta localized to the owning function | Image delta map; the certificate when the hash matches | future |
| Writes hooks and trampolines | Detours with instruction relocation and rollback; detourability decided at export | Hook browser with live fire-rate sparklines | partial |
| Calls a function with the right ABI | Typed adapters from recovered calling contracts; low-confidence ABIs refused | Typed call stub with its contract drawn | partial |
| Finds code caves | Validated caves as anchored plans with capacity and restore | Cave map on the byte band | future |
| Checks which build is running | Identifies by image hash; unknown builds admitted signature-only | Identity chip on drop | future |
| Decides what to do next | Admits eligible missing work automatically; skips anything with a valid result | Stage strip with live counts; no buttons | partial |

## 6. How it behaves end to end

1. **Upload.** Files are hashed and identified in a second. Installers and packages are dismantled.
2. **Group variants.** Builds join a version family by evidence, never by filename.
3. **Identify.** Logical entities are bound across builds by fused evidence. Similarity proposes; independent evidence accepts.
4. **Calibrate.** Format, ABI, compiler, flags and layout are learned globally before any per-function search.
5. **Scaffold.** Validated linkable regions prove the round trip early. The floor is scaffolding, not recovered C.
6. **C.** Ghidra C plus deterministic repair produces candidates. Compile admits a candidate, not a replacement.
7. **Propagate.** Candidates flow to compatible sibling builds. Each recipient earns its own compile and checks.
8. **Targeted AI.** Models work only on the measured leftovers, leaves before callers, one bounded attempt each.
9. **Parity.** Function and region comparisons run continuously. Local, linked and behaviour results stay separate.
10. **Whole-image identity.** A fresh rebuild relinks to a file whose hash equals the shipped binary. This is terminal.
11. **Exports.** The bundle is emitted, byte-identical on every re-run under the same basis.

Identity work, knowledge fusion, runtime reuse and exports run beside this loop. They never wait for it.

- **No Start button.** Open, add or resume admits the work; the only control is pause and resume.
- **Reuse first.** Existing analysis and valid results are reused and labelled reused; nothing is recomputed without a reason.
- **Deterministic.** Same inputs, same outputs, byte for byte; ties break on content hashes.
- **Compile-gated.** Knowledge crosses builds only when it compiles and fits, so unattended runs cannot poison themselves.
- **Blocked locally.** Missing evidence blocks its own claim; every independent lane keeps moving.

## 7. Why the strategy wins

The field moved in 2026. Agents now finish per-function matching of whole console games in weeks. That work is commodity. What nobody ships is the rest, and that is where AgentDecompile stands.

- **N builds as one program.** Every existing tool is pairwise with a human clicking Accept, or treats builds as a dropdown. Sibling builds in famous decompilations sit near 50% for years. Cross-build unification with automatic, compile-gated acceptance is the clearest unowned gap in the market.
- **Stable identity across compiler changes.** The same matching is designed to cross toolchain switches, exactly where hand-maintained extenders lost weeks each time. The fixture build-d exercises it.
- **No setup.** Existing agent loops need a hand-built repository, split configs and compiler presets per game. AgentDecompile is built to start from an upload.
- **Byte identity as ground truth.** "Compiles" and "passes tests" are gameable. Research shows model refinement raising build rates while behavioural fidelity fell. A hash is not gameable.
- **Whole-image certification.** Function-level 100% is not a rebuilt file. The terminal bar here is stricter than what matching projects claim.
- **Underserved targets.** PC compilers of the 1990s and 2000s: 18 Windows projects on the main tracker against 42 for one console.
- **Products fall out.** The community itself says a finished decompilation is "pretty unusable" for mods and ports. AgentDecompile aims to ship the API, headers and port from the same understanding.
- **Deterministic and reuse-first.** Results are cached by their inputs, so the corpus accretes and resumes instead of starting over.
- **Safe by default.** Bring your own binary, private-by-default outputs, patches and recipes instead of redistributed code or assets. Proof replaces the "vibe-coded port" stigma.
- **Beyond games.** The same N-build matching is patch diffing for defenders (what changed from N to N+1, ranked). "The source you lost, proven byte-identical" is legacy-software recovery.

**Do not headline:** "AI decompiler", "MCP for reverse engineering", "AI matches functions", "a better Ghidra", "Ghidra parity", compile rates, similarity percentages, "works on all builds", or the words receipt, audit, claim and verified. Vendors and communities own the first ones; the rest are metrics that lie or paperwork. Lead with outcomes and clocks: the mod that survives the patch, minutes from new build to ready, hours for siblings to converge, the hash that matches, the program playing in a tab.

## 8. Look and feel

**An IDE fused with a flight deck.** You always know where you are in the corpus. Power is one gesture away. Async work stays in peripheral vision. One theme, Graphite: dark surfaces, one blue accent for focus, and six work-family colours (identity blue, recovery green, unify amber, runtime teal, verify purple, intake graphite). Tokens live in `docs/design-system/project/tokens.json`.

**Draw the work.** Never a spinner beside "Running". Show the actual thing: blocks aligning across builds, a field moving from donor to recipient, diff lines flipping to identical, a byte map re-tinting as analysis claims it. Motion replays observed events only.

**Show, don't tell.** Visible text is names, numbers and labels of three words or fewer. Everything explanatory is a tooltip answering "what am I looking at?" Encoding carries the truth: solid means recorded, dashed means hypothesis, double means byte-authoritative, and the strictest level is always the solid segment of a stacked bar. `unknown`, `reused` and `stale` are stamps, not paragraphs.

The surfaces, in the order a user meets them:

- **The upload moment.** Drop files. Each becomes an identity chip within a second and slides into a version-family tree. One byte-map square per build appears as small multiples and starts re-tinting. An unknown build is a new node, not an error. Work has already begun.
- **The machine at work.** The hero view: one address band per build, stacked and aligned by matched entities, each worker drawn as a moving cursor, regions turning green as they land. Beside it, a builds × entities matrix where a match pulses across the row, and an engine room of worker lanes showing what unblocked what. A zero-text watch mode and a timelapse export.
- **The outputs gallery.** A lineage graph where understanding nodes (functions, types, globals, signatures) feed product nodes; when understanding improves, a pulse travels to the products. Below it, one tile per product with one verb: Browse, Inject, Play, Download, Connect. Each tile shows a readiness level and its proof badge. The home metric is a stacked bar per build: certified, matched, portable, scriptable, playable. Beside it, three clocks: upload → first resolved hook, new build → ready, build-a certified → siblings certified.
- **Each product's showcase.** Source: a size-weighted treemap of the program, and the certificate page with hash rows per build. Signatures: the readiness board, entities × builds, filling in live. Lua bridge: a generated API reference and event catalogue, and a mods panel with one dot per build. Browser build: play-in-page with a stats strip and a replay-verified badge. Editor: live typed memory rows and "who writes this" counters. Multiplayer: a per-tick divergence timeline. Learn-the-build: the toolchain chip and the compiler story.
- **The demo moment.** Split screen: one Lua mod running unchanged on build-a and build-d, the signature count resolving per build, and a slope chart of human-years against machine-hours for the same program.
- **The Code Browser as drill-down.** Listing, decompile, hex, graph and xrefs on one cursor, every pane following one selection, builds as columns. Full Ghidra functional parity lives here, one click below any tile or cell. It is where you inspect, never where you start.

Evidence is one click away and never the default view.

## 9. Where we are and how we get to done

**Where we are.** Two products reach a user today: the MCP server and context fusion. Everything else is partial or future. 18,578 functions compile and 1,617 are byte-exact, but no build rehashes identical yet. No export → Lua → observed-behaviour run has happened. Reviewed code is not serving live.

| Outputs done (bounded, existing or docs-only) | Partial | Future | Observed live | Whole-image hash match |
|---|---|---|---|---|
| 29 of 67 | 13 | 21 | 0 | 0 builds |

Sources: docs/research/2026-09-29-exports-and-outputs-inventory.md:70-72; docs/plans/2026-09-22-history-grounded-maintainability-design.md:47.

**Why we drifted:** honesty became paperwork, Ghidra parity became the core, and planning became progress: 398 Markdown files in a month, "receipt" ×1,386, the browser build ×53 (counted 2026-09-29 over docs added since 2026-08-29).

**Build order.** Every step ships with its showcase on the real event stream: no step is done until its picture is live. The upload moment, the machine at work and the outputs gallery are built in step 1 and grow with each step.

1. **Run live; readiness board live.** Reviewed code serving on the live workbench is the one blocker; every step below targets it. Nothing counts until it runs there. Emit export bundle v0 (signature pack, readiness grid, divergence report) from the 223 automatic matches and 193 identities that already exist. Entities × build-a…build-d, filling in on screen.
2. **One mod, four builds.** Generate the Lua surface from the pack; regenerate the ancestor's signatures, hooks and API; run one script unchanged on build-a and build-d. Record it: this is the launch video.
3. **Patch day.** Treat build-d as the new patch: readiness in minutes, divergence treemap ranked. The same report is the security audience's patch diff.
4. **Learn-the-build, then one certificate.** Calibrate the toolchain, drive function parity at scale, then relink one build to an identical hash.
5. **Play in a tab, floor first (its own lane from step 2).** Measure the emulation route (the original under an x86+Wine WASM host with the bridge attached) against its gate: median ≥20 fps, a non-black first frame, bridge status visible via F12. Ship it with replay verification. Recovered source then replaces the emulated code function by function; the tab's meter shows the share of C. A pure WASM build from recovered source, proven faithful by replay, is the ceiling, not the entry.
6. **F12 editor** in the injected original: pick, edit, run Lua, copy as Lua.
7. **Then** headers and cave plans from the pack, native platforms, multiplayer state maps, managed engines and compute scale-out.

**How to judge any plan.**

1. Which product in section 4 moves, and which clock shortens, on a real corpus?
2. Does it reuse what already exists, or does it re-plan it?
3. Can the user see the result as a picture within one click of opening the workbench?
4. Does it run without anyone pressing a button?
5. Is its claim checkable against bytes or a hash, and stated in one status word?

A plan that fails any of these is not ready.

## 10. Rules for agents

- **Authority order.** This page for intent. `AGENTS.md` for operations. `STRATEGY.md` for pipeline policy. `docs/design-system/project/` for look and feel. `docs/research/2026-09-29-exports-and-outputs-inventory.md` for the outputs map. `docs/DELIVERY_STATUS.md` for what is real. Everything else is history: read it when a task needs it, not to re-derive intent.
- **Names.** No product, game or binary names in repo docs, code, defaults or samples. Use `corpus-alpha`, `build-a` … `build-d`, "a classic PC game with four builds", "the runtime scripting bridge", "the injection host". Symbols follow `AGENTS.md`: camelCase locals and parameters, PascalCase types, snake_case fields, COBRA_CASE enum constants.
- **Honesty in one word.** done, partial, next or future. Never call a future or partial deliverable done. Never write a disclaimer paragraph where a status word, glyph or frame will do.
- **Never re-plan what exists.** The 67 outputs, 193 tracked units and 114 component specs already exist on paper; build them in product order. The 224 parity features and 113 proposed contracts are drill-down work: build one only when a product showcase needs it. Do not write new audits, receipt ledgers or parity matrices as progress.
- **Build toward the prototype.** The target experience is drawn in [prototypes/agentdecompile-product/](prototypes/agentdecompile-product/README.md). Every change should make the upload moment, the machine at work, the outputs gallery or a product showcase more real on the real corpus.
- **Operate as `AGENTS.md` says.** The live workbench and its action catalog only. Reuse before analysis. One writer per resource. No restarts, no alternate ports, no tests or builds to validate documents.
- **Show, don't tell** applies to your docs too. Short sentences. Tables and pictures over paragraphs.
