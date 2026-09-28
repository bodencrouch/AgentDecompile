import type { Data, Selection } from "../contracts";
import type { EvidenceRecord } from "../evidence/EvidenceBundle";
import type { DiffMismatch } from "../views/DiffEvidence";
import type { MatchPhase } from "../matching/MatchingWorkspace";

const MATCH_SCHEMA = "agentdecompile.workbench-match-candidate.v1";
const terminalJobStates = new Set(["ok", "failed", "cancelled", "interrupted", "blocked"]);
const matchPhases = new Set<MatchPhase>([
  "draft", "compiling", "compiled", "linked", "structurally-similar", "diffing",
  "mismatch", "objdiff-verified", "provider-unavailable", "failed", "incomplete",
]);

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function record(value: unknown): Data {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Data)
    : {};
}

export function parseMatchPayload(job: Data): Data {
  const direct = record(job.matchResult);
  if (direct.schema === MATCH_SCHEMA) return direct;
  if (typeof job.log !== "string") return {};
  const start = job.log.indexOf("{");
  if (start < 0) return {};
  try {
    const parsed = record(JSON.parse(job.log.slice(start)));
    return parsed.schema === MATCH_SCHEMA ? parsed : {};
  } catch {
    return {};
  }
}

export function matchingPhase(jobId: string, job: Data, providerAvailable: boolean): MatchPhase {
  const result = parseMatchPayload(job);
  const phase = String(result.phase || "");
  if (phase === "objdiff-verified") {
    const receipt = record(result.receipt);
    const consistent = result.verified === true
      && receipt.status === "matched"
      && receipt.differences === 0
      && receipt.objdiffExit === 0
      && receipt.targetRevision === result.targetRevision
      && receipt.candidateRevision === result.candidateRevision;
    return consistent ? "objdiff-verified" : "incomplete";
  }
  if (phase === "compile-failed" || phase === "cancelled") return "failed";
  if (matchPhases.has(phase as MatchPhase)) return phase as MatchPhase;
  if (jobId && !terminalJobStates.has(String(job.status || ""))) return "compiling";
  if (jobId) return String(job.status || "") === "failed" ? "failed" : "incomplete";
  return providerAvailable ? "draft" : "provider-unavailable";
}

export function sourceDraftKey(selection: Selection): string {
  return JSON.stringify([
    selection.locator,
    selection.slug,
    selection.program,
    selection.addr,
    "source",
  ]);
}

export function evidenceRecords(
  detail: Data,
  selection: Selection,
): EvidenceRecord[] {
  const path = text(detail.evidencePath);
  const revisionId = text(detail.evidenceRevision);
  if (!path || !revisionId) return [];

  const provenance = record(detail.provenance);
  const provider = text(provenance.tool);
  return [{
    id: path,
    revisionId,
    label: provider
      ? `${provider} function observation`
      : "Recorded function observation",
    kind: "recorded function evidence",
    provider: provider || undefined,
    address: text(detail.addr) || selection.addr || undefined,
  }];
}

export function targetRevision(detail: Data): string {
  return text(detail.evidenceRevision) || text(record(detail.provenance).revision);
}

export function diffMismatches(detail: Data): DiffMismatch[] {
  const proof = record(detail.proof || detail.verification);
  const mismatches = Array.isArray(proof.mismatches) ? proof.mismatches : [];
  return mismatches.flatMap((value): DiffMismatch[] => {
    const mismatch = record(value);
    const id = text(mismatch.id);
    const summary = text(mismatch.summary);
    if (!id || !summary) return [];
    return [{
      id,
      summary,
      address: text(mismatch.address) || undefined,
      region: text(mismatch.region) || undefined,
      expected: text(mismatch.expected) || undefined,
      actual: text(mismatch.actual) || undefined,
    }];
  });
}

export function diffReceipts(detail: Data): Data[] {
  const proof = record(detail.proof || detail.verification);
  const entries = Array.isArray(proof.receipts)
    ? proof.receipts
    : proof.receipt === undefined
      ? []
      : [proof.receipt];
  return entries.flatMap((entry): Data[] => {
    if (entry && typeof entry === "object" && !Array.isArray(entry))
      return [entry as Data];
    const path = text(entry);
    return path ? [{ path }] : [];
  });
}

export function matchingProvider(catalog: Data[]) {
  const action = catalog.find((entry) => entry.id === "workbench.match-candidate");
  const legacyDiff = catalog.find((entry) => entry.id === "corpus.objdiff-check");
  return {
    available: Boolean(action),
    actionId: action?.id,
    engine: action ? "Candidate-bound compiler and objdiff job" : "No registered provider",
    reason: action
      ? undefined
      : legacyDiff
        ? "The server exposes path-based objdiff, but not the atomic candidate-bound compile and diff action required for browser drafts."
        : "No candidate-bound objdiff capability is advertised by the current runtime. Browser-local drafts remain available and unverified.",
  };
}
