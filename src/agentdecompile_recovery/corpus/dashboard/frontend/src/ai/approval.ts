import type { Data } from "../contracts";

export type ApprovalRecord = {
  id: string;
  actorId: string;
  actionId: string;
  params: Data;
  targetRevision: string;
  expiresAt: string | number;
  auditEventId: string;
};

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value as Data)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonical((value as Data)[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function expiresAt(value: unknown): number {
  if (typeof value === "number") return value < 1e12 ? value * 1000 : value;
  const parsed = Date.parse(String(value));
  return Number.isFinite(parsed) ? parsed : 0;
}

export function validApproval(
  records: unknown,
  actionId: string,
  params: Data,
  targetRevision: unknown,
  now = Date.now(),
): ApprovalRecord | undefined {
  if (!Array.isArray(records)) return undefined;
  const expectedParams = canonical(params);
  const expectedRevision = String(targetRevision || "");
  return records.find((raw): raw is ApprovalRecord => {
    if (!raw || typeof raw !== "object") return false;
    const record = raw as Partial<ApprovalRecord>;
    return (
      typeof record.id === "string" &&
      typeof record.actorId === "string" &&
      typeof record.auditEventId === "string" &&
      typeof record.actionId === "string" &&
      record.actionId === actionId &&
      typeof record.targetRevision !== "undefined" &&
      String(record.targetRevision) === expectedRevision &&
      Boolean(record.params) &&
      canonical(record.params) === expectedParams &&
      expiresAt(record.expiresAt) > now
    );
  });
}
