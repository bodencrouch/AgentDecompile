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

export function receiptLabel(receipt: Data): string {
  const identity = receipt.label || receipt.path || receipt.id || "Recorded receipt";
  const status = receipt.status || receipt.phase;
  const differences = receipt.differences !== null && receipt.differences !== "" && Number.isFinite(Number(receipt.differences))
    ? Number(receipt.differences)
    : undefined;
  return [identity, status, differences === undefined ? undefined : `${differences} differences`]
    .filter((value) => value !== undefined && value !== "")
    .join(" · ");
}

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
        {receipts.length ? <ul>{receipts.map((receipt, index) => <li key={`${receipt.id || receipt.path || receipt.label || "receipt"}:${index}`}>
          {receiptLabel(receipt)}{receipt.freshnessLabel ? ` · ${receipt.freshnessLabel}` : ""}{receipt.sourceExists === false ? " · source unavailable" : ""}
          {receipt.targetRevision || receipt.compiledRevision ? <small> target {String(receipt.targetRevision || "not recorded").slice(0, 12)} · compiled {String(receipt.compiledRevision || "not recorded").slice(0, 12)}</small> : null}
          {receipt.mismatchHistogram && Object.keys(receipt.mismatchHistogram).length ? <small> {Object.entries(receipt.mismatchHistogram).map(([kind, count]) => `${kind}: ${String(count)}`).join(" · ")}</small> : null}
        </li>)}</ul> : <p>No provider receipt is available.</p>}
      </details>
    </section>
  );
}
