import { describe, expect, it } from 'vitest';
import { eventTime, hex, laneOf, parseActivity, parseAddr, parseCells, parseCellsDiff, parseFunction, parseSummary, ratio } from './api';
import { presenceRows, shortSlug } from './Lens';
import { markPosition, pickWindow, statusTone } from './ActivityLanes';
import { orderedBuilds } from './VariantMatrix';

const rawSummary = {
  ok: true,
  generated: '2026-09-29T12:00:00Z',
  db: { path: '/data/corpus.sqlite', bytes: 10, mtime: 5 },
  totals: { binaries: 3, functions: '30', logical: 12, bound: 20, recovered_logical: 2, named_above_placeholder: 6, named_of: 12 },
  programs: [
    { id: 'alpha', label: 'Alpha', ref: 'alpha__win', n: 10, builds: [
      { id: 1, slug: 'alpha__win', platform: 'win', format: 'pe', functions: 10, bound: 8, real_c: 1 },
      { id: 2, slug: 'alpha__mac', platform: 'mac', format: 'macho', functions: 12, bound: 6, real_c: 0 },
      { bogus: true },
    ] },
    'not a program',
  ],
  tiers: [['human', 1], ['debug', 2], ['bad']],
  match_methods: [['exact', 9]],
  activity: [{ ts: 1700000000, lane: 'match', kind: 'match.run', label: 'Match builds', status: 'done', addr: '0x401000' }, { nothing: 1 }],
};

describe('parseSummary', () => {
  it('normalises the payload and drops malformed rows', () => {
    const s = parseSummary(rawSummary);
    expect(s.totals.functions).toBe(30);
    expect(s.programs).toHaveLength(1);
    expect(s.programs[0].builds.map(b => b.slug)).toEqual(['alpha__win', 'alpha__mac']);
    expect(s.tiers).toEqual([['human', 1], ['debug', 2]]);
    expect(s.activity).toHaveLength(1);
    expect(s.activity[0].lane).toBe('match');
  });

  it('rejects errors and payloads without programs', () => {
    expect(() => parseSummary({ ok: false, error: 'no corpus db' })).toThrow('no corpus db');
    expect(() => parseSummary({ ok: true, totals: {} })).toThrow();
    expect(() => parseSummary(null)).toThrow();
  });
});

describe('parseCells', () => {
  it('clamps arrays to the shortest of n, addr and state', () => {
    const c = parseCells({
      ok: true, program_id: 'alpha', ref: 'alpha__win', n: 4, addr: [16, 32, 48], size: [16, 16, 16, 16], state: '0120', nb: [0, 1, 2, 3],
      tier: '1234', logical: [0, 5, 6, 7], names: { 1: 'f', 2: '' }, edges: [[0, 1], [2], [1, 'x']],
    });
    expect(c.n).toBe(3);
    expect(c.state).toBe('012');
    expect(c.size).toEqual([16, 16, 16]);
    expect(c.names).toEqual({ 1: 'f' });
    expect(c.edges).toEqual([[0, 1], [1, -1]]);
  });

  it('rejects a payload without addresses', () => {
    expect(() => parseCells({ ok: true, state: '0' })).toThrow();
  });
});

describe('stream frames', () => {
  it('parses cell diffs including reload and ref extras', () => {
    expect(parseCellsDiff({ program_id: 'alpha', changes: [[1, 2, 3, 4], [5]] })).toEqual({ program_id: 'alpha', changes: [[1, 2, 3, 4]], ref: undefined, reload: false });
    expect(parseCellsDiff({ program_id: 'alpha', changes: [], reload: true, ref: 'alpha__mac' })?.reload).toBe(true);
    expect(parseCellsDiff({ changes: [] })).toBeUndefined();
  });

  it('parses activity and maps unknown lanes to other', () => {
    const a = parseActivity({ ts: '2026-09-29T00:00:00Z', lane: 'mystery', kind: 'x', label: '', status: 'failed', program_id: null });
    expect(a?.lane).toBe('other');
    expect(a?.label).toBe('x');
    expect(a?.program_id).toBeUndefined();
    expect(parseActivity('nope')).toBeUndefined();
    expect(laneOf('compile')).toBe('compile');
  });

  it('parses function detail defensively', () => {
    const d = parseFunction({
      ok: true, name: 'f', tier: 3, tier_name: 'symbols', logical_id: 7, signature: null, source_file: null,
      instances: [{ binary_id: 1, slug: 'alpha__win', platform: 'win', addr: '0x10', size: 4, confidence: null, method: 'exact' }],
      absent: ['alpha__mac'], callers: [{ index: 2, name: 'g', addr: 32 }], callees: 'bad',
      recovered: [{ binary_slug: 'alpha__win', addr: 16, real_c: 1, convention: 'cdecl', size: 4 }], decomp: null, addr: '0x10',
    });
    expect(d.instances[0].addr).toBe(16);
    expect(d.instances[0].confidence).toBeNull();
    expect(d.callees).toEqual([]);
    expect(d.recovered[0].real_c).toBe(true);
    expect(d.addr).toBe(16);
  });
});

describe('helpers', () => {
  it('parses addresses and times', () => {
    expect(parseAddr('0x1F')).toBe(31);
    expect(parseAddr('31')).toBe(31);
    expect(parseAddr('ff')).toBe(255);
    expect(parseAddr('')).toBeUndefined();
    expect(parseAddr(undefined)).toBeUndefined();
    expect(eventTime(1700000000)).toBe(1700000000000);
    expect(eventTime('1700000000')).toBe(1700000000000);
    expect(eventTime('2026-09-29T00:00:00Z')).toBe(Date.parse('2026-09-29T00:00:00Z'));
    expect(Number.isNaN(eventTime('soon'))).toBe(true);
    expect(hex(31)).toBe('0x0000001f');
    expect(ratio(1, 0)).toBeNull();
    expect(ratio(3, 2)).toBe(1);
  });

  it('builds per-build presence rows: instances, absent, unknown', () => {
    const s = parseSummary(rawSummary);
    const p = { ...s.programs[0], builds: [...s.programs[0].builds, { id: 3, slug: 'alpha__linux', platform: 'linux', format: 'elf', functions: 1, bound: 0, real_c: 0 }] };
    const d = parseFunction({
      ok: true, name: 'f', tier: 1, tier_name: 'human', logical_id: 1, instances: [
        { slug: 'alpha__win', platform: 'win', addr: 1, size: 1, confidence: 0.9, method: 'm' },
        { slug: 'alpha__win', platform: 'win', addr: 2, size: 1, confidence: 0.9, method: 'm' },
      ], absent: ['alpha__mac'],
    });
    const rows = presenceRows(p, d);
    expect(rows.map(r => [r.slug, r.state, r.instances.length])).toEqual([
      ['alpha__win', 'present', 2], ['alpha__mac', 'absent', 0], ['alpha__linux', 'unknown', 0],
    ]);
    expect(presenceRows(p, null).every(r => r.state === 'unknown')).toBe(true);
    expect(orderedBuilds(p).map(b => b.slug)).toEqual(['alpha__win', 'alpha__mac', 'alpha__linux']);
    expect(shortSlug('alpha__win', 'alpha')).toBe('win');
    expect(shortSlug('solo', 'x')).toBe('solo');
  });

  it('places activity marks on a window ending now', () => {
    const now = 10_000_000;
    expect(pickWindow([], now)).toBe(30 * 60_000);
    expect(pickWindow([now - 20 * 60_000], now)).toBe(30 * 60_000);
    expect(pickWindow([now - 48 * 3_600_000], now)).toBe(1440 * 60_000);
    expect(markPosition(now, now, 60_000)).toBe(1);
    expect(markPosition(now - 30_000, now, 60_000)).toBeCloseTo(0.5);
    expect(markPosition(now - 120_000, now, 60_000)).toBeNull();
    expect(markPosition(now + 5_000, now, 60_000)).toBe(1); // clock skew clamps to now
    expect(statusTone('failed')).toBe('bad');
    expect(statusTone('done')).toBe('ok');
    expect(statusTone('running')).toBe('run');
  });
});
