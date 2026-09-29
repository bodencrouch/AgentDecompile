# Linked views

The workstation removes view switching with one idea: **information comes to the selection; the operator does not travel to the information.** Every mention is a typed link. Every pane either follows the one selection or is explicitly held. Detail opens in place, and the location lives in the URL. This section is the contract; components implement it and point here rather than restating it.

## Typed links

Every mention of a navigable object is an `<a class="ad-link" href="?…">` over the shared location schema. It is never plain text and never a `div` with a click handler. `data-kind` names the target type for routing and accessible names only; there are no per-kind colors. Each type resolves to exactly one place:

| Target | Resolves to | Moves primary location | Focus lands on |
|---|---|---|---|
| address, symbol | Code Browser at that build and address | yes | the Listing row at the address |
| logical id | Compare, with the CounterpartMatrix | yes | the entity's matrix row |
| counterpart (entity @ build) | Code Browser for that build, same entity | yes | the Listing row at the counterpart's entry |
| fact | the receipt card that decided it, in the evidence rail | no | the receipt card |
| receipt id | the receipt card; it links back to "Produced by job ‹id›" | no | the receipt card |
| job id | the dock Jobs record. Its Targets line names what the job was asked to act on; its Changed line filters the rows its receipts recorded as changed | no | the job record |
| basis digest | the ProvenanceStamp detail and what changed since | no | the stamp detail |
| compiler diagnostic file(line) | the SourceRepairDiff line in Recovery | yes | the diff line |
| image delta region | Listing at the range start in that build, with the ObjectDiff pair | yes | the Listing row at the range start |
| merge or placement conflict | NameProvenance or the placed address, for that entity and build | yes | the conflict record |
| work-view event | the diff or transfer it drew, at that moment of the WorkTimeline | no | the timeline event |
| pipeline node id | the PipelineMap node and its filtered live view | no | the map node |
| matrix cell (entity × build) | selects that entity and build in place; the EntityBuildCard in the evidence rail follows | yes: entity and build, one stop | the cell (focus stays) |
| xref hint (XREF[n]) | References at that build and address, Line scope, incoming | no; if the row is not the cursor, the cursor moves with replaceState | the References grid |
| build | the Navigator program row for that build | no | the program row |

Every "Reveal in" destination follows the same two columns.

Each link's accessible name carries type, target and state, for example "Job a3f9, corpus.cross-place, finished" or "Address 0041b210, build-b".

- **Uncertain targets.** "absent" and "unresolved" are plain words (`.ad-absent`), never an anchor and never a link to a guess. "ambiguous" and "contested" are the word plus a link to the ladder evidence. A contested target also lists both evidenced members as candidate links, marked "no winner". Merges say "conflicting".
- **Cross-build.** A counterpart link shows its identity-edge word (accepted or candidate), both visibly and in its accessible name. No counterpart link exists without a recorded edge. An address link always carries its build and is never re-resolved into another build. A build link only reveals its program row; switching the inspected build stays an explicit action there, and it states any checked-set clearing first.
- **Cross-project.** Opening a project admits its eligible missing work (U105). So a link or new tab that names a project other than the open one never opens it. It lands on a StateNotice that names both projects, with "Open ‹project›" armed and confirm-gated, never run.

## One activation grammar

The same keys and gestures on every link, on both surfaces:

| Gesture | Keyboard / pointer | Result |
|---|---|---|
| Go | Enter, click | Goes to the target per the table above. One history stop is pushed. |
| Open beside | Shift+Enter, Shift+click | Creates a Held pane (below). The primary location does not change and no stop is pushed. On 8080 without split panes, the same link opens in a new window and the menu item reads "Open beside (new window)". Below 700px it is the second segment of the split toggle (U191). |
| Peek | Alt+↓; 400ms pointer rest; 800ms focus rest | Opens a read-only Peek card in place, following the 1.4.13 rules in 90. Focus-rest opening is off by default at 400% zoom and below 700px, and the sheet never covers its trigger (2.4.11). `aria-expanded` and `aria-controls` are present only while the Peek is open. Alt+Enter and Ctrl/Cmd+I are rejected: many tools use them for properties, and Firefox uses Ctrl+I for Page Info. |
| Keep | the Keep button (aria-pressed) in a Peek or evidence card; Shift+K while focus is inside that Peek or card | The card stays in the evidence rail, labelled "Kept", carried as `keep=`. The letter never works in lists where j/k move. From a trigger, the path is Tab then K, or the menu. The binding lives in `keymap.json` and is remappable. |
| Link menu | Shift+F10, the context-menu key, right-click | Opens the one link menu (below). Shift+right-click passes through to the browser's native menu. |
| New browser tab | Ctrl/Cmd+Enter, Ctrl/Cmd+click, middle-click | Native behaviour; it works because every target is a real URL. |

**Grid modifier precedence.** In checkable grids (entity lists, review queues), Ctrl/Cmd-click and Shift-click anywhere on a row, including its name link, belong to the checked set. Shift+↑↓ and Shift+j/k extend the range. In those grids, Open beside is Shift+Enter or the menu, and a new tab is Ctrl/Cmd+Enter, middle-click or the menu. Outside checkable grids the grammar above applies unchanged. Space stays select or check.

**The link menu.** There is one menu for every link, a flat APG Menu with separated groups and no cascading submenu:

1. Open · Open beside · Peek · Keep (Keep appears only inside a Peek or card).
2. **Edit**: only on editable tokens (locals, parameters, fields, callees, labels, operands, data), and only for actions present in `GET /api/v1/actions`, such as Rename…, Retype…, Comment… or Edit callee signature…. An item that does not apply stays listed, `aria-disabled`, with its reason. Choosing one opens its inline editor or arms the ActionStrip; nothing posts from the menu.
3. **Reveal in**: only the destinations this target type resolves to, drawn from Code Browser, Compare, Recovery, Evidence, Navigator, Dock and Pipeline map. A guessed destination is never listed.
4. Copy link · Copy ‹typed value›, e.g. "Copy address 0041b210". Copy announces "Copied address 0041b210, build-b".

With a coarse pointer, every row exposes one 44px row-menu button carrying the same menu, and inline links fall back to Go.

**Arrival.** The landing cue is focus moving to the landing row or record, plus the selection or cursor shape and the existing 120ms flash. Under reduced motion the flash becomes 90's static outline. There is no separate "landed" style.

**Announcements.** Focus is the primary cue. Exactly one polite message is added in these cases, coalesced as described in 90:
- when Go changes the workspace, build or dock tab;
- when a Go lands somewhere other than where it was asked to go;
- when a Back/Forward stop lands, announced once;
- when a narrow-layout Go changes the visible pane, announced once.

The document title updates on push and popstate only. Nothing relies on title changes being announced.

## Follow and hold

There is exactly one selection owner: the primary location (project, logical entity, inspected build and address). Every other pane is one of two things.

- **Following** (default): a pure function of the primary location.
  - When the selection moves with arrows or j/k, focus moves at once. Following panes redraw in place after a 200ms settle.
  - A pane that is redrawing keeps its previous content dimmed, with its address and an inline "Loading ‹name›" notice. It drops late responses for superseded selections. It sets `aria-busy` on itself, never on the pane that holds focus.
  - Cached panes (Listing, Decompile, Evidence) follow by default. Expensive panes (Graph, Matching, corpus sections) and matrices commit on Enter; in a matrix, arrows move focus only. A commit-on-Enter pane whose selection has moved stays dimmed and says "Shows ResourceRef::Resolve; selection is now Actor::LoadFromTemplate · Enter to load".
  - An **Update panes** control in the NavigationBar (a two-option radio group: "As I move" / "On Enter") switches every following pane to commit-on-Enter. Every following pane's header shows its mode in words ("Follows · on Enter").
  - A following pane never decompiles, fetches expensive evidence or starts work on a cache miss. It says "Not decompiled in this session · Enter to decompile" and waits for an explicit Go. Following never crosses a project and never opens a program ("Not loaded. Open to read it.").
  - The Graph follows by marking the current node. It keeps its root, zoom and scroll while the selection stays inside the drawn graph. When the selection leaves it, it says "Selection is outside this graph · Re-root here" and re-roots only on that action. Moving within the graph moves focus; Enter on a node is Go, and focus lands on the Listing row.
- **Held**: frozen to one entity × build × address, with an optional basis token.
  - Only center and secondary panes are held. Evidence sections and Peeks are kept as cards instead.
  - The pane's toolbar has a toggle with the constant name **Hold this pane** (aria-pressed). The visible state words beside it read "Following · sync A" or "Held · ‹entity› @ ‹build› · ‹age›".
  - A held pane has a 2px `ink-strong` frame. It shows current data labelled "Held · read ‹time›".
  - A different basis reads "◷ Basis changed since held · Refresh". A hold without a basis token reads "Basis at hold time not recorded". Old data is never replayed, and a pane is never marked unchanged by assumption.
  - A held pane has its own Back/Forward buttons, which never touch browser history. Inside it, Enter moves that pane. On a kept card, Enter on a link goes. Each container's footer says which.
  - **Make primary** (Enter on its Held chip) is the only way a held pane changes the primary selection. It moves the one selection to the held location, pushes a stop and releases the hold; the pane stays open and becomes Following. A held pane never closes by itself.
  - Held panes and kept cards are read-only. The ActionStrip always binds the primary selection.
  - When the selection moves other than by a history step (which rebinds without arming, below), an armed ActionStrip keeps its bound target and says "Bound to ResourceRef::Resolve · selection is now Actor::LoadFromTemplate · Rebind". It never retargets silently. Rebind binds it to the current selection without arming it; Esc with focus in the strip disarms it. Either way the entered fields stay as a draft.

The Code Browser has at most two center panes. The Compare workspace may show a three-way split as its one secondary area. A further hold becomes a kept card, with the notice "Two center panes in use; kept as a card in Evidence". At most three cards are kept; a fourth Keep is refused with "Three cards kept; release one", and nothing is evicted. A kept card whose basis changed reads "◷ Basis changed since kept · Refresh". In a derived pane, Alt+PageDown/PageUp move to the next or previous build with a counterpart.

**Focus never changes workspace, build, dock tab or history.** Only Go, Make primary, a workspace or build switch, or a history step does.

Held state is a word and a frame, never color alone. "Held" and "Kept" are reserved words, distinct from the locator word `pinned` and the ownership word `lock`.

## Reflection

Listing, DecompileView, HexStrip and GraphPane share the one cursor in the primary location. They point here rather than restating it.

- **One cursor.** Arrows and clicks move the cursor; the URL is replaced after the settle. Enter on a link is Go: every view lands and one stop is pushed. Enter in an editable well enters edit mode.
- **Mapped set.** Every other visible view marks the rows mapped to the cursor. The mapping may be many-to-many. The mark is the `raised` fill, a 3px `ink-muted` bar (`reflect-bar`), the words "↔ line 7" or "↔ 3 instructions", and ▸ at the exact address. In forced colors it is a dashed `CanvasText` outline.
- **Missing mappings are answers.** "No address mapping for line 7" or "No decompiled line for 0041b213". The other view keeps its cursor and draws no mark. Nothing is inferred from line order or the nearest address.
- **Pointer brushing** is optional, for fine pointers only, and off unless the viewer turns on "Brush on hover" in View settings. Resting on a token for the settle delay outlines its mapped set with a 1px dotted `line-control` outline (`brush-outline`) and no bar, and the status line says "Pointer: ↔ line 7". It never moves the cursor, the selection or history, never fetches, and clears when the pointer leaves. It is off in forced colors.
- **`r`** moves focus to the first reflected row: Listing → Decompile, Decompile → Listing, Hex → Listing, Graph → Listing at the block's first instruction. A hidden target view is shown in the same slot, and the switch is announced once. With no mapping, focus stays and the status says "No mapping; focus stays".
- **Highlight all** (`h`) on a register, variable or constant marks every occurrence in each visible view of the same build, up to four at once, lettered A–D. Each occurrence gets a 1px `ink-strong` box (`highlight-box`) and its letter, never an underline, because an underline means a link in code wells. The key is variable identity where the decompile projection gives it, otherwise exact text. The legend chip says which and counts in words ("A eax · 7 in this function · text match"); activating the chip removes the highlight. Another build gets a highlight only through recorded anchors or identity ("via anchor"); otherwise it reads "text match on build-c". A fifth `h` does nothing and says "Four highlights in use; remove one". Highlights are per-viewer view state, never in the URL.
- **Pointer and touch.** The link menu and the 44px row-menu button carry "Show reflected row" and "Highlight all"; both are palette commands.
- **Proof wells.** A candidate source line maps to rebuilt rows through that compile's line table ("rebuilt r15 · line table") and to target rows through the ObjectDiff alignment receipt ("aligned by receipt ‹id› · aligned ≠ equivalent"). If the source changed since that compile, the mapping reads "◷ compiled from r14; source is r15".

## Confirming edits

Inline edits (rename, retype, comment) confirm in place. The inline field names its exact binding (program, build, address or local storage) and the tier change, and Enter or Save posts the catalog action once. ConfirmDialog is reserved for batch, destructive or cross-build mutations. A struct-field retype, any structure-layout change that resizes, overwrites or clears components, and a callee-signature edit also use ConfirmDialog, because they change every use of that type or callee. The dialog names the type or callee, the build, and the known use or caller count, or "uses not indexed". Outside an open inline editor or the ActionStrip, no key alone mutates anything.

## In place, not elsewhere

- **Peek** shows a callee, counterpart, fact, receipt, job, locator cell or ladder where it is mentioned. It reads only cached or already-loaded evidence; unloaded evidence says "Not loaded. Open to read it." The fact strip is one ≥24px button that opens a Peek, not a link. Per-fact receipt links live in the Peek and in the rail's Facts section.
- **Detail expands in place.** FailureRecords, review decisions and matrix cells open inline or in the detail pane beside their list, never on another page.
- **Corpus panels become rail sections** scoped to the selection ("For ResourceRef::Resolve · build-b"). Each has a "Show all" link to the full corpus view (`panel=`).
- **Outcomes land where the verb was invoked.**
  - The row or token gets a compact lifecycle cell once the terminal result arrives: admitted → running → terminal word, with its job link.
  - The cell's binding comes from the job record, and its words come from the Job outcome vocabulary (State vocabularies).
  - Nothing is shown optimistically.
  - Changed lines carry a "changed by job ‹id›" gutter mark until the next navigation. The mark is drawn only from stored or cached reads; otherwise the pane says "Not decompiled in this session · Enter to decompile".
- **Dead ends name the next step.**
  - An empty or unbound view names the program and the cause. It arms at most one action taken from `GET /api/v1/actions`, choosing reuse first, and never runs it. The design system hardcodes no action ids.
  - When read-only discovery finds existing recovered analysis or receipts, only the catalog's binding or resume action is armed, and the evidence found is named. An analysis action is never armed while such evidence exists.
  - Nothing is armed while discovery is not loaded.
  - Armed fixes come from the resolved state, never from URL parameters.

## Location schema (deep links)

Both surfaces load one machine-readable schema, [`location-schema.json`](../location-schema.json): parameters, value grammars, the alias table, and a mapping for every legacy `tab` and `window=wb-*` value. Acceptance is that the two parsers agree exactly.

| Parameter | Carries |
|---|---|
| `project` · `session` | active project and session tab |
| `entity` | logical entity |
| `build` · `addr` | inspected build, and address or cursor |
| `ws` | workspace: `code`, `compare`, `recovery`, `evidence` (four values only) |
| `panel` | a full corpus view inside a workspace, such as `report` or `atlas`; the target of every "Show all" |
| `views` | co-visible code views: listing, decompile, hex, graph |
| `cmp` | split pair, e.g. `build-a..build-c` |
| `hold` | held center panes only: `kind:id@build[:addr][~basis]`, at most two |
| `keep` | Kept cards: `kind:id[@build][~basis]`, repeatable, at most three; `hold` and `keep` share one kind list in the schema |
| `dock` · `job` · `receipt` | dock tab, focused job, focused receipt |
| `type` | a type or field path, e.g. `CacheEntry.name_len` |
| `f` · `q` | `axis:value` filters and free text |
| `page` | review match-id cursor |
| `t` | accepted work-view event id |
| `node` | pipeline-model node id |
| `wl` | active worklist |

- **Aliases.**
  - Both surfaces read `p`, `e`, `b`, `a`, `sp`, `slug`, `logical_id`, `binary`, `tool`, `tab` (→ `views`), `pin` (→ `keep`), `window=wb-*` (→ `ws` + `panel`) and `focus=`.
  - A canonical name wins over its alias, and an ignored alias is named in a notice.
  - Old bookmarks redirect through the alias table. Explorer is the Navigator region, expanded and focused, never a center surface.
- **Lossless round trip.** A parameter that a surface cannot render stays verbatim in its URL and gets a StateNotice. Static 8080 shows holds as Held entries in the evidence rail.
- **Unresolved values are words**, never a guess. Examples:
  - "Event ‹id› is no longer retained";
  - "Worklist not available here";
  - a score-shaped `page` is refused by name;
  - `cmp` uses only recorded edges and locators (absent, unresolved, or contested with no winner);
  - an `addr` without a `build` lists the builds that contain it.
- **Never in the URL:** the checked set, drafts (durable workspace state keeps them) and credentials.
- **Opening a URL is read-only.** It resolves against existing analysis. An unbound or empty build shows a StateNotice with its fix armed, never run, per the dead-end rule. If the basis changed since the link was copied, current data is shown and holds are marked with the basis words.

### Project and session

A URL or history stop that names a project other than the active one never switches projects. It shows a StateNotice that names both projects, with **Switch** armed and **Stay**. The notice says that opening a project admits its eligible missing work and reuses its receipts. A landing with no active project offers "Open ‹project›" the same way. History never crosses session tabs silently. An explicit URL wins over a restored session tab only within the active project.

### History

- **Push** on:
  - Go (a link, row Enter or click, a go-to pick, Make primary, a job or receipt link, Show all);
  - a filter applied from a link, which is a Go (for example "Changed by a3f9" on a job record);
  - a workspace switch by click, Enter or shortcut;
  - a build switch;
  - opening or closing a `cmp` pair.
  Consecutive workspace switches with no Go in between collapse into one stop. Explicit pushes are never coalesced.
- **Replace**, throttled to after the 200ms settle, on:
  - list and grid focus moves (arrows, j/k);
  - cursor moves;
  - typing or editing a filter, and removing a filter chip;
  - `views`, `dock`, `hold` and `keep` changes;
  - alias rewrites.
  At narrow widths `views` and `hold` are never rewritten.
- **Back and Forward.** Browser Back, Alt+←/→ and mouse buttons 4/5 (natively, through popstate) are the app's Back and Forward, and always act on the primary history.
  - Alt+←/→ are not intercepted in text fields or edit mode, and are remappable in `keymap.json`.
  - A stop stores the viewport as an anchor address plus caret, and focus as a stable region + component + row key. It restores workspace, views, split, viewport and focus.
  - Back and Forward never open, close or re-point held panes or kept cards: those are layout, and the URL is rewritten with replaceState to the current holds.
  - In-app Back is disabled at the tab's first stop ("no earlier location in this tab").
- **The Recent menu.** An APG Menu Button beside Back (right-click on Back opens the same menu) lists up to 20 of this tab's stops, each with its label, time and "✎ edited". A **Changed since visited** filter keeps the stops whose entity and build appear in a job's recorded change units after the visit, each with its job link and time; jobs that recorded no units, or only reused evidence, do not qualify. Picking a stop in this tab traverses with `history.go`. Picking an older durable entry is a Go. Snippets are labelled "as read ‹time›". Back itself has no history menu, no Alt+↓ and no long-press.
- **History never replays.**
  - A history move that changes the program clears the checked set, as any program change does. Back's accessible description says so first ("clears 12 checked rows on build-a"), and the polite region confirms it afterwards.
  - A history move cancels an open ConfirmDialog, so nothing is sent.
  - A history move rebinds the ActionStrip to the restored selection without arming it.
  - No action or submission is ever replayed.
- **Restore reads now.** "Restore the place; data is read now."
  - On restore or landing, cached panes (Listing, Decompile, Evidence) render from stored evidence.
  - Expensive panes (Graph, Matching, corpus panels, a build whose program is not open) show "Not loaded. Open to read it." until Enter.
  - Reads are keyed by location token and selection generation, and superseded reads are aborted.
- **Non-authoritative state.** `history.state` (per browser tab, per viewer) and Recent (stored in the durable workspace, F23) are client state. They are never evidence, and never a basis for a claim.

### Link interception contract

- A surface intercepts only same-origin anchors whose href parses fully under `location-schema.json` and its alias table.
- Everything else stays native: unknown parameters, `/api`, `/docs`, settings, downloads, `target=_blank`, and modified clicks outside the grammar.
- An intercepted link never issues its server GET, and nothing is prefetched speculatively.
- The URL, read through one shared location resolver, is the only navigation state. There is no separate bus or store.

## The Linking block

Every component README carries a **Linking** block with these fields, in this order:

- **Publishes**: what it changes: the primary location, a hold, a keep, or nothing.
- **Follows**: settle or commit-on-Enter, and whether it can be held.
- **Targets rendered**: which target types from the typed-link table it links.
- **Peek source**: which cached evidence its Peeks read.
- **Absent copy**: the exact words for absent, unresolved, ambiguous and contested targets.
- **Target-size exception**: any inline-link exception to 2.5.8, or "none".

A diagram-only component with no app rendering writes "Linking: none (print diagram)".

## Why this removes clicks

Most tedious switching in the documented journeys comes from four habits:

- **Travelling to a separate view to *see* something.** Peek, the XrefPanel, the CounterpartStrip and rail sections fix this.
- **Replacing the current context to compare.** Open beside and held panes fix this.
- **Losing the place on return.** The location schema and shared history fix this.
- **Finding the next item by hand.** Worklists, F8 stepping and outcomes on the row fix this.

The plan document `docs/dashboard-design/2026-09-29-linked-views-and-accessibility.md` estimates the before and after counts for each journey. Every count there is an estimate, not an observation.
