# Linked views

The workstation removes view switching with one idea: **information comes to the selection; the operator does not travel to the information.** Every mention is a typed link, every pane either follows the one selection or is explicitly held, detail opens in place, and the location lives in the URL. This section is the contract; components implement it.

## Typed links

Every mention of a navigable object is an `<a class="ad-link" href="?…">` over the shared location schema, never plain text and never a `div` with a click handler. Each link type resolves to exactly one place:

| Target | Resolves to |
|---|---|
| address, symbol | Code Browser at that build and address |
| logical id | Compare with the CounterpartMatrix |
| counterpart (entity @ build) | Code Browser for that build, same entity |
| fact | the receipt card that decided it, in the evidence rail |
| receipt id | the receipt card; it links back to "Produced by job ‹id›" |
| job id | the dock Jobs record, focused; its Targets line reveals the rows it changed |
| basis digest | the ProvenanceStamp detail and what changed since |
| compiler diagnostic file(line) | the SourceRepairDiff line in Recovery |
| image delta region | Listing at the range start in that build, with the ObjectDiff pair |
| merge or placement conflict | NameProvenance or the placed address, for that entity and build |
| work-view event | the diff or transfer it drew, at that moment of the WorkTimeline |
| pipeline node id | the PipelineMap node and its filtered live view |

An absent or unresolved target is written as a word ("absent", "unresolved"), never a link to a guess. Each link's accessible name carries type, target and state: "Job a3f9, corpus.cross-place, finished"; "Address 0041b210, build-b".

## One activation grammar

The same keys and gestures on every link, on both surfaces:

| Gesture | Keyboard | Result |
|---|---|---|
| Go | Enter, click | The primary location changes; one history stop is pushed. |
| Open beside | Shift+Enter, Shift+click | The target opens in a secondary pane (SplitCompare); the primary selection does not change. |
| Peek | Alt+↓; a 400ms pointer rest or 800ms focus rest | A read-only Peek card opens in place (WCAG 1.4.13 rules). Alt+Enter and Ctrl/Cmd+I are rejected (properties in many tools; Page Info in Firefox). |
| Keep | K inside a Peek or evidence card | The card stays in the evidence rail, labelled "Kept" (carried as `hold=card:…`). |
| Reveal in | Shift+F10, context-menu key, right-click | Menu: Code Browser · Compare · Evidence · Navigator · Dock · Pipeline map, plus Copy link and Copy value. |
| New browser tab | Ctrl/Cmd+Enter, Ctrl/Cmd+click, middle-click | Native; works because every target is a real URL. |

Space stays select or check in grids. Every component README carries a **Linking** block: what it publishes, what it follows, which targets it renders, and what an absent target looks like.

## Follow and hold

There is exactly one selection owner: the primary location (project, logical entity, inspected build, address). Every other pane is one of two things.

- **Following** (default): a pure function of the primary location. When the selection moves with arrows or j/k, focus moves at once; following panes update after a 200ms settle, keep their previous content dimmed with its address and an inline "Loading ‹name›" notice, and drop late responses for superseded selections. A **Link panes** toggle (aria-pressed) in the NavigationBar switches to commit-on-Enter. Cached panes (Listing, Decompile, Evidence) follow by default; expensive panes (Graph, Matching, corpus sections) commit on Enter.
- **Held**: frozen to one entity × build × address. Its header says **Held** with what it holds and its age, in a 2px `ink-strong` frame. It keeps its own Back/Forward, never refreshes by itself, and shows "◷ Basis changed since held · Refresh" when its basis changes. **Make primary** moves the one selection to it. Held panes and kept cards are read-only; the ActionStrip always binds the primary selection.

At most two center panes in the Code Browser; the Compare workspace may show a three-way split as its one secondary area. Further holds become kept evidence cards. Inside a held pane, Enter moves that pane through its own history and Alt+←/→ step it while focus is there; **Make primary** (Enter on its Held chip) is the only way a held pane changes the primary selection. In a derived pane, Alt+PageDown/PageUp move it to the next or previous build with a counterpart. Held state is a word and a frame, never color alone; "Held" and "Kept" are reserved words distinct from the locator word `pinned` and the ownership word `lock`.

## In place, not elsewhere

- **Peek** shows a callee, counterpart, fact, receipt, job, locator cell or ladder where it is mentioned. It reads only cached or already-loaded evidence; unloaded evidence says "Not loaded. Open to read it."
- **Detail expands in place**: FailureRecords, review decisions and matrix cells open inline or in the detail pane beside their list, never on another page.
- **Corpus panels become rail sections** scoped to the selection ("For ResourceRef::Resolve · build-b"), each with "Show all" linking to the full corpus view.
- **Outcomes land where the verb was invoked**: the row or token gets a compact lifecycle cell (admitted → running → terminal word, with its job link) once the terminal result arrives. Nothing is shown optimistically. Changed lines carry a "changed by job ‹id›" gutter mark until the next navigation.
- **Dead ends name the next step**: an empty or unbound view names the program and cause and arms, but never runs, the one catalog action that would fix it.

## Location schema (deep links)

Both surfaces parse the same query parameters and the same alias table; acceptance is that the two parsers agree exactly.

| Parameter | Carries |
|---|---|
| `project` · `session` | active project and session tab |
| `entity` | logical entity |
| `build` · `addr` | inspected build and address or cursor |
| `ws` | workspace: code, compare, recovery, evidence |
| `views` | co-visible code views: listing, decompile, hex, graph |
| `cmp` | split pair, e.g. `build-a..build-c` |
| `hold` | repeatable `kind:id@build` for held panes and kept cards |
| `dock` · `job` · `receipt` | dock tab, focused job, focused receipt |
| `f` · `q` | `axis:value` filters and free text |
| `page` | review match-id cursor |
| `t` | work-view event |
| `node` | pipeline-model node id |
| `wl` | active worklist |

Aliases read by both surfaces: `p`, `e`, `b`, `a`, `sp`, `slug`, `logical_id`, `binary`, `tool` and `tab` (→ `views`), `pin` (→ `hold`), `window=wb-*`, `focus=`.

- pushState only on user navigation (Go, workspace switch, build switch, split open). replaceState for cursor moves inside one function and for typed filters.
- Browser Back, Alt+←/→ and mouse buttons 4/5 are the app's Back and Forward. Each stop restores workspace, views, split and held panes, viewport and the focused element, and the landing is announced once. The Back button has a history menu of labelled stops.
- Never in the URL: the checked set, drafts (durable workspace state keeps them) and credentials.
- Opening a URL is read-only. It resolves against existing analysis; an unbound or empty build shows a StateNotice with the fix armed, never run. If the basis changed since the link was copied, current data is shown and held panes are marked stale.
- Every request is keyed by its location token; superseded responses are discarded.

## Why this removes clicks

Most tedious switching in the documented journeys comes from four habits: travelling to a separate view to *see* something (fixed by Peek, the XrefPanel, the CounterpartStrip and rail sections), replacing the current context to compare (fixed by Open beside and held panes), losing the place on return (fixed by the location schema and shared history), and finding the next item by hand (fixed by worklists, F8 stepping and outcomes on the row). The plan document `docs/dashboard-design/2026-09-29-linked-views-and-accessibility.md` counts the before and after for each journey.
