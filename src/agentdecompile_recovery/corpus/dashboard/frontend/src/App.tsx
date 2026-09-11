import {UnifiedActivity} from './UnifiedActivity';
import { useCallback, useEffect, useRef, useState } from "react";
import {
  API,
  emptySelection,
  normalizeSelection,
  functionKey,
  request,
  recordedSelection,
  type ActionRequest,
  type Data,
  type Notify,
  type Selection,
} from "./contracts";
import {
  ErrorLine,
  jump as jumpTo,
  readPref,
  ResizeBar,
  savePref,
  useData,
  usePref,
} from "./ui";
import { WorkbenchSurfaces, EvidenceInspector } from "./Surfaces";
import { Commands, ActionRunner, DialogFrame } from "./Actions";
import { PreparationActivity } from "./PreparationActivity";
import { CodeBrowser } from "./CodeBrowser";
import { GuideWorkflows } from "./GuideWorkflows";
import { useLibraryTransfer } from "./BinaryLibrary";
import { PersistentExplorer } from "./PersistentExplorer";
import { useEntityActivity } from "./activity";
import { ProjectDialog } from "./ProjectDialog";
import {
  installSessionFlush,
  loadClientSessions,
  queueSessionSave,
  setSessionRevision,
} from "./sessionSync";
import { ensureWorkspaceState, patchWorkspaceState } from "./workspaceState";
import { projectLocatorsMatch } from "./projectLocator";
import { SourceDownload } from "./SourceDownload";
import { WorkbenchIntegration } from "./integration/WorkbenchIntegration";
import { CorpusDbPicker } from "./CorpusDbPicker";
import { LocalArtifactPanel } from "./runtime/LocalArtifactPanel";
import "./actions.css";
const sectionNames: Record<string,string> = {
  overview: "Project overview", preparation: "Preparation status", listing: "Source and assembly",
  "code-browser": "Browse program data", guide: "Reversing workflows", graph: "Call relationships",
  logical: "Equivalent functions", review: "Review evidence", pipeline: "Pipeline progress",
  knowledge: "Shared names and types", types: "Types and debug information", recovery: "Recover and verify source",
  exports: "Exports and reports", context: "Assemble context", commands: "All commands",
  "evidence-first-ai": "Evidence-bounded assistance", "matching-workspace": "Candidate matching",
};
const workspaceNavigation = [
  { id: "compare-builds", label: "Compare builds" },
  { id: "inspect-work", label: "Inspect" },
  { id: "recover-verify", label: "Recover & verify" },
];
function jump(id: string) {
  let parent = document.getElementById(id)?.parentElement;
  while (parent) { if (parent instanceof HTMLDetailsElement) parent.open = true; parent = parent.parentElement; }
  jumpTo(id);
}
function route(): Selection {
  const q = new URLSearchParams(location.search);
  const rawRegion = q.get("region");
  let region: Selection["region"];
  if (rawRegion) {
    try {
      const value = JSON.parse(rawRegion);
      if (value?.start?.offset) region = value;
    } catch {
      region = {
        start: {
          offset: rawRegion,
          binaryHash: q.get("binary_hash") || q.get("binary") || q.get("slug") || "",
        },
      };
    }
  }
  const evidenceIds = [
    ...q.getAll("evidence"),
    ...q.getAll("evidence_id"),
    ...String(q.get("evidence_ids") || "").split(","),
  ].filter(Boolean);
  return normalizeSelection({
    ...emptySelection,
    slug: q.get("binary") || q.get("slug") || q.get("binary_hash") || "",
    program: q.get("program") || "",
    addr: q.get("addr") || q.get("function") || q.get("function_id") || "",
    logicalId: q.get("logical_id") || "",
    locator: q.get("locator") || q.get("project") || q.get("project_id") || "",
    binaryHash: q.get("binary_hash") || undefined,
    functionId: q.get("function_id") || undefined,
    region,
    evidenceIds: evidenceIds.length ? evidenceIds : undefined,
  });
}
function routeFilter() {
  return new URLSearchParams(location.search).get("filter") || "";
}
function selectionUrl(selection: Selection) {
  const params = new URLSearchParams(location.search);
  for (const key of ["slug", "binary", "program", "addr", "function", "function_id", "logical_id", "locator", "project", "project_id", "binary_hash", "evidence", "evidence_id", "evidence_ids", "region"])
    params.delete(key);
  params.set("mode", "workbench");
  const values: Record<string, string | undefined> = {
    binary: selection.slug,
    program: selection.program,
    addr: selection.addr,
    logical_id: selection.logicalId,
    locator: selection.locator,
    binary_hash: selection.binaryHash,
    function_id: selection.functionId,
    region: selection.region ? JSON.stringify(selection.region) : undefined,
  };
  for (const [key, value] of Object.entries(values)) if (value) params.set(key, value);
  for (const evidence of selection.evidenceIds || []) params.append("evidence", evidence);
  return `${location.pathname}?${params}`;
}
function fromSession(s: Data): Selection {
  return normalizeSelection({
    ...emptySelection,
    ...s.selection,
    locator: s.selection?.locator ?? s.locator ?? "",
    slug: s.selection?.slug || s.projectSlug || "",
    program: s.selection?.program || s.program || "",
  });
}
function BatchTarget({
  batchId,
  index,
  row,
}: {
  batchId: string;
  index: number;
  row: Data;
}) {
  const [open, setOpen] = useState(false);
  const data = useData(
    open ? `/api/v1/batches/${batchId}/targets/${index}` : null,
  );
  return (
    <details onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>Parameters and result</summary>
      <ErrorLine error={data.error} />
      <pre>{JSON.stringify(data.data.target || row, null, 2)}</pre>
    </details>
  );
}
export function App() {
  const [selection, setSelection] = useState<Selection>(() => route());
  const selectionRef = useRef(selection);
  selectionRef.current = selection;
  const [sessions, setSessions] = useState<Data[]>([]);
  const sessionsRef = useRef<Data[]>([]);
  sessionsRef.current = sessions;
  const [active, setActive] = useState("");
  const activeRef = useRef("");
  activeRef.current = active;
  const [ready, setReady] = useState(false);
  const preparedContexts = useRef(new Set<string>());
  const revisionRef = useRef(0);
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision((x) => x + 1), []);
  const [events, setEvents] = usePref<Data[]>("activity", []);
  const persistEvents = useCallback((rows: Data[]) => {
    patchWorkspaceState("meta", "activity", rows.slice(-500));
  }, []);
  const notify: Notify = useCallback(
    (message, level = "info", details = {}) =>
      setEvents((old) => {
        const next = [
          ...old,
          {
            id: crypto.randomUUID(),
            at: Date.now(),
            message,
            level,
            ...details,
          },
        ].slice(-500);
        persistEvents(next);
        return next;
      }),
    [setEvents, persistEvents],
  );
  const [layout, setLayout] = usePref("layout", {
    explorer: 320,
    dock: 200,
    inspector: 300,
    tree: 200,
    showExplorer: true,
    showInspector: true,
    showDock: true,
  });
  const [density, setDensity] = usePref("density", "compact");
  const [dialog, setDialog] = useState<
    "open" | "create" | "copy" | "connection" | "import" | null
  >(null);
  const [pendingProject, setPendingProject] = useState<Selection | null>(null);
  const [action, setAction] = useState<ActionRequest | null>(null);
  const [checked, setChecked] = useState<Record<string, Selection>>({});
  const [filter, setFilter] = useState(() => routeFilter() || readPref("filter", ""));
  const [offset, setOffset] = useState(0);
  const [recordFilter, setRecordFilter] = usePref("record-filter", "all");
  const navigationRef = useRef({ filter, recordFilter, offset, scroll: 0 });
  navigationRef.current = {
    filter,
    recordFilter,
    offset,
    scroll: document.querySelector("main")?.scrollTop || 0,
  };
  const [palette, setPalette] = useState(false);
  const [paletteQuery, setPaletteQuery] = useState("");
  const [menu, setMenu] = useState("");
  const [context, setContext] = useState<{
    x: number;
    y: number;
    target: Selection;
    kind: string;
  } | null>(null);
  const [jobs, setJobs] = useState<Data[]>([]);
  const [batches, setBatches] = useState<Data[]>([]);
  const [jobId, setJobId] = useState("");
  const [matchingJobId, setMatchingJobId] = useState("");
  const [dockTab, setDockTab] = usePref("dock-tab", "logs");
  const [connection, setConnection] = useState("Connecting");
  const jobsSnapshot = useRef<Record<string, string>>({});
  const pollRef = useRef(false);
  const jobsInitialized = useRef(false);
  const workflowActivity = useEntityActivity(selection.locator, selection.slug, selection.program);
  const workflowRevision = useRef(0);
  useEffect(() => {
    if (!workflowActivity.revision || workflowActivity.revision === workflowRevision.current) return;
    workflowRevision.current = workflowActivity.revision;
    refresh();
  }, [workflowActivity.revision, refresh]);
  const [sessionError, setSessionError] = useState("");
  const binaries = useData(API + "/binaries", revision);
  const libraryTransfer = useLibraryTransfer(binaries.data.binaries || [], notify);
  const catalog = useData("/dashboard/api/actions");
  const activateContext = useCallback((next: Selection) => {
    const found = sessionsRef.current.find(s => next.locator
      ? projectLocatorsMatch(s.locator, next.locator)
      : !s.locator && s.selection?.slug === next.slug);
    if (found) { if(found.hidden){sessionsRef.current=sessionsRef.current.map(s=>s.id===found.id?{...s,hidden:false}:s);setSessions(sessionsRef.current);}setActive(found.id); return; }
    // A selection is an inspection target within the loaded workspace, not a request
    // to open another project tab. Project replacement always goes through openSelection.
    if (sessionsRef.current.length) { setActive(sessionsRef.current[0].id); return; }
    if (!next.locator && !next.slug) { setActive(""); return; }
    const session = { id: crypto.randomUUID(),
      title: next.locator.split("/").pop() || next.program || next.slug,
      locator: next.locator, projectSlug: next.slug,
      imports: next.slug ? [next.slug] : [], selection: next };
    sessionsRef.current = [...sessionsRef.current, session];
    setSessions(sessionsRef.current);
    setActive(session.id);
  }, []);
  const select = useCallback((patch: Partial<Selection>) => {
    const prior = selectionRef.current;
    const next = normalizeSelection({ ...prior, ...patch });
    if (
      (patch.slug !== undefined && patch.slug !== prior.slug) ||
      (patch.program !== undefined && patch.program !== prior.program) ||
      (patch.locator !== undefined && patch.locator !== prior.locator)
    ) {
      next.addr = patch.addr || "";
      next.logicalId = patch.logicalId || "";
      setOffset(0);
      setChecked({});
    }
    const priorState = {
      ...navigationRef.current,
      scroll: document.querySelector("main")?.scrollTop || 0,
    };
    history.replaceState(priorState, "", location.href);
    selectionRef.current = next;
    activateContext(next);
    setSelection(next);
    history.pushState(
      {
        ...priorState,
        offset:
          next.slug !== prior.slug || next.program !== prior.program
            ? 0
            : priorState.offset,
      },
      "",
      selectionUrl(next),
    );
  }, []);
  async function projectVisibility(record:Data,hidden:boolean) {
    const locator=String(record.locator||'');
    let next=sessionsRef.current.map(session=>session.locator===locator?{...session,hidden}:session);
    if(!next.some(session=>session.locator===locator))next.push({...record,id:record.id||crypto.randomUUID(),locator,hidden});
    let nextActive=active;
    if(hidden&&selectionRef.current.locator===locator){
      let fallback=next.find(session=>!session.hidden&&session.locator!==locator);
      if(!fallback){fallback={id:crypto.randomUUID(),title:'Untitled',locator:'',imports:[],selection:emptySelection};next.push(fallback);}
      nextActive=fallback.id;setActive(nextActive);
      const nextSelection=fromSession(fallback);selectionRef.current=nextSelection;setSelection(nextSelection);setChecked({});setOffset(0);
      history.replaceState(null, "", selectionUrl(nextSelection));
    }
    sessionsRef.current=next;setSessions(next);
    await queueSessionSave({ active: nextActive, sessions: next }).then((response) => {
      if (response?.revision != null) revisionRef.current = Number(response.revision);
    });notify(hidden?'Project removed from workspace. Files and background work remain available.':'Project restored to workspace.','info',{target:locator});
  }
  const onAction = useCallback(
    (id: string, params: Data = {}, targets?: Selection[]) =>
      setAction({ id, params, targets: targets || Object.values(checked) }),
    [checked],
  );
  const openSelection = useCallback(
    (patch: Partial<Selection>, force = false) => {
      const next = normalizeSelection(patch);
      const current = selectionRef.current;
      if (!force && current.locator && next.locator && !projectLocatorsMatch(current.locator, next.locator)) {
        setPendingProject(next);
        return;
      }
      const existing = sessionsRef.current.find((item) => next.locator && projectLocatorsMatch(item.locator, next.locator));
      const session = {
        ...(existing || {}), id: existing?.id || crypto.randomUUID(),
        title: existing?.title || next.locator.split("/").pop() || next.slug || "Project",
        locator: next.locator, projectSlug: next.slug,
        imports: Array.from(new Set([...(existing?.imports || []), next.slug].filter(Boolean))),
        selection: next, hidden: false,
      };
      // One workspace has one loaded project. This prevents a second tab from silently duplicating it.
      sessionsRef.current = [session]; setSessions([session]); setActive(session.id);
      select(next); refresh();
    }, [select, refresh],
  );
  const combineAndOpen = useCallback(async () => {
    if (!pendingProject) return;
    const incoming = pendingProject, current = selectionRef.current, currentSession = sessionsRef.current[0];
    const currentImports = Array.from(new Set((currentSession?.imports || []).map(String).filter(Boolean)));
    const incomingImports = incoming.slug ? [incoming.slug] : [];
    const added = incomingImports.filter((value) => !currentImports.includes(value));
    const shared = incomingImports.filter((value) => currentImports.includes(value));
    const imports = Array.from(new Set([...currentImports, ...incomingImports]));
    setPendingProject(null); openSelection(incoming, true);
    // Retain the combined browser references after opening the requested project.
    const opened = sessionsRef.current[0];
    if (opened) {
      const mergedSession = { ...opened, imports };
      sessionsRef.current = [mergedSession];
      setSessions([mergedSession]);
    }
    notify("Workspace references combined; requested project is active", "info", { target: incoming.locator, merge: {
      loadedProject: incoming.locator || incoming.slug || "Requested project", retainedProject: current.locator || current.slug || "No prior project",
      requestedProjectImports: incomingImports.length, currentProjectImports: currentImports.length, importsAfterCombine: imports.length,
      importsInLoadedProject: incomingImports, importsInCurrentProject: currentImports,
      importsNewlyLinked: added, importsAlreadyShared: shared,
      combinedRecords: ["Workspace import links", "The decision to load the requested project"],
      unchangedRecords: ["Ghidra databases and program files", "Analysis, recovery jobs, and human metadata", "Source artifacts and proof receipts"],
      scope: "Only browser workspace references changed. No project database, analysis result, source artifact, metadata field, or proof receipt was copied or overwritten.",
    }});
  }, [pendingProject, notify, openSelection]);
  useEffect(() => {
    let alive = true;
    void ensureWorkspaceState().then((state) => {
      const stored = state.meta?.activity;
      if (!alive || !Array.isArray(stored) || !stored.length) return;
      setEvents((old) => (old.length ? old : stored));
    });
    return () => {
      alive = false;
    };
  }, [setEvents]);
  useEffect(() => {
    let dead = false;
    Promise.resolve(loadClientSessions())
      .then((data) => {
        if (dead) return;
        revisionRef.current = data.revision || 0;
        setSessionRevision(revisionRef.current);
        const list: Data[] = data.sessions || [];
        const explicit = route();
        const linked = Boolean(explicit.slug || explicit.locator || explicit.program);
        let current = linked
          ? list.find(s => explicit.locator ? projectLocatorsMatch(s.locator, explicit.locator) : (explicit.slug ? s.projectSlug === explicit.slug : s.program === explicit.program))
          : list.find(s => s.id === data.active) || list[0];
        if (linked && !current) {
          current = {id: crypto.randomUUID(), title: explicit.locator.split("/").pop() || explicit.program || explicit.slug,
            locator: explicit.locator, program: explicit.program, projectSlug: explicit.slug,
            selection: explicit, imports: explicit.slug ? [explicit.slug] : []};
          list.push(current);
        }
        // There is one loaded project. Older saved workspace state may retain
        // repeated tabs for that same project, so normalize it before rendering.
        const normalized = current ? [{...current, hidden:false}] : [];
        sessionsRef.current = normalized;
        setSessions(normalized);
        setActive(current?.id || "");
        if (!linked && current) setSelection(fromSession(current));
        setReady(true);
      })
      .catch((e) => {
        if (!dead) {
          setSessionError(e.message);
          setReady(true);
        }
      });
    return () => {
      dead = true;
    };
  }, []);
  useEffect(() => {
    if (!ready) return;
    installSessionFlush(() => ({
      active: activeRef.current,
      sessions: sessionsRef.current,
    }));
  }, [ready, active]);
  useEffect(() => {
    if (!ready) return;
    void ensureWorkspaceState().then((state) => {
      const saved = state.meta?.activity;
      if (Array.isArray(saved) && saved.length)
        setEvents((old) => (old.length ? old : saved));
    });
  }, [ready, setEvents]);
  useEffect(() => {
    if (!ready || (!selection.locator && !selection.slug)) return;
    const context = {locator: selection.locator, program: selection.program, slug: selection.slug};
    const key = JSON.stringify(context);
    if (preparedContexts.current.has(key)) return;
    preparedContexts.current.add(key);
    request(API + "/prepare", {method: "POST", body: JSON.stringify(context)})
      .then(result => notify("Project preparation accepted", "info", {target: context.locator || context.slug, preparationId: result.run?.id}))
      .catch(error => {preparedContexts.current.delete(key);notify("Project preparation could not start: " + error.message, "error");});
  }, [ready, selection.locator, selection.program, selection.slug, notify]);
  useEffect(() => {
    if (!ready) return;
    savePref("filter", filter);
  }, [ready, filter]);
  useEffect(() => {
    if (!ready || !active) return;
    setSessions((old) => {
      const next = old.map((s) =>
        s.id === active && (!s.locator || projectLocatorsMatch(s.locator, selection.locator))
          ? {
              ...s,
              locator: selection.locator || s.locator,
              program: selection.program,
              selection,
              imports: Array.from(
                new Set([...(s.imports || []), selection.slug].filter(Boolean)),
              ),
            }
          : s,
      );
      sessionsRef.current = next;
      return next;
    });
  }, [selection, active, ready]);
  useEffect(() => {
    if (!ready) return;
    const timer = setTimeout(() => {
      void queueSessionSave({ active, sessions }).then(
        (result) => {
          if (!result) return;
          revisionRef.current = Number(result.revision || revisionRef.current);
          setSessionRevision(revisionRef.current);
          setSessionError("");
          const remote: Data[] = result.sessions || [];
          const remoteActive = String(result.active || active);
          const changed =
            Boolean(result.merged) ||
            remoteActive !== active ||
            JSON.stringify(remote) !== JSON.stringify(sessions);
          if (changed && remote.length) {
            setSessions((old) => {
              const ids = new Set(old.map((s) => s.id));
              const next = [
                ...old.map((s) => {
                  const saved = remote.find((r) => r.id === s.id);
                  return saved
                    ? {
                        ...saved,
                        ...s,
                        imports: Array.from(
                          new Set([
                            ...(saved.imports || []),
                            ...(s.imports || []),
                          ]),
                        ),
                      }
                    : s;
                }),
                ...remote.filter((s) => !ids.has(s.id)),
              ];
              sessionsRef.current = next;
              return JSON.stringify(next) === JSON.stringify(old) ? old : next;
            });
            if (remoteActive && remoteActive !== active) {
              activeRef.current = remoteActive;
              setActive(remoteActive);
            }
          } else if (!sessions.length && result.active) {
            setActive(result.active);
          }
        },
        (e) => setSessionError(String(e)),
      );
    }, 100);
    return () => clearTimeout(timer);
  }, [sessions, active, ready]);
  useEffect(() => {
    const pop = (event: PopStateEvent) => {
      const next = route();
      if (
        next.slug !== selectionRef.current.slug ||
        next.program !== selectionRef.current.program ||
        next.locator !== selectionRef.current.locator
      )
        setChecked({});
      selectionRef.current = next;
      activateContext(next);
      setSelection(next);
      setFilter(routeFilter());
      if (event.state) {
        setFilter(event.state.filter || "");
        setRecordFilter(event.state.recordFilter || "all");
        setOffset(event.state.offset || 0);
        requestAnimationFrame(() => {
          const main = document.querySelector("main");
          if (main) main.scrollTop = event.state.scroll || 0;
        });
      }
    };
    window.addEventListener("popstate", pop);
    return () => window.removeEventListener("popstate", pop);
  }, []);
  useEffect(() => {
    if (!ready) return;
    const params = new URLSearchParams(location.search);
    let id =
      params.get("window") ||
      params.get("focus") ||
      params.get("tool") ||
      location.hash.slice(1);
    id = id.replace(/^wb-/, "");
    const aliases: Data = {
      fnbrowse: "listing",
      functions: "listing",
      corpus: "overview",
      match: "knowledge",
      stabs: "types",
      report: "exports",
      recover: "recovery",
    };
    if (id) setTimeout(() => jump(aliases[id] || id), 300);
  }, [ready]);
  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      if (pollRef.current) return;
      pollRef.current = true;
      try {
        const [jobsResult, batchesResult] = await Promise.allSettled([
          request("/dashboard/api/jobs", { signal: AbortSignal.timeout(8000) }),
          request("/api/v1/batches", { signal: AbortSignal.timeout(8000) }),
        ]);
        if (stopped) return;
        const list = jobsResult.status === "fulfilled" ? jobsResult.value.jobs || [] : [];
        const initialJobs = !jobsInitialized.current && jobsResult.status === "fulfilled";
        if (jobsResult.status === "fulfilled") {
          setJobs(list);
          jobsInitialized.current = true;
        }
        if (batchesResult.status === "fulfilled") {
          const nextBatches = batchesResult.value.batches || [];
          setBatches(nextBatches);
        }
        const activityConnection = workflowActivity.connection;
        setConnection(
          jobsResult.status === "fulfilled"
            ? batchesResult.status === "fulfilled"
              ? activityConnection === "live"
                ? "Connected"
                : activityConnection === "polling"
                  ? "Connected · refreshing workflow activity"
                  : "Connected · workflow activity reconnecting"
              : "Connected · batch updates delayed"
            : activityConnection === "live"
              ? "Connected · workflow activity live"
              : "Reconnecting · refreshing durable activity",
        );
        if (jobsResult.status !== "fulfilled") return;
        for (const job of list) {
          const prior = jobsSnapshot.current[job.id];
          if (!initialJobs && prior !== job.status) {
            notify(
              `${job.title || job.actionId}: ${job.status}`,
              job.status === "failed" ? "error" : "info",
              {
                jobId: job.id,
                action: job.actionId,
                target: job.params?.program || job.params?.slug,
                status: job.status,
              },
            );
            if (!["running", "queued", "cancelling"].includes(job.status)) {
              const current = selectionRef.current;
              if (
                !job.params?.slug ||
                job.params.slug === current.slug ||
                job.params.program === current.program
              )
                refresh();
            }
          }
          jobsSnapshot.current[job.id] = job.status;
        }
      } catch {
        if (!stopped)
          setConnection(
            workflowActivity.connection === "live"
              ? "Connected · workflow activity live"
              : "Reconnecting · refreshing durable activity",
          );
      } finally {
        pollRef.current = false;
        if (!stopped) timer = setTimeout(poll, document.hidden ? 10000 : 2000);
      }
    }
    poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [notify, refresh, workflowActivity.connection]);
  useEffect(() => {
    function keyboard(e: KeyboardEvent) {
      const typing = (e.target as HTMLElement).matches(
        "input,textarea,select,[contenteditable=true]",
      );
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette((x) => !x);
        return;
      }
      if (e.key === "Escape") {
        setPalette(false);
        setMenu("");
        setContext(null);
        return;
      }
      if (typing || dialog || action || palette) return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        save();
      }
    }
    window.addEventListener("keydown", keyboard);
    return () => window.removeEventListener("keydown", keyboard);
  }, [dialog, action, palette, selection]);
  function toggle(row: Data) {
    const target = {
      ...selection,
      addr: String(row.addr),
      logicalId: String(row.logicalId || ""),
    };
    const key = functionKey(target);
    setChecked((old) => {
      const next = { ...old };
      if (next[key]) delete next[key];
      else next[key] = target;
      return next;
    });
  }
  async function save() {
    try {
      const result = await queueSessionSave({
        active,
        sessions: sessionsRef.current,
      });
      if (result?.revision != null)
        revisionRef.current = Number(result.revision);
      setSessionError("");
      notify("Workspace saved.", "info", {
        target: selection.locator || selection.slug,
        result: { revision: result?.revision },
      });
    } catch (e) {
      setSessionError(String(e));
      notify(String(e), "error");
    }
  }
  function selectedSession(id: string) {
    setActive(id);
    const s = sessions.find((s) => s.id === id);
    if (s) select(fromSession(s));
  }
  const onBrowseFunctions = (scope: {
    slugs: string[];
    program?: string;
    locator?: string;
    filter: string;
  }) => {
    select({
      slug: scope.slugs[0] || "",
      program: scope.program || "",
      locator: scope.locator || "",
      addr: "",
      logicalId: "",
    });
    setRecordFilter(scope.filter);
    setFilter("");
    setOffset(0);
  };
  const surfaceProps = {
    selection,
    onSelect: select,
    onAction,
    notify,
    revision,
    onBrowseFunctions,
  };
  const batchCount = Object.keys(checked).length;
  const visibleProjectSessions: Data[] = (() => {
    const current = sessions.find((session) => session.id === active && !session.hidden)
      || sessions.find((session) => !session.hidden);
    return current ? [current] : [];
  })();
  return (
    <div
      className={"app " + density}
      style={
        {
          "--explorer": layout.showExplorer ? layout.explorer + "px" : "0px",
          "--inspector": layout.showInspector ? layout.inspector + "px" : "0px",
          "--dock": layout.showDock ? layout.dock + "px" : "28px",
        } as React.CSSProperties
      }
    >
      <a className="skip-link" href="#function-list">
        Skip to functions
      </a>
      <header className="chrome">
        <strong className="brand">AgentDecompile</strong>
        <span className="divider" />
        {["File", "View", "Analyze"].map((name) => (
          <div className="menu" key={name}>
            <button
              aria-expanded={menu === name}
              onClick={() => setMenu(menu === name ? "" : name)}
            >
              {name}
            </button>
            {menu === name && (
              <div className="popup">
                {name === "File" ? (
                  <>
                    {(
                      [
                        "open",
                        "create",
                        "import",
                        "copy",
                        "connection",
                      ] as const
                    ).map((mode) => (
                      <button
                        key={mode}
                        onClick={() => {
                          setDialog(mode);
                          setMenu("");
                        }}
                      >
                        {
                          {
                            open: "Open project…",
                            create: "Create project…",
                            import: "Import binaries…",
                            copy: "Copy project…",
                            connection: "Save connection…",
                          }[mode]
                        }
                      </button>
                    ))}
                    <button
                      onClick={() => {
                        save();
                        setMenu("");
                      }}
                    >
                      Save workspace <kbd>Ctrl S</kbd>
                    </button>
                  </>
                ) : name === "View" ? (
                  <>
                    <button
                      onClick={() =>
                        setDensity(density === "compact" ? "roomy" : "compact")
                      }
                    >
                      Use {density === "compact" ? "roomy" : "compact"} layout
                    </button>
                    {(
                      ["showExplorer", "showInspector", "showDock"] as const
                    ).map((key) => (
                      <button
                        key={key}
                        onClick={() =>
                          setLayout((x) => ({ ...x, [key]: !x[key] }))
                        }
                      >
                        {layout[key] ? "Hide" : "Show"} {{showExplorer:"project explorer",showInspector:"evidence inspector",showDock:"Activity dock"}[key]}
                      </button>
                    ))}
                    <button
                      onClick={() => {
                        setLayout({
                          explorer: 320,
                          dock: 200,
                          inspector: 300,
                          tree: 200,
                          showExplorer: true,
                          showInspector: true,
                          showDock: true,
                        });
                        Object.keys(localStorage)
                          .filter((k) => k.startsWith("ad.react.height."))
                          .forEach((k) => localStorage.removeItem(k));
                        location.reload();
                      }}
                    >
                      Reset layout
                    </button>
                  </>
                ) : (
                  <>
                    {[
                      {id:"mcp.decompile-function",label:"Decompile selected function",enabled:Boolean(selection.addr)},
                      {id:"corpus.bsim-report",label:"Review cross-build matches",enabled:Boolean(selection.slug||selection.locator)},
                      {id:"corpus.bsim-ingest",label:"Index project for matching",enabled:Boolean(selection.locator||selection.slug)},
                      {id:"corpus.ghidra-bulk",label:"Generate compiling C",enabled:Boolean(selection.slug)},
                      {id:"corpus.cross-place",label:"Share source with related builds",enabled:Boolean(selection.slug)},
                      {id:"corpus.objdiff-check",label:"Verify compiled bytes",enabled:Boolean(selection.slug)},
                    ].map(({id,label,enabled})=><button key={id} disabled={!enabled} onClick={()=>{onAction(id);setMenu("");}}>{label}</button>)}
                    <hr />
                    <button onClick={()=>{setPalette(true);setMenu("");}}>Find another command…</button>
                  </>
                )}
              </div>
            )}
          </div>
        ))}
        <button onClick={() => setPalette(true)}>
          Commands <kbd>Ctrl K</kbd>
        </button>
        <span className="muted connection">{connection}</span>
      </header>
      <div
        className="project-tabs"
        role="tablist"
        aria-label="Project sessions"
      >
        {visibleProjectSessions.map((s) => (
          <div
            className={"session " + (active === s.id ? "selected" : "")}
            {...libraryTransfer.dropProps(s.locator)}
            key={s.id}
          >
            <button
              role="tab"
              aria-selected={active === s.id}
              onClick={() => selectedSession(s.id)}
              onDoubleClick={() => {
                const title = window.prompt("Project tab name", s.title);
                if (title)
                  setSessions((old) =>
                    old.map((x) => (x.id === s.id ? { ...x, title } : x)),
                  );
              }}
            >
              {s.title || "Project"}
            </button>
            <button
              aria-label={"Close " + s.title}
              onClick={() => {
                setSessions((old) => old.filter((x) => x.id !== s.id));
                if (s.id === active) {
                  const other = sessions.find((x) => x.id !== s.id);
                  setActive(other?.id || "");
                  select(other ? fromSession(other) : emptySelection);
                }
              }}
            >
              ×
            </button>
          </div>
        ))}
        <button
          aria-label="Open another project"
          onClick={() => setDialog("open")}
        >
          ＋
        </button>
        <span className="project-path" title={selection.locator}>
          {selection.locator || "Open a project or import binaries"}
        </span>
      </div>
      {sessionError && (
        <div className="error">
          Session state: {sessionError}{" "}
          <button onClick={() => setSessions([...sessions])}>Retry save</button>
        </div>
      )}
      <CorpusDbPicker notify={notify} />
      {libraryTransfer.confirmation}
      <nav className="region-controls" aria-label="Workspace regions">
        <button
          aria-controls="project-explorer"
          aria-expanded={layout.showExplorer}
          onClick={() =>
            setLayout((current) => ({
              ...current,
              showExplorer: !current.showExplorer,
            }))
          }
        >
          {layout.showExplorer ? "Hide navigator" : "Show navigator"}
        </button>
        <button
          aria-controls="workspace"
          onClick={() => document.getElementById("workspace")?.focus()}
        >
          Analysis
        </button>
        <button
          aria-controls="evidence-inspector"
          aria-expanded={layout.showInspector}
          onClick={() =>
            setLayout((current) => ({
              ...current,
              showInspector: !current.showInspector,
            }))
          }
        >
          {layout.showInspector ? "Hide evidence" : "Show evidence"}
        </button>
        <button
          aria-controls="activity-dock"
          aria-expanded={layout.showDock}
          onClick={() =>
            setLayout((current) => ({
              ...current,
              showDock: !current.showDock,
            }))
          }
        >
          {layout.showDock ? "Hide activity" : "Show activity"}
        </button>
      </nav>
      <div className="work-area">
        <aside id="project-explorer" className="explorer" aria-label="Project and function navigator" hidden={!layout.showExplorer}>
          <PersistentExplorer onProjectVisibility={projectVisibility} notify={notify} libraryLoading={binaries.loading} libraryError={binaries.error} builds={binaries.data.binaries || []} projects={sessions} unresolved={binaries.data.unresolvedBinaries || []}
            selection={selection} onSelect={select} onAdd={libraryTransfer.stage} dropProps={libraryTransfer.dropProps} revision={revision} recordFilter={recordFilter} onRecordFilterChange={setRecordFilter} functionQuery={filter} onFunctionQueryChange={setFilter}
            onImport={()=>setDialog("import")} onCreate={()=>setDialog("create")}
            checkedFunctions={row=>Boolean(checked[functionKey({...selection,addr:row.addr})])}
            onCheckFunction={(row,shift,range)=>{
              if(shift && range?.length){setChecked(old=>{const next={...old};for(const item of range){const target={...selection,addr:item.addr,logicalId:String(item.logicalId||"")};next[functionKey(target)]=target;}return next;});}
              else toggle(row);
            }}
            onFunctionContextMenu={(event,row)=>{event.preventDefault();setContext({x:event.clientX,y:event.clientY,target:{...selection,addr:row.addr,logicalId:String(row.logicalId||"")},kind:"function"});}}
            functionToolbar={batchCount>0?<div className="checked-info">{batchCount} functions checked <button onClick={()=>setChecked({})}>Clear</button><button onClick={()=>setPalette(true)}>Run command on {batchCount}</button></div>:undefined}
          />
        </aside>
        {layout.showExplorer && (
          <ResizeBar
            axis="x"
            label="Resize explorer"
            value={layout.explorer}
            min={240}
            max={560}
            onReset={() => setLayout((current) => ({ ...current, explorer: 320 }))}
            onCollapse={() => setLayout((current) => ({ ...current, showExplorer: false }))}
            onResize={(d) =>
              setLayout((x) => ({
                ...x,
                explorer: Math.max(240, Math.min(560, x.explorer + d)),
              }))
            }
          />
        )}
        <main id="workspace" tabIndex={-1} aria-label="Analysis workspace">
          <nav className="section-index" aria-label="Workspace sections">
            {workspaceNavigation.map(({id,label})=><button key={id} onClick={()=>jump(id)}>{label}</button>)}
            {selection.slug && <SourceDownload selection={selection} notify={notify} />}
          </nav>
          <LocalArtifactPanel
            binaries={binaries.data.binaries || []}
            notify={notify}
            onOpenRecorded={(binary) => {
              const binding = (binary.projectBindings || []).find((item: Data) => item.locator === selection.locator)
                || (binary.projectBindings || [])[0]
                || {};
              select({
                slug: binary.slug || "",
                program: binding.program || binary.program || "",
                locator: binding.locator || binary.locator || "",
                binaryHash: binary.sha256 || "",
                addr: "",
                logicalId: "",
              });
            }}
          />
          <WorkbenchSurfaces {...surfaceProps} inspectTools={<CodeBrowser {...surfaceProps} />} preparationTools={<PreparationActivity {...surfaceProps} />} />
          <WorkbenchIntegration
            selection={selection}
            revision={revision}
            catalog={catalog.data.actions || []}
            onSelect={select}
            onMatchCandidate={(params) => setAction({ id: "workbench.match-candidate", params })}
            matchingJobId={matchingJobId}
            notify={notify}
          />
          <details id="wb-more" className="workspace-reference"><summary>Reversing workflows</summary><section id="guide">
            <GuideWorkflows {...surfaceProps} />
          </section>
          </details><details className="workspace-reference"><summary>All commands</summary><section id="commands" tabIndex={-1}>
            <Commands {...surfaceProps} />
          </section></details>
        </main>
        {layout.showInspector && (
          <>
            <ResizeBar
              axis="x"
              label="Resize evidence inspector"
              value={layout.inspector}
              min={220}
              max={600}
              onReset={() => setLayout((current) => ({ ...current, inspector: 300 }))}
              onCollapse={() => setLayout((current) => ({ ...current, showInspector: false }))}
              onResize={(d) =>
                setLayout((x) => ({
                  ...x,
                  inspector: Math.max(220, Math.min(600, x.inspector - d)),
                }))
              }
            />
            <aside id="evidence-inspector" className="inspector" aria-label="Evidence inspector">
              <header>
                <h2>Evidence inspector</h2>
                <button
                  aria-label="Hide evidence inspector"
                  onClick={() =>
                    setLayout((x) => ({ ...x, showInspector: false }))
                  }
                >
                  ×
                </button>
              </header>
              <EvidenceInspector {...surfaceProps} />
            </aside>
          </>
        )}
      </div>
      <ResizeBar
        axis="y"
        label="Resize Activity dock"
        value={layout.dock}
        min={100}
        max={650}
        collapsed={!layout.showDock}
        onReset={() => setLayout((current) => ({ ...current, dock: 200, showDock: true }))}
        onCollapse={() => setLayout((current) => ({ ...current, showDock: false }))}
        onRestore={() => setLayout((current) => ({ ...current, showDock: true }))}
        onResize={(d) =>
          setLayout((x) => ({
            ...x,
            showDock: true,
            dock: Math.max(100, Math.min(650, x.dock - d)),
          }))
        }
      />
      <section id="activity-dock" className="activity" aria-label="Activity dock"><UnifiedActivity jobs={jobs} events={events} batches={batches} expanded={layout.showDock} onToggle={()=>setLayout(x=>({...x,showDock:!x.showDock}))} notify={notify} onRetry={job=>setAction({id:job.actionId,params:job.params,targets:[recordedSelection(job,selection)]})} onRetryBatch={batch=>setAction({id:batch.action,params:batch.results[0]?.params,targets:batch.results.filter((row:Data)=>row.status!=='ok').map((row:Data)=>row.context)})}/></section>
      <footer>
        <span>
          {selection.program || selection.slug || "No program selected"}
        </span>
        <code>{selection.addr}</code>
        {selection.binaryHash ? <code title={selection.binaryHash}>sha256:{selection.binaryHash.slice(0, 12)}</code> : null}
        <span className="claim">Verification not established</span>
        <span>{connection}</span>
      </footer>
      <div className="sr-only" aria-live="polite">
        {events.at(-1)?.message}
      </div>
      {palette && (
        <div className="modal-backdrop" onClick={() => setPalette(false)}>
          <div
            className="palette"
            role="dialog"
            aria-modal="true"
            aria-label="Command palette"
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => {
              if (e.key === "Tab") {
                const items = Array.from(
                  e.currentTarget.querySelectorAll<HTMLElement>(
                    "input,button:not(:disabled)",
                  ),
                );
                const first = items[0],
                  last = items.at(-1);
                if (e.shiftKey && document.activeElement === first) {
                  e.preventDefault();
                  last?.focus();
                } else if (!e.shiftKey && document.activeElement === last) {
                  e.preventDefault();
                  first?.focus();
                }
              }
            }}
          >
            <input
              autoFocus
              aria-label="Search commands and sections"
              value={paletteQuery}
              onChange={(e) => setPaletteQuery(e.target.value)}
              placeholder="Find an action or section…"
            />
            <button onClick={() => setPalette(false)}>Close</button>
            <div className="palette-results">
              {Object.keys(sectionNames)
                .filter((id) => (id+" "+sectionNames[id]).toLowerCase().includes(paletteQuery.toLowerCase()))
                .map((id) => (
                  <button
                    key={id}
                    onClick={() => {
                      setPalette(false);
                      jump(id);
                    }}
                  >
                    Go to {sectionNames[id]}
                  </button>
                ))}
              {(catalog.data.actions || [])
                .filter((a: Data) =>
                  (a.id + " " + a.title)
                    .toLowerCase()
                    .includes(paletteQuery.toLowerCase()),
                )
                .slice(0, 60)
                .map((a: Data) => (
                  <button
                    key={a.id}
                    onClick={() => {
                      setPalette(false);
                      onAction(a.id);
                    }}
                  >
                    {a.title} <code>{a.id}</code>
                  </button>
                ))}
              <button
                onClick={() => {
                  setPalette(false);
                  jump("commands");
                }}
              >
                Browse all commands
              </button>
            </div>
          </div>
        </div>
      )}
      {context && (
        <div className="context-catcher" onClick={() => setContext(null)}>
          <div
            className="popup context-popup"
            style={{
              left: Math.min(context.x, innerWidth - 240),
              top: Math.min(context.y, innerHeight - 180),
            }}
          >
            {[
              "mcp.decompile-function",
              "mcp.rename-function",
              "mcp.get-references",
            ].map((id) => (
              <button
                key={id}
                onClick={() => {
                  setAction({
                    id,
                    params: { addr: context.target.addr },
                    targets: [context.target],
                  });
                  setContext(null);
                }}
              >
                {id.split(".").pop()}
              </button>
            ))}
            <button
              onClick={() =>
                navigator.clipboard
                  .writeText(context.target.addr)
                  .then(() => notify("Address copied"))
              }
            >
              Copy address
            </button>
          </div>
        </div>
      )}
      <ActionRunner
        request={action}
        selection={selection}
        onClose={() => setAction(null)}
        notify={notify}
        onSubmitted={(result) => {
          if (action?.id === "workbench.match-candidate" && result.job?.id) setMatchingJobId(result.job.id);
          refresh();
        }}
      />
      <ProjectDialog
        mode={dialog}
        selection={selection}
        onClose={() => setDialog(null)}
        onSelect={openSelection}
        notify={notify}
        onRefresh={refresh}
      />
      {pendingProject && <DialogFrame title="Load another project?" onClose={() => setPendingProject(null)}>
        <p>A project is already loaded. Review both locations before changing the active workspace.</p>
        <dl className="project-merge-summary"><div><dt>Current project</dt><dd><code>{selection.locator || selection.slug || "Not recorded"}</code></dd></div><div><dt>Requested project</dt><dd><code>{pendingProject.locator || pendingProject.slug || "Not recorded"}</code></dd></div></dl>
        <p>Combining preserves workspace import references and records the decision. It does not copy or overwrite Ghidra program databases, analysis, source artifacts, or proof receipts.</p>
        <div className="dialog-actions"><button onClick={() => setPendingProject(null)}>Keep current project</button><button onClick={() => void combineAndOpen()}>Combine references and load requested project</button></div>
      </DialogFrame>}
    </div>
  );
}
