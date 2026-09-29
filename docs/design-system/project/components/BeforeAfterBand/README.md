# BeforeAfterBand

The in-place strip that appears over the changed lines once an edit's job reaches its terminal result: old → new name, type, signature or storage as read back from the program, labelled with the words "before" and "after", the job link, and a "changed by job a3f9" gutter note on each changed line, dismissible.

**Use it** in DecompileView, Listing, the signature line and StorageEditor after a catalog edit (rename, retype, edit signature, edit storage, apply type) submitted from where the operator reads: F2, the token menu or the ActionStrip. It is the SourceRepairDiff idea at field size: the operator sees what changed without opening the Jobs dock or re-reading the function by eye.

**Consumer provides** the job id, verb and lifecycle state; the target (entity, function, concrete build, field kind and which variable, parameter or field); the value before the edit (the value the edit was bound to at submission); after the terminal result, the value from a fresh re-read of the program, with the read time and analysis generation; the request, when the re-read differs from it; and the lines whose text changed in the re-read, for the gutter.

- **After comes only from a re-read.** Until the job's terminal result arrives and the dependent views re-read, the band shows **before** and "after: pending · read after the job ends; nothing is predicted" in a dashed frame. It never paints the requested value as if it were applied. If the re-read differs from the request, the band shows the re-read and says so ("Requested itemCount; the function already had one").
- **Words, not color.** Each field is a `<dl>` group: the field kind as `dt` ("Name · local variable in ResourceRef::Resolve · build-a", "Storage · parameter 1", "Signature", "Return"), then a **before** line and an **after** line, each starting with that word in `type-kicker` `ink-muted`. Before values are mono `ink-muted`; after values are mono `ink-strong`; the tokens that changed are bold with a `fact-stale` underline (like the diff `mark`). No red or green fills.
- Band: `pane` fill, 1px `line`, a 2px `ink-strong` inline-start rule (dashed when the job failed), inserted in the flow between lines like an inline Peek. It pushes the following lines down and never covers code. In a grid-based well it is its own row with one cell spanning every column, so the grid stays valid.
- Header: kicker "Before and after", the verb and the job link with its state ("Rename local · job a3f9 · finished"), the ProvenanceStamp of the re-read ("fresh · re-read 14:02:11 · decompile gen 43") and a 24px ✕ named "Dismiss before and after for job a3f9". Fields lay out in columns of at least 260px and stack in the rail.
- Footer: how many lines changed and the gutter rule, or the job's own failure ("Worker exited 1. No line is marked changed."). A failed or refused job shows the re-read as unchanged ("local_8 · unchanged"); a stale refusal says what changed since the edit was bound.
- **Gutter**: every line whose text changed in the re-read carries a 3px `ink-strong` gutter bar and, on the first line of each changed run, the note "✎ changed by job a3f9" (✎ `aria-hidden`, the job id a link) in `ink-muted` at the line end, the same mark InlineRename leaves. Each marked line also carries the hidden words "changed by job a3f9". Marks stay until the next navigation (a Go that leaves the function), survive dismissing the band, and are never animated.
- **Scope** is one concrete build: the band says the build, and the footer says when other builds are unaffected ("this edit is scoped to build-a"). Propagation to other builds is separate work with its own receipts.
- Naming hints follow the project conventions (camelCase locals and parameters, PascalCase types, snake_case fields, COBRA_CASE enum constants) in the edit field, never here: the band shows what the program now holds.
- Both surfaces show the band from the same job record and re-read; the static 8080 surface may render it above the well instead of between lines, with the same words.

**Linking**

- **Publishes:** nothing. Dismiss changes only this band; it never moves the primary location, holds or keeps, and never touches history.
- **Follows:** the function and build it was raised in. It appears only when the job's terminal result has arrived and the re-read has landed; leaving the function (a Go) removes the band and the gutter marks. Not holdable.
- **Targets rendered:** job id → the dock Jobs record (it does not move the primary location) · the re-read's basis → the ProvenanceStamp detail · the function and build in the field label as text. Link names read "Job a3f9, rename, finished".
- **Peek source:** Alt+↓ on the job id reads the stored job record as a read-only ActivityRecord; Shift+K inside the Peek keeps it. The band itself reads only the re-read the host already made.
- **Absent copy:** "pending · read after the job ends; nothing is predicted" · "none" (a value that did not exist before) · "unchanged" (the re-read shows no change) · "No line is marked changed."
- **Target-size exception:** inline: the job link inside a gutter note relies on the inline exception; the ✕ is 24px (44px below 700px).

**Keyboard**

- The band is not in the way: focus stays where the edit returned it (the renamed token, WCAG 2.4.3). Tab from that token reaches the band's links and Dismiss in document order; Shift+Tab returns.
- Esc while focus is inside the band dismisses it and returns focus to the changed token; outside the band, Esc keeps its usual order (Peek, menu, typed filter).
- Enter on the job link goes to the dock record; Alt+↓ peeks it; Shift+F10 opens the link menu (Open, Open beside, Peek; Reveal in Dock; Copy link, Copy job id).
- In the code well the gutter notes are part of their row, reachable with the well's own row navigation.

**Accessibility**

- The band is labelled by its header ("Before and after, Rename local, job a3f9, finished") and described by its footer. Each field reads "Name, local variable in ResourceRef::Resolve, build-a. Before: local_8. After: itemCount." because the words are real text, not CSS.
- One polite announcement when the re-read lands: "Renamed local_8 to itemCount; decompile updated." Pending is announced once ("Rename pending"). A failed job is announced once by the dock ("Job c7d2 failed"), and the band's text says what the program still holds. Nothing is assertive.
- Never color alone: before and after are words, changed tokens are bold and underlined, failed is ✕ plus the word plus a dashed rule, and the gutter mark has hidden and visible words.
- ✕ is a 24px target, 44px below 700px. Text wraps; long signatures break inside the band rather than scrolling.
- Under reduced motion nothing changes, because nothing moves: the band and marks appear only when the re-read arrives.
- Forced colors map the band frame and gutter bars to `CanvasText`.

**Removes switching:** J11, rename a local seen in the decompiler, goes from 6 switches to 2 (F2, type, Enter, confirm; the result is read in place). J12, edit a signature or storage and verify the dependent views, goes from 5 to 2: the Jobs-dock trip and the manual re-read are replaced by the band and the gutter marks. J13, apply or refine a type, goes from 5 to 2 with the type Peek and the band.
