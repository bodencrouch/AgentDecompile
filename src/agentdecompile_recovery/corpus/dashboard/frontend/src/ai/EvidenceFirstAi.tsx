import { EvidenceBundle, type EvidenceClaim, type EvidenceRecord } from "../evidence/EvidenceBundle";
import "./ai.css";

export type AiState =
  | "idle"
  | "loading"
  | "streaming"
  | "cancelled"
  | "timeout"
  | "provider-unavailable"
  | "partial-response"
  | "invalid-citation"
  | "stale-citation"
  | "retry"
  | "approval-pending"
  | "complete";

const stateLabel: Record<AiState, string> = {
  idle: "Ready for an evidence-bounded request",
  loading: "Preparing bounded evidence",
  streaming: "Receiving a proposal",
  cancelled: "Request cancelled; no conclusion was accepted",
  timeout: "Provider timed out; no conclusion was accepted",
  "provider-unavailable": "AI provider is unavailable; evidence remains browsable",
  "partial-response": "Partial response; no conclusion was accepted",
  "invalid-citation": "Response has invalid citations; claims are withheld",
  "stale-citation": "Response cites a stale revision; claims are withheld",
  retry: "Request can be retried with the same bounded evidence",
  "approval-pending": "Proposal awaits a durable human approval record",
  complete: "Response received; citation validation determines support",
};

export function EvidenceFirstAi({
  state,
  records,
  claims = [],
  error,
  onCancel,
  onRetry,
  onNavigate,
}: {
  state: AiState;
  records: EvidenceRecord[];
  claims?: EvidenceClaim[];
  error?: string;
  onCancel?: () => void;
  onRetry?: () => void;
  onNavigate?: (record: EvidenceRecord) => void;
}) {
  const pending = state === "loading" || state === "streaming";
  const recoverable = ["timeout", "provider-unavailable", "partial-response", "retry"].includes(state);
  return (
    <section className="evidence-first-ai" aria-label="Evidence-first AI" aria-busy={pending}>
      <header>
        <strong>Evidence-first AI</strong>
        <span role="status" aria-live="polite">{stateLabel[state]}</span>
      </header>
      {error ? <p role="alert">{error}</p> : null}
      {pending && onCancel ? <button type="button" onClick={onCancel}>Cancel request</button> : null}
      {recoverable && onRetry ? <button type="button" onClick={onRetry}>Retry with recorded evidence</button> : null}
      <EvidenceBundle records={records} claims={claims} onNavigate={onNavigate} />
      <p className="ai-boundary">
        AI can inspect bounded evidence and propose work. It cannot execute
        commands, patches, uploads, promotions, or publication from this panel.
      </p>
    </section>
  );
}
