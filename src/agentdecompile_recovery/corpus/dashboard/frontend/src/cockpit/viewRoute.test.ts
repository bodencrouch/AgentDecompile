import { describe, expect, it } from 'vitest';
import { chooseView, cockpitHash, readCockpitHash, workstationHref } from './viewRoute';
import { productsFrom } from './ProductShelf';
import { buildTree } from './DropZone';

describe('chooseView', () => {
  it('defaults to the cockpit and honours explicit hashes', () => {
    expect(chooseView('', '')).toBe('cockpit');
    expect(chooseView('#cockpit', '?slug=a')).toBe('cockpit');
    expect(chooseView('#workstation', '')).toBe('workstation');
  });
  it('keeps existing workstation deep links working', () => {
    expect(chooseView('', '?slug=a&addr=0x10&view=Decompiler')).toBe('workstation');
    expect(chooseView('', '?view=decompile')).toBe('workstation');
    expect(chooseView('', '?unrelated=1')).toBe('cockpit');
  });
});

describe('links', () => {
  it('builds a workstation drill-down link', () => {
    expect(workstationHref('P__a', 0x401000)).toBe('?slug=P__a&addr=0x00401000&view=Decompiler#workstation');
    expect(workstationHref('P__a', undefined, 'Graph')).toBe('?slug=P__a&view=Graph#workstation');
  });
  it('round-trips the cockpit location', () => {
    expect(cockpitHash({})).toBe('#cockpit');
    expect(cockpitHash({ program: 'K 1', fn: 12 })).toBe('#cockpit?program=K+1&fn=12');
    expect(readCockpitHash('#cockpit?program=K+1&fn=12')).toEqual({ program: 'K 1', fn: 12 });
    expect(readCockpitHash('#cockpit?program=alpha&fn=-3')).toEqual({ program: 'alpha', fn: undefined });
    expect(readCockpitHash('#workstation?program=alpha')).toEqual({});
  });
});

describe('productsFrom', () => {
  it('computes rings only from real totals and leaves the rest empty', () => {
    const p = productsFrom({ binaries: 1, functions: 200, logical: 100, bound: 50, recovered_logical: 25, named_above_placeholder: 10, named_of: 40 });
    expect(p.find(x => x.id === 'source')?.frac).toBe(0.25);
    expect(p.find(x => x.id === 'signatures')?.frac).toBe(0.25);
    expect(p.find(x => x.id === 'agent')?.frac).toBe(0.25);
    expect(p.filter(x => x.frac === null).length).toBe(p.length - 3);
    expect(productsFrom(undefined).every(x => x.frac === null)).toBe(true);
    expect(productsFrom({ binaries: 0, functions: 0, logical: 0, bound: 0, recovered_logical: 0, named_above_placeholder: 0, named_of: 0 })
      .every(x => x.frac === null)).toBe(true);
  });
});

describe('buildTree', () => {
  it('nests dropped paths with folders first', () => {
    const f = (path: string, size = 1) => ({ path, size, file: {} as File });
    const t = buildTree([f('game/bin/a.exe', 10), f('game/readme.txt', 2), f('game/bin/b.dll', 5), f('solo.elf', 7)]);
    expect(t.count).toBe(4);
    expect(t.bytes).toBe(24);
    expect(t.children.map(c => c.name)).toEqual(['game', 'solo.elf']);
    const game = t.children[0];
    expect(game.children.map(c => c.name)).toEqual(['bin', 'readme.txt']);
    expect(game.children[0].children.map(c => c.name)).toEqual(['a.exe', 'b.dll']);
    expect(game.children[0].bytes).toBe(15);
  });
});
