import { useEffect, useState } from "react";
import type { Data } from "../contracts";
import { ApprovalGate } from "../ai/ApprovalGate";
import { DiffEvidence, type DiffMismatch } from "../views/DiffEvidence";
import "./matching.css";

export type MatchPhase =
  | "draft"
  | "compiling"
  | "compiled"
  | "linked"
  | "structurally-similar"
  | "diffing"
  | "mismatch"
  | "objdiff-verified"
  | "provider-unavailable"
  | "failed";

const phaseLabel: Record<MatchPhase, string> = {
  draft: "Candidate draft",
  compiling: "Compiling candidate",
  compiled: "Compile completed",
  linked: "Linked candidate",
  "structurally-similar": "Structurally similar",
  diffing: "Comparing object bytes",
  mismatch: "Byte mismatch recorded",
  "objdiff-verified": "Objdiff verified",
  "provider-unavailable": "Objdiff provider unavailable",
  failed: "Compile or diff failed",
};

export function MatchingWorkspace({
  candidate,
  candidateRevision,
  targetRevision,
  compilerPreset,
  phase,
  provider,
  mismatches = [],
  receipts = [],
  approvalRecords,
  onCandidateChange,
  onCompile,
  onRetry,
  onNavigateMismatch,
  onRequestPromotion,
}: {
  candidate: string;
  candidateRevision: string;
  targetRevision: string;
  compilerPreset: string;
  phase: MatchPhase;
  provider: { available: boolean; reason?: string; engine?: string; version?: string };
  mismatches?: DiffMismatch[];
  receipts?: Data[];
  approvalRecords?: unknown;
  onCandidateChange: (candidate: string) => void;
  onCompile?: () => void;
  onRetry?: () => void;
  onNavigateMismatch?: (mismatch: DiffMismatch) => void;
  onRequestPromotion?: (approvalId: string) => void;
}) {
  const [draft, setDraft] = useState(candidate);
  useEffect(() => setDraft(candidate), [candidateRevision, candidate]);
  const busy = phase === "compiling" || phase === "diffing";
  const proof = phase === "objdiff-verified";
  const params = { candidateRevision, targetRevision, compilerPreset };
  return (
    <section className="matching-workspace" aria-label="Matching workspace" aria-busy={busy}>
      <header>
        <strong>Candidate → compile → diff</strong>
        <span data-phase={phase}>{phaseLabel[phase]}</span>
      </header>
      {!provider.available ? (
        <p className="matching-unavailable" role="status">
          {provider.reason || "The selected objdiff provider is unavailable."}
          Drafts remain local and no byte-proof result is implied.
        </p>
      ) : null}
      <dl>
        <div><dt>Candidate revision</dt><dd>{candidateRevision}</dd></div>
        <div><dt>Target revision</dt><dd>{targetRevision}</dd></div>
        <div><dt>Compiler preset</dt><dd>{compilerPreset || "Not recorded"}</dd></div>
        <div><dt>Provider</dt><dd>{provider.engine || "Not recorded"}{provider.version ? ` ${provider.version}` : ""}</dd></div>
      </dl>
      <label>
        Candidate source
        <textarea value={draft} disabled={busy} onChange={(event) => setDraft(event.target.value)} onBlur={() => onCandidateChange(draft)} />
      </label>
      <div className="matching-actions">
        <button type="button" disabled={!provider.available || busy || !onCompile} onClick={onCompile}>Compile and diff</button>
        {["failed", "mismatch", "provider-unavailable"].includes(phase) && onRetry ? <button type="button" onClick={onRetry}>Retry recorded attempt</button> : null}
      </div>
      <p className={proof ? "matching-proof" : "matching-boundary"}>
        {proof ? "Objdiff verification is recorded for these exact revisions." : "Compile success, a logical ID, and structural similarity are not byte proof."}
      </p>
      <DiffEvidence mismatches={mismatches} receipts={receipts} onNavigate={onNavigateMismatch} />
      {proof && onRequestPromotion ? (
        <ApprovalGate records={approvalRecords} actionId="corpus.promote-verified-match" params={params} targetRevision={targetRevision}>
          {(approval) => <button type="button" disabled={!approval} onClick={() => approval && onRequestPromotion(approval.id)}>Request approved promotion</button>}
        </ApprovalGate>
      ) : null}
    </section>
  );
}
