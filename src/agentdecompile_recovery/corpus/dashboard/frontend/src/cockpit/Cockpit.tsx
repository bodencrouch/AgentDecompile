// The cockpit: every program in the corpus drawn as a live map of its functions.
// One page: programs × builds on the left, the map in the middle, the lens / product shelf
// on the right, the machine lanes underneath. Everything comes from /dashboard/api/cockpit.
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from 'react';
import { COCKPIT_API, fmt, hex, parseAddr, ratio, useCockpitStream, type Program, type Summary, type Transport } from './api';
import { NO_FILTER, cellName, indexOfAddr, searchCells, type ColorBy, type LiveActivity, type MapFilter, type ProgramCells } from './state';
import { ProgramMap, type FlyRequest } from './ProgramMap';
import { Lens, shortSlug } from './Lens';
import { VariantMatrix } from './VariantMatrix';
import { ActivityLanes } from './ActivityLanes';
import { ProductShelf } from './ProductShelf';
import { CommandStrip } from './CommandStrip';
import { DropZone } from './DropZone';
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
  const [scope, setScope] = useState<string | null>(null);
  const [filter, setFilter] = useState<MapFilter>(NO_FILTER);
  const [colorBy, setColorBy] = useState<ColorBy>('state');
  const [hits, setHits] = useState<number[]>([]);
  const [fly, setFly] = useState<FlyRequest | null>(null);
  const pending = useRef<{ fn?: number; addr?: number }>({ fn: initial.fn });
  const { state, transport, retry, setPaused, paused, queued, cellsError } = useCockpitStream(programId);
  const summary = state.summary;
  const programs = useMemo(() => summary?.programs || [], [summary]);
  const program = programs.find(p => p.id === programId);
  const cells = programId ? state.cells[programId] : undefined;
  const tierNames = useMemo(() => (summary?.tiers || []).map(t => t[0]), [summary]);

  useEffect(() => {
    document.title = 'AgentDecompile · Cockpit';
  }, []);

  // Default to the largest program; drop a selection that no longer exists.
  useEffect(() => {
    if (!summary || !programs.length) return;
    if (!programId || !programs.some(p => p.id === programId)) {
      setProgramId(programs[0].id);
      setSelected(-1);
      setScope(null);
    }
  }, [summary, programs, programId]);

  const flyCount = useRef(0);
  const jump = useCallback((index: number, scale?: number) => {
    setSelected(index);
    setFly({ index, nonce: ++flyCount.current, scale });
  }, []);

  // Restore a function (from the URL or an activity mark) once its program's cells arrive.
  useEffect(() => {
    if (!cells) return;
    const p = pending.current;
    pending.current = {};
    const i = p.fn !== undefined ? p.fn : p.addr !== undefined ? indexOfAddr(cells, p.addr) : -1;
    if (i !== undefined && i >= 0 && i < cells.n) jump(i, 28);
  }, [cells?.programId, cells?.n]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const hash = cockpitHash({ program: programId, fn: selected >= 0 ? selected : undefined });
    if (location.hash !== hash && (location.hash === '' || location.hash.startsWith('#cockpit'))) {
      history.replaceState(history.state, '', `${location.pathname}${location.search}${hash}`);
    }
  }, [programId, selected]);

  const choose = useCallback((id: string) => {
    if (id === programId) return;
    setProgramId(id);
    setSelected(-1);
    setScope(null);
    setHits([]);
    setFilter(NO_FILTER);
  }, [programId]);

  const onScope = useCallback((pid: string, slug: string | null) => {
    choose(pid);
    setScope(slug);
  }, [choose]);

  const canFocus = useCallback((e: LiveActivity) => {
    if (parseAddr(e.addr) === undefined) return false;
    return !e.program_id || programs.some(p => p.id === e.program_id);
  }, [programs]);

  const focusEvent = useCallback((e: LiveActivity) => {
    const a = parseAddr(e.addr);
    if (a === undefined) return;
    const pid = e.program_id && programs.some(p => p.id === e.program_id) ? e.program_id : programId;
    if (!pid) return;
    const target = programs.find(p => p.id === pid);
    if (e.binary && target && e.binary !== target.ref) setScope(target.builds.some(b => b.slug === e.binary) ? e.binary : null);
    if (pid !== programId || !cells) {
      pending.current = { addr: a };
      if (pid !== programId) {
        setProgramId(pid);
        setSelected(-1);
      }
      return;
    }
    const i = indexOfAddr(cells, a);
    if (i >= 0) jump(i, 28);
  }, [programs, programId, cells, jump]);

  // "/" focuses search; Esc outside inputs clears the selection.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      const typing = t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable);
      if (e.key === '/' && !typing) {
        e.preventDefault();
        document.getElementById('cp-search')?.focus();
      } else if (e.key === 'Escape' && !typing && !e.defaultPrevented && selected >= 0 && !(t && t.classList.contains('cp-map-canvas'))) setSelected(-1);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selected]);

  const lensOpen = !!(program && cells && selected >= 0 && selected < cells.n);

  return (
    <div className={`cockpit ${lensOpen ? 'lens-open' : ''}`} ref={rootRef}>
      <TopBar summary={summary} transport={transport} error={state.error} paused={paused} queued={queued} applied={state.applied} onPause={setPaused} />
      <aside className="cp-left" aria-label="Programs">
        <div className="cp-section-h">
          <span>Programs</span>
          <span className="cp-q" tabIndex={0} data-tip="Each row is one program, each cell one of its builds · fill: share bound to a shared identity · green: C with a byte-exact receipt · click a cell to scope the lens to that build">?</span>
        </div>
        {summary ? (
          programs.length ? <VariantMatrix programs={programs} selected={programId} scope={scope} onProgram={choose} onScope={onScope} /> : <div className="cp-empty-mini"><span className="cp-chip dash">0 programs</span></div>
        ) : (
          <div className="cp-matrix" aria-hidden="true"><div className="cp-mrow skeleton" /><div className="cp-mrow skeleton" /></div>
        )}
        <div className="cp-left-foot">
          <DropZone />
          <CommandStrip />
        </div>
      </aside>
      <main className="cp-main" aria-label="Program map">
        <MainArea
          summary={summary} transport={transport} error={state.error} program={program} cells={cells} cellsError={cellsError}
          selected={selected} scope={scope} hits={hits} filter={filter} colorBy={colorBy} tierNames={tierNames} fly={fly} reducedMotion={reducedMotion}
          onRetry={retry} onSelect={setSelected} onJump={jump} onFilter={setFilter} onColorBy={setColorBy} onHits={setHits} onUnscope={() => setScope(null)}
        />
      </main>
      <aside className="cp-right" aria-label={lensOpen ? 'Lens' : 'Products'}>
        {lensOpen ? (
          <>
            <ProductShelf totals={summary?.totals} compact />
            <Lens program={program!} cells={cells!} index={selected} scope={scope} binaries={summary?.totals.binaries ?? 0} tierNames={tierNames}
              onJump={i => jump(i)} onClose={() => setSelected(-1)} />
          </>
        ) : (
          <>
            <div className="cp-section-h"><span>Products</span></div>
            <ProductShelf totals={summary?.totals} compact={false} />
          </>
        )}
      </aside>
      <section className="cp-bottom" aria-label="Machine lanes">
        <ActivityLanes activity={state.activity} paused={paused} onFocusEvent={focusEvent} canFocus={canFocus} />
      </section>
      <TipLayer root={rootRef} />
    </div>
  );
}

function TopBar({ summary, transport, error, paused, queued, applied, onPause }: {
  summary: Summary | undefined; transport: Transport; error?: string; paused: boolean; queued: number; applied: number; onPause: (p: boolean) => void;
}) {
  const t = summary?.totals;
  const dbName = summary?.db?.path ? summary.db.path.split(/[\\/]/).pop() : '';
  const connTip =
    transport === 'stream' ? 'Live stream' :
    transport === 'polling' ? 'Stream unavailable · summary polled every 5 s' :
    transport === 'offline' ? `Cockpit API unreachable${error ? ` · ${error}` : ''}` : 'Connecting';
  const stats: { k: string; v: number | undefined; of?: number; tip: string; color: string }[] = [
    { k: 'binaries', v: t?.binaries, tip: `Binaries in the corpus, grouped into ${fmt(summary?.programs.length)} programs`, color: '--muted' },
    { k: 'functions', v: t?.functions, tip: 'Functions across every build', color: '--muted' },
    { k: 'bound', v: t?.bound, of: t?.functions, tip: 'Build functions bound to a logical function shared across builds', color: '--c-bound' },
    { k: 'named', v: t?.named_above_placeholder, of: t?.named_of, tip: 'Logical functions named above placeholder', color: '--f-verify' },
    { k: 'real C', v: t?.recovered_logical, of: t?.logical, tip: 'Logical functions with C carrying a byte-exact receipt in some build', color: '--c-rec' },
  ];
  return (
    <header className="cp-top">
      <div className="cp-brand">
        <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true"><rect x="1" y="1" width="20" height="20" rx="4" fill="none" stroke="var(--accent)" strokeWidth="1.5" /><rect x="5" y="5" width="4" height="4" fill="var(--c-rec)" /><rect x="10" y="5" width="4" height="4" fill="var(--c-bound)" /><rect x="5" y="10" width="4" height="4" fill="var(--c-bound)" /><rect x="10" y="10" width="4" height="4" fill="var(--c-unbound)" /><rect x="15" y="5" width="2" height="12" fill="var(--accent)" opacity=".5" /></svg>
        AgentDecompile
      </div>
      <div className={`cp-corpus ${transport} ${paused ? 'paused' : ''}`} tabIndex={0}
        data-tip={`${connTip}${summary?.db?.path ? ` · ${summary.db.path}` : ''}${summary?.generated ? ` · generated ${new Date(summary.generated).toLocaleTimeString()}` : ''} · ${fmt(applied)} cell changes applied`}>
        <span className="cp-pulse" aria-hidden="true" />
        <b>{dbName || 'corpus'}</b>
        <span className="cp-mono cp-conn">{transport === 'stream' ? 'live' : transport}</span>
      </div>
      <button type="button" className={`cp-pause ${paused ? 'on' : ''}`} aria-pressed={paused} onClick={() => onPause(!paused)}
        aria-label={paused ? 'Resume live updates' : 'Pause live updates'}
        data-tip={paused ? `Resume · ${fmt(queued)} updates waiting` : 'Pause live updates in this view; updates that arrive meanwhile are applied on resume'}>
        {paused
          ? <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M2.5 1.5l8 4.5-8 4.5z" fill="currentColor" /></svg>
          : <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><rect x="2" y="1.5" width="3" height="9" fill="currentColor" /><rect x="7" y="1.5" width="3" height="9" fill="currentColor" /></svg>}
        {paused && queued > 0 && <span className="cp-badge cp-mono">{queued > 999 ? '999+' : queued}</span>}
      </button>
      <dl className="cp-stats-top">
        {stats.map(s => {
          const f = s.of !== undefined ? ratio(s.v, s.of) : null;
          return (
            <div key={s.k} className="cp-ts" tabIndex={0} data-tip={`${s.tip} · ${fmt(s.v)}${s.of !== undefined ? ` of ${fmt(s.of)}` : ''}`}>
              <dt>{s.k}</dt>
              <dd className="cp-num">{f !== null ? `${(f * 100).toFixed(f < 0.1 ? 1 : 0)}%` : fmt(s.v)}</dd>
              {s.of !== undefined && <span className="cp-ts-bar" aria-hidden="true"><span style={{ width: `${(f ?? 0) * 100}%`, background: `var(${s.color})` }} /></span>}
            </div>
          );
        })}
      </dl>
      <nav className="cp-views" aria-label="Views">
        <a href="#cockpit" aria-current="page">Cockpit</a>
        <a href="#workstation" data-tip="Code Browser, matching, jobs and every workstation view">Workstation</a>
      </nav>
    </header>
  );
}

type MainProps = {
  summary: Summary | undefined;
  transport: Transport;
  error?: string;
  program: Program | undefined;
  cells: ProgramCells | undefined;
  cellsError?: string;
  selected: number;
  scope: string | null;
  hits: number[];
  filter: MapFilter;
  colorBy: ColorBy;
  tierNames: string[];
  fly: FlyRequest | null;
  reducedMotion: boolean;
  onRetry: () => void;
  onSelect: (i: number) => void;
  onJump: (i: number, scale?: number) => void;
  onFilter: (f: MapFilter) => void;
  onColorBy: (c: ColorBy) => void;
  onHits: (h: number[]) => void;
  onUnscope: () => void;
};

function MainArea(p: MainProps) {
  if (!p.summary) {
    return p.transport === 'offline' ? <EmptyState kind="offline" detail={p.error} onRetry={p.onRetry} /> : <EmptyState kind="connecting" />;
  }
  if (!p.summary.programs.length) return <EmptyState kind="empty" />;
  if (!p.program) return <EmptyState kind="connecting" />;
  const scoped = p.scope ? p.program.builds.find(b => b.slug === p.scope) : undefined;
  return (
    <>
      <div className="cp-mainhead">
        <h1 title={p.program.label}>{p.program.label}</h1>
        <span className="cp-chip" data-tip={`Reference build ${p.program.ref}: the map is laid out from its functions, in address order`}>
          {shortSlug(p.program.ref, p.program.id)}<span className="cp-muted">{fmt(p.cells?.n ?? p.program.n)}</span>
        </span>
        {scoped && (
          <span className="cp-chip scope" data-tip={`Lens scoped to ${scoped.slug} · ${fmt(scoped.functions)} functions · ${fmt(scoped.bound)} bound · ${fmt(scoped.real_c)} real C`}>
            {shortSlug(scoped.slug, p.program.id)}
            <button type="button" onClick={p.onUnscope} aria-label="Clear build scope">×</button>
          </span>
        )}
        <Search cells={p.cells} onPick={i => p.onJump(i, 28)} onHits={p.onHits} />
      </div>
      <div className="cp-mapwrap">
        {p.cells ? (
          <ProgramMap cells={p.cells} buildCount={p.program.builds.length} binaries={p.summary.totals.binaries} selected={p.selected} hits={p.hits}
            filter={p.filter} colorBy={p.colorBy} tierNames={p.tierNames} fly={p.fly} reducedMotion={p.reducedMotion}
            onSelect={p.onSelect} onFilter={p.onFilter} onColorBy={p.onColorBy} />
        ) : p.cellsError ? (
          <EmptyState kind="cells-error" detail={p.cellsError} onRetry={p.onRetry} />
        ) : (
          <div className="cp-map-loading" role="status" aria-label="Loading program map"><span /></div>
        )}
      </div>
    </>
  );
}

function Search({ cells, onPick, onHits }: { cells: ProgramCells | undefined; onPick: (i: number) => void; onHits: (h: number[]) => void }) {
  const [q, setQ] = useState('');
  const [active, setActive] = useState(0);
  const [open, setOpen] = useState(false);
  const results = useMemo(() => searchCells(cells, q, 40), [cells, q]);
  useEffect(() => setActive(0), [q]);
  useEffect(() => onHits(q.trim() ? results : []), [results, q, onHits]);
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
        placeholder="name or address" value={q} disabled={!cells} autoComplete="off" spellCheck={false}
        onChange={e => { setQ(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 120)} onKeyDown={onKey}
        data-tip="Search function names or hex addresses · / to focus · Enter flies there; every match is ringed on the map" />
      {q.trim() && cells && <span className="cp-mono cp-muted cp-hitcount">{results.length >= 40 ? '40+' : results.length}</span>}
      <kbd aria-hidden="true">/</kbd>
      {show && (
        <ul id="cp-search-list" role="listbox" className="cp-results" aria-label="Matching functions">
          {results.slice(0, 14).map((i, k) => (
            <li key={i} id={`cp-sr-${i}`} role="option" aria-selected={k === active} className={k === active ? 'on' : ''}
              onMouseDown={e => { e.preventDefault(); pick(i); }} onMouseEnter={() => setActive(k)}>
              <i className={`cp-swatch s${cells!.state[i]}`} aria-hidden="true" />
              <span className="cp-res-name">{cellName(cells!, i)}</span>
              <span className="cp-addr">{hex(cells!.addr[i])}</span>
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
      {(kind === 'empty' || kind === 'offline') && <CommandStrip />}
    </div>
  );
}
