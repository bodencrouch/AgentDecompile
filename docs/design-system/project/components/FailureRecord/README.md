# FailureRecord

A failure drawn at its real unmet dependency, in guideline 50's fixed field order. Every field is words, a typed link or a disclosure that expands in place.

**Consumer provides** the stable reason; the failure lifecycle state (backend states only); the classification; the affected scope as a node id with entity and build; the evidence reference (log offset or diagnostic, whether the log is still retained) and its stamp; owner and resource exactly as the backend reports them; evidence freshness; attempts and budget spent; the recovery action (chosen fallback, the one retry owner and its persistent budget); the wake condition; the independent work that continues (job ids, and function targets only when the backend names them); any escalation; and the served `pipeline-model.json` revision for Explain.

**Fields, in this order** (50, Failure record), the same on both surfaces and in ObjectiveSummary's predicate diagnoses:

1. **Reason**, as the record's heading: a stable phrase ("Provider paused for this input revision") on `lane-fault-fill`. Its heading level is relative to the host.
2. **Lifecycle rail**: observed → classified → contained → recovery_pending → reconciling → eligible, an `<ol>` with `aria-current="step"` and the 2px `ink-strong` now-frame. Backend states only; rail steps are words, never links. Branches: waiting_external, budget_exhausted, unsupported. `detector_unknown` is never shown as healthy or failed.
3. **Classification**: mismatch, transient, resource or policy, as a word.
4. **Scope**: a PipelineBreadcrumb crumb or node link, with the entity and build.
5. **Evidence**: a disclosure. Its excerpt of the stored log tail, or the SourceRepairDiff lines around the diagnostic, is read only when expanded, never on focus, hover or prefetch; the read is keyed by location token and late responses are dropped. The excerpt carries its ProvenanceStamp. "Open log at line 211" appears only when the record carries an offset. A rotated log reads "log no longer retained".
6. **Owner and resource**: a disclosure showing OwnershipPanel and ResourceState inline, as reported, else "unknown". An external owner is never offered kill or restart.
7. **Freshness**: the evidence's ProvenanceStamp link group.
8. **Attempts and budget spent**: "2 of 3 attempts".
9. **Recovery action**: the chosen fallback, the one retry owner and its persistent budget. It is its own field and never folded into the spend line.
10. **Wake condition**: the awaited job or lock, as a link.
11. **What continues**: a link to the dock's Jobs tab filtered to the continuing work; to Functions only when the backend names function targets.
12. **Escalation and authority**, only when an external intervention is unavoidable: the failed predicate, raw evidence references, the independent work still eligible, the attempted recoveries and consumed budget, and the exact external change or decision required. Emitted on transitions, not polls. Dismissing is not resolution.
13. **Explain**: a disclosure rendering the scope node from the backend-served `pipeline-model.json` (never the outline markdown), headed "From the pipeline design · model rev ‹8 hex›" with "Design description ≠ this item's evidence", in the context-hint claim tier (dotted frame, ClaimTier). Its crosswalk line names the model's interpretation of the current state and ends "(interpretation)": observed and classified → `resil-step-1`; contained, recovery_pending and reconciling → `resil-step-3`; eligible → `resil-step-5`. The branches have no crosswalk, and no state maps to steps 2 or 4.

- It renders as a `<dl>`; long values sit behind APG disclosure buttons. **Expand all** and **Collapse all** sit in the header. Expanded and collapsed state lives in durable workspace state, never localStorage. The static 8080 surface renders `<details>` in the same order.
- Always show what continues. The affected branch stops visibly; every eligible sibling continues.
- **Empty and unbound hosts** follow 35's dead-end rule: name the program and cause, show reuse evidence and any existing or pending admission first, then arm at most one catalog action for the primary selection, reuse first, never run it, never while discovery is not loaded. The design system names no action ids.

**Linking**

- **Publishes:** nothing. "What continues" applies `f=eligible:…` to the dock's Jobs tab, which owns that filter; a filter applied from a link pushes one stop.
- **Follows:** its host: the dock's Problems treegrid (F8 steps it only after "Step problems" collects it as the active worklist), the evidence rail for the primary entity and build, or an ObjectiveSummary diagnosis. Not holdable; a record can be kept as a card (`keep=failure:f19@build-c`).
- **Targets rendered:** scope → the PipelineBreadcrumb crumb or node (`?node=stage-4`) for that entity and build · evidence → the log at the recorded line (`dock=logs&job=0b17&f=log.line:211`) or the SourceRepairDiff line (`f=src.line:resource.c:41`) · owner job → the dock Jobs record; resource → its lock node · freshness → the ProvenanceStamp link group · retry owner → its job record · wake condition → the awaited job or lock · what continues → the dock's Jobs tab filtered to that work · inside Explain only, the crosswalked resilience node, labelled "(interpretation)". Link names read "Scope stage 4, C/C++ candidates, ResourceRef.cpp, build-c"; "resil-step-3 Repair, reroute or wait, interpretation".
- **Peek source:** the stored failure record; the evidence excerpt from the stored log tail or SourceRepairDiff, read on expand only; Explain from the served `pipeline-model.json` at its revision. Nothing is re-run.
- **Absent copy:** "owner: unknown" · "process identity: not reported" · "log no longer retained" · "no log offset recorded" · "revalidation: not scheduled" · "No crosswalk for this state".
- **Target-size exception:** none; disclosure buttons are 24px and links sit on 24px field rows; 44px below 700px.

**Keyboard**

- Disclosures are APG Disclosure buttons: Enter or Space toggles; focus stays on the button. Links follow the linked-views grammar. F8 / Shift+F8 step the active worklist only.

**Accessibility**

- The reason is the record's heading; fields are a `<dl>` in the fixed order. Excerpts are `role="log"` with `aria-live="off"`. Unavailable actions are `aria-disabled` with the reason in `aria-describedby`. A failure is assertive only when it blocks the action in hand; otherwise its transition is announced once, politely. Disclosures never move focus (WCAG 3.2.1).

**Removes switching:** opening the logs, the Jobs dock, the pipeline map and the resource list to learn why something is blocked and what still runs (J04; counts in the plan ledger).
