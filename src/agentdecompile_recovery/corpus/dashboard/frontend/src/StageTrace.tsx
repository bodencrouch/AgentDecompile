import type { Data } from "./contracts";
import { stageDisplayProgress, stageProgressLabel } from "./preparationProgress";

const PLACEHOLDER: { key: string; title: string }[] = [
  { key: "prepare", title: "Prepare" },
  { key: "inventory", title: "Inventory" },
  { key: "decompile", title: "Decompile" },
  { key: "matching", title: "Match" },
  { key: "recover-source", title: "Synthesize" },
  { key: "verify-byte-accuracy", title: "Verify" },
];

const ACTIVE = new Set([
  "queued",
  "running",
  "waiting",
  "cancelling",
  "disconnected",
  "resync",
]);

function normalizeStatus(status: unknown): string {
  const value = String(status || "idle").toLowerCase();
  if (["completed", "done", "ok", "succeeded"].includes(value)) return "completed";
  if (["failed", "error", "blocked", "partial", "interrupted"].includes(value)) return "fault";
  if (["disconnected", "resync", "resumable"].includes(value)) return "recoverable";
  if (value === "cancelled") return "cancelled";
  if (value === "waiting" || value === "cancelling") return "waiting";
  if (value === "running") return "running";
  if (value === "queued" || value === "paused") return "queued";
  return "idle";
}

function strategyLabel(stage?: Data): string {
  if (!stage) return "";
  const named = stage.strategy || stage.method || stage.matcher || stage.profile;
  if (named) return String(named);
  const action = String(stage.currentAction || "").replace(/^mcp\./, "").replace(/[-_]/g, " ");
  if (action) return action.slice(0, 48);
  const reason = String(stage.reason || "");
  return reason.length > 56 ? `${reason.slice(0, 53)}…` : reason;
}

export type StageTraceByteGate = {
  status: string;
  label: string;
};

export type StageTraceProps = {
  run?: Data;
  loading?: boolean;
  relatedCount?: number;
  byteGate?: StageTraceByteGate;
  onPause?: () => void;
  onStop?: () => void;
  onResume?: () => void;
  canControl?: boolean;
  runStatus?: string;
};

export function StageTrace({
  run,
  loading = false,
  relatedCount,
  byteGate,
  onPause,
  onStop,
  onResume,
  canControl = false,
  runStatus,
}: StageTraceProps) {
  const stages: Data[] = Array.isArray(run?.stages) && run.stages.length
    ? run.stages
    : PLACEHOLDER.map((item) => ({ ...item, status: "idle" }));
  const current =
    stages.find((stage) => ACTIVE.has(String(stage.status))) ||
    stages.find((stage) => stage.key === run?.currentStage);
  const statusKey = String(runStatus ?? run?.status ?? "").toLowerCase();
  const live = Boolean(run && ACTIVE.has(String(run.status)));
  const progress = stageDisplayProgress(current);
  const controlActive = ACTIVE.has(statusKey);
  const controlPaused = statusKey === "paused";
  const showPause = canControl && Boolean(onPause) && controlActive;
  const showStop = canControl && Boolean(onStop) && (controlActive || controlPaused);
  const showResume = canControl && Boolean(onResume) && controlPaused;
  const showControls = showPause || showStop || showResume;
  const showRelated = typeof relatedCount === "number";
  const showByteGate = Boolean(byteGate?.label);

  return (
    <section className="stage-trace" aria-label="Recovery stage trace" data-live={live || undefined}>
      <header className="stage-trace-banner">
        <span className="stage-trace-live">{loading ? "SYNC" : live ? "LIVE" : run ? "IDLE" : "STANDBY"}</span>
        <strong>{current?.title || (run ? String(run.status || "Workflow") : "Open a project to arm the pipeline")}</strong>
        {progress.primary ? (
          <code>{stageProgressLabel(progress.primary)}</code>
        ) : current?.currentProgram || run?.program ? (
          <code>{current?.currentProgram || run?.program}</code>
        ) : null}
        {strategyLabel(current) ? <em>{strategyLabel(current)}</em> : null}
        {(showRelated || showByteGate) ? (
          <span className="stage-trace-chips" role="status">
            {showRelated ? (
              <span className="stage-trace-chip stage-trace-related">
                {relatedCount} related build{relatedCount === 1 ? "" : "s"}
              </span>
            ) : null}
            {showByteGate ? (
              <span className={`stage-trace-chip atlas-byte-chip state-${String(byteGate!.status || "queued").toLowerCase()}`}>
                {byteGate!.label}
              </span>
            ) : null}
          </span>
        ) : null}
        {showControls ? (
          <span className="stage-trace-controls">
            {showPause ? (
              <button type="button" className="stage-trace-control" onClick={onPause}>
                Pause
              </button>
            ) : null}
            {showStop ? (
              <button type="button" className="stage-trace-control" onClick={onStop}>
                Stop
              </button>
            ) : null}
            {showResume ? (
              <button type="button" className="stage-trace-control" onClick={onResume}>
                Resume
              </button>
            ) : null}
          </span>
        ) : null}
      </header>
      <ol className="stage-trace-rail">
        {stages.map((stage, index) => {
          const state = normalizeStatus(stage.status);
          const { primary, secondary } = stageDisplayProgress(stage);
          const active = stage === current;
          return (
            <li
              key={String(stage.key || index)}
              className={`stage-node state-${state}${active ? " is-current" : ""}`}
              data-state={state}
              aria-current={active ? "step" : undefined}
            >
              <span className="stage-node-mark" aria-hidden="true" />
              <div className="stage-node-copy">
                <strong>{stage.title || stage.key}</strong>
                <span>{state === "idle" ? "—" : state}</span>
                {active && primary ? <small>{stageProgressLabel(primary)}</small> : null}
                {active && secondary ? <small>{stageProgressLabel(secondary)}</small> : null}
                {active && primary?.currentTarget ? <code>{primary.currentTarget}</code> : null}
              </div>
              {index < stages.length - 1 ? <span className="stage-node-link" aria-hidden="true" /> : null}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
