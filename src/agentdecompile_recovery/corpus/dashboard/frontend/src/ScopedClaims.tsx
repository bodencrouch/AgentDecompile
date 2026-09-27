import type { EntityActivity } from './activity';
import type { Selection } from './contracts';

export type ScopedClaim = {
  kind: 'raw-local' | 'named-identity' | 'placed-contribution';
  state: 'recorded' | 'stale' | 'unknown' | 'unavailable';
  accepted: false;
  scope: string; label: string; summary: string; reason: string;
};
export type ClaimCandidate = {
  id: string; address: string; targetSha256: string; recordedTargetSha256: string | null;
  candidate: {program: string; name: string; binary_id: number; addr: number; path: string; source_sha256: string | null};
  sourceState: string; sourceReason: string;
  claims: ScopedClaim[];
  receipts: Array<{id: string; path: string; href: string; label: string; candidateBound: false}>;
};
export type ClaimProjection = {
  schema: 'agentdecompile.activity-claims/v1'; state: string; reason: string;
  targetSha256: string | null; checkedAt: number | null; basis: string;
  candidates: ClaimCandidate[]; truncated: boolean; limit: number;
  observationLimited?: boolean; omittedMalformed?: number; contributionReason: string;
};

const addressKey = (value: unknown) => String(value || '').toLowerCase().replace(/^0x0*/, '') || '0';

export function readClaimProjection(value: unknown): ClaimProjection | undefined {
  if (!value || typeof value !== 'object') return undefined;
  const p = value as ClaimProjection;
  const text = (v: unknown) => typeof v === 'string';
  if (p.schema !== 'agentdecompile.activity-claims/v1' || !text(p.reason) || !text(p.basis) ||
      !['recorded','unavailable'].includes(p.state) || !Array.isArray(p.candidates) || p.candidates.length > 64 ||
      typeof p.truncated !== 'boolean' || !Number.isSafeInteger(p.limit) || p.limit < 1 ||
      (p.targetSha256 !== null && (!text(p.targetSha256) || !/^[a-f0-9]{64}$/.test(p.targetSha256))) ||
      (p.checkedAt !== null && (typeof p.checkedAt !== 'number' || !Number.isFinite(p.checkedAt) || Math.abs(p.checkedAt) > 8640000000000))) return undefined;
  for (const row of p.candidates) {
    if (!row || !text(row.id) || !text(row.address) || row.targetSha256 !== p.targetSha256 ||
        !text(row.sourceState) || !text(row.sourceReason) || !row.candidate ||
        ![row.candidate.name,row.candidate.program,row.candidate.path,row.candidate.source_sha256].every(v => v == null || text(v)) ||
        !Number.isSafeInteger(row.candidate.binary_id) || !Number.isSafeInteger(row.candidate.addr) ||
        !Array.isArray(row.claims) || row.claims.length !== 3 || new Set(row.claims.map(c=>c?.kind)).size !== 3 ||
        row.claims.some(c => !c || c.accepted !== false || !['raw-local','named-identity','placed-contribution'].includes(c.kind) ||
          !['recorded','stale','unknown','unavailable'].includes(c.state) || ![c.label,c.summary,c.reason,c.scope].every(text)) ||
        !Array.isArray(row.receipts) || row.receipts.length > 4 || row.receipts.some(r=>!r || r.candidateBound !== false || ![r.id,r.path,r.href,r.label].every(text))) return undefined;
  }
  return p;
}

/** Exact selected build first; an address or logical name never selects a target. */
export function selectClaimProjection(entities: EntityActivity[], selection: Selection): ClaimProjection | undefined {
  const binaries = entities.filter(entity => entity.kind === 'binary' && entity.claimProjection &&
    (selection.binaryHash ? entity.sha256 === selection.binaryHash : selection.slug ?
      (entity.slug === selection.slug || entity.aliasSlugs?.includes(selection.slug)) : Boolean(selection.program)) &&
    (!(selection.locator || selection.program) || entity.projectBindings?.some(binding => (!selection.locator || binding.locator === selection.locator) &&
      (!selection.program || binding.program.replace(/^\//, '') === selection.program.replace(/^\//, '')))));
  if (binaries.length !== 1) return undefined;
  return binaries[0].claimProjection;
}

/** Only server-created artifact-viewer links; the URL never selects acceptance inputs. */
export function safeClaimHref(value: unknown): string | undefined {
  if (typeof value !== 'string' || !value.startsWith('/dashboard/artifact?')) return undefined;
  try {
    const url = new URL(value, 'https://evidence.invalid');
    const path = url.searchParams.get('p');
    if (url.pathname !== '/dashboard/artifact' || url.origin !== 'https://evidence.invalid' || url.hash ||
        [...url.searchParams.keys()].some(key => key !== 'p') || url.searchParams.getAll('p').length !== 1 ||
        !path || path.startsWith('/') || path.includes('\\') || path.includes('\0') || path.split('/').includes('..')) return undefined;
    return value;
  } catch { return undefined; }
}

export function ScopedClaims({projection: supplied, address, connection = 'disconnected'}: {
  projection?: ClaimProjection; address?: string; connection?: string;
}) {
  const projection = readClaimProjection(supplied);
  const rows = projection?.candidates.filter(candidate => !address || addressKey(candidate.address) === addressKey(address)) || [];
  return <section aria-label="Scoped recovery evidence" className="scoped-claims">
    <h3>Recovery evidence</h3>
    <p>Recorded observations are separate from current acceptance. No compiler-produced whole image or callable ABI is claimed.</p>
    {connection !== 'live' && connection !== 'polling' && <p role="status">Evidence feed disconnected or connecting; showing the last received scope. Current state unknown.</p>}
    {!projection ? <p>No target-bound claim projection received for this selection.</p> : <>
      <p>Target SHA-256 <code>{projection.targetSha256 || 'unknown'}</code></p>
      <p>{projection.basis}</p>
      {typeof projection.checkedAt === 'number' && Number.isFinite(projection.checkedAt) && <p>Source checks observed at {new Date(projection.checkedAt * 1000).toLocaleString()}. This is not a target-currentness check.</p>}
      {projection.truncated && <p role="status">Candidate list truncated at {projection.limit}. A selected function outside this batch may still have evidence.</p>}
      {projection.observationLimited && <p role="status">File-read budget reached; some observations or links are unavailable.</p>}
      {Boolean(projection.omittedMalformed) && <p>{projection.omittedMalformed} malformed candidate records omitted.</p>}
      {!rows.length && <p>{projection.state === 'unavailable' ? `Projection unavailable: ${projection.reason}` : projection.truncated ? 'No candidate for this address in the bounded batch.' : 'No recorded candidate for this selection in this snapshot.'}</p>}
      {rows.map(row => <details key={row.id} open={Boolean(address)}>
        <summary>{row.candidate.name || 'Unnamed candidate'} · {row.address} · source {row.candidate.source_sha256?.slice(0, 12) || 'unbound'}</summary>
        <p>Candidate {row.id} · database binary {row.candidate.binary_id}</p>
        <p>Source digest: {row.sourceState} · {row.sourceReason}</p>
        <dl>{row.claims.map(claim => <div key={claim.kind} data-claim={claim.kind} data-state={claim.state}>
          <dt>{claim.label} · {claim.state}</dt><dd>{claim.summary}<small> Scope: {claim.scope} · {claim.reason}</small></dd>
        </div>)}</dl>
        {row.receipts.length ? <ul>{row.receipts.map(receipt => <li key={receipt.id + receipt.path}>
          {safeClaimHref(receipt.href) ? <a href={safeClaimHref(receipt.href)} target="_blank" rel="noreferrer">{receipt.label}</a> : <span>Receipt link unavailable</span>}
          <small> Target/address reference; not proof for this particular source candidate. SHA-256 {receipt.id}</small>
        </li>)}</ul> : <p>No safe server-discovered receipt link for this candidate's target/address.</p>}
      </details>)}
    </>}
    <p>Placed source contribution: unavailable without a trusted serving-process reconstruction observation. Imported JSON does not establish it.</p>
  </section>;
}
