# FunctionIdManager

Function ID across the project. It covers the FidDb databases the server knows about (choose active, attach, create, detach and populate) and the stored FID hashes of each function on each build, keyed by logical entity with builds as columns. It also covers FID names as a named witness tier. Every database change is a catalog job, populating is a long-running job, and a FID name is only ever a candidate.

**Use it** from Tools › Function ID…, the palette ("Function ID", "FidDb", "Populate FidDb", "FID hashes"), AnalyzerPanel's Function ID analyzer row ("Databases…") and NameProvenance's Function ID tier row. It replaces Ghidra's Function ID plug-in menu (Choose active, Create new empty, Attach existing, Detach, Populate) and the Debug Search Window. Opening it reads stored database metadata and stored hashes only. It never hashes, matches or analyzes.

**Consumer provides:**

- The databases the server knows, each with:
  - file name, whether it shipped with the server or was attached, writable or read-only (`.fidb` or `.fidbf`);
  - active or not;
  - its libraries: family, version, variant, language id, compiler specs, function count.
- Per logical entity and build:
  - the stored full hash (FH) and specific hash (XH);
  - the Function ID match: database, library, single or multiple match, score, and the name applied or left unapplied;
  - the job or receipt that computed them;
  - the build's language id, since hashes compare only within one language.
- Per build, its language and compiler spec (ProgramSettings), for populate filtering.
- The name tier of each candidate function (NameProvenance), so populate can skip placeholders.
- The catalog actions that manage databases and populate them (read from `GET /api/v1/actions`; no action id is named here).

**Anatomy**

1. **Header.**
   - "Function ID · ‹project›".
   - An APG tablist: **Databases** · **Hashes** · **Populate**.
   - The note (`role="note"`): "A Function ID name is a candidate from a hash match. Equal hashes are not a byte match and not an identity edge."
2. **Databases.** A table with columns Database, Origin, Access, Active, Language and Libraries.
   - Shipped databases are read-only and cannot be detached, as in Ghidra; they can only be made inactive.
   - Row actions (catalog):
     - **Choose active…** confirms in place for one database. It names the consequence: "affects every later Function ID run on every build; runs already recorded keep their receipts".
     - **Attach existing…** and **Create new empty…** name the file. A database is never placed under the server's install tree.
     - **Detach…** uses ConfirmDialog and names the databases it forgets. The file itself is not deleted.
     - **Populate…** opens the Populate tab.
     - **Search records** is a read-only lookup by name, FH, XH or domain path, as in the Debug Search Window.
3. **Hashes.** Rows are logical entities and columns are builds, plus an Across builds column.
   - Each cell shows FH and XH in mono, with the match beneath: "memset · crt 7.1 release · single match". The other forms are "2 matches · left unnamed" (Ghidra leaves ambiguous matches unnamed), "no match" and "not hashed".
   - An entity absent from a build reads "◌ unresolved · no function to hash" (LocatorGlyph words).
   - Across builds compares hashes only between builds with the same language id:
     - "same full hash on build-a and build-b" (≡ for those builds);
     - "differs: no two builds share a full hash" (±);
     - "not comparable · build-d is x86:LE:64".
   - Where hashes differ, the variance class is a dashed hypothesis with its basis, such as "≈ compile variance · hypothesis (heuristic): VC 7.1 → 8.0 (Rich header witness); no source identity recorded".
   - Enter on a match opens NameProvenance at the Function ID tier. Enter on a hash searches records with it (read-only).
4. **FID names as a named witness tier.** A section beside the Hashes grid shows, for the focused entity and build, the NameProvenance rows:
   - **Tier.** "analysis · Function ID" sits inside analysis names, below human annotations, debug info and authentic symbols, and above placeholders. Only a placeholder is replaced by it.
   - **Witness.** The FidDb record: database, library, version and variant, the FH and XH that matched, and the job that ran the match.
   - **Claim.** "candidate · never a recovery or identity claim".
   - A FID name crosses to another build only through PropagationTransfer's "Propose to…", gated by an accepted identity edge.
5. **Populate** (a job, ConfirmDialog):
   - **Fields.** Database, which must be writable and attached. Library family, version and variant. Base library (optional). Language id (required). Compiler specs and source languages (optional). Common symbol file (optional).
   - **Programs.** The project's builds, each checkable or excluded with its reason. Examples: "build-c · excluded: compiler spec gcc does not match windows (as imported; see Program settings)" and "build-d · excluded: language x86:LE:64 ≠ x86:LE:32". Nothing is skipped silently.
   - **Names.** "Only names at the authentic-symbols tier or stronger are ingested; 1,122 placeholders on build-a are skipped." Ghidra needs accurate symbols for parent and child links.
   - **Consequence.** "Writes corpus-alpha-libs.fidb only. build-a is read and not changed. One writer per database." The primary button counts the job ("Populate · 1 job"). The finished job's summary (functions ingested, most-called list) lands in the job record.

**States**

- **Not hashed:** "not hashed · hashes are computed only by an admitted job (the Function ID analyzer in Analysis, or a hash-only run)". Nothing hashes on open.
- **Stale:** hashes whose basis predates a program change on that build read "◷ stale · 3 transactions since". A language change (ProgramSettings) makes them all stale.
- **Database writer owned:** Populate waits in admission for the job that holds the database. Nothing is killed.
- **Read-only database:** Populate lists only writable databases. A `.fidbf` says "read-only form · cannot be populated".
- **Running, checking, finished, failed, cancelled:** the Job outcome words. A cancelled populate names what was ingested before it stopped.
- **Not loaded:** "Not loaded. Open to read it."
- **No catalog action:** "Function ID databases are read-only here · catalog action needed · not offered yet". Stored hashes and database metadata still read.

**Multi-variant rules**

- Hashes are keyed by logical entity with builds as columns. An address never crosses builds; each cell carries its own build's address.
- Hashes compare only within one language id. Equal full hashes are an observation about bytes with constants masked. They are not a byte match, not an identity edge and not recovery evidence.
- Databases are tool-level: choosing active databases affects every later run on every build, and the confirm says so. A FidDb is never program data and is never propagated.
- Populating reads builds and writes only the database. Excluded builds are named with their reasons.

**Linking**

- **Publishes:**
  - proposed `panel=fid` with `build`, not registered in `location-schema.json` (see the proposals);
  - Enter on an entity, which goes to Compare with the CounterpartStrip;
  - Enter on a match, which opens NameProvenance (`ws=evidence&panel=names`).
  - Tabs and the Populate draft are durable workspace state.
- **Follows:** the primary selection's entity and the inspected build, after the settle. Not holdable.
- **Targets rendered:**
  - an entity → Compare;
  - a build cell's address → the Code Browser at that build;
  - a match → NameProvenance;
  - a toolchain basis → ToolchainEvidence;
  - a language exclusion → ProgramSettings;
  - a job → the dock records;
  - the analyzer → AnalyzerPanel.
- **Peek source:** Alt+↓ on a hash reads the stored FidDb records that share it. On a match, it reads the stored match record. Nothing is hashed or searched beyond stored records.
- **Absent copy:** "not hashed" · "no match" · "left unnamed" · "unresolved on build-d" · "not comparable · ‹language›" · "Not loaded. Open to read it." · "catalog action needed · not offered yet".
- **Target-size exception:** none; rows are 28px and every control is 24px, or 44px below 700px and with a coarse pointer.

**Keyboard**

- The tablist uses APG Tabs with manual activation. The databases table and the hashes grid are APG Grids, one tab stop each. Space in the Active column toggles a draft, never a post; **Apply…** confirms.
- Proposed keymap id `fid.open` has no keys; it is reached from the menu and palette only. No key populates, attaches or detaches.

**Accessibility**

- The hashes grid is named "Function ID hashes per build". A cell reads "FUN_0041c880, build-a: full hash 7c19e05ad3b2f604, specific hash 31a8…; match memset, crt 7.1 release, single match". Hashes carry `translate="no"`.
- The tier and claim are words. Dashed variance chips say "hypothesis" in text.
- A finished populate is announced once by the dock.

**Parity rows covered**

Rows from the [Ghidra Code Browser parity specification](../../../../dashboard-design/2026-09-29-ghidra-code-browser-parity.md), section "Rows not yet designed".

- **I01** Function ID covers:
  - Choose active FidDbs, Create new empty FidDb, Attach existing FidDb, Detach attached FidDb and Populate FidDb from programs, with every dialog field;
  - the Debug Search Window as a read-only record search;
  - FH and XH per function per build, and single and multiple matches;
  - FID names as a named witness tier inside analysis names.
  - Supporting, owned elsewhere: enabling the Function ID analyzer and its options (AnalyzerPanel, Z02) and the tier table itself (NameProvenance).
  - Not offered: Create Read-only Database (`.fidbf`) and editing specialized mitigation records. They are database-authoring tools, noted for a later catalog action.

**Prior art**

Ghidra Function ID (`FunctionID/FunctionID.html`), the Function ID plug-in (`FunctionIDPlugin.html`) and the Function ID Debug plug-in (`FunctionIDDebug.html`). Unlike Ghidra, the active set is a confirmed catalog change, hashes are compared per build within one language, and a match never names a function above a stronger tier.
