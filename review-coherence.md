# Coherence and feasibility review

Scope: the three new planning files only; inspected the synthesized master contract/units/verification sections, the living and todo projections, and assembled-index metadata. Read both requested persona assets in full. No production changes, tests, builds, service probes or runtime acceptance. Raw appendices were sampled only where needed to corroborate a finding.

## Coherence lens

### CR1 — Namespace legacy frontend unit references in synthesized prose

- Severity: P2; confidence: 100; disposition: safe_auto.
- Location: comprehensive master lines 612, 625, 637, 648, 660, 672–673, and similar bare legacy references in U13–U28.
- Evidence: KTD4 promises original IDs are namespaced. U24 says “U33; source pack exists”, but the master’s U33 is “Source baseline and identity” for multiplayer. U28 says “U40 precise WASM consumer target discovery” and “U41 static … U42 Vite”; its actual U40–U42 are semantic findings, collaboration and packaging.
- Impact: a reader following these references reaches a different deliverable, potentially interpreting an unrelated unit as a prerequisite or its evidence as export acceptance.
- Fix: qualify all original frontend U references with the exact namespace already used by their source-qualified obligation records. Reserve bare U1–U42 for the new integration units. Do not rewrite the preserved historical source text.

### CR2 — Apply supersessions in the active queue, not only in the master conflict table

- Severity: P2; confidence: 100; disposition: safe_auto.
- Location: todo lines 98 and 151; living rows 116 and 169; master conflict decisions C19/C20.
- Evidence: the todo commands `portable-plan-2026-09-21:U21` “Purge every product, binary, and project name … code, docs” followed by “satisfy the full inherited acceptance”. C20 explicitly preserves named fixtures, adapters, research and provenance. The U65 checkbox still leads with “effectively unbounded”, although C19 replaces that mechanism with bounded progress/deadline/checkpoint containment. Both living rows say simply `required` with no override pointer.
- Impact: the supposedly sole execution queue directs an executor toward an explicitly obsolete mechanism; consulting source detail reinforces that direction unless the reader independently remembers the global conflict table.
- Fix: retain these obligations but give the active checkbox corrected behavior and an explicit `modified by C20` / `modified by C19` disposition in both projections and obligation headers. Keep the historical wording inside the source record. Apply the same check to other C-table corrections, particularly pipeline launch controls.

## Feasibility lens

No additional architectural blocker was established in the inspected synthesized sections. They preserve independent source/runtime acceptance, resource fencing/quarantine, real-consumer proof, durable exchange proposals and exact target qualification. Broad U1–U42 units are explicitly integration owners with detailed child obligations, so their size alone is not a finding.

Review limitation: no implementation read or runtime investigation was performed under this documentation-only scope. This review therefore does not certify that the planned mechanisms are implemented or that every external prerequisite is available.

## Exhaustiveness caution

The inventory demonstrates retention of source text and named records, not independent semantic verification of every clause. For example the entire 977-line recovery SVG and 1,022-line drawio are each represented by one source clause assigned to fifteen integration owners. This is lossless archival coverage, but not a one-to-one proof of diagram element ownership. Do not present counts alone as proof of zero semantic gaps. The synthesized lane and gate descriptions plus inherited source acceptance can still be the delivery contract; explicitly report this distinction or add a diagram-element mapping if claiming element-level exhaustive reconciliation.

## Final recheck — findings resolved

CR1 is resolved: synthesized export-unit references now use `frontend-plan-2026-09-28:U31` through `frontend-plan-2026-09-28:U42`; the inspected U23–U28 section has no remaining ambiguous bare legacy reference. Current master dependency IDs remain unqualified and distinct.

CR2 is resolved: active todo U21 now requires generic core defaults while retaining named fixture/adapter/research provenance and cites C20. Active todo U65 requires bounded analyzer lifecycle, durable progress/deadlines/checkpoints and cites C19. The living plan now explicitly states these active interpretations and says historical labels are not execution instructions.

The exhaustiveness caution has been addressed structurally: assembled-index now has 494 named obligations and 2,839 source/diagram clauses (814 source clauses plus 2,025 diagram elements), with exactly one coverage owner for each clause. All 494 named keys and all 2,839 clause keys occur in each of the three final files. This is a read-only document consistency check, not a software test or product acceptance. The living plan explicitly distinguishes textual capture from semantic implementation and states that cross-cutting source coverage does not create premature prerequisite edges.

No new mechanical regression was found in this recheck. This resolves the review's two concrete findings; the feasibility/runtime limitations above remain unchanged.
