# EditHistory

Undo and redo for one build's program as its list of recorded transactions, with Undo, Redo and "Undo to here" run as confirmed catalog verbs, propagated edits undone per recipient, and an honest "cannot be undone" on everything a transaction list cannot take back.

**Use it** from the Edit menu (Undo…, Redo…, Edit history), the palette ("Undo", "Redo", "Edit history"), a job record's "Transaction" link, and the ScriptConsole transcript footer. It replaces Ghidra's Undo and Redo toolbar buttons and their drop-down lists. EntityTimeline keeps showing edits per entity; this list is per program.

**Consumer provides** the build and its program's undo stack as the server reports it: each transaction's name (as Ghidra records it), position, time, submitter (you, agent or external), the job or inline edit that made it and the job's outcome, the change count, and any propagation it belongs to (donor, recipients); the redo list; the stack limit; whether the stack was cleared (program closed, or a new edit cleared the redo list) and when; the last checked-in version and the transactions since (VersionControlPanel); older transactions from the event store, marked as not undoable; the writer lock as reported; and the catalog actions for undo and redo (read from `GET /api/v1/actions`; no action id is named here; today they are a gap and the verbs say so).

**Anatomy**

- **Header.** "Edit history · ‹build›" and a summary: "undo stack 5 of 20 (Ghidra keeps the last 20) · 1 redo available · version 7 checked in · 5 transactions since · writer: this session · read 14:08". A Program segment picks the build. There is no merged all-builds stack: each build has its own history, and switching builds switches lists.
- **Redo group** (undone transactions, oldest undo last) on `chassis`, each "↷ redo available", headed "Redo · undone, can be redone until the next edit".
- **Undo stack**, newest first. Each row: position, the transaction name with typed links (address, entity), its state word on the right, and a meta line: submitter and job or "inline edit", time, and what it touched. State words: "↶ undoable"; "↶ program changes undoable · side effects are not" for a job; "↶ undoable on build-a only" for a propagated edit; "would make receipt ‹id› stale" when undoing invalidates a receipt.
- **Cannot be undone.** A separate group below the stack: "⊘ cannot be undone here" rows for transactions checked in to the server, beyond the stack limit, or recorded before the program was last closed. A job row also carries "⊘ its log, receipt and transcript cannot be undone".
- **The boundary sentence**, always under the list: "Undo reverts the program's changes on ‹build›. It does not delete jobs, logs, receipts, artifacts or files a job wrote: byte journal rollback ≠ undo of executed side effects. Undone work leaves its receipts marked ◷ stale."
- **Verbs.** **Undo…** (the top transaction), **Redo…** (the next redo), and **Undo to here…** on a row, which undoes that transaction and every newer one. A single top undo or redo of a single-target edit (one inline rename, retype or comment) confirms in place, naming the transaction and the build (Linked views, Confirming edits; `edit.undo`). Every other undo or redo (a job's transaction, a batch, a propagated edit, or Undo to here…) opens ConfirmDialog: title "Undo 2 transactions on build-a"; the consequence names each transaction, what a job keeps, "Other builds are unchanged" and "Both can be redone until the next edit on build-a". The primary button repeats the verb and count ("Undo 2").

**States**

- **Propagated edit:** "Undo applies to build-a only." The donor keeps its value; other recipients keep theirs; each recipient's undo is its own step in its own history.
- **Writer owned:** "‹build› has a writer" with the owner as reported; Undo waits; nothing is killed or restarted.
- **Modification conflict:** "Undo refused: ‹build› changed since you armed it", naming the new transaction; nothing was undone. "Review the new change, then Undo again on the new top."
- **Stack cleared:** "No undo stack for ‹build›", with why (closed at ‹time›, or "Redo list cleared by ‹transaction› at ‹time›"). Earlier transactions are listed from the event store and cannot be undone here.
- **No catalog action:** Undo and Redo are disabled with "Not available on this server yet. The list still reads. · What this server offers", where the last part links to Help › What this server offers.
- **After a verb:** the Job outcome words on the invoking row; the terminal message names the result ("Undo saved on build-a: 2 transactions reverted, job ‹id›"). Nothing is shown optimistically.
- **Unsaved and saved:** the summary distinguishes transactions not yet saved from saved but not checked in (Ghidra Save; V03); saving never clears the undo stack, checking in does.

**Multi-variant rules**

- Keyed by program: one history per build, never interleaved. Every verb names its build.
- Undoing on one build never undoes on another. A propagated edit shows its donor and recipients as words and links, and each recipient's history offers its own undo.
- Undoing a transaction that produced a receipt marks that receipt stale on that build only.

**Linking**

- **Publishes:** `panel=history` (registered) with `build`. The focused row is durable workspace state, not location. Undo and Redo never change the primary selection.
- **Follows:** the inspected build, settle, unless the Program segment was set by hand in this panel. Not holdable.
- **Targets rendered:** addresses and entities in transaction names → the Code Browser at that build · jobs → the dock Jobs record · propagation → PropagationTransfer's record for that job · receipts → the receipt card · a checked-in version → VersionControlPanel history (`panel=versions`).
- **Peek source:** Alt+↓ on a transaction reads its stored change summary (what it changed, from the event store); on a job, the stored job record.
- **Absent copy:** "cannot be undone here" · "No undo stack for ‹build›" · "Redo list cleared by ‹transaction› at ‹time›" · "Not available on this server yet. The list still reads. · What this server offers" · "beyond the undo limit (20)".
- **Target-size exception:** addresses and job ids inside transaction rows are inline tokens (the inline exception); row buttons are 24px, 44px below 700px and with a coarse pointer.

**Keyboard**

- The list is in reading order; ↑/↓ move the focused row when the list has focus (roving focus on rows); Enter on a row's **Undo to here…** opens the confirm. Links inside a row are reachable with Tab.
- Keymap ids: `edit.undo` (Ctrl/Cmd+Z) and `edit.redo` (Ctrl/Cmd+Shift+Z, and Ctrl+Y on Windows and Linux), global but never in text fields or edit mode, where the browser's own undo applies. A single top undo of a single-target edit confirms in place; a batch, cross-build or multi-step undo arms ConfirmDialog. They never post silently.

**Accessibility**

- Each row reads as one sentence: "4, ApplyCacheEntryLayout.py, 12 changes, by script job a3f9 finished at 14:02; program changes undoable, side effects are not; its log, receipt and transcript cannot be undone." Glyphs are `aria-hidden`.
- The focused row carries `aria-current="true"`. Group headings are list items with text, not headings, so the list keeps one structure.
- Confirm is ConfirmDialog (APG Alert dialog). The terminal message is announced once in the polite region.

**Parity rows covered**

Rows from the [Ghidra Code Browser parity specification](../../../../dashboard-design/2026-09-29-ghidra-code-browser-parity.md), section "New components needed".

- **V01** Undo and Redo of program transactions: per-build list, Undo and Redo as catalog verbs, the drop-down "undo to here", the 20-step limit and the redo list cleared by a new edit.
- Also: **V02** transactions and modification conflicts on undo, and the saved versus checked-in distinction of **V03**.

**Prior art**

Ghidra Undo/Redo (`Tool/Undo_Redo.htm`): a limit of 20, redo cleared by a new edit, a drop-down list that undoes an item and all above it. The boundary sentence reuses the Copy guideline's "byte journal rollback ≠ undo of executed side effects".

## Behavior

- Undo reverts the program's changes on build-a. It does not delete jobs, logs, receipts, artifacts or files a job wrote: byte journal rollback ≠ undo of executed side effects.
- Undone work leaves its receipts marked ◷ stale.
- Undo on build-b waits while another writer owns it; nothing is killed or restarted.
- Undo refused: the build changed since you armed it. Nothing was undone. Review the new change, then Undo again on the new top.
