// Typed client for the cockpit live API (docs/cockpit/API.md) and the live stream hook.
// Every value the cockpit draws comes through here; nothing is synthesised on the client.
import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import { feedReducer, initialFeed, type FeedAction } from './state';

export const COCKPIT_API = '/dashboard/api/cockpit';
export const STREAM_URL = `${COCKPIT_API}/stream`;
export const POLL_MS = 5000;
export const STREAM_RETRY_MS = 30000;
export const STREAM_OPEN_TIMEOUT_MS = 6000;

export type Build = {
  id: number | string;
  slug: string;
  platform: string;
  format: string;
  functions: number;
  bound: number;
  real_c: number;
};

export type Program = {
  id: string;
  label: string;
  ref: string;
  n: number;
  builds: Build[];
};

export type Totals = {
  binaries: number;
  functions: number;
  logical: number;
  bound: number;
  recovered_logical: number;
  named_above_placeholder: number;
  named_of: number;
};

export const LANES = ['decompile', 'pointers', 'match', 'name', 'compile', 'signature', 'import', 'other'] as const;
export type Lane = (typeof LANES)[number];

export type ActivityEvent = {
  ts: string | number;
  lane: Lane | string;
  kind: string;
  program_id?: string;
  binary?: string;
  addr?: number | string;
  label: string;
  status: string;
  job_id?: string | number;
};

export type Summary = {
  ok: true;
  generated: string;
  db: { path: string; bytes: number; mtime: number | string };
  totals: Totals;
  programs: Program[];
  tiers: [string, number][];
  match_methods: [string, number][];
  activity: ActivityEvent[];
};

export type CellsResponse = {
  ok: true;
  program_id: string;
  ref: string;
  n: number;
  addr: number[];
  size: number[];
  state: string;
  nb: number[];
  tier: string;
  logical: number[];
  names: Record<string, string>;
  edges: [number, number][];
};

export type FunctionRef = { index: number; name: string; addr: number };

export type FunctionInstance = {
  binary_id: number | string;
  slug: string;
  platform: string;
  addr: number;
  size: number;
  confidence: number | null;
  method: string | null;
};

export type RecoveredRow = { binary_slug: string; addr: number; real_c: number | boolean; convention: string; size: number; name?: string };

export type FunctionDetail = {
  ok: true;
  name: string;
  tier: number | string;
  tier_name: string;
  logical_id: number | null;
  signature: string | null;
  source_file: string | null;
  instances: FunctionInstance[];
  absent: string[];
  callers: FunctionRef[];
  callees: FunctionRef[];
  recovered: RecoveredRow[];
  decomp: { ok: boolean; n_lines: number; n_calls: number; max_nest: number } | null;
  program_id?: string;
  binary_id?: number | string;
  index?: number;
  addr?: number;
  size?: number;
};

/** index, state, nb, tier */
export type CellChange = [number, number, number, number];
export type CellsDiff = { program_id: string; changes: CellChange[]; ref?: string; reload?: boolean };
export type Hello = { db: string; programs: string[] };

export const STATE_LABELS = ['Unbound', 'Bound across builds', 'C with a byte-exact receipt (this build or a sibling)'] as const;
export const STATE_SHORT = ['unbound', 'bound', 'real C'] as const;
export const TIER_LABELS: Record<number, string> = {
  0: 'No name',
  1: 'Human',
  2: 'Debug info',
  3: 'Symbols',
  4: 'Derived',
  5: 'Placeholder',
};

export class ApiError extends Error {
  constructor(message: string, readonly status = 0) {
    super(message);
  }
}

/* ---------------- parsing (defensive: a bad payload is an error, never a guess) ---------------- */

const isObj = (x: unknown): x is Record<string, any> => !!x && typeof x === 'object' && !Array.isArray(x);
const num = (x: unknown, fallback = 0) => {
  const n = typeof x === 'number' ? x : typeof x === 'string' && x.trim() !== '' ? Number(x) : NaN;
  return Number.isFinite(n) ? n : fallback;
};
const str = (x: unknown) => (x === undefined || x === null ? '' : String(x));

/** Parse an address that may arrive as a number, decimal string or 0x-hex string. */
export function parseAddr(x: unknown): number | undefined {
  if (typeof x === 'number') return Number.isFinite(x) ? x : undefined;
  if (typeof x !== 'string' || !x.trim()) return undefined;
  const s = x.trim();
  const n = /^0x[0-9a-f]+$/i.test(s) ? parseInt(s.slice(2), 16) : /^[0-9]+$/.test(s) ? Number(s) : /^[0-9a-f]+$/i.test(s) ? parseInt(s, 16) : NaN;
  return Number.isFinite(n) ? n : undefined;
}

function checkOk(body: unknown, what: string): Record<string, any> {
  if (!isObj(body)) throw new ApiError(`${what}: not an object`);
  if (body.ok === false) throw new ApiError(str(body.error) || `${what}: not ok`);
  return body;
}

function parseBuild(x: unknown): Build | undefined {
  if (!isObj(x) || !x.slug) return undefined;
  return {
    id: x.id ?? x.slug, slug: str(x.slug), platform: str(x.platform), format: str(x.format),
    functions: num(x.functions), bound: num(x.bound), real_c: num(x.real_c),
  };
}

export function parseSummary(body: unknown): Summary {
  const b = checkOk(body, 'summary');
  if (!Array.isArray(b.programs) || !isObj(b.totals)) throw new ApiError('summary: missing programs or totals');
  const t = b.totals;
  const totals: Totals = {
    binaries: num(t.binaries), functions: num(t.functions), logical: num(t.logical), bound: num(t.bound),
    recovered_logical: num(t.recovered_logical), named_above_placeholder: num(t.named_above_placeholder), named_of: num(t.named_of),
  };
  const programs: Program[] = b.programs.filter(isObj).map((p: Record<string, any>) => ({
    id: str(p.id), label: str(p.label || p.id), ref: str(p.ref), n: num(p.n),
    builds: (Array.isArray(p.builds) ? p.builds : []).map(parseBuild).filter((x: Build | undefined): x is Build => !!x),
  })).filter((p: Program) => p.id !== '');
  const pairs = (x: unknown): [string, number][] =>
    Array.isArray(x) ? x.filter(e => Array.isArray(e) && e.length >= 2).map(e => [str(e[0]), num(e[1])] as [string, number]) : [];
  const db = isObj(b.db) ? b.db : {};
  return {
    ok: true,
    generated: str(b.generated),
    db: { path: str(db.path), bytes: num(db.bytes), mtime: db.mtime ?? '' },
    totals, programs,
    tiers: pairs(b.tiers),
    match_methods: pairs(b.match_methods),
    activity: (Array.isArray(b.activity) ? b.activity : []).map(parseActivity).filter((a: ActivityEvent | undefined): a is ActivityEvent => !!a),
  };
}

export function parseCells(body: unknown): CellsResponse {
  const b = checkOk(body, 'cells');
  if (!Array.isArray(b.addr) || typeof b.state !== 'string') throw new ApiError('cells: missing addr or state');
  const n = Math.max(0, Math.min(num(b.n, b.addr.length), b.addr.length, b.state.length));
  const arr = (x: unknown) => (Array.isArray(x) ? x.slice(0, n).map(v => num(v)) : new Array(n).fill(0));
  const edges = Array.isArray(b.edges)
    ? b.edges.filter((e: unknown) => Array.isArray(e) && e.length >= 2).map((e: unknown[]) => [num(e[0], -1), num(e[1], -1)] as [number, number])
    : [];
  const names: Record<string, string> = {};
  if (isObj(b.names)) for (const [k, v] of Object.entries(b.names)) if (v) names[k] = String(v);
  return {
    ok: true, program_id: str(b.program_id), ref: str(b.ref), n,
    addr: arr(b.addr), size: arr(b.size), state: b.state.slice(0, n),
    nb: arr(b.nb), tier: typeof b.tier === 'string' ? b.tier.slice(0, n) : '', logical: arr(b.logical), names, edges,
  };
}

export function parseCellsDiff(body: unknown): CellsDiff | undefined {
  if (!isObj(body) || body.program_id === undefined) return undefined;
  const changes = Array.isArray(body.changes)
    ? body.changes.filter((c: unknown) => Array.isArray(c) && c.length >= 4).map((c: unknown[]) => [num(c[0], -1), num(c[1]), num(c[2]), num(c[3])] as CellChange)
    : [];
  return { program_id: str(body.program_id), changes, ref: body.ref ? str(body.ref) : undefined, reload: body.reload === true };
}

export function parseActivity(body: unknown): ActivityEvent | undefined {
  if (!isObj(body)) return undefined;
  if (body.ts === undefined && body.label === undefined && body.kind === undefined) return undefined;
  return {
    ts: typeof body.ts === 'number' ? body.ts : str(body.ts),
    lane: laneOf(str(body.lane)),
    kind: str(body.kind), label: str(body.label || body.kind), status: str(body.status),
    program_id: body.program_id === undefined || body.program_id === null ? undefined : str(body.program_id),
    binary: body.binary === undefined || body.binary === null ? undefined : str(body.binary),
    addr: body.addr === undefined || body.addr === null ? undefined : body.addr,
    job_id: body.job_id ?? undefined,
  };
}

export function parseFunction(body: unknown): FunctionDetail {
  const b = checkOk(body, 'function');
  const refs = (x: unknown): FunctionRef[] =>
    (Array.isArray(x) ? x : []).filter(isObj).map(r => ({ index: num(r.index, -1), name: str(r.name), addr: parseAddr(r.addr) ?? 0 }));
  return {
    ok: true,
    name: str(b.name), tier: b.tier ?? 0, tier_name: str(b.tier_name),
    logical_id: b.logical_id === null || b.logical_id === undefined ? null : num(b.logical_id),
    signature: b.signature ? str(b.signature) : null, source_file: b.source_file ? str(b.source_file) : null,
    instances: (Array.isArray(b.instances) ? b.instances : []).filter(isObj).map((i: Record<string, any>) => ({
      binary_id: i.binary_id ?? '', slug: str(i.slug), platform: str(i.platform), addr: parseAddr(i.addr) ?? 0, size: num(i.size),
      confidence: i.confidence === null || i.confidence === undefined ? null : num(i.confidence), method: i.method ? str(i.method) : null,
    })),
    absent: (Array.isArray(b.absent) ? b.absent : []).map(str),
    callers: refs(b.callers), callees: refs(b.callees),
    recovered: (Array.isArray(b.recovered) ? b.recovered : []).filter(isObj).map((r: Record<string, any>) => ({
      binary_slug: str(r.binary_slug), addr: parseAddr(r.addr) ?? 0, real_c: r.real_c === true || num(r.real_c) > 0,
      convention: str(r.convention), size: num(r.size), name: r.name ? str(r.name) : undefined,
    })),
    decomp: isObj(b.decomp) ? { ok: !!b.decomp.ok, n_lines: num(b.decomp.n_lines), n_calls: num(b.decomp.n_calls), max_nest: num(b.decomp.max_nest) } : null,
    program_id: b.program_id === undefined ? undefined : str(b.program_id),
    binary_id: b.binary_id ?? undefined,
    index: b.index === undefined ? undefined : num(b.index, -1),
    addr: parseAddr(b.addr),
    size: b.size === undefined ? undefined : num(b.size),
  };
}

/* ---------------- HTTP ---------------- */

export async function getJson(path: string, signal?: AbortSignal, timeoutMs = 20000): Promise<unknown> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const abort = () => controller.abort();
  signal?.addEventListener('abort', abort);
  try {
    const response = await fetch(path, { signal: controller.signal, headers: { Accept: 'application/json' } });
    const text = await response.text();
    let body: any;
    try {
      body = JSON.parse(text);
    } catch {
      throw new ApiError(`Unexpected response (${response.status})`, response.status);
    }
    if (!response.ok || body?.ok === false) throw new ApiError(String(body?.error || `Request failed (${response.status})`), response.status);
    return body;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', abort);
  }
}

export const summaryUrl = () => `${COCKPIT_API}/summary`;
export const cellsUrl = (programId: string, ref?: string) =>
  `${COCKPIT_API}/program/${encodeURIComponent(programId)}/cells${ref ? `?ref=${encodeURIComponent(ref)}` : ''}`;
export const functionUrl = (programId: string, index: number) =>
  `${COCKPIT_API}/function?program_id=${encodeURIComponent(programId)}&index=${index}`;

export const fetchSummary = async (signal?: AbortSignal) => parseSummary(await getJson(summaryUrl(), signal));
export const fetchCells = async (programId: string, signal?: AbortSignal) => parseCells(await getJson(cellsUrl(programId), signal, 60000));
export const fetchFunction = async (programId: string, index: number, signal?: AbortSignal) =>
  parseFunction(await getJson(functionUrl(programId, index), signal));

/* ---------------- formatting ---------------- */

export const hex = (value: number | string | undefined | null) => {
  if (value === undefined || value === null || value === '') return '';
  const n = typeof value === 'number' ? value : parseAddr(value);
  return n !== undefined && Number.isFinite(n) ? `0x${n.toString(16).padStart(8, '0')}` : String(value);
};

export const fmt = (value: number | undefined | null) =>
  value === undefined || value === null || !Number.isFinite(value) ? '—' : value.toLocaleString('en-US');

export const ratio = (num: number | undefined, den: number | undefined): number | null =>
  num === undefined || den === undefined || !Number.isFinite(num) || !Number.isFinite(den) || den <= 0 ? null : Math.max(0, Math.min(1, num / den));

export const laneOf = (lane: string | undefined): Lane => ((LANES as readonly string[]).includes(String(lane)) ? (lane as Lane) : 'other');

/** Event time in epoch ms (the API sends epoch seconds or ISO strings). */
export function eventTime(ts: string | number): number {
  if (typeof ts === 'number') return ts < 1e12 ? ts * 1000 : ts;
  const n = Number(ts);
  if (ts.trim() !== '' && Number.isFinite(n)) return n < 1e12 ? n * 1000 : n;
  const d = Date.parse(ts);
  return Number.isFinite(d) ? d : NaN;
}

/* ---------------- live stream hook ---------------- */

export type Transport = 'connecting' | 'stream' | 'polling' | 'offline';

function parseData(event: Event): unknown {
  try {
    return JSON.parse(String((event as MessageEvent).data));
  } catch {
    return undefined;
  }
}

/**
 * Live feed. EventSource on /stream (hello, summary, cells, activity, resync);
 * while the stream is not open the summary is polled every 5 s and, when the
 * corpus changed, the open program's cells are refetched and applied as a diff.
 * A closed stream is retried every 30 s. `paused` queues incoming data until resume.
 */
export function useCockpitStream(programId: string | undefined) {
  const [state, dispatch] = useReducer(feedReducer, initialFeed);
  const [transport, setTransport] = useState<Transport>('connecting');
  const [cellsError, setCellsError] = useState<Record<string, string>>({});
  const streamOpen = useRef(false);
  const selected = useRef(programId);
  selected.current = programId;
  const loaded = useRef(new Set<string>());
  const inflight = useRef(new Set<string>());
  const send = useCallback((a: FeedAction) => dispatch(a), []);

  const loadCells = useCallback(async (pid: string) => {
    if (inflight.current.has(pid)) return;
    inflight.current.add(pid);
    try {
      const cells = await fetchCells(pid);
      loaded.current.add(pid);
      send({ type: 'cells', cells, now: Date.now() });
      setCellsError(old => {
        if (!(pid in old)) return old;
        const next = { ...old };
        delete next[pid];
        return next;
      });
    } catch (error) {
      setCellsError(old => ({ ...old, [pid]: String((error as Error)?.message || error) }));
    } finally {
      inflight.current.delete(pid);
    }
  }, [send]);

  const pollSummary = useCallback(async () => {
    try {
      const summary = await fetchSummary();
      send({ type: 'summary', summary, now: Date.now() });
      if (!streamOpen.current) setTransport('polling');
      return summary;
    } catch (error) {
      if (!streamOpen.current) {
        setTransport('offline');
        send({ type: 'error', error: String((error as Error)?.message || error) });
      }
      return undefined;
    }
  }, [send]);

  useEffect(() => {
    let alive = true;
    let es: EventSource | undefined;
    let pollTimer: ReturnType<typeof setTimeout> | undefined;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let openTimer: ReturnType<typeof setTimeout> | undefined;
    let lastStamp = '';
    const stamp = (s: Summary) => `${s.generated}|${s.db.mtime}|${s.db.bytes}`;

    const refreshLoaded = () => {
      for (const pid of loaded.current) if (pid === selected.current) void loadCells(pid);
    };

    const schedulePoll = (delay = POLL_MS) => {
      if (pollTimer || !alive) return;
      pollTimer = setTimeout(async () => {
        pollTimer = undefined;
        if (!alive || streamOpen.current) return;
        const summary = await pollSummary();
        if (summary) {
          const s = stamp(summary);
          if (lastStamp && s !== lastStamp) refreshLoaded();
          lastStamp = s;
        }
        schedulePoll();
      }, delay);
    };

    const openStream = () => {
      if (!alive) return;
      if (typeof EventSource === 'undefined') {
        schedulePoll(0);
        return;
      }
      es?.close();
      let source: EventSource;
      try {
        source = new EventSource(STREAM_URL);
      } catch {
        schedulePoll(0);
        return;
      }
      es = source;
      let errors = 0;
      const opened = () => {
        errors = 0;
        clearTimeout(openTimer);
        if (!streamOpen.current) {
          streamOpen.current = true;
          setTransport('stream');
          send({ type: 'error', error: undefined });
        }
      };
      clearTimeout(openTimer);
      openTimer = setTimeout(() => {
        if (!streamOpen.current && es === source) {
          source.close();
          schedulePoll(0);
          retryTimer = setTimeout(openStream, STREAM_RETRY_MS);
        }
      }, STREAM_OPEN_TIMEOUT_MS);
      source.onopen = opened;
      source.addEventListener('hello', event => {
        opened();
        const hello = parseData(event) as Hello | undefined;
        if (hello && typeof hello === 'object') send({ type: 'hello', hello });
      });
      source.addEventListener('summary', event => {
        opened();
        try {
          const summary = parseSummary(parseData(event));
          lastStamp = stamp(summary);
          send({ type: 'summary', summary, now: Date.now() });
        } catch {
          /* malformed frame: ignore, the next one replaces it */
        }
      });
      source.addEventListener('cells', event => {
        opened();
        const diff = parseCellsDiff(parseData(event));
        if (!diff || diff.ref) return; // only the default reference build is drawn
        if (diff.reload) {
          if (loaded.current.has(diff.program_id)) void loadCells(diff.program_id);
          return;
        }
        send({ type: 'diff', diff, now: Date.now() });
      });
      source.addEventListener('activity', event => {
        opened();
        const activity = parseActivity(parseData(event));
        if (activity) send({ type: 'activity', event: activity, now: Date.now() });
      });
      source.addEventListener('resync', () => {
        opened();
        void pollSummary();
        refreshLoaded();
      });
      source.onerror = () => {
        errors++;
        const wasOpen = streamOpen.current;
        streamOpen.current = false;
        if (wasOpen) setTransport('polling');
        schedulePoll(0);
        if (source.readyState === EventSource.CLOSED || errors >= 3) {
          source.close();
          if (es === source) es = undefined;
          clearTimeout(retryTimer);
          retryTimer = setTimeout(openStream, STREAM_RETRY_MS);
        }
      };
    };

    void pollSummary().then(summary => {
      if (summary && !lastStamp) lastStamp = stamp(summary);
    });
    openStream();
    return () => {
      alive = false;
      streamOpen.current = false;
      es?.close();
      clearTimeout(pollTimer);
      clearTimeout(retryTimer);
      clearTimeout(openTimer);
    };
  }, [pollSummary, loadCells, send]);

  // A fresh summary means the API answered again: allow failed cell loads to retry.
  useEffect(() => setCellsError(old => (Object.keys(old).length ? {} : old)), [state.summary?.generated]);

  useEffect(() => {
    if (programId && !state.cells[programId] && !cellsError[programId]) void loadCells(programId);
  }, [programId, state.cells, cellsError, loadCells]);

  // Returning to a program loaded earlier: refresh it in the background (applied as a diff).
  useEffect(() => {
    if (programId && loaded.current.has(programId)) void loadCells(programId);
  }, [programId, loadCells]);

  const retry = useCallback(() => {
    setCellsError({});
    void pollSummary();
  }, [pollSummary]);

  const setPaused = useCallback((paused: boolean) => send({ type: paused ? 'pause' : 'resume', now: Date.now() }), [send]);

  return {
    state,
    transport,
    retry,
    setPaused,
    paused: state.paused,
    queued: state.queue.length,
    cellsError: programId ? cellsError[programId] : undefined,
  };
}
