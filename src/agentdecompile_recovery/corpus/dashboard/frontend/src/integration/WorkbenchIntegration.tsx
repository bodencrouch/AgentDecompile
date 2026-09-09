import { useEffect, useMemo, useState } from "react";
import type { Data, Notify, Selection } from "../contracts";
import { API, query } from "../contracts";
import { EvidenceFirstAi } from "../ai/EvidenceFirstAi";
import { MatchingWorkspace } from "../matching/MatchingWorkspace";
import { useFunctionEvidence } from "../SourceEditor";
import { readWorkspaceDraft, useWorkspaceDraft } from "../workspaceState";
import {
  diffMismatches,
  diffReceipts,
  evidenceRecords,
  matchingProvider,
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

export function WorkbenchIntegration({
  selection,
  revision,
  catalog,
  onSelect,
  notify,
}: {
  selection: Selection;
  revision: number;
  catalog: Data[];
  onSelect: (patch: Partial<Selection>) => void;
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
  const provider = useMemo(() => matchingProvider(catalog), [catalog]);
  const revisionId = targetRevision(detail.data);

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
              candidateRevision={candidate ? "Browser-local draft" : "No local draft"}
              targetRevision={revisionId || "Not recorded"}
              compilerPreset="Not recorded"
              phase="provider-unavailable"
              provider={provider}
              mismatches={diffMismatches(detail.data)}
              receipts={diffReceipts(detail.data)}
              onCandidateChange={(next) => {
                save(next);
                notify("Candidate draft saved locally. No provider operation was started.");
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
