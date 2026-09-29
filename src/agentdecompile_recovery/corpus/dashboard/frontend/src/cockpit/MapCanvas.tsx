import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from 'react';
import { STATE_LABELS, TIER_LABELS, hex } from './api';
import { DIM_BUCKET, FLASH_MS, bucketsFor, callersOf, calleesOf, cellName, type MapFilter, type ProgramCells } from './state';
import {
  cellCenter, cellRect, centerOn, clampView, fitView, gapFor, gridFor, hitTest, isCellVisible, lerpView,
  minimapFit, minimapViewport, panBy, rowsOf, stepIndex, viewFromMinimap, visibleRows, zoomAt, type Grid, type View,
} from './mapMath';

export type FlyRequest = { index: number; nonce: number; scale?: number };

type Props = {
  cells: ProgramCells;
  buildCount: number;
  selected: number;
  filter: MapFilter;
  fly: FlyRequest | null;
  reducedMotion: boolean;
  onSelect: (index: number) => void;
};

const LABEL_SCALE = 40;
const MINI_W = 168, MINI_H = 104;

function readPalette(el: Element) {
  const cs = getComputedStyle(el);
  const v = (name: string, fallback: string) => cs.getPropertyValue(name).trim() || fallback;
  return {
    buckets: [
      v('--c-unbound', '#2e333d'), v('--c-bound', '#28446f'), v('--c-rec', '#7fd6a4'),
      v('--c-unbound-named', '#474e5c'), v('--c-bound-named', '#4a78bb'), v('--c-rec-named', '#b1f0cc'),
      v('--c-dim', '#181b21'),
    ],
    well: v('--well', '#0f1115'),
    ink: v('--ink-strong', '#f2f4f7'),
    accent: v('--accent', '#8cbaff'),
    callee: v('--f-identity', '#8cbaff'),
    caller: v('--f-unify', '#f0c060'),
    flash: v('--f-source', '#7fd6a4'),
    mono: v('--font-mono', 'monospace'),
  };
}

export function MapCanvas({ cells, buildCount, selected, filter, fly, reducedMotion, onSelect }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const miniRef = useRef<HTMLCanvasElement>(null);
  const size = useRef({ w: 0, h: 0, dpr: 1 });
  const grid = useRef<Grid>({ n: 0, cols: 1 });
  const gridProgram = useRef('');
  const view = useRef<View>({ scale: 1, ox: 0, oy: 0 });
  const hoverRef = useRef(-1);
  const frame = useRef(0);
  const anim = useRef<{ from: View; to: View; start: number; ms: number } | null>(null);
  const palette = useRef<ReturnType<typeof readPalette> | null>(null);
  const miniImage = useRef<HTMLCanvasElement | null>(null);
  const [hover, setHover] = useState<{ index: number; x: number; y: number; source: 'pointer' | 'keyboard' } | null>(null);
  const [scaleLabel, setScaleLabel] = useState(1);

  const buckets = useMemo(() => bucketsFor(cells, filter), [cells, filter]);
  const selectedRef = useRef(selected);
  selectedRef.current = selected;

  const draw = useCallback(() => {
    frame.current = 0;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const pal = (palette.current ||= readPalette(canvas));
    const { w, h, dpr } = size.current;
    const now = performance.now();
    if (anim.current) {
      const a = anim.current;
      const t = Math.min(1, (now - a.start) / a.ms);
      view.current = lerpView(a.from, a.to, t);
      if (t >= 1) anim.current = null;
    }
    const v = view.current, g = grid.current;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = pal.well;
    ctx.fillRect(0, 0, w, h);
    if (g.n === 0) return;
    const [r0, r1] = visibleRows(v, g, h);
    const i0 = r0 * g.cols, i1 = Math.min(g.n - 1, (r1 + 1) * g.cols - 1);
    const gap = gapFor(v.scale), sz = Math.max(0.6, v.scale - gap);
    for (let b = 0; b <= DIM_BUCKET; b++) {
      ctx.fillStyle = pal.buckets[b];
      for (let i = i0; i <= i1; i++) {
        if (buckets[i] !== b) continue;
        const c = i % g.cols;
        const x = v.ox + c * v.scale;
        if (x + sz < 0 || x > w) continue;
        ctx.fillRect(x, v.oy + ((i / g.cols) | 0) * v.scale, sz, sz);
      }
    }
    // Named marker: a notch in the corner once cells are big enough to carry one.
    if (v.scale >= 7) {
      ctx.fillStyle = pal.ink;
      const k = Math.min(6, v.scale * 0.22);
      for (const [i] of cells.names) {
        if (i < i0 || i > i1 || buckets[i] === DIM_BUCKET) continue;
        const r = cellRect(v, g, i);
        if (r.x + r.size < 0 || r.x > w) continue;
        ctx.beginPath();
        ctx.moveTo(r.x + r.size - k, r.y);
        ctx.lineTo(r.x + r.size, r.y);
        ctx.lineTo(r.x + r.size, r.y + k);
        ctx.closePath();
        ctx.fill();
      }
    }
    // Live changes glow briefly.
    let flashing = false;
    if (cells.flashes.size) {
      ctx.strokeStyle = pal.flash;
      for (const [i, t] of cells.flashes) {
        const age = Date.now() - t;
        if (age > FLASH_MS) continue;
        flashing = true;
        const r = cellRect(v, g, i);
        ctx.globalAlpha = reducedMotion ? 0.9 : 1 - age / FLASH_MS;
        ctx.lineWidth = 2;
        const pad = reducedMotion ? 1 : 1 + (age / FLASH_MS) * 5;
        ctx.strokeRect(r.x - pad, r.y - pad, r.size + pad * 2, r.size + pad * 2);
      }
      ctx.globalAlpha = 1;
    }
    // Labels once zoomed in.
    if (v.scale >= LABEL_SCALE) {
      const fontPx = Math.max(9, Math.min(12, v.scale / 6));
      ctx.font = `${fontPx}px ${pal.mono}`;
      ctx.textBaseline = 'top';
      for (let i = i0; i <= i1; i++) {
        const r = cellRect(v, g, i);
        if (r.x + r.size < 0 || r.x > w) continue;
        const named = cells.names.has(i);
        ctx.fillStyle = buckets[i] === DIM_BUCKET ? 'rgba(242,244,247,.25)' : cells.state[i] === 2 ? '#0f1115' : named ? pal.ink : 'rgba(242,244,247,.55)';
        const maxW = r.size - 6;
        const lines = [named ? cells.names.get(i)! : hex(cells.addr[i])];
        if (named && v.scale >= 80) lines.push(hex(cells.addr[i]));
        lines.forEach((text, li) => {
          let t = text;
          if (ctx.measureText(t).width > maxW) {
            while (t.length > 1 && ctx.measureText(`${t}…`).width > maxW) t = t.slice(0, -1);
            t = `${t}…`;
          }
          ctx.fillText(t, r.x + 3, r.y + 3 + li * (fontPx + 2));
        });
      }
    }
    // Real call edges of the selection.
    const sel = selectedRef.current;
    if (sel >= 0 && sel < g.n) {
      const from = cellCenter(v, g, sel);
      const drawEdges = (targets: number[], color: string) => {
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.25;
        ctx.globalAlpha = 0.75;
        for (const j of targets.slice(0, 600)) {
          const to = cellCenter(v, g, j);
          const mx = (from.x + to.x) / 2, my = (from.y + to.y) / 2;
          const dx = to.x - from.x, dy = to.y - from.y;
          ctx.beginPath();
          ctx.moveTo(from.x, from.y);
          ctx.quadraticCurveTo(mx - dy * 0.18, my + dx * 0.18, to.x, to.y);
          ctx.stroke();
          ctx.fillStyle = color;
          ctx.fillRect(to.x - 1.5, to.y - 1.5, 3, 3);
        }
        ctx.globalAlpha = 1;
      };
      drawEdges(callersOf(cells, sel), pal.caller);
      drawEdges(calleesOf(cells, sel), pal.callee);
      const r = cellRect(v, g, sel);
      const pad = Math.max(2, Math.min(5, v.scale * 0.2));
      ctx.lineWidth = 2;
      ctx.strokeStyle = pal.accent;
      ctx.strokeRect(r.x - pad, r.y - pad, r.size + pad * 2, r.size + pad * 2);
      ctx.strokeStyle = 'rgba(140,186,255,.35)';
      ctx.lineWidth = 6;
      ctx.strokeRect(r.x - pad - 4, r.y - pad - 4, r.size + pad * 2 + 8, r.size + pad * 2 + 8);
    }
    const hv = hoverRef.current;
    if (hv >= 0 && hv !== sel) {
      const r = cellRect(v, g, hv);
      ctx.lineWidth = 1.5;
      ctx.strokeStyle = pal.ink;
      ctx.strokeRect(r.x - 1.5, r.y - 1.5, r.size + 3, r.size + 3);
    }
    drawMini();
    if (anim.current || flashing) frame.current = requestAnimationFrame(draw);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cells, buckets, reducedMotion]);

  function drawMini() {
    const mini = miniRef.current, img = miniImage.current;
    if (!mini) return;
    const ctx = mini.getContext('2d');
    if (!ctx) return;
    const dpr = size.current.dpr, g = grid.current;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, MINI_W, MINI_H);
    if (!img || g.n === 0) return;
    const m = minimapFit(g, MINI_W, MINI_H);
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(img, m.ox, m.oy, g.cols * m.s, rowsOf(g) * m.s);
    const vp = minimapViewport(view.current, g, size.current.w, size.current.h, MINI_W, MINI_H);
    ctx.strokeStyle = palette.current?.ink || '#f2f4f7';
    ctx.lineWidth = 1.5;
    const x = Math.max(0.75, vp.x), y = Math.max(0.75, vp.y);
    const r = Math.min(MINI_W - 0.75, vp.x + vp.w), b = Math.min(MINI_H - 0.75, vp.y + vp.h);
    if (r > x && b > y) ctx.strokeRect(x, y, r - x, b - y);
  }

  const requestDraw = useCallback(() => {
    if (!frame.current) frame.current = requestAnimationFrame(draw);
  }, [draw]);

  const commitView = useCallback((next: View) => {
    const { w, h } = size.current;
    view.current = clampView(next, grid.current, w, h);
    anim.current = null;
    setScaleLabel(view.current.scale);
    requestDraw();
  }, [requestDraw]);

  const cellsRef = useRef(cells);
  cellsRef.current = cells;
  const [layoutVersion, setLayoutVersion] = useState(0);
  /** Lay the grid out for the current program once the canvas has a size. */
  function ensureLayout(): boolean {
    const { w, h } = size.current;
    const c = cellsRef.current;
    if (!w || !h) return false;
    if (gridProgram.current === c.programId && grid.current.n === c.n) return false;
    grid.current = gridFor(c.n, w, h);
    gridProgram.current = c.programId;
    view.current = fitView(grid.current, w, h);
    anim.current = null;
    hoverRef.current = -1;
    setScaleLabel(view.current.scale);
    setHover(null);
    setLayoutVersion(v => v + 1);
    return true;
  }

  // Size + DPR tracking.
  useLayoutEffect(() => {
    const wrap = wrapRef.current, canvas = canvasRef.current, mini = miniRef.current;
    if (!wrap || !canvas || !mini) return;
    const resize = () => {
      const rect = wrap.getBoundingClientRect();
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const prev = size.current;
      size.current = { w: rect.width, h: rect.height, dpr };
      canvas.width = Math.max(1, Math.round(rect.width * dpr));
      canvas.height = Math.max(1, Math.round(rect.height * dpr));
      mini.width = Math.round(MINI_W * dpr);
      mini.height = Math.round(MINI_H * dpr);
      if (!ensureLayout() && grid.current.n && prev.w) {
        view.current = clampView(panBy(view.current, (rect.width - prev.w) / 2, (rect.height - prev.h) / 2), grid.current, rect.width, rect.height);
      }
      requestDraw();
    };
    const ro = new ResizeObserver(resize);
    ro.observe(wrap);
    resize();
    return () => ro.disconnect();
  }, [requestDraw]);

  // (Re)layout when the program changes; keep the view across live diffs.
  useLayoutEffect(() => {
    ensureLayout();
  });

  // Minimap bitmap (one pixel per cell) rebuilt when cells or filter change.
  useEffect(() => {
    const g = grid.current;
    if (!g.n) return;
    const rows = rowsOf(g);
    const off = document.createElement('canvas');
    off.width = g.cols;
    off.height = rows;
    const ctx = off.getContext('2d');
    if (!ctx) return;
    const pal = (palette.current ||= readPalette(canvasRef.current || document.body));
    const rgb = pal.buckets.map(c => {
      const m = /^#?([0-9a-f]{6})$/i.exec(c.trim());
      const n = m ? parseInt(m[1], 16) : 0x333333;
      return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
    });
    const data = ctx.createImageData(g.cols, rows);
    for (let i = 0; i < g.n; i++) {
      const [r, gg, b] = rgb[buckets[i]];
      data.data[i * 4] = r;
      data.data[i * 4 + 1] = gg;
      data.data[i * 4 + 2] = b;
      data.data[i * 4 + 3] = 255;
    }
    ctx.putImageData(data, 0, 0);
    miniImage.current = off;
    requestDraw();
  }, [buckets, layoutVersion, requestDraw]);

  useEffect(() => { requestDraw(); }, [selected, cells, buckets, requestDraw]);

  // Fly to a requested cell (search, caller/callee jump).
  useEffect(() => {
    if (!fly || fly.index < 0 || fly.index >= grid.current.n) return;
    const { w, h } = size.current;
    const to = clampView(centerOn(view.current, grid.current, fly.index, w, h, fly.scale ?? 48), grid.current, w, h);
    if (reducedMotion) {
      commitView(to);
      return;
    }
    anim.current = { from: view.current, to, start: performance.now(), ms: 520 };
    setScaleLabel(to.scale);
    requestDraw();
  }, [fly, reducedMotion, commitView, requestDraw]);

  // Wheel zoom at the cursor (non-passive so the page does not scroll).
  useEffect(() => {
    const canvas = canvasRef.current;
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

  // Pointer: drag pan, click lock, hover tooltip, two-finger pinch.
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const drag = useRef<{ x: number; y: number; moved: boolean; pinch?: number } | null>(null);
  const local = (e: { clientX: number; clientY: number }) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };
  const updateHover = (x: number, y: number) => {
    const i = hitTest(view.current, grid.current, x, y);
    if (i !== hoverRef.current) {
      hoverRef.current = i;
      requestDraw();
    }
    setHover(i >= 0 ? { index: i, x, y, source: 'pointer' } : null);
  };
  const onPointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (e.button !== 0 && e.pointerType === 'mouse') return;
    e.currentTarget.setPointerCapture(e.pointerId);
    const p = local(e);
    pointers.current.set(e.pointerId, p);
    if (pointers.current.size === 2) {
      const [a, b] = [...pointers.current.values()];
      drag.current = { x: p.x, y: p.y, moved: true, pinch: Math.hypot(a.x - b.x, a.y - b.y) };
    } else drag.current = { x: p.x, y: p.y, moved: false };
  };
  const onPointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const p = local(e);
    const d = drag.current;
    if (!d) {
      updateHover(p.x, p.y);
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
      setHover(null);
    }
    if (d.moved && prev) commitView(panBy(view.current, p.x - prev.x, p.y - prev.y));
  };
  const onPointerUp = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const d = drag.current;
    pointers.current.delete(e.pointerId);
    if (pointers.current.size) return;
    drag.current = null;
    if (d && !d.moved) {
      const p = local(e);
      const i = hitTest(view.current, grid.current, p.x, p.y);
      if (i >= 0) onSelect(i); // empty space keeps the locked selection
      updateHover(p.x, p.y);
    }
  };
  const onPointerLeave = () => {
    if (drag.current) return;
    hoverRef.current = -1;
    setHover(null);
    requestDraw();
  };

  const zoomCenter = (factor: number) => {
    const { w, h } = size.current;
    commitView(zoomAt(view.current, factor, w / 2, h / 2));
  };
  const fit = () => {
    const { w, h } = size.current;
    commitView(fitView(grid.current, w, h));
  };

  const showKeyboardTip = (i: number, v: View = view.current) => {
    if (i < 0) {
      setHover(null);
      return;
    }
    const c = cellCenter(v, grid.current, i);
    setHover({ index: i, x: c.x, y: c.y, source: 'keyboard' });
  };

  const onKeyDown = (e: ReactKeyboardEvent<HTMLCanvasElement>) => {
    const g = grid.current;
    const { w, h } = size.current;
    if (e.key === '+' || e.key === '=') return (e.preventDefault(), zoomCenter(1.4));
    if (e.key === '-' || e.key === '_') return (e.preventDefault(), zoomCenter(1 / 1.4));
    if (e.key === '0') return (e.preventDefault(), fit());
    if (e.key === 'Escape') {
      if (selected >= 0) {
        e.preventDefault();
        onSelect(-1);
        setHover(null);
      }
      return;
    }
    const next = stepIndex(g, selected, e.key, Math.max(1, Math.floor(h / Math.max(1, view.current.scale))));
    if (next === selected && !['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(e.key)) return;
    e.preventDefault();
    if (next < 0) return;
    let v = view.current;
    if (!isCellVisible(v, g, next, w, h)) {
      v = clampView(centerOn(v, g, next, w, h, Math.max(v.scale, 8)), g, w, h);
      view.current = v;
      setScaleLabel(v.scale);
    }
    onSelect(next);
    showKeyboardTip(next, v);
  };

  // Minimap: click or drag to move the viewport.
  const miniDrag = useRef(false);
  const miniMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const { w, h } = size.current;
    commitView(viewFromMinimap(view.current, grid.current, e.clientX - rect.left, e.clientY - rect.top, w, h, MINI_W, MINI_H));
  };

  const tip = hover && hover.index >= 0 && hover.index < cells.n ? hover : null;
  const tipStyle = tip ? tipPosition(tip.x, tip.y, size.current.w, size.current.h, tip.source === 'keyboard' ? view.current.scale : 0) : undefined;
  const selectedText = selected >= 0 && selected < cells.n
    ? `${cellName(cells, selected)}, ${STATE_LABELS[cells.state[selected]]}, bound in ${cells.nb[selected]} builds`
    : '';

  return (
    <div className="cp-map" ref={wrapRef}>
      <canvas
        ref={canvasRef}
        className="cp-map-canvas"
        tabIndex={0}
        role="application"
        aria-roledescription="program map"
        aria-label={`Program map, ${cells.n.toLocaleString()} functions in address order. Arrow keys move the selection, plus and minus zoom, 0 fits, Escape clears.`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onPointerLeave={onPointerLeave}
        onDoubleClick={e => {
          const p = local(e);
          commitView(zoomAt(view.current, 2, p.x, p.y));
        }}
        onKeyDown={onKeyDown}
        onFocus={() => selected >= 0 && showKeyboardTip(selected)}
        onBlur={() => setHover(h => (h?.source === 'keyboard' ? null : h))}
        style={{ cursor: drag.current?.moved ? 'grabbing' : hover ? 'pointer' : 'grab' }}
      />
      <span className="cp-sr" aria-live="polite">{selectedText}</span>
      {tip && tipStyle && <CellTip cells={cells} index={tip.index} buildCount={buildCount} style={tipStyle} />}
      <div className="cp-zoom" role="group" aria-label="Zoom">
        <button type="button" onClick={() => zoomCenter(1.5)} aria-label="Zoom in" data-tip="Zoom in · wheel or +">+</button>
        <button type="button" onClick={() => zoomCenter(1 / 1.5)} aria-label="Zoom out" data-tip="Zoom out · wheel or −">−</button>
        <button type="button" onClick={fit} aria-label="Fit whole program" data-tip="Fit the whole program · 0">
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M1 4V1h3M8 1h3v3M11 8v3H8M4 11H1V8" fill="none" stroke="currentColor" strokeWidth="1.4" /></svg>
        </button>
        <span className="cp-zoom-level" aria-hidden="true">{scaleLabel >= 10 ? Math.round(scaleLabel) : scaleLabel.toFixed(1)}px</span>
      </div>
      <canvas
        ref={miniRef}
        className="cp-minimap"
        style={{ width: MINI_W, height: MINI_H }}
        aria-hidden="true"
        data-tip="Whole program · the box is what the map shows; click or drag to move"
        onPointerDown={e => {
          miniDrag.current = true;
          e.currentTarget.setPointerCapture(e.pointerId);
          miniMove(e);
        }}
        onPointerMove={e => miniDrag.current && miniMove(e)}
        onPointerUp={() => (miniDrag.current = false)}
        onPointerCancel={() => (miniDrag.current = false)}
      />
    </div>
  );
}

function tipPosition(x: number, y: number, w: number, h: number, offset: number) {
  const tw = 260, th = 120, gap = 14 + offset / 2;
  const left = x + gap + tw > w ? Math.max(4, x - gap - tw) : x + gap;
  const top = y + gap + th > h ? Math.max(4, y - gap - th) : y + gap;
  return { left, top };
}

function CellTip({ cells, index, buildCount, style }: { cells: ProgramCells; index: number; buildCount: number; style: { left: number; top: number } }) {
  const st = cells.state[index], tier = cells.tier[index], nb = cells.nb[index];
  return (
    <div className="cp-tip cp-cell-tip" style={style} role="tooltip">
      <b className="cp-tip-name">{cellName(cells, index)}</b>
      <div className="cp-tip-row"><span className="cp-mono cp-addr">{hex(cells.addr[index])}</span><span className="cp-mono">{(cells.size[index] ?? 0).toLocaleString()} B</span></div>
      <div className="cp-tip-row"><i className={`cp-swatch s${st}`} />{STATE_LABELS[st]}</div>
      <div className="cp-tip-row">
        <span className="cp-builds" aria-hidden="true">
          {Array.from({ length: Math.min(Math.max(buildCount, nb), 24) }, (_, k) => <i key={k} className={k < nb ? 'on' : ''} />)}
        </span>
        <span className="cp-mono">{nb} {nb === 1 ? 'build' : 'builds'}</span>
      </div>
      <div className="cp-tip-row cp-muted">{TIER_LABELS[tier] ?? `Tier ${tier}`}</div>
    </div>
  );
}
