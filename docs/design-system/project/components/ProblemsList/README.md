# ProblemsList

The dock's Problems tab: one row per unmet predicate, failure or external action, grouped by objective, each row a set of typed links to the entity, the evidence and the job, with its FailureRecord expanding in place.

**Use it** as the Problems tab of the activity dock on both surfaces, and anywhere an objective needs "what is blocked and why" without leaving the current view. It is the list form of ObjectiveSummary's unmet predicates; it never replaces FailureRecord, it hosts it.

**Consumer provides** the objectives from the shared projection (name, next automatic action with its wake condition, independent work that continues); per problem: kind (unmet predicate, failure, external action), the stable reason phrase, the governing fact and its state for a predicate, the classification for a failure, the entity or scope with its build, the evidence reference (receipt, diagnostic, basis digest or pipeline node), the job when one exists, the observation time it started waiting and any deadline; for an external action its deduplication key, report count and the objectives it blocks; and the snapshot time and projection revision.

- Three kinds, each glyph plus word: **Failure** (✕ `fact-failed`, with its classification chip: mismatch, transient, resource, policy), **Predicate** (the governing fact's own glyph: ○ not_run, ◷ stale, ✕ failed, ? unknown) and **External action** (⚑ `fact-stale`, the approval-required glyph). The kind word is `type-kicker` in `ink-strong`; the reason is the stable phrase from the FailureRecord ("Provider paused for this input revision"), never a log line.
- **Grouped by objective.** A level-1 row names the objective, its problem count, the next automatic action as a sentence with its wake condition ("verify recipients when a3f9 finishes"), and how much independent work continues. If there is no automatic action it says so and names what is needed. Group rows sit on `pane`; problem rows on `chassis`.
- **External actions are deduplicated.** One external action appears once, in its own first group, with "N reports, shown once · blocks K objectives". Each objective it blocks shows a one-line "Also blocked by" row that links to it and says "(not repeated)". It reappears only on material change. Dismissing is not resolution; there is no dismiss control.
- **Disclosure, not a page.** A failure row expands in place (→ or a click on the twisty) into a level-3 row holding the full FailureRecord: `lane-fault-fill` header, lifecycle rail, scope, evidence with its ProvenanceStamp, spend, recovery, wake and what continues. Collapsing returns focus to the row. Opening the FailureRecord never opens another view.
- **Waiting column = starvation per row.** Each row shows how long it has waited (`type-code-small` mono) and sorts oldest first within its group (`aria-sort="descending"`). The oldest row in the list says "oldest". A job past its deadline shows ✕ `fact-failed` and "+18m past deadline" in words and names its failover; "deadline ≠ termination". Ages are observed durations from the snapshot, never ETAs or percentages.
- **Selection only** (an `ad-filt` checkbox with its count) limits rows to the one primary selection: the logical entity across builds, or the concrete build when the selection is build-scoped. The filter line says "Follows selection · ‹entity›", and rows drop the entity column value that is now implied. With nothing matching it shows a StateNotice: "No problems for ‹entity› on ‹build›. N problems elsewhere" with **Show all**.
- **Kind chips** (`ad-filt`, counts in mono) filter by kind; unchecked chips are dashed. **Collect into worklist…** (`list.worklist`, `w` in the grid) hands the current rows, in order, to MarksList. **Freeze updates** (`aria-pressed`) holds the rows; a frozen list says "Frozen at 14:02", counts what arrived and resolved since, and resumes on request (WCAG 2.2.2).
- **Refreshes never move the reader.** A new projection keeps focus, scroll, expanded rows and the selected row. A problem that resolves while focused stays in place struck through with "resolved 13:59" until focus leaves it; nothing jumps under the cursor.
- Disconnected or reconnecting: the last snapshot stays, read-only, visibly dated ("Showing problems from 13:58"), and ages say they count from that snapshot. Nothing is hidden or reset.
- Rows are 28px minimum, twisties 24px, `line` separators, the selected row `row-selected-bg` plus the 3px `accent` bar with state words promoted to `ink-strong` (glyphs keep their color). Below a 620px container the row reflows to reason on top, links and age beneath; below 700px rows and twisties are `touch-h`.
- Both surfaces render the same projection that drives the CLI and agents; the footer names the snapshot time and projection revision. The static 8080 surface may render the same rows as a plain treegrid without the sticky header; it never drops the grouping, the ages or the in-place record.

**Linking**

- Publishes: nothing by focus. Enter on a link or row goes (pushes history); `dock=problems` and `q` carry the tab and its filter in the location, so a copied link reopens the same filtered list.
- Follows: the primary selection only while **Selection only** is on. Otherwise it shows the whole project and follows nothing.
- Renders: entity and counterpart (Code Browser at that build), receipt (receipt card), compiler diagnostic file(line) (the SourceRepairDiff line), basis digest (ProvenanceStamp detail), job (dock Jobs record, focused), pipeline node (PipelineMap node), and "N recipients" as a filtered entity list.
- Absent: "no job admitted", "external · no job", "whole build" are words, never links. An entity whose counterpart is unresolved says "unresolved on build-d".

**Keyboard**

- APG Treegrid with one tab stop. ↑/↓ move between rows, Home/End to first and last row, Ctrl+Home/End likewise across groups. → expands a collapsed row, or on an expanded row moves into its first cell; ← collapses, or moves to the parent group row. Typeahead matches the reason text.
- Within a row, ←/→ move between cells; Enter on a link cell goes; Shift+Enter opens it beside; Alt+↓ peeks it; Shift+F10 opens **Reveal in** (Code Browser, Compare, Evidence, Navigator, Dock). On the reason cell, Enter toggles the FailureRecord.
- In an expanded FailureRecord, Tab moves through its links; Esc returns focus to the owning row.
- Space or x (`list.check`) checks the focused row; checked rows show a 24px checkbox cell and a count chip, never a second fill. `w` or **Collect into worklist…** collects the checked rows, or every visible row when none is checked, in their current order. The toolbar comes before the grid in Tab order.
- Keys come from `keymap.json` (`list.move` j/k, `list.worklist` w, `list.mark` m then a letter, `leader` g); single keys act only while focus is in the grid and can be turned off (profile Off) or remapped in KeymapSettings (WCAG 2.1.4).

**Accessibility**

- `role="treegrid"` named "Problems by objective, oldest first", with `aria-rowcount`; rows carry `aria-level`, `aria-posinset`, `aria-setsize` and `aria-expanded` where they expand; the expanded record is a level-3 row whose single cell spans the columns and holds a named group.
- A row reads as a sentence: "Failure, mismatch: Provider paused for this input revision. ResourceRef::Resolve on build-c. Evidence resource.c line 41. Job 0b17, repair, waiting. Waiting 22 minutes." Glyphs are `aria-hidden`; every link's name carries type, target and state.
- The polite region announces once per filter change or problem transition ("5 problems in 3 groups. Oldest: ABI checks not run on build-d, 3 hours 40 minutes"), never per poll. An external action that newly blocks the action in hand is the only assertive message.
- Expanding or filtering changes only this list (WCAG 3.2.2); focus never moves on its own (3.2.1). `scroll-padding-block` keeps the focused row clear of the sticky header (2.4.11). Targets are 24px, 44px below 700px (2.5.8).
- Every state is a glyph and a word; the waiting age is text, not a bar.

**Removes switching:** J04 "why is this blocked and what continues" goes from 5 switches (ladder → Problems → Logs → Jobs → Operations → back) to 1 (open the Problems tab; the record, diagnostic and job are in the row or a peek). J28 "act on starvation" goes from 4 (Review, Jobs, Pipeline, each target) to 1: ages sit on the rows, oldest first. J35 "why is this fact stale" goes from 3 to 1 through the basis link. Counts before come from the journeys table; after counts are design targets, not measurements.
