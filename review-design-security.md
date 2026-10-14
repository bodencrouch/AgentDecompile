# Design and security review

Reviewed 2026-09-28; planning artifacts only. Read both complete ce-doc-review persona prompts. Scope: master contract, integration units, verification gates, living/todo projections; targeted source checks against unified workstation, distributed compute and multiplayer source snapshots. No implementation, runtime, build or acceptance verification was performed.

## Design lens

- Information architecture: 8/10 — product purpose, actors, selection context, project tabs, shared navigation, dense CodeBrowser and bottom activity hierarchy are explicit. A 10 would include the final visual layout for every integrated tool; the retained source clauses already own those detailed decisions.
- Interaction state coverage: 8/10 — loading, unavailable, stale, failed, pending, absent counterparts, reconnect, conflicting drafts and per-cell state are retained across U14–U20/U38 and inherited frontend U8. A 10 would give one compact state matrix at each implementation owner rather than requiring its child clauses.
- User flow completeness: 8/10 — F1–F3 define the main entry/exit paths; U14 covers open/import/merge/reconnect; U31 preserves contribution opt-in and Stop; U38 covers the browser and join refusals. A 10 would include the final cross-surface walkthrough visual, but there is no demonstrated dropped flow.
- Responsive/accessibility: 8/10 — U15/U17/V7 preserve keyboard, screen readers, reduced motion, narrow layouts and structured graph alternatives; retained frontend source includes approximately 1100px/700px adaptations and 44px touch targets. A 10 would place the inherited dimension rules directly in U15.
- Unresolved design decisions: 8/10 — WASM and provider provisioning are explicit prerequisite gates, not invented completed experiences. A 10 requires completing those future investigations; their unresolved state is represented honestly.

No finding meets the persona's <=7 threshold. No generic hero/card-grid pattern displaces the product-specific dense workbench. The in-game browser's blue/translucent treatment is a specific user-derived target rather than generic decoration.

## Security lens

No blocking plan-level security finding established in the reviewed scope. The following protections are present and must remain acceptance detail:

1. Admission versus consent: R24/U14 allow explicit recovery admission and forbid passive reads starting work; C21/U31 retain explicit opt-in for provider-backed browser contribution, transient secrets, fixed CSP origins, and no credential proxy.
2. Untrusted distributed results: U11/U32 preserve proposal-only results, credential-bound capabilities, signatures/revocation/rate limits, independent verifier authority, current input basis, durable acknowledgement and replay semantics. Source role labels cannot self-promote truth.
3. Public directory and join secrets: source README lines143–152 explicitly limits metadata to public listing fields, requires endpoint ownership and expiry, prohibits publishing join passwords/reusable hashes/admin credentials, and routes verification through authenticated/encrypted join. These clauses are inherited by the master; do not call them missing merely because U37's short synthesis omits them.
4. Dangerous local operations: catalog/current ownership gates, exact target identity, bounded artifact browsing, export traversal protection, mutation conflict handling and scoped acceptance remain explicit. No plan language authorizes an unrelated restart or external publication.

Top exploitable paths considered: forged contributor acceptance is addressed by independent proof and credential/current-basis checks; directory impersonation/password leakage is addressed by endpoint verification and public-metadata limits; stale UI targets causing unintended writes are addressed by identity-bound selection, draft conflict and backend admission. This is a review of the required design, not evidence that these controls are currently implemented.

Optional readability improvement, not an additional obligation or blocking finding: repeat the directory metadata/secret boundary directly in U37 and repeat the authenticated password-check boundary in U35/U38. The master already contains and requires them, so this would improve discoverability rather than close a missing requirement.

## Review limits

This was targeted semantic review, not an independent proof that every one of the large register's source clauses has the correct owner. Parent coverage reconciliation must establish that separately. No acceptance status was promoted and no source-controlled files were edited.
