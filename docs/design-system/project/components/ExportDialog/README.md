# ExportDialog

A dialog that runs one Ghidra exporter (C/C++, SARIF, XML, ASCII, HTML, GZF and any other format the catalog lists) with its options, over a function, a selection, a whole program, a graph or a type archive, on the builds you choose, as one export job per build whose output lands as an artifact with its basis in Outputs.

**Use it** from File › Export…, the link menu's **Export…** on a function or symbol (C export of the current function), GraphPane's **Export graph…**, TypeManager's **Export archive…** and the palette ("Export"). It replaces Ghidra's Export dialog, the decompiler's Export to C and the graph export dialog. There is no free output path: outputs are artifacts that OutputsCatalog lists and ArtifactCard shows, with a download link there.

**Consumer provides** the invoking source (function with its logical id, an address selection on one build, a whole program, a graph with its basis, or a type archive); the builds of the project, and for each the counterpart through accepted identity edges (or candidate or absent), its analysis state with receipt, whether the source's decompile is cached, and the writer lock as reported; the catalog's export action and the formats and option fields it lists (read from `GET /api/v1/actions`; no action id or format list is hardcoded); each format's scope support (function, selection, whole program); each build's decompiler program options (for the basis); any existing artifact with the same basis and options; and after posting, the jobs and their artifacts.

**Anatomy**

- **Title** is verb + object: "Export ResourceRef::Resolve", "Export build-a", "Export Calls graph of ResourceRef::Resolve". The header names the catalog action by label.
- **What.** A radio group: This function (its counterpart on each chosen build), Address selection (one build only, with its range), Whole program. A graph or archive invocation fixes What and shows its basis instead (graph: build, depth, the graph as drawn including collapsed groups, read time).
- **Format.** A radio group rendered from the catalog: each format with a one-line description. A format that the catalog does not list is shown disabled with "Not available on this server yet. The formats above still export. · What this server offers" (today: raw bytes, original file, Intel Hex and GDT) so the gap is visible, not hidden. Original file can carry PatchEditor byte patches (Ghidra's "Export user byte modifications"); when it arrives, that option says "patched bytes are not recovery evidence". A format that cannot export the chosen What is disabled with its reason ("GZF · whole program only").
- **Options** for the chosen format, from the catalog's fields. C/C++: Create C file, Create header file, Emit data type definitions, Emit referenced globals, Use C++ style comments, function tag filter (include or exclude), and "Decompile functions that have no cached decompile" (off by default; when on, the export job decompiles, and says so). ASCII and HTML: the listing fields to include (comments, properties, structures, undefined bytes, xref headers, function signatures). SARIF and XML: the sections to include. The decompiler program options that shape C output are shown as part of the basis, read-only; they change only through OptionsPanel's program section and the catalog.
- **Builds · one job each.** A checkbox row per build: counterpart address, analysis and decompile-cache state, writer state. Defaults: the inspected build and builds with an accepted counterpart. A candidate counterpart is unchecked with "identity edge is a candidate, not accepted"; an absent one is disabled with "No counterpart of ‹entity› on ‹build›", and an unresolved one with "◌ unresolved" and "‹entity› is unresolved on ‹build›; there is no function to export there". An existing artifact with the same basis and options says "exists: artifact from job ‹id›, 3 d, reused unless you export again" (reuse first).
- **Lands as artifacts.** Where outputs go (Outputs › Exports, one artifact per build and file), what each ArtifactCard records (build, program version, format, options, decompiler options, job) and the claim boundary with its tier: advisory, "Exported C ≠ recovered source", and "⊡ not observed on 8080": a delivered export is a bounded receipt, not something live.
- **Footer.** Cancel and the verb with a count: **Export** for one build posts on activation; **Export N builds…** opens ConfirmDialog, which names each job ("build-a at 0041b210 and build-c at 00082f40") and any existing artifact it would duplicate.

**States**

- **Posted:** the dialog closes; the invoking row or menu target shows the Job outcome words, and a batch shows "2 exports: 1 running · 1 finished" with each artifact linked. Nothing says the C compiles, matches or is recovered.
- **Format not in the catalog / no export action at all:** the format rows or the verb are disabled with the reason; a graph export today reads "Not available on this server yet. The graph still reads. · What this server offers", where the last part links to Help › What this server offers.
- **Not analyzed:** a build with no analysis is selectable, with "not analyzed · the export reads the program as it is"; exporting never starts analysis.
- **No cached decompile:** "decompile not cached · the export job decompiles it only if the option is on".
- **Writer owned:** export reads, so a writer does not block it, but the row says "program has a writer; the export reads the last saved state" when the backend reports that.
- **Basis changed while open:** the dialog refreshes the build rows, keeps your choices and says "Basis changed for build-c since this opened"; ConfirmDialog refuses a frozen target that changed.

**Multi-variant rules**

- Keyed by the source entity or program, with builds as explicit targets; one job per build, never one merged file for several builds.
- The function on each build is its counterpart through accepted identity edges only. Different decompiler options between builds are recorded in each artifact's basis and flagged when the artifacts are compared.

**Linking**

- **Publishes:** nothing. The dialog is not a place; its choices persist per viewer as the last-used format and options (durable workspace state). After posting, the job and artifact links appear on the invoking row and in the dock.
- **Follows:** nothing while open; it is bound to the source it was opened on. A history move closes it as Cancel. Not holdable.
- **Targets rendered:** the source function → the Code Browser at that build · jobs → the dock Jobs record · artifacts → OutputsCatalog focused on that artifact (`ws=evidence&panel=outputs&artifact=…`, the outputs agent's proposal) and its ArtifactCard.
- **Peek source:** Alt+↓ on an existing artifact reads its stored ArtifactCard; on a job, the stored record.
- **Absent copy:** "Not available on this server yet. ‹What still works›. · What this server offers" · "◌ unresolved" · "not observed on 8080" · "whole program only" · "No counterpart of ‹entity› on ‹build›" · "identity edge is a candidate, not accepted".
- **Target-size exception:** none; radios and checkboxes are 24px, rows at least 24px, 44px below 700px and with a coarse pointer.

**Keyboard**

- A modal dialog: Tab moves between the groups; arrows move within a radio group; Space toggles a build; Enter on the verb posts or opens the ConfirmDialog; Esc cancels and returns focus to the invoker.
- Keymap id `export.open` (registered) (no keys · menu and palette only; Ctrl/Cmd+E is browser-reserved).

**Accessibility**

- `role="dialog"` with `aria-modal`, named by its title and described by its first sentence. Each group is a `fieldset` with a `legend`. Disabled formats and builds carry `aria-describedby` to their reason.
- The confirm is ConfirmDialog (APG Alert dialog). The posted summary is announced once in the polite region.

**Parity rows covered**

Rows from the [Ghidra Code Browser parity specification](../../../../dashboard-design/2026-09-29-ghidra-code-browser-parity.md), section "New components needed".

- **D03** Export to C for the current function (What: This function, format C/C++).
- **G10** graph export: GraphML, DOT, GML, JSON, CSV (the graph form; catalog action needed).
- **V06** exporters: ASCII, C/C++, GZF, HTML, SARIF, XML through the catalog; GDT, hex records, original file and raw bytes shown as "Not available on this server yet" until actions exist.
- Also: the export half of **V10** (a GZF of one build) and type export from TypeManager (GDT, pending).

**Prior art**

Ghidra Exporter and Export dialog (`ExporterPlugin/exporter.htm`), Decompiler Export to C and graph export. Outputs presentation follows the reference research on typed reports with honest filters (decomp.dev, reccmp) and the OutputsCatalog and ArtifactCard components.

## Behavior

Moved from the preview's tips and chips (Guideline 25).

- ≠ analyze (chip removed): "Exporting reads the program as it is; it never analyzes or decompiles a function that has no cached decompile unless you choose so below."
- ⊘ not available (raw formats): "Not available on this server yet. The formats above still export." What this server offers is a Peek (Alt+↓), never a link inside the tip.
- ◇ decompiler options: "Decompiler options in the basis: each build's program options, read-only (OptionsPanel). Builds exported with different options are flagged in the artifact's basis."
- ↺ reused: "an export with this basis and these options exists: artifact from job 6e21, 3 d, reused unless you export again"
- ◇ basis: "Each ArtifactCard records the build, program version, format, options and decompiler options."
- ⊘ graph Export: "Not available on this server yet. The graph still reads." ⊘ GDT: "Not available on this server yet. C header export still works."
- ✓ C header: "C header export with Emit data type definitions covers CacheEntry today."
