# ObjectiveSummary

The top of every objective: accepted capabilities, active attempts, independent eligible work, unmet required predicates and the next automatic action. Its values are typed links or disclosures that expand in place.

**Use it** at the top of each objective and as the dock's **Objectives** tab (`dock=objectives`), which shows the ObjectiveSummary for the active project with its FailureRecords. The tab's empty state reads "No blocked objectives".

**Consumer provides** those five fields from the shared projection that also drives the other surface, the CLI and agents; for each unmet predicate, its diagnosis in FailureRecord's fields; for each attempt, its job record and its verb's `catalog_verbs` mapping.

- **Five fields, always in this order**, everywhere: accepted capabilities · active attempts · independent eligible work · unmet required predicates · next automatic action. Diagnosis expands in place; nobody should correlate logs to learn whether work is progressing.
- **Accepted capabilities** are count links to the rows they count (`f=`).
- **Active attempts** are job links, each with its StageChip rendered only from its verb's `catalog_verbs` mapping ("stage: unmapped" otherwise, with no lane guess).
- **Independent eligible work** is a typed link: "Continues 38 independent jobs on build-c" → the dock's Jobs tab filtered to that work; it filters Functions only when the backend names function targets.
- **Unmet predicates** are APG disclosures. Each expands into FailureRecord's fields in guideline 50's order: reason · lifecycle rail · classification · scope · evidence · owner and resource · freshness · attempts and budget spent · recovery action · wake condition · what continues · escalation (only when unavoidable) · Explain. The five-field order above is unchanged by this; the diagnosis sits inside field 4.
- **Next automatic action** is a sentence whose wake condition is a link to the awaited job or lock ("wake: a3f9 terminal" → the job). If none exists, it says so and names what is needed.
- **Expand all** and **Collapse all** sit in the header; expanded state lives in durable workspace state, never localStorage.
- **Empty or unbound scope** follows 35's dead-end rule: name the program and cause in words, show existing reuse evidence and any existing or pending admission first, and only then arm at most one catalog action for the primary selection (labelled "Prepare: resume from receipts"; its accessible name adds "nothing runs until Run"), never run it, and never while discovery is not loaded. No action ids are fixed in the design system.

**Linking**

- **Publishes:** nothing. Count and work links apply filters (`f=`) owned by the Functions grid and the dock; a filter applied from a link pushes one stop.
- **Follows:** `project` and the objective's scope (a build or the corpus), re-read from the shared projection after the settle. Not holdable; keepable as a card (`keep=objective:readable-c@build-b`).
- **Targets rendered:** capability counts → the Functions grid filtered to those rows · attempts → their dock Jobs records · StageChips → pipeline nodes · eligible work → the dock's Jobs tab filtered to that work · each predicate's fields → as in FailureRecord · wake condition → the awaited job or lock · the stamp → its basis detail.
- **Peek source:** the stored objective projection and the failure records it references; nothing is fetched on hover.
- **Absent copy:** "No active attempts." · "No independent eligible work." · "No next automatic action. Needed: ‹predicate›." · "revalidation: not scheduled" · "Discovery not loaded. Nothing is armed."
- **Target-size exception:** none; disclosure buttons are 24px and fields sit on 24px rows; 44px below 700px.

**Keyboard**

- Disclosures toggle with Enter or Space and keep focus; links follow the linked-views grammar.

**Accessibility**

- A `<dl>` in the fixed order; each predicate disclosure is a button with `aria-expanded` whose region follows it in the DOM. Nothing here is a live region; transitions are announced once by the dock.

**Removes switching:** opening the Jobs dock, the problems list and the pipeline map to learn why an objective is not advancing (J04; counts in the plan ledger).
