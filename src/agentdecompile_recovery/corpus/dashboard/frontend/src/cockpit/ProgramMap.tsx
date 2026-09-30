// The program map: every function of the reference build as one cell, in address order.
// Two canvases: a view layer drawn from an offscreen base bitmap (one block per cell,
// repainted incrementally from live diffs) and an overlay redrawn per frame for hover,
// selection, real call edges, search hits and live-change highlights.
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from 'react';
import { STATE_LABELS, STATE_SHORT, TIER_LABELS, fmt, hex } from './api';
import {
  FLASH_MS, callersOf, calleesOf, cellCounts, cellName, colorKey, filterActive, hasBit, matchesFilter, maxNb, toggleBit,
  NO_FILTER, type ColorBy, type MapFilter, type ProgramCells,
} from './state';
import {
  baseCellPx, cellCenter, cellRect, centerOn, clampView, fitView, gridFor, hitTest, isCellVisible, lerpView, minimapFit,
  minimapViewport, mixRgb, packRgb, paintBaseCell, panBy, parseColor, rowsOf, stepIndex, viewFromMinimap, visibleRows, zoomAt,
  type Grid, type View,
} from './mapMath';

export type FlyRequest = { index: number; nonce: number; scale?: number };

type Props = {
  cells: ProgramCells;
  buildCount: number;
  binaries: number;
  selected: number;
  hits: number[];
  filter: MapFilter;
  colorBy: ColorBy;
  tierNames: string[];
  fly: FlyRequest | null;
  reducedMotion: boolean;
  onSelect: (index: number) => void;
  onFilter: (f: MapFilter) => void;
  onColorBy: (c: ColorBy) => void;
};

const BITMAP_BELOW = 10; // px per cell: below this the view layer blits the base bitmap
const LABEL_SCALE = 30;
const MINI_MAX_W = 176, MINI_MAX_H = 104;
const EDGE_CAP = 160;
const GROW_MS = 420;

type Rgb = [number, number, number];
type Palette = {
  state: Rgb[]; tier: Rgb[]; builds: Rgb[];
  well: Rgb; ink: string; accent: string; callee: string; caller: string; flash: string; hit: string; mono: string;
};

function readPalette(el: Element): Palette {
  const cs = getComputedStyle(el);
  const v = (name: string, fallback: string) => cs.getPropertyValue(name).trim() || fallback;
  const c = (name: string, fallback: string) => parseColor(v(name, fallback), parseColor(fallback));
  const state = [c('--c-unbound', '#2e333d'), c('--c-bound', '#3d64a3'), c('--c-rec', '#7fd6a4')];
  const tier = ['--t0', '--t1', '--t2', '--t3', '--t4', '--t5'].map((t, k) => c(t, ['#3a404c', '#8cbaff', '#c9a4f0', '#67d3d0', '#4f6f9f', '#ef968b'][k]));
  while (tier.length < 10) tier.push(c('--muted', '#98a0ad'));
  const lo = c('--c-builds-lo', '#232a38'), hi = c('--c-builds-hi', '#9cc6ff');
  const builds = Array.from({ length: 9 }, (_, k) => (k === 0 ? state[0] : mixRgb(lo, hi, k / 8)));
  return {
    state, tier, builds, well: c('--well', '#0f1115'),
    ink: v('--ink-strong', '#f2f4f7'), accent: v('--accent', '#8cbaff'), callee: v('--f-identity', '#8cbaff'),
    caller: v('--f-unify', '#f0c060'), flash: v('--f-source', '#7fd6a4'), hit: v('--f-unify', '#f0c060'),
    mono: v('--font-mono', 'monospace'),
  };
}

const colorsFor = (pal: Palette, by: ColorBy) => (by === 'tier' ? pal.tier : by === 'builds' ? pal.builds : pal.state);
const cssRgb = (c: readonly number[]) => `rgb(${c[0]},${c[1]},${c[2]})`;

export function ProgramMap(props: Props) {
  const { cells, buildCount, binaries, selected, hits, filter, colorBy, tierNames, fly, reducedMotion, onSelect } = props;
  const wrapRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<HTMLCanvasElement>(null);
  const fxRef = useRef<HTMLCanvasElement>(null);
  const miniRef = useRef<HTMLCanvasElement>(null);
  const size = useRef({ w: 0, h: 0, dpr: 1 });
  const grid = useRef<Grid>({ n: 0, cols: 1 });
  const layoutKey = useRef('');
  const view = useRef<View>({ scale: 1, ox: 0, oy: 0 });
  const atFit = useRef(true);
  const anim = useRef<{ from: View; to: View; start: number; ms: number } | null>(null);
  const pal = useRef<Palette | null>(null);
  const base = useRef<{ canvas: HTMLCanvasElement; img: ImageData; u32: Uint32Array; cp: number } | null>(null);
  const baseState = useRef({ key: '', version: -1, nbMax: 0 });
  const dirtyView = useRef(true);
  const raf = useRef(0);
  const hoverRef = useRef(-1);
  const focusStart = useRef({ index: -1, t: 0 });
  const [hover, setHover] = useState<{ index: number; x: number; y: number } | null>(null);
  const [zoomLabel, setZoomLabel] = useState(1);
  const [mini, setMini] = useState({ w: MINI_MAX_W, h: 60 });

  // Latest props for the frame loop.
  const live = useRef({ cells, selected, hits, filter, colorBy, reducedMotion });
  live.current = { cells, selected, hits, filter, colorBy, reducedMotion };

  const palette = () => (pal.current ||= readPalette(wrapRef.current || document.body));

  /* ---------- base bitmap ---------- */
  const rebuildBase = useCallback(() => {
    const { cells: c, filter: f, colorBy: by } = live.current;
    const g = grid.current;
    if (!g.n) return;
    const cp = baseCellPx(g);
    const w = g.cols * cp, h = rowsOf(g) * cp;
    let b = base.current;
    if (!b || b.canvas.width !== w || b.canvas.height !== h) {
      const canvas = b?.canvas || document.createElement('canvas');
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      const img = ctx.createImageData(w, h);
      b = base.current = { canvas, img, u32: new Uint32Array(img.data.buffer), cp };
    }
    b.u32.fill(0);
    const p = palette();
    const colors = colorsFor(p, by);
    const packed = colors.map(x => packRgb(x));
    const dim = colors.map(x => packRgb(mixRgb(x, p.well, 0.78)));
    const nbMax = maxNb(c);
    const filt = filterActive(f);
    for (let i = 0; i < c.n; i++) {
      const k = colorKey(c, i, by, nbMax);
      paintBaseCell(b.u32, w, g, i, cp, filt && !matchesFilter(c, i, f) ? dim[k] : packed[k]);
    }
    b.canvas.getContext('2d')!.putImageData(b.img, 0, 0);
    baseState.current = { key: `${layoutKey.current}|${by}|${f.states}|${f.tiers}`, version: c.version, nbMax };
    dirtyView.current = true;
  }, []);

  /** Repaint only the cells a live diff changed. */
  const patchBase = useCallback((indices: number[]) => {
    const b = base.current;
    const { cells: c, filter: f, colorBy: by } = live.current;
    if (!b || !indices.length) return;
    const nbMax = maxNb(c);
    if (by === 'builds' && nbMax !== baseState.current.nbMax) return rebuildBase();
    const p = palette();
    const colors = colorsFor(p, by);
    const filt = filterActive(f);
    const g = grid.current;
    for (const i of indices) {
      if (i < 0 || i >= g.n) continue;
      const rgb = colors[colorKey(c, i, by, nbMax)];
      paintBaseCell(b.u32, b.canvas.width, g, i, b.cp, packRgb(filt && !matchesFilter(c, i, f) ? mixRgb(rgb, p.well, 0.78) : rgb));
    }
    b.canvas.getContext('2d')!.putImageData(b.img, 0, 0);
    baseState.current.version = c.version;
    dirtyView.current = true;
  }, [rebuildBase]);

  /* ---------- view layer ---------- */
  const drawView = useCallback(() => {
    const canvas = viewRef.current, ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;
    const { w, h, dpr } = size.current;
    const { cells: c, filter: f, colorBy: by } = live.current;
    const v = view.current, g = grid.current, p = palette();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = cssRgb(p.well);
    ctx.fillRect(0, 0, w, h);
    const b = base.current;
    if (!g.n || !b) return;
    if (v.scale < BITMAP_BELOW) {
      ctx.imageSmoothingEnabled = v.scale < b.cp;
      ctx.imageSmoothingQuality = 'medium';
      ctx.drawImage(b.canvas, v.ox, v.oy, g.cols * v.scale, rowsOf(g) * v.scale);
    } else {
      const colors = colorsFor(p, by).map(cssRgb);
      const dimmed = colorsFor(p, by).map(x => cssRgb(mixRgb(x, p.well, 0.78)));
      const filt = filterActive(f);
      const nbMax = baseState.current.nbMax;
      const [r0, r1] = visibleRows(v, g, h);
      const c0 = Math.max(0, Math.floor(-v.ox / v.scale)), c1 = Math.min(g.cols - 1, Math.floor((w - v.ox) / v.scale));
      const gap = v.scale >= 16 ? 2 : 1, sz = v.scale - gap;
      for (let r = r0; r <= r1; r++) {
        for (let col = c0; col <= c1; col++) {
          const i = r * g.cols + col;
          if (i >= g.n) break;
          const k = colorKey(c, i, by, nbMax);
          ctx.fillStyle = filt && !matchesFilter(c, i, f) ? dimmed[k] : colors[k];
          ctx.fillRect(v.ox + col * v.scale, v.oy + r * v.scale, sz, sz);
        }
      }
      // Named functions carry a corner notch.
      ctx.fillStyle = p.ink;
      const notch = Math.min(7, v.scale * 0.22);
      for (let r = r0; r <= r1; r++) {
        for (let col = c0; col <= c1; col++) {
          const i = r * g.cols + col;
          if (i >= g.n) break;
          if (!c.names.has(i) || (filt && !matchesFilter(c, i, f))) continue;
          const x = v.ox + col * v.scale + sz, y = v.oy + r * v.scale;
          ctx.beginPath();
          ctx.moveTo(x - notch, y);
          ctx.lineTo(x, y);
          ctx.lineTo(x, y + notch);
          ctx.closePath();
          ctx.fill();
        }
      }
      if (v.scale >= LABEL_SCALE) {
        const fontPx = Math.max(9, Math.min(13, Math.round(v.scale * 0.2)));
        ctx.font = `${fontPx}px ${p.mono}`;
        ctx.textBaseline = 'top';
        const maxLines = v.scale >= 56 ? 3 : v.scale >= 42 ? 2 : 1;
        const maxW = sz - 6;
        const fit = (t: string) => {
          if (ctx.measureText(t).width <= maxW) return t;
          let s = t;
          while (s.length > 1 && ctx.measureText(`${s}…`).width > maxW) s = s.slice(0, -1);
          return `${s}…`;
        };
        for (let r = r0; r <= r1; r++) {
          for (let col = c0; col <= c1; col++) {
            const i = r * g.cols + col;
            if (i >= g.n) break;
            const x = v.ox + col * v.scale + 3, y = v.oy + r * v.scale + 3;
            const dim = filt && !matchesFilter(c, i, f);
            const light = !dim && by === 'state' && c.state[i] === 2;
            ctx.fillStyle = dim ? 'rgba(152,160,173,.35)' : light ? '#0b0d10' : '#e8ebf0';
            const name = c.names.get(i);
            if (name) {
              // Wrap by characters into up to maxLines lines.
              const per = Math.max(3, Math.floor(maxW / (fontPx * 0.62)));
              let rest = name;
              for (let li = 0; li < maxLines && rest; li++) {
                const last = li === maxLines - 1;
                const line = last ? fit(rest) : rest.slice(0, per);
                ctx.fillText(line, x, y + li * (fontPx + 2));
                rest = last ? '' : rest.slice(per);
              }
            }
            if (v.scale >= 46 || !name) {
              ctx.fillStyle = dim ? 'rgba(159,217,232,.3)' : light ? '#16323a' : 'rgba(159,217,232,.85)';
              ctx.fillText(fit(hex(c.addr[i]).replace(/^0x0*/, '') || '0'), x, name ? v.oy + (r + 1) * v.scale - fontPx - gap - 4 : y);
            }
          }
        }
      }
    }
    dirtyView.current = false;
  }, []);

  const drawMini = useCallback(() => {
    const m = miniRef.current, ctx = m?.getContext('2d'), b = base.current;
    if (!m || !ctx) return;
    const dpr = size.current.dpr, g = grid.current;
    const mw = m.width / dpr, mh = m.height / dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, mw, mh);
    if (!b || !g.n) return;
    const fit = minimapFit(g, mw, mh);
    ctx.imageSmoothingEnabled = true;
    ctx.drawImage(b.canvas, fit.ox, fit.oy, g.cols * fit.s, rowsOf(g) * fit.s);
    const vp = minimapViewport(view.current, g, size.current.w, size.current.h, mw, mh);
    const x = Math.max(0.75, vp.x), y = Math.max(0.75, vp.y);
    const r = Math.min(mw - 0.75, vp.x + vp.w), bt = Math.min(mh - 0.75, vp.y + vp.h);
    ctx.strokeStyle = palette().hit;
    ctx.lineWidth = 1.5;
    if (r > x && bt > y) ctx.strokeRect(x, y, Math.max(3, r - x), Math.max(3, bt - y));
    const sel = live.current.selected;
    if (sel >= 0 && sel < g.n) {
      ctx.fillStyle = palette().accent;
      ctx.fillRect(fit.ox + (sel % g.cols) * fit.s - 1.5, fit.oy + Math.floor(sel / g.cols) * fit.s - 1.5, 3, 3);
    }
  }, []);

  /* ---------- overlay ---------- */
  const drawFx = useCallback((now: number): boolean => {
    const canvas = fxRef.current, ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return false;
    const { w, h, dpr } = size.current;
    const { cells: c, selected: sel, hits: hs, reducedMotion: rm } = live.current;
    const v = view.current, g = grid.current, p = palette();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    if (!g.n) return false;
    let busy = false;
    const s = v.scale, rs = Math.max(s, 5), off = (rs - s) / 2;
    const at = (i: number) => ({ x: v.ox + (i % g.cols) * s - off, y: v.oy + Math.floor(i / g.cols) * s - off });
    const onScreen = (x: number, y: number) => x > -40 && y > -40 && x < w + 40 && y < h + 40;

    // Live changes: a ring that expands and fades.
    if (c.flashes.size) {
      const t = Date.now();
      ctx.lineWidth = 1.5;
      for (const [i, t0] of c.flashes) {
        const age = (t - t0) / FLASH_MS;
        if (age < 0 || age >= 1 || i >= g.n) continue;
        busy = true;
        const { x, y } = at(i);
        if (!onScreen(x, y)) continue;
        const grow = rm ? 2 : 2 + age * 10;
        ctx.strokeStyle = p.flash;
        ctx.globalAlpha = rm ? 0.9 : 1 - age;
        ctx.strokeRect(x - grow, y - grow, rs + 2 * grow, rs + 2 * grow);
      }
      ctx.globalAlpha = 1;
    }
    // Search hits.
    if (hs.length) {
      ctx.strokeStyle = p.hit;
      ctx.lineWidth = 1.2;
      for (const i of hs) {
        if (i >= g.n) continue;
        const { x, y } = at(i);
        if (onScreen(x, y)) ctx.strokeRect(x - 2, y - 2, rs + 4, rs + 4);
      }
    }
    // Real call edges of the focused function (selection, else hover).
    const focus = sel >= 0 ? sel : hoverRef.current;
    if (focus !== focusStart.current.index) focusStart.current = { index: focus, t: now };
    if (focus >= 0 && focus < g.n) {
      const grow = rm ? 1 : Math.min(1, (now - focusStart.current.t) / GROW_MS);
      if (grow < 1) busy = true;
      const outs = calleesOf(c, focus).slice(0, EDGE_CAP), ins = callersOf(c, focus).slice(0, EDGE_CAP);
      const centre = (i: number) => cellCenter(v, g, i);
      const arc = (a: number, b: number) => {
        const A = centre(a), B = centre(b);
        const mx = (A.x + B.x) / 2 + (B.y - A.y) * 0.18, my = (A.y + B.y) / 2 - Math.abs(B.x - A.x) * 0.18 - 8;
        ctx.beginPath();
        ctx.moveTo(A.x, A.y);
        if (grow >= 1) ctx.quadraticCurveTo(mx, my, B.x, B.y);
        else {
          const N = 16, L = Math.floor(N * grow);
          for (let q = 1; q <= L; q++) {
            const u = q / N, k0 = (1 - u) * (1 - u), k1 = 2 * (1 - u) * u, k2 = u * u;
            ctx.lineTo(k0 * A.x + k1 * mx + k2 * B.x, k0 * A.y + k1 * my + k2 * B.y);
          }
        }
        ctx.stroke();
      };
      const dash = rm ? 0 : -(now / 40) % 12;
      if (!rm && sel >= 0) busy = true;
      ctx.lineWidth = 1.4;
      ctx.setLineDash([6, 6]);
      ctx.lineDashOffset = dash;
      ctx.strokeStyle = p.callee;
      ctx.globalAlpha = 0.85;
      for (const j of outs) arc(focus, j);
      ctx.lineDashOffset = -dash;
      ctx.strokeStyle = p.caller;
      for (const j of ins) arc(j, focus);
      ctx.setLineDash([]);
      ctx.globalAlpha = 1;
      if (grow >= 1) {
        ctx.lineWidth = 1.2;
        ctx.strokeStyle = p.callee;
        for (const j of outs) { const { x, y } = at(j); if (onScreen(x, y)) ctx.strokeRect(x - 1.5, y - 1.5, rs + 3, rs + 3); }
        ctx.strokeStyle = p.caller;
        for (const j of ins) { const { x, y } = at(j); if (onScreen(x, y)) ctx.strokeRect(x - 1.5, y - 1.5, rs + 3, rs + 3); }
      }
    }
    const hv = hoverRef.current;
    if (hv >= 0 && hv !== sel && hv < g.n) {
      const { x, y } = at(hv);
      ctx.strokeStyle = p.ink;
      ctx.lineWidth = 2;
      ctx.strokeRect(x - 2, y - 2, rs + 4, rs + 4);
    }
    if (sel >= 0 && sel < g.n) {
      const { x, y } = at(sel);
      const pulse = rm ? 0 : (Math.sin(now / 260) + 1) * 1.5;
      ctx.strokeStyle = p.accent;
      ctx.lineWidth = 2.5;
      ctx.strokeRect(x - 3 - pulse, y - 3 - pulse, rs + 6 + 2 * pulse, rs + 6 + 2 * pulse);
      ctx.strokeStyle = 'rgba(15,17,21,.9)';
      ctx.lineWidth = 1;
      ctx.strokeRect(x - 1, y - 1, rs + 2, rs + 2);
    }
    return busy;
  }, []);

  /* ---------- frame loop (runs only while something moves) ---------- */
  const frame = useCallback((now: number) => {
    raf.current = 0;
    let busy = false;
    if (anim.current) {
      const a = anim.current;
      const t = Math.min(1, (now - a.start) / a.ms);
      view.current = lerpView(a.from, a.to, t);
      dirtyView.current = true;
      if (t >= 1) {
        anim.current = null;
        setZoomLabel(view.current.scale);
      } else busy = true;
    }
    if (dirtyView.current) {
      drawView();
      drawMini();
    }
    if (drawFx(now)) busy = true;
    if (busy) raf.current = requestAnimationFrame(frame);
  }, [drawView, drawMini, drawFx]);

  const kick = useCallback(() => {
    if (!raf.current) raf.current = requestAnimationFrame(frame);
  }, [frame]);
  useEffect(() => () => cancelAnimationFrame(raf.current), []);

  const commitView = useCallback((next: View, fitted = false) => {
    const { w, h } = size.current;
    view.current = fitted ? next : clampView(next, grid.current, w, h);
    atFit.current = fitted;
    anim.current = null;
    dirtyView.current = true;
    setZoomLabel(view.current.scale);
    kick();
  }, [kick]);

  const animateTo = useCallback((to: View) => {
    if (reducedMotion) return commitView(to);
    anim.current = { from: view.current, to, start: performance.now(), ms: 450 };
    atFit.current = false;
    kick();
  }, [reducedMotion, commitView, kick]);

  const fitAll = useCallback((animate: boolean) => {
    const { w, h } = size.current;
    const to = fitView(grid.current, w, h);
    if (animate && !reducedMotion) {
      anim.current = { from: view.current, to, start: performance.now(), ms: 350 };
      atFit.current = true;
      kick();
    } else commitView(to, true);
    atFit.current = true;
  }, [reducedMotion, commitView, kick]);

  /* ---------- layout ---------- */
  const layout = useCallback(() => {
    const { w, h } = size.current;
    const c = live.current.cells;
    if (!w || !h) return;
    const key = `${c.programId}|${c.ref}|${c.n}`;
    if (layoutKey.current === key) return;
    layoutKey.current = key;
    grid.current = gridFor(c.n, w, h);
    const g = grid.current;
    // Minimap keeps the grid's aspect inside its max box.
    const ar = rowsOf(g) / Math.max(1, g.cols);
    let mw = MINI_MAX_W, mh = Math.round(mw * ar);
    if (mh > MINI_MAX_H) { mh = MINI_MAX_H; mw = Math.max(40, Math.round(MINI_MAX_H / ar)); }
    setMini({ w: mw, h: Math.max(20, mh) });
    hoverRef.current = -1;
    setHover(null);
    rebuildBase();
    commitView(fitView(g, w, h), true);
  }, [rebuildBase, commitView]);

  useLayoutEffect(() => {
    const wrap = wrapRef.current, vc = viewRef.current, fc = fxRef.current;
    if (!wrap || !vc || !fc) return;
    const resize = () => {
      const r = wrap.getBoundingClientRect();
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const prev = size.current;
      size.current = { w: r.width, h: r.height, dpr };
      for (const cv of [vc, fc]) {
        cv.width = Math.max(1, Math.round(r.width * dpr));
        cv.height = Math.max(1, Math.round(r.height * dpr));
      }
      const before = layoutKey.current;
      layout();
      if (before === layoutKey.current && grid.current.n && prev.w) {
        if (atFit.current) commitView(fitView(grid.current, r.width, r.height), true);
        else commitView(panBy(view.current, (r.width - prev.w) / 2, (r.height - prev.h) / 2));
      }
      dirtyView.current = true;
      kick();
    };
    const ro = new ResizeObserver(resize);
    ro.observe(wrap);
    resize();
    return () => ro.disconnect();
  }, [layout, commitView, kick]);

  useLayoutEffect(() => {
    const m = miniRef.current;
    if (!m) return;
    const dpr = size.current.dpr || 1;
    m.width = Math.round(mini.w * dpr);
    m.height = Math.round(mini.h * dpr);
    dirtyView.current = true;
    kick();
  }, [mini, kick]);

  // New program → relayout; same program, new version → incremental repaint.
  useLayoutEffect(() => {
    const before = layoutKey.current;
    layout();
    if (before !== layoutKey.current) return;
    if (cells.version !== baseState.current.version) {
      if (cells.changed.length && cells.changed.length < cells.n / 4) patchBase(cells.changed);
      else rebuildBase();
    }
    kick();
  }, [cells, layout, patchBase, rebuildBase, kick]);

  // Filter / colour mode → full base rebuild.
  useEffect(() => {
    if (!grid.current.n) return;
    const key = `${layoutKey.current}|${colorBy}|${filter.states}|${filter.tiers}`;
    if (key !== baseState.current.key) rebuildBase();
    kick();
  }, [filter, colorBy, rebuildBase, kick]);

  useEffect(() => { dirtyView.current = true; kick(); }, [selected, hits, reducedMotion, kick]);

  // Fly to a requested cell (search, caller/callee jump, activity mark).
  useEffect(() => {
    if (!fly || fly.index < 0 || fly.index >= grid.current.n) return;
    const { w, h } = size.current;
    animateTo(clampView(centerOn(view.current, grid.current, fly.index, w, h, fly.scale ?? 22), grid.current, w, h));
  }, [fly, animateTo]);

  // Wheel zoom at the cursor (non-passive so the page does not scroll).
  useEffect(() => {
    const canvas = fxRef.current;
    if (!canvas) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const unit = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? rect.height : 1;
      const dy = (e.deltaY || e.deltaX) * unit;
      const k = e.ctrlKey ? 0.01 : 0.0018; // trackpad pinch reports small ctrl+wheel deltas
      commitView(zoomAt(view.current, Math.exp(-Math.max(-300, Math.min(300, dy)) * k), e.clientX - rect.left, e.clientY - rect.top));
    };
    canvas.addEventListener('wheel', onWheel, { passive: false });
    return () => canvas.removeEventListener('wheel', onWheel);
  }, [commitView]);

  /* ---------- pointer ---------- */
  const accept = useMemo(() => (filterActive(filter) ? (i: number) => matchesFilter(live.current.cells, i, live.current.filter) : undefined), [filter]);
  const hitAt = (x: number, y: number) => hitTest(view.current, grid.current, x, y, 6, accept);
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const drag = useRef<{ x: number; y: number; moved: boolean; pinch?: number } | null>(null);
  const [grabbing, setGrabbing] = useState(false);
  const local = (e: { clientX: number; clientY: number }) => {
    const rect = fxRef.current!.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };
  const setHoverIndex = (i: number, x = 0, y = 0) => {
    if (i !== hoverRef.current) {
      hoverRef.current = i;
      kick();
    }
    setHover(i >= 0 ? { index: i, x, y } : null);
  };
  const onPointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (e.button !== 0 && e.pointerType === 'mouse') return;
    e.currentTarget.setPointerCapture(e.pointerId);
    const p = local(e);
    pointers.current.set(e.pointerId, p);
    anim.current = null;
    if (pointers.current.size === 2) {
      const [a, b] = [...pointers.current.values()];
      drag.current = { x: p.x, y: p.y, moved: true, pinch: Math.hypot(a.x - b.x, a.y - b.y) };
    } else drag.current = { x: p.x, y: p.y, moved: false };
  };
  const onPointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const p = local(e);
    const d = drag.current;
    if (!d) {
      const i = hitAt(p.x, p.y);
      setHoverIndex(e.pointerType === 'touch' ? -1 : i, p.x, p.y);
      return;
    }
    const prev = pointers.current.get(e.pointerId);
    pointers.current.set(e.pointerId, p);
    if (pointers.current.size >= 2 && d.pinch) {
      const [a, b] = [...pointers.current.values()];
      const dist = Math.hypot(a.x - b.x, a.y - b.y);
      if (dist > 0) commitView(zoomAt(view.current, dist / d.pinch, (a.x + b.x) / 2, (a.y + b.y) / 2));
      d.pinch = dist;
      return;
    }
    if (!d.moved && Math.hypot(p.x - d.x, p.y - d.y) > 4) {
      d.moved = true;
      setGrabbing(true);
      setHoverIndex(-1);
    }
    if (d.moved && prev) commitView(panBy(view.current, p.x - prev.x, p.y - prev.y));
  };
  const onPointerUp = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const d = drag.current;
    pointers.current.delete(e.pointerId);
    if (pointers.current.size) return;
    drag.current = null;
    setGrabbing(false);
    if (d && !d.moved && e.type === 'pointerup') {
      const p = local(e);
      const i = hitAt(p.x, p.y);
      onSelect(i); // empty space clears the selection
      setHoverIndex(i, p.x, p.y);
    }
  };

  const zoomCenter = (factor: number) => {
    const { w, h } = size.current;
    commitView(zoomAt(view.current, factor, w / 2, h / 2));
  };

  const firstVisible = () => {
    const g = grid.current, v = view.current;
    const col = Math.max(0, Math.min(g.cols - 1, Math.ceil(-v.ox / v.scale)));
    const row = Math.max(0, Math.min(rowsOf(g) - 1, Math.ceil(-v.oy / v.scale)));
    return Math.max(0, Math.min(g.n - 1, row * g.cols + col));
  };

  const onKeyDown = (e: ReactKeyboardEvent<HTMLCanvasElement>) => {
    const g = grid.current;
    const { w, h } = size.current;
    if (e.key === '+' || e.key === '=') return (e.preventDefault(), zoomCenter(1.6));
    if (e.key === '-' || e.key === '_') return (e.preventDefault(), zoomCenter(1 / 1.6));
    if (e.key === '0') return (e.preventDefault(), fitAll(true));
    if (e.key === 'Enter' && hoverRef.current >= 0) return (e.preventDefault(), onSelect(hoverRef.current));
    if (e.key === 'Escape') {
      if (selected >= 0) {
        e.preventDefault();
        onSelect(-1);
      }
      return;
    }
    if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End'].includes(e.key)) return;
    e.preventDefault();
    const from = selected >= 0 ? selected : hoverRef.current;
    const next = from < 0 ? firstVisible() : stepIndex(g, from, e.key, Math.max(1, Math.floor(h / Math.max(1, view.current.scale))));
    if (next < 0) return;
    const v = view.current;
    if (v.scale < 12) animateTo(clampView(centerOn(v, g, next, w, h, 16), g, w, h));
    else if (!isCellVisible(v, g, next, w, h)) animateTo(clampView(centerOn(v, g, next, w, h, v.scale), g, w, h));
    onSelect(next);
  };

  // Minimap: click or drag to move the viewport.
  const miniDrag = useRef(false);
  const miniMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const { w, h } = size.current;
    commitView(viewFromMinimap(view.current, grid.current, e.clientX - rect.left, e.clientY - rect.top, w, h, mini.w, mini.h));
  };

  const tip = hover && hover.index >= 0 && hover.index < cells.n && !grabbing ? hover : null;
  const selText = selected >= 0 && selected < cells.n
    ? `${cellName(cells, selected)}, ${STATE_LABELS[cells.state[selected]]}, bound in ${cells.nb[selected]} binaries`
    : '';

  return (
    <div className="cp-mapbox">
      <MapFilters cells={cells} filter={filter} colorBy={colorBy} tierNames={tierNames} onFilter={props.onFilter} onColorBy={props.onColorBy} />
      <div className="cp-map" ref={wrapRef}>
        <canvas ref={viewRef} className="cp-map-view" aria-hidden="true" />
        <canvas
          ref={fxRef}
          className={`cp-map-canvas ${grabbing ? 'grabbing' : tip ? 'pointing' : ''}`}
          tabIndex={0}
          role="application"
          aria-roledescription="program map"
          aria-label={`Program map, ${cells.n.toLocaleString()} functions in address order. Arrow keys move the selection, plus and minus zoom, 0 fits, Escape clears.`}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          onPointerLeave={() => !drag.current && setHoverIndex(-1)}
          onDoubleClick={e => { const p = local(e); commitView(zoomAt(view.current, 2.2, p.x, p.y)); }}
          onKeyDown={onKeyDown}
        />
        <span className="cp-sr" aria-live="polite">{selText}</span>
        {tip && <CellTip cells={cells} index={tip.index} x={tip.x} y={tip.y} w={size.current.w} h={size.current.h} buildCount={buildCount} binaries={binaries} tierNames={tierNames} />}
        <div className="cp-zoom" role="group" aria-label="Zoom">
          <button type="button" onClick={() => zoomCenter(1.6)} aria-label="Zoom in" data-tip="Zoom in · wheel or +">+</button>
          <button type="button" onClick={() => zoomCenter(1 / 1.6)} aria-label="Zoom out" data-tip="Zoom out · wheel or −">−</button>
          <button type="button" onClick={() => fitAll(true)} aria-label="Fit whole program" data-tip="Fit the whole program · 0">
            <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M1 4V1h3M8 1h3v3M11 8v3H8M4 11H1V8" fill="none" stroke="currentColor" strokeWidth="1.4" /></svg>
          </button>
          <span className="cp-zoom-level cp-mono" data-tip="Screen pixels per function">{zoomLabel >= 10 ? Math.round(zoomLabel) : zoomLabel.toFixed(1)}</span>
        </div>
        <canvas
          ref={miniRef}
          className="cp-minimap"
          style={{ width: mini.w, height: mini.h }}
          aria-hidden="true"
          data-tip="Whole program · the box is the visible part; click or drag to move"
          onPointerDown={e => { miniDrag.current = true; e.currentTarget.setPointerCapture(e.pointerId); miniMove(e); }}
          onPointerMove={e => miniDrag.current && miniMove(e)}
          onPointerUp={() => (miniDrag.current = false)}
          onPointerCancel={() => (miniDrag.current = false)}
        />
      </div>
    </div>
  );
}

/* ---------- filter chips + colour mode ---------- */

const TIER_ORDER = [1, 2, 3, 4, 5, 0];
export const tierLabel = (tierNames: string[], t: number) => (t === 0 ? TIER_LABELS[0] : tierNames[t - 1] || TIER_LABELS[t] || `tier ${t}`);

function MapFilters({ cells, filter, colorBy, tierNames, onFilter, onColorBy }: {
  cells: ProgramCells; filter: MapFilter; colorBy: ColorBy; tierNames: string[]; onFilter: (f: MapFilter) => void; onColorBy: (c: ColorBy) => void;
}) {
  const counts = useMemo(() => cellCounts(cells), [cells]);
  const STATE_TIPS = [
    'Found in the reference build, not yet tied to a shared identity',
    'Tied to one logical function shared across builds',
    'C with a recorded byte-exact receipt in this build or a sibling build (a sibling-only receipt is transferred evidence, not a verdict for this build)',
  ];
  return (
    <div className="cp-filters" role="toolbar" aria-label="Highlight functions">
      {[0, 1, 2].map(s => (
        <button key={s} type="button" className="cp-fchip" aria-pressed={hasBit(filter.states, s)}
          onClick={() => onFilter({ ...filter, states: toggleBit(filter.states, s) })}
          data-tip={`${STATE_LABELS[s]} · ${STATE_TIPS[s]} · click to highlight, click more to combine`}>
          <i className={`cp-swatch s${s}`} aria-hidden="true" />{STATE_SHORT[s]}<b className="cp-mono">{fmt(counts.states[s])}</b>
        </button>
      ))}
      <span className="cp-fsep" aria-hidden="true" />
      {TIER_ORDER.filter(t => counts.tiers[t] > 0).map(t => (
        <button key={t} type="button" className="cp-fchip" aria-pressed={hasBit(filter.tiers, t)}
          onClick={() => onFilter({ ...filter, tiers: toggleBit(filter.tiers, t) })}
          data-tip={`Name from ${tierLabel(tierNames, t)} · ${fmt(counts.tiers[t])} functions · click to highlight`}>
          <i className={`cp-swatch t${t}`} aria-hidden="true" />{tierLabel(tierNames, t)}<b className="cp-mono">{fmt(counts.tiers[t])}</b>
        </button>
      ))}
      {filterActive(filter) && (
        <button type="button" className="cp-fchip clear" onClick={() => onFilter(NO_FILTER)} aria-label="Clear highlight" data-tip="Clear highlight">
          <svg width="9" height="9" viewBox="0 0 12 12" aria-hidden="true"><path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" strokeWidth="1.8" /></svg>
        </button>
      )}
      <span className="cp-seg" role="group" aria-label="Colour cells by">
        {([['state', 'state', 'Colour by recovery state'], ['builds', 'builds', 'Colour by how many binaries hold the function (brighter = more)'], ['tier', 'name', 'Colour by where the name came from']] as const).map(([k, l, t]) => (
          <button key={k} type="button" aria-pressed={colorBy === k} onClick={() => onColorBy(k)} data-tip={t}>{l}</button>
        ))}
      </span>
    </div>
  );
}

/* ---------- cell tooltip (hover) ---------- */

function CellTip({ cells, index, x, y, w, h, buildCount, binaries, tierNames }: {
  cells: ProgramCells; index: number; x: number; y: number; w: number; h: number; buildCount: number; binaries: number; tierNames: string[];
}) {
  const tw = 250, th = 132, gap = 16;
  const left = x + gap + tw > w ? Math.max(4, x - gap - tw) : x + gap;
  const top = y + gap + th > h ? Math.max(4, y - gap - th) : y + gap;
  const st = cells.state[index], nb = cells.nb[index];
  const outs = cells.outStart[index + 1] - cells.outStart[index], ins = cells.inStart[index + 1] - cells.inStart[index];
  const slots = Math.min(Math.max(buildCount, nb), 24);
  return (
    <div className="cp-tip cp-cell-tip" style={{ left, top }} role="tooltip">
      <b className="cp-tip-name">{cellName(cells, index)}</b>
      <div className="cp-tip-row"><span className="cp-addr">{hex(cells.addr[index])}</span><span className="cp-mono cp-muted">{fmt(cells.size[index] ?? 0)} B</span></div>
      <div className="cp-tip-row"><i className={`cp-swatch s${st}`} />{STATE_LABELS[st]}</div>
      <div className="cp-tip-row">
        <span className="cp-builds" aria-hidden="true">{Array.from({ length: slots }, (_, k) => <i key={k} className={k < nb ? 'on' : ''} />)}</span>
        <span className="cp-mono">{fmt(nb)}{binaries ? ` / ${fmt(binaries)}` : ''} binaries</span>
      </div>
      <div className="cp-tip-row cp-muted"><i className={`cp-swatch t${cells.tier[index]}`} />{tierLabel(tierNames, cells.tier[index])}<span className="cp-mono" style={{ marginLeft: 'auto' }}>↑{ins} ↓{outs}</span></div>
    </div>
  );
}
