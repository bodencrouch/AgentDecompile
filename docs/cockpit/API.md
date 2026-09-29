# Cockpit live API (contract)

The cockpit is the product home screen: every program in the corpus drawn as a map of its
functions, updating live as the machine works. Both the Vite app (`/react/#cockpit`) and the
static page (`/dashboard/cockpit`) consume exactly this contract. Nothing here is simulated:
every value comes from the corpus identity database at request time. Generic by construction:
no product, program or binary names in code; programs are groups of binaries by `binary.game`
(fallback: variant group, then one program per binary).

Corpus DB resolution (read-only, `?mode=ro`): `?db=` query param (must be an existing file) →
env `AGENTDECOMPILE_COCKPIT_DB` → first `*.sqlite` under the configured corpus root / AIO
`databases/` that contains table `logical_function` → the dashboard's configured corpus db.
Schema used: `binary, func, identity, logical_function, logical_name, recovered_function,
calledge` (missing tables degrade to empty fields, never errors).

All responses: `{"ok": true, ...}` or `{"ok": false, "error": "..."}`. Cached by (db path, mtime,
`PRAGMA data_version`); heavy queries run in a worker thread; every endpoint answers < 2 s from
cache and never blocks the event loop.

## GET /dashboard/api/cockpit/summary
```
{ ok, generated: iso, db: {path, bytes, mtime},
  totals: {binaries, functions, logical, bound, recovered_logical, named_above_placeholder, named_of},
  programs: [ {id, label, ref: <binary slug with most functions>, n: <ref function count>,
               builds: [ {id, slug, platform, format, functions, bound, real_c} ] } ],
  tiers: [[tier_name, count]], match_methods: [[method, count]],
  activity: [ <latest 50 activity events, newest first> ] }
```

## GET /dashboard/api/cockpit/program/{program_id}/cells
Reference build = binary in the program with most functions.
```
{ ok, program_id, ref, n,
  addr: [int], size: [int],
  state: "0121…",   // per cell: 0 unbound, 1 bound to a logical fn, 2 real-C recovered (row match or its logical fn has real C anywhere).
                    // recovered_function keeps only rows with a byte-exact coverage verdict, so 2 means "C with a recorded
                    // byte-exact receipt in this build or a sibling". A sibling-only 2 is transferred evidence, not a
                    // verdict for this build, and neither is fresh whole-image acceptance. UI labels must say so.
  nb: [int],        // distinct builds bound to the cell's logical fn
  tier: "13…",      // logical_name.tier digit, '0' none (1 human, 2 debug info, 3 symbols, 4 derived, 5 placeholder)
  logical: [int],   // logical_function.id or 0
  names: {"<i>": name},   // tiers 1–3
  edges: [[i, j]] }       // call edges among ref-build cells, ≤ 30000, named-first
```

## GET /dashboard/api/cockpit/function?program_id=&index=   (or ?binary_id=&addr=)
```
{ ok, name, tier, tier_name, logical_id, signature, source_file,
  instances: [ {binary_id, slug, platform, addr, size, confidence, method} ],   // every build it is bound in
  absent: [slug],                                                               // builds in the program with no instance
  callers: [ {index, name, addr} ], callees: [ {index, name, addr} ],           // in the ref build, ≤ 64 each
  recovered: [ {binary_slug, addr, real_c, convention, size} ],
  decomp: {ok, n_lines, n_calls, max_nest} | null }
```

## GET /dashboard/api/cockpit/stream   (text/event-stream)
Emits, with `retry: 3000`:
- `event: hello` `{db, programs:[ids]}` on connect
- `event: summary` full summary when `data_version`/mtime changes (checked every 2 s)
- `event: cells` `{program_id, changes: [[index, state, nb, tier]]}` diff vs. the previous snapshot
- `event: activity` `{ts, lane, kind, program_id?, binary?, addr?, label, status}` from the
  dashboard's existing activity/job feed (lanes: decompile, pointers, match, name, compile, signature,
  import, other); mapped from job/action names, never invented
- `: ping` every 15 s
Multiple clients may connect; each gets its own queue; one shared poller.

## GET /dashboard/cockpit
Static cockpit page (no build step) served from `dashboard/static/cockpit/`.

## Implementation notes

Implemented in `src/agentdecompile_recovery/corpus/dashboard/cockpit.py` (`create_cockpit_router()`,
included by `create_dashboard_router()` next to the React router); tests in
`tests/test_dashboard_cockpit.py`. Additive details beyond the contract above:
- Programs group by `binary.game`; a binary with no `game` is its own program (label = slug).
  Variant groups are not used (they depend on comparison receipts, not the corpus DB).
  Program `id` is the slugified label; `programs` are ordered by ref size, largest first.
- `cells` and `function` accept `&ref=<build slug>` to draw another build of the same program
  (default: the build with most functions). `function` also returns `program_id, binary_id,
  index, addr, size`; `recovered[]` items also carry `name`. `addr=` accepts decimal or `0x` hex.
- Real-C rows with NULL `addr` resolve by a name unique within the same binary; a row's logical
  function comes from its `logical_id` column and/or the identity at its resolved address.
- `activity` events are mapped from the existing job store (`GET /api/v1/jobs` rows):
  `ts` is epoch seconds (finished → started → created), `kind` is the action id, `label` the job
  title, plus `job_id`. Lane = first keyword match on action id + title, else `other`.
- SSE extras: a `cells` event carries `ref` when it is for a non-default build and
  `reload: true` (with empty `changes`) when the function layout itself changed (refetch cells);
  `event: resync` is sent to a client whose queue (512) overflowed (refetch everything).
  Only cell sets that some client has fetched are diffed.
- Cache key: (path, db mtime/size, `-wal` mtime/size, `PRAGMA data_version` on a persistent
  read-only connection). No indexes are created; everything else is in-memory dicts.

## Running it

The canonical checkout (this repo) is not what 8080 executes: the live runtime serves code from
`/home/brunner56/agentdecompile-nvme/src`, and its in-place hot reload only swaps function
bodies — it never re-runs `create_dashboard_router()`, so new routes cannot appear by reload.
To make the cockpit live the user must, deliberately and at a time they choose:
1. Copy `src/agentdecompile_recovery/corpus/dashboard/cockpit.py` (new file) into
   `/home/brunner56/agentdecompile-nvme/src/agentdecompile_recovery/corpus/dashboard/`, and apply
   the two-line `router.py` change (the `create_cockpit_router` include after
   `create_react_router`) to that tree's `router.py` — merge it, do not overwrite, since the
   trees may differ. Copy `dashboard/static/cockpit/` too once the page exists.
2. Restart the 8080 server process once (route registration happens only at app construction).
3. Optionally set `AGENTDECOMPILE_COCKPIT_DB=/home/brunner56/biodecompwarehouse/kotorxid/db/kotorxid.sqlite`
   in the server environment (otherwise pass `?db=` or rely on the discovery order above).
4. Verify: `GET /dashboard/api/cockpit/summary` returns `ok: true`, then open `/dashboard/cockpit`.
Measured on the 1.1 GB corpus (cold/warm): summary 5–8 s / 0.01 s; largest program cells
(74k functions) 1.5–2.2 s / 0.01 s; function detail 0.1–0.8 s.
