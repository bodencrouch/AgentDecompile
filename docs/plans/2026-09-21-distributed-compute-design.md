---
title: Distributed compute design — agentdecompile_grid (one-command donated and free-cloud compute)
date: 2026-09-21
status: design synthesized by the design workflow (4 architectures × 3 judge lenses, 9 stage analyses); grill round 5 applied and the licensing reasoning removed (audit 4, 2026-09-22); Phase 15 joined the plan in walking-skeleton order; this file is the detailed specification behind the plan's Phase 15 bullets
applies-to: 2026-09-21-portable-signatures-codecaves-generic-plan.md (program thesis 2–5)
---

# Distributed compute design: `agentdecompile_grid`

Status: design input to convergence (plan, design, diagrams); amended 2026-09-22 by audit 4 (round 5 amendments A2/A3/A5/A6; licensing reasoning removed per the user directive; §7.5 and §8 restated for the walking skeleton).
Date: 2026-09-21. Repo head observed: `a501e9d` on `feat/portable-signatures-codecaves-generic` (the tasking text names `f6f008c`, an ancestor three commits back; every `path:line` below is against `a501e9d`; the skeleton commits cited in 7.5 and 8 are at `a4e4aca`).

## Scope note (governing set)

Per the user's correction, `STRATEGY.md` is **not** an input to this design and no `STRATEGY.md` edit is proposed. The loop charter records the same rule (docs/plans/2026-09-21-loop-charter.md:78-83: the strategy is rewritten from the plan, design and diagrams once they converge, never edited while they converge). One code docstring cites the strategy file (src/agentdecompile_recovery/corpus/whole_image_relink.py:1); that citation is reported here as data and is not used.

Judged against: the program thesis (docs/plans/2026-09-21-portable-signatures-codecaves-generic-plan.md:48-70), the Autonomy rule (plan:114-125), the determinism basis (plan:455-481), U65/U66 (plan:1512-1521), U110 (plan:1918-1922), the risk register (H1, H2, H5, A2, R1; the rows this design adds are merged there under "Distributed compute"), the two exchange docs (docs/plans/2026-09-08-donated-compute-work-exchange.md, docs/plans/2026-09-10-exchange-submission-durability.md) and the landed package `src/agentdecompile_recovery/exchange/`. Stage labels use the inventory's own vocabulary.

Conventions: every number is either MEASURED (a receipt or attestation exists and is cited) or ESTIMATE (basis stated). No product, game, binary or project names appear; builds are named by content hash and slugs are hashed (src/agentdecompile_recovery/corpus/cli.py:18-20). Generic words are used for tools: "the analyzer" (JVM-hosted program analysis), "the era-exact toolchain" (closed-source compiler and linker run under a compatibility layer), "the parity checker" (the native object-diff tool), "the similarity index" (the signature database).

The five user requirements and the five thesis points are restated where each is discharged; section 11 is a compliance table.

---

## 1. Decision

### 1.1 Architecture in one paragraph

A new top-level package `src/agentdecompile_grid/` (CLI verb `adgrid`) provides three layers, only one of which is mutable, and that one is a pointer: (1) a content-addressed **object store** (sha256-keyed immutable blobs: inputs, sources, objects, packed programs, receipts, log records, checkpoint indexes) with local-directory, S3-compatible-bucket, static-mirror and peer-HTTP adapters; (2) **per-partition append-only logs** of signed, hash-chained records (partition = lane x binary content hash x task-id prefix), from which the **frontier is a pure function** (tasks whose result object does not exist and whose advisory intent has lapsed); (3) **head pointers** per partition updated by compare-and-swap. Every task is `task_id = sha256(canonical(kind, kind_version, input hashes, params, basis_hash))` and its result lives at `objects/results/<task_id>`, so "done" is an existence check, identical-basis re-runs are cache hits (U66) and a change to a basis field invalidates exactly the ids of the kinds whose declared projection names that field (2.8; U25 stays the pack-level rule). Leases are advisory TTL objects because a duplicated or lost lease can only waste compute, never produce a wrong commit. **Every result from every node is a proposal**, including results from the operator's own fleet nodes; a record enters the verified stream only when a machine check by an independent key passes (section 2.5). The corpus SQLite store becomes a materialized view replayed from verified records by one applier per partition; nothing that computes ever holds its write lock. The pipeline's task kinds live in a thin adapter module that imports from `agentdecompile_recovery`; the grid package never imports the pipeline, so it is reusable for other CPU/IO-heavy work (thesis 2).

### 1.2 Package name

`agentdecompile_grid`, CLI `adgrid`. "Grid" is the established word for donated, heterogeneous, capability-labelled compute (the volunteer-computing lineage) and names no pipeline concept. "Mesh" implies peers talk to each other (they do not: every node is outbound-only and talks to objects and heads); "hive" and "swarm" imply a queen or a central scheduler, which this design removes; "workers" names a role, not a layer.

Layout:

```
src/agentdecompile_grid/
  objects/    content-addressed store adapters (local dir, S3-compatible with conditional PUT, static mirror, peer HTTP), GC, size cap
  log/        record schema, hash chain, head CAS with sub-partitioning, frontier derivation, checkpoint-index, compaction snapshots, local outbox
  tasks/      task-kind registry, canonical encoding, budget classes, kill deadlines
  worker/     join (attach-first), capability canaries, lease loop, sandbox, outbox flusher
  verify/     independent-key verification loop, masked-COFF hasher, parity-check runner, proposal caps
  view/       replay of the verified stream into SQLite (and the similarity index) as materialized views
  fleet/      cloud-init rendering, provider adapters, fleet manifest as objects
src/agentdecompile_recovery/grid_lanes/   pipeline task kinds (adapters; import direction recovery -> grid only)
```

Packaging: a separate, slim distribution `agentdecompile-grid` (pure Python plus a signing library, no analyzer bindings, no dashboard). This is a prerequisite unit, not an assumption: today `pyproject.toml:72-76` declares four entry points and none is a grid CLI, `pyproject.toml:60` puts the analyzer bindings in the base dependency set, and `pyproject.toml:121-123` finds only `agentdecompile_cli*` and `agentdecompile_recovery*`, so a `src/agentdecompile_grid/` package would not ship at all without a packaging unit (U120).

### 1.3 The one command, per donor class

All four donor classes run the same verb; what differs is what the canaries prove. A node that proves a capability by canary is offered the lanes that capability serves and fetches the input objects those tasks name; there is no other fetch rule (6.3).

| Class | Command | What it proves by canary | Lanes it can be offered |
|---|---|---|---|
| No toolchain (any stranger; python only) | `curl -fsSL https://<fabric-host>/join.sh \| sh -s -- https://<fabric-host>/g/<fabric-id>#<invite>` (or, with uv present, `uvx agentdecompile-grid join <url>`) | `python` (hash a fixture), `parity:<hash>` if the parity checker binary is fetched (hash-pinned release; fixture pair must yield the pinned receipt), `llm` if a key is configured (reachable, never proven) | match-score-shard, parity-check (advisory), permute-text-generate, rewrite, logical-build-shard, export-site-shard (advisory), place-check/splice re-derivations (advisory) |
| Toolchain-capable (an owned install or a fetched toolchain object; native or containerised) | same command plus `--with toolchain <hash>` (fetches the content-addressed toolchain object and proves it by canary) or `--toolchain-path <dir>` for a copy the donor already owns | `toolchain:<toolchain_identity_hash>`: compile a fixed TU, masked-COFF hash must equal the pinned value; persistent wineserver probe; per-node concurrency cap measured | compile-attempt, search-shard, score-candidates, parity-check, link (fleet only) |
| Analyzer-capable (an owned install or a fetched analyzer bundle) | same command plus `--with analyzer` (fetches a runtime and the analyzer as a content-addressed toolchain object, ESTIMATE 1-2 GB, basis: inventory replica note) or `--analyzer-path <dir>` for an install the donor already owns | `analyzer:<version>:<options_hash>`: open a fixture packed program headless, hash its function inventory, must equal the pinned value | decompile-chunk, bsim-sigs, extract-graph-facts, analysis-slice; the packed program is fetched like any other input, and the `program:<gzf_hash>` affinity plus the nodes-per-program cap (5.5) bound egress |
| Browser tab | open `https://<fabric-host>/g/<fabric-id>/donate`, click Contribute (opt-in, attributed, one click to stop) | `browser`, `parity-wasm:<hash>` (fixture pair), `llm` (own key, stays in worker memory) | rewrite, parity-check (advisory), permute-text-generate |

Attach-first semantics (user rule: exclusive lock is not join): `join` first looks for a running local agent at the well-known socket / `http://127.0.0.1:<port>/adgrid` and attaches (adds lanes, prints status); it bootstraps one only when none exists; `EADDRINUSE` is reported as "already owned" and never retried as a start. Ctrl-C or `adgrid leave` drops intents; the local object cache is the only state and may be deleted at any time. `--idle-only` and `--cores N` are the two donor knobs.

What `join` installs by default: the slim package (hash-pinned), the parity checker binary (hash-pinned), a compatibility-layer probe. Nothing else. A container is one packaging option for the fleet image, never a donor requirement (user baseline prefers non-container; a bare compatibility-layer prefix tarball is the default toolchain object).

### 1.4 Free cloud node and the operator's fleet bootstrap

Free cloud node: the identical join command placed in cloud-init user-data with a fleet invite. Operator bootstrap, one command:

```
adgrid fleet up --provider <adapter> --count N --role fleet --lanes analyzer,toolchain
```

renders the user-data, creates instances through the provider's CLI/API (credentials via the user's secret-session path, never prompts), and records the fleet manifest as objects. `fleet down`, `fleet replace`, `fleet status` are the same verb family. Lane placement is by canary, not assumption: the x86 micro tiers run the toolchain under the compatibility layer (1 vCPU / 1 GB class, ESTIMATE, basis: provider free tiers), the always-free ARM tiers (large RAM) run the analyzer; an ARM node that cannot pass the toolchain canary is never offered toolchain work. Hosted-CI minutes are excluded from the default provider set (terms of service). A fleet node is **not trusted by role** (section 2.5); the fleet invite differs from a donor invite only in what the node mirrors by default (image-bearing, packed-program and toolchain objects, 6.3) and in that fleet keys may sign further fleet invites, run verifiers and run view appliers, so the operator laptop is not a liveness single point.

### 1.5 Why the others lost, and what was grafted from each

**Hive (durable-stream broker, total 17).** Lost on requirement (4) and the register's top class: a three-node replicated broker on reclaimable free-tier VMs is a stateful service the operator must run correctly, and its quorum-loss mode (two nodes reclaimed, the survivor still TCP-reachable) is a hang without a named refusal. Its compile-lane verification hashed the donor's returned object against the target slice, which the byte-emitter attack defeats (copy the target bytes, attach junk source). Its acceptance writer funnelled every result through one SQLite consumer on the USB drive. **Grafted:** (a) the basis inside the work address on both ends: publish refuses a task whose `basis_hash` is not admitted, and the verifier refuses a result whose basis differs from its task's, closing the confirmed `derive_unit_id` collision (src/agentdecompile_recovery/exchange/store.py:160-170 digests the payload alone); (b) capability claims enforced as permissions bound to the credential, so a false claim cannot be offered that lane, plus a `rejoin`/reprobe step so a donor who gains a capability later is not stranded; (c) the store-as-projection rule: `adgrid view materialize` replays the verified stream from record 1 into a fresh database.

**Mesh, gossip variant (peer-to-peer CRDT work list, total 18).** Lost on operational simplicity and on hidden serial work: a VPN-class overlay and control plane, a two-peer blob-durability rule that nobody can satisfy while the operator is offline, deterministic global task selection that makes every free slot pick the same advert (thundering herd), and an unbounded grow-only record set on 1 GB nodes. Its acceptance path ("hash equality of two independent receipts") is a quorum of two under another name. **Grafted:** (a) `toolchain_identity_hash` = sha256 over the sorted `(relative path, sha256(content))` pairs of the **toolchain manifest**: every file under the toolchain root's compiler-and-linker binary directory (driver, front-end and back-end modules, linker, the shared libraries they load) and under its link-input library directory. Headers are excluded because the TU is header-free text (section 4 row 3); nothing outside the manifest (documentation, installers, registry or prefix state, file times, the install path, the compatibility layer's own files) enters the hash. This replaces path+size+mtime identity (src/agentdecompile_recovery/source_parity_synthesize.py:21705-21722; src/agentdecompile_recovery/source_plugin_runner.py:369-392, unused `path_sha256` at :394). The canary fingerprint (masked-COFF of the pinned probe TU, 1.3 row 2) gates the `toolchain:<hash>` capability and is **not** part of the identity, so under O2-false (T2) caches still key on the toolchain, never on the host. The default toolchain object (the bare prefix tarball, 1.3) carries the manifest as metadata; the object's own hash is not the identity; (b) resume = adverts minus receipts with advisory claims, which this design already had; (c) the observation that a record set needs compaction: this design adds signed checkpoint snapshots that peers prune below (section 2.3).

**Mesh, CRDT-document variant (total 18).** Lost on trust and reversibility: "two independent donors agree, a fleet node countersigns without recomputing" is Sybil-trivial under open enrollment; G-Set identity edges cannot be retracted once a caught lie has fused two components; a determinism-defect receipt with no emitted value is a human gate; verifier authority is a key delivered through instance metadata on the least trusted machines. It also opted the donors' input path into one bucket's egress quota. **Grafted:** (a) the capability probe that doubles as the continuous cross-machine determinism measurement (every joining toolchain node compiles the same probe TU and signs the masked-COFF hash, so O2 is measured for free on every join and disagreement is a named defect before any lane depends on it); (b) leases as hints with the fence retained only so a stale renewal cannot evict a newer holder; (c) the rule that a determinism defect must still emit a value (ordered candidates, refuse at use time) rather than stall.

**Grid's own judged flaws, fixed here rather than inherited.** (1) Fleet keys trusted by role: removed; fleet output is a proposal, verification is independent-key (section 2.5). (2) `artifact-pinned` first-wins on the analyzer output: replaced by a deterministic pin check with the pin policy recorded in the basis (section 5.3). (3) Hot-key CAS starvation on one head per (lane x binary): heads are sub-partitioned by task-id prefix, records are batched, backoff is stated (section 2.2). (4) Verification funnel livelock: proposals per task are capped, the frontier orders verification before generation, and a task with N unverified proposals is not re-offered (section 2.6). (5) Budget classes as labels: the worker owns a hard kill deadline per kind and emits a timeout record (section 2.7). (6) Operator as liveness single point: fleet keys sign fleet invites, run verifiers and appliers; the toolchain object is served by any fleet mirror (section 6). Corrections from the stage analyses that contradict grid's premises are adopted: JVM-free extraction covers names/functions/comments/memory/composites only, not references or instructions (src/agentdecompile_recovery/ghidra_db/program.py:49-52; features at src/agentdecompile_recovery/corpus/features.py:144-241 need the live program); the busy_timeout citation is src/agentdecompile_recovery/corpus/store.py:178-183, not the exchange store; preprocessed-input caching is not load-bearing for the bulk lane because the TU is already header-free text (section 4).

---

## 2. Coordination state

### 2.1 Three layers; one mutable; the mutable one is a pointer

**Objects.** sha256-addressed, immutable, write-once (`If-None-Match: *` on buckets, atomic rename on disk). Nothing is ever overwritten, so replication is copying and any node may serve any object. Reads are static files (cacheable, mirrorable), which is the structural fix for the observer-path saturation the exchange still documents as outstanding (src/agentdecompile_recovery/exchange/routes.py:12-16). Objects carrying image bytes, packed programs or the toolchain are tagged in metadata so mirrors know what to hold and GC knows what to keep (section 6.3); any node whose offered task names one as an input fetches it. The local object store lives on the fast disk with a size cap and GC of unreferenced objects; the USB drive is an archive replica only (R1/R2; this session's own read-only commands on that drive exceeded 120 s).

**Logs.** A record is `{prev_hash, kind, task_id, node_key, sig, ts, payload_hash}`; kinds: `task-offered`, `intent` (advisory lease with TTL), `result-proposed`, `result-verified`, `result-refuted`, `result-timeout`, `artifact-pinned`, `pin-divergence`, `checkpoint-index`, `snapshot`. Records are objects; the chain of a partition is verifiable offline. A partition never needs ordering against another partition.

**Heads.** One small key per partition holding the latest record hash, updated by compare-and-swap. Primary backend: the bucket's conditional PUT (`If-Match`) so the operator runs no service; fallback: a two/three-node Postgres-class head table across fleet nodes (thesis 4 names exactly this; it holds pointers only). If the head store is lost, any node rebuilds heads by scanning record objects for the longest valid chain; workers keep computing off their last `checkpoint-index` and queue results in a local outbox.

Why it is not a single stateful device: correctness never depends on the mutable layer (task ids are derivable, results are idempotent by content, a stale frontier only causes duplicate work); the mutable layer is sharded into hundreds of independent keys; every layer is rebuildable from the immutable one; no process holds an exclusive lock over the corpus.

### 2.2 Partitioning, batching and fairness (fix for hot-key CAS starvation)

A partition is `(lane, binary content_sha256, task_id_prefix)`. The prefix width is chosen per lane from the expected task count so that no head sees more than ESTIMATE 200 tasks per hour of steady state (basis: a conditional PUT round trip of 50-200 ms and a target of under 10 % retry rate): compile-attempt on a 12.8k-function build uses a 6-bit prefix (64 heads, ~200 tasks each); parity-check the same; match shards a 4-bit prefix; analysis, link and export-merge a single head. Workers append **batches**: a worker accumulates records for a partition in its outbox and appends one batch record (a list of record hashes) per flush interval (default 5 s) or 64 records, whichever first. CAS failure uses full-jitter exponential backoff (base 100 ms, cap 5 s); after 8 consecutive failures on one head the worker rotates to another partition it holds work for and retries the first later, so no writer can starve indefinitely on one key while others progress. Reads never touch heads: workers derive the frontier from the partition's latest `checkpoint-index` object plus any records newer than it, and `checkpoint-index` objects are written by whichever node appended last if the index is older than 60 s (idempotent: two nodes writing the same index produce the same object).

### 2.3 Compaction

Record sets grow without bound otherwise (a defect the mesh judge named). A `snapshot` record, signed by an operator or fleet key, carries the partition's current frontier set, the verified-result set and a retired-set Merkle root; peers may prune records below the snapshot. A prior-basis partition is snapshotted once and archived. A 1 GB node holds at most the latest snapshot plus tail per partition it serves.

### 2.4 The SQLite store as a materialized view

`adgrid view materialize` replays `result-verified` records in partition order with one applier thread per view and bounded transactions (at most 200 rows or 2 s each, ack after commit), rebuilding: `match` rows from `match-rows` objects (replacing the DELETE+INSERT at src/agentdecompile_recovery/corpus/propagate.py:65-121), `identity`/`logical_function` from pinned `logical-build-merge` and `identity-merge` delta objects (replacing the wipe at src/agentdecompile_recovery/corpus/logical.py:128-130 and the `BEGIN IMMEDIATE` at :461/:534 of dashboard/workflow.py), `func_knowledge` from `decompile-chunk` results (replacing the per-function commit at src/agentdecompile_recovery/corpus/dashboard/workflow.py:600-609), `binary.content_sha256` and basis columns from `image-registered` and `basis-stamped` records (replacing src/agentdecompile_recovery/corpus/backfill.py:170's per-row commit under a long-held lock, A2), compile receipts from `compile-attempt` receipts, and the similarity index from `bsim-merge` objects via the commit verb (src/agentdecompile_recovery/corpus/dashboard/actions/catalog.py:418). The applier is the only writer; a foreign writer holding the lock delays the view and produces a named `view-stale` state, never a stalled worker (H1 removed by construction; today `busy_timeout` 30 s at src/agentdecompile_recovery/corpus/store.py:178-183 is the only defence). The view can be deleted and rebuilt; ESTIMATE minutes for the reference corpus (basis: measured logical.build 20-22 s and export 122-200 s bound the row volumes). The cross-place `should_write` decision (src/agentdecompile_recovery/corpus/cross_place.py:46-52), which today reads destination filesystem state, moves into the applier so placement objects stay pure. The similarity index (a database-server-backed service) is likewise a view: `adgrid view materialize --lane bsim` replays verified merged-signature objects through the commit verb (3.3-9.6 s per program MEASURED); losing the cluster is a rebuild, never a loss of pipeline state.

The landed exchange store's lease/fence/idempotency vocabulary (src/agentdecompile_recovery/exchange/store.py:1-40, :668-670, :1062-1063) is kept as the intent-record vocabulary; its persistence (authoritative state in one process's memory behind one `asyncio.Lock` at :421, full snapshot rewrite per mutation at :552, the 64 KiB artifact cap justified by that rewrite at routes.py:36-41) is the O(n)-per-mutation single point thesis 4 forbids and is retired. The HTTP routes survive only as the browser lane's gateway.

### 2.5 Trust-the-hash, applied to everyone (fix for fleet-by-role)

The landed claim boundary says the compile-verify gate is "the sole proof mechanism for any artifact a remote fulfiller reports" (src/agentdecompile_recovery/exchange/store.py:69-74). A free-tier node the operator rents is a remote fulfiller. So:

- **Every result is a proposal**, whatever key signed it. Keys attribute, rate-limit and revoke; they never decide truth.
- **What must be verified before it enters the verified stream:** anything identity-bearing or reused as an input by another partition: byte-exact compile receipts, pinned analyzer artifacts, match-rows objects, logical-build and identity-merge deltas, placement objects, merged signature objects, export fragments, image receipts.
- **What need not be verified:** a result consumed only by the next task in the same chain (a non-byte-exact `.obj` and its diagnostics feeding repair round k+1; a decompile chunk feeding compile; a proposal from a search shard). Its consumer recomputes from it, and a wrong value is refuted downstream at the compile gate or the parity check. Trusting nothing costs nothing here because nothing is trusted.
- **How verification is done:** (a) hash lookup when the check is a pure recomputation whose output hash is known (masked-COFF equality against a pinned expected hash when O2 holds; parity-check receipts; export fragments; logical shards; placement objects) run by a node holding a key **different from the producer's**, on a different node; (b) recompile + parity check on an independent-key toolchain node for byte-exact claims (ESTIMATE 1-3 s each, basis: sub-second compile plus 0.06 s MEASURED native parity floor); (c) for the analyzer's pinned artifact, agreement of the canonical function-inventory hash between two independent analyzer keys (section 5.3). Independent-key means: not the producing key and not any key in its invite ancestry (nor the reverse). Because fleet keys may sign fleet invites (section 6.2), the fleet must always hold at least two keys with disjoint invite ancestry, otherwise the two-key pin (section 5.3) has no valid pair; the operator's two initial keys satisfy this and U126 asserts it.
- **Cost:** a second run of the verified fraction only. Byte-exact wins are ESTIMATE 1-20 % of compile attempts (basis: 77-97 % compile success and the leftover counts at src/agentdecompile_recovery/corpus/ghidra_bulk.py:965-970 and the text-permuter status 17 closed / 1,657 unclosed), so the verification mass is a fraction of the compile mass; pinned artifacts double the analysis stage (ESTIMATE +2.5-15 node-hours per corpus, parallel across binaries); logical/export/placement re-derivations are seconds.
- **The asymmetry rule per lane** (2026-09-08 doc §1): a claim is accepted from a key only where verifying it is cheaper than producing it (byte-exact after a repair chain or search: 10-100:1; LLM rewrite: ~1000:1; parity check: 1:1 so a parity-check receipt from an unverified key is a priority hint; plain "it compiles": 1:1 so it is a hint and never identity evidence). A negative verdict from any key never marks anything failed; it lowers that key's own priority weight only.
- **What can never be evidence:** any self-reported verdict; a donated `.obj` as proof of a source (the byte-emitter attack: submit the target's own bytes); a donated `.bin` placement artefact (it is *defined* as bytes equal to the shipped image at src/agentdecompile_recovery/corpus/verify_recovered_byteexact.py:212 and src/agentdecompile_recovery/corpus/whole_image_relink.py:109-110, so a copy passes every gate); the analyzer's output as a claim (it is a pinned input, section 5); anything with an absolute path (`assert_portable_payload`, exchange/store.py:176-203, kept as a publish-time check); anything whose projection for its kind differs from the current basis's (2.8).
- **No quorum, no credit, no reputation** (2026-09-08 doc §2 :49-50). Two independent runs agreeing on a *deterministic* function's output is a recomputation check, not a vote; it is used only where the output is a pure function of pinned inputs and the check is cheaper than a third path. It is never used for stochastic lanes.

### 2.6 The verification frontier (fix for the funnel livelock)

Proposals per `task_id` are a set capped at 4 (`result-proposed` beyond the cap is dropped at append time with a named reason). The frontier orders work as: verification of pending proposals first (a `verify-<task_id>` task with `caps_required` = toolchain or python by kind, offered to independent keys), then generation. A task with one or more unverified proposals is not re-offered for generation until its proposals are refuted or the cap is reached and all are refuted. Verification tasks carry their own kill deadline. This bounds the unverified set per partition to 4 x |tasks| objects and guarantees that generation cannot outrun verification indefinitely: when verification capacity is the binding resource, generation stops being offered and idle donors see "nothing to do" instead of producing unverifiable proposals.

### 2.7 Budgets are kill deadlines, not labels (fix for hangs)

Budget classes: micro (wall 60 s), chunk (300 s), large (3600 s; link, analysis slices; fleet only). The **worker** enforces them: every task runs in a subprocess group with a hard kill at the class deadline (SIGTERM then SIGKILL after 5 s), the analyzer and compatibility-layer processes included; on kill the worker appends `result-timeout {task_id, kind, deadline, node_key}` and releases the intent. Repeated timeouts on one task id (3, from independent keys) produce `task-poison` and the task is exported as unresolved with its reason (Autonomy rule: nothing waits for a person). Per-kind deadlines are recorded in the basis `timeout_policy` field so a timeout is a named, replayable failover (H2, U65). The parity checker's node path gets the timeout it lacks today (src/agentdecompile_recovery/corpus/objdiff_check.py:42, bare `subprocess.run`). Today's shape this replaces: the per-program analysis lock with no timeout (src/agentdecompile_cli/mcp_utils/program_analysis.py:127-138, acquired at :135) inside the dashboard's `CONTEXT_LOCK` (src/agentdecompile_recovery/corpus/dashboard/mcp_bridge.py:19) and the 600 s idle wait (:249-261).

### 2.8 Determinism basis and content addressing

Each `kind_version` declares `basis_fields(kind)`, the list of basis field **paths** (plan:455-481) its output depends on; `basis_projection(kind) = sha256(canonical({path: basis[path] for path in basis_fields(kind)}))` and `task_id = sha256(canonical(kind, kind_version, input hashes, params, basis_projection(kind)))`. Every task record and receipt carries both the full `basis_hash` of the run that produced it (provenance; U25 supersession receipts) and the projection hash (admission: publish refuses a task whose projection is not admitted, the verifier refuses a result whose projection differs from its task's, a consumer refuses an input whose projection for its kind differs from the current basis's). A change to a field outside a kind's projection invalidates nothing in that kind (ledger: never redo completed work); a change inside it invalidates every id of that kind. Wall deadlines (`timeout_policy.<kind>.wall_s`) enter no projection: a task killed at its deadline writes nothing (2.7), so a deadline never shapes an output; `timeout_policy` fields enter a projection only where a timeout is recorded as data (U65). The analysis slice budget (`slice_budget_s`) stays a task param, never a projection field: completed slices are reused because each slice's output packed program is a content-addressed input of the next, so a raised budget re-keys only the slice that resumes from the last checkpoint object (Q19). The task-kind registry is the single place the lists live (the skeleton's `tasks.registry` declares the slot; the lists themselves are the plan's U158): every registered kind declares a `basis_fields` list, explicitly empty only where the table says so, or is refused registration by name.

| Kind family | `basis_fields` |
|---|---|
| compile-attempt, verify-byte-exact, repair-context, permuter-case, score-candidates, verify-win, link | `toolchain_identity_hash`, compiler profile, flags (link: `LINK_FLAGS`) |
| search-shard | the row above plus `seeds` |
| import-image, analysis-slice, pin-artifact | `analyzer.version`, `.processor_spec_hash`, `.compiler_spec_ids`, `.options_hash`, `.loader_revision`, `pin_policy`; `timeout_policy.analysis.per_file_s` only if A2.2 records non-convergence (then the budget shapes the artifact) |
| inventory, extract-names-facts, extract-graph-facts, decompile-chunk | the five `analyzer.*` fields; decompile-chunk adds the pinned decompiler option set and `timeout_policy.decompile.per_function_s` (timed-out rows are data) |
| bsim-sigs, bsim-merge, bsim-query-shard | the five `analyzer.*` fields, `external_channels.bsim_generator_revision`, the template id, `threshold_params.BSim` |
| match-slice, match-anchor, match-score-shard, match-assign, match-finalize, logical-build-*, identity-merge, cross-place-recipient | `algorithm_version`, `threshold_params`, `decoder`, `masking_rule_version` |
| mkobj-target | `masking_rule_version` |
| parity-check | explicitly empty (`verifier_id` and both objects are inputs) |
| site-key-table, export-slice, export-site-shard, export-merge, window-index, window-shard, verify-determinism, place-check, splice-shard, image-join, image-receipt | `masking_rule_version`, `algorithm_version`, `filler_set`, `data_packs`, `decoder` |
| rewrite, permute-text-generate | compiler profile |
| bsim-commit | explicitly empty (keyed on the merged XML hash and the index URL; the XML's id already carries the signature projection) |
| register-image | explicitly empty (the output is the raw bytes' own hash) |
| stamp-basis | the full basis by definition |
| `verify-<task_id>` (2.6) | the projection of the kind it verifies |
| `repair-step` | not registered: derived, never offered (3.3); the `compile-attempt` it derives carries the compile row |

Old results remain as an archive under their partition snapshot; nothing under a different projection for its kind is reused. Receipts carry `{stable_key, build, operation, member, outcome}` so both surfaces replay them (U66/U110). Every task validates its `basis_hash` and capability before fetching inputs (the A5 lesson: refusal first, at 1 ms, not after 150 s). Identity-bearing outputs are pure functions of pinned inputs (the cascade is a pure function of the rows per src/agentdecompile_recovery/corpus/determinism_harness.py:1-25), so the grid determinism harness is: same inputs on two nodes give identical task ids and identical result hashes, and where the producer is not deterministic (the analyzer), the divergence is a recorded object, never a silent merge.

---

## 3. Micro-task catalogue per stage

Shape of every task: `{kind, kind_version, inputs: {name: sha256}, params (canonical JSON, sorted keys), basis_projection (and basis_hash on the record, 2.8), caps_required, budget_class}`. Durations: MEASURED where a receipt exists, otherwise ESTIMATE with basis. "Checkpoint" says what survives a node dying mid-task. "Serial" says what is inherently ordered and why. "Who" says which keys are offered the task (all outputs are proposals regardless).

### 3.1 Stage 1 extract: analyzer import and auto-analysis per binary

Today: one JVM call with no wall-clock bound in the live dashboard path (src/agentdecompile_recovery/corpus/dashboard/preparation.py:1476-1482), a per-program lock with no timeout (src/agentdecompile_cli/mcp_utils/program_analysis.py:127-138), idle poll 600 s (:249-261); the ephemeral headless path discards the analyzed database (`-deleteProject`, src/agentdecompile_recovery/ghidra_context.py:200-212). MEASURED import 1.1-26.7 s (n=3), readiness probe max 786.7 s, `mcp.analyze-program` 20 of 20 failed. ESTIMATE full analysis 5-30 min per multi-MB image (basis: the 786.7 s probe, acquire.py:144's "many minutes", H2).

| Kind | Inputs -> outputs | Duration | Class / who | Checkpoint | Serial |
|---|---|---|---|---|---|
| `import-image` | image sha, loader/language/cspec ids, options_hash -> packed program gzf_0 (no analysis; headless import then export via `write_packed_file`, src/agentdecompile_recovery/ghidra_db/packed.py:271) | MEASURED 1.1-26.7 s | micro / analyzer-capable (the image is an input object) | result object | one process per image; seconds |
| `analysis-slice` | gzf_k, options_hash, slice_budget_s, k -> gzf_{k+1} + `{analysis_idle}` (headless process with a per-file analysis timeout, post-script save and pack) | ESTIMATE 180-300 s per slice incl. 20-60 s overhead for JVM start + open + save + pack (basis: 10-30 s headless open estimate; one 28 MB packed program observed at packed.py:21) | chunk-large / fleet | the packed program after every slice is the checkpoint; resume = next slice from gzf_k anywhere | phase-ordered inside one binary (disassembly -> functions -> references -> decompiler-driven); parallel only across binaries |
| `pin-artifact` | final gzf candidates from >= 2 independent analyzer keys -> `artifact-pinned` record (section 5.3) | seconds | micro / verifier keys | record | one decision per (image, basis) |
| `extract-names-facts` | gzf, address range -> symbol / function inventory / comment / memory-block / composite rows | ESTIMATE seconds per range (basis: pure-Python reader, ghidra_db/program.py:444, :470, :540, :590, :617) | micro / any python node (the packed program is an input object; fleet mirrors hold it by default, 6.3) | result object | none |
| `extract-graph-facts` | gzf, range of 64 functions -> calledge + mnemonic profile + strings/consts rows | ESTIMATE seconds to tens of seconds per range (basis: live-program feature walk at src/agentdecompile_recovery/corpus/features.py:144-241) | chunk / analyzer-capable, program affinity | result object | **JVM task until a References/Instructions reader lands (U138)** (ghidra_db reads no reference or instruction table: program.py:49-52; calledge rows come from caller-supplied rows at src/agentdecompile_recovery/corpus/extract.py:344,360). Grid's "core finding 3" is corrected here. |

Stays serial: one binary's analysis (5-30 min ESTIMATE) is the pipeline's critical-path floor; slicing checkpoints it but does not parallelise it. Parallelism = min(binaries, analyzer nodes). Slice-and-resume convergence to the same function boundaries as a monolithic run is a **design claim, not a measured fact**, and is the first spike (U137 acceptance A2.2); if it fails, the slice budget is raised so most binaries finish in one slice and the divergence is recorded in `timeout_policy`.

### 3.2 Stage 1-2: bulk decompile

Today: chunk loop behind `CONTEXT_LOCK` (src/agentdecompile_recovery/corpus/dashboard/workflow.py:117-129, :565-628): bare `DecompInterface()` with no options set (:576; the MCP providers use `grabFromProgram`, src/agentdecompile_cli/mcp_utils/decompiler_util.py:68-74, so the option set is an unpinned basis field today), 64 functions / 90 s (:586), per-function 20 s cap (:596), one SQLite commit per function (:600-609), cursor in the run row (:154-160), fingerprint = executable MD5 (:624). MEASURED 525.2 s for one whole-program extraction job; ESTIMATE 0.05-2 s per function, 10-60 min per 12.8k-function image in one JVM.

| Kind | Inputs -> outputs | Duration | Class / who | Checkpoint | Serial |
|---|---|---|---|---|---|
| `inventory` | pinned gzf -> sorted (entry, size) list + shard entry-list objects (JVM-free, program.py:470) | ESTIMATE seconds | micro / fleet | object | one pass per gzf, before shards |
| `decompile-chunk` | gzf, entries (16, parameter), pinned decompiler options (grabFromProgram + fixed toggles, decompiler_util.py:68-88), timeout_policy {per_function 20 s, task_wall 300 s} -> canonical JSONL rows `{entry, name, size, prototype, calling_convention, decompiled_c|null, error|null, timed_out, elapsed_ms}` + receipt | ESTIMATE 1-32 s typical, 320 s worst (basis: 16 x 0.05-2 s; 16 x 20 s cap) | chunk / analyzer-capable with program affinity `program:<gzf_hash>` | result object; on SIGTERM the covered subset is flushed as a partial result and a continuation `task-offered` names the rest | per-node open cost 10-30 s ESTIMATE, amortised by affinity; one decompiler instance is single-threaded (decompiler_util.py:58-66), instances per core are independent |

Timeouts are data (`timed_out: true`, U65), never a retry loop. The knowledge KB becomes a view (section 2.4). Two nodes may legitimately differ (plan:631): the verifier pins one and records the divergence; downstream compile refutes a wrong one.

### 3.3 Stage 5-7: compile one function under the era-exact toolchain

Today: one compiler invocation per TU (scripts/cl-compile.sh:32-36: mktemp dir, source renamed to `in.c`, `/c /O2`), 60 s guard (src/agentdecompile_recovery/corpus/ghidra_bulk.py:962-976), but the blocking unit is the whole repair chain in `_try_compile_inner` (:1289-1370): sanitize retry, three drains of up to 16 compiles each (:1129-1140, :1170-1181, :1214-1217), `REPAIR_ROUNDS = 8` (:989, :1311-1317), an LLM cleanup bounded at 300 s (:1320-1329; src/agentdecompile_recovery/rewrite_provider.py:35), the drains again (:1345-1353), a sanitize compile, an asm fallback: up to ~70 spawns, ESTIMATE 20-140 s per function. Pool: `ThreadPoolExecutor(max_workers=args.workers)` (:1699) pinned to `'workers': 1` by the dashboard (workflow.py:368), `_CORPUS_LOCK` (:109). The TU is already self-contained text (header = `ctx_text()` :622-626 plus generated typedefs/externs, :674; no `#include` emitted), so the INCLUDE mapping at cl-compile.sh:27-29 is idle for this lane. Toolchain identity is path+size+mtime (source_parity_synthesize.py:21705-21722), so cross-node cache reuse is zero today; both compile-side caches are mtime-keyed (src/agentdecompile_recovery/corpus/compile_link.py:95-102, :130-154).

| Kind | Inputs -> outputs | Duration | Class / who | Checkpoint | Serial |
|---|---|---|---|---|---|
| `compile-attempt` | tu_text sha (header + body, 2-30 KB), profile, flags, toolchain_identity_hash -> `.obj` object + receipt `{outcome: obj, obj_sha, masked_coff_sha}` or diagnostics object + receipt `{outcome: diag}`; INFRA (timeout, no object, no diagnostic) writes nothing and the task stays in the frontier | ESTIMATE 0.3-2 s (basis: sub-second compile of a one-function TU; process spawn dominates; the 0.06 s parity floor shows startup floors are small) | micro (60 s) / toolchain keys | result object; nothing inside a compile needs saving | none across functions |
| `repair-step` (derived, not offered) | previous tu_text, diagnostics, chain state {stage, index, round} -> next tu_text via the pure transforms `repair_from_diagnostics` (:1018-1068), `_add_cl_named_macros` (:1112-1125), `_add_cl_named_callees` (:1156-1167), pointer drain (:1214-1217), `sanitize_body` | milliseconds | computed by whichever node derives the frontier | the chain object `{function_key, stage, index, round, s_k, diag_k}` written after each attempt; recomputable from the result sequence | round k+1 needs round k diagnostics: inherent, per function; ~70 attempts max ESTIMATE 1-2 min per-function critical path |
| `rewrite` | the existing exchange unit payload (src/agentdecompile_recovery/exchange/producers.py:155-213) plus basis_hash and profile in the id (today `derive_request_id` at src/agentdecompile_recovery/rewrite_queue.py:161-163 keys on name + source only) -> source proposal (<= 64 KiB) | ESTIMATE 5-120 s (basis: one model round trip; 300 s guard) | micro (120 s) / any key with `llm`; browser | none needed; a dropped call is re-offered | bounded by `max_rewrite_requests_per_function` = 1 (src/agentdecompile_recovery/autonomy_budget.py:26): a model is the bounded leftover, never the mechanism (thesis 1) |
| `verify-byte-exact` | source sha, target slice sha, profile, toolchain hash -> verified receipt | ESTIMATE 1-3 s | micro / **independent-key** toolchain node | record | one per win |
| `link` | sorted object-set hash, LINK_FLAGS (compile_link.py:105), toolchain hash -> image + link receipt | ESTIMATE 10-120 s (basis: the 3600 s value at compile_link.py:245 is a hang guard; no receipt exists; measured in U131) | large / fleet | none; re-run whole | one process over all objects; incremental linking changes bytes; < 1 % of work, 100 % of the tail |

Persistent wineserver per node and a per-node concurrency cap (ESTIMATE one compile per core, basis: the 2026-08-30 saturation plateau at ghidra_bulk.py:965-970) are worker configuration, and per-attempt wall is written into every receipt so the 0.3-2 s estimate becomes a measurement in the first week.

### 3.4 Stage 7: parity check per function

Today three invocation paths with different semantics: the node helper with no timeout (src/agentdecompile_recovery/corpus/objdiff_check.py:26-49, bare `subprocess.run` at :42), the same helper called with candidate and target reversed (src/agentdecompile_recovery/corpus/seed_validation.py:353-357 vs the helper's `<base> <target>` positional order), and the native CLI (src/agentdecompile_recovery/source_parity_synthesize.py:20988-21023) parsed fail-closed (src/agentdecompile_recovery/objdiff_verification.py:49-127). The target side comes from `mkobj` (src/agentdecompile_recovery/corpus/mkobj.py:155-190), which is **host-dependent**: `find_call_targets` returns `{}` on `OSError` (:34-54, :42, :54) and displacement zeroing (:178-183) is skipped when the dict is empty, so a node without `objdump` emits a different target object for identical inputs. MEASURED native floor 0.06 s / 8 MiB on a 613-byte pair; node path 0.5-1.2 s (n=2).

| Kind | Inputs -> outputs | Duration | Class / who | Checkpoint | Serial |
|---|---|---|---|---|---|
| `mkobj-target` | image sha, offset, size, name, format -> target `.o` object, **pinned**; `objdump` is a declared capability with a named refusal, never a silent empty path | ESTIMATE <= 1 s | micro / keys with the objdump canary (the image slice is an input object) | pinned object | one per function |
| `parity-check` (kind; receipt schema keeps its landed name) | target_obj, candidate_obj, symbol, verifier_id (`parity:<binary hash>` or `parity-wasm:<hash>`) -> `verify-objdiff.v1` receipt (objdiff_verification.py:112-127), raw JSON spilled to its own object; sides are **named** target/candidate and rendered as `-1 target -2 candidate` so the reversed-order call cannot recur | ESTIMATE 0.1-0.5 s native, ~1 s node/wasm (basis: measured floors plus linear scaling) | micro; dispatched as range envelopes of ~60-300 pairs sized to 10-30 s, each pair keeps its own task id / any parity-capable key (advisory) and independent verifier keys (load-bearing) | per-pair result object flushed as it completes; a re-leased range skips existing pairs | none inherent; per-pair startup floor amortised by envelopes |

The pipeline's compile -> parity-check -> repair chain becomes continuation records, so the three steps can run on three nodes; no call site awaits a local verifier subprocess (today source_parity_synthesize.py:18580-19297 call it inline).

### 3.5 Stage 2-6: identity cascade and cross-place

Today: `corpus.match-pair` runs `match_binaries(rounds=4)` (src/agentdecompile_recovery/corpus/propagate.py:52-121; src/agentdecompile_recovery/corpus/match_store.py:376-937) as one subprocess with no checkpoint under the executor's 1800 s default deadline (src/agentdecompile_recovery/corpus/dashboard/actions/jobs.py:946-949). MEASURED (548 job receipts): 16 ok at 61-1597 s (median ~988 s); **5 killed at ~1800 s**, 6 interrupted, 11 cancelled: 24 of 40 launched pairs produced nothing. Pairs already run concurrently up to min(6, cpu) (preparation.py:115-129, :1774-1787) capped by `MAX_CONCURRENT = 4` (jobs.py:35); the pair set is a spanning forest, n-1 per arch group (src/agentdecompile_recovery/corpus/donor_schedule.py:27-48). The "strictly sequential, quadratic" premises of the 2026-09-08 doc are stale. `logical.build` (src/agentdecompile_recovery/corpus/logical.py:99-201) MEASURED 20-22 s; `workbench.merge-evidence` (workflow.py:446-542) MEASURED 25.5 and 35.8 s (n=2). Cross-place (src/agentdecompile_recovery/corpus/cross_place.py:171-200) writes a per-recipient banner into each placed file (:19-20, :36) so identical bodies hash differently per recipient. The matcher-input digest (preparation.py:2090-2107) omits the `bsim_hit` rows the matcher reads (match_store.py:318-323). At this head `dependency_token` keys on content hash (match_store.py:44-63) and `tokenise_callgraph_results` runs after all four propagation sites, so match rows are a pure function of the frozen slice.

| Kind | Inputs -> outputs | Duration | Class / who | Checkpoint | Serial |
|---|---|---|---|---|---|
| `match-slice` | func/calledge/decomp rows of one build + bsim_hit rows per planned pair + fingerprint column -> `matcher-input-v2` object (hashed slugs, no binary.id, no repo_path) | ESTIMATE 5-40 s per 20k-function build (basis: the v1 digest walk) | chunk / fleet, once per basis | object | one per build |
| `match-anchor` | src slice, dst slice, bsim-hits -> mapping_0 + results_0 (match_store.py:388-703 as a pure function) | ESTIMATE 5-60 s (basis: dict-indexed anchors; parent scan at src/agentdecompile_recovery/corpus/callgraph_propagate.py:133-139 is O(mapping) per pair) | chunk / any python key with slice access | object | one per pair |
| `match-score-shard` | slices, mapping_k, round k, src address range (512-1024 addresses) -> scored tuples (the body of match_store.py:716-768 against the frozen `taken` :708 and `int_map` :714) | ESTIMATE 5-10 s (basis: 988 s / 4 rounds / ~27k addresses ≈ 9 ms each) | micro / any python key (advisory); independent-key recompute for the accepted set | result object | none |
| `match-assign` | all shard outputs for (pair, k) -> mapping_{k+1}, results_{k+1} + continuation (round k+1 shards or finalize) via the global sort (:774) and greedy accept (:775-821) and callgraph fixpoint (:824-844) | ESTIMATE 1-20 s | micro / verifier keys | object | **inherent barrier**: destination contention needs every shard of the round; rounds are sequential (up to 4) |
| `match-finalize` | mapping_4 -> late similarity fusion (:850-855), inlines (:883-917), `match-rows` object sorted (src_addr, dst_addr) + cascade receipt | ESTIMATE seconds | micro / verifier keys | object | one per pair |
| `logical-build-shard` / `logical-build-merge` | canon_key-scoped func rows, key range, id offset (from a counting pass) -> fragments; merge concatenates in key order (logical.py:132-186; ids sequential in canon_key order at :153, :175) | ESTIMATE 1-5 s per shard; merge seconds | micro / any python key; merge by verifier key | fragments | the counting pass and the concatenation |
| `identity-merge` | logical object + verified match-rows for one recovery family (families never share pairs, preparation.py:1687-1710) -> identity delta (the union-find of workflow.py:467-531 with its score-ordered conflict rule :482, :490-492) | MEASURED 25-36 s whole store today; ESTIMATE seconds to tens of seconds per family | chunk / verifier keys | delta object | one deterministic reduce per family |
| `cross-place-recipient` | source compile-ok ids, identity slice (src, dst), body objects -> placement object `[{dst_addr, body_hash, provenance}]`; the banner moves to metadata so an identical body placed on N siblings is **one** object and one `compile-attempt` when profile/flags/toolchain match | ESTIMATE < 1 s per recipient | micro / any python key (advisory) | object | none |

Recipient recompiles are `compile-attempt` tasks from 3.3 and are the node-hour mass of "propagation" (section 7). An interim change independent of the grid is worth half a day: make `corpus.match-pair` write a per-round checkpoint object and resume from it, and add bsim_hit to the v1 digest, so the 1800 s deadline stops discarding 30 minutes of work.

### 3.6 Stage 7: permuter and LLM candidate generation

Today: the harness walks functions sequentially (src/agentdecompile_recovery/corpus/permuter_harness.py:730-768), runs the search under `subprocess.run(timeout=seconds)` with default 120 s (:634-636, :782) and **discards the best candidate on timeout** (:766, :835), writes results only at pass end (:772, :841), repairs the context header with up to 12 compile-and-drop rounds every pass (:467-478), and never passes a seed. MEASURED: 8 result rows, all `permuter_no_output` (base-compile failures), so no successful search exists in any receipt; text-permuter 17 closed / 1,657 unclosed, engine imported from a host-absolute path (src/agentdecompile_recovery/corpus/text_permuter_watch.py:33-42, :106-107).

| Kind | Inputs -> outputs | Duration | Class / who | Checkpoint | Serial |
|---|---|---|---|---|---|
| `repair-context` | raw context sha, profile, toolchain hash -> repaired header object | ESTIMATE up to 12 compiles, 5-30 s | micro / toolchain keys, once per basis | object | inherent chain (round k+1 needs round k) but once per basis |
| `permuter-case` | base_c, context_h, target_bytes, symbol, profile -> case bundle (base.c, function.txt, target_bytes.bin, target.o from mkobj, settings, compile script template with no absolute paths) + base_score; non-compiling base -> `case-refused` | ESTIMATE 1-3 s | micro / toolchain keys (the target bytes are an input object) | object | one per leftover |
| `search-shard` | case hash, seed range (or seed + trials), jobs 1-2, wall cap 30 s -> winners only `{best_score, best_source_hash?, seeds_covered}`; the shim harvests `output-*/*.c` before the deadline | <= 35 s by construction | micro / toolchain keys; donors owning the toolchain (canary) | `search-progress` record (seeds covered, best-so-far as a commutative minimum, the campaign_checkpoint rule at src/agentdecompile_recovery/campaign_checkpoint.py:51-104) | none: seeds are independent (2026-09-08 R5) |
| `permute-text-generate` / `score-candidates` | candidate set (<= 64 KiB) from a no-toolchain node; scoring compiles + masked-diffs the set in one batch | generate <= 10 s; score <= 60 s | micro / generate: any key, browser; score: toolchain keys | objects | scoring is 1:1 with generation, so browser text-permute is a priority-hint producer only (narrows the 2026-09-08 lane table :86) |
| `verify-win` | best_source, target.o, profile, toolchain hash -> verified byte-exact receipt or refutation (recompile from source; never the donated object) | ESTIMATE 1-3 s | micro / independent-key toolchain node | record; `case-closed` removes remaining shards from the frontier | per win |

Whether the pinned search checkout accepts a `--seed` flag is unverified (no checkout found under the repo); the fallback is N independent short runs with distinct seeding, which is acceptable because the grid needs the result verified, never the search reproducible (plan:627 asks only that seeds be pinned in the receipt).

### 3.7 Stage 2: similarity signatures and queries

Today: one whole-program signature script per program under `_BSIM_LOCK` (preparation.py:22, :1612-1614) and `CONTEXT_LOCK`, 1200 s monitor (:1638, :1962, :1990), MEASURED ok n=18 median 445 s, max 746 s, **failed n=79 of 97**; commit 3.3-9.6 s; createdatabase 13.8 s. Two determinism facts: without a template name the vector factory comes from live server state (:1965-1976), and the output is named by executable MD5 (:1995-1997). Queries are not exercised by the pipeline: `_fuse_bsim` (match_store.py:306-330) reads an optional `bsim_hit` table that nothing in `src/` produces (U5d, plan:821-828; the generator revision is a pending basis field, src/agentdecompile_recovery/corpus/determinism_basis.py:62-69).

| Kind | Inputs -> outputs | Duration | Class / who | Checkpoint | Serial |
|---|---|---|---|---|---|
| `bsim-sigs` | gzf, entry cursor, n=128, template_id (pinned-template path mandatory), generator revision -> signature XML fragment for the range + receipt | ESTIMATE 2-3 s (basis: 445 s / ~27k functions ≈ 16 ms each) | micro / analyzer-capable with program affinity | fragment object | per-node open once |
| `bsim-merge` | sorted fragment set covering one gzf -> canonical whole-program XML (functions ordered by entry) | ESTIMATE ms to seconds | micro / verifier keys | object | one per program; exists because commit of N fragment files per executable is unverified (probe in U141) |
| `bsim-commit` | merged XML hash, cluster url -> commit via the existing verb (catalog.py:418) | MEASURED 3.3-9.6 s | view applier / fleet or operator | verified record keyed (xml hash, url) | single-writer per program into the index; the index is a view |
| `bsim-query-shard` | src vector fragments for a range, candidate fragments of target build(s), thresholds from the basis -> `bsim_hit` rows object ordered (src_addr, dst_addr) | ESTIMATE seconds per range (JVM path); python cosine path unmeasured | micro / analyzer-capable (JVM path); any python key if the python path proves bit-exact (U141), else advisory only | object | none |

### 3.8 Stage 0 and substrate: backfill and export

Today: export-hookpack is one loop over every logical row with one JOIN per row (src/agentdecompile_recovery/corpus/export_hookpack.py:160-181), per-instance unique-window scans (:198-212, :56-67), one 120 MB `json.dumps` (:291); MEASURED 122-200 s, byte-identical across runs; the site key depends on a global counter over all logicals (:164, :222-227). verify-determinism copies the 1.33 GB store twice and exports twice: MEASURED 248.5-260.6 s. Backfill reads the raw image for every pass including those with `needs_raw_image=False` (src/agentdecompile_recovery/corpus/backfill.py:151 vs :86), and `analyzer_identity` reads the node's current install (:57, :64), so it is not a pure function of content-addressed inputs; MEASURED 19.9 s / 0.2 s resumed, 35.3 s. A5 basis-first is landed at this head (export_hookpack.py:134-137; cli.py:782-785). 28 of 30 analyzed builds lack `content_sha256` (attestation §4, R3), which blocks the stage on the real store independently of this design.

| Kind | Inputs -> outputs | Duration | Class / who | Checkpoint | Serial |
|---|---|---|---|---|---|
| `register-image` | raw image bytes -> object (address = content hash) + `image-registered` record | ESTIMATE 10-50 ms hash (basis: sha256 throughput) | micro / operator | record | none; R3 is registration, not compute |
| `stamp-basis` | binary key, language id, explicit analyzer-identity object (package_basis fields, determinism_basis.py:168-193) -> `basis-stamped` record | ESTIMATE ~1 ms per row, batched | micro / fleet or operator | record | none |
| `site-key-table` | logical rows -> pinned `logical_id -> site_key` table (the counter rule) | ESTIMATE 0.5-2 s | micro / verifier keys | object | **must precede every shard** (global multiplicity) |
| `export-slice` | store snapshot -> `export-input-v1` objects per ~1,000 logicals (member rows ordered by content hash, addr) + binaries table | ESTIMATE 1-4 MB per shard | chunk / view node | objects | one per snapshot |
| `export-site-shard` | member slice, site-key table, policy/adapter hashes, window values -> fragment `{site_key: site}` + receipt | ESTIMATE 1-4 s (basis: 240 sites/s measured with the SQL; without it dict building only) | micro / any python key (advisory; 1:1 to verify), verifier keys (load-bearing) | fragment | none |
| `window-index` / `window-shard` | image sha -> per-image occurrence index (n in 8..24); probe list -> window values | index ESTIMATE 1-3 min per image; probes < 1 s per 5,000 with the index (basis: today's 12k probes become ~291k when images are registered; 1-5 ms per scan ESTIMATE) | chunk / any python key (the image is an input object) | pinned index; value objects | index per image |
| `export-merge` | fragments in site-key order, binaries table, key table -> pack + pack hash; global collision checks (:227, :267) run here | ESTIMATE 5-20 s (basis: 120 MB indented dump) | chunk / verifier keys | object | one pass; drops to a manifest (< 1 s) if U87's directory layout is chosen |
| `verify-determinism` | second export at identical basis -> 100 % cache hits and equal pack hash (gate a, ESTIMATE 1 s); k shards recomputed on a different node (gate b) | ~1 s + k x 1-4 s | micro / independent keys | receipt | none; the two-copy verb survives as a diagnostic |

### 3.9 Stage 8: whole-image relink and byte identity

Today: the splice diagnostic (src/agentdecompile_recovery/corpus/whole_image_relink.py:78-118) assumes `FileAlignment == SectionAlignment` without asserting it (:98; `parse_pe` :28-46 reads neither) and localises a mismatch with a byte-by-byte Python loop (:142-149); it is rebuilt whole every 60 s by `matching_watch` (src/agentdecompile_recovery/corpus/matching_watch.py:29-34, :87, :95-101). The terminal fresh receipt (src/agentdecompile_recovery/corpus/verify_direct_full_image.py) refuses to resume (:50), defaults to `--workers 1` (:32), compiles every function **twice** (:62-73), and proves freshness by mtime (:88, :95). ESTIMATE 2-14 h wall per terminal pass, unresumable.

| Kind | Inputs -> outputs | Duration | Class / who | Checkpoint | Serial |
|---|---|---|---|---|---|
| `place-check` | `.obj`, target slice, image base -> placement `{addr, size, reloc_offsets, masked_diff, linked_bytes_sha|null}` (verify_recovered_byteexact.py:83-129, :199-214 lifted to a pure function; the equality gate at :212 preserved) | ESTIMATE < 10 ms | micro / any python key (advisory), verifier keys | object | none |
| `splice-shard` | target sha, offset range, placement index -> shard bytes + per-4 KiB block hashes; refuses by name when the alignment assumption fails | ESTIMATE <= 1 s per MiB | micro / any python key (the target image is an input object) | object | none |
| `image-join` | ordered shard hashes -> whole-image sha256 + `{identical, first_delta}` from block-hash inequality | ESTIMATE 0.1-2 s | micro / verifier keys | receipt | one streaming pass (sha256 chains) |
| `image-receipt` | link image sha, target sha, placement index, basis -> terminal receipt `{wholeFileByteIdentical, verified, closure_hash}`; freshness = every hash in the closure pinned under the current basis by verified records, not mtime | sub-second | micro / verifier keys | receipt | none |

A donated object or placement artefact is never evidence in this stage; what a donor contributes is source text, recompiled under an independent key (section 2.5). One `compile-attempt` feeds both the link and the placement check, retiring the double compile.

### 3.10 What is retired

`workbench.prepare`'s stage-ordered admission loop (jobs.py:341-400; preparation.py:487-540) and its run row + lease file become a viewer of receipts (U110). `MAX_CONCURRENT = 4`, `CONTEXT_LOCK`, `_BSIM_LOCK`, `_CORPUS_LOCK`, the `workers: 1` pin, the per-program lock and the exchange store's in-memory snapshot all disappear as coordination points. The single one-shot recovery subprocess with a wall budget up to 7 days (workflow.py:26-27, :384-392) is the anti-pattern; its per-function checkpoints (src/agentdecompile_recovery/campaign_checkpoint.py:1-12) are the shape the grid generalises.

---

## 4. Compile strategy decision

**Decision:** keep the era-exact toolchain behind the existing wrapper; the unit of work is one function translation unit, one compiler invocation (0.3-2 s ESTIMATE); make the TU text and the toolchain tree content-addressed; split compile from link (already the code's shape); express the repair chain as a derived graph of attempts; keep the link as the one large-class serial task. Compilation becomes resumable and shardable at the attempt level without any new toolchain and without any mid-compile checkpoint, because nothing inside a 2 s compile needs saving. Scope of the byte-accurate compile lane: builds whose toolchain identity is the pinned one. On the attestation copy (MEASURED, 2026-09-21) 30 builds are analyzed: 11 32-bit PE and 2 32-bit console-format share the era-exact toolchain's class; the other 17 (ELF, Mach-O, 64-bit, ARM) are outside it and receive no byte-exact compile, parity or recipient task under this identity. A second toolchain identity is a second lane with its own canary and pin (S17).

Ranking of the five candidate paths, by realism first, byte-accuracy risk second:

| # | Path | Realism | Byte-accuracy risk | Decision |
|---|---|---|---|---|
| 1 | Per-function translation units | Already the shape: one file per compiler call in a fresh temp dir (scripts/cl-compile.sh:32-36), per function in bulk (ghidra_bulk.py:962-985), per unit in the tree build (compile_link.py:309-420) | None | Adopt; the missing piece is 12.8k advisory leases instead of `ThreadPoolExecutor(max_workers=1)` (workflow.py:368) |
| 2 | Split compile / link with an object cache | Already the shape (compile_link.py:340-362 compile phase; `link_msvc` :239-300; `object_is_current` :95-102) but the cache is mtime-keyed | None for each `.obj`; the link's `LINK_FLAGS` (`/nologo /FORCE /OPT:NOREF`, :105) are explicitly not a byte-accuracy claim (:302-305) | Adopt; re-key caches on (tu sha, toolchain hash, flags) and (sorted object-set hash, flags, toolchain hash). There is no assemble stage to split: `/c` emits COFF directly and a listing is not a linkable input |
| 3 | Self-contained TU text + content-hashed toolchain identity (the manifest hash of 1.5 (a); what "preprocessed-input cache" actually means for this lane) | High: the bulk TU is already header-free text (ghidra_bulk.py:622-626, :674), so `sha256(header + body)` already closes the input set and donors never need a header tree; `/P` preprocessing is **optional normalisation insurance**, not the load-bearing addition grid claimed | Low but non-zero for `/P`: `__FILE__`/`__LINE__`, `#line`, pragma placement can change bytes; `/Zi` is forbidden regardless | Adopt the content hashing now; land `/P` only after masked-COFF equality of compile(x.c) vs compile(x.i) over >= 200 TUs is measured (U131). If it fails, ship the TU text as is |
| 4 | Thin wrapper around the legacy toolchain in a container image nodes pull | Technically trivial (the wrapper is cl-compile.sh plus a compatibility-layer prefix); the image is one packaging of the same content-addressed toolchain object (the manifest hash of 1.5 (a)) | None beyond O2 | Adopt as one packaging option, never a requirement: the bare prefix tarball is the default toolchain object (user baseline prefers non-container); a node that already owns the toolchain declares its path and the canary proves the hash; a node that does not fetches the toolchain object like any other capability input (6.3) |
| 5 | Alternative toolchain reproducing the same bytes | Rejected: closed-source code generator; no other compiler reproduces its register allocation, scheduling and padding (cl-compile.sh:4-6 records the in-repo basis; ideal-loop doc 4a.1 as cited by the inventory) | Total | Diagnostics-only lane at most; never on the verification path. A donor on the toolchain's native OS running the same compiler binary is not an alternative toolchain (same bytes expected, no compatibility layer): it passes the same canary and joins the same lane |

Repair rounds: the chain is inherently serial per function (round k+1 needs round k diagnostics) and parallel across the 12.8k functions; every transform in the chain is already a pure function of (header, body, diagnostics) (section 3.3), so the chain state is a small object and any toolchain node can take the next attempt. The LLM cleanup step is emitted as a `rewrite` proposal task, never executed inline. Worst-case per-function critical path ESTIMATE 1-2 min (~70 attempts).

Verification of a compile output: masked-COFF hash equality (zero the COFF file-header `TimeDateStamp`, forbid `/Zi`) when O2 proves cross-machine determinism, else recompile + parity check (0.06 s MEASURED native floor, ~1-3 s with the compile). O2 hypothesis: high match rate, because the wrapper already normalises the source name to `in.c` in a fresh working directory (cl-compile.sh:32-34), so the embedded file record is machine-invariant, leaving the timestamp and the toolchain bytes as the only variables. Measured, not asserted, as the first toolchain unit (U131) and continuously by the join canary (mesh graft).

Byte-accuracy invariant that survives regardless: the object of record is always produced from source by a toolchain node, and it is accepted only by hash equality or parity against the target under an independent key; no donated object or placement artefact is ever evidence.

---

## 5. Analyzer strategy

### 5.1 Avoid re-analysis entirely

Analysis runs once per `(image content_sha256, analyzer basis: version, processor_spec_hash, compiler_spec_ids, options_hash, timeout_policy, loader_revision, pin_policy)` (plan:455-466 plus the pin policy this design adds). Its product is a packed program object (a `.gbf` inside a ZIP, src/agentdecompile_recovery/ghidra_db/packed.py:6-16), never a live project handle. Every downstream task keys on the packed program's hash, never on the image, so the analyzer's own non-determinism (plan:631) cannot leak into task identity. "Never re-analyze" becomes an existence check; the `-deleteProject` discard path (ghidra_context.py:200-212) is retired and `reuse_ghidra_acquisition` (src/agentdecompile_recovery/corpus/acquire.py:144-150) is re-keyed on content hash + basis.

### 5.2 Checkpoint the long step; shard across binaries, never inside one

The analysis of one binary is phase-ordered inside one program database and cannot be sharded without forking the analyzer; ESTIMATE 5-30 min per multi-MB image, the pipeline's critical-path floor. It is checkpointed as `analysis-slice` tasks: each slice runs the headless analyzer on the previous packed program with a per-file analysis timeout, saves and packs; the packed program after each slice is the checkpoint and any analyzer-capable node resumes from it. Slice overhead (JVM start + open + save + pack) is ESTIMATE 20-60 s, so slices are 180-300 s and the wall grows by roughly 10-30 % per binary in exchange for preemptible free-tier nodes being usable at all. Convergence of a sliced run to a monolithic run's function boundaries is a spike (U137 acceptance A2.2), because the analyzer's queue lets analyzers enqueue follow-on work and a resumed run may not converge identically; if it does not, slices stay large enough that most binaries finish in one and the divergence is recorded in `timeout_policy`. Deferring decompiler-driven analyzers (extending program_analysis.py:276-282) and deriving prototypes from decompile chunks is kept as an option (U137b), a basis change, not the default. Parallelism is across binaries: 30-90 binaries over K analyzer nodes gives min(binaries, K)x.

### 5.3 Pinning behind a deterministic check (fix for first-wins)

First-wins pinning would let arrival order decide the one artifact every downstream id keys on, and would let a single compromised node that wins the race control every downstream task id for that binary. Instead: a packed program is pinned only when the canonical inventory hash (sorted function inventory + memory-block table + address map, all JVM-free via ghidra_db program.py:470, :590) agrees between the outputs of **two independent analyzer keys**. If they disagree, a `pin-divergence` record carries both hashes and the operator key pins one (a machine rule: the lexically smaller inventory hash, so no human is in the loop and the choice is reproducible); the divergence count is a determinism finding for U25. The pin policy (`two-key-agree` or `operator-lexmin`) is a basis field, so a re-pin is a basis change and never a silent shift. Cost: analysis runs twice per binary on fleet nodes (ESTIMATE +2.5-15 node-hours per corpus, parallel across binaries; not on the critical path when K >= 2 nodes per binary can be spared). Once pinned, the packed program is immutable and downstream is deterministic by construction.

### 5.4 Fact extraction and decompile without the coordinator

JVM-free today (ghidra_db): symbols, functions, comments, memory blocks, composites (program.py:444-617): `extract-names-facts` is a python task. **Not JVM-free today:** references, instructions, mnemonic profiles, strings/consts as computed by the feature walk (features.py:144-241), so `extract-graph-facts` stays a JVM range task over the pinned packed program until a References reader (U138) and, optionally, a python decoder (U138b, a basis change) land. `decompile-chunk` and `bsim-sigs` open the pinned packed program once per node (ESTIMATE 10-30 s), advertise `program:<gzf_hash>` affinity and drain ranges; no shared project, no project server, nothing under `CONTEXT_LOCK`.

### 5.5 Fleet placement and the unmeasured precondition

The analyzer needs RAM a 1 GB x86 free tier does not have; it lands on the large-RAM ARM tier by canary. R12 (packed-program size and headless open time for a multi-MB image, proposed in 9.3) is unmeasured: ESTIMATE 20-150 MB (basis: one 28 MB packed program observed at packed.py:21). If it is at the high end, nodes-per-program is capped at ~3 by affinity so egress stays around 30 x 3 x (20-150 MB) = 2-14 GB per corpus pass. Measured in U131 before any fan-out default is set. Not relied upon: a JVM-free decompiler (O3, unverified) and browser analysis (impossible, 2026-09-08 §8).

### 5.6 Who runs the packed-program lanes

Any node that passes the analyzer canary runs them; the packed program is an input object fetched by hash like every other input (6.3), so grid's "core finding 3" (JVM-free extraction on any python node) holds for every node that holds the packed program. What bounds the fan-out is size, not role: fleet nodes mirror packed programs and images by default (6.1), the nodes-per-program affinity cap (5.5) bounds egress, and the derived values (matcher-input slices with hashed slugs, mnemonic-class profiles, per-function target slices) are the small objects the python lanes consume.

---

## 6. Transport, NAT, security

### 6.1 Transport

Outbound-only HTTPS (443) from every node; no inbound port on any donor; nodes never talk to each other, so no hole punching and no relay. Reads are immutable objects fetched by hash from a static mirror or bucket (cacheable, CDN-able, served by any fleet node with a public address). Writes are a write-once PUT to a presigned URL (`If-None-Match: *`, size-capped, scoped to the task's expected output hash) followed by a batched signed record append via the head CAS (the only live RPC, per sub-partition, tiny). The operator's laptop behind NAT is another outbound client; the fabric host is a bucket plus a static site plus at least one fleet node with a public address, never the laptop. Fleet nodes additionally serve objects to each other over peer HTTP and act as mirrors for the toolchain and packed-program objects. The browser lane runs the same protocol from `fetch()` in a Web Worker with CORS on the bucket. Disconnected operation: a worker keeps its last `checkpoint-index`, works through the frontier it knows, queues results in its outbox, flushes when a head is reachable; the cost of staleness is duplicate work only.

### 6.2 Identity and roles

At join the node generates an Ed25519 keypair. The invite fragment binds a role (`operator`, `fleet`, `donor`) and is signed by an operator key **or a fleet key** (fleet keys may sign fleet and donor invites, so joining never depends on the laptop). A role decides three things only: what the node mirrors by default, whether its key may sign invites, and whether it may run verifiers and view appliers; it never decides what a node may fetch or which lanes it is offered — canaries do. Every record and upload is signed by the node key. Open donor enrolment with per-key rate limits (records/minute, bytes/hour), object size caps (the exchange's 64 KiB for inline payloads, routes.py:36-41; larger outputs by presigned URL with a per-kind cap), and a revocation-list object that any fleet key may extend. Keys are short-lived (default 7 days, renewed by canary re-run) and per-node. No accounts, no reputation, no quorum. Capabilities are bound to the credential at join and re-proven on `adgrid rejoin`, so a donor who installs a toolchain later is not stranded (hive graft).

### 6.3 Object tags and capability-scoped fetch

Objects are tagged in metadata by what they are, so mirrors, GC and size caps can act on them: `record` (task records, receipts, hashed-slug slices, source proposals, compile diagnostics; small, replicated everywhere), `image` (raw images, packed programs, target slices, window indexes, placement shards; large, mirrored by fleet nodes by default), `toolchain` (the era-exact toolchain tree, the analyzer bundle; large, mirrored by fleet nodes and cached by every node that passes the matching canary). The tag is object metadata, not a path convention (U140 acceptance), and nothing reads it as a permission. Fetch is scoped by capability, never by role: a presigned GET for an object is issued to any key whose offered task names that object as an input, and a task is offered only to keys whose canaries prove its `caps_required`; a `toolchain` object is additionally fetchable by any key attempting the matching canary, because the canary is how a node without an owned install gains the capability. A key that asks for an object no task offered to it names is refused by name (`not-an-input`); a node whose canaries pass but which no open lane currently needs is told `no-lane-open` by name rather than idling (U125 acceptance).

### 6.4 Proposals only; nothing donated writes identity tables

The verified stream is appended only by verification tasks run under independent keys (section 2.5); the view appliers read only the verified stream; identity, logical, match, knowledge, compile-receipt and export tables are therefore written by nothing a donor or a single fleet node signed alone. This keeps the landed rule "identity writers never leave home" (2026-09-08 R2) in a stronger form: identity writers are replayers of machine-verified records, and home is any node running the applier. Review overrides under the Autonomy rule (plan:114-125) are separate signed override records applied at materialisation, never a gate on producers.

### 6.5 Abuse and poison

Flooding: rate limits, size caps, the 4-proposal cap per task, and the fact that unverified proposals never reach a view. A liar can waste verifier time at most 4 x |tasks| x verify cost, bounded per key by the rate limit. Poison tasks: 3 timeouts from independent keys retire the task as unresolved with a reason (Autonomy rule). A hijacked fleet node can forge nothing that lands (its records are proposals); short-lived keys and revocation bound in time what it can waste. The observer-path fixes the exchange still lists as outstanding (2026-09-08 §6b; routes.py:12-16: shared SSE snapshot, connection cap, hidden-tab gating) are a prerequisite before strangers connect to the browser gateway (U130); the static read path removes most of that load, but the dashboard's own polling remains.

### 6.6 Privacy of donated data

Source proposals, diagnostics and image-bearing inputs travel to whichever node's canary the task needs; slugs are hashed and no product label appears in any payload or object name (A6/U21a; U151 acceptance greps the object store for registered slugs and repo paths). Fleet-only mode (no donor invites issued) is a configuration of the same protocol, not a different one.

---

## 7. Speedup and work estimate

All figures are ESTIMATES built from the inventory's measured receipts; the basis is stated per row. Reference corpus: 30 analyzed binaries, one 12.8k-function reference build with ~70 % compile-ok bodies and ~2.5k leftovers. Node = one laptop-core-equivalent; a free-tier fleet node ≈ 0.5; a donor ≈ 0.5. Fleet is split by canary into analyzer nodes (large-RAM ARM tier) and toolchain nodes (x86 tier).

### 7.1 Bounded work per corpus pass (node-hours)

| Lane | Node-hours | Capability | Basis |
|---|---|---|---|
| Analysis, first run | 2.5-15 | analyzer | 30 x 5-30 min |
| Analysis, second run for the deterministic pin (section 5.3) | 2.5-15 | analyzer | same |
| Slice overhead | 0.3-5 | analyzer | 2-10 slices x 20-60 s per binary |
| Bulk decompile | 15 | analyzer | 30 x 30 min (mid of 10-60) |
| Graph-facts extraction (JVM until U138) | 0.5-5 | analyzer | 30 x 1-10 min |
| Similarity signatures | 3.7-6.2 | analyzer | MEASURED 30 x 445-746 s |
| Compile pass, reference build | 3-30 (ESTIMATE; 23-78 with every failing body at the ~70 cap) | toolchain | 12.8k x A x 0.3-1 s. A is unmeasured and two-population: 1-2 attempts for the ~70 % compile-ok bodies; for the rest the chain of 3.3 exits early at every tier (:1129-1140, :1311-1317) under its ceiling of ~70 spawns, taken as 5-25 until U131(h) records the distribution |
| Cross-place recipient recompiles, same-class siblings | ceiling 7-30 before dedupe; 2-21 after (ESTIMATE) | toolchain | 12.8k x 0.7 x S x 0.3-1 s with S = same-toolchain-class siblings, not 29. Attestation copy (MEASURED): 30 analyzed builds, 11 32-bit PE + 2 32-bit console-format, so S ≤ 10-12 (12 only if the console builds' toolchain identity matches; S17); pairs form per (arch, bits) group (donor_schedule.py:13-17, :27-48) and parity receipts never cross toolchains. Identity fan-out on the attestation copy is 3.93 rows per logical (291,302 / 74,205; 44,385 shared) and the reference build holds 49 identity rows today (1.84 same-class siblings per shared logical), so the realized term is ≈ 90 placements until the cascade covers it; this row is the projection for a fully matched corpus, an estimate-class ceiling. Banner-out-of-body dedupe removes 30-70 % (profile sharing per family, U144) |
| Link | 1 | toolchain | 30 x 2 min |
| Independent-key verification of byte-exact wins | 1-5 | toolchain | 1-20 % of attempts x 1-3 s |
| Parity checks | 2-10 | any (advisory) / independent keys | attempt count x 0.1-0.5 s native |
| Match cascade | 8 | python | 29 pairs x 988 s median MEASURED |
| Logical / identity / export / backfill / verify-determinism | 0.2-0.5 | python | MEASURED 20-22 s, 25-36 s, 122-200 s, 55 s; verify collapses to ~1 s |
| Window probes (once images are registered) | 0.5-1.5 with the index | python | 291k probes; index 1-3 min per image |
| **Total bounded** | **≈ 40-140 (mid ≈ 85, same rule)** | of which analyzer ≈ 25-61 (mid 40), toolchain ≈ 7-57 (the two corrections above move in opposite directions; 42 stays the working divisor of 7.3 and 7.4 until U131(h) and U144 file receipts), python/any ≈ 10-19 | |
| Elastic residue (not bounded): search on ~2.5k leftovers | 83-208 at 120-300 s per function | toolchain | permuter budgets |

Today, one host (one JVM, one lock, `workers: 1`, one SQLite writer): ≈ 105-130 h wall for the bounded set (basis: the stage sums at their current serial shape), with the failure classes on top (79 of 97 signature jobs failed at 7-20 min each; 24 of 40 match pairs produced nothing).

### 7.2 The levers, in the order they matter (requirement 2)

1. **Reduce the toolchain-bound mass.** Cross-place bodies as content-addressed objects with the banner in metadata (cross_place.py:19-20, :36) turn identical placed bodies across siblings into one compile task: ESTIMATE 2-21 node-hours removed from the recipient row's 7-30 class ceiling (7.1); once S is class-bounded the compile pass is the larger toolchain row, so the python-side predicate that skips bodies the preparse already knows cannot compile carries more of this lever. De-duplicating the terminal pass's double compile (verify_direct_full_image.py:62-73) halves that stage for one day of work. A python-side predicate before any compiler run (skip a recipient recompile whose TU hash already has a result under the same profile; refuse bodies the deterministic preparse already knows cannot compile) removes attempts that would only produce diagnostics. Grid's own table treated fleet size as the only lever and therefore opted the whole into a fleet-size bottleneck; this design does not.
2. **Admit toolchain- and analyzer-capable donors by canary** (section 1.3). Any node that passes the toolchain canary — an owned install or a fetched toolchain object — is a toolchain node, and any node that passes the analyzer canary is an analyzer node; the browser is neither. Their objects are cache fills; their claims are verified by independent-key recompute.
3. **Fleet size** for the analyzer and toolchain lanes.
4. **Donor count** for the python lanes and the elastic residue.

### 7.3 Per-stage speedup at 5 / 20 / 100 donors (4 fleet nodes assumed: 2 analyzer + 2 toolchain, plus the laptop)

| Stage | Today (wall) | 5 donors | 20 donors | 100 donors | What binds |
|---|---|---|---|---|---|
| Analysis (with pin doubling) | 2.5-15 h | analyzer-capable nodes only (ESTIMATE): 5-30 h of runs / 2 node-eq ≈ 2.5-15 h; 10 nodes ≈ 1-5 h; 30 ≈ one round (5-30 min); a donor that passes the analyzer canary counts as one of those nodes | same rule | same rule | analyzer-capable node count (fleet plus canary-proven donors); RAM per node |
| Bulk decompile | 10-60 min per build, 15 h corpus | ≈ 6.5x with 5 analyzer-capable donors (ESTIMATE, stage analysis; changed assumption: any node that passes the analyzer canary fetches the packed program) | ≈ 14x | ≈ 45x, capped by ~3 nodes per program on egress | analyzer canary; egress (nodes-per-program cap) |
| Compile pass + cross-place recompiles | 74 h serial-equivalent | toolchain-less donors: 1.0x; fleet (laptop + 2 x86 = 2 node-eq) after dedupe: 24-61 h / 2 ≈ 12-30 h (≈ 2.5-6x); toolchain-owning donors: 5 → 42 / 4.5 ≈ 9 h (8x) | 20 toolchain donors → 42 / 12 ≈ 3.5 h (21x) | 100 → 42 / 52 ≈ 50 min (≈ 90x), floor = longest repair chain (1-2 min) + link | toolchain-capable node count; per-node compatibility-layer cap |
| Parity checks | 2-10 h inline behind the compile loop | verified path 1.0x (1:1 rule); advisory latency 8 pairs/s extra | 33 pairs/s advisory | 165 pairs/s advisory | independent-key verification; the real win is decoupling from the compile loop (K fleet ≈ Kx) and native vs node (5-20x per check) |
| Match cascade | ~2 h ideal, waves often unfinished | 2-2.5 h (two waves) ≈ 1x, but every pair completes | 10-45 min (≈ 3-10x); floor = longest pair chain 5-8 min | 6-10 min (≈ 12-20x); donors idle ~95 % | 29-pair fan-out, per-round barriers |
| Similarity signatures | 3.7-6.2 h, 81 % failure | 1.0x from donors; 2 analyzer nodes ≈ 1-1.5 h; 10 ≈ 25-40 min | queries: 20-40 min if the python path proves bit-exact | queries: minutes | analyzer; failures cost 3 s per range instead of 7-20 min per program |
| Export + backfill + verify-determinism | ≈ 7.6 min | 1.0x from donors; fleet: 30-90 s; verify 250 s → ~1 s (U66, 250x) | same | same | the window index per image (a task input); merge tail 5-20 s |
| Relink terminal receipt | 2-14 h, unresumable | 1.0x from donors; 2x from de-dup; fleet 4: 0.3-2.3 h; incremental win 1-5 s | same | same | toolchain; link is the tail |
| Elastic residue (search) | 125 h per pass at 3 min/function, lost on crash | toolchain donors 5 + 4 fleet: ≈ 28 h (4.5x); toolchain-less: rewrite lane only, 0.7-17 h of proposals | 20 → ≈ 10 h (12x); rewrite 10 min-4 h | 100 → ≈ 2.4 h (50x); rewrite minutes, fleet verify floor 20-60 min | toolchain; no pipeline wall-clock effect (off the critical path) |

### 7.4 End-to-end: cold start versus steady state

The bounded set splits into a **cold-start** term that runs once per (corpus, analyzer basis) and a **steady-state** term that runs on every pass (a new build entering the corpus, a re-run under an unchanged analyzer basis, a toolchain or profile change). Reporting them as one flat figure is what made grid's table read as an opted-in bottleneck: the analyzer term is fleet-bound and doubled by the deterministic pin, and it dominated every row. It is a one-time cost, and "never re-analyze" is the mechanism that makes it one-time; the inventory's 30 binaries are already analyzed once.

**Cold start** (analysis with the two-key pin, bulk decompile, graph facts, signatures: ≈ 25-61 node-hours, mid 40; bounded by the analyzer-capable node count — fleet nodes plus donors that pass the analyzer canary — and by egress, never by a fixed property):

| Analyzer-capable nodes | Wall (ESTIMATE) |
|---|---|
| Laptop + 2 | ≈ 20 h, once |
| Laptop + 8 | ≈ 8 h, once |
| Laptop + 30 | ≈ 2-3 h, once (two pin runs per binary, 30 binaries) |

**Steady state** per pass (toolchain range per 7.1; 42 is the working mid until receipts replace it; python lanes ≈ 10-19; a new build adds one analysis pair, one decompile and one signature run ≈ 1 h on analyzer nodes, in parallel with the rest):

| Configuration | Wall (ESTIMATE) | Speedup vs today (≈ 90-110 h steady state) |
|---|---|---|
| 4 fleet (2 + 2) + 5 toolchain-less donors | toolchain 42 / 2 node-eq ≈ 21 h; donor lanes 15 / 3.5 ≈ 4 h in parallel → ≈ 21-23 h | ≈ 4-5x |
| 4 fleet + 5 toolchain-owning donors | 42 / 4.5 ≈ 9 h | ≈ 10x |
| 4 fleet + 20 donors (≈ 2 own the toolchain) | 42 / 3 ≈ 14 h | ≈ 7x |
| 4 fleet + 20 toolchain-owning donors | 42 / 12 ≈ 3.5 h | ≈ 25x |
| 4 fleet + 100 donors (≈ 10 own the toolchain) | 42 / 7 ≈ 6 h | ≈ 15x |
| 4 fleet + 100 toolchain-owning donors | ≈ 50 min, then the floor: longest repair chain (1-2 min) + link (10-120 s) + the new build's own analysis (5-30 min) ≈ 40-75 min | ≈ 90x |
| 20 toolchain fleet nodes, any donors | 42 / 11 ≈ 4 h | ≈ 22x |

Formal Amdahl over the post-design serial fraction (link ≈ 90 s + identity/logical merge ≈ 30 s + export merge ≈ 20 s + site-key table ≈ 2 s + per-round match barriers ≈ 40 s ≈ 3-5 min of ≈ 85 h; s ≈ 0.0006-0.001): 5 nodes → 4.98x, 20 → 19.6x, 100 → 91x if every node had every capability. In steady state the toolchain-capable node count (fleet plus donors that pass the toolchain canary, whether they own the install or fetched the toolchain object) is the lever and it scales to the floor; donors with neither the toolchain nor the analyzer canary buy coverage (residue, match and parity latency) rather than wall clock, and the per-stage rows in 7.3 say so. The cold-start analyzer term is bounded by the analyzer-capable node count and by egress, and is paid once. Changed assumption (2026-09-22): the first draft assumed donors could not run the analyzer, decompile or compile lanes; every figure in 7.3 and 7.4 is an ESTIMATE under the corrected assumption that a canary-proven donor runs any lane its capability serves, so toolchain- and analyzer-capable donors buy throughput in those lanes exactly as fleet nodes do. Today's pre-design serial fraction is 50-100 % per stage (one JVM, `workers: 1`, one writer), which is why even 4 fleet nodes are a large win.

### 7.5 Work estimate — agent-hours, walking skeleton first

The figure the first draft carried here (≈ 170 working days over 38 units; ≈ 34 weeks solo; 13-16 calendar weeks with three engineers) was built up from the stage units as a **human-team estimate**. It is **not the plan** (ledger §6, user 2026-09-22; charter §6c): effort in this program is measured in agent-hours, and the delivery shape is a walking skeleton — a thin end-to-end path through every layer, built in hours by builders in parallel worktrees, with every abstraction and extension point declared up front (speculative generality to the extreme; YAGNI rejected) — followed by adapters behind the interfaces the skeleton already fixed. What that is for this design:

| Slice | What it is | Status (branch head `a4e4aca`, 2026-09-22) |
|---|---|---|
| Skeleton, plan U120–U124 | the contract (Protocols, records, task ids, registries); objects + tasks + config; log + heads + frontier + signing + compaction; view + pipeline lanes + CLI; worker + verify + fleet + transport — one working implementation per layer, every other adapter declared with a named slot and a named refusal | landed by parallel builders in one day (`d8447f6` … `a4e4aca`) |
| Integrator pass, plan U125 | reconcile the names each slice assumed; one "grid of one" cycle on a laptop (publish → work → verify → materialize); the documented walkthrough | next |
| Adapters, plan U126–U170 | each unit turns one declared adapter, canary, provider or lane into a working one behind the interface the skeleton fixed (section 8; plan Phase 15), interleaved with the plan's remaining phases | as units, hour-class each |

Interim wins that need no grid and remain worth doing first (hour-class each): per-round checkpoint in `corpus.match-pair`; bsim_hit in the matcher digest; timeout on the parity node path; `needs_raw_image` honoured in backfill; de-dup of the terminal pass's double compile.

---

## 8. Plan phase: Phase 15 — distributed compute

**Walking skeleton first** (charter §6c). The plan's Phase 15 lists the units in the order they are built — skeleton U120–U125, then adapters — and its numbering is authoritative. This section keeps its original unit ids as the detailed specification behind those bullets (owned paths, acceptance clauses, prerequisites); the map below is the bridge and every id in this section is read through it. Per the loop charter (§6b) no tests are written or run until the plan, design and diagrams converge and the build completes; each unit names the test it will land. Prerequisites from earlier phases: U54 basis fields and per-binary `basis_hash` (plan:455-481), U65 timeout policy, U66 receipts (read as the kind's basis projection, 2.8), the A4/R3 content-hash backfill (R3 landed `6d95a40`/`40d50ce`; A4 admission pending), A1/A2 bounded commits (landed `a501e9d`), R1 (repo and store off the USB drive; read-only commands on it exceeded 120 s this session).

| Design id (this section) | Plan Phase 15 id | Status at `a4e4aca` |
|---|---|---|
| U120 slim distribution and package skeleton | U120 contract (`agentdecompile_grid.core` + packaging + `adgrid` entry point) | ✔ `d8447f6` |
| U121 object store adapters | U121 objects + tasks + config (local adapter working; `s3`, static mirror, peer, layered declared); the declared adapters become working in plan U159 (S3 conditional PUT), U160 (static mirror + rsync), U161 (peer HTTP) | ✔ `7cc0b63`, `c575411`, `b147f99` |
| U122 logs, heads, frontier, outbox | U122 log + heads + frontier + signing + compaction | ✔ `515fd47`, `95e8428` |
| U123 compaction snapshots | absorbed into plan U122 (checkpoints, prune); pruning and retention policies → plan U170 | ✔ / adapter |
| U124 worker runtime with kill deadlines | plan U124 (work loop, kill deadlines, outbox; `tasks/registry.py` landed in plan U121); container sandbox → plan U166; `basis_fields(kind)` lists → plan U158 | ✔ `8eb5202`, `a4e4aca` |
| U125 join, attach-first, capability canaries | absorbed into plan U124 (attach-first join, canary framework, `python-canary`); the toolchain, analyzer and parity canaries as working adapters → plan U163, U164, U165. **The plan's U125 is the integrator pass, not this unit** | ✔ / adapters |
| U126 roles, keys, invites, revocation, rate limits | plan U126 (Ed25519 as the default signer; invites, revocation list, per-key rate limits, key lifetime; the two-lineage invariant) | adapter |
| U127 verifier loop, independent keys, proposal caps | absorbed into plan U124 (verifier loop with independence; caps in the frontier); its named tests stay with plan U124/U156 | ✔ |
| U128 view materialisation and appliers | absorbed into plan U123 (`SQLiteViewApplier`, `grid_*` tables, materialize); the similarity applier → plan U169 | ✔ `eecfcaf`, `85784cc` |
| U129 fleet bootstrap | plan U129 (cloud providers oci/hetzner/aws/gcp with `fleet up/down/status/replace`; `manual` and `ssh` landed in plan U124) | adapter |
| U130–U157 | the same ids in the plan (U143 and U150 retitled as delta binders) | adapters and lanes |
| — | plan U158 basis projection per kind (2.8); U162 HTTPS outbound-only transport with presigned write-once PUT (6.1); U167 idle policies (`--idle-only`, battery, user activity); U168 `corpus-attest` lane (after U28x); U169 similarity applier; U170 compaction pruning policies | new in the plan |

### 15.0 Substrate — the walking skeleton and the adapters it declares

**U120 Slim distribution and package skeleton.** Owns: `pyproject.toml` (a second distribution `agentdecompile-grid` with its own entry point `adgrid`, no analyzer bindings, no dashboard), `src/agentdecompile_grid/__init__.py`, `src/agentdecompile_recovery/grid_lanes/__init__.py`, an import-boundary test. Acceptance: `uvx agentdecompile-grid --version` works from a wheel that contains no `agentdecompile_recovery` module; an import of `agentdecompile_recovery` from anywhere under `agentdecompile_grid` fails the boundary test. Prereq: none.

**U121 Object store adapters.** Owns: `src/agentdecompile_grid/objects/{local,s3,mirror,peer}.py`, GC and size cap, metadata tags (6.3). Acceptance: write-once semantics on every adapter (a second PUT of a different body under the same hash is refused); a store at its cap GCs unreferenced objects and refuses new writes with a named error (R2); a presigned GET is issued for any object an offered task names as an input and refused by name (`not-an-input`) for any other; the tag is read from metadata, never from the path; no object path under the USB mount appears in any receipt. Prereq: U120.

**U122 Logs, heads, frontier, outbox.** Owns: `src/agentdecompile_grid/log/{records,chain,heads,frontier,checkpoint_index,outbox}.py`. Acceptance: (a) two workers appending to one sub-partition under conditional PUT with the stated backoff reach 1,000 records each with no writer starved beyond 30 s (chaos test with induced CAS failure rate 50 %); (b) a head-store outage leaves workers computing from the last checkpoint-index and flushing outboxes afterwards with identical record ids; (c) heads rebuilt by chain scan equal the live heads; (d) batch records containing 64 record hashes verify offline; (e) the frontier over a partition is identical on two nodes given the same objects. Prereq: U121.

**U123 Compaction snapshots.** Owns: `src/agentdecompile_grid/log/snapshot.py`. Acceptance: a node bootstrapping from snapshot + tail derives the same frontier as one replaying the full chain; a prior-basis partition is archived under one snapshot and its records are prunable; a 1 GB node's resident set for 100 partitions stays under 200 MB (ESTIMATE target; measured). Prereq: U122.

**U124 Worker runtime with kill deadlines.** Owns: `src/agentdecompile_grid/worker/{loop,sandbox,deadline}.py`, `tasks/registry.py`. Acceptance: a task that sleeps forever is killed at its class deadline and a `result-timeout` record exists within deadline + 5 s; three timeouts from independent keys yield `task-poison` and an unresolved export entry; a killed worker leaves no partial result object; duplicate execution of one task yields one identical object (second upload is a no-op); every registered kind declares a `basis_fields` list (explicitly empty only where the 2.8 table says so) or is refused registration by name; changing `pin_policy` or any `timeout_policy.<kind>.wall_s` leaves every compile-attempt id unchanged; changing `toolchain_identity_hash` changes every compile-attempt id and no decompile-chunk id; changing `analyzer.options_hash` changes every decompile-chunk id and no compile-attempt id. Prereq: U122.

**U125 Join, attach-first, capability canaries.** Owns: `src/agentdecompile_grid/worker/{join,canary}.py`, `join.sh`. Acceptance: `join` against a running local agent attaches and prints status; `EADDRINUSE` is reported as already owned and never retried as a start; capabilities appear only after the pinned fixture hashes match (`python`, `parity:<hash>`, `toolchain:<hash>`, `analyzer:<version>`, `objdump`); a node with a different parity-checker binary hash advertises a different capability and is not offered tasks keyed to the pinned verifier; `rejoin` re-proves and re-binds capabilities; a node whose canaries pass but which no open lane currently needs is told `no-lane-open` by name, with the canary that would open each lane, rather than idling. Prereq: U124.

**U126 Roles, keys, invites, revocation, rate limits.** Owns: `src/agentdecompile_grid/worker/keys.py`, `verify/roles.py`. Acceptance: a fleet key can sign a donor and a fleet invite; a revoked key's records are ignored by the frontier within one checkpoint interval; per-key rate limits refuse the 65th record in a minute with a named reason; keys expire at 7 days and renew only after a canary re-run; the fleet key set always contains at least two keys with disjoint invite ancestry, and an invite that would leave only one lineage is refused by name. Prereq: U125.

**U127 Verifier loop, independent keys, proposal caps.** Owns: `src/agentdecompile_grid/verify/{loop,masked_coff,parity,caps}.py`. Acceptance: a `result-verified` record is never produced by the key that produced the proposal or by a key it invited; a fifth proposal for one task is dropped at append with a reason; a task with unverified proposals is not offered for generation; a donated object equal to the target bytes with junk source is refuted (byte-emitter test); masked-COFF hashes of the same object with different `TimeDateStamp` are equal. Prereq: U124, U126.

**U128 View materialisation and appliers.** Owns: `src/agentdecompile_grid/view/{materialize,applier}.py`, adapters in `grid_lanes/views.py`. Acceptance: materialising twice from the same verified set yields identical row dumps; no worker process ever opens a view for writing (grep test); with a foreign writer holding the store lock for 400 s (the attestation's hold-lock probe) every compute task still completes and the applier reports `view-stale` by name (H1); the similarity index rebuilt from merged-signature objects lists the same executables and functions. Prereq: U127.

**U129 Fleet bootstrap.** Owns: `src/agentdecompile_grid/fleet/{cloudinit,providers/*.py,manifest}.py`. Acceptance: `adgrid fleet up --provider <a> --count 2 --role fleet` renders user-data whose only step is the join command, creates two instances through the provider adapter, and records a manifest object; an ARM node fails the toolchain canary and is offered no toolchain task; `fleet down` reclaims and records it. Prereq: U125, U126.

**U130 Observer-path fixes (prerequisite for strangers).** Owns: `src/agentdecompile_recovery/exchange/routes.py` and the dashboard SSE path (2026-09-08 §6b: shared snapshot, connection cap, hidden-tab gating). Acceptance: 200 simulated browser connections hold one snapshot computation per interval; the 201st is refused by name. Prereq: none (parallel).

**U131 Measurements.** Owns: receipts under the grid's measurement partition. Acceptance: receipts exist for (a) headless open, save+pack, packed-program size and JVM start on a multi-MB image (R12); (b) O2: masked-COFF equality of >= 500 real TUs compiled on two toolchain nodes, with the differing fields named if any; (c) `/P` equivalence over >= 200 TUs; (d) link wall time on the reference object set; (e) per-scan window cost; (f) one real permuter search (trials/s, seed-flag support); (g) native vs wasm parity timing on a real pair; (h) attempts per function over one full compile pass of the reference build (both populations), the input to the compile-pass row. Prereq: U125 (canaries give the nodes).

### 15.1 Toolchain lanes

**U132 Toolchain object and content-hash identity.** Owns: `grid_lanes/toolchain.py`, changes at source_parity_synthesize.py:21705-21722 and source_plugin_runner.py:369-394. Acceptance: two nodes holding the toolchain at different paths and mtimes derive identical `toolchain_identity_hash` and identical compile task ids; two installs of the same toolchain that differ only outside the manifest (extra SDK directories, missing documentation, different prefix files) derive the same identity; flipping one byte of any manifest file changes both; the toolchain root on the USB drive vs the fast disk yields the same hash; the manifest list is stored as a receipt object under the identity. Prereq: U121.

**U133 compile-attempt adapter, persistent wineserver, per-node cap.** Owns: `grid_lanes/compile.py`, scripts/cl-compile.sh (template without absolute paths). Acceptance: same TU on two nodes gives the same task id and (if O2 holds) equal masked-COFF hashes; a re-run with an existing result spawns no compiler; INFRA leaves no object and the task reappears after intent expiry; 200 consecutive attempts on one node show no plateau (ghidra_bulk.py:965-970) and each receipt carries wall time; the canary TU matches the pinned hash before any toolchain task is offered. Prereq: U124, U132.

**U134 Repair chain as a derived graph.** Owns: `grid_lanes/repair.py` (lifting ghidra_bulk.py:1289-1370 into a stateless step function). Acceptance: replaying a recorded chain on a second node reproduces every intermediate TU hash; killing the worker between any two attempts and resuming elsewhere yields the identical final result; no task spawns more than one compiler process; the LLM step is emitted as a `rewrite` task, never inline. Prereq: U133.

**U135 Content caches, link task, readable-tree unification.** Owns: compile_link.py:95-102, :130-154, :239-306, :165-200; `grid_lanes/link.py`. Acceptance: a fresh checkout with rewritten mtimes hits every cached object; changing one TU recompiles exactly one unit and triggers exactly one link; identical sorted object-set hash is a link cache hit with no linker spawn; the response file contains no host path; the tree compile over a tree whose objects exist spawns zero compiles. Prereq: U133.

**U136 Parity lane.** Owns: `grid_lanes/parity.py`, `grid_lanes/mkobj_target.py`, objdiff_check.py (timeout), seed_validation.py:353-357 (named sides). Acceptance: native and wasm verifiers with pinned ids derive the same task id and, for the same verifier, byte-identical canonical receipts; a stubbed verifier that never returns yields a timeout receipt within 10 s per pair and 60 s per envelope; a node without `objdump` refuses `mkobj-target` by name; two nodes with it emit byte-identical target objects; killing a worker mid-envelope leaves completed pairs and a second lease completes only the rest; the compile → parity → repair chain completes across three nodes with no inline verifier call. Prereq: U124, U127.

### 15.2 Analyzer lanes

**U137 Import, analysis slices, deterministic pin.** Owns: `grid_lanes/analysis.py`, headless scripts, ghidra_context.py:200-212 (retire discard), acquire.py:144-150 (re-key). Acceptance: A1 two nodes importing the same image produce packed programs with identical canonical inventory and memory-block hashes; A2.1 k slices converge to `analysis_idle`; **A2.2 (spike first)** sliced final packed program vs monolithic analysis on a fixture: inventory hash and address map compared, verdict recorded in `timeout_policy`; A2.3 killing a node mid-slice and resuming on a second node passes A2.2 against the first; A3 a second request for the same (image, basis) starts no JVM; a basis change produces a new id and no reuse; pin: two independent keys agreeing pin; disagreeing keys produce a `pin-divergence` record and the lexmin rule pins deterministically; the pin policy is a basis field. Prereq: U124, U127, U131(a).

**U138 JVM-free facts and the References reader.** Owns: `grid_lanes/facts.py`, `src/agentdecompile_recovery/ghidra_db/references.py` (new), optional `decoder.py` (U138b, a basis change). Acceptance: names/functions/comments/memory/composite rows equal the JVM tier-1 extractor's rows byte-for-byte after canonicalisation; calledge rows from the References reader equal the JVM-inserted rows (extract.py:344-360) on the fixture; U138b: mnemonic-class profile per function equals the JVM value, else the lane stays JVM by name. Prereq: U137.

**U139 Decompile chunks, affinity, knowledge view.** Owns: `grid_lanes/decompile.py`, workflow.py:117-160 and :565-628 (replaced by a reader). Acceptance: same packed program on two nodes gives byte-identical inventory and shard ids; rows for a fixture equal today's script's rows once both use the pinned options; a function over the per-function cap yields `timed_out: true` under `task_wall_s`; SIGTERM mid-shard: union of partial + continuation equals the full shard; materialised KB is byte-identical across two materialisations; no worker opens the KB for writing. Prereq: U137, U128.

**U140 H2 closure and object tags.** Owns: program_analysis.py:127-138 (advisory intent with TTL), `objects` metadata tags for image-bearing objects (6.3). Acceptance: a deliberately hung slice is reported as failover within budget + TTL and re-leased by another node; no path waits without a deadline; a packed program is fetched by any key whose offered task names it and refused by name to a key with no such task. Prereq: U121, U137.

**U141 Similarity signatures and queries.** Owns: `grid_lanes/bsim.py`, preparation.py:1953-2015 (range variant, pinned template only), catalog.py:418 (applier), determinism_basis.py:62-69 (generator revision producer). Acceptance: fragments over disjoint ranges union to the whole-program run's function count and vector bytes; a config without a template name is refused; the composability probe records accepts/rejects and `bsim-merge` reproduces the whole-program listing; dropping the index and re-materialising reproduces the inventory; changing template or generator revision changes every task id; `_fuse_bsim` reports hits used > 0 on a fixture pair; python (similarity, significance) equals the client's bit-for-bit or the lane is marked advisory-only by receipt. Prereq: U137, U128.

### 15.3 Identity lanes

**U142 Match cascade decomposed.** Owns: `grid_lanes/match.py`, propagate.py (interim per-round checkpoint first), preparation.py:2090-2107 (v2 digest with bsim_hit). Acceptance: P0 a pair killed at the 1800 s executor deadline resumes from its last round; P1 slice hash identical across the harness's layouts and changes when one bsim_hit row changes; P2 sharded execution with shard sizes 1/64/1024, shuffled, across two nodes yields match rows byte-identical to the monolithic `match_binaries`; SIGKILL mid-round + resume gives the same rows; the longest real pair completes as a chain with no member over 60 s; two different outputs for one shard id are a refutation, never a merge. Prereq: U124, U127.

**U143 Logical build shards, identity merge, view applier.** Owns: `grid_lanes/logical.py`, `grid_lanes/identity.py`, logical.py, workflow.py:446-542. Acceptance: fragments merged in key order equal `logical.build`'s rows on the attestation store copy (291k/74k rows); the delta applied by the applier reproduces merge-evidence's identity rows; families merged concurrently on two nodes are byte-identical; the content-hash refusal is a named record before any fragment. Prereq: U142, U128.

**U144 Cross-place as placement objects.** Owns: `grid_lanes/cross_place.py`, cross_place.py:19-52. Acceptance: placement objects identical on two nodes regardless of destination filesystem state; the placed body hash identical across all recipients (banner in metadata); two siblings sharing a profile produce exactly one compile task for the shared body; no plaintext program name in any payload; a profile-per-family count and a same-toolchain-class recipient count per logical are recorded as receipts (the dedupe and recipient rows' inputs). Prereq: U133, U143.

### 15.4 Residue lanes

**U145 Permuter case, search shards, progress records.** Owns: `grid_lanes/permuter.py`, permuter_harness.py (deadline-safe harvest). Acceptance: bundle hash identical on two nodes with no absolute path; non-compiling base → `case-refused`; shard p99 <= 35 s; output found before the deadline is reported; with a seed flag two nodes given the same range report the same best hash, else both are distinct proposals; after a verified win no shard for that case is offered; covered ranges never overlap; a worker restarted from the checkpoint-index alone continues. Prereq: U133, U127, U131(f).

**U146 Rewrite adapter and win verifier.** Owns: `grid_lanes/rewrite.py` over producers.py:155-213, rewrite_queue.py:161-163. Acceptance: the same source under two bases yields two task ids; a foreign-basis proposal is ignored; an artifact over 64 KiB is rejected; a proposal whose object equals the target but whose source does not recompile to it is refuted; a genuine win is verified only by an independent key. Prereq: U127, U133.

**U147 Text permuter in-tree, generate/score split.** Owns: `grid_lanes/text_permute.py`, text_permuter_watch.py:33-42. Acceptance: generate runs on a node with no toolchain; score returns per-candidate masked diffs in one batch <= 60 s; no plaintext name in any payload. Prereq: U133.

### 15.5 Export and relink lanes

**U148 Export slices, shards, merge.** Owns: `grid_lanes/export.py`, export_hookpack.py (site-key table, shard, merge). Acceptance: slice and key-table objects byte-identical across runs and hash seeds; the key table reproduces the 41,210 suffixed keys on the attestation corpus; merged pack byte-identical to the single-process export (74,205 sites, 120 MB); a second run at identical basis performs zero shard recomputation; a missing fragment is a named merge refusal. Prereq: U128.

**U149 Window index and shards.** Owns: `grid_lanes/windows.py`. Acceptance: window results equal `unique_window` on the build with a registered image (11,039 / 1,039); per-scan cost recorded and the index decision taken from it; window objects reused unchanged after an identity-only change; image objects fetched by hash as task inputs by whichever key the task is offered to. Prereq: U121, U148, U131(e).

**U150 Backfill as records.** Owns: `grid_lanes/backfill.py`, backfill.py:57-64, :151. Acceptance: a recorded backfill replays identically on both surfaces (U66/U110); `stamp-basis` refuses when the declared identity object's basis hash differs from the package's; the analyzer_identity pass over 90 rows completes in ≈ 1 s with no raw-image reads; a held lock produces a named `locked` refusal within busy_timeout. Prereq: U128.

**U151 verify-determinism as a receipt gate; anonymisation.** Owns: `grid_lanes/determinism.py`, determinism_basis.py:320-340 (kept as diagnostic). Acceptance: gate (a) returns `identical: true` in < 5 s on the attestation corpus with no store copy written; a perturbed fragment is caught by gate (b) with `first_diff_path`; a grep of the object store for any registered slug or repo path returns nothing. Prereq: U148.

**U152 Place-check, splice shards, image join.** Owns: `grid_lanes/relink.py`, whole_image_relink.py:28-46, :98, :142-149. Acceptance: placement objects identical across nodes; a mismatching placement is never emitted; N shards joined reproduce the legacy rebuild byte-for-byte; a target failing the alignment assertion is refused by name; one changed placement re-runs exactly one shard and one join; a single-byte corruption is localised to block/offset/section/address without a byte scan. Prereq: U133, U127.

**U153 Closure-based terminal receipt, compile de-dup, watch viewer.** Owns: verify_direct_full_image.py, verify_full_image_receipt.py, matching_watch.py:29-101. Acceptance: a receipt built entirely from cache-hit objects is accepted; a closure member whose projection for its kind differs from the current basis's is refused naming the field; `wholeFileByteIdentical` and `verified` stay separate claims; the compile count for a fresh terminal run halves; the watch status is produced from the checkpoint-index with zero rebuilds. Prereq: U152, U135.

### 15.6 Surfaces and hardening

**U154 Browser lane.** Owns: `src/agentdecompile_grid/worker/browser/` (module worker), the donate page over the exchange gateway routes. Acceptance: a browser worker fetches two objects by hash, runs the wasm parity checker and PUTs a signed receipt matching the native receipt byte-for-byte after canonicalisation; a rewrite proposal with the contributor's own key appears as `result-proposed`; one click stops it; it is never offered a toolchain or analyzer task because its canaries cannot prove those capabilities. Prereq: U125, U130, U136.

**U155 Bundle manifest stub (U87 shape).** Owns: `grid_lanes/bundle.py`. Acceptance: two bundle runs under one basis produce a byte-identical tree; the manifest refuses when an artifact is absent; the pack layout decision (single JSON vs directory of shards) is recorded with measured merge costs. Prereq: U148.

**U156 Grid determinism harness and chaos tests.** Owns: `tests/grid/`. Acceptance: same inputs → same task ids and result hashes on two nodes for every kind; chaos: lease expiry mid-task, duplicate delivery, head loss, disconnected outbox, basis change mid-run, CAS starvation injection, verifier livelock injection (generation offered faster than verification), a single-field basis change mid-run (re-keys only the kinds whose projection names it, asserted per kind against the registry) all leave the frontier consistent and never write a verified record from a producing key. Prereq: all lanes.

**U157 Retire the coordinator.** Owns: jobs.py:341-400, preparation.py:487-540, workflow.py:26-27 and :384-392, exchange/store.py persistence. Acceptance: `workbench.prepare` draws receipts and starts nothing; the exchange snapshot file is no longer written; `--enable-exchange` routes to the grid gateway only. Prereq: U139, U142, U148, U154.

---

## 9. Risks and the register rows they add

Hangs and starvation first, per the register's top class. Each row: risk, where it bites, mitigation in this design, and the register row proposed. The `#` column is a per-table index; the register id a row will occupy is the one named in its Register-row cell (`New Rn`, `New Hn`, `Extends Rn`); 9.4 proposes no register rows and its S1-S5 are table-local, distinct from the register's anticipated S1-S17.

### 9.1 Hangs and starvation

| # | Risk | Mitigation | Register row |
|---|---|---|---|
| H7 | **Head CAS hot-key starvation**: many writers on one conditional-PUT key with no fairness; the unluckiest writer never wins. | Sub-partition heads by task-id prefix; batch records; full-jitter backoff with rotation to another partition after 8 failures; reads never touch heads (checkpoint-index). Chaos test in U122 with 50 % induced CAS failure. | New H7: CAS retry storms on a hot partition; detect by per-head retry rate > 10 %; response: widen the prefix for that lane (a basis-free config change). |
| H8 | **Verification funnel livelock**: proposals arrive faster than independent-key verification drains; the same task keeps being re-offered. | 4-proposal cap per task; verification-before-generation ordering; no re-offer while unverified proposals exist; verification tasks carry kill deadlines. | New H8: unverified-proposal backlog; metric = oldest unverified proposal age per partition; response: add verifier keys (fleet), never relax the cap. |
| H9 | **Worker wedge**: a hung compiler under the compatibility layer, a stuck JVM open, or the parity checker's node path (no timeout at objdiff_check.py:42) holds a slot forever on an unattended node. | Worker-owned subprocess-group kill at the class deadline; `result-timeout` records; poison after 3 independent timeouts; timeout added to every parity path. | Extends H2: every task kind has a recorded deadline in `timeout_policy`; a slot held past deadline + 5 s is a defect. |
| H10 | **Analysis slice never converges** (`analysis_idle` never true because a resumed queue keeps enqueuing). | Slice count cap per binary (default 10) → `task-poison` with the last packed program pinned as partial and the binary exported as unresolved; the A2.2 spike decides the default slice budget. | New H10: analysis slice cap exceeded; response: raise the budget for that image class, never wait. |
| H11 | **View applier lag masquerading as progress**: the frontier advances while the SQLite view is stale, and a consumer reads stale identity. | `view-stale` is a named state with an age; consumers of identity (export, readiness, surfaces) read the pinned logical/identity objects by hash, not the view, when the view age exceeds a bound (default 10 min). | Demotes H1 to a view-freshness metric; adds H11: view age bound. |
| H12 | **Disconnected duplicate work**: workers on stale frontiers redo tasks. | Bounded by checkpoint-index freshness (60 s) and advisory intents; wasted compute only. | Note under H7; no new row. |
| H13 | **Operator liveness**: invites, revocation, toolchain mirror, view applier all on one NAT'd laptop. | Fleet keys sign invites and extend revocation; fleet nodes mirror image and toolchain objects and run appliers. | New H13: single operator host on any liveness path is a defect; acceptance in U126/U128. |

### 9.2 Determinism and trust

| # | Risk | Mitigation | Register row |
|---|---|---|---|
| T1 | A hijacked or provider-reclaimed fleet node with a valid key. | Its records are proposals; independent-key verification; short-lived keys; revocation. | New T1: fleet compromise is never a correctness risk; verified by the byte-emitter and self-verification tests in U127. |
| T2 | O2 false (compile not byte-deterministic across hosts). | Verification degrades to recompile + parity (1-3 s) and the compile cache keys on toolchain hash; the design works, slower. Measured in U131 and by every join canary. | Existing O2 stays open until U131 lands a receipt. |
| T3 | Analyzer non-determinism (plan:631) produces divergent packed programs; a re-baseline shifts function boundaries (S8). | Two-key agreement pin; `pin-divergence` records with the lexmin rule; pin policy in the basis; U25 re-baseline is mandatory on a policy change. | New T3: pin divergence rate per corpus; a rate above 10 % is a basis-tightening finding, but the pipeline never stalls on it. |
| T4 | Sybil: one donor with many keys. | No quorum anywhere; keys only rate-limit; independent-key verification requires keys not invited by the producer, and donor keys are never verifier keys. | Covered by T1; no new row. |
| T5 | `/P` preprocessing changes bytes. | Not load-bearing; measured in U131 before landing; fallback is the TU text as is. | Note under O2. |
| T6 | `mkobj` host dependence yields different target objects per node. | `mkobj-target` pinned, `objdump` a declared capability with a named refusal. | New T6: unpinned target objects are a defect; acceptance in U136. |
| T7 | Donor `.bin` / `.obj` as evidence. | Never evidence; source text only; recompile under an independent key. | Covered by the claim boundary; U127 test. |

### 9.3 Resources and providers

| # | Risk | Mitigation | Register row |
|---|---|---|---|
| P1 | Free-tier provider policy: instance-hour quotas, egress caps, idle reclamation, sustained-compute clauses; hosted-CI minutes are not a compute farm. | Hosted-CI excluded from the default provider set; fleet nodes are preemptible by design (advisory intents); egress bounded by nodes-per-program caps; `--idle-only` and attributed work on donors. | New P1: provider policy; a fleet loss stalls, never loses, work. |
| R4 | Local object store fills the fast disk (R2 at 97 %). | Size cap and GC; refusal by name at the cap; USB drive archive-only. | Extends R2. |
| R5 | Packed-program size (R12) at the high end makes decompile fan-out egress-bound. | Nodes-per-program cap; fewer bigger analyzer nodes; measured in U131. | New R12: packed-program size and headless open time unmeasured; closes when U131(a) files its receipt. |
| R7 | Head-store backend lacks conditional writes. | Fallback Postgres-class head table across fleet nodes: pointers only, rebuildable by chain scan, but a service to run. | New R13: head-store backend choice recorded; the fallback's rebuild test is in U122. |
| R8 | Compatibility-layer saturation on small nodes (the 2026-08-30 plateau). | Persistent wineserver, per-node cap, measured in U133. | Note under H6 (compile-pool and lane starvation, register H6); no new row. |

### 9.4 Scope and product

| # | Risk | Mitigation |
|---|---|---|
| S1 | Scope creep into quorum/credit/reputation when the first liar appears. | The answer is hash verification only; U127's tests fail if a vote path is added. |
| S2 | The grid package grows pipeline concepts. | Import-boundary test (U120); lanes live under `agentdecompile_recovery/grid_lanes/`. |
| S3 | Product or program names leak into task payloads, receipts or object names. | Hashed-slug rule enforced by U151's grep acceptance; no plaintext slug in any object. |
| S4 | Two coordination paths during migration (exchange snapshot + grid log). | U157 retires the snapshot; `--enable-exchange` routes to the grid gateway only. |
| S5 | Donor-facing value is thin for donors with neither the toolchain nor the analyzer canary (their lanes are ~10 % of bounded work). | Stated honestly in section 7; the browser and python lanes are an on-ramp and a residue sink, not the wall-clock lever; the join flow tells such a donor which canary would open which lane. |

---

## 10. Open questions with defaults

| # | Question | Default until decided |
|---|---|---|
| Q1 | Head-store backend: bucket conditional PUT or a Postgres-class head table? | Bucket conditional PUT; the head table is the fallback and its rebuild path is tested either way (U122). |
| Q2 | Pin policy for the analyzer artifact: two-key agreement or operator-key only? | Two-key agreement with lexmin fallback on divergence; recorded in the basis. Operator-key-only is allowed for a corpus with one analyzer node, recorded as a different policy value. |
| Q4 | Slice budget for analysis and whether slice-and-resume converges (A2.2). | 300 s slices, cap 10 per binary; if A2.2 fails, one slice per binary sized to the measured p95 analysis time and preemption costs one analysis. |
| Q5 | O2 (cross-host byte determinism of the compile). | Assume no until U131's receipt; verification is recompile + parity. |
| Q6 | `/P` preprocessed inputs. | Off; TU text is shipped as is; turn on only after the U131 equivalence receipt. |
| Q7 | Default shard sizes (decompile 16, match 512-1024 addresses, parity envelopes 60-300 pairs, signatures 128). | As listed; each is a parameter re-set from the first measured p99 in that lane. |
| Q8 | Proposal cap per task. | 4. |
| Q9 | Key lifetime and canary re-run interval. | 7 days; re-canary on rejoin and on every key renewal. |
| Q10 | Pack layout for export (single 120 MB JSON vs directory of shards + manifest, U87). | Single JSON kept for byte-compatibility until U155 records merge costs; the directory layout is the expected outcome. |
| Q11 | Whether the pinned search checkout accepts a seed flag. | Assume no; N independent short runs with distinct seeding; result verification is what matters. |
| Q12 | Does the similarity index accept N fragment files per executable? | Assume no; `bsim-merge` produces one canonical file; the probe in U141 decides. |
| Q13 | Python cosine/significance path for similarity queries. | Advisory-only until bit-exact against the client on a fixture (U141). |
| Q14 | Provider adapters in the first fleet unit. | One always-free ARM tier (analyzer) and one x86 micro tier (toolchain); hosted-CI excluded. |
| Q15 | When does the exchange's HTTP gateway retire? | After U154 moves the browser lane; `--enable-exchange` then routes to the grid only (U157). |
| Q18 | Where is each kind's basis projection declared: the grid task registry or the plan's U54 basis object? | The registry declares `basis_fields(kind)` as field paths (2.8; plan U158); U54's basis object is the vocabulary those paths must resolve in; U156 asserts every kind declares one. |
| Q19 | Does the analysis slice budget enter the analysis kinds' projection? | Not by default: it is a task param (3.1) and completed slices are reused as content-addressed inputs; it enters only if A2.2 records non-convergence (2.8). |
| Q20 | Does the compile-attempt input stay header-free text, so headers stay out of the toolchain manifest? | Yes (4 row 3; Q6 off); if `/P` is ever turned on the preprocessed text is still the input and headers still stay out; if a lane ever ships headers, they join the manifest by the same relative-path rule (1.5 (a)). |
| Q21 | Who signs a key renewal when the operator is offline, and does a renewed key keep its lineage? | Self-renewal before expiry under the still-valid key after the canary re-run (Q9), lineage preserved; after expiry, a fresh invite from any live key of another lineage (U126). Recorded as a default; no amendment (residue of a killed round-5 finding). |
| Q22 | Does a repair chain continue on the worker that produced the last diagnostics, or is every hop re-dispatched? | The producing worker continues while its intent lives; the chain object is the resume point; relocation only on kill or intent expiry (3.3, U134). Recorded as a default; no amendment (residue of a killed round-5 finding). |
| Q23 | Is the search engine a pinned, content-addressed input, and does it accept a seed flag? | Q11's default stands (assume no seed flag; N independent short runs); the engine revision hash is recorded in every search-shard receipt and a node without the pinned revision is not offered `search-shard` (U125 canary). U145 is not blocked (residue of a killed round-5 finding). |
| Q24 | What free-tier egress cap applies per provider adapter, and is intra-region fleet traffic exempt? | A basis-free config value per adapter, cited in P1 once known; intra-fleet peer HTTP is the mirror path (6.1); no refusal mechanism is added (residue of a killed round-5 finding). |
| Q25 | Which unit gives `runtime_claim` promotion (`bind_identities`, audit 3) and pause/resume scope a record kind, so no surface remains a foreign writer of the view after U157? | U128 adds `runtime-claim` and `override` record kinds applied at materialisation (6.4 already names override records); until then those surfaces are listed under S4 as the second coordination path. |

Q3, Q16 and Q17 are not in this table (withdrawn 2026-09-22, plan audit 4).

---

## 11. Compliance table

| Requirement / thesis point | Where discharged |
|---|---|
| (1) One-command join, browser where genuinely useful | 1.3, 1.4, 6.1; browser limited to rewrite, parity-wasm, text-permute (3.6, U154) |
| (2) No permanent bottleneck opted into | 7.4 steady-state column (toolchain-capable nodes scale to the floor: 8x / 25x / 90x), 7.2 (mass reduction + canary-proven toolchain/analyzer donors + fleet), 2.1-2.3 (no stateful device), 9.1 H13 (no operator liveness single point); the cold-start analyzer term is one-time and bounded by the analyzer-capable node count and egress, not by a fixed property; remaining capacity bounds are the canary-proven node count per capability, egress and RAM, stated in 7.3 |
| (3) Miniature, non-blocking tasks; long steps checkpointed and resumable elsewhere | 3.1-3.9 (every kind with class, checkpoint, serial), 2.7 (kill deadlines), 4 (compile), 5.2 (analysis slices) |
| (4) State stateless or concurrently updatable; no single stateful database | 2.1-2.4; SQLite and the similarity index are views; heads are pointers rebuilt by chain scan |
| (5) Realistic speedups and work | 7.1-7.4 with bases (ESTIMATES under the capability-only assumption); 7.5: the walking skeleton landed in agent-hours, adapters as units; the 170-day figure is a human-team estimate and not the plan |
| Determinism basis and Autonomy rule; proposal verified by hash, never trusted | 2.5-2.8, 5.3, 6.4; fleet output is a proposal; no human gate anywhere (timeouts, poison, divergence all emit records) |
| Thesis 1 deterministic and model-free | 3.3/3.6: the LLM is one bounded `rewrite` proposal lane with budget 1 per function; no path depends on it |
| Thesis 2 potato laptop → concurrency → compute that is not ours; reusable package | 1.2 (import boundary), 2.4 (local-only materialised view works with zero fleet), 1.4 (fleet), 7.5 interim wins |
| Thesis 3 miniature only | 3.x; the only large-class tasks are link and analysis slices, both checkpointed or unsplittable by bytes |
| Thesis 4 no single stateful device; I/O bottlenecks are defects | 2.1-2.4, 9.1 H11, 9.3 R4 |
| Thesis 5 small projects reclaimed; none opts the whole into a bottleneck | U157 retires the coordinator and the exchange snapshot; every lane is an adapter over the same substrate |
| New package under `src/` with an idiomatic name | `src/agentdecompile_grid/` (1.2) |
| No product names | Generic wording throughout; hashed slugs enforced by U151 |
