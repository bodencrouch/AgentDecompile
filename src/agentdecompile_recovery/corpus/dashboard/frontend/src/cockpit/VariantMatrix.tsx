// Every binary as one: programs (rows) × their builds (cells). Fill = share of the build's
// functions bound to a shared identity; the green cap = C with a byte-exact receipt.
import { fmt, ratio, type Build, type Program } from './api';
import { shortSlug } from './Lens';

type Props = {
  programs: Program[];
  selected?: string;
  scope: string | null;
  onProgram: (id: string) => void;
  onScope: (programId: string, slug: string | null) => void;
};

export function orderedBuilds(p: Program): Build[] {
  return [...p.builds].sort((a, b) => Number(b.slug === p.ref) - Number(a.slug === p.ref) || b.functions - a.functions || a.slug.localeCompare(b.slug));
}

const pct = (f: number | null) => (f === null ? '–' : `${(f * 100).toFixed(f < 0.1 && f > 0 ? 1 : 0)}%`);

export function VariantMatrix({ programs, selected, scope, onProgram, onScope }: Props) {
  if (!programs.length) return null;
  return (
    <div className="cp-matrix" role="grid" aria-label="Programs and their builds">
      {programs.map(p => {
        const fns = p.builds.reduce((s, b) => s + (b.functions || 0), 0);
        const bound = p.builds.reduce((s, b) => s + (b.bound || 0), 0);
        const pb = ratio(bound, fns);
        return (
          <div key={p.id} role="row" className={`cp-mrow ${p.id === selected ? 'on' : ''}`}>
            <button type="button" role="rowheader" className="cp-mlabel" aria-pressed={p.id === selected} onClick={() => onProgram(p.id)}
              data-tip={`${p.label} · ${fmt(p.n)} functions in the reference build · ${p.builds.length} builds · ${pct(pb)} bound across all builds`}>
              <span className="cp-mname">{p.label}</span>
              <span className="cp-mbar" aria-hidden="true"><span style={{ width: `${(pb ?? 0) * 100}%` }} /></span>
              <small className="cp-mono">{p.builds.length}×</small>
            </button>
            <div className="cp-mcells">
              {orderedBuilds(p).map(b => {
                const r = ratio(b.bound, b.functions) ?? 0;
                const c = ratio(b.real_c, b.functions) ?? 0;
                const on = p.id === selected && scope === b.slug;
                return (
                  <button key={b.slug} type="button" role="gridcell" className={`cp-mc ${b.slug === p.ref ? 'ref' : ''} ${on ? 'on' : ''}`}
                    aria-pressed={on} aria-label={`${b.slug}: ${pct(r)} bound`}
                    onClick={() => onScope(p.id, on ? null : b.slug)}
                    data-tip={`${b.slug}${b.platform ? ` · ${b.platform}` : ''}${b.format ? `/${b.format}` : ''} · ${fmt(b.functions)} functions · ${fmt(b.bound)} bound (${pct(r)}) · ${fmt(b.real_c)} real C${b.slug === p.ref ? ' · reference build: the map is laid out from it' : ' · click to scope the lens to this build'}`}>
                    <span className="f" style={{ height: `${r * 100}%` }} />
                    {b.real_c > 0 && <span className="r" style={{ height: `${Math.max(2, c * 100)}%` }} />}
                    <span className="p" aria-hidden="true">{(b.platform || shortSlug(b.slug, p.id) || '?').slice(0, 1).toUpperCase()}</span>
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
