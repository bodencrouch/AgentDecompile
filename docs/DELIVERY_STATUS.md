# Delivery status and prioritized closeout

Status date: 2026-09-20. This is the implementation/acceptance ledger for
[FRONTEND_INTENT.md](FRONTEND_INTENT.md), the
[workstation spec](dashboard-design/2026-09-20-unified-workstation-spec.md), and
the [implementation plan](plans/2026-09-20-unified-reversing-workstation.md).
Requirements being documented or source code being present is not delivery.

## Evidence boundary

Completed in documentation only:

- The current correction is explicit: deliver both a complete static HTML/CSS/JS
  alternative on8080 and an optional full Vite application (default5174 and
  packageable at `/react/`) over shared backend/state semantics.
- Recovery operations remain exclusively on the existing8080 service. No new
  server, port, recovery scheduler or state owner is authorized.
- The consolidated F01-F28 scope, conflicts/supersessions, acceptance scenarios,
  and archive/source limitations are recorded in `FRONTEND_INTENT.md`.

Observed by bounded source review, but not runtime-accepted:

- The inspected runtime routes static `/dashboard` separately from packaged
  `/react/`; packaged assets existed when inspected. Presence is not execution,
  currency or parity proof.
- The delivery investigation found different runtime and isolated roots. Commit
  `7b3ff60` now mounts WorkstationApp in the isolated source and reconciles its
  missing native dependencies. Task1 parameter storage (`a6bbe36`) has source
  review approval. Task2 and its stale-navigation/hidden-editor lifecycle fixes
  are source-reviewed at `275d50a`; neither React task is deployed or accepted
  in the browser. App/AtlasApp are not mounted by the reconciled entry.

Verified bounded delivery, not whole-workstation acceptance:

- The static job-activity correction in `275d50a` was selectively activated on
  NVMe. A Playwright reload retained the exact K1 selection, kept the duplicate
  Functions widget absent, and no longer announced historical completions.
  Only measured work totals produce determinate progress. The served asset was
  inspected after polling; server PID616810 and existing job50f7fc81e7ab remained
  unchanged. Two session-state PUTs occurred; no recovery POST was observed.
- Standalone hot-reload package `inplace-hotreload` exists independently under
  `/home/brunner56/inplace-hotreload`; its `0.1.0` wheel SHA256 is
  `6e65fbacd1bed118b2118dc6a4a2485049c7175aa12da3b82b55837e5185abca`.
  Installed metadata and the live in-process engine were inspected. This does
  not promise migration of active frames, native code or incompatible class
  layouts, and is not a PyPI publication or fresh behavioral reload receipt.

Still open: end-to-end parity, the current max-C ZIP, runtime-reuse proof,
distributed worker flow, optional Vite runtime acceptance, and fresh whole-image
recovery proof. The historical `k1gog_byteaccurate_build.zip` is not a current
max-C source archive. Existing compiler-owned source must reach a safe snapshot
boundary before export; cancel is not pause.

Runtime update after that observation: server616810 disappeared for an unknown
reason, while compiler701843 survived. After checking startup had no eligible
preparation/batch/inventory work, the exact NVMe server was restored as1102130;
Playwright confirmed healthy and the same selected K1 corpus. Existing history
projection observes the surviving process as running but non-cancellable. It is
not a reattached controllable job, and its retained log is not fresh progress.
No overlapping recovery was submitted. Durable child-output/ownership and
resource admission remain an explicit closeout item, not a reason to overwrite
the live compiler or fabricate completion.

## Actionable delivery checklist

These IDs track delivery dependencies, not recovery priorities. STRATEGY remains
the sole recovery ordering authority; this is not another priority-zero gate.

| ID | Delivery action | Evidence required to close |
|---|---|---|
| Delivery 0 | Reconcile executing, canonical and isolated source/build identities; preserve live owners and durable state. | File/revision/loaded-module and process-owner receipt; reviewed selective-transfer list. |
| Delivery 1 | Keep `/dashboard` complete as the static alternative; reconcile the optional Vite root around WorkstationApp without App/AtlasApp auto-prepare behavior. | Source review plus explicit proof that selecting/browsing cannot admit recovery. |
| Delivery 2 | Unify project/logical-entity/concrete-build selection, navigation, compatibility links and stale-response rejection across both alternatives. | Real reload/back/forward/deep-link/target-switch interactions with preserved identity and no duplicate work. |
| Delivery 3 | Deliver the corpus-first Code Browser, Compare, Recovery and Evidence workflows, all guide/KotORXID inventory rows, and genuine target-bound editing. | Requirement-to-live-evidence matrix; unsupported backend gaps named rather than represented by inert controls. |
| Delivery 4 | Connect one backend-owned start/pause/resume flow and evidence-bound actual-work events; remove routine manual stage launch controls. | Owner transitions, safe pause/resume, reconnect/failover and inspected entity/diff/event evidence; no fabricated progress. |
| Delivery 5 | Package and activate safely without replacing live state: static8080 independently useful, packaged `/react/` current, optional standalone5174 validated only when separately authorized. | Installed-artifact hashes/revision, atomic asset handoff, desktop/narrow real interactions for each claimed mode, and shared-state parity. |
| Delivery 6 | Close broader requested outcomes: durable project import/merge/export, max-C and byte-accurate variants, runtime reuse, distributed contribution, collaboration/CI, hot-reload packaging and reporting integrations. | Outcome-specific live/artifact receipts; current authorization for any external post or publication. |
| Delivery 7 | Claim a recovered build only after current STRATEGY terminal acceptance. | Fresh complete source/toolchain build, object evidence, exact-placement relink and whole-file comparison for that exact build/variant. |

## Source traceability limits

`FRONTEND_INTENT.md` defines every shorthand key it uses (D1-D2, H1-H3,
C1-C9, P1, A1 and R14). Both H3 source locators were subsequently resolved and
their duplicated originating request is explicitly identified. The coverage
section records bounded scans, giant-record and missing pasted-text gaps.
Treat those remaining gaps as open provenance work, not unnamed
evidence or proof that all prior conversations were exhausted. New recovered
requirements must be added to the consolidated ledger with an explicit source
and supersession decision; do not create another competing intent document.
