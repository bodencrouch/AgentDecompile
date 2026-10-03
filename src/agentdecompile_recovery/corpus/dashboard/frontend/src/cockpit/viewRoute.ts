// Which top-level view /react/ shows, and links between the cockpit and the workstation.

export type AppView = 'cockpit' | 'workstation';

// Query keys the workstation route understands (see workstation/navigation.ts).
const WORKSTATION_KEYS = [
  'slug', 'program', 'addr', 'logicalId', 'corpusIdentity', 'locator', 'binaryHash', 'projectId', 'functionId',
  'lastFunctionAddr', 'binary', 'function', 'logical_id', 'corpus_identity', 'project', 'binary_hash', 'project_id',
  'function_id', 'view', 'window', 'focus', 'tool',
];

/** `#workstation` / `#cockpit` win; otherwise an existing workstation deep link keeps working. */
export function chooseView(hash: string, search: string): AppView {
  if (hash.startsWith('#workstation')) return 'workstation';
  if (hash.startsWith('#cockpit')) return 'cockpit';
  const params = new URLSearchParams(search);
  return WORKSTATION_KEYS.some(key => params.has(key)) ? 'workstation' : 'cockpit';
}

export const hexAddr = (addr: number) => `0x${addr.toString(16).padStart(8, '0')}`;

/** Deep link into the workstation's drill-down (Decompiler by default) for one build's function. */
export function workstationHref(slug: string, addr: number | undefined, view = 'Decompiler'): string {
  const params = new URLSearchParams({ slug });
  if (addr !== undefined && Number.isFinite(addr)) params.set('addr', hexAddr(addr));
  params.set('view', view);
  return `?${params.toString()}#workstation`;
}

export type CockpitLocation = { program?: string; fn?: number };

export function readCockpitHash(hash: string): CockpitLocation {
  const q = hash.indexOf('?');
  if (!hash.startsWith('#cockpit') || q < 0) return {};
  const params = new URLSearchParams(hash.slice(q + 1));
  const fn = Number(params.get('fn'));
  return { program: params.get('program') || undefined, fn: params.has('fn') && Number.isInteger(fn) && fn >= 0 ? fn : undefined };
}

export function cockpitHash(loc: CockpitLocation): string {
  const params = new URLSearchParams();
  if (loc.program) params.set('program', loc.program);
  if (loc.program && loc.fn !== undefined && loc.fn >= 0) params.set('fn', String(loc.fn));
  const s = params.toString();
  return s ? `#cockpit?${s}` : '#cockpit';
}
