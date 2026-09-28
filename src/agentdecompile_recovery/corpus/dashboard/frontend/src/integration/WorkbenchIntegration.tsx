import { useEffect, useMemo, useState } from "react";
import type { Data, Notify, Selection } from "../contracts";
import { API, query, request } from "../contracts";
import { EvidenceFirstAi } from "../ai/EvidenceFirstAi";
import { MatchingWorkspace, type MatchPhase } from "../matching/MatchingWorkspace";
import { useFunctionEvidence } from "../SourceEditor";
import { readWorkspaceDraft, useWorkspaceDraft } from "../workspaceState";
import {
  diffMismatches,
  diffReceipts,
  evidenceRecords,
  matchingProvider,
  matchingPhase,
  parseMatchPayload,
  sourceDraftKey,
  targetRevision,
} from "./boundaries";
import "./integration.css";

function useSharedSourceDraft(selection: Selection) {
  const key = sourceDraftKey(selection);
  const { save } = useWorkspaceDraft(key);
  const [candidate, setCandidate] = useState("");

  useEffect(() => {
    let active = true;
    setCandidate("");
    if (!selection.addr) return () => {
      active = false;
    };
    void readWorkspaceDraft(key).then((draft) => {
      if (active) setCandidate(draft || "");
    });
    return () => {
      active = false;
    };
  }, [key, selection.addr]);

  return { candidate, save };
}

const terminalJobStates = new Set(["ok", "failed", "cancelled", "interrupted", "blocked"]);

function useMatchingJob(jobId: string) {
  const [job, setJob] = useState<Data>({});
  useEffect(() => {
    if (!jobId) { setJob({}); return; }
    let active = true;
    let timer = 0;
    const poll = async () => {
      try {
        const response = await request(`/api/v1/jobs/${encodeURIComponent(jobId)}`);
        if (!active) return;
        const next = response.job || response;
        setJob(next);
        if (!terminalJobStates.has(String(next.status || ""))) timer = window.setTimeout(poll, 1000);
      } catch (error) {
        if (active) setJob({ id: jobId, status: "failed", error: error instanceof Error ? error.message : String(error) });
      }
    };
    void poll();
    return () => { active = false; window.clearTimeout(timer); };
  }, [jobId]);
  return job;
}

export function WorkbenchIntegration({
  selection,
  revision,
  catalog,
  onSelect,
  onMatchCandidate,
  matchingJobId = "",
  notify,
}: {
  selection: Selection;
  revision: number;
  catalog: Data[];
  onSelect: (patch: Partial<Selection>) => void;
  onMatchCandidate?: (params: Data) => void;
  matchingJobId?: string;
  notify: Notify;
}) {
  const hasFunction = Boolean(selection.addr);
  const detail = useFunctionEvidence(
    hasFunction ? `${API}/function?${query(selection)}` : null,
    revision,
  );
  const { candidate, save } = useSharedSourceDraft(selection);
  const records = useMemo(
    () => evidenceRecords(detail.data, selection),
    [detail.data, selection],
  );
  const provider = useMemo(() => {
    const negotiated = matchingProvider(catalog);
    return onMatchCandidate
      ? negotiated
      : {
          ...negotiated,
          available: false,
          reason: "This legacy surface cannot submit the approval-gated matching action. Open the canonical workstation.",
        };
  }, [catalog, onMatchCandidate]);
  const revisionId = targetRevision(detail.data);
  const matchingJob = useMatchingJob(matchingJobId);
  const matchingResult = useMemo(() => parseMatchPayload(matchingJob), [matchingJob]);
  const phase: MatchPhase = matchingPhase(matchingJobId, matchingJob, provider.available);
  const resultReceipt = matchingResult.receipt && typeof matchingResult.receipt === "object"
    ? [matchingResult.receipt]
    : [];

  return (
    <section className="workbench-integration" aria-label="Evidence and matching">
      <header>
        <h2>Evidence and matching</h2>
        <p>
          Optional providers are capability-gated. Local drafts and recorded
          evidence remain separate from byte proof.
        </p>
      </header>
      {!hasFunction ? (
        <p role="status">
          Select a function to bind its recorded evidence and local source draft.
        </p>
      ) : null}
      <details className="workspace-reference">
        <summary>Evidence-bounded assistance</summary>
        <section id="evidence-first-ai">
          <EvidenceFirstAi
            state="provider-unavailable"
            records={records}
            error={detail.error || undefined}
            onNavigate={(record) => {
              if (record.address) onSelect({ addr: record.address });
            }}
          />
          {!records.length && !detail.loading && !detail.error ? (
            <p className="integration-note" role="status">
              No revision-bound function evidence is available for this selection.
              Evidence remains inspectable when a provider records it.
            </p>
          ) : null}
        </section>
      </details>
      <details className="workspace-reference">
        <summary>Candidate matching</summary>
        <section id="matching-workspace">
          {hasFunction ? (
            <MatchingWorkspace
              candidate={candidate}
              candidateRevision={matchingResult.candidateRevision || (candidate ? "Browser-local draft" : "No local draft")}
              targetRevision={matchingResult.targetRevision || revisionId || "Not recorded"}
              compilerPreset={matchingResult.compilerPreset || "Choose an approved preset in action review"}
              phase={phase}
              provider={provider}
              mismatches={diffMismatches(detail.data)}
              receipts={resultReceipt.length ? resultReceipt : diffReceipts(detail.data)}
              onCandidateChange={(next) => {
                save(next);
                notify("Candidate draft saved locally. No provider operation was started.");
              }}
              onCompile={(nextCandidate) => {
                save(nextCandidate);
                const functionRecord = detail.data.function && typeof detail.data.function === "object"
                  ? detail.data.function
                  : {};
                onMatchCandidate?.({
                  artifactHash: selection.binaryHash || "",
                  targetRevision: revisionId || "",
                  function: detail.data.name || functionRecord.name || selection.logicalId || selection.addr,
                  candidateSource: nextCandidate,
                  compilerPreset: detail.data.compilerPreset || detail.data.compiler_preset || "",
                });
                notify("Candidate draft saved. Review exact target, compiler preset, and revision before submitting the match job.");
              }}
              onNavigateMismatch={(mismatch) => {
                if (mismatch.address) onSelect({ addr: mismatch.address });
              }}
            />
          ) : (
            <p role="status">
              Select a function before creating a candidate draft. No compile or
              diff operation is available without a negotiated provider.
            </p>
          )}
        </section>
      </details>
    </section>
  );
}
