// Lens: everything known about the selected function, from /function plus the loaded cells.
import { useEffect, useMemo, useState } from 'react';
import { STATE_LABELS, STATE_SHORT, fetchFunction, fmt, hex, type FunctionDetail, type FunctionInstance, type Program } from './api';
import { callersOf, calleesOf, cellCounts, cellName, type ProgramCells } from './state';
import { tierLabel } from './ProgramMap';
import { workstationHref } from './viewRoute';

type Props = {
  program: Program;
  cells: ProgramCells;
  index: number;
  scope: string | null;
  binaries: number;
  tierNames: string[];
  onJump: (index: number) => void;
  onClose: () => void;
};

type Ref = { index: number; name: string; addr: number };
const TIER_ORDER = [1, 2, 3, 4, 5, 0];

/** Strip a program-id prefix like "<program>__" so build names stay short. */
export function shortSlug(slug: string, programId: string): string {
  const prefix = `${programId}__`;
  if (slug.startsWith(prefix)) return slug.slice(prefix.length);
  const k = slug.lastIndexOf('__');
  return k > 0 ? slug.slice(k + 2) : slug;
}

export type PresenceRow = { slug: string; platform: string; ref: boolean; instances: FunctionInstance[]; state: 'present' | 'absent' | 'unknown' };

/** One row per build of the program: its instances, or absent (reported by the API), or unknown. */
export function presenceRows(program: Program, detail: FunctionDetail | null): PresenceRow[] {
  const bySlug = new Map<string, FunctionInstance[]>();
  for (const inst of detail?.instances || []) bySlug.set(inst.slug, [...(bySlug.get(inst.slug) || []), inst]);
  const absent = new Set(detail?.absent || []);
  const builds = [...program.builds].sort((a, b) => Number(b.slug === program.ref) - Number(a.slug === program.ref) || b.functions - a.functions);
  const rows: PresenceRow[] = builds.map(b => {
    const instances = bySlug.get(b.slug) || [];
    return { slug: b.slug, platform: b.platform, ref: b.slug === program.ref, instances, state: instances.length ? 'present' : absent.has(b.slug) ? 'absent' : 'unknown' };
  });
  for (const [slug, instances] of bySlug) {
    if (!program.builds.some(b => b.slug === slug)) rows.push({ slug, platform: instances[0].platform, ref: false, instances, state: 'present' });
  }
  return rows;
}

export function Lens({ program, cells, index, scope, binaries, tierNames, onJump, onClose }: Props) {
  const [detail, setDetail] = useState<FunctionDetail | null>(null);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setError('');
    fetchFunction(program.id, index, controller.signal)
      .then(d => !controller.signal.aborted && setDetail(d))
      .catch(e => !controller.signal.aborted && (setDetail(null), setError(String(e?.message || e))));
    return () => controller.abort();
  }, [program.id, index, attempt]);
  useEffect(() => setDetail(null), [program.id, index]);

  // A live change to this cell refetches its detail.
  useEffect(() => {
    if (cells.changed.includes(index)) setAttempt(a => a + 1);
  }, [cells.version]); // eslint-disable-line react-hooks/exhaustive-deps

  const local = (list: number[]): Ref[] => list.slice(0, 64).map(i => ({ index: i, name: cellName(cells, i), addr: cells.addr[i] }));
  const callers: Ref[] = detail?.callers.length ? detail.callers : local(callersOf(cells, index));
  const callees: Ref[] = detail?.callees.length ? detail.callees : local(calleesOf(cells, index));
  const nIn = cells.inStart[index + 1] - cells.inStart[index], nOut = cells.outStart[index + 1] - cells.outStart[index];
  const state = cells.state[index];
  const name = detail?.name || cellName(cells, index);
  const tierNum = detail ? Number(detail.tier) || 0 : cells.tier[index];
  const rows = useMemo(() => presenceRows(program, detail), [program, detail]);
  const present = rows.filter(r => r.state === 'present').length;
  const counts = useMemo(() => cellCounts(cells), [cells]);
  const methods = useMemo(() => {
    const m = new Map<string, { n: number; c: number; k: number }>();
    for (const i of detail?.instances || []) {
      if (!i.method) continue;
      const e = m.get(i.method) || { n: 0, c: 0, k: 0 };
      e.n++;
      if (i.confidence !== null) { e.c += i.confidence; e.k++; }
      m.set(i.method, e);
    }
    return [...m.entries()];
  }, [detail]);

  // Code Browser target: the scoped build's instance, else the reference build's, else the cell itself.
  const open = (() => {
    const pick = (slug: string) => rows.find(r => r.slug === slug && r.instances.length)?.instances[0];
    const inst = (scope && pick(scope)) || pick(program.ref);
    return inst ? { slug: inst.slug, addr: inst.addr } : { slug: cells.ref || program.ref, addr: cells.addr[index] };
  })();
  const logicalId = detail?.logical_id ?? (cells.logical[index] || null);

  return (
    <section className="cp-lens" aria-label={`Function ${name}`}>
      <header className="cp-lens-head">
        <div className="cp-lens-title">
          <h2 title={name}>{name}</h2>
          <div className="cp-lens-meta">
            <span className="cp-addr">{hex(cells.addr[index])}</span>
            <span className="cp-mono cp-muted">{fmt(cells.size[index] ?? 0)} B</span>
            <span className="cp-mono cp-muted">#{index}</span>
          </div>
        </div>
        <button type="button" className="cp-iconbtn" onClick={onClose} aria-label="Close lens" data-tip="Close · Esc">
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" strokeWidth="1.6" /></svg>
        </button>
      </header>

      <div className="cp-lens-chips">
        <span className={`cp-chip s${state}`} data-tip={STATE_LABELS[state]}><i className={`cp-swatch s${state}`} />{STATE_SHORT[state]}</span>
        <span className="cp-chip" data-tip="Binaries across the corpus holding a bound instance">{fmt(cells.nb[index])}{binaries ? ` / ${fmt(binaries)}` : ''}</span>
        {logicalId ? <span className="cp-chip" data-tip="Logical function shared by every bound instance">L{logicalId}</span> : null}
        {detail?.source_file && <span className="cp-chip" data-tip={`Source file recorded for this function · ${detail.source_file}`}>{detail.source_file.split(/[\\/]/).pop()}</span>}
      </div>

      <div className="cp-lens-actions">
        <a className="cp-btn primary" href={workstationHref(open.slug, open.addr, 'Decompiler')} data-tip={`Open ${open.slug} at ${hex(open.addr)} in the Code Browser`}>
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M4 3L1 6l3 3M8 3l3 3-3 3" fill="none" stroke="currentColor" strokeWidth="1.5" /></svg>
          Open in Code Browser
        </a>
        <a className="cp-iconbtn" href={workstationHref(open.slug, open.addr, 'Disassembly')} aria-label="Listing" data-tip="Listing">
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M1 2h10M1 5h7M1 8h10M1 11h5" stroke="currentColor" strokeWidth="1.3" /></svg>
        </a>
        <a className="cp-iconbtn" href={workstationHref(open.slug, open.addr, 'Graph')} aria-label="Graph" data-tip="Control-flow graph">
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><rect x="4" y="1" width="4" height="3" fill="none" stroke="currentColor" /><rect x="1" y="8" width="4" height="3" fill="none" stroke="currentColor" /><rect x="7" y="8" width="4" height="3" fill="none" stroke="currentColor" /><path d="M6 4v2M3 8V6h6v2" fill="none" stroke="currentColor" /></svg>
        </a>
      </div>

      <div className="cp-lens-body">
        {error && (
          <div className="cp-lens-error" role="status" data-tip={error}>
            <span className="cp-dot bad" aria-hidden="true" />
            <span className="cp-mono">detail unavailable</span>
            <button type="button" className="cp-btn" onClick={() => setAttempt(a => a + 1)}>Retry</button>
          </div>
        )}

        <h3 className="cp-h3">
          <span>Every build</span>
          <span className="cp-mono cp-count" data-tip="Builds of this program holding an instance">{detail ? `${present}/${rows.length}` : '…'}</span>
        </h3>
        <ul className="cp-builds-list" aria-busy={!detail && !error}>
          {rows.map(r => {
            const inst = r.instances[0];
            const conf = inst?.confidence ?? null;
            const tip = r.state === 'present'
              ? `${r.slug} · ${r.instances.length} instance${r.instances.length > 1 ? 's' : ''} · ${hex(inst.addr)}${conf !== null ? ` · confidence ${Math.round(conf * 100)}%` : ''}${inst.method ? ` · ${inst.method}` : ''}${r.ref ? ' · reference build (the map is laid out from it)' : ''}`
              : r.state === 'absent' ? `${r.slug} · no counterpart in this build` : `${r.slug} · not reported`;
            return (
              <li key={r.slug} className={`${r.state} ${scope === r.slug ? 'scoped' : ''} ${r.ref ? 'ref' : ''}`} data-tip={tip}>
                <span className="cp-build-name"><b className="cp-plat">{(r.platform || '?').slice(0, 3)}</b>{shortSlug(r.slug, program.id)}</span>
                <span className="cp-presence" aria-hidden="true">
                  {r.state === 'present'
                    ? <span className={r.ref ? 'ref' : ''} style={{ width: `${Math.max(18, (conf ?? 1) * 100)}%`, opacity: conf === null ? 1 : 0.45 + 0.55 * conf }} />
                    : r.state === 'absent' ? <span className="hatch" /> : null}
                </span>
                {inst ? (
                  <a className="cp-addr" href={workstationHref(r.slug, inst.addr, 'Decompiler')} aria-label={`Open ${r.slug} at ${hex(inst.addr)}`}>
                    {hex(inst.addr).replace(/^0x0*/, '')}{r.instances.length > 1 ? ` ×${r.instances.length}` : ''}
                  </a>
                ) : <span className="cp-mono cp-muted">{r.state === 'absent' ? '∅' : detail ? '–' : '…'}</span>}
              </li>
            );
          })}
        </ul>

        <h3 className="cp-h3" data-tip="Real call edges in the reference build · blue: calls, amber: called by">
          <span>Calls</span><span className="cp-mono cp-count">↑{nIn} ↓{nOut}</span>
        </h3>
        <CallFan name={name} callers={callers} callees={callees} onJump={onJump} />
        <div className="cp-calls">
          <CallList kind="caller" list={callers} total={nIn} onJump={onJump} />
          <CallList kind="callee" list={callees} total={nOut} onJump={onJump} />
        </div>

        <h3 className="cp-h3" data-tip="Where the name came from; a weaker source never overwrites a stronger one"><span>Name</span><span className="cp-mono cp-count">{detail?.tier_name || tierLabel(tierNames, tierNum)}</span></h3>
        <div className="cp-tierbar" role="img" aria-label={`Name tier ${tierLabel(tierNames, tierNum)}`}>
          {TIER_ORDER.filter(t => counts.tiers[t] > 0 || t === tierNum).map(t => (
            <span key={t} className={`t${t} ${t === tierNum ? 'me' : ''}`} style={{ flexGrow: Math.max(counts.tiers[t], 1) }}
              data-tip={`${tierLabel(tierNames, t)} · ${fmt(counts.tiers[t])} functions in this program`} />
          ))}
        </div>
        {methods.length > 0 && (
          <div className="cp-lens-chips">
            {methods.map(([m, e]) => (
              <span key={m} className="cp-chip mini" data-tip={`${e.n} instance(s) bound by ${m}${e.k ? `, mean confidence ${Math.round((100 * e.c) / e.k)}%` : ''}`}>
                {m.length > 26 ? `${m.slice(0, 25)}…` : m}{e.k ? ` ${Math.round((100 * e.c) / e.k)}%` : ''}
              </span>
            ))}
          </div>
        )}
        {detail?.signature && <pre className="cp-sig" data-tip="Recorded signature">{detail.signature}</pre>}

        {detail?.decomp && (
          <div className="cp-stats" data-tip="Shape of the decompiled output">
            <Stat k="lines" v={detail.decomp.n_lines} />
            <Stat k="calls" v={detail.decomp.n_calls} />
            <Stat k="nesting" v={detail.decomp.max_nest} />
          </div>
        )}
        {!!detail?.recovered?.length && (
          <>
            <h3 className="cp-h3" data-tip="Recovered rows with a recorded byte-exact receipt"><span>Recovered</span><span className="cp-mono cp-count">{detail.recovered.length}</span></h3>
            <ul className="cp-rec-list">
              {detail.recovered.map((r, k) => (
                <li key={`${r.binary_slug}:${r.addr}:${k}`}>
                  <a href={workstationHref(r.binary_slug, r.addr, 'Decompiler')} data-tip={`${r.name || name} · ${r.binary_slug} · ${r.convention || 'convention not recorded'} · ${fmt(r.size)} B`}>
                    <i className={`cp-swatch ${r.real_c ? 's2' : 's1'}`} />
                    <span className="cp-build-name">{shortSlug(r.binary_slug, program.id)}</span>
                    <span className="cp-addr">{hex(r.addr).replace(/^0x0*/, '')}</span>
                    <span className="cp-mono cp-muted">{r.real_c ? 'C' : '–'}</span>
                  </a>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </section>
  );
}

function Stat({ k, v }: { k: string; v: number }) {
  return (
    <span className="cp-stat">
      <b className="cp-num">{fmt(v)}</b>
      <small>{k}</small>
    </span>
  );
}

const trunc = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

/** Callers fan in from the left, callees fan out to the right; every node flies to its cell. */
function CallFan({ name, callers, callees, onJump }: { name: string; callers: Ref[]; callees: Ref[]; onJump: (i: number) => void }) {
  const ins = callers.slice(0, 6), outs = callees.slice(0, 6);
  const rows = Math.max(ins.length, outs.length, 1), rh = 22, H = rows * rh + 12, W = 320, cy = H / 2;
  const yAt = (k: number, len: number) => cy + (k - (len - 1) / 2) * rh;
  const node = (r: Ref, x: number, y: number, cls: string) => (
    <g key={`${cls}${r.index}:${r.addr}`} className={`cp-fan-node ${cls}`} role="button" tabIndex={r.index >= 0 ? 0 : -1}
      onClick={() => r.index >= 0 && onJump(r.index)} onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && r.index >= 0 && (e.preventDefault(), onJump(r.index))}
      data-tip={`${r.name} · ${hex(r.addr)}`} aria-label={r.name}>
      <rect x={x} y={y - 9} width={100} height={18} rx={4} />
      <text x={x + 6} y={y + 4}>{trunc(r.name, 14)}</text>
    </g>
  );
  return (
    <svg className="cp-fan" viewBox={`0 0 ${W} ${H}`} role="group" aria-label={`${callers.length} callers, ${callees.length} callees`}>
      {ins.map((_, k) => { const y = yAt(k, ins.length); return <path key={`pi${k}`} className="caller" d={`M102 ${y} C 112 ${y}, 106 ${cy}, 116 ${cy}`} />; })}
      {outs.map((_, k) => { const y = yAt(k, outs.length); return <path key={`po${k}`} className="callee" d={`M204 ${cy} C 214 ${cy}, 208 ${y}, 218 ${y}`} />; })}
      {ins.map((r, k) => node(r, 2, yAt(k, ins.length), 'caller'))}
      {outs.map((r, k) => node(r, 218, yAt(k, outs.length), 'callee'))}
      <rect className="cp-fan-me" x={116} y={cy - 12} width={88} height={24} rx={5} />
      <text className="cp-fan-me-t" x={160} y={cy + 4} textAnchor="middle">{trunc(name, 12)}</text>
      {!ins.length && <text className="cp-fan-none" x={52} y={cy + 4} textAnchor="middle">∅</text>}
      {!outs.length && <text className="cp-fan-none" x={268} y={cy + 4} textAnchor="middle">∅</text>}
    </svg>
  );
}

function CallList({ kind, list, total, onJump }: { kind: 'caller' | 'callee'; list: Ref[]; total: number; onJump: (i: number) => void }) {
  return (
    <div className={`cp-calllist ${kind}`}>
      <ul aria-label={kind === 'caller' ? 'Called by' : 'Calls'}>
        {list.map(r => (
          <li key={`${r.index}:${r.addr}`}>
            <button type="button" onClick={() => onJump(r.index)} disabled={!(r.index >= 0)} data-tip={`${r.name} · ${hex(r.addr)}`}>
              <i className={`cp-edge ${kind}`} aria-hidden="true" />
              <span className="cp-call-name">{r.name}</span>
            </button>
          </li>
        ))}
        {total > list.length && <li className="cp-muted cp-more cp-mono">+{fmt(total - list.length)}</li>}
        {!list.length && <li className="cp-muted cp-none">∅</li>}
      </ul>
    </div>
  );
}
