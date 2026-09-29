import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from 'react';
import { COCKPIT_API, STATE_LABELS, TIER_LABELS, fmt, hex, type Program, type Summary } from './api';
import { ALL, cellCounts, cellName, searchCells, type LiveActivity, type MapFilter, type ProgramCells } from './state';
import { useCockpitFeed } from './useCockpitFeed';
import { MapCanvas, type FlyRequest } from './MapCanvas';
import { Lens, shortSlug } from './Lens';
import { Lanes } from './Lanes';
import { Shelf } from './Shelf';
import { CliStrip, DropZone } from './DropZone';
import { TipLayer } from './Tips';
import { cockpitHash, readCockpitHash } from './viewRoute';
import './cockpit.css';

function useReducedMotion() {
  const [reduced, setReduced] = useState(() => typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches);
  useEffect(() => {
    if (typeof matchMedia !== 'function') return;
    const m = matchMedia('(prefers-reduced-motion: reduce)');
    const on = () => setReduced(m.matches);
    m.addEventListener('change', on);
    return () => m.removeEventListener('change', on);
  }, []);
  return reduced;
}

const initial = readCockpitHash(typeof location === 'undefined' ? '' : location.hash);

export function Cockpit() {
  const rootRef = useRef<HTMLDivElement>(null);
  const reducedMotion = useReducedMotion();
  const [programId, setProgramId] = useState<string | undefined>(initial.program);
  const [selected, setSelected] = useState(-1);
  const [filter, setFilter] = useState<MapFilter>(ALL);
  const [fly, setFly] = useState<FlyRequest | null>(null);
  const pendingFn = useRef(initial.fn);
  const { state, retry, cellsError } = useCockpitFeed(programId);
  const summary = state.summary;
  const programs = summary?.programs || [];
  const program = programs.find(p => p.id === programId);
  const cells = programId ? state.cells[programId] : undefined;

  useEffect(() => {
    document.title = 'AgentDecompile · Cockpit';
  }, []);

  // Default to the first program; drop a selection that no longer exists.
  useEffect(() => {
    if (!summary || !programs.length) return;
    if (!programId || !programs.some(p => p.id === programId)) {
      setProgramId(programs[0].id);
      setSelected(-1);
    }
  }, [summary, programs, programId]);

  // Restore a function from the URL once its program's cells arrive.
  useEffect(() => {
    if (cells && pendingFn.current !== undefined) {
      const fn = pendingFn.current;
      pendingFn.current = undefined;
      if (fn < cells.n) {
        setSelected(fn);
        setFly({ index: fn, nonce: Date.now() });
      }
    }
  }, [cells]);

  useEffect(() => {
    const hash = cockpitHash({ program: programId, fn: selected >= 0 ? selected : undefined });
    if (location.hash !== hash && (location.hash === '' || location.hash.startsWith('#cockpit'))) {
      history.replaceState(history.state, '', `${location.pathname}${location.search}${hash}`);
    }
  }, [programId, selected]);

  const choose = useCallback((id: string) => {
    setProgramId(id);
    setSelected(-1);
    setFilter(ALL);
  }, []);

  const jump = useCallback((index: number, scale?: number) => {
    setSelected(index);
    setFly({ index, nonce: Date.now() + Math.random(), scale });
  }, []);

  const addrIndex = useMemo(() => {
    const m = new Map<number, number>();
    if (cells) cells.addr.forEach((a, i) => m.set(a, i));
    return m;
  }, [cells?.programId, cells?.n]); // eslint-disable-line react-hooks/exhaustive-deps

  const focusEvent = useCallback((e: LiveActivity) => {
    if (!cells || !program || e.addr === undefined) return;
    if (e.program_id && e.program_id !== program.id) return;
    if (e.binary && e.binary !== program.ref) return; // the map shows the reference build only
    const a = typeof e.addr === 'number' ? e.addr : parseInt(String(e.addr).replace(/^0x/i, ''), 16);
    const i = addrIndex.get(a);
    if (i !== undefined) jump(i, 32);
  }, [cells, program, addrIndex, jump]);

  // Esc closes the lens from anywhere outside inputs.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      const typing = t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable);
      if (e.key === '/' && !typing) {
        e.preventDefault();
        document.getElementById('cp-search')?.focus();
      }
      if (e.key === 'Escape' && !typing && !e.defaultPrevented && selected >= 0 && !(t && t.classList.contains('cp-map-canvas'))) setSelected(-1);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selected]);

  const lensOpen = !!(program && cells && selected >= 0 && selected < cells.n);

  return (
    <div className={`cockpit ${lensOpen ? 'lens-open' : ''}`} ref={rootRef}>
      <TopBar summary={summary} connection={state.connection} error={state.error} />
      <aside className="cp-left" aria-label="Programs">
        <DropZone />
        <div className="cp-section-h">
          <span>Programs</span>
          <span className="cp-q" tabIndex={0} data-tip="Each program groups its builds · bars: blue bound to the shared identity, green byte-matching C">?</span>
        </div>
        <ProgramList programs={programs} selected={programId} onChoose={choose} loading={!summary} />
        <CliStrip />
      </aside>
      <main className="cp-main" aria-label="Program map">
        <MainArea
          summary={summary}
          connection={state.connection}
          error={state.error}
          program={program}
          cells={cells}
          cellsError={cellsError}
          selected={selected}
          filter={filter}
          fly={fly}
          reducedMotion={reducedMotion}
          onRetry={retry}
          onSelect={i => setSelected(i)}
          onJump={jump}
          onFilter={setFilter}
        />
      </main>
      <aside className="cp-right" aria-label={lensOpen ? 'Lens' : 'Products'}>
        {lensOpen ? (
          <>
            <Shelf totals={summary?.totals} compact />
            <Lens program={program!} cells={cells!} index={selected} onJump={i => jump(i)} onClose={() => setSelected(-1)} />
          </>
        ) : (
          <>
            <div className="cp-section-h"><span>Products</span></div>
            <Shelf totals={summary?.totals} compact={false} />
          </>
        )}
      </aside>
      <section className="cp-bottom" aria-label="Activity lanes">
        <Lanes activity={state.activity} reducedMotion={reducedMotion} onFocusEvent={focusEvent} />
      </section>
      <TipLayer root={rootRef} />
    </div>
  );
}

function TopBar({ summary, connection, error }: { summary: Summary | undefined; connection: string; error?: string }) {
  const t = summary?.totals;
  const dbName = summary?.db?.path ? summary.db.path.split(/[\\/]/).pop() : '';
  const connTip =
    connection === 'live' ? 'Live stream connected' :
    connection === 'polling' ? 'Stream unavailable · summary refreshed every 5 s' :
    connection === 'offline' ? `Cockpit API unreachable${error ? ` · ${error}` : ''}` : 'Connecting';
  const stats: [string, number | undefined, string, string][] = [
    ['binaries', t?.binaries, 'Binaries in the corpus', ''],
    ['functions', t?.functions, 'Functions across every build', ''],
    ['logical', t?.logical, 'Logical functions: one identity shared by every build', ''],
    ['bound', t?.bound, 'Build functions bound to a logical function', 'var(--c-bound-named)'],
    ['recovered', t?.recovered_logical, 'Logical functions with byte-matching C', 'var(--c-rec)'],
  ];
  return (
    <header className="cp-top">
      <div className="cp-brand">
        <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true"><rect x="1" y="1" width="20" height="20" rx="4" fill="none" stroke="var(--accent)" strokeWidth="1.5" /><path d="M5 15 L9 7 L13 13 L17 6" fill="none" stroke="var(--f-source)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /><circle cx="17" cy="6" r="1.8" fill="var(--f-unify)" /></svg>
        AgentDecompile
      </div>
      <div className={`cp-corpus ${connection}`} tabIndex={0} data-tip={`${connTip}${summary?.db?.path ? ` · ${summary.db.path}` : ''}${summary?.generated ? ` · ${new Date(summary.generated).toLocaleTimeString()}` : ''}`}>
        <span className="cp-pulse" aria-hidden="true" />
        <b>{dbName || 'corpus'}</b>
        <span className="cp-mono cp-conn">{connection === 'polling' ? 'polling' : connection}</span>
      </div>
      <dl className="cp-stats-top">
        {stats.map(([k, v, tip, color]) => (
          <div key={k} className="cp-ts" tabIndex={0} data-tip={tip}>
            {color && <i style={{ background: color }} aria-hidden="true" />}
            <dt>{k}</dt>
            <dd className="cp-num">{fmt(v)}</dd>
          </div>
        ))}
      </dl>
      <nav className="cp-views" aria-label="Views">
        <a href="#cockpit" aria-current="page">Cockpit</a>
        <a href="#workstation" data-tip="Code Browser, matching, jobs and every workstation view">Workstation</a>
      </nav>
    </header>
  );
}

function ProgramList({ programs, selected, onChoose, loading }: { programs: Program[]; selected?: string; onChoose: (id: string) => void; loading: boolean }) {
  if (loading) return <div className="cp-programs"><div className="cp-prog skeleton" aria-hidden="true" /><div className="cp-prog skeleton" aria-hidden="true" /></div>;
  return (
    <ul className="cp-programs">
      {programs.map(p => {
        const fns = p.builds.reduce((s, b) => s + (b.functions || 0), 0);
        return (
          <li key={p.id}>
            <button type="button" className={`cp-prog ${p.id === selected ? 'on' : ''}`} aria-pressed={p.id === selected} onClick={() => onChoose(p.id)}
              data-tip={`${p.label} · ${p.builds.length} builds · ${fmt(fns)} functions · map: ${shortSlug(p.ref, p.id)}`}>
              <span className="cp-prog-h">
                <span className="cp-prog-name">{p.label}</span>
                <span className="cp-mono cp-muted">{fmt(p.n)}</span>
              </span>
              <span className="cp-variants" aria-hidden="true">
                {p.builds.map(b => {
                  const f = Math.max(1, b.functions || 0);
                  return (
                    <span key={b.slug} className={`cp-vchip ${b.slug === p.ref ? 'ref' : ''}`}
                      data-tip={`${shortSlug(b.slug, p.id)} · ${b.platform}${b.format ? `/${b.format}` : ''} · ${fmt(b.functions)} fns · ${fmt(b.bound)} bound · ${fmt(b.real_c)} C`}>
                      <span className="b" style={{ height: `${Math.min(100, ((b.bound || 0) / f) * 100)}%` }} />
                      <span className="r" style={{ height: `${Math.min(100, ((b.real_c || 0) / f) * 100)}%` }} />
                      <span className="p">{(b.platform || '?').slice(0, 1).toUpperCase()}</span>
                    </span>
                  );
                })}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

type MainProps = {
  summary: Summary | undefined;
  connection: string;
  error?: string;
  program: Program | undefined;
  cells: ProgramCells | undefined;
  cellsError?: string;
  selected: number;
  filter: MapFilter;
  fly: FlyRequest | null;
  reducedMotion: boolean;
  onRetry: () => void;
  onSelect: (i: number) => void;
  onJump: (i: number, scale?: number) => void;
  onFilter: (f: MapFilter) => void;
};

function MainArea(p: MainProps) {
  if (!p.summary) {
    return p.connection === 'offline'
      ? <EmptyState kind="offline" detail={p.error} onRetry={p.onRetry} />
      : <EmptyState kind="connecting" />;
  }
  if (!p.summary.programs.length) return <EmptyState kind="empty" />;
  if (!p.program) return <EmptyState kind="connecting" />;
  const counts = cellCounts(p.cells);
  const buildCount = p.program.builds.length;
  return (
    <>
      <div className="cp-mainhead">
        <h1>{p.program.label}</h1>
        <span className="cp-chip" data-tip="Reference build: every function in address order">{shortSlug(p.program.ref, p.program.id)}</span>
        <Search cells={p.cells} onPick={i => p.onJump(i, 48)} />
      </div>
      <Legend counts={counts} filter={p.filter} onFilter={p.onFilter} disabled={!p.cells} />
      <div className="cp-mapwrap">
        {p.cells ? (
          <MapCanvas cells={p.cells} buildCount={buildCount} selected={p.selected} filter={p.filter} fly={p.fly} reducedMotion={p.reducedMotion}
            onSelect={i => i >= 0 ? p.onSelect(i) : p.onSelect(-1)} />
        ) : p.cellsError ? (
          <EmptyState kind="cells-error" detail={p.cellsError} onRetry={p.onRetry} />
        ) : (
          <div className="cp-map-loading" role="status" aria-label="Loading program map"><span /></div>
        )}
      </div>
    </>
  );
}

function Legend({ counts, filter, onFilter, disabled }: { counts: ReturnType<typeof cellCounts>; filter: MapFilter; onFilter: (f: MapFilter) => void; disabled: boolean }) {
  const toggle = (f: MapFilter) => onFilter(JSON.stringify(f) === JSON.stringify(filter) ? ALL : f);
  const tips = [
    'No shared identity yet · click to highlight',
    'Bound to a logical function shared across builds · click to highlight',
    'Byte-matching C recovered · click to highlight',
  ];
  return (
    <div className="cp-legend" role="toolbar" aria-label="Highlight">
      {[0, 1, 2].map(s => (
        <button key={s} type="button" className="cp-lg" aria-pressed={filter.kind === 'state' && filter.value === s} disabled={disabled}
          onClick={() => toggle({ kind: 'state', value: s })} data-tip={`${STATE_LABELS[s]} · ${tips[s]}`}>
          <i className={`cp-swatch s${s}`} />{STATE_LABELS[s]}<span className="cp-mono">{fmt(counts.states[s])}</span>
        </button>
      ))}
      <button type="button" className="cp-lg" aria-pressed={filter.kind === 'named'} disabled={disabled}
        onClick={() => toggle({ kind: 'named' })} data-tip="Named from human, debug-info or symbol sources · corner notch when zoomed in · click to highlight">
        <i className="cp-swatch named" />Named<span className="cp-mono">{fmt(counts.named)}</span>
      </button>
      <label className="cp-tier" data-tip="Highlight one name tier">
        <span className="cp-sr">Highlight name tier</span>
        <select disabled={disabled} value={filter.kind === 'tier' ? String(filter.value) : ''}
          onChange={e => onFilter(e.target.value === '' ? ALL : { kind: 'tier', value: Number(e.target.value) })}>
          <option value="">All tiers</option>
          {[1, 2, 3, 4, 5, 0].map(t => <option key={t} value={t}>{t ? `${t} · ` : ''}{TIER_LABELS[t]}</option>)}
        </select>
      </label>
      {filter.kind !== 'all' && (
        <button type="button" className="cp-iconbtn" onClick={() => onFilter(ALL)} aria-label="Clear highlight" data-tip="Clear highlight">
          <svg width="10" height="10" viewBox="0 0 12 12" aria-hidden="true"><path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" strokeWidth="1.6" /></svg>
        </button>
      )}
    </div>
  );
}

function Search({ cells, onPick }: { cells: ProgramCells | undefined; onPick: (i: number) => void }) {
  const [q, setQ] = useState('');
  const [active, setActive] = useState(0);
  const [open, setOpen] = useState(false);
  const results = useMemo(() => searchCells(cells, q, 12), [cells, q]);
  useEffect(() => setActive(0), [q]);
  const pick = (i: number) => {
    onPick(i);
    setOpen(false);
  };
  const onKey = (e: ReactKeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setOpen(true); setActive(a => Math.min(results.length - 1, a + 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(a => Math.max(0, a - 1)); }
    else if (e.key === 'Enter' && results[active] !== undefined) { e.preventDefault(); pick(results[active]); }
    else if (e.key === 'Escape') { e.preventDefault(); if (open && q) setOpen(false); else { setQ(''); (e.target as HTMLInputElement).blur(); } }
  };
  const show = open && q.trim() !== '' && !!cells;
  return (
    <div className="cp-search">
      <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><circle cx="5" cy="5" r="3.6" fill="none" stroke="currentColor" strokeWidth="1.5" /><path d="M8 8l3 3" stroke="currentColor" strokeWidth="1.5" /></svg>
      <input id="cp-search" type="search" role="combobox" aria-expanded={show} aria-controls="cp-search-list" aria-autocomplete="list"
        aria-activedescendant={show && results.length ? `cp-sr-${results[active]}` : undefined}
        placeholder="Function or address" value={q} disabled={!cells} autoComplete="off" spellCheck={false}
        onChange={e => { setQ(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 120)} onKeyDown={onKey}
        data-tip="Search names or hex addresses · / to focus · Enter flies there" />
      <kbd aria-hidden="true">/</kbd>
      {show && (
        <ul id="cp-search-list" role="listbox" className="cp-results" aria-label="Matching functions">
          {results.map((i, k) => (
            <li key={i} id={`cp-sr-${i}`} role="option" aria-selected={k === active} className={k === active ? 'on' : ''}
              onMouseDown={e => { e.preventDefault(); pick(i); }} onMouseEnter={() => setActive(k)}>
              <i className={`cp-swatch s${cells!.state[i]}`} aria-hidden="true" />
              <span className="cp-res-name">{cellName(cells!, i)}</span>
              <span className="cp-mono cp-addr">{hex(cells!.addr[i])}</span>
            </li>
          ))}
          {!results.length && <li className="cp-none cp-muted" role="option" aria-selected={false} aria-disabled="true">0</li>}
        </ul>
      )}
    </div>
  );
}

function EmptyState({ kind, detail, onRetry }: { kind: 'offline' | 'connecting' | 'empty' | 'cells-error'; detail?: string; onRetry?: () => void }) {
  const title = kind === 'offline' ? 'Cockpit API unreachable' : kind === 'empty' ? 'No programs yet' : kind === 'cells-error' ? 'Program map unavailable' : 'Connecting';
  return (
    <div className={`cp-empty ${kind}`} role={kind === 'connecting' ? 'status' : undefined}>
      <svg className="cp-empty-art" width="132" height="84" viewBox="0 0 132 84" aria-hidden="true">
        {Array.from({ length: 6 * 11 }, (_, k) => (
          <rect key={k} x={2 + (k % 11) * 12} y={2 + Math.floor(k / 11) * 14} width="9" height="11" rx="1.5"
            className={kind === 'connecting' ? 'pulse' : ''} style={kind === 'connecting' ? { animationDelay: `${(k % 11) * 60}ms` } : undefined} />
        ))}
        {kind === 'offline' && <path d="M52 30l28 28M80 30L52 58" className="x" />}
      </svg>
      <h2>{title}</h2>
      {(kind === 'offline' || kind === 'cells-error') && (
        <p className="cp-mono cp-muted" data-tip={detail || ''}>{kind === 'offline' ? `${COCKPIT_API}/summary` : detail}</p>
      )}
      {onRetry && <button type="button" className="cp-btn primary" onClick={onRetry}>Retry</button>}
      {(kind === 'empty' || kind === 'offline') && <CliStrip />}
    </div>
  );
}
