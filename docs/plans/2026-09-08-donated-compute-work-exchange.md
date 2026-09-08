# Donated compute: a capability-labeled work exchange

Status: design. Date: 2026-09-08.

Goal: anyone who opens the Vite frontend can contribute their own hardware and
make the corpus go faster.

## 1. The finding that decides the design

The pipeline's cost is not one thing, and the two halves have opposite
economics:

| Half | Cost per unit | Portable? | Needs |
|---|---|---|---|
| **Candidate generation** — write a C spelling that might match | seconds to minutes (LLM), or microseconds (idiom permutation) | **yes, fully** | nothing, or an LLM |
| **Verification** — compile it and compare bytes | milliseconds | **no** | era-exact `cl.exe` + VC7 `link.exe` under Wine |

Donated compute pays off exactly when generation cost per candidate exceeds
verification cost per candidate. That gives a clean rule:

- **Mechanism 3 (subagent rewrite) is the lane worth opening to anyone.** One
  LLM call costs the contributor seconds and their own money; it costs the
  coordinator a millisecond to refute. The ratio is ~1000:1 in the
  coordinator's favour. A browser tab with the contributor's own API key is a
  genuinely useful node.
- **Mechanisms 1 and 2 and `decomp-permuter` are compile-bound.** A contributor
  without `cl.exe` cannot help with them at all, and a contributor *with*
  `cl.exe` should run the whole generate to compile to compare loop locally and
  report only winners. Shipping raw candidates to the coordinator for these
  would make the coordinator the bottleneck.

Everything below follows from that split.

## 2. Why this is safe to open to strangers

The repo already states the trust boundary, in `rewrite_queue.py`:

```
CLAIM_BOUNDARY = (
    "rewrite-queue entries are advisory only; the objdiff compile-verify gate "
    "is the sole proof mechanism for any resulting candidate"
)
```

A contribution is a **proposal**. `objdiff-check.mjs` exits 0 only on
`MATCH 100%`. A liar gains nothing: a forged "I matched it" is refuted by a
check orders of magnitude cheaper than the search that allegedly produced it.

This is the Nix model (trust the hash, not the builder), not the BOINC model
(quorum over N redundant runs). **Do not build quorum, credit, or reputation.**
Verification is asymmetric and already implemented; that removes the entire
subsystem from scope.

Corollary, enforced at the API boundary rather than by convention: volunteer
output never lands in `verified/`, never writes SQLite, never touches the
identity tables. AGENTS.md already says *never promote byte-emitters into
`verified/`* — the exchange makes that structural.

## 3. The existing seed

`state/rewrite-queue.json` (schema `agentdecompile.rewrite-queue.v1`) is
already most of a distributed work queue:

- lifecycle `pending -> claimed -> completed | failed`
- content-addressed ids: `sha256(candidate_source)[:16]`
- lease semantics: `claimedBy` + `claimedAt`, stale reclaim at 1800s
- a cross-process `flock` spanning read, verify, write
- an entry payload that is **already a pure value**: `functionName`, `entry`,
  `candidateSource`, `mismatchClass`, `mismatchHistogram`, `alignedDiff`,
  `compilerProfile`. No absolute path. No db handle. Shippable as-is.

The design is therefore not "build a distributed system". It is **lift this one
file queue onto HTTP, add capability labels, and let remote fulfillers claim
from it**. Same lifecycle, same trust boundary, same schema plus a version bump.

## 4. Lanes

A contributor advertises capabilities; the scheduler only offers work the
contributor can actually run. This is the GitHub Actions / GitLab Runner label
model, and it is what makes "anyone" workable without pretending everyone has a
2003 Microsoft compiler.

| Lane | Capability required | Runs in | Unit in, out | Who verifies |
|---|---|---|---|---|
| `rewrite` | an LLM (contributor's own key or Claude Code) | **browser tab** or CLI | queue entry, alternate C | coordinator compiles + objdiffs |
| `permute` | none — pure JS/WASM | **browser tab** | entry + seed range, candidate C set | coordinator, batched |
| `compile` | `msvc-vc7`, `wine` | native runner | C + profile, COFF `.o` + verdict | coordinator re-runs objdiff |
| `search` | `msvc-vc7`, `wine` | native runner | entry + seed range, **winners only** | coordinator re-runs objdiff |
| `objdiff` | node, or `objdiff-wasm` | browser or runner | two `.o`, verdict | recomputable; spot-checked |
| `match` | python only | native runner | `matcher-input-v1` slice, match rows | coordinator commits |
| `ghidra` | `ghidra-12` + project replica | native runner | program, facts / sigs / decomp KB | program fingerprint |

`search` is the high-throughput lane: a contributor who owns the toolchain runs
the closed loop locally and reports only byte-exact wins. `rewrite` is the
zero-install lane that matches the "open the page and help" intent.

## 5. Avoiding the stateful problems

Six rules. Each is a workaround for a specific thing the code does today.

**R1 — Values, not paths.** A work unit carries its inputs inline or by content
hash. Nothing may reference `live_root()` or `live_db()`. This is the real
porting work: today `run_id`, `_comparison_path`, `read_comparison_receipt`,
and `identity_lock_key` all embed `str(live_db())`, so every receipt and memo
key is machine-local. `compile_cache.cache_key` and `match_cache.cache_key` are
the two existing keys that are already portable — copy their shape.

**R2 — Propose, don't commit.** Remote nodes return artifacts and verdicts. The
coordinator alone writes SQLite, identity tables, and `verified/`. The eight
`IDENTITY_WRITERS` never leave home.

**R3 — Idempotent by content address.** A resubmission of the same
`(target_slice_sha, source_sha, compiler_profile, lane, flags)` is a cache
write, not a conflict. Duplicate delivery is expected under lease reissue and
must be harmless.

**R4 — Leases, not assignments.** Keep `pending -> claimed -> completed`, keep
stale reclaim. A vanished volunteer costs one lease timeout. Never assume a
remote worker is alive — note that `_owner_alive()` currently returns `True`
unconditionally for any non-local host, which is the wrong default the moment
work is remote.

**R5 — Shard the search, don't share it.** Permuter trials are independent
random seeds. Hand out disjoint seed ranges. No coordination, no shared state,
unbounded fan-out. **This is the mechanism that absorbs arbitrary donated
compute** — it is the only part of the pipeline with no scaling ceiling.

**R6 — Ghidra stays home.** `CONTEXT_LOCK` guards a singleton: one JVM, one MCP
session, one open program (`mcp_bridge.py:20-24`). All 73 `mcp.*` actions are
serialized behind it, which is why stages 2, 3, 4, 5, 7 and 9 cannot fan out
today. Distributing them requires per-worker project replicas, and shipping
analyzed program databases back may cost more than it saves. Measure before
promising it.

## 6. Free wins to take first

Two of these need no distribution at all and should land before any protocol:

1. **`workflow.py` pins `'workers': 1` for `corpus.ghidra-bulk`**, whose inner
   per-function compile loop is already a `ThreadPoolExecutor(max_workers=...)`.
   Raising it parallelizes the single best-shaped unit in the tree on hardware
   already owned.
2. **`corpus.match-pair` runs pairs strictly sequentially**, and the pair set is
   quadratic in corpus size. Its inputs are already frozen and digested as
   `matcher-input-v1`; only the final `INSERT` is shared. Parallelizing locally
   is a smaller change than distributing it, and tells you whether distribution
   is even worth it.

Measure wall-clock per stage before building the exchange. If Ghidra analysis
dominates, no volunteer architecture helps, because that is the one stage that
is both expensive and non-distributable.

## 6b. The fan-in problem bites before any compute is donated

"Anyone opens the page" is a load problem *first* and a compute problem second.
Measured against the current server:

- One uvicorn worker, one event loop, **no `workers=`** in the uvicorn kwargs.
- Blocking routes offload through `asyncio.to_thread`, which uses the default
  executor. Nothing calls `set_default_executor`, so the ceiling is
  `min(32, cpu_count + 4)` threads for the entire app.
- The SSE endpoint runs `await asyncio.to_thread(snapshot, ...)` **every 2
  seconds per open connection**, and `snapshot`/`_replay` both serialize on one
  module-level `_LOCK` around a SQLite connection opened and closed each tick.
  **There is no connection cap.**
- Twelve separate frontend `setInterval` loops poll per tab, the fastest at
  750 ms (`CodeBrowser.tsx:57-64`), several with no hidden-tab gating.

So thirty spectators can saturate the executor and starve the four job slots
before donating a single cycle. **Fix the observer path first**: one shared
snapshot broadcast to all SSE subscribers instead of per-connection polling, a
connection cap, and hidden-tab gating on every loop. Otherwise the feature makes
the pipeline slower, which is the exact opposite of the goal.

Two related facts to handle when the server stops being loopback-only:

- `local_control_allowed` (`server_control.py:39-47`) compares
  `request.client.host` against a loopback set and **does not read
  `X-Forwarded-For`**. Behind any reverse proxy every caller looks local and
  can reach `POST /dashboard/api/server/shutdown` and `/restart`. This is an
  availability bug the moment strangers can connect, independent of any
  security posture.
- `rewrite_queue.py` has three defects that only matter once it is shared:
  `import fcntl` is unconditional (unimportable on Windows); a corrupt read
  returns an empty queue which the next write then persists, **silently
  dropping every live entry**; and stale-claim takeover has no fencing token,
  so duplicate *execution* is possible even though duplicate *commit* is not.

## 7. Protocol sketch

FastAPI + uvicorn already back the dashboard (`router.py`), so long-poll, SSE
and WebSocket are all available; no server rewrite is needed. Submissions should
copy the batch-receipt pattern already in `react_api.py`: a client-chosen
idempotency key plus a content `fingerprint`, returning 409 when the same key is
reused for different work.

```
POST /dashboard/api/exchange/enroll    {capabilities, agent} -> {workerId}
POST /dashboard/api/exchange/claim     {workerId, lanes} -> 204 | {unit, leaseToken, leaseExpiresAt}
POST /dashboard/api/exchange/heartbeat {leaseToken} -> {leaseExpiresAt}
POST /dashboard/api/exchange/submit    {leaseToken, artifact, verdict} -> {accepted, verdict}
GET  /dashboard/api/exchange/roster    -> contributors, throughput, wins
```

Outbound-only, so contributors behind NAT work. No inbound ports. Enrollment is
open per the project's stated posture; rate-limit by worker id so a broken
client cannot drain the queue.

The browser lane is the same protocol from `fetch()` in a Web Worker.
Cross-origin isolation, if ever needed for wasm threads, costs two response
headers here — every asset is same-origin and Monaco is bundled by Vite, not
CDN-loaded.

## 8. What will not work

State these plainly rather than discovering them in month two.

- **Ghidra in a browser: no.** JVM plus a native C++ decompiler subprocess.
  Browsers have no subprocess, and wasm32 caps at 4 GiB.
- **MSVC in a browser: no, permanently.** `cl.exe` is closed-source; there is no
  wasm build and there cannot be one. Contributors must bring their own
  toolchain — which is why capability labels are load-bearing, and why the
  realistic `search`-lane contributor is someone already doing decomp work.
- **BSim in a browser: no.** It needs a PostgreSQL cluster.
- **Unsolicited background compute in a page reads as malware** post-Coinhive.
  Contribution must be opt-in, visibly attributed, and one click to stop.

## 9. Open questions

- **O1 (gating).** Wall-clock per stage on a representative binary. Decides
  whether any of this is worth building.
- **O2.** Is VC7 `cl.exe` byte-deterministic for `/c` across machines? If yes,
  hash equality can replace an objdiff run on the coordinator.
- **O3.** Does Ghidra's standalone C++ decompiler build under Emscripten? High
  payoff if so; would make the decompile stage portable. Believed unattempted.
- **O4.** `decomp-permuter` reportedly shipped "permuter@home" for exactly this
  problem. Its trust model (open vs vouched) is worth knowing before
  reinventing it. Unverified — the research pass had no web access.
