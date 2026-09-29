# ScriptConsole

An advanced panel that holds the script manager, a read-only console transcript, an interpreter and the list of script bundles, where running a script or an interpreter line is a catalog job that names its target build or builds and is confirmed before it posts.

**Use it** from the palette ("Scripts", "Run script…", "Interpreter") and the Tools menu, only when **Advanced** is on in View settings; otherwise the panel is hidden, not shown disabled. It replaces Ghidra's Script Manager, Script Quick Launcher, Console, Python interpreter and Bundle Manager windows. Reading a finished run's transcript in the dock never needs Advanced.

**Consumer provides** the script list read from the server (file name, category, description, author, declared menu path and key binding, directory, bundle, compile status with the first error line); the catalog action that executes a script (read from `GET /api/v1/actions`; its id is never named here); the inspected build and selection that would be passed as script state (current address, current selection, current program); for each build the writer lock as reported; the viewer's last-run script; per run the job id, build, Job outcome word, the job's log lines as recorded and the transaction it committed, if any; the interpreter session binding (build, confirm time, lines run); and the bundle list with each bundle's kind and state.

**Anatomy**

- **Header.** "Scripts · ‹project› · advanced", a standing caution: "A script can change anything in a program. Each run is one catalog job against one named build and confirms first." Then an APG tablist: Manager · Interpreter · Bundles.
- **Manager.** A filter field that matches name or description and reports "N of M scripts match" in a status; a category tree (APG Tree, counts per category); the scripts grid with Status (✓ compiles, ✕ compile error with its line), **Declares** ("writes: unknown · scripts declare no write scope; treated as mutating") and Last run (job, build, outcome word); a description list for the focused script (category, author as the header states it, menu path and key binding "declared in the header · not bound here; scripts are not catalog entries", directory).
- **Run buttons.** **Run on ‹build› (catalog)…** names the inspected build; **Run on other builds…** chooses builds explicitly (there is no "all builds" default); **Run last…** re-arms the last script against the current selection's build, never the last run's build. **New · Rename · Delete** and **Edit** are unavailable until a catalog action writes script files, and say so.
- **Confirm a run.** Every run opens a ConfirmDialog (unrestricted mutation): title "Run ‹script› on ‹build›" or "on build-b and build-c"; one sentence that each build is its own job, that what the script writes is not known before it runs, and what can and cannot be undone; a per-build preview table of the script state passed (the address is the counterpart through an accepted identity edge, or "no counterpart on build-d · not runnable there") and the writer state (a build with a writer waits in admission). The primary button counts the jobs ("Run 2 jobs"). Focus starts on Cancel.
- **Transcript.** The job's recorded log in a `well`, read-only: each line carries job id and time; addresses are typed links to that build; compile errors carry ✕ and the file and line. **Scroll lock**, **Clear view** ("hides lines here only; the job's log is kept") and **Find** act on the view only. The footer links the job record and, when the job committed a transaction, that transaction in EditHistory.
- **Interpreter.** A session bound to one build, started by its own ConfirmDialog ("Start an interpreter session on build-a. Each line runs as its own job on build-a and can change the program."). After that each line posts on Enter, the way an inline editor confirms in place, and appears in the transcript with its job id. The binding strip says "Session on build-a · confirmed 14:10 · 3 lines run · switching build ends the session". **Interrupt ‹job› (catalog)** cancels the running line's job; **Reset** ends the session and needs a new confirm.
- **Bundles.** A read-only table of source bundles (path, user or system, state: active, inactive, build error with its reason). Enable, Disable, Clean and Refresh are not offered until a catalog action exists. Bundles are tool-level and affect script runs on every build; they never belong to one program.

**States**

- **Advanced off:** the panel is hidden; "Scripts are an advanced tool. Turn on Advanced in View settings to show Scripts."
- **Compile error:** ✕ in Status, Run stays available (the server recompiles on run) and the transcript shows the error lines.
- **Writer owned:** the preview row says "owned by job ‹id› · external · this job waits in admission". Nothing is killed or restarted.
- **No counterpart:** for a build with no accepted identity edge for the current entity, the preview says "no counterpart on ‹build› · script state has no address" and that build is not checked by default.
- **Running, checking, finished, failed, cancelled:** the Job outcome words. "Checking whether the operation completed" disables Run for that script and build until reconciled. A cancelled run names what was kept; it never claims a rollback.
- **Script list not read:** "Not loaded. Open to read it." Listing scripts is a read and never compiles or runs anything.

**Multi-variant rules**

- Keyed by script and project, with build as an explicit target on every run. A run on several builds is several jobs in one confirmed batch, each with its own outcome ("2 runs: 1 waiting · 1 finished").
- Script state (current address, selection) moves between builds only through recorded anchors and identity edges, never by offset.
- A script's effect on one build is never propagated to others by this panel; propagation is PropagationTransfer's separate step.

**Linking**

- **Publishes:** `panel=scripts` (proposed) with `q` for the filter text. The interpreter session and scroll lock are durable workspace state, not location. Running never changes the selection.
- **Follows:** the inspected build and selection, settle, for the next run's target; a confirmed dialog and an interpreter session keep their binding when the selection moves ("Bound to build-a · selection is now build-c · Rebind"). Not holdable.
- **Targets rendered:** job ids → the dock Jobs and Logs records · addresses in the transcript → the Code Browser at that build · a committed transaction → EditHistory for that build (`panel=history`, proposed) · owners → OwnershipPanel.
- **Peek source:** Alt+↓ on a script reads its stored header and description; on a job, the stored job record. Nothing is compiled or fetched.
- **Absent copy:** "writes: unknown" · "never run" · "no counterpart on ‹build›" · "Not loaded. Open to read it." · "not bound here; scripts are not catalog entries".
- **Target-size exception:** addresses inside the transcript are inline code tokens (the inline exception); all controls are 24px, 44px below 700px and with a coarse pointer.

**Keyboard**

- The tablist is APG Tabs with manual activation (Interpreter and Bundles read more). The category tree is an APG Tree; the scripts grid is an APG Grid with typeahead behind `/`.
- In the interpreter input, Enter posts the line within the confirmed session, ↑/↓ recall earlier lines, Esc leaves the input (the one Esc order). Ctrl/Cmd+F in the transcript opens Find, as in code wells.
- Proposed keymap ids: `scripts.open` (no keys · menu and palette only), `scripts.runLast` (no keys; arms only). No key posts a run.

**Accessibility**

- The caution is `role="note"`; the confirm is an APG Alert dialog with `aria-describedby` on its consequence sentence.
- The transcript is a `pre` with an accessible name and is not a live region; each new interpreter result is announced once in the polite region ("Line 3 on build-a: job b7e3 running"), never per poll.
- Status and outcome words are text; glyphs are `aria-hidden`. Script names carry `translate="no"`.

**Parity rows covered**

- **C01** Script Manager: category tree, table, filter, run, run last, quick launcher (the palette's "Run script…" lists recent scripts first), create, rename, delete, key binding and directories (read-only until catalog actions exist).
- **C03** interpreter: interactive session, interrupt and reset, bound to one build.
- Also: **C02** console output, scroll lock, clear, find and navigation from addresses (the transcript; the full record stays ActivityRecord's); **C04** Bundle Manager as a read-only list; **C05** script key bindings stay unbound because scripts are not catalog entries (the row stays missing until they are).

**Prior art**

Ghidra Script Manager, Script Quick Launcher and Script Development (`GhidraScriptMgrPlugin`), the Console (`ConsolePlugin`), the Python interpreter and Bundle Manager (`BundleManager`). Unlike Ghidra, a run never uses an implicit current program: the build is named in the confirm.
