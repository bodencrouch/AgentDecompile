import type { Data } from "./contracts";
import { canonicalProjectLocator } from "./projectLocator";

const programKey = (value: unknown) => String(value || "").replace(/^\/+/, "");

function workflowActivity(run: Data, program: string, jobs?: Data[] | null): Data {
  const stages = run.stages || [];
  const analysis = stages.find((stage: Data) => stage.key === "analysis");
  const matching = stages.find((stage: Data) => stage.key === "matching");
  const matchingJobs = Array.isArray(jobs) ? jobs.filter((job: Data) =>
    job.actionId === "corpus.match-pair" && job.params?.run === `prepare-${run.id}` &&
    ["queued", "running", "waiting", "cancelling"].includes(String(job.status)) &&
    [job.params?.src, job.params?.dst].some(value => programKey(value) === programKey(program)),
  ) : [];
  const job = matchingJobs.sort((left: Data, right: Data) =>
    (left.status === "running" || left.status === "cancelling" ? -1 : 0) -
    (right.status === "running" || right.status === "cancelling" ? -1 : 0) ||
    Number(left.createdAt || 0) - Number(right.createdAt || 0),
  )[0];
  const source = String(job?.params?.src || "");
  const target = String(job?.params?.dst || "");
  const active = Boolean(job) && ["running", "cancelling"].includes(String(job.status));
  const queued = Boolean(job) && ["queued", "waiting"].includes(String(job.status));
  // Once the job feed has arrived it is the authority for a member's current
  // work. The receipt is a project audit record and may name the preceding pair.
  const pair = source && target ? `${source} → ${target}` : !Array.isArray(jobs) ? String(matching?.currentProgram || "") : "";
  return {
    status: active ? "running" : queued ? "queued" : analysis?.status === "completed" ? "idle" : String(analysis?.status || "idle"),
    stage: active || queued ? "Match related builds" : analysis?.status === "completed" ? "Ghidra analysis complete" : "Analysis state pending",
    action: job?.actionId || (!Array.isArray(jobs) ? matching?.currentAction : ""),
    target: pair,
    startedAt: job?.startedAt || (!Array.isArray(jobs) ? matching?.startedAt : null),
    progress: active || queued ? matching?.total > 0 ? { kind: "measured", completed: Number(matching.completed || 0), total: Number(matching.total) } : { kind: active ? "indeterminate" : "idle" } : { kind: "idle" },
    eta: { label: active ? "Estimating from comparable work" : queued ? "Waiting for this comparison" : "Analysis recorded", basis: job ? "Live matching job" : "Durable project preparation receipt", observations: 0 },
    facets: [
      ...(analysis?.status === "completed" ? [{ kind: "analysis", label: "Ghidra analyzed", source: "preparation receipt" }] : []),
      ...(active ? [{ kind: "match", label: "Cross-match active", source: "live matching job" }] : queued ? [{ kind: "match", label: "Cross-match queued", source: "live matching job" }] : []),
    ],
    queue: { position: active ? null : queued ? job?.params?.queuePosition ?? null : null, reason: active ? "Current comparison target" : queued ? "This binary is in a queued comparison" : "No admitted queue entry" },
    error: "",
  };
}

/**
 * Keep a live project usable while its corpus rows are still being written.
 * The preparation receipt is authoritative for the programs Ghidra already owns.
 */
export function workflowProgramMembers(project: Data, binaries: Data[], runs: Data[], jobs?: Data[] | null): Data[] {
  const locator = canonicalProjectLocator(project.locator);
  const run = (runs || []).find((item) => canonicalProjectLocator(item.locator) === locator);
  if (!run) return [];
  const programs = Array.isArray(run.programs) && run.programs.length
    ? run.programs
    : Object.keys(run.executionProgramPaths || {});
  const known = new Set<string>();
  return programs.map((value: unknown) => {
    const program = String(value || "");
    const key = programKey(program);
    const existing = binaries.find((binary) =>
      binary.slug === key || binary.aliasSlugs?.includes(key) ||
      (binary.projectBindings || []).some((binding: Data) =>
        canonicalProjectLocator(binding.locator) === locator && programKey(binding.program) === key,
      ),
    );
    if (existing) return { ...existing, program, workflowActivity: workflowActivity(run, program, jobs) };
    return {
      id: `program:${locator}:${key}`,
      slug: "",
      label: key,
      program,
      locator,
      imported: true,
      kind: "binary",
      workflowOnly: true,
      projectBindings: [{ locator, program }],
      platform: "Recorded Ghidra program",
      protection: run.checkpoints?.[program]?.protection || { status: "unknown", encryption: "unknown", drm: "unknown" },
      funcs: Number(run.checkpoints?.[program]?.workSize || 0),
      libraryId: `program:${locator}:${key}`,
      identityStatus: "recorded-program",
      workflowActivity: workflowActivity(run, program, jobs),
    };
  }).filter((item) => {
    const key = programKey(item.program);
    if (!key || known.has(key)) return false;
    known.add(key);
    return true;
  });
}
