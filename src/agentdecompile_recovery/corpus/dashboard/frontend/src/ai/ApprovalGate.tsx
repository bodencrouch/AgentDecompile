import type { Data } from "../contracts";
import type { ReactNode } from "react";
import { validApproval, type ApprovalRecord } from "./approval";
import "./ai.css";

export function ApprovalGate({
  records,
  actionId,
  params,
  targetRevision,
  children,
}: {
  records: unknown;
  actionId: string;
  params: Data;
  targetRevision: unknown;
  children: (approval: ApprovalRecord | undefined) => ReactNode;
}) {
  const approval = validApproval(records, actionId, params, targetRevision);
  return (
    <section
      className="ai-approval-gate"
      aria-label="Human approval"
      data-approved={Boolean(approval) || undefined}
    >
      {approval ? (
        <p role="status">
          Approved by {approval.actorId} · record {approval.id} · audit{" "}
          {approval.auditEventId}
        </p>
      ) : (
        <p role="alert">
          Execution is unavailable until the action context supplies an
          unexpired, actor-bound approval record for these exact parameters and
          target revision. A browser confirmation is not approval.
        </p>
      )}
      {children(approval)}
    </section>
  );
}
