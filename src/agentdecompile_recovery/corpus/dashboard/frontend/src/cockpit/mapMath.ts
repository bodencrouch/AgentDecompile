// Geometry for the program map: cells laid out in address order on a grid of
// `cols` columns. World units are cells; screen = world * scale + offset (CSS px).

export type View = { scale: number; ox: number; oy: number };
export type Grid = { n: number; cols: number };

export const MIN_SCALE = 0.35;
export const MAX_SCALE = 160;
export const SNAP_PX = 6;

export const gapFor = (scale: number) => (scale >= 6 ? 1 : scale >= 3.5 ? 0.5 : 0);

export function gridFor(n: number, width: number, height: number): Grid {
  if (n <= 0 || width <= 0 || height <= 0) return { n: Math.max(0, n), cols: 1 };
  const cols = Math.max(1, Math.min(n, Math.ceil(Math.sqrt((n * width) / height))));
  return { n, cols };
}

export const rowsOf = (g: Grid) => Math.max(1, Math.ceil(g.n / g.cols));

export function fitView(g: Grid, width: number, height: number, pad = 8): View {
  const rows = rowsOf(g);
  const scale = clampScale(Math.min((width - pad * 2) / g.cols, (height - pad * 2) / rows));
  return { scale, ox: (width - g.cols * scale) / 2, oy: (height - rows * scale) / 2 };
}

export const clampScale = (s: number) => Math.max(MIN_SCALE, Math.min(MAX_SCALE, Number.isFinite(s) && s > 0 ? s : 1));

/** Zoom by `factor` keeping the world point under (sx, sy) fixed on screen. */
export function zoomAt(v: View, factor: number, sx: number, sy: number): View {
  const scale = clampScale(v.scale * factor);
  const k = scale / v.scale;
  return { scale, ox: sx - (sx - v.ox) * k, oy: sy - (sy - v.oy) * k };
}

export const panBy = (v: View, dx: number, dy: number): View => ({ ...v, ox: v.ox + dx, oy: v.oy + dy });

/** Keep at least `margin` px of the grid inside the viewport. */
export function clampView(v: View, g: Grid, width: number, height: number, margin = 40): View {
  const w = g.cols * v.scale, h = rowsOf(g) * v.scale;
  const m = Math.min(margin, w / 2, h / 2);
  const ox = Math.min(width - m, Math.max(m - w, v.ox));
  const oy = Math.min(height - m, Math.max(m - h, v.oy));
  return ox === v.ox && oy === v.oy ? v : { ...v, ox, oy };
}

export const cellCol = (g: Grid, i: number) => i % g.cols;
export const cellRow = (g: Grid, i: number) => Math.floor(i / g.cols);

export function cellRect(v: View, g: Grid, i: number) {
  const gap = gapFor(v.scale);
  const size = Math.max(0.5, v.scale - gap);
  return { x: v.ox + cellCol(g, i) * v.scale, y: v.oy + cellRow(g, i) * v.scale, size };
}

export function cellCenter(v: View, g: Grid, i: number) {
  const r = cellRect(v, g, i);
  return { x: r.x + r.size / 2, y: r.y + r.size / 2 };
}

/**
 * Cell under a screen point, or the nearest cell whose drawn square lies within
 * `snap` screen px. Returns -1 when nothing is close enough.
 */
export function hitTest(v: View, g: Grid, sx: number, sy: number, snap = SNAP_PX): number {
  if (g.n <= 0) return -1;
  const fx = (sx - v.ox) / v.scale, fy = (sy - v.oy) / v.scale;
  const reach = Math.min(8, Math.ceil(snap / v.scale) + 1);
  // Clamp the search centre to the grid so points just outside still find edge cells.
  const c0 = Math.max(0, Math.min(g.cols - 1, Math.floor(fx)));
  const r0 = Math.max(0, Math.min(rowsOf(g) - 1, Math.floor(fy)));
  const size = Math.max(0.5, v.scale - gapFor(v.scale));
  let best = -1, bestD = Infinity;
  for (let r = r0 - reach; r <= r0 + reach; r++) {
    if (r < 0) continue;
    for (let c = c0 - reach; c <= c0 + reach; c++) {
      if (c < 0 || c >= g.cols) continue;
      const i = r * g.cols + c;
      if (i >= g.n) continue;
      const x = v.ox + c * v.scale, y = v.oy + r * v.scale;
      const dx = sx < x ? x - sx : sx > x + size ? sx - (x + size) : 0;
      const dy = sy < y ? y - sy : sy > y + size ? sy - (y + size) : 0;
      const d = Math.hypot(dx, dy);
      if (d < bestD || (d === bestD && i < best)) {
        bestD = d;
        best = i;
      }
    }
  }
  return bestD <= snap ? best : -1;
}

/** Inclusive index range of rows visible in the viewport (for culling). */
export function visibleRows(v: View, g: Grid, height: number): [number, number] {
  const rows = rowsOf(g);
  const r0 = Math.max(0, Math.floor(-v.oy / v.scale));
  const r1 = Math.min(rows - 1, Math.ceil((height - v.oy) / v.scale));
  return [r0, r1];
}

/** View that centres cell i at `scale` (defaults to at least `minScale`). */
export function centerOn(v: View, g: Grid, i: number, width: number, height: number, minScale = 18): View {
  const scale = clampScale(Math.max(v.scale, minScale));
  return {
    scale,
    ox: width / 2 - (cellCol(g, i) + 0.5) * scale,
    oy: height / 2 - (cellRow(g, i) + 0.5) * scale,
  };
}

/** Is cell i fully visible (with margin) in the viewport? */
export function isCellVisible(v: View, g: Grid, i: number, width: number, height: number, margin = 12) {
  const r = cellRect(v, g, i);
  return r.x >= margin && r.y >= margin && r.x + r.size <= width - margin && r.y + r.size <= height - margin;
}

/** Interpolate views for fly-to (zoom in log space so it feels even). */
export function lerpView(a: View, b: View, t: number): View {
  const e = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
  const scale = Math.exp(Math.log(a.scale) + (Math.log(b.scale) - Math.log(a.scale)) * e);
  // Interpolate the world point at the viewport centre-independent offset.
  return { scale, ox: a.ox + (b.ox - a.ox) * e, oy: a.oy + (b.oy - a.oy) * e };
}

/** Minimap: fit the whole grid into (mw, mh); returns scale and offsets. */
export function minimapFit(g: Grid, mw: number, mh: number) {
  const rows = rowsOf(g);
  const s = Math.min(mw / g.cols, mh / rows);
  return { s, ox: (mw - g.cols * s) / 2, oy: (mh - rows * s) / 2 };
}

/** Viewport rectangle (in minimap px) for the main view. */
export function minimapViewport(v: View, g: Grid, width: number, height: number, mw: number, mh: number) {
  const m = minimapFit(g, mw, mh);
  const wx0 = -v.ox / v.scale, wy0 = -v.oy / v.scale;
  return { x: m.ox + wx0 * m.s, y: m.oy + wy0 * m.s, w: (width / v.scale) * m.s, h: (height / v.scale) * m.s };
}

/** Centre the main view on the world point under minimap px (mx, my). */
export function viewFromMinimap(v: View, g: Grid, mx: number, my: number, width: number, height: number, mw: number, mh: number): View {
  const m = minimapFit(g, mw, mh);
  const wx = (mx - m.ox) / m.s, wy = (my - m.oy) / m.s;
  return { ...v, ox: width / 2 - wx * v.scale, oy: height / 2 - wy * v.scale };
}

/** Arrow-key movement in address order across the grid. */
export function stepIndex(g: Grid, i: number, key: string, page = 10): number {
  if (g.n <= 0) return -1;
  if (i < 0) return 0;
  let next = i;
  switch (key) {
    case 'ArrowLeft': next = i - 1; break;
    case 'ArrowRight': next = i + 1; break;
    case 'ArrowUp': next = i - g.cols; break;
    case 'ArrowDown': next = i + g.cols; break;
    case 'PageUp': next = i - g.cols * page; break;
    case 'PageDown': next = i + g.cols * page; break;
    case 'Home': next = 0; break;
    case 'End': next = g.n - 1; break;
    default: return i;
  }
  return Math.max(0, Math.min(g.n - 1, next));
}
