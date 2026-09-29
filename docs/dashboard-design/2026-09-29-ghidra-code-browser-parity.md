# Ghidra Code Browser functional parity specification

Date: 2026-09-29

Status: design specification, refreshed 2026-09-29 (second pass). It is not a
delivery, runtime or recovery receipt.
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

Refreshed 2026-09-29 (second pass) against the design system as it now stands:
the 20 components added for parity, the "Parity extensions (2026-09-29)"
sections in 11 existing components, and the round-2 review revisions of those
components. Every row now has two statuses (defined under
[Evidence boundary](#evidence-boundary)):

- **Design**: designed, partial or missing, meaning covered by a design-system
  spec.
- **Backend status**: backed by a named tool or catalog action, or catalog
  action needed. "backed (client)" marks rows that need no server call
  (per-viewer or client state). A needed row names the proposed contract entries
  in the [catalog contracts for parity](2026-09-29-catalog-contracts-for-parity.md)
  (R reads, W writes, J jobs, G contract gaps).

Rows: **224** Ghidra features across 15 groups, drawn from 174 cited help
pages in 98 help topic directories. Per-topic counts are in
[Coverage by Ghidra help topic](#coverage-by-ghidra-help-topic).

| Design | Rows | Share |
|---|---|---|
| designed | 222 | 99% |
| partial | 0 | 0% |
| missing | 2 | 1% (both by decision: X08 not planned, C05 until scripts are catalog entries) |

| Backend status | Rows | Share |
|---|---|---|
| backed | 121 (29 of them client only, as of round 2) | 54% |
| catalog action needed | 103 | 46% |

| Design × backend | backed | needed | Rows |
|---|---|---|---|
| designed | 121 | 101 | 222 |
| partial | 0 | 0 | 0 |
| missing | 0 | 2 | 2 |

**Before (round 2):** 196 designed, 23 partial, 5 missing. Round 3 closed 26 rows through Listing, GraphPane, DecompileView, SymbolTree, ResultsTable, PropagationTransfer, ReviewDetail and SignatureEditor extensions and five new components (ProgramValidation, ProgramSettings, DebugInfoImport, FunctionIdManager, ProjectWindow), plus ScriptConsole manager actions. The per-group and per-topic tables below are recomputed from the matrix.

**Before (2026-09-29 first pass):** one status per row: 47 covered (21%),
94 partial (42%), 83 missing (37%). A first-pass "covered" row needed both a
design and a backend; its nearest equivalent now is designed and backed,
112 rows.

| Group | Rows | designed | partial | missing | backed | needed | Before: covered / partial / missing |
|---|---|---|---|---|---|---|---|
| 1. Listing, navigation and the byte viewer | 43 | 43 | 0 | 0 | 29 | 14 | 9 / 22 / 12 |
| 2. Decompiler | 32 | 32 | 0 | 0 | 20 | 12 | 10 / 9 / 13 |
| 3. Function Graph, call graph and call trees | 13 | 13 | 0 | 0 | 9 | 4 | 3 / 5 / 5 |
| 4. Symbol Tree, Symbol Table and references | 13 | 13 | 0 | 0 | 7 | 6 | 3 / 8 / 2 |
| 5. Data Type Manager and type editors | 19 | 19 | 0 | 0 | 9 | 10 | 0 / 9 / 10 |
| 6. Program Trees, Memory Map, relocations, equates, registers | 12 | 12 | 0 | 0 | 2 | 10 | 1 / 2 / 9 |
| 7. Strings, data, bookmarks, comments, labels | 11 | 11 | 0 | 0 | 8 | 3 | 2 / 7 / 2 |
| 8. Functions | 16 | 16 | 0 | 0 | 13 | 3 | 4 / 9 / 3 |
| 9. Disassembly, clearing, data creation, references | 11 | 11 | 0 | 0 | 1 | 10 | 0 / 2 / 9 |
| 10. Searches | 12 | 12 | 0 | 0 | 4 | 8 | 0 / 7 / 5 |
| 11. Analysis | 9 | 9 | 0 | 0 | 4 | 5 | 4 / 2 / 3 |
| 12. Patching, Program Diff, Version Tracking | 8 | 7 | 0 | 1 | 3 | 5 | 2 / 3 / 3 |
| 13. Scripting | 5 | 4 | 0 | 1 | 2 | 3 | 1 / 2 / 2 |
| 14. Undo, transactions, multi-user, import and export | 10 | 10 | 0 | 0 | 3 | 7 | 3 / 6 / 1 |
| 15. Identification tools, utilities, keyboard and options | 10 | 10 | 0 | 0 | 7 | 3 | 5 / 1 / 4 |
| **Total** | **224** | **222** | **0** | **2** | **121** | **103** | **47 / 94 / 83** |

What the counts say:

- **The design caught up.** Every component the first pass marked NEW now
  exists, and after round 3, 222 rows are designed. The two that are not are
  missing by decision: X08 is not planned, and C05 waits until scripts are
  catalog entries ([Rows not yet designed](#rows-not-yet-designed)).
- **The backend is now the gap.** 101 rows need a catalog action, and 84 of
  them are fully designed, so their designs wait only on a backend contract. The
  [catalog contracts](2026-09-29-catalog-contracts-for-parity.md) propose each
  one. The heaviest clusters are disassembly and references (10 of 11 rows
  need an action), types (10 of 19), program-level objects (9 of 12) and
  searches (8 of 12).
- **Reading code is designed and mostly backed.** Listing, DecompileView,
  HexStrip, GraphPane, CallHierarchy, XrefPanel and Peek cover browsing. What
  still needs a backend is the paged section-wide Listing read (R01), optional
  columns (R02), the overview lanes (R06) and block graphs (R07).
- **The multi-variant model still depends on two shared reads.** Anchor pairs
  (R25) move every cursor, range and checksum between builds, and the layout
  check (R24) gates every type, storage and frame proposal. Neither is served
  today per the docs.
- **The static 8080 surface still has no split panes** (LayoutPresets). On
  8080, every "Open beside" and held-pane row opens a new window; the function
  exists, the side-by-side presentation does not.
- **Design inconsistencies to reconcile** (owned by those components, not
  changed here): the Listing extension says operand and EOL display options are
  read from OptionsPanel's Listing display section, and the XrefPanel extension
  puts its display options in OptionsPanel's Cross-reference hints section, but
  ListingFieldLayout owns those options and OptionsPanel's rows only link to it.
  OptionsPanel's own D30 bullet still says "analysis and program options per
  build", while its body now makes the decompiler analysis options per-viewer
  request options and leaves only Prototype evaluation as a program option.

Top ten gaps by recovery value, now all backend: the paged Listing read (R01);
anchor pairs (R25); the layout check (R24); Commit Params/Return and Local Names
(W01); reference, flow and fallthrough edits (W13, W10); the stack frame
(R20, W07); byte and instruction search (R10, R03); relocations, equates and
register ranges (R12); patching (W26, R05); type archives and sync (W17, R23).
The largest remaining design gaps are the debug-decompile capture (D06), Set
external entry point (S11), Validate Program (P11) and the stack-depth change
(F10).

### Coverage by Ghidra help topic

The help checkout holds 204 pages in 116 topic directories (714 files
including images). 98 topic directories have at least one matrix row, and
174 of the 204 pages are cited by a row. 18 topic directories (23 pages,
two of which are cited only in notes) have no row, and 7 pages inside mapped
topics are not cited, so 174 + 23 + 7 = 204. Both lists below
give the reason. A row counts toward every topic it cites, so the topic rows
sum to more than 224. The design and backend columns count rows; the last
column keeps the first pass's covered, partial and missing counts.

Paths are repo-relative to `NationalSecurityAgency/ghidra`; each links to
GitHub at `master`. Every action and section heading in each cited page is
listed in the
[appendix](#appendix-actions-and-sections-named-in-each-cited-help-page).

| Module | Help topic | Files | Files cited | Rows | designed | partial | missing | backed | needed | Before: covered / partial / missing |
|---|---|---|---|---|---|---|---|---|---|---|
| BSim | BSim [`Ghidra/Features/BSim/src/main/help/help/topics/BSim/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/BSim/src/main/help/help/topics/BSim) | 5 | 5 | 1 | 1 | 0 | 0 | 1 | 0 | 1 / 0 / 0 |
| BSim | BSimSearchPlugin [`Ghidra/Features/BSim/src/main/help/help/topics/BSimSearchPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/BSim/src/main/help/help/topics/BSimSearchPlugin) | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 1 / 0 / 0 |
| Base | About [`Ghidra/Features/Base/src/main/help/help/topics/About/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/About) | 2 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 1 / 0 / 0 |
| Base | Accessibility [`Ghidra/Features/Base/src/main/help/help/topics/Accessibility/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Accessibility) | 1 | 1 | 2 | 2 | 0 | 0 | 2 | 0 | 2 / 0 / 0 |
| Base | Annotations [`Ghidra/Features/Base/src/main/help/help/topics/Annotations/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Annotations) | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 0 / 1 / 0 |
| Base | AssemblerPlugin [`Ghidra/Features/Base/src/main/help/help/topics/AssemblerPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/AssemblerPlugin) | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 1 | 0 / 0 / 1 |
| Base | AutoAnalysisPlugin [`Ghidra/Features/Base/src/main/help/help/topics/AutoAnalysisPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/AutoAnalysisPlugin) | 1 | 1 | 7 | 7 | 0 | 0 | 4 | 3 | 3 / 1 / 3 |
| Base | BlockModel [`Ghidra/Features/Base/src/main/help/help/topics/BlockModel/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/BlockModel) | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 1 | 0 / 0 / 1 |
| Base | BookmarkPlugin [`Ghidra/Features/Base/src/main/help/help/topics/BookmarkPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/BookmarkPlugin) | 1 | 1 | 2 | 2 | 0 | 0 | 2 | 0 | 0 / 2 / 0 |
| Base | BundleManager [`Ghidra/Features/Base/src/main/help/help/topics/BundleManager/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/BundleManager) | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 1 | 0 / 0 / 1 |
| Base | CParserPlugin [`Ghidra/Features/Base/src/main/help/help/topics/CParserPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/CParserPlugin) | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 0 / 1 / 0 |
| Base | CallTreePlugin [`Ghidra/Features/Base/src/main/help/help/topics/CallTreePlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/CallTreePlugin) | 1 | 1 | 3 | 3 | 0 | 0 | 3 | 0 | 1 / 1 / 1 |
| Base | Charsets [`Ghidra/Features/Base/src/main/help/help/topics/Charsets/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Charsets) | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 1 | 0 / 0 / 1 |
| Base | ClearPlugin [`Ghidra/Features/Base/src/main/help/help/topics/ClearPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ClearPlugin) | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 1 | 0 / 0 / 1 |
| Base | ClipboardPlugin [`Ghidra/Features/Base/src/main/help/help/topics/ClipboardPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ClipboardPlugin) | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 1 | 0 / 1 / 0 |
| Base | CodeBrowserPlugin [`Ghidra/Features/Base/src/main/help/help/topics/CodeBrowserPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/CodeBrowserPlugin) | 5 | 5 | 23 | 23 | 0 | 0 | 17 | 6 | 5 / 13 / 5 |
| Base | CommentWindowPlugin [`Ghidra/Features/Base/src/main/help/help/topics/CommentWindowPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/CommentWindowPlugin) | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 0 / 1 / 0 |
| Base | CommentsPlugin [`Ghidra/Features/Base/src/main/help/help/topics/CommentsPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/CommentsPlugin) | 1 | 1 | 2 | 2 | 0 | 0 | 1 | 1 | 1 / 1 / 0 |
| Base | ComputeChecksumsPlugin [`Ghidra/Features/Base/src/main/help/help/topics/ComputeChecksumsPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ComputeChecksumsPlugin) | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 1 | 0 / 0 / 1 |
| Base | ConsolePlugin [`Ghidra/Features/Base/src/main/help/help/topics/ConsolePlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ConsolePlugin) | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 1 / 0 / 0 |
| Base | DWARFExternalDebugFilesPlugin [`Ghidra/Features/Base/src/main/help/help/topics/DWARFExternalDebugFilesPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DWARFExternalDebugFilesPlugin) | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 1 | 0 / 1 / 0 |
| Base | DataPlugin [`Ghidra/Features/Base/src/main/help/help/topics/DataPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DataPlugin) | 1 | 1 | 4 | 4 | 0 | 0 | 2 | 2 | 0 / 3 / 1 |
| Base | DataTypeEditors [`Ghidra/Features/Base/src/main/help/help/topics/DataTypeEditors/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DataTypeEditors) | 3 | 3 | 4 | 4 | 0 | 0 | 4 | 0 | 0 / 3 / 1 |
| Base | DataTypeManagerPlugin [`Ghidra/Features/Base/src/main/help/help/topics/DataTypeManagerPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DataTypeManagerPlugin) | 4 | 4 | 11 | 11 | 0 | 0 | 2 | 9 | 0 / 5 / 6 |
| Base | DataTypePreviewPlugin [`Ghidra/Features/Base/src/main/help/help/topics/DataTypePreviewPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DataTypePreviewPlugin) | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 0 / 0 / 1 |
| Base | DataWindowPlugin [`Ghidra/Features/Base/src/main/help/help/topics/DataWindowPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DataWindowPlugin) | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 0 / 0 / 1 |
| Base | DefinedStringsPlugin [`Ghidra/Features/Base/src/main/help/help/topics/DefinedStringsPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DefinedStringsPlugin) | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 1 | 0 / 1 / 0 |
| Base | DisassembledViewPlugin [`Ghidra/Features/Base/src/main/help/help/topics/DisassembledViewPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DisassembledViewPlugin) | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 1 | 0 / 0 / 1 |
| Base | DisassemblerPlugin [`Ghidra/Features/Base/src/main/help/help/topics/DisassemblerPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DisassemblerPlugin) | 1 | 1 | 2 | 2 | 0 | 0 | 0 | 2 | 0 / 0 / 2 |
| Base | DockingWindows [`Ghidra/Features/Base/src/main/help/help/topics/DockingWindows/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DockingWindows) | 1 | 1 | 2 | 2 | 0 | 0 | 2 | 0 | 1 / 1 / 0 |
| Base | EquatePlugin [`Ghidra/Features/Base/src/main/help/help/topics/EquatePlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/EquatePlugin) | 1 | 1 | 3 | 3 | 0 | 0 | 0 | 3 | 0 / 0 / 3 |
| Base | ExporterPlugin [`Ghidra/Features/Base/src/main/help/help/topics/ExporterPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ExporterPlugin) | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 1 | 0 / 1 / 0 |
| Base | FallThroughPlugin [`Ghidra/Features/Base/src/main/help/help/topics/FallThroughPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FallThroughPlugin) | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 1 | 0 / 0 / 1 |
| Base | FileSystemBrowserPlugin [`Ghidra/Features/Base/src/main/help/help/topics/FileSystemBrowserPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FileSystemBrowserPlugin) | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 1 / 0 / 0 |
| Base | FlowSelection [`Ghidra/Features/Base/src/main/help/help/topics/FlowSelection/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FlowSelection) | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 1 | 0 / 0 / 1 |
| Base | FrontEndPlugin [`Ghidra/Features/Base/src/main/help/help/topics/FrontEndPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FrontEndPlugin) | 14 | 12 | 4 | 4 | 0 | 0 | 1 | 3 | 1 / 3 / 0 |
| Base | FunctionComparison [`Ghidra/Features/Base/src/main/help/help/topics/FunctionComparison/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FunctionComparison) | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 1 / 0 / 0 |
| Base | FunctionPlugin [`Ghidra/Features/Base/src/main/help/help/topics/FunctionPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FunctionPlugin) | 2 | 2 | 15 | 15 | 0 | 0 | 12 | 3 | 3 / 10 / 2 |
| Base | FunctionTagPlugin [`Ghidra/Features/Base/src/main/help/help/topics/FunctionTagPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FunctionTagPlugin) | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 0 / 1 / 0 |
| Base | FunctionWindowPlugin [`Ghidra/Features/Base/src/main/help/help/topics/FunctionWindowPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FunctionWindowPlugin) | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 1 / 0 / 0 |
| Base | GhidraScriptMgrPlugin [`Ghidra/Features/Base/src/main/help/help/topics/GhidraScriptMgrPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/GhidraScriptMgrPlugin) | 2 | 2 | 2 | 1 | 0 | 1 | 0 | 2 | 0 / 1 / 1 |
| Base | GhidraServer [`Ghidra/Features/Base/src/main/help/help/topics/GhidraServer/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/GhidraServer) | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 1 | 0 / 1 / 0 |
| Base | Graph [`Ghidra/Features/Base/src/main/help/help/topics/Graph/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Graph) | 2 | 2 | 1 | 1 | 0 | 0 | 1 | 0 | 0 / 1 / 0 |
| Base | HeadlessAnalyzer [`Ghidra/Features/Base/src/main/help/help/topics/HeadlessAnalyzer/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/HeadlessAnalyzer) | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 1 / 0 / 0 |
| Base | ImporterPlugin [`Ghidra/Features/Base/src/main/help/help/topics/ImporterPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ImporterPlugin) | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 1 / 0 / 0 |
| Base | LabelMgrPlugin [`Ghidra/Features/Base/src/main/help/help/topics/LabelMgrPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/LabelMgrPlugin) | 2 | 2 | 6 | 6 | 0 | 0 | 4 | 2 | 3 / 2 / 1 |
| Base | LanguageProviderPlugin [`Ghidra/Features/Base/src/main/help/help/topics/LanguageProviderPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/LanguageProviderPlugin) | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 1 | 0 / 1 / 0 |
| Base | LibreTranslatePlugin [`Ghidra/Features/Base/src/main/help/help/topics/LibreTranslatePlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/LibreTranslatePlugin) | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 1 | 0 / 0 / 1 |
| Base | LocationReferencesPlugin [`Ghidra/Features/Base/src/main/help/help/topics/LocationReferencesPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/LocationReferencesPlugin) | 1 | 1 | 2 | 2 | 0 | 0 | 2 | 0 | 2 / 0 / 0 |
| Base | MemoryMapPlugin [`Ghidra/Features/Base/src/main/help/help/topics/MemoryMapPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/MemoryMapPlugin) | 1 | 1 | 2 | 2 | 0 | 0 | 1 | 1 | 0 / 1 / 1 |
| Base | Misc [`Ghidra/Features/Base/src/main/help/help/topics/Misc/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Misc) | 3 | 1 | 2 | 2 | 0 | 0 | 0 | 2 | 0 / 0 / 2 |
| Base | Navigation [`Ghidra/Features/Base/src/main/help/help/topics/Navigation/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Navigation) | 1 | 1 | 6 | 6 | 0 | 0 | 5 | 1 | 2 / 3 / 1 |
| Base | OverviewPlugin [`Ghidra/Features/Base/src/main/help/help/topics/OverviewPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/OverviewPlugin) | 1 | 1 | 2 | 2 | 0 | 0 | 0 | 2 | 0 / 0 / 2 |
| Base | ProgramManagerPlugin [`Ghidra/Features/Base/src/main/help/help/topics/ProgramManagerPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ProgramManagerPlugin) | 6 | 6 | 5 | 5 | 0 | 0 | 3 | 2 | 3 / 2 / 0 |
| Base | ProgramTreePlugin [`Ghidra/Features/Base/src/main/help/help/topics/ProgramTreePlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ProgramTreePlugin) | 3 | 3 | 2 | 2 | 0 | 0 | 0 | 2 | 0 / 0 / 2 |
| Base | PropertyManagerPlugin [`Ghidra/Features/Base/src/main/help/help/topics/PropertyManagerPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/PropertyManagerPlugin) | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 1 | 0 / 0 / 1 |
| Base | ReferencesPlugin [`Ghidra/Features/Base/src/main/help/help/topics/ReferencesPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ReferencesPlugin) | 4 | 4 | 5 | 5 | 0 | 0 | 0 | 5 | 0 / 0 / 5 |
| Base | RegisterPlugin [`Ghidra/Features/Base/src/main/help/help/topics/RegisterPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/RegisterPlugin) | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 1 | 0 / 0 / 1 |
| Base | RelocationTablePlugin [`Ghidra/Features/Base/src/main/help/help/topics/RelocationTablePlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/RelocationTablePlugin) | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 1 | 0 / 0 / 1 |
| Base | Repository [`Ghidra/Features/Base/src/main/help/help/topics/Repository/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Repository) | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 1 | 0 / 1 / 0 |
| Base | RuntimeInfoPlugin [`Ghidra/Features/Base/src/main/help/help/topics/RuntimeInfoPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/RuntimeInfoPlugin) | 2 | 1 | 1 | 1 | 0 | 0 | 0 | 1 | 0 / 1 / 0 |
| Base | ScalarSearchPlugin [`Ghidra/Features/Base/src/main/help/help/topics/ScalarSearchPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ScalarSearchPlugin) | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 0 / 1 / 0 |
| Base | Search [`Ghidra/Features/Base/src/main/help/help/topics/Search/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Search) | 11 | 11 | 10 | 10 | 0 | 0 | 2 | 8 | 0 / 5 / 5 |
| Base | SelectBytesPlugin [`Ghidra/Features/Base/src/main/help/help/topics/SelectBytesPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/SelectBytesPlugin) | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 0 / 1 / 0 |
| Base | Selection [`Ghidra/Features/Base/src/main/help/help/topics/Selection/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Selection) | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 0 / 1 / 0 |
| Base | SetHighlightPlugin [`Ghidra/Features/Base/src/main/help/help/topics/SetHighlightPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/SetHighlightPlugin) | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 0 / 1 / 0 |
| Base | ShowInstructionInfoPlugin [`Ghidra/Features/Base/src/main/help/help/topics/ShowInstructionInfoPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ShowInstructionInfoPlugin) | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 1 | 0 / 0 / 1 |
| Base | Snapshots [`Ghidra/Features/Base/src/main/help/help/topics/Snapshots/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Snapshots) | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 1 / 0 / 0 |
| Base | SourceFilesTablePlugin [`Ghidra/Features/Base/src/main/help/help/topics/SourceFilesTablePlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/SourceFilesTablePlugin) | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 1 | 0 / 1 / 0 |
| Base | StackEditor [`Ghidra/Features/Base/src/main/help/help/topics/StackEditor/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/StackEditor) | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 1 | 0 / 0 / 1 |
| Base | SymbolTablePlugin [`Ghidra/Features/Base/src/main/help/help/topics/SymbolTablePlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/SymbolTablePlugin) | 3 | 3 | 3 | 3 | 0 | 0 | 1 | 2 | 0 / 3 / 0 |
| Base | SymbolTreePlugin [`Ghidra/Features/Base/src/main/help/help/topics/SymbolTreePlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/SymbolTreePlugin) | 1 | 1 | 5 | 5 | 0 | 0 | 3 | 2 | 1 / 3 / 1 |
| Base | Tool [`Ghidra/Features/Base/src/main/help/help/topics/Tool/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Tool) | 6 | 5 | 6 | 6 | 0 | 0 | 5 | 1 | 4 / 0 / 2 |
| Base | TranslateStringsPlugin [`Ghidra/Features/Base/src/main/help/help/topics/TranslateStringsPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/TranslateStringsPlugin) | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 1 | 0 / 0 / 1 |
| Base | ValidateProgram [`Ghidra/Features/Base/src/main/help/help/topics/ValidateProgram/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ValidateProgram) | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 1 | 0 / 0 / 1 |
| Base | VersionControl [`Ghidra/Features/Base/src/main/help/help/topics/VersionControl/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/VersionControl) | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 1 | 0 / 1 / 0 |
| BytePatterns | FunctionBitPatternsExplorerPlugin [`Ghidra/Features/BytePatterns/src/main/help/help/topics/FunctionBitPatternsExplorerPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/BytePatterns/src/main/help/help/topics/FunctionBitPatternsExplorerPlugin) | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 1 | 0 / 0 / 1 |
| ByteViewer | ByteViewerPlugin [`Ghidra/Features/ByteViewer/src/main/help/help/topics/ByteViewerPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/ByteViewer/src/main/help/help/topics/ByteViewerPlugin) | 2 | 2 | 3 | 3 | 0 | 0 | 2 | 1 | 0 / 1 / 2 |
| DataGraph | DataGraphPlugin [`Ghidra/Features/DataGraph/src/main/help/help/topics/DataGraphPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/DataGraph/src/main/help/help/topics/DataGraphPlugin) | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 0 / 0 / 1 |
| Decompiler | DecompilePlugin [`Ghidra/Features/Decompiler/src/main/help/help/topics/DecompilePlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Decompiler/src/main/help/help/topics/DecompilePlugin) | 5 | 5 | 33 | 33 | 0 | 0 | 20 | 13 | 10 / 9 / 14 |
| DecompilerDependent | DecompilerTextFinderPlugin [`Ghidra/Features/DecompilerDependent/src/main/help/help/topics/DecompilerTextFinderPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/DecompilerDependent/src/main/help/help/topics/DecompilerTextFinderPlugin) | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 0 / 1 / 0 |
| FunctionGraph | FunctionGraphPlugin [`Ghidra/Features/FunctionGraph/src/main/help/help/topics/FunctionGraphPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/FunctionGraph/src/main/help/help/topics/FunctionGraphPlugin) | 2 | 2 | 4 | 4 | 0 | 0 | 2 | 2 | 0 / 3 / 1 |
| FunctionID | FunctionID [`Ghidra/Features/FunctionID/src/main/help/help/topics/FunctionID/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/FunctionID/src/main/help/help/topics/FunctionID) | 3 | 3 | 1 | 1 | 0 | 0 | 0 | 1 | 0 / 0 / 1 |
| GraphFunctionCalls | FunctionCallGraphPlugin [`Ghidra/Features/GraphFunctionCalls/src/main/help/help/topics/FunctionCallGraphPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/GraphFunctionCalls/src/main/help/help/topics/FunctionCallGraphPlugin) | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 1 / 0 / 0 |
| GraphServices | GraphServices [`Ghidra/Features/GraphServices/src/main/help/help/topics/GraphServices/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/GraphServices/src/main/help/help/topics/GraphServices) | 2 | 2 | 2 | 2 | 0 | 0 | 1 | 1 | 0 / 1 / 1 |
| PDB | Pdb [`Ghidra/Features/PDB/src/main/help/help/topics/Pdb/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/PDB/src/main/help/help/topics/Pdb) | 2 | 2 | 1 | 1 | 0 | 0 | 0 | 1 | 0 / 1 / 0 |
| ProgramDiff | Diff [`Ghidra/Features/ProgramDiff/src/main/help/help/topics/Diff/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/ProgramDiff/src/main/help/help/topics/Diff) | 1 | 1 | 3 | 3 | 0 | 0 | 1 | 2 | 0 / 2 / 1 |
| ProgramGraph | ProgramGraphPlugin [`Ghidra/Features/ProgramGraph/src/main/help/help/topics/ProgramGraphPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/ProgramGraph/src/main/help/help/topics/ProgramGraphPlugin) | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 1 | 0 / 0 / 1 |
| PyGhidra | PyGhidra [`Ghidra/Features/PyGhidra/src/main/help/help/topics/PyGhidra/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/PyGhidra/src/main/help/help/topics/PyGhidra) | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 0 / 1 / 0 |
| Sarif | Sarif [`Ghidra/Features/Sarif/src/main/help/help/topics/Sarif/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Sarif/src/main/help/help/topics/Sarif) | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 1 | 0 / 1 / 0 |
| VersionTracking | VersionTrackingPlugin [`Ghidra/Features/VersionTracking/src/main/help/help/topics/VersionTrackingPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/VersionTracking/src/main/help/help/topics/VersionTrackingPlugin) | 13 | 13 | 4 | 4 | 0 | 0 | 3 | 1 | 2 / 2 / 0 |
| VersionTrackingBSim | BSimCorrelator [`Ghidra/Features/VersionTrackingBSim/src/main/help/help/topics/BSimCorrelator/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/VersionTrackingBSim/src/main/help/help/topics/BSimCorrelator) | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 1 / 0 / 0 |
| WildcardAssembler | WildcardAssemblerModule [`Ghidra/Features/WildcardAssembler/src/main/help/help/topics/WildcardAssemblerModule/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/WildcardAssembler/src/main/help/help/topics/WildcardAssemblerModule) | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 1 | 0 / 0 / 1 |
| Docking | KeyboardNavigation [`Ghidra/Framework/Docking/src/main/help/help/topics/KeyboardNavigation/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Framework/Docking/src/main/help/help/topics/KeyboardNavigation) | 1 | 1 | 2 | 1 | 0 | 1 | 1 | 1 | 1 / 0 / 1 |
| Docking | Search [`Ghidra/Framework/Docking/src/main/help/help/topics/Search/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Framework/Docking/src/main/help/help/topics/Search) | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 0 / 1 / 0 |
| Docking | Tables [`Ghidra/Framework/Docking/src/main/help/help/topics/Tables/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Framework/Docking/src/main/help/help/topics/Tables) | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 0 / 1 / 0 |
| Docking | Trees [`Ghidra/Framework/Docking/src/main/help/help/topics/Trees/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Framework/Docking/src/main/help/help/topics/Trees) | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 0 / 1 / 0 |
| Graph | VisualGraph [`Ghidra/Framework/Graph/src/main/help/help/topics/VisualGraph/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Framework/Graph/src/main/help/help/topics/VisualGraph) | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 0 / 1 / 0 |

Topic directories with no row:

| Module | Help topic | Files | Why it has no row |
|---|---|---|---|
| BSim | StructureRecovery [`Ghidra/Features/BSim/src/main/help/help/topics/StructureRecovery/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/BSim/src/main/help/help/topics/StructureRecovery) | 1 | BSim-driven structure recovery. Deferred. |
| BSimFeatureVisualizer | BSimFeatureVisualizerPlugin [`Ghidra/Features/BSimFeatureVisualizer/src/main/help/help/topics/BSimFeatureVisualizerPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/BSimFeatureVisualizer/src/main/help/help/topics/BSimFeatureVisualizerPlugin) | 1 | Deferred. |
| Base | DbViewerPlugin [`Ghidra/Features/Base/src/main/help/help/topics/DbViewerPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DbViewerPlugin) | 1 | Developer database viewer; not a Code Browser feature. Not planned. |
| Base | EclipseIntegration [`Ghidra/Features/Base/src/main/help/help/topics/EclipseIntegration/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/EclipseIntegration) | 1 | IDE integration. Not planned. |
| Base | Glossary [`Ghidra/Features/Base/src/main/help/help/topics/Glossary/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Glossary) | 1 | Reference text; no feature. |
| Base | Intro [`Ghidra/Features/Base/src/main/help/help/topics/Intro/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Intro) | 3 | Introduction; no feature. |
| Base | PrintingPlugin [`Ghidra/Features/Base/src/main/help/help/topics/PrintingPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/PrintingPlugin) | 1 | Printing; the browser print of AccessibleView is enough. Not counted. |
| Base | Program [`Ghidra/Features/Base/src/main/help/help/topics/Program/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Program) | 1 | Concept page; no feature. |
| Base | Project [`Ghidra/Features/Base/src/main/help/help/topics/Project/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Project) | 1 | Concept page; no feature. |
| Base | ResourceActionsPlugin [`Ghidra/Features/Base/src/main/help/help/topics/ResourceActionsPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ResourceActionsPlugin) | 1 | Save embedded images. Not planned (ContainerTree covers extracted members). |
| Base | VSCodeIntegration [`Ghidra/Features/Base/src/main/help/help/topics/VSCodeIntegration/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/VSCodeIntegration) | 1 | IDE integration. Not planned. |
| DecompilerDependent | DecompilerTaint [`Ghidra/Features/DecompilerDependent/src/main/help/help/topics/DecompilerTaint/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/DecompilerDependent/src/main/help/help/topics/DecompilerTaint) | 1 | Deferred (see the note under the Decompiler matrix). |
| FileFormats | FileFormatsPlugin [`Ghidra/Features/FileFormats/src/main/help/help/topics/FileFormatsPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/FileFormats/src/main/help/help/topics/FileFormatsPlugin) | 1 | Format-specific container actions; ContainerTree and export-context cover browsing. Not counted. |
| FileFormats | cart [`Ghidra/Features/FileFormats/src/main/help/help/topics/cart/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/FileFormats/src/main/help/help/topics/cart) | 1 | A container format handled on import; ContainerTree. Not counted. |
| GhidraGo | GhidraGo [`Ghidra/Features/GhidraGo/src/main/help/help/topics/GhidraGo/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/GhidraGo/src/main/help/help/topics/GhidraGo) | 1 | External URL protocol handler; deep links (the location schema) are the analog. Not counted. |
| SourceCodeLookup | SourceCodeLookupPlugin [`Ghidra/Features/SourceCodeLookup/src/main/help/help/topics/SourceCodeLookupPlugin/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/SourceCodeLookup/src/main/help/help/topics/SourceCodeLookupPlugin) | 1 | IDE source lookup. Not planned. |
| Docking | Misc [`Ghidra/Framework/Docking/src/main/help/help/topics/Misc/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Framework/Docking/src/main/help/help/topics/Misc) | 1 | Welcome pages only. |
| Docking | Theming [`Ghidra/Framework/Docking/src/main/help/help/topics/Theming/`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Framework/Docking/src/main/help/help/topics/Theming) | 4 | Look and theme; out of scope by request. |

Pages inside mapped topics that no row cites:

- [`Ghidra/Features/Base/src/main/help/help/topics/About/About_Ghidra.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/About/About_Ghidra.htm): About Ghidra (version and license); not a feature.
- [`Ghidra/Features/Base/src/main/help/help/topics/FrontEndPlugin/Edit_Plugin_Path.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FrontEndPlugin/Edit_Plugin_Path.htm): Plugin search paths; plugins are not a dashboard concept.
- [`Ghidra/Features/Base/src/main/help/help/topics/FrontEndPlugin/Extensions.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FrontEndPlugin/Extensions.htm): Ghidra extensions management; not planned.
- [`Ghidra/Features/Base/src/main/help/help/topics/Misc/Appendix.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Misc/Appendix.htm): Appendix index; no feature.
- [`Ghidra/Features/Base/src/main/help/help/topics/Misc/Welcome_to_Ghidra_Help.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Misc/Welcome_to_Ghidra_Help.htm): Welcome page; no feature.
- [`Ghidra/Features/Base/src/main/help/help/topics/RuntimeInfoPlugin/RuntimeInfo.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/RuntimeInfoPlugin/RuntimeInfo.htm): Runtime diagnostics of the Ghidra install; the dashboard `/health` view is the analog. Not counted.
- [`Ghidra/Features/Base/src/main/help/help/topics/Tool/Tip_Of_The_Day.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Tool/Tip_Of_The_Day.htm): Tip of the day; no feature.

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
  component READMEs. The second pass re-read every parity component README and
  every "Parity extensions (2026-09-29)" section, then re-read them again after
  the round-2 review revisions landed, before the counts were final. Nothing
  under `src/` or any frontend code was read. No server, test, build or job was
  run.
- **What a status means.** Both statuses describe the documented design and the
  documented tool surface, not observed behavior.
  - **Design · designed**: a design-system component README, or a "Parity
    extensions (2026-09-29)" section, specifies the whole interaction of the row.
  - **Design · partial**: a spec covers only part of the Ghidra feature, or the
    row relies on generic components (ActionStrip, ConfirmDialog, a Peek) with
    no row-specific spec.
  - **Design · missing**: no spec covers it.
  - **Backend · backed**: a tool in TOOLS_LIST, a catalog verb named in the
    docs, or a source path the guide inventory records, covers every operation
    the row needs. "backed (client)" means the row needs no server call.
  - **Backend · needed**: at least one operation still needs a catalog action.
    The cell names the proposed entries in the
    [catalog contracts](2026-09-29-catalog-contracts-for-parity.md).
  - The first pass's single status (covered, partial, missing) survives only as
    the "Before" counts.

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
- **AgentDecompile mapping**: a design-system component. "(parity extension: …)"
  names an addition that now lives in that component's "Parity extensions
  (2026-09-29)" section, listed in
  [Extensions to existing components](#extensions-to-existing-components). The
  first pass marked components that did not yet exist as `NEW:`; all of them now
  exist and the prefix is gone.
- **Backend**: a documented tool, or "catalog action needed".
- **Multi-variant**: how the feature works per logical entity across build-a…build-d.
- **Doctrine**: codes from the table below.
- **Design**: designed, partial or missing.
- **Backend status**: backed, backed (client), or needed with the contract
  entries that would back it.

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

Example used throughout: `ResourceRef::Resolve` (logical #88) is at 0041b210 on build-a,
0041b2c0 on build-b and 00082f40 on build-c, and is unresolved on build-d.
FUN_0041c880 on build-a is a different, unnamed function. The first parameter
of `ResourceRef::Resolve` points to a `CacheEntry`.

## Full matrix

### 1. Listing, navigation and the byte viewer

| ID | Ghidra feature | R/M | AgentDecompile mapping | Backend | Multi-variant | Doctrine | Design | Backend status |
|---|---|---|---|---|---|---|---|---|
| L01 | Listing view: continuous code-unit display with one address cursor [cb] | RO | Listing inside CodeBrowser | `inspect-memory` (mode `disasm`), `get-function`; catalog action needed for paged section-wide listing rows | per-build; switching builds keeps the entity (anchor-mapped); SplitCompare shows build-a beside build-c | RO, NA | designed | needed: R01 |
| L02 | Address field and its options: padding, block name [cbopt] | RO | Listing address column | `inspect-memory` | per-build addresses; the logical entity is in the composite header | RO | designed | backed |
| L03 | Bytes field and options: grouping, reverse order, max bytes shown [cbopt] | RO | Listing bytes column; moves into HexStrip when Hex is on | `inspect-memory` (mode `bytes`) | per-build | RO | designed | backed |
| L04 | Mnemonic and Operands fields; operand display options: block names, register-variable markup, reference underline, line wrap [cbopt] | RO | Listing mnemonic and operand cells; symbol operands are typed links; operand display options in ListingFieldLayout | `inspect-memory` (mode `disasm`), `get-references` | per-build; operands differ by register allocation; no alignment is inferred between builds | RO | designed | backed |
| L05 | Labels field: primary and non-primary labels, namespace display [cbopt] [lbl] | RO | Listing label cell with its NameProvenance tier word | `manage-symbols` | counterpart names via CounterpartStrip | RO | designed | backed |
| L06 | Function header fields: signature, signature source, call-fixup, purge, tags, repeatable comment, register values at entry [bff] | RO | Listing (parity extension: function header rows) | `get-function`, `manage-function-tags` | per-build; a signature difference shows as a divergence class in CounterpartMatrix | RO | designed | needed: R12 |
| L07 | Function variables display: stack and register annotations, open/close [cb] | RO | Listing (parity extension: collapsible variable rows); CodeBrowser Outline Locals | `get-function` | per-build storage | RO | designed | backed |
| L08 | Comment fields: EOL, pre, post, plate, repeatable; EOL options [bff] [cbopt] | RO | Listing (parity extension: one row kind per comment type); DecompileView comments | `manage-comments` | per-build; each comment carries its donor when propagated | RO | designed | backed |
| L09 | XREFs field: xref hints with delimiter, block, namespace prefix, ref-type letter, group by function, max count, sort [cbopt] | RO | Listing XREF[n] hint → XrefPanel; Peek shows the first 20; XREF field options in ListingFieldLayout | `get-references` | scope one/all: the XrefPanel All builds mode has per-build counts | RO | designed | backed |
| L10 | Offset fields: file offset, function offset, image-base offset, block offset [cbopt] | RO | ListingFieldLayout (optional columns) | catalog action needed (address → file offset) | per-build; file offsets back `section_offset` pinned locators | RO | designed | needed: R02, R09 |
| L11 | PCode, Stack Depth, Register Transition, Parallel and Source Map fields [bff] | RO | ListingFieldLayout (optional columns) | catalog action needed (per-instruction p-code, stack depth, source map) | per-build | RO | designed | needed: R02 |
| L12 | Browser Field Formatter: add, remove, move, enable fields and rows; custom formats; reset [bff] | RO | ListingFieldLayout | none (a per-viewer diff in durable workspace state) | viewer; SplitCompare panes share one layout | PV | designed | backed (client) |
| L13 | Open/close structures and arrays inline; the Field Name field [cb] | RO | Listing (parity extension: expandable data rows) | `get-data` | per-build; the layout may differ, so show that build's component offsets | RO | designed | backed |
| L14 | Hover popups: reference, truncated text, data type, address, function name, scalar [cb] | RO | Peek (cache only; Alt+↓ or pointer rest) | peek cache (existing reads) | Peek names the counterpart and its locator word | RO | designed | backed |
| L15 | Flow arrows margin: select, navigate along an arrow, disable [cb] | RO | Listing flow column (parity extension: arrow margin with go-to-source and go-to-target) | `inspect-memory` (mode `disasm`), `get-references` (`includeFlow`) | per-build | RO | designed | backed |
| L16 | Marker margin and navigation margin: bookmarks, selection, highlight, changes, search hits [cb] | RO | Listing gutter marks ("changed by job"); OverviewBar for the navigation margin | `manage-bookmarks`, `get-references` | per-build markers; logical marks resolve per build via LocatorGlyph | RO | designed | backed |
| L17 | Overview bar, address-type mode [ov] | RO | OverviewBar | `inspect-memory` (`get-memory-blocks`); catalog action needed for the code-unit type map | side-by-side bars per build in Compare; ImageDeltaMap is the rebuild analog | RO | designed | needed: R06 |
| L18 | Entropy overview bar: calculation, palette legend, window [ov] | RO | OverviewBar (entropy mode, text key with values) | catalog action needed | side-by-side; equal regions across builds are cheap divergence evidence | RO, NP | designed | needed: R06 |
| L19 | Cursor text highlight: all matches of the token under the cursor [cb] [cbopt] | RO | Highlight all (`h`, sets A–D) in Listing and DecompileView | none (client, over loaded rows) | per-build; never a cross-build text match | RO | designed | backed (client) |
| L20 | Listing background colors: set a color on a range, navigate colors [lbg] | MUT | MarksList (per-viewer marks with notes) replaces it; color is never meaning here; round 3: Listing (program colors, round 3) | catalog action needed only to read existing program colors | viewer | PV | designed | needed: R12, W35 |
| L21 | Selection: address-set selection, select all, next/previous selected range [sel] | RO | Listing (parity extension: address-set selection extent, collapsed by Esc); checked set for row batches | none on the client; verbs accept `addressRange` | per-build; changing program clears it (F11) | RO | designed | backed (client) |
| L22 | Select by flow: forward/reverse scoped flow, subroutine, function, dead code [flowsel] | RO | Listing (parity extension); GraphPane Blocks | catalog action needed | per-build | RO | designed | needed: R07 |
| L23 | Select Bytes: select N bytes from the cursor [selbytes] | RO | HexStrip byte selection (maps back to rows) | none | per-build | RO | designed | backed (client) |
| L24 | Selection tables: build a table of ranges from a selection [seltab] | RO | ResultsTable (ranges mode); MarksList worklist | none | per-build | RO, PV | designed | backed (client) |
| L25 | Highlight from selection: set, add, subtract, clear, navigate [hl] | RO | MarksList worklist; Highlight all covers token highlight only; round 3: Listing (highlight from selection) | none | per-build | RO, PV | designed | backed (client) |
| L26 | Clipboard: copy, copy special (addresses, byte strings, labels, comments), paste [clip] | RO+MUT | AccessibleView Copy all; link menu Copy link; paste is a catalog verb; round 3: Listing (Paste) | none for copy; catalog action needed for paste | per-build; paste targets one build | RO; paste CAT, 1W | designed | needed: W26 |
| L27 | Show Instruction Info: operand objects, inputs and outputs, raw instruction; processor manual [instinfo] | RO | Peek (parity extension: an instruction-info card on a mnemonic) | catalog action needed (instruction prototype read) | per-build; show the build's language id | RO | designed | needed: R03 |
| L28 | Disassembled View: speculative disassembly at a data cursor without committing [disview] | RO | Peek (parity extension: speculative disassembly, drawn dashed and labelled hypothesis) | catalog action needed (non-committing decode) | per-build | RO, NP | designed | needed: R04 |
| L29 | Show References To / From: popup actions for address, code unit and data type [cb] [locref] | RO | XrefPanel (References · Calls · Slots), Line or token scope, in/out direction | `get-references` (`direction` to/from) | scope one/all with per-build counts | RO | designed | backed |
| L30 | Show Thunk Xrefs and Delete Reference from the XREF field [cb] | RO+MUT | XrefPanel; delete through ActionStrip | `get-references` (`resolve-thunk`); catalog action needed for delete | per-build | RO; delete CAT, 1W | designed | needed: W13 |
| L31 | Open/close functions: collapse a whole function in the Listing [cb] | RO | Listing (parity extension: collapsible function body) | none (view state) | viewer | RO, PV | designed | backed (client) |
| N01 | Go To address, label or expression; wildcards; repeat previous go-to [nav] | RO | NavigationBar go-to field; Ctrl/Cmd+G (`:` prefix); CommandPalette | `search-everything`, `manage-symbols` | results carry per-build locator words; an ambiguous name lists every candidate and never picks one | RO | designed | backed |
| N02 | Go To File Offset and address expressions (math, logic, bit operators, symbol names) [nav] [addrx] | RO | NavigationBar (parity extension: expression and file-offset prefixes) | catalog action needed (expression evaluation, offset mapping) | per-build; a symbol in an expression resolves on the inspected build | RO | designed | needed: R09 |
| N03 | Next/previous code unit: instruction, data, undefined, label, function, non-function, matching bytes, bookmark; invert [nav] | RO | Listing (parity extension: keymap commands for each kind); round 3: Listing (step by matching bytes, Invert) | `inspect-memory`, `list-functions`, `manage-bookmarks` | per-build | RO | designed | backed |
| N04 | Next/previous function [nav] | RO | Listing keymap; Functions list order | `list-functions` | per-build order | RO | designed | backed |
| N05 | Navigation history: back/forward, next/previous function in history, clear [nav] | RO | NavigationBar Back, Forward and Recent menu; Alt+←/→ | none (location schema, history state) | history stops carry `build`; a Back that crosses a build switch says so | RO | designed | backed (client) |
| N06 | Program navigation: next/previous program, go to program, last active program [prg-nav] | RO | CounterpartStrip, the build menu, Alt+PageDown/PageUp; SessionTab | `list-project-files` | an explicit build switch keeps the entity (anchor-mapped) or explains its absence | RO | designed | backed |
| N07 | Starting location and initial-analysis navigation options [nav] | RO | NavigationBar restores location from the URL | none | per-build | RO, NA | designed | backed (client) |
| N08 | Split views: a second listing and multiple docked views [dock] | RO | CodeBrowser two center panes; SplitCompare; LayoutPresets | none | side-by-side builds | RO | designed | backed (client) |
| N09 | Snapshots: connected (follows location) and disconnected listing, decompiler and graph snapshots; tool connections that share location [snap] [connect] | RO | HeldPane: Following means connected, Held means disconnected; Hold this pane | none | a held pane pins entity × build × address with its basis and flags a basis change | RO | designed | backed (client) |
| N10 | Byte Viewer formats: hex, chars, address, disassembled, hex short/int/long/long long, integer, octal, binary [bv] | RO | HexStrip (hex and ASCII only) | `inspect-memory` (mode `bytes`) | per-build; anchor-mapped byte range across builds | RO | designed | backed |
| N11 | Byte Viewer options: bytes per line, alignment offset, group size, charset, char width [bvopt] | RO | HexStrip (parity extension) via OptionsPanel | none | viewer | PV | designed | backed (client) |
| N12 | Byte Viewer memory editing [bv] | MUT | PatchEditor | catalog action needed (the inventory found no bounded patch tool; only `execute-script` `setBytes`) | per-build only; never propagated | CAT, CF-dlg, 1W, MC | designed | needed: W26 |

### 2. Decompiler

| ID | Ghidra feature | R/M | AgentDecompile mapping | Backend | Multi-variant | Doctrine | Design | Backend status |
|---|---|---|---|---|---|---|---|---|
| D01 | Decompiler window: decompiles the function at the cursor, cross-highlights with the Listing [dw] [dintro] | RO | DecompileView, reflected with Listing | `decompile-function` (`get-decompilation`) | per-build; counterpart C in SplitCompare; missing mappings are words, never guesses | RO, NA (a cache miss says "Enter to decompile") | designed | backed |
| D02 | Automatic re-decompile after annotation changes; disable auto refresh [dw] | RO | DecompileView "◷ predates job" marker; Enter re-decompiles | `decompile-function` | per-build; a propagated edit marks each recipient's decompile | RO | designed | backed |
| D03 | Export to C for the current function [dw] | RO | AccessibleView Copy all; link menu Export → ExportDialog | `export` (format `c`), `decompile-function` | per-build file | CAT (artifact), NP | designed | backed |
| D04 | Decompiler snapshot window [dw] | RO | HeldPane | none | holds entity × build | RO | designed | backed (client) |
| D05 | Eliminate Unreachable Code and Respect Read-only Flags toggles [dw] | RO | DecompileView (parity extension: toggles) via OptionsPanel | `decompile-function`: `showUnreachable` exists in source per the guide inventory (:34); Respect Read-only Flags and the other decompiler analysis options are not documented request fields | per-build; the flag is part of the decompile basis | RO | designed | needed: G16 |
| D06 | Debug Function Decompilation: XML capture for one function [dw] | RO | DecompileView link menu on the function → an artifact in the dock; round 3: DecompileView (debug XML capture as an artifact) | catalog action needed | per-build | RO, CAT (artifact) | designed | needed: J01 |
| D07 | Graph Data Flow and Graph Control Flow from the decompiler [dw] | RO | GraphPane (parity extension: a data-flow mode) | `analyze-data-flow`; catalog action needed for the p-code graph | per-build | RO | designed | needed: R08 |
| D08 | Mouse actions: click, double-click, ctrl-double-click, middle-click highlight [dw] | RO | DecompileView typed tokens: Enter goes, Shift+Enter opens beside, Alt+↓ peeks, Shift+F10 opens the menu | none | per-build | RO | designed | backed (client) |
| D09 | Rename Variable, Rename Label and Rename Global [dw] | MUT | InlineRename (F2 or Enter on the token) | `rename-variable`, `rename-data-label`, `manage-function` | per-build, then propose→counterparts | CAT, CF-in, 1W, MC, NC | designed | backed |
| D10 | Rename Function from a token [dw] | MUT | InlineRename (link menu Rename…) | `rename-function`, `manage-function` | per-build, then propose→counterparts | CAT, CF-in, 1W, MC, NC | designed | backed |
| D11 | Rename Field of a structure from a token [dw] | MUT | InlineRename on the field token, confirmed by ConfirmDialog (type-wide) | `manage-structures` (`fieldName`, `newFieldName`) | layout-gated: the type may be shared by every use on a build; counterpart types renamed only by proposal | CAT, CF-dlg, 1W, MC, NC | designed | backed |
| D12 | Retype Variable, Retype Global [dw] | MUT | InlineRename (type mode, with completion) | `manage-function` (`set-local-variable-type` per the inventory, `newType`, `datatypeMappings`), `apply-data-type` | layout-gated per build | CAT, CF-in, 1W, MC | designed | backed |
| D13 | Retype Return [dw] | MUT | SignatureEditor (return row); StorageEditor for return storage | `manage-function` (`prototype`) | layout-gated; callers on the same build change, so confirm | CAT, CF-dlg, 1W, MC | designed | backed |
| D14 | Retype Field [dw] | MUT | TypeEditor, opened from the field token | `manage-structures` (`newDataType`) | layout-gated; a resize is cross-build | CAT, CF-dlg, 1W, MC | designed | backed |
| D15 | Commit Params/Return: writes the decompiler's recovered prototype to the program [dw] [dann] | MUT | DecompileView link menu on the function name → ActionStrip | catalog action needed | per-build; the prototype can be proposed to counterparts (`migrate-metadata` `propagatePrototype`) behind an ABI gate | CAT, CF-dlg (a callee-signature change), 1W, MC | designed | needed: W01 |
| D16 | Commit Local Names: writes decompiler-discovered local names and storage as variable annotations [dw] | MUT | DecompileView link menu → ActionStrip | catalog action needed | per-build | CAT, 1W | designed | needed: W01 |
| D17 | Edit Function Signature dialog [dw] [var] | MUT | SignatureEditor (hosts StorageEditor) | `manage-function` (`prototype`; modes `set_calling_convention` and `set_storage`) | per-build: conventions and registers come from that build's compiler spec; propose→counterparts only through the ABI gate | CAT, CF-dlg, 1W, MC, NC | designed | backed |
| D18 | Override Signature, Edit Signature Override, Remove Signature Override at a call site [dw] [dann] | MUT | SignatureEditor (call-site mode) from the callee token | catalog action needed | per-build and per call site; counterpart call sites only via anchors | CAT, CF-in, 1W | designed | needed: W02 |
| D19 | Split Out As New Variable [dw] | MUT | DecompileView link menu Edit group | catalog action needed | per-build | CAT, 1W | designed | needed: W03 |
| D20 | Force Field, Adjust Pointer Offset [dw] | MUT | DecompileView link menu; TypeEditor for the pointer-typedef | catalog action needed | layout-gated | CAT, CF-dlg, 1W | designed | needed: W04 |
| D21 | Auto Create Structure and Auto Fill in Structure from variable usage [dw] | MUT | DecompileView link menu → ActionStrip; the result opens TypeEditor | `manage-structures` (create); catalog action needed for usage-derived layout | per-build; the proposed `CacheEntry` layout is a hypothesis until each build's size check passes | CAT, CF-dlg, 1W, NP | designed | needed: R22, W05 |
| D22 | Edit Data Type from a type token [dw] | MUT | the `type=` link → TypeEditor | `manage-structures`, `manage-data-types` | layout-gated | CAT, CF-dlg, 1W | designed | backed |
| D23 | Comments from the decompiler at a statement address [dw] | MUT | InlineRename (comment mode, with catalog comment kinds) | `manage-comments` | per-build, then propose→counterparts | CAT, CF-in, 1W | designed | backed |
| D24 | Convert constant display (hex, decimal, char, …), Set Equate, Remove Convert/Equate [dw] [eq] | MUT | DecompileView and Listing link menu on a constant → ActionStrip | catalog action needed | per-build; offered to counterparts only when the operand anchors align | CAT, 1W | designed | needed: W06 |
| D25 | Highlight: Def-use, Forward Slice, Backward Slice, Forward/Backward Operator Slice [dw] | RO | DecompileView (parity extension: slice sets drawn as Highlight all sets and labelled with their basis) | `analyze-data-flow` (direction `forward`/`backward`; `find-variable-accesses`) | per-build | RO | designed | backed |
| D26 | Secondary Highlight: persistent multi-token highlights; next/previous highlight [dw] | RO | Highlight all sets A–D with a legend chip | none | per-build | RO, PV | designed | backed (client) |
| D27 | Go To Next/Previous Brace [dw] | RO | DecompileView (parity extension: keymap commands) | none | per-build | RO | designed | backed (client) |
| D28 | Find… in the decompiled function [dw] | RO | DecompileView find (Ctrl/Cmd+F is bound inside a code well) | none (over cached lines) | per-build | RO | designed | backed (client) |
| D29 | References from a token: variable, field, data type, function [dw] | RO | XrefPanel "References to ‹token›" | `get-references`; `manage-data-types` (find uses, per the inventory) | scope one/all | RO | designed | backed |
| D30 | Decompiler options: general, analysis, display and program options [dopt] | RO / program-affecting | OptionsPanel (display options per viewer; program options only through the catalog) | `decompile-function` (`includeComments`, `includeDisassembly`, …); catalog action needed for the analysis options as request fields and for the program option (Prototype evaluation) | builds compared on different options are flagged in the ProvenanceStamp basis | PV; program options CAT | designed | needed: G16, R17, W29 |
| D31 | Specification extensions: import or remove prototype and call-fixup extensions [dopt] | MUT | OptionsPanel (extensions section) | catalog action needed | per-build compiler spec; must match that build's language | CAT, CF-dlg, 1W | designed | needed: R17, W30 |
| D32 | Decompiler variable annotations: committed program variables vs decompiler-only high variables [dann] [dcon] | RO | DecompileView (parity extension: the token kind word says "committed" or "decompiler-only") | `decompile-function` | per-build | RO | designed | backed |

Deferred and out of core scope: decompiler taint (source/sink slice tree)
[taint]. It maps to `analyze-data-flow` views later. It is not counted.

### 3. Function Graph, call graph and call trees

| ID | Ghidra feature | R/M | AgentDecompile mapping | Backend | Multi-variant | Doctrine | Design | Backend status |
|---|---|---|---|---|---|---|---|---|
| G01 | Function Graph: basic blocks as vertices, typed edges, block navigation and info [fg] | RO | GraphPane Blocks | catalog action needed (basic-block and edge read) | per-build; CandidateAlignment aligns blocks across builds on anchors | RO, NA | designed | needed: R07 |
| G02 | Vertex grouping, path highlight (paths from/to, scoped flow), selection from paths and blocks [fg] | RO | GraphPane (parity extension) | catalog action needed | per-build | RO | designed | needed: R07 |
| G03 | Layouts (nested code, flow chart), zoom, satellite view, saved view state [fgl] [vg] | RO | GraphPane (zoom, pan, bounded drawing, list form); round 3: GraphPane (layouts, satellite, saved view state) | none | viewer | RO, PV | designed | backed (client) |
| G04 | Editing from graph vertices (vertex listings are editable) [fg] | MUT | GraphPane nodes are links; edits happen in the Listing; round 3: GraphPane (decision: no in-vertex editing) | as each edit | per-build | CAT | designed | backed |
| G05 | Function Call Graph: level edges, satellite, navigate on incoming location [fcg] | RO | GraphPane Calls (depth 1–3, bounded, "truncated" in words) | `get-call-graph` (mode `graph`) | per-build; the root maps to counterparts through anchors | RO | designed | backed |
| G06 | Function Call Trees: incoming and outgoing trees, recursive expand, navigate on location change [ct] | RO | CallHierarchy (the Calls mode of References) | `get-call-graph` (modes `tree`, `callers`, `callees`; `get-call-tree`) | per-build column with locator words | RO | designed | backed |
| G07 | Call tree filtering, depth, duplicate and thunk handling [ct] | RO | CallHierarchy (depth up to 3; recursion marked) | `get-call-graph` | per-build | RO | designed | backed |
| G08 | Program Graph: block flow, code flow, calls, data references; reuse or append a graph [pg] | RO | GraphPane (parity extension: bounded program scope) | `get-call-graph`; catalog action needed for block and code flow | per-build | RO | designed | needed: R07 |
| G09 | Data Graph: references from a data item [dg] | RO | GraphPane (parity extension: data-reference mode) | `get-references` | per-build | RO | designed | backed |
| G10 | Graph export: GraphML, DOT, GML, JSON, CSV and other formats [gexp] | RO (file) | GraphPane → ExportDialog | catalog action needed | per-build; the export records its basis | CAT (artifact) | designed | needed: J06 |
| G11 | Graph display popups: select vertices and edges, filter, show location [gdisp] [gintro] [gsvc] | RO | GraphPane list form (APG tree); round 3: GraphPane (filter and selection popups) | none | per-build | RO | designed | backed (client) |
| G12 | Function Comparison window: listing, decompiler and graph diff of N functions; navigate differences [fcmp] | RO | SplitCompare (F7/Shift+F7), CandidateAlignment | `decompile-function` per side; `match-function` | side-by-side, anchor-mapped, N-way in Compare | RO, NP (aligned ≠ equivalent) | designed | backed |
| G13 | Common callers of several functions (Ghidra: Call Trees on a selection) [ct] | RO | CallHierarchy (parity extension: multi-root) | `get-call-graph` (mode `common_callers`) | per-build | RO | designed | backed |

### 4. Symbol Tree, Symbol Table and references

| ID | Ghidra feature | R/M | AgentDecompile mapping | Backend | Multi-variant | Doctrine | Design | Backend status |
|---|---|---|---|---|---|---|---|---|
| S01 | Symbol Tree hierarchy: Imports, Exports, Functions, Labels, Classes, Namespaces [st] | RO | SymbolTree (the Symbols, Imports and Exports navigator scopes) | `manage-symbols`, `list-imports`, `list-exports` | a logical node shows per-build presence with LocatorGlyph | RO | designed | backed |
| S02 | Symbol Tree edits: create namespace or class, convert namespace to class, move by drag or cut/paste, delete, rename [st] | MUT | SymbolTree; InlineRename (F2); ActionStrip for move and delete | `manage-symbols`, `rename-function` | per-build, then propose→counterparts (namespace path per field) | CAT, CF-in (rename), CF-dlg (move or delete batch), 1W, MC, NC | designed | needed: W20 |
| S03 | External locations and libraries: create library, set external program, create/edit external location, external program names [st] [extn] | MUT | SymbolTree (Imports node) | catalog action needed | program-local | CAT, 1W | designed | needed: W21 |
| S04 | Symbol Tree navigation mode and snapshot/clone [st] | RO | Following vs HeldPane | none | per-build | RO | designed | backed (client) |
| S05 | Symbol Table: every symbol with name, location, type, namespace, source, reference count, offcut; filter queries [stab] | RO | ResultsTable (symbols) in the Symbols navigator scope | `manage-symbols`, `search-everything` (scope `symbols`) | logical rows with per-build columns, or scope one | RO | designed | backed |
| S06 | Symbol Table actions: rename, delete symbols or references, pin, set primary, make selection, temporary tables [stab] [stt] | MUT | ResultsTable + ActionStrip (checked set) | `manage-symbols`, `create-label` (`setAsPrimary`) | per-build | CAT, CF-dlg (batch delete), 1W, MC | designed | needed: W20 |
| S07 | Symbol References panel: references to, instructions from, data from; delete a reference [sref] | RO+MUT | XrefPanel; delete through ActionStrip | `get-references`; catalog action needed for delete | scope one/all | RO; delete CAT, 1W | designed | needed: W13 |
| S08 | Location References: references to an address, code unit, data type or field; results window [locref] | RO | XrefPanel; a type link lists its uses | `get-references`, `manage-data-types` | scope one/all with per-build counts | RO | designed | backed |
| S09 | Labels: add/edit, namespace chooser, remove, set primary [lbl] | MUT | InlineRename (F2 on a label); Listing link menu | `create-label`, `manage-symbols`, `rename-data-label` | per-build, then propose→counterparts at anchor-mapped addresses | CAT, CF-in, 1W, MC, NC | designed | backed |
| S10 | Label history [lbl] | RO | EntityTimeline (name edits); NameProvenance | catalog action needed (the program's label history) | per-build | RO | designed | needed: R13 |
| S11 | Set external entry point [lbl] | MUT | Listing link menu → ActionStrip; round 3: SymbolTree and Listing (external entry point) | catalog action needed | program-local | CAT, 1W | designed | needed: W20 |
| S12 | Namespaces and classes for functions and labels [st] [var] | MUT | SymbolTree; SignatureEditor namespace field | `manage-function` (namespace, per the inventory), `manage-symbols` | per-build; the class is a logical entity across builds | CAT, 1W, NC | designed | backed |
| S13 | Demangled names and demangling [aa] | MUT | NameProvenance (authentic-symbol tier) | `manage-symbols` (`demangleAll`) | per-build | CAT, NA | designed | backed |

### 5. Data Type Manager and type editors

| ID | Ghidra feature | R/M | AgentDecompile mapping | Backend | Multi-variant | Doctrine | Design | Backend status |
|---|---|---|---|---|---|---|---|---|
| T01 | Data Type Manager tree: built-in, program, file (.gdt) and project archives; categories; filter [dtm] [dtmw] | RO | TypeManager (a Types navigator scope) | `manage-data-types` (archives, categories) | logical type rows with per-build presence and size columns | RO | designed | backed |
| T02 | Archive lifecycle: open, create, close, set architecture, save, archive undo/redo, delete [dtm] | MUT | TypeManager | catalog action needed | a shared archive is the natural cross-build type carrier | CAT, CF-dlg, 1W (one archive writer) | designed | needed: W17 |
| T03 | Source-archive sync: update, commit, revert, disassociate, refresh indicators, archive paths [dtma] | MUT | TypeManager (sync state column) | catalog action needed | the primary way to sync types per build; per-build sync state; commits are layout-gated | CAT, CF-dlg, 1W | designed | needed: R23, W17 |
| T04 | Categories: create, rename, delete, move, copy [dtm] | MUT | TypeManager | catalog action needed (`manage-data-types` `categoryPath` is read-only in the docs) | per-build or archive | CAT, 1W | designed | needed: W17 |
| T05 | Data types: create, rename, edit, delete, move, copy [dtmw] | MUT | TypeManager + TypeEditor | `manage-structures`, `manage-data-types`, `create-structure`, `edit-structure`, `create-enum`, `edit-enum` | layout-gated per build | CAT, CF-dlg, 1W, MC, NC | designed | needed: W18 |
| T06 | Replace and Merge data types; conflict resolution mode [dtmw] | MUT | TypeManager → ConfirmDialog with use counts per build | catalog action needed | cross-build ConfirmDialog; every use on each build changes | CAT, CF-dlg, 1W, MC | designed | needed: W18 |
| T07 | Find types by name, by size, enums by value, structures by size or by offset [dtmw] | RO | TypeManager filters | `manage-data-types`, `manage-structures` (`nameFilter`), `search-everything` (scope `data_types`) | scope one/all with per-build hit columns | RO | designed | needed: R23 |
| T08 | Apply Function Data Types and Capture Function Data Types [dtmw] | MUT | TypeManager → ActionStrip | catalog action needed (the API reference documents `ApplyFunctionDataTypesCmd`) | per-build batch | CAT, CF-dlg, 1W | designed | needed: W19 |
| T09 | Export data types, create labels from enums, show base type, display as graph [dtmw] | RO+MUT | TypeManager actions | `export` (`includeTypes`); catalog action needed for the rest | per-build | RO; label creation CAT | designed | needed: W18, J06 |
| T10 | Structure/union editor: component grid, name, description, size, alignment, packing, bitfields, flexible arrays, insert, move, duplicate, delete, clear, create array, unpackage, create from selection, go to offset, editor undo/redo [se] | MUT | TypeEditor (composite mode) | `manage-structures` (`fields`, `fieldName`, `dataType`, `offset`, `bitfield`, `packed`, `newLength`, …) | layout-gated: the edit applies to one build's type manager or a shared archive; a per-build size and offset delta table precedes Save; propose→counterparts only when layouts are identical | CAT, CF-dlg (resize, overwrite, clear), 1W, MC, NC | designed | backed |
| T11 | Enum editor: entries, values, hex toggle, add, delete, apply [ee] | MUT | TypeEditor (enum mode) | `manage-data-types`, `create-enum`, `edit-enum` | side-by-side value sets per build | CAT, CF-dlg, 1W, NC | designed | backed |
| T12 | Typedefs, pointers (with pointer-typedef settings), arrays [data] [dtm] | MUT | TypeEditor (typedef and pointer modes) | `manage-data-types`, `apply-data-type` (array syntax) | layout-gated; pointer width differs by build language | CAT, 1W | designed | needed: W04 |
| T13 | Function definitions: create one from a function [var] | MUT | TypeEditor (function-definition mode) | catalog action needed | per-build | CAT, 1W | designed | needed: W18 |
| T14 | Data type chooser: completion, typed pointer and array creation, browse [dtsel] | RO | InlineRename type field with completion from the build's type manager | `manage-data-types` (list) | per-build completion; warns when the type is absent on a counterpart | RO | designed | backed |
| T15 | C-Parser: parse headers into types [cparse] | MUT | TypeManager (import header); a C-definition validation path exists per the inventory | `manage-structures` (`cDefinition`, `headerContent`) | into one build or a shared archive; per-build size validation | CAT, CF-dlg, 1W, NP (a parse is not layout proof) | designed | backed |
| T16 | Data Type Preview window: types previewed at the cursor without applying [dtp] | RO | Peek (parity extension: type-at-address preview) | `get-data`, `inspect-memory` (mode `data`) | anchor-mapped: the same type previewed at each counterpart address | RO, NP | designed | backed |
| T17 | Data types table: flat table with a program-types filter [dtt] | RO | ResultsTable (types) | `manage-data-types` | per-build columns | RO | designed | backed |
| T18 | Favorites, recently used types, cycle groups [data] | RO | TypeManager favourites and recently used (per viewer); TypeEditor Cycle (cycle groups, as a draft retype) | none | viewer | PV | designed | backed (client) |
| T19 | Structure and union editor tool options: hex display, and related options [se] | RO | OptionsPanel | none | viewer | PV | designed | backed (client) |

### 6. Program Trees, Memory Map, relocations, equates, registers

| ID | Ghidra feature | R/M | AgentDecompile mapping | Backend | Multi-variant | Doctrine | Design | Backend status |
|---|---|---|---|---|---|---|---|---|
| P01 | Program Tree folders and fragments: create, delete, rename, move code units, merge, sort, select, restrict the view [ptree] | RO+MUT | ProgramTreeView (navigator scope); ContainerTree covers file containers only | catalog action needed | per-build; a logical module grouping may map to fragments | CAT, 1W | designed | needed: R12, W24 |
| P02 | Program tree views and organizations: default tree, subroutine, dominance, complexity depth [pview] [porg] | MUT | ProgramTreeView | catalog action needed | per-build | CAT, 1W | designed | needed: R12, J03 |
| P03 | Memory Map table: name, range, length, RWX, volatile, overlay, type, initialized, source, comment [mm] | RO | MemoryMapTable (the Sections navigator scope) | `inspect-memory` (`get-memory-blocks`) | side-by-side section maps per build; ImageDeltaMap for a rebuild | RO | designed | backed |
| P04 | Memory block edits: rename, permissions, volatile, artificial, initialize, comment; add, move, split, expand, merge, delete; set image base; rename overlay [mm] | MUT | MemoryMapTable → inline editor (one block) or ActionStrip + ConfirmDialog | catalog action needed | program-local; never propagated. Rename, permission, volatile, artificial and comment edits on one block confirm in place in the inline editor; restructuring (add, move, split, expand, merge), destructive changes (delete, initialize, set uninitialized, rename overlay) and set image base use ConfirmDialog. An image-base change invalidates absolute pinned locators, and the dialog names the affected anchors | CAT, CF-dlg, 1W, MC, NA | designed | needed: W22 |
| P05 | Relocation table [reloc] | RO | ResultsTable (relocations) | catalog action needed | program-local; feeds ObjectDiff's relocation-aware equality | RO | designed | needed: R12 |
| P06 | Equates: view table, rename, remove, edit/show/apply enum; convert display (signed/unsigned decimal, hex, octal, char, binary, float, double) [eq] | RO+MUT | ResultsTable (equates); Listing link menu on operands | catalog action needed | per-build; names offered to counterparts only at anchor-aligned operands | CAT, 1W, NC | designed | needed: R12, W06 |
| P07 | Register Manager: register and context values over ranges; set, clear, delete ranges [reg] | RO+MUT | RegisterValuesEditor | catalog action needed | program-local; context registers differ by build language | CAT, CF-dlg, 1W, NA (re-disassembly follows only when admitted) | designed | needed: R12, W23 |
| P08 | Processor language: view and change language or compiler spec; installed processors [lang] [procs] | MUT | build crumb Peek shows the language id; a change goes through ActionStrip + ConfirmDialog; round 3: ProgramSettings | `change-processor`, `list-processors` | program-local; re-disassembly requires admission | CAT, CF-dlg, 1W, NA | designed | needed: J17 (was backed) |
| P09 | Program options and About Program: metadata, compiler, hashes, properties [popt] [about] | RO | build crumb Peek; the evidence rail build header | `get-current-program`, `open` | per-build; hashes identify builds | RO | designed | backed |
| P10 | Block models: basic, isolated entry, multiple entry, partitioned, overlapped [blk] | RO | GraphPane (parity extension: model selector) | catalog action needed | per-build | RO | designed | needed: R07 |
| P11 | Validate Program: post-analysis problem detection [val] | RO | ProblemsList (findings as predicates, typed links); round 3: ProgramValidation | catalog action needed | per-build | RO | designed | needed: R14, R35, J16 |
| P12 | Property Viewer: program properties at addresses [prop] | RO | Peek (parity extension) | catalog action needed | per-build | RO | designed | needed: R12 |

### 7. Strings, data, bookmarks, comments, labels

| ID | Ghidra feature | R/M | AgentDecompile mapping | Backend | Multi-variant | Doctrine | Design | Backend status |
|---|---|---|---|---|---|---|---|---|
| A01 | Defined Strings table: columns, make selection, refresh, settings [dstr] | RO | ResultsTable (strings) in the Strings navigator scope; Outline Strings for the current function | `manage-strings` (mode `list`, `includeReferencingFunctions`); catalog action needed for string settings (charset, rendering) | logical string rows across builds matched by content, with per-build addresses | RO | designed | needed: W12 |
| A02 | Defined Data window: all defined data, type filter, make selection [dwin] | RO | ResultsTable (defined data) | `inspect-memory` overload `list_data_items(offset, limit)` (TOOLS_LIST:942) enumerates data items; `get-data` per address. A data-type filter is not documented | per-build | RO | designed | backed |
| A03 | Translate strings and charsets; translation services [tr] [charsets] [libre] | MUT | ResultsTable (strings) row action; round 3: ResultsTable (translation and charsets) | catalog action needed | per-build | CAT | designed | needed: J08 |
| A04 | Bookmarks: add in the Listing; categories and types; Bookmarks window [bm] | RO+MUT | MarksList: the program Bookmarks scope (read-only) and per-viewer marks; saving a program bookmark posts on Run | `manage-bookmarks` | program-local per build; logical marks resolve per build; program bookmarks go to counterparts only by proposal (`migrate-metadata` `propagateBookmarks`) | CAT, 1W, PV (marks) | designed | backed |
| A05 | Bookmarks window actions: edit category and description, remove, filter, select [bm] | RO+MUT | MarksList (parity extension: edit and remove program bookmarks through ActionStrip) | `manage-bookmarks` (`removeAll`, `categories`, `types`) | per-build | CAT, CF-dlg (bulk remove), 1W | designed | backed |
| A06 | Comments: set or edit EOL, pre, post, plate, repeatable; delete [cm] | MUT | InlineRename (comment mode with the catalog's comment kinds) | `manage-comments` (`commentType`) | per-build, then propose→counterparts (PropagationTransfer comment field) | CAT, CF-in, 1W, MC | designed | backed |
| A07 | Comment history [cm] | RO | EntityTimeline (parity extension: comment edits) | catalog action needed (the program's comment history) | per-build | RO | designed | needed: R13 |
| A08 | Comment window: table of every comment [cw] | RO | ResultsTable (comments) | `manage-comments` (`searchText`, `pattern`), `search-everything` (scope `comments`) | scope one/all | RO | designed | backed |
| A09 | Comment annotations: symbol, address and URL links inside comments [ann] | RO | typed links rendered in comment text (linked views); round 3: Listing (comment annotations) | none | links resolve on the same build | RO | designed | backed (client) |
| A10 | Field names: Edit Field Name dialog for data components [fieldnames] | MUT | InlineRename on the Listing field-name cell | `manage-structures` (`newFieldName`) | layout-gated; type-wide, so ConfirmDialog | CAT, CF-dlg, 1W, NC | designed | backed |
| A11 | Labels from the Listing: rename a label in place [lbl] | MUT | InlineRename (F2) | `create-label`, `rename-data-label` | per-build, then propose→counterparts | CAT, CF-in, 1W, NC | designed | backed |

### 8. Functions

| ID | Ghidra feature | R/M | AgentDecompile mapping | Backend | Multi-variant | Doctrine | Design | Backend status |
|---|---|---|---|---|---|---|---|---|
| F01 | Create function, re-create function, create multiple functions [fn] | MUT | Listing link menu → ActionStrip; round 3: Listing (Function group: create) | `manage-function` (create, per the inventory); `list-functions` (`get-undefined-function-candidates`) | per-build; propose on counterparts only at accepted anchors | CAT, 1W, MC | designed | backed |
| F02 | Delete function [fn] | MUT | ActionStrip + ConfirmDialog (destructive); round 3: Listing (Function group: delete) | `manage-function` (delete, per the inventory) | per-build | CAT, CF-dlg, 1W | designed | backed |
| F03 | Rename function [fn] | MUT | InlineRename (F2 on the EntityRow or the composite header name) | `rename-function`, `manage-function` | per-build, then propose→counterparts | CAT, CF-in, 1W, MC, NC | designed | backed |
| F04 | Thunk functions: set thunk target, follow thunk [fn] | RO+MUT | SignatureEditor thunk field; XrefPanel | `manage-function` (thunk target, per the inventory); `get-references` (`resolve-thunk`) | per-build | CAT, 1W | designed | backed |
| F05 | External functions [fn] | RO | SymbolTree (Imports) | `list-imports`, `get-references` (`find-import-references`) | per-build; the same import on each build forms a logical row | RO | designed | backed |
| F06 | Calling convention from the program's compiler spec [var] | MUT | SignatureEditor convention list | `manage-function` mode `set_calling_convention` | per-build; never borrow another build's spec | CAT, CF-dlg, 1W | designed | backed |
| F07 | Custom storage: parameter and return storage; the Edit Parameter Storage dialog [var] | MUT | StorageEditor | `manage-function` mode `set_storage` | layout-gated per build: registers come from that build's spec; no storage propagation without an ABI gate | CAT, CF-in, 1W, MC | designed | backed |
| F08 | Varargs, No Return and Inline attributes [var] | MUT | SignatureEditor flags | `manage-function` (flags, per the inventory) | per-build; No Return changes callers' flow, so confirm | CAT, CF-dlg (No Return), 1W | designed | backed |
| F09 | Call-fixup [var] | MUT | SignatureEditor call-fixup picker from the build's spec | `manage-function` (call fixup, per the inventory) | per-build spec | CAT, 1W | designed | backed |
| F10 | Function purge and stack depth change: set and remove [fn] | MUT | SignatureEditor (purge); Listing link menu (stack depth); round 3: Listing (stack depth) and SignatureEditor (purge) | catalog action needed | per-build | CAT, 1W | designed | needed: W08 |
| F11 | Variables: rename, retype, delete; define data type [var] | MUT | InlineRename; CodeBrowser Outline Locals | `manage-function` (`rename-variable`, `set-local-variable-type`, per the inventory) | per-build | CAT, CF-in, 1W, NC | designed | needed: W07 |
| F12 | Function repeatable comment [fn] | MUT | InlineRename (repeatable kind) | `manage-comments` | per-build, then propose→counterparts | CAT, CF-in, 1W | designed | backed |
| F13 | Stack frame editor: local size, parameter offset and size, stack variables (create, delete, clear, retype, array), hex display [stack] | MUT | StackFrameEditor | catalog action needed (`manage-function` variable operations cover part) | side-by-side frames per build; layouts differ by compiler | CAT, CF-dlg, 1W, MC, NC | designed | needed: R20, W07 |
| F14 | Function tags: create, delete, edit; add to or remove from functions; load external tags; tag window [ftag] | MUT | Functions list tag filter (FilterChip); ResultsTable (tags); ActionStrip | `manage-function-tags`; `list-functions` (`filterByTag`, `untagged`) | a tag on a logical entity is offered to each accepted counterpart (`match-function` `propagateTags`) | CAT, 1W | designed | backed |
| F15 | Function window: every function, navigate on incoming location, make selection, compare selected [fwin] | RO | the one Functions list (EntityRow grid) | `list-functions`, `get-functions` | logical rows with counterpart counts; Compare selected opens SplitCompare | RO | designed | backed |
| F16 | Function signature source (default, analysis, imported, user-defined) [bff] | RO | NameProvenance tier beside the signature | `get-function` | per-build | RO | designed | backed |

### 9. Disassembly, clearing, data creation, references

| ID | Ghidra feature | R/M | AgentDecompile mapping | Backend | Multi-variant | Doctrine | Design | Backend status |
|---|---|---|---|---|---|---|---|---|
| E01 | Disassemble, static and restricted disassembly, processor-mode variants, processor options [dis] | MUT | Listing link menu on undefined bytes → ActionStrip | catalog action needed (the script namespace has `disassemble` per the inventory; there is no bounded tool) | per-build | CAT, 1W, NA (follow-on analysis only if admitted) | designed | needed: W09 |
| E02 | Modify instruction flow (branch, call, call-return, return overrides) and modify instruction length [dis] [dann] | MUT | Listing link menu → ReferenceEditor (flow section) | catalog action needed | per-build; changes only that build's decompile | CAT, CF-dlg, 1W | designed | needed: W10 |
| E03 | Fallthrough override: set, auto override, clear [fall] | MUT | ReferenceEditor (fallthrough field) | catalog action needed | per-build | CAT, 1W | designed | needed: W10 |
| E04 | Clear Code Bytes, Clear With Options (symbols, comments, properties, instructions, data, references, functions, registers, equates, bookmarks), Clear Flow and Repair [clr] | MUT | ActionStrip + ConfirmDialog (destructive) | catalog action needed (the script's `clearListing` only) | per-build; never cross-build | CAT, CF-dlg, 1W, MC | designed | needed: W11 |
| E05 | Create data: apply built-in and user types; data settings (format, endianness, charset) [data] | MUT | Listing link menu "Set data type…" → InlineRename (type mode) | `apply-data-type`, `manage-data-types` | layout-gated; propose at counterpart addresses (anchor-mapped) | CAT, CF-in, 1W, MC | designed | needed: W12 |
| E06 | Create array, pointer, string; create structure from a selection; quick Edit Field dialog [data] | MUT | Listing link menu → ActionStrip; TypeEditor | `apply-data-type`, `manage-structures` | layout-gated; array counts never copied blindly between builds | CAT, CF-dlg (structure from selection), 1W | designed | backed |
| E07 | Add/Edit References dialog: memory, external, stack and register panels; ref-type; operand; primary [refs] [refs-intro] | MUT | ReferenceEditor | catalog action needed (`get-references` is read-only) | per-build | CAT, CF-in, 1W, MC | designed | needed: W13 |
| E08 | Create default reference; delete references from a code unit [refs] | MUT | Listing link menu → ActionStrip | catalog action needed | per-build | CAT, 1W | designed | needed: W13 |
| E09 | Add memory references from a selection; Create Offset References Table [refs] [offtab] | MUT | ReferenceEditor → ActionStrip batch | catalog action needed | per-build | CAT, CF-dlg, 1W | designed | needed: W13 |
| E10 | Stack and register references and their variable binding [refs] | MUT | ReferenceEditor (stack and register panels) | catalog action needed | per-build; storage from the build's spec | CAT, 1W | designed | needed: W13 |
| E11 | Make address tables and disassemble their targets [saddr] | MUT | ResultsTable (address tables) → ActionStrip | catalog action needed | per-build | CAT, CF-dlg, 1W, NA | designed | needed: R11, W15 |

### 10. Searches

| ID | Ghidra feature | R/M | AgentDecompile mapping | Backend | Multi-variant | Doctrine | Design | Backend status |
|---|---|---|---|---|---|---|---|---|
| Q01 | Search Memory: hex, binary, string, regex, decimal, float, double; incremental forward/back; combined searches; scan controls [smem] [sfmt] | RO | SearchWorkbench (memory mode) → ResultsTable | catalog action needed (byte-pattern search is not in the documented tool set) | scope one/all; per-build hit columns; one pattern at different addresses is expected | RO | designed | needed: R10 |
| Q02 | Search Program Text: labels, comments, mnemonics, operands, data fields; incremental and search all; regular expression syntax [stext] [regex] [searching] | RO | SearchWorkbench (text mode); CommandPalette | `search-everything` (scopes `comments`, `symbols`, `disassembly`, …) | scope one/all | RO | designed | backed |
| Q03 | Search for Matching Instructions: masks built from a selection [smnem] | RO | SearchWorkbench (instruction mode) | `search-code` searches disassembly or p-code text only; catalog action needed for operand masks and a masked byte search | scope one/all; a masked pattern is a candidate identity channel only | RO, NP | designed | needed: R03, R10 |
| Q04 | Instruction Pattern Search dialog: instruction table, preview, bounds, manual entry [sinstr] | RO | SearchWorkbench (instruction mode) | `search-code` (text patterns only); catalog action needed for the instruction table's operand masks and a masked byte search | scope one/all | RO | designed | needed: R03, R10 |
| Q05 | Search for Scalars: specific value or range; selection scope; scalar table filters [scalar] | RO | SearchWorkbench (scalar mode) → ResultsTable | `search-constants` (modes `specific`, `range`, `common`) | scope one/all with per-build hits | RO | designed | backed |
| Q06 | Search for Strings: minimum length, alignment, terminator, charset; make strings; encoded strings [sstr] | RO+MUT | SearchWorkbench (string mode); a "Make string" row action | `manage-strings`, `search-everything` (scope `strings`); catalog action needed to make a string | scope one/all | RO; make CAT, 1W | designed | needed: W14, R10 |
| Q07 | Search for Direct References: scan memory for address values; alignment filter [sdref] | RO | SearchWorkbench (direct-reference mode) | catalog action needed | per-build (address values are build-specific) | RO | designed | needed: R11 |
| Q08 | Search for Address Tables: minimum length, alignment, skip [saddr] | RO | SearchWorkbench (address-table mode) | catalog action needed | per-build | RO | designed | needed: R11 |
| Q09 | Search results window: navigation, marker margin, rename, make selection, remove items, selection navigation [sres] | RO | ResultsTable; MarksList worklist (F8 stepping); FilterChip | none | per-build hit columns | RO, PV | designed | backed (client) |
| Q10 | Search and Replace: labels, comments, types, namespaces, regex; apply changes [srepl] | MUT | SearchWorkbench (replace mode) → ActionStrip batch + ConfirmDialog | catalog action needed for the batch replace (search via `search-everything`) | a per-build preview; across builds, a cross-build ConfirmDialog | CAT, CF-dlg, 1W, MC, NC | designed | needed: W16 |
| Q11 | Wildcard assembler patterns for instruction search [wasm] | RO | SearchWorkbench (instruction mode, wildcard syntax) | catalog action needed | scope one/all | RO | designed | needed: R05, R10 |
| Q12 | Search Decompiled Text across functions; select matching functions [dtf] | RO | SearchWorkbench (decompiled-text mode) → ResultsTable | `search-code` (`search-decompilation`), `search-everything` (scope `decompilation`) | scope one/all with per-build hit columns; never decompiles builds that have not been decompiled without saying so | RO, NA | designed | backed |

### 11. Analysis

| ID | Ghidra feature | R/M | AgentDecompile mapping | Backend | Multi-variant | Doctrine | Design | Backend status |
|---|---|---|---|---|---|---|---|---|
| Z01 | Auto analysis on import or open; Ask To Analyze [aa] | MUT | WorkflowControl (pause/resume admission; no Start); ImportAdmission | `analyze-program` (`force` only for a deliberate reanalysis), `manage-workflow` (`prepare`) | per-build admission; valid receipts reused | NA, 1W | designed | backed |
| Z02 | Analyzer list and options: enable, disable, per-analyzer options, saved configurations [aa] | MUT | AnalyzerPanel (reads the current configuration; changes through the catalog) | catalog action needed | analysis options should match across builds; per-build configuration differences are shown | CAT, CF-dlg, NA | designed | needed: R17, W28 |
| Z03 | Analyze All Open [aa] | MUT | workflow scope; never a per-stage button | `manage-workflow` | corpus admission; one writer per project | NA, 1W | designed | backed |
| Z04 | One-shot analysis: one analyzer on a selection [aa] | MUT | ActionStrip bound to the selection | catalog action needed | per-build | CAT, 1W, NA (explicit only) | designed | needed: J02 |
| Z05 | Analysis log and background task progress [aa] [showlog] [prg-ann] | RO | ActivityRecord in the dock (Logs, Jobs) | `read-workspace-activity` | per-build jobs | RO | designed | backed |
| Z06 | Headless analyzer [headless-help] [headless] | MUT | no UI; admitted through the workflow | `manage-workflow` | corpus | NA, 1W | designed | backed |
| Z07 | Load PDB (symbol servers, parser options) or external DWARF debug files; SARIF import [pdb] [loadpdb] [dwarf] [sarif] | MUT | ImportAdmission; ContextPlacement for context pieces; round 3: DebugInfoImport | catalog action needed (`export` writes SARIF; the import path is not documented) | per-build (debug info is build-specific); the NameProvenance debug-info tier | CAT, 1W | designed | needed: J04, J18 |
| Z08 | Demangler, aggressive instruction finder and other prototype analyzers [aa] | MUT | AnalyzerPanel | catalog action needed | per-build | CAT, NA | designed | needed: R17, W28, J02 |
| Z09 | Source files table and source map entries [srcf] | RO | NameProvenance debug-info witness; SourceRepairDiff; round 3: DebugInfoImport (source files table) | catalog action needed | per-build | RO | designed | needed: J04, R36 |

### 12. Patching, Program Diff, Version Tracking

| ID | Ghidra feature | R/M | AgentDecompile mapping | Backend | Multi-variant | Doctrine | Design | Backend status |
|---|---|---|---|---|---|---|---|---|
| X01 | Assembler: Patch Instruction, Assemble…, Patch Data [asm] | MUT | PatchEditor (original-byte preview, exact target, confirm, post-write read) | catalog action needed | per-build only; never propagated; patching the original is not recovery | CAT, CF-dlg, 1W, MC | designed | needed: R05, W26 |
| X02 | Program Diff: open the diff view; determine differences (bytes, code units, references, comments, symbols, functions, bookmarks, properties, context) over ranges; navigate; select [diff] | RO | SplitCompare (entity level); ObjectDiff | `match-function`; catalog action needed for program-level range diff | build-a vs build-c aligned by anchors, not raw addresses | RO, NP | designed | needed: R15, J05, R25 |
| X03 | Apply or ignore differences; apply settings (replace, merge, ignore per category) [diff] [vt-apply] | MUT | PropagationTransfer (per field) + ConfirmDialog; round 3: PropagationTransfer (per-category apply settings) | `migrate-metadata` (`propagateNames`, `propagateTags`, `propagateComments`, `propagatePrototype`, `propagateBookmarks`) | per recipient gate; blocked recipients keep their value | CAT, CF-dlg, 1W, MC | designed | backed |
| X04 | Viewing difference details at a location [diff] | RO | SplitCompare difference Peek | none beyond X02 | side-by-side | RO | designed | needed: R15 |
| X05 | Version Tracking sessions: correlators (exact bytes, instructions, mnemonics, symbol name, data, references, implied, manual, BSim), matches table, markup items, accept, apply markup, dual listing [vt] [vtcorr] [vtmatch] [vtmark] [gvt] [vt-wiz] [vt-flow] [vt-pre] [vt-fn] [vt-impl] [vt-rel] | RO+MUT | MatchReview, ReviewDetail, CandidateAlignment, CounterpartMatrix, PropagationTransfer | `match-function`, `migrate-metadata`, `bsim-report`; stage-1 catalog verbs `corpus.match-pair` and `corpus.extract-stabs` (the consolidated plan) | the product's native N-way form; accepted edges drive propagation | CAT, CF-dlg (decisions), 1W, NP (similarity proposes; evidence accepts) | designed | backed |
| X06 | Auto Version Tracking [vt] [vt-auto] | MUT | pipeline stage 1 (automatic, no button) | `manage-workflow` | corpus | NA, 1W | designed | backed |
| X07 | Version Tracking manual match: create, accept, apply [vt-tool] | MUT | ReviewDetail decision controls; round 3: ReviewDetail (manual match) | catalog action needed for a manual edge | the identity edge between two builds | CAT, CF-dlg, 1W | designed | needed: W31 |
| X08 | Function Bit Patterns Explorer: mine function-start byte patterns [fbp] | RO | not planned | catalog action needed | across builds | RO | missing | needed (not planned) |

### 13. Scripting

| ID | Ghidra feature | R/M | AgentDecompile mapping | Backend | Multi-variant | Doctrine | Design | Backend status |
|---|---|---|---|---|---|---|---|---|
| C01 | Script Manager: category tree, table, filter, run, run last, quick launcher, create, rename, delete, key binding, directories [sm] [scriptdev] | MUT | ScriptConsole (advanced; gated by the catalog); round 3: ScriptConsole (manager actions, catalog-gated) | `execute-script` | runs against one explicitly targeted build | CAT, CF-dlg (unrestricted mutation), 1W | designed | needed: R34, W34 |
| C02 | Console: output, scroll lock, clear, find, navigation from addresses [con] | RO | ActivityRecord log tail with typed links | `read-workspace-activity` | per job | RO | designed | backed |
| C03 | PyGhidra interpreter: interactive session, interrupt, reset [pyi] | MUT | ScriptConsole (REPL mode) | `execute-script` | one build | CAT, 1W | designed | backed |
| C04 | Bundle Manager: script source bundles, enable, clean, refresh [bun] | MUT | not planned; round 3: ScriptConsole (bundle actions, catalog-gated) | catalog action needed | none | none | designed | needed: R34, W34 |
| C05 | Script key bindings and Quick Action (Ctrl-3) launcher [sm] [kbn] | RO | CommandPalette actions from `GET /api/v1/actions` | catalog | none | RO | missing | needed: G13 |

### 14. Undo, transactions, multi-user, import and export

| ID | Ghidra feature | R/M | AgentDecompile mapping | Backend | Multi-variant | Doctrine | Design | Backend status |
|---|---|---|---|---|---|---|---|---|
| V01 | Undo/Redo of program transactions [undo] | MUT | EditHistory (per-build transaction list; Undo and Redo as catalog verbs); EntityTimeline shows edits | catalog action needed | per-build; undoing a propagated edit is per recipient | CAT, CF-in (a single top undo or redo of a single-target edit, per `edit.undo`), CF-dlg (batch, cross-build, multi-step or a job's transaction), 1W | designed | needed: R18, W27 |
| V02 | Transactions and modification conflicts [undo] | MUT | ActionStrip → OutcomeCell; the StateNotice conflict state | `resolve-modification-conflict` | per-build | MC, 1W | designed | backed |
| V03 | Save, Save As, Save All [save] | MUT | durable, crash-safe saves (the consolidated plan §4.7); round 3: ProjectWindow (Save, Save As, Save All) | catalog action needed for explicit save of a program | per-build | CAT, 1W | designed | needed: W32, W36 |
| V04 | Multi-user repository: connect, add to version control, check out, check in, undo checkout, update, version history, view/find checkouts, undo hijack; server connection [vc] [fe] [gserver] | MUT | VersionControlPanel (per-build checkout state); OwnershipPanel for exclusive checkouts | `checkout-program`, `checkin-program`, `checkout-status`, `sync-project`, `svr-admin` | per-build domain file; an exclusive checkout is the one-writer lock | CAT, CF-dlg (check-in), 1W | designed | needed: R19, W33 |
| V05 | Merge on check-in: auto merge; resolve conflicts in memory, trees, types, context, listing, externals, properties [merge] | MUT | MergeReview (adapted to check-in conflicts) | `checkin-program`; catalog action needed for conflict choices | per-build | CAT, CF-dlg, 1W, MC | designed | needed: R19, W33, J15 |
| V06 | Exporters: ASCII, C/C++, GZF, GDT, HTML, hex-record formats, Original File, Raw Bytes, XML, SARIF [exp] | RO (file) | ExportDialog (format, options, build; the artifact lands in the dock) | `export` (formats `gzf`, `c`, `cpp`, `sarif`, `xml`, `html`, `ascii`); `manage-workflow` (`export-source`) | one job per build; a batch across builds confirms | CAT (artifact), NP (exported C ≠ recovered source) | designed | needed: J06 |
| V07 | Importers: import file, batch import, load libraries, add to program, per-format options, language and compiler choice, library search path [imp] | MUT | ImportAdmission | `import-binary`, `open`, `list-processors` | variant grouping comes from match evidence | CAT, NA | designed | backed |
| V08 | File System Browser: browse containers, import from them, export, view as text or image [fsb] | RO | ContainerTree | `export-context` | per container | RO | designed | backed |
| V09 | Project window and program files: create, open, reopen, close, delete projects; data tree and table; open, close, rename, move, delete programs; read-only views of other projects and repositories [fe] [fe-proj] [prg-open] [fe-open] [fe-reopen] [fe-close] [fe-del] [fe-save] [fe-info] [fe-menus] [prg-close] | RO+MUT | SessionTab; the project navigator scope; ContainerTree; round 3: ProjectWindow | `list-project-files`, `manage-files`, `delete-project-binary` | builds are project members | CAT, CF-dlg (delete), 1W | designed | needed: W37 (was backed) |
| V10 | Archive and restore a project [fe-archive] [fe-restore] | MUT | project manager (F02); round 3: ProjectWindow (archive and restore) | `export` (`gzf`); catalog action needed for a whole-project archive | corpus | CAT | designed | needed: J07 |

### 15. Identification tools, utilities, keyboard and options

| ID | Ghidra feature | R/M | AgentDecompile mapping | Backend | Multi-variant | Doctrine | Design | Backend status |
|---|---|---|---|---|---|---|---|---|
| I01 | Function ID: the FID analyzer and FidDb management (choose, attach, detach, create, populate, debug search) [fid] [fidp] [fid-debug] | RO+MUT | NameProvenance (a FID name is an analysis-tier candidate); no FidDb management; round 3: FunctionIdManager | catalog action needed | per-build; a FID name on build-a reaches build-c only through an identity edge | CAT, NA, NP | designed | needed: J09 |
| I02 | BSim: overview query, similar-function search, filters, results, compare functions, databases; the BSim Version Tracking correlator [bsim] [bsimov] [bsimcorr] [bsim-ingest] [bsim-db] [bsim-cli] [bsim-fw] | RO | CandidateAlignment (BSim evidence channel); MatchReview | `bsim-createdatabase`, `bsim-ingest`, `bsim-report` | corpus-wide; similarity proposes, never accepts | RO, NP; ingest CAT, 1W | designed | backed |
| I03 | Checksum generator: checksum-8/16/32, Adler-32, CRC-16/32, MD5, SHA family, over a selection or everything [cks] | RO | HexStrip selection → link menu "Checksums" in a Peek (parity extension) | catalog action needed | anchor-mapped: the same range hashed on each build is cheap divergence evidence | RO | designed | needed: R16, R25 |
| I04 | Evaluator: Ghidra has no help topic by that name; the nearest are Go To Expression [addrx] and equate Convert [eq] | RO | NavigationBar expression prefix; Peek scalar conversions | catalog action needed | per-build | RO | designed | needed: R09 |
| I05 | Key bindings: change, remove, import, export [tool] | RO | KeymapSettings (`keymap.json` plus a per-viewer diff) | none | viewer | PV | designed | backed (client) |
| I06 | Tool Options dialog: restore defaults, tool and program caching [tool] | RO | View settings; OptionsPanel for decompiler, byte viewer and search options, linking to ListingFieldLayout for Listing operand, EOL and xref options | none | viewer | PV | designed | backed (client) |
| I07 | Keyboard navigation: component traversal and the Quick Action dialog [kbn] [acc] | RO | F6 regions; CommandPalette | `GET /api/v1/actions` | none | RO | designed | backed |
| I08 | Docking windows and tool configuration: move, stack, tab, rename transient windows; configure and save tools [dock] [tooladm] [cfgtool] | RO | Workstation regions; LayoutPresets (five presets plus a per-viewer diff) | none | viewer | PV | designed | backed (client) |
| I09 | Accessibility: screen-reader guidance [acc] | RO | AccessibleView and the accessibility guideline | none | viewer | RO | designed | backed (client) |
| I10 | Tables and tree filters: sort, choose columns, column settings and filters, copy, CSV export; tree filter strategy, globbing, multi-term [tables] [tfilt] | RO | ResultsTable; the Functions grid typeahead (`/`) and FilterChip | none (client) | per-build columns | RO, PV | designed | backed (client) |

Not counted: printing [print] (the browser's print of the AccessibleView is
enough), theming (out of scope), IDE integrations, and the database viewer.

## Components added for parity

This section was "New components needed" in the first pass; component READMEs
still cite it by that name. Every component the first pass listed as NEW now
exists under
[`docs/design-system/project/components/`](../design-system/project/components/).
Each follows the design system: typed links, one selection owner, words beside
glyphs, the Linking block, and catalog-only mutation. The Rows column repeats
each README's "Parity rows covered" section as read on 2026-09-29 after the
round-2 review.

| Component | Purpose | Rows its README claims | Actions it still needs |
|---|---|---|---|
| [ListingFieldLayout](../design-system/project/components/ListingFieldLayout/README.md) | Per-viewer Listing field formatter: fields and rows per row kind, field options, optional columns, flow-arrow and marker margins, collapsible function bodies. Owns the operand, EOL and XREF field display options. | L10, L11, L12, L31; display options of L02–L04, L08, L09; margins of L15, L16 | R02, R09 |
| [OverviewBar](../design-system/project/components/OverviewBar/README.md) | Navigation margin with address-type, byte-entropy, marker and divergence lanes, a text key and ranges list; per-build bars in Compare. | L16, L17, L18; margins of Q09 | R06, R25, R32 |
| [SymbolTree](../design-system/project/components/SymbolTree/README.md) | Namespace, class, import, export and label treegrid with per-build presence, edits per build and proposals. | S01, S02, S03, S12, F05; S04 (Reveal current); the tree-filter part of I10 | W20, W21, J14 |
| [ProgramTreeView](../design-system/project/components/ProgramTreeView/README.md) | Program trees, folders and fragments, view restriction, organizations as admitted jobs. | P01, P02 | R12, W24, J03, R07 |
| [MemoryMapTable](../design-system/project/components/MemoryMapTable/README.md) | Memory map per build, inline single-block editor, block operations, Align builds with variance class. | P03, P04 | W22, R32 |
| [ResultsTable](../design-system/project/components/ResultsTable/README.md) | The one results table: sort, filter, columns, CSV, make selection, worklists, per-build hit columns, a checked set for the ActionStrip. | L24, S05, S06, T17, P05, P06, A01, A02, A03, A08, F14, E11, Q09, I10; the result side of Q01–Q08, Q10, Q12 | R12, W06, W12, W13, W14, W15, W20, J08 |
| [SearchWorkbench](../design-system/project/components/SearchWorkbench/README.md) | One search surface in memory, text, decompiled-text, instruction, wildcard, scalar, string, direct-reference, address-table and replace modes. | Q01–Q12 | R03, R05, R10, R11, W14, W15, W16 |
| [TypeManager](../design-system/project/components/TypeManager/README.md) | Archives and categories with per-build type columns, sync state, find by name, size or offset, replace and merge, apply and capture, header import. | T01–T09, T15, T18 (favourites and recents) | R23, W17, W18, W19, J06 |
| [TypeEditor](../design-system/project/components/TypeEditor/README.md) | Structure, union, enum, typedef and pointer, array, function-definition and inferred modes, a per-build layout check before Save, proposals; a read-only following form for Walk pointers. | D14, D20, D21, D22, T05, T10–T13, E06, T19 (hex), T18 (cycle groups) | R22, R24, W04, W05, W18, J14 |
| [SignatureEditor](../design-system/project/components/SignatureEditor/README.md) | Prototype, convention from the build's spec, storage (hosts StorageEditor), attributes, call fixup, thunk, purge, namespace, call-site overrides, ABI-gated proposals. | D13, D17, D18, F04, F06–F10 (purge part of F10), S12; F11 in the grid | R21, R24, W02, W08, J14 |
| [StackFrameEditor](../design-system/project/components/StackFrameEditor/README.md) | The frame by logical slot with per-build columns, frame fields, stack variables, proposals by slot mapping. | F13, F11 (delete variable) | R20, R28, W07, J14 |
| [ReferenceEditor](../design-system/project/components/ReferenceEditor/README.md) | Memory, external, stack and register references, flow, length and fallthrough overrides, references from a selection and offset tables. | E02, E03, E07–E10; E08 results | W10, W13, R21, R25 |
| [RegisterValuesEditor](../design-system/project/components/RegisterValuesEditor/README.md) | Register and context values over ranges per build, with the consequence before Save and Track cursor. | P07 | R12, W23, W09, R25 |
| [PatchEditor](../design-system/project/components/PatchEditor/README.md) | Assemble, patch data, bytes, clear, disassemble and create data on one build with original-byte preview and post-write read. | N12, X01; the preview panel of E01, E04, E05, E06 | R04, R05, W09, W11, W12, W26 |
| [AnalyzerPanel](../design-system/project/components/AnalyzerPanel/README.md) | Analyzer enablement and options per build, configurations, one-shot runs, analysis state and log. | Z02, Z04, Z08 | R17, W28, J02 |
| [ScriptConsole](../design-system/project/components/ScriptConsole/README.md) | Script manager, transcript, interpreter bound to one build, read-only bundles. | C01, C03; C02, C04 (read-only), C05 (declined) | R34, W34, G13 |
| [VersionControlPanel](../design-system/project/components/VersionControlPanel/README.md) | Checkout state per build, check in, update and merge, history, other checkouts; an exclusive checkout is the writer lock. | V04; V05, V02 | R19, W33, J15 |
| [ExportDialog](../design-system/project/components/ExportDialog/README.md) | One exporter per call over a function, selection, program, graph or archive, one job per build, artifacts in Outputs. | D03, G10, V06; V10 (one build's GZF), T09 (type export) | J06, R33 |
| [OptionsPanel](../design-system/project/components/OptionsPanel/README.md) | Per-viewer tool options (decompiler display and analysis request options, byte viewer, structure editor, search) beside read-only program options per build. | I06, D30, D31, D05, N11, T19; links to L04, L08, L09 | G16, R17, W29, W30 |
| [EditHistory](../design-system/project/components/EditHistory/README.md) | One build's transactions with Undo, Redo and Undo to here; a single top undo of a single-target edit confirms in place. | V01; V02, V03 (saved versus checked in) | R18, W27 |

### Extensions to existing components

Each is a "Parity extensions (2026-09-29)" section in that component's README.

- **Listing**: operand and EOL display options, function header rows,
  collapsible variable rows, inline composite data with a Field name column, one
  row kind per comment type, flow-arrow Go to source and target, address-set
  selection with next and previous range, select by flow, next and previous
  commands per code-unit kind. Rows: L04, L06–L09, L13, L15, L21, L22, N03, N04.
- **DecompileView**: options through OptionsPanel, slice highlight sets with
  next and previous, brace navigation, the committed or decompiler-only word, and
  Edit-group items for Commit Params/Return, Commit Local Names, Split Out, Force
  Field, Adjust Pointer Offset, Auto Create/Fill Structure and Convert/Set Equate.
  Rows: D05, D15, D16, D19–D21, D24–D27, D32.
- **GraphPane**: data-flow mode, grouping and path highlight, program-scope
  graphs, data-reference graphs, block-model selector, Export graph. Rows: D07,
  G02, G08, G09, G10, P10.
- **HexStrip**: integer, octal, binary, char, address and disassembled formats;
  byte viewer options from OptionsPanel; Select bytes with a count; Checksums.
  Rows: N10, N11, L23, I03.
- **Peek**: instruction info, speculative disassembly (a hypothesis), type at
  address on one or every build, checksums, program properties. Rows: L27, L28,
  T16, I03, P12.
- **XrefPanel**: display options, thunk references, instructions from and data
  from, Delete reference. Rows: L09, L30, S07.
- **CallHierarchy**: filters and a common-callers mode. Rows: G07, G13.
- **NavigationBar**: wildcards and repeat, `=` expressions, `file:` offsets, the
  evaluator row. Rows: N01, N02, I04.
- **MarksList**: edit and remove program bookmarks, filter and select. Row: A05.
- **EntityTimeline**: comment and label history events. Rows: A07, S10.
- **SplitCompare**: program-level range diff aligned by anchors and a
  difference-detail Peek. Rows: X02, X04.

## Rows not yet designed

2 rows are not designed, both by decision. Round 3 designed the other 26 rows this section listed in round 2 (see each row's "round 3" mapping).

| ID | Feature | Design | Backend status | Reason |
|---|---|---|---|---|
| X08 | Function Bit Patterns Explorer | missing | needed (not planned) | Not planned: it authors function-start pattern files for the analysers, a tool-level change that would force re-analysis of every build instead of reusing receipts, and its evidence is heuristic (recorded in ProgramValidation). |
| C05 | Script key bindings and Quick Action launcher | missing | needed: G13 | By decision until scripts are catalog entries. The future design is specified: a Scripts section in the CommandPalette, with no new key, where Enter opens the run confirm and never runs. |

## Backend and catalog gaps

The [catalog contracts for parity](2026-09-29-catalog-contracts-for-parity.md)
turn every gap below into proposed catalog actions (34 reads, 34 writes,
15 jobs and 16 contract or schema gaps); the ids after each item point there.
Items the component READMEs added since the first pass are listed after the
original lists.

Each entry needs a catalog action (listed in `GET /api/v1/actions` with its
target fields, its mutating flag and its resource claim) and a provider. A
documented tool that already covers part of the gap is named. The mutating
flag matters because the consolidated plan records a verb that advertises
non-mutating while it writes. Admission must use real owner state, not the
flag alone.

**Read gaps.** All are RO and add no writer.

1. A paged, section-wide Listing read: code units with address, bytes,
   mnemonic, operands, labels, comments by type, flow targets, xref counts and
   the function header (L01, L06–L09, L13) → R01.
2. Per-instruction extras: p-code, stack depth, register transitions, file
   offset and source map entry (L10, L11) → R02, R09.
3. Instruction info: the instruction prototype, operand objects, inputs and
   outputs (L27) → R03.
4. Non-committing speculative disassembly at an address (L28) → R04.
5. Code-unit type map and entropy per block for the overview bar (L17, L18) → R06.
6. Basic blocks and typed edges per function, with a selectable block model;
   program-scope block and code-flow graphs (G01, G08, P10) → R07.
7. A p-code or data-flow graph for one function (D07) → R08.
8. Address-expression evaluation and file-offset ↔ address mapping (N02, I04) → R09.
9. Byte-pattern memory search with formats, masks, alignment and scope (Q01) → R10.
10. Direct-reference and address-table scans (Q07, Q08) → R11.
11. Wildcard-assembler instruction patterns (Q11) → R05.
12. Enumeration of defined data, the relocation table, equates, program trees,
    register and context value ranges, the program's comment and label
    history, program properties, and validation findings (A02, P01, P05–P07,
    A07, S10, P11, P12) → R12, R13, R14.
13. Program-level diff over address ranges by category, aligned by anchors
    between two builds (X02, X04) → R15, J05, R25.
14. Checksums over a range (I03) → R16.
15. The analyzer configuration of each build (Z02) → R17.
16. Debug-decompile capture for one function as an artifact (D06) → J01.

**Write gaps.** Each needs a catalog verb with CAT and 1W. Destructive or
batch verbs also need CF-dlg, and MC where custom data can be overwritten.

1. Commit Params/Return and Commit Local Names (D15, D16) → W01.
2. Call-site signature override: set, edit and remove (D18) → W02.
3. Split out variable, force field, adjust pointer offset, auto-create
   structure from usage (D19–D21) → W03, W04, R22, W05.
4. Convert constant display, set/rename/remove equate, apply enum to an
   operand (D24, P06) → W06.
5. Delete a variable; set or remove function purge and stack depth change
   (F10, F11) → W07, W08.
6. Stack frame edits (F13) → W07.
7. Disassemble variants; modify instruction flow and length; fallthrough
   override; clear with options; clear flow and repair (E01–E04) → W09, W10, W11.
8. Reference create, edit and delete for memory, external, stack and register
   references, plus offset tables (E07–E10, L30, S07) → W13.
9. Make string and make address table from search results (Q06, E11) → W14, W15.
10. Batch search-and-replace over names, comments and types (Q10) → W16.
11. Type archive lifecycle, category edits, source-archive sync, replace and
    merge, apply and capture function data types, function definitions, create
    labels from enums (T02–T04, T06, T08, T09, T13) → W17, W18, W19.
12. Symbol Tree edits: namespace and class creation, move, delete, external
    locations and library association, set external entry point (S02, S03,
    S11) → W20, W21.
13. Memory block edits and image base (P04) → W22.
14. Register and context value ranges (P07) → W23.
15. Program tree and fragment edits (P01, P02) → W24, J03.
16. Program bookmark edit and remove, surfaced as catalog verbs;
    `manage-bookmarks` already accepts the fields (A05) → W25.
17. Byte and instruction patching with original-byte preview and post-write
    read (N12, X01) → W26, R05.
18. Undo and redo of a program transaction (V01) → W27, R18.
19. Analyzer options, one-shot analyzers, spec extensions; all admission-bound
    (Z02, Z04, D31) → W28, J02, W30.
20. Import of PDB, external DWARF and SARIF as context or annotations (Z07) → J04.
21. A manual identity edge from the review surface (X07) → W31.
22. Explicit program save and a whole-project archive (V03, V10) → W32, J07.
23. Translate strings (A03) → J08.
24. FidDb management (I01) → J09.
25. Additional exporters: GDT, hex records, original file, raw bytes (V06) → J06.

**Contract gaps.** These cut across the matrix.

- Mode lists for `manage-function`, `manage-symbols`, `manage-comments`,
  `manage-bookmarks`, `manage-data-types`, `manage-structures` and
  `manage-strings` are documented only as "see MCP schema" in TOOLS_LIST. The
  catalog must expose them so that each Edit-group item can be derived rather
  than hand-listed per frontend (F22). → G01.
- Every write verb needs a propagation companion that produces
  PropagationTransfer rows for one field and a recipient set. Today
  `migrate-metadata` and `match-function` propagate names, tags, comments,
  prototypes and bookmarks in bulk. Parity needs a per-field,
  per-recipient-gated verb with receipts. → G02, J14.
- Layout-gated application needs a read that returns, for a type or storage
  proposal, each build's size, alignment, pointer width and register
  availability. It must run before any cross-build ConfirmDialog. → G03, R24.

**Added by the component READMEs since the first pass.**

- String settings (charset, rendering) and data settings (format,
  endianness) (A01, E05) → W12.
- Decompiler analysis options as per-viewer request fields of the decompile
  read, and the program option Prototype evaluation (D05, D30) → G16, R17, W29.
- Stored frames, spec facts, type presence with sync state and use counts,
  inferred structures, transactions and version history (F13, D17, T03, T07,
  D21, V01, V04) → R20, R21, R23, R22, R18, R19.
- Version-control verbs beyond check-out and check-in, and update with merge
  (V04, V05) → W33, J15.
- Script files and bundles (C01, C04) → R34, W34; scripts as catalog entries
  (C05) → G13.
- The compiler-aware and outputs views (no parity rows): R26–R33, J10–J13 and
  G09–G12, G14.

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
- **Addresses move only through anchors.** Moving the cursor from ResourceRef::Resolve
  at 0041b210 on build-a to its counterpart at 00082f40 on build-c uses recorded anchor pairs. Between
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

## Appendix: actions and sections named in each cited help page

Each line lists the level-2 and level-3 headings of one help page, in page
order, with the matrix rows that cite the page. Headings are Ghidra's names
for actions, dialogs, fields and options. The only change is that product,
vendor and platform names have been replaced with generic words. A row cites a
page when it covers some or all of that page's actions. Where a page names
more actions than its rows cover, the row's status is partial or missing and
says which part is absent.

| Help file | Rows | Actions and sections named in the help |
|---|---|---|
| [`BSim/BSimOverview.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/BSim/src/main/help/help/topics/BSim/BSimOverview.html) | I02 | Quick Reference Links · Overview · Overview of Tools · Note |
| [`BSim/CommandLineReference.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/BSim/src/main/help/help/topics/BSim/CommandLineReference.html) | I02 | bsim_ctl · bsim · Ghidra and BSim URLs · Ghidra Server/Project Repository URLs · BSim Database URLs |
| [`BSim/DatabaseConfiguration.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/BSim/src/main/help/help/topics/BSim/DatabaseConfiguration.html) | I02 | Overview · Server Configuration · Relational database backend configuration · Warning · Search-engine backend configuration · Creating a Database · Tailoring BSim Metadata · Executable Categories · Function Tags · Creating Database Templates |
| [`BSim/FeatureWeight.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/BSim/src/main/help/help/topics/BSim/FeatureWeight.html) | I02 | Features of Software Functions · Weighting Software Features · Comparing Feature Vectors · Similarity · Confidence |
| [`BSim/IngestProcess.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/BSim/src/main/help/help/topics/BSim/IngestProcess.html) | I02 | Ingest Process · Analysis · Generating Features and Function Metadata · Importing Features to a BSim Database · Tailoring Analysis · Ingesting Executable Categories · Ingesting Function Tags · Analysis Effects on Feature Extraction · Maintenance · Deleting Executables · Updating Names and Other Metadata · Dropping the Feature Vector Index · Prewarming the Database · Migration |
| [`BSimSearchPlugin/BSimSearch.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/BSim/src/main/help/help/topics/BSimSearchPlugin/BSimSearch.html) | I02 | Enabling the BSim Search Plugin · Defining and Managing BSim Databases · Defining a new BSim server/database · BSim Overview Query · BSim Overview Results · BSim Similar Function Search · Standard Fields · Filters · Similar Function Search Results · Function Matches Panel · Executable Match Summary · Actions · Comparing Functions · Loading Executables · Authentication |
| [`About/About_Program_File.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/About/About_Program_File.htm) | P09 | To view information about the currently open (active) program · To view information about any program in the project window · Standard information displayed in the "About Program" dialog · To close this dialog |
| [`Accessibility/AccessibilityOverview.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Accessibility/AccessibilityOverview.html) | I07, I09 | Screen-Reader Guidance · Keyboard Navigation · Quick Action Dialog (Ctrl-3) · Script Launcher (Ctrl-Shift-S) · Known Limitations |
| [`Annotations/Annotations.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Annotations/Annotations.html) | A09 | Examples · Valid Annotations · Errors |
| [`AssemblerPlugin/Assembler.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/AssemblerPlugin/Assembler.htm) | X01 | Actions · Patch Instruction · Assemble... · Patch Data |
| [`AutoAnalysisPlugin/AutoAnalysis.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/AutoAnalysisPlugin/AutoAnalysis.htm) | S13, Z01, Z02, Z03, Z04, Z05, Z08 | Auto Analysis · Analyze All Open · One Shot Analysis · Ask To Analyze · Auto Analysis Options Panel · Saved Options Configurations · Analysis Panel Buttons · Auto Analyzers · Address Table Analyzer · Processor-specific analyzer (32-bit RISC) · ASCII Strings Analyzer · Data Archive Analyzer · Data Reference Analyzer · Decompiler Parameter ID Analyzer · Demangler Analyzer · Demangler (per compiler family) · Entry Point Analyzer · Embedded Media Analyzer · Processor-specific address markup analyzer (A) · Processor-specific address markup analyzer (B) · Propagate External Parameters Analyzer · Scalar Operand Analyzer · Stack Analyzer · Subroutine Reference Analyzer · x86 PE analyzers · (Prototype) Auto Analysis Plugins · Aggressive Instruction Finder · Condense Filler Bytes Analyzer · Format String Analyzer · (Variadic Function Signature Override) |
| [`BlockModel/Block_Model.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/BlockModel/Block_Model.htm) | P10 | (single section) |
| [`BookmarkPlugin/Bookmarks.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/BookmarkPlugin/Bookmarks.htm) | A04, A05 | Add a Bookmark (in the CodeBrowser) · Remove a Bookmark (in the CodeBrowser) · Bookmarks Window · Edit Category · Edit Description · Change the Sort Order · Navigate to a Bookmark · Filter Bookmarks · Reorder Columns · Make Selection in the Code Browser · Remove Bookmarks · Dismiss the Bookmarks Window |
| [`BundleManager/BundleManager.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/BundleManager/BundleManager.htm) | C04 | Dynamic modules · Source bundles · Exploded Bundles · Generated Files · Dependency · Intra-bundle (compile time) Dependency · Inter-bundle (run time) Dependency · Enabling and disabling bundles · Adding and removing bundles from the manager · Cleaning bundles · Refresh bundles |
| [`CParserPlugin/CParser.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/CParserPlugin/CParser.htm) | T15 | Setting up to Parse · C++ Header files · Tips: |
| [`CallTreePlugin/Call_Tree_Plugin.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/CallTreePlugin/Call_Tree_Plugin.html) | G06, G07, G13 | Filtering · Actions · Context Menu Actions |
| [`Charsets/Charsets.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Charsets/Charsets.htm) | A03 | Unicode Code Point · Unicode Scripts · Charset Picker · Name · Description · Fixed Length · Min BPC / Max BPC (Bytes Per Character) · Scripts · Charset Details · Aligned Size |
| [`ClearPlugin/Clear.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ClearPlugin/Clear.htm) | E04 | Clear Code Bytes · Clear With Options · Symbols · Comments · Properties · Instructions · Data · User-defined References · Analysis References · Import References · Default References · Functions · Registers · Equates · Bookmarks · Clear Flow and Repair · Clear Symbols · Clear Data · Repair |
| [`ClipboardPlugin/Clipboard.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ClipboardPlugin/Clipboard.htm) | L26 | Default Operations · Copy · Paste · Custom Operations · Copy Special · Supported Windows · Listing · Bytes in Memory |
| [`CodeBrowserPlugin/Browser_Field_Formatter.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/CodeBrowserPlugin/Browser_Field_Formatter.htm) | L06, L08, L11, L12, F16 | Configuring the Format · Adding Fields · Removing Fields · Moving Fields · Disabling Fields · Enable Field · Insert Row · Remove Row · Reset Format · Reset All Formats · Quick Toggle Actions · Custom Formats · Create Custom Format · Delete Custom Format · Save Custom Format · Available Fields |
| [`CodeBrowserPlugin/CodeBrowser.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/CodeBrowserPlugin/CodeBrowser.htm) | L01, L07, L13, L14, L15, L16, L19, L29, L30, L31 | Main Display · The View · Cursor · Selection · Highlight · Background Color · Navigation · Xrefs · Refresh · Show Thunk Xrefs · Delete Reference · Labels · Delete Label · Keyboard Controls · Markers · Margin Marker · Navigation Marker · Flow Arrows · Selecting Flow Arrows · Disabling Flow Arrows · Navigating Flow Arrows · Mouse Hover · Reference Popups · Truncated Text Popups · Data Type Popups · Address Popup · Function Name Popup · Scalar Popup · Disabling Mouse Hover · Opening/Closing Structures and Arrays · Actions for Expanding/Collapsing Data · Opening/Closing Functions · Actions for Opening/Closing a Function · Opening/Closing Function Variables Display · Actions for Opening/Closing Function Variables Display · Cursor Text Highlight · Default Settings · Configuring · Errors in Fields |
| [`CodeBrowserPlugin/CodeBrowserOptions.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/CodeBrowserPlugin/CodeBrowserOptions.htm) | L02, L03, L04, L05, L08, L09, L10, L19 | Color and Fonts · Font · Screen Element · Color · Style Settings · Swatches/HSB/RGB · Preview · Fields, Highlights, & Selections · Address Field · Array Options · Bytes Field · Cursor Text Highlight · EOL Comments Field · File Offset Field · Function Offset Field · Imagebase Offset Field · MemoryBlock Offset Field · Format Code · Function Pointers · Function Signature Field · Labels Field · Mnemonic Field · Operands Field · PCode Field · Selection Colors · Source Map Field · Template Display Options · XREFs Field · Popups · Listing Popups · Reference Code Viewer |
| [`CodeBrowserPlugin/ListingBackground.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/CodeBrowserPlugin/ListingBackground.html) | L20 | Changing Colors · Actions · Service · Navigating Colors · Markers |
| [`CodeBrowserPlugin/SelectionTable.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/CodeBrowserPlugin/SelectionTable.htm) | L24 | Range Table Actions |
| [`CommentWindowPlugin/comment_window.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/CommentWindowPlugin/comment_window.htm) | A08 | Make Selection |
| [`CommentsPlugin/Comments.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/CommentsPlugin/Comments.htm) | A06, A07 | Adding or Editing Comments (Set Comment) · Deleting Comments · Navigating in the Code Browser · Displaying Comment History |
| [`ComputeChecksumsPlugin/Generate_Checksum_Help.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ComputeChecksumsPlugin/Generate_Checksum_Help.html) | I03 | Checksum-8 · Checksum-16 · Checksum-32 · Adler-32 · CRC-16 · CRC-16/CCITT · CRC-32 · MD2 · MD5 · SHA-1 · SHA-256 · SHA-384 · SHA-512 · Using the Checksum Generator · Checksum Options: · Generating Checksums: |
| [`ConsolePlugin/console.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ConsolePlugin/console.html) | C02 | Scroll Lock · Clear · Find · Navigation |
| [`DWARFExternalDebugFilesPlugin/DWARFExternalDebugFilesPlugin.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DWARFExternalDebugFilesPlugin/DWARFExternalDebugFilesPlugin.html) | Z07 | Configuration · Button actions: · Debug location types: |
| [`DataPlugin/Data.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DataPlugin/Data.htm) | T12, T18, E05, E06 | Data Types · Built-In Data Types · User-Defined Data Types · Applying Data Type · Drag from Data Type Manager · Cycle Groups · Favorites · Recently Used Data Type · Clearing Data · Changing Data Settings · Creating Other Data Types · Structure · Union · Enum · Pointer · Array · Typedef · Void · String Data Types · Dynamic Data Type · Quick Editing of a Structure or Union Field · Edit Field Dialog |
| [`DataTypeEditors/DataTypeSelectionDialog.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DataTypeEditors/DataTypeSelectionDialog.htm) | T14 | Completion Window · Creating Pointers and Arrays · Data Type Browser |
| [`DataTypeEditors/EnumEditor.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DataTypeEditors/EnumEditor.htm) | T11 | Enum Editor Fields · Edit an Enum Entry · Toggle Hex Mode · Add an Enum Entry · Delete an Enum Entry · Apply Changes · Show In Data Type Manager · Change the Sort Order |
| [`DataTypeEditors/StructureEditor.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DataTypeEditors/StructureEditor.htm) | T10, T19 | Applying Changes · Undo Change · Redo Change · Show In Data Type Manager · Closing the Editor · Searching in the Editor · Changing the Name · Entering a Description · Changing the Size · Alignment · Packed vs. Non-Packed · Non-Packed Structures · Packed Structures · Non-packed Unions · Packed Unions · Bitfield Component · Zero-Element / Flexible Array Components · Edit Actions · Insert Undefined Byte · Move Up · Move Down · Duplicate Component · Duplicate Multiple of Component... · Delete Component(s) · Clear Component(s) · Create Array · Create Zero-Element / Flexible Array Component · Unpackage Component · Create Structure From Selection · Bitfield Actions (Non-Packed Structures) · Add Bitfield · Edit Bitfield · Component Fields · Editing Component Fields · Applying an Edit · Canceling an Edit · Editing More Than One Component Field · Editing the DataType Field · Editing the Name Field · Editing the Comment Field · Pointers · Cycling a Component Data Type · Union or Packed Structure · Non-Packed Structure · Drag and Drop Basics · Favorites Basics · Adding a Data Type · Drag and Drop · Favorites · Inserting a Data Type · Replacing a Data Type · Go To Next / Previous Defined Type · Go To Offset · Showing a Component's Data Type Category · Editing a Component's Data Type · Toggling Hex/Decimal Display · Structure and Union Editor Tool Options · Bitfield Editor (Non-Packed Structures only) · Bitfield Parameters |
| [`DataTypeManagerPlugin/data_type_manager_archives.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DataTypeManagerPlugin/data_type_manager_archives.html) | T03 | Updating Archives · Committing to Archives · Reverting Data Types · Disassociating Data Types · Refreshing Sync Indicators For Data Types · Edit Data Type Archive Paths |
| [`DataTypeManagerPlugin/data_type_manager_description.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DataTypeManagerPlugin/data_type_manager_description.htm) | T01, T02, T04, T12 | Topics · Basic Concepts · Data Types · Data Type Archives · Built-In Data Type Archive · File Data Type Archive · Project Data Type Archive · Data Types in a Program · Categories · Data Type Manager Tree · Applying Data Types · Resolving Data Types · Source Archive · Client Archive · Committing Changes To Source Archive · Updating Data Types From Source Archive · Reverting · Synchronizing an Archive · File Archive Path · Working with Data Type Archives · Opening a File Data Type Archive · Opening a Project Data Type Archive · Creating a New File Data Type Archive · Creating a New Project Data Type Archive · Setting Data Type Archive Architecture · Clearing Data Type Archive Architecture · Closing a Data Type Archive · Opening a File Data Type Archive for Editing · Closing a File Data Type Archive for Editing · Saving Changes to a Data Type Archive · Saving a File Data Type Archive to a New File · Undo Unsaved Archive Change · Redo Unsaved Archive Change · Deleting a Data Type Archive · Removing an Invalid Data Type Archive · Updating an Archive From a Source Archive · Committing Changes in an Archive To a Source Archive · Reverting Changes in an Archive Back To a Source Archive · Disassociating Data Types in an Archive From a Source Archive · Refreshing Data Type Sync Indicators in an Archive For a Source Archive · Version Control / Multi-user Actions on Project Archives · Working with Categories · Creating a New Category · Renaming a Category · Deleting a Category · Moving a Category · Copying a Category · Working with Data Types · Applying Data Types to a Program · Creating New User Defined Data Types · Renaming a Data Type · Editing a Data Type · Creating a new Enum from a Selection of Enums · Deleting a Data Type · Moving a Data Type · Copying a Data Type · Reverting Changes · Disassociate a Data Type · Associate a Data Type with a Source Archive · Replacing a Data Type · Merging Data Types · Setting Favorite Data Types · Pointer-Typedef Settings |
| [`DataTypeManagerPlugin/data_type_manager_window.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DataTypeManagerPlugin/data_type_manager_window.html) | T01, T05, T06, T07, T08, T09 | The Data Type Tree · Filter · Data Type Conflict Resolution Mode · Local Toolbar Actions · Local Menu Actions · Miscellaneous Actions · Copy · Cut · Delete · Paste · Rename · Compare... · Replace... · Merge... · Collapse All · Expand All · Associate With Archive · Apply Function Data Types · Capture Function Data Types · Find Data Types by Name · Find Data Types by Size · Find Enums by Value · Find Structures by Size · Find Structures by Offset · Export Data Type(s) · Create Labels From Enums · Show Base Data Type · Display Data Type as Graph |
| [`DataTypeManagerPlugin/data_types_table.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DataTypeManagerPlugin/data_types_table.html) | T17 | Drag and Drop · Actions · Select Data Types in Tree · Program Types Filter · Data Types Table Clone |
| [`DataTypePreviewPlugin/DataTypePreviewPlugin.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DataTypePreviewPlugin/DataTypePreviewPlugin.html) | T16 | Adding Data Types · Removing Data Types |
| [`DataWindowPlugin/data_window.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DataWindowPlugin/data_window.htm) | A02 | Make Selection · Filtering Types |
| [`DefinedStringsPlugin/DefinedStringsPlugin.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DefinedStringsPlugin/DefinedStringsPlugin.htm) | A01 | Defined Strings Table Columns · Defined Strings Menus and Actions · Make Selection · Refresh · Settings... and Default Settings... · Translate |
| [`DisassembledViewPlugin/DisassembledViewPlugin.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DisassembledViewPlugin/DisassembledViewPlugin.htm) | L28 | Main Display · Display Settings |
| [`DisassemblerPlugin/Disassembly.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DisassemblerPlugin/Disassembly.htm) | E01, E02 | Disassembly · Disassembler Options · Static Disassembly · Restricted Disassembly · Disassemble in an alternate instruction-set mode · Processor Options · Modify Instruction Flow · Modify Instruction Length |
| [`DockingWindows/Docking_Windows.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/DockingWindows/Docking_Windows.htm) | N08, I08 | The Basic Dockable Component · Title Bar · Local Toolbar · Menu Icon · Close Icon · Work Area · Arranging Components · Moving Components · Resizing components · Renaming Components Transient components (e.g., search windows) can be… |
| [`EquatePlugin/Equates.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/EquatePlugin/Equates.htm) | D24, P06, I04 | Set Equate · Rename Equate · Remove Equate · Edit Enum · Show Enum · Apply Enum · View Equates · Convert · Signed Decimal · Unsigned Decimal · Unsigned Octal · Signed Hex · Unsigned Hex · Char / Char Sequence · Unsigned Binary · Float · Double |
| [`ExporterPlugin/exporter.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ExporterPlugin/exporter.htm) | V06 | Export Action · To export from the front-end project window: · To export from the CodeBrowser tool: · Export Dialog · Dialog Fields · Exporters · Ascii · C/C++ · Ghidra Zip File (GZF) · Ghidra Data Type Archive File (GDT) · HTML · Hex-record format · Original File · Raw Bytes · XML · SARIF |
| [`FallThroughPlugin/Override_Fallthrough.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FallThroughPlugin/Override_Fallthrough.htm) | E03 | Set a Fallthrough Address · Auto Override · Clear Overrides |
| [`FileSystemBrowserPlugin/FileSystemBrowserPlugin.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FileSystemBrowserPlugin/FileSystemBrowserPlugin.html) | V08 | Introduction · GHIDRA Tool File Menu Actions · Open File System · Right-click Context Menu Actions · Get Info · Expand All · Collapse All · Open File System in new window · Open Program(s) · Import · Batch Import · Add To Program · Export · Export All · Add Library Search Path · View As Image · View As Text · List Mounted File Systems · Clear Cached Passwords · Refresh · Close · Browser Dialog Actions · Open File System Chooser · Password Dialog · How To Handle Unsupported File Systems · Known issues · Strong Crypto Support |
| [`FlowSelection/Selection_By_Flow.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FlowSelection/Selection_By_Flow.html) | L22 | Forward and Reverse Scoped Flow |
| [`FrontEndPlugin/Archive_Project.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FrontEndPlugin/Archive_Project.htm) | V10 | Why Archive a Project? · When Archiving Errors Occur |
| [`FrontEndPlugin/Close_Project.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FrontEndPlugin/Close_Project.htm) | V09 | (single section) |
| [`FrontEndPlugin/Connecting_Tools.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FrontEndPlugin/Connecting_Tools.htm) | N09 | Automatic Tool Connection · Manual Tool Connection · Connecting Tools · Disconnect Tools |
| [`FrontEndPlugin/Creating_a_Project.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FrontEndPlugin/Creating_a_Project.htm) | V09 | Creating a Shared Project |
| [`FrontEndPlugin/Deleting_a_Ghidra_Project.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FrontEndPlugin/Deleting_a_Ghidra_Project.htm) | V09 | (single section) |
| [`FrontEndPlugin/Ghidra_Front_end.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FrontEndPlugin/Ghidra_Front_end.htm) | V04, V09 | Tool Chest · Active Project · Project Data Tree · Tree Only Actions · Project Data Table · Actions for Both the Data Tree and the Data Table · Version Control Actions · File Icons · Ghidra URL Formats · Read-Only Project Data · View Other Projects · View a Shared Project · View a Repository · View Recent · Close View · Close All Read-Only Views · Create Linked Folder or File · Workspaces · Running Tools · Ghidra Server Connection Status · Edit Project Access List · Change Password · Console · Getting Help · Context Sensitive Help · About Ghidra |
| [`FrontEndPlugin/Ghidra_Front_end_Menus.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FrontEndPlugin/Ghidra_Front_end_Menus.htm) | V09 | Configure Project Window · Refresh · Edit Menu Options · Project Window and Tool Options · Manage Certificates (some platforms only) · Set PKI Certificate · Clear PKI Certificate · Server Allow List · Exiting Ghidra |
| [`FrontEndPlugin/Opening_a_Ghidra_Project.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FrontEndPlugin/Opening_a_Ghidra_Project.htm) | V09 | (single section) |
| [`FrontEndPlugin/Project_Info.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FrontEndPlugin/Project_Info.htm) | V09 | Convert Project Storage to an Indexed Filesystem · Changing Shared Project Information · Converting a Non-Shared Project to a Shared Project |
| [`FrontEndPlugin/Re-opening_a_Project.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FrontEndPlugin/Re-opening_a_Project.htm) | V09 | (single section) |
| [`FrontEndPlugin/Restore_Project.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FrontEndPlugin/Restore_Project.htm) | V10 | Restoring a Version 2.x Project |
| [`FrontEndPlugin/Saving_a_Ghidra_Project.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FrontEndPlugin/Saving_a_Ghidra_Project.htm) | V09 | (single section) |
| [`FunctionComparison/FunctionComparison.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FunctionComparison/FunctionComparison.htm) | G12 | Listing View · Cursor Arrow · Listing Layout Actions · Navigating Differences · Difference Settings · Listing Code Comparison Options · Decompiler Diff View · Decompiler Code Comparison Options · Decompiler Code Comparison Actions · Function Graph Diff View · Function Graph Code Comparison Actions · Comparing Multiple Functions · Add To Existing Comparison · Remove Function From Comparison · Go To Next Function · Go To Previous Function · Navigate To Selected Function · Other Function Comparison Actions |
| [`FunctionPlugin/Functions.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FunctionPlugin/Functions.htm) | F01, F02, F03, F04, F05, F10, F12 | Function Signature, Attributes and Variables · Create Function · Re-Create Function · Thunk Functions · External Functions · Create Multiple Functions · Edit Function · Rename Function · Delete Function · Function Purge · Function Repeatable Comment · Stack Depth Change · Set Stack Depth Change · Remove Stack Depth Change |
| [`FunctionPlugin/Variables.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FunctionPlugin/Variables.htm) | D17, S12, T13, F06, F07, F08, F09, F11 | Function Signature · Function Attributes · Custom Storage · Inline · No Return · Varargs · Call-Fixup · Variables · Parameters (includes Function Return) · Local Variables · Define Variable Data Type or Function Return Type · Edit Function · Function Signature Field · Function Name · Namespace · Calling Convention · Parameters/Return Type Table · Call Fixup · Commit all return/parameter details · Edit Parameter Storage Dialog · Size Information · Storage Table · Create Function Definition · Rename Variable · Delete Variable · Edit Comment · Remove Comment · Recently Used Data Type |
| [`FunctionTagPlugin/function_tag_window.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FunctionTagPlugin/function_tag_window.htm) | F14 | Window Components · Tag Operations · Create · Delete · Edit · Add to Function · Remove from Function · Loading External Tags |
| [`FunctionWindowPlugin/function_window.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/FunctionWindowPlugin/function_window.htm) | F15 | Navigate on Incoming Location Changes · Make Selection · Compare Selected Functions |
| [`GhidraScriptMgrPlugin/GhidraScriptMgrPlugin.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/GhidraScriptMgrPlugin/GhidraScriptMgrPlugin.htm) | C01, C05 | Script Category Tree · Script Table · Filter · Description Panel · Script Manager Actions · Run Script · Run Last Script · Script Quick Launcher · Edit Script · Edit Script in an external IDE (A) · Edit Script in an external IDE (B) · Assign Key Binding · Delete Script · Rename Script · Create New Script · Refresh Script List · Script Directories / Bundle Manager · Help |
| [`GhidraScriptMgrPlugin/ScriptDevelopment.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/GhidraScriptMgrPlugin/ScriptDevelopment.htm) | C01 | Creating Scripts in the host JVM language · Tips · Meta-data · Supporting Other Languages · File createNewScript() · String getCommentCharacter() · String getDescription() · String getExtension() · GhidraScript getScriptInstance(File sourceFile, PrintWriter writer) |
| [`GhidraServer/GhidraServer.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/GhidraServer/GhidraServer.htm) | V04 | GhidraServer · Running the Server |
| [`Graph/GraphIntro.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Graph/GraphIntro.html) | G11 | (single section) |
| [`Graph/GraphServicesIntro.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Graph/GraphServicesIntro.html) | G11 | (single section) |
| [`HeadlessAnalyzer/HeadlessAnalyzer.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/HeadlessAnalyzer/HeadlessAnalyzer.htm) | Z06 | Headless Analyzer Options · Accessing the Headless Analyzer · Headless Analyzer Documentation |
| [`ImporterPlugin/importer.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ImporterPlugin/importer.htm) | V07 | Introduction · Supported Formats · File Import Actions · Import File · Batch Import · Open File System · Add to Program · Load Libraries · Other Import Actions · Import Selection · Importer Dialog · Dialog Fields · Options · Common Options · COFF Options · ELF Options · Hex-record format options (A) · Mach-O Options · Hex-record format options (B) · MZ Options · NE Options · PE Options · Raw Binary Options · XML Options · SARIF Options · Library Search Path · Change the Library Path Search Order · Add Library Search Path · Remove Library Search Path · Reset Library Search Paths · Language and Compiler Specification Dialog · Table Columns · Filter · Description · Show Only Recommended Language/Compiler Specs · Batch Import Dialog · Import Sources · Files to Import · Import Options |
| [`LabelMgrPlugin/FieldNames.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/LabelMgrPlugin/FieldNames.htm) | A10 | Edit Field Name Dialog · Dialog Fields |
| [`LabelMgrPlugin/Labels.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/LabelMgrPlugin/Labels.htm) | L05, S09, S10, S11, A11 | Label Name · Label Source · Default Labels · Label Properties · Add/Edit Label Dialog · Dialog Fields · Namespace Chooser Dialog · Set Label Dialog · Label · Label Operations · Adding a Label · Renaming a Label · Edit External Location Similar to editing a label associated with the… · Setting the Namespace · Setting an External Entry Point · Making a Label Primary · Selecting a referenced Label for an Operand · Show Label History |
| [`LanguageProviderPlugin/Languages.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/LanguageProviderPlugin/Languages.htm) | P08 | Setting a Program's Language · PCode |
| [`LibreTranslatePlugin/LibreTranslatePlugin.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/LibreTranslatePlugin/LibreTranslatePlugin.htm) | A03 | Configuration |
| [`LocationReferencesPlugin/Location_References.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/LocationReferencesPlugin/Location_References.html) | L29, S08 | To Find Location References · Results Window Header · Search Results · To Find Location References to Data Types · To Show Location References to Code Unit · Renaming Windows |
| [`MemoryMapPlugin/Memory_Map.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/MemoryMapPlugin/Memory_Map.htm) | P03, P04 | Rename Overlay Address Space · Memory Block Edits · Rename · Change Read Permission · Change Write Permission · Change Execute Permission · Change Volatile Setting · Change Artificial Setting · Initialize Memory Block · Edit Comment · Memory Block Operations · Add · Move · Split · Expand Up · Expand Down · Merge · Delete · Set Image Base · Auto Updating Selection by Location |
| [`Misc/AddressExpressions.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Misc/AddressExpressions.htm) | N02, I04 | Operands · Names · Numbers · Operators · Math Operators · Logical and Relational Operators · Bit Operators · Groups Operators · Result · Examples |
| [`Navigation/Navigation.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Navigation/Navigation.htm) | N01, N02, N03, N04, N05, N07 | Go To Address, Label, or Expression · To Perform a Go To: · Go To Address · Go To Label · Go To File Offset · Go To Expression · Repeating a Previous Go To · Error Messages · Next/Previous Code Unit · Search Direction · Invert Search Logic · Navigate to Instruction · Navigate to Data · Navigate to Undefined · Navigate to Label · Navigate to Function · Navigate to Matching Byte Values · Navigate to Bookmark · Next/Previous Function · Next Function · Previous Function · Navigation History · Go To Next/Previous Location · Go To Next/Previous Function in History · Clear History · Component Provider Navigation · Go To Last Active Component · Navigation Options · Starting Program Location Options · Initial Analysis Navigation Options |
| [`OverviewPlugin/Overview.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/OverviewPlugin/Overview.htm) | L17, L18 | General Overview Bar (Address Type) · Legend · Options · Entropy Overview Bar · Calculation of Entropy · Data Encoding · Color Palette Legend · Configuring the Entropy Window |
| [`PrintingPlugin/Printing.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/PrintingPlugin/Printing.htm) |  | The Page Setup Dialog · The Print Options Dialog · The Print Dialog · Printing |
| [`ProgramManagerPlugin/Closing_Program_Files.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ProgramManagerPlugin/Closing_Program_Files.htm) | V09 | To Close a Program File · To Close All Programs · To Close All Programs Other Than The Current Program |
| [`ProgramManagerPlugin/Navigating_Program_Files.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ProgramManagerPlugin/Navigating_Program_Files.htm) | N06 | Navigation Actions · Go To Next Program and Go To Previous Program Actions · Go To Program... Action · Go To Last Active Program Action |
| [`ProgramManagerPlugin/Opening_Program_Files.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ProgramManagerPlugin/Opening_Program_Files.htm) | V09 | Opening a Program File in the Current Tool · History · Opening a Program in a New Tool via Drag and Drop · Opening a Versioned Program File |
| [`ProgramManagerPlugin/Program_Annotation.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ProgramManagerPlugin/Program_Annotation.htm) | Z05 | (single section) |
| [`ProgramManagerPlugin/Program_Options_Dialog.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ProgramManagerPlugin/Program_Options_Dialog.htm) | P09 | Accessing Program Properties · Detailed Properties Descriptions · Property Editors · Date Editor · File Chooser Editor |
| [`ProgramManagerPlugin/Saving_Program_Files.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ProgramManagerPlugin/Saving_Program_Files.htm) | V03 | Save · Save As · Save All |
| [`ProgramTreePlugin/Program_Organizations.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ProgramTreePlugin/Program_Organizations.htm) | P02 | Subroutine Modularization · Dominance Tree Modularization · Complexity Depth Modularization · Default Tree Organizations |
| [`ProgramTreePlugin/program_tree.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ProgramTreePlugin/program_tree.htm) | P01 | Folders and Fragments · Create Folders and Fragments · Delete Folders and Fragments · Rename Folders and Fragments · Expand/Collapse Folders · Merge a Folder with its Parent Folder · Move Code Units to a Fragment · Tool Tips on a Fragment · Sort by Address or Name · Auto Rename on a Fragment · Select Addresses in a Folder or Fragment · Control the View in the Code Browser · Show Folders/ Fragments in the Code Browser · Remove Folders/Fragments from the view in the Code Browser · Set the View in the Code Browser with Folders/Fragments · Add to the View in the Code Browser · Navigation · Cut/Copy/Paste and Drag and Drop · Cut and Paste · Copy and Paste · Drag and Drop (Move) · Drag and Drop (Copy) · Reorder Folder Contents using Drag and Drop · Menu Enablement |
| [`ProgramTreePlugin/view_manager.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ProgramTreePlugin/view_manager.htm) | P02 | Create a Default Program Tree · Open Program Tree · Select Fragments Corresponding to a Program Location · Close a Program Tree · Rename a Program Tree · Delete a Program Tree · Change to Other Program Tree |
| [`PropertyManagerPlugin/Property_Viewer.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/PropertyManagerPlugin/Property_Viewer.htm) | P12 | (single section) |
| [`ReferencesPlugin/CreateOffsetReferencesTable.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ReferencesPlugin/CreateOffsetReferencesTable.htm) | E09 | (single section) |
| [`ReferencesPlugin/References.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ReferencesPlugin/References.htm) | E07 | Forward References · Back References |
| [`ReferencesPlugin/References_from.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ReferencesPlugin/References_from.htm) | E07, E08, E09, E10 | Introduction · Types of References · Memory References · External References · Stack References · Register References · Reference Destination Symbols · Ref-Types · Actions for Creating and Deleting References From a Code Unit · Add Reference From · Creating a Default Reference {Alt-R} · Deleting References from a Code Unit {Delete} · Viewing and Editing References (Add/Edit...) {'R'} · Source · References Table · Actions · Adding a Reference · Editing a Reference · Memory Reference Panel · Offset · To Address · Base Address · Include OTHER overlay spaces · Address History Button · Ref-Type · External Reference Panel · Name · Path (Clear/Edit) · Label / Address · Stack Reference Panel · Stack Offset · Variable Name · Register Reference Panel · Register · Adding Memory References from a Selection |
| [`ReferencesPlugin/external_program_names.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ReferencesPlugin/external_program_names.htm) | S03 | External Programs View · Name Column · Ghidra Program Column · Add Button · Delete External Name Button · Move Library Up Button · Move Library Down Button · Set External Path Association Button · Clear External Path Association Button · Working with External Program Names · Adding a New External Program Name · Resolving an External Name to an existing Ghidra program · Clearing a Resolved External Program Name · Removing an External Program Name |
| [`RegisterPlugin/Registers.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/RegisterPlugin/Registers.htm) | P07 | Register Manager · Toolbar Buttons · Menu Actions · Editing an Address Value Range · Setting Register Values Over Address Ranges · Clearing Register Values Over Address Ranges · Delete Exiting Register Value Ranges Associations |
| [`RelocationTablePlugin/relocation_table.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/RelocationTablePlugin/relocation_table.htm) | P05 | Displaying the Relocation Table · Relocation |
| [`Repository/Merge_Program_Files.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Repository/Merge_Program_Files.htm) | V05 | Auto Merge · Memory · Program Trees · Data Types and Categories · Program Context Registers · Listing · External Program Names · Property Lists · Resolving Conflicts |
| [`RuntimeInfoPlugin/InstalledProcessors.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/RuntimeInfoPlugin/InstalledProcessors.htm) | P08 | (single section) |
| [`ScalarSearchPlugin/The_Scalar_Table.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ScalarSearchPlugin/The_Scalar_Table.htm) | Q05 | To Search for Scalars: · Search Options · Search Type · Selection Scope · Scalar Table · Scalar Table Filters · Actions · Make Selection · Selection Navigation · Remove Items |
| [`Search/Instruction_Mnemonic_Search.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Search/Instruction_Mnemonic_Search.htm) | Q03 | (single section) |
| [`Search/Query_Results_Dialog.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Search/Query_Results_Dialog.htm) | Q09 | Navigation · Marker Margins · Renaming Windows · Actions · Make Selection · Remove Items · Selection Navigation |
| [`Search/SearchAndReplace.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Search/SearchAndReplace.htm) | Q10 | Search and Replace Dialog · Find · Replace · Options · Search For · Results Window · Table information · Applying Changes · Navigation · Search Examples · Basic Searches · Advanced RegEx Searches |
| [`Search/Search_Formats.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Search/Search_Formats.htm) | Q01 | Hex: · Binary: · String: · Reg Ex: · Decimal: · Float: · Double: |
| [`Search/Search_Instruction_Patterns.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Search/Search_Instruction_Patterns.htm) | Q04 | Dialog Layout · Instruction Table · Preview Table · Search Bounds · Manual Entry · Search Results · Usage |
| [`Search/Search_Memory.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Search/Search_Memory.htm) | Q01 | Contents · Memory Search Window · Search Controls · Scan Controls · Results Table · Options · Search Formats · Actions · Incremental Search Forward · Incremental Search Backwards · Refresh · Toggle Search Controls · Toggle Scan Controls · Toggle Options Panel · Make Selection · Toggle Single Click Navigation · Delete Selected Table Rows · Combining Searches · Search Forward/Backwards Using Global Actions · Search Memory Forwards: · Search Memory Backwards: · Highlight Search Options |
| [`Search/Search_Program_Text.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Search/Search_Program_Text.htm) | Q02 | Search Type · Incremental Search · Search All · Search Limit Option · Highlight Search Option · Default Search Order for Program Database Search |
| [`Search/Search_for_AddressTables.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Search/Search_for_AddressTables.htm) | E11, Q08 | Searching for Address Tables · Search Results Table · Making Address Tables · Actions · Make Selection · Selection Navigation |
| [`Search/Search_for_DirectReferences.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Search/Search_for_DirectReferences.htm) | Q07 | Restoring the Search Selection · Filtering Results Based on Alignment · Actions · Make Selection · Selection Navigation |
| [`Search/Search_for_Strings.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Search/Search_for_Strings.htm) | Q06 | String Search Dialog · Search Options · String Search Results · Table Columns · String Filters · Make String Options · Actions · Refresh · Make Selection · Selection Navigation · Search For Encoded Strings |
| [`Search/Searching.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Search/Searching.htm) | Q02 | (single section) |
| [`SelectBytesPlugin/Select_Bytes_Help.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/SelectBytesPlugin/Select_Bytes_Help.html) | L23 | By Method Options · Byte Selection · Error Messages |
| [`Selection/Selecting.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Selection/Selecting.htm) | L21 | Selection by Flow Tool Options · Navigating Over a Selection · Using the Navigation Margin · Next Selected Range · Previous Selected Range |
| [`SetHighlightPlugin/Highlighting.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/SetHighlightPlugin/Highlighting.htm) | L25 | To set a highlight from a selection · To clear a highlight · To add a selection to a highlight · To subtract a selection from a highlight · To create a selection from a highlight · Navigating over a highlight · Using the Navigation Margin · Using the Navigation Menu |
| [`ShowInstructionInfoPlugin/ShowInstructionInfo.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ShowInstructionInfoPlugin/ShowInstructionInfo.htm) | L27 | Raw Instruction Display · Processor Manual · Examples · Instruction Info Window |
| [`Snapshots/Snapshots.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Snapshots/Snapshots.html) | N09 | Creating a Snapshot View · Snapshot Views, Windows, and Actions |
| [`SourceFilesTablePlugin/SourceFilesTable.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/SourceFilesTablePlugin/SourceFilesTable.html) | Z09 | Source Files Table · Reload Model · Show Source Map Entries · View Source Files · Transform File · Transform Directory · Transforms Table · Remove Transform · Edit Transform · Listing Actions · View Source · Plugin Options · Use Existing As Default · Viewer for Source Files · Source Files · Source Map Entries · Source File Manager · Source Path Transformations |
| [`StackEditor/StackEditor.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/StackEditor/StackEditor.html) | F13 | Applying Changes · Closing the Editor · Changing the Local Size · Changing the Parameter Offset · Changing the Parameter Size · Edit Actions · Delete Stack Frame Byte(s) · Clear Stack Variable(s) · Change Stack Variable's Data Type To Array · Component Fields · Editing Component Fields · Applying an Edit · Canceling an Edit · Editing More Than One Component Field · Editing the Offset Field · Editing the DataType Field · Editing the Name Field · Editing the Comment Field · Pointers · Cycling a Component Data Type · Drag and Drop Basics · Favorites Basics · Creating a Stack Variable · Drag and Drop · Favorites · Replacing a Stack Variable's Data Type · Showing a Stack Variable's Data Type Category · Editing a Stack Variable's Data Type · Showing Numbers in Hexadecimal · Stack Editor Tool Options |
| [`SymbolTablePlugin/symbol_references.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/SymbolTablePlugin/symbol_references.htm) | S07 | Displaying the Symbol References component · References To · Instructions From · Data From · Delete Reference |
| [`SymbolTablePlugin/symbol_table.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/SymbolTablePlugin/symbol_table.htm) | S05, S06 | Displaying the Symbol Table component · Filter Text Field · Viewing Symbol References · Deleting Symbols · Deleting Symbol References · Making a Selection · Navigate on Incoming Location Changes · Navigate on Table Row Changes · Renaming a Symbol · Edit External Location · Pinning a Symbol · Filtering · Sample Queries |
| [`SymbolTablePlugin/symbol_table_transient.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/SymbolTablePlugin/symbol_table_transient.htm) | S06 | Drag and Drop · Actions · Create Table From Selection · Set Primary |
| [`SymbolTreePlugin/SymbolTree.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/SymbolTreePlugin/SymbolTree.htm) | S01, S02, S03, S04, S12 | Display · Create a Library · Set External Program · Create External Location · Edit External Location · Show References to · Convert Namespace to Class · Create a Class · Create a Namespace · Rename a Symbol · Move Symbols · Drag and Drop · Cut and Paste · Delete Symbols · Make a Selection · Navigation · Navigating on Program Location Changes · Navigating on Symbol Changes · Navigating to External Locations · View Qualified Names in Code Browser · Create Table From Selection · Symbol Tree Snapshots · Symbol Tree Clone Action · Disable Category · Enable Category |
| [`Tool/Configure_Tool.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Tool/Configure_Tool.htm) | I08 | Configure Plugins Dialog · Plugin Table · Information Window |
| [`Tool/Ghidra_Tool_Administration.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Tool/Ghidra_Tool_Administration.htm) | I08 | Default Tool · Tool Management · Create Tool · Save Tool to Tool Chest · Export Tool · Import Tool · Run Tool · Rename Tool · Set Tool Associations · Close Tool · Delete Tool · Tool Status Components |
| [`Tool/ShowLog.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Tool/ShowLog.htm) | Z05 | (single section) |
| [`Tool/ToolOptions_Dialog.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Tool/ToolOptions_Dialog.htm) | I05, I06 | Restoring Default Settings · Key Bindings · Change a Key Binding · Remove a Key Binding · Import Key Bindings · Key Binding Short-Cut · Export Key Bindings · Tool · Program Caching |
| [`Tool/Undo_Redo.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/Tool/Undo_Redo.htm) | V01, V02 | (single section) |
| [`TranslateStringsPlugin/TranslateStringsPlugin.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/TranslateStringsPlugin/TranslateStringsPlugin.htm) | A03 | Translate Menu · Manual string translation · Clear translated values · Toggle show translated values · String translation services · Creating a String translation service |
| [`ValidateProgram/ValidateProgram.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/ValidateProgram/ValidateProgram.html) | P11 | Post-Analysis Problem Detection · Program Validator |
| [`VersionControl/project_repository.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/help/help/topics/VersionControl/project_repository.htm) | V04 | Connect to the Server · Troubleshooting a Failed Connection · Version Control · Add to Version Control · Check Out · Check In · Undo Checkout · Update · Undo Hijack · Show Version History · View Version · Delete · View Checkouts · Find Checkouts |
| [`FunctionBitPatternsExplorerPlugin/FunctionBitPatternsExplorerPlugin.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/BytePatterns/src/main/help/help/topics/FunctionBitPatternsExplorerPlugin/FunctionBitPatternsExplorerPlugin.htm) | X08 | Data Sources · Current Program · Directory of XML Files · Data Gathering Parameters · Number of First Bytes · Number of Pre-Bytes · Number of Return Bytes · Number of First Instructions · Number of Pre-Instructions · Number of Return Instructions · Context Registers · Data Views · Byte Sequence Tabs · Instruction Sequence Tabs · Function Start Alignment Tab · Context Register Information Tab · Pattern Clipboard · Analyzing Byte Sequences · Send Selected to Clipboard · Merge Selected Rows · Send Merged to Clipboard · Mine Sequential Patterns · Mining Closed Sequential Patterns · Minimum Support Percentage · Minimum Number of Fixed Bits · Binary Sequences vs. Character Sequences |
| [`ByteViewerPlugin/ByteViewerOptions.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/ByteViewer/src/main/help/help/topics/ByteViewerPlugin/ByteViewerOptions.htm) | N11 | (single section) |
| [`ByteViewerPlugin/The_Byte_Viewer.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/ByteViewer/src/main/help/help/topics/ByteViewerPlugin/The_Byte_Viewer.htm) | N10, N12 | Boundaries · Data Formats · Hex · Chars · Address · Disassembled · Hex Short · Hex Integer · Hex Long · Hex Long Long · Integer · Octal · Binary · Status Fields · Editing Memory · Cursor Colors · Byte Viewer Options · Bytes Per Line · Alignment Offset · Hex Group Size · Charset · Compact Char Width · Use Char Alignment · View Selection · Reorder / Resize Views · Writing Your Own Format Plugin |
| [`DataGraphPlugin/Data_Graph.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/DataGraph/src/main/help/help/topics/DataGraphPlugin/Data_Graph.html) | G09 | Primary View · Vertices · Data Vertices · Code Vertices · Vertex Layout · Vertex Actions · Selecting Vertices · Navigating Vertices · Data Graph Actions · Toolbar Actions · Standard Graph Features and Actions |
| [`DecompilePlugin/DecompilerAnnotations.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Decompiler/src/main/help/help/topics/DecompilePlugin/DecompilerAnnotations.html) | D15, D18, D32, E02 | Machine Instructions · Entry Point · Formal Function Body · Flow Overrides · Comments · Display · Unreachable Blocks · Warning Comments · Variable Annotations · Creating Variable Annotations · Variable Symbols · Variable Data-types · Variable Storage · Function Prototypes · Signature Source · Discovering Parameters · Custom Storage · Data Mutability · Read-only · Volatile · Constant Annotations · Equates · Format Conversions · Register Values · Context Registers |
| [`DecompilePlugin/DecompilerConcepts.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Decompiler/src/main/help/help/topics/DecompilePlugin/DecompilerConcepts.html) | D32 | P-code · Address Space · Varnodes · P-code Operations · The HighFunction · HighSymbol · Varnodes in the Decompiler · HighVariable · Prototype Model · SLEIGH Specification Files · Modifying Specification Files |
| [`DecompilePlugin/DecompilerIntro.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Decompiler/src/main/help/help/topics/DecompilePlugin/DecompilerIntro.html) | D01 | Overview · Enabling the Plug-in · Decompiling a Function · Capabilities |
| [`DecompilePlugin/DecompilerOptions.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Decompiler/src/main/help/help/topics/DecompilePlugin/DecompilerOptions.html) | D30, D31 | General Options · Analysis Options · Display Options · Program Options · Specification Extensions · Extension Types · Status · Importing a New Extension · Removing an Extension |
| [`DecompilePlugin/DecompilerWindow.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Decompiler/src/main/help/help/topics/DecompilePlugin/DecompilerWindow.html) | D01, D02, D03, D04, D05, D06, D07, D08, D09, D10, D11, D12, D13, D14, D15, D16, D17, D18, D19, D20, D21, D22, D23, D24, D25, D26, D27, D28, D29 | Display · Main Window · Cross-Highlighting · Disabling Auto Refresh · Snapshot Windows · Undefined Functions · Tool Bar · Export to C · Snapshot · Re-decompile · Eliminate Unreachable Code · Respect Read-only Flags · Copy · Debug Function Decompilation · Graph Data Flow · Graph Control Flow · Mouse Actions · Left-Click · Right-Click · Double-Click · Ctrl-Double-Click · Ctrl-Shift-Click · Middle-Click · Pop-up Menu and Keyboard Actions · Adjust Pointer Offset · Auto Create Structure · Comments · Commit Local Names · Commit Params/Return · Convert · Edit Data Type · Edit Function Signature · Find... · Force Field · Go To Next/Previous Brace · Go To Next/Previous Highlight · Highlight · Secondary Highlight · Override Signature · Edit Signature Override · References · Remove Convert/Equate · Remove Signature Override · Remove Label · Rename Function · Rename Field · Rename Global · Rename Label · Rename Variable · Retype Field · Retype Global · Retype Return · Retype Variable · Set Equate... · Split Out As New Variable |
| [`DecompilerTaint/DecompilerTaint.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/DecompilerDependent/src/main/help/help/topics/DecompilerTaint/DecompilerTaint.html) |  | Initialization Actions (Tools → Source-Sink) · Delete Facts and Index · Export PCode Facts · Initialize Program Index · Re-export Function Facts · Tool Options (Options/Decompiler/Taint) · Directories.Engine · Directories.Facts · Directories.Output · Query.Current Query · Query.Index · Force Direction · Highlight Color · Highlight Style · Match on Fields · Output Format · Query Engine · Decompiler Pop-up Menu and Keyboard Actions · Source · Source (Symbol) · Sink · Sink (Symbol) · Gate · Clear · Slice Tree · Decompiler Toolbar Actions · Run taint query · Run default taint query · Run custom taint query · Load SARIF file · Show label table · Results Pop-up Menu · Add To Program · Apply taint · Clear taint · Make Selection |
| [`DecompilerTextFinderPlugin/Decompiler_Text_Finder.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/DecompilerDependent/src/main/help/help/topics/DecompilerTextFinderPlugin/Decompiler_Text_Finder.html) | Q12 | Search Results · Select Functions Action · Other Actions · Example Searches |
| [`FunctionGraphPlugin/Function_Graph.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/FunctionGraph/src/main/help/help/topics/FunctionGraphPlugin/Function_Graph.html) | G01, G02, G04 | Primary View · Vertices (Blocks) · Selecting Blocks · Navigating Blocks · Block Information · Vertex Actions · Popup Menu Vertex Actions · Grouped Vertex Actions · Edges · Selecting Edges · Navigating Edges · Edge Information · Articulated Edges · Vertex Grouping · The Ungrouping Process · Graph Actions · Path Highlight Actions · Function Graph Options · Creating Program Selections · From Paths · From Code Blocks · Clearing Selections · Popups · Grouping · Zooming · Vertex Quick Zoom · Interaction Threshold · Saving View Information · Standard Graph Features and Actions |
| [`FunctionGraphPlugin/Function_Graph_Layouts.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/FunctionGraph/src/main/help/help/topics/FunctionGraphPlugin/Function_Graph_Layouts.html) | G03 | Nested Code Layout · Nested Code Layout Options · Flow Chart Layout · Flow Chart Layout (Left) |
| [`FunctionID/FunctionID.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/FunctionID/src/main/help/help/topics/FunctionID/FunctionID.html) | I01 | Overview · Hashing · Parents and Children · Libraries · Single Matches · Multiple Matches · Analysis Options · Scoring and Disambiguation · Matching Function Names |
| [`FunctionID/FunctionIDDebug.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/FunctionID/src/main/help/help/topics/FunctionID/FunctionIDDebug.html) | I01 | Enabling the Plug-in · Plug-in Functionality · Create Read-only Database · Debug Search Window · Table Viewer |
| [`FunctionID/FunctionIDPlugin.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/FunctionID/src/main/help/help/topics/FunctionID/FunctionIDPlugin.html) | I01 | Enabling the Plug-in · Plug-in Functionality · Choose active FidDbs... · Create new empty FidDb... · Attach existing FidDb... · Detach attached FidDb... · Populate FidDb from programs... · Preparing Libraries for a Function ID Database · Location of Programs · Analysis · False Positives · Causes · Mitigation via Threshold · Specialized Mitigation |
| [`FunctionCallGraphPlugin/Function_Call_Graph.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/GraphFunctionCalls/src/main/help/help/topics/FunctionCallGraphPlugin/Function_Call_Graph.html) | G05 | Terms · Actions · Show/Hide Edges Action · Show/Hide Level Edges Action · Navigate on Incoming Location Changes · Layout Action · Snapshot Action · Graph 'Function Name' · Satellite View · Detached Satellite · Docked Satellite Location · Options |
| [`GraphServices/GraphDisplay.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/GraphServices/src/main/help/help/topics/GraphServices/GraphDisplay.htm) | G11 | Manipulating the Graph · Toolbar Buttons · Popup Actions · Standard Popup Actions · Vertex Popup Actions · Edge Popup Actions · Graph Type Display Options · Edge Colors · Miscellaneous · Vertex Colors · Vertex Shapes |
| [`GraphServices/GraphExport.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/GraphServices/src/main/help/help/topics/GraphServices/GraphExport.htm) | G10 | Export Dialog |
| [`Pdb/LoadPDB.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/PDB/src/main/help/help/topics/Pdb/LoadPDB.html) | Z07 | Symbol Servers and Symbol Storage · Menu Actions · Load PDB File · Symbol Server Config · PDB Search - Search Options · PDB Parser · Troubleshooting |
| [`Pdb/PDB.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/PDB/src/main/help/help/topics/Pdb/PDB.htm) | Z07 | To Load a PDB · Information Loaded From PDB · The platform debug-SDK capability · Platform debug SDK |
| [`Diff/Diff.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/ProgramDiff/src/main/help/help/topics/Diff/Diff.htm) | X02, X03, X04 | Opening and Closing the Diff View · Viewing Program Differences · Determine Program Differences Dialog · Do Differences On · Address Ranges To Diff · Diff and Multiple Program Tabs · Diff Apply Settings · Getting New Differences · Limiting the Diff to the Browser Selection · Navigating Differences · Next Difference · Previous Difference · Marker Margin · Selecting Differences · Automatically Selecting a Difference Block · Manually Selecting Differences · Select All · Setting the Program Diff Selection From the Tool's Program Selection · Applying Differences · To apply a selection · Example: · Applying Differences and Going To Next · To apply a selection and go to the next difference · Ignoring Differences · To ignore a selection · Viewing Difference Details at a Location · Why view the difference details at a particular program location? · Diff Apply Settings Tool Options · Problems/Limitations |
| [`ProgramGraphPlugin/ProgramGraph.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/ProgramGraph/src/main/help/help/topics/ProgramGraphPlugin/ProgramGraph.htm) | G08 | Graph Output · Graph types · Graph Scope · If there is a selection: · If there is no selection: · Synchronization · Selection · Location · Graph Representation · Reuse Graph · Append Graph · Show Location · Block Flow Graph · Rename Symbol · Graph Code Flow · Graph Calls · Graph Data References · Add References · Program Graphs Display Options |
| [`PyGhidra/interpreter.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/PyGhidra/src/main/help/help/topics/PyGhidra/interpreter.html) | C03 | Environment · Clear · Interrupt · Reset · Keybindings · Copy/Paste · API Documentation · Additional Help |
| [`Sarif/SARIF.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Sarif/src/main/help/help/topics/Sarif/SARIF.htm) | Z07 | (single section) |
| [`VersionTrackingPlugin/VT_AutoVT.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/VersionTracking/src/main/help/help/topics/VersionTrackingPlugin/VT_AutoVT.html) | X06 | Auto Version Tracking Options |
| [`VersionTrackingPlugin/VT_Correlators.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/VersionTracking/src/main/help/help/topics/VersionTrackingPlugin/VT_Correlators.html) | X05 | Data Match Correlators · Exact Data Match · Duplicate Data Match · Similar Data Match · Function Match Correlators · Exact Function Bytes Match · Exact Function Instructions Match · Duplicate Function Instructions Match · Exact Function Mnemonics Match · Legacy Import Correlator · Implied Correlator · Manual Match Correlator · Symbol Name Match Correlators · Exact Symbol Name Match · Duplicate Exact Symbol Name Match · Similar Symbol Name Match · Reference Correlators that Use Match Information to Find Other Matches · Data Reference Correlator · Function Reference Correlator · Combined Function and Data Reference Correlator |
| [`VersionTrackingPlugin/VT_Preconditions.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/VersionTracking/src/main/help/help/topics/VersionTrackingPlugin/VT_Preconditions.html) | X05 | Current Preconditions |
| [`VersionTrackingPlugin/VT_Tool.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/VersionTracking/src/main/help/help/topics/VersionTrackingPlugin/VT_Tool.html) | X07 | Version Tracking Session · Version Tracking Sub-tools · Version Tracking Tool Actions · Version Tracking Menu · Create Manual Match · Create And Accept Manual Match · Create And Apply Manual Match |
| [`VersionTrackingPlugin/VT_Wizard.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/VersionTracking/src/main/help/help/topics/VersionTrackingPlugin/VT_Wizard.html) | X05 | Creating a New Session · New Version Tracking Session Panel · Preconditions Panel · Summary Panel · Add to an Existing Session · Correlation Algorithm Panel · Options Panel · Address Set Options Panel · Select Address Range(s) Panel · Open an Existing Session · Sessions in Project Repositories |
| [`VersionTrackingPlugin/VT_Workflow.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/VersionTracking/src/main/help/help/topics/VersionTrackingPlugin/VT_Workflow.html) | X05 | Preconditions · Correlators · What Correlator Should I Use First? · Example Work Flow - Match All Possible Functions Between Two Binaries · Workflow FAQ · What are Implied Matches? · What do the Scores and Confidence Columns Mean? · How Do I Know Which Functions Have Not Been Matched Yet? · Why Do I See The Same Match More Than Once in the Match Table? · What Part of the Binary Should I Run The Correlators On? · Common Problems · Making Program Changes |
| [`VersionTrackingPlugin/Version_Tracking_Intro.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/VersionTracking/src/main/help/help/topics/VersionTrackingPlugin/Version_Tracking_Intro.html) | X05, X06 | Version Tracking Session · Version Tracking Associations · Version Tracking Matches · Version Tracking Markup Items · Version Tracking Correlators · How to Start |
| [`VersionTrackingPlugin/providers/VT_Apply_Options.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/VersionTracking/src/main/help/help/topics/VersionTrackingPlugin/providers/VT_Apply_Options.html) | X03 | Accept Match Options · Apply Markup Options |
| [`VersionTrackingPlugin/providers/VT_Functions_Table.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/VersionTracking/src/main/help/help/topics/VersionTrackingPlugin/providers/VT_Functions_Table.html) | X05 | Functions Table Columns · Functions Table Actions · Create Manual Match · Create And Accept Manual Match · Create And Apply Manual Match · Select Existing Match · Functions Table Filter · Show/Hide the Function Comparison Panel · Text Filter |
| [`VersionTrackingPlugin/providers/VT_Implied_Matches_Table.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/VersionTracking/src/main/help/help/topics/VersionTrackingPlugin/providers/VT_Implied_Matches_Table.html) | X05 | Version Tracking Implied Match · Implied Match Table Columns · Implied Match Table Actions · Text Filter |
| [`VersionTrackingPlugin/providers/VT_Markup_Table.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/VersionTracking/src/main/help/help/topics/VersionTrackingPlugin/providers/VT_Markup_Table.html) | X05 | Markup Items Table Columns · Markup Type · Markup Item Status · Markup Item Actions · Markup Items Filters · Comparison Views · Dual Listing Window · Dual Listing Actions · Background Colors in the Listings · Drag and Drop |
| [`VersionTrackingPlugin/providers/VT_Matches_Table.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/VersionTracking/src/main/help/help/topics/VersionTrackingPlugin/providers/VT_Matches_Table.html) | X05 | Version Tracking Match · Match Status · Match Table Columns · Match Table Actions · Match Filters · Table Filters · Advanced Filters · Table Column Filters |
| [`VersionTrackingPlugin/providers/VT_Related_Associations_Table.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/VersionTracking/src/main/help/help/topics/VersionTrackingPlugin/providers/VT_Related_Associations_Table.html) | X05 | Related Matches · Version Tracking Matches For Source · Version Tracking Matches For Destination · Actions · Compare Functions · Select Match in VT Matches Table |
| [`BSimCorrelator/BSim_Correlator.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/VersionTrackingBSim/src/main/help/help/topics/BSimCorrelator/BSim_Correlator.html) | I02 | (single section) |
| [`WildcardAssemblerModule/Wildcard_Assembler.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/WildcardAssembler/src/main/help/help/topics/WildcardAssemblerModule/Wildcard_Assembler.html) | Q11 | Wildcard Syntax |
| [`KeyboardNavigation/KeyboardNavigation.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Framework/Docking/src/main/help/help/topics/KeyboardNavigation/KeyboardNavigation.html) | C05, I07 | Component Traversal · Actions · Quick Action Dialog |
| [`Search/Regular_Expressions.htm`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Framework/Docking/src/main/help/help/topics/Search/Regular_Expressions.htm) | Q02 | Examples · Regular Expression Syntax |
| [`Tables/GhidraTableHeaders.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Framework/Docking/src/main/help/help/topics/Tables/GhidraTableHeaders.html) | I10 | Sorting Columns · Choosing Columns · Column Settings · Copy · Copy Current Column · Copy Columns... · Export to CSV Text File · Export to CSV Text File by Columns... · Select All |
| [`Trees/GhidraTreeFilter.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Framework/Docking/src/main/help/help/topics/Trees/GhidraTreeFilter.html) | I10 | Filter Actions · Activate Filter · Hide Filter · Clear Filter · The Filter Options Dialog · Filter Strategy · Case Sensitive · Allow Globbing · Invert Filter · Use Path · Enable Multi-Term Filtering · Delimiter · Evaluation Mode · Multi-Term Filter Examples · Ghidra Table Column Filters · Filters Panel · Actions · Constraint Types · Filter Results · Miscellaneous Actions · Copy Formatted |
| [`VisualGraph/Visual_Graph.html`](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Framework/Graph/src/main/help/help/topics/VisualGraph/Visual_Graph.html) | G03 | Primary View · Satellite View · Detached Satellite · Docked Satellite Location · Standar Graph Operations · Panning · Zooming · Interaction Threshold · Painting Threshold |

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

The definitions above are the targets of the bracketed keys in the matrix
rows, such as `[cb]`. The
[appendix](#appendix-actions-and-sections-named-in-each-cited-help-page) lists
every cited page as a visible link with its repo-relative path.

ghidra.re class guides and API:
[Beginner student guide](https://ghidra.re/ghidra_docs/GhidraClass/Beginner/Introduction_to_Ghidra_Student_Guide.html),
[Intermediate student guide](https://ghidra.re/ghidra_docs/GhidraClass/Intermediate/Intermediate_Ghidra_Student_Guide.html),
[Improving disassembly and decompilation](https://ghidra.re/ghidra_docs/GhidraClass/Advanced/improvingDisassemblyAndDecompilation.pdf),
[API reference](https://ghidra.re/ghidra_docs/api/index.html).

Repository documents:
[guide capability inventory](2026-09-20-ghidra-guide-capability-inventory.md) ·
[unified workstation spec](2026-09-20-unified-workstation-spec.md) ·
[consolidated design plan](2026-09-21-consolidated-design-plan.md) ·
[catalog contracts for parity](2026-09-29-catalog-contracts-for-parity.md) ·
[linked views and accessibility](2026-09-29-linked-views-and-accessibility.md) ·
[FRONTEND_INTENT](../FRONTEND_INTENT.md) ·
[PyGhidra API reference](../PyGhidra_API_Reference.md) ·
[TOOLS_LIST](../../TOOLS_LIST.md) ·
[design system](../design-system/project/README.md) and its
[components](../design-system/project/components/).
