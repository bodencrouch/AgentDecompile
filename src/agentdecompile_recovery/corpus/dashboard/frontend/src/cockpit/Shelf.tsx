import { fmt, ratio, type Totals } from './api';

export type Product = {
  id: string;
  name: string;
  color: string;
  frac: number | null;
  value: string;
  tip: string;
};

/** Products and their rings, computed only from real totals; no feed = no ring value. */
export function productsFrom(t: Totals | undefined): Product[] {
  const has = (k: keyof Totals) => t !== undefined && Number.isFinite(t[k]);
  const source = t && has('recovered_logical') && has('logical') ? ratio(t.recovered_logical, t.logical) : null;
  const bound = t && has('bound') && has('functions') ? ratio(t.bound, t.functions) : null;
  const named = t && has('named_above_placeholder') && has('named_of') ? ratio(t.named_above_placeholder, t.named_of) : null;
  const none = (id: string, name: string, color: string, tip: string): Product => ({ id, name, color, frac: null, value: '', tip });
  return [
    {
      id: 'source', name: 'Source that rebuilds', color: '--f-source', frac: source,
      value: t ? `${fmt(t.recovered_logical)} / ${fmt(t.logical)}` : '',
      tip: 'C with a recorded byte-exact receipt · ring: shared identities with such C in any build',
    },
    {
      id: 'signatures', name: 'Portable signatures', color: '--f-unify', frac: bound,
      value: t ? `${fmt(t.bound)} / ${fmt(t.functions)}` : '',
      tip: 'Every function found on every build without an address · ring: functions bound to a shared identity',
    },
    {
      id: 'agent', name: 'Agent context', color: '--f-identity', frac: named,
      value: t ? `${fmt(t.named_above_placeholder)} / ${fmt(t.named_of)}` : '',
      tip: 'The recovered program as context an agent can read · ring: functions named above placeholder',
    },
    none('lua', 'Script extender', '--f-runtime', 'Every routine callable and every event hookable from Lua'),
    none('headers', 'Headers & structs', '--f-identity', 'Per-build headers and pointer paths that hold across builds'),
    none('caves', 'Code caves', '--f-unify', 'Verified unused spans, found by signature'),
    none('build', 'Learn the build', '--f-verify', 'Compiler and flags read off the bytes, then reproduced'),
    none('port', 'Browser port', '--f-runtime', 'The program rebuilt to WebAssembly'),
    none('multiplayer', 'Multiplayer', '--f-verify', 'Engine state understood well enough to network'),
  ];
}

export const pctLabel = (f: number) => (f >= 0.995 ? '100' : f >= 0.1 ? String(Math.round(f * 100)) : f > 0 ? (f * 100).toFixed(f < 0.01 ? 2 : 1) : '0');

export function Ring({ frac, color, size = 46, stroke = 5, label }: { frac: number | null; color: string; size?: number; stroke?: number; label?: string }) {
  const r = (size - stroke) / 2, c = 2 * Math.PI * r;
  const f = frac === null ? 0 : Math.max(0, Math.min(1, frac));
  const dash = f > 0 && f * c < 2 ? 2 : f * c;
  return (
    <svg className="cp-ring" width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--ring-track)" strokeWidth={stroke} strokeDasharray={frac === null ? '2 3' : undefined} />
      {frac !== null && f > 0 && (
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={`var(${color})`} strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={`${dash} ${c}`} transform={`rotate(-90 ${size / 2} ${size / 2})`} className="cp-ring-arc" />
      )}
      {label !== undefined && (
        <text x="50%" y="53%" textAnchor="middle" dominantBaseline="middle" className="cp-ring-label" fontSize={size * 0.26}>{label}</text>
      )}
    </svg>
  );
}

export function Shelf({ totals, compact }: { totals: Totals | undefined; compact: boolean }) {
  const products = productsFrom(totals);
  if (compact) {
    return (
      <ul className="cp-shelf compact" aria-label="Products">
        {products.map(p => (
          <li key={p.id} tabIndex={0} className={p.frac === null ? 'nodata' : ''}
            data-tip={`${p.name} · ${p.frac === null ? 'no data yet' : `${pctLabel(p.frac)}% · ${p.value}`} · ${p.tip}`}
            aria-label={`${p.name}: ${p.frac === null ? 'no data yet' : `${pctLabel(p.frac)} percent`}`}>
            <Ring frac={p.frac} color={p.color} size={30} stroke={3.5} />
          </li>
        ))}
      </ul>
    );
  }
  return (
    <ul className="cp-shelf" aria-label="Products">
      {products.map(p => (
        <li key={p.id} className={`cp-prod ${p.frac === null ? 'nodata' : ''}`} tabIndex={0}
          data-tip={`${p.name} · ${p.tip}`}
          aria-label={`${p.name}: ${p.frac === null ? 'no data yet' : `${pctLabel(p.frac)} percent, ${p.value}`}`}>
          <Ring frac={p.frac} color={p.color} label={p.frac === null ? '' : pctLabel(p.frac)} />
          <span className="cp-prod-name">{p.name}</span>
          {p.frac === null ? <span className="cp-chip dash">no data</span> : <span className="cp-prod-val cp-mono">{p.value}</span>}
        </li>
      ))}
    </ul>
  );
}
