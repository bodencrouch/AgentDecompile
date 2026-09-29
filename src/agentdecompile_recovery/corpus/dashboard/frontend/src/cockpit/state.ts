// Pure state for the cockpit feed: SSE / polling messages in, drawable state out.
import { laneOf, type ActivityEvent, type CellsDiff, type CellsResponse, type Hello, type Lane, type Summary } from './api';

export type Connection = 'connecting' | 'live' | 'polling' | 'offline';

export type ProgramCells = {
  programId: string;
  ref: string;
  n: number;
  addr: number[];
  size: number[];
  state: Uint8Array;
  nb: Uint16Array;
  tier: Uint8Array;
  logical: number[];
  names: Map<number, string>;
  edges: [number, number][];
  /** CSR adjacency: callees of i are outList[outStart[i]..outStart[i+1]) */
  outStart: Uint32Array;
  outList: Uint32Array;
  inStart: Uint32Array;
  inList: Uint32Array;
  /** index -> client time of the last live change (for a brief glow) */
  flashes: Map<number, number>;
  version: number;
};

export type LiveActivity = ActivityEvent & { key: string; lane: Lane; arrivedAt: number; live: boolean };

export type FeedState = {
  connection: Connection;
  error?: string;
  hello?: Hello;
  summary?: Summary;
  summaryAt?: number;
  cells: Record<string, ProgramCells>;
  activity: LiveActivity[];
};

export type FeedAction =
  | { type: 'connection'; connection: Connection; error?: string }
  | { type: 'hello'; hello: Hello }
  | { type: 'summary'; summary: Summary; now: number }
  | { type: 'cells'; cells: CellsResponse; now: number }
  | { type: 'diff'; diff: CellsDiff; now: number }
  | { type: 'activity'; event: ActivityEvent; now: number };

export const ACTIVITY_CAP = 200;
export const FLASH_MS = 2500;

export const initialFeed: FeedState = { connection: 'connecting', cells: {}, activity: [] };

export const activityKey = (e: ActivityEvent) =>
  [e.ts, e.lane, e.kind, e.label, e.status, e.program_id ?? '', e.binary ?? '', e.addr ?? ''].join('|');

const digit = (s: string, i: number) => {
  const c = s.charCodeAt(i) - 48;
  return c >= 0 && c <= 9 ? c : 0;
};

function csr(n: number, pairs: [number, number][], from: 0 | 1): [Uint32Array, Uint32Array] {
  const to = from === 0 ? 1 : 0;
  const start = new Uint32Array(n + 1);
  for (const p of pairs) if (p[from] < n && p[to] < n) start[p[from] + 1]++;
  for (let i = 0; i < n; i++) start[i + 1] += start[i];
  const fill = start.slice(0, n);
  const list = new Uint32Array(start[n]);
  for (const p of pairs) if (p[from] < n && p[to] < n) list[fill[p[from]]++] = p[to];
  return [start, list];
}

export function decodeCells(r: CellsResponse): ProgramCells {
  const n = Math.max(0, Math.min(r.n | 0, r.addr?.length ?? 0));
  const state = new Uint8Array(n), tier = new Uint8Array(n), nb = new Uint16Array(n);
  for (let i = 0; i < n; i++) {
    state[i] = Math.min(2, digit(r.state || '', i));
    tier[i] = digit(r.tier || '', i);
    nb[i] = Math.max(0, Math.min(65535, r.nb?.[i] ?? 0));
  }
  const names = new Map<number, string>();
  for (const [k, v] of Object.entries(r.names || {})) {
    const i = Number(k);
    if (Number.isInteger(i) && i >= 0 && i < n && v) names.set(i, v);
  }
  const edges = (r.edges || []).filter(e => Array.isArray(e) && e[0] >= 0 && e[1] >= 0 && e[0] < n && e[1] < n) as [number, number][];
  const [outStart, outList] = csr(n, edges, 0);
  const [inStart, inList] = csr(n, edges, 1);
  return {
    programId: String(r.program_id), ref: r.ref, n,
    addr: (r.addr || []).slice(0, n), size: (r.size || []).slice(0, n),
    state, nb, tier, logical: (r.logical || []).slice(0, n), names, edges,
    outStart, outList, inStart, inList, flashes: new Map(), version: 1,
  };
}

export const calleesOf = (c: ProgramCells, i: number) => Array.from(c.outList.subarray(c.outStart[i], c.outStart[i + 1]));
export const callersOf = (c: ProgramCells, i: number) => Array.from(c.inList.subarray(c.inStart[i], c.inStart[i + 1]));

export function applyDiff(c: ProgramCells, diff: CellsDiff, now: number): ProgramCells {
  if (!diff.changes?.length) return c;
  const state = c.state.slice(), nb = c.nb.slice(), tier = c.tier.slice();
  const flashes = new Map<number, number>();
  for (const [i, t] of c.flashes) if (now - t < FLASH_MS) flashes.set(i, t);
  let changed = false;
  for (const change of diff.changes) {
    const [i, s, b, t] = change;
    if (!Number.isInteger(i) || i < 0 || i >= c.n) continue;
    const ns = Math.max(0, Math.min(2, s | 0));
    if (state[i] !== ns) flashes.set(i, now);
    if (state[i] !== ns || nb[i] !== b || tier[i] !== t) changed = true;
    state[i] = ns;
    nb[i] = Math.max(0, Math.min(65535, b | 0));
    tier[i] = Math.max(0, Math.min(9, t | 0));
  }
  if (!changed) return c;
  return { ...c, state, nb, tier, flashes, version: c.version + 1 };
}

function addActivity(list: LiveActivity[], events: ActivityEvent[], now: number, live: boolean): LiveActivity[] {
  const known = new Set(list.map(a => a.key));
  const fresh: LiveActivity[] = [];
  for (const e of events) {
    if (!e || typeof e !== 'object') continue;
    const key = activityKey(e);
    if (known.has(key)) continue;
    known.add(key);
    fresh.push({ ...e, key, lane: laneOf(e.lane), arrivedAt: now, live });
  }
  if (!fresh.length) return list;
  // `events` arrive oldest-first; the list is newest-first.
  return [...fresh.reverse(), ...list].slice(0, ACTIVITY_CAP);
}

export function feedReducer(state: FeedState, action: FeedAction): FeedState {
  switch (action.type) {
    case 'connection':
      if (state.connection === action.connection && state.error === action.error) return state;
      return { ...state, connection: action.connection, error: action.error };
    case 'hello':
      return { ...state, hello: action.hello, connection: 'live', error: undefined };
    case 'summary': {
      // Summary activity is newest-first. On first load it is history (no
      // packets); afterwards unseen events are real arrivals and animate.
      const events = [...(action.summary.activity || [])].reverse();
      const live = state.summary !== undefined;
      const activity = addActivity(state.activity, events, action.now, live);
      return { ...state, summary: action.summary, summaryAt: action.now, activity };
    }
    case 'cells':
      return { ...state, cells: { ...state.cells, [String(action.cells.program_id)]: decodeCells(action.cells) } };
    case 'diff': {
      const current = state.cells[String(action.diff.program_id)];
      if (!current) return state;
      const next = applyDiff(current, action.diff, action.now);
      return next === current ? state : { ...state, cells: { ...state.cells, [current.programId]: next } };
    }
    case 'activity': {
      const activity = addActivity(state.activity, [action.event], action.now, true);
      return activity === state.activity ? state : { ...state, activity };
    }
  }
}

/** Count of cells per state (0,1,2) and named cells, for legends. */
export function cellCounts(c: ProgramCells | undefined) {
  const out = { states: [0, 0, 0], named: 0 };
  if (!c) return out;
  for (let i = 0; i < c.n; i++) out.states[c.state[i]]++;
  out.named = c.names.size;
  return out;
}

export type MapFilter =
  | { kind: 'all' }
  | { kind: 'state'; value: number }
  | { kind: 'tier'; value: number }
  | { kind: 'named' };

export const ALL: MapFilter = { kind: 'all' };

export function matchesFilter(c: ProgramCells, i: number, f: MapFilter): boolean {
  switch (f.kind) {
    case 'all': return true;
    case 'state': return c.state[i] === f.value;
    case 'tier': return c.tier[i] === f.value;
    case 'named': return c.names.has(i);
  }
}

/**
 * Colour bucket per cell: 0..2 state, +3 when named (tiers 1–3 carry a name),
 * 6 = dimmed by the active filter.
 */
export const DIM_BUCKET = 6;
export function bucketsFor(c: ProgramCells, f: MapFilter): Uint8Array {
  const out = new Uint8Array(c.n);
  for (let i = 0; i < c.n; i++) {
    out[i] = !matchesFilter(c, i, f) ? DIM_BUCKET : c.state[i] + (c.names.has(i) ? 3 : 0);
  }
  return out;
}

/** Function name for display: recorded name, else an address-derived label. */
export function cellName(c: ProgramCells, i: number): string {
  const name = c.names.get(i);
  if (name) return name;
  const a = c.addr[i];
  return Number.isFinite(a) ? `sub_${a.toString(16)}` : `#${i}`;
}

/** Realtime search over names and addresses; exact/prefix matches first. */
export function searchCells(c: ProgramCells | undefined, query: string, limit = 12): number[] {
  const q = query.trim().toLowerCase();
  if (!c || !q) return [];
  const hexQ = q.replace(/^0x/, '').replace(/^sub_/, '');
  const isHex = /^[0-9a-f]+$/.test(hexQ);
  const scored: [number, number][] = [];
  for (const [i, name] of c.names) {
    const n = name.toLowerCase();
    const at = n.indexOf(q);
    if (at < 0) continue;
    scored.push([n === q ? 0 : at === 0 ? 1 : 2 + n.length / 1000, i]);
  }
  if (isHex && hexQ.length >= 3) {
    for (let i = 0; i < c.n && scored.length < 4000; i++) {
      const h = c.addr[i]?.toString(16);
      if (!h) continue;
      if (h === hexQ) scored.push([0.5, i]);
      else if (h.startsWith(hexQ)) scored.push([3 + h.length / 1000, i]);
    }
  }
  scored.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const seen = new Set<number>(), out: number[] = [];
  for (const [, i] of scored) {
    if (seen.has(i)) continue;
    seen.add(i);
    out.push(i);
    if (out.length >= limit) break;
  }
  return out;
}
