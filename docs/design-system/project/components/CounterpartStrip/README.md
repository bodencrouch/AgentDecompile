# CounterpartStrip

A one-row strip under the view title that shows the current logical entity's counterpart on every build: build name, address link, locator glyph and word, divergence class and identity-edge state. Each counterpart is a typed link.

**Use it** directly under the title of the Listing, Decompile and Hex views and of the evidence rail's entity header. It shows one entity, the primary selection, and follows it. It replaces opening the Compare workspace to learn where else the entity exists.

**Consumer provides** the logical entity (id and name) and the build count. For every build in the related-build scope, in corpus order: the build name, and either the counterpart address or the absence; the locator status and its word (resolved(member), pinned(member) with `module_rva` or `section_offset`, degraded, ambiguous with its candidates, unresolved, contested with both addresses); the divergence class (1↔1, 1↔N, ≠); the identity-edge state (accepted, candidate, rejected, unresolved or none); and whether that counterpart is open beside. It also provides the source and read time of the stored cross-build index.

- **Every build appears, in corpus order, including the inspected one.** The inspected build keeps its place, so cells never reorder when the build switches. It takes the selection shape: `selection` fill, a 3px `accent` bar, `aria-current="location"` and the words "inspected build".
- **Each cell has two lines.** Line 1: the LocatorGlyph (`ink-strong` ●, `address` ◎, `fact-stale` ◑ and ⋯, `fact-unknown` ◌, `fact-failed` ⇉), the build name underlined as the link text, and the address in `address` mono. Line 2, at 11px in `ink-muted`: the locator word, the divergence notation in bold mono `ink-strong`, and the IdentityEdge mini line with its word. Cells are 36px tall on `pane` with a 1px `line` frame, so the strip stays a single row at normal center widths.
- **Absent builds stay visibly absent.** An absent cell has a dashed `line-control` frame on `chassis`, no address, the italic word "absent", the locator word and "no edge". It is a button that opens the reason (a Peek: ladder outcome, members tried, a link to the ladder receipt, and "Open beside as an absent pane"). It is never a link to a guess.
- **Ambiguous and contested never pick.** The cell says "2 candidates" or "2 addresses" and opens a menu that lists every candidate as a link with its channel and margin. The footer says "Opening one does not accept it."
- **Open beside** marks the cell with a `beside` tag while that counterpart is shown in SplitCompare.
- **No identity** is an answer: "∅ FUN_0041c880 has no identity. No counterpart is claimed on any build." Nothing is inferred from names or addresses.
- **Follows, never fetches.** The strip reads the stored cross-build index and receipts only. When the selection moves, the previous cells dim (`opacity-disabled`, `inert`) behind "… Loading counterparts of ‹name›" after the 200ms settle. A late response for an old selection is dropped. A counterpart whose program is not open still shows its locator; its Peek says "Not loaded. Open to read it."
- **Layout.** A leading label (`type-kicker` "Counterparts" over the logical-id link "#88 · 4 builds" and the index read time "13:41" in mono `ink-muted`), then the cells. The row wraps and never scrolls sideways. The full workspace may fold trailing cells into "+N more" when the row is full; the label on that button counts what it hides by state ("+2: 1 resolved, 1 absent"), so an absent build is never hidden silently.
- **Both surfaces** render the same cells from the same index read. The static 8080 surface may omit the `beside` tag, but never an absent cell or a word.

**Linking**

- Publishes nothing on its own. Enter publishes a new `b` and `a` with the same `e` (pushState). Shift+Enter publishes `sp`.
- Follows the primary location's `e` (logical entity) and marks `b` (inspected build) as current.
- Renders counterpart links (Code Browser for that build, same entity), the logical id (Compare with the CounterpartMatrix), and receipt links inside the absent-reason Peek.
- An absent target is a button labelled with the word "absent" and its reason. Unresolved, contested and ambiguous targets are never links to one guessed address.

**Keyboard**

- The cells form an APG Toolbar with one tab stop. Tab enters on the last focused cell, or on the inspected build. ←/→ move between cells, Home/End go to the first and last cell, and Tab leaves the strip. The logical-id link is a separate tab stop before the toolbar.
- **Enter** on a counterpart goes there: the inspected build switches to that build and the entity is kept. The switch is announced ("Inspected build: build-b. ResourceRef::Resolve at 0041b2c0."), and Back returns. Enter on the inspected cell does nothing.
- **Alt+↓** peeks the counterpart read-only (facts, locator, first cached lines). On an absent cell it shows the reason.
- **Shift+Enter** opens the counterpart in SplitCompare beside the current pane. The primary selection and inspected build do not change. On an absent cell it opens an absent pane with the reason.
- **Ctrl/Cmd+Enter** opens the counterpart's URL in a browser tab (links only). **Shift+F10** opens Reveal in (Code Browser · Compare · Evidence · Navigator · Dock) with Peek, Open beside and Copy link.
- **Alt+PageDown / Alt+PageUp** (`build.next`, `build.prev`), anywhere in the center region, go to the next or previous build that has a counterpart. This is the same as arrowing to that cell and pressing Enter. Absent builds are skipped, and they stay visible in the strip.
- The `g` leader's "g c counterparts" hint moves focus into the strip at the inspected cell.
- On an ambiguous or contested cell, Enter, Space or ↓ opens the candidate menu (APG Menu Button). Inside it, ↑/↓ move, Enter goes, Shift+Enter opens beside, Alt+↓ peeks and Esc returns to the cell.

**Accessibility**

- `role="toolbar"` labelled "Counterparts" and described by a hidden sentence naming the keys. Each cell's accessible name is a full sentence with type, target and state: "Counterpart on build-b, address 0041b2c0, resolved, one to one, identity edge accepted". Glyphs and the edge line are `aria-hidden`, and their words are visible. `aria-keyshortcuts` lists Enter, Shift+Enter and Alt+ArrowDown.
- The inspected cell carries `aria-current="location"`. Absent and multi-candidate cells are buttons with `aria-haspopup` and `aria-expanded`.
- WCAG 3.2.1 and 3.2.2: arrowing through cells never navigates, peeks or switches the build. Only Enter, Shift+Enter or Alt+↓ act.
- WCAG 4.1.3: build switches and "Loading counterparts of ‹name›" are polite status messages, sent once. A refresh of the same entity announces nothing.
- WCAG 2.5.8: cells are at least 36px tall, and 44px below 700px. The strip reflows to 320px by wrapping cells.
- Identifiers carry `translate="no"`. The source line gives its read time in words for assistive technology ("Read from the stored cross-build index at 13:41").

**Removes switching:**

- Go to the same entity on build-b. Before: Code Browser → Compare workspace → CounterpartMatrix row → address → Code Browser, 2 workspace switches and 4 actions. After: →, → and Enter in the strip, 0 switches.
- Learn why build-d has no counterpart. Before: Compare workspace → CounterpartMatrix → Evidence workspace for ladder A, 2 switches. After: Alt+↓ on the absent cell, 0 switches.
- Put two builds side by side. Before: Compare workspace plus a second window, 2 switches. After: Shift+Enter on the cell, 0 switches (see SplitCompare).
- Check whether an entity has any counterpart at all. Before: 1 switch to Compare, then back. After: visible under the title, 0 switches.
