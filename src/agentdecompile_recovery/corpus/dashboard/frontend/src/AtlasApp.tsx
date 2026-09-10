import {UnifiedActivity} from './UnifiedActivity';
import {SourceDownload} from './SourceDownload';
import {SourceEditor,sourceWitness,sourceExtent,useFunctionEvidence} from './SourceEditor';
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  API,
  emptySelection,
  normalizeSelection,
  query,
  request,
  recordedSelection,
  type Data,
  type Selection,
  type ActionRequest,
} from "./contracts";
import { ActionRunner, DialogFrame } from "./Actions";
import { ProjectDialog } from "./ProjectDialog";
import { RecordView, ResizeBar, useData, usePref } from "./ui";
import "./atlas.css";
import { useLibraryTransfer } from "./BinaryLibrary";
import { AtlasAnalysis } from "./AtlasAnalysis";
import { PersistentExplorer } from "./PersistentExplorer";
import { PreparationProgress, selectPreparation } from "./PreparationActivity";
import { matchingStageSummary, stageDisplayProgress, stageProgressLabel } from "./preparationProgress";
import { StageTrace } from "./StageTrace";
import {
  installSessionFlush,
  queueSessionSave,
  setSessionRevision,
} from "./sessionSync";
const number = (value: unknown) =>
  typeof value === "number" ? value.toLocaleString() : "—";
const title = (s: Partial<Selection>) =>
  (s.program || s.locator || s.slug || "Project").split("/").pop();
import {
  canonicalProjectLocator,
  projectLocatorsMatch,
} from "./projectLocator";
const measuredStage = (stage?: Data) => stageDisplayProgress(stage).primary;
function workbenchUrl(selection: Selection, windowId = "") {
  // Static workbench page (workbench-app.js) — not the Vite React shell.
  const params = new URLSearchParams(query(selection));
  if (windowId) {
    const id = windowId.startsWith("wb-") ? windowId : `wb-${windowId}`;
    params.set("window", id);
  }
  const qs = params.toString();
  return `/dashboard${qs ? `?${qs}` : ""}`;
}

function RecoveryStrip({ run, related }: { run?: Data; related: Data[] }) {
  const stages: Data[] = run?.stages || [];
  const current =
    stages.find((stage) => ["running", "waiting", "cancelling"].includes(String(stage.status))) ||
    stages.find((stage) => stage.status === "queued");
  const next = stages.find((stage) => stage !== current && stage.status === "queued");
  const matching = stages.find((stage) => stage.key === "matching");
  const byteAudit = stages.find((stage) => stage.key === "verify-byte-accuracy");
  const auditStatus = String(byteAudit?.status || "queued");
  const relatedLabel =
    matching?.status === "completed"
      ? `${related.length} related build${related.length === 1 ? "" : "s"}`
      : matching?.status === "running"
        ? "matching"
        : "match queued";
  const gateLabel =
    auditStatus === "completed"
      ? "byte audit recorded"
      : auditStatus === "running"
        ? "byte audit running"
        : auditStatus === "blocked" || auditStatus === "failed"
          ? "byte audit blocked"
          : "byte gate waiting";
  return (
    <p className="atlas-recovery-strip" role="status">
      <span>
        Now <strong>{current?.title || "Waiting for workflow"}</strong>
        {measuredStage(current) ? ` · ${stageProgressLabel(measuredStage(current)!)}` : ""}
      </span>
      <span>{relatedLabel}</span>
      <span className={`atlas-byte-chip state-${auditStatus}`}>{gateLabel}</span>
      {next ? <span>Next {next.title}</span> : null}
    </p>
  );
}
function ActivityJob({
  summary,
  notify,
  onRetry,
  selected=false,
  visible=true,
}: {
  onRetry: (job:Data)=>void;
  selected?:boolean;
  visible?:boolean;
  summary: Data;
  notify: (message: string, level?: string) => void;
}) {
  const [expanded, setExpanded] = useState(selected),
    [job, setJob] = useState<Data>(summary),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(false);
  useEffect(()=>{if(selected)setExpanded(true);},[selected]);
  useEffect(() => {
    if (!expanded||!visible) return;
    setLoading(true);
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    async function poll() {
      try {
        const result = await request(
          "/dashboard/api/jobs/" + encodeURIComponent(summary.id),
          { signal: controller.signal },
        );
        if (!alive) return;
        setJob(result.job);
        setLoading(false);
        setError("");
        if (["queued", "running", "cancelling"].includes(result.job.status))
          timer = setTimeout(poll, 1500);
      } catch (e) {
        if (alive) {
          setLoading(false);
          setError(e instanceof Error ? e.message : String(e));
          if (["queued", "running", "cancelling"].includes(summary.status))
            timer = setTimeout(poll, 3000);
        }
      }
    }
    void poll();
    return () => {
      alive = false;
      controller.abort();
      clearTimeout(timer);
    };
  }, [expanded, visible, summary.id, summary.status]);
  return (
    <details open={expanded} onToggle={(e) => setExpanded(e.currentTarget.open)}>
      <summary>
        {summary.title || summary.actionId} · {summary.status}
      </summary>
      {expanded && (
        <>
          <p>
            {job.params?.programPath ||
              job.params?.program ||
              job.params?.slug ||
              "Target not recorded"}{" "}
            · Job {summary.id}
          </p>
          {error && <p role="alert">{error}</p>}
          {["failed", "cancelled", "interrupted"].includes(job.status) && <button onClick={()=>onRetry(job)}>Retry with recorded parameters</button>}
          {["queued", "running", "cancelling"].includes(job.status) && (
            <button
              disabled={job.status === "cancelling"}
              onClick={() =>
                request(
                  "/dashboard/api/jobs/" +
                    encodeURIComponent(summary.id) +
                    "/cancel",
                  { method: "POST" },
                )
                  .then(() => {
                    setJob((j) => ({ ...j, status: "cancelling" }));
                    notify(
                      "Cancellation requested. Completed changes are not rolled back.",
                    );
                  })
                  .catch((e) => notify(e.message, "error"))
              }
            >
              Request cancellation
            </button>
          )}
          <pre>
            {loading && !Object.hasOwn(job, "log")
              ? "Loading job output…"
              : job.log || job.error || "No output recorded."}
          </pre>
          <details>
            <summary>Parameters and result metadata</summary>
            <RecordView
              value={{
                params: job.params,
                result: job.result,
                returncode: job.returncode,
              }}
            />
          </details>
        </>
      )}
    </details>
  );
}
function atlasUrl(selection?: Selection) {
  const params = new URLSearchParams(selection ? query(selection) : "");
  const mode = new URLSearchParams(location.search).get("mode");
  if (mode) params.set("mode", mode);
  return location.pathname + (params.size ? "?" + params.toString() : "");
}
export function AtlasApp() {
  const [selection, setSelection] = usePref<Selection>("atlas.selection",emptySelection),
    [loaded, setLoaded] = useState(false),
    [search, setSearch] = useState(""),
    [offset, setOffset] = useState(0),
    [revision, setRevision] = useState(0);
  const [explorerWidth,setExplorerWidth]=usePref("atlas.explorer-width",320);
  const [explorerOpen,setExplorerOpen]=usePref("atlas.explorer-open",true);
  const loadedRef = useRef(false);
  const selectionRef = useRef<Selection>(emptySelection);
  loadedRef.current = loaded;
  selectionRef.current = selection;
  const [dialog, setDialog] = useState<
      "open" | "create" | "copy" | "connection" | "import" | null
    >(null),
    [runs, setRuns] = useState<Data[]>([]),
    [jobs, setJobs] = useState<Data[]>([]),
    [batches,setBatches]=useState<Data[]>([]),
    [connection, setConnection] = useState("Connecting"),
    [prepareError, setPrepareError] = useState("");
  const [pendingProject, setPendingProject] = useState<Selection | null>(null);
  const [preparationFeedError,setPreparationFeedError]=useState("");
  const [lastPreparationAt,setLastPreparationAt]=useState(0);
  const [messages,setMessages]=usePref<Data[]>('atlas.activity',[]);
  const [activityOpen,setActivityOpen]=usePref('atlas.dock-open',true);
  const [dockHeight,setDockHeight]=usePref('atlas.dock-height',220);
  const explorerColumnWidth=Math.max(240,Math.min(560,explorerWidth));
  const dockOccupied=activityOpen?Math.max(120,dockHeight):36;
  const [seenAt,setSeenAt]=usePref('atlas.activity-seen',0);
  const [selectedJob,setSelectedJob]=useState('');
  const jobStatuses=useRef<Record<string,string>>({});
  const [recordFilter, setRecordFilter] = useState("all");
  const [toolsOpen, setToolsOpen] = useState(false),
    [action, setAction] = useState<ActionRequest | null>(null);
  const pendingJobs = useRef(new Set<string>());
  const openKey = useRef("");
  const mounted = useRef(true);
  const prepared = useRef(new Set<string>());
  const notify = useCallback(
    (message: string, level = "info", metadata:Data={}) =>
      setMessages((old) =>
        [...old, { ...metadata,id:crypto.randomUUID(),message,level,at:Date.now() }].slice(-500),
      ),
    [],
  );
  const refresh = useCallback(() => setRevision((v) => v + 1), []);
  const binaries = useData(API + "/binaries", revision),
    sessions = useData(API + "/sessions", revision);
  const sessionsRef = useRef<Data[]>([]);
  sessionsRef.current = sessions.data.sessions || [];
  const atlasActiveRef = useRef("");
  useEffect(() => {
    if (sessions.data.active) {
      atlasActiveRef.current = String(sessions.data.active);
    }
  }, [sessions.data.active]);
  useEffect(() => {
    if (sessions.loading) return;
    setSessionRevision(Number(sessions.data.revision || 0));
    installSessionFlush(() => ({
      active: atlasActiveRef.current || String(sessions.data.active || ""),
      sessions: sessionsRef.current,
    }));
  }, [sessions.loading, sessions.data.revision, sessions.data.active]);
  const detailResponse = useFunctionEvidence(
    loaded && selection.addr ? API + "/function?" + query(selection) : null,
    revision,
  );
  const detail = detailResponse.data.listing
    ? {
        ...detailResponse.data,
        ...detailResponse.data.listing,
        function: detailResponse.data.selected,
      }
    : detailResponse.data;
  const open = useCallback(
    (patch: Partial<Selection>, force = false) => {
      const next = normalizeSelection(patch);
      const savedSessions: Data[] = sessions.data.sessions || [];
      const savedActive = savedSessions.find((item) => item.id === sessions.data.active && !item.hidden && item.locator);
      const currentLocator = selectionRef.current.locator || String(savedActive?.locator || "");
      if (!force && currentLocator && next.locator && !projectLocatorsMatch(next.locator, currentLocator)) {
        // A direct deep link is still an attempt to load a different project.
        // Restore the saved project first so the operator can decide whether
        // to combine it; otherwise a reload bypasses the merge dialog.
        if (!loadedRef.current && savedActive) {
          const restored = normalizeSelection({
            ...(savedActive.selection || {}),
            locator: String(savedActive.locator),
            slug: String(savedActive.projectSlug || savedActive.slug || ""),
            program: String(savedActive.program || ""),
            addr: "",
            logicalId: "",
          });
          setSelection(restored);
          setLoaded(true);
          history.replaceState(null, "", atlasUrl(restored));
        }
        setPendingProject(next);
        return;
      }
      const key = JSON.stringify([next.locator, next.program, next.slug]);
      const selectionChanged = openKey.current !== key;
      openKey.current = key;
      setSelection(next);
      setLoaded(true);
      setOffset(0);
      setSearch("");
      setRecordFilter("all");
      setPrepareError("");
      history.replaceState(null, "", atlasUrl(next));
      if (next.locator)
        request(API + "/sessions")
          .then((data) => {
            const list: Data[] = data.sessions || [];
            const existing = list.find((s) => projectLocatorsMatch(s.locator, next.locator));
            const id = existing?.id || crypto.randomUUID();
            const item = {
              ...existing,
              hidden: false,
              id,
              // Session `title` from older versions often contains the last
              // selected binary.  A project locator is the reliable display
              // identity unless the operator explicitly assigned a label.
              title: existing?.userLabel || existing?.label || title(next),
              locator: next.locator,
              program: next.program,
              projectSlug: existing?.projectSlug || next.slug,
              selection: next,
              imports: Array.from(
                new Set(
                  [...(existing?.imports || []), next.slug].filter(Boolean),
                ),
              ),
            };
            atlasActiveRef.current = id;
            return queueSessionSave({
              active: id,
              sessions: [...list.filter((s) => s.id !== id), item],
            });
          })
          .then(refresh)
          .catch((e) =>
            notify(
              "Project opened, but recent-project state could not be saved: " +
                e.message,
              "error",
            ),
          );
      if (!prepared.current.has(key)) {
        prepared.current.add(key);
        request(API + "/prepare", {
          method: "POST",
          body: JSON.stringify(next),
        })
          .then(() => refresh())
          .catch((e) => {
            prepared.current.delete(key);
            if (mounted.current && openKey.current === key)
              setPrepareError(e.message);
          });
      }
    },
    [refresh, notify, sessions.data],
  );
  const requestOpen = useCallback((patch: Partial<Selection>) => open(patch), [open]);
  async function combineAndOpen() {
    if (!pendingProject) return;
    const incoming = pendingProject;
    const current = selection;
    setPendingProject(null);
    try {
      const snapshot = await request(API + "/sessions");
      const sessions: Data[] = snapshot.sessions || [];
      const currentSession = sessions.find(item => projectLocatorsMatch(item.locator, current.locator));
      const incomingSession = sessions.find(item => projectLocatorsMatch(item.locator, incoming.locator));
      const currentImports = [...new Set((currentSession?.imports || []).map(String).filter(Boolean))];
      const incomingImports = [...new Set((incomingSession?.imports || []).map(String).filter(Boolean))];
      const addedImports = incomingImports.filter(item => !currentImports.includes(item));
      const retainedImports = incomingImports.filter(item => currentImports.includes(item));
      const mergedImports = [...new Set([...currentImports, ...incomingImports, current.slug, incoming.slug].filter(Boolean))];
      const merged = {
        ...(incomingSession || {}),
        id: incomingSession?.id || crypto.randomUUID(),
        title: incomingSession?.title || title(incoming),
        locator: incoming.locator,
        hidden: false,
        imports: mergedImports,
        mergedFrom: [...new Set([...(incomingSession?.mergedFrom || []), current.locator].filter(Boolean))],
      };
      atlasActiveRef.current = String(merged.id);
      await queueSessionSave({
        active: merged.id,
        sessions: [...sessions.filter((item) => item.id !== merged.id), merged],
      });
      open(incoming, true);
      const detailLines = [
        `Loaded project: ${incoming.locator || title(incoming)}`,
        `Merged workspace record from: ${current.locator || title(current)}`,
        `Imports retained: ${mergedImports.length}`,
        `Imports newly linked from requested project: ${addedImports.length}${addedImports.length ? ` (${addedImports.join(", ")})` : ""}`,
        `Imports already present in both: ${retainedImports.length}${retainedImports.length ? ` (${retainedImports.join(", ")})` : ""}`,
        "Preserved: project-session imports and the link to the prior workspace record.",
        "Not merged: the two Ghidra databases, program files, or proof receipts. They remain separate and unchanged.",
      ];
      notify("Project workspace records combined", "info", {
        target: incoming.locator,
        details: detailLines.join("\n"),
        merge: {
          loadedProject: incoming.locator || title(incoming),
          retainedProject: current.locator || title(current),
          importsRetained: mergedImports.length,
          importsNewlyLinked: addedImports,
          importsAlreadyShared: retainedImports,
          scope: "Workspace imports and provenance link only; Ghidra databases and proof receipts remain separate.",
        },
      });
    } catch (error) {
      notify("Could not combine project data: " + (error instanceof Error ? error.message : String(error)), "error");
    }
  }
  useEffect(() => {
    mounted.current = true;
    const q = new URLSearchParams(location.search);
    if (sessions.loading) return;
    if (q.get("slug") || q.get("program") || q.get("locator")) {
      const patch = {
        slug: q.get("slug") || "",
        program: q.get("program") || "",
        locator: q.get("locator") || "",
        addr: q.get("addr") || "",
        logicalId: q.get("logical_id") || "",
      };
      const key = JSON.stringify([patch.locator, patch.program, patch.slug]);
      // Re-binding the same project from a sessions refresh must not re-enter
      // open() — that used to force the workspace view back to overview.
      if (!loadedRef.current || openKey.current !== key) open(patch);
    } else if (!loadedRef.current && (selection.slug || selection.program || selection.locator)) {
      open(selection);
    }
    return () => {
      mounted.current = false;
    };
  }, [open, sessions.loading]);
  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    let signature = "";
    async function poll() {
      try {
        const [preparationsResult, jobsResult] = await Promise.allSettled([
          request(API + "/preparations", {signal: AbortSignal.timeout(8000)}).then(data=>{
            if(!stopped){setRuns(data.runs||[]);setLastPreparationAt(Date.now());setPreparationFeedError("");}
            return data;
          }),
          request("/dashboard/api/jobs", {signal: AbortSignal.timeout(8000)}).then(data=>{
            if(!stopped)setJobs(data.jobs||[]);
            return data;
          }),
          request('/api/v1/batches',{signal:AbortSignal.timeout(8000)}).then(data=>{if(!stopped)setBatches(data.batches||[]);return data;}),
        ]);
        if (stopped) return;
        const p=preparationsResult.status==='fulfilled'?preparationsResult.value:null;
        const j=jobsResult.status==='fulfilled'?jobsResult.value:null;
        if(!p)setPreparationFeedError("Preparation updates unavailable. Showing the last received state.");
        for (const job of j?.jobs || []) {
          const previous=jobStatuses.current[job.id];
          if((previous&&previous!==job.status)||(!previous&&pendingJobs.current.has(job.id)&&!['queued','running','cancelling'].includes(job.status)))notify(`${job.title||job.actionId}: ${job.status}`,job.status==='failed'?'error':'info',{jobId:job.id,status:job.status,action:job.actionId,target:job.params?.programPath||job.params?.program||job.params?.slug});
          jobStatuses.current[job.id]=job.status;
          if (
            pendingJobs.current.has(job.id) &&
            !["queued", "running", "cancelling"].includes(job.status)
          ) {
            pendingJobs.current.delete(job.id);
            refresh();
          }
        }
        setConnection(p&&j?"Live":p?"Job updates unavailable":j?"Preparation updates unavailable":"Reconnecting");
        const next = JSON.stringify(
          (p?.runs || []).map((r: Data) => [
            r.id,
            r.status,
            (r.stages || []).map((s: Data) => [s.key, s.status, s.completed, s.total]),
          ]),
        );
        if (p && signature && signature !== next) refresh();
        if(p)signature = next;
      } catch {
        if (!stopped) setConnection("Reconnecting");
      } finally {
        if (!stopped) timer = setTimeout(poll, document.hidden ? 8000 : 2000);
      }
    }
    poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [refresh,notify]);
  useEffect(() => {
    document.querySelector(".atlas-shell")?.scrollTo({ top: 0 });
  }, [loaded, selection.addr, selection.locator]);
  const builds: Data[] = binaries.data.binaries || [];
  const liveLocators = useMemo(
    () =>
      [
        ...new Set(
          runs
            .filter((item) => ["queued", "running", "paused"].includes(String(item.status)) && item.locator)
            .map((item) => canonicalProjectLocator(item.locator)),
        ),
      ].filter(Boolean),
    [runs],
  );
  const ensureLiveProjectVisible = useCallback(
    async (locator: string) => {
      const key = canonicalProjectLocator(locator);
      if (!key) return;
      try {
        const snapshot = await request(API + "/sessions");
        const items: Data[] = snapshot.sessions || [];
        const existing = items.find((item) => projectLocatorsMatch(item.locator, key));
        if (existing && !existing.hidden) return;
        const record = existing
          ? { ...existing, hidden: false, locator: key }
          : {
              id: crypto.randomUUID(),
              title: key.split("/").pop() || "Project",
              locator: key,
              hidden: false,
              imports: [],
              selection: { ...emptySelection, locator: key },
            };
        await queueSessionSave({
          active: record.id,
          sessions: [...items.filter((item) => item.id !== record.id), record],
        });
        refresh();
      } catch (error) {
        notify(String(error), "error");
      }
    },
    [refresh, notify],
  );
  const libraryTransfer = useLibraryTransfer(builds, notify);
  const build = builds.find((b) => b.slug === selection.slug);
  const related = build ? builds.filter((b) => b.game === build.game) : [];
  const matchedRun = selectPreparation(runs, selection);
  const jobTarget = (job: Data, fallback: unknown) => {
    const source = job.params?.src;
    const target = job.params?.dst;
    return source && target ? `${source} → ${target}` : job.params?.programPath || job.params?.program || fallback;
  };
  const activeWorkflowJob = matchedRun && jobs
    .filter((job: Data) => job.params?.run === `prepare-${matchedRun.id}` && ["queued", "running", "cancelling"].includes(job.status))
    .sort((left: Data, right: Data) => (left.status === "running" ? -1 : right.status === "running" ? 1 : Number(right.createdAt || 0) - Number(left.createdAt || 0)))[0];
  const run: Data | undefined = matchedRun ? {...matchedRun, stages:(matchedRun.stages||[]).map((stage:Data)=>{
    const job=(stage.key === "matching" ? activeWorkflowJob : undefined) || jobs.find((item)=>item.id===stage.jobId);
    return job?{...stage,jobStatus:job.status,currentAction:job.title||job.actionId,currentProgram:jobTarget(job,stage.currentProgram),startedAt:job.startedAt||stage.startedAt}:stage;
  }).map((stage:Data, index:number, stages:Data[])=>{
    const activeIndex=stages.findIndex((candidate:Data)=>candidate.key===matchedRun.currentStage);
    if(activeIndex>=0 && index>activeIndex && stage.status==='running') return {...stage,status:'queued',reason:stage.reason||`Waiting for ${stages[activeIndex].title||matchedRun.currentStage} to complete.`};
    return stage;
  })}:undefined;
  // The durable preparation feed is intentionally independent of the job
  // output endpoint.  Under a heavy Ghidra operation that endpoint can be
  // slow, but the dock must still show the admitted work rather than saying
  // there are no active jobs.
  const workflowJobs: Data[] = (run?.stages || [])
    .filter((stage: Data) => stage.jobId && ["queued", "running", "waiting", "cancelling"].includes(String(stage.status)))
    .map((stage: Data) => ({
      id: String(stage.jobId),
      actionId: String(stage.currentAction || stage.key || "workflow-stage"),
      title: String(stage.currentAction || stage.title || stage.key || "Workflow stage"),
      status: stage.jobStatus || stage.status,
      startedAt: stage.startedAt || run?.startedAt,
      params: {locator: selection.locator, program: stage.currentProgram || run?.currentProgram || selection.program},
      logState: "pending",
      logReason: "Live workflow status is available; job output is still being collected.",
      workflowDerived: true,
    }));
  const activityJobs = [...jobs, ...workflowJobs.filter((candidate) => !jobs.some((job) => job.id === candidate.id))];
  const source = sourceWitness(detail);
  const graph = detail.graph || {};
  const selectedName =
    detail.function?.name || detail.selected?.name || selection.addr;
  const selectContext = (patch: Partial<Selection>) => {
    const changed = (patch.slug !== undefined && patch.slug !== selection.slug) ||
      (patch.program !== undefined && patch.program !== selection.program) ||
      (patch.locator !== undefined && patch.locator !== selection.locator);
    const next = normalizeSelection({...selection,...(changed ? {addr:'',logicalId:''}:{}),...patch});
    if (changed) {setOffset(0);setSearch('');}
    const url=atlasUrl(next);
    if(url!==location.pathname+location.search){
      const scroll=document.querySelector('.atlas-shell')?.scrollTop||0;
      history.replaceState({...history.state,atlas:{search,offset,recordFilter,scroll}},'',location.href);
      history.pushState({atlas:{search:changed?'':search,offset:changed?0:offset,recordFilter,scroll}},'',url);
    }
    setSelection(next);
  };
  useEffect(()=>{
    const restore=(event:PopStateEvent)=>{
      const params=new URLSearchParams(location.search);
      const next=normalizeSelection({slug:params.get('slug')||'',program:params.get('program')||'',locator:params.get('locator')||'',addr:params.get('addr')||'',logicalId:params.get('logical_id')||''});
      setSelection(next);setLoaded(Boolean(next.slug||next.program||next.locator));
      const saved=event.state?.atlas;
      if(saved){setSearch(saved.search||'');setOffset(saved.offset||0);setRecordFilter(saved.recordFilter||'all');requestAnimationFrame(()=>document.querySelector('.atlas-shell')?.scrollTo({top:saved.scroll||0}));}
      // Navigation restores context only. Previously admitted work keeps running.
    };
    window.addEventListener('popstate',restore);return()=>window.removeEventListener('popstate',restore);
  },[]);
  async function projectVisibility(record:Data,hidden:boolean) {
    const snapshot=await request(API+'/sessions');
    const items:Data[]=snapshot.sessions||[];
    const recordKey=canonicalProjectLocator(record.locator);
    const next=items.map(item=>canonicalProjectLocator(item.locator)===recordKey?{...item,hidden}:item);
    if(!next.some(item=>canonicalProjectLocator(item.locator)===recordKey))next.push({...record,id:record.id||crypto.randomUUID(),hidden});
    let nextActive=snapshot.active;
    const activeItem=items.find(item=>item.id===snapshot.active);
    if(hidden&&activeItem&&canonicalProjectLocator(activeItem.locator)===recordKey){let fallback=next.find(item=>!item.hidden);if(!fallback){fallback={id:crypto.randomUUID(),title:'Untitled',locator:'',imports:[],selection:emptySelection};next.push(fallback);}nextActive=fallback.id;}
    await queueSessionSave({active:nextActive,sessions:next});
    if(hidden&&projectLocatorsMatch(selection.locator, record.locator)){setSelection(emptySelection);setLoaded(false);history.replaceState(null,'',atlasUrl());}
    refresh();notify(hidden?'Project removed from workspace. Files and background work remain available.':'Project restored to workspace.','info',{target:record.locator});
  }
  const submitted = (data: Data) => {
    if (data.job?.id) pendingJobs.current.add(data.job.id);
    refresh();
  };
  const surfaceProps = {
    selection,
    onSelect: selectContext,
    onInspectSource: () => undefined,
    onAction: (id: string, params: Data = {}, targets?: Selection[]) =>
      setAction({ id, params, targets: targets || [{ ...selection }] }),
    notify,
    revision,
    onBrowseFunctions: (scope: {
      slugs: string[];
      program?: string;
      locator?: string;
      filter: "all" | "named" | "bound" | "real-c";
    }) => {
      selectContext({
        ...emptySelection,
        slug: scope.slugs[0] || "",
        program: scope.program || "",
        locator: scope.locator || "",
      });
      setSearch("");
      setOffset(0);
      setRecordFilter(scope.filter);
    },
  };
  const [editorSurface,setEditorSurface]=usePref('atlas.editor-surface','source');
  async function saveWorkspace(){try{const snapshot=await request(API+'/sessions');const existing=(snapshot.sessions||[]).find((item:Data)=>projectLocatorsMatch(item.locator, selection.locator)&&(selection.locator||item.selection?.slug===selection.slug));const record={...(existing||{id:crypto.randomUUID(),title:title(selection),locator:selection.locator}),selection,program:selection.program,hidden:false,imports:[...new Set([...(existing?.imports||[]),selection.slug].filter(Boolean))]};await queueSessionSave({active:record.id,sessions:[...(snapshot.sessions||[]).filter((item:Data)=>item.id!==record.id),record]});notify('Workspace saved. Project selection and imports retained.','info',{target:selection.locator||selection.slug});refresh();}catch(error){notify(String(error),'error');}}
  const goHome = () => {
    setLoaded(false);
    setSelection(emptySelection);
    history.replaceState(null, "", atlasUrl());
  };
  const callers = (graph.callers || detail.callers || []) as Data[];
  const callees = (graph.callees || detail.callees || []) as Data[];
  return (
    <div className="atlas-app">
      {explorerOpen && <div id="atlas-explorer" className="atlas-explorer-column" style={{width:explorerColumnWidth,height:`calc(100dvh - ${dockOccupied}px)`}}>
        <PersistentExplorer onProjectVisibility={projectVisibility} notify={notify} libraryLoading={binaries.loading} libraryError={binaries.error} liveLocators={liveLocators} builds={builds} projects={sessions.data.sessions||[]} unresolved={binaries.data.unresolvedBinaries||[]} selection={selection} onSelect={patch=>{if(patch.slug!==undefined||patch.locator!==undefined)requestOpen({...selection,...patch});else{selectContext(patch);setLoaded(true);}}} onAdd={libraryTransfer.stage} dropProps={libraryTransfer.dropProps} revision={revision} recordFilter={recordFilter} onRecordFilterChange={setRecordFilter} onImport={()=>setDialog("import")} onCreate={()=>setDialog("create")}/>
        <ResizeBar axis="x" label="Resize binary explorer" onResize={delta=>setExplorerWidth(w=>Math.max(240,Math.min(560,w+delta)))}/>
      </div>}
      <div className="atlas-shell" style={{height:`calc(100dvh - ${dockOccupied}px)`,overflow:'auto',paddingBottom:16}}>
        {libraryTransfer.confirmation}
        <header className="atlas-top atlas-context-toolbar">
          <strong className="atlas-wordmark" title="AgentDecompile">AD<span> / </span></strong>
          {loaded?<button type="button" className="atlas-home-link" onClick={goHome} title="Clear selection and return to workspace home">Workspace</button>:<span className="atlas-home-link" aria-current="page">Workspace</span>}
          <span className="atlas-current-context" title={selection.locator||selection.program||selection.slug}>{loaded?title(selection):'Choose a project in the explorer'}</span>
          <span className="atlas-connection" title={'Backend '+connection}>{connection}</span>
          <button type="button" aria-controls="atlas-explorer" aria-expanded={explorerOpen} onClick={()=>setExplorerOpen(open=>!open)}>{explorerOpen?"Hide navigator":"Show navigator"}</button>
          <a className="atlas-workbench-link" href={workbenchUrl(selection, "pipeline")}>Workbench ↗</a>
          <button onClick={()=>setToolsOpen(true)} aria-label="Project tools">Tools</button>
        </header>
        {!loaded ? (
          <main className="atlas-landing atlas-workspace-empty">
            <StageTrace run={undefined} loading={!lastPreparationAt && !preparationFeedError} />
            <h1>Workspace</h1>
            <p>Select a project or binary in the explorer. The stage trace arms when a workflow is admitted.</p>
            <p>Dense recover, compare, and program-browser controls live on the <a href={workbenchUrl(emptySelection)}>workbench</a>.</p>
            {runs.filter(item=>["queued","running","paused"].includes(String(item.status))&&item.locator).map(item=>
              <button key={item.id} className="atlas-live-run" type="button" onClick={()=>{void ensureLiveProjectVisible(String(item.locator)).finally(()=>requestOpen({locator:item.locator,slug:item.slug||"",program:item.program||""}));}}>
                Open live workflow · {(item.locator||"").split("/").pop()} · {matchingStageSummary(item)||item.status}
              </button>
            )}
            {binaries.error&&<p role="alert">{binaries.error}</p>}
          </main>
        ) : (
          <main className="atlas-work atlas-view-work">
            <StageTrace run={run} loading={!lastPreparationAt && !preparationFeedError} />
            <RecoveryStrip run={run} related={related} />
            <div className="atlas-work-context">
              <span className="atlas-context-platform">{build?.platform || "Project evidence"}</span>
              <a className="atlas-workbench-link" href={workbenchUrl(selection, "pipeline")}>Recover &amp; verify on workbench ↗</a>
              {(selection.slug || selection.program) && <SourceDownload selection={selection} notify={notify} />}
            </div>
            <div className="atlas-preparation-primary" role="region" aria-label="Workflow controls">
              <PreparationProgress
                run={run}
                selection={selection}
                notify={notify}
                error={preparationFeedError}
                loading={!lastPreparationAt && !preparationFeedError}
                lastConnectedAt={lastPreparationAt}
                compact
              />
            </div>
            {prepareError && (
              <div className="atlas-error" role="alert">
                Preparation admission: {prepareError}
                <span>Accepted work keeps running. Admission details stay in the activity dock.</span>
              </div>
            )}

            <div className="atlas-function-layout">
              <section className="atlas-function-detail">
                {!selection.addr ? (
                  <div className="atlas-function-empty">
                    {(selection.slug || selection.program) ? (
                      <AtlasAnalysis {...surfaceProps} />
                    ) : (
                      <>
                        <span>ƒ</span>
                        <h2>Select a binary or function</h2>
                        <p>Use the explorer to open a build, then pick a function. Pipeline stages keep updating above.</p>
                      </>
                    )}
                  </div>
                ) : (
                  <>
                    <header className="atlas-function-heading">
                      <code>{selection.addr}</code>
                      <h1 title={selectedName}>{selectedName}</h1>
                      <select aria-label="Editor evidence surface" value={editorSurface} onChange={(event) => setEditorSurface(event.target.value)}>
                        <option value="source">Source</option>
                        <option value="assembly">Assembly</option>
                        <option value="compare">Source + assembly</option>
                      </select>
                    </header>
                    {detailResponse.error && <p role="alert">{detailResponse.error}</p>}
                    {detailResponse.loading && <p role="status">Loading evidence…</p>}
                    <div className={"atlas-code-grid editor-surface-" + editorSurface}>
                      <article className="atlas-source-pane" hidden={editorSurface === "assembly"}>
                        <SourceEditor selection={selection} value={source} loading={detailResponse.loading} extent={sourceExtent(detail)} />
                      </article>
                      <article className="atlas-assembly-pane" hidden={editorSurface === "source"}>
                        <SourceEditor selection={selection} value={detail.assembly?.text || detail.disassembly?.text || ""} kind="assembly" loading={detailResponse.loading} />
                      </article>
                    </div>
                    <div className="atlas-edge-strip" aria-label="Callers and callees">
                      <div>
                        <span>Callers</span>
                        {callers.slice(0, 8).map((r: Data, i: number) => (
                          <button key={`caller-${i}`} type="button" onClick={() => selectContext({addr: String(r.addr || r.address), logicalId: ""})}>
                            <code>{r.addr || r.address}</code> {r.name || "Unnamed"}
                          </button>
                        ))}
                        {!callers.length && <em>None recorded</em>}
                      </div>
                      <div>
                        <span>Callees</span>
                        {callees.slice(0, 8).map((r: Data, i: number) => (
                          <button key={`callee-${i}`} type="button" onClick={() => selectContext({addr: String(r.addr || r.address), logicalId: ""})}>
                            <code>{r.addr || r.address}</code> {r.name || "Unnamed"}
                          </button>
                        ))}
                        {!callees.length && <em>None recorded</em>}
                      </div>
                      {(graph.callersTruncated || graph.calleesTruncated) && <p>Additional edges omitted by the server.</p>}
                    </div>
                    <p className="atlas-proof-note">
                      No byte-verification claim is inferred from source text, names, or job completion.{" "}
                      <a href={workbenchUrl(selection, "fnbrowse")}>Inspect on workbench ↗</a>
                    </p>
                  </>
                )}
              </section>
            </div>
          </main>
        )}

      </div>
      <section className={'atlas-activity-dock '+(activityOpen?'expanded':'collapsed')} style={{height:activityOpen?Math.max(120,dockHeight):36,left:explorerOpen?explorerColumnWidth:0}} aria-label="Activity dock">
        {activityOpen&&<ResizeBar axis="y" label="Resize activity dock" onResize={delta=>setDockHeight(h=>Math.max(120,Math.min(window.innerHeight*.65,h-delta)))}/>}
        <UnifiedActivity jobs={activityJobs} events={messages} batches={batches} expanded={activityOpen} onToggle={()=>setActivityOpen(v=>!v)} notify={notify} onRetry={job=>setAction({id:job.actionId,params:job.params,targets:[recordedSelection(job,selection)]})} onRetryBatch={batch=>setAction({id:batch.action,params:batch.results[0]?.params,targets:batch.results.filter((row:Data)=>row.status!=='ok').map((row:Data)=>row.context)})}/>
      </section>
      <ActionRunner
        request={action}
        selection={selection}
        onClose={() => setAction(null)}
        notify={notify}
        onSubmitted={submitted}
      />
      {toolsOpen && (
        <DialogFrame
          title="Project tools"
          onClose={() => setToolsOpen(false)}
        >
          <div className="atlas-tools">
            <div className="atlas-workspace-commands">
              <button onClick={()=>{setToolsOpen(false);setDialog('open');}}>Open existing project</button>
              <button onClick={()=>{setToolsOpen(false);setDialog('create');}}>Create project</button>
              <button onClick={()=>{setToolsOpen(false);setDialog('import');}}>Add binaries</button>
              <button onClick={()=>void saveWorkspace()}>Save workspace</button>
              <button disabled={!selection.locator} onClick={()=>{setToolsOpen(false);setDialog('copy');}}>Copy project…</button>
              <button onClick={()=>{setToolsOpen(false);setDialog('connection');}}>Save connection…</button>
            </div>
            <p className="atlas-tools-handoff">
              Compare builds, recover forms, program listings, reversing guides, and the full action catalogue stay on the{" "}
              <a href={workbenchUrl(selection)}>workbench</a>.
            </p>
          </div>
        </DialogFrame>
      )}
      <ProjectDialog
        mode={dialog}
        selection={selection}
        onClose={() => setDialog(null)}
        onSelect={requestOpen}
        notify={notify}
        onRefresh={refresh}
      />
      {pendingProject && <DialogFrame title="Load another project?" onClose={()=>setPendingProject(null)}>
        <p>A project is already loaded.</p>
        <div className="project-merge-summary"><strong>Current project</strong><code>{selection.locator || title(selection)}</code><strong>Requested project</strong><code>{pendingProject.locator || title(pendingProject)}</code></div>
        <p>Combine recorded imports, evidence links, and workspace metadata, then load the requested project. The original Ghidra databases remain preserved; this action never deletes or silently overwrites either project.</p>
        <div className="dialog-actions"><button onClick={()=>setPendingProject(null)}>Keep current project</button><button onClick={()=>void combineAndOpen()}>Combine data and load requested project</button></div>
      </DialogFrame>}
    </div>
  );
}
