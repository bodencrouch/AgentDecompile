# Ghidra Code Browser functional parity specification

Date: 2026-09-29

Status: design specification. It is not a delivery, runtime or recovery receipt.
[DELIVERY_STATUS](../DELIVERY_STATUS.md) owns observed outcomes.

Scope: every functional capability of Ghidra's Code Browser tool, plus the
closely related tools named in the request, mapped onto the static 8080
dashboard (`/dashboard`). Only features and functionality are covered. Ghidra's
look, themes, colors, fonts and window chrome are out of scope. Theming help
topics were deliberately skipped.

This document extends the
[Ghidra guide capability inventory](2026-09-20-ghidra-guide-capability-inventory.md).
That inventory maps the guide's 16 chapters to source. This one enumerates
Ghidra's own help topics feature by feature. Where a row repeats an inventory
finding, the row cites it rather than restating it.

## Summary

Rows: **221** Ghidra features across 15 groups.

| Status | Rows | Share |
|---|---|---|
| covered | 42 | 19% |
| partial | 91 | 41% |
| missing | 88 | 40% |

| Group | Rows | covered | partial | missing |
|---|---|---|---|---|
| 1. Listing, navigation and the byte viewer | 42 | 8 | 19 | 15 |
| 2. Decompiler | 32 | 7 | 10 | 15 |
| 3. Function Graph, call graph and call trees | 13 | 3 | 5 | 5 |
| 4. Symbol Tree, Symbol Table and references | 13 | 3 | 8 | 2 |
| 5. Data Type Manager and type editors | 19 | 0 | 9 | 10 |
| 6. Program Trees, Memory Map, relocations, equates, registers | 12 | 1 | 3 | 8 |
| 7. Strings, data, bookmarks, comments, labels | 11 | 2 | 7 | 2 |
| 8. Functions | 16 | 3 | 9 | 4 |
| 9. Disassembly, clearing, data creation, references | 11 | 0 | 2 | 9 |
| 10. Searches | 11 | 0 | 6 | 5 |
| 11. Analysis | 9 | 4 | 2 | 3 |
| 12. Patching, Program Diff, Version Tracking | 8 | 2 | 3 | 3 |
| 13. Scripting | 5 | 1 | 2 | 2 |
| 14. Undo, transactions, multi-user, import and export | 10 | 3 | 6 | 1 |
| 15. Identification tools, utilities, keyboard and options | 9 | 5 | 0 | 4 |
| **Total** | **221** | **42** | **91** | **88** |

What the counts say:

- **Reading code is mostly designed.** Listing, DecompileView, HexStrip,
  GraphPane, CallHierarchy, XrefPanel, Peek, HeldPane, SplitCompare and
  NavigationBar already specify most read-only browsing. The gaps are Listing
  field configuration, the overview and flow margins, address-set selection,
  and the byte viewer's alternate formats.
- **Editing is the largest gap.** Rename, retype, comment, custom storage and
  apply-type are specified (InlineRename, StorageEditor). There is no
  design-system component for these: the signature dialog, the type manager
  and structure/enum editors, the stack frame editor, references, flow and
  fallthrough overrides, clear, disassemble, register values, memory blocks,
  equates and patching. Most also lack a documented catalog action.
- **Search is thin.** `search-everything`, `search-code`, `search-constants`
  and `manage-strings` exist. Byte-pattern memory search, direct-reference
  search, address-table search and search-and-replace have no documented
  backend.
- **The multi-variant model is stronger than Ghidra's.** Program Diff, Version
  Tracking and function comparison map onto the corpus-first design:
  CounterpartMatrix, SplitCompare, MatchReview and PropagationTransfer. Two
  things remain partial there: program-level range diff, and applying a diff
  category as propagation.
- **The static 8080 surface has no split panes** (LayoutPresets). On 8080,
  every "Open beside" and held-pane row opens a new window. The function exists
  there, but the side-by-side presentation does not.

Top ten gaps by recovery value: continuous Listing (L01); the signature editor
(D13, F06–F09); the type manager and editors (T01–T11); commit params/locals
(D11, D12); the reference and flow-override editors (E03, E08–E10); byte and
instruction search (Q01, Q03, Q04); scalar search results (Q05); the relocation
table (P05); the stack frame editor (F13); patching (X01).

## Evidence boundary

- **Ghidra sources.** Ghidra's help topics were read from a sparse checkout of
  `NationalSecurityAgency/ghidra` at commit
  `9d9b5def0214f9227fcb0d8de248a5b743dfbfac`. The paths read were
  `Ghidra/Features/*/src/main/help/help/topics/**` and
  `Ghidra/Framework/*/src/main/help/help/topics/**`. The ghidra.re class
  guides and API reference are cited where they add context. URLs in the
  reference list point at the `master` branch.
- **Repository sources.** Only text documentation was read:
  [FRONTEND_INTENT](../FRONTEND_INTENT.md), the
  [unified workstation spec](2026-09-20-unified-workstation-spec.md), the
  [consolidated design plan](2026-09-21-consolidated-design-plan.md),
  [PyGhidra API reference](../PyGhidra_API_Reference.md),
  [TOOLS_LIST](../../TOOLS_LIST.md), [AGENTS](../../AGENTS.md), and the
  [design system](../design-system/project/README.md) with its guidelines and
  component READMEs. Nothing under `src/` or any frontend code was read. No
  server, test, build or job was run.
- **What a status means.** Status describes the documented design and the
  documented tool surface, not observed behavior.
  - **covered**: a design-system component specifies the interaction, and a
    documented MCP tool or catalog path backs it.
  - **partial**: only one of the two exists, or only a subset of the Ghidra
    feature is specified.
  - **missing**: neither exists.

  No row is delivered until live 8080 evidence says so.
- **Tool names.** A tool name appears only when a repository document names it.
  Mode names such as `set_calling_convention` and `set_storage` come from the
  guide inventory. Everything else reads "catalog action needed": the verb must
  be added to `GET /api/v1/actions` and backed by a provider.

## How to read a row

Each matrix has these columns:

- **Ghidra feature**: the feature and a one-line description of what it does,
  with a source link.
- **R/M**: `RO` for read-only, `MUT` for mutating. `RO+MUT` means the window
  reads and also offers edits.
- **AgentDecompile mapping**: an existing design-system component, or
  `NEW: ‹Name›`. "(extend)" means an existing component needs an addition,
  listed in [Extensions to existing components](#extensions-to-existing-components).
- **Backend**: a documented tool, or "catalog action needed".
- **Multi-variant**: how the feature works per logical entity across build-a…build-d.
- **Doctrine**: codes from the table below.
- **Status**: covered, partial or missing.

### Doctrine codes

| Code | Meaning |
|---|---|
| RO | Read-only browsing. Opening, following, peeking or hovering never writes, decompiles on a cache miss, or analyzes. |
| NA | No analysis on open. Analysis or re-disassembly runs only when admitted through the workflow (`manage-workflow`) or an explicit catalog verb. |
| CAT | The mutation goes through the catalog: `GET /api/v1/actions`, then ActionStrip (or InlineRename for one target), then a job. The outcome lands on the invoking row (OutcomeCell), and BeforeAfterBand shows the re-read value. |
| CF-in | Confirms in place, in its own named editor (Enter or Save): a single-target rename, retype, comment or storage change. |
| CF-dlg | Confirms through ConfirmDialog: batch, destructive, or cross-build. A struct-layout change, field retype or callee-signature change counts as cross-build, because it changes every use. |
| 1W | One Ghidra writer per project or program. Admission checks the real owner (PID, start time, command). Owners are never inferred from job labels. |
| MC | May return a modification conflict, resolved explicitly with `resolve-modification-conflict`. |
| NP | No promotion. The result is advisory (a hypothesis or candidate) and is never proof of layout, identity or recovery. |
| PV | Per-viewer state (keymap, layout, marks, view settings), kept as durable workspace state. It is not program data and is never propagated. |
| NC | The editor shows the repository naming convention for the identifier kind. Locals, globals and parameters use `camelCase`. Types use `PascalCase`. Fields use `snake_case`. Enum constants use `COBRA_CASE`. |

### Multi-variant patterns

These terms are used in the Multi-variant column.

| Term | Meaning |
|---|---|
| per-build | Acts on one concrete build only. The CounterpartStrip shows where else the entity exists. |
| propose→counterparts | After a per-build edit, the change can be offered field by field to accepted counterparts as a PropagationTransfer. The offer is gated by identity edge and compatibility. Nothing is applied automatically, and each recipient gets its own outcome. |
| layout-gated | A type or storage change applies to a build only after that build's own size, alignment, pointer width and register checks pass. A mismatch blocks that recipient and says why. |
| scope one/all | A read or search runs on the inspected build or on all builds, with one hit column per build and LocatorGlyph words. The same logical hit may sit at different addresses. |
| side-by-side | Per-build values are shown together in SplitCompare or CounterpartMatrix and never merged. |
| program-local | A program-level fact of one build. Across builds it can be compared, but it has no shared meaning. |
| anchor-mapped | Cursor or range positions move between builds only through recorded anchor pairs, never by offset or order. |
| viewer | Per-viewer presentation that applies to every build alike. |

Example used throughout: `ResourceRef::Resolve` is FUN_0041c880 on build-a
and sits at 0041b210 on build-c. Its first parameter points to a `CacheEntry`.

## Full matrix

### 1. Listing, navigation and the byte viewer

| ID | Ghidra feature | R/M | AgentDecompile mapping | Backend | Multi-variant | Doctrine | Status |
|---|---|---|---|---|---|---|---|
| L01 | Listing view: continuous code-unit display with one address cursor [cb] | RO | Listing inside CodeBrowser | `inspect-memory` (mode `disasm`), `get-function`; catalog action needed for paged section-wide listing rows | per-build; switching builds keeps the entity (anchor-mapped); SplitCompare shows build-a beside build-c | RO, NA | partial (the inventory lists continuous Listing as the highest-value missing piece) |
| L02 | Address field and its options: padding, block name [cbopt] | RO | Listing address column | `inspect-memory` | per-build addresses; the logical entity is in the composite header | RO | covered |
| L03 | Bytes field and options: grouping, reverse order, max bytes shown [cbopt] | RO | Listing bytes column; moves into HexStrip when Hex is on | `inspect-memory` (mode `bytes`) | per-build | RO | partial (options) |
| L04 | Mnemonic and Operands fields; operand display options: block names, register-variable markup, reference underline, line wrap [cbopt] | RO | Listing mnemonic and operand cells; symbol operands are typed links | `inspect-memory` (mode `disasm`), `get-references` | per-build; operands differ by register allocation; no alignment is inferred between builds | RO | partial (display options) |
| L05 | Labels field: primary and non-primary labels, namespace display [cbopt] [lbl] | RO | Listing label cell with its NameProvenance tier word | `manage-symbols` | counterpart names via CounterpartStrip | RO | covered |
| L06 | Function header fields: signature, signature source, call-fixup, purge, tags, repeatable comment, register values at entry [bff] | RO | Listing (extend: function header rows) | `get-function`, `manage-function-tags` | per-build; a signature difference shows as a divergence class in CounterpartMatrix | RO | partial |
| L07 | Function variables display: stack and register annotations, open/close [cb] | RO | Listing (extend: collapsible variable rows); CodeBrowser Outline Locals | `get-function` | per-build storage | RO | partial |
| L08 | Comment fields: EOL, pre, post, plate, repeatable; EOL options [bff] [cbopt] | RO | Listing (extend: one row kind per comment type); DecompileView comments | `manage-comments` | per-build; each comment carries its donor when propagated | RO | partial |
| L09 | XREFs field: xref hints with delimiter, block, namespace prefix, ref-type letter, group by function, max count, sort [cbopt] | RO | Listing XREF[n] hint → XrefPanel; Peek shows the first 20 | `get-references` | scope one/all: the XrefPanel All builds mode has per-build counts | RO | partial (display options not configurable) |
| L10 | Offset fields: file offset, function offset, image-base offset, block offset [cbopt] | RO | NEW: ListingFieldLayout (optional columns) | catalog action needed (address → file offset) | per-build; file offsets back `section_offset` pinned locators | RO | missing |
| L11 | PCode, Stack Depth, Register Transition, Parallel and Source Map fields [bff] | RO | NEW: ListingFieldLayout (optional columns) | catalog action needed (per-instruction p-code, stack depth, source map) | per-build | RO | missing |
| L12 | Browser Field Formatter: add, remove, move, enable fields and rows; custom formats; reset [bff] | RO | NEW: ListingFieldLayout | none (a per-viewer diff in durable workspace state) | viewer; SplitCompare panes share one layout | PV | missing |
| L13 | Open/close structures and arrays inline; the Field Name field [cb] | RO | Listing (extend: expandable data rows) | `get-data` | per-build; the layout may differ, so show that build's component offsets | RO | partial |
| L14 | Hover popups: reference, truncated text, data type, address, function name, scalar [cb] | RO | Peek (cache only; Alt+↓ or pointer rest) | peek cache (existing reads) | Peek names the counterpart and its locator word | RO | covered |
| L15 | Flow arrows margin: select, navigate along an arrow, disable [cb] | RO | Listing flow column (extend: arrow margin with go-to-source and go-to-target) | `inspect-memory` (mode `disasm`), `get-references` (`includeFlow`) | per-build | RO | partial |
| L16 | Marker margin and navigation margin: bookmarks, selection, highlight, changes, search hits [cb] | RO | Listing gutter marks ("changed by job"); NEW: OverviewBar for the navigation margin | `manage-bookmarks`, `get-references` | per-build markers; logical marks resolve per build via LocatorGlyph | RO | partial |
| L17 | Overview bar, address-type mode [ov] | RO | NEW: OverviewBar | `inspect-memory` (`get-memory-blocks`); catalog action needed for the code-unit type map | side-by-side bars per build in Compare; ImageDeltaMap is the rebuild analog | RO | missing |
| L18 | Entropy overview bar: calculation, palette legend, window [ov] | RO | NEW: OverviewBar (entropy mode, text key with values) | catalog action needed | side-by-side; equal regions across builds are cheap divergence evidence | RO, NP | missing |
| L19 | Cursor text highlight: all matches of the token under the cursor [cb] [cbopt] | RO | Highlight all (`h`, sets A–D) in Listing and DecompileView | none (client, over loaded rows) | per-build; never a cross-build text match | RO | covered |
| L20 | Listing background colors: set a color on a range, navigate colors [lbg] | MUT | MarksList (per-viewer marks with notes) replaces it; color is never meaning here | catalog action needed only to read existing program colors | viewer | PV | partial (replaced on purpose) |
| L21 | Selection: address-set selection, select all, next/previous selected range [sel] | RO | Listing (extend: address-set selection extent, collapsed by Esc); checked set for row batches | none on the client; verbs accept `addressRange` | per-build; changing program clears it (F11) | RO | partial |
| L22 | Select by flow: forward/reverse scoped flow, subroutine, function, dead code [flowsel] | RO | Listing (extend); GraphPane Blocks | catalog action needed | per-build | RO | missing |
| L23 | Select Bytes: select N bytes from the cursor [selbytes] | RO | HexStrip byte selection (maps back to rows) | none | per-build | RO | partial (no count entry) |
| L24 | Selection tables: build a table of ranges from a selection [seltab] | RO | NEW: ResultsTable (ranges mode); MarksList worklist | none | per-build | RO, PV | partial |
| L25 | Highlight from selection: set, add, subtract, clear, navigate [hl] | RO | MarksList worklist; Highlight all covers token highlight only | none | per-build | RO, PV | partial |
| L26 | Clipboard: copy, copy special (addresses, byte strings, labels, comments), paste [clip] | RO+MUT | AccessibleView Copy all; link menu Copy link; paste is a catalog verb | none for copy; catalog action needed for paste | per-build; paste targets one build | RO; paste CAT, 1W | partial |
| L27 | Show Instruction Info: operand objects, inputs and outputs, raw instruction; processor manual [instinfo] | RO | Peek (extend: an instruction-info card on a mnemonic) | catalog action needed (instruction prototype read) | per-build; show the build's language id | RO | missing |
| L28 | Disassembled View: speculative disassembly at a data cursor without committing [disview] | RO | Peek (extend: speculative disassembly, drawn dashed and labelled hypothesis) | catalog action needed (non-committing decode) | per-build | RO, NP | missing |
| L29 | Show References To / From: popup actions for address, code unit and data type [cb] [locref] | RO | XrefPanel (References · Calls · Slots), Line or token scope, in/out direction | `get-references` (`direction` to/from) | scope one/all with per-build counts | RO | covered |
| L30 | Show Thunk Xrefs and Delete Reference from the XREF field [cb] | RO+MUT | XrefPanel; delete through ActionStrip | `get-references` (`resolve-thunk`); catalog action needed for delete | per-build | RO; delete CAT, 1W | partial |
| L31 | Open/close functions: collapse a whole function in the Listing [cb] | RO | Listing (extend: collapsible function body) | none (view state) | viewer | RO, PV | missing |
| N01 | Go To address, label or expression; wildcards; repeat previous go-to [nav] | RO | NavigationBar go-to field; Ctrl/Cmd+G (`:` prefix); CommandPalette | `search-everything`, `manage-symbols` | results carry per-build locator words; an ambiguous name lists every candidate and never picks one | RO | partial (expressions: see N02) |
| N02 | Go To File Offset and address expressions (math, logic, bit operators, symbol names) [nav] [addrx] | RO | NavigationBar (extend: expression and file-offset prefixes) | catalog action needed (expression evaluation, offset mapping) | per-build; a symbol in an expression resolves on the inspected build | RO | missing |
| N03 | Next/previous code unit: instruction, data, undefined, label, function, non-function, matching bytes, bookmark; invert [nav] | RO | Listing (extend: keymap commands for each kind) | `inspect-memory`, `list-functions`, `manage-bookmarks` | per-build | RO | partial (old roots had some; the keymap lacks them) |
| N04 | Next/previous function [nav] | RO | Listing keymap; Functions list order | `list-functions` | per-build order | RO | partial |
| N05 | Navigation history: back/forward, next/previous function in history, clear [nav] | RO | NavigationBar Back, Forward and Recent menu; Alt+←/→ | none (location schema, history state) | history stops carry `build`; a Back that crosses a build switch says so | RO | covered |
| N06 | Program navigation: next/previous program, go to program, last active program [prg-nav] | RO | CounterpartStrip, the build menu, Alt+PageDown/PageUp; SessionTab | `list-project-files` | an explicit build switch keeps the entity (anchor-mapped) or explains its absence | RO | covered |
| N07 | Starting location and initial-analysis navigation options [nav] | RO | NavigationBar restores location from the URL | none | per-build | RO, NA | covered |
| N08 | Split views: a second listing and multiple docked views [dock] | RO | CodeBrowser two center panes; SplitCompare; LayoutPresets | none | side-by-side builds | RO | partial (8080 has no split panes; Open beside opens a new window) |
| N09 | Snapshots: connected (follows location) and disconnected listing, decompiler and graph snapshots; tool connections that share location [snap] [connect] | RO | HeldPane: Following means connected, Held means disconnected; Hold this pane | none | a held pane pins entity × build × address with its basis and flags a basis change | RO | covered (8080: new window) |
| N10 | Byte Viewer formats: hex, chars, address, disassembled, hex short/int/long/long long, integer, octal, binary [bv] | RO | HexStrip (hex and ASCII only) | `inspect-memory` (mode `bytes`) | per-build; anchor-mapped byte range across builds | RO | partial |
| N11 | Byte Viewer options: bytes per line, alignment offset, group size, charset, char width [bvopt] | RO | HexStrip (extend) via NEW: OptionsPanel | none | viewer | PV | missing |
| N12 | Byte Viewer memory editing [bv] | MUT | NEW: PatchEditor | catalog action needed (the inventory found no bounded patch tool; only `execute-script` `setBytes`) | per-build only; never propagated | CAT, CF-dlg, 1W, MC | missing |

### 2. Decompiler

| ID | Ghidra feature | R/M | AgentDecompile mapping | Backend | Multi-variant | Doctrine | Status |
|---|---|---|---|---|---|---|---|
| D01 | Decompiler window: decompiles the function at the cursor, cross-highlights with the Listing [dw] [dintro] | RO | DecompileView, reflected with Listing | `decompile-function` (`get-decompilation`) | per-build; counterpart C in SplitCompare; missing mappings are words, never guesses | RO, NA (a cache miss says "Enter to decompile") | covered |
| D02 | Automatic re-decompile after annotation changes; disable auto refresh [dw] | RO | DecompileView "◷ predates job" marker; Enter re-decompiles | `decompile-function` | per-build; a propagated edit marks each recipient's decompile | RO | covered |
| D03 | Export to C for the current function [dw] | RO | AccessibleView Copy all; link menu Export → NEW: ExportDialog | `export` (format `c`), `decompile-function` | per-build file | CAT (artifact), NP | partial |
| D04 | Decompiler snapshot window [dw] | RO | HeldPane | none | holds entity × build | RO | covered |
| D05 | Eliminate Unreachable Code and Respect Read-only Flags toggles [dw] | RO | DecompileView (extend: toggles) via NEW: OptionsPanel | `decompile-function` (`showUnreachable`, per the inventory) | per-build; the flag is part of the decompile basis | RO | partial |
| D06 | Debug Function Decompilation: XML capture for one function [dw] | RO | DecompileView link menu on the function → an artifact in the dock | catalog action needed | per-build | RO, CAT (artifact) | missing |
| D07 | Graph Data Flow and Graph Control Flow from the decompiler [dw] | RO | GraphPane (extend: a data-flow mode) | `analyze-data-flow`; catalog action needed for the p-code graph | per-build | RO | missing |
| D08 | Mouse actions: click, double-click, ctrl-double-click, middle-click highlight [dw] | RO | DecompileView typed tokens: Enter goes, Shift+Enter opens beside, Alt+↓ peeks, Shift+F10 opens the menu | none | per-build | RO | covered |
| D09 | Rename Variable, Rename Label and Rename Global [dw] | MUT | InlineRename (F2 or Enter on the token) | `rename-variable`, `rename-data-label`, `manage-function` | per-build, then propose→counterparts | CAT, CF-in, 1W, MC, NC | covered |
| D10 | Rename Function from a token [dw] | MUT | InlineRename (link menu Rename…) | `rename-function`, `manage-function` | per-build, then propose→counterparts | CAT, CF-in, 1W, MC, NC | covered |
| D11 | Rename Field of a structure from a token [dw] | MUT | InlineRename on the field token, confirmed by ConfirmDialog (type-wide) | `manage-structures` (`fieldName`, `newFieldName`) | layout-gated: the type may be shared by every use on a build; counterpart types renamed only by proposal | CAT, CF-dlg, 1W, MC, NC | partial |
| D12 | Retype Variable, Retype Global [dw] | MUT | InlineRename (type mode, with completion) | `manage-function` (`set-local-variable-type` per the inventory, `newType`, `datatypeMappings`), `apply-data-type` | layout-gated per build | CAT, CF-in, 1W, MC | covered |
| D13 | Retype Return [dw] | MUT | NEW: SignatureEditor (return row); StorageEditor for return storage | `manage-function` (`prototype`) | layout-gated; callers on the same build change, so confirm | CAT, CF-dlg, 1W, MC | partial |
| D14 | Retype Field [dw] | MUT | NEW: TypeEditor, opened from the field token | `manage-structures` (`newDataType`) | layout-gated; a resize is cross-build | CAT, CF-dlg, 1W, MC | partial |
| D15 | Commit Params/Return: writes the decompiler's recovered prototype to the program [dw] [dann] | MUT | DecompileView link menu on the function name → ActionStrip | catalog action needed | per-build; the prototype can be proposed to counterparts (`migrate-metadata` `propagatePrototype`) behind an ABI gate | CAT, CF-dlg (a callee-signature change), 1W, MC | missing |
| D16 | Commit Local Names: writes decompiler-discovered local names and storage as variable annotations [dw] | MUT | DecompileView link menu → ActionStrip | catalog action needed | per-build | CAT, 1W | missing |
| D17 | Edit Function Signature dialog [dw] [var] | MUT | NEW: SignatureEditor (hosts StorageEditor) | `manage-function` (`prototype`; modes `set_calling_convention` and `set_storage`) | per-build: conventions and registers come from that build's compiler spec; propose→counterparts only through the ABI gate | CAT, CF-dlg, 1W, MC, NC | partial (the source FunctionEditor exists per the inventory; there is no design-system component) |
| D18 | Override Signature, Edit Signature Override, Remove Signature Override at a call site [dw] [dann] | MUT | NEW: SignatureEditor (call-site mode) from the callee token | catalog action needed | per-build and per call site; counterpart call sites only via anchors | CAT, CF-in, 1W | missing |
| D19 | Split Out As New Variable [dw] | MUT | DecompileView link menu Edit group | catalog action needed | per-build | CAT, 1W | missing |
| D20 | Force Field, Adjust Pointer Offset [dw] | MUT | DecompileView link menu; NEW: TypeEditor for the pointer-typedef | catalog action needed | layout-gated | CAT, CF-dlg, 1W | missing |
| D21 | Auto Create Structure and Auto Fill in Structure from variable usage [dw] | MUT | DecompileView link menu → ActionStrip; the result opens NEW: TypeEditor | `manage-structures` (create); catalog action needed for usage-derived layout | per-build; the proposed `CacheEntry` layout is a hypothesis until each build's size check passes | CAT, CF-dlg, 1W, NP | missing |
| D22 | Edit Data Type from a type token [dw] | MUT | the `type=` link → NEW: TypeEditor | `manage-structures`, `manage-data-types` | layout-gated | CAT, CF-dlg, 1W | partial (the link exists; the editor does not) |
| D23 | Comments from the decompiler at a statement address [dw] | MUT | InlineRename (comment mode, with catalog comment kinds) | `manage-comments` | per-build, then propose→counterparts | CAT, CF-in, 1W | covered |
| D24 | Convert constant display (hex, decimal, char, …), Set Equate, Remove Convert/Equate [dw] [eq] | MUT | DecompileView and Listing link menu on a constant → ActionStrip | catalog action needed | per-build; offered to counterparts only when the operand anchors align | CAT, 1W | missing |
| D25 | Highlight: Def-use, Forward Slice, Backward Slice, Forward/Backward Operator Slice [dw] | RO | DecompileView (extend: slice sets drawn as Highlight all sets and labelled with their basis) | `analyze-data-flow` (direction `forward`/`backward`; `find-variable-accesses`) | per-build | RO | partial |
| D26 | Secondary Highlight: persistent multi-token highlights; next/previous highlight [dw] | RO | Highlight all sets A–D with a legend chip | none | per-build | RO, PV | partial (no next/previous command) |
| D27 | Go To Next/Previous Brace [dw] | RO | DecompileView (extend: keymap commands) | none | per-build | RO | missing |
| D28 | Find… in the decompiled function [dw] | RO | DecompileView find (Ctrl/Cmd+F is bound inside a code well) | none (over cached lines) | per-build | RO | covered |
| D29 | References from a token: variable, field, data type, function [dw] | RO | XrefPanel "References to ‹token›" | `get-references`; `manage-data-types` (find uses, per the inventory) | scope one/all | RO | covered |
| D30 | Decompiler options: general, analysis, display and program options [dopt] | RO / program-affecting | NEW: OptionsPanel (display options per viewer; program options only through the catalog) | `decompile-function` (`includeComments`, `includeDisassembly`, …); catalog action needed for program-level options | builds compared on different options are flagged in the ProvenanceStamp basis | PV; program options CAT | missing |
| D31 | Specification extensions: import or remove prototype and call-fixup extensions [dopt] | MUT | NEW: OptionsPanel (extensions section) | catalog action needed | per-build compiler spec; must match that build's language | CAT, CF-dlg, 1W | missing |
| D32 | Decompiler variable annotations: committed program variables vs decompiler-only high variables [dann] [dcon] | RO | DecompileView (extend: the token kind word says "committed" or "decompiler-only") | `decompile-function` | per-build | RO | missing |

Deferred and out of core scope: decompiler taint (source/sink slice tree)
[taint]. It maps to `analyze-data-flow` views later. It is not counted.

### 3. Function Graph, call graph and call trees

| ID | Ghidra feature | R/M | AgentDecompile mapping | Backend | Multi-variant | Doctrine | Status |
|---|---|---|---|---|---|---|---|
| G01 | Function Graph: basic blocks as vertices, typed edges, block navigation and info [fg] | RO | GraphPane Blocks | catalog action needed (basic-block and edge read) | per-build; CandidateAlignment aligns blocks across builds on anchors | RO, NA | partial |
| G02 | Vertex grouping, path highlight (paths from/to, scoped flow), selection from paths and blocks [fg] | RO | GraphPane (extend) | catalog action needed | per-build | RO | missing |
| G03 | Layouts (nested code, flow chart), zoom, satellite view, saved view state [fgl] [vg] | RO | GraphPane (zoom, pan, bounded drawing, list form) | none | viewer | RO, PV | partial (one layout) |
| G04 | Editing from graph vertices (vertex listings are editable) [fg] | MUT | GraphPane nodes are links; edits happen in the Listing | as each edit | per-build | CAT | partial |
| G05 | Function Call Graph: level edges, satellite, navigate on incoming location [fcg] | RO | GraphPane Calls (depth 1–3, bounded, "truncated" in words) | `get-call-graph` (mode `graph`) | per-build; the root maps to counterparts through anchors | RO | covered |
| G06 | Function Call Trees: incoming and outgoing trees, recursive expand, navigate on location change [ct] | RO | CallHierarchy (the Calls mode of References) | `get-call-graph` (modes `tree`, `callers`, `callees`; `get-call-tree`) | per-build column with locator words | RO | covered |
| G07 | Call tree filtering, depth, duplicate and thunk handling [ct] | RO | CallHierarchy (depth up to 3; recursion marked) | `get-call-graph` | per-build | RO | partial |
| G08 | Program Graph: block flow, code flow, calls, data references; reuse or append a graph [pg] | RO | GraphPane (extend: bounded program scope) | `get-call-graph`; catalog action needed for block and code flow | per-build | RO | missing |
| G09 | Data Graph: references from a data item [dg] | RO | GraphPane (extend: data-reference mode) | `get-references` | per-build | RO | missing |
| G10 | Graph export: GraphML, DOT, GML, JSON, CSV and other formats [gexp] | RO (file) | GraphPane → NEW: ExportDialog | catalog action needed | per-build; the export records its basis | CAT (artifact) | missing |
| G11 | Graph display popups: select vertices and edges, filter, show location [gdisp] [gintro] [gsvc] | RO | GraphPane list form (APG tree) | none | per-build | RO | partial |
| G12 | Function Comparison window: listing, decompiler and graph diff of N functions; navigate differences [fcmp] | RO | SplitCompare (F7/Shift+F7), CandidateAlignment | `decompile-function` per side; `match-function` | side-by-side, anchor-mapped, N-way in Compare | RO, NP (aligned ≠ equivalent) | covered |
| G13 | Common callers of several functions (Ghidra: Call Trees on a selection) [ct] | RO | CallHierarchy (extend: multi-root) | `get-call-graph` (mode `common_callers`) | per-build | RO | missing |

### 4. Symbol Tree, Symbol Table and references

| ID | Ghidra feature | R/M | AgentDecompile mapping | Backend | Multi-variant | Doctrine | Status |
|---|---|---|---|---|---|---|---|
| S01 | Symbol Tree hierarchy: Imports, Exports, Functions, Labels, Classes, Namespaces [st] | RO | NEW: SymbolTree (the Symbols, Imports and Exports navigator scopes) | `manage-symbols`, `list-imports`, `list-exports` | a logical node shows per-build presence with LocatorGlyph | RO | partial (search exists; hierarchy is partial per the inventory) |
| S02 | Symbol Tree edits: create namespace or class, convert namespace to class, move by drag or cut/paste, delete, rename [st] | MUT | NEW: SymbolTree; InlineRename (F2); ActionStrip for move and delete | `manage-symbols`, `rename-function` | per-build, then propose→counterparts (namespace path per field) | CAT, CF-in (rename), CF-dlg (move or delete batch), 1W, MC, NC | partial (rename only) |
| S03 | External locations and libraries: create library, set external program, create/edit external location, external program names [st] [extn] | MUT | NEW: SymbolTree (Imports node) | catalog action needed | program-local | CAT, 1W | missing |
| S04 | Symbol Tree navigation mode and snapshot/clone [st] | RO | Following vs HeldPane | none | per-build | RO | covered |
| S05 | Symbol Table: every symbol with name, location, type, namespace, source, reference count, offcut; filter queries [stab] | RO | NEW: ResultsTable (symbols) in the Symbols navigator scope | `manage-symbols`, `search-everything` (scope `symbols`) | logical rows with per-build columns, or scope one | RO | partial |
| S06 | Symbol Table actions: rename, delete symbols or references, pin, set primary, make selection, temporary tables [stab] [stt] | MUT | NEW: ResultsTable + ActionStrip (checked set) | `manage-symbols`, `create-label` (`setAsPrimary`) | per-build | CAT, CF-dlg (batch delete), 1W, MC | partial |
| S07 | Symbol References panel: references to, instructions from, data from; delete a reference [sref] | RO+MUT | XrefPanel; delete through ActionStrip | `get-references`; catalog action needed for delete | scope one/all | RO; delete CAT, 1W | partial |
| S08 | Location References: references to an address, code unit, data type or field; results window [locref] | RO | XrefPanel; a type link lists its uses | `get-references`, `manage-data-types` | scope one/all with per-build counts | RO | covered |
| S09 | Labels: add/edit, namespace chooser, remove, set primary [lbl] | MUT | InlineRename (F2 on a label); Listing link menu | `create-label`, `manage-symbols`, `rename-data-label` | per-build, then propose→counterparts at anchor-mapped addresses | CAT, CF-in, 1W, MC, NC | covered |
| S10 | Label history [lbl] | RO | EntityTimeline (name edits); NameProvenance | catalog action needed (the program's label history) | per-build | RO | partial |
| S11 | Set external entry point [lbl] | MUT | Listing link menu → ActionStrip | catalog action needed | program-local | CAT, 1W | missing |
| S12 | Namespaces and classes for functions and labels [st] [var] | MUT | NEW: SymbolTree; NEW: SignatureEditor namespace field | `manage-function` (namespace, per the inventory), `manage-symbols` | per-build; the class is a logical entity across builds | CAT, 1W, NC | partial |
| S13 | Demangled names and demangling [aa] | MUT | NameProvenance (authentic-symbol tier) | `manage-symbols` (`demangleAll`) | per-build | CAT, NA | partial |

### 5. Data Type Manager and type editors

| ID | Ghidra feature | R/M | AgentDecompile mapping | Backend | Multi-variant | Doctrine | Status |
|---|---|---|---|---|---|---|---|
| T01 | Data Type Manager tree: built-in, program, file (.gdt) and project archives; categories; filter [dtm] [dtmw] | RO | NEW: TypeManager (a Types navigator scope) | `manage-data-types` (archives, categories) | logical type rows with per-build presence and size columns | RO | partial (a types pane exists in old roots per the inventory) |
| T02 | Archive lifecycle: open, create, close, set architecture, save, archive undo/redo, delete [dtm] | MUT | NEW: TypeManager | catalog action needed | a shared archive is the natural cross-build type carrier | CAT, CF-dlg, 1W (one archive writer) | missing |
| T03 | Source-archive sync: update, commit, revert, disassociate, refresh indicators, archive paths [dtma] | MUT | NEW: TypeManager (sync state column) | catalog action needed | the primary way to sync types per build; per-build sync state; commits are layout-gated | CAT, CF-dlg, 1W | missing |
| T04 | Categories: create, rename, delete, move, copy [dtm] | MUT | NEW: TypeManager | catalog action needed (`manage-data-types` `categoryPath` is read-only in the docs) | per-build or archive | CAT, 1W | missing |
| T05 | Data types: create, rename, edit, delete, move, copy [dtmw] | MUT | NEW: TypeManager + NEW: TypeEditor | `manage-structures`, `manage-data-types`, `create-structure`, `edit-structure`, `create-enum`, `edit-enum` | layout-gated per build | CAT, CF-dlg, 1W, MC, NC | partial |
| T06 | Replace and Merge data types; conflict resolution mode [dtmw] | MUT | NEW: TypeManager → ConfirmDialog with use counts per build | catalog action needed | cross-build ConfirmDialog; every use on each build changes | CAT, CF-dlg, 1W, MC | missing |
| T07 | Find types by name, by size, enums by value, structures by size or by offset [dtmw] | RO | NEW: TypeManager filters | `manage-data-types`, `manage-structures` (`nameFilter`), `search-everything` (scope `data_types`) | scope one/all with per-build hit columns | RO | partial |
| T08 | Apply Function Data Types and Capture Function Data Types [dtmw] | MUT | NEW: TypeManager → ActionStrip | catalog action needed (the API reference documents `ApplyFunctionDataTypesCmd`) | per-build batch | CAT, CF-dlg, 1W | missing |
| T09 | Export data types, create labels from enums, show base type, display as graph [dtmw] | RO+MUT | NEW: TypeManager actions | `export` (`includeTypes`); catalog action needed for the rest | per-build | RO; label creation CAT | missing |
| T10 | Structure/union editor: component grid, name, description, size, alignment, packing, bitfields, flexible arrays, insert, move, duplicate, delete, clear, create array, unpackage, create from selection, go to offset, editor undo/redo [se] | MUT | NEW: TypeEditor (composite mode) | `manage-structures` (`fields`, `fieldName`, `dataType`, `offset`, `bitfield`, `packed`, `newLength`, …) | layout-gated: the edit applies to one build's type manager or a shared archive; a per-build size and offset delta table precedes Save; propose→counterparts only when layouts are identical | CAT, CF-dlg (resize, overwrite, clear), 1W, MC, NC | partial (backend exists per the inventory; no editor) |
| T11 | Enum editor: entries, values, hex toggle, add, delete, apply [ee] | MUT | NEW: TypeEditor (enum mode) | `manage-data-types`, `create-enum`, `edit-enum` | side-by-side value sets per build | CAT, CF-dlg, 1W, NC | partial |
| T12 | Typedefs, pointers (with pointer-typedef settings), arrays [data] [dtm] | MUT | NEW: TypeEditor (typedef and pointer modes) | `manage-data-types`, `apply-data-type` (array syntax) | layout-gated; pointer width differs by build language | CAT, 1W | partial |
| T13 | Function definitions: create one from a function [var] | MUT | NEW: TypeEditor (function-definition mode) | catalog action needed | per-build | CAT, 1W | missing |
| T14 | Data type chooser: completion, typed pointer and array creation, browse [dtsel] | RO | InlineRename type field with completion from the build's type manager | `manage-data-types` (list) | per-build completion; warns when the type is absent on a counterpart | RO | partial |
| T15 | C-Parser: parse headers into types [cparse] | MUT | NEW: TypeManager (import header); a C-definition validation path exists per the inventory | `manage-structures` (`cDefinition`, `headerContent`) | into one build or a shared archive; per-build size validation | CAT, CF-dlg, 1W, NP (a parse is not layout proof) | partial |
| T16 | Data Type Preview window: types previewed at the cursor without applying [dtp] | RO | Peek (extend: type-at-address preview) | `get-data`, `inspect-memory` (mode `data`) | anchor-mapped: the same type previewed at each counterpart address | RO, NP | missing |
| T17 | Data types table: flat table with a program-types filter [dtt] | RO | NEW: ResultsTable (types) | `manage-data-types` | per-build columns | RO | partial |
| T18 | Favorites, recently used types, cycle groups [data] | RO | CommandPalette recents; keymap cycle commands | none | viewer | PV | missing |
| T19 | Structure and union editor tool options: hex display, and related options [se] | RO | NEW: OptionsPanel | none | viewer | PV | missing |

### 6. Program Trees, Memory Map, relocations, equates, registers

| ID | Ghidra feature | R/M | AgentDecompile mapping | Backend | Multi-variant | Doctrine | Status |
|---|---|---|---|---|---|---|---|
| P01 | Program Tree folders and fragments: create, delete, rename, move code units, merge, sort, select, restrict the view [ptree] | RO+MUT | NEW: ProgramTreeView (navigator scope); ContainerTree covers file containers only | catalog action needed | per-build; a logical module grouping may map to fragments | CAT, 1W | missing |
| P02 | Program tree views and organizations: default tree, subroutine, dominance, complexity depth [pview] [porg] | MUT | NEW: ProgramTreeView | catalog action needed | per-build | CAT, 1W | missing |
| P03 | Memory Map table: name, range, length, RWX, volatile, overlay, type, initialized, source, comment [mm] | RO | NEW: MemoryMapTable (the Sections navigator scope) | `inspect-memory` (`get-memory-blocks`) | side-by-side section maps per build; ImageDeltaMap for a rebuild | RO | partial |
| P04 | Memory block edits: rename, permissions, volatile, artificial, initialize, comment; add, move, split, expand, merge, delete; set image base; rename overlay [mm] | MUT | NEW: MemoryMapTable → ActionStrip + ConfirmDialog | catalog action needed | program-local; never propagated; an image-base change invalidates pinned locators, and the dialog names the affected anchors | CAT, CF-dlg, 1W, MC, NA | missing |
| P05 | Relocation table [reloc] | RO | NEW: ResultsTable (relocations) | catalog action needed | program-local; feeds ObjectDiff's relocation-aware equality | RO | missing |
| P06 | Equates: view table, rename, remove, edit/show/apply enum; convert display (signed/unsigned decimal, hex, octal, char, binary, float, double) [eq] | RO+MUT | NEW: ResultsTable (equates); Listing link menu on operands | catalog action needed | per-build; names offered to counterparts only at anchor-aligned operands | CAT, 1W, NC | missing |
| P07 | Register Manager: register and context values over ranges; set, clear, delete ranges [reg] | RO+MUT | NEW: RegisterValuesEditor | catalog action needed | program-local; context registers differ by build language | CAT, CF-dlg, 1W, NA (re-disassembly follows only when admitted) | missing |
| P08 | Processor language: view and change language or compiler spec; installed processors [lang] [procs] | MUT | build crumb Peek shows the language id; a change goes through ActionStrip + ConfirmDialog | `change-processor`, `list-processors` | program-local; re-disassembly requires admission | CAT, CF-dlg, 1W, NA | partial |
| P09 | Program options and About Program: metadata, compiler, hashes, properties [popt] [about] | RO | build crumb Peek; the evidence rail build header | `get-current-program`, `open` | per-build; hashes identify builds | RO | covered |
| P10 | Block models: basic, isolated entry, multiple entry, partitioned, overlapped [blk] | RO | GraphPane (extend: model selector) | catalog action needed | per-build | RO | missing |
| P11 | Validate Program: post-analysis problem detection [val] | RO | ProblemsList (findings as predicates, typed links) | catalog action needed | per-build | RO | missing |
| P12 | Property Viewer: program properties at addresses [prop] | RO | Peek (extend) | catalog action needed | per-build | RO | missing |

### 7. Strings, data, bookmarks, comments, labels

| ID | Ghidra feature | R/M | AgentDecompile mapping | Backend | Multi-variant | Doctrine | Status |
|---|---|---|---|---|---|---|---|
| A01 | Defined Strings table: columns, make selection, refresh, settings [dstr] | RO | NEW: ResultsTable (strings) in the Strings navigator scope; Outline Strings for the current function | `manage-strings` (mode `list`, `includeReferencingFunctions`) | logical string rows across builds matched by content, with per-build addresses | RO | partial |
| A02 | Defined Data window: all defined data, type filter, make selection [dwin] | RO | NEW: ResultsTable (defined data) | catalog action needed for enumeration; `get-data` per address | per-build | RO | missing |
| A03 | Translate strings and charsets; translation services [tr] [charsets] [libre] | MUT | ResultsTable (strings) row action | catalog action needed | per-build | CAT | missing |
| A04 | Bookmarks: add in the Listing; categories and types; Bookmarks window [bm] | RO+MUT | MarksList: the program Bookmarks scope (read-only) and per-viewer marks; saving a program bookmark posts on Run | `manage-bookmarks` | program-local per build; logical marks resolve per build; program bookmarks go to counterparts only by proposal (`migrate-metadata` `propagateBookmarks`) | CAT, 1W, PV (marks) | partial |
| A05 | Bookmarks window actions: edit category and description, remove, filter, select [bm] | RO+MUT | MarksList (extend: edit and remove program bookmarks through ActionStrip) | `manage-bookmarks` (`removeAll`, `categories`, `types`) | per-build | CAT, CF-dlg (bulk remove), 1W | partial |
| A06 | Comments: set or edit EOL, pre, post, plate, repeatable; delete [cm] | MUT | InlineRename (comment mode with the catalog's comment kinds) | `manage-comments` (`commentType`) | per-build, then propose→counterparts (PropagationTransfer comment field) | CAT, CF-in, 1W, MC | covered |
| A07 | Comment history [cm] | RO | EntityTimeline (extend: comment edits) | catalog action needed (the program's comment history) | per-build | RO | partial |
| A08 | Comment window: table of every comment [cw] | RO | NEW: ResultsTable (comments) | `manage-comments` (`searchText`, `pattern`), `search-everything` (scope `comments`) | scope one/all | RO | partial |
| A09 | Comment annotations: symbol, address and URL links inside comments [ann] | RO | typed links rendered in comment text (linked views) | none | links resolve on the same build | RO | partial |
| A10 | Field names: Edit Field Name dialog for data components [fieldnames] | MUT | InlineRename on the Listing field-name cell | `manage-structures` (`newFieldName`) | layout-gated; type-wide, so ConfirmDialog | CAT, CF-dlg, 1W, NC | partial |
| A11 | Labels from the Listing: rename a label in place [lbl] | MUT | InlineRename (F2) | `create-label`, `rename-data-label` | per-build, then propose→counterparts | CAT, CF-in, 1W, NC | covered |

### 8. Functions

| ID | Ghidra feature | R/M | AgentDecompile mapping | Backend | Multi-variant | Doctrine | Status |
|---|---|---|---|---|---|---|---|
| F01 | Create function, re-create function, create multiple functions [fn] | MUT | Listing link menu → ActionStrip | `manage-function` (create, per the inventory); `list-functions` (`get-undefined-function-candidates`) | per-build; propose on counterparts only at accepted anchors | CAT, 1W, MC | partial |
| F02 | Delete function [fn] | MUT | ActionStrip + ConfirmDialog (destructive) | `manage-function` (delete, per the inventory) | per-build | CAT, CF-dlg, 1W | partial |
| F03 | Rename function [fn] | MUT | InlineRename (F2 on the EntityRow or the composite header name) | `rename-function`, `manage-function` | per-build, then propose→counterparts | CAT, CF-in, 1W, MC, NC | covered |
| F04 | Thunk functions: set thunk target, follow thunk [fn] | RO+MUT | NEW: SignatureEditor thunk field; XrefPanel | `manage-function` (thunk target, per the inventory); `get-references` (`resolve-thunk`) | per-build | CAT, 1W | partial |
| F05 | External functions [fn] | RO | NEW: SymbolTree (Imports) | `list-imports`, `get-references` (`find-import-references`) | per-build; the same import on each build forms a logical row | RO | partial |
| F06 | Calling convention from the program's compiler spec [var] | MUT | NEW: SignatureEditor convention list | `manage-function` mode `set_calling_convention` | per-build; never borrow another build's spec | CAT, CF-dlg, 1W | partial (no design-system component) |
| F07 | Custom storage: parameter and return storage; the Edit Parameter Storage dialog [var] | MUT | StorageEditor | `manage-function` mode `set_storage` | layout-gated per build: registers come from that build's spec; no storage propagation without an ABI gate | CAT, CF-in, 1W, MC | covered (the inventory's parameter-storage fix awaits live acceptance) |
| F08 | Varargs, No Return and Inline attributes [var] | MUT | NEW: SignatureEditor flags | `manage-function` (flags, per the inventory) | per-build; No Return changes callers' flow, so confirm | CAT, CF-dlg (No Return), 1W | partial |
| F09 | Call-fixup [var] | MUT | NEW: SignatureEditor call-fixup picker from the build's spec | `manage-function` (call fixup, per the inventory) | per-build spec | CAT, 1W | partial |
| F10 | Function purge and stack depth change: set and remove [fn] | MUT | NEW: SignatureEditor (purge); Listing link menu (stack depth) | catalog action needed | per-build | CAT, 1W | missing |
| F11 | Variables: rename, retype, delete; define data type [var] | MUT | InlineRename; CodeBrowser Outline Locals | `manage-function` (`rename-variable`, `set-local-variable-type`, per the inventory) | per-build | CAT, CF-in, 1W, NC | partial (delete missing) |
| F12 | Function repeatable comment [fn] | MUT | InlineRename (repeatable kind) | `manage-comments` | per-build, then propose→counterparts | CAT, CF-in, 1W | covered |
| F13 | Stack frame editor: local size, parameter offset and size, stack variables (create, delete, clear, retype, array), hex display [stack] | MUT | NEW: StackFrameEditor | catalog action needed (`manage-function` variable operations cover part) | side-by-side frames per build; layouts differ by compiler | CAT, CF-dlg, 1W, MC, NC | missing |
| F14 | Function tags: create, delete, edit; add to or remove from functions; load external tags; tag window [ftag] | MUT | Functions list tag filter (FilterChip); NEW: ResultsTable (tags); ActionStrip | `manage-function-tags`; `list-functions` (`filterByTag`, `untagged`) | a tag on a logical entity is offered to each accepted counterpart (`match-function` `propagateTags`) | CAT, 1W | partial |
| F15 | Function window: every function, navigate on incoming location, make selection, compare selected [fwin] | RO | the one Functions list (EntityRow grid) | `list-functions`, `get-functions` | logical rows with counterpart counts; Compare selected opens SplitCompare | RO | covered |
| F16 | Function signature source (default, analysis, imported, user-defined) [bff] | RO | NameProvenance tier beside the signature | `get-function` | per-build | RO | missing (source not displayed) |

### 9. Disassembly, clearing, data creation, references

| ID | Ghidra feature | R/M | AgentDecompile mapping | Backend | Multi-variant | Doctrine | Status |
|---|---|---|---|---|---|---|---|
| E01 | Disassemble, static and restricted disassembly, processor-mode variants, processor options [dis] | MUT | Listing link menu on undefined bytes → ActionStrip | catalog action needed (the script namespace has `disassemble` per the inventory; there is no bounded tool) | per-build | CAT, 1W, NA (follow-on analysis only if admitted) | missing |
| E02 | Modify instruction flow (branch, call, call-return, return overrides) and modify instruction length [dis] [dann] | MUT | Listing link menu → NEW: ReferenceEditor (flow section) | catalog action needed | per-build; changes only that build's decompile | CAT, CF-dlg, 1W | missing |
| E03 | Fallthrough override: set, auto override, clear [fall] | MUT | NEW: ReferenceEditor (fallthrough field) | catalog action needed | per-build | CAT, 1W | missing |
| E04 | Clear Code Bytes, Clear With Options (symbols, comments, properties, instructions, data, references, functions, registers, equates, bookmarks), Clear Flow and Repair [clr] | MUT | ActionStrip + ConfirmDialog (destructive) | catalog action needed (the script's `clearListing` only) | per-build; never cross-build | CAT, CF-dlg, 1W, MC | missing |
| E05 | Create data: apply built-in and user types; data settings (format, endianness, charset) [data] | MUT | Listing link menu "Set data type…" → InlineRename (type mode) | `apply-data-type`, `manage-data-types` | layout-gated; propose at counterpart addresses (anchor-mapped) | CAT, CF-in, 1W, MC | partial (data settings missing) |
| E06 | Create array, pointer, string; create structure from a selection; quick Edit Field dialog [data] | MUT | Listing link menu → ActionStrip; NEW: TypeEditor | `apply-data-type`, `manage-structures` | layout-gated; array counts never copied blindly between builds | CAT, CF-dlg (structure from selection), 1W | partial |
| E07 | Add/Edit References dialog: memory, external, stack and register panels; ref-type; operand; primary [refs] [refs-intro] | MUT | NEW: ReferenceEditor | catalog action needed (`get-references` is read-only) | per-build | CAT, CF-in, 1W, MC | missing |
| E08 | Create default reference; delete references from a code unit [refs] | MUT | Listing link menu → ActionStrip | catalog action needed | per-build | CAT, 1W | missing |
| E09 | Add memory references from a selection; Create Offset References Table [refs] [offtab] | MUT | NEW: ReferenceEditor → ActionStrip batch | catalog action needed | per-build | CAT, CF-dlg, 1W | missing |
| E10 | Stack and register references and their variable binding [refs] | MUT | NEW: ReferenceEditor (stack and register panels) | catalog action needed | per-build; storage from the build's spec | CAT, 1W | missing |
| E11 | Make address tables and disassemble their targets [saddr] | MUT | ResultsTable (address tables) → ActionStrip | catalog action needed | per-build | CAT, CF-dlg, 1W, NA | missing |

### 10. Searches

| ID | Ghidra feature | R/M | AgentDecompile mapping | Backend | Multi-variant | Doctrine | Status |
|---|---|---|---|---|---|---|---|
| Q01 | Search Memory: hex, binary, string, regex, decimal, float, double; incremental forward/back; combined searches; scan controls [smem] [sfmt] | RO | NEW: SearchWorkbench (memory mode) → NEW: ResultsTable | catalog action needed (byte-pattern search is not in the documented tool set) | scope one/all; per-build hit columns; one pattern at different addresses is expected | RO | missing |
| Q02 | Search Program Text: labels, comments, mnemonics, operands, data fields; incremental and search all; regular expression syntax [stext] [regex] [searching] | RO | NEW: SearchWorkbench (text mode); CommandPalette | `search-everything` (scopes `comments`, `symbols`, `disassembly`, …) | scope one/all | RO | partial |
| Q03 | Search for Matching Instructions: masks built from a selection [smnem] | RO | NEW: SearchWorkbench (instruction mode) | `search-code` | scope one/all; a masked pattern is a candidate identity channel only | RO, NP | partial |
| Q04 | Instruction Pattern Search dialog: instruction table, preview, bounds, manual entry [sinstr] | RO | NEW: SearchWorkbench (instruction mode) | `search-code` | scope one/all | RO | partial |
| Q05 | Search for Scalars: specific value or range; selection scope; scalar table filters [scalar] | RO | NEW: SearchWorkbench (scalar mode) → ResultsTable | `search-constants` (modes `specific`, `range`, `common`) | scope one/all with per-build hits | RO | partial |
| Q06 | Search for Strings: minimum length, alignment, terminator, charset; make strings; encoded strings [sstr] | RO+MUT | NEW: SearchWorkbench (string mode); a "Make string" row action | `manage-strings`, `search-everything` (scope `strings`); catalog action needed to make a string | scope one/all | RO; make CAT, 1W | partial |
| Q07 | Search for Direct References: scan memory for address values; alignment filter [sdref] | RO | NEW: SearchWorkbench (direct-reference mode) | catalog action needed | per-build (address values are build-specific) | RO | missing |
| Q08 | Search for Address Tables: minimum length, alignment, skip [saddr] | RO | NEW: SearchWorkbench (address-table mode) | catalog action needed | per-build | RO | missing |
| Q09 | Search results window: navigation, marker margin, rename, make selection, remove items, selection navigation [sres] | RO | NEW: ResultsTable; MarksList worklist (F8 stepping); FilterChip | none | per-build hit columns | RO, PV | partial |
| Q10 | Search and Replace: labels, comments, types, namespaces, regex; apply changes [srepl] | MUT | NEW: SearchWorkbench (replace mode) → ActionStrip batch + ConfirmDialog | catalog action needed for the batch replace (search via `search-everything`) | a per-build preview; across builds, a cross-build ConfirmDialog | CAT, CF-dlg, 1W, MC, NC | missing |
| Q11 | Wildcard assembler patterns for instruction search [wasm] | RO | NEW: SearchWorkbench (instruction mode, wildcard syntax) | catalog action needed | scope one/all | RO | missing |
| Q12 | Search Decompiled Text across functions; select matching functions [dtf] | RO | NEW: SearchWorkbench (decompiled-text mode) → ResultsTable | `search-code` (`search-decompilation`), `search-everything` (scope `decompilation`) | scope one/all with per-build hit columns; never decompiles builds that have not been decompiled without saying so | RO, NA | partial |

### 11. Analysis

| ID | Ghidra feature | R/M | AgentDecompile mapping | Backend | Multi-variant | Doctrine | Status |
|---|---|---|---|---|---|---|---|
| Z01 | Auto analysis on import or open; Ask To Analyze [aa] | MUT | WorkflowControl (pause/resume admission; no Start); ImportAdmission | `analyze-program` (`force` only for a deliberate reanalysis), `manage-workflow` (`prepare`) | per-build admission; valid receipts reused | NA, 1W | covered |
| Z02 | Analyzer list and options: enable, disable, per-analyzer options, saved configurations [aa] | MUT | NEW: AnalyzerPanel (reads the current configuration; changes through the catalog) | catalog action needed | analysis options should match across builds; per-build configuration differences are shown | CAT, CF-dlg, NA | missing |
| Z03 | Analyze All Open [aa] | MUT | workflow scope; never a per-stage button | `manage-workflow` | corpus admission; one writer per project | NA, 1W | covered |
| Z04 | One-shot analysis: one analyzer on a selection [aa] | MUT | ActionStrip bound to the selection | catalog action needed | per-build | CAT, 1W, NA (explicit only) | missing |
| Z05 | Analysis log and background task progress [aa] [showlog] [prg-ann] | RO | ActivityRecord in the dock (Logs, Jobs) | `read-workspace-activity` | per-build jobs | RO | covered |
| Z06 | Headless analyzer [headless-help] [headless] | MUT | no UI; admitted through the workflow | `manage-workflow` | corpus | NA, 1W | covered |
| Z07 | Load PDB (symbol servers, parser options) or external DWARF debug files; SARIF import [pdb] [loadpdb] [dwarf] [sarif] | MUT | ImportAdmission; ContextPlacement for context pieces | catalog action needed (`export` writes SARIF; the import path is not documented) | per-build (debug info is build-specific); the NameProvenance debug-info tier | CAT, 1W | partial |
| Z08 | Demangler, aggressive instruction finder and other prototype analyzers [aa] | MUT | NEW: AnalyzerPanel | catalog action needed | per-build | CAT, NA | missing |
| Z09 | Source files table and source map entries [srcf] | RO | NameProvenance debug-info witness; SourceRepairDiff | catalog action needed | per-build | RO | partial |

### 12. Patching, Program Diff, Version Tracking

| ID | Ghidra feature | R/M | AgentDecompile mapping | Backend | Multi-variant | Doctrine | Status |
|---|---|---|---|---|---|---|---|
| X01 | Assembler: Patch Instruction, Assemble…, Patch Data [asm] | MUT | NEW: PatchEditor (original-byte preview, exact target, confirm, post-write read) | catalog action needed | per-build only; never propagated; patching the original is not recovery | CAT, CF-dlg, 1W, MC | missing |
| X02 | Program Diff: open the diff view; determine differences (bytes, code units, references, comments, symbols, functions, bookmarks, properties, context) over ranges; navigate; select [diff] | RO | SplitCompare (entity level); ObjectDiff | `match-function`; catalog action needed for program-level range diff | build-a vs build-c aligned by anchors, not raw addresses | RO, NP | partial |
| X03 | Apply or ignore differences; apply settings (replace, merge, ignore per category) [diff] [vt-apply] | MUT | PropagationTransfer (per field) + ConfirmDialog | `migrate-metadata` (`propagateNames`, `propagateTags`, `propagateComments`, `propagatePrototype`, `propagateBookmarks`) | per recipient gate; blocked recipients keep their value | CAT, CF-dlg, 1W, MC | partial |
| X04 | Viewing difference details at a location [diff] | RO | SplitCompare difference Peek | none beyond X02 | side-by-side | RO | missing |
| X05 | Version Tracking sessions: correlators (exact bytes, instructions, mnemonics, symbol name, data, references, implied, manual, BSim), matches table, markup items, accept, apply markup, dual listing [vt] [vtcorr] [vtmatch] [vtmark] [gvt] [vt-wiz] [vt-flow] [vt-pre] [vt-fn] [vt-impl] [vt-rel] | RO+MUT | MatchReview, ReviewDetail, CandidateAlignment, CounterpartMatrix, PropagationTransfer | `match-function`, `migrate-metadata`, `bsim-report`; stage-1 catalog verbs `corpus.match-pair` and `corpus.extract-stabs` (the consolidated plan) | the product's native N-way form; accepted edges drive propagation | CAT, CF-dlg (decisions), 1W, NP (similarity proposes; evidence accepts) | covered |
| X06 | Auto Version Tracking [vt] [vt-auto] | MUT | pipeline stage 1 (automatic, no button) | `manage-workflow` | corpus | NA, 1W | covered |
| X07 | Version Tracking manual match: create, accept, apply [vt-tool] | MUT | ReviewDetail decision controls | catalog action needed for a manual edge | the identity edge between two builds | CAT, CF-dlg, 1W | partial |
| X08 | Function Bit Patterns Explorer: mine function-start byte patterns [fbp] | RO | not planned | catalog action needed | across builds | RO | missing |

### 13. Scripting

| ID | Ghidra feature | R/M | AgentDecompile mapping | Backend | Multi-variant | Doctrine | Status |
|---|---|---|---|---|---|---|---|
| C01 | Script Manager: category tree, table, filter, run, run last, quick launcher, create, rename, delete, key binding, directories [sm] [scriptdev] | MUT | NEW: ScriptConsole (advanced; gated by the catalog) | `execute-script` | runs against one explicitly targeted build | CAT, CF-dlg (unrestricted mutation), 1W | partial |
| C02 | Console: output, scroll lock, clear, find, navigation from addresses [con] | RO | ActivityRecord log tail with typed links | `read-workspace-activity` | per job | RO | covered |
| C03 | PyGhidra interpreter: interactive session, interrupt, reset [pyi] | MUT | NEW: ScriptConsole (REPL mode) | `execute-script` | one build | CAT, 1W | partial |
| C04 | Bundle Manager: script source bundles, enable, clean, refresh [bun] | MUT | not planned | catalog action needed | none | none | missing |
| C05 | Script key bindings and Quick Action (Ctrl-3) launcher [sm] [kbn] | RO | CommandPalette actions from `GET /api/v1/actions` | catalog | none | RO | missing (scripts are not catalog entries) |

### 14. Undo, transactions, multi-user, import and export

| ID | Ghidra feature | R/M | AgentDecompile mapping | Backend | Multi-variant | Doctrine | Status |
|---|---|---|---|---|---|---|---|
| V01 | Undo/Redo of program transactions [undo] | MUT | NEW: EditHistory (per-build transaction list; Undo and Redo as catalog verbs); EntityTimeline shows edits | catalog action needed | per-build; undoing a propagated edit is per recipient | CAT, CF-dlg, 1W | missing |
| V02 | Transactions and modification conflicts [undo] | MUT | ActionStrip → OutcomeCell; the StateNotice conflict state | `resolve-modification-conflict` | per-build | MC, 1W | covered |
| V03 | Save, Save As, Save All [save] | MUT | durable, crash-safe saves (the consolidated plan §4.7) | catalog action needed for explicit save of a program | per-build | CAT, 1W | partial |
| V04 | Multi-user repository: connect, add to version control, check out, check in, undo checkout, update, version history, view/find checkouts, undo hijack; server connection [vc] [fe] [gserver] | MUT | NEW: VersionControlPanel (per-build checkout state); OwnershipPanel for exclusive checkouts | `checkout-program`, `checkin-program`, `checkout-status`, `sync-project`, `svr-admin` | per-build domain file; an exclusive checkout is the one-writer lock | CAT, CF-dlg (check-in), 1W | partial |
| V05 | Merge on check-in: auto merge; resolve conflicts in memory, trees, types, context, listing, externals, properties [merge] | MUT | MergeReview (adapted to check-in conflicts) | `checkin-program`; catalog action needed for conflict choices | per-build | CAT, CF-dlg, 1W, MC | partial |
| V06 | Exporters: ASCII, C/C++, GZF, GDT, HTML, hex-record formats, Original File, Raw Bytes, XML, SARIF [exp] | RO (file) | NEW: ExportDialog (format, options, build; the artifact lands in the dock) | `export` (formats `gzf`, `c`, `cpp`, `sarif`, `xml`, `html`, `ascii`); `manage-workflow` (`export-source`) | one job per build; a batch across builds confirms | CAT (artifact), NP (exported C ≠ recovered source) | partial (GDT, hex records, original file and raw bytes are not documented) |
| V07 | Importers: import file, batch import, load libraries, add to program, per-format options, language and compiler choice, library search path [imp] | MUT | ImportAdmission | `import-binary`, `open`, `list-processors` | variant grouping comes from match evidence | CAT, NA | covered |
| V08 | File System Browser: browse containers, import from them, export, view as text or image [fsb] | RO | ContainerTree | `export-context` | per container | RO | covered |
| V09 | Project window and program files: create, open, reopen, close, delete projects; data tree and table; open, close, rename, move, delete programs; read-only views of other projects and repositories [fe] [fe-proj] [prg-open] [fe-open] [fe-reopen] [fe-close] [fe-del] [fe-save] [fe-info] [fe-menus] [prg-close] | RO+MUT | SessionTab; the project navigator scope; ContainerTree | `list-project-files`, `manage-files`, `delete-project-binary` | builds are project members | CAT, CF-dlg (delete), 1W | partial |
| V10 | Archive and restore a project [fe-archive] [fe-restore] | MUT | project manager (F02) | `export` (`gzf`); catalog action needed for a whole-project archive | corpus | CAT | partial |

### 15. Identification tools, utilities, keyboard and options

| ID | Ghidra feature | R/M | AgentDecompile mapping | Backend | Multi-variant | Doctrine | Status |
|---|---|---|---|---|---|---|---|
| I01 | Function ID: the FID analyzer and FidDb management (choose, attach, detach, create, populate, debug search) [fid] [fidp] [fid-debug] | RO+MUT | NameProvenance (a FID name is an analysis-tier candidate); no FidDb management | catalog action needed | per-build; a FID name on build-a reaches build-c only through an identity edge | CAT, NA, NP | missing |
| I02 | BSim: overview query, similar-function search, filters, results, compare functions, databases; the BSim Version Tracking correlator [bsim] [bsimov] [bsimcorr] [bsim-ingest] [bsim-db] [bsim-cli] [bsim-fw] | RO | CandidateAlignment (BSim evidence channel); MatchReview | `bsim-createdatabase`, `bsim-ingest`, `bsim-report` | corpus-wide; similarity proposes, never accepts | RO, NP; ingest CAT, 1W | covered |
| I03 | Checksum generator: checksum-8/16/32, Adler-32, CRC-16/32, MD5, SHA family, over a selection or everything [cks] | RO | HexStrip selection → link menu "Checksums" in a Peek (extend) | catalog action needed | anchor-mapped: the same range hashed on each build is cheap divergence evidence | RO | missing |
| I04 | Evaluator: Ghidra has no help topic by that name; the nearest are Go To Expression [addrx] and equate Convert [eq] | RO | NavigationBar expression prefix; Peek scalar conversions | catalog action needed | per-build | RO | missing |
| I05 | Key bindings: change, remove, import, export [tool] | RO | KeymapSettings (`keymap.json` plus a per-viewer diff) | none | viewer | PV | covered |
| I06 | Tool Options dialog: restore defaults, tool and program caching [tool] | RO | View settings; NEW: OptionsPanel for listing, decompiler, byte viewer and search options | none | viewer | PV | missing |
| I07 | Keyboard navigation: component traversal and the Quick Action dialog [kbn] [acc] | RO | F6 regions; CommandPalette | `GET /api/v1/actions` | none | RO | covered |
| I08 | Docking windows and tool configuration: move, stack, tab, rename transient windows; configure and save tools [dock] [tooladm] [cfgtool] | RO | Workstation regions; LayoutPresets (five presets plus a per-viewer diff) | none | viewer | PV | covered (free docking is not planned) |
| I09 | Accessibility: screen-reader guidance [acc] | RO | AccessibleView and the accessibility guideline | none | viewer | RO | covered |
| I10 | Tables and tree filters: sort, choose columns, column settings and filters, copy, CSV export; tree filter strategy, globbing, multi-term [tables] [tfilt] | RO | NEW: ResultsTable; the Functions grid typeahead (`/`) and FilterChip | none (client) | per-build columns | RO, PV | partial |

Not counted: printing [print] (the browser's print of the AccessibleView is
enough), theming (out of scope), IDE integrations, and the database viewer.

## New components needed

Each one follows the design system: typed links, one selection owner, words
beside glyphs, the Linking block, and catalog-only mutation.

| Component | Purpose | Rows |
|---|---|---|
| NEW: ListingFieldLayout | A per-viewer Listing column set: add, remove, move, enable, reset; optional offset, p-code, stack depth, register transition and source map columns. | L10, L11, L12, L31 |
| NEW: OverviewBar | A vertical margin beside the Listing: address-type, entropy, marker and search-hit modes; every value repeated in a text key; per-build bars side by side in Compare. | L16, L17, L18 |
| NEW: ResultsTable | One sortable, filterable, column-choosable, CSV-exportable table for symbols, strings, defined data, comments, equates, relocations, tags, types, ranges and search hits. It has per-build hit columns, make-selection into a worklist, and a checked set for the ActionStrip. | L24, S05, S06, T17, P05, P06, A01, A02, A08, F14, Q01–Q10, Q12, I10 |
| NEW: SymbolTree | The namespace, class, import, export and label hierarchy as an APG tree. Per-build presence is shown with LocatorGlyph. It supports create namespace or class, convert, move, and external locations. | S01–S03, S12, F05 |
| NEW: TypeManager | Archive and category tree for built-in, program, file and project archives. It covers source-archive sync state, find by name, size or offset, apply and capture function types, replace and merge with use counts per build, and header import. | T01–T09, T15 |
| NEW: TypeEditor | A grid editor in structure/union, enum, typedef/pointer and function-definition modes: bitfields, packing, alignment, flexible arrays. A per-build layout delta table precedes Save, and any resize goes through ConfirmDialog. | D14, D20–D22, T05, T10–T13, E06 |
| NEW: SignatureEditor | Name, namespace, convention (from the build's spec), return type, parameters, varargs, No Return, inline, call-fixup, thunk target and purge. It hosts StorageEditor and has a call-site override mode. It is the design-system counterpart of the existing source FunctionEditor. | D13, D17, D18, F04, F06, F08–F10, S12 |
| NEW: StackFrameEditor | The stack frame as a grid: local size, parameter offset and size, and stack variables. Frames can be compared per build side by side. | F13 |
| NEW: ReferenceEditor | Add or edit memory, external, stack and register references; set ref-type, operand and primary; flow and fallthrough overrides; references from a selection. | E02, E03, E07–E10 |
| NEW: RegisterValuesEditor | Register and context values over address ranges, with the consequence ("re-disassembly requires admission") stated before Save. | P07 |
| NEW: MemoryMapTable | Blocks with permissions, overlay and initialization state; block edits through ActionStrip and ConfirmDialog. An image-base change names the affected anchors. | P03, P04 |
| NEW: ProgramTreeView | Program trees, folders and fragments, organizations, and view restriction of the Listing. | P01, P02 |
| NEW: SearchWorkbench | One search surface in memory, text, decompiled-text, instruction, wildcard, scalar, string, direct-reference, address-table and replace modes. Scope is this build or all builds. Results go to ResultsTable. | Q01–Q08, Q10–Q12 |
| NEW: AnalyzerPanel | Reads each build's analyzer configuration. Changes and one-shot runs are catalog verbs behind admission, never automatic. | Z02, Z04, Z08 |
| NEW: PatchEditor | Assemble or patch bytes with an original-byte preview, the exact target, confirmation, the transaction receipt and a post-write read. Per build only. | N12, X01 |
| NEW: ScriptConsole | A script list and REPL for `execute-script`. Advanced only; each run targets one build explicitly and posts through the catalog. | C01, C03 |
| NEW: VersionControlPanel | Per-build checkout state: check out, check in, undo checkout, update, history. An exclusive checkout is shown as the one-writer lock. | V04 |
| NEW: ExportDialog | Choose the exporter, options and build; the artifact lands in the dock with its basis. Covers C export, graph export and type export. | D03, G10, V06 |
| NEW: OptionsPanel | Per-viewer display options for Listing operands, xrefs, the decompiler, the byte viewer, the structure editor and search. Program-affecting options (decompiler analysis, spec extensions) are shown read-only and change only through the catalog. | D05, D30, D31, N11, T19, I06 |
| NEW: EditHistory | A per-build list of program transactions with Undo and Redo as catalog verbs. Propagated edits are undone per recipient. | V01 |

### Extensions to existing components

These are additions to existing components, not new components.

- **Listing**: address-set selection with next/previous range; the flow-arrow
  margin with go-to-source and go-to-target; expandable composite data and
  variable rows; function header rows (signature source, purge, tags,
  repeatable comment); one row kind per comment type; next/previous commands
  for instruction, data, undefined, label, function and bookmark; select by
  flow. Rows: L04, L06–L09, L13, L15, L21, L22, N03, N04.
- **DecompileView**: slice highlight sets (def-use, forward, backward, operator
  slices), next/previous highlight, brace navigation, a committed vs
  decompiler-only word on locals, and Edit-group items for Commit
  Params/Return, Commit Local Names, Split Out, Force Field, Adjust Pointer
  Offset, Auto Create Structure and Convert/Set Equate. Rows: D05, D15, D16,
  D19–D21, D24–D27, D32.
- **GraphPane**: grouping and path highlight, a block-model selector, data
  reference graphs, program-scope graphs and a data-flow graph. Rows: D07,
  G02, G08, G09, P10.
- **HexStrip**: integer, octal, binary and short/long formats; bytes per line,
  group size and charset; a count entry for Select Bytes. Rows: N10, N11, L23.
- **Peek**: instruction info, speculative disassembly (dashed, "hypothesis"),
  type-at-address preview, checksums of a selection, program properties.
  Rows: L27, L28, T16, I03, P12.
- **XrefPanel**: delete a reference; xref display options (group by function,
  ref-type letter). Rows: L09, L30, S07.
- **CallHierarchy**: filters and a multi-root common-callers mode. Rows: G07,
  G13.
- **NavigationBar**: expression and file-offset go-to. Rows: N01, N02, I04.
- **MarksList**: edit and remove program bookmarks through ActionStrip. Row: A05.
- **EntityTimeline**: comment and label history events. Rows: A07, S10.
- **SplitCompare**: program-level range diff and a difference-detail Peek.
  Rows: X02, X04.

## Backend and catalog gaps

Each entry needs a catalog action (listed in `GET /api/v1/actions` with its
target fields, its mutating flag and its resource claim) and a provider. A
documented tool that already covers part of the gap is named. The mutating
flag matters because the consolidated plan records a verb that advertises
non-mutating while it writes. Admission must use real owner state, not the
flag alone.

**Read gaps.** All are RO and add no writer.

1. A paged, section-wide Listing read: code units with address, bytes,
   mnemonic, operands, labels, comments by type, flow targets, xref counts and
   the function header (L01, L06–L09, L13).
2. Per-instruction extras: p-code, stack depth, register transitions, file
   offset and source map entry (L10, L11).
3. Instruction info: the instruction prototype, operand objects, inputs and
   outputs (L27).
4. Non-committing speculative disassembly at an address (L28).
5. Code-unit type map and entropy per block for the overview bar (L17, L18).
6. Basic blocks and typed edges per function, with a selectable block model;
   program-scope block and code-flow graphs (G01, G08, P10).
7. A p-code or data-flow graph for one function (D07).
8. Address-expression evaluation and file-offset ↔ address mapping (N02, I04).
9. Byte-pattern memory search with formats, masks, alignment and scope (Q01).
10. Direct-reference and address-table scans (Q07, Q08).
11. Wildcard-assembler instruction patterns (Q11).
12. Enumeration of defined data, the relocation table, equates, program trees,
    register and context value ranges, the program's comment and label
    history, program properties, and validation findings (A02, P01, P05–P07,
    A07, S10, P11, P12).
13. Program-level diff over address ranges by category, aligned by anchors
    between two builds (X02, X04).
14. Checksums over a range (I03).
15. The analyzer configuration of each build (Z02).
16. Debug-decompile capture for one function as an artifact (D06).

**Write gaps.** Each needs a catalog verb with CAT and 1W. Destructive or
batch verbs also need CF-dlg, and MC where custom data can be overwritten.

1. Commit Params/Return and Commit Local Names (D15, D16).
2. Call-site signature override: set, edit and remove (D18).
3. Split out variable, force field, adjust pointer offset, auto-create
   structure from usage (D19–D21).
4. Convert constant display, set/rename/remove equate, apply enum to an
   operand (D24, P06).
5. Delete a variable; set or remove function purge and stack depth change
   (F10, F11).
6. Stack frame edits (F13).
7. Disassemble variants; modify instruction flow and length; fallthrough
   override; clear with options; clear flow and repair (E01–E04).
8. Reference create, edit and delete for memory, external, stack and register
   references, plus offset tables (E07–E10, L30, S07).
9. Make string and make address table from search results (Q06, E11).
10. Batch search-and-replace over names, comments and types (Q10).
11. Type archive lifecycle, category edits, source-archive sync, replace and
    merge, apply and capture function data types, function definitions, create
    labels from enums (T02–T04, T06, T08, T09, T13).
12. Symbol Tree edits: namespace and class creation, move, delete, external
    locations and library association, set external entry point (S02, S03,
    S11).
13. Memory block edits and image base (P04).
14. Register and context value ranges (P07).
15. Program tree and fragment edits (P01, P02).
16. Program bookmark edit and remove, surfaced as catalog verbs;
    `manage-bookmarks` already accepts the fields (A05).
17. Byte and instruction patching with original-byte preview and post-write
    read (N12, X01).
18. Undo and redo of a program transaction (V01).
19. Analyzer options, one-shot analyzers, spec extensions; all admission-bound
    (Z02, Z04, D31).
20. Import of PDB, external DWARF and SARIF as context or annotations (Z07).
21. A manual identity edge from the review surface (X07).
22. Explicit program save and a whole-project archive (V03, V10).
23. Translate strings (A03).
24. FidDb management (I01).
25. Additional exporters: GDT, hex records, original file, raw bytes (V06).

**Contract gaps.** These cut across the matrix.

- Mode lists for `manage-function`, `manage-symbols`, `manage-comments`,
  `manage-bookmarks`, `manage-data-types`, `manage-structures` and
  `manage-strings` are documented only as "see MCP schema" in TOOLS_LIST. The
  catalog must expose them so that each Edit-group item can be derived rather
  than hand-listed per frontend (F22).
- Every write verb needs a propagation companion that produces
  PropagationTransfer rows for one field and a recipient set. Today
  `migrate-metadata` and `match-function` propagate names, tags, comments,
  prototypes and bookmarks in bulk. Parity needs a per-field,
  per-recipient-gated verb with receipts.
- Layout-gated application needs a read that returns, for a type or storage
  proposal, each build's size, alignment, pointer width and register
  availability. It must run before any cross-build ConfirmDialog.

## Multi-variant rules that apply to every row

- **Reads never cross silently.** A read, search or graph states its scope:
  the inspected build, or all builds with one column per build. Absent
  counterparts read "absent". Nothing is interpolated.
- **Edits are per-build, then proposed.** Every mutation acts on one concrete
  build. Propagation is a separate, reviewable proposal: donor, field,
  recipients, gate result and per-recipient outcome. Rename proposals for
  `ResourceRef::Resolve` reach only builds with an accepted identity edge.
- **Types are layout-gated.** Applying `CacheEntry` to build-c requires
  build-c's own size and offset check. A mismatch blocks that recipient and
  shows both layouts.
- **Program-level objects stay program-level.** Bookmarks, memory blocks,
  relocations, register values, program trees, analyzer options and patches
  belong to one build. Across builds they are compared, never merged. Logical
  per-viewer marks are separate and resolve per build through LocatorGlyph.
- **Addresses move only through anchors.** Moving the cursor from FUN_0041c880
  on build-a to its counterpart on build-c uses recorded anchor pairs. Between
  anchors, the view says which preceding anchor it used.

## Doctrine that applies to every row

- Browsing is read-only. Following a selection never decompiles a cache miss,
  opens a program, imports or analyzes. An empty view is a StateNotice, never
  permission to analyze again.
- Every mutation goes through the action catalog and a job. The result appears
  on the invoking row only after the terminal result. Single-target edits
  confirm in place. Batch, destructive and cross-build edits use ConfirmDialog.
- There is one Ghidra writer per project or program. Admission checks the real
  owner. External owners are never offered kill or restart. A second writer
  waits.
- There is no auto-analysis on open. Analysis, re-disassembly and reanalysis
  run only when admitted, and valid receipts are reused.
- Nothing here is recovery proof. A cleaner decompile, a parsed header, a BSim
  hit or a completed job is advisory until the recovery acceptance in STRATEGY
  holds.

## References

Ghidra help, at `master` in `NationalSecurityAgency/ghidra`:

[cb]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/CodeBrowserPlugin/CodeBrowser.htm
[cbopt]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/CodeBrowserPlugin/CodeBrowserOptions.htm
[bff]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/CodeBrowserPlugin/Browser_Field_Formatter.htm
[lbg]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/CodeBrowserPlugin/ListingBackground.html
[seltab]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/CodeBrowserPlugin/SelectionTable.htm
[nav]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Navigation/Navigation.htm
[addrx]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Misc/AddressExpressions.htm
[prg-nav]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ProgramManagerPlugin/Navigating_Program_Files.htm
[sel]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Selection/Selecting.htm
[flowsel]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FlowSelection/Selection_By_Flow.html
[selbytes]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/SelectBytesPlugin/Select_Bytes_Help.html
[hl]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/SetHighlightPlugin/Highlighting.htm
[ov]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/OverviewPlugin/Overview.htm
[snap]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Snapshots/Snapshots.html
[clip]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ClipboardPlugin/Clipboard.htm
[instinfo]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ShowInstructionInfoPlugin/ShowInstructionInfo.htm
[disview]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DisassembledViewPlugin/DisassembledViewPlugin.htm
[dock]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DockingWindows/Docking_Windows.htm
[bv]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/ByteViewer/src/main/help/help/topics/ByteViewerPlugin/The_Byte_Viewer.htm
[bvopt]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/ByteViewer/src/main/help/help/topics/ByteViewerPlugin/ByteViewerOptions.htm
[dw]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Decompiler/src/main/help/help/topics/DecompilePlugin/DecompilerWindow.html
[dopt]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Decompiler/src/main/help/help/topics/DecompilePlugin/DecompilerOptions.html
[dann]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Decompiler/src/main/help/help/topics/DecompilePlugin/DecompilerAnnotations.html
[dcon]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Decompiler/src/main/help/help/topics/DecompilePlugin/DecompilerConcepts.html
[taint]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/DecompilerDependent/src/main/help/help/topics/DecompilerTaint/DecompilerTaint.html
[dtf]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/DecompilerDependent/src/main/help/help/topics/DecompilerTextFinderPlugin/Decompiler_Text_Finder.html
[fg]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/FunctionGraph/src/main/help/help/topics/FunctionGraphPlugin/Function_Graph.html
[fgl]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/FunctionGraph/src/main/help/help/topics/FunctionGraphPlugin/Function_Graph_Layouts.html
[vg]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Framework/Graph/src/main/help/help/topics/VisualGraph/Visual_Graph.html
[fcg]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/GraphFunctionCalls/src/main/help/help/topics/FunctionCallGraphPlugin/Function_Call_Graph.html
[ct]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/CallTreePlugin/Call_Tree_Plugin.html
[pg]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/ProgramGraph/src/main/help/help/topics/ProgramGraphPlugin/ProgramGraph.htm
[dg]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/DataGraph/src/main/help/help/topics/DataGraphPlugin/Data_Graph.html
[gexp]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/GraphServices/src/main/help/help/topics/GraphServices/GraphExport.htm
[gdisp]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/GraphServices/src/main/help/help/topics/GraphServices/GraphDisplay.htm
[fcmp]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FunctionComparison/FunctionComparison.htm
[st]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/SymbolTreePlugin/SymbolTree.htm
[stab]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/SymbolTablePlugin/symbol_table.htm
[stt]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/SymbolTablePlugin/symbol_table_transient.htm
[sref]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/SymbolTablePlugin/symbol_references.htm
[locref]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/LocationReferencesPlugin/Location_References.html
[lbl]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/LabelMgrPlugin/Labels.htm
[fieldnames]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/LabelMgrPlugin/FieldNames.htm
[extn]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ReferencesPlugin/external_program_names.htm
[dtm]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DataTypeManagerPlugin/data_type_manager_description.htm
[dtmw]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DataTypeManagerPlugin/data_type_manager_window.html
[dtma]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DataTypeManagerPlugin/data_type_manager_archives.html
[dtt]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DataTypeManagerPlugin/data_types_table.html
[se]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DataTypeEditors/StructureEditor.htm
[ee]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DataTypeEditors/EnumEditor.htm
[dtsel]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DataTypeEditors/DataTypeSelectionDialog.htm
[data]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DataPlugin/Data.htm
[cparse]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/CParserPlugin/CParser.htm
[dtp]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DataTypePreviewPlugin/DataTypePreviewPlugin.html
[ptree]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ProgramTreePlugin/program_tree.htm
[pview]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ProgramTreePlugin/view_manager.htm
[porg]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ProgramTreePlugin/Program_Organizations.htm
[mm]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/MemoryMapPlugin/Memory_Map.htm
[reloc]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/RelocationTablePlugin/relocation_table.htm
[eq]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/EquatePlugin/Equates.htm
[reg]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/RegisterPlugin/Registers.htm
[lang]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/LanguageProviderPlugin/Languages.htm
[popt]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ProgramManagerPlugin/Program_Options_Dialog.htm
[about]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/About/About_Program_File.htm
[blk]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/BlockModel/Block_Model.htm
[val]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ValidateProgram/ValidateProgram.html
[prop]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/PropertyManagerPlugin/Property_Viewer.htm
[dstr]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DefinedStringsPlugin/DefinedStringsPlugin.htm
[dwin]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DataWindowPlugin/data_window.htm
[tr]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/TranslateStringsPlugin/TranslateStringsPlugin.htm
[charsets]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Charsets/Charsets.htm
[bm]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/BookmarkPlugin/Bookmarks.htm
[cm]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/CommentsPlugin/Comments.htm
[cw]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/CommentWindowPlugin/comment_window.htm
[ann]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Annotations/Annotations.html
[fn]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FunctionPlugin/Functions.htm
[var]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FunctionPlugin/Variables.htm
[ftag]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FunctionTagPlugin/function_tag_window.htm
[fwin]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FunctionWindowPlugin/function_window.htm
[stack]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/StackEditor/StackEditor.html
[dis]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DisassemblerPlugin/Disassembly.htm
[clr]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ClearPlugin/Clear.htm
[fall]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FallThroughPlugin/Override_Fallthrough.htm
[refs]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ReferencesPlugin/References_from.htm
[offtab]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ReferencesPlugin/CreateOffsetReferencesTable.htm
[smem]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Search/Search_Memory.htm
[sfmt]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Search/Search_Formats.htm
[stext]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Search/Search_Program_Text.htm
[smnem]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Search/Instruction_Mnemonic_Search.htm
[sinstr]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Search/Search_Instruction_Patterns.htm
[sstr]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Search/Search_for_Strings.htm
[sdref]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Search/Search_for_DirectReferences.htm
[saddr]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Search/Search_for_AddressTables.htm
[sres]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Search/Query_Results_Dialog.htm
[srepl]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Search/SearchAndReplace.htm
[scalar]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ScalarSearchPlugin/The_Scalar_Table.htm
[wasm]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/WildcardAssembler/src/main/help/help/topics/WildcardAssemblerModule/Wildcard_Assembler.html
[aa]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/AutoAnalysisPlugin/AutoAnalysis.htm
[pdb]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/PDB/src/main/help/help/topics/Pdb/PDB.htm
[dwarf]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DWARFExternalDebugFilesPlugin/DWARFExternalDebugFilesPlugin.html
[sarif]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Sarif/src/main/help/help/topics/Sarif/SARIF.htm
[srcf]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/SourceFilesTablePlugin/SourceFilesTable.html
[asm]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/AssemblerPlugin/Assembler.htm
[diff]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/ProgramDiff/src/main/help/help/topics/Diff/Diff.htm
[vt]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/VersionTracking/src/main/help/help/topics/VersionTrackingPlugin/Version_Tracking_Intro.html
[vt-tool]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/VersionTracking/src/main/help/help/topics/VersionTrackingPlugin/VT_Tool.html
[vtcorr]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/VersionTracking/src/main/help/help/topics/VersionTrackingPlugin/VT_Correlators.html
[vtmatch]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/VersionTracking/src/main/help/help/topics/VersionTrackingPlugin/providers/VT_Matches_Table.html
[vtmark]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/VersionTracking/src/main/help/help/topics/VersionTrackingPlugin/providers/VT_Markup_Table.html
[fbp]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/BytePatterns/src/main/help/help/topics/FunctionBitPatternsExplorerPlugin/FunctionBitPatternsExplorerPlugin.htm
[sm]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/GhidraScriptMgrPlugin/GhidraScriptMgrPlugin.htm
[con]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ConsolePlugin/console.html
[pyi]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/PyGhidra/src/main/help/help/topics/PyGhidra/interpreter.html
[bun]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/BundleManager/BundleManager.htm
[undo]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Tool/Undo_Redo.htm
[save]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ProgramManagerPlugin/Saving_Program_Files.htm
[vc]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/VersionControl/project_repository.htm
[merge]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Repository/Merge_Program_Files.htm
[fe]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FrontEndPlugin/Ghidra_Front_end.htm
[fe-archive]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FrontEndPlugin/Archive_Project.htm
[exp]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ExporterPlugin/exporter.htm
[imp]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ImporterPlugin/importer.htm
[fsb]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FileSystemBrowserPlugin/FileSystemBrowserPlugin.html
[fid]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/FunctionID/src/main/help/help/topics/FunctionID/FunctionID.html
[fidp]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/FunctionID/src/main/help/help/topics/FunctionID/FunctionIDPlugin.html
[bsim]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/BSim/src/main/help/help/topics/BSimSearchPlugin/BSimSearch.html
[bsimov]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/BSim/src/main/help/help/topics/BSim/BSimOverview.html
[cks]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ComputeChecksumsPlugin/Generate_Checksum_Help.html
[tool]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Tool/ToolOptions_Dialog.htm
[tooladm]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Tool/Ghidra_Tool_Administration.htm
[kbn]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Framework/Docking/src/main/help/help/topics/KeyboardNavigation/KeyboardNavigation.html
[acc]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Accessibility/AccessibilityOverview.html
[print]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/PrintingPlugin/Printing.htm
[libre]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/LibreTranslatePlugin/LibreTranslatePlugin.htm
[procs]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/RuntimeInfoPlugin/InstalledProcessors.htm
[headless-help]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/HeadlessAnalyzer/HeadlessAnalyzer.htm
[gintro]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Graph/GraphIntro.html
[connect]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FrontEndPlugin/Connecting_Tools.htm
[gserver]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/GhidraServer/GhidraServer.htm
[fe-proj]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FrontEndPlugin/Creating_a_Project.htm
[prg-open]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ProgramManagerPlugin/Opening_Program_Files.htm
[bsimcorr]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/VersionTrackingBSim/src/main/help/help/topics/BSimCorrelator/BSim_Correlator.html
[regex]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Framework/Docking/src/main/help/help/topics/Search/Regular_Expressions.htm
[loadpdb]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/PDB/src/main/help/help/topics/Pdb/LoadPDB.html
[tables]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Framework/Docking/src/main/help/help/topics/Tables/GhidraTableHeaders.html
[tfilt]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Framework/Docking/src/main/help/help/topics/Trees/GhidraTreeFilter.html
[vt-wiz]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/VersionTracking/src/main/help/help/topics/VersionTrackingPlugin/VT_Wizard.html
[vt-flow]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/VersionTracking/src/main/help/help/topics/VersionTrackingPlugin/VT_Workflow.html
[vt-pre]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/VersionTracking/src/main/help/help/topics/VersionTrackingPlugin/VT_Preconditions.html
[vt-fn]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/VersionTracking/src/main/help/help/topics/VersionTrackingPlugin/providers/VT_Functions_Table.html
[vt-impl]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/VersionTracking/src/main/help/help/topics/VersionTrackingPlugin/providers/VT_Implied_Matches_Table.html
[vt-rel]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/VersionTracking/src/main/help/help/topics/VersionTrackingPlugin/providers/VT_Related_Associations_Table.html
[vt-auto]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/VersionTracking/src/main/help/help/topics/VersionTrackingPlugin/VT_AutoVT.html
[vt-apply]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/VersionTracking/src/main/help/help/topics/VersionTrackingPlugin/providers/VT_Apply_Options.html
[bsim-ingest]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/BSim/src/main/help/help/topics/BSim/IngestProcess.html
[bsim-db]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/BSim/src/main/help/help/topics/BSim/DatabaseConfiguration.html
[bsim-cli]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/BSim/src/main/help/help/topics/BSim/CommandLineReference.html
[bsim-fw]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/BSim/src/main/help/help/topics/BSim/FeatureWeight.html
[fe-open]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FrontEndPlugin/Opening_a_Ghidra_Project.htm
[fe-reopen]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FrontEndPlugin/Re-opening_a_Project.htm
[fe-close]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FrontEndPlugin/Close_Project.htm
[fe-del]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FrontEndPlugin/Deleting_a_Ghidra_Project.htm
[fe-save]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FrontEndPlugin/Saving_a_Ghidra_Project.htm
[fe-info]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FrontEndPlugin/Project_Info.htm
[fe-menus]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FrontEndPlugin/Ghidra_Front_end_Menus.htm
[prg-close]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ProgramManagerPlugin/Closing_Program_Files.htm
[fe-restore]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FrontEndPlugin/Restore_Project.htm
[refs-intro]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ReferencesPlugin/References.htm
[searching]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Search/Searching.htm
[cfgtool]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Tool/Configure_Tool.htm
[showlog]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Tool/ShowLog.htm
[prg-ann]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ProgramManagerPlugin/Program_Annotation.htm
[dintro]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Decompiler/src/main/help/help/topics/DecompilePlugin/DecompilerIntro.html
[fid-debug]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/FunctionID/src/main/help/help/topics/FunctionID/FunctionIDDebug.html
[gsvc]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Graph/GraphServicesIntro.html
[scriptdev]: https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/GhidraScriptMgrPlugin/ScriptDevelopment.htm
[headless]: https://ghidra.re/ghidra_docs/GhidraClass/Intermediate/HeadlessAnalyzer.html
[gvt]: https://ghidra.re/ghidra_docs/GhidraClass/Intermediate/VersionTracking.html

The reference definitions above render as links in each matrix row. The
rendered list is here:

- Listing, navigation and selection: [cb], [cbopt], [bff], [lbg], [seltab],
  [nav], [addrx], [prg-nav], [sel], [flowsel], [selbytes], [hl], [ov], [snap],
  [clip], [instinfo], [disview], [dock].
- Byte viewer: [bv], [bvopt].
- Decompiler: [dw], [dopt], [dann], [dcon], [taint], [dtf].
- Graphs: [fg], [fgl], [vg], [fcg], [ct], [pg], [dg], [gexp], [gdisp], [fcmp].
- Symbols: [st], [stab], [stt], [sref], [locref], [lbl], [fieldnames], [extn].
- Types: [dtm], [dtmw], [dtma], [dtt], [se], [ee], [dtsel], [data], [cparse],
  [dtp].
- Program structure: [ptree], [pview], [porg], [mm], [reloc], [eq], [reg],
  [lang], [popt], [about], [blk], [val], [prop].
- Strings, bookmarks and comments: [dstr], [dwin], [tr], [charsets], [bm],
  [cm], [cw], [ann].
- Functions: [fn], [var], [ftag], [fwin], [stack].
- Code and data definition: [dis], [clr], [fall], [refs], [offtab].
- Search: [smem], [sfmt], [stext], [smnem], [sinstr], [sstr], [sdref],
  [saddr], [sres], [srepl], [scalar], [wasm].
- Analysis: [aa], [pdb], [dwarf], [sarif], [srcf], [headless].
- Patching, diff and version tracking: [asm], [diff], [vt], [vt-tool],
  [vtcorr], [vtmatch], [vtmark], [gvt], [fbp].
- Scripting: [sm], [con], [pyi], [bun].
- Projects, versions, import and export: [undo], [save], [vc], [merge], [fe],
  [fe-archive], [exp], [imp], [fsb].
- Identification, tools and keyboard: [fid], [fidp], [bsim], [bsimov], [cks],
  [tool], [tooladm], [kbn], [acc], [print].

ghidra.re class guides and API:
[Beginner student guide](https://ghidra.re/ghidra_docs/GhidraClass/Beginner/Introduction_to_Ghidra_Student_Guide.html),
[Intermediate student guide](https://ghidra.re/ghidra_docs/GhidraClass/Intermediate/Intermediate_Ghidra_Student_Guide.html),
[Improving disassembly and decompilation](https://ghidra.re/ghidra_docs/GhidraClass/Advanced/improvingDisassemblyAndDecompilation.pdf),
[API reference](https://ghidra.re/ghidra_docs/api/index.html).

Repository documents:
[guide capability inventory](2026-09-20-ghidra-guide-capability-inventory.md) ·
[unified workstation spec](2026-09-20-unified-workstation-spec.md) ·
[consolidated design plan](2026-09-21-consolidated-design-plan.md) ·
[linked views and accessibility](2026-09-29-linked-views-and-accessibility.md) ·
[FRONTEND_INTENT](../FRONTEND_INTENT.md) ·
[PyGhidra API reference](../PyGhidra_API_Reference.md) ·
[TOOLS_LIST](../../TOOLS_LIST.md) ·
[design system](../design-system/project/README.md) and its
[components](../design-system/project/components/).
