# ProgramSettings

Each build's processor language and compiler spec, side by side, with the evidence for each value, plus the one flow that changes them. A change is a destructive per-build job: it confirms in a ConfirmDialog that lists its consequences, it re-analyses nothing by itself, and it is never offered for all builds.

**Use it** from a build's row menu in the navigator ("Program settings…", Ghidra's Set Language…), from the build crumb's Peek (the language line), from the Analysis menu and from the palette ("Language", "Compiler spec", "Program settings"). It replaces Ghidra's Set Language flow and the language part of the Installed Processors list. Opening it reads stored program settings only.

**Consumer provides:**

- The project and its builds.
- Per build, the program's language as Ghidra stores it:
  - the language id (processor, endianness, size and variant) and its version;
  - the compiler spec id;
  - how each value was set: loader choice at import, set by a job, or not recorded;
  - the witness or record behind it, such as the image header's machine field with its file offset, or the import record.
- Per build:
  - the image base, read only as MemoryMapTable reports it;
  - the version-control state: versioned, and checked out exclusively or not;
  - the writer lock as reported (owner kind, job, PID and start time);
  - its analysis receipt.
- The installed processors and, for a chosen build, the languages and compiler specs the server reports as compatible with its current language.
- For a proposed change, the server's dry-run counts:
  - registers whose stored values transfer by name;
  - registers whose values would be removed;
  - address spaces and whether each maps to one of the same size or larger;
  - functions whose calling convention name the new compiler spec does not define;
  - types whose size or alignment changes under the new data organisation;
  - receipts whose basis the change makes stale.
- The catalog action that changes the language (listed today as change-processor; read from `GET /api/v1/actions`, and no action id is named here).

**Anatomy**

1. **Header.** "Program settings · ‹project› · N builds", then the note (`role="note"`): "The compiler spec is Ghidra's model of calling conventions and data layout. It is not the toolchain that built the image; that is in Toolchain."
2. **Settings grid.**
   - Rows are settings and columns are builds, plus an Across builds column.
   - **Language id.** Every value carries its evidence level (`ad-evd`). A witness names the header machine field ("PE machine 0x14c (x86-32) · witness at file offset 0x84"). A record names the import record.
   - **Processor · endian · size · variant.**
   - **Compiler spec.** A record names the loader's choice at import. A conflict with ToolchainEvidence is stated, never resolved here ("windows expected: the Rich header records VC 8.0 (witness); gcc was the loader's choice").
   - **Pointer size.**
   - **Image base.** Read-only here, with "edit in Memory map". MemoryMapTable owns Set image base (P04) and its anchor consequences.
   - **Program properties.** A link to Peek's Properties (P12) and OptionsPanel's program options.
   - The Across builds cell compares stored values only: "same in all builds" (≡), "differs: build-d x86:LE:64" (±), or "unknown for ‹build›" (?).
3. **Change language or compiler spec… (catalog).** This opens the change flow for **one** build: the inspected build, or the build whose column holds focus.
   - **Choose.** A listbox of the compatible languages and compiler specs the server reports, headed with the compatible and installed counts ("3 of 12 shown · 186 installed"). **Show all installed** lists the rest `aria-disabled`, each with the reason it cannot be chosen ("address space ram is 32-bit; the new language's is smaller" or "not closely related"). A 32-bit to 64-bit move is allowed; the reverse is refused, as in Ghidra.
   - **Consequences (ConfirmDialog).** Title "Change ‹build›'s compiler spec from gcc to windows". The body is a numbered list, one consequence per line, each with the dry-run count:
     1. Ownership: the job needs build-c's writer and, if versioned, an exclusive checkout. It waits in admission for any other owner, and nothing is killed.
     2. Register and context values transfer by register name; values for registers the new language lacks are removed ("0 removed").
     3. Calling conventions are revalidated against the new spec ("1,204 functions keep their convention names; 0 become unknown"), and every stored signature's storage is rechecked (SignatureEditor).
     4. Types are revalidated by the layout check under the new data organisation ("CacheEntry stays 0x1c · 4 on build-c"; any change is listed).
     5. Re-disassembly and re-analysis are **not** run. They need their own admission in AnalyzerPanel, and build-c's analysis receipt becomes stale.
     6. Decompile caches, comparisons and FID hashes on build-c's old basis become stale. Identity edges stay, with their comparison evidence marked stale.
     7. It cannot be undone with Undo. To revert, undo the checkout (versioned) or change the language again. The dialog offers **Archive the project first** (ProjectWindow) and, for a versioned build, **Save a private copy**.
   - The footer says "Other builds are unchanged. There is no all-builds change and nothing is proposed to counterparts." The primary button names the build ("Change build-c · 1 job"). Focus starts on Cancel.
4. **After the job.** The build's column re-reads and shows a read-back line: "✓ read back · compiler spec windows · job ‹id›", or "✗ read back · differs from preview". Downstream stale state is listed with links to AnalyzerPanel and the stale receipts.

**States**

- **Writer owned:** "Waiting: build-b has a writer", with the owner as reported. The change waits in admission.
- **Not checked out:** for a versioned build without an exclusive checkout, the button is `aria-disabled` with "Check out build-c exclusively first", linking VersionControlPanel.
- **Incompatible choice:** a choice the server refuses is listed with its reason, and Change stays disabled.
- **Running, checking, finished, failed, cancelled:** the Job outcome words on the build's column and in the dock. "Checking whether the operation completed" disables another change on that build until reconciled. A failed or cancelled change names what the program now holds, as read back.
- **Not loaded:** "Not loaded. Open to read it." Reading settings is a read.
- **Conflicting evidence:** when the compiler spec disagrees with the toolchain evidence, the cell carries ⇄ and "conflicts with Toolchain" in words (the conflict glyph) and links ToolchainEvidence. Nothing is changed automatically.
- **No catalog action:** "Settings are read-only here · catalog action needed · not offered yet".

**Multi-variant rules**

- The panel is keyed by project and setting, with build as the column. The language and compiler spec are program-local: across builds they are compared, never merged or propagated. There is no "Propose to…" for this setting.
- One build per change, always named. Changing several builds means several separate flows, each with its own dry run and confirm.
- A build whose language differs (build-d, x86-64) is a fact of that build, not an error. It changes which analyzers, extensions and FidDb libraries apply to it, and other components name it when they exclude it.

**Linking**

- **Publishes:**
  - proposed `panel=program` with `build`, not registered in `location-schema.json` (see the proposals);
  - Enter on an evidence address, which goes to that address on that build.
  - The change flow's choice is dialog state, never in the URL.
- **Follows:** the inspected build, after the settle. A confirmed dialog keeps its build when the selection moves ("Bound to build-c · selection is now build-a · Rebind"). Not holdable.
- **Targets rendered:**
  - the header field witness → the Code Browser at that build and address (the mapped header, for example 00400084 on build-a for file offset 0x84);
  - the import record → the receipt card;
  - the compiler conflict → ToolchainEvidence (`ws=evidence&panel=toolchain`);
  - image base → a **Memory map…** button that opens MemoryMapTable for that build (MemoryMapTable publishes no location of its own);
  - properties → Peek (P12) and OptionsPanel;
  - the checkout → VersionControlPanel;
  - stale receipts → their cards;
  - a job → the dock records.
- **Peek source:** Alt+↓ on a value reads its stored evidence record, and on a job, the stored job record. Nothing is fetched or re-derived.
- **Absent copy:** "not recorded" · "unknown for ‹build›" · "Not loaded. Open to read it." · "catalog action needed · not offered yet" · "not closely related".
- **Target-size exception:** none; every control is 24px, and 44px below 700px and with a coarse pointer.

**Keyboard**

- The settings grid is an APG Grid, one tab stop, with arrows, Home/End and Ctrl+Home/End. Enter on a value's evidence link goes to it.
- The language choice is an APG Listbox with typeahead. Enter selects a language and moves focus to **Review consequences…**, which opens the ConfirmDialog; nothing posts from the list.
- Proposed keymap id `program.settings.open` has no keys; it is reached from the menu and palette only. No key changes a language.

**Accessibility**

- The grid is named "Program settings per build". A cell reads "Compiler spec, build-c: gcc, record, import record; conflicts with Toolchain". The evidence level is a word; the frame is the second cue.
- The ConfirmDialog is an APG Alert dialog. `aria-describedby` points at the first consequence sentence, and the numbered list is an `ol`.
- Read-back words are text. The job outcome is announced once by the dock.

**Parity rows covered**

Rows from the [Ghidra Code Browser parity specification](../../../../dashboard-design/2026-09-29-ghidra-code-browser-parity.md), section "Rows not yet designed".

- **P08** Processor language: covers viewing the language and compiler spec per build with evidence, Set Language with a filtered list of compatible languages, the installed processors, and Ghidra's warnings as listed consequences. The warnings are: needs an exclusive checkout, not open in a tool, register values transfer by name or are removed, address spaces must map to the same size or larger, and revert only through undo checkout or a backup.
- Checked and left to their owners: image base (P03 and P04, MemoryMapTable) and program properties (P12, Peek; program options in OptionsPanel). They are shown here read-only with links; nothing is duplicated.

**Prior art**

Ghidra Processor Languages and Set Language (`LanguageProviderPlugin/Languages.htm`) and Installed Processors (`RuntimeInfoPlugin/InstalledProcessors.htm`). Unlike Ghidra, the change never applies to the program you happen to have open: the build is named, the consequences are counted before the confirm, and re-analysis is a separate admission.
