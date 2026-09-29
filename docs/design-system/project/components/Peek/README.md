# Peek

A read-only look at any linked entity without leaving the current view: a hover or focus card, or an inline peek under a code line, that can be kept or promoted to a split pane.

**Use it** on every link that names an entity: address, symbol, counterpart, fact cell, receipt, job, logical id, locator cell and pipeline node. In the Listing and Decompile the chord opens the inline form under the line; everywhere else it opens the card. Hover and focus-rest always open the card.

**Consumer provides** the entity kind and title; the concrete build and address when there is one; where the shown copy came from (fresh, reused or historical, with basis and read time); the facts, locator or identity edge that matter for that kind; up to six cached code lines with "N of M"; and the cache state: cached, not loaded or stale.

- **Read-only by construction.** Hover, focus, prefetch and the chord read only evidence that is already loaded or stored: the peek cache, receipts, fact and locator rows, and analysis already open in this session. A peek never opens a program, decompiles, imports, matches, admits or starts a job.
- **Not loaded** is an answer, not a fetch: `fact-unknown` ○ with "Not loaded. Open to read it." and why (for example, the build's program is not open).
- **Stale** content stays visible and labelled: a `fact-stale` ◷ note with the word "Stale" and what changed ("source changed from r14 to r15"). It is never refreshed silently and never shown without its ProvenanceStamp.
- **Stale responses never land.** Each read is keyed to its trigger and the selection generation. A response that arrives after the pointer or focus moved is discarded; it never fills another trigger's card.
- Card: `dialog-bg`, 1px `line-control`, `shadow-popup`, square corners, at most 440px wide. Kicker names the kind and build; the title is mono bold `ink-strong`. Code sits in a `code-bg` well with `shadow-inset`: addresses `address`, mnemonics `ink-strong`, symbols `lane-identity-ink`.
- Inline form: no shadow, `pane` fill, 1px `line` above and below and a 2px `line-control` rule at the inline start. It pushes the following lines down; it never covers code.
- Facts appear as FactBadge words, locators as LocatorGlyph, identity as IdentityEdge. Never a score, bar or single verdict.
- Actions, in this order. **Open** makes the entity the selection and pushes history. **Open to the side** promotes the peek to a split pane that is unlinked from the selection and read-only; the primary selection and the inspected build do not change. **Keep** (`aria-pressed`, key K) keeps the card in the evidence rail's Kept list, labelled "Kept"; it survives selection changes and is carried in the link as `hold=card:…`. (The word "pinned" is reserved for the locator status.) Only Open changes the selection, and nothing in a peek changes the inspected build.
- Placement: below the trigger, else above, never over it. A 4px gap is bridged by an invisible hover zone so the pointer can travel into the card.
- No animation. It appears and disappears in place.
- Both surfaces read the same cached projection and show the same three states. The static 8080 surface may offer only the card; the full workspace adds the inline form. Where a surface has no split panes, Open to the side opens the same deep link in a new window.

**Keyboard**

- Opens after pointer rest (400 ms) or focus rest (800 ms). Both delays are Keyboard settings, and focus-open can be turned off. Moving focus quickly through a list opens nothing.
- **Alt+↓** (Option+↓ on macOS) opens it at once on the focused link, cell or node. It is a modifier chord, so Space, x, j/k and plain arrows keep their list and grid meaning. Ctrl+I is not used because Firefox binds it to Page Info. The chord does nothing in text fields; in an open go-to list it peeks the highlighted result.
- While a chord-opened peek is showing, moving focus within the same list or grid retargets it after the focus-rest delay, until Esc.
- **Tab** from the trigger moves into the peek's first action. Shift+Tab returns to the trigger. Tab past the last action continues to the element after the trigger.
- **Esc** closes and leaves focus on the trigger, or returns it there. A second Esc goes to the surface underneath.
- **Enter** on Open (or on the trigger) opens. **Shift+Enter** opens the target to the side, from the trigger or from inside the peek. Ctrl/Cmd+Enter on a trigger keeps the browser's own new-tab behavior.
- Shift+F10 or the context menu on any trigger lists Peek, Open, Open to the side, Keep and Copy link.

**Accessibility**

- WCAG 1.4.13: dismissable with Esc without moving the pointer, hoverable, and persistent until Esc, until focus leaves both trigger and card, or until the pointer leaves both. No timeout. It opens on focus as well as hover.
- WCAG 3.2.1: opening on focus never moves focus, changes the selection, switches the build or navigates. Only Open, Open to the side and Keep act, and only when activated.
- The card is a non-modal `role="dialog"` named by its title. The trigger carries `aria-expanded`, `aria-controls` and `aria-keyshortcuts="Alt+ArrowDown"`. Close is a 24px button named "Close peek". Every action is at least 24×24px (WCAG 2.5.8); 44px below 700px.
- A chord-opened peek is announced once in the polite region: "Peek: ‹title›, ‹provenance›. Tab to read." Hover and focus-rest opens announce nothing (WCAG 4.1.3 without chatter).
- The card never covers its trigger or the focused element (WCAG 2.4.11), and it never holds the only copy of anything: Open reaches the same content.
- Identifiers carry `translate="no"`; glyphs are `aria-hidden` next to their words.

**Removes switching:** opening the Functions list, Evidence workspace, Compare workspace or Jobs dock just to read a target's facts, counterparts, receipt or first instructions, and then pressing Back.
