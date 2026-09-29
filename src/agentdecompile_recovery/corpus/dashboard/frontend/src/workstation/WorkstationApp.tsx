import {useCallback,useEffect,useRef,useState,type CSSProperties,type KeyboardEvent} from 'react';
import {API,emptySelection,normalizeSelection,query,request,type ActionRequest,type Data,type Notify,type Selection} from '../contracts';
import {useData,usePref,readPref,savePref,ResizeBar,ErrorLine,RecordView} from '../ui';
import {ActionRunner,Commands,DialogFrame} from '../Actions';
import {ProjectDialog} from '../ProjectDialog';
import {ExchangeContribution} from '../ExchangeContribution';
import {LocalProjectRuntime} from '../runtime/localProject';
import {matchRecordedArtifact} from '../runtime/LocalArtifactPanel';
import type {NormalizedAnalysisModel} from '../analysis/contracts';
import {ScratchWorkspace} from '../scratch/ScratchWorkspace';
import {MatchReview} from './MatchReview';
import {projectStore} from '../storage/projectStore';
import {SourceDownload} from '../SourceDownload';
import {PreparationProgress,selectPreparation} from '../PreparationActivity';
import {usePreparationRuns} from '../usePreparationRuns';
import {useEntityActivity} from '../activity';
import {ScopedClaims,selectClaimProjection} from '../ScopedClaims';
import {ProjectSnapshots} from './ProjectSnapshots';
import {RetainedPanel} from './RetainedPanel';
import {AnalysisView} from './AnalysisView';
import {CompareView} from './CompareView';
import {LogicalNavigator} from './LogicalNavigator';
import {canPrepareAnalysis,shellShortcut,addressOf,analysisTabs,extraTabs,readRoute,routeUrl,sessionKey,mergeSelection,memberSelection,type AnalysisTab,type Route} from './navigation';
import './workstation.css';

type Session={selection:Selection;name:string};
const initialRoute=():Route=>readRoute(location.search,readPref('workstation.route',{selection:emptySelection,tab:'Logical'} as Route));
function Icon({name}:{name:'folder'|'file'|'search'|'command'|'menu'|'close'|'reload'|'share'}) {
  const paths={folder:'M3 7V5h6l2 2h10v13H3Z',file:'M6 3h8l4 4v14H6Z M14 3v5h4',search:'M20 20l-5-5 M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0',command:'m4 6 6 6-6 6 M13 18h7',menu:'M4 6h16 M4 12h16 M4 18h16',close:'m6 6 12 12 M18 6 6 18',reload:'M20 7v5h-5 M20 12a8 8 0 1 0-2 6',share:'M8 12l8-6 M8 12l8 6 M5 9h3v6H5Z M16 3h3v6h-3Z M16 15h3v6h-3Z'};
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d={paths[name]}/></svg>;
}
function tabKeys(e:KeyboardEvent<HTMLElement>){
  if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;
  const tabs=Array.from(e.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]'));
  const i=tabs.indexOf(document.activeElement as HTMLButtonElement);
  const next=e.key==='Home'?0:e.key==='End'?tabs.length-1:(i+(e.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;
  e.preventDefault();tabs[next]?.focus();tabs[next]?.click();
}
const transientReadError=(value:unknown)=>/request failed \((?:408|429|5\d\d)\)|failed to fetch|networkerror|network request failed|timeout/i.test(String(value||''));
const activeJob=(job:Data)=>['queued','running','waiting','cancelling'].includes(String(job.status));
const failedJob=(job:Data)=>['failed','cancelled','interrupted','blocked','partial','budget-stop','near-miss','readability-blocked','error'].includes(String(job.status));
const jobTime=(job:Data)=>Number(job.finishedAt||job.updatedAt||job.createdAt||job.startedAt||0);
const jobTarget=(job:Data)=>String(job.params?.input||job.params?.programPath||job.params?.program||job.params?.slug||job.context?.program||job.context?.slug||'Target not recorded');
const jobWorkdir=(job:Data)=>String(job.params?.['work-dir']||job.params?.workdir||job.params?.output||job.params?.['dump-source']||'');
function jobProgress(job:Data){
  const value=job.progress;
  if(typeof value==='number'&&Number.isFinite(value))return {completed:value,total:100,label:`${value}%`};
  if(value&&typeof value==='object'&&Number.isFinite(Number(value.completed))&&Number.isFinite(Number(value.total))&&Number(value.total)>0)return {completed:Number(value.completed),total:Number(value.total),label:String(value.message||`${value.completed} / ${value.total}`)};
  const matches=[...String(job.log||'').matchAll(/\[[^\]\r\n]*\]\s*(\d+)\s*\/\s*(\d+)\s+([^\r\n]+)/g)];
  const match=matches.at(-1);
  return match?{completed:Number(match[1]),total:Number(match[2]),label:`${match[1]} / ${match[2]} · ${match[3]}`} : null;
}
function jobLogSummary(job:Data){
  const lines=String(job.log||job.error||'').split(/\r?\n/).map(line=>line.trim()).filter(line=>line&&!/^stage-timing:/.test(line));
  return [...lines].reverse().find(line=>/^\[[^\]]*\]\s*\d+\s*\/\s*\d+\s+\S/.test(line))||[...lines].reverse().find(line=>!/^[[\]{},]|^"[^"\r\n]+"\s*:/.test(line))||'';
}
const sameLocator=(left:unknown,right:unknown)=>String(left||'').replace(/\/+$/,'')===String(right||'').replace(/\/+$/,'');
function belongsToSelection(job:Data,selection:Selection){
  if(!selection.locator&&!selection.program&&!selection.slug)return activeJob(job);
  const values=[job.params,job.context,job.result?.context,job.result?.job?.context].filter(Boolean) as Data[];
  return values.some(value=>
    (selection.locator&&value.locator&&sameLocator(value.locator,selection.locator)) ||
    (selection.program&&(value.program===selection.program||value.programPath===selection.program)) ||
    (selection.slug&&value.slug===selection.slug)
  );
}
function jobTitle(job:Data){return String(job.title||job.actionId||job.action||'Operation').replace(/^mcp\./,'').replaceAll('-',' ');}
function JobRecord({job,scope,initialOpen=false,onAction}:{job:Data;scope:'live'|'current'|'history';initialOpen?:boolean;onAction:(id:string,params?:Data,targets?:Selection[])=>void}){
  const [open,setOpen]=useState(initialOpen),[detailRevision,setDetailRevision]=useState(0);
  const detail=useData(open?`/dashboard/api/jobs/${encodeURIComponent(String(job.id))}`:null,detailRevision);
  const record=detail.data.job||job;
  useEffect(()=>{if(!open||!activeJob(record))return;const timer=setInterval(()=>setDetailRevision(value=>value+1),2000);return()=>clearInterval(timer);},[open,record.status]);
  const progress=jobProgress(record),target=jobTarget(record),workdir=jobWorkdir(record),logSummary=jobLogSummary(record);
  return <details className={`ws-job-record ${scope}`} open={open} onToggle={event=>setOpen((event.currentTarget as HTMLDetailsElement).open)}><summary><span className="ws-job-summary"><strong>{record.status} · {jobTitle(record)}</strong><small>{record.id} · {scope==='live'?'live across workspace':scope==='current'?'selected project':'recorded history'}</small></span><span className="ws-job-path"><b>Target</b><code title={target}>{target}</code></span>{workdir&&<span className="ws-job-path"><b>Workdir</b><code title={workdir}>{workdir}</code></span>}{progress?<span className="ws-job-progress"><progress value={progress.completed} max={progress.total}/><small>{progress.label}</small></span>:activeJob(record)&&<span className="ws-job-progress"><progress/><small>Working · reading measured stage progress</small></span>}{logSummary&&<span className="ws-job-log-summary">{logSummary}</span>}</summary>{detail.loading?<p role="status">Reading current job output…</p>:detail.error?<p className="ws-job-refresh" role="status">Refreshing recorded job receipt.<details><summary>Connection details</summary>{detail.error}</details></p>:<pre>{record.log||record.error||'No log output yet.'}</pre>}<button onClick={()=>onAction(record.actionId||record.action,record.params,record.context?[normalizeSelection(record.context)]:undefined)}>Review rerun…</button></details>;
}
export function WorkstationApp(){
  const [route,setRoute]=useState(initialRoute),[sessions,setSessions]=usePref<Session[]>('workstation.sessions',[]);
  const {selection,tab}=route;
  const [revision,setRevision]=useState(0),[dialog,setDialog]=useState<'open'|'commands'|'binary'|null>(null),[projectDialog,setProjectDialog]=useState<'open'|'import'|'create'|null>(null);
  const [navOpen,setNavOpen]=usePref('workstation.nav',true),[evidenceOpen,setEvidenceOpen]=usePref('workstation.evidence',true),[mobilePane,setMobilePane]=useState<'functions'|'evidence'|null>(null);
  const [navWidth,setNavWidth]=usePref('workstation.navWidth',240),[evidenceWidth,setEvidenceWidth]=usePref('workstation.evidenceWidth',260),[dockHeight,setDockHeight]=usePref('workstation.dockHeight',170),[dockOpen,setDockOpen]=usePref('workstation.dockOpen',true);
  const [isMobile,setIsMobile]=useState(()=>matchMedia('(max-width:700px)').matches),[mobileDockOpen,setMobileDockOpen]=useState(false);
  useEffect(()=>{const media=matchMedia('(max-width:700px)');const change=()=>setIsMobile(media.matches);media.addEventListener('change',change);return()=>media.removeEventListener('change',change);},[]);
  const effectiveDockOpen=isMobile?mobileDockOpen:dockOpen;
  const setVisibleDockOpen=isMobile?setMobileDockOpen:setDockOpen;
  const [dockTab,setDockTab]=usePref('workstation.dockTab','Activity'),[events,setEvents]=usePref<Data[]>('workstation.events',[]),[showJobHistory,setShowJobHistory]=usePref('workstation.showJobHistory',false);
  const [action,setAction]=useState<ActionRequest|null>(null),[matchingJobId,setMatchingJobId]=useState<string>(),[createNonce,setCreateNonce]=useState(0),[evidence,setEvidence]=useState<Data>({});
  const [filter,setFilter]=useState(''),[functionQuery,setFunctionQuery]=useState(''),[offset,setOffset]=useState(0),[address,setAddress]=useState(selection.addr),[binaryFilter,setBinaryFilter]=useState('');
  const [busy,setBusy]=useState(false),[localModel,setLocalModel]=useState<NormalizedAnalysisModel>();
  const pendingPrepare=useRef(readPref<string|null>('workstation.prepareJob',null));
  const runtime=useRef(new LocalProjectRuntime('local:workbench'));
  const reportedReadErrors=useRef<Record<string,string>>({});
  const jumpSequence=useRef(0);
  const searchRef=useRef<HTMLInputElement>(null),fileRef=useRef<HTMLInputElement>(null);
  const corpus=useData(`${API}/corpus-db`,revision);
  const corpusBlocked=Boolean(selection.logicalId&&!selection.corpusIdentity)||Boolean(selection.corpusIdentity&&(corpus.loading||corpus.error||corpus.data.corpus?.identity!==selection.corpusIdentity));
  useEffect(()=>{if(corpusBlocked){setAction(null);setEvidence({});}},[corpusBlocked]);
  const binaries=useData(`${API}/binaries?${query({locator:selection.locator,corpusIdentity:selection.corpusIdentity})}`,revision);
  const preparation=usePreparationRuns();
  const catalog=useData('/api/v1/actions',revision);
  const local=Boolean(selection.binaryHash&&!selection.slug&&!selection.program);
  const claimFeed=useEntityActivity(selection.locator,selection.slug,selection.program,!local&&!corpusBlocked&&Boolean(selection.slug||selection.program));
  const claimProjection=selectClaimProjection(claimFeed.entities,selection);
  const functions=useData(!local&&!corpusBlocked&&(selection.slug||selection.program)?`${API}/functions?${query({slug:selection.slug,locator:selection.locator,program:selection.program,corpusIdentity:selection.corpusIdentity},{q:functionQuery,filter:'all',offset,limit:100})}`:null,revision);
  const functionRows:Data[]=functions.data.functions||functions.data.results||[];
  const [jobs,setJobs]=useState<Data[]>([]),[jobsError,setJobsError]=useState('');
  const notify:Notify=useCallback((message,level='info',details={})=>{setEvents(old=>[...old,{id:crypto.randomUUID(),time:new Date().toISOString(),message,level,details}].slice(-500));if(level==='error'){if(!isMobile)setDockOpen(true);setDockTab('Problems');}},[setEvents,setDockOpen,setDockTab,isMobile]);
  const navigate=useCallback((next:Route,replace=false)=>{
    jumpSequence.current++;
    const url=routeUrl(location.href,next);
    if(location.pathname+location.search+location.hash!==url)history[replace?'replaceState':'pushState']({},'',url);
    setRoute(next);
  },[]);
  const select=useCallback((patch:Partial<Selection>)=>{
    navigate({...route,selection:mergeSelection(selection,patch.addr!==undefined&&patch.logicalId&&!patch.corpusIdentity?{...patch,logicalId:''}:patch)});setMobilePane(null);
  },[route,selection,navigate]);
  const chooseTab=(next:AnalysisTab)=>navigate({...route,tab:next});
  const refresh=()=>setRevision(r=>r+1);
  const onAction=useCallback((id:string,params?:Data,targets?:Selection[])=>{if(corpusBlocked){notify('The selected corpus identity is unavailable or changed. Select an identity from the current corpus before acting.','warning');return;}setDialog(null);setAction({id,params,targets:targets||[{...selection}]});},[selection,corpusBlocked,notify]);
  const props={selection,onSelect:select,onAction,notify,revision};
  useEffect(()=>{const handle=()=>{jumpSequence.current++;setRoute(readRoute(location.search,{selection:emptySelection,tab:'Disassembly'}));setMobilePane(null);};addEventListener('popstate',handle);return()=>{jumpSequence.current++;removeEventListener('popstate',handle);};},[]);
  useEffect(()=>{savePref('workstation.route',route);if(selection.slug||selection.program||selection.binaryHash){setSessions(old=>{const key=sessionKey(selection),existing=old.find(s=>sessionKey(s.selection)===key);const next={selection,name:existing?.name||selection.program.split('/').pop()||selection.slug||localModel?.artifacts.find(a=>a.hash===selection.binaryHash)?.name||selection.binaryHash?.slice(0,12)||'Binary'};return existing?old.map(s=>sessionKey(s.selection)===key?next:s):[...old,next];});}},[route,localModel,setSessions]);
  useEffect(()=>{setOffset(0);setFilter('');setFunctionQuery('');setEvidence({});},[selection.slug,selection.program,selection.locator,selection.binaryHash]);
  useEffect(()=>{setAddress(selection.addr);setEvidence({});},[selection.addr,selection.logicalId,selection.functionId]);
  useEffect(()=>{const timer=setTimeout(()=>{setFunctionQuery(filter);setOffset(0);},250);return()=>clearTimeout(timer);},[filter]);
  useEffect(()=>{void runtime.current.restore().then(async model=>{const saved=readPref<Data|null>('workstation.snapshot',null);if(saved){const snapshot=await projectStore.loadSnapshot(saved.projectId,saved.revision);if(!snapshot)throw new Error('Selected snapshot is unavailable. Open a stored revision from Binary menu.');runtime.current.index.replace(snapshot.model);setLocalModel(snapshot.model);}else setLocalModel(model);}).catch(e=>notify(`Local storage could not restore: ${e.message}`,'error'));},[notify]);
  useEffect(()=>{
    let alive=true;
    let timer:ReturnType<typeof setTimeout>;
    let controller:AbortController;
    const poll=async()=>{
      if(document.hidden){timer=setTimeout(()=>void poll(),5000);return;}
      controller=new AbortController();
      const timeout=setTimeout(()=>controller.abort(),8000);
      try{
        const result=await request('/dashboard/api/jobs',{signal:controller.signal});
        if(!Array.isArray(result.jobs))throw new Error('Invalid job response');
        if(alive){
          setJobs(result.jobs);setJobsError('');
          const prepared=result.jobs.find((job:Data)=>job.id===pendingPrepare.current&&['ok','failed','cancelled','interrupted','blocked'].includes(job.status));
          if(prepared){pendingPrepare.current=null;savePref('workstation.prepareJob',null);notify(`Preparation ${prepared.status}; refreshing recorded inventory.`,prepared.status==='ok'?'info':'warning',{jobId:prepared.id,error:prepared.error});setRevision(r=>r+1);}
        }
      }catch(e){if(alive)setJobsError(String(e));}
      finally{clearTimeout(timeout);if(alive)timer=setTimeout(()=>void poll(),5000);}
    };
    void poll();
    return()=>{alive=false;clearTimeout(timer);controller?.abort();};
  },[revision,notify]);
  useEffect(()=>{const key=(e:globalThis.KeyboardEvent)=>{
    const shortcut=shellShortcut(e,Boolean(dialog||action||projectDialog)||Boolean(document.querySelector('[role="dialog"][aria-modal="true"]')));
    if(!shortcut)return;
    if(shortcut==='commands'){e.preventDefault();setDialog('commands');}
    if(shortcut==='functions'){e.preventDefault();setNavOpen(true);setMobilePane('functions');setTimeout(()=>{if(!document.querySelector('[role="dialog"][aria-modal="true"]'))searchRef.current?.focus();},0);}
    if(shortcut==='dismiss')setMobilePane(null);
  };addEventListener('keydown',key);return()=>removeEventListener('keydown',key);},[setNavOpen,dialog,action,projectDialog]);
  useEffect(()=>{for(const [name,error] of [['binary library',binaries.error],['function inventory',functions.error],['action catalog',catalog.error]] as const){if(!error){delete reportedReadErrors.current[name];continue;}if(reportedReadErrors.current[name]===error)continue;reportedReadErrors.current[name]=error;notify(transientReadError(error)?`Refreshing ${name}; saved content remains available.`:error,transientReadError(error)?'info':'error',{sourceError:error,source:name});}},[binaries.error,functions.error,catalog.error,notify]);
  function openBinary(binary:Data){
    const next={...memberSelection({slug:binary.slug},[binary],selection),logicalId:''};
    setSessions(old=>{const entry={selection:next,name:String(binary.name||binary.label||binary.slug||binary.program||'Binary')};return [...old.filter(s=>sessionKey(s.selection)!==sessionKey(next)),entry];});
    navigate({selection:next,tab:'Disassembly'});setDialog(null);notify(`Opened ${binary.name||binary.slug||next.program}`);
  }
  function openLocal(hash:string,name:string){const next={...emptySelection,binaryHash:hash,projectId:'local:workbench'};setSessions(old=>[...old.filter(s=>sessionKey(s.selection)!==sessionKey(next)),{selection:next,name}]);navigate({selection:next,tab:'Hex'});setDialog(null);}
  async function ingest(files:File[]){
    if(busy||!files.length)return;setBusy(true);
    try{for(const file of files){notify(`Inspecting ${file.name} locally`);const result=await runtime.current.ingest({name:file.name,bytes:await file.arrayBuffer(),sourceKind:'regular'});if(result.status!=='completed'||!result.value){notify(`${file.name}: ${result.failure?.message||result.status}`,'error');continue;}savePref('workstation.snapshot',null);setLocalModel(result.value);const artifact=result.value.artifacts.find(a=>a.hash===result.value?.artifactHash)!;openLocal(artifact.hash,artifact.name);notify(`${file.name} stored locally by SHA256`);}}
    catch(e){notify(String(e),'error');}finally{setBusy(false);if(fileRef.current)fileRef.current.value='';}
  }
  async function jumpAddress(){
    const sequence=++jumpSequence.current;
    const value=address.trim();if(!value)return;
    if(corpusBlocked){chooseTab('Logical');return;}
    if(/^(0x)?[0-9a-f]+$/i.test(value)){select({addr:value,logicalId:''});return;}
    if(local){notify('Local byte navigation requires a hexadecimal file offset.','error');return;}
    try{const result=await request(`${API}/functions?${query(selection,{q:value,filter:'all',offset:0,limit:100})}`);if(sequence!==jumpSequence.current)return;const rows:Data[]=result.functions||result.results||[];const exact=rows.filter(r=>String(r.name).toLowerCase()===value.toLowerCase());const found=exact.length===1?exact[0]:rows.length===1?rows[0]:undefined;if(found)select({addr:addressOf(found),lastFunctionAddr:addressOf(found),logicalId:String(found.logical_id||'')});else{setFilter(value);setNavOpen(true);setMobilePane('functions');notify(rows.length?'Choose a function from the matching results.':`No recorded function found for ${value}`,'warning');}}
    catch(e){if(sequence===jumpSequence.current)notify(String(e),'error');}
  }
  const currentKey=sessionKey(selection);
  function closeSession(key:string){const remaining=sessions.filter(s=>sessionKey(s.selection)!==key);setSessions(remaining);if(key===currentKey)navigate({selection:mergeSelection(selection,remaining.at(-1)?.selection||emptySelection),tab});}
  const selectedFunction=functionRows.find(r=>addressOf(r)===selection.addr);
  const inspectMember=(next:Selection)=>{navigate({selection:mergeSelection(selection,next,true),tab:'Disassembly'});setMobilePane(null);};
  const css={'--nav-width':`${navOpen?navWidth:0}px`,'--evidence-width':`${evidenceOpen?evidenceWidth:0}px`,'--dock-height':`${effectiveDockOpen?dockHeight:38}px`} as CSSProperties;
  const offerPrepare=!corpusBlocked&&canPrepareAnalysis({local,selected:Boolean(selection.slug||selection.program),loading:functions.loading,error:functions.error,filter:filter||functionQuery,offset,count:Math.max(functionRows.length,Number(functions.data.total)||0),advertised:(catalog.data.actions||[]).some((a:Data)=>a.id==='workbench.prepare'&&a.available!==false)});
  const problems=events.filter(e=>(e.level==='error'||e.level==='warning')&&!transientReadError(e.message));
  // Running work is workspace-wide and must remain visible while the operator
  // inspects another project. Completed results retain project scope.
  const liveJobs=jobs.filter(activeJob).sort((left,right)=>jobTime(right)-jobTime(left));
  const scopedJobs=jobs.filter(job=>!activeJob(job)&&belongsToSelection(job,selection));
  const selectedJobs=scopedJobs.filter(job=>!failedJob(job)).sort((left,right)=>jobTime(right)-jobTime(left));
  const currentJobs=[...liveJobs,...selectedJobs];
  const historicalJobs=jobs.filter(job=>!currentJobs.some(current=>current.id===job.id)).sort((left,right)=>jobTime(right)-jobTime(left));
  const renderedJobs=showJobHistory?[...currentJobs,...historicalJobs]:currentJobs;
  const jobRefreshState=jobsError?'Refreshing recorded job state; the last received activity remains available.':'';
  const preparationRun=selectPreparation(preparation.runs,selection);
  return <div className="workstation" style={css}>
    <header className="ws-header"><button className="ws-mobile-menu" aria-label="Toggle Functions" aria-expanded={mobilePane==='functions'} onClick={()=>setMobilePane(mobilePane==='functions'?null:'functions')}><Icon name="menu"/></button><strong className="ws-brand">AgentDecompile</strong><a className="ws-cockpit-link" href="#cockpit" title="Program map, products and live lanes">Cockpit</a><button onClick={()=>setDialog('open')}><Icon name="folder"/>Open binary</button><button onClick={()=>{setCreateNonce(n=>n+1);chooseTab('Matching');setMobilePane(null);}}><Icon name="file"/>New scratch</button><button className="ws-search-button" onClick={()=>{setNavOpen(true);setMobilePane('functions');setTimeout(()=>searchRef.current?.focus(),0);}}><Icon name="search"/>Search functions… <kbd>Ctrl P</kbd></button><button onClick={()=>setDialog('commands')}><Icon name="command"/><span>Commands</span><kbd>Ctrl K</kbd></button><ExchangeContribution/></header>
    <div className="ws-sessions" aria-label="Binary sessions">{sessions.map(session=>{const key=sessionKey(session.selection);return <div key={key} className={key===currentKey?'active':''}><button aria-pressed={key===currentKey} onClick={()=>navigate({selection:mergeSelection(selection,session.selection),tab})}><Icon name="file"/>{session.name}</button><button aria-label={`Close ${session.name}`} onClick={()=>closeSession(key)}><Icon name="close"/></button></div>;})}{!sessions.length&&<span>No binary open</span>}<button onClick={()=>setDialog('binary')}>Binary menu…</button><button aria-label="Open another binary" onClick={()=>setDialog('open')}>+</button></div>
    <nav className="ws-analysis-tabs" aria-label="Analysis views"><div role="tablist" aria-label="Analysis" onKeyDown={tabKeys}>{analysisTabs.map(name=><button key={name} id={`tab-${name}`} role="tab" aria-selected={tab===name} aria-controls="analysis-panel" tabIndex={tab===name||(extraTabs.includes(tab)&&name==='Disassembly')?0:-1} onClick={()=>chooseTab(name)}>{name}</button>)}</div><label className="ws-more"><span>More</span><select aria-label="Additional analysis tools" value={extraTabs.includes(tab)?tab:''} onChange={e=>{if(e.target.value)chooseTab(e.target.value as AnalysisTab);}}><option value="">Tools…</option>{extraTabs.map(name=><option key={name}>{name}</option>)}</select></label></nav>
    <div className="ws-navigation"><button title="Back through selections" onClick={()=>history.back()}>← <span>Back</span></button><button title="Forward through selections" onClick={()=>history.forward()}>→</button>{selection.lastFunctionAddr&&selection.lastFunctionAddr!==selection.addr&&<button onClick={()=>select({addr:selection.lastFunctionAddr,logicalId:''})}>Last function</button>}<form onSubmit={e=>{e.preventDefault();void jumpAddress();}}><label className="sr-only" htmlFor="ws-address">{local?'Hex file offset':'Address or function name'}</label><input id="ws-address" value={address} onChange={e=>setAddress(e.target.value)} placeholder={local?'File offset (hex)':'Address or function name'}/><button>Go</button></form><button aria-label="Reload current evidence" onClick={refresh}><Icon name="reload"/></button><button aria-label="Copy share URL" onClick={()=>{const url=new URL(routeUrl(location.href,route),location.href).href;void navigator.clipboard.writeText(url).then(()=>notify(local?'Local link copied; the recipient needs this artifact in their browser.':'Selection link copied')).catch(()=>notify(`Copy this selection link: ${url}`,'warning'));}}><Icon name="share"/></button><button className="ws-desktop-toggle" aria-pressed={navOpen} onClick={()=>setNavOpen(!navOpen)}>Functions</button><button className="ws-desktop-toggle" aria-pressed={evidenceOpen} onClick={()=>setEvidenceOpen(!evidenceOpen)}>Evidence</button></div>
    <div className={`ws-workspace ${mobilePane?'has-mobile-pane':''}`}>
      <aside className={`ws-functions ${navOpen?'':'collapsed'} ${mobilePane==='functions'?'mobile-open':''}`} aria-label="Function navigator"><header><strong>Functions</strong><button aria-label="Close Functions" onClick={()=>{setNavOpen(false);setMobilePane(null);}}><Icon name="close"/></button></header><input ref={searchRef} aria-label="Search functions" placeholder="Search name or address…" value={filter} onChange={e=>setFilter(e.target.value)}/><ErrorLine error={functions.error}/><div className="ws-function-head"><span>Address</span><span>Name</span></div><div className="ws-function-list" aria-busy={functions.loading}>{functionRows.map((row,i)=><button key={`${addressOf(row)}:${i}`} aria-pressed={addressOf(row)===selection.addr} onClick={()=>select({addr:addressOf(row),lastFunctionAddr:addressOf(row),logicalId:String(row.logical_id||row.logicalId||'')})}><code>{addressOf(row)}</code><span>{row.name||row.symbol||'Unnamed function'}</span></button>)}{!functionRows.length&&<p>{functions.loading?'Loading functions…':local?'Local parser provides no function inventory.':selection.slug||selection.program?'No functions returned.':'Open a binary to browse functions.'}</p>}{offerPrepare&&<div className="ws-prepare"><p>No function inventory is recorded for this binary. Review preparation to generate analysis.</p><button onClick={()=>onAction('workbench.prepare',{slug:selection.slug,program:selection.program,locator:selection.locator})}>Prepare analysis…</button></div>}</div><footer><button disabled={!offset} onClick={()=>setOffset(Math.max(0,offset-100))}>Previous</button><span>{functionRows.length} shown</span><button disabled={functionRows.length<100} onClick={()=>setOffset(offset+100)}>Next</button></footer></aside>
      {navOpen&&<ResizeBar axis="x" label="Resize Functions" value={navWidth} min={180} max={480} onResize={d=>setNavWidth(w=>Math.max(180,Math.min(480,w+d)))}/>}
      <main id="analysis-panel" role="tabpanel" aria-label={tab} aria-labelledby={analysisTabs.includes(tab as any)?`tab-${tab}`:undefined} tabIndex={0} className="ws-main"><header className="ws-view-title"><strong>{tab}</strong><span>{selectedFunction?.name||selection.addr||selection.program||selection.slug||'Workspace'}</span></header><RetainedPanel active={tab==='Matching'}><MatchReview active={tab==='Matching'} revision={revision} notify={notify}/></RetainedPanel><RetainedPanel active={tab==='Matching'}><ScratchWorkspace selection={selection} revision={revision} catalog={catalog.data.actions||[]} notify={notify} onSelect={select} createNonce={createNonce} matchingJobId={matchingJobId} onMatchCandidate={(params:Data,captured?:Selection)=>{const matches=(binaries.data.binaries||[]).filter((b:Data)=>b.sha256===params.artifactHash);const binary=matches.length===1?matches[0]:undefined;onAction('workbench.match-candidate',params,[captured||normalizeSelection({slug:binary?.slug||'',program:binary?.program||'',locator:binary?.locator||'',binaryHash:params.artifactHash,addr:params.function||''})]);}}/></RetainedPanel><RetainedPanel active={tab==='Compare'}><CompareView active={tab==='Compare'} selection={selection} revision={revision} enabled={!local&&!corpusBlocked} onSelect={select}/></RetainedPanel>{tab==='Logical'&&<LogicalNavigator key={`${selection.corpusIdentity||''}:${selection.locator}:${selection.projectId||''}`} selection={selection} corpus={corpus} binaries={binaries.data.binaries||[]} revision={revision} onSelect={select} onMember={inspectMember}/>}{corpusBlocked&&tab!=='Logical'&&<p role="alert">The saved corpus identity is unverified, unavailable, or changed. <button onClick={()=>chooseTab('Logical')}>Choose a logical identity</button></p>}{tab!=='Matching'&&tab!=='Logical'&&tab!=='Compare'&&!corpusBlocked&&<AnalysisView key={currentKey} tab={tab} props={props} onEvidence={setEvidence}/>}</main>
      {evidenceOpen&&<ResizeBar axis="x" label="Resize Evidence" value={evidenceWidth} min={200} max={480} onResize={d=>setEvidenceWidth(w=>Math.max(200,Math.min(480,w-d)))}/>}
      <aside className={`ws-evidence ${evidenceOpen?'':'collapsed'} ${mobilePane==='evidence'?'mobile-open':''}`} aria-label="Evidence inspector"><header><strong>Evidence</strong><button aria-label="Close Evidence" onClick={()=>{setEvidenceOpen(false);setMobilePane(null);}}><Icon name="close"/></button></header><div className="ws-document"><dl><dt>Logical identity</dt><dd>{selection.logicalId||'No logical relationship selected'}</dd><dt>Concrete build</dt><dd>{selection.slug||selection.program||'No mutation target selected'}</dd><dt>Project</dt><dd>{selection.locator||selection.projectId||'Unbound corpus observation'}</dd><dt>Selected function</dt><dd>{evidence.function?.name||selectedFunction?.name||'None'}</dd><dt>{local?'File offset':'Address'}</dt><dd><code>{selection.addr||'None'}</code></dd><dt>Provider</dt><dd>{evidence.provider||evidence.source||evidence.decompile?.source||'Not recorded'}</dd><dt>Proof status</dt><dd>See the separate recorded claims below</dd></dl><ScopedClaims projection={claimProjection} address={selection.addr} connection={claimFeed.connection}/><p className="muted">Source and assembly are observations. Byte equivalence requires a revision-bound objdiff receipt.</p>{localModel&&local&&<section aria-label="Local artifact observation"><h3>Local observation</h3>{localModel.evidence.filter(e=>e.source.artifactHash===selection.binaryHash).map(item=><p key={item.id}>{item.summary}</p>)}</section>}<details><summary>Recorded evidence and provenance</summary><RecordView value={evidence}/>{localModel&&local&&<RecordView value={localModel.evidence.filter(e=>e.source.artifactHash===selection.binaryHash)}/>}</details><button disabled={!selection.addr||!selection.program} onClick={()=>onAction('mcp.manage-comments',{mode:'set',addressOrSymbol:selection.addr,comment:''})}>Add comment…</button></div></aside>
    </div>
    <div className="ws-mobile-rails"><button aria-expanded={mobilePane==='functions'} onClick={()=>setMobilePane(mobilePane==='functions'?null:'functions')}>Functions</button><button aria-expanded={mobilePane==='evidence'} onClick={()=>setMobilePane(mobilePane==='evidence'?null:'evidence')}>Evidence</button><button aria-expanded={effectiveDockOpen} onClick={()=>setVisibleDockOpen(!effectiveDockOpen)}>Activity ({problems.length?`${problems.length} problems`:events.length})</button></div>
    {(!isMobile||effectiveDockOpen)&&<ResizeBar axis="y" label="Resize Activity dock" value={dockHeight} min={100} max={420} onResize={d=>{setVisibleDockOpen(true);setDockHeight(h=>Math.max(100,Math.min(420,h-d)));}}/>}
    <section className={`ws-dock ${effectiveDockOpen?'':'closed'}`} aria-label="Activity dock" hidden={isMobile&&!effectiveDockOpen}><header><div role="tablist" aria-label="Activity" onKeyDown={tabKeys}>{['Activity','Recovery','Logs','Jobs','Problems'].map(name=><button key={name} role="tab" aria-selected={dockTab===name} tabIndex={dockTab===name?0:-1} onClick={()=>{setDockTab(name);setVisibleDockOpen(true);}}>{name}{name==='Recovery'&&preparationRun?` · ${preparationRun.status}`:name==='Jobs'&&currentJobs.length?liveJobs.length?` (${liveJobs.length} live)`:` (${currentJobs.length})`:name==='Problems'&&problems.length?` (${problems.length})`:''}</button>)}</div><button aria-label={effectiveDockOpen?'Collapse Activity':'Expand Activity'} onClick={()=>setVisibleDockOpen(!effectiveDockOpen)}>{effectiveDockOpen?'⌄':'⌃'}</button></header>{effectiveDockOpen&&<div className="ws-dock-body" role="tabpanel" aria-label={dockTab}>{dockTab==='Recovery'?<PreparationProgress run={preparationRun} selection={selection} notify={notify} error={preparation.error} loading={preparation.loading} lastConnectedAt={preparation.lastConnectedAt} now={preparation.now}/>:<>{jobRefreshState&&<p className="ws-job-refresh" role="status">{jobRefreshState}<details><summary>Connection details</summary>{jobsError}</details></p>}{dockTab==='Jobs'?<><div className="ws-job-heading"><strong>Workspace jobs</strong><span>{liveJobs.length?`${liveJobs.length} live across the workspace · ${selectedJobs.length} selected-project results`:selectedJobs.length?`${selectedJobs.length} selected-project results`:'No current jobs recorded.'}</span>{historicalJobs.length>0&&<button aria-pressed={showJobHistory} onClick={()=>setShowJobHistory(value=>!value)}>{showJobHistory?`Hide history (${historicalJobs.length})`:`Show history (${historicalJobs.length})`}</button>}</div>{renderedJobs.length?renderedJobs.map((job,index)=><JobRecord key={job.id} job={job} scope={activeJob(job)?'live':selectedJobs.some(current=>current.id===job.id)?'current':'history'} initialOpen={index===0} onAction={onAction}/>):<p>No jobs recorded.</p>}</>:dockTab==='Logs'?<>{currentJobs.map(job=><details key={job.id} open={activeJob(job)}><summary>{jobTitle(job)} · {job.status} · {activeJob(job)?'live across workspace':'selected project'}</summary><pre>{job.log||job.error||'Open Jobs to read current output.'}</pre></details>)}{events.map(event=><p key={event.id}><time>{new Date(event.time).toLocaleTimeString()}</time> {event.message}</p>)}{!currentJobs.length&&!events.length&&<p>No logs yet.</p>}</>:<>{(dockTab==='Problems'?problems:events).map(event=><div className={`ws-event ${event.level}`} key={event.id}><time>{new Date(event.time).toLocaleTimeString()}</time><span>{event.message}</span>{Object.keys(event.details||{}).length>0&&<details><summary>Details</summary><RecordView value={event.details}/></details>}</div>)}{!(dockTab==='Problems'?problems:events).length&&<p>{dockTab==='Problems'?'No reported problems.':'No activity yet.'}</p>}</>}</>}</div>}</section>
    <footer className="ws-status"><span>{busy?'Inspecting local file…':local?'Local artifact':selection.slug||selection.program?'Recorded analysis':'Ready'}</span><span>{selection.addr||'No address selected'}</span><span>{jobs.filter(j=>['running','queued'].includes(j.status)).length} active jobs</span></footer>
    <input hidden ref={fileRef} type="file" multiple accept=".elf,.so,.exe,.dll" onChange={e=>void ingest(Array.from(e.target.files||[]))}/>
    {dialog==='open'&&<DialogFrame title="Open binary" onClose={()=>setDialog(null)} busy={busy}><div className="ws-open"><div className="ws-toolbar"><button disabled={busy} onClick={()=>fileRef.current?.click()}>Choose local ELF / PE…</button><button onClick={()=>{setDialog(null);setProjectDialog('open');}}>Open server project…</button><button onClick={()=>{setDialog(null);setProjectDialog('import');}}>Import to server…</button></div><p>Local files stay in this browser. Server import uses the existing explicit import workflow.</p><label>Filter binaries <input value={binaryFilter} onChange={e=>setBinaryFilter(e.target.value)} placeholder="Binary name or SHA256"/></label><ErrorLine error={binaries.error}/><h3>Recorded binaries</h3>{binaries.loading&&<p role="status">Loading binary library…</p>}{(binaries.data.binaries||[]).filter((b:Data)=>`${b.name} ${b.slug} ${b.sha256}`.toLowerCase().includes(binaryFilter.toLowerCase())).map((binary:Data,i:number)=><button className="ws-open-row" key={binary.slug||i} onClick={()=>openBinary(binary)}><Icon name="file"/><span>{binary.name||binary.label||binary.slug||binary.program}<small>{binary.architecture||binary.format||binary.program||binary.locator}</small></span></button>)}{!binaries.loading&&!(binaries.data.binaries||[]).length&&<p>No recorded binaries returned.</p>}<h3>Stored locally</h3>{(localModel?.artifacts||[]).filter(a=>`${a.name} ${a.hash}`.toLowerCase().includes(binaryFilter.toLowerCase())).map(artifact=>{const match=matchRecordedArtifact(artifact,binaries.data.binaries||[]);return <div className="ws-local-row" key={artifact.hash}><button className="ws-open-row" onClick={()=>openLocal(artifact.hash,artifact.name)}><Icon name="file"/><span>{artifact.name}<small>{artifact.architecture} · {artifact.byteLength.toLocaleString()} bytes · {artifact.hash.slice(0,12)}</small></span></button>{match.state==='unique'?<button onClick={()=>openBinary(match.binary)}>Open recorded analysis</button>:<small>{match.state==='ambiguous'?'Multiple recorded bindings; choose a binary above.':'No recorded binding for this exact SHA256.'}</small>}</div>;})}</div></DialogFrame>}
    {dialog==='binary'&&<DialogFrame title="Binary and local project" onClose={()=>setDialog(null)}><div className="ws-open"><h3>Binary-wide source archive</h3>{selection.slug||selection.program?<SourceDownload selection={selection} notify={notify}/>:<p>Select a recorded binary to export its available source.</p>}<ProjectSnapshots projectId={selection.projectId||'local:workbench'} revision={revision} notify={notify} onOpen={snapshot=>{savePref('workstation.snapshot',{projectId:snapshot.projectId,revision:snapshot.revision});runtime.current.index.replace(snapshot.model);setLocalModel(snapshot.model);const artifact=snapshot.model.artifacts.find(a=>a.hash===snapshot.model.artifactHash)||snapshot.model.artifacts[0];if(artifact)openLocal(artifact.hash,artifact.name);else{navigate({selection:{...emptySelection,projectId:snapshot.projectId},tab:'Info'});setDialog(null);}}}/></div></DialogFrame>}
    {dialog==='commands'&&<DialogFrame title="Commands" onClose={()=>setDialog(null)}><Commands {...props}/></DialogFrame>}
    <ProjectDialog mode={projectDialog} selection={selection} onClose={()=>setProjectDialog(null)} onSelect={patch=>{navigate({selection:normalizeSelection(patch),tab:'Disassembly'});setProjectDialog(null);refresh();}} notify={notify} onRefresh={refresh}/>
    <ActionRunner request={action} selection={selection} onClose={()=>setAction(null)} notify={notify} onSubmitted={result=>{if(action?.id==='workbench.prepare'&&result.job?.id){pendingPrepare.current=result.job.id;savePref('workstation.prepareJob',result.job.id);}if(action?.id==='workbench.match-candidate'&&result.job?.id)setMatchingJobId(result.job.id);refresh();}}/>
  </div>;
}
