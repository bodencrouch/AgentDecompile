# Project query performance audit

Readonly source audit plus actual8080 Playwright timings; no writes/jobs/retries.
Root observed one scopedWinMain request39.8s, repeat5.7s, corpus-db24.6s then43ms,
and healthz18.3s then7ms. These timings do not prove direct shared-lock blockage.

project_universe.py rebuilds every open-project inventory/property-file scan,
rereads up to100 preparationJSONs, then performs broad SQLite counts and LIKE
search before paging/evidencejoins. Each query repeats this aggregation; no
membership cache. Its SQLite15s deadline does not bound prior filesystem work.
router.py offloads this route through asyncio.to_thread. No native/Ghidra/context
or global request lock found here. Health probes normally read cached values;
I/O/GIL/threadpool contention or another blocking route remain possible causes.
Existing logs do not distinguish those causes with phase timings/eventlooplag.

Focused next repair: retain a membership snapshot by actual underlying identities
and invalidate on explicit project/progress changes; search/page before expensive
evidencejoins; avoid rebuilding universe for every search; preserve stale/error
labels, opt-in aggregation and all-project scope. Add phase/loop timing before
claiming health-delay cause fixed. Do not guess remote/server revisions or reuse
cache as fresh matching/compiler proof.
