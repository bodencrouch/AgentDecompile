import type { Data } from "../contracts";
import "./DiffEvidence.css";

export type DiffMismatch = {
  id: string;
  address?: string;
  region?: string;
  summary: string;
  expected?: string;
  actual?: string;
};

export function DiffEvidence({
  mismatches,
  receipts = [],
  onNavigate,
}: {
  mismatches: DiffMismatch[];
  receipts?: Data[];
  onNavigate?: (mismatch: DiffMismatch) => void;
}) {
  return (
    <section className="diff-evidence" aria-label="Byte diff evidence">
      <h3>Mismatch evidence</h3>
      {mismatches.length ? (
        <ol>
          {mismatches.map((mismatch) => (
            <li key={mismatch.id}>
              {onNavigate ? <button type="button" onClick={() => onNavigate(mismatch)}>{mismatch.summary}</button> : mismatch.summary}
              <small>{mismatch.address ? ` · ${mismatch.address}` : ""}{mismatch.region ? ` · ${mismatch.region}` : ""}</small>
              {mismatch.expected || mismatch.actual ? <pre>expected: {mismatch.expected || "not recorded"}{"\n"}actual: {mismatch.actual || "not recorded"}</pre> : null}
            </li>
          ))}
        </ol>
      ) : <p>No mismatch regions were recorded.</p>}
      <details>
        <summary>Provider receipts ({receipts.length})</summary>
        {receipts.length ? <ul>{receipts.map((receipt, index) => <li key={`${receipt.path || receipt.label || "receipt"}:${index}`}>{String(receipt.label || receipt.path || "Recorded receipt")}{receipt.freshnessLabel ? ` · ${receipt.freshnessLabel}` : ""}{receipt.sourceExists === false ? " · source unavailable" : ""}</li>)}</ul> : <p>No provider receipt is available.</p>}
      </details>
    </section>
  );
}
