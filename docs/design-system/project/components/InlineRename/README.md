# InlineRename

The in-place rename and retype editor used by DecompileView and EntityRow: it shows the current name and its provenance tier, the proposed name and type, the tier after save, the exact target, any edit that arrived meanwhile, and posts one reviewed catalog action on Save, confirmed in place.

**Use it** wherever a name or type is edited in place: a local, parameter or label in DecompileView (Enter or F2 on the token, or Rename… and Retype… in the token menu), a function name in an EntityRow (F2 on the row), a global, field or callee from the token menu. It replaces the palette → ActionStrip → Fields… → confirm path for these verbs and adds no backend verb.

**Consumer provides** the target (program and build, function address, and the local's storage; or the symbol's address; or the type and field offset) with its basis generation; the current name and type with the winning NameProvenance tier and origin; the catalog action ids (`rename-variable`, `set-local-variable-type`, `rename-function`, `rename-data-label`) and their fields; the naming convention for the identifier kind; which builds are left unchanged; and live updates for the same target (an edit that arrives, then the job lifecycle after Save).

- **Bound when opened.** The target and basis are captured at open and shown in the Target block: program, build, function address, and "local local_8 · stack [ebp − 0x4]" (a local has storage, not an address). Moving the selection never retargets an open editor, and it never changes the target build. If the selection moves the pane away while a draft is open, the draft is kept in durable workspace state and restored when the editor reopens on the same target.
- Fields: **Now** (current name in mono `ink-strong` plus the tier chip), **Name** (input on `well` framed by `line-control`), **Type** (when retype applies), **After save** (the new tier chip with a 2px `ink-strong` frame: "1 human · you"). Tier chips are NameProvenance tiers, number plus word (1 human, 2 debug info, 3 symbols, 4 analysis, 5 placeholder); placeholder and analysis chips are dashed. The Now chip links to NameProvenance. Name tiers never imply a verified claim.
- **Confirmed in place.** The editor is the review. The field names its binding (program, build, address or local storage) and the tier change, and a "Enter or Save posts once" block states the exact catalog action or actions, old → new values, the build, and what stays unchanged: "Counterparts on build-b and build-c keep their names; propagation is a separate reviewed step." **Enter** or **Save** commits through the catalog action path once, with a versioned intent id, through the same admission path agents use. There is no extra ConfirmDialog for a single-target rename or retype; ConfirmDialog is reserved for batch, destructive or cross-build mutations (PropagationTransfer). Outside the open editor no key alone ever mutates.
- **No pre-disabled Save.** Save stays enabled while the editor is open. Validation runs on Enter or Save, before anything is posted: an invalid field keeps focus, gets `aria-invalid="true"` and a 2px `fact-failed` frame, and shows ✕ with a message linked by `aria-describedby` that is also placed in the polite status region. Messages name the rule and the fix: "`name` is already a parameter of ResourceRef::Resolve. Choose another name."; "`2nd` is not a C identifier. Start with a letter or _."; "`CacheEntery` is not a type in build-a." Nothing is posted.
- Convention hints under the field, never blockers: locals, globals and parameters `camelCase`; classes and types `CapitalCase`; structure fields `snake_case`; enum constants `COBRA_CASE`.
- **Conflict.** When another edit to the same target arrives while the editor is open, the editor shows ⇄ on `lane-fault-fill` with both values side by side: your draft (basis, not posted) and the arrived value (time, job link, session, tier, generation). The choices are Save mine over gen N (posts against the new basis), Keep ‹arrived value›, and Cancel. Neither is pre-picked; arrival order is not a tie-breaker.
- **Outcome lands on the token.** After Save the editor closes and the token gets a compact lifecycle cell: admitted → running · job ‹id› (a link). The token keeps the old name until the terminal result. Then it shows the new name, its line's gutter says "✎ job ‹id›" (changed by job) until the next navigation, and the polite region says once: "Rename saved: local_8 is now nameText on build-a, job c4d2." Nothing is shown optimistically.
- **Ambiguous outcome.** When the result cannot be established: "Checking whether the operation completed". The lifecycle cell says "outcome unknown" in a dashed frame, and rename and retype of that target wait until it is reconciled; reading, peek and references stay available. A double activation, reconnect or stale tab never posts twice (same intent id).
- A failed job shows its FailureRecord reason in the token's lifecycle cell and keeps the draft; reopening the editor restores it for a new intent.
- Surfaces: `dialog-bg` with 1px `line-control`. The inline form under a code line has a 2px `ink-strong` rule at the inline start and pushes the code below it down; the popup form adds `shadow-popup`. Controls are `control-h-comfortable`, 44px below 700px.
- Both surfaces use the same catalog actions, target binding and states. The static 8080 surface may render the editor as a dialog anchored to the token or row.

**Linking**

- Publishes nothing to the location: a draft is never in the URL, and the editor is not a place.
- Follows nothing: it stays bound to its target.
- Renders the target function (Code Browser at its address), the tier (NameProvenance for that field), the arrived edit's job and the Save job (dock Jobs record).
- Absent: a local shows its storage in words and has no address link; a function with no identity says "no identity · no counterparts to update".

**Keyboard**

- Opens with focus in Name (Enter, F2, Rename…) or Type (Retype…), the current text selected.
- Tab and Shift+Tab move through the editor's links, fields and buttons; Tab past Cancel continues after the invoking token or row.
- **Enter** in a field, or Ctrl/Cmd+S, saves: it posts the catalog action once. This is the only key path that mutates, and it exists only inside the open editor. **Esc** leaves the editor restoring the text (Keymap Esc order) and returns focus to the token or row. `n` and `y` in the `ida` profile open the editor on the name or the type.
- In the conflict state focus stays in the field; the choices are the first buttons in the footer.

**Accessibility**

- Non-modal `role="dialog"` named "Rename or retype ‹name›"; the invoking token or row carries `aria-expanded="true"` and `aria-controls`.
- Every field has a visible `label`. Hints and errors are linked with `aria-describedby`; invalid fields carry `aria-invalid`. WCAG 3.3.1 and 3.3.3: the error names the field and the fix. WCAG 3.3.4: the review block shows exactly what will change, and where, before Save.
- WCAG 4.1.3: a validation error is polite (and focused); a conflict is assertive (`role="alert"`) because it blocks the action in hand; the outcome is announced once, at the terminal result.
- WCAG 3.2.2: typing never saves, navigates or retargets; only Enter or Save posts.
- Tier chips are a number and a word; the invalid frame is backed by the ✕ glyph and text; the lifecycle cell uses words and frame weight, never color alone.
- Identifiers carry `translate="no"`. Targets are at least 24px, 44px below 700px.

**Removes switching:** J11 rename or retype a local seen in the decompiler, 6 → 0 (no palette, ActionStrip, Fields…, confirm, Jobs dock or return to the Decompiler; the outcome lands on the token). J21 inner loop for rename-function on the selected row, 5 → 0 (F2 on the EntityRow instead of palette → strip → Fields… → Run → confirm → dock). J18 why a function has its name, 4 → 1 (tier and origin are in the editor, and the tier opens NameProvenance in place; rejected alternatives still live there).
