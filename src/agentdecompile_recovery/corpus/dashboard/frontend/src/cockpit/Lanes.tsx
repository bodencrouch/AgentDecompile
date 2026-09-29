import { useCallback, useEffect, useLayoutEffect, useMemo, useRef } from 'react';
import { LANES, hex, type Lane } from './api';
import type { LiveActivity } from './state';

export const LANE_INFO: Record<Lane, { name: string; color: string; tip: string }> = {
  decompile: { name: 'Decompile', color: '--f-identity', tip: 'Lifting functions to C, build by build' },
  pointers: { name: 'Follow pointers', color: '--f-identity', tip: 'Calls, jumps, vtable slots and data references chased to their targets' },
  match: { name: 'Match builds', color: '--f-unify', tip: 'Deciding which functions in different builds are the same function' },
  name: { name: 'Name & type', color: '--f-verify', tip: 'Names, types and signatures merged from every source' },
  compile: { name: 'Compile & diff', color: '--f-source', tip: 'Candidate C compiled and compared with the shipped bytes' },
  signature: { name: 'Cut signatures', color: '--f-runtime', tip: 'Byte signatures that find each function on every build without an address' },
  import: { name: 'Import', color: '--f-verify', tip: 'Builds recognised, grouped into programs and loaded' },
  other: { name: 'Other', color: '--ctrl', tip: 'Other recorded jobs and actions' },
};

const TRAVEL_MS = 1800;
const STILL_MS = 1600;
export const LABEL_W = 138;

export function statusTone(status: string): 'ok' | 'bad' | 'run' | 'idle' {
  const s = status.toLowerCase();
  if (/^(ok|done|success|succeeded|completed|complete|matched|passed)$/.test(s)) return 'ok';
  if (/fail|error|cancel|interrupt|block|reject|mismatch/.test(s)) return 'bad';
  if (/run|queue|wait|start|progress|active/.test(s)) return 'run';
  return 'idle';
}

type Props = { activity: LiveActivity[]; reducedMotion: boolean; onFocusEvent?: (e: LiveActivity) => void };

export function Lanes({ activity, reducedMotion, onFocusEvent }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const size = useRef({ w: 0, h: 0, dpr: 1 });
  const frame = useRef(0);
  const activityRef = useRef(activity);
  activityRef.current = activity;

  const latest = useMemo(() => {
    const out: Partial<Record<Lane, LiveActivity>> = {};
    const counts: Partial<Record<Lane, number>> = {};
    for (const a of activity) {
      if (!out[a.lane]) out[a.lane] = a;
      counts[a.lane] = (counts[a.lane] || 0) + 1;
    }
    return { out, counts };
  }, [activity]);

  const draw = useCallback(() => {
    frame.current = 0;
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;
    const cs = getComputedStyle(canvas);
    const color = (name: string) => cs.getPropertyValue(name).trim() || '#8cbaff';
    const { w, h, dpr } = size.current;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const laneH = h / LANES.length;
    const x0 = LABEL_W, x1 = Math.max(x0 + 40, w - 220);
    ctx.lineWidth = 1;
    ctx.strokeStyle = color('--line');
    LANES.forEach((_, k) => {
      const y = Math.round(laneH * (k + 0.5)) + 0.5;
      ctx.beginPath();
      ctx.moveTo(x0, y);
      ctx.lineTo(x1, y);
      ctx.stroke();
    });
    const now = Date.now();
    let moving = false;
    for (const a of activityRef.current) {
      if (!a.live) continue;
      const age = now - a.arrivedAt;
      const life = reducedMotion ? STILL_MS : TRAVEL_MS;
      if (age < 0 || age > life) continue;
      moving = true;
      const k = LANES.indexOf(a.lane);
      const y = laneH * (k + 0.5);
      const tone = statusTone(a.status);
      const c = tone === 'ok' ? color('--f-source') : tone === 'bad' ? color('--f-fail') : color(LANE_INFO[a.lane].color);
      const t = reducedMotion ? 1 : age / TRAVEL_MS;
      const e = 1 - Math.pow(1 - t, 3);
      const x = x0 + (x1 - x0) * e;
      if (!reducedMotion) {
        const grad = ctx.createLinearGradient(Math.max(x0, x - 90), 0, x, 0);
        grad.addColorStop(0, 'rgba(0,0,0,0)');
        grad.addColorStop(1, c);
        ctx.strokeStyle = grad;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(Math.max(x0, x - 90), y);
        ctx.lineTo(x, y);
        ctx.stroke();
      }
      ctx.fillStyle = c;
      ctx.globalAlpha = reducedMotion ? 1 - age / STILL_MS / 2 : 1;
      ctx.beginPath();
      ctx.arc(x, y, 3.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = 1;
    }
    if (moving) frame.current = requestAnimationFrame(draw);
  }, [reducedMotion]);

  useLayoutEffect(() => {
    const wrap = wrapRef.current, canvas = canvasRef.current;
    if (!wrap || !canvas) return;
    const resize = () => {
      const r = wrap.getBoundingClientRect();
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      size.current = { w: r.width, h: r.height, dpr };
      canvas.width = Math.max(1, Math.round(r.width * dpr));
      canvas.height = Math.max(1, Math.round(r.height * dpr));
      if (!frame.current) frame.current = requestAnimationFrame(draw);
    };
    const ro = new ResizeObserver(resize);
    ro.observe(wrap);
    resize();
    return () => ro.disconnect();
  }, [draw]);

  useEffect(() => {
    if (!frame.current) frame.current = requestAnimationFrame(draw);
  }, [activity, draw]);
  useEffect(() => () => cancelAnimationFrame(frame.current), []);

  return (
    <div className="cp-lanes" ref={wrapRef}>
      <canvas ref={canvasRef} aria-hidden="true" />
      <ul className="cp-lane-rows" aria-label="Machine lanes">
        {LANES.map(lane => {
          const last = latest.out[lane];
          const info = LANE_INFO[lane];
          const tone = last ? statusTone(last.status) : 'idle';
          return (
            <li key={lane} className={`cp-lane ${last ? '' : 'idle'}`}>
              <span className="cp-lane-label" tabIndex={0} data-tip={`${info.name} · ${info.tip}`}>
                <i style={{ background: `var(${info.color})` }} aria-hidden="true" />
                {info.name}
                {!!latest.counts[lane] && <small className="cp-mono">{latest.counts[lane]}</small>}
              </span>
              {last ? (
                <button
                  type="button"
                  className={`cp-lane-last ${tone}`}
                  onClick={() => onFocusEvent?.(last)}
                  disabled={!onFocusEvent || last.addr === undefined}
                  data-tip={[last.kind, last.status, last.binary, last.addr !== undefined ? hex(last.addr) : '', formatTs(last.ts)].filter(Boolean).join(' · ')}
                >
                  <span className={`cp-dot ${tone}`} aria-hidden="true" />
                  <span className="cp-lane-text">{last.label}</span>
                </button>
              ) : (
                <span className="cp-lane-last idle" aria-label={`${info.name}: no events`} />
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function formatTs(ts: string | number) {
  const d = typeof ts === 'number' ? new Date(ts < 1e12 ? ts * 1000 : ts) : new Date(ts);
  return Number.isNaN(d.getTime()) ? String(ts) : d.toLocaleTimeString();
}
