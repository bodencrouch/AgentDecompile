export function preparationResponse(data: any): Record<string, any>[] {
  if (!data || data.ok === false || !Array.isArray(data.runs)) throw new Error("Invalid preparation response");
  const object = (value: any) => value !== null && typeof value === "object" && !Array.isArray(value);
  const texts = ["id", "status", "locator", "program", "slug", "title", "key", "reason", "error", "currentProgram", "currentTarget", "currentAction", "jobStatus", "unit", "nextFallback", "message", "action", "nextAction", "wakeCondition", "label", "state", "why", "next", "receipt", "programPath", "src", "dst", "actionId"];
  const numbers = ["completed", "total", "done", "attempts", "attemptsSpent", "attemptsRemaining", "executionLimitSeconds"];
  const times = ["updatedAt", "createdAt", "startedAt", "retryAt", "at", "executionDeadlineAt", "deadline"];
  function row(value: any) {
    if (!object(value)) return false;
    if (texts.some(key => value[key] != null && typeof value[key] !== "string")) return false;
    if (numbers.some(key => value[key] != null && (typeof value[key] !== "number" || !Number.isFinite(value[key])))) return false;
    if (times.some(key => value[key] != null && (typeof value[key] !== "number" || !Number.isFinite(value[key]) || Math.abs(value[key]) > 8640000000000))) return false;
    return true;
  }
  for (const run of data.runs) {
    if (!row(run)) throw new Error("Invalid preparation record");
    for (const key of ["stages", "events"]) {
      if (run[key] != null && (!Array.isArray(run[key]) || !run[key].every(row))) throw new Error("Invalid preparation " + key);
    }
    if (run.currentJob != null && (!row(run.currentJob) || (run.currentJob.params != null && !row(run.currentJob.params)))) throw new Error("Invalid current job");
    for (const stage of run.stages || []) {
      if (stage.workProgress != null && !row(stage.workProgress)) throw new Error("Invalid stage work progress");
    }
    if (run.programs != null && (!Array.isArray(run.programs) || !run.programs.every((value: unknown) => typeof value === "string"))) throw new Error("Invalid preparation programs");
    if (run.retryDecisions != null && (!object(run.retryDecisions) || !Object.values(run.retryDecisions).every(row))) throw new Error("Invalid continuation decisions");
  }
  return data.runs;
}
