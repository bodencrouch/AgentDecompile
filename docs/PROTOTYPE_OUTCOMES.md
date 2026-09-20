# Unfinished prototype outcomes

Assessment: 2026-09-20. This is an outcome/evidence ledger, not a second priority
policy. [STRATEGY](../STRATEGY.md) owns the pipeline and repeated per-target loop;
[AGENTS](../AGENTS.md) owns operations. The current thread goal is paused. This
document does not resume it or declare the full prototype complete.

The intended result is a reusable corpus workflow, first across the provided
BioWare releases, with readable-source recovery and original-engine observation
as distinct useful branches. Another game's multiplatform corpus is the later
generality check. Recurring intent below uses independent original user answers,
not repeated exports or assistant completion claims. Evidence keys follow the table.

| Requested outcome | Current evidence and claim boundary | Next action |
|---|---|---|
| Complete provided corpus and architecture coverage; reusable for another game (A1–A3) | **Not reassessed live.** Existing corpus registration and workflow source do not prove complete imports/analysis. Historical handoffs describe deferred Witcher DRM work, Dragon Age not started and Sonic ARM9 architecture limits; retain those as historical, not current inventory facts. | Reconcile every supplied build, architecture, analyzed project binding and receipt through 8080; expose supported, missing, deferred and incompatible cases. |
| Repeated per-binary recovery/enrichment/cross-match loop, with corpus roll-up (D1–D3) | **Policy restored; execution incomplete/unverified.** STRATEGY now maps the loop to its stages without inventing a ninth stage from “priorities 1–9.” Corpus `dashboard/workflow.py:continue_recovery` has resume/profile-admission paths; their presence does not establish the full loop. | Pick the next authorized target from existing state, reuse accumulated knowledge, and require per-target outcome evidence while independent identity/metadata lanes continue. |
| Complete matcher chain and field-level knowledge transfer (D1–D3, E1–E3) | **Partial source evidence.** `corpus/identity.py`, program bindings and export exist. Full cascade coverage, precision, ambiguity handling and bidirectional per-field transfer across all builds were not measured here. | Audit existing matching receipts against STRATEGY; preserve human/STABS/symbol/Ghidra/placeholder name precedence, conflicts, ABI/layout gates and compile-gated source transfer. |
| Both byte-accurate C+assembly-floor and max-C variants, fresh whole-image proof (D1–D3; current acceptance directive) | **Unverified terminal outcome.** Function compilation, isolated objdiff and original-byte floors are distinct evidence. No fresh complete compiler/linker/whole-file equality proof was performed here for either variant. | Reconcile each variant's current source and provenance, then obtain separately attributed fresh acceptance when authorized. Never count copied bytes as recovered C. |
| Current K1 max-C ZIP and maintained paired source deliveries | **Requested; not reassessed.** A current handoff requests a max-C K1 ZIP and maintained byte-accurate/max-C pair; no delivery receipt was verified in this audit. | Locate existing archive, source revision, manifest and delivery receipt first. Do not repackage merely to create fresh activity or describe an old ZIP as current. |
| Portable runtime bindings, typed calls, caves/detours and feedback (B1–B3) | **Verified source gaps; end-to-end unverified.** `corpus/export_hookpack.py:export_hookpack` and the advertised `corpus.export-hookpack` exist; KotorPhasor loads packs. Export lacks complete ABI/context/site/patch contracts. See [runtime reuse](RUNTIME_REUSE.md) for x86-32 limits, typed native call sites, cave capacity, detour rollback and weaker address-hint cases. | Use the existing exporter/loader seam; bind a supported target and typed adapter, validate install/call and independent state, then feed provenance-bound observations back to the corpus. |
| Live quest completion, engine-state driving and softlock recovery (B3, C1, F1) | **Historical partial evidence only.** KotorPhasor's `docs/harness-research/live-softlock-20260909.md` records stagnation and failed recovery; `live-k2-native-20260909.md` records missing gameplay adapters. A historical rancor report is not a full quest or universal harness proof. | Reassess current adapters and existing recordings/receipts, then demonstrate a complete real quest and recovery from a measured softlock when live work is authorized. |
| Source-built client/server split, in-game server browser and configurable master lobby (C1–C3) | **Requested; not reassessed end-to-end.** Existing multiplayer paths and local runtime examples do not establish authoritative cross-process replication or source-built products. Earlier Lua-only integration evolved into explicit C/C++ client/server requests. | Recover the networking contract and existing project evidence before building on it; require separate processes, real gameplay and browser/lobby outcomes. |
| Dashboard resume, admission, ownership, resource-aware concurrency and failover (G1–G3, E1–E3) | **Implemented pieces, incomplete acceptance.** `dashboard/workflow.py` contains resume and measured compiler admission; action jobs retain state. Source presence does not prove durable continuity, correct process ownership or all failover paths. | Inspect existing jobs/receipts and corroborate owners; remove repeated orchestration work, keep safe independent lanes moving, and verify selected-target continuity without restarting or duplicating workers. |
| Python hot reload preserving server/JVM/jobs/compiler | **Unimplemented; concrete live blocker.** The controller's read-only investigation found supervisor/server/compiler in one service cgroup with `KillMode=control-group`, `Restart=always`, `ExitType=main`. The running supervisor has no control input to disable source-triggered replacement. Restart controls in `dashboard/server_control.py` are not hot reload. | Preserve all processes. Resolve lifecycle authority and Python 3.14 dependency compatibility before an actual compatible-body-edit proof through the existing consumer. Supervisor termination/adoption is not established safe; no manager mutation or alternative control tool is an authorized workaround. |
| KotorXID interaction obligations (H1–H3; design 00/09/10) | **Requirements recovered, current UI acceptance not reassessed.** Corpus roll-up plus per-binary ladders; actionable counts; one-click function/sibling/identity navigation; subject-grouped visuals; raw output on demand; source/age on figures; honest real-C versus byte-exact counts; preserved selection/deep-link/refresh state. A single port alone does not satisfy these. | Review the running 8080 experience against the original design: one 1440×900 landing view, deliberate graph navigation, no dead counts or silent target substitution, measured page/query performance and visible stale/failed state. |
| Reliable progress reporting, including Discord | **Historical handoff: paused/broken; not reassessed.** No current delivery, connection or notification receipt was inspected. | Locate the configured reporting owner and latest receipt; keep it distinct from recovery completion. Do not send messages or resume reporting without current authorization. |

The source locations above are relative to `src/agentdecompile_recovery/` in the
canonical AgentDecompile checkout unless another repository is named. Read-only
inspection is evidence about implementation shape, never live completion.

Hot-reload source-root observation, 2026-09-20: the controller inspected the
running Python environment at `/home/brunner56/agentdecompile-nvme`, while the
canonical repository is
`/run/media/brunner56/MyBook/Workspaces/ai-projects/AgentDecompile`.
These are this investigation's paths, not a universal deployment layout.
Before editing, reconcile the server PID/cwd, loaded module `__file__`, and source
revisions; changing canonical files alone does not activate code in the NVMe
process. Preserve both checkouts' changes and the running jobs; no blind sync,
overwrite or restart is authorized by this observation.

## Original-user evidence locators

Only task-related intent is retained; raw private conversation content is not
republished. The investigation reports retain exact source paths and quote context.

- **A1–A3, corpus/generality:** Codex session `01a0aca5-acc2-7011-abdf-aba17449c646`,
  2026-09-20, JSONL line 33936; `.codex/history.jsonl:652` (2026-08-23);
  `.claude/history.jsonl:1498` (2026-08-31).
- **B1–B3, callable originals/signatures:** same Codex session, line 34026;
  `.claude/history.jsonl:1488` (2026-08-31 code-cave parameter validation);
  Codex session `01a088ae-66c0-7560-952c-541d93d1f774`, line 454
  (2026-09-10 harness, signatures and softlocks).
- **C1–C3, multiplayer products:** `.claude/history.jsonl:1463` (2026-08-31);
  Codex session `01a0a7f6-0941-7533-aa0b-b20e1cf993d6`, line 10 (2026-09-16);
  session `01a0ab3c-efc3-74a0-96b0-b4afe3f194bc`, line 722 (2026-09-17).
- **D1–D3, target recurrence:** Claude session `7e5a0694-ed24-41ff-9b03-d38b372016ca`,
  user `0e909466-6aad-49ee-9625-f717a717dc3d` (2026-08-22);
  session `a7b84e5e-db13-4ab3-9ec1-ece6b12798cc`, users
  `c5a31689-2b3d-483c-80ce-c2399a508c05` and
  `df5e7003-c988-42e0-bc4a-7ac426060ba3` (2026-08-21).
- **E1–E3, helpers/failover/knowledge:** `.claude/history.jsonl:1453`, session
  `c36fc397-b44d-4652-ae0a-39eee31f50c6` (2026-08-30);
  session `5c087816-8588-4902-b8b5-58434b26399e`, user
  `28c9682e-d700-48de-afe1-730ad24ee6f9` (2026-08-12);
  session `a7b84e5e-db13-4ab3-9ec1-ece6b12798cc`, user
  `72f036a3-94c6-4753-bb29-8a12a7db24c0` (2026-08-21).
- **F1, quest-first observation:** Codex continuation session
  `01a088ae-66c0-7560-952c-541d93d1f774_01a089c7-7ca9-7f33-b386-6b4022c4a3a7`,
  line 13242 (2026-09-10). This corroborates B3; it is not a runtime receipt.
- **G1–G3, durable operation:** Codex session `01a0bd66-96b2-7682-a605-f3693301d894`,
  2026-09-20T06:00:12.293Z; session `01a080d3-7a48-7cf3-be7b-72e79532ae4b`,
  2026-09-08T11:53:52.646Z; Claude session `5c087816-8588-4902-b8b5-58434b26399e`,
  user `a993821c-ba57-4c49-bea5-0227623d1ea1` (2026-08-12).
- **H1–H3, integrated UI:** Codex session `01a080d3-7a48-7cf3-be7b-72e79532ae4b`,
  messages `msg_01a080d7-bda6-7c73-a2b0-c3b3fa11626a` and
  `msg_01a081b4-9e13-7943-acad-4a661aa5a651` (2026-09-08);
  session `01a0bd66-96b2-7682-a605-f3693301d894`, message
  `msg_01a0bd66-1e23-79a0-b72b-7e9f8548ed1f` (2026-09-20).

KotorXID documentary corroboration: donor
`docs/dashboard-design/00-CONTINUATION-PROMPT.md`, `09-linked-entities.md` and
`10-relationship-layout.md`. Their embedded quotations are not counted as further
independent user answers. Layout 10 supersedes earlier layout choices while the
identity/proof and linked-entity obligations survive.

Local dated audit context (retained in the isolated worktree, not delivered into
the canonical checkout):
`/home/brunner56/agentdecompile-worktrees/phasor-prototype-docs-20260920/.superpowers/sdd/2026-09-20-phasor-prototype-alignment/` contains
`archive-prototype.md`, `archive-operations.md`, `archive-prototype-omissions.md`
and `hotreload-investigation.md`. The packaging, coverage exceptions and Discord
rows are supplied historical handoff requests pending source-receipt reassessment;
they are deliberately not promoted to inferred recurring intent or current proof.
