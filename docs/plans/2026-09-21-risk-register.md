---
title: Risk register — time, energy, single points of failure, performance, data loss, ambiguity
date: 2026-09-21
applies-to: 2026-09-21-portable-signatures-codecaves-generic-plan.md; the design docs; the loop
status: living; every loop iteration runs a risk grill and updates this file
---

# Risk register

The standing rule for the loop: each iteration grills for anything that costs time or energy,
any single point of failure (a slow I/O device counts), any performance drag, any path to
data loss, and any ambiguity in the plan or design — and either fixes it as a unit, schedules
it, or records why it is accepted. Rows are removed only when the mitigation is verified.

## Open

| # | Risk | Class | Evidence | Mitigation | Owner / when |
|---|---|---|---|---|---|
| R1 | Canonical repo and its object store live on a rotational USB drive at 93 % full; every git op, test and agent read goes through it (worktree creation > 5 min; routine commands hit the 120 s timeout). | bottleneck / SPOF | session timings 2026-09-21 | Full clone on the fast disk as the working canon; the USB copy becomes a synced remote; the existing off-machine remote is the backup. Do it between worker waves so no worktree is orphaned. | ✔ in effect 2026-09-22: canonical checkout is the fast-disk clone (`~/agentdecompile-nvme/AgentDecompile`; remotes `codeberg`, `gitlab`, `usb`); unit worktrees are created from it; the USB copy is fast-forwarded as a mirror |
| R2 | Fast disk at 97 % (19 GB free): a full disk kills builds, tests and worktrees mid-write. | SPOF | `df` 2026-09-21 | Measure the large consumers; move caches/venvs/fixtures off or prune; alert threshold in the loop's risk grill. Extended by the grid (design R4): the local object store has a size cap and GC of unreferenced objects with a named refusal at the cap; the USB drive is archive-only. | loop, next iteration; U121 ✔ |
| R3 | `preparation.py` calls `upsert_binary` with no digest; `ON CONFLICT … SET content_sha256 = excluded.content_sha256` **overwrites a backfilled hash with NULL** on the next prepare. The audited plan makes that hash the tie-break key and a cascade precondition. | data loss | U22 worker report; `extract.py` upsert | Unit: `upsert_binary` never clears a non-NULL `content_sha256` with NULL (COALESCE); the backfill is the only writer of a computed digest; test both. | next dispatch wave |
| R4 | The loop is bound to one session and one orchestrator context; if the session ends the loop stops. | SPOF | `/loop` semantics | All state is durable (branch, plan with ✔ marks, audit files, this register); each iteration writes a resume line under "Resume point" below; restart is `/loop` with the same prompt. | continuous |
| R5 | Full test suite exceeds ten minutes; one test reads a real image from the USB drive and times out; 7–18 pre-existing failures hide regressions; workers therefore run slices. | time / masking | worker reports | Triage unit: mark/skip the environment-bound test, fix or quarantine the pre-existing failures with receipts, keep fixtures on the fast disk, define the `unit` slice every worker must run. | dispatch after R1 |
| R6 | CI name gate fails closed without the repository secret `AGENT_DECOMPILE_NAME_DENYLIST`. | blocked CI | U21c design | The user adds the secret (contents of the out-of-repo denylist). | user |
| R7 | The plan has no units for the 5174/8080 surfaces ("draw the work", one control, corpus-first); "done" would exclude the UI. | ambiguity / scope | design docs vs Recommended order | **Mitigated by Phase 14 (pending implementation):** U104–U112 with acceptance tests, surface-ownership rule, goal done-definition (6); audit 3. | Phase 14 wave |
| R8 | Shared `refs/stash` across worktrees: a `git stash pop` in one worktree popped another branch's stash (happened once). | data loss | worker incident 2026-09-21 | Worker packets forbid stash; baselines via `git show <base>:<path>`. Keep the rule in every packet. | continuous |
| R9 | `raw_image_path` falls back to a cwd-relative path when the env var is unset, so pack bytes depend on the operator's working directory. | ambiguity / determinism | U1–U3 worker report; `ghidra_bulk.py` | Unit: refuse when the env var is unset and no absolute root is configured; record the root in the basis. | Phase 2 wave |
| R10 | Each grill round costs ~120–290 k tokens; the loop is deliberately expensive. | energy | session usage | Accepted for now; one grill per iteration, targeted by "oldest audit or most code change". | accepted |
| R11 | Slow-disk contention when many agents read the tree at once (five grills made simple commands take minutes). | bottleneck | session timings | R1 removes most of it; until then cap concurrent agents at four. | orchestrator |

## Attestation findings (real store copy, 2026-09-21)

| # | Finding | Class | Evidence | Mitigation | Owner / when |
|---|---|---|---|---|---|
| A1 | **Attestation 2026-09-21 (real store copy):** D8's `logical.build()` deletes `identity` (291k rows) and `logical_function` (74k) and *then* refuses on NULL hashes — refuse-after-wipe. | data loss | `/tmp/attest/20260921T232925Z/report.md` §2 | Hotfix: run the hash guard before any DELETE; a refusal leaves the store untouched; test on a store with one NULL hash. | hotfix wave now |
| A2 | On an already-migrated store, `backfill_recovery_family()` (D9) runs its rewrite inside Python's implicit transaction and never commits: `in_transaction=True` after `connect()`, the write lock is held for the verb's whole run (export: 150 s) and the rewrite rolls back on close. | hang / starvation (H1) | attestation §3 | Hotfix: commit the backfill; read-only verbs must never hold the write lock; assert `not con.in_transaction` after `connect()` in tests. | hotfix wave now |
| A3 | D8 residue: `match.evidence.dependencies[]`/`dependency_ancestry[]` tokens are `f"{src_id}:{addr}"` with a binary **rowid** (`match_store.py:560`); the harness on two real builds is NOT identical. | determinism | attestation §2 | Hotfix: token = `content_sha256[:16]:addr`; harness fixture generator emits dependency tokens so the gate covers it. | ✔ hotfix `a501e9d`; `ALGORITHM_VERSION` bumped `2dbd467`; stores stamped under `phase0.2` refuse until `corpus rebaseline` runs |
| A4 | The real corpus cannot satisfy the content-hash key: 89/90 rows have no `content_sha256`, only 1 raw image is resolvable under any root, 60 rows are placeholder registrations with no analysis, two analyzed rows share one `md5`. Every keyed verb (`export-hookpack`, `verify-determinism`, `logical-build`) refuses on the real store. | blocks-goal on the real corpus | attestation §1, §4 | Unit "real-corpus admission": materialize raw images from the analysis project's stored file bytes (`FileBytes`) as a backfill pass; scope the key requirement to analyzed builds (placeholders excluded from keys and basis, quarantined); merge/alias duplicate registrations with a receipt. Plan amendment to Decision 3 scope. | next wave after hotfix |
| A5 | `export-hookpack` runs the full 150 s site loop before `basis()` refuses in 1 ms; `content_hash_index`'s `ValueError` and `sqlite3.OperationalError` (lock) surface as tracebacks, not named refusals (H5). | time / hangs | attestation §2, §3 | Hotfix: basis first; both error classes → exit 2 with a named class; lock waits reported as `locked` after the busy timeout. | hotfix wave now |
| A6 | Refusal messages, backfill stdout, receipt file names and pack `binaries[].slug/game` carry plaintext slugs (product tokens); 55 % of real pack site keys are `__{lid}` ordinals. | validator 4 / key rule | attestation §4 | U21a scope: hashed slugs + counts in messages and receipt names; U30 `stable_key` is not optional (already decided). | U21a, U30 |
| A7 | Ledger row 1 holds a v1 `basis_hash` that no longer matches; no `basis_version` column beside it. | ambiguity | attestation §4 | U22 remaining: add `basis_version` to `schema_migration`. | U22 remaining |

## Hangs and starvation — the user's top class (grilled first every iteration)

| # | Risk | Evidence | Mitigation | Owner / when |
|---|---|---|---|---|
| H1 | SQLite writer starvation: several orchestrator and dashboard processes contend for the write lock; "database is locked" already observed; a long cascade or backfill transaction can starve readers and watchers, and a watcher holding a WAL read lock can block checkpoints indefinitely. | `store.py` lock-tolerance comments; U22 worker | Single-writer acceptance queue for identity/receipt/backfill writes; bounded transactions; `busy_timeout` plus a deadline that surfaces as a named stall, never a silent wait; WAL checkpoint policy with a receipt. Under the grid the store is a materialized view with one applier per view and no worker ever holds its lock (design §2.4; U123 landed the applier); H1 then demotes to the `view-stale` age metric of H11. | unit after R1; U123 ✔ / U125 |
| H2 | Analyzer/decompiler jobs hang (JVM startup, headless analysis, decompile timeouts): no global timeout policy; a hung job holds the per-program lock forever. | U65 "effectively unbounded"; `_collectors.py:194-196` 30 s timeout | Per-job deadline recorded in the basis (`analyzer.timeout_policy`), heartbeat receipts, lock lease with expiry; a hung job is reported as a named failover, not a spinner. Extended by the grid (design H9): every task kind has a recorded deadline in `timeout_policy`; the worker kills the subprocess group at the class deadline and appends `result-timeout`; three timeouts from independent keys poison the task; a slot held past deadline + 5 s is a defect (U124 ✔; U140 for the analysis path). | Phase 2 wave; U124 ✔, U140 |
| H3 | Review-lane starvation: thousands of `review` matches with no triage → nothing promotes → coverage stalls and the operator waits on nothing. | S12 | Auto-triage order, batch accept above evidence thresholds with receipts, keyboard-driven review; a starvation metric (age of oldest unreviewed row) drawn on both surfaces. | Phase 14 surfaces |
| H4 | CLI verbs and agents hang on slow I/O with no progress signal (routine commands hit 120 s; worktree creation > 5 min). | session timings | R1 disk move; every long verb streams progress receipts; the loop caps concurrent agents. | orchestrator |
| H5 | Admission cannot drain what it cannot see: `backfill`, `verify-determinism`, `export-hookpack` carry no `mutating`/`identity_scope`/`long_running` flags, so pause/resume and the lock model skip them — a stall that looks like a hang. | grill 6, `cli.py:195-215`, `jobs.py:363-386` | Catalog flags (U29 addition); admission loop honours them; test that pause drains a running backfill. | next wave |
| H6 | Compile-pool and lane starvation: one lane holding the shared corpus mutation point blocks siblings; resource-aware admission today is measured memory only. | design docs §locks | Fair scheduling at the acceptance point (FIFO with lane quotas); starvation metric per lane; failover rule draws the named unmet dependency. Note (design R8): compatibility-layer saturation on small nodes (the 2026-08-30 plateau) is a per-node cap and a persistent wineserver, measured in U133; no new row. | Phase 14 + U29; U133 |
| H7 | Grid head CAS hot-key starvation: many writers on one conditional-PUT key with no fairness; the unluckiest writer never wins. Includes disconnected duplicate work (design H12: workers on stale frontiers redo tasks — wasted compute only, bounded by checkpoint-index freshness and advisory intents). | design §2.2 | Heads sub-partitioned by task-id prefix; batched records; full-jitter backoff with rotation to another partition after 8 failures; reads never touch heads (checkpoint-index). Detect: per-head retry rate > 10 %; respond: widen the prefix for that lane (a basis-free config change). Named chaos test in U122 (50 % induced CAS failure). | U122 ✔ (backoff, rotation); chaos test named, verification phase |
| H8 | Grid verification funnel livelock: proposals arrive faster than independent-key verification drains and the same task keeps being re-offered. | design §2.6 | 4-proposal cap per task; verification-before-generation ordering; no re-offer while unverified proposals exist; verification tasks carry kill deadlines. Metric: oldest unverified proposal age per partition; respond: add verifier keys (fleet), never relax the cap. | U122 ✔ (frontier caps), U124 ✔ (verifier); U126 |
| H10 | Grid analysis slice never converges (`analysis_idle` never true because a resumed queue keeps enqueuing). | design §5.2 | Slice count cap per binary (default 10) → `task-poison` with the last packed program pinned as partial and the binary exported as unresolved; the A2.2 spike decides the default slice budget; respond by raising the budget for that image class, never by waiting. | U137 |
| H11 | Grid view applier lag masquerading as progress: the frontier advances while the SQLite view is stale and a consumer reads stale identity. | design §2.4 | `view-stale` is a named state with an age; consumers of identity (export, readiness, surfaces) read the pinned logical/identity objects by hash, not the view, when the view age exceeds a bound (default 10 min). Demotes H1 to this metric. | U123 ✔ (`view-stale` named); U111 draws it |
| H13 | Grid operator liveness: invites, revocation, toolchain mirror and view applier all on one NAT'd laptop. | design §6.1–6.2 | Fleet keys sign invites and extend revocation; fleet nodes mirror image and toolchain objects and run appliers; a single operator host on any liveness path is a defect. | U126, U129 |

## Distributed compute (design 2026-09-21, merged by audit 4 on 2026-09-22; hangs rows H7–H13 sit above)

Rows the distributed-compute design adds outside the hangs class. Ids follow the design's
§9 Register-row cells after the round-5 renumbering (design "new R7" → R13, the dangling
R6 → R12, design R8 → a note under H6, design R4 → a note under R2). The design's §9.4
scope rows S1–S5 are table-local to the design and are not register rows.

| # | Risk | Class | Evidence | Mitigation | Owner / when |
|---|---|---|---|---|---|
| R12 | Packed-program size and headless open time for a multi-MB image are unmeasured (ESTIMATE 20–150 MB from one 28 MB observation); at the high end decompile fan-out is egress-bound. | performance / unmeasured | design §5.5, §9.3 R5 | Nodes-per-program affinity cap (~3); fewer, bigger analyzer nodes; measured by U131(a) before any fan-out default is set. Closes when U131(a) files its receipt. | U131 |
| R13 | Head-store backend lacks conditional writes (bucket without `If-Match`). | SPOF / backend choice | design §2.1, §9.3 R7 | Backend choice recorded per grid; fallback is a small head table across fleet nodes holding pointers only, rebuildable by chain scan; the rebuild path is a named U122 test either way. | U159 (S3 heads), U122 ✔ (rebuild by chain scan) |
| T1 | A hijacked or provider-reclaimed fleet node with a valid key. | trust | design §2.5, §6.5 | Its records are proposals; independent-key verification; short-lived keys; revocation. Fleet compromise is never a correctness risk; the byte-emitter and self-verification tests are named in U124/U156. | U124 ✔, U126 |
| T3 | Analyzer non-determinism produces divergent packed programs; a re-baseline shifts function boundaries (S8). | determinism | design §5.3 | Two-key agreement pin; `pin-divergence` records with the lexmin rule; the pin policy is a basis field, so a re-pin is a basis change; a divergence rate above 10 % per corpus is a basis-tightening finding, never a stall. | U137, U25 |
| T6 | `mkobj` host dependence yields different target objects per node (`find_call_targets` returns `{}` on `OSError`, displacement zeroing skipped). | determinism | design §3.4 | `mkobj-target` outputs are pinned objects; `objdump` is a declared capability with a named refusal, never a silent empty path; unpinned target objects are a defect. | U136, U165 |
| P1 | Free-tier provider policy: instance-hour quotas, egress caps, idle reclamation, sustained-compute clauses; hosted-CI minutes are not a compute farm. | provider policy | design §1.4, §9.3 | Hosted-CI excluded from the default provider set; fleet nodes are preemptible by design (advisory intents); egress bounded by the nodes-per-program cap; `--idle-only` and attributed work on donors; a fleet loss stalls, never loses, work. Per-adapter egress caps are a basis-free config value (design Q24). | U129, U167 |

Notes folded into existing rows: R2 gains the grid's local object store size cap and GC
with a named refusal at the cap (design R4; U121 ✔); H6 gains the compatibility-layer
saturation note (design R8; U133). T2 (O2 false), T4 (Sybil), T5 (`/P`), T7 (donated
objects as evidence) are covered by the design's claim boundary and add no row.

## Anticipated — think-ahead rows (speculative until the risk grill verifies each)

The loop's risk grill re-examines every row here each iteration as a senior reverse-engineering
and binary-analysis architect would: confirm with evidence, promote to Open with a unit, or
record why it is accepted. New speculative rows are added whenever one is foreseen.

| # | Anticipated problem | Class | Why it will bite | Proposed mitigation |
|---|---|---|---|---|
| S1 | Identical-code folding: optimizing linkers fold identical functions to one address, so two different logical functions of one kind share `(binary, kind, addr)` — the audit-2 primary key collides again. | correctness / ambiguity | common with modern linkers and in release builds | `identity` allows N logical ids per address with relation `fold`; the pack instance carries `folded_with[]`; resolve in the next plan grill (contradicts audit-2 decision 3). |
| S2 | Packed / DRM-wrapped builds: on-disk bytes are not the executing code; file-derived windows are garbage. | correctness | frequent in the target class | Unpacked-image ingestion path; `unpack_state` recorded; export refuses masked windows for packed images unless computed from the unpacked image. |
| S3 | Rebased images with **unmasked** windows: every verify fails on a reloc-bearing image loaded at a different base → false `unresolved`. | correctness | today's `expected_bytes` are unmasked | Unmasked windows are never `verify` members for images with relocations until U4 masking lands; the resolver rebase-adjusts absolute operands or skips the member with a reason. |
| S4 | Functions already hooked by other software (overlays, patchers): entry bytes are a `jmp` → verification fails. | coexistence | very common at runtime | Detect the occupied prologue, report `contested(occupied)` with the observed owner bytes; ownership registry (U57/U74) admits foreign claims. |
| S5 | Adjustor thunks and multiple inheritance: vtable slots point at thunks with per-build addresses. | correctness | any C++ engine | Slot correspondence resolves through thunks to the target method identity; a `thunk_of` relation. |
| S6 | Optimization-level and PGO variance (inlining, hot/cold splitting, jump-table shapes) makes masked windows and CFGs unrecognizable across builds. | coverage expectation | release vs debug builds | Coverage floor per build in the readiness report; ladder members caller/callee/data-xref carry the load; telemetry on which member resolves what. |
| S7 | x64 ABI depth: XMM args, struct-by-value classification, shadow space, varargs register count — descriptors can be correct-looking and wrong. | correctness | U13c thunks depend on it | U64 recompile-and-diff on real toolchains is mandatory before a call stub is emitted; refuse otherwise. |
| S8 | Analyzer version drift silently changes function boundaries and storage; identities computed under two versions are not comparable. | determinism | every Ghidra upgrade | Store bound to one analyzer version (migration 2 captures it); upgrade = explicit U25 re-baseline. |
| S9 | Decoder choice limited to x86 forces a U4 rewrite when a non-x86 build arrives. | rework | plan targets other classes | Choose a multi-arch decoder library with Python and C++ bindings in U4. |
| S10 | Cascade scaling: pairwise matching across many builds × tens of thousands of functions as recompute-all takes days. | performance | corpus growth | Incremental cascade per new build with hash-blocked candidate sets; budgets and receipts; measure on the reference corpus. |
| S11 | Corpus DB and analysis projects have no backup and sit on a USB drive; WAL under several writers already reports "database is locked". | data loss / SPOF | hours of analysis at stake | Snapshot verb (`VACUUM INTO` to the other disk, content-addressed); single-writer acceptance service for identity/receipt writes. |
| S12 | Review-lane starvation: thousands of `review` matches nobody triages → nothing promotes → coverage stalls. | throughput / UX | any real corpus | Auto-triage order, batch accept above evidence thresholds with receipts, keyboard-driven review in the 5174 design. |
| S13 | Synthetic fixtures do not exercise real compiler idioms; green on synthetic, wrong on real. | verification | every unit so far | Reference corpus: an open-source program built at O0/O1/O2/Os with two compilers; legal, generic, deterministic; used by ladders, divergence, struct and ABI tests. |
| S14 | Packs carry original byte windows / cave `original_bytes`; packs plus Lua inject code. | legal / security | — | **Deprioritized by the user 2026-09-21: copyright and trust are assumed.** Keep short windows; no unit. |
| S15 | Anti-cheat bans for detours in multiplayer titles. | user harm | — | **Deprioritized by the user 2026-09-21: niche; not now.** |
| S16 | String-anchored locators break on localized builds. | correctness | localized releases | Anchor only to ID-stable strings (resource ids, script names); U85 classifies. |
| S17 | Ambiguity of "byte-accurate" when sibling builds used different compilers: parity receipts cannot be shared across toolchains. | ambiguity | mixed corpora | Parity receipts keyed by toolchain identity; never borrowed across it (extends U62). |

## Resume point

- Canonical checkout: `/home/brunner56/agentdecompile-nvme/AgentDecompile` (fast disk, R1 done), branch
  `feat/portable-signatures-codecaves-generic`; the USB path is the `usb` mirror. Landed this iteration:
  U125 (`86b9d6d`, `fe9d563`), 3d U25 + A3 bump (`2dbd467`, `ca7fdb6`), audit-4 docs (`708683e`).
  In flight: A4 admission (`unit/a4-admission`, worktree `~/agentdecompile-worktrees/unit-a4-admission`).
  Attestation copies live under `~/agentdecompile-nvme/attest/<ts>/` (never the live store); the
  latest iteration's receipts are in the directory named by `/tmp/attest/LATEST_ITER`.
  Next: integrate A4 (scope U25's `stored_basis_rows` to admitted rows at the merge; renumber the
  migration if both took v3), attest the admit → rebaseline → backfill → verify-determinism →
  export-hookpack chain, then U28x/U168, U104 (H5), U21a/U21b, U19a, adapters (U158, U126, U159–U165).
  Round-4 survivors F1–F9/D1–D14 and the foundations audit are still pending application.
