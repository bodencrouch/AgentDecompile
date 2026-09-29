# VersionControlPanel

Ghidra Server version control for every build of the project in one grid: each build's version and checkout state, check out, check in, update with merge, undo checkout, add to version control, undo hijack, version history and other users' checkouts, with an exclusive checkout shown as that build's one-writer lock and every verb run as a catalog job.

**Use it** from the Project menu, the palette ("Version control", "Check in…", "Update…") and a build's row menu in the navigator. It replaces Ghidra's project-window version control actions, Show Version History, View Checkouts and the check-in and merge dialogs. Opening it reads checkout state; it never connects, checks out, merges or analyzes by itself.

**Consumer provides** the repository connection state as the server reports it (connected, reconnecting with the last snapshot time, not a shared project) and the viewer's server identity; per build its domain file kind (versioned program file, private file, hijacked), local and latest versions, checkout (none, exclusive or not, by you or another user as reported, since when), unsaved and un-checked-in transaction counts, and the writer lock as reported (owner kind, job, PID and start time); per build its version history (version, time, submitter, comment) and the checkouts the server lists; after an update or check-in, the merge job's per-category counts (memory, program trees, data types, program context, listing, externals, properties) and each conflict's three values (latest, checked out, original); and the catalog actions for checkout, check-in, status, sync and administration (read from `GET /api/v1/actions`; no action id is named here).

**Anatomy**

- **Connection line.** "connected · Ghidra Server repository ‹name› (RMI over SSL) · as you · checkout state read 14:02", and a link to the one-writer lock node. The repository is a Ghidra Server repository; the word "repository" is reserved for it (Copy, Terms).
- **Builds grid.** One row per build: Version ("7 of 7 · ✓ latest", "5 of 6 · ↓ update available · version 6 checked in by another user 13:58", "not versioned"); Checkout ("● checked out · exclusive · by you · this checkout is the writer lock for build-a", "checked out · not exclusive · by you", "● checked out · exclusive · by another user · as reported: ‹user› · since 11:20", "not under version control"); Local changes and writer ("✎ 5 transactions not checked in · saved 14:06 · writer: this session", "writer: job 77c0 · external"); Verbs (catalog actions, labelled without a "(catalog)" mark), only those that apply to that row's state. The words are ✓ latest · ↓ update available · ● checked out, and ✎ for transactions not checked in (never ◷, which means stale).
- **The one-writer rule.** An exclusive checkout is drawn with the lock glyph and the word, and is that build's writer lock. A non-exclusive checkout does not make a second writer: admission still checks the real owner of the program, and a verb that needs the writer waits with the owner named. Another user's exclusive checkout makes the build read-only here ("Open version 3 read-only"). Memory map changes need an exclusive checkout (Ghidra's rule), so MemoryMapTable's edits are unavailable on a non-exclusive checkout and say why.
- **Check in (ConfirmDialog).** Title "Check in ‹build› as version N"; the consequence names the transaction count, the server's current version and whether a merge will run ("The server is at version 7, the same version you checked out, so nothing needs merging"), and "After check-in these transactions cannot be undone here". Fields: Comment; Stay checked out on ‹build› ("the writer lock stays yours"; Ghidra's Keep checked out, renamed because "Kept" is reserved for evidence cards); Save a private copy of this version (.keep file). The footer says "Other builds are unchanged." Checking in several builds is one batch dialog naming each build, its version and whether it merges.
- **Update and merge.** Update merges the latest version into the checkout as a job. The panel shows per-category counts; non-conflicting changes merge automatically. Each conflict opens in MergeReview (adapted to check-in conflicts) with three values, latest, checked out and original; nothing is picked for you. A choice is a catalog action on that build; "use for all in this category" confirms through ConfirmDialog. The same summary appears when a check-in needs a merge.
- **Program options are not merged.** A standing note: analysis and other program options are not merged on check-in or update, so the latest checked-in values can replace yours; it links AnalyzerPanel's per-build comparison.
- **History.** Per build: version, checked-in time, submitter (you, agent with job, or another user as reported), comment. **Open read-only** reads that version; it never checks out, merges or analyzes. **Delete version N…** is offered only for the oldest or latest version, only to its owner or a repository administrator, and never while it is checked out; it confirms through ConfirmDialog.
- **Other verbs.** Check out… (choose exclusive; exclusive is the default when the operator will write), Undo checkout… (ConfirmDialog: "discards N transactions not checked in; save a private copy" option), Add to version control…, Undo hijack… (keeps the private file as a copy), and View checkouts (read-only list; ending another user's checkout needs a repository administrator and is not offered here).

**States**

- **Disconnected:** ↻ "Reconnecting. Showing data from 14:02." Server verbs are unavailable; local edits on checked-out builds continue.
- **Not a shared project:** "‹project› is not under version control." with Add to version control….
- **Update available, checked out by another user, hijacked, private file, writer owned:** as in the grid, each with glyph and word.
- **Merge pending:** "3 conflicts wait for your choice" with the job link; the build's writer lock stays with the merge until the conflicts are resolved or the update is cancelled.
- **Nothing to check in:** Ghidra refuses to check in an unchanged file; Check in… is `aria-disabled` with "No changes to check in on ‹build›".
- **Modification conflict:** a verb refused because the program changed since it was armed shows the StateNotice conflict state with **Review changes** (the catalog's conflict action, labelled from the catalog). The action id is never shown.
- **Job outcomes:** pending, admitted, waiting, running, checking, finished, failed, cancelled on the invoking row. A finished check-in says which version it created; it never says "synced" or "saved to server" beyond what the receipt records.

**Multi-variant rules**

- Keyed by project with build as the row. Each verb names its exact build; a batch across builds confirms and reports one outcome per build.
- Version control never moves anything between builds. Versions of build-a and versions of build-c are unrelated histories; propagation stays PropagationTransfer's separate step.

**Linking**

- **Publishes:** `panel=versions` (registered) with `build` for the focused row. Dialogs and the history disclosure are not location. Nothing here changes the primary selection except Open read-only, which opens that version as a Held pane.
- **Follows:** the inspected build, settle, to focus its row. Not holdable.
- **Targets rendered:** jobs → the dock Jobs record · the writer lock → OwnershipPanel and `?node=lock-1` · conflicts → MergeReview for that build and category · analysis options → AnalyzerPanel (`panel=analysis`) · a version → a read-only Held pane of that version.
- **Peek source:** Alt+↓ on a version reads its stored comment and change summary; on a lock or job, the stored record. Nothing is fetched from the server on Peek.
- **Absent copy:** "not versioned" · "as reported: ‹user›" · "owner: unknown" · "Reconnecting. Showing data from ‹time›." · "Ending another user's checkout needs a repository administrator and is not offered here."
- **Target-size exception:** none; row buttons are 24px, 44px below 700px and with a coarse pointer.

**Keyboard**

- The builds grid is an APG Grid, one tab stop; Enter on a row's verb opens its dialog; the history is a table in reading order. Dialogs follow ConfirmDialog (focus starts on Cancel; Esc cancels).
- Keymap id `vcs.open` (registered; "Version control"; no default key, menu and palette only, because `g then v` belongs to VTableBrowser). No key checks in, updates or checks out.

**Accessibility**

- Each row reads as one sentence: "build-a, version 7 of 7, latest, checked out exclusive by you, writer lock, 5 transactions not checked in." Glyphs are `aria-hidden`.
- Disabled verbs use `aria-disabled` with the reason in `aria-describedby` ("Update waits: build-b has a writer, job 77c0, external").
- Merge counts are a list; each non-zero count is a link naming its build and category.

**Parity rows covered**

Rows from the [Ghidra Code Browser parity specification](../../../../dashboard-design/2026-09-29-ghidra-code-browser-parity.md), section "New components needed".

- **V04** multi-user repository: connect, add to version control, check out, check in, undo checkout, update, version history, view and find checkouts, undo hijack, server connection.
- Also: **V05** merge on check-in and update (the summary here; conflict choices in MergeReview), **V02** modification conflicts on these verbs, and the "Keep checked out" (here Stay checked out) and private-copy options of Ghidra's check-in.

**Prior art**

Ghidra Project Repository (`VersionControl/project_repository.htm`), Merge Program Files (`Repository/Merge_Program_Files.htm`) and the Ghidra Server topics. The merge's three-value choice follows Ghidra's Latest, Checked Out and Original panels; its presentation reuses MergeReview's master-detail form.
