import type { Data } from "./contracts";

export type StageProgress = {
  completed: number;
  total: number;
  unit: string;
  currentTarget?: string;
};

const DEFAULT_UNITS: Record<string, string> = {
  matching: "comparisons",
  analysis: "programs",
  facts: "programs",
  bsim: "programs",
};

function measured(progress?: Partial<StageProgress>): StageProgress | undefined {
  const total = progress?.total;
  const completed = progress?.completed;
  if (!Number.isFinite(total) || !total || total <= 0) return undefined;
  if (
    typeof completed !== "number" ||
    !Number.isFinite(completed) ||
    completed < 0 ||
    completed > total
  )
    return undefined;
  return {
    completed,
    total,
    unit: progress?.unit || "items",
    currentTarget: progress?.currentTarget,
  };
}

/** Primary stage counter (e.g. 97/459 comparisons). Secondary sub-work (e.g. inventory read). */
export function stageDisplayProgress(stage?: Data): {
  primary?: StageProgress;
  secondary?: StageProgress;
} {
  if (!stage) return {};
  const primary = measured({
    completed: stage.completed,
    total: stage.total,
    unit: stage.unit || DEFAULT_UNITS[String(stage.key)] || "items",
    currentTarget: stage.currentTarget,
  });
  const secondary = measured(stage.workProgress);
  return { primary, secondary };
}

export function stageProgressLabel(progress: StageProgress): string {
  return `${progress.completed} / ${progress.total} ${progress.unit}`;
}

/**
 * A stage without a numeric counter still has a useful durable state.  Keep
 * that state visible instead of presenting missing telemetry as progress.
 */
export function stageProgressDetail(stage?: Data): string {
  if (!stage) return "No stage receipt recorded";
  const { primary, secondary } = stageDisplayProgress(stage);
  if (primary) return stageProgressLabel(primary);
  if (secondary) return stageProgressLabel(secondary);
  const reason = String(stage.reason || "").trim();
  const target = String(stage.currentTarget || stage.currentProgram || "").trim();
  const action = String(stage.currentAction || "").replace(/^mcp\./, "").replace(/[-_]/g, " ").trim();
  const status = String(stage.status || "").toLowerCase();
  if (status === "queued") return reason || "Queued behind preceding work";
  if (["running", "waiting", "cancelling"].includes(status))
    return [target && `Working on ${target}`, action].filter(Boolean).join(" · ") || reason || "Live operation has not published a numeric counter";
  if (reason) return reason;
  if (stage.receipt) return "Recorded stage receipt";
  if (status === "completed") return "Completed with recorded state";
  return "Awaiting a prerequisite receipt";
}

export function matchingStageSummary(run?: Data): string | undefined {
  const matching = run?.stages?.find((stage: Data) => stage.key === "matching");
  if (!matching) return undefined;
  const { primary, secondary } = stageDisplayProgress(matching);
  if (!primary) return matching.reason || undefined;
  const parts = [stageProgressLabel(primary)];
  if (secondary) parts.push(stageProgressLabel(secondary));
  return `${parts.join(" · ")} (${matching.status})`;
}
