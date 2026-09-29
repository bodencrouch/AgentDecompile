# DebugInfoImport

The debug information of every build in one panel. It shows what each image records about its own debug data, what has been found for it, and what has been applied. From here the operator loads a PDB (symbol-server search locations and parser options), an external DWARF file or a SARIF file into one build, each as an admitted job. It also shows the source files table and source map entries per build. Imported names and types enter at their witness tier with provenance per field, and never overwrite a stronger tier.

**Use it** from File › Load debug info… (Ghidra's Load PDB File), the Analysis menu, a build's row menu, the palette ("Load PDB", "Debug info", "Source files", "Import SARIF") and ImportAdmission's "debug info found" line. It replaces Ghidra's Load PDB dialog, Symbol Server Config, DWARF External Debug Config, the SARIF Read File action and the Source Files table. Opening it reads stored records only. It never searches a symbol server, downloads, parses or applies anything.

**Consumer provides:**

- Per build, what the image records about its debug data:
  - the debug directory's CodeView entry: PDB name, GUID or signature, and age, as a witness with its location;
  - for ELF images, `.gnu_debuglink` or the build-id note.
- Per build, what has been found for it:
  - the file, the search location it came from, and whether GUID and age match (a record);
  - whether it was read for other facts, such as ToolchainEvidence's PDB records.
- Per build, what has been applied: the debug-info receipt (job, basis, source file, parser and options, provenance) and the counts it recorded (names, types, source files, source map entries, conflicts).
- The server's configured search locations, in order: kind, path or URL, enabled, status, and whether use needs network approval.
- The parsers the server reports, with availability.
- For a load, the dry-run counts:
  - names and types to add;
  - fields where a stronger tier already holds a different value;
  - type layouts checked per build.
- For SARIF: the run's artifact hash, rule ids and result counts, and which build (if any) the hash names.
- Per build, the source files (path, ID type, identifier, map entry count) and, for a chosen file, its source map entries (line, base address, length).
- The viewer's source path transforms, which are durable workspace state per viewer.
- The catalog action that imports debug info (read from `GET /api/v1/actions`; no action id is named here).

**Anatomy**

1. **Header.**
   - "Debug info · ‹project› · N builds".
   - An APG tablist: **Builds** · **Search locations** · **Source files**.
   - The note (`role="note"`): "Imported names and types enter at their own tier and never overwrite a stronger one. Loading is one admitted job per build."
2. **Builds** (one row per build; debug info is program-level):
   - **In the image.** "CodeView · build-d.pdb · GUID 3f2a9c41… · age 1" as a solid witness. On a build without one: "no CodeView entry in the debug directory (witness)". This is a solid absence that names what was checked.
   - **Found.** "local symbol storage · GUID and age match" as a record. Otherwise "not searched", or "searched 14:02 · not found in 3 locations".
   - **Applied.** Either "applied · job ‹id› · 1,930 types · 5,812 names · reused" with its ProvenanceStamp, or "not applied · no debug-info receipt". A PDB that was read only for toolchain facts says "read for Toolchain facts · not applied to the program".
   - **DWARF.** For a PE build: "⊘ not applicable · no .gnu_debuglink or build-id note (witness)".
   - Row actions: **Load PDB on ‹build› (catalog)…**, **Load DWARF file… (catalog)** and **Import SARIF… (catalog)**. Each opens its dialog for that one build. There is no all-builds load.
3. **Load PDB (ConfirmDialog; it writes many fields on one build):**
   - **PDB file.** The found file, with its match stated. **Choose file…** picks another.
   - **Search options.** Ignore age and Ignore GUID are off by default. Turning either on says: "A non-exact PDB is a hypothesis: its names enter with analysis names, not debug info, and every value is marked 'GUID or age not matched'."
   - **Parser.** Universal, or MSDIA shown `aria-disabled` "unavailable on this server" when the server says so.
   - **Control.** Process all · Data types only · Public symbols only.
   - **Dry run.** Names to add, with their tier: "debug info · record: GUID and age match". Types to add, each type checked by build-d's own layout check ("CacheEntry: 0x20 · 8 in the PDB, the same as build-d's layout"). Source files and source map entries to add. Fields where a stronger tier already holds a different value: "2 · kept; the PDB value is recorded as a rejected alternative" (NameProvenance).
   - **Network.** When the file is only on a remote symbol server: "⚑ approval-required · downloading from ‹URL› is network use". The primary button stays disabled until approval is recorded.
   - The footer says "Other builds are unchanged. A PDB belongs to one image." The primary button names the build ("Load into build-d · 1 job"). Focus starts on Cancel.
4. **Load DWARF file.** The same dialog shape for ELF builds: an external debug file matched by build-id or debuglink CRC (a record) or chosen by hand (a hypothesis until it matches).
5. **Import SARIF.** Choose a SARIF file from Outputs or from disk. The preview shows:
   - the run's artifact hash against each build's SHA-256: "matches build-a (record)", or "names no build in this project · not offered";
   - results grouped by rule id.
   What to apply (names, comments, bookmarks, types) is chosen per category. SARIF names enter with analysis names as "imported · SARIF", and comments and bookmarks enter as context pieces (ContextPlacement, context-hint tier). A SARIF file never outranks debug info or a human annotation.
6. **Search locations.**
   - An ordered list: Local symbol storage (required; its layout, level 1 or level 2, is read from the directory), then the additional locations, which are Program's import location, directories, symbol-server URLs and, for DWARF, build-id, debuglink and debuginfod locations.
   - Each location shows enabled, status (**Refresh status** is a read), and "⚑ needs approval before use" for a URL.
   - Add, Remove and Move up or down edit the next job's fields as a per-viewer draft. **Save as server default (catalog)** is `aria-disabled` "catalog action needed · not offered yet".
7. **Source files (Z09).**
   - A build segment chooses the build.
   - The table lists each source file's path, ID type (NONE, UNKNOWN, TIMESTAMP_64, MD5, SHA1, SHA256 or SHA512), identifier, number of map entries and **Transformed path**.
   - **Show map entries** lists the chosen file's entries: line → base address (a typed link on that build) → length → the logical entity at that address when a locator is recorded, or "no entity at this address". A source line is never an identity edge.
   - **Transforms** (file or directory, per viewer) rewrite paths for **Open source (read-only)**. They are not program data, not checked in and not in EditHistory.
   - Source files and map entries are added only by an import job. As in Ghidra, there is no manual add.

**States**

- **No debug record:** "build-a records no PDB (no CodeView entry in the debug directory)". Load PDB stays available with Choose file…, and a chosen file is a hypothesis until its GUID and age match.
- **Not searched:** "Not searched. Search runs only as part of a load job, or with **Search locations** (a read over configured locations; remote locations need approval)."
- **Found, not applied:** "matched · not applied to the program". The load is armed, not run.
- **Applied, reused:** "applied · job 5c1e · reused". A second load of the same file and options is refused with "already applied with this basis" and a link to its receipt. Reloading needs the catalog's force field and a ConfirmDialog.
- **Writer owned:** the load waits in admission with the owner as reported. Nothing is killed or restarted.
- **Running, checking, finished, failed, cancelled:** the Job outcome words appear on the build row and in the dock. A cancelled load names what it applied before it stopped. It never claims a rollback, and EditHistory holds the transaction.
- **Conflicts after a load:** "2 stronger values kept" links NameProvenance, filtered to those fields.
- **No source files:** "∅ No source files on build-a. Source files come from an applied PDB or DWARF import."
- **No catalog action:** "Debug info is read-only here · catalog action needed · not offered yet". The Builds and Source files tabs still read.

**Multi-variant rules**

- The panel is keyed by build, because debug info belongs to one image. A PDB matched to build-d is never offered for build-a. The GUID and age are the gate, and a forced mismatch is a hypothesis.
- Imported values are per-build edits. Offering a debug-info name to counterparts is PropagationTransfer's separate "Propose to…" step, gated by identity edge. For example, Actor::LoadFromTemplate's PDB name on build-d reaches build-a only as a proposal through the accepted edge.
- Types from a PDB are layout-gated per build: build-d's CacheEntry (0x20 · 8) is never applied to build-c (0x1c · 4).
- Source map entries and addresses stay on their build. A source line shared by two builds does not map their addresses to each other.

**Linking**

- **Publishes:**
  - proposed `panel=debuginfo` with `build`, not registered in `location-schema.json` (see the proposals);
  - a map entry's address, which goes to that build (one history stop);
  - a source line, which uses the registered `f=src.line:‹file›:‹line›` axis where a view filters by it.
  - Tabs, drafts and transforms are durable workspace state.
- **Follows:** the inspected build, after the settle. A confirmed load keeps its build ("Bound to build-d"). Not holdable.
- **Targets rendered:**
  - an image witness → the Code Browser at that build and address;
  - a receipt → the receipt card;
  - a name conflict → NameProvenance for that entity and build;
  - a type → TypeManager on that build;
  - context pieces → ContextPlacement;
  - a map entry → the Code Browser at that build;
  - a job → the dock records;
  - a SARIF artifact → its ArtifactCard.
- **Peek source:** Alt+↓ on a receipt, job or map entry reads the stored record or cached Listing lines. Nothing is fetched, downloaded or parsed.
- **Absent copy:** "no CodeView entry" · "not searched" · "not applied" · "not applicable" · "no entity at this address" · "Not loaded. Open to read it." · "catalog action needed · not offered yet".
- **Target-size exception:** addresses in the map-entry table are 24px links. Everything is 44px below 700px and with a coarse pointer.

**Keyboard**

- The tablist uses APG Tabs with manual activation. The builds table, source files table and map entries table are APG Grids. The search locations list is an APG Listbox; Alt+↑ and Alt+↓ move the focused location.
- Proposed keymap id `debuginfo.open` has no keys; it is reached from the menu and palette only. No key loads or imports.

**Accessibility**

- The note is `role="note"`. The Load dialogs are APG Alert dialogs whose `aria-describedby` points at the consequence sentence.
- The tier and evidence level are words ("debug info · record"). The frame is the second cue.
- When the server reports approval-required, it is text with ⚑ `aria-hidden`. A finished load is announced once by the dock.

**Parity rows covered**

Rows from the [Ghidra Code Browser parity specification](../../../../dashboard-design/2026-09-29-ghidra-code-browser-parity.md), section "Rows not yet designed".

- **Z07** covers:
  - Load PDB File: the found file, Choose file, and the program's PDB information;
  - Symbol Server Config: local storage, additional locations, add, delete, move, refresh, save and `_NT_SYMBOL_PATH`-style entries, where save is a catalog action;
  - PDB search options: Ignore age, Ignore GUID and the overrides;
  - the parser (Universal or MSDIA) and Control;
  - DWARF External Debug Files: the location types and the config;
  - the SARIF import and Add To Program.
  Each is an admitted job on one build.
- **Z09** covers the Source Files table (path, ID type, identifier, entry count), Show Source Map Entries, file and directory transforms, and View Source as Open source (read-only).

**Prior art**

Ghidra Load PDB and Symbol Server Config (`Pdb/LoadPDB.html`, `Pdb/PDB.htm`), DWARF External Debug Files (`DWARFExternalDebugFilesPlugin`), SARIF (`Sarif/SARIF.htm`) and Source Files (`SourceFilesTablePlugin/SourceFilesTable.html`). Unlike Ghidra, a load never applies to whichever program is open: the build is named, the dry run counts conflicts first, and stronger names always win.
