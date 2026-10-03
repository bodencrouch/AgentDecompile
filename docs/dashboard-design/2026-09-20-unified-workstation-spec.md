# Unified reversing and recovery workstation

Status: implementation specification; not a completion or recovery receipt.
Current completion claims and prioritized closeout are tracked in
[`../DELIVERY_STATUS.md`](../DELIVERY_STATUS.md).

## Authority and scope

User request: redesign the entire AgentDecompile dashboard around all KotORXID
HTML/JS functionality and the GUI capabilities in
https://github.com/OpenKotOR/PyKotor/wiki/Ghidra-Reversing-Guide .
The latest user directives also require one project/program-bound pipeline
start/pause/resume control, automatic stage progression, no individual stage
launch buttons, and a single Functions browser in the editor area.

Current operational authority is the canonical AGENTS.md and STRATEGY.md at
/run/media/brunner56/MyBook/Workspaces/ai-projects/AgentDecompile . The isolated
worktree's September 9 strategy is older; do not let it override September 20
canonical policy. This spec organizes the GUI, not another recovery policy.

Source inventories, with implemented/partial/missing distinctions:

- 2026-09-20-donor-dashboard-capability-inventory.md
- 2026-09-20-ghidra-guide-capability-inventory.md
- 2026-09-20-delivery-reconciliation.md

## Shared interaction contract

Latest user refinement: treat the project's binaries as comparable implementations
of ONE shared codebase. The primary selected object is a logical entity in the
corpus, not an isolated binary/address. Show all matched instances, unmatched
builds, ambiguity, provenance and divergence together. Compare is a fundamental
workspace interaction, not a secondary destination the user must repeatedly open.
Individual builds remain explicitly distinct for bytes, ABI, addresses, edits
and proof; never imply that every candidate is equivalent or one build's receipt
proves another. Support both logical-entity-first browsing and entry from a
concrete function that has not yet acquired an accepted identity.

One selected project, logical entity, inspected build(s), and address owns all
views. A project is not a
binary; a saved tab is not proof that its locator is accessible. Selection
changes invalidate obsolete requests and never silently choose another target.
Project-wide recovery scope and the currently inspected member must both be
visible when they differ. Keep back/forward navigation and deep links.

Opening a view reads existing analysis; it must not reanalyze, import, or start
recovery merely because a list is empty. Use existing program bindings and
fingerprint-bound evidence. Loading, empty, disconnected, unavailable, stale and
unsupported are distinct states.

Primary work areas:

1. Code Browser: synchronized Listing and Decompile, symbol/type navigation,
   one Functions inspector, references/call trees, memory, bookmarks, function
   editor, structures, vtables, guide and advanced scripting/export.
2. Compare: corpus/build roster, logical identities and sibling navigation,
   matcher evidence, ambiguity/review queue, STABS and field-level provenance.
3. Recovery: per-target and corpus ladders, compile-gated source transfer,
   residual work, paired byte-accurate/max-C variants and receipt-backed proof.
4. Evidence: artifact/database views, original names, knowledge coverage,
   manifests, source/toolchain identity, freshness, and raw evidence on demand.

A compact activity drawer and contextual annotations carry actual job ownership,
current operation, source/target builds, measured progress, changed outcomes,
blocking prerequisites, last activity and receipt freshness. A spinner and the
word Running alone are not an acceptable status. Unknown progress names the
operation and last observation without inventing a percentage or ETA. Use inline
row changes, stage details, expandable causal explanations and navigable evidence
as appropriate, not a wall of logs or repeated generic badges.
It must not flood startup with historical completion
toasts. Pipeline steps are observable, not a manual checklist of Run buttons.
Expert editing commands remain explicit, target-bound and conflict-aware.

## Pipeline control

## Show the work, not a status report

User explicitly rejected replacing Running with a textual statistics sentence.
The primary feedback is a live, inspectable visualization of the actual work:

- Matching: candidate implementations are brought together; highlight the
  actual blocks, references or evidence under comparison. Distinguish candidate,
  accepted, rejected and unresolved edges; show alternatives without pretending
  all builds are one-to-one or all candidates are equivalent.
- Source recovery: show before/after source edits and the actual compiler
  diagnostic or semantic evidence each change addresses. A stage name is not
  evidence of a particular source transformation.
- Verification: align original/generated instruction or byte regions, reveal
  residual differences and relocation-aware interpretation; distinguish fresh
  comparisons from historical receipts.
- Propagation: animate the specific eligible source/name/type/comment change
  from its evidenced donor to concrete recipient builds, show compatibility
  gates, conflicts and recipient validation. No animation of a successful
  transfer before the corresponding event/receipt exists.

Every meaningful element is inspectable and navigates to the underlying entity,
diff or evidence. Motion follows observed events, with pause/step/history and a
reduced-motion presentation conveying the same changes. Unknown internals remain
explicitly unobserved rather than a looping pretend-work animation. Counts,
timestamps and logs are secondary details, not the primary feedback design.
Backend event instrumentation is part of this scope where current receipts lack
the necessary operation/entity/artifact evidence. Do not approximate it from a
timer, broad phase name, or a count increase.

## Pipeline control semantics

Use the existing preparation/workflow coordinator and action catalog, not a
new browser scheduler. Start/resume reuse eligible checkpoints. Pause drains
accepted native work and preserves ownership until safe. A standalone live job
must remain visible and prevent duplicate admission; cancellation is not pause.
Catalog `mutating` alone is insufficient admission evidence: the running
corpus.ghidra-bulk advertises false despite write=true. Backend resource claims
and actual owner state must arbitrate admission across tabs and clients.

The full canonical identity/recovery/failover chain remains in scope, including
bidirectional field-level metadata, type/ABI gates, source compile gates,
cheap-first residue repair and fresh full-image compiler/objdiff acceptance.
Do not call function slices, copied bytes, placeholders or a completed job proof.

## Guide coverage

Cover all 16 sections through actual workflows, not only a documentation tab.
Reuse CodeBrowser, GuideWorkflows, FunctionEditor and existing MCP providers.
Close the known GUI gaps: continuous instruction/data listing, shared address
navigation and history, local-variable rename/type gestures, genuinely editable
parameter storage, field-level structures, and vtable/inheritance evidence.
Show runtime/compiler-spec-derived calling conventions and storage registers.
Never encode the guide's example x86 layouts or simplified ABI claims as rules.
Unsupported mutations must say why; buttons cannot merely resubmit old values.

## Visual direction

The initial binary-first concept images below, and the subsequent text-heavy
corpus concept, are superseded as information architecture/feedback. Reuse their
typography/palette, not their primary program selector, generic Running status,
or statistic strips. Generate a corpus-first, actual-work visualization reference
before composing the shell.

Dense, legible graphite IDE, restrained blue selection, thin separators,
code-native text/controls, no card-grid marketing treatment. Project/program
selection and one pipeline control stay visible. Listing and Decompile occupy
the primary workspace; inspectors and activity are resizable/collapsible.
At narrow widths, one primary pane at a time replaces crushed side-by-side
content. No duplicate function sidebar or giant blank upper workspace.

Initial primary-screen design reference:
/home/brunner56/.codex/generated_images/01a0aca5-acc2-7011-abdf-aba17449c646/exec-4a990f44-d482-4103-9356-6fac6ad835db.png
This is a generated design reference, not user-approved runtime evidence; its
sample rows, code and status are illustrative and must never seed production
data. Recovery-state reference:
/home/brunner56/.codex/generated_images/01a0aca5-acc2-7011-abdf-aba17449c646/exec-1984dcc2-dc04-4ba3-8299-bb8abb1863fe.png
Narrow-screen layout reference:
/home/brunner56/.codex/generated_images/01a0aca5-acc2-7011-abdf-aba17449c646/exec-eb353da8-df00-4c89-9148-2971f625541d.png
Comparison/evidence references remain to be completed. Generated output pixel
dimensions do not establish responsive acceptance; the real598x912 browser must
be inspected after implementation.

## Delivery and acceptance

Deliver two maintained alternatives over one backend/state contract: (1) a
complete useful static HTML/CSS/JavaScript workbench served by the MCP HTTP
server on 8080, without requiring Node or the Vite application, and (2) an
optional full React/TypeScript Vite application whose default standalone port
is 5174 and which is also packageable at `/react/`. The optional application is
not a development-preview-only route. They may differ in layout and richness,
but must agree on project identity, catalog capabilities, durable state, jobs,
mutations and proof semantics. This delivery requirement does not authorize
starting 5174 during the current recovery mission: recovery operations and live
acceptance remain exclusively through the existing 8080 service. Do not add a
fourth shell, backend, catalog, state owner or recovery scheduler, or copy
providers into either frontend.
Preserve all KotORXID implemented navigation/evidence capabilities identified
in the inventory, including bounded queries and no-JS/evidence fallbacks where
applicable. Old donor ports and the KotORXID donor's standalone server are not
part of the design.

Acceptance requires a requirement-to-live-evidence matrix, real selection
changes, navigation and safe edits, actual control owner transitions, independent
spec/quality review and Playwright CLI screenshots/interactions on8080 at desktop
and598x912. The optional Vite application also needs a separately authorized
packaging and browser receipt before it can be called delivered; this plan does
not authorize starting it. No filesystem tests or test fixtures. No5174 process,
curl, systemctl, automatic server restart, reanalysis, duplicate compiler/Wine
jobs, or public PR during current recovery work.
Source presence is not runtime parity, and dashboard completion is not recovery
completion. Deployment must preserve server/worker IDs and existing receipts.
