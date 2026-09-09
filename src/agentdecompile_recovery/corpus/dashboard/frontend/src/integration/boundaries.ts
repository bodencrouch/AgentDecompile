import type { Data, Selection } from "../contracts";
import type { EvidenceRecord } from "../evidence/EvidenceBundle";
import type { DiffMismatch } from "../views/DiffEvidence";

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function record(value: unknown): Data {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Data)
    : {};
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
  const action = catalog.find((entry) => entry.id === "corpus.objdiff-check");
  return {
    available: false,
    engine: action ? "Cataloged backend workflow" : "No registered provider",
    reason: action
      ? "The server advertises an objdiff action, but no provider has advertised a candidate-bound compile and diff adapter for this browser-local draft."
      : "No objdiff capability is advertised by the current runtime. Browser-local drafts remain available and unverified.",
  };
}
