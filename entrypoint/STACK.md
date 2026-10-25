# The stack

Every tool AgentDecompile relies on or recommends, what it is for, what it cannot do, and
how far this repository has integrated it. [stack.json](stack.json) is the machine-readable
form that `setup/doctor.py` probes. Add a tool here and there together.

Integration status vocabulary:

| Status | Meaning |
|---|---|
| integrated | Called by code in this repository or exposed through the 8080 catalog |
| adapter-proposed | Named in [COORDINATOR.md](COORDINATOR.md) with a defined role; no code yet |
| curated | Recommended and probed by the doctor; nothing in the pipeline calls it |
| reference | Read its papers and code; do not depend on it |

Repository links are given only where this document's author could confirm them. Entries
marked "locate" came from the research brief that selected them; confirm the source before
installing anything.

## Analysis core

| Tool | Role | Limits | Status |
|---|---|---|---|
| Ghidra (NationalSecurityAgency/ghidra) | Disassembly, decompilation, types, P-code; the project store | Transactions are not fully isolated across concurrent writers | integrated |
| AgentDecompile MCP server and corpus pipeline (this repository) | Live Ghidra state over MCP; corpus stages; objdiff-gated recovery; 8080 workbench and catalog | Whole-image receipt route not implemented end-to-end | integrated |
| Ghidra Server | Shared repositories, checkouts, versioning (RMI over SSL) | Not HTTP; credentials do not authenticate the MCP listener | integrated |
| ghidra-rpc (cellebrite-labs/ghidra-rpc) | Persistent PyGhidra daemon with a CLI over local sockets so agents keep analysis state between commands | Local sockets; multi-agent safety still depends on one writer | curated |
| BSim | Function similarity over decompiler features across a corpus | Needs a populated database; an empty result may mean `createdatabase` never ran | integrated |
| BinDiff (google/bindiff) | Call-graph and flow-graph diffing between two binaries | Pairwise; no many-to-many | curated |
| VexIR2Vec (IITH-Compilers/VexIR2Vec) | Architecture-neutral function embeddings over VEX IR | Embedding similarity is not identity | curated |
| objdiff (encounter/objdiff) | Per-function object diff for the compile-and-compare proof | Per function; not a whole-image comparison | integrated |
| ReAgent | Agentic decompile, compile, test, repeat loop; scoped evidence alongside objdiff | Contributes scoped evidence only; does not replace objdiff or whole-file acceptance | integrated (optional check) |
| rev.ng (revng/revng) | Lifter and decompiler to LLVM IR; alternative view for hard regions | Separate type and ABI model from Ghidra | curated |
| ilspycmd (icsharpcode/ILSpy) | .NET IL decompilation | Installed separately; not a pip extra | integrated |

## The eight additions

| # | Tool | Role | Limits | Status |
|---|---|---|---|---|
| 1 | FIN | Explicit function-inlining identification from debug information, so one source function inside another binary function is modeled as one-to-many | Needs suitable debug info; cannot resolve arbitrary stripped binaries | adapter-proposed; locate |
| 2 | BinKit 2.0 (SoftSec-KAIST/BinKit lineage) | Ground-truth similarity datasets: 8 architectures, 23 compilers, 6 optimization levels, 371,928 binaries per the research brief; calibrates matcher thresholds | Does not represent every proprietary compiler or optimization; the 2.0 figures were not re-verified here | adapter-proposed |
| 3 | VeriBin (NDSS 2025) | Binary-vs-binary behavioral comparison by symbolic execution for patch safety; verification without recovered source | Built for patches, not arbitrary whole-program equivalence | adapter-proposed; locate |
| 4 | CounterTV (compilerai/counter per the brief) | Optimized x86 assembly against LLVM IR by semantic alignment and equivalence checking | Architecture, solver and semantics limits | adapter-proposed; locate |
| 5 | Dolt (dolthub/dolt) | Version-controlled SQL with branches, merges, row and schema conflicts for identities and competing findings | Cannot decide which conflicting interpretation is correct | adapter-proposed |
| 6 | Temporal (temporalio/temporal) | Durable workflows, retries and history for thousands of analysis jobs | Retried activities can run more than once; writes must be idempotent | adapter-proposed |
| 7 | OpenLineage (OpenLineage/OpenLineage) | Standard job, input, output, version and test relationships with custom facets | Does not evaluate hypothesis truth | adapter-proposed |
| 8 | Sigstore Cosign (sigstore/cosign) | Signs and verifies evidence artifacts and attestations | A signed wrong conclusion is still wrong | adapter-proposed |

## Conditional additions

| Tool | Role | Include when | Status |
|---|---|---|---|
| SBridge (FSE 2026, DOI 10.1145/3797090) | Source-to-binary function similarity by cross-domain control-block matching; robust to inlining and stripping | Candidate source exists for part of the corpus | curated; locate |
| binary2source matching under function inlining (arXiv 2112.12928 and follow-ups) | One-to-many binary-to-source correspondences and a labeled dataset | Heavy inlining and candidate source | curated; locate |

## Execution and hardware fidelity

| Tool | Role | Limits | Status |
|---|---|---|---|
| PANDA (panda-re/panda) | Whole-system record and replay, taint, plugins | Emulated timing | curated |
| avatar² (avatartwo/avatar2) | Orchestrates emulators, debuggers and real hardware together | Needs target-specific glue | curated |
| Renode (renode/renode) | Deterministic multi-node embedded simulation | Peripheral models are functional, not physically exact | curated |
| Frida (frida/frida) | Dynamic instrumentation of running processes | Observation under the user's permissions; not recovered source | curated |
| KotorPhasor adapters (read-only sibling checkout) | Typed native calls, detours, packs for known builds | Known builds only; see [RUNTIME_REUSE.md](../docs/RUNTIME_REUSE.md) | integrated (export side) |

## Verification and semantic correctness

| Tool | Role | Limits | Status |
|---|---|---|---|
| AFL++ (AFLplusplus/AFLplusplus) | Differential fuzzing of original vs recovered units | Coverage-bounded; no proof | curated |
| angr (angr/angr) | Symbolic execution and path comparison on bounded regions | Path explosion; environment modeling | curated |
| Alive2 (AliveToolkit/alive2) | Bounded SMT translation validation of LLVM IR transformations | IR-to-IR only; bounded loops; no inter-procedural | curated |
| STOKE (StanfordPL/stoke) | x86-64 instruction-level equivalence checking and synthesis | Research prototype, no active development; never a dependency | reference |

## Provenance and coordination

| Tool | Role | Limits | Status |
|---|---|---|---|
| DVC (iterative/dvc) | Content-addressed storage of binaries, traces and large receipts | Not a database | curated |
| in-toto (in-toto/in-toto) | Supply-chain layouts and link metadata for the evidence pipeline | Attests process, not truth | curated |
| Dolt, Temporal, OpenLineage, Cosign | See additions | | adapter-proposed |

## Specialized

| Tool | Role | Limits | Status |
|---|---|---|---|
| RenderDoc (baldurk/renderdoc) | Frame, shader, resource and draw-call inspection | No D3D9/10 or legacy OpenGL compatibility profile | curated |
| apitrace (apitrace/apitrace) | API tracing for older graphics workloads RenderDoc does not cover | Older APIs | curated |
| REA (morluto/rea) | Peer MCP server for JavaScript/Electron, .NET, websites, APKs, firmware, captures | Findings enter as context hints; different claim bar | curated |

## Research references

| Tool | Role | Why not production yet |
|---|---|---|
| vSim (OSUSecLab/vSim, NDSS 2026) | Semantic-value extraction for similarity | Value extraction is very slow; benchmark comparator until it beats existing matchers on an independent corpus |
| Co2FuLL (ASE 2025) | Context-content fusion with LLM verification for similarity | Same bar as vSim; repository not located here |

## Toolchains and build

| Tool | Role | Notes |
|---|---|---|
| Identified original compilers (MSVC under Wine, GCC, Clang, CodeWarrior and others as evidence dictates) | The only compilers whose output can match bytes | One writer per toolchain; never duplicate compiler or Wine work |
| uv, Python 3.10+, Java 21 | Repository runtime | See [USAGE.md](../USAGE.md) |
