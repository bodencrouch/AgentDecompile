import { describe, expect, it } from 'vitest';
import type { ActivityEvent, CellsResponse, Summary } from './api';
import {
  ACTIVITY_CAP, bucketsFor, callersOf, calleesOf, cellCounts, cellName, decodeCells, feedReducer, initialFeed,
  searchCells, type FeedState,
} from './state';

const cellsResponse = (): CellsResponse => ({
  ok: true,
  program_id: 'P',
  ref: 'P__build_a',
  n: 5,
  addr: [0x401000, 0x401010, 0x401020, 0x401030, 0x401040],
  size: [16, 16, 16, 16, 16],
  state: '01210',
  nb: [0, 3, 4, 2, 0],
  tier: '01354',
  logical: [0, 11, 12, 13, 0],
  names: { '1': 'InitThing', '2': 'DrawThing', '3': 'initAudio' },
  edges: [[1, 2], [1, 3], [2, 3], [4, 99]],
});

const summary = (activity: ActivityEvent[], generated = '2026-09-29T00:00:00Z'): Summary => ({
  ok: true,
  generated,
  db: { path: '/x/corpus.sqlite', bytes: 1, mtime: 1 },
  totals: { binaries: 2, functions: 10, logical: 5, bound: 6, recovered_logical: 1, named_above_placeholder: 3, named_of: 5 },
  programs: [{ id: 'P', label: 'P', ref: 'P__build_a', n: 5, builds: [] }],
  tiers: [],
  match_methods: [],
  activity,
});

const ev = (label: string, lane = 'match', status = 'ok'): ActivityEvent => ({ ts: `2026-09-29T00:00:0${label.length}Z`, lane, kind: 'job', label, status });

describe('decodeCells', () => {
  it('decodes the compact strings and builds call adjacency, dropping out-of-range edges', () => {
    const c = decodeCells(cellsResponse());
    expect(Array.from(c.state)).toEqual([0, 1, 2, 1, 0]);
    expect(Array.from(c.tier)).toEqual([0, 1, 3, 5, 4]);
    expect(Array.from(c.nb)).toEqual([0, 3, 4, 2, 0]);
    expect(c.names.get(2)).toBe('DrawThing');
    expect(c.edges).toHaveLength(3);
    expect(calleesOf(c, 1)).toEqual([2, 3]);
    expect(callersOf(c, 3)).toEqual([1, 2]);
    expect(callersOf(c, 0)).toEqual([]);
    expect(cellName(c, 0)).toBe('sub_401000');
    expect(cellCounts(c)).toEqual({ states: [2, 2, 1], named: 3 });
  });

  it('assigns colour buckets and dims cells outside the filter', () => {
    const c = decodeCells(cellsResponse());
    expect(Array.from(bucketsFor(c, { kind: 'all' }))).toEqual([0, 4, 5, 4, 0]);
    expect(Array.from(bucketsFor(c, { kind: 'state', value: 1 }))).toEqual([6, 4, 6, 4, 6]);
    expect(Array.from(bucketsFor(c, { kind: 'tier', value: 4 }))).toEqual([6, 6, 6, 6, 0]);
    expect(Array.from(bucketsFor(c, { kind: 'named' }))).toEqual([6, 4, 5, 4, 6]);
  });

  it('searches names first, then hex addresses', () => {
    const c = decodeCells(cellsResponse());
    expect(searchCells(c, 'init')).toEqual([1, 3]);
    expect(searchCells(c, 'drawthing')).toEqual([2]);
    expect(searchCells(c, '0x401030')).toEqual([3]);
    expect(searchCells(c, '')).toEqual([]);
  });
});

describe('feedReducer', () => {
  it('moves through connection states', () => {
    let s = feedReducer(initialFeed, { type: 'connection', connection: 'offline', error: 'down' });
    expect(s.connection).toBe('offline');
    expect(s.error).toBe('down');
    s = feedReducer(s, { type: 'hello', hello: { db: 'x', programs: ['P'] } });
    expect(s.connection).toBe('live');
    expect(s.error).toBeUndefined();
    expect(feedReducer(s, { type: 'connection', connection: 'live' })).toBe(s);
  });

  it('treats the first summary as history and later unseen events as live arrivals', () => {
    let s = feedReducer(initialFeed, { type: 'summary', summary: summary([ev('bb'), ev('a')]), now: 1000 });
    expect(s.activity.map(a => [a.label, a.live])).toEqual([['bb', false], ['a', false]]);
    s = feedReducer(s, { type: 'summary', summary: summary([ev('ccc', 'weird'), ev('bb'), ev('a')], 'later'), now: 2000 });
    expect(s.activity[0].label).toBe('ccc');
    expect(s.activity[0].live).toBe(true);
    expect(s.activity[0].lane).toBe('other');
    expect(s.activity[0].arrivedAt).toBe(2000);
    expect(s.activity).toHaveLength(3);
    expect(s.summary?.generated).toBe('later');
  });

  it('dedupes stream activity against polled activity and caps the list', () => {
    let s: FeedState = feedReducer(initialFeed, { type: 'activity', event: ev('x'), now: 5 });
    expect(s.activity[0].live).toBe(true);
    const same = feedReducer(s, { type: 'activity', event: ev('x'), now: 6 });
    expect(same).toBe(s);
    for (let k = 0; k < ACTIVITY_CAP + 20; k++) s = feedReducer(s, { type: 'activity', event: { ...ev('y'), ts: k }, now: k });
    expect(s.activity).toHaveLength(ACTIVITY_CAP);
    expect(s.activity[0].ts).toBe(ACTIVITY_CAP + 19);
  });

  it('applies cell diffs to the loaded program and flashes state changes', () => {
    let s = feedReducer(initialFeed, { type: 'cells', cells: cellsResponse(), now: 0 });
    const before = s.cells.P;
    s = feedReducer(s, { type: 'diff', diff: { program_id: 'P', changes: [[0, 2, 5, 1], [3, 1, 3, 5], [42, 2, 1, 1]] }, now: 100 });
    const after = s.cells.P;
    expect(after).not.toBe(before);
    expect(Array.from(before.state)).toEqual([0, 1, 2, 1, 0]); // previous snapshot untouched
    expect(Array.from(after.state)).toEqual([2, 1, 2, 1, 0]);
    expect(after.nb[0]).toBe(5);
    expect(after.nb[3]).toBe(3);
    expect(after.flashes.has(0)).toBe(true);
    expect(after.flashes.has(3)).toBe(false); // nb-only change: no flash
    expect(after.version).toBe(before.version + 1);
  });

  it('ignores diffs for programs that are not loaded and no-op diffs', () => {
    const s = feedReducer(initialFeed, { type: 'cells', cells: cellsResponse(), now: 0 });
    expect(feedReducer(s, { type: 'diff', diff: { program_id: 'Q', changes: [[0, 2, 1, 1]] }, now: 1 })).toBe(s);
    expect(feedReducer(s, { type: 'diff', diff: { program_id: 'P', changes: [[1, 1, 3, 1]] }, now: 1 })).toBe(s);
  });
});
