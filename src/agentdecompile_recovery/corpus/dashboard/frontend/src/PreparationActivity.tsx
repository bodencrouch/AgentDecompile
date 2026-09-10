import { useEffect, useState } from "react";
import { API, request, type Data, type SurfaceProps, type Selection, type Notify } from "./contracts";
import { usePreparationFeed } from "./preparationFeed";
import { ErrorLine, PrefDetails, Section } from "./ui";
import { stageDisplayProgress, stageProgressLabel } from "./preparationProgress";
import "./preparation.css";
const active = (status: string) => ["queued", "running", "waiting", "cancelling", "disconnected", "resync"].includes(status);
const statusLabels: Record<string, string> = {
  queued: "Preparation queued",
  running: "Preparing project",
  paused: "Preparation paused",
  disconnected: "Preparation disconnected · saved state retained",
  resync: "Preparation resynchronizing saved state",
  resumable: "Preparation can resume from its recorded checkpoint",
  cancelling: "Stopping preparation",
  cancelled: "Preparation cancelled",
  blocked: "Preparation needs attention",
  failed: "Preparation failed",
  completed: "Preparation completed",
  partial: "Preparation needs attention",
};
const stageStatusLabels: Record<string, string> = {
  queued: "waiting", running: "running", waiting: "waiting",
  cancelling: "stopping", cancelled: "stopped", completed: "complete",
  partial: "needs attention", blocked: "needs attention", interrupted: "recovering",
};
function ProgressMessage({message}: {message: unknown}) {
  const text = String(message || "");
  if (text.length <= 220 && !text.includes("\n")) return <>{text}</>;
  const firstLine = text.split("\n")[0];
  return <details><summary>{firstLine.slice(0, 180)}{firstLine.length > 180 ? "…" : ""} · Details</summary><pre>{text}</pre></details>;
}
export function selectPreparation(runs: Data[], selection: Selection): Data | undefined {
  const applicable = runs.filter(run => selection.locator ? run.locator === selection.locator && (!selection.program || !run.program || run.program === selection.program || run.programs?.includes(selection.program)) : Boolean(selection.slug) && run.slug === selection.slug);
  return applicable.sort((a, b) => Number(active(b.status)) - Number(active(a.status)) || Number(b.updatedAt || 0) - Number(a.updatedAt || 0))[0];
}
function WorkflowControls({run,selection,notify,compact=false}:{run:Data;selection:Selection;notify:Notify;compact?:boolean}) {
  const [busy,setBusy]=useState(''),[error,setError]=useState(''),[hours,setHours]=useState(24),[budgetMode,setBudgetMode]=useState('unlimited');
  useEffect(()=>{setBudgetMode(run.budgetSeconds==null?'unlimited':'finite');if(typeof run.budgetSeconds==='number')setHours(Math.max(1,Math.ceil(run.budgetSeconds/3600)));},[run.id]);
  async function control(operation:string){
    if(busy)return;setBusy(operation);setError('');
    try {const result=await request('/dashboard/api/jobs',{method:'POST',body:JSON.stringify({action:'workbench.workflow-control',params:{preparation_id:run.id,operation,...(operation==='budget'?{seconds:budgetMode==='unlimited'?null:Math.round(hours*3600)}:{})},context:selection,confirm:true})});notify(`${operation==='budget'?'Budget change':operation==='pause'?'Pause':operation==='resume'?'Resume':'Stop'} requested`, 'info',{jobId:result.job?.id,target:run.locator||run.slug});}
    catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy('');}
  }
  return <div className="workflow-controls">{active(run.status)&&<><button type="button" disabled={Boolean(busy)} onClick={()=>void control('pause')}>Pause</button><button type="button" disabled={Boolean(busy)} onClick={()=>void control('stop')}>Stop</button></>}{run.status==='paused'&&(!run.deadline||run.deadline>Date.now()/1000)&&<button type="button" disabled={Boolean(busy)} onClick={()=>void control('resume')}>Resume</button>}{!compact&&<details><summary>Execution budget · {run.deadline==null?'Unlimited':'Limited'}</summary><p>Unlimited work has no wall-clock deadline. Per-function attempt limits and prerequisite checks still apply. A budget is not an estimate of completion.</p>{run.deadline!=null?<p>{Math.max(0,Math.ceil((run.deadline-Date.now()/1000)/60))} minutes remaining</p>:<p>No execution deadline</p>}<label>Budget <select name="workflow-budget" aria-label="Workflow execution budget" value={budgetMode} onChange={e=>setBudgetMode(e.target.value)}><option value="unlimited">Unlimited</option><option value="finite">Time allowance</option></select></label>{budgetMode==='finite'&&<label>Hours from now <input name="workflow-budget-hours" aria-label="Workflow execution budget hours" type="number" min={1} max={168} value={hours} onChange={e=>setHours(Number(e.target.value))}/></label>}<button type="button" disabled={Boolean(busy)||(budgetMode==='finite'&&(!Number.isFinite(hours)||hours<1||hours>168))} onClick={()=>void control('budget')}>{budgetMode==='unlimited'?'Use unlimited budget':'Set time allowance'}</button></details>}{busy&&<span role="status">Submitting {busy}…</span>}<ErrorLine error={error}/></div>;
}
export function PreparationProgress({ run, selection, notify, error = "", loading = false, lastConnectedAt, now = Date.now(), compact = false }: {
  run?: Data; selection: Selection; notify: Notify; error?: string; loading?: boolean; lastConnectedAt?: number; now?: number; compact?: boolean;
}) {
  const stages: Data[] = run?.stages || [];
  const current = active(run?.status) ? stages.find(stage => stage.status === "running" || stage.status === "waiting" || stage.status === "cancelling") || stages.find(stage => stage.status === "queued") : undefined;
  const recent = run?.events?.at(-1);
  const currentProgress = stageDisplayProgress(current);
  const programCount = Array.isArray(run?.programs) ? run.programs.length : currentProgress.primary?.total || 0;
  const workMeasured = Boolean(currentProgress.secondary);
  const stale = Boolean(error) || Boolean(lastConnectedAt && now - lastConnectedAt > 10000);
  const currentJob = run?.currentJob;
  const startedAt = currentJob?.startedAt || currentJob?.started_at || current?.startedAt;
  const elapsed = startedAt ? Math.max(0, Math.floor((now - Number(startedAt) * 1000) / 1000)) : null;
  const pair = currentJob?.params?.src && currentJob?.params?.dst
    ? `${currentJob.params.src} → ${currentJob.params.dst}` : '';
  const program = pair || currentJob?.params?.programPath || currentJob?.params?.program || current?.currentProgram || run?.program;
  const action = currentJob?.title || currentJob?.actionId || current?.currentAction;
  const actionName = String(action || "").replace(/^mcp\./, "").replace(/[-_]/g, " ");
  const operation = /execute script/i.test(actionName) ? ({analysis: "Check existing analysis", facts: "Index functions and relationships", bsim: "Build similarity signatures"} as Record<string,string>)[current?.key] || actionName : /analyze program/i.test(actionName) ? "Analyze binary" : /match pair/i.test(actionName) ? "Compare related builds" : actionName;
  const state = currentJob?.status || current?.jobStatus || run?.status;
  const updated = run?.updatedAt ? new Date(run.updatedAt * 1000) : null;
  const executionDeadline = Number(current?.executionDeadlineAt || 0);
  const executionLimit = Number(current?.executionLimitSeconds || 0);
  // The workflow budget is authoritative.  A legacy per-call timer must not
  // turn an unlimited workflow into a visible deadline after reconnect.
  const deadlineRemaining = run?.deadline != null && executionDeadline
    ? Math.max(0, Math.ceil((executionDeadline - now / 1000) / 60))
    : null;
  const statusLabel = run
    ? (statusLabels[String(run.status)] || `Preparation ${run.status}`)
    : loading ? "Checking preparation status…" : selection.locator || selection.slug ? "No preparation job reported for this selection" : "Open a project to prepare its binaries";
  return <div className={`preparation-progress${compact ? " preparation-compact" : ""}`} aria-busy={loading}>
    {!compact ? (
      <div className="preparation-status" role="status" aria-live="polite">
        <strong>{statusLabel}</strong>
        <span>{stale ? "Connection lost · retrying; showing last received state" : run ? "Connected" : ""}</span>
      </div>
    ) : (!run || stale) ? (
      <div className="preparation-status preparation-status-compact" role="status" aria-live="polite">
        <strong>{!run ? statusLabel : stale ? "Connection lost · retrying" : null}</strong>
      </div>
    ) : null}
    {run && <>
      {!compact && <>
        <p className="preparation-scope">{run.program ? `Program · ${run.program}` : `Project-wide · ${run.locator || selection.locator}`}</p>
        <div className="preparation-current">
          <span>{state === "queued" ? "Waiting for a worker" : state === "cancelling" ? "Waiting for accepted work to stop" : state === "disconnected" ? "Connection unavailable; saved workflow state is retained" : state === "resync" ? "Reconciling saved workflow state" : state === "resumable" ? "Resume from the recorded checkpoint" : current?.title || "Recorded result"}</span>
          {program && <code title={program}>{program}</code>}
          {operation && <span title={actionName}>{operation}</span>}
          <span>{programCount} programs</span>
          {elapsed !== null && active(state) && <span>Current job {elapsed}s elapsed</span>}
          {deadlineRemaining !== null && active(state) && <span title="Execution bound, not a completion estimate">Execution limit: {deadlineRemaining}m remaining{executionLimit ? ` of ${Math.ceil(executionLimit / 60)}m` : ""}</span>}
        </div>
      </>}
      {workMeasured && currentProgress.secondary && <div className="preparation-live-work" role="status"><strong>{current?.title}: {stageProgressLabel(currentProgress.secondary)}</strong><progress value={currentProgress.secondary.completed} max={currentProgress.secondary.total} aria-label={`${current?.title}: ${currentProgress.secondary.completed} of ${currentProgress.secondary.total} ${currentProgress.secondary.unit}`}/>{currentProgress.secondary.currentTarget && <code>{currentProgress.secondary.currentTarget}</code>}</div>}
      {!compact && <ol className="preparation-rail" aria-label="Preparation stages">
        {stages.map(stage => {
          const { primary, secondary } = stageDisplayProgress(stage);
          const measured = Boolean(primary);
          return <li key={stage.key} data-state={stage.status} aria-current={stage === current ? "step" : undefined}>
            <div><strong>{stage.title}</strong><span>{stageStatusLabels[String(stage.status)] || stage.status}</span></div>
            {measured && primary ? <progress max={primary.total} value={primary.completed} aria-label={`${stage.title}: ${primary.completed} of ${primary.total}`} /> : active(stage.status) && stage.status !== "queued" ? <progress aria-label={`${stage.title}: progress not yet measured`} /> : <div className="preparation-track" />}
            <small>{measured && primary ? stageProgressLabel(primary) : stage.total === 0 ? "No applicable items" : stage.status === "queued" ? "Waiting for preceding work" : "Awaiting a measured counter from the active operation"}</small>
            {secondary && <small className="preparation-subprogress">{stageProgressLabel(secondary)}</small>}
            {stage.status === 'waiting' && stage.nextFallback && <small>{stage.nextFallback}{stage.retryAt?` · next attempt ${new Date(stage.retryAt*1000).toLocaleTimeString()}`:''}{stage.attempts?` · attempt ${stage.attempts}`:''}</small>}
            {stage.reason && <div className="preparation-reason"><ProgressMessage message={stage.reason} /></div>}
          </li>;
        })}
      </ol>}
      {run.admissionPending&&<p role="status">Waiting for a project worker. Work starts automatically when one becomes available.</p>}
      {run.status==='paused'&&<p>Workflow paused. Accepted native operations may finish before the pause takes effect.</p>}
      {["disconnected","resync","resumable"].includes(String(run.status))&&<p role="status">No new completion is implied while this workflow is recovering. Refreshing this view reconciles the durable record.</p>}
      {(run.error || run.reason) && <p className="error">{run.error || run.reason}</p>}
      {recent && <div className="preparation-latest"><time>{new Date(recent.at * 1000).toLocaleTimeString()}</time> <ProgressMessage message={recent.message} /></div>}
      <div className="preparation-footer">
        {!compact && updated && <time dateTime={updated.toISOString()}>Last change {updated.toLocaleTimeString()}{active(run.status) ? ` · ${Math.max(0, Math.floor((now - updated.getTime()) / 1000))}s ago` : ""}</time>}
        {!compact && lastConnectedAt ? <span>Last received {Math.max(0, Math.floor((now - lastConnectedAt) / 1000))}s ago</span> : null}
        {!compact && <span>Stage completion is not byte verification.</span>}
        <WorkflowControls run={run} selection={selection} notify={notify} compact={compact}/>
      </div>
      {!compact && <PrefDetails pref="prep.events-open" className="preparation-events" summary={`Activity history (${run.events?.length || 0})`}><ol>{(run.events || []).map((event: Data, index: number) => <li key={`${event.at}:${index}`}><time>{new Date(event.at * 1000).toLocaleTimeString()}</time><div><ProgressMessage message={event.message} /></div></li>)}</ol></PrefDetails>}
    </>}
    <ErrorLine error={error} />
  </div>;
}
export function PreparationActivity({ selection, notify }: SurfaceProps) {
  const { runs, error, loading, lastConnectedAt, now } = usePreparationFeed();
  const run = selectPreparation(runs, selection);
  const [childJob, setChildJob] = useState<Data | undefined>();
  const childId = run?.stages?.find((stage: Data) => stage.status === "running")?.jobId;
  const runId = run?.id;
  useEffect(() => {
    let alive = true, timer: ReturnType<typeof setTimeout>;
    setChildJob(undefined);
    if (!run) return;
    async function pollJob() {
      try {
        const data = await request('/dashboard/api/jobs');
        const children: Data[] = (data.jobs || []).filter((job: Data) => job.params?.run === `prepare-${runId}` && active(String(job.status)));
        children.sort((left, right) => left.status === 'running' ? -1 : right.status === 'running' ? 1 : Number(right.createdAt || 0) - Number(left.createdAt || 0));
        const job = children[0] || (childId ? (await request(`/dashboard/api/jobs/${encodeURIComponent(childId)}`)).job : undefined);
        if (alive) setChildJob(job);
      }
      catch { /* Preparation state remains useful when a child job is unavailable. */ }
      finally { if (alive) timer = setTimeout(pollJob, 2000); }
    }
    void pollJob();
    return () => { alive = false; clearTimeout(timer); };
  }, [childId, runId]);
  const displayed = run && childJob ? {...run, currentJob: childJob} : run;
  return <Section id="preparation" title="Prepare the project"><PreparationProgress run={displayed} selection={selection} notify={notify} error={error} loading={loading} lastConnectedAt={lastConnectedAt} now={now} /></Section>;
}
