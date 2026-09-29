# HeldPane

The header treatment and rules for any held pane or kept evidence card, meaning anything frozen to one target instead of following the selection. It shows the word "Held" or "Kept", what it holds, its age and basis, and a "Current differs" notice when the live value has changed. Its actions are Make primary, Follow again and Release. A held pane never presents historical data as current.

**Use it** on every secondary pane that stops following: a SplitCompare pane after Hold, a pane opened beside and then held, a kept Peek or evidence card in the evidence rail, and a kept XrefPanel. "Held" names panes. "Kept" names cards. Both are reserved words, distinct from the locator word `pinned` and the ownership word `lock`.

**Consumer provides** the held target (kind, logical entity, concrete build, address, view), the basis token and read time of the held content, its ProvenanceStamp, and a change signal from the store: whether the held target's basis has moved, a one-line summary of what differs now, and whether the target still resolves (identity edge state). It also provides the held pane's own history stack.

- **Frame and word, never color.** A held pane or kept card has a 2px `ink-strong` frame. Its header starts with the tag `HELD` (broken-chain icon) or `KEPT` (keep icon) in `ink-strong` bold uppercase, followed by what it holds in `type-ui`: "Held · build-c · 4 min ago". A following pane has a 1px `line` frame and says "Follows selection" with the chain icon. A derived pane says "Counterpart of #88 · derived". The accent is not used.
- **What it holds.** The meta line gives the view, entity name and logical id, the address link, "read 13:54", the basis link, and "unchanged" once the store confirms no change. The age counts from the read time ("4 min ago"). It is a plain age, never a countdown, and it updates without announcements.
- **It never refreshes by itself** and never switches its target build. The pane keeps its entity, build, address and view until an explicit action.
- **Current differs.** When the held target's basis moves, a notice appears under the header on `chassis` with the `fact-stale` ◷ glyph: "**Current differs.** Basis changed since held: 9f3c…a1e0 → b71e…04c2 (build-c gen 17 → 18, 14:03)", followed by one line on what differs now and "This pane still shows the listing as read at 13:54." The held content's ProvenanceStamp switches to `historical` (dashed) with "not current". The notice offers **Refresh**, which re-reads the same target at the current basis and stays held, and **Compare with current**, which opens a text diff of held against current.
- **The target no longer resolves.** If the held counterpart stops being the entity's counterpart (edge rejected, locator now unresolved or contested), the notice says so with the IdentityEdge word and the job that decided it. The content stays, labelled historical, and "claims nothing about build-b now". It is never relabelled as the new counterpart.
- **Actions**, in order, as 24px buttons: the pane's own Back and Forward (◂ ▸), **Make primary**, **Follow again** and **Release**.
  - **Make primary** moves the one selection to the held target, with one history stop. A build switch is stated in the button's description and announced after it. The held pane then closes, because the primary pane now shows its target.
  - **Follow again** turns the pane back into a following or derived pane, showing the current selection's counterpart on the same build.
  - **Release** closes the pane or removes the card, and returns focus to the primary pane.
  - None of them asks for confirmation, because none mutates evidence.
- **Read-only.** A held pane and a kept card carry no mutation verbs. A footer line on held panes says "Read-only. Actions apply to the primary selection, build-a 0041d0a0." The ActionStrip always binds the primary selection.
- **Limits.** There are at most two center panes (primary plus one secondary; SplitCompare's third column lives only in Compare). A further Hold becomes a kept evidence card in the rail. Kept cards stack in the rail in the order they were kept.
- **Card form.** A kept card uses the same frame, tag, meta, notice and stamp at `evidence-w` (260px). The header wraps and actions go to their own line.
- **Both surfaces** render the same frame, words and notices from the same change signal. The static 8080 surface may drop the pane's own Back and Forward, but never the Held word, the age or Current differs.

**Linking**

- Publishes `hold` (repeatable, `kind:id@build`, for example `hold=fn:00082f40@build-c`) for held panes, and `hold=card:…` for kept cards, as in the keymap's `link.keep`. Holding, releasing and following again use replaceState. Make primary uses pushState.
- Follows nothing. It listens only for its own target's basis and edge changes.
- Renders the held address (Code Browser for that build), the logical id (CounterpartMatrix), the basis ids (ProvenanceStamp detail and what changed since), the deciding job (dock Jobs record) and receipts (receipt card).
- If the held target is gone, the pane keeps its address link, which is still a real place, and states in words that it is no longer the counterpart. It never links to a guessed replacement.
- Opening a URL whose `hold` basis has since moved shows current data in the primary pane and marks the held pane stale with Current differs.

**Keyboard**

- The header actions are in Tab order after the tag. Enter or Space activates them. Shift+F10 on the header opens the same actions plus Copy link.
- Inside a held pane, Enter on a link follows it within the pane (same build, recorded in the pane's own history). Alt+←/Alt+→ step that history while focus is inside the pane, and anywhere else they are the app's Back and Forward. Shift+Enter opens the link beside, Alt+↓ peeks, Ctrl/Cmd+Enter opens a browser tab. Make primary is the only way a held pane moves the one selection.
- **K** (`link.keep`, region scope) keeps the focused Peek or evidence card; on a kept card it releases it. The key is focus-scoped and can be remapped.
- Esc moves focus from the held pane back to the primary pane. It never releases.

**Accessibility**

- A held pane is a `section` whose name starts with the word: "Held · build-c · 4 min ago". `aria-describedby` points to the read-only sentence. The broken-chain and keep icons are `aria-hidden`, and the word is visible.
- The Current differs notice is `role="status"` and is announced once when it appears ("Held pane build-c: current differs"). It is not announced again until the basis moves again. Its glyph is `aria-hidden` next to the word.
- The held content grid is named with its read time and state ("Held listing, build-c, historical, as read at 13:54"), so assistive technology never hears it as current.
- Make primary describes its effect ("Moves the one selection to ResourceRef::Resolve on build-c. The inspected build changes to build-c.") before activation (WCAG 3.2.2). Nothing in a held pane acts on focus (WCAG 3.2.1).
- WCAG 2.5.8: actions are 24px, and 44px below 700px (history buttons 44 by 44). WCAG 1.4.13 does not apply, because a held pane is not hover content; kept cards are persistent until Release.
- `forced-colors`: the frame maps to `CanvasText`. The word "Held" or "Kept" still carries the state.

**Removes switching:**

- Keep a reference function in view while navigating elsewhere. Before: a second browser window, or Back and Forward round trips, 2 switches per look. After: Hold, 0 switches.
- Notice that held evidence went stale. Before: nothing says so; reopen the target to check, 1 or 2 switches, and risk reading old data as current. After: Current differs in place, 0 switches.
- Return to what was held as the main target. Before: the go-to field or Compare workspace to find it again, 1 switch plus search. After: Make primary, 0 switches.
- Hold a receipt or fact while reviewing others. Before: the Evidence workspace in a separate tab, 1 switch per look. After: a kept card in the rail, 0 switches.
