# InlineRename

The in-place editor for a name, a type or a comment, used by DecompileView, Listing and EntityRow: it shows the current value and its provenance tier, the proposed value, the tier after save, the exact target, any edit that arrived meanwhile, and posts one catalog action on Save, confirmed in place.

**Use it** wherever a single target is edited in place: a local, parameter or label in DecompileView or the Listing (Enter or F2 on the token, or Rename…, Retype… and Comment… in the link menu's Edit group), a function name in an EntityRow (F2 on the row), a global or data label from the menu, and a single proposed label applied from ContextPlacement (a batch goes through the ActionStrip and ConfirmDialog). It replaces the palette → ActionStrip → Fields… → confirm path for these verbs and adds no backend verb.

**Consumer provides** the target (program and build, function address, and the local's storage; or the symbol's address; or the address and comment kind) with its basis generation; the current name, type or comment with the winning NameProvenance tier and origin; the catalog actions for rename, retype and comment that `GET /api/v1/actions` exposes for this target, with their labels and fields (the design system names no action ids); the comment kinds the catalog exposes; the naming convention for the identifier kind; which builds are left unchanged; and live updates for the same target (an edit that arrives, then the job lifecycle after Save).

- **Opens under the line, never over it.** F2, and in the `ida` profile `n`, `y` and `;`, open this editor under the line or row it edits, pushing the following lines down. The popup form is used only where there is no line to push (a menu pick on a collapsed row).
- **Bound when opened.** The target and basis are captured at open and shown in the Target block: program, build, function address, and "local local_8 · stack [ebp − 0x4]" (a local has storage, not an address). Moving the selection never retargets an open editor, and it never changes the target build. If the selection moves the pane away while a draft is open, the draft is kept in durable workspace state and restored when the editor reopens on the same target.
- Fields: **Now** (current value in mono `ink-strong` plus the tier chip), **Name** (input on `well` framed by `line-control`), **Type** (when retype applies), **After save** (the new tier chip with a 2px `ink-strong` frame: "1 human · you"). Tier chips are NameProvenance tiers, number plus word (1 human, 2 debug info, 3 symbols, 4 analysis, 5 placeholder); placeholder and analysis chips are dashed. The Now chip links to NameProvenance. Name tiers never imply a verified claim.
- **Comment mode**, opened by Comment… or `;` in the `ida` profile: bound to the address, the build and one of the comment kinds the catalog exposes (a Kind field lists only those), with the current comment under Now. It confirms in place like a rename.
- **Confirmed in place.** The editor is the review. The field names its binding (program, build, address or local storage) and the tier change, and an "Enter or Save posts once" block states the catalog action by its label, old → new values, the build, and what stays unchanged: "Counterparts on build-b and build-c keep their names; propagation is a separate reviewed step." **Enter** or **Save** commits through the catalog action path once, with a versioned intent id, through the same admission path agents use. There is no ConfirmDialog for a single-target rename, retype or comment. ConfirmDialog is reserved for batch, destructive and cross-build changes (35 Confirming edits): a struct-field retype, a structure-layout change that resizes, overwrites or clears components, and a callee-signature edit count as cross-build, so for them Save opens ConfirmDialog naming the type or callee, the build and the known use or caller count, or "uses not indexed". Outside the open editor no key alone ever mutates.
- **No pre-disabled Save.** Save stays enabled while the editor is open. Validation runs on Enter or Save, before anything is posted: an invalid field keeps focus, gets `aria-invalid="true"` and a 2px `fact-failed` frame, and shows ✕ with a message linked by `aria-describedby` that is also placed in the polite status region. Messages name the rule and the fix: "`name` is already a parameter of ResourceRef::Resolve. Choose another name."; "`2nd` is not a C identifier. Start with a letter or _."; "`CacheEntery` is not a type in build-a." Nothing is posted.
- Convention hints under the field, never blockers: locals, globals and parameters `camelCase`; classes and types `CapitalCase`; structure fields `snake_case`; enum constants `COBRA_CASE`.
- **Conflict.** When another edit to the same target arrives while the editor is open, the editor shows ⇄ on `lane-fault-fill` with both values side by side: your draft (basis, not posted) and the arrived value (time, job link, session, tier, generation). The choices are Save mine over gen N (posts against the new basis), Keep ‹arrived value›, and Cancel. Neither is pre-picked; arrival order is not a tie-breaker.
- **Outcome lands on the token.** After Save the editor closes and the token gets an OutcomeCell: admitted → running → terminal word, with its job link. Nothing is announced on pending, and nothing is shown optimistically: the token keeps the old name until the terminal result. Then it shows the new name, its line's gutter says "✎ job c4d2" until the next navigation, and the polite region says once: "Rename saved: local_8 is now itemCount on build-a, job c4d2." It never says "decompile updated".
- **Ambiguous outcome.** When the result cannot be established: "Checking whether the operation completed". The OutcomeCell says "outcome unknown" in its plain frame, and edits of that target wait until it is reconciled; reading, peek and references stay available. A double activation, reconnect or stale tab never posts twice (same intent id).
- A failed job shows its FailureRecord reason in the token's OutcomeCell and keeps the draft; reopening the editor restores it for a new intent.
- Surfaces: `dialog-bg` with 1px `line-control`. The inline form has a 2px `ink-strong` rule at the inline start and pushes the code below it down; the popup form adds `shadow-popup`. Controls are `control-h-comfortable`, 44px below 700px.
- **Parity.** Both surfaces render the same Edit items from the same catalog and use the same target binding, fields and states. The static 8080 surface may render this editor, StorageEditor and the comment editor as dialogs anchored to the token or row, with identical words, fields and states.

**Linking**

- **Publishes:** nothing. A draft is never in the URL, and the editor is not a place.
- **Follows:** nothing; it stays bound to its target. Not holdable (held panes and kept cards are read-only and never open it).
- **Targets rendered:** the target function (the Code Browser at its build and address), the tier (NameProvenance for that field, `panel=names`), the arrived edit's job and the Save job (the dock Jobs record).
- **Peek source:** Alt+↓ on the tier chip reads the stored NameProvenance rows for the field; on a job link, the stored job record. Nothing is fetched.
- **Absent copy:** a local shows its storage in words and has no address link; a function with no identity says "no identity · no counterparts to update"; a comment kind the catalog does not expose is not listed.
- **Target-size exception:** none; fields and buttons are at least 24px (28px comfortable), 44px below 700px.

**Keyboard**

- Opens with focus in Name (Enter, F2, Rename…), Type (Retype…) or the comment text (Comment…, `;`), the current text selected. F2 is `code.rename` in code wells and `tabs.rename` on rows.
- Tab and Shift+Tab move through the editor's links, fields and buttons; Tab past Cancel continues after the invoking token or row.
- **Enter** in a field, or Ctrl/Cmd+S, saves: it posts the catalog action once, or opens ConfirmDialog for a cross-build change. This is the only key path that mutates, and it exists only inside the open editor. **Esc** follows the one order in `keymap.json` `escapeOrder` (edit mode, restoring the text) and returns focus to the token or row.
- In the conflict state focus stays in the field; the choices are the first buttons in the footer.

**Accessibility**

- Non-modal `role="dialog"` named "Rename or retype ‹name›" or "Comment at ‹address›"; the invoking token or row carries `aria-expanded="true"` and `aria-controls`. The grid cell that hosts it sets `aria-readonly="false"`.
- Every field has a visible `label`. Hints and errors are linked with `aria-describedby`; invalid fields carry `aria-invalid`. WCAG 3.3.1 and 3.3.3: the error names the field and the fix. WCAG 3.3.4: the review block shows exactly what will change, and where, before Save.
- WCAG 4.1.3: a validation error is polite (and focused); a conflict is assertive (`role="alert"`) because it blocks the action in hand; nothing is announced on pending; the outcome is announced once, at the terminal result.
- WCAG 3.2.2: typing never saves, navigates or retargets; only Enter or Save posts.
- Tier chips are a number and a word; the invalid frame is backed by the ✕ glyph and text; the OutcomeCell uses words and frame weight, never color alone.
- Identifiers carry `translate="no"`.

**Removes switching** (counts from the plan ledger):

- J11 rename or retype a local seen in the decompiler: 6 → 0 (F2, type, Enter; U185).
- J21 inner loop, a catalog verb on the selected row read on the row: 5 → 2, credited to U184; F2 on an EntityRow is its rename form.
- J18 why a function has its name: 4 → 0, credited to the "Why this name" rail section (U176); the Now chip opens it in place.
