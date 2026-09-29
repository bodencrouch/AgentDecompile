# BeforeAfterBand

Its own component, not a variant of SourceRepairDiff: an in-place band inserted under the statements an edit changed, once the edit's job has reached its terminal result. It shows old → new name, type, signature or storage with + / − / ± markers and words, the job link and read time, and leaves a "✎ job ‹id›" gutter mark on each changed line. It is dismissible.

**Use it** in DecompileView, Listing, the signature line and StorageEditor after a catalog edit (rename, retype, comment, edit signature, edit storage, apply type) submitted from where the operator reads: F2, the link menu's Edit group or the ActionStrip. The operator sees what changed without opening the Jobs dock or re-reading the function by eye.

**Consumer provides** the job id, verb and terminal state; the target (entity, function, concrete build, field kind and which variable, parameter or field); the old and requested values from the job record; the after value and its source, which is the job's record or receipt, or a decompile cache entry written after the terminal result, with its read time and generation; whether the after value differs from the request; and the lines whose text changed, for the gutter.

- **Placement: under, never over.** The band is inserted under the changed statements, like an inline Peek. It pushes the following lines down and never overlays code. In a grid-based well it is its own row with one cell spanning every column, so the grid stays valid.
- **Label.** The header reads "Before / after job c4d2 · read 14:03" with the verb ("Rename local") and the job link with its terminal word, then a 24px ✕ named "Dismiss before and after for job c4d2". The footer says "decompiler output; not a verified claim".
- **Source of the after value.** It is shown only from the job's record or receipt, or from a decompile cache entry written after the terminal result. Otherwise the band says "After: not read · Decompile predates job c4d2 · Enter to decompile" and shows only the old → new values from the job record, labelled as such. It never paints the requested value as if it were applied, and nothing is shown before the terminal result. If the after value differs from the request, the band shows the read value and says so ("Requested itemCount; the function already had one").
- **Markers with words, no fills.** Each field is a `<dl>` group: the field kind as `dt` ("Name · local variable in ResourceRef::Resolve · build-a", "Storage · parameter 1", "Signature", "Return") with "± changed" or "+ added", then a "− before" line and a "+ after" line, each starting with the marker and the word in `type-kicker` `ink-muted`. Before values are mono `ink-muted`; after values are mono `ink-strong`; the tokens that changed are bold. There are no `rep-candidate` or `lane-fault-fill` fills, and no red or green.
- Band: `pane` fill, 1px `line`, a 2px `ink-strong` inline-start rule (solid in every state; a failed job says ✕ failed in words). Fields lay out in columns of at least 260px and stack in the rail.
- Footer: how many lines changed and the gutter rule, or the job's own failure ("Worker exited 1. No line is marked changed."). A failed or refused job shows the value as unchanged ("local_8 · unchanged"); a stale refusal says what changed since the edit was bound.
- **Gutter**: every line whose text changed carries a 3px `ink-strong` gutter bar and, on the first line of each changed run, "✎ job c4d2" (✎ `aria-hidden`, the job id a link) in `ink-muted` at the line end, the same mark InlineRename leaves. Each marked line also carries the hidden words "changed by job c4d2". The marks stay until the next navigation (a Go that leaves the function), survive dismissing the band, and are never animated.
- **Dismiss** hides the band only; the gutter marks stay (35).
- **Scope** is one concrete build: the band says the build, and the footer says when other builds are unaffected ("this edit is scoped to build-a"). Propagation to other builds is separate work with its own receipts.
- Naming hints follow the project conventions (camelCase locals and parameters, PascalCase types, snake_case fields, COBRA_CASE enum constants) in the edit field, never here: the band shows what the program now holds.
- Both surfaces show the band from the same job record and read; the static 8080 surface may render it above the well instead of between lines, with the same words.

**Linking**

- **Publishes:** nothing. Dismiss changes only this band; it never moves the primary location, holds or keeps, and never touches history.
- **Follows:** the function and build it was raised in. It appears only after the job's terminal result; leaving the function (a Go) removes the band and the gutter marks. Not holdable.
- **Targets rendered:** job id → the dock Jobs record (it does not move the primary location) · the read's basis → the ProvenanceStamp detail · the function and build in the field label as text. Link names read "Job c4d2, rename local, finished".
- **Peek source:** Alt+↓ on the job id reads the stored job record as a read-only ActivityRecord; Shift+K inside the Peek keeps it. The band itself reads only the job record, its receipt or the post-terminal decompile cache entry the host already has.
- **Absent copy:** "After: not read · Decompile predates job c4d2 · Enter to decompile" · "none" (a value that did not exist before) · "unchanged" · "No line is marked changed."
- **Target-size exception:** inline: the job link inside a gutter note relies on the code-well inline exception; the ✕ is 24px (44px below 700px).

**Keyboard**

- The band is not in the way: focus stays where the edit returned it (the renamed token, WCAG 2.4.3). Tab from that token reaches the band's links and Dismiss in document order; Shift+Tab returns.
- Esc while focus is inside the band dismisses it and returns focus to the changed token; elsewhere Esc keeps the one order in `keymap.json` `escapeOrder`.
- Enter on the job link goes to the dock record; Alt+↓ peeks it; Shift+F10 opens the one link menu (Open · Open beside · Peek; Reveal in Dock; Copy link · Copy job id).
- Enter on "Enter to decompile" decompiles the function from existing analysis, as a read.
- In the code well the gutter notes are part of their row, reachable with the well's own row navigation.

**Accessibility**

- The band is labelled by its header ("Before / after job c4d2, rename local, finished, read 14:03") and described by its footer. Each field reads "Name, local variable in ResourceRef::Resolve, build-a, changed. Before: local_8. After: itemCount." because the words are real text, not CSS.
- Nothing is announced on pending. The terminal message is announced once, in InlineRename's form: "Rename saved: local_8 is now itemCount on build-a, job c4d2." It never says "decompile updated". A failed job is announced once by the dock, and the band's text says what the program still holds. Nothing is assertive.
- Never color alone: before and after are markers plus words, changed tokens are bold, failed is ✕ plus the word, and the gutter mark has hidden and visible words.
- Text wraps; long signatures break inside the band rather than scrolling.
- Under reduced motion nothing changes, because nothing moves. Forced colors map the band frame and gutter bars to `CanvasText`.

**Removes switching** (counts from the plan ledger):

- J11 rename or retype a local seen in the decompiler: 6 → 0 (F2, type, Enter; U185).
- J12 edit a signature, calling convention or storage and verify the dependent views: 5 → 1, plus one per caller verified (Enter decompiles it; U185).
- J13 inspect and refine a type: 5 → 2 (U185; changing the structure still opens the type view).
