# ObjectiveSummary

The top of every objective: accepted capabilities, active attempts, independent eligible work, unmet required predicates and the next automatic action, each a typed link or a disclosure that expands in place.

**Consumer provides** those five fields from the shared projection that also drives the other surface, the CLI and agents; for each unmet predicate, its diagnosis fields.

- The same five fields in the same order everywhere. Diagnosis expands in place; nobody should correlate logs to learn whether work is progressing.
- **Accepted capabilities** are count links to the rows they count (`f=`). **Active attempts** are job links with their StageChip. **Independent eligible work** is a count link that applies a FilterChip to Functions and the dock.
- **Unmet predicates** are APG disclosures. Each expands into the FailureRecord diagnosis fields in the fixed order: reason · scope · evidence excerpt · owner and resource · freshness · spend · wake condition · continues · Explain.
- The **next automatic action** is a sentence with its wake condition, and the awaited job or lock is a link. If none exists, say so and name what is needed.
- **Expand all** and **Collapse all** sit in the header; expanded state persists per viewer.

**Linking**

- **Publishes:** nothing. Count links apply filters (`f=`) owned by the Functions grid and the dock.
- **Follows:** `project` and the objective's scope (a build or the corpus), re-read from the shared projection after the settle. Not holdable; keepable as a card (`keep=objective:readable-c@build-b`).
- **Targets rendered:** capability counts → the Functions grid filtered to those rows · attempts → their dock Jobs records · StageChips → pipeline nodes · eligible work → the filtered Functions grid and dock · each predicate's scope → its PipelineBreadcrumb crumb or node · wake condition → the awaited job or lock · the stamp → its basis detail.
- **Peek source:** the stored objective projection and the failure records it references.
- **Absent copy:** "No active attempts." · "No independent eligible work." · "No next automatic action. Needed: ‹predicate›." · "revalidation: not scheduled".
- **Target-size exception:** none; disclosure buttons are 24px and fields sit on 24px rows.

**Keyboard**

- Disclosures toggle with Enter or Space and keep focus; links follow the linked-views grammar.

**Accessibility**

- A `<dl>` in the fixed order; each predicate disclosure is a button with `aria-expanded` whose region follows it in the DOM. Nothing here is a live region; transitions are announced once by the dock.

**Removes switching:** opening the Jobs dock, the problems list and the pipeline map to learn why an objective is not advancing (J04).
