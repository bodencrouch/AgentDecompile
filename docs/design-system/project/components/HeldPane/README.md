# HeldPane

The header treatment and rules for any held pane or kept evidence card, meaning anything frozen to one target instead of following the selection. It shows the word "Held" or "Kept", what it holds, its read time and basis, and "◷ Basis changed since held · Refresh" when the basis has moved. Its actions are Make primary, Follow again and Release. A held pane never presents historical data as current. It implements 35 Follow and hold and points there rather than restating it.

**Use it** on every center or secondary pane that stops following: a pane created by Open beside (Shift+Enter), a SplitCompare pane after Hold this pane, a held GraphPane; and, as the card form, on a kept Peek or evidence card in the evidence rail and a kept References section. "Held" names panes. "Kept" names cards. Both are reserved words, distinct from the locator word `pinned` and the ownership word `lock`.

**Consumer provides** the held target (kind, logical entity, concrete build, address, view), the basis token and read time of the held content (or that none was recorded), its ProvenanceStamp, and a change signal from the store: whether the held target's basis has moved, a one-line summary of what differs now, and whether the target still resolves (identity edge state and locator word). It also provides the held pane's own history stack.

- **The toggle.** A pane header has **Hold this pane** (`aria-pressed`), a constant name. The state words beside it read "Following · sync A" or "Held · ResourceRef::Resolve @ build-c · 4 min". Pressing it again is Follow again. A card has **Keep** (`aria-pressed`) instead; Shift+K works only while focus is inside the Peek or card, never in lists where j/k move.
- **Frame and word, never color.** A held pane or kept card has a 2px `ink-strong` frame. Its header starts with the tag `HELD` (broken-chain icon in `ink-strong`) or `KEPT` (keep icon) in `ink-strong` bold uppercase, followed by what it holds: "Held · ResourceRef::Resolve @ build-c · 4 min". The header is sticky, so the tag stays visible at every scroll position; the 2px frame alone also means other things (fresh evidence, the current step), so the word is required. A following pane has a 1px `line` frame and says "Follows selection". A derived pane says "Counterpart of #88 · derived". The accent is not used.
- **What it holds.** The meta line gives the view, entity name and logical id, the address link, "Held · read 13:54", the basis link, and "unchanged" only once the store confirms no change. The age counts from the read time ("4 min"). It is a plain age, never a countdown, and it updates without announcements.
- **It never refreshes by itself** and never switches its target build. The pane keeps its entity, build, address and view until an explicit action. Back and Forward (the app's history) never open, close or re-point a hold; the URL is rewritten to the current holds with replaceState.
- **Basis changed.** When the held target's basis moves, a notice appears under the header on `chassis` with the `fact-stale` ◷ glyph: "◷ Basis changed since held · Refresh", then "9f3c…a1e0 → b71e…04c2 (build-c gen 17 → 18, 14:03)", one line on what differs now, and "This pane still shows the listing as read at 13:54." The held content's ProvenanceStamp switches to `historical` (dashed) with "not current". **Refresh** re-reads the same target at the current basis and stays held; **Compare with current** opens a text diff of held against current. A kept card reads "◷ Basis changed since kept · Refresh". A hold without a basis token reads "Basis at hold time not recorded" and is never marked unchanged by assumption.
- **The target no longer resolves.** If the held counterpart stops being the entity's counterpart (edge rejected, locator now unresolved or contested), the notice says so with the IdentityEdge word and the job that decided it. The content stays, labelled historical, and "claims nothing about build-b now". It is never relabelled as the new counterpart.
- **Actions**, in order, as 24px buttons: the pane's own Back and Forward (◂ ▸), which never touch browser history; **Hold this pane**; **Make primary**; **Follow again**; **Release**.
  - **Make primary** (Enter on the Held chip, or the button) moves the one selection to the held location, pushes one history stop and releases the hold. A build switch is stated in the button's description and announced after it. The pane stays open and becomes Following; a held pane never closes by itself.
  - **Make primary on a contested candidate** carries "contested candidate 1 of 2 · no winner" onto the primary header. Entity-scoped catalog verbs (propagation, cross-place) are `aria-disabled` there with that reason; address-scoped reads stay available.
  - **Follow again** turns the pane back into a following or derived pane, showing the current selection's counterpart on the same build.
  - **Release** closes the pane or removes the card, and returns focus to the primary pane.
  - None of them asks for confirmation, because none mutates evidence.
- **Enter inside.** Inside a held pane, Enter on a link moves that pane (same build, recorded in the pane's own history). On a kept card, Enter on a link goes. Each container's footer says which.
- **Read-only.** A held pane and a kept card carry no mutation verbs. A footer line on held panes says "Read-only. Actions apply to the primary selection, build-a 0041d0a0." The ActionStrip always binds the primary selection.
- **Limits.** The Code Browser has at most two center panes; the Compare workspace may show a three-way split as its one secondary area. A further hold becomes a kept card with the notice "Two center panes in use; kept as a card in Evidence". At most three cards are kept; a fourth Keep is refused with "Three cards kept; release one", and nothing is evicted.
- **Card form.** A kept card uses the same frame, tag, meta, notice and stamp at `evidence-w` (260px). The header wraps and actions go to their own line.
- **Both surfaces** render the same frame, words and notices from the same change signal. The static 8080 surface shows holds as Held entries in the evidence rail and may drop the pane's own Back and Forward, but never the Held word, the age or the basis notice.

**Linking**

- **Publishes:** `hold=kind:id@build[:addr][~basis]` for held panes (at most two, for example `hold=fn:00082f40@build-c:00082f40~9f3c`) and `keep=kind:id[@build][~basis]` for kept cards (at most three). `hold` and `keep` share one kind list in `location-schema.json` (symbol, fn, addr, entity, entitybuild, receipt, fact, job, ladder, xref, calls, graph, peek, names, runtime, objective, failure, node). Holding, keeping, releasing and following again use replaceState; Make primary pushes one stop.
- **Follows:** nothing. It listens only for its own target's basis and edge changes.
- **Targets rendered:** the held address (the Code Browser for that build) · the logical id (Compare with the CounterpartMatrix) · the basis ids (ProvenanceStamp detail and what changed since) · the deciding job (dock Jobs record) · receipts (receipt card).
- **Peek source:** the held content itself, as read; a Peek inside a held pane reads the peek cache for that build only.
- **Absent copy:** "Basis at hold time not recorded" · "claims nothing about build-b now" (the target no longer resolves; the address link stays, as a real place, and no replacement is guessed) · "Two center panes in use; kept as a card in Evidence" · "Three cards kept; release one".
- **Target-size exception:** none; actions are 24px, 44px below 700px (history buttons 44 by 44).

**Keyboard**

- The header actions are in Tab order after the tag. Enter or Space activates them. Shift+F10 on the header opens the same actions plus Copy link.
- Inside a held pane, Enter on a link moves the pane. The pane's ◂ ▸ buttons step its own history. Alt+←/Alt+→ always act on the primary history. Shift+Enter opens the link beside (within the limit), Alt+↓ peeks, Ctrl/Cmd+Enter opens a browser tab.
- **Shift+K** (`link.keep`) toggles Keep only while focus is inside a Peek or kept card; it is remappable. From a trigger the path is Tab then K, or the menu.
- Esc follows the one order in `keymap.json` `escapeOrder`: in a held pane it returns focus to the primary pane. Esc never releases a hold or removes a kept card.

**Accessibility**

- A held pane is a `section` whose name starts with the word: "Held · ResourceRef::Resolve @ build-c · 4 min". `aria-describedby` points to the read-only sentence. The broken-chain and keep icons are `aria-hidden`, and the word is visible.
- The basis notice is `role="status"` and is announced once when it appears ("Held pane build-c: basis changed since held"). It is not announced again until the basis moves again. Its glyph is `aria-hidden` next to the words.
- The held content grid is named with its state and read time ("Listing, build-c, ResourceRef::Resolve, held, as read 13:54"), so assistive technology never hears it as current.
- Make primary describes its effect before activation (WCAG 3.2.2). Nothing in a held pane acts on focus (WCAG 3.2.1).
- The held frame is one of several 2px `ink-strong` uses (90: fresh evidence, the current step, the running unit), so the word carries the state. WCAG 1.4.13 does not apply, because a held pane is not hover content; kept cards are persistent until Release.
- `forced-colors`: the frame maps to `CanvasText`. The word "Held" or "Kept" still carries the state.

**Removes switching:** held panes and kept cards contribute to J01, J07 and J20 (a reference kept in view while navigating, a held review pair, a work-view event opened beside); their counts are credited to U175, U186 and U180 in the plan ledger, which is authoritative.
