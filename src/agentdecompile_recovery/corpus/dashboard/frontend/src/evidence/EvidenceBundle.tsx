import "./evidence.css";

export type EvidenceRecord = {
  id: string;
  revisionId: string;
  label: string;
  kind?: string;
  provider?: string;
  confidence?: number;
  address?: string;
  region?: string;
  href?: string;
};
export type EvidenceClaim = {
  id: string;
  kind: "fact" | "hypothesis" | "recommendation" | "unknown";
  text: string;
  citations: Array<{ id: string; revisionId: string }>;
};

function citationState(claim: EvidenceClaim, records: EvidenceRecord[]) {
  const indexed = new Map(records.map((record) => [record.id, record]));
  const missing = claim.citations.filter((citation) => !indexed.has(citation.id));
  const stale = claim.citations.filter(
    (citation) => indexed.get(citation.id)?.revisionId !== citation.revisionId,
  );
  return { missing, stale, valid: !missing.length && !stale.length };
}

export function EvidenceBundle({
  records,
  claims,
  onNavigate,
}: {
  records: EvidenceRecord[];
  claims: EvidenceClaim[];
  onNavigate?: (record: EvidenceRecord) => void;
}) {
  return (
    <section className="evidence-bundle" aria-label="Bounded evidence bundle">
      <p>{records.length} indexed evidence record{records.length === 1 ? "" : "s"} supplied to this response.</p>
      <ul className="evidence-records">
        {records.map((record) => (
          <li key={`${record.id}:${record.revisionId}`}>
            {onNavigate ? <button type="button" onClick={() => onNavigate(record)}>{record.label}</button> : record.label}
            <small> · {record.kind || "evidence"} · revision {record.revisionId}{record.address ? ` · ${record.address}` : ""}{record.region ? ` · ${record.region}` : ""}</small>
          </li>
        ))}
      </ul>
      {claims.map((claim) => {
        const state = citationState(claim, records);
        return (
          <article key={claim.id} className="evidence-claim" data-state={state.valid ? "supported" : "withheld"}>
            <strong>{claim.kind}</strong>
            <p>{claim.text}</p>
            {state.valid ? <small>Supported by {claim.citations.length} current citation{claim.citations.length === 1 ? "" : "s"}.</small> : <p role="alert">{state.missing.length ? "Unsupported: cited evidence is unavailable." : "Withheld: cited evidence revision is stale."}</p>}
          </article>
        );
      })}
      {!claims.length ? <p>No claims were supplied. Evidence browsing remains available.</p> : null}
    </section>
  );
}
