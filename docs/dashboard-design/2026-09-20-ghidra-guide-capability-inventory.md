# Ghidra Reversing Guide capability inventory

Date: 2026-09-20

Guide: [Ghidra Reversing Guide](https://github.com/OpenKotOR/PyKotor/wiki/Ghidra-Reversing-Guide)

Scope: map the guide's human-facing Ghidra Code Browser workflow to the current AgentDecompile dashboard, API, and MCP implementation under `src/`.

Evidence boundary: this is a read-only source inspection. “Implemented” below means that the relevant UI and backing source paths are present and wired in the inspected checkout. It is not runtime, persistence, live-Ghidra, or browser proof. No server, job, build, test, or filesystem behavior was exercised for this inventory.

Continuation correction: the reconciled WorkstationApp does not yet mount the
existing CodeBrowser/GuideWorkflows components. Their source wiring in older app
roots is not reachability proof in the current root. Task 4 must compose them.
The parameter-storage gap below was subsequently implemented and source-reviewed
in `a6bbe36`; live acceptance remains open. Historical line references below
describe the initial inspection, not a claim that these files never changed.

**2026-09-28:** a concrete UI redesign closing these gaps for the static (8080)
surface only is in
[`2026-09-28-static-codebrowser-guide-redesign.md`](2026-09-28-static-codebrowser-guide-redesign.md).
That doc's guide-chapter table and gap analysis build directly on the rows below;
read this inventory first, then that doc for the implementation plan.

## Status meanings

- **Implemented**: the guide capability has a first-class source-wired UI and backing MCP/API path.
- **Partial**: useful support exists, but the dashboard does not yet provide the guide-equivalent interaction or the behavior is available only through a generic action or script.
- **Missing**: no first-class dashboard or dedicated tool was found.

## Requirement matrix

| Guide section | Required GUI capability | Current support and source evidence | Status | Redesign requirement |
|---|---|---|---|---|
| [1. Introduction](https://github.com/OpenKotOR/PyKotor/wiki/Ghidra-Reversing-Guide#1-introduction) | One main reverse-engineering workspace centered on the selected program and address. | `src/agentdecompile_recovery/corpus/dashboard/frontend/src/CodeBrowser.tsx` implements an address-centered browser backed by MCP jobs and is wired in older app roots. The reconciled `workstation/WorkstationApp.tsx` currently uses AnalysisView, not CodeBrowser. | **Partial**: existing component needs composition in the active root | Preserve one shared project/logical/member selection across panes. Reuse the existing browser, not a second independent analysis workspace. |
| [2. Ghidra Repos and Projects](https://github.com/OpenKotOR/PyKotor/wiki/Ghidra-Reversing-Guide#2-ghidra-repos-and-projects) | Browse project contents, open/select programs, and show active project/program context. | `frontend/src/GuideWorkflows.tsx:20-38` launches `list-project-files` and `get-current-program`. Project, import, local project, and shared repository operations are implemented in `src/agentdecompile_cli/mcp_server/providers/project.py:177-518,2489-2781`. | **Implemented**, project UX still **partial** | Use the correct hierarchy: project → folders/domain files/programs. Reserve “repository” for Ghidra shared/version-control infrastructure. Show exact locator and program identity. |
| [3. Code Browser Overview](https://github.com/OpenKotOR/PyKotor/wiki/Ghidra-Reversing-Guide#3-code-browser-overview) | Connect/refresh a program, go to an address or symbol, and switch among analysis panes without losing context. | `CodeBrowser.tsx:408-495` provides connect/refresh, address-or-symbol go-to, and panes for functions, symbols, types, memory, bookmarks, references, type uses, and vtables. | **Implemented** | Keep the selected program and address as the single state owner. Pane changes must not silently change the target. |
| [4. Symbol Tree](https://github.com/OpenKotOR/PyKotor/wiki/Ghidra-Reversing-Guide#4-symbol-tree) | Search and navigate symbols, classes, namespaces, functions, labels, imports, and exports; browse hierarchy. | `CodeBrowser.tsx:252-318,444-530` implements symbol-kind selection, search, address jumps, and ambiguous exact-name handling. `src/agentdecompile_cli/mcp_server/providers/symbols.py:1-9,115-259,323-346,660-736` provides symbols, classes, namespaces, imports, exports, labels, search, and pagination. | **Implemented** search; hierarchy **partial** | Reuse the existing provider. If full hierarchy is required, add an expandable namespace/class tree over the same results; do not duplicate symbol lookup. Preserve ambiguity instead of guessing an address. |
| [5. Data Type Manager](https://github.com/OpenKotOR/PyKotor/wiki/Ghidra-Reversing-Guide#5-data-type-manager) | Browse type archives/categories, inspect structures/unions/enums/function types, hide pointer noise, find uses, and edit layouts. | The types pane, category filter, pointer hiding, info, and find-uses are wired in `CodeBrowser.tsx:258-275,600-640`; guided actions are in `GuideWorkflows.tsx:39-76`. `src/agentdecompile_cli/mcp_server/providers/_collectors.py:821-948` enumerates types, archives, structures, enums, members, and fields. `providers/datatypes.py`, `structures.py`, `enums.py`, and `data.py` provide inspection and mutations. | Browse/info/find-uses **implemented**; component editor **partial** | Compose the existing type operations into a category/archive browser. Add a field/component editor only if required; the current browser does not equal Ghidra’s structure/union/enum grid editor. |
| [6. The Listing](https://github.com/OpenKotOR/PyKotor/wiki/Ghidra-Reversing-Guide#6-the-listing) | Show addresses, bytes, interpreted instructions, operands, labels, data, and xrefs; navigate by instruction/function/label/undefined item; define data. | `frontend/src/GuideWorkflows.tsx:78-137` exposes instruction operands, navigation, byte reads, function evidence, decompile plus assembly, apply-data-type, and rename. `providers/functions.py:7,94,214-328,468-489`, `providers/memory.py:45-304`, and `providers/data.py` provide disassembly, memory, and typed-data operations. `dashboard/workbench.py:1881-2035,2047+` composes listing metadata, callers/callees, and function evidence. `CodeBrowser.tsx:758-827` provides previous/next navigation, clickable instruction flows, and an assembly `SourceEditor`. | **Partial** | Build a continuous instruction-row Listing over existing data: address, bytes, mnemonic, operands, labels/comments, flow, and xref indicators. Current one-instruction inspection plus assembly text is not Listing parity. Keep bytes and processor context visible; do not claim the rendered disassembly is infallible ground truth. |
| [7. Decompile View](https://github.com/OpenKotOR/PyKotor/wiki/Ghidra-Reversing-Guide#7-decompile-view) | Display the containing function’s decompilation, retain the last valid function while inspecting data, navigate referenced functions/symbols, rename, edit signatures, and optionally include unreachable code. | `CodeBrowser.tsx:319-390,798-856` loads assembly and decompile for one selected function and deliberately retains the last function when a non-function address is inspected. Token inspection performs exact program-symbol lookup with ambiguity handling at `CodeBrowser.tsx:276-318,844-851`. `GuideWorkflows.tsx:104-120` exposes `includeDisassembly`, comments, and `showUnreachable`; `providers/decompiler.py:47-89,239-240` backs those controls. | Function-level view **implemented**; cursor/local-variable UX **partial** | Synchronize listing and decompiler at address/token level and add explicit back/forward navigation. Program symbol/function navigation exists. Local-variable rename/type exists in the backend but lacks a direct decompiler gesture; expose it without treating local variables as program addresses. |
| [8. Other Code Browser Tools](https://github.com/OpenKotOR/PyKotor/wiki/Ghidra-Reversing-Guide#8-other-code-browser-tools) | Incoming/outgoing call trees and xrefs, memory map, bookmarks, symbol table, function table, and scripting. | `providers/xrefs.py:40-226`, `providers/callgraph.py`, `providers/memory.py:181-203`, and `providers/bookmarks.py` provide the backing operations. `CodeBrowser.tsx:531-598` filters functions by convention, signature, address range, size, inline state, and undefined parameters. `GuideWorkflows.tsx:139-180` launches xrefs, call graph, memory blocks, bookmarks, and comments. | Data/actions **implemented**; rich tool views **partial** | Reuse these operations. Interactive call-tree/graph and memory-map visualizations are optional UI composition, not new backends. Bookmarks need a clear jump action and persistent category/comment display. |
| [9. Functions](https://github.com/OpenKotOR/PyKotor/wiki/Ghidra-Reversing-Guide#9-functions) | Inspect and edit name, namespace, convention, return type, parameters, varargs, inline/no-return flags, call fixup, thunk target, and storage. | `frontend/src/FunctionEditor.tsx:25-52,121-248` loads function properties and edits namespace, flags, call fixup, thunk target, and convention. Draft persistence and incoming-state detection are at `FunctionEditor.tsx:31-108`. `providers/getfunction.py:340-408` routes info, property/storage edits, rename, prototype, convention, return type, variable operations, create, and delete through program transactions and conflicts. | **Implemented**, with parameter-storage defect | Keep the draft/conflict flow. Fix the misleading parameter-storage control described below. Avoid a second function mutation implementation. |
| [10. Calling Conventions](https://github.com/OpenKotOR/PyKotor/wiki/Ghidra-Reversing-Guide#10-calling-conventions) | Inspect the selected function’s actual convention and choose from conventions supported by its language/compiler specification. | `FunctionEditor.tsx:209-248` renders server-provided available conventions and submits `manage-function mode=set_calling_convention`. `GuideWorkflows.tsx:183-230` correctly warns that the guide’s 32-bit x86 examples are not cross-ABI defaults. | **Implemented** | Continue deriving conventions from the selected program. Never hard-code cdecl/stdcall/fastcall/thiscall assumptions into the UI or mutation defaults. |
| [11. Returns and Custom Storage](https://github.com/OpenKotOR/PyKotor/wiki/Ghidra-Reversing-Guide#11-returns-and-custom-storage) | Edit explicit return and parameter storage using registers and stack pieces appropriate to the active ABI. | Return type and editable multi-piece register/stack return storage are implemented in `FunctionEditor.tsx:249-399`; submission uses `manage-function mode=set_storage`. Recorded parameter storage is displayed at `FunctionEditor.tsx:400-454`. `GuideWorkflows.tsx:208-216` exposes the same storage operation. | Return storage **implemented**; parameter storage **partial/defective** | Make parameter storage genuinely editable and validate register sizes, ordinals, piece sizes, and overlap against the selected program. Do not preserve the current no-op-like “Edit parameter storage” behavior. |
| [12. Structures](https://github.com/OpenKotOR/PyKotor/wiki/Ghidra-Reversing-Guide#12-structures) | Browse structures, inspect fields/offsets/sizes/descriptions, validate proposed C layouts, edit components, and apply types to memory/signatures. | `GuideWorkflows.tsx:233-258` provides browse, info, and C-definition validation. `providers/structures.py` dispatches list/info/create/update/delete/validate operations; `apply-data-type` handles application. | Inspection/validation/application **implemented**; field editor **partial** | If included in redesign scope, provide a bounded field editor over the existing structure provider. Parsing a C definition and a cleaner decompile are not proof of binary layout. |
| [13. VTables](https://github.com/OpenKotOR/PyKotor/wiki/Ghidra-Reversing-Guide#13-vtables) | Find candidate vtables, inspect slots and referenced functions, trace callers, and relate observed virtual dispatch to class layouts without hiding ambiguity. | `providers/vtable.py:1-6,38-208` supports `containing`, `analyze`, and `callers`. `CodeBrowser.tsx:271-275,327-331` invokes containing/detailed analysis. `GuideWorkflows.tsx:259-268` explicitly states that candidates/references do not prove class identity or every inherited slot. | Candidate analysis **implemented**; semantic class model **partial** | Display candidate evidence, slot offsets, targets, and references. Do not infer a universal class, parent, destructor slot, or inheritance model from one address. Per-derived-class ambiguity must remain visible. |
| [14. Template Classes](https://github.com/OpenKotOR/PyKotor/wiki/Ghidra-Reversing-Guide#14-template-classes) | Locate each concrete template instantiation and inspect its observed size, pointer width, capacity, and element layout. | `GuideWorkflows.tsx:270-291` locates concrete data types and inspects structures. Existing generic type/structure providers supply the evidence. No template-specific provider or comparison UI was found. | **Partial**, appropriately generic | Treat template instantiations as concrete Ghidra types. A template-specific abstraction is unnecessary unless repeated comparison proves a need. Never encode the guide’s 12-byte/4-byte examples as defaults. |
| [15. Common Decompile Issues](https://github.com/OpenKotOR/PyKotor/wiki/Ghidra-Reversing-Guide#15-common-decompile-issues) | Investigate `extraout`, `unaff`, reused stack slots, wrong return types, and virtual-call ambiguity by checking machine code, callers/callees, and data flow before changing analysis. | `GuideWorkflows.tsx:293-326` wires `analyze-data-flow`, get-function, prototype correction, and redecompile. `providers/dataflow.py` backs data-flow analysis. The workflow already states that a cleaner decompile is not a verified source match. | Evidence workflow **implemented**; automatic diagnosis **missing** | Keep this hypothesis-driven. A dedicated diagnostic view may correlate symptoms with relevant callees/register flow, but must not auto-apply types or prototypes solely to remove decompiler artifacts. |
| [16. Closing](https://github.com/OpenKotOR/PyKotor/wiki/Ghidra-Reversing-Guide#16-closing) | Provide discoverable help, documentation links, and honest evidence limitations. | The guide launcher covers every chapter in `GuideWorkflows.tsx:20-328`; dashboard documentation/help links exist elsewhere in the web UI. | **Implemented** at workflow level | Link the guide as reference material and retain AgentDecompile’s evidence/provenance language. Do not present the guide as an executable specification. |

## Cross-cutting findings

### Listing/decompiler synchronization

Current synchronization is function/address-level. One selected address drives instruction evidence, assembly, decompile, xrefs, and the function editor. The UI also retains the last valid containing function while a data address is inspected (`CodeBrowser.tsx:836-843`), which matches the useful behavior described by the guide.

The remaining gap is fine-grained synchronization:

- selecting an instruction row should highlight the corresponding decompiler token or statement when a mapping exists;
- selecting a decompiler symbol/address should navigate the Listing and update xrefs without confusing local variables with addresses;
- both panes should share explicit back/forward history;
- absence of a mapping must remain visible rather than fabricating one.

### Navigation and xrefs

Go-to address/symbol, next/previous instruction/function/label/undefined navigation, instruction flow targets, incoming/outgoing references, and call graph operations are present. The redesign should compose these into a common navigation model rather than add another resolver.

### Local-variable refinement

Local-variable operations are present in the MCP backend:

- `providers/getfunction.py:156-165` advertises/routes rename-variable, set-local-variable-type, and datatype-change aliases;
- `providers/getfunction.py:373-392,415-452+` resolves those actions through the decompiler’s `HighFunction` local symbol map.

The GUI gap is direct access from the decompile view. `CodeBrowser.tsx:844-851` currently treats an inspected token as a possible program symbol. A local variable may not be a program address. The redesign should classify the selected token in the current high function and offer rename/type operations only when the backend identifies a local symbol.

### Parameter-storage correction

`FunctionEditor.tsx:400-449` displays each parameter and its recorded storage. Its button labeled “Edit parameter storage” immediately submits a `parameterStorage` array containing the existing ordinal, datatype, and unchanged storage pieces. It does not open an editor or maintain editable parameter-storage state.

This is not complete parameter editing. The smallest correct fix is either:

1. make the row genuinely editable and submit the changed pieces; or
2. remove/relabel the action until editing exists.

Return storage is genuinely editable at `FunctionEditor.tsx:249-399` and should be reused as the interaction pattern.

### Mutation safety

Function and analysis mutations use the existing action review and conflict workflow. In particular, `providers/getfunction.py:398-408,474-497` returns a modification conflict before applying property/storage changes and applies accepted changes in a Ghidra transaction.

The redesign must preserve:

- exact project/program/address identity;
- preview/review before mutation;
- persisted drafts tied to that identity;
- explicit conflict resolution;
- post-write refresh of the affected program evidence;
- provenance that distinguishes analysis annotations from recovered or verified source.

### Patch, export, and scripting

Export is implemented at the MCP source level. `src/agentdecompile_cli/mcp_server/providers/import_export.py:491-540,1721-2175` exposes C/C++ pseudocode, GZF, SARIF, XML, HTML, and ASCII formats. The `format` field selects a Ghidra exporter and remains separate from recovery source language.

Unrestricted PyGhidra scripting is implemented in `providers/script.py:99-137,352-506`. Its namespace exposes mutation primitives including `setBytes`, `clearListing`, `removeDataAt`, and `disassemble` (`script.py:169,278-285`). `providers/strings.py:570` also writes bytes for its string-specific operation.

No dedicated, bounded general patch-bytes or assemble UI/tool was found. Therefore:

- scripting and export should remain advanced actions;
- raw unrestricted scripting should not become the ordinary patch UX;
- if first-class patching is explicitly in scope, add original-byte preview, exact target identity, confirmation, a Ghidra transaction/conflict receipt, and a post-write byte read;
- do not infer successful export, persistence, or patching from source presence alone.

### Existing guide launcher

`frontend/src/GuideWorkflows.tsx:20-328` already covers the guide’s substantive chapters. It launches the established tools, filters unsupported fields against the action catalog, and includes several important evidence warnings. The redesign should reuse this ordered workflow rather than reimplement it.

## Guide claims that must not become implementation rules

The guide is valuable reference evidence, but several statements are shorthand, build-specific observations, or inaccurate generalizations.

1. **“Each repo represents an executable” is not the Ghidra object model.** A project contains folders and domain files, including program domain objects. A repository is shared/version-control infrastructure. The dashboard must not rename every program a repository.

2. **PE exports and the entry point are distinct.** The guide’s statement that exports for a Windows executable are the entry point is incorrect. Many executables export nothing, and an export table entry is not the image entry point.

3. **The Listing is interpreted evidence, not infallible truth.** Raw bytes plus correct load mapping, processor language, context, and decoder configuration are the substrate. Disassembly can be wrong when those inputs are wrong.

4. **The decompiler is algorithmic even though it uses heuristics and inference.** The actionable rule is that decompiled C-like text is inferred/advisory and must be checked against lower-level evidence—not that it is “not an algorithm.”

5. **Calling-convention descriptions are compiler-, architecture-, and build-specific.** Stack cleanup, register assignment, name decoration, hidden parameters, and structure returns must come from the selected language/compiler specification and observed calls. A no-stack-argument member function does not become cdecl merely because no stack cleanup is visible.

6. **Return values do not universally live in EAX.** Depending on ABI and type, returns may use EDX:EAX, x87 ST registers, SSE/vector registers, hidden structure-return pointers, memory, or other architecture-specific storage. Bits left in EAX after a `void` function are not thereby a supported return value or safe patch hook.

7. **“Float 10” and composite return examples are not general rules.** x87 extended precision, ST(0), and any simultaneous general-purpose-register result must be modeled from the exact function, compiler specification, callers, and observed storage.

8. **Vtable layout claims are not universal ABI rules.** The first slot need not universally be a destructor; a vptr need not always be the only pointer at object offset zero; multiple inheritance can add secondary vptrs; thunks and RTTI affect interpretation. “Ghidra stores the vtable on the most senior parent” may describe one project’s type modeling, not an intrinsic rule.

9. **Template layout sizes are exact-build observations.** The guide’s 12-byte array-list and 4-byte linked-list examples depend on pointer width, compiler, ABI, implementation, and recovered type accuracy. `GuideWorkflows.tsx:270-291` correctly refuses to assume those sizes.

10. **A cleaner decompilation is not validation.** Changing a signature, return type, convention, or storage to remove `extraout`/`unaff` artifacts is hypothesis refinement. The UI must retain bytes, assembly, caller/callee evidence, and mutation provenance.

## Planning conclusion

Most required backend and MCP primitives already exist. The redesign should primarily compose them into one synchronized Code Browser.

Highest-value gaps:

1. a continuous, navigable Listing rather than an assembly text document plus one-instruction inspector;
2. shared listing/decompiler selection and back/forward navigation;
3. direct, correctly classified local-variable rename/type actions;
4. genuine parameter custom-storage editing;
5. optional bounded structure-field editing and general patching only if those capabilities are explicitly in scope.

Avoid reimplementing providers. Reuse `CodeBrowser`, `FunctionEditor`, `GuideWorkflows`, the action runner, and the established MCP tools.
