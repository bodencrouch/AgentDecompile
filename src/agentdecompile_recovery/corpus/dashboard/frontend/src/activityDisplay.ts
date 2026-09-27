import type { Data } from "./contracts";

const LIVE = new Set([
  "queued",
  "running",
  "cancelling",
  "waiting",
  "paused",
  "disconnected",
  "resync",
  "resumable",
]);

function basename(path: string): string {
  return String(path).split("/").filter(Boolean).pop() || path;
}

export function activityTarget(job: Data): string {
  const src = job.params?.src || job.params?.source;
  const dst = job.params?.dst || job.params?.destination;
  if (src && dst) return `${basename(String(src))} → ${basename(String(dst))}`;
  return String(
    job.params?.programPath ||
      job.params?.program ||
      job.params?.slug ||
      job.context?.program ||
      "",
  );
}

export function workflowStatusText(value: unknown): string {
  const text = String(value || "");
  if (/source repository changed after the native checkout was created|reconcile changed source before continuing/i.test(text))
    return "Reconciling the local recovery checkout with updated shared-project data. Existing annotations remain preserved.";
  return text;
}

export function ownershipUnresolved(job: Data): boolean {
  return job.resourceDisposition === "quarantined" || job.ownershipUnresolved === true;
}

export function activityHeadline(jobs: Data[]): string {
  const live = jobs.filter((job) => LIVE.has(String(job.status)) && !job.ownerUnavailable);
  const matching = live.filter((job) => job.actionId === "corpus.match-pair");
  const comparing = matching.filter((job) => job.status === "running").length;
  const queued = matching.filter((job) => job.status === "queued").length;
  const other = live.length - matching.length;
  const recoverable = live.filter((job) =>
    ["paused", "disconnected", "resync", "resumable"].includes(
      String(job.status),
    ),
  ).length;
  const parts: string[] = [];
  const quarantined = jobs.filter(ownershipUnresolved).length;
  if (quarantined) parts.push(`${quarantined} ownership unresolved`);
  if (comparing) parts.push(`${comparing} comparing`);
  if (queued) parts.push(`${queued} queued`);
  if (recoverable) parts.push(`${recoverable} recoverable`);
  if (other) parts.push(`${other} other active`);
  if (!parts.length) return live.length ? `${live.length} active` : "No active jobs";
  return parts.join(" · ");
}
