# FailureRecord

A failure drawn at its real unmet dependency: stable reason, scope, evidence, owner and resource, freshness, spend, wake condition, what continues, and authority only when unavoidable. Every field is a typed link or a disclosure that expands in place.

**Consumer provides** those fields, the failure lifecycle position, the classification (mismatch, transient, resource, policy), the log or diagnostic lines around the evidence, the owner and resource as the backend reports them, and the independent work that continues.

- Header on `lane-fault-fill` names the reason in a stable phrase ("Provider paused for this input revision") as the record's heading. The lifecycle rail sits in the body as an `<ol>` with `aria-current="step"`: observed → classified → contained → recovery_pending → reconciling → eligible. The current state links to its resilience step (`resil-step-1`…`resil-step-5`).
- **Fixed field order**, the same on both surfaces and in ObjectiveSummary diagnoses: **reason** (the heading) · **scope** (a link to the PipelineBreadcrumb crumb or PipelineMap node, with the entity and build) · **evidence** (a disclosure with an inline excerpt of the existing log tail or the SourceRepairDiff lines around the diagnostic, and "Open log at line") · **owner and resource** (a disclosure showing OwnershipPanel and ResourceState inline, process identity as reported) · **freshness** (ProvenanceStamp) · **spend** (attempts and budget, with the recovery action it pays for) · **wake condition** (a link to the awaited job or lock) · **continues** (a count link that applies a FilterChip to Functions and the dock) · **Explain** (a disclosure rendering the node's Trying to / How / In → out / Gate text).
- **Expand all** and **Collapse all** sit in the header; expanded state persists per viewer.
- Always show what continues. The affected branch stops visibly; every eligible sibling continues.
- An escalation adds the failed predicate, raw evidence references, attempted recoveries and the exact external change required. It is emitted on transitions, not polls. Dismissing is not resolution.

**Linking**

- **Publishes:** nothing. "Continues" applies `f=eligible:…` to the Functions grid and the dock, which own those filters.
- **Follows:** its host: the dock's Problems grid (F8 steps records from anywhere), the evidence rail for the primary entity and build, or an ObjectiveSummary diagnosis. Not holdable; a record can be kept as a card (`keep=failure:f19@build-c`).
- **Targets rendered:** scope → the PipelineBreadcrumb crumb or node (`?node=stage-4`) for that entity and build · evidence → the log at that line (`dock=logs&job=0b17`) or the SourceRepairDiff line · owner job → the dock Jobs record; resource → its lock node · freshness → the ProvenanceStamp link group · wake condition → the awaited job or lock · continues → the Functions grid filtered to the eligible work · lifecycle state → its resilience node. Link names read "Scope stage 4, C/C++ candidates, ResourceRef.cpp, build-c".
- **Peek source:** the stored failure record, the job's log tail already in the dock, and the generated outline text for Explain; nothing is re-run.
- **Absent copy:** "owner: unknown" · "process identity: not reported" · "revalidation: not scheduled" · "no log excerpt recorded".
- **Target-size exception:** none; disclosure buttons are 24px and links sit on 24px field rows.

**Keyboard**

- Disclosures are APG Disclosure buttons: Enter or Space toggles; focus stays on the button. Links follow the linked-views grammar. F8 / Shift+F8 step problems from anywhere.

**Accessibility**

- The reason is the record's heading; fields are a `<dl>` in the fixed order. Excerpts are `role="log"` with `aria-live="off"`. Unavailable actions are `aria-disabled` with the reason in `aria-describedby`. A failure is assertive only when it blocks the action in hand; otherwise its transition is announced once, politely.

**Removes switching:** opening the logs, the Jobs dock, the pipeline map and the resource list to learn why something is blocked and what still runs (J04, J28).
