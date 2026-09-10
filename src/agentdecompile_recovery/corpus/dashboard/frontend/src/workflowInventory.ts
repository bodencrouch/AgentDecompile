import type { Data } from "./contracts";
import { canonicalProjectLocator } from "./projectLocator";

const programKey = (value: unknown) => String(value || "").replace(/^\/+/, "");

function workflowActivity(run: Data, program: string, jobs: Data[]): Data {
  const stages = run.stages || [];
  const analysis = stages.find((stage: Data) => stage.key === "analysis");
  const matching = stages.find((stage: Data) => stage.key === "matching");
  const livePair = (jobs || []).find((job: Data) =>
    job.actionId === "corpus.match-pair" && job.params?.run === `prepare-${run.id}` &&
    ["running", "cancelling"].includes(String(job.status)),
  );
  const source = String(livePair?.params?.src || "");
  const target = String(livePair?.params?.dst || "");
  const active = Boolean(livePair) && [source, target].some(value => programKey(value) === programKey(program));
  const pair = source && target ? `${source} → ${target}` : String(matching?.currentProgram || "");
  const queued = ["running", "queued", "waiting"].includes(String(matching?.status));
  return {
    status: active ? "running" : queued ? "queued" : analysis?.status === "completed" ? "idle" : String(analysis?.status || "idle"),
    stage: active || queued ? "Match related builds" : analysis?.status === "completed" ? "Ghidra analysis complete" : "Analysis state pending",
    action: livePair?.actionId || matching?.currentAction || "",
    target: active ? pair : String(matching?.currentProgram || ""),
    startedAt: livePair?.startedAt || matching?.startedAt || null,
    progress: matching?.total > 0 ? { kind: "measured", completed: Number(matching.completed || 0), total: Number(matching.total) } : { kind: "idle" },
    eta: { label: active ? "Estimating from comparable work" : queued ? "Waiting for comparison worker" : "Analysis recorded", basis: "Durable project preparation receipt", observations: 0 },
    facets: [
      ...(analysis?.status === "completed" ? [{ kind: "analysis", label: "Ghidra analyzed", source: "preparation receipt" }] : []),
      ...(active ? [{ kind: "match", label: "Cross-match active", source: "preparation receipt" }] : queued ? [{ kind: "match", label: "Cross-match queued", source: "preparation receipt" }] : []),
    ],
    queue: { position: active ? null : queued ? matching?.queuePosition ?? null : null, reason: active ? "Current comparison target" : queued ? "Project comparison queue" : "No admitted queue entry" },
    error: "",
  };
}

/**
 * Keep a live project usable while its corpus rows are still being written.
 * The preparation receipt is authoritative for the programs Ghidra already owns.
 */
export function workflowProgramMembers(project: Data, binaries: Data[], runs: Data[], jobs: Data[] = []): Data[] {
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
    if (existing) return { ...existing, program };
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
