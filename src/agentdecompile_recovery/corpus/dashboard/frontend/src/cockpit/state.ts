// Pure state for the cockpit feed: SSE / polling messages in, drawable state out.
import { laneOf, type ActivityEvent, type CellChange, type CellsDiff, type CellsResponse, type Hello, type Lane, type Summary } from './api';

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
  /** index -> client time of the last live change (for a brief highlight) */
  flashes: Map<number, number>;
  /** indices changed by the latest update (the map repaints only these on its base bitmap) */
  changed: number[];
  version: number;
};

export type LiveActivity = ActivityEvent & { key: string; lane: Lane; arrivedAt: number; live: boolean };

type DataAction =
  | { type: 'summary'; summary: Summary; now: number }
  | { type: 'cells'; cells: CellsResponse; now: number }
  | { type: 'diff'; diff: CellsDiff; now: number }
  | { type: 'activity'; event: ActivityEvent; now: number };

export type FeedAction =
  | DataAction
  | { type: 'hello'; hello: Hello }
  | { type: 'error'; error: string | undefined }
  | { type: 'pause'; now: number }
  | { type: 'resume'; now: number };

export type FeedState = {
  error?: string;
  hello?: Hello;
  summary?: Summary;
  summaryAt?: number;
  cells: Record<string, ProgramCells>;
  activity: LiveActivity[];
  /** Live updates held back while paused; applied in order on resume. */
  paused: boolean;
  queue: DataAction[];
  /** Cell changes applied since load (for the source chip tooltip). */
  applied: number;
};

export const ACTIVITY_CAP = 400;
export const QUEUE_CAP = 5000;
export const FLASH_MS = 1600;

export const initialFeed: FeedState = { cells: {}, activity: [], paused: false, queue: [], applied: 0 };

export const activityKey = (e: ActivityEvent) =>
  [e.ts, e.lane, e.kind, e.label, e.status, e.program_id ?? '', e.binary ?? '', e.addr ?? '', e.job_id ?? ''].join('|');

const digit = (s: string, i: number) => {
  const c = s.charCodeAt(i) - 48;
  return c >= 0 && c <= 9 ? c : 0;
};

function csr(n: number, pairs: [number, number][], from: 0 | 1): [Uint32Array, Uint32Array] {
  const to = from === 0 ? 1 : 0;
  const start = new Uint32Array(n + 1);
  for (const p of pairs) start[p[from] + 1]++;
  for (let i = 0; i < n; i++) start[i + 1] += start[i];
  const fill = start.slice(0, n);
  const list = new Uint32Array(start[n]);
  for (const p of pairs) list[fill[p[from]]++] = p[to];
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
  const edges = (r.edges || []).filter(e => Array.isArray(e) && e[0] >= 0 && e[1] >= 0 && e[0] < n && e[1] < n && e[0] !== e[1]) as [number, number][];
  const [outStart, outList] = csr(n, edges, 0);
  const [inStart, inList] = csr(n, edges, 1);
  return {
    programId: String(r.program_id), ref: r.ref, n,
    addr: (r.addr || []).slice(0, n), size: (r.size || []).slice(0, n),
    state, nb, tier, logical: (r.logical || []).slice(0, n), names, edges,
    outStart, outList, inStart, inList, flashes: new Map(), changed: [], version: 1,
  };
}

export const calleesOf = (c: ProgramCells, i: number) => Array.from(c.outList.subarray(c.outStart[i], c.outStart[i + 1]));
export const callersOf = (c: ProgramCells, i: number) => Array.from(c.inList.subarray(c.inStart[i], c.inStart[i + 1]));

/** Same functions in the same order: a refetch can be applied as a diff. */
export function sameLayout(a: ProgramCells, b: ProgramCells): boolean {
  if (a.n !== b.n || a.ref !== b.ref) return false;
  for (let i = 0; i < a.n; i++) if (a.addr[i] !== b.addr[i]) return false;
  return true;
}

/** Changes that turn `a` into `b` (same layout). */
export function diffCells(a: ProgramCells, b: ProgramCells): CellChange[] {
  const out: CellChange[] = [];
  for (let i = 0; i < a.n; i++) {
    if (a.state[i] !== b.state[i] || a.nb[i] !== b.nb[i] || a.tier[i] !== b.tier[i]) out.push([i, b.state[i], b.nb[i], b.tier[i]]);
  }
  return out;
}

/** Apply `[index, state, nb, tier]` changes; flash cells whose state or tier moved. */
export function applyDiff(c: ProgramCells, changes: CellChange[], now: number): ProgramCells {
  if (!changes?.length) return c;
  const state = c.state.slice(), nb = c.nb.slice(), tier = c.tier.slice();
  const flashes = new Map<number, number>();
  for (const [i, t] of c.flashes) if (now - t < FLASH_MS) flashes.set(i, t);
  const changed: number[] = [];
  for (const change of changes) {
    const [i, s, b, t] = change;
    if (!Number.isInteger(i) || i < 0 || i >= c.n) continue;
    const ns = Math.max(0, Math.min(2, s | 0));
    const nn = Math.max(0, Math.min(65535, b | 0));
    const nt = Math.max(0, Math.min(9, t | 0));
    if (state[i] === ns && nb[i] === nn && tier[i] === nt) continue;
    if (state[i] !== ns || tier[i] !== nt) flashes.set(i, now);
    state[i] = ns;
    nb[i] = nn;
    tier[i] = nt;
    changed.push(i);
  }
  if (!changed.length) return c;
  return { ...c, state, nb, tier, flashes, changed, version: c.version + 1 };
}

function addActivity(list: LiveActivity[], events: ActivityEvent[], now: number, live: boolean): LiveActivity[] {
  const known = new Set(list.map(a => a.key));
  const fresh: LiveActivity[] = [];
  for (const e of events) {
    if (!e || typeof e !== 'object') continue;
    const key = activityKey(e);
    if (known.has(key)) continue;
    known.add(key);
    fresh.push({ ...e, key, lane: laneOf(String(e.lane)), arrivedAt: now, live });
  }
  if (!fresh.length) return list;
  // `events` arrive oldest-first; the list is newest-first.
  return [...fresh.reverse(), ...list].slice(0, ACTIVITY_CAP);
}

function applyData(state: FeedState, action: DataAction): FeedState {
  switch (action.type) {
    case 'summary': {
      // Summary activity is newest-first. On first load it is history; afterwards unseen events are live arrivals.
      const events = [...(action.summary.activity || [])].reverse();
      const live = state.summary !== undefined;
      const activity = addActivity(state.activity, events, action.now, live);
      return { ...state, summary: action.summary, summaryAt: action.now, activity, error: undefined };
    }
    case 'cells': {
      const pid = String(action.cells.program_id);
      const fresh = decodeCells(action.cells);
      const current = state.cells[pid];
      if (current && sameLayout(current, fresh)) {
        // Refetch of the same layout (poll or reload): apply as a diff so changed cells highlight.
        const base: ProgramCells = {
          ...current, names: fresh.names, edges: fresh.edges, outStart: fresh.outStart, outList: fresh.outList,
          inStart: fresh.inStart, inList: fresh.inList, logical: fresh.logical, size: fresh.size, changed: [], version: current.version + 1,
        };
        const next = applyDiff(base, diffCells(current, fresh), action.now);
        return { ...state, cells: { ...state.cells, [pid]: next }, applied: state.applied + next.changed.length };
      }
      return { ...state, cells: { ...state.cells, [pid]: fresh } };
    }
    case 'diff': {
      const current = state.cells[String(action.diff.program_id)];
      if (!current) return state;
      const next = applyDiff(current, action.diff.changes, action.now);
      return next === current ? state : { ...state, cells: { ...state.cells, [current.programId]: next }, applied: state.applied + next.changed.length };
    }
    case 'activity': {
      const activity = addActivity(state.activity, [action.event], action.now, true);
      return activity === state.activity ? state : { ...state, activity };
    }
  }
}

export function feedReducer(state: FeedState, action: FeedAction): FeedState {
  switch (action.type) {
    case 'hello':
      return { ...state, hello: action.hello, error: undefined };
    case 'error':
      return state.error === action.error ? state : { ...state, error: action.error };
    case 'pause':
      return state.paused ? state : { ...state, paused: true };
    case 'resume': {
      if (!state.paused) return state;
      let next: FeedState = { ...state, paused: false, queue: [] };
      // Replayed arrivals animate as of now, so the resume itself shows what changed.
      for (const a of state.queue) next = applyData(next, { ...a, now: action.now });
      return next;
    }
    default: {
      // A program's first cells load always applies, so pausing never blanks the map.
      const firstCells = action.type === 'cells' && !state.cells[String(action.cells.program_id)];
      const firstSummary = action.type === 'summary' && !state.summary;
      if (state.paused && !firstCells && !firstSummary) {
        const queue = state.queue.length >= QUEUE_CAP ? [...state.queue.slice(1), action] : [...state.queue, action];
        return { ...state, queue };
      }
      return applyData(state, action);
    }
  }
}

/* ---------------- map filters and colouring ---------------- */

/** Bitmask filters: bit k of `states` keeps state k, bit t of `tiers` keeps tier t; 0 = no filter on that axis. */
export type MapFilter = { states: number; tiers: number };
export const NO_FILTER: MapFilter = { states: 0, tiers: 0 };
export const filterActive = (f: MapFilter) => f.states !== 0 || f.tiers !== 0;
export const toggleBit = (mask: number, bit: number) => mask ^ (1 << bit);
export const hasBit = (mask: number, bit: number) => (mask & (1 << bit)) !== 0;

export function matchesFilter(c: ProgramCells, i: number, f: MapFilter): boolean {
  if (f.states && !hasBit(f.states, c.state[i])) return false;
  if (f.tiers && !hasBit(f.tiers, c.tier[i])) return false;
  return true;
}

export type ColorBy = 'state' | 'builds' | 'tier';

/** Max `nb` in the program (for the builds colour scale). */
export function maxNb(c: ProgramCells): number {
  let m = 0;
  for (let i = 0; i < c.n; i++) if (c.nb[i] > m) m = c.nb[i];
  return m;
}

/** Palette index for a cell: state 0..2, tier 0..9, or builds 0 (none) .. 8 (all). */
export function colorKey(c: ProgramCells, i: number, by: ColorBy, nbMax: number): number {
  if (by === 'tier') return c.tier[i];
  if (by === 'builds') {
    const n = c.nb[i];
    return n <= 0 ? 0 : 1 + Math.min(7, Math.floor(((n - 1) / Math.max(1, nbMax)) * 8));
  }
  return c.state[i];
}

/** Count of cells per state (0..2) and tier (0..9), and named cells, for filter chips. */
export function cellCounts(c: ProgramCells | undefined) {
  const out = { states: [0, 0, 0], tiers: new Array(10).fill(0) as number[], named: 0 };
  if (!c) return out;
  for (let i = 0; i < c.n; i++) {
    out.states[c.state[i]]++;
    out.tiers[c.tier[i]]++;
  }
  out.named = c.names.size;
  return out;
}

/** Function name for display: recorded name, else an address-derived label. */
export function cellName(c: ProgramCells, i: number): string {
  const name = c.names.get(i);
  if (name) return name;
  const a = c.addr[i];
  return Number.isFinite(a) ? `sub_${a.toString(16)}` : `#${i}`;
}

/** Index of the function containing address `a` (sorted addresses), or -1. */
export function indexOfAddr(c: ProgramCells, a: number): number {
  let lo = 0, hi = c.n - 1, r = -1;
  while (lo <= hi) {
    const m = (lo + hi) >> 1;
    if (c.addr[m] <= a) {
      r = m;
      lo = m + 1;
    } else hi = m - 1;
  }
  if (r < 0) return -1;
  return a === c.addr[r] || a < c.addr[r] + Math.max(1, c.size[r] || 0) ? r : -1;
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
    const inside = indexOfAddr(c, parseInt(hexQ, 16));
    if (inside >= 0) scored.push([0.5, inside]);
    for (let i = 0; i < c.n && scored.length < 4000; i++) {
      const h = c.addr[i]?.toString(16);
      if (h && h !== hexQ && h.startsWith(hexQ)) scored.push([3 + h.length / 1000, i]);
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
