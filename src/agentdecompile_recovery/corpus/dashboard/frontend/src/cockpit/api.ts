// Typed client for the cockpit live API (docs/cockpit/API.md). Every value the
// cockpit draws comes through here; nothing is synthesised on the client.

export const COCKPIT_API = '/dashboard/api/cockpit';
export const STREAM_URL = `${COCKPIT_API}/stream`;
export const POLL_MS = 5000;

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
  confidence: number;
  method: string;
};

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
  recovered: { binary_slug: string; addr: number; real_c: number | boolean; convention: string; size: number }[];
  decomp: { ok: boolean; n_lines: number; n_calls: number; max_nest: number } | null;
};

/** index, state, nb, tier */
export type CellChange = [number, number, number, number];
export type CellsDiff = { program_id: string; changes: CellChange[] };
export type Hello = { db: string; programs: string[] };

export const STATE_LABELS = ['Unbound', 'Bound across builds', 'C with a byte-exact receipt (this build or a sibling)'] as const;
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

export async function getJson<T>(path: string, signal?: AbortSignal, timeoutMs = 10000): Promise<T> {
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
    return body as T;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', abort);
  }
}

export const fetchSummary = (signal?: AbortSignal) => getJson<Summary>(`${COCKPIT_API}/summary`, signal);
export const fetchCells = (programId: string, signal?: AbortSignal) =>
  getJson<CellsResponse>(`${COCKPIT_API}/program/${encodeURIComponent(programId)}/cells`, signal, 30000);
export const fetchFunction = (programId: string, index: number, signal?: AbortSignal) =>
  getJson<FunctionDetail>(`${COCKPIT_API}/function?program_id=${encodeURIComponent(programId)}&index=${index}`, signal);

export const hex = (value: number | string | undefined | null) => {
  if (value === undefined || value === null || value === '') return '';
  const n = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(n) ? `0x${n.toString(16).padStart(8, '0')}` : String(value);
};

export const fmt = (value: number | undefined | null) =>
  value === undefined || value === null || !Number.isFinite(value) ? '—' : value.toLocaleString('en-US');

export const ratio = (num: number | undefined, den: number | undefined): number | null =>
  num === undefined || den === undefined || !Number.isFinite(num) || !Number.isFinite(den) || den <= 0 ? null : Math.max(0, Math.min(1, num / den));

export const laneOf = (lane: string | undefined): Lane => ((LANES as readonly string[]).includes(String(lane)) ? (lane as Lane) : 'other');
