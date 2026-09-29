import { useEffect, useMemo, useState } from 'react';
import { STATE_LABELS, TIER_LABELS, fetchFunction, hex, type FunctionDetail, type FunctionInstance, type Program } from './api';
import { callersOf, calleesOf, cellName, type ProgramCells } from './state';
import { workstationHref } from './viewRoute';

type Props = {
  program: Program;
  cells: ProgramCells;
  index: number;
  onJump: (index: number) => void;
  onClose: () => void;
};

type Ref = { index: number; name: string; addr: number };

export function Lens({ program, cells, index, onJump, onClose }: Props) {
  const [detail, setDetail] = useState<FunctionDetail | null>(null);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setDetail(null);
    setError('');
    fetchFunction(program.id, index, controller.signal)
      .then(d => !controller.signal.aborted && setDetail(d))
      .catch(e => !controller.signal.aborted && setError(String(e?.message || e)));
    return () => controller.abort();
  }, [program.id, index, attempt]);

  const local = (list: number[]): Ref[] => list.slice(0, 64).map(i => ({ index: i, name: cellName(cells, i), addr: cells.addr[i] }));
  const callers: Ref[] = detail ? detail.callers : local(callersOf(cells, index));
  const callees: Ref[] = detail ? detail.callees : local(calleesOf(cells, index));
  const state = cells.state[index];
  const name = detail?.name || cellName(cells, index);
  const tierNum = detail ? Number(detail.tier) : cells.tier[index];
  const tierName = detail?.tier_name || TIER_LABELS[tierNum] || `Tier ${tierNum}`;
  const refBuild = program.builds.find(b => b.slug === program.ref);

  const rows = useMemo(() => {
    const bySlug = new Map<string, FunctionInstance>();
    for (const inst of detail?.instances || []) if (!bySlug.has(inst.slug)) bySlug.set(inst.slug, inst);
    const recovered = new Set((detail?.recovered || []).filter(r => r.real_c).map(r => r.binary_slug));
    const out = program.builds.map(b => ({ slug: b.slug, platform: b.platform, format: b.format, inst: bySlug.get(b.slug), rec: recovered.has(b.slug) }));
    for (const [slug, inst] of bySlug) if (!program.builds.some(b => b.slug === slug)) out.push({ slug, platform: inst.platform, format: '', inst, rec: recovered.has(slug) });
    return out;
  }, [detail, program.builds]);
  const present = rows.filter(r => r.inst).length;

  return (
    <section className="cp-lens" aria-label={`Function ${name}`}>
      <header className="cp-lens-head">
        <div className="cp-lens-title">
          <h2 title={name}>{name}</h2>
          <div className="cp-lens-meta">
            <span className="cp-mono cp-addr">{hex(cells.addr[index])}</span>
            <span className="cp-mono cp-muted">{(cells.size[index] ?? 0).toLocaleString()} B</span>
            <span className={`cp-chip s${state}`} data-tip={`Map state · ${STATE_LABELS[state]}`}><i className={`cp-swatch s${state}`} />{STATE_LABELS[state]}</span>
            <span className={`cp-chip tier t${tierNum}`} data-tip={`Name tier ${tierNum} · ${tierName} (1 human, 2 debug info, 3 symbols, 4 derived, 5 placeholder)`}>{tierName}</span>
          </div>
        </div>
        <button type="button" className="cp-iconbtn" onClick={onClose} aria-label="Close lens" data-tip="Close · Esc">
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" strokeWidth="1.6" /></svg>
        </button>
      </header>

      <div className="cp-lens-actions">
        <a className="cp-btn primary" href={workstationHref(program.ref, cells.addr[index], 'Decompiler')} data-tip={`Open ${refBuild?.slug || program.ref} at this function in the Code Browser`}>
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M4 3L1 6l3 3M8 3l3 3-3 3" fill="none" stroke="currentColor" strokeWidth="1.5" /></svg>
          Decompile
        </a>
        <a className="cp-btn" href={workstationHref(program.ref, cells.addr[index], 'Disassembly')} data-tip="Open the listing in the Code Browser">Listing</a>
        <a className="cp-btn" href={workstationHref(program.ref, cells.addr[index], 'Graph')} data-tip="Open the call graph in the Code Browser">Graph</a>
      </div>

      <div className="cp-lens-body">
        {error && (
          <div className="cp-lens-error" role="status">
            <span className="cp-dot bad" aria-hidden="true" />
            <span className="cp-mono" title={error}>function detail unavailable</span>
            <button type="button" className="cp-btn" onClick={() => setAttempt(a => a + 1)}>Retry</button>
          </div>
        )}
        {detail?.signature && <pre className="cp-sig" data-tip="Recorded signature">{detail.signature}</pre>}
        {detail?.source_file && <div className="cp-mono cp-muted cp-src" data-tip="Recorded source file">{detail.source_file}</div>}

        <h3 className="cp-h3">
          <span>Every build</span>
          <span className="cp-mono cp-count" data-tip="Builds of this program where the function is bound">{detail ? `${present}/${rows.length}` : `${cells.nb[index]}`}</span>
        </h3>
        <ul className="cp-builds-list" aria-busy={!detail && !error}>
          {rows.map(r => {
            const conf = r.inst ? Math.max(0.06, Math.min(1, Number(r.inst.confidence) || 0)) : 0;
            const tip = r.inst
              ? `${r.slug} · ${hex(r.inst.addr)} · ${r.inst.size} B · ${r.inst.method || 'bound'} · confidence ${(Number(r.inst.confidence) || 0).toFixed(2)}${r.rec ? ' · real C recovered' : ''}`
              : detail ? `${r.slug} · no instance bound` : `${r.slug}`;
            return (
              <li key={r.slug} className={r.inst ? 'present' : detail ? 'absent' : 'pending'} data-tip={tip}>
                <span className="cp-build-name" title={r.slug}>
                  <b className="cp-plat">{(r.platform || '?').slice(0, 3)}</b>
                  {shortSlug(r.slug, program.id)}
                </span>
                {r.inst ? (
                  <a className="cp-mono cp-addr" href={workstationHref(r.slug, r.inst.addr, 'Decompiler')} aria-label={`Open ${r.slug} at ${hex(r.inst.addr)}`}>{hex(r.inst.addr)}</a>
                ) : (
                  <span className="cp-mono cp-muted">{detail ? '—' : '…'}</span>
                )}
                <span className="cp-presence" aria-hidden="true">
                  {r.inst ? <span className={r.rec ? 'rec' : ''} style={{ width: `${conf * 100}%` }} /> : detail ? <span className="hatch" /> : null}
                </span>
              </li>
            );
          })}
        </ul>

        <div className="cp-calls">
          <CallList title="Callers" tip="Functions in the reference build that call this one (yellow edges on the map)" kind="caller" list={callers} onJump={onJump} />
          <CallList title="Callees" tip="Functions this one calls in the reference build (blue edges on the map)" kind="callee" list={callees} onJump={onJump} />
        </div>

        {detail?.decomp && (
          <div className="cp-stats" data-tip="Decompiler output shape for the reference build">
            <Stat k="lines" v={detail.decomp.n_lines} />
            <Stat k="calls" v={detail.decomp.n_calls} />
            <Stat k="nesting" v={detail.decomp.max_nest} />
          </div>
        )}
        {!!detail?.recovered?.length && (
          <>
            <h3 className="cp-h3"><span>Recovered</span><span className="cp-mono cp-count">{detail.recovered.length}</span></h3>
            <ul className="cp-rec-list">
              {detail.recovered.map((r, k) => (
                <li key={`${r.binary_slug}:${r.addr}:${k}`} data-tip={`${r.binary_slug} · ${r.convention || 'convention not recorded'} · ${r.size} B`}>
                  <i className={`cp-swatch ${r.real_c ? 's2' : 's1'}`} />
                  <span className="cp-build-name">{shortSlug(r.binary_slug, program.id)}</span>
                  <span className="cp-mono cp-addr">{hex(r.addr)}</span>
                  <span className="cp-mono cp-muted">{r.real_c ? 'C' : 'lifted'}</span>
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
      <b className="cp-num">{Number.isFinite(v) ? v.toLocaleString() : '—'}</b>
      <small>{k}</small>
    </span>
  );
}

function CallList({ title, tip, kind, list, onJump }: { title: string; tip: string; kind: 'caller' | 'callee'; list: Ref[]; onJump: (i: number) => void }) {
  return (
    <div className={`cp-calllist ${kind}`}>
      <h3 className="cp-h3" data-tip={tip}>
        <span><i className={`cp-edge ${kind}`} aria-hidden="true" />{title}</span>
        <span className="cp-mono cp-count">{list.length}{list.length >= 64 ? '+' : ''}</span>
      </h3>
      <ul>
        {list.map(r => (
          <li key={`${r.index}:${r.addr}`}>
            <button type="button" onClick={() => onJump(r.index)} disabled={!(r.index >= 0)} data-tip={`${r.name} · ${hex(r.addr)}`}>
              <span className="cp-call-name">{r.name}</span>
              <span className="cp-mono cp-addr">{hex(r.addr).replace(/^0x0+/, '0x')}</span>
            </button>
          </li>
        ))}
        {!list.length && <li className="cp-muted cp-none">—</li>}
      </ul>
    </div>
  );
}

/** Strip a program-id prefix like "K1__" so build names stay short. */
export function shortSlug(slug: string, programId: string): string {
  const prefix = `${programId}__`;
  return slug.startsWith(prefix) ? slug.slice(prefix.length) : slug;
}
