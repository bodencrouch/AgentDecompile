import { describe, expect, it } from 'vitest';
import {
  MAX_SCALE, MIN_SCALE, cellCenter, cellRect, centerOn, clampView, fitView, gridFor, hitTest, minimapViewport,
  rowsOf, stepIndex, viewFromMinimap, visibleRows, zoomAt, type View,
} from './mapMath';

const grid = { n: 100, cols: 10 };

describe('grid layout', () => {
  it('chooses columns that follow the viewport aspect', () => {
    expect(gridFor(100, 400, 400).cols).toBe(10);
    expect(gridFor(100, 800, 200).cols).toBe(20);
    expect(gridFor(0, 800, 200)).toEqual({ n: 0, cols: 1 });
    expect(rowsOf({ n: 101, cols: 10 })).toBe(11);
  });

  it('fits the whole grid centred inside the padding', () => {
    const v = fitView(grid, 216, 216, 8);
    expect(v.scale).toBe(20);
    expect(v.ox).toBe(8);
    expect(v.oy).toBe(8);
  });
});

describe('zoomAt', () => {
  it('keeps the world point under the cursor fixed', () => {
    const v: View = { scale: 10, ox: 5, oy: 7 };
    const sx = 123, sy = 45;
    const wx = (sx - v.ox) / v.scale, wy = (sy - v.oy) / v.scale;
    const z = zoomAt(v, 2.5, sx, sy);
    expect(z.scale).toBe(25);
    expect((sx - z.ox) / z.scale).toBeCloseTo(wx, 9);
    expect((sy - z.oy) / z.scale).toBeCloseTo(wy, 9);
  });

  it('clamps scale to the allowed range', () => {
    expect(zoomAt({ scale: 10, ox: 0, oy: 0 }, 1e6, 0, 0).scale).toBe(MAX_SCALE);
    expect(zoomAt({ scale: 10, ox: 0, oy: 0 }, 1e-6, 0, 0).scale).toBe(MIN_SCALE);
  });
});

describe('hitTest', () => {
  const v: View = { scale: 20, ox: 0, oy: 0 }; // gap 1px: cells are 19px squares

  it('returns the cell under the point', () => {
    expect(hitTest(v, grid, 5, 5)).toBe(0);
    expect(hitTest(v, grid, 25, 5)).toBe(1);
    expect(hitTest(v, grid, 45, 25)).toBe(12);
  });

  it('snaps to the nearest cell within 6 screen px', () => {
    // Right of the grid (grid is 200px wide; last column drawn to x=199).
    expect(hitTest(v, grid, 203, 5)).toBe(9);
    // Above the grid.
    expect(hitTest(v, grid, 25, -5)).toBe(1);
    // Too far away.
    expect(hitTest(v, grid, 210, 5)).toBe(-1);
    expect(hitTest(v, grid, 25, -8)).toBe(-1);
  });

  it('snaps generously when cells are tiny', () => {
    const tiny: View = { scale: 1, ox: 0, oy: 0 };
    expect(hitTest(tiny, grid, 13, 2.5)).toBe(29); // 3px right of row 2 of the 10px-wide grid
    expect(hitTest(tiny, grid, 20, 2.5)).toBe(-1);
  });

  it('ignores empty slots on the last row', () => {
    const partial = { n: 95, cols: 10 };
    // Slot 97 does not exist and no real cell is within 6px of its centre.
    const i = hitTest(v, partial, 7 * 20 + 10, 9 * 20 + 10);
    expect(i).toBe(-1);
    expect(hitTest(v, partial, 5 * 20 - 3, 9 * 20 + 5)).toBe(94);
  });

  it('agrees with cellRect/cellCenter for every cell', () => {
    const z: View = { scale: 7.3, ox: -13.2, oy: 4.1 };
    for (let i = 0; i < grid.n; i++) {
      const c = cellCenter(z, grid, i);
      expect(hitTest(z, grid, c.x, c.y)).toBe(i);
      const r = cellRect(z, grid, i);
      expect(r.size).toBeGreaterThan(0);
    }
  });
});

describe('view helpers', () => {
  it('computes visible rows for culling', () => {
    expect(visibleRows({ scale: 10, ox: 0, oy: -25 }, grid, 40)).toEqual([2, 7]);
    expect(visibleRows({ scale: 10, ox: 0, oy: 0 }, grid, 1000)).toEqual([0, 9]);
  });

  it('centres a cell and keeps at least the minimum scale', () => {
    const v = centerOn({ scale: 2, ox: 0, oy: 0 }, grid, 55, 400, 300, 20);
    expect(v.scale).toBe(20);
    const c = cellCenter(v, grid, 55);
    // centre is offset by half the 1px gap
    expect(Math.abs(c.x - 200)).toBeLessThan(1);
    expect(Math.abs(c.y - 150)).toBeLessThan(1);
  });

  it('keeps some of the grid on screen', () => {
    const v = clampView({ scale: 10, ox: 5000, oy: -5000 }, grid, 400, 300, 40);
    expect(v.ox).toBeLessThanOrEqual(400 - 40);
    expect(v.oy + rowsOf(grid) * 10).toBeGreaterThanOrEqual(40);
  });

  it('round-trips minimap coordinates', () => {
    const v: View = { scale: 30, ox: -120, oy: -60 };
    const vp = minimapViewport(v, grid, 300, 150, 100, 100);
    const back = viewFromMinimap(v, grid, vp.x + vp.w / 2, vp.y + vp.h / 2, 300, 150, 100, 100);
    expect(back.ox).toBeCloseTo(v.ox, 6);
    expect(back.oy).toBeCloseTo(v.oy, 6);
  });

  it('moves the selection with arrow keys within bounds', () => {
    expect(stepIndex(grid, -1, 'ArrowRight')).toBe(0);
    expect(stepIndex(grid, 5, 'ArrowRight')).toBe(6);
    expect(stepIndex(grid, 5, 'ArrowDown')).toBe(15);
    expect(stepIndex(grid, 5, 'ArrowUp')).toBe(0);
    expect(stepIndex(grid, 99, 'ArrowRight')).toBe(99);
    expect(stepIndex(grid, 50, 'End')).toBe(99);
    expect(stepIndex(grid, 50, 'x')).toBe(50);
  });
});
