# K1 GOG exact-recovery throughput redesign

Status: active design and implementation plan. This plan does not declare any
candidate accepted, any historical receipt current, or the full-image goal done.
Owner: AgentDecompile recovery pipeline, with KotorXID/Mizuchi adapters where
needed.

Latest delivered runtime slice (2026-10-04): the NVMe 8080 preparation listing
now reuses bounded compact durable projections and scopes fresh child-job
observation to the displayed preparations. Independent review preceded scoped
in-process activation. Three spaced browser reads fell from 203/550/257 ms to
12/36/15 ms; all nine complete response records were unchanged. PID/start time
were unchanged and the reloader reported zero restarts. This small live sample
is dashboard latency evidence only, not improved exact-match yield. Compiler,
candidate-custody and verifier work below remains isolated until explicitly
integrated and accepted through the dashboard.

Current isolated slice: provisional compiler recipes and bounded preserved-C
waves retain exact compiler-input bytes, generated object identity, independent
raw-byte and objdiff results, exclusions and failed attempts. Timeout/signal or
uncertain compile-call outcomes stop further candidates pending resource
clearance. This is not yet a dashboard-admitted run. Next deliverable is the
parser-derived wave action using the existing shared compiler/Wine admission
lifecycle, followed by a bounded live receipt; no new model workers are needed
to exercise the preserved-C lane. Retry-ledger repair and feedback-directed
model refinement remain subsequent work, not completed by this slice.

## Objective and success contract

Raise the rate of **fresh, target-bound, byte-exact readable C replacements** for
`/K1/k1_win_gog_swkotor.exe` without weakening the proof bar, losing existing
work, or saturating the shared compiler/Wine/model host. The user's desired
aspirational pace is roughly ten useful functions per minute; treat it as a
measured target, not a reason to count candidates, compiled output, assembly
substrate, copied C, or historical success as accepted recovery.

The unit of throughput is a unique target function address with a fresh receipt
binding all of:

1. target binary content hash and function range/bytes;
2. candidate C source hash and evidence lineage;
3. compiler executable/version, target, flags, ABI and object hash;
4. objdiff result against the correct target function, with zero differences;
5. promotion decision and the exact accepted source hash.

Function-slice success is useful intermediate evidence. Full-image completion
still requires a fresh whole-image compiler + objdiff receipt with zero
differences for the required build variant(s). Assembly floors, `_emit`, copied
sources, function identity, equal size, historical receipts and successful
compilation never substitute for that receipt.

## Current evidence update (2026-10-08)

Read-only live diagnosis distinguishes host availability from recovery yield.
The host slept from 08:08:55 to 19:27:56 CDT (11h19m01s). Five attempts include
that interval in Date.now-based receipt durations while SDK query durations
are 108–344 seconds. Do not label suspend-inclusive durations model compute
time or use them to benchmark compiler speed. Preserve elapsed time and report
active query time separately where the SDK supplies it; missing active time
must remain unknown. Do not retroactively subtract inferred downtime from all
historical cohorts.

The six currently live cohorts at 19:40–19:42 CDT contain 109 distinct completed
functions: zero exact, 25 compiled mismatches, 24 compiler failures, 57 session-limit
failures and three connection errors. This is not additive to the October 4
samples. Workers are advancing, not frozen. Next scheduler correction must
classify the actual provider/session-limit result and pause the affected lane,
retaining candidates for resumption rather than consuming them as code failures.
Inspect existing usage-limit handling before adding another classifier. Continue
the model-independent preserved-C compiler lane in parallel once dashboard
admission is installed and verified. Detailed process/receipt/source evidence:
`.superpowers/sdd/2026-10-04-k1-exact-yield-throughput-redesign/current-worker-stalls-2026-10-08.md`.

Later read-only receipt snapshot at 19:49 CDT: 127 unique completed names across
the same six cohort runs, zero exact, 35 compiler successes, 32 compiler failures,
60 compiler skips, 57 session-limit errors and three connection-closed errors.
Shard 02 has naturally completed its 40-function run; the remaining five are
still active. The 35 compiler successes all remain non-exact; objdiff exact count
is zero. This moving snapshot supersedes the 109 count above only for current
status; preserve the earlier receipt as its time-stamped measurement.

The missing 8080 runtime was restored under existing restoration authorization;
no staged compiler code was deployed and no recovery job was submitted. The
compiler-only runtime port is still incomplete and requires review before use.

Follow-up source audit demonstrates the routing defect: the installed Claude
Agent SDK permits `result.subtype === 'success'` with `is_error === true` and
can convert a later transport exception into the generic error text present in
receipts. Mizuchi checks assistant `rate_limit`/`billing_error` only inside the
non-success subtype branch, so this structured error can become an ordinary
failed-function result. Historical receipts do not retain raw SDK frames; the
specific subtype for a past session-limit attempt remains unknown. Repair the
shared collector to classify scoped provider signals while excluding local
turn/budget errors and transient transport failures. Its interactive Continue/
Abort path cannot serve detached `/dev/null` workers: unattended behavior must
pause/stop admission with resumable candidate state and must not guess a reset
time from message text. See `quota-routing-findings.md`. The current Mizuchi
source/dist directory has no tracked Git history at its root; stage a reversible
patch with provenance instead of editing that dependency in place.

## Earlier evidence (volatile snapshot, 2026-10-04)

Additional read-only memory audit: installed Mizuchi source/dist retain full
PipelineRunResult records for all completed batch functions, including attempt
outputs and cumulative Claude conversation report sections. Partial report
writes do not release those objects. Objdiff configurations/parsed objects/diffs
also lack deterministic disposal at their call sites; installed objdiff-wasm3.8.0
has a Symbol.dispose protocol and FinalizationRegistry destructors, so this is
cleanup timing/pressure, not proof of a permanent native leak. Correct both
ownership paths before increasing concurrency: explicit disposal with correct
returned-resource lifetimes, and durable detailed function records with compact
in-memory batch summaries. Measure heap/external/PSS against completed functions
on separately admitted fresh workers; do not alter current external workers or
claim these source findings quantify their RSS contribution.

Authoritative inputs are the K1 shard manifests/receipts and read-only KotorXID
DB, not the dashboard's aggregate counter. The user's recent receipt cohort
was 185 completed functions / 580.3 model-minutes / 147 compiler successes /
144 objdiff failures / 3 exact. A fresh read-only snapshot during this session
showed six active manifests with partial receipts: 64 completed prompts / 227.8
minutes of recorded model time / 11 compiler-failure stages / 49 objdiff-failure
stages / 1 objdiff-success stage (the only exact result in this partial cohort).
The six workers' first-to-last completed-attempt span was about 141 minutes,
giving an approximate 0.007 fresh exact results per wall-minute so far. That
span is an operational snapshot, not a controlled benchmark: shard start times
and prior work differ. This current partial sample is not additive to the user's
receipt cohort and can change while workers continue. Across both views, the
bottleneck is candidate-to-exact yield, not compiler execution speed; recent
completed prompts consume about 3.6 recorded model-minutes each. A single function's
configured `maxRetries: 1` is one Mizuchi attempt, but that attempt can call the
Claude, Compiler and Objdiff pipeline stages; increasing that knob is not the
same as enabling a purposeful, evidence-directed refinement loop.

The lifetime `attempt_ledger.json` count is demonstrably not a valid retry
count. A read-only reconciliation of its 8,568 canonical function keys found
194,862 receipt references. Normalizing only the `.done_YYYYMMDD_HHMMSS`
archive-directory suffix leaves 99,140 unique receipt references: 95,722
references duplicate a run-results receipt already present under its active
directory name, and 8,534 function keys contain such duplicates. A deeper
basename audit found duplicates for 8,566 of 8,568 keys. It counted 3,245
functions as cap-exhausted by raw reference count (`>=25`), but only 41 by
distinct result filename (max 31); 3,204 names are therefore potential
re-entries, **not automatically safe retries**. Example: `AABB::~AABB` has 30
references but only 15 result names. The harvest code tags an attempt with
`<directory-name>:<result-filename>`; when the same timestamped result is
re-harvested after a shard directory becomes `.done_TIMESTAMP`, the storage path
turns one result into a second ledger tag. Historical result files are no
longer all present, so exact byte identity of every historical pair cannot be
re-proven; the accounting defect itself is proven by path-derived identity.
The ledger also does not bind an attempt to candidate source hash, prompt hash,
model/config, target hash, toolchain, objdiff version, failure class or whether
the attempt was actually run. The current cap of 25 can suppress candidates
after roughly half as many recorded result names and still re-serve work
without learning why it failed. Preserve the legacy ledger as historical
provenance, but stop using raw list length for eligibility. Introduce versioned
append-only attempt evidence and policy-aware eligibility; reconcile legacy
references into a shadow view by stable run/session identity, labeling
ambiguous entries, without deleting or rewriting old records. Do not unlock all
3,204 potential re-entries at once: the old receipts span known-bad toolchain
eras, and identical-prompt repetitions have poor measured economics. Admit a
bounded pilot only after the new evidence-directed policy is implemented and
the shared compiler/memory resources are safe.

Six simultaneous shards remain active and are already creating material memory
and swap pressure. More workers are not the default remedy. Existing jobs are
externally owned and must be allowed to drain; the dashboard presently observes
five active Mizuchi cards but still says `No active project`. Its ordinary
corpus selection scans and picks the first SQLite file, while action context
falls back to a missing path. This is a safety/operation blocker, not the
cause of poor model yield; the two must be repaired independently.

Useful pre-existing leverage, not yet fresh acceptance:

- The authoritative DB is `kotorxid/db/kotorxid.sqlite` (about 1.15 GB). Empty
  similarly named DB files exist at the KotorXID and AgentDecompile roots and
  must never be initialized/selected as if they were the corpus.
- These are separate database profiles. Read-only inspection found KotorXID's
  DB has `PRAGMA user_version=3` and migration rows 1–3, while AgentDecompile
  requires schema version 13; KX has later binary/function columns despite
  that older ledger and its source code does not define a compatible migration
  contract. Similar table names do not make it an AgentDecompile store, and
  `store.connect(read_only=True)` correctly rejects it. Do not weaken that
  reader or set KX as the general AgentDecompile corpus DB. Bind KX only as a
  read-only proposal/provenance source with a named-column contract; its
  `content_sha256` is absent on current binary rows, so its candidate rows are
  never proof. The actual selected AgentDecompile target artifact supplies the
  hash checked by the strict verifier.
- K1 GOG has 24,242 functions, 12,032 current identity bindings and 6,125
  functions with source-file attribution. Attribution and identity are routing
  evidence, not byte proof; source paths can be archival and absent locally.
- Existing DB inventory reports 865 K1 GOG `real_c` records. Refresh and bind
  them to current content before reuse; do not infer they cover the current
  binary from count alone.
- `reuse_candidate` contains 923 K1-target real-C same-byte proposals across
  918 target addresses, but 856 proposals/852 addresses originate in K1 GOG
  itself. Only 67 cross-program proposals cover 17 unique K1 target addresses.
  All are marked `identical-bytes-uncompiled`; they are leads, not acceptance.
- A later read-only query during this turn sees 984 K1-target proposal rows
  across 911 addresses: 856 rows/852 addresses have the K1 GOG source program,
  and 128 rows/78 addresses have other source programs. This differs from the
  earlier 923/918 inventory and its narrower 67/17 cross-program subset, so
  these are volatile database snapshots and must not be merged or treated as a
  frozen work queue. Campaign preview must record its exact snapshot identity.
- The same inspection found `content_sha256` is NULL on all 49 current KX
  `binary` rows; the K1 GOG row does carry executable MD5
  `9a44891011437deb6536d992bccdfe4b`. Cross-check this MD5 against the selected
  artifact as candidate-scope corroboration; the selected artifact's SHA-256
  and its strict compiler/objdiff receipt remain authoritative.
- Prior `seed_validation_compile_summary.json` reports 39 identity-linked
  destinations compiled and byte-exact among an older set of 572 materialized
  candidates. It is a historical design signal only. Re-run against current
  hashes/toolchain once exclusive compiler ownership is available.
- Existing first-principles implementation is present in
  `kx/seed_validation.py`, `kx/mizuchi_bridge.py`, and
  `kx/ingest_recovered.py`: source-evidence gating, target compiler/objdiff,
  raw-byte check and gated promotion. Reuse it instead of inventing a second
  acceptance path.

Dashboard observation has improved: the 8080 page currently shows five
`observed-mizuchi-*` jobs and current shard candidate counts. Still, no project
is selected; it says `No active project`, and its corpus default resolves to a
missing `agentdecompile_projects/corpus.db`. External run observation is not
yet a campaign control plane, a correct database binding, or proof ledger.

The dashboard source audit found three disconnected observation paths:

- `dashboard/panels/processes.py` reports generic KX/process rows from cwd/PID,
  without invocation or receipt correlation.
- The current `dashboard/actions/openapi.py` audit found no synthetic external
  Mizuchi jobs in its job-list surface; an earlier description of synthetic
  rows was stale and is retired. External workers are not currently represented
  as AgentDecompile job records, which is the safer ownership boundary. The
  existing `panels/processes.py` display is still a broad cwd/PID view without
  manifest/config/process-start identity or receipt correlation, and must be
  upgraded separately rather than creating fake jobs.
- `corpus.seed-validation` is already registered in `corpus.cli` and exposed
  through generic dashboard action introspection, though it is not an
  Operations-page mutating action. Keep the CLI surface for compatibility, but
  call its reusable audit logic internally from the campaign; do not surface a
  separate stage control beside the campaign control.
- `dashboard/live_recovery.py` reads attempt ledgers but uses write recency as
  process activity; its advertised endpoint appears unregistered.

Task 2 therefore remains observation-only and must share one typed projection:
include PID start identity, invocation/config and corpus scope where present;
only correlate receipts whose identity and output contract match that process;
validate counts and timestamps; normalize measured progress into the existing
job shape; and expose `unavailable`, `stale` or `ambiguous` with a reason rather
than fabricate activity. Keep external entries unowned and uncancellable, and
keep attempt activity separate from proof. No observer may acquire process
control or enqueue work.

## Design: order work by cheapest sound evidence

### Correction: calibration is evidence, not a universal prerequisite

The bootstrap emits unverified source hypotheses. Failure to match one of them
does not disqualify a compiler recipe for every other target function; passing
the cohort does not identify the original whole-program compiler either.
Keep full-cohort calibration as a stronger evidence label, not a gate on bounded
Lane A experiments. A provisional recipe must still pin actual tool bytes and
effective invocation, target identity, explicit machine/ABI assumptions, and
exclusive admitted resources. Record provisional versus cohort-calibrated state
separately from distinct measured support and preserve alternative recipes.

The minimum Lane A dependency chain is original target + existing candidate +
pinned compatible experimental recipe + resource clearance. Full-program
decompilation and complete calibration are supporting work, not prerequisites
for compiling an already available source candidate. Do not simply weaken the
existing workflow's global continue gate: provisional recipes initially serve
only the bounded compile-only Lane A, not automatic bulk recovery/propagation.

Promotion remains fresh candidate compilation, native objdiff zero, independent
raw-byte equality and source/target/toolchain identity continuity. Final linked
whole-image proof remains separate. This changes scheduling, not acceptance.
Rank recipes by distinct measured support with attempted coverage; untested is
not measured failure. Permit bounded candidate-specific fallback without
globally rejecting a recipe because one source hypothesis failed.

This is a K1 yield-repair slice within `STRATEGY.md`, not a replacement global
priority ladder. Identity and calibration may proceed independently; build
scaffolding and its unchanged round-trip remain early; compiling readable C
and compatible-recipient propagation stay ahead of model-only cleanup; local
and linked parity run continuously. The K1 queue must therefore stop sending
every unresolved address directly back to a model session when the shared
corpus contains applicable source/evidence or a cheaper diagnostic repair.
Independent eligible binary/build pairs may proceed concurrently only when
their actual mutable resources (Ghidra project, compiler/Wine state, corpus
writer, output directory, model memory) are isolated and admitted. No stage
name grants a concurrency exception.

Every unique target address flows through one resumable decision queue. A stage
may skip only when it has a current, content-bound receipt for that target and
the required toolchain.

The frozen campaign identity is not a single `db` string. It contains both
database profiles and the exact work scope:

- AgentDecompile store: canonical path, current schema/migration identity, file
  identity, selected project/program and output root.
- KotorXID candidate source: canonical path, file identity, and an explicit
  allowlisted fingerprint of the consumed read-only `binary`, `func`,
  `reuse_candidate` and `recovered_function` schema (types/keys, not merely
  column presence). Record `user_version` and migration rows as observations,
  not proof of compatibility: the DB reports version 3 / ledger rows 1–3 with
  later columns, and KX source does not define them as a version contract. Its
  current K1 row has a populated MD5 but no SHA-256; require caller MD5
  agreement to scope candidates, keep the actual artifact SHA-256 in campaign
  identity, and treat all reuse rows as proposals.
- Target: selected K1 GOG binary id/slug, recorded target SHA-256, and each
  function address/range plus original-byte hash.
- Candidate: source/provenance id, source path/content hash, donor evidence
  hashes, and campaign policy revision; plus compiler/ABI/objdiff fingerprints
  and output root.

Candidate enumeration runs inside a read-only SQLite snapshot. Retain its
database observation and frozen consumed rows for provenance; recheck the
selected target and consumed source/context/tool identities before dispatch
and promotion. Unrelated database writes do not invalidate a frozen proposal
or its independently verified proof. Never join later rows into that snapshot
or treat a prior proposal as current verification. KX admission must use
named-column read-only queries, never invoke
`store.connect()` in writable mode, run migrations, or alter `PRAGMA user_version`.
Hash candidate files into the work-item key; immediately before compilation,
reread under the selected source root, verify the frozen hash, and pass those
exact in-memory bytes to the compiler (never reopen the path during compile).
Missing KX target hashes are not synthesized; the selected AgentDecompile
artifact hash and strict compiler/objdiff result bind and prove each attempt.

The current KX source-path migration needs an explicit input adapter: a fresh
read-only SQL/file-existence audit found no existing recorded paths among the
current K1 real-C proposals. `output/kotor_authoritative/metadata/selection.json`
retains original paths, selected paths, donor metadata and content hashes;
`kx/materialize_binaries.py` defines the move from `src/<slug>/verified_c` to
`output/binaries/<slug>/source/verified_c`. Resolve this named manifest/layout
explicitly and hash preserved files; never recursively search for similarly
named C. Preserve old path and manifest lineage while labeling preserved bytes
as new proposal inputs. Do not claim fresh equality to an absent old file or
inherit historical donor verification as destination acceptance.

### Lane A — validate already present exact-byte candidates (first)

1. Resolve one immutable campaign scope: K1 GOG binary SHA-256, DB file identity,
   target program id, compiler/toolchain fingerprint, selected candidate set,
   output root and current shard ownership.
2. Join `reuse_candidate`, target `func`, identity evidence, recovered-source
   inventory and prior attempt ledgers by binary id + address + content hash.
   Collapse duplicate candidate rows to one address while preserving every
   source/provenance edge. Exclude already-currently-verified targets.
3. Rank candidate sources by proof prerequisites (current donor receipt,
   matching original target bytes, independent identity binding, compatible
   ABI/variant, source hash present), not by row count or equal size alone.
4. Compile each remaining candidate once for the target. Compare using the
   established relocation-aware objdiff and raw target-byte verifier. A donor
   identity or same-byte basis only admits an attempt; it never admits C.
5. Append immutable per-attempt evidence. Promote only source whose current
   attempt has target compiler success, objdiff zero, raw-byte equality and
   matching hashes. Keep failed and ambiguous candidates addressable for later
   work; never delete/quarantine prior accepted material as a side effect.

Start with a fresh deduplicated cross-program snapshot and an explicit bounded
pilot cap, then K1-local proposals only if they lack current proof and have a
distinct candidate source hash. The earlier 17-address count is historical,
not a queue specification. Do not spend a second concurrent VC71/Wine slot
while the current shards own that toolchain.

The planner measures each unique candidate by *cost to fresh proof*, not by
number of match edges. Preserve all provenance edges, but collapse identical
source hashes for the same target/toolchain. Candidates that resolve to the
same C body, compiler ABI and proof basis are one compile work item; new identity
evidence is not another compile unless it changes which source can be selected.
Emit a dry preview with reason-coded exclusions (`already current`, `same
source hash`, `target hash changed`, `no materialized source`, `identity only`,
`ABI unknown`, `attempt leased`) before any compiler launch.

### Lane B — recover from authoritative source and binary evidence

For targets not solved by Lane A, search source archives/build objects and
cross-build source lineage. Use the exact target compiler and build settings;
compile + objdiff every concrete recipient independently. Source filename,
class/method name, identity, disassembly similarity, caller agreement and equal
size can improve selection or prompts, but cannot replace recipient proof.

Where original source is unavailable, retain an explainable candidate package
with ABI, data layout, function bytes, disassembly, compiler behavior, reliable
call/type/source evidence and donor candidates. Route uncertain identity/layout
to additional analysis before model work.

### Lane C — bounded model reconstruction (last, targeted)

The model sees only candidates with adequate target scope and context. Persist
each C revision and compiler/objdiff result. Classify failures:

- compiler/setup failure → repair toolchain, command, symbol/ABI or context;
- objdiff mismatch → send only relevant changed instructions, registers,
  relocation facts and previous candidate diff, preserving already-correct code;
- no improvement across bounded iterations → stop and route for richer analysis,
  do not rerun the same prompt/session blindly;
- infrastructure/TTFT failure → retry only under a separately budgeted
  infrastructure policy, not as a semantic retry.

Do not replace Mizuchi's existing error-feedback implementation. Source audit
found it already passes previous source and compiler/objdiff diagnostics between
attempts; sampled K1 runs simply allow one attempt. The cross-run selector is
the missing policy boundary: live KX counts archive-sensitive ledger tags,
while AgentDecompile's current generator has no corresponding function-attempt
gate. Keep preparation-action retry accounting separate from function/model
attempt evidence. Likewise, KX retains compiled near misses only at one through
five differences: a sampled 25-difference result took 269.389 seconds in the
model stage and 0.737 seconds compiling but is excluded from that reuse path.
Index usable failed C already present in immutable results without a blanket
five-difference discard. These timings are historical stage observations, not
new throughput measurements or pure inference-time measurements.

Do not start with an assumed model upgrade or more inference workers. First
capture failure causes and exact changed-instruction locations by immutable
candidate revision, then test a small paired cohort: unchanged baseline vs a
specific prompt/context/repair intervention on held-out functions in the same
compiler/ABI/evidence strata. Continue a candidate only when a new revision
changes the failure evidence or adds information; stop identical/no-progress
retries. Separately classify compiler failure, invalid extraction, ABI/symbol
failure, relocation mismatch, instruction mismatch and infrastructure timeout.
Compiler/setup repair must not spend a semantic retry; transient infra retry
must be separately budgeted. Allocate a small exploration budget to new
evidence/transform strategies and rank exploitation by measured **expected
fresh exact proofs per total wall-clock/resource-second**. Use uncertainty-aware
estimates, stratified by target compiler/ABI, function shape, evidence class,
candidate provenance and intervention version. Keep a minimum exploration
share, label sample sizes and intervals, and never tune from three successes.

Every model session and candidate revision needs an append-only attempt record
with at least: stable campaign/target key; target binary and function-byte
hashes; selected evidence IDs and hashes; prompt/policy revision; model and
generation settings; source revision hash; compiler/toolchain/ABI fingerprint;
objdiff binary/config identity; phase timestamps and durations; token/resource
cost when available; structured compiler error class or changed-instruction
signature; and terminal proof disposition. Reuse may reference an old record,
but may not overwrite it. Retrying the same candidate is eligible only when a
material input changes or the failure-directed editor creates a new source hash.
The global canonical-name count remains a legacy display only; it must not be a
proof-quality retry gate.

Do not duplicate the existing KX near-miss feature blindly:
`harvest_shards.py` already preserves best compiled C and objdiff detail for
exact-address failures of at most five instruction differences, and
`genproject.py` seeds that source into a later prompt. This useful narrow path
excludes larger mismatches and compiler failures; it also stores a best
candidate rather than full revision/prompt/toolchain lineage. Extend this
source of truth losslessly and measure candidate improvement instead of
creating a competing best-candidate store. The user's current receipt cohort
averaged 12.6 instruction differences among objdiff failures, so the <=5 gate
does not cover most of that mismatch surface.

The targeted correction loop is bounded by a policy-controlled attempt/time
budget and should request an edit only against the mismatching evidence while
preserving matching assembly regions. Persist each revision before compiling.
The loop stops when (a) byte-exact proof passes, (b) compilation fails with an
unresolved source/toolchain issue, (c) the objdiff signature makes no progress,
(d) evidence is insufficient, or (e) its resource budget is spent. Stop reasons
must route to a different action (toolchain repair, new evidence, manual
analysis, or lower-priority queue), not silently re-enter the same prompt. The
initial correction budget and any different model/context are selected by a
paired, held-out cohort; do not ship a guessed retry count as if it were proven.

## Throughput scorecard and experiment discipline

Maintain three non-interchangeable rates, each bound to a target image and
toolchain: (1) fresh accepted C replacements per wall-minute; (2) accepted C
replacements per paid/model-minute; and (3) accepted C replacements per
compiler/Wine-minute. Show median and tail latency, all failure classes, total
resource pressure, and unique targets—not just function sessions or model tool
calls. Report the ten-per-minute aspiration separately from measured rates.

After deterministic reuse candidates are exhausted, compare the current
single-session baseline against one intervention at a time (for example a
targeted diff revision, recovered source/type context, or another model), using
paired/randomized or stratified disjoint cohorts with the same binary, compiler,
ABI, and evidence quality. Track confidence intervals and compute cost. Promote
an intervention only when it improves *fresh exact proofs per total resource*
without materially increasing swap pressure or poisoning max-C quality. A
configuration change is not an improvement until its new receipts demonstrate
the improvement. Never run a capacity bakeoff while the current external shard
fleet owns the compiler or memory headroom is under pressure.

### Resource admission and concurrency

One coordinator owns work leases keyed by target SHA + function range + source
hash + toolchain fingerprint. Existing external workers are observed, not
adopted or duplicated. A new campaign may start only after current shared
compiler/Wine ownership has drained or been explicitly coordinated through the
dashboard.

Use measured CPU, available RAM, swap-in/out, compiler queue time and model
resident memory to admit work. When swap-in/out is sustained, reduce concurrency
and prefer local compile-only tasks only if they do not share the constrained
toolchain. Concurrency tuning is a bounded measurement after the current batch,
not an assumption that more workers mean more throughput.

## Dashboard and operation contract

8080 is the sole operator surface. It must bind the selected K1 program to the
authoritative corpus DB and KotorXID output root explicitly, reject empty
placeholder databases, and show DB identity/hash and project selection before
any mutation. External process observation must bind worker PID to manifest,
receipt paths and config hash; show the current function, model/tool/compiler/
objdiff phase, last receipt timestamp, attempts, instruction difference count,
yield and host resource pressure. `running` alone is not progress.

Campaign controls are campaign-level start/pause/resume/cancel. Campaign start
and resume automatically invoke frozen KX-candidate reconciliation inside the
same campaign lease; `workbench.prepare` can host the internal provider hook,
but it must not become a separate required click or an alternate route around
campaign admission. Individual pipeline stages are automatic. Resume first reconciles stable target keys and
valid receipts, then enqueues only missing/stale targets. It must never overwrite
or restart a valid receipt because a UI session or dashboard process changed.
Import/rebuild operations must be idempotent, append-only or staged+atomic, and
preview their exact target mutations; a collector that can quarantine output is
not a read-only report.

The dashboard should display three separate counts: (1) planned candidates,
(2) attempts currently in progress / attempts completed, (3) fresh accepted
target-byte exact readable-C replacements. Show proof-stage details and actual
changed assembly alongside activity; do not turn generation, compilation,
cross-match or verification into unrelated manually clicked buttons.

## Ordered implementation and acceptance plan

| Order | Deliverable | Acceptance evidence |
|---|---|---|
| 0 | Preserve/reconcile current live campaign ownership; snapshot every shard manifest, config hash, receipts and active PIDs without restarting | No overlapping campaign/compiler owner; immutable observation snapshot; live owner state retained |
| 1 | Keep AgentDecompile DB selection schema-valid; add separate read-only KX source binding joined to the selected K1 project, target SHA-256 and output root | Both DB identities and the supported KX schema/consumed-column contract are pinned; KX stays read-only; missing/ambiguous/mismatched bindings fail closed; no auto-created DB or migration |
| 1c | Persist compound campaign identity through preparation birth/resume while preserving existing run IDs and authority | Selected AgentDecompile DB, K1 binary/program and eventual target-image hash, explicit KX source identity, and canonical output root are immutable campaign facts; resume revalidates without rekeying or overwriting; legacy-unbound runs are retained and never silently rebound; multi-binary projects carry per-binary identities |
| 2 | Add read-only campaign/shard/function telemetry and host resource admission | Browser view agrees with current receipt files/processes; each phase/time/count has source path and timestamp; no false progress. **Status: staged read-only observer, independent correctness/data-integrity/security review PASS; producer events and live integration still pending.** |
| 2a | Emit compact, versioned KX/Mizuchi stage events bound to launched process, manifest/config, target/function bytes and output contract | Durable phase start/complete events join to exact process identity; no prompts/source/chat/secrets; incomplete, duplicate or mismatched streams remain uncertain; events never replace compiler/objdiff proof |
| 3 | Add a frozen read-only KX candidate provider to the campaign's internal preparation/matching wave; start/resume calls it automatically | Stable target keys; source/provenance paths; current verified targets and duplicate source hashes excluded; reason-coded preview; no stage button, extra click or preview writes |
| 4 | Execute Lane A automatically inside the same campaign only when shared compiler/resource admission is clear | Fresh per-candidate compiler + zero-diff objdiff + raw-byte receipts; accepted count reflects only passing targets; measured target functions/min |
| 4a | Route provider/session quota as a resumable lane pause rather than a candidate failure | Structured SDK quota signals stop further model dispatch, preserve the current target and untouched queue, distinguish provider quota from local turn/budget and transient connection failures; no reset-time guessing |
| 5 | Repair source/result format adapters and append-only acceptance ledger | Multiple actual receipt schemas parsed without loss; duplicate archive-path references do not inflate unique attempts; legacy ambiguity is preserved; current-policy attempts are keyed by target, input/prompt/source revision and toolchain; historical/current/partial separated; rerun is idempotent and preserves receipts |
| 5a | Bind KotorXID producer receipts to exact target bytes | Generator computes the selected executable SHA-256 and exact per-function raw-byte SHA-256 from the same immutable bytes used to create the target object; manifest/settings bind both hashes and target-object identity; Mizuchi prompt input, `PipelineRunResult`, and partial/final receipts retain the per-function hash; harvester validates it against the current raw target before any prompt seed or promotion; missing/legacy hashes remain unbound and are never inferred retroactively |
| 6 | Revise candidate economics and model feedback loop from measured strata | Paired/held-out cohort, bounded spend, exact proofs/resource-second rises versus baseline; no threshold based on only the three current wins |
| 7 | Maintain two separate deliverables: byte-accurate C+assembly-floor and max-C readable C | Independent inventory, source/provenance, fresh compile receipts and quality metrics; no cross-contamination |
| 8 | Fresh full-image acceptance for each required build variant | Fresh compiler + objdiff receipt covers the entire image, zero differences, bound to target/toolchain/source manifest |

### Implementation task boundaries

Each task is independently reviewable but downstream tasks consume the contract
from earlier tasks. Do not dispatch implementation in parallel when it shares
these interfaces.

| Task | Exclusive ownership | Produces / consumed by |
|---|---|---|
| 1. Campaign binding | AgentDecompile DB resolver plus distinct read-only KX adapter and dashboard project context | Stable compound identity including both DB fingerprints, KX schema contract, target/function/source hashes and output root; AgentDecompile writers retain current-schema-only contract; consumed by observer, candidate provider and mutations |
| 1c. Campaign identity continuity | `preparation.submit` durable row and existing preparation/JobStore resume authority | Append-only binding snapshot that preserves current run/job IDs, distinguishes per-binary target-image receipts, and refuses changed/unbound identity without resetting or silently adopting stale state. **Status: staged reversible patch, independent correctness/data-integrity reviews PASS; runtime integration pending.** |
| 2. External worker observation | Existing dashboard process panel/observer modules and their read-only API projection | Shard/process/receipt phase snapshot bound to manifests; consumed by cockpit and campaign admission |
| 2a. Producer stage-event contract | KX shard launcher + Mizuchi model/compiler/objdiff lifecycle and partial/final receipt owner | Compact event stream bound to session/process/config/manifest/target/function; no prompt/source/chat payload; consumed by observer/visualization, never by proof promotion |
| 3. Candidate reconciliation | Read-only KX provider integrated into existing `workbench.prepare` matching wave | Deduplicated stable target keys + provenance + prior receipt status; consumed by compile queue; no standalone user-facing action |
| 4. Compile-only fast lane | Campaign coordinator, admission/lease contract, existing KX seed verifier adapter | Per-target attempt receipts and accepted proof events; consumes Tasks 1–3 and current source candidates |
| 4a. Provider quota pause | Mizuchi SDK result adapter, existing detached launcher/recovery loop and harvester boundary | Provider quota is not a failed source candidate; preserve retryable target/queue and stop the unattended model lane without interactive stdin; controller must not delete/regenerate or harvest the paused shard |
| 5. Receipt and source consolidation | Mizuchi receipt adapter + append-only proof ledger/materialization boundary | Schema-versioned history, idempotent acceptance; consumes Task 4 receipts and feeds recovery views |
| 5a. Producer target identity | KX prompt generator + Mizuchi prompt loader/result/report path | Exact executable/function-byte identity is captured before inference and carried unchanged into every partial/final result; legacy receipts remain explicitly unbound |
| 6. Evidence-directed model lane | Mizuchi prompt/feedback/config integration, only after lossless KX source custody is established | Bounded candidate revisions, classified failure evidence and calibration cohort; consumes Tasks 1–5 |
| 7. Operator visualization | 8080 dashboard views and campaign-level controls | Real-time, source-linked explanation of actual transformations and proof states; consumes Tasks 1–6 |
| 8. Full-image acceptance | Variant inventory + whole-image compiler/objdiff receipt + packaging gate | Fresh zero-difference whole-image proof for each requested variant; consumes accepted source/floor artifacts |

KX implementation is an external dependency currently present as untracked
working material. Tasks 4–6 may initially add only an AgentDecompile adapter
around its existing read-only/dry-run surfaces. Direct KX source edits are a
separately reviewed task and require recovering the tree's ownership/history
plus a restorable source snapshot first.

### Global constraints

- Preserve all existing work, receipts, logs, ledgers, processes and unrelated
  dirty changes. No `systemctl`; no shell substitute for dashboard mutations.
- Use port 8080 exclusively for dashboard operations, driven through
  Playwright CLI. Do not use curl. Do not use `agentdecompile-cli` as a recovery
  bypass.
- No filesystem tests or test files in this session. Use bounded non-test,
  read-only inspection and production compiler/objdiff receipts only after
  campaign admission is safe.
- Do not claim byte accuracy from copied code, source metadata, identity,
  successful compilation, historical reports, or per-function match alone.
- Keep K1 GOG first. Siblings and platform variants contribute donor evidence,
  but each target build remains independently compiled/verified.

## Open implementation decision

KotorXID source files currently appear as untracked material in an initialized
repository with no commits. Do not bulk-rewrite or commit that tree until its
intended ownership/history is recovered. Prefer wiring AgentDecompile's adapter
to the existing, inspectable KX verifier first; if KX implementation changes
prove necessary, preserve the complete pre-change tree and create a recoverable,
content-addressed patch/backup before editing.

## New implementation findings (2026-10-04)

The independent campaign audit refined the Lane A boundary. `workbench.prepare`
first does database-level pair matching; it does not produce machine code
proof. The per-program recovery path later calls
`materialize_original_target()` and records a content-addressed target-image
receipt. That receipt can bind the selected artifact SHA, but it is a raw
executable image, not the per-function target `.o` required by
`dashboard/actions/matching.py::execute`. The latter also requires an
artifact-SHA-bound compiler preset, target object revision, and named symbol.
There is no candidate-wave preset binding today. Follow-up inspection found
the existing `genproject.build_target` and relocation-aware `mkobj.write_object`
already generate reference COFF objects from explicit binary slices. Reuse this
implementation with recorded input bytes, bounds, architecture and relocation
policy; a generated reference object is not an original compiler object.
Do not invoke `matching.execute` with guessed preset inputs.

There are two existing verifier capabilities, with different receipts and
authority: `matching.execute` produces strict two-sided objdiff evidence when
an approved target-object preset exists; `corpus.seed_validation.compile_seed`
can compile a materialized function candidate and compare extracted function
bytes directly with the selected target region (and optionally run objdiff when
its source evidence provides a target object). Its standalone CLI currently
does not pass `compiler_for` or `evidence_root` to `audit()`, so `--compile`
can end in `not_run`; do not use that CLI option as proof that compilation
occurred. Future campaign integration must consume a named verifier result,
fail visibly when its prerequisites are missing, and keep raw-byte and objdiff
receipts distinct. A function-level exact result remains below whole-image
acceptance. The subsequent source repair now rejects standalone compile flags
explicitly and requires target-image reader/compiler/object-parser inputs before
the audit reads candidates or writes output. Compilation preflights the target
object and checker, rejects nonzero objdiff exits (including decoration-only
differences), and cache reuse requires successful objdiff. These changes are
isolated source, not deployed production evidence.

Task 1b's read-only KX adapter is now present in the isolated worktree and has
independent static review. It requires explicit DB/root/target identity,
checks the reviewed consumed-schema fingerprint and the selected target MD5
against KX metadata solely to scope proposals, hashes source files under the
explicit root, and returns frozen bytes. It now excludes rows unless both
`reuse_candidate.real_c` and `recovered_function.real_c` are true, with an
exclusion reason before hashing their source. The adapter is proposal-only; it
is not integrated with the project binding, campaign, target-byte extraction,
job admission, or proof ledger. Its `work_item_key` is only a proposal key,
not the final target-function attempt lease: that lease still needs selected
target function bytes/range hash, exact candidate revision, and toolchain
fingerprint from the campaign-owned snapshot.

A fresh read-only host snapshot at 2026-10-04 16:14 UTC shows five active KX
Mizuchi CLI processes (PIDs 535014, 632309, 645652, 648653, 670939), five
child Claude sessions, and no active compiler/Wine compile command matching
the targeted process scan. Memory was 31 GiB total / 25 GiB used / 1.9 GiB
free / 5.7 GiB available; swap was 25/42 GiB used. Memory PSI `avg10` was
20.60% (`full` 17.26%). This confirms that adding model/compiler workers is
unsafe now. The existing KX work remains user-owned and was neither adopted
nor stopped. Wait for it to drain before any controlled K1 compiler pilot.

### Revised next implementation boundary

1. Finish compound campaign binding without conflating the two DB profiles.
   Derive selected target SHA only from the immutable target-image receipt;
   derive the target function range and raw-byte hash from that same image and
   Ghidra function facts. Require the selected program and output root to be
   explicit in the existing campaign, not guessed from the first DB/file.
2. Add a read-only reconciliation provider inside `workbench.prepare` after
   target materialization. It joins only the selected binary's KX rows to
   explicit, hashed readable-C donor files and current target facts; removes
   stale target hashes, already-current proofs, duplicate source hashes,
   non-real-C and ambiguous target symbols; emits a stable reason-coded
   campaign event. It must not make a separate user-facing stage button.
3. Bind reference targets through the existing slice/object generator, selected
   target-image receipt, function bounds and compiler profile. Compile only
   when target and objdiff prerequisites exist; require both raw equality and
   successful objdiff for admission. Raw-only or symbol-normalized observations
   remain diagnostics and cannot qualify accepted C or whole-image completion.
4. Route every admitted candidate through the durable campaign job/admission
   path, not by calling compiler helpers as unowned subprocesses. Persist
   immutable attempt receipts and a resumable lease keyed by compound campaign,
   target-function-byte hash, candidate source hash, and compiler identity.
   Pause prevents new child dispatch but lets an admitted child finish and
   checkpoint; resume revalidates before reusing any result.
5. Only after existing workers drain and memory/swap admission is clear, run a
   bounded Lane A cross-program pilot first. Compare fresh exact proofs per
   wall/model/compiler minute with a baseline cohort; if it does not raise
   proof yield, inspect the failure signatures before changing concurrency or
   retry policy.

## First implementation task brief

### Task 1 — make campaign binding explicit and fail closed

**Why this precedes throughput changes:** the 8080 cockpit currently says
`No active project`, while its default action context resolves to a missing
`agentdecompile_projects/corpus.db`. There are empty placeholder DBs and a
separate KotorXID DB on a different schema track. The first AgentDecompile
resolver correctly rejects that KX DB: KX reports schema v3/migration rows 1–3,
while AgentDecompile requires v13. This is not a reason to loosen v13 checks.
The production design must bind an AgentDecompile store and a distinct
read-only KX candidate source through separate adapters, together with the K1
target hash and output root. A planner without that compound identity risks
measuring or mutating the wrong corpus.

**Ownership:** only `src/agentdecompile_recovery/corpus/dashboard/common.py`,
`cockpit.py`, `router.py`'s corpus-db selection handler, and corpus identity
fields in `actions/context.py`. Do not edit static or React UI, the route
catalog, job runner, KX, or recovery artifacts.

**Implement:** preserve the explicit AgentDecompile-store resolver and add a
separate KX candidate-source profile that validates an explicit allowlist and
fingerprint of the tables/columns actually consumed; record but do not trust
the KX `user_version`/migration ledger because it is not a declared
compatibility contract. Do not infer compatibility from table names. Never
write KX migration metadata or `PRAGMA user_version`. Bind both stores to one selected K1 program
and target SHA-256, plus output root. Reject missing,
zero-byte, schema-invalid, ambiguous, or identity-mismatched inputs. Do not
search-and-auto-select across database profiles. Keep ordinary browsing
compatible. Mutation/action context receives the validated AgentDecompile
identity; candidate reads receive the KX adapter. Errors identify the missing
or inconsistent binding. Resolution never creates or migrates a database.

**Constraints:** no tests or test files in this session; no DB writes, corpus
imports, recovery work, service restarts, dashboard navigation that changes
project state, direct recovery CLI, 5174, curl, or `systemctl`. Use read-only
source inspection. Do not claim live UI behavior has changed: the worktree is
isolated from both the 8080 process and the dirty active checkout.

**Acceptance:** database type is explicit; the pinned compound identity binds
both canonical DB paths/file identities, the supported KX schema fingerprint,
K1 target hash/function range and output root; candidate enumeration uses a
read-only snapshot and identity recheck; campaign start/resume invokes that
reconciliation internally. KX reads are strictly read-only (no KX migration or
`user_version` write); all
AgentDecompile writers continue to require current schema; invalid/ambiguous/
mismatched bindings fail closed before persistence; selection does not create
or migrate any DB. Report exact files changed and validation deliberately not
performed. This task fixes a blocker to safely operating the throughput plan;
it does not itself claim higher exact-match yield.

### Calibration correctness findings and implementation status

Source-only repairs now require an exact executable fingerprint for workflow
compiler-profile binding; architecture similarity no longer substitutes for it.
Profile admission requires distinct selected-case coverage by a configuration,
not receipt counts or exclusivity among successful configurations. Multiple
zero-diff configurations remain recorded. Duplicate configuration names are
rejected before probing, and compiler roots must be explicit absolute paths.
These repairs have received independent static review, not execution proof.

The next admission repair must route automatic calibration through the existing
`recover.compiler-profile-corpus` catalog action with concrete shared resource
claims. The current inline helper invokes real compiler probes outside child-job
admission. Moving that call alone is insufficient: compiler/Wine ownership and
clearance must cover existing external workers too. No new stage button or
parallel recovery runner is required. Port 8080 was restored on October 4 using
the existing NVMe project and database; source changes remain isolated, and no
throughput improvement is established.

The existing compiler-profile-corpus command now supports measured profile
admission with explicit target identity, compiler profiles and Wine prefix.
Generated compiler wrappers delegate to the same compilation implementation as
the probes, rather than a shell helper with different flags/environment policy.
This is source-only integration preparation, not dashboard dispatch or external
worker coordination. Path preflight preserves probe inputs and constrains scratch
writes; independent static review and correction rounds are recorded in the SDD
ledger. No compiler run, benchmark or fresh acceptance receipt has been produced.

Catalog resource binding is now implemented and statically reviewed: parameters
freeze against the captured execution root before job persistence/dispatch,
resource claims identify output/compiler/Wine paths, and historical records cannot
rediscover current defaults. The isolated source also has independently reviewed calibration
lifecycle clearance, including child/session identity, pinned Wine-prefix inode,
no-dispatch evidence and conservative historical quarantine. This supersedes
reservation-only support, not the external-prefix ownership prerequisite.
The live NVMe runtime has not received these changes.

Seed verification now accepts an explicit compiler binding for argument protocol,
environment and fallback context; the protocol is part of the reuse fingerprint.
This removes reliance on a measured wrapper's filename and prevents its two-arg
interface from receiving a legacy symbol argument when explicitly bound. Legacy
callers remain adapted in one place. Static review passed; campaign consumption
and actual compiler/objdiff execution remain outstanding.

### Remaining pilot dependencies (October 4 continuation)

The existing runtime is schema 4 and is not a Git checkout; the isolated source
expects schema 13. Activation must reconcile the required source changes rather
than wholesale swapping trees or pointing the new store at the old DB. The
restored catalog confirms the established NVMe DB and K1 GOG inventory; it does
not yet expose the new measured-admission parameters.

An ignored --max-workers control is repaired and independently source-reviewed:
it now reaches every launcher context construction. Existing live context pools
are unchanged, so the runtime memory effect is not yet measured.

Calibration lifecycle work must combine exact-child/session clearance with the
existing read-only Wine-prefix probe and pinned prefix inode. A clear probe is
not exclusion against an external writer. The pilot must use an independently
provisioned prefix, not the active KX prefix, and remain within available memory.

No matched-examples.jsonl corpus was found beneath the runtime corpus_work.
Trace and connect its real producer before attempting calibration. The producer
must bind source and target-object artifacts to the selected executable; merely
copying a caller-supplied fingerprint onto a profile is not that binding. A
global sample corpus must not silently become target-specific evidence. This is
a pilot dependency, not permission to fabricate matched examples or to require
an already-admitted compiler before collecting calibration candidates.

Continuation: target-bound bootstrap source and its independent review are now
complete. It reuses the existing source hypothesis catalog, corroborates
contiguous original PE ranges, rejects base relocations and uncertain relative
references, builds only the selected bounded target objects, and preserves
analysis-image provenance separately. Hypotheses remain unmatched until real
compiler/objdiff evidence exists. The real Ghidra inventory export and automatic
dashboard child dispatch are still integration work; preparation's factsPath
is a summary receipt and cannot stand in for that inventory.
