// Machine lanes: one row per kind of work, a time axis ending at now, and one mark per
// real `activity` event (from the summary history and the live stream). No event, no mark.
import { useEffect, useMemo, useState } from 'react';
import { LANES, eventTime, fmt, hex, type Lane } from './api';
import type { LiveActivity } from './state';

export const LANE_INFO: Record<Lane, { name: string; color: string; tip: string }> = {
  decompile: { name: 'Decompile', color: '--f-identity', tip: 'Functions lifted out of every build' },
  pointers: { name: 'Pointers', color: '--accent', tip: 'Calls, jumps and references chased to their targets' },
  match: { name: 'Match', color: '--f-unify', tip: 'Functions in different builds proven to be the same function' },
  name: { name: 'Name', color: '--f-verify', tip: 'Names and types merged from every source, strongest first' },
  compile: { name: 'Compile', color: '--f-source', tip: 'Candidate C compiled and compared with the shipped bytes' },
  signature: { name: 'Signature', color: '--f-runtime', tip: 'Byte signatures that find each function on every build' },
  import: { name: 'Import', color: '--muted', tip: 'Binaries recognised by content and grouped into programs' },
  other: { name: 'Other', color: '--faint', tip: 'Any other job the machine reports' },
};

export function statusTone(status: string): 'ok' | 'bad' | 'run' | 'idle' {
  const s = status.toLowerCase();
  if (/^(ok|done|success|succeeded|completed|complete|matched|passed|finished)$/.test(s)) return 'ok';
  if (/fail|error|cancel|interrupt|block|reject|mismatch/.test(s)) return 'bad';
  if (/run|queue|wait|start|progress|active|pending/.test(s)) return 'run';
  return 'idle';
}

const WINDOWS = [5, 15, 30, 60, 180, 360, 720, 1440].map(m => m * 60_000);

/** Smallest standard window (5 min … 24 h) that covers the oldest event. */
export function pickWindow(times: number[], now: number): number {
  const finite = times.filter(Number.isFinite);
  if (!finite.length) return WINDOWS[2];
  const span = now - Math.min(...finite);
  return WINDOWS.find(w => w >= span) ?? WINDOWS[WINDOWS.length - 1];
}

/** Horizontal position (0..1) of an event on a window ending at now; null when outside. */
export function markPosition(t: number, now: number, windowMs: number): number | null {
  if (!Number.isFinite(t)) return null;
  const x = 1 - (now - t) / windowMs;
  return x < -0.001 ? null : Math.min(1, x);
}

const spanLabel = (ms: number) => (ms >= 3_600_000 ? `${Math.round(ms / 3_600_000)}h` : `${Math.round(ms / 60_000)}m`);

type Props = { activity: LiveActivity[]; paused: boolean; onFocusEvent?: (e: LiveActivity) => void; canFocus?: (e: LiveActivity) => boolean };

export function ActivityLanes({ activity, paused, onFocusEvent, canFocus }: Props) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (paused) return;
    const t = setInterval(() => setNow(Date.now()), 5000);
    return () => clearInterval(t);
  }, [paused]);
  useEffect(() => { if (!paused) setNow(Date.now()); }, [activity, paused]);

  const timed = useMemo(() => activity.map(a => ({ a, t: eventTime(a.ts) })), [activity]);
  const windowMs = useMemo(() => pickWindow(timed.map(x => x.t), now), [timed, now]);
  const byLane = useMemo(() => {
    const m = new Map<Lane, { a: LiveActivity; t: number; x: number }[]>();
    for (const lane of LANES) m.set(lane, []);
    for (const { a, t } of timed) {
      const x = markPosition(t, now, windowMs);
      if (x !== null) m.get(a.lane)!.push({ a, t, x });
    }
    return m;
  }, [timed, now, windowMs]);

  return (
    <div className="cp-lanes" role="list" aria-label="Machine lanes">
      <div className="cp-lanes-axis" aria-hidden="true">
        <span className="cp-mono">−{spanLabel(windowMs)}</span>
        <span className="cp-mono">−{spanLabel(windowMs / 2)}</span>
        <span className="cp-mono">now</span>
      </div>
      {LANES.map(lane => {
        const info = LANE_INFO[lane];
        const marks = byLane.get(lane)!;
        const last = marks[0]?.a;
        return (
          <div key={lane} role="listitem" className={`cp-lane ${marks.length ? '' : 'idle'}`} style={{ ['--lane' as string]: `var(${info.color})` }}>
            <span className="cp-lane-label" tabIndex={0}
              data-tip={`${info.name} · ${info.tip} · ${fmt(marks.length)} events in the last ${spanLabel(windowMs)}${last ? ` · last: ${last.label}${last.status ? ` (${last.status})` : ''}` : ''}`}>
              <i aria-hidden="true" />{info.name}{marks.length > 0 && <small className="cp-mono">{marks.length}</small>}
            </span>
            <span className="cp-lane-track">
              {marks.map(({ a, t, x }) => {
                const tone = statusTone(a.status);
                const fresh = a.live && now - a.arrivedAt < 4000;
                const focusable = !!onFocusEvent && (canFocus ? canFocus(a) : a.addr !== undefined);
                const tip = [a.label, a.kind, a.status, a.binary, a.addr !== undefined ? hex(a.addr) : '', Number.isFinite(t) ? new Date(t).toLocaleTimeString() : String(a.ts)]
                  .filter(Boolean).join(' · ');
                return (
                  <button key={a.key} type="button" className={`cp-mark ${tone} ${fresh ? 'fresh' : ''}`} style={{ left: `${(x * 100).toFixed(3)}%` }}
                    tabIndex={focusable ? 0 : -1} aria-disabled={!focusable}
                    onClick={() => focusable && onFocusEvent!(a)} data-tip={focusable ? `${tip} · click to fly there` : tip} aria-label={tip} />
                );
              })}
            </span>
          </div>
        );
      })}
    </div>
  );
}
