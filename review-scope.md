# Scope, product and adversarial document review

Reviewed document type: plan. Upstream scope is explicitly user-set across the named documents; this review does not reopen that scope or propose narrowing it. Deep review of the complete main contract, representative named obligation records, multiplayer source and source-clause ownership mechanism. No software tests, builds or runtime probes.

## Re-review disposition — resolved

The P1 below is resolved in the revised artifacts. The master Implementation Units contract now distinguishes the single accountable owner of named delivery obligations from the single coverage owner of source clauses, and explicitly says clause ownership is not a prerequisite edge. Each unit closes its own named children and predicates without inheriting unrelated downstream acceptance. The todo repeats that completion rule; the living plan states cross-cutting coverage closes at final integration.

Checked the concrete reproducer in all three artifacts: `S044-C0005` gameplay modes maps to U35, `S044-C0006` multi-stage implementation sequence maps to U39 final integration, and `S044-C0007` directory metadata maps to U37. U33/U34 no longer inherit directory completion. Additional individually trackable frontend requirements, feature families, guide chapters and capability milestones strengthen execution accountability.

No remaining concrete P1 consequence from this review. This is a focused re-review of the fix and representative mappings, not an independent audit of all 2,839 source clauses/elements or a claim of software acceptance. Historical finding follows for traceability.

## Scope guardian — original finding, now resolved

### P1 — Give each inherited obligation a specific accountable delivery owner

Confidence: 100. Main plan lines 253 and 893–897 require each integration unit to close every applicable mapped child/clause. But source-clause mappings assign whole source families to every unit in that family, rather than the unit delivering the clause. For example, `S044-C0007` (plan lines 54685–54704) assigns the complete public-directory metadata contract to U33, U34, U35, U36, U37, U38 and U39. U33 is source baseline and identity; U34 is local transport. Neither should wait for public listing, active authenticated player counts, expiry, endpoint ownership and password metadata to close its own deliverable. The todo lines 915–922 repeat this broad ownership for every multiplayer section. The assembler confirms filename-level ownership, and the same problem affects the much larger frontend source family.

Concrete consequence: an executor either follows the close-all-mapped-clauses rule and cannot finish prerequisite source/local-transport units until dependent directory/UI work finishes, or informally chooses which clauses are “applicable,” reintroducing the omissions and scope ambiguity the consolidation was intended to eliminate. The main caveat that dependencies denote consumed predicates does not name those predicates or resolve the shared clause's acceptance responsibility.

Fix: retain every captured source clause, but distinguish a source coverage acknowledgement from a delivery obligation. Give each delivery obligation one primary unit and any explicit contributing units; decompose genuinely cross-cutting clauses into individually checkable acceptance predicates or a defined joint gate. For example, U37 owns directory registration/listing/expiry/metadata, U35 owns authenticated gameplay/password exchange and session count source, U38 consumes discovery metadata, and U39 proves cross-network integration. U33 and U34 can reference the source for context without inheriting directory completion. Mirror that primary-owner/predicate mapping into the living plan and todo. Do not remove any existing requirements or evidence.

No finding challenges the requested program size. Existing backend, recovery and runtime adapters are reused rather than a new parallel framework; that is appropriately scoped.

## Product lens

No separate material finding. The contract preserves model-free deterministic recovery, original-code runtime reuse, both frontend products, contributed compute as a supporting package, all 193 weekend records plus 110 later records and 43 frontend units, and M0–M7. It does not confuse the user-reported BioWare lobby behavior with accepted remote multiplayer. The multiplayer scope preserves both co-op and persistent-world modes, source-built client/server deliverables, and a real in-game browser.

## Adversarial document lens

The scope finding above also falsifies the assumption that source capture plus a nonempty owner set establishes an executable coverage map: all source bytes can be retained while ownership and closure remain ambiguous. Do not report source-line preservation as semantic completeness until that mapping is corrected. No additional independent material finding from the examined contract: versioned evidence, independent acceptance, exact-build operation gates, publication fencing versus quarantine, unknown-effect reconciliation, provider qualification and mode-specific live proof are correctly retained.

## Limits

This review inspected the full synthesized main contract and sampled the large obligation/source appendix; it did not independently reread all 68,615 lines. Captured-source counts and hashes establish retention only. This report is a planning review, not software or live-game acceptance.
