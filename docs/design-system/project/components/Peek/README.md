# Peek

A read-only look at any linked target without leaving the current view: a card beside the trigger, or an inline form under a code line. It can be kept as a card or opened beside as a Held pane.

**Use it** on every typed link (Linked views): address, symbol, callee, counterpart, fact, receipt, job, logical id, basis digest, locator cell, ladder run, pipeline node and XREF[n] hint. In a code well (Listing, DecompileView, HexStrip) Alt+↓ opens the inline form under the line; everywhere else it opens the card. Pointer rest always opens the card. Below 700px the narrow sheet is used; NarrowFlow owns that variant and this README does not restate it.

**Consumer provides** the target's kind and title; the concrete build and address when there is one; where the shown copy came from (fresh, reused or historical, with basis and read time); the cached content for that kind (table below); and the cache state: cached, not loaded or stale.

**Content by target type.** Every row is cache-only. Anything not already read says "Not loaded. Open to read it." (the Peek's Open button reads it) and is never fetched. Panes and panels say "Not loaded · Enter to load" instead; the Peek keeps its own words because it has an Open button.

| Target | The Peek shows |
|---|---|
| address, symbol, callee | up to `peek-lines-card` (6) cached lines in the card, `peek-lines-inline` (12) in the inline form, with "N of M"; the fact strip in words; identity or "no identity" |
| XREF[n] hint | the first 20 references at that build and address, then "n more · Open" |
| fact | the state word and glyph, its ProvenanceStamp, the receipt and job links, the job's StageChip |
| ◷ stale fact | the old and new basis, the dependency that changed, and the revalidation job or "Revalidation: none recorded" |
| ◇ gate wait | "waiting at gate ◇" with the gate text from the model and the age |
| ladder run | the methods tried, in order, and the terminal outcome; `observed_status` on its own line |
| counterpart | the identity-edge word (accepted or candidate), the divergence class (1↔1, 1↔N, ≠), and lines around an evidenced anchor only, with "aligned ≠ equivalent". A program that is not open says "Not loaded. Open build-c to read it." |
| receipt | what it covers, the fact it decided, the toolchain, "Produced by job ‹id›" and its StageChip |
| job | an "as of 14:02" snapshot of the dock's last read: the three readouts, the Targets line and the Changed line. It does not poll and announces nothing |
| name, type, slot, capability refusal | the winning name tier and the alternatives; the type layout; the slot on each build; the named refusal |
| locator cell | glyph and word per build; "contested · no winner" with both candidates as links |
| pipeline node | "From the pipeline design · model rev ‹8 hex›", the gate text, cached counts and the oldest wait |

- **Read-only by construction.** Pointer rest, focus rest and Alt+↓ read only evidence that is already loaded or stored: the peek cache, receipts, fact and locator rows, stored job records, `pipeline-model.json` and analysis already open in this session. A Peek never opens a program, decompiles, imports, matches, admits or starts a job, and nothing is prefetched.
- **Stale** content stays visible and labelled with `fact-stale` ◷, the word and what changed ("source changed from r14 to r15"). It is never refreshed silently and never shown without its ProvenanceStamp. After a job that changed a function's signature, storage or types, that function's cached decompile and its callers' read "◷ predates job ‹id›" here too; nothing is re-decompiled automatically, and Enter decompiles.
- **Stale responses never land.** Each read is keyed to its trigger and the selection generation. A response that arrives after the pointer or focus moved is discarded.
- **Nested Peeks** replace the content in place, with "‹ back" at the top. There is never a second card.
- Card: `dialog-bg`, 1px `line-control`, `shadow-popup`, square corners, `peek-w` wide. The kicker names the kind and build; the title is mono bold `ink-strong`. Code sits in a `code-bg` well with `shadow-inset`.
- Inline form: no shadow, `pane` fill, 1px `line` above and below and a 2px `line-control` rule at the inline start. It pushes the following lines down and never covers code.
- Facts appear as FactBadge words, locators as LocatorGlyph, identity as IdentityEdge. Never a score, bar or single verdict.
- **Footer, in this order.**
  - **Open** is Go: it moves the primary location and pushes one stop.
  - **Open beside** creates a Held pane; the primary location does not change and no stop is pushed. On 8080 without split panes the item reads "Open beside (new window)" and opens the same link in a new window.
  - **Keep** is an `aria-pressed` button with a constant name. Pressed, the card stays in the evidence rail labelled "Kept", carried as `keep=`. At most three cards are kept; a fourth Keep is refused with "Three cards kept; release one".
  - **Copy link**.
  Only Open changes the selection. Nothing in a Peek changes the inspected build.
- **Placement.** The card opens below the trigger, else above, and never covers the trigger or the focused element (WCAG 2.4.11). A `peek-gap` (4px) gap is bridged by an invisible hover zone so the pointer can move onto the card.
- **Narrow and short viewports.** Below 700px the Peek is NarrowFlow's sheet: at most `sheet-h` (64%) of the pane, non-modal, with a Full height button. Below `bp-short-h` (480px of viewport height) it opens as the full-height Inspect sheet. See NarrowFlow.
- No animation. It appears and disappears in place.
- Both surfaces read the same cached projection and show the same three states. The static 8080 surface may offer only the card; the full workspace adds the inline form.

**Linking**

- **Publishes:** nothing when it opens. Open publishes the primary location (Go, one history stop). Open beside publishes `hold=` (replaceState, no stop). Keep publishes `keep=` with the target's kind from the shared kind list, for example `keep=receipt:7c21@build-a` or `keep=peek:0041c880@build-a` (replaceState).
- **Follows:** its trigger, never the selection. A chord-opened Peek retargets to the newly focused link in the same list or grid after `peek-focus-rest`, until Esc. It is never held; Keep turns it into a card instead.
- **Targets rendered:** the links inside the card, each per the typed-link table: address and symbol → Code Browser at that build · counterpart → Code Browser for that build, with its edge word · fact and receipt → the receipt card · job → the dock Jobs record · basis → the ProvenanceStamp detail · pipeline node → the PipelineMap node · ladder evidence. Every link keeps the one grammar.
- **Peek source:** the peek cache, stored receipts, fact and locator rows, stored job records as of the dock's last read, the served `pipeline-model.json`, and analysis already open in this session.
- **Absent copy:** "Not loaded. Open to read it." · "absent" and "unresolved" as plain words · "ambiguous" or "contested · no winner" with a ladder link and both candidates · "no identity" · "Revalidation: none recorded".
- **Target-size exception:** none. Footer buttons are 28px and Close is 24px; 44px below 700px and with a coarse pointer.

**Keyboard**

- **Alt+↓** (Option+↓ on macOS) opens a Peek at once on the focused link, cell or node. It is a modifier chord, so Space, x, j/k and plain arrows keep their list and grid meaning. It does nothing in text fields; in an open go-to list it peeks the highlighted result. Alt+Enter and Ctrl/Cmd+I are rejected (35).
- It also opens after a `peek-pointer-rest` (400ms) pointer rest on a link token or whole-strip button, and after a `peek-focus-rest` (800ms) focus rest. Focus-rest opening is off by default at 400% zoom and below 700px. Pointer rest can be turned off with "Peek on hover" in View settings. Moving focus quickly through a list opens nothing.
- **Tab** from the trigger moves into the Peek's first action. Shift+Tab returns to the trigger. Tab past the last action continues to the element after the trigger.
- **Enter** on Open (or on the trigger) goes. **Shift+Enter** opens beside, from the trigger or from inside the Peek. **Shift+K** keeps, only while focus is inside the Peek; from the trigger, Tab, then Shift+K, or the link menu. Ctrl/Cmd+Enter on a trigger keeps the browser's new-tab behaviour.
- **Esc** follows the one Esc order in the Keymap section (`keymap.json` `escapeOrder`); an open Peek is its second layer, after any modal. Focus stays on, or returns to, the trigger.
- Shift+F10, the context-menu key or right-click on a trigger opens the one link menu (Linked views). With a coarse pointer, Peek is an item in the row's 44px row-menu button.

**Accessibility**

- WCAG 1.4.13: dismissable with Esc without moving the pointer; hoverable; persistent until Esc, until focus leaves both trigger and card, or until the pointer has left both for `peek-grace` (300ms). There is no timeout. It opens on focus as well as hover.
- WCAG 3.2.1: opening never moves focus, changes the selection, switches the build or navigates. Only Open, Open beside and Keep act, and only when activated.
- The card is a non-modal `role="dialog"` named by its title. `aria-expanded` and `aria-controls` are present on the trigger only while its Peek is open. `aria-keyshortcuts="Alt+ArrowDown"` is set once on the well or grid, not on every token. Close is a 24px button named "Close peek".
- Opening adds no live-region message: the trigger's expanded state is the cue, and Tab reaches the card.
- The card never covers its trigger or the focused element (2.4.11), and it never holds the only copy of anything: Open reaches the same content.
- Every action is at least 24×24px (2.5.8); 44px below 700px and with a coarse pointer.
- Identifiers carry `translate="no"`; glyphs are `aria-hidden` beside their words.

**Removes switching:** J35 (a stale fact) goes from 3 switches to 0 through the stale Peek, or to 1 when the dependency change is not recorded or not cached. The ledger credits it to U174. The Peek also supplies the reads for J01, J02, J06, J09, J13, J18 and J33, which the ledger credits to their own units.

**Parity extensions (2026-09-29)**

Rows from the [Ghidra Code Browser parity specification](../../../../dashboard-design/2026-09-29-ghidra-code-browser-parity.md): L27, L28, T16, I03, P12.

- **Instruction info (L27).** Alt+↓ on a mnemonic in the Listing opens an instruction card: the build's language id, the instruction prototype, operand objects with their kinds, inputs and outputs (registers and memory), and the raw bytes. It is cache-only like every Peek; until a catalog read action returns instruction info, it reads "Instruction info not loaded. Open to read it." It never re-disassembles.
- **Speculative disassembly (L28).** On a data or undefined cursor, **Disassemble here (preview)** in the link menu opens an inline Peek of instructions decoded at that address with the build's language, drawn in a dashed frame, labelled "hypothesis", with its basis ("decoded at 0041b210 with build-c's language · not committed"). It never commits code. Committing is **Disassemble…** (a catalog action) through the ActionStrip, which admits a job.
- **Type at address (T16).** **Preview type here…** in the link menu takes a type (CacheEntry) and shows its fields laid over the bytes at the address (name_len, flags, next with values), dashed and labelled "hypothesis · not applied". **On every build** repeats the preview at each counterpart address reached through anchors, one block per build; a size or alignment that does not fit reads "does not fit on build-d: 12 of 16 bytes defined". Applying the type is TypeEditor or the ActionStrip, never the Peek.
- **Checksums (I03).** The checksum card that HexStrip's selection opens is a Peek kind: algorithm rows, range, build, and the per-build rows when requested. It is read-only and keepable.
- **Program properties (P12).** On an address, **Properties** lists the program's property maps that hold a value there (name, value, build). It is cache-only; "no properties at 0041b210 on build-c" when empty; "Property maps not loaded" until read.
- The preview is unchanged; these are new content kinds in the existing card and inline forms, with the same Keep, Open beside and cache rules.
