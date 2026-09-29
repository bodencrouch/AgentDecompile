# ProjectWindow

The project and its program files in one panel. It covers:

- the program files tree with each member's kind, language, saved state, version and writer;
- explicit **Save**, **Save As** and **Save All** per program, separate from check-in;
- the known projects: create one, view another read-only, open one through the cross-project notice, or delete one;
- archive and restore of a whole project as jobs with receipts.

**Use it** from the Project menu, the palette ("Project", "Program files", "Save", "Save all", "New project", "Archive project", "Restore project"), Ctrl/Cmd+O (`open`) and the navigator's project header. It replaces Ghidra's Project Window (data tree and table, New, Open, Reopen, Close and Delete Project, Save Project, Archive and Restore), and File › Save, Save As and Save All. Opening it reads the stored project inventory. It never opens a program, switches project, imports or analyzes.

**Consumer provides:**

- The active project: name, kind (`kind-gpr`, `kind-shared-fs`, `kind-shared-http`) and location.
- Its members, as folders and files:
  - builds (programs), program copies (with the SHA-256 identity they alias), type archives and other files;
  - per member: language id, version-control state, and read-only flag;
  - transactions not saved and transactions not checked in;
  - the last save time and who saved (you, agent, external, or the server's own save when it reports one);
  - the writer lock as reported (owner kind, job, PID and start time).
- The known projects the server lists: name, kind, location, last opened, member count, and the owners and running jobs as reported.
- For a viewed project, its stored inventory only.
- Archive receipts: file, digest, time, the per-build saved state it captured, and the unsaved transactions it left out.
- The catalog actions for:
  - save, save as and save all (W32);
  - project create and delete;
  - program rename, move, delete and read-only;
  - archive and restore (J07).
  They are read from `GET /api/v1/actions`, and no action id is named here.

**Anatomy**

1. **Header.**
   - "Project · ‹project›", with the project-kind chip and "N builds · M files".
   - An APG tablist: **Program files** · **Projects** · **Archive**.
2. **Program files.**
   - An APG Treegrid of folders and members with these columns:
     - **Kind:** build, program copy, type archive or file;
     - **Language**;
     - **Saved:** "saved 14:06", "✎ 2 transactions not saved · saved 14:06", or "not reported by owner";
     - **Version:** "v7 · 5 not checked in" or "not versioned", linking VersionControlPanel;
     - **Writer:** "this session", "job 77c0 · external", or "○ free".
   - A program copy is labelled "program copy · alias of build-a (same SHA-256) · not a build". The copy has no receipts of its own, and binding it to a build's evidence is a separate program-binding step.
   - Row actions:
     - **Open**, which goes (for a build it moves the inspected build and pushes one history stop);
     - **Close**;
     - **Rename…** and **Move…**, which confirm in place;
     - **Delete…**, a ConfirmDialog that names the receipts, identity edges and held or kept cards that reference the member;
     - **Read-only**, a toggle posted through the catalog. As in Ghidra, the read-only state cannot change while the file is in use.
3. **Save row** for the inspected build:
   - "build-a · 2 transactions not saved · last saved 14:06 · 5 not checked in".
   - **Save build-a** (a catalog action, as are the verbs below) confirms in place: Enter on the armed button posts. Ctrl/Cmd+S outside an editor arms it and never posts on its own.
   - **Save As…** opens a small dialog (folder and name). Its consequence sentence says "build-a's own file stays at its last save (14:06); this session then writes to the copy until you reopen build-a."
   - **Save All…** is a ConfirmDialog listing each build where this session is the writer, with its count. It also lists the builds it leaves out with the reason, for example "build-b · writer job 77c0 · external · only its owner can save".
   - One sentence separates Save from check-in: "Save writes transactions to the project file and never clears the undo stack. Check-in sends a version to the server and clears it (Version control)."
4. **Projects.**
   - A table of known projects: name, kind, location, builds, last opened, and owners as reported.
   - **New project…** asks for the name, kind and location (a Ghidra Server repository takes a host and port; it is RMI over SSL). The result says "Created corpus-gamma. Opening it is a separate step." Creating never switches project.
   - **View read-only** reads the other project's stored inventory into a read-only tree headed "corpus-beta · viewed read-only · nothing admitted". It opens no program and admits no work.
   - **Copy into ‹active project›…** on a viewed member is an import through ImportAdmission.
   - **Open ‹project›…** always lands on the cross-project StateNotice, which names both projects and says that opening admits eligible missing work. **Switch to corpus-beta** is armed and confirm-gated, and **Stay** is the alternative. "Open ‹project›" is the StateNotice's action only when no project is active.
   - **Delete ‹project›…** is offered only for a project that is not active. It is a ConfirmDialog: "Delete corpus-beta permanently. Its 2 programs, receipts and history are removed and cannot be recovered." It offers **Archive it first**. Delete is refused while any owner or running job is reported ("job 6e21 · external holds corpus-beta"). Nothing is killed.
5. **Archive.**
   - **Archive ‹project›…** is a non-mutating job. It shows the archive file name (`.gar`) and the consequence: "Captures each build's last saved state. 2 unsaved transactions on build-a are not included; save first to include them."
   - The finished archive is an artifact in OutputsCatalog with its receipt (digest, time and per-build versions). "Delivered" means only that a bounded receipt exists.
   - **Restore…** is a mutating job into a **new** project: archive file, directory and name. A name that exists is refused ("corpus-alpha exists · choose another name"). Restore never replaces a project.
   - The restored project's receipts are labelled "historical · restored from archive ‹digest›", never fresh. Opening it goes through the cross-project StateNotice.

**States**

- **Nothing to save:** Save is `aria-disabled` with "Nothing to save on build-c".
- **Writer owned:** Save and Save All exclude that build with the owner as reported. Delete and Restore wait or refuse. Nothing is killed or restarted, and an external owner is never offered either.
- **Running, checking, finished, failed, cancelled:** the Job outcome words on the invoking row and in the dock. A save that is "checking whether the operation completed" disables another save of that build until reconciled. A cancelled restore removes the files it created, as Ghidra does, and names them.
- **Viewed project gone:** "corpus-beta is no longer at its recorded location". The view closes and nothing is created.
- **Not loaded:** "Not loaded · Enter to load".
- **No catalog action:** each missing verb is `aria-disabled` with "Not available on this server yet. The inventory still reads. · What this server offers" (the last part links to Help › What this server offers).

**Multi-variant rules**

- Builds are project members. Every save names one build, and Save All is a confirmed batch of per-build saves, each with its own outcome ("2 saves: 2 finished").
- A program copy is never a new build. It aliases its build's SHA-256 identity and carries no identity edges or receipts until they are bound explicitly.
- A project archive captures the project, never one merged program. One build's GZF is ExportDialog's job (V10, one build).

**Linking**

- **Publishes:**
  - `panel=project` (Program files, Projects, Archive), registered in `location-schema.json`.
  - **Open**, which on a build publishes `build` (one history stop);
  - **Open ‹project›**, which publishes nothing until **Switch to ‹project›** is chosen on the StateNotice.
  - A viewed project, expansions and drafts are durable workspace state, never `project=`.
- **Follows:** the active project and the inspected build for the Save row, after the settle. Not holdable.
- **Targets rendered:**
  - a build → the Code Browser;
  - a version → VersionControlPanel (`panel=versions`);
  - transactions → EditHistory (`panel=history`);
  - owners → OwnershipPanel;
  - an archive → its ArtifactCard (`ws=evidence&panel=outputs&artifact=‹id›`);
  - a job → the dock records;
  - another project → the cross-project StateNotice.
- **Peek source:** Alt+↓ on a member reads its stored inventory row, and on an archive, its receipt header. Nothing opens or loads.
- **Absent copy:** "not reported by owner" · "not versioned" · "Nothing to save on ‹build›" · "viewed read-only · nothing admitted" · "Not loaded · Enter to load" · "Not available on this server yet. The inventory still reads. · What this server offers".
- **Target-size exception:** none; tree rows are 28px and every control is 24px, or 44px below 700px and with a coarse pointer.

**Keyboard**

- The tablist uses APG Tabs with manual activation. Program files and Projects are APG Treegrids: arrows move and expand, Enter opens (on another project it shows the StateNotice), F2 renames (`tabs.rename` in program rows), and Delete opens the Delete confirm (never deletes directly).
- `save` (Ctrl/Cmd+S): inside an open editor it saves that editor, as today. Outside any editor it arms **Save ‹inspected build›**, so a second Enter posts. It never posts from the key alone. See the proposals.
- `open` (Ctrl/Cmd+O) focuses the Projects tab. It never switches project.
- Keymap id `project.saveAll` has no keys; it is reached from the menu and palette only.

**Accessibility**

- The treegrids are named "Program files, corpus-alpha" and "Projects". Kind, saved state and writer are words, the kind chip carries its word, and glyphs are `aria-hidden`.
- The Save row is a group named "Save build-a". An armed Save says "Save build-a armed · Enter posts" in its description.
- The Delete and Save All dialogs are APG Alert dialogs whose `aria-describedby` points at the consequence sentence.
- Job transitions are announced once by the dock. The StateNotice follows its own rules.

**Parity rows covered**

Rows from the [Ghidra Code Browser parity specification](../../../../dashboard-design/2026-09-29-ghidra-code-browser-parity.md), section "Rows not yet designed".

- **V09** Project window and program files:
  - New, Open, Reopen (recent projects in the Projects table), Close (the Project menu's Close project; with no active project, the StateNotice offers Open ‹project› as its one armed action) and Delete Project;
  - the data tree and the table view as one treegrid with columns;
  - open, close, rename, move, delete and read-only for program files;
  - read-only views of other projects, with Copy into the active project through ImportAdmission;
  - Save Project, which is durable workspace state and needs no verb.
- **V10** Archive Current Project and Restore Project, as jobs with receipts, restore only into a new project.
- **V03** Save, Save As and Save All per program, distinct from check-in (VersionControlPanel) and from undo history (EditHistory).

**Prior art**

Ghidra Project Window and project menus (`FrontEndPlugin/*`: Creating, Opening, Re-opening, Closing, Deleting, Saving, Archive and Restore Project; Project Info), Ghidra Projects (`Project/Ghidra_Projects.htm`) and Saving Program Files (`ProgramManagerPlugin/Saving_Program_Files.htm`). Unlike Ghidra, creating or restoring a project never switches to it, a viewed project admits nothing, and Save never happens by itself on archive.

## Behavior

- Opening the Project window reads stored inventory only; it never opens a program, switches project or analyzes.
- Save writes transactions to the project file and never clears the undo stack. Check-in sends a version to the server and clears it (Version control).
- Restore never replaces a project; the restored project's receipts read historical.
