import { describe, expect, it } from 'vitest';
import type { ActivityEvent, CellsResponse, Summary } from './api';
import {
  ACTIVITY_CAP, NO_FILTER, QUEUE_CAP, applyDiff, callersOf, calleesOf, cellCounts, cellName, colorKey, decodeCells, diffCells, feedReducer,
  filterActive, indexOfAddr, initialFeed, matchesFilter, maxNb, searchCells, toggleBit, type FeedState,
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
    const counts = cellCounts(c);
    expect(counts.states).toEqual([2, 2, 1]);
    expect(counts.tiers.slice(0, 6)).toEqual([1, 1, 0, 1, 1, 1]);
    expect(counts.named).toBe(3);
  });

  it('filters by combined state and tier bitmasks', () => {
    const c = decodeCells(cellsResponse());
    const keep = (f: typeof NO_FILTER) => [0, 1, 2, 3, 4].filter(i => matchesFilter(c, i, f));
    expect(filterActive(NO_FILTER)).toBe(false);
    expect(keep(NO_FILTER)).toEqual([0, 1, 2, 3, 4]);
    const bound = { states: toggleBit(0, 1), tiers: 0 };
    expect(keep(bound)).toEqual([1, 3]);
    expect(keep({ states: toggleBit(bound.states, 2), tiers: 0 })).toEqual([1, 2, 3]);
    expect(keep({ states: bound.states, tiers: toggleBit(0, 5) })).toEqual([3]);
    expect(toggleBit(toggleBit(0, 2), 2)).toBe(0);
  });

  it('computes colour keys per mode', () => {
    const c = decodeCells(cellsResponse());
    const nbMax = maxNb(c);
    expect(nbMax).toBe(4);
    expect([0, 1, 2, 3, 4].map(i => colorKey(c, i, 'state', nbMax))).toEqual([0, 1, 2, 1, 0]);
    expect([0, 1, 2, 3, 4].map(i => colorKey(c, i, 'tier', nbMax))).toEqual([0, 1, 3, 5, 4]);
    const builds = [0, 1, 2, 3, 4].map(i => colorKey(c, i, 'builds', nbMax));
    expect(builds[0]).toBe(0);
    expect(builds[4]).toBe(0);
    expect(builds[2]).toBe(7); // the most-shared function gets the brightest key
    expect(builds[3]).toBeLessThan(builds[1]);
  });

  it('finds the function containing an address', () => {
    const c = decodeCells(cellsResponse());
    expect(indexOfAddr(c, 0x401000)).toBe(0);
    expect(indexOfAddr(c, 0x40101f)).toBe(1);
    expect(indexOfAddr(c, 0x400fff)).toBe(-1);
    expect(indexOfAddr(c, 0x401050)).toBe(-1);
  });

  it('searches names first, then hex addresses', () => {
    const c = decodeCells(cellsResponse());
    expect(searchCells(c, 'init')).toEqual([1, 3]);
    expect(searchCells(c, 'drawthing')).toEqual([2]);
    expect(searchCells(c, '0x401030')).toEqual([3]);
    expect(searchCells(c, '0x401035')[0]).toBe(3); // inside a function
    expect(searchCells(c, '')).toEqual([]);
  });
});

describe('feedReducer', () => {
  it('records hello and errors without touching data', () => {
    let s = feedReducer(initialFeed, { type: 'error', error: 'down' });
    expect(s.error).toBe('down');
    expect(feedReducer(s, { type: 'error', error: 'down' })).toBe(s);
    s = feedReducer(s, { type: 'hello', hello: { db: 'x', programs: ['P'] } });
    expect(s.hello?.programs).toEqual(['P']);
    expect(s.error).toBeUndefined();
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
    s = feedReducer(s, { type: 'diff', diff: { program_id: 'P', changes: [[0, 2, 5, 1], [3, 1, 3, 5], [42, 2, 1, 1], [-1, 2, 1, 1]] }, now: 100 });
    const after = s.cells.P;
    expect(after).not.toBe(before);
    expect(Array.from(before.state)).toEqual([0, 1, 2, 1, 0]); // previous snapshot untouched
    expect(Array.from(after.state)).toEqual([2, 1, 2, 1, 0]);
    expect(after.nb[0]).toBe(5);
    expect(after.nb[3]).toBe(3);
    expect(after.flashes.has(0)).toBe(true);
    expect(after.flashes.has(3)).toBe(false); // nb-only change: no flash
    expect(after.version).toBe(before.version + 1);
    expect(after.changed).toEqual([0, 3]);
    expect(s.applied).toBe(2);
  });

  it('applies a refetch with the same layout as a diff, and replaces a new layout', () => {
    let s = feedReducer(initialFeed, { type: 'cells', cells: cellsResponse(), now: 0 });
    const next = { ...cellsResponse(), state: '01211', tier: '01334' };
    s = feedReducer(s, { type: 'cells', cells: next, now: 50 });
    expect(Array.from(s.cells.P.state)).toEqual([0, 1, 2, 1, 1]);
    expect(s.cells.P.changed).toEqual([3, 4]);
    expect(s.cells.P.flashes.has(4)).toBe(true);
    const moved = { ...cellsResponse(), n: 2, addr: [1, 2], size: [1, 1], state: '22', nb: [1, 1], tier: '11', logical: [1, 2], names: {}, edges: [] as [number, number][] };
    s = feedReducer(s, { type: 'cells', cells: moved, now: 60 });
    expect(s.cells.P.n).toBe(2);
    expect(s.cells.P.flashes.size).toBe(0);
  });

  it('diffCells and applyDiff round-trip', () => {
    const a = decodeCells(cellsResponse());
    const b = decodeCells({ ...cellsResponse(), state: '22222', nb: [9, 9, 9, 9, 9] });
    const changes = diffCells(a, b);
    expect(changes).toHaveLength(5);
    const c = applyDiff(a, changes, 10);
    expect(Array.from(c.state)).toEqual([2, 2, 2, 2, 2]);
    expect(diffCells(c, b)).toEqual([]);
    expect(applyDiff(c, changes, 11)).toBe(c); // already applied: no-op
  });

  it('queues live data while paused and applies it in order on resume', () => {
    let s = feedReducer(initialFeed, { type: 'cells', cells: cellsResponse(), now: 0 });
    s = feedReducer(s, { type: 'summary', summary: summary([ev('a')]), now: 0 });
    s = feedReducer(s, { type: 'pause', now: 1 });
    expect(s.paused).toBe(true);
    const held = s;
    s = feedReducer(s, { type: 'diff', diff: { program_id: 'P', changes: [[0, 1, 1, 1]] }, now: 2 });
    s = feedReducer(s, { type: 'diff', diff: { program_id: 'P', changes: [[0, 2, 1, 1]] }, now: 3 });
    s = feedReducer(s, { type: 'activity', event: ev('bb'), now: 4 });
    expect(s.cells).toBe(held.cells);
    expect(s.activity).toBe(held.activity);
    expect(s.queue).toHaveLength(3);
    s = feedReducer(s, { type: 'resume', now: 10 });
    expect(s.paused).toBe(false);
    expect(s.queue).toHaveLength(0);
    expect(s.cells.P.state[0]).toBe(2);
    expect(s.cells.P.flashes.get(0)).toBe(10);
    expect(s.activity[0].label).toBe('bb');
    expect(feedReducer(s, { type: 'resume', now: 11 })).toBe(s);
  });

  it('still loads a program map and a first summary while paused, and caps the queue', () => {
    let s = feedReducer(initialFeed, { type: 'pause', now: 0 });
    s = feedReducer(s, { type: 'summary', summary: summary([]), now: 1 });
    s = feedReducer(s, { type: 'cells', cells: cellsResponse(), now: 1 });
    expect(s.summary).toBeDefined();
    expect(s.cells.P).toBeDefined();
    for (let k = 0; k < QUEUE_CAP + 5; k++) s = feedReducer(s, { type: 'activity', event: { ...ev('z'), ts: k }, now: k });
    expect(s.queue).toHaveLength(QUEUE_CAP);
  });

  it('ignores diffs for programs that are not loaded and no-op diffs', () => {
    const s = feedReducer(initialFeed, { type: 'cells', cells: cellsResponse(), now: 0 });
    expect(feedReducer(s, { type: 'diff', diff: { program_id: 'Q', changes: [[0, 2, 1, 1]] }, now: 1 })).toBe(s);
    expect(feedReducer(s, { type: 'diff', diff: { program_id: 'P', changes: [[1, 1, 3, 1]] }, now: 1 })).toBe(s);
  });
});
