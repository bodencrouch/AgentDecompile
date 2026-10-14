# Vite reference workbench — 2026-10-09

Status: bounded production source change; not built or accepted in the running application.

## Slice-3 P2 fix — resolve ID-only collection scope

Review found that binary inventory projectBindings currently provide locator/program, so filtering an ID-only selection directly by project ID missed real members even when its project tab had already resolved an unambiguous same-corpus locator.

Fixed without changing backend contracts:
- ProjectSession now retains the resolved locator alongside its opaque key.
- WorkstationApp reads the active group's locator, uses it as the fallback parameter for the existing binary inventory read, and passes it to LogicalNavigator. This also preserves the inventory endpoint's locator-dependent shared-program observation.
- LogicalNavigator constructs a collection-only effective selection from the explicit locator or the verified tab association. Project member filtering, displayed targets and in-project member drill-in use that same selection.
- Raw route/saved selection is not silently rewritten. Outside-project members still clear project scope before deriving their target.
- Changing or revoking the resolved locator invalidates an in-flight member inspection through the existing generation guard.
- An unresolved or ambiguous ID gets an explicit locator-unavailable message rather than suggesting an empty project. Cross-corpus ID associations remain prohibited by the existing project identity helper.

Files: projectSessions.ts, WorkstationApp.tsx, LogicalNavigator.tsx, ProjectCollection.tsx, this report. Inline TypeScript parser: four files, zero syntax diagnostics, no emit. Tracked diff checks passed; new-file /dev/null checks emitted no whitespace diagnostics (exit 1 for differences). No tests/build/browser/runtime/backend/static/recovery actions. Focused source re-review requested from the existing reviewer.

Incremental fix diff below comes from in-memory before/after source for the first three files and the exact one-line ProjectCollection edit.

```diff
--- a/frontend/src/workstation/WorkstationApp.tsx (before ID-only collection fix)
+++ b/frontend/src/workstation/WorkstationApp.tsx (after ID-only collection fix)
@@ -82,6 +82,7 @@
   const projects=useMemo(()=>groupProjectSessions(sessions,selection),[sessions,selection]);
   const projectScopeSessions=useMemo(()=>[...sessions,{selection,name:''}],[sessions,selection]);
   const currentProjectKey=projectSessionKey(selection,projectScopeSessions);
+  const collectionLocator=projects.find(project=>project.key===currentProjectKey)?.locator||'';
   const [revision,setRevision]=useState(0),[dialog,setDialog]=useState<'open'|'commands'|'project'|null>(null),[projectDialog,setProjectDialog]=useState<'open'|'import'|'create'|null>(null),[contributionOpen,setContributionOpen]=useState(false);
   const [navOpen,setNavOpen]=usePref('workstation.nav',true),[evidenceOpen,setEvidenceOpen]=usePref('workstation.evidence',true),[mobilePane,setMobilePane]=useState<'functions'|'evidence'|null>(null);
   const [navWidth,setNavWidth]=usePref('workstation.navWidth',240),[evidenceWidth,setEvidenceWidth]=usePref('workstation.evidenceWidth',260),[dockHeight,setDockHeight]=usePref('workstation.dockHeight',170),[dockOpen,setDockOpen]=usePref('workstation.dockOpen',true);
@@ -101,7 +102,7 @@
   const corpus=useData(`${API}/corpus-db`,revision);
   const corpusBlocked=Boolean(selection.logicalId&&!selection.corpusIdentity)||Boolean(selection.corpusIdentity&&(corpus.loading||corpus.error||corpus.data.corpus?.identity!==selection.corpusIdentity));
   useEffect(()=>{if(corpusBlocked){setAction(null);setEvidence({});}},[corpusBlocked]);
+  const binaries=useData(`${API}/binaries?${query({locator:selection.locator||collectionLocator,corpusIdentity:selection.corpusIdentity})}`,revision);
-  const binaries=useData(`${API}/binaries?${query({locator:selection.locator,corpusIdentity:selection.corpusIdentity})}`,revision);
   const preparation=usePreparationRuns();
   const catalog=useData('/api/v1/actions',revision);
   const local=Boolean(selection.binaryHash&&!selection.slug&&!selection.program);
@@ -268,7 +269,7 @@
             }}/>
         </RetainedPanel>
         <RetainedPanel active={tab==='Compare'}><CompareView active={tab==='Compare'} selection={selection} revision={revision} enabled={!local&&!corpusBlocked} onSelect={select}/></RetainedPanel>
+        {tab==='Logical'&&<LogicalNavigator key={`${selection.corpusIdentity||''}:${selection.locator}:${selection.projectId||''}`} selection={selection} collectionLocator={collectionLocator} corpus={corpus} binaries={binaries.data.binaries||[]} binariesLoading={binaries.loading} binariesError={binaries.error||String(binaries.data.error||'')} revision={revision} onSelect={select} onMember={inspectMember}/>}
-        {tab==='Logical'&&<LogicalNavigator key={`${selection.corpusIdentity||''}:${selection.locator}:${selection.projectId||''}`} selection={selection} corpus={corpus} binaries={binaries.data.binaries||[]} binariesLoading={binaries.loading} binariesError={binaries.error||String(binaries.data.error||'')} revision={revision} onSelect={select} onMember={inspectMember}/>}
         {corpusBlocked&&tab!=='Logical'&&<p role="alert">The saved corpus identity is unverified, unavailable, or changed. <button onClick={()=>chooseTab('Logical')}>Choose a logical identity</button></p>}
         {tab!=='Matching'&&tab!=='Logical'&&tab!=='Compare'&&!corpusBlocked&&<AnalysisView key={currentKey} tab={tab} props={props} onEvidence={setEvidence}/>}
       </main>
--- a/frontend/src/workstation/LogicalNavigator.tsx (before ID-only collection fix)
+++ b/frontend/src/workstation/LogicalNavigator.tsx (after ID-only collection fix)
@@ -7,7 +7,8 @@
 import {CoverageMatrix} from './coverageMatrix';
 import {ProjectCollection} from './ProjectCollection';
 
+export function LogicalNavigator({selection,collectionLocator='',binaries,binariesLoading=false,binariesError='',corpus,revision,onSelect,onMember}:{selection:Selection;collectionLocator?:string;binaries:Data[];binariesLoading?:boolean;binariesError?:string;corpus:ReturnType<typeof useData>;revision:number;onSelect:(patch:Partial<Selection>)=>void;onMember:(selection:Selection)=>void}) {
+  const projectSelection={...selection,locator:selection.locator||collectionLocator};
-export function LogicalNavigator({selection,binaries,binariesLoading=false,binariesError='',corpus,revision,onSelect,onMember}:{selection:Selection;binaries:Data[];binariesLoading?:boolean;binariesError?:string;corpus:ReturnType<typeof useData>;revision:number;onSelect:(patch:Partial<Selection>)=>void;onMember:(selection:Selection)=>void}) {
   const [filter,setFilter]=useState(''),[search,setSearch]=useState(''),[pages,setPages]=useState<number[]>([0]);
   const [inspecting,setInspecting]=useState(false),[inspectionError,setInspectionError]=useState('');
   const [tierReports,setTierReports]=useState<{key:string;reports:Record<string,Data>;loading:boolean}>({key:'',reports:{},loading:false});
@@ -21,7 +22,7 @@
   const detailReady=compatible&&!legacy&&!list.error&&!detail.loading&&!detail.error&&!inspectionError&&detail.data.corpus?.identity===expected;
   const members:Data[]=detailReady?detail.data.members||[]:[];
   const generation=useRef(0);
+  useEffect(()=>{generation.current++;setInspectionError('');setInspecting(false);return()=>{generation.current++;};},[selection,collectionLocator,expected,revision]);
-  useEffect(()=>{generation.current++;setInspectionError('');setInspecting(false);return()=>{generation.current++;};},[selection,expected,revision]);
   const binaryBasis=JSON.stringify(binaries.map(binary=>[String(binary.slug||''),String(binary.content_sha256||binary.contentSha256||binary.sha256||'')]));
   const tierKey=detailReady?`${expected}:${selection.logicalId}:${revision}:${binaryBasis}`:'';
   useEffect(()=>{
@@ -41,13 +42,13 @@
       const fresh=await request(detailUrl!);
       if(attempt!==generation.current)return;
       if(fresh.corpus?.identity!==expected||!(fresh.members||[]).some((row:Data)=>row.slug===member.slug&&row.addr===member.addr))throw new Error('The corpus or member changed. Refresh and select the member again.');
+      onMember(memberSelection(member,binaries,outsideProject?{...selection,locator:'',projectId:''}:projectSelection));
-      onMember(memberSelection(member,binaries,outsideProject?{...selection,locator:'',projectId:''}:selection));
     }catch(error){if(attempt===generation.current)setInspectionError(String(error));}
     finally{if(attempt===generation.current)setInspecting(false);}
   }
   const missing=detailReady?binaries.filter(binary=>!members.some(member=>binary.slug===member.slug||binary.aliasSlugs?.includes(member.slug))):[];
   return <div className="ws-document">
+    <ProjectCollection selection={projectSelection} binaries={binaries} members={members} identityName={String(detail.data.name||'')} sourceFile={String(detail.data.source_file||'')} objectFile={String(detail.data.object_file||'')} ready={compatible&&!binariesLoading&&!binariesError} loading={corpus.loading||binariesLoading} error={corpus.error||binariesError} relationshipReady={detailReady} relationshipLoading={detail.loading} canInspect={detailReady&&!inspecting&&(detail.data.errors||[]).length===0} onInspect={(member,outside)=>void inspect(member,outside)} onBuild={onMember}/>
-    <ProjectCollection selection={selection} binaries={binaries} members={members} identityName={String(detail.data.name||'')} sourceFile={String(detail.data.source_file||'')} objectFile={String(detail.data.object_file||'')} ready={compatible&&!binariesLoading&&!binariesError} loading={corpus.loading||binariesLoading} error={corpus.error||binariesError} relationshipReady={detailReady} relationshipLoading={detail.loading} canInspect={detailReady&&!inspecting&&(detail.data.errors||[]).length===0} onInspect={(member,outside)=>void inspect(member,outside)} onBuild={onMember}/>
     <h2>Find related implementations</h2>
     <p>Reading corpus <code>{corpus.data.corpus?.path||corpus.data.current||'Unavailable'}</code>. This is the server-selected corpus, not a project-scoped lookup. Member evidence does not establish accepted equivalence or byte accuracy.</p>
     <ErrorLine error={corpus.error||inspectionError}/>
--- a/frontend/src/workstation/projectSessions.ts (before ID-only collection fix)
+++ b/frontend/src/workstation/projectSessions.ts (after ID-only collection fix)
@@ -3,7 +3,7 @@
 import {sessionKey} from './navigation';
 
 export type WorkstationSession={selection:Selection;name:string;lastFocusedAt?:number};
+export type ProjectSession={key:string;name:string;scope:string;locator:string;selection:Selection;members:WorkstationSession[]};
-export type ProjectSession={key:string;name:string;scope:string;selection:Selection;members:WorkstationSession[]};
 
 export function hasWorkspaceSelection(selection:Selection):boolean {
   return Boolean(selection.locator||selection.projectId||selection.slug||selection.program||selection.binaryHash||selection.logicalId);
@@ -49,7 +49,7 @@
     const scope=`${locator||selection.projectId||'Unbound observations — no project binding'}${selection.corpusIdentity?` · corpus ${selection.corpusIdentity}`:''}`;
     const name=locator?locator.split('/').pop()||locator:selection.projectId==='local:workbench'?'Local workspace':selection.projectId||'Unbound observations';
     let group=groups.get(key);
+    if(!group){group={key,name,scope,locator,selection,members:[]};groups.set(key,group);}
-    if(!group){group={key,name,scope,selection,members:[]};groups.set(key,group);}
     const recency=Number.isFinite(session.lastFocusedAt)?session.lastFocusedAt!:index;
     if(recency>=(latest.get(key)??-1)){group.selection=selection;latest.set(key,recency);}
     if(selection.slug||selection.program||selection.binaryHash){
--- a/frontend/src/workstation/ProjectCollection.tsx (before ID-only collection fix)
+++ b/frontend/src/workstation/ProjectCollection.tsx (after ID-only collection fix)
@@ -40,7 +40,7 @@
     {loading&&<p role="status">Reading recorded project bindings…</p>}
     {error&&<p role="alert">{error}</p>}
     {!ready&&!loading&&!error&&<p>Project relationships are unavailable until the corpus identity is verified.</p>}
+    {ready&&bound&&!builds.length&&<p>{!selection.locator&&selection.projectId?'This project ID has no unambiguous locator in the saved corpus context. Open the project by its locator to inspect recorded membership.':'No project-bound builds were returned. This does not establish an empty project; open its existing program inventory to inspect its contents.'}</p>}
-    {ready&&bound&&!builds.length&&<p>No project-bound builds were returned. This does not establish an empty project; open its existing program inventory to inspect its contents.</p>}
     {ready&&bound&&builds.length>0&&<>
       {selection.logicalId&&!relationshipReady&&<p role="status">{relationshipLoading?'Reading recorded logical membership…':'Recorded membership is unavailable for this identity.'}</p>}
       {hasRelationship&&<div className="collection-relationship" aria-label="Recorded logical membership across project builds">
```


## Continuation slice 3 — project collection and recorded relationships

Status: implemented in source only. No runtime, visual-fidelity or native recovery acceptance.

### Brief, source contract and added ownership

Make the selected project readable as a related collection with concrete member drill-in. Before coding, inspected VISION §§1–6, STRATEGY recovery/whole-image proof boundaries, FRONTEND_INTENT F07–F12, LogicalNavigator, coverageMatrix, selection helpers, the binary inventory, project-universe read contract and logical-detail JSON source.

Ownership added: workstation/LogicalNavigator.tsx (existing Vite logical surface), ProjectCollection.tsx and project-collection.css (new). WorkstationApp.tsx receives only inventory-state props and the project-open default view change. No backend/static/recovery files were edited.

Existing binary inventory is corpus-wide even when a locator is supplied: workbench.py _build_binary_inventory reads binary rows and joins durable program_binding records. ProjectCollection therefore filters projectBindings by canonical selected locator, or by explicit project ID when no locator exists. A binary's generic locator/name/path is not used to infer project membership. The logical API is also corpus-wide: pages.py _logical_detail_json returns identity members with slug, address, confidence, method and evidence, plus logical source_file/object_file metadata. No new API or secondary scheduler is added.

### User-visible behavior

- Opening a project now lands in the existing Logical view, whose primary surface is Project collection.
- Without a logical identity selected, the collection shows real project-bound build rows, their recorded platform/architecture/format and the uniquely resolved program target. A build name drills into existing analysis; ambiguous bindings cannot be opened by that control.
- Selecting an identity draws a directed membership tree from the named logical record to each project's returned build/function implementations. Every branch is supported by current detail.members and a recorded project binding. These are membership edges, not invented donor propagation, pairwise equivalence, accepted matches or call-graph edges.
- Member addresses drill directly into the existing concrete view. Method, confidence, exact bound program and one-to-many ambiguity are visible; relationship witness data is expandable.
- The logical record's source and object paths are available as recorded metadata, without pretending they are downloadable/current compiled files.
- Builds without a returned member stay in a separate roster. The UI explicitly avoids a negative-match claim.
- Corpus members outside project bindings are separate expandable evidence. Their inspection reuses the existing fresh logical-member revalidation but clears the selected project's locator/ID before deriving another binding, preventing the current project from being carried onto an outside member.
- The existing global logical search remains clearly labeled as server-selected corpus scope.
- Detailed coverage/tier and recovery/export surfaces remain available behind disclosures, leaving relationships primary. Their evidence semantics and underlying hooks are unchanged.

### Design and reference use

This is a functional addition within the existing workstation visual system, not a full shell redesign: frontend-app-builder's small-existing-UI exception applies. No image concept or copied reference assets/code. The collection uses existing navy/gray surfaces, cyan selection/evidence accents, compact system typography, monospace coordinates, native buttons/details, and a single CSS membership tree. Native controls remain keyboard reachable; the tree collapses to one column at a 600px container width. No animation, progress number, statistic wall, or per-build pipeline controls were added.

Reference influence: capa's expandable function-bound evidence; objdiff-web's selected symbol leading directly to concrete comparison; decomp.dev's project orientation; RzWeb's connected concrete views; Dogbolt's explicit output context. APKMan's import boundary and DQIV's real reconstruction/proof requirements remain intact rather than becoming extra pipeline buttons.

Source-only fidelity ledger: palette reuses existing tokens; typography reuses existing system/monospace roles; tree encodes returned membership only; unknown/failed/loading membership is distinct from empty results; source/object paths are labeled as logical-record metadata; mobile rules are authored but unrendered. Current source cannot be claimed visually accepted without the prohibited build/runtime work. No concept-to-browser comparison was performed.

### Exact checks and remaining gaps

Inline TypeScript createSourceFile parsed ProjectCollection.tsx, LogicalNavigator.tsx and WorkstationApp.tsx with zero syntax diagnostics and no emit. Tracked-file git diff --check returned no diagnostics; new-file /dev/null diff checks also returned no whitespace diagnostics (their exit 1 indicates additions). No tests/test files, builds, dependency installs, browser calls, server restarts, pipeline calls, deployment, or live 8080/5174 activity.

Remaining: complete authoritative project membership beyond returned binary bindings; bounded large-collection navigation/virtualization; Compare/Recover/Work consolidation; true pairwise relationship edges and acceptance/divergence receipts if provided by backend contracts; source/object file opening beyond recorded paths; actual event-to-diff work visualization; keyboard/mobile/rendered fidelity acceptance. Corpus-wide search is deliberately not falsely presented as a project-filtered identity index.

### Actual incremental slice-3 diff

Captured from exact source immediately before/after this slice, excluding previous dirty work and completed slice-2 edits. New components are /dev/null additions. Generated in memory; no temporary test/patch file.

```diff
--- a/frontend/src/workstation/WorkstationApp.tsx (before collection slice)
+++ b/frontend/src/workstation/WorkstationApp.tsx (after collection slice)
@@ -268,7 +268,7 @@
             }}/>
         </RetainedPanel>
         <RetainedPanel active={tab==='Compare'}><CompareView active={tab==='Compare'} selection={selection} revision={revision} enabled={!local&&!corpusBlocked} onSelect={select}/></RetainedPanel>
+        {tab==='Logical'&&<LogicalNavigator key={`${selection.corpusIdentity||''}:${selection.locator}:${selection.projectId||''}`} selection={selection} corpus={corpus} binaries={binaries.data.binaries||[]} binariesLoading={binaries.loading} binariesError={binaries.error||String(binaries.data.error||'')} revision={revision} onSelect={select} onMember={inspectMember}/>}
-        {tab==='Logical'&&<LogicalNavigator key={`${selection.corpusIdentity||''}:${selection.locator}:${selection.projectId||''}`} selection={selection} corpus={corpus} binaries={binaries.data.binaries||[]} revision={revision} onSelect={select} onMember={inspectMember}/>}
         {corpusBlocked&&tab!=='Logical'&&<p role="alert">The saved corpus identity is unverified, unavailable, or changed. <button onClick={()=>chooseTab('Logical')}>Choose a logical identity</button></p>}
         {tab!=='Matching'&&tab!=='Logical'&&tab!=='Compare'&&!corpusBlocked&&<AnalysisView key={currentKey} tab={tab} props={props} onEvidence={setEvidence}/>}
       </main>
@@ -291,7 +291,7 @@
     </DialogFrame>}
     {dialog==='commands'&&<DialogFrame title="Commands" onClose={()=>setDialog(null)}><Commands {...props}/></DialogFrame>}
     <ExchangeContribution showTrigger={false} open={contributionOpen} onOpenChange={setContributionOpen}/>
+    <ProjectDialog mode={projectDialog} selection={selection} onClose={()=>setProjectDialog(null)} onSelect={patch=>{navigate({selection:normalizeSelection(patch),tab:'Logical'});setProjectDialog(null);refresh();}} notify={notify} onRefresh={refresh}/>
-    <ProjectDialog mode={projectDialog} selection={selection} onClose={()=>setProjectDialog(null)} onSelect={patch=>{navigate({selection:normalizeSelection(patch),tab:'Disassembly'});setProjectDialog(null);refresh();}} notify={notify} onRefresh={refresh}/>
     <ActionRunner request={action} selection={selection} onClose={()=>setAction(null)} notify={notify} onSubmitted={result=>{if(action?.id==='workbench.prepare'&&result.job?.id){pendingPrepare.current=result.job.id;savePref('workstation.prepareJob',result.job.id);}if(action?.id==='workbench.match-candidate'&&result.job?.id)setMatchingJobId(result.job.id);refresh();}}/>
   </div>;
 }
--- a/frontend/src/workstation/LogicalNavigator.tsx (before collection slice)
+++ b/frontend/src/workstation/LogicalNavigator.tsx (after collection slice)
@@ -2,11 +2,12 @@
 import {ExportReadiness} from '../ExportReadiness';
 import {useEffect,useRef,useState} from 'react';
 import {API,request,type Data,type Selection} from '../contracts';
+import {ErrorLine,useData} from '../ui';
-import {ErrorLine,RecordView,useData} from '../ui';
 import {memberSelection} from './navigation';
 import {CoverageMatrix} from './coverageMatrix';
+import {ProjectCollection} from './ProjectCollection';
 
+export function LogicalNavigator({selection,binaries,binariesLoading=false,binariesError='',corpus,revision,onSelect,onMember}:{selection:Selection;binaries:Data[];binariesLoading?:boolean;binariesError?:string;corpus:ReturnType<typeof useData>;revision:number;onSelect:(patch:Partial<Selection>)=>void;onMember:(selection:Selection)=>void}) {
-export function LogicalNavigator({selection,binaries,corpus,revision,onSelect,onMember}:{selection:Selection;binaries:Data[];corpus:ReturnType<typeof useData>;revision:number;onSelect:(patch:Partial<Selection>)=>void;onMember:(selection:Selection)=>void}) {
   const [filter,setFilter]=useState(''),[search,setSearch]=useState(''),[pages,setPages]=useState<number[]>([0]);
   const [inspecting,setInspecting]=useState(false),[inspectionError,setInspectionError]=useState('');
   const [tierReports,setTierReports]=useState<{key:string;reports:Record<string,Data>;loading:boolean}>({key:'',reports:{},loading:false});
@@ -33,19 +34,21 @@
     void Promise.all([worker(),worker()]).then(()=>{if(!controller.signal.aborted)setTierReports({key:tierKey,reports:{...reports},loading:false});});
     return()=>controller.abort();
   },[tierKey,binaryBasis,expected]);
+  async function inspect(member:Data,outsideProject=false){
-  async function inspect(member:Data){
     const attempt=++generation.current;
     setInspecting(true);setInspectionError('');
     try{
       const fresh=await request(detailUrl!);
       if(attempt!==generation.current)return;
       if(fresh.corpus?.identity!==expected||!(fresh.members||[]).some((row:Data)=>row.slug===member.slug&&row.addr===member.addr))throw new Error('The corpus or member changed. Refresh and select the member again.');
+      onMember(memberSelection(member,binaries,outsideProject?{...selection,locator:'',projectId:''}:selection));
-      onMember(memberSelection(member,binaries,selection));
     }catch(error){if(attempt===generation.current)setInspectionError(String(error));}
     finally{if(attempt===generation.current)setInspecting(false);}
   }
   const missing=detailReady?binaries.filter(binary=>!members.some(member=>binary.slug===member.slug||binary.aliasSlugs?.includes(member.slug))):[];
+  return <div className="ws-document">
+    <ProjectCollection selection={selection} binaries={binaries} members={members} identityName={String(detail.data.name||'')} sourceFile={String(detail.data.source_file||'')} objectFile={String(detail.data.object_file||'')} ready={compatible&&!binariesLoading&&!binariesError} loading={corpus.loading||binariesLoading} error={corpus.error||binariesError} relationshipReady={detailReady} relationshipLoading={detail.loading} canInspect={detailReady&&!inspecting&&(detail.data.errors||[]).length===0} onInspect={(member,outside)=>void inspect(member,outside)} onBuild={onMember}/>
+    <h2>Find related implementations</h2>
-  return <div className="ws-document"><h2>Shared logical codebase</h2>
     <p>Reading corpus <code>{corpus.data.corpus?.path||corpus.data.current||'Unavailable'}</code>. This is the server-selected corpus, not a project-scoped lookup. Member evidence does not establish accepted equivalence or byte accuracy.</p>
     <ErrorLine error={corpus.error||inspectionError}/>
     {legacy&&<p role="status">This saved logical ID has no database identity. Select an identity from the list explicitly to bind it to this corpus.</p>}
@@ -59,16 +62,10 @@
     <div className="ws-toolbar"><button disabled={pages.length===1||list.loading} onClick={()=>setPages(old=>old.slice(0,-1))}>Previous identities</button><button disabled={!list.data.more||list.loading||Boolean(list.error)} onClick={()=>setPages(old=>[...old,Number(list.data.rows?.at(-1)?.id)||0])}>Next identities</button></div>
     {selection.logicalId&&<section aria-label="Logical entity members"><h3>{detail.data.name||`Identity ${selection.logicalId}`}</h3><ErrorLine error={detail.error}/>{(detail.data.errors||[]).map((error:string,index:number)=><ErrorLine key={index} error={error}/>)}
       {detail.loading&&<p role="status">Reading members…</p>}
+      {detailReady&&!members.length&&<p>No members returned for this identity.</p>}
+      {detailReady&&<details><summary>Recorded coverage and tier evidence</summary><CoverageMatrix members={members} binaries={binaries} logicalId={selection.logicalId} corpusIdentity={selection.corpusIdentity} tierReportsBySlug={tierReports.key===tierKey?tierReports.reports:{}} loading={tierReports.key===tierKey&&tierReports.loading}/></details>}
-      <table className="ws-table"><thead><tr><th>Build / address</th><th>Relationship evidence</th><th>Inspection target</th></tr></thead><tbody>{members.map((member,index)=>{
-        const target=memberSelection(member,binaries,selection);
-        const ambiguous=members.filter(row=>row.slug===member.slug).length>1;
-        return <tr key={`${member.slug}:${member.addr}:${index}`}><td><strong>{member.slug}</strong><br/><code>{member.addr||'No address'}</code></td><td>{ambiguous?'Multiple recorded members in this build; relationship ambiguous. ':''}{member.method||'Method not recorded'} · confidence {member.confidence??'not recorded'}<details><summary>Evidence / divergence</summary><RecordView value={member.evidence??{status:'No divergence or acceptance verdict supplied'}}/></details></td><td><button disabled={!target.slug||!target.addr||!detailReady||inspecting||(detail.data.errors||[]).length>0} onClick={()=>void inspect(member)}>Inspect member</button><small>{target.program?`${target.locator} · ${target.program}`:'No unique project binding; corpus browsing only'}</small></td></tr>;
-      })}</tbody></table>
-      {!detail.loading&&!members.length&&<p>No members returned for this identity.</p>}
-      {detailReady&&<CoverageMatrix members={members} binaries={binaries} logicalId={selection.logicalId} corpusIdentity={selection.corpusIdentity} tierReportsBySlug={tierReports.key===tierKey?tierReports.reports:{}} loading={tierReports.key===tierKey&&tierReports.loading}/>}
       {missing.length>0&&<details><summary>Builds without a returned member ({missing.length})</summary><p>This does not establish that a build is unmatched; the API supplies no negative-match or divergence verdict.</p><ul>{missing.map((binary,index)=><li key={binary.slug||index}>{binary.name||binary.slug||binary.sha256}</li>)}</ul></details>}
     </section>}
+    <details><summary>Recovery and export evidence</summary><TierProgress selection={selection} revision={revision}/><ExportReadiness selection={selection} revision={revision}/></details>
-    <TierProgress selection={selection} revision={revision}/>
-    <ExportReadiness selection={selection} revision={revision}/>
   </div>;
 }
diff --git a/src/agentdecompile_recovery/corpus/dashboard/frontend/src/workstation/ProjectCollection.tsx b/src/agentdecompile_recovery/corpus/dashboard/frontend/src/workstation/ProjectCollection.tsx
new file mode 100644
index 00000000..4488b9e2
--- /dev/null
+++ b/src/agentdecompile_recovery/corpus/dashboard/frontend/src/workstation/ProjectCollection.tsx
@@ -0,0 +1,58 @@
+import type {Data,Selection} from '../contracts';
+import {canonicalProjectLocator} from '../projectLocator';
+import {RecordView} from '../ui';
+import {memberSelection} from './navigation';
+import './project-collection.css';
+
+/** Only recorded bindings establish project membership; filenames do not. */
+export function collectionBuilds(binaries:Data[],selection:Selection):Data[] {
+  const locator=canonicalProjectLocator(selection.locator);
+  return binaries.filter(binary=>(binary.projectBindings||[]).some((binding:Data)=>
+    locator?canonicalProjectLocator(binding.locator)===locator:
+      Boolean(selection.projectId&&(binding.projectId||binding.project_id)===selection.projectId)));
+}
+const contains=(binary:Data,member:Data)=>binary.slug===member.slug||Boolean(binary.aliasSlugs?.includes(member.slug));
+const buildName=(binary:Data)=>String(binary.name||binary.label||binary.slug||'Unnamed build');
+
+export function ProjectCollection({selection,binaries,members,identityName,sourceFile,objectFile,ready,loading,error,relationshipReady,relationshipLoading,canInspect,onInspect,onBuild}:{
+  selection:Selection;binaries:Data[];members:Data[];identityName:string;sourceFile:string;objectFile:string;ready:boolean;loading:boolean;error:string;relationshipReady:boolean;relationshipLoading:boolean;canInspect:boolean;
+  onInspect:(member:Data,outsideProject?:boolean)=>void;onBuild:(selection:Selection)=>void;
+}){
+  const builds=ready?collectionBuilds(binaries,selection):[];
+  const related=builds.filter(binary=>members.some(member=>contains(binary,member)));
+  const withoutMembership=builds.filter(binary=>!members.some(member=>contains(binary,member)));
+  const outside=ready?members.filter(member=>!builds.some(binary=>contains(binary,member))):[];
+  const bound=Boolean(selection.locator||selection.projectId);
+  const hasRelationship=Boolean(selection.logicalId&&relationshipReady);
+  function membership(member:Data,index:number,external=false){
+    const siblings=members.filter(row=>row.slug===member.slug);
+    const target=memberSelection(member,binaries,external?{...selection,locator:'',projectId:''}:selection);
+    return <li key={`${member.slug}:${member.addr}:${index}`} className="collection-member">
+      <button type="button" disabled={!canInspect||!member.slug||!member.addr} onClick={()=>onInspect(member,external)} title="Inspect this recorded function implementation"><code>{String(member.addr||'Address unavailable')}</code><span>{String(member.name||member.slug||'Recorded member')}</span></button>
+      <small>{String(member.method||'Method not recorded')} · confidence {String(member.confidence??'not recorded')}</small>
+      <small>{target.program?`${target.locator} · ${target.program}`:'No unique project binding; corpus observation only'}</small>
+      {siblings.length>1&&<small>Multiple recorded members in this build; correspondence is ambiguous.</small>}
+      <details><summary>Relationship evidence</summary><RecordView value={member.evidence??{status:'No divergence or acceptance verdict supplied'}}/></details>
+    </li>;
+  }
+  return <section className="project-collection" aria-label="Selected project collection">
+    <header><h2>{bound?'Project collection':'Corpus relationships'}</h2><code>{selection.locator||selection.projectId||'No project binding selected'}</code></header>
+    {loading&&<p role="status">Reading recorded project bindings…</p>}
+    {error&&<p role="alert">{error}</p>}
+    {!ready&&!loading&&!error&&<p>Project relationships are unavailable until the corpus identity is verified.</p>}
+    {ready&&bound&&!builds.length&&<p>No project-bound builds were returned. This does not establish an empty project; open its existing program inventory to inspect its contents.</p>}
+    {ready&&bound&&builds.length>0&&<>
+      {selection.logicalId&&!relationshipReady&&<p role="status">{relationshipLoading?'Reading recorded logical membership…':'Recorded membership is unavailable for this identity.'}</p>}
+      {hasRelationship&&<div className="collection-relationship" aria-label="Recorded logical membership across project builds">
+        <div className="collection-identity"><strong>{identityName||`Identity ${selection.logicalId}`}</strong><code>logical {selection.logicalId}</code><span>Recorded membership</span><small>Branches link this identity to returned functions. They do not establish accepted equivalence or byte accuracy.</small>{(sourceFile||objectFile)&&<details><summary>Logical record paths</summary>{sourceFile&&<p>Source <code>{sourceFile}</code></p>}{objectFile&&<p>Object <code>{objectFile}</code></p>}</details>}</div>
+        {related.length?<ol className="collection-branches">{related.map((binary,index)=><li key={`${binary.slug}:${index}`} className="collection-build"><h3>{buildName(binary)}</h3><small>{[binary.platform,binary.architecture,binary.format].filter(Boolean).join(' · ')||'Build metadata not recorded'}</small><ul>{members.filter(member=>contains(binary,member)).map((member,index)=>membership(member,index))}</ul></li>)}</ol>:<p>No member of this logical identity was returned for the project's recorded builds.</p>}
+      </div>}
+      {!selection.logicalId&&<p>Select a logical entity below to see its recorded implementations across these builds.</p>}
+      {withoutMembership.length>0&&<section className="collection-roster" aria-label="Project build roster"><h3>{hasRelationship?'Project builds without returned membership':'Builds in this project'}</h3>{hasRelationship&&<p className="muted">No returned membership is not a negative-match verdict.</p>}<ul>{withoutMembership.map((binary,index)=>{
+        const target=memberSelection({slug:binary.slug},binaries,{...selection,logicalId:''});
+        return <li key={`${binary.slug}:${index}`}><button type="button" disabled={!target.program||!target.locator||!ready} onClick={()=>onBuild(target)} title="Inspect this build's recorded analysis">{buildName(binary)}</button><span>{[binary.platform,binary.architecture,binary.format].filter(Boolean).join(' · ')||'Build metadata not recorded'}</span><small>{target.program||'No unique project/program binding for inspection'}</small></li>;
+      })}</ul></section>}
+    </>}
+    {outside.length>0&&<details className="collection-outside" open={!bound}><summary>{bound?'Related corpus members outside these project bindings':'Recorded corpus members'}</summary><p>These are corpus relationships; they are not evidence of membership in the selected project.</p><ul>{outside.map((member,index)=>membership(member,index,true))}</ul></details>}
+  </section>;
+}
diff --git a/src/agentdecompile_recovery/corpus/dashboard/frontend/src/workstation/project-collection.css b/src/agentdecompile_recovery/corpus/dashboard/frontend/src/workstation/project-collection.css
new file mode 100644
index 00000000..25492b0c
--- /dev/null
+++ b/src/agentdecompile_recovery/corpus/dashboard/frontend/src/workstation/project-collection.css
@@ -0,0 +1,13 @@
+.project-collection{container-type:inline-size;margin-bottom:20px;border-bottom:1px solid var(--border);padding-bottom:16px}
+.project-collection>header{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:12px}
+.project-collection>header h2{margin:0}.project-collection>header code{font-size:11px;color:var(--muted);overflow-wrap:anywhere}
+.collection-relationship{display:grid;grid-template-columns:minmax(180px,1fr) minmax(0,3fr);gap:24px;margin-block:16px}
+.collection-identity{display:flex;flex-direction:column;gap:7px;align-self:start;position:sticky;top:0;border-left:3px solid var(--accent);padding:10px 12px;background:var(--bg-panel);overflow-wrap:anywhere}
+.collection-relationship:has(.collection-branches) .collection-identity:after{content:'';position:absolute;right:-24px;top:9px;width:24px;border-top:1px solid var(--accent)}
+.collection-identity>span{color:var(--accent);font-size:11px}.collection-identity>code{font-size:11px;color:var(--muted)}
+.collection-branches,.collection-build>ul,.collection-roster ul,.collection-outside>ul{list-style:none;margin:0;padding:0}
+.collection-branches{border-left:1px solid var(--accent);padding-left:20px}
+.collection-build{position:relative;padding:0 0 18px}.collection-build:before{content:'';position:absolute;left:-20px;top:9px;width:14px;border-top:1px solid var(--accent)}.collection-build:after{content:'';position:absolute;left:-10px;top:6px;width:6px;height:6px;border-top:1px solid var(--accent);border-right:1px solid var(--accent);transform:rotate(45deg)}
+.collection-build h3{margin-bottom:3px;overflow-wrap:anywhere}.collection-member{border-bottom:1px solid var(--border);padding:8px 0;min-width:0}.collection-member>button{display:flex;justify-content:flex-start;width:100%;text-align:left;border:0;background:transparent;padding:4px 0;flex-wrap:wrap}.collection-member>button code{color:var(--accent);font-size:12px}.collection-member>button span{overflow-wrap:anywhere}.collection-member>small{font-size:11px}.collection-member summary{font-size:11px;color:var(--muted)}
+.collection-roster{margin-top:14px}.collection-roster li{display:grid;grid-template-columns:minmax(130px,1fr) minmax(0,1fr);gap:4px 12px;border-top:1px solid var(--border);padding:7px 0}.collection-roster button{justify-content:flex-start;text-align:left;border:0;background:transparent;padding-left:0;overflow-wrap:anywhere}.collection-roster li>span{align-self:center;color:var(--muted);font-size:11px}.collection-roster li>small{grid-column:1/-1;overflow-wrap:anywhere}.collection-outside{margin-top:12px}.collection-outside>summary{color:var(--muted)}
+@container(max-width:600px){.collection-relationship{grid-template-columns:minmax(0,1fr);gap:14px}.collection-identity{position:static}.collection-identity:after{display:none}.collection-branches{margin-left:12px}.collection-roster li{grid-template-columns:minmax(0,1fr)}.collection-roster li>small{grid-column:1}}
```


## Slice-2 review fix — locator authority namespace

The locator contract does not guarantee globally namespaced identity. [parse_shared_locator](../../src/agentdecompile_recovery/corpus/ghidra_project.py) (lines 120–155) retains host/port/repository for shared Ghidra URLs and URL authority for HTTP projects. However, classify_locator (lines 168–193 and 225–235 in the same file) returns a resolved local .gpr filesystem path as locator/canonical without a server namespace. [The frontend normalizer](../../src/agentdecompile_recovery/corpus/dashboard/frontend/src/projectLocator.ts) performs lexical path normalization only; it adds no backend authority. [Selection](../../src/agentdecompile_recovery/corpus/dashboard/frontend/src/contracts.ts) supplies corpusIdentity as the explicit database-file context. A bare canonical path was therefore insufficient to justify cross-context grouping.

Updated only projectSessions.ts and this report. Locator keys now serialize [corpusIdentity, canonicalLocator], both for explicit locators and same-corpus ID-to-locator associations. Same-path selections with different corpus identities remain separate; unknown corpus context also stays separate from known context. The common identity helper returns the display locator separately from its opaque key, so tab labels and scope text never parse or display a serialized identity. Scope text includes corpus identity even for explicit locators. The unbound key also serializes its context, avoiding collision between missing context and an opaque corpus literally named unbound.

This supersedes the preceding review note that canonical locators alone were authoritative. Conservative separation can leave separate tabs for a known and an unknown corpus referring to the same physical path until the existing selection contract supplies matching context; this slice does not invent or migrate that evidence.

Checks: inline TypeScript createSourceFile on projectSessions.ts returned zero syntax diagnostics, no emit. No tests/builds/browser/runtime/backend/static/job/approval actions. This is source-only; no server or data inspection was performed.

Actual incremental before/after diff captured in memory:

```diff
--- a/frontend/src/workstation/projectSessions.ts (before locator-namespace review fix)
+++ b/frontend/src/workstation/projectSessions.ts (after locator-namespace review fix)
@@ -9,40 +9,44 @@
   return Boolean(selection.locator||selection.projectId||selection.slug||selection.program||selection.binaryHash||selection.logicalId);
 }
 
-/** IDs are context-scoped; only an unambiguous same-corpus association joins tabs. */
-export function projectSessionKey(selection:Selection,sessions:WorkstationSession[]):string {
-  selection=normalizeSelection(selection);
-  const locator=canonicalProjectLocator(selection.locator);
-  if(locator)return `locator:${locator}`;
-  if(selection.projectId){
-    const corpusIdentity=selection.corpusIdentity||'';
-    const locators=new Set(sessions.map(session=>normalizeSelection(session.selection))
-      .filter(saved=>saved.projectId===selection.projectId&&(saved.corpusIdentity||'')===corpusIdentity)
-      .map(saved=>canonicalProjectLocator(saved.locator)).filter(Boolean));
-    if(locators.size===1)return `locator:${[...locators][0]}`;
-    return `project:${JSON.stringify([corpusIdentity,selection.projectId])}`;
-  }
-  // Unbound observations share a clearly labeled workspace, not an invented project.
-  return `corpus:${selection.corpusIdentity||'unbound'}`;
-}
-
-function memberName(selection:Selection):string {
-  return selection.program||selection.slug||selection.binaryHash?.slice(0,12)||'Project overview';
-}
-
-/** Project tabs are a projection; retain concrete saved sessions and their contexts. */
-export function groupProjectSessions(sessions:WorkstationSession[],current:Selection):ProjectSession[] {
-  const records=sessions.map(session=>({...session,selection:normalizeSelection(session.selection)}));
-  if(hasWorkspaceSelection(current)&&!records.some(session=>sessionKey(session.selection)===sessionKey(current)))
-    records.push({selection:current,name:memberName(current)});
-  const groups=new Map<string,ProjectSession>();
-  const latest=new Map<string,number>();
-  for(const [index,session] of records.entries()){
-    const selection=session.selection;
-    if(!hasWorkspaceSelection(selection))continue;
-    const key=projectSessionKey(selection,records);
-    const locator=key.startsWith('locator:')?key.slice('locator:'.length):'';
-    const scope=locator||`${selection.projectId||'Unbound observations — no project binding'}${selection.corpusIdentity?` · corpus ${selection.corpusIdentity}`:''}`;
+/** Local paths and project IDs have no global server namespace. */
+function projectSessionIdentity(selection:Selection,sessions:WorkstationSession[]):{key:string;locator:string} {
+  selection=normalizeSelection(selection);
+  const corpusIdentity=selection.corpusIdentity||'';
+  const located=(locator:string)=>({key:`locator:${JSON.stringify([corpusIdentity,locator])}`,locator});
+  const locator=canonicalProjectLocator(selection.locator);
+  if(locator)return located(locator);
+  if(selection.projectId){
+    const locators=new Set(sessions.map(session=>normalizeSelection(session.selection))
+      .filter(saved=>saved.projectId===selection.projectId&&(saved.corpusIdentity||'')===corpusIdentity)
+      .map(saved=>canonicalProjectLocator(saved.locator)).filter(Boolean));
+    if(locators.size===1)return located([...locators][0]);
+    return {key:`project:${JSON.stringify([corpusIdentity,selection.projectId])}`,locator:''};
+  }
+  // Unbound observations share a clearly labeled workspace, not an invented project.
+  return {key:`corpus:${JSON.stringify(corpusIdentity)}`,locator:''};
+}
+
+export function projectSessionKey(selection:Selection,sessions:WorkstationSession[]):string {
+  return projectSessionIdentity(selection,sessions).key;
+}
+
+function memberName(selection:Selection):string {
+  return selection.program||selection.slug||selection.binaryHash?.slice(0,12)||'Project overview';
+}
+
+/** Project tabs are a projection; retain concrete saved sessions and their contexts. */
+export function groupProjectSessions(sessions:WorkstationSession[],current:Selection):ProjectSession[] {
+  const records=sessions.map(session=>({...session,selection:normalizeSelection(session.selection)}));
+  if(hasWorkspaceSelection(current)&&!records.some(session=>sessionKey(session.selection)===sessionKey(current)))
+    records.push({selection:current,name:memberName(current)});
+  const groups=new Map<string,ProjectSession>();
+  const latest=new Map<string,number>();
+  for(const [index,session] of records.entries()){
+    const selection=session.selection;
+    if(!hasWorkspaceSelection(selection))continue;
+    const {key,locator}=projectSessionIdentity(selection,records);
+    const scope=`${locator||selection.projectId||'Unbound observations — no project binding'}${selection.corpusIdentity?` · corpus ${selection.corpusIdentity}`:''}`;
     const name=locator?locator.split('/').pop()||locator:selection.projectId==='local:workbench'?'Local workspace':selection.projectId||'Unbound observations';
     let group=groups.get(key);
     if(!group){group={key,name,scope,selection,members:[]};groups.set(key,group);}
```


## Slice-2 review fix — corpus-scoped project IDs

The grouping risk was valid. Source inspection found no global uniqueness guarantee for projectId: Selection.projectId is an optional string (frontend/src/contracts.ts); SharedContext.projectId is a plain string (analysis/contracts.ts); LocalProjectRuntime accepts the caller's string unchanged (runtime/localProject.ts), and WorkstationApp uses the reusable local:workbench ID. Selection.corpusIdentity explicitly identifies the database file, while existing sessionKey already includes both fields. These contracts do not justify treating an arbitrary saved project ID as globally unique.

Fixed only frontend/src/workstation/projectSessions.ts:
- Project-ID-to-locator association now requires the same corpusIdentity as well as projectId. A known corpus cannot borrow an association from an unknown or different corpus.
- Unresolved ID-only keys serialize [corpusIdentity, projectId], keeping reused IDs in separate contexts without delimiter collisions.
- Saved selections are normalized before association checks, matching existing legacy .gpr handling.
- Scope text includes the corpus identity for ID-only workspaces, so identical display IDs can be distinguished.
- Explicit canonical locators remain the project-tab authority: views with the same recorded physical project locator share a tab while their concrete member Selection retains its own corpus identity. No new cross-corpus equivalence or native write claim is made.

Inline TypeScript createSourceFile returned zero syntax diagnostics, no emit. Tracked WorkstationApp diff check passed; the new helper's git diff --no-index --check against /dev/null emitted no whitespace diagnostics (exit 1 denotes its new-file difference). No tests/build/browser/runtime/backend/static/job/approval actions. This supersedes the earlier slice-2 ID association description; previous embedded diffs remain historical before/after artifacts.

Actual incremental fix diff, calculated in memory from source immediately before and after this review fix:

```diff
--- a/frontend/src/workstation/projectSessions.ts (before corpus-scope review fix)
+++ b/frontend/src/workstation/projectSessions.ts (after corpus-scope review fix)
@@ -9,38 +9,40 @@
   return Boolean(selection.locator||selection.projectId||selection.slug||selection.program||selection.binaryHash||selection.logicalId);
 }
 
-/** Only an explicit, unambiguous ID/locator association may join saved tabs. */
-export function projectSessionKey(selection:Selection,sessions:WorkstationSession[]):string {
-  selection=normalizeSelection(selection);
-  const locator=canonicalProjectLocator(selection.locator);
-  if(locator)return `locator:${locator}`;
-  if(selection.projectId){
-    const locators=new Set(sessions.filter(session=>session.selection.projectId===selection.projectId)
-      .map(session=>canonicalProjectLocator(session.selection.locator)).filter(Boolean));
-    if(locators.size===1)return `locator:${[...locators][0]}`;
-    return `project:${selection.projectId}`;
-  }
-  // Unbound observations share a clearly labeled workspace, not an invented project.
-  return `corpus:${selection.corpusIdentity||'unbound'}`;
-}
-
-function memberName(selection:Selection):string {
-  return selection.program||selection.slug||selection.binaryHash?.slice(0,12)||'Project overview';
-}
-
-/** Project tabs are a projection; retain concrete saved sessions and their contexts. */
-export function groupProjectSessions(sessions:WorkstationSession[],current:Selection):ProjectSession[] {
-  const records=sessions.map(session=>({...session,selection:normalizeSelection(session.selection)}));
-  if(hasWorkspaceSelection(current)&&!records.some(session=>sessionKey(session.selection)===sessionKey(current)))
-    records.push({selection:current,name:memberName(current)});
-  const groups=new Map<string,ProjectSession>();
-  const latest=new Map<string,number>();
-  for(const [index,session] of records.entries()){
-    const selection=session.selection;
-    if(!hasWorkspaceSelection(selection))continue;
-    const key=projectSessionKey(selection,records);
-    const locator=key.startsWith('locator:')?key.slice('locator:'.length):'';
-    const scope=locator||selection.projectId||`Unbound observations — no project binding${selection.corpusIdentity?` · corpus ${selection.corpusIdentity}`:''}`;
+/** IDs are context-scoped; only an unambiguous same-corpus association joins tabs. */
+export function projectSessionKey(selection:Selection,sessions:WorkstationSession[]):string {
+  selection=normalizeSelection(selection);
+  const locator=canonicalProjectLocator(selection.locator);
+  if(locator)return `locator:${locator}`;
+  if(selection.projectId){
+    const corpusIdentity=selection.corpusIdentity||'';
+    const locators=new Set(sessions.map(session=>normalizeSelection(session.selection))
+      .filter(saved=>saved.projectId===selection.projectId&&(saved.corpusIdentity||'')===corpusIdentity)
+      .map(saved=>canonicalProjectLocator(saved.locator)).filter(Boolean));
+    if(locators.size===1)return `locator:${[...locators][0]}`;
+    return `project:${JSON.stringify([corpusIdentity,selection.projectId])}`;
+  }
+  // Unbound observations share a clearly labeled workspace, not an invented project.
+  return `corpus:${selection.corpusIdentity||'unbound'}`;
+}
+
+function memberName(selection:Selection):string {
+  return selection.program||selection.slug||selection.binaryHash?.slice(0,12)||'Project overview';
+}
+
+/** Project tabs are a projection; retain concrete saved sessions and their contexts. */
+export function groupProjectSessions(sessions:WorkstationSession[],current:Selection):ProjectSession[] {
+  const records=sessions.map(session=>({...session,selection:normalizeSelection(session.selection)}));
+  if(hasWorkspaceSelection(current)&&!records.some(session=>sessionKey(session.selection)===sessionKey(current)))
+    records.push({selection:current,name:memberName(current)});
+  const groups=new Map<string,ProjectSession>();
+  const latest=new Map<string,number>();
+  for(const [index,session] of records.entries()){
+    const selection=session.selection;
+    if(!hasWorkspaceSelection(selection))continue;
+    const key=projectSessionKey(selection,records);
+    const locator=key.startsWith('locator:')?key.slice('locator:'.length):'';
+    const scope=locator||`${selection.projectId||'Unbound observations — no project binding'}${selection.corpusIdentity?` · corpus ${selection.corpusIdentity}`:''}`;
     const name=locator?locator.split('/').pop()||locator:selection.projectId==='local:workbench'?'Local workspace':selection.projectId||'Unbound observations';
     let group=groups.get(key);
     if(!group){group={key,name,scope,selection,members:[]};groups.set(key,group);}
```


## Continuation slice 2 — project tabs and build focus

Status: implemented in source only; supersedes the initial report's missing visible project-tab projection. Full project-member inventory and workspace destination consolidation remain outstanding.

### Brief and design-system scope

Replace the existing per-binary tab strip with project tabs while preserving every saved concrete session, its address, and its evidence context. Reuse the current compact workstation strip, typography, border/accent tokens and close icon. This is a bounded navigation fix within the existing design system; no new shell, concept image, assets or runtime activation. The RzWeb reference's one-binary-per-worker tab model is deliberately not adopted because the user requires project tabs.

Files changed in this continuation:
- frontend/src/workstation/WorkstationApp.tsx: targeted session projection, project menu/manager and tab-strip wiring.
- frontend/src/workstation/projectSessions.ts: new pure projection of existing saved sessions into project groups.
- frontend/src/workstation/ProjectTabs.tsx: project selection and explicit inspected-build drill-in.
- frontend/src/workstation/project-tabs.css: isolated responsive styles.
- This report.

### Resulting behavior

- Project tabs group by the existing canonicalProjectLocator normalizer. Changing a program, slug, address or artifact hash does not create another tab for that locator.
- An ID-only saved session joins a locator only when the records explicitly associate that project ID with exactly one locator. Ambiguous ID-to-locator associations remain separate; no filename-based project inference.
- Local artifacts with the existing local:workbench ID share Local workspace. Observations with no project binding share a clearly labeled Unbound observations workspace per corpus identity; this label does not claim a native project or write target.
- The existing binary-level workstation.sessions records and sessionKey remain. Project grouping is a presentation projection, not a destructive migration. An optional lastFocusedAt field records the most recently viewed concrete context for returning to a project; older records use their existing order.
- Project-only selections now persist even before a program exists. The tab strip's Open project action opens the existing project dialog.
- Each project exposes a native select labeled Inspected build with previously inspected concrete members. It does not imply that this list is the complete server-project inventory.
- Selecting a project restores its full saved Selection directly; selecting an inspected build changes that concrete focus. The existing AnalysisView key remains binary-level so a project grouping cannot reuse a different binary's analysis component identity.
- Project menu and manager now list the same grouped workspaces. Closing a workspace tab removes its saved view records, as closing binary tabs previously did; stored artifacts, drafts, backend project contents and native jobs are untouched by this handler. Existing reopen/history routes can restore a workspace.
- The group-key lookup used during closing includes the current selection, preventing an ID-only view from surviving a just-opened explicit ID/locator association before persistence completes.

The ProjectTabs surface uses ordinary keyboard-accessible buttons and a native select. Full scope paths are available as text/tooltips. Mobile wraps the scope line and retains the existing 44px controls. No new motion or fake progress is introduced.

### Checks and boundaries

Exact checks run: inline TypeScript createSourceFile syntax parsing of WorkstationApp.tsx, projectSessions.ts and ProjectTabs.tsx returned zero syntax diagnostics for all three, with no emit; git diff --check for WorkstationApp.tsx passed; read-only rg confirmed AnalysisView still uses the original currentKey and all tab/menu close callbacks use closeProject. These are source checks only, not behavior tests, typecheck, build or browser acceptance.

No filesystem tests, test suites, builds, dependency installs, browser calls, 5174/server starts, deployment, backend/static edits, job/approval changes, recovery actions or restarts occurred in this continuation. The earlier packaged-route observation is not evidence for this source.

Remaining gaps: complete project member tree from authoritative bindings; multi-project logical comparison scope; Compare/Recover/Work destination consolidation; source/object/build receipt path navigation; directed relationship and capability evidence views; real event-to-diff activity presentation; current-source responsive/browser verification when authorized. Project grouping does not itself implement import ownership, Save/Check-in capture, or native serialization; existing contracts are unchanged.

Independent-review focus: project locator/ID ambiguity; preserving concrete selection keys; active-tab closing; legacy session projection; empty project opens; no accidental job mutation; clearly limited inspected-member list.

### Actual incremental slice-2 diff

WorkstationApp was already dirty before this task. Its diff below was calculated in memory from exact pre-slice and post-slice source, excluding prior user edits. New files are /dev/null additions. No temporary test or patch file was created.

```diff
--- a/frontend/src/workstation/WorkstationApp.tsx (before slice 2)
+++ b/frontend/src/workstation/WorkstationApp.tsx (after slice 2)
@@ -1,5 +1,5 @@
 import {DependencyGraph} from '../DependencyGraph';
+import {useCallback,useEffect,useMemo,useRef,useState,type CSSProperties,type KeyboardEvent} from 'react';
-import {useCallback,useEffect,useRef,useState,type CSSProperties,type KeyboardEvent} from 'react';
 import {API,emptySelection,normalizeSelection,query,request,type ActionRequest,type Data,type Notify,type Selection} from '../contracts';
 import {useData,usePref,readPref,savePref,ResizeBar,ErrorLine,RecordView} from '../ui';
 import {ActionRunner,Commands,DialogFrame} from '../Actions';
@@ -17,6 +17,8 @@
 import {useEntityActivity} from '../activity';
 import {ScopedClaims,selectClaimProjection} from '../ScopedClaims';
 import {ProjectSnapshots} from './ProjectSnapshots';
+import {ProjectTabs} from './ProjectTabs';
+import {groupProjectSessions,hasWorkspaceSelection,projectSessionKey,type WorkstationSession} from './projectSessions';
 import {MenuBar, type MenuGroup} from './MenuBar';
 import {RetainedPanel} from './RetainedPanel';
 import {AnalysisView} from './AnalysisView';
@@ -25,7 +27,6 @@
 import {canPrepareAnalysis,shellShortcut,addressOf,analysisTabs,extraTabs,readRoute,routeUrl,sessionKey,mergeSelection,memberSelection,type AnalysisTab,type Route} from './navigation';
 import './workstation.css';
 
-type Session={selection:Selection;name:string};
 const initialRoute=():Route=>readRoute(location.search,readPref('workstation.route',{selection:emptySelection,tab:'Logical'} as Route));
 function Icon({name}:{name:'folder'|'file'|'search'|'command'|'menu'|'close'|'reload'|'share'}) {
   const paths={folder:'M3 7V5h6l2 2h10v13H3Z',file:'M6 3h8l4 4v14H6Z M14 3v5h4',search:'M20 20l-5-5 M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0',command:'m4 6 6 6-6 6 M13 18h7',menu:'M4 6h16 M4 12h16 M4 18h16',close:'m6 6 12 12 M18 6 6 18',reload:'M20 7v5h-5 M20 12a8 8 0 1 0-2 6',share:'M8 12l8-6 M8 12l8 6 M5 9h3v6H5Z M16 3h3v6h-3Z M16 15h3v6h-3Z'};
@@ -76,8 +77,11 @@
   return <details className={`ws-job-record ${scope}`} open={open} onToggle={event=>setOpen((event.currentTarget as HTMLDetailsElement).open)}><summary><span className="ws-job-summary"><strong>{record.status} · {jobTitle(record)}</strong><small>{record.id} · {scope==='live'?'live across workspace':scope==='current'?'selected project':'recorded history'}</small></span><span className="ws-job-path"><b>Target</b><code title={target}>{target}</code></span>{workdir&&<span className="ws-job-path"><b>Workdir</b><code title={workdir}>{workdir}</code></span>}{progress?<span className="ws-job-progress"><progress value={progress.completed} max={progress.total}/><small>{progress.label}</small></span>:activeJob(record)&&<span className="ws-job-progress"><progress/><small>Working · reading measured stage progress</small></span>}{logSummary&&<span className="ws-job-log-summary">{logSummary}</span>}</summary>{detail.loading?<p role="status">Reading current job output…</p>:detail.error?<p className="ws-job-refresh" role="status">Refreshing recorded job receipt.<details><summary>Connection details</summary>{detail.error}</details></p>:<pre>{record.log||record.error||'No log output yet.'}</pre>}<button onClick={()=>onAction(record.actionId||record.action,record.params,record.context?[normalizeSelection(record.context)]:undefined)}>Review rerun…</button></details>;
 }
 export function WorkstationApp(){
+  const [route,setRoute]=useState(initialRoute),[sessions,setSessions]=usePref<WorkstationSession[]>('workstation.sessions',[]);
-  const [route,setRoute]=useState(initialRoute),[sessions,setSessions]=usePref<Session[]>('workstation.sessions',[]);
   const {selection,tab}=route;
+  const projects=useMemo(()=>groupProjectSessions(sessions,selection),[sessions,selection]);
+  const projectScopeSessions=useMemo(()=>[...sessions,{selection,name:''}],[sessions,selection]);
+  const currentProjectKey=projectSessionKey(selection,projectScopeSessions);
   const [revision,setRevision]=useState(0),[dialog,setDialog]=useState<'open'|'commands'|'project'|null>(null),[projectDialog,setProjectDialog]=useState<'open'|'import'|'create'|null>(null),[contributionOpen,setContributionOpen]=useState(false);
   const [navOpen,setNavOpen]=usePref('workstation.nav',true),[evidenceOpen,setEvidenceOpen]=usePref('workstation.evidence',true),[mobilePane,setMobilePane]=useState<'functions'|'evidence'|null>(null);
   const [navWidth,setNavWidth]=usePref('workstation.navWidth',240),[evidenceWidth,setEvidenceWidth]=usePref('workstation.evidenceWidth',260),[dockHeight,setDockHeight]=usePref('workstation.dockHeight',170),[dockOpen,setDockOpen]=usePref('workstation.dockOpen',true);
@@ -121,7 +125,7 @@
   const onAction=useCallback((id:string,params?:Data,targets?:Selection[])=>{if(corpusBlocked){notify('The selected corpus identity is unavailable or changed. Select an identity from the current corpus before acting.','warning');return;}setDialog(null);setAction({id,params,targets:targets||[{...selection}]});},[selection,corpusBlocked,notify]);
   const props={selection,onSelect:select,onAction,notify,revision};
   useEffect(()=>{const handle=()=>{jumpSequence.current++;setRoute(readRoute(location.search,{selection:emptySelection,tab:'Disassembly'}));setMobilePane(null);};addEventListener('popstate',handle);return()=>{jumpSequence.current++;removeEventListener('popstate',handle);};},[]);
+  useEffect(()=>{savePref('workstation.route',route);if(hasWorkspaceSelection(selection)){setSessions(old=>{const key=sessionKey(selection),existing=old.find(s=>sessionKey(s.selection)===key);const next={selection,name:existing?.name||selection.program.split('/').pop()||selection.slug||localModel?.artifacts.find(a=>a.hash===selection.binaryHash)?.name||selection.binaryHash?.slice(0,12)||'Project overview',lastFocusedAt:Date.now()};return existing?old.map(s=>sessionKey(s.selection)===key?next:s):[...old,next];});}},[route,localModel,setSessions]);
-  useEffect(()=>{savePref('workstation.route',route);if(selection.slug||selection.program||selection.binaryHash){setSessions(old=>{const key=sessionKey(selection),existing=old.find(s=>sessionKey(s.selection)===key);const next={selection,name:existing?.name||selection.program.split('/').pop()||selection.slug||localModel?.artifacts.find(a=>a.hash===selection.binaryHash)?.name||selection.binaryHash?.slice(0,12)||'Binary'};return existing?old.map(s=>sessionKey(s.selection)===key?next:s):[...old,next];});}},[route,localModel,setSessions]);
   useEffect(()=>{setOffset(0);setFilter('');setFunctionQuery('');setEvidence({});},[selection.slug,selection.program,selection.locator,selection.binaryHash]);
   useEffect(()=>{setAddress(selection.addr);setEvidence({});},[selection.addr,selection.logicalId,selection.functionId]);
   useEffect(()=>{const timer=setTimeout(()=>{setFunctionQuery(filter);setOffset(0);},250);return()=>clearTimeout(timer);},[filter]);
@@ -185,7 +189,7 @@
     catch(e){if(sequence===jumpSequence.current)notify(String(e),'error');}
   }
   const currentKey=sessionKey(selection);
+  function closeProject(key:string){const remaining=sessions.filter(s=>projectSessionKey(s.selection,projectScopeSessions)!==key);setSessions(remaining);if(key===currentProjectKey){const next=groupProjectSessions(remaining,emptySelection).at(-1)?.selection||emptySelection;navigate({selection:normalizeSelection(next),tab});}}
-  function closeSession(key:string){const remaining=sessions.filter(s=>sessionKey(s.selection)!==key);setSessions(remaining);if(key===currentKey)navigate({selection:mergeSelection(selection,remaining.at(-1)?.selection||emptySelection),tab});}
   const selectedFunction=functionRows.find(r=>addressOf(r)===selection.addr);
   const startScratch=()=>{setScratchCreating(true);setCreateNonce(n=>n+1);chooseTab('Matching');setMobilePane(null);};
   const openFunctions=()=>{setNavOpen(true);setMobilePane('functions');setDialog(null);setTimeout(()=>searchRef.current?.focus(),0);};
@@ -214,12 +218,12 @@
       {label:`${effectiveDockOpen?'Hide':'Show'} Activity`,run:()=>setVisibleDockOpen(!effectiveDockOpen)},
     ]},
     {label:'Project',actions:[
+      ...projects.map(project=>({label:project.name,hint:project.scope,selected:project.key===currentProjectKey,run:()=>navigate({selection:project.selection,tab})})),
+      ...(!projects.length?[{label:'No projects open',disabled:true,run:()=>{}}]:[]),
-      ...sessions.map(session=>({label:session.name||'Binary',hint:sessionKey(session.selection)===currentKey?'Current analysis target':'Switch to this binary',selected:sessionKey(session.selection)===currentKey,run:()=>navigate({selection:mergeSelection(selection,session.selection),tab})})),
-      ...(!sessions.length?[{label:'No binaries open',disabled:true,run:()=>{}}]:[]),
       {label:'Project manager…',run:()=>setDialog('project')},
       {label:'Open Ghidra project…',run:()=>setProjectDialog('open')},
       {label:'Import binaries or project…',run:()=>setProjectDialog('import')},
+      {label:'Close current workspace tab',disabled:!projects.length,run:()=>closeProject(currentProjectKey)},
-      {label:'Close current binary',disabled:!sessions.length,run:()=>closeSession(currentKey)},
     ]},
     {label:'Tools',actions:[
       {label:'Commands…',hint:'Search available actions',shortcut:'Ctrl+K',run:()=>setDialog('commands')},
@@ -243,7 +247,7 @@
   return <div className="workstation" style={css}>
     <header className="ws-header"><button className="ws-mobile-menu" aria-label="Toggle Functions" aria-expanded={mobilePane==='functions'} onClick={()=>setMobilePane(mobilePane==='functions'?null:'functions')}><Icon name="menu"/></button><strong className="ws-brand">AgentDecompile</strong><a className="ws-cockpit-link" href="#cockpit" title="Program map, products and live lanes">Cockpit</a><button className="ws-open-binary" onClick={()=>setDialog('open')}><Icon name="folder"/>Open binary</button><button className="ws-new-scratch" onClick={startScratch}><Icon name="file"/>New scratch</button><button className="ws-search-button" onClick={openFunctions}><Icon name="search"/>Search functions… <kbd>Ctrl P</kbd></button><button className="ws-commands" onClick={()=>setDialog('commands')}><Icon name="command"/><span>Commands</span><kbd>Ctrl K</kbd></button></header>
     <MenuBar groups={menuGroups}/>
+    <ProjectTabs projects={projects} currentKey={currentProjectKey} selection={selection} onSelect={next=>navigate({selection:next,tab})} onClose={closeProject} onOpen={()=>setProjectDialog('open')} onManage={()=>setDialog('project')}/>
-    <div className="ws-sessions" aria-label="Binary sessions">{sessions.map(session=>{const key=sessionKey(session.selection);return <div key={key} className={key===currentKey?'active':''}><button aria-pressed={key===currentKey} onClick={()=>navigate({selection:mergeSelection(selection,session.selection),tab})}><Icon name="file"/>{session.name}</button><button aria-label={`Close ${session.name}`} onClick={()=>closeSession(key)}><Icon name="close"/></button></div>;})}{!sessions.length&&<span>No binary open</span>}<button onClick={()=>setDialog('project')}>Project manager…</button><button aria-label="Open another binary" title="Open another binary" onClick={()=>setDialog('open')}>+</button></div>
     <nav className="ws-analysis-tabs" aria-label="Analysis views"><div role="tablist" aria-label="Analysis" onKeyDown={tabKeys}>{analysisTabs.map(name=><button key={name} id={`tab-${name}`} role="tab" aria-selected={tab===name} aria-controls="analysis-panel" tabIndex={tab===name||(extraTabs.includes(tab)&&name==='Disassembly')?0:-1} onClick={()=>chooseTab(name)}>{name}</button>)}</div><label className="ws-more"><span>More</span><select aria-label="Additional analysis tools" value={extraTabs.includes(tab)?tab:''} onChange={e=>{if(e.target.value)chooseTab(e.target.value as AnalysisTab);}}><option value="">Tools…</option>{extraTabs.map(name=><option key={name}>{name}</option>)}</select></label></nav>
     <div className="ws-navigation"><button title="Back through selections" onClick={()=>history.back()}>← <span>Back</span></button><button title="Forward through selections" onClick={()=>history.forward()}>→</button>{selection.lastFunctionAddr&&selection.lastFunctionAddr!==selection.addr&&<button onClick={()=>select({addr:selection.lastFunctionAddr,logicalId:''})}>Last function</button>}<form onSubmit={e=>{e.preventDefault();void jumpAddress();}}><label className="sr-only" htmlFor="ws-address">{local?'Hex file offset':'Address or function name'}</label><input id="ws-address" value={address} onChange={e=>setAddress(e.target.value)} placeholder={local?'File offset (hex)':'Address or function name'}/><button>Go</button></form><button aria-label="Reload current evidence" onClick={refresh}><Icon name="reload"/></button><button aria-label="Copy share URL" onClick={()=>{const url=new URL(routeUrl(location.href,route),location.href).href;void navigator.clipboard.writeText(url).then(()=>notify(local?'Local link copied; the recipient needs this artifact in their browser.':'Selection link copied')).catch(()=>notify(`Copy this selection link: ${url}`,'warning'));}}><Icon name="share"/></button><button className="ws-desktop-toggle" aria-pressed={navOpen} onClick={()=>setNavOpen(!navOpen)}>Functions</button><button className="ws-desktop-toggle" aria-pressed={evidenceOpen} onClick={()=>setEvidenceOpen(!evidenceOpen)}>Evidence</button></div>
     <div className={`ws-workspace ${mobilePane?'has-mobile-pane':''}`}>
@@ -281,7 +285,7 @@
       <div className="ws-project-manager">
         <section className="ws-project-current"><p className="muted">Current analysis target</p><h3>{selectedFunction?.name||selection.program||selection.slug||'No binary selected'}</h3><dl><dt>Program</dt><dd>{selection.program||selection.slug||'Not selected'}</dd><dt>Project</dt><dd><code>{selection.locator||selection.projectId||'Not bound to a server project'}</code></dd>{selection.binaryHash&&<><dt>SHA-256</dt><dd><code>{selection.binaryHash}</code></dd></>}</dl><p>Switching a binary changes the concrete view; saved evidence and background jobs remain scoped to their recorded target.</p></section>
         <section><h3>Open or add</h3><div className="ws-project-actions"><button onClick={()=>{setDialog('open');}}>Open binary…</button><button onClick={()=>{setDialog(null);setProjectDialog('open');}}>Open Ghidra project…</button><button onClick={()=>{setDialog(null);setProjectDialog('import');}}>Import binaries or project…</button><button onClick={()=>{setDialog(null);setProjectDialog('create');}}>Create Ghidra project…</button></div></section>
+        <section><h3>Open project workspaces</h3>{projects.length?projects.map(project=>{const selected=project.key===currentProjectKey;return <div className="ws-project-session" key={project.key}><button className="ws-project-session-open" aria-current={selected?'true':undefined} onClick={()=>{navigate({selection:project.selection,tab});setDialog(null);}}><strong>{project.name}</strong><small>{project.scope} · {project.members.length} inspected builds</small></button><button aria-label={`Close workspace tab ${project.name}`} onClick={()=>closeProject(project.key)}>Close tab</button></div>;}):<p>No project workspace is open. Open a project or inspect a recorded or local binary.</p>}</section>
-        <section><h3>Open binaries in this workspace</h3>{sessions.length?sessions.map(session=>{const key=sessionKey(session.selection);const selected=key===currentKey;return <div className="ws-project-session" key={key}><button className="ws-project-session-open" aria-current={selected?'true':undefined} onClick={()=>{navigate({selection:mergeSelection(selection,session.selection),tab});setDialog(null);}}><strong>{session.name||'Binary'}</strong><small>{selected?'Current target':session.selection.program||session.selection.slug||session.selection.binaryHash||'Local binary'}</small></button><button aria-label={`Close ${session.name||'binary'}`} onClick={()=>closeSession(key)}>Close</button></div>;}):<p>No binaries are open. Use Open binary to choose a recorded or local file.</p>}</section>
         <section><h3>Source and local revisions</h3>{selection.slug||selection.program?<SourceDownload selection={selection} notify={notify}/>:<p>Open a recorded binary to export its available source.</p>}<ProjectSnapshots projectId={selection.projectId||'local:workbench'} revision={revision} notify={notify} onOpen={snapshot=>{savePref('workstation.snapshot',{projectId:snapshot.projectId,revision:snapshot.revision});runtime.current.index.replace(snapshot.model);setLocalModel(snapshot.model);const artifact=snapshot.model.artifacts.find(a=>a.hash===snapshot.model.artifactHash)||snapshot.model.artifacts[0];if(artifact)openLocal(artifact.hash,artifact.name);else{navigate({selection:{...emptySelection,projectId:snapshot.projectId},tab:'Info'});setDialog(null);}}}/></section>
       </div>
     </DialogFrame>}
diff --git a/src/agentdecompile_recovery/corpus/dashboard/frontend/src/workstation/projectSessions.ts b/src/agentdecompile_recovery/corpus/dashboard/frontend/src/workstation/projectSessions.ts
new file mode 100644
index 00000000..dc5dba20
--- /dev/null
+++ b/src/agentdecompile_recovery/corpus/dashboard/frontend/src/workstation/projectSessions.ts
@@ -0,0 +1,63 @@
+import {normalizeSelection,type Selection} from '../contracts';
+import {canonicalProjectLocator} from '../projectLocator';
+import {sessionKey} from './navigation';
+
+export type WorkstationSession={selection:Selection;name:string;lastFocusedAt?:number};
+export type ProjectSession={key:string;name:string;scope:string;selection:Selection;members:WorkstationSession[]};
+
+export function hasWorkspaceSelection(selection:Selection):boolean {
+  return Boolean(selection.locator||selection.projectId||selection.slug||selection.program||selection.binaryHash||selection.logicalId);
+}
+
+/** Only an explicit, unambiguous ID/locator association may join saved tabs. */
+export function projectSessionKey(selection:Selection,sessions:WorkstationSession[]):string {
+  selection=normalizeSelection(selection);
+  const locator=canonicalProjectLocator(selection.locator);
+  if(locator)return `locator:${locator}`;
+  if(selection.projectId){
+    const locators=new Set(sessions.filter(session=>session.selection.projectId===selection.projectId)
+      .map(session=>canonicalProjectLocator(session.selection.locator)).filter(Boolean));
+    if(locators.size===1)return `locator:${[...locators][0]}`;
+    return `project:${selection.projectId}`;
+  }
+  // Unbound observations share a clearly labeled workspace, not an invented project.
+  return `corpus:${selection.corpusIdentity||'unbound'}`;
+}
+
+function memberName(selection:Selection):string {
+  return selection.program||selection.slug||selection.binaryHash?.slice(0,12)||'Project overview';
+}
+
+/** Project tabs are a projection; retain concrete saved sessions and their contexts. */
+export function groupProjectSessions(sessions:WorkstationSession[],current:Selection):ProjectSession[] {
+  const records=sessions.map(session=>({...session,selection:normalizeSelection(session.selection)}));
+  if(hasWorkspaceSelection(current)&&!records.some(session=>sessionKey(session.selection)===sessionKey(current)))
+    records.push({selection:current,name:memberName(current)});
+  const groups=new Map<string,ProjectSession>();
+  const latest=new Map<string,number>();
+  for(const [index,session] of records.entries()){
+    const selection=session.selection;
+    if(!hasWorkspaceSelection(selection))continue;
+    const key=projectSessionKey(selection,records);
+    const locator=key.startsWith('locator:')?key.slice('locator:'.length):'';
+    const scope=locator||selection.projectId||`Unbound observations — no project binding${selection.corpusIdentity?` · corpus ${selection.corpusIdentity}`:''}`;
+    const name=locator?locator.split('/').pop()||locator:selection.projectId==='local:workbench'?'Local workspace':selection.projectId||'Unbound observations';
+    let group=groups.get(key);
+    if(!group){group={key,name,scope,selection,members:[]};groups.set(key,group);}
+    const recency=Number.isFinite(session.lastFocusedAt)?session.lastFocusedAt!:index;
+    if(recency>=(latest.get(key)??-1)){group.selection=selection;latest.set(key,recency);}
+    if(selection.slug||selection.program||selection.binaryHash){
+      const member={...session,name:session.name||memberName(selection)};
+      const existing=group.members.findIndex(value=>sessionKey(value.selection)===sessionKey(selection));
+      if(existing<0)group.members.push(member);else group.members[existing]=member;
+    }
+  }
+  if(hasWorkspaceSelection(current)){
+    const active=groups.get(projectSessionKey(current,records));
+    if(active){
+      active.selection=current;
+      active.members=active.members.map(member=>sessionKey(member.selection)===sessionKey(current)?{...member,selection:current}:member);
+    }
+  }
+  return [...groups.values()];
+}
diff --git a/src/agentdecompile_recovery/corpus/dashboard/frontend/src/workstation/ProjectTabs.tsx b/src/agentdecompile_recovery/corpus/dashboard/frontend/src/workstation/ProjectTabs.tsx
new file mode 100644
index 00000000..04966d72
--- /dev/null
+++ b/src/agentdecompile_recovery/corpus/dashboard/frontend/src/workstation/ProjectTabs.tsx
@@ -0,0 +1,31 @@
+import type {Selection} from '../contracts';
+import {sessionKey} from './navigation';
+import type {ProjectSession} from './projectSessions';
+import './project-tabs.css';
+
+export function ProjectTabs({projects,currentKey,selection,onSelect,onClose,onOpen,onManage}:{
+  projects:ProjectSession[];currentKey:string;selection:Selection;
+  onSelect:(selection:Selection)=>void;onClose:(key:string)=>void;onOpen:()=>void;onManage:()=>void;
+}){
+  const current=projects.find(project=>project.key===currentKey);
+  const selectedMember=current?.members.find(member=>sessionKey(member.selection)===sessionKey(selection));
+  return <section className="ws-project-tabs" aria-label="Project workspace">
+    <nav className="ws-sessions" aria-label="Open projects">
+      {projects.map(project=><div key={project.key} className={project.key===currentKey?'active':''}>
+        <button type="button" aria-current={project.key===currentKey?'page':undefined} aria-pressed={project.key===currentKey} title={project.scope} onClick={()=>onSelect(project.selection)}>{project.name}</button>
+        <button type="button" aria-label={`Close workspace tab ${project.name}`} title="Close this tab; recorded work remains available" onClick={()=>onClose(project.key)}><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><path d="m6 6 12 12 M18 6 6 18"/></svg></button>
+      </div>)}
+      {!projects.length&&<span>No project open</span>}
+      <button type="button" onClick={onOpen}>Open project…</button>
+      <button type="button" onClick={onManage}>Project manager…</button>
+    </nav>
+    {current&&<div className="ws-project-focus">
+      <span className="ws-project-scope" title={current.scope}>{current.scope}</span>
+      <label>Inspected build <select aria-label="Inspected build in this project" value={selectedMember?sessionKey(selectedMember.selection):''} onChange={event=>{const member=current.members.find(value=>sessionKey(value.selection)===event.target.value);if(member)onSelect(member.selection);}}>
+        <option value="" disabled>{current.members.length?'Project overview':'No build inspected'}</option>
+        {current.members.map(member=><option key={sessionKey(member.selection)} value={sessionKey(member.selection)}>{member.name}{member.selection.program&&member.name!==member.selection.program?` · ${member.selection.program}`:''}</option>)}
+      </select></label>
+      <small>Previously inspected builds</small>
+    </div>}
+  </section>;
+}
diff --git a/src/agentdecompile_recovery/corpus/dashboard/frontend/src/workstation/project-tabs.css b/src/agentdecompile_recovery/corpus/dashboard/frontend/src/workstation/project-tabs.css
new file mode 100644
index 00000000..e468fa28
--- /dev/null
+++ b/src/agentdecompile_recovery/corpus/dashboard/frontend/src/workstation/project-tabs.css
@@ -0,0 +1,8 @@
+.ws-project-tabs{flex:none;min-width:0}
+.ws-project-tabs .ws-sessions button{font-size:12px}
+.ws-project-focus{display:flex;align-items:center;gap:10px;padding:5px 10px;border-bottom:1px solid var(--border);background:var(--bg)}
+.ws-project-scope{flex:1;min-width:0;color:var(--muted);font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
+.ws-project-focus label{display:flex;align-items:center;gap:7px;min-width:0;font-size:12px}
+.ws-project-focus select{max-width:min(35vw,420px);font-size:12px}
+.ws-project-focus small{font-size:10px}
+@media(max-width:700px){.ws-project-focus{flex-wrap:wrap;gap:5px}.ws-project-scope{flex-basis:100%}.ws-project-focus label{flex:1}.ws-project-focus select{flex:1;max-width:100%;min-width:0}.ws-project-focus small{display:none}.ws-project-tabs .ws-sessions button{min-height:44px}}
```


## Independent review fix round 1

Important finding: the locally inspected address could outlive replacement/removal of its aligned instruction or mismatch evidence during the five-second refresh. The stale navigation button could remain while the diff highlight reset.

Fix: memoize mismatch records with the current detail, and revalidate the selected inspection address against the current aligned target addresses and mismatch addresses on every render. Render the navigation affordance only for that current valid address, so there is no stale render before effects. An effect clears invalidated local state so a later receipt cannot resurrect the old selection. An address still present in current evidence remains inspectable; an unavailable/removed address loses the affordance. The existing function selection key and explicit navigation semantics remain unchanged.

Source checks: inline TypeScript parser returned zero syntax diagnostics, no emit. No browser, backend, static changes, builds, tests, native actions or restarts were performed during this fix round. Runtime behavior remains unverified.

Actual incremental fix diff below was calculated in memory from the source captured immediately before and after the fix (not the cumulative initial implementation diff).

```diff
--- a/frontend/src/workstation/CompareView.tsx (before fix round 1)
+++ b/frontend/src/workstation/CompareView.tsx (after fix round 1)
@@ -10,30 +10,35 @@
 /** Compare tab body. Reads the same recorded proof fields as the matching surface. */
 export function ComparePanel({detail,loading,error,hasFunction,onSelect,selection}:{detail:Data;loading:boolean;error:string;hasFunction:boolean;onSelect:(patch:Partial<Selection>)=>void;selection?:Selection}) {
   const rows = useMemo(() => instructionDiffRows(detail), [detail]);
-  const [inspectedAddress,setInspectedAddress]=useState('');
-  const [showSource,setShowSource]=useState(true);
-  const source=sourceWitness(detail);
-  const sourcePath=typeof detail.sourcePath==='string'?detail.sourcePath:'';
-  const hasEvidence=Object.keys(detail).length>0;
-  if(!hasFunction)return <div className="ws-document"><p role="status">Select a function to see its recorded byte diff.</p></div>;
-  return <div className="ws-document compare-document">
-    <header className="compare-context">
-      <div><strong>{detail.name||detail.function?.name||selection?.addr||'Selected function'}</strong><small>{selection?.program||selection?.slug||'Recorded target'}{selection?.addr?` · ${selection.addr}`:''}</small></div>
-      {selection&&<button type="button" aria-pressed={showSource} onClick={()=>setShowSource(value=>!value)}>{showSource?'Hide recorded source':'Show recorded source'}</button>}
-    </header>
-    <ErrorLine error={error}/>
-    {loading&&<p role="status">{hasEvidence?'Refreshing recorded evidence…':'Reading recorded evidence…'}</p>}
-    {hasEvidence&&<div className={`compare-evidence-panes${showSource&&selection?' with-source':''}`}>
-      {showSource&&selection&&<section className="compare-source" aria-label="Recorded source for selected function">
-        <h3>Recorded source</h3>
-        <p className="muted">Function observation. A candidate-bound receipt is needed to link this source to compiled output.</p>
-        {sourcePath&&<code className="compare-source-path">{sourcePath}</code>}
-        <SourceEditor selection={selection} value={source} sourcePath={sourcePath} extent={sourceExtent(detail)} allowDraft={false}/>
-      </section>}
-      <section className="compare-diff" aria-label="Recorded comparison for selected function">
-        <InstructionDiff rows={rows} verified={matchingPhase('',detail,false)==='objdiff-verified'} onNavigate={setInspectedAddress}/>
-        {inspectedAddress&&<div className="compare-location"><span>Inspected target address <code>{inspectedAddress}</code></span><button type="button" onClick={()=>onSelect({addr:inspectedAddress,lastFunctionAddr:selection?.lastFunctionAddr||selection?.addr||''})}>Navigate to address</button></div>}
-        <DiffEvidence mismatches={diffMismatches(detail)} receipts={diffReceipts(detail)} onNavigate={mismatch=>{if(mismatch.address)setInspectedAddress(mismatch.address);}}/>
+  const mismatches = useMemo(() => diffMismatches(detail), [detail]);
+  const [inspectedAddress,setInspectedAddress]=useState('');
+  // Revalidate against the current receipt during render, before effects run.
+  // Clearing removed addresses also prevents their resurrection on a later poll.
+  const currentInspectedAddress=rows.some(row=>row.address===inspectedAddress)||mismatches.some(mismatch=>mismatch.address===inspectedAddress)?inspectedAddress:'';
+  useEffect(()=>{if(inspectedAddress&&!currentInspectedAddress)setInspectedAddress('');},[inspectedAddress,currentInspectedAddress]);
+  const [showSource,setShowSource]=useState(true);
+  const source=sourceWitness(detail);
+  const sourcePath=typeof detail.sourcePath==='string'?detail.sourcePath:'';
+  const hasEvidence=Object.keys(detail).length>0;
+  if(!hasFunction)return <div className="ws-document"><p role="status">Select a function to see its recorded byte diff.</p></div>;
+  return <div className="ws-document compare-document">
+    <header className="compare-context">
+      <div><strong>{detail.name||detail.function?.name||selection?.addr||'Selected function'}</strong><small>{selection?.program||selection?.slug||'Recorded target'}{selection?.addr?` · ${selection.addr}`:''}</small></div>
+      {selection&&<button type="button" aria-pressed={showSource} onClick={()=>setShowSource(value=>!value)}>{showSource?'Hide recorded source':'Show recorded source'}</button>}
+    </header>
+    <ErrorLine error={error}/>
+    {loading&&<p role="status">{hasEvidence?'Refreshing recorded evidence…':'Reading recorded evidence…'}</p>}
+    {hasEvidence&&<div className={`compare-evidence-panes${showSource&&selection?' with-source':''}`}>
+      {showSource&&selection&&<section className="compare-source" aria-label="Recorded source for selected function">
+        <h3>Recorded source</h3>
+        <p className="muted">Function observation. A candidate-bound receipt is needed to link this source to compiled output.</p>
+        {sourcePath&&<code className="compare-source-path">{sourcePath}</code>}
+        <SourceEditor selection={selection} value={source} sourcePath={sourcePath} extent={sourceExtent(detail)} allowDraft={false}/>
+      </section>}
+      <section className="compare-diff" aria-label="Recorded comparison for selected function">
+        <InstructionDiff rows={rows} verified={matchingPhase('',detail,false)==='objdiff-verified'} onNavigate={setInspectedAddress}/>
+        {currentInspectedAddress&&<div className="compare-location"><span>Inspected target address <code>{currentInspectedAddress}</code></span><button type="button" onClick={()=>onSelect({addr:currentInspectedAddress,lastFunctionAddr:selection?.lastFunctionAddr||selection?.addr||''})}>Navigate to address</button></div>}
+        <DiffEvidence mismatches={mismatches} receipts={diffReceipts(detail)} onNavigate={mismatch=>{if(mismatch.address)setInspectedAddress(mismatch.address);}}/>
       </section>
     </div>}
     {!loading&&!error&&!hasEvidence&&<p role="status">No recorded evidence is available for this function.</p>}
```


## Task brief and ownership

Improve the existing React/Vite application's recorded comparison workflow while the static dashboard is edited independently. Operator: a reverse engineer inspecting one concrete implementation within a related-build workspace. Immediate job: read the observed source and recorded target/candidate instruction alignment together without losing the selected function.

Owned changes: frontend/src/workstation/CompareView.tsx, frontend/src/workstation/compare.css, and this report. No static/backend/canonical-document edits, commits, installs, servers, recovery actions, cancellations, binary uploads, tests, or builds.

The checkout already contained changes in README, Actions, ExchangeContribution, ScopedClaims, activity, cockpit CSS, scratch workspace/CSS, usePreparationRuns, WorkstationApp, workstation CSS, an untracked MenuBar, and untracked dist. These are preserved. CompareView was clean at task entry; its git diff below is this task's incremental change. New CSS is isolated to avoid editing the already dirty workstation stylesheet.

## Reference research and synthesis

| Reference inspected directly | Useful pattern | Application / limit |
| --- | --- | --- |
| [APKMan](https://apkman.wencai.app/) | Clear local-file entry with explicit processing boundary; resource/source exploration | Preserve existing local ingest, show server-project import separately. No APK upload or support claim was added. |
| [decomp.dev repository](https://github.com/encounter/decomp.dev) | Project progress and GitHub integration | Main website fetch was restricted. Read actual repository README via gh; do not claim visual website inspection or reinterpret coverage as proof. |
| [DQIV-DECOMP](https://github.com/GoldieLeGenie/DQIV-DECOMP) | Known target ROM hash, ds-decomp reconstruction, region configuration, generated objdiff.json and per-source symbol review | This is a reconstruction/proof workflow reference, not a UI reference. README distinguishes a normal ROM build from matching-ROM prerequisites. Do not copy its toolchain or claim AgentDecompile has its proof. |
| [capa Explorer](https://mandiant.github.io/capa/explorer/) / [source README](https://github.com/mandiant/capa/tree/master/web/explorer) | Function/process scoped capability tree, expandable evidence, filtering | Future contextual evidence should attach to selected concrete functions. No capability counts invented. Web fetch was a JS shell; inspected repository documentation via gh. |
| [objdiff-web](https://github.com/encounter/objdiff-web) | Symbol selection beside object comparison; real object parsing and diff | Retain existing symbol rail and alignedDiff receipt viewer; add observed-source context. No fake alignment or client compiler added. |
| [Dogbolt](https://dogbolt.org/) | Juxtaposed named decompiler outputs | Source and recorded instructions are now adjacent at sufficient pane width. Dogbolt retains uploads; no user binaries were uploaded. |
| [RzWeb](https://rizin.pages.dev/) / [repository](https://github.com/IndAlok/rzweb) | Connected assembly, source, references, CFG and hex views; explicit worker limits | Reuse concrete selection and existing source editor. Its binary-per-worker tabs are not the requested project-tab model. |

Research used website reads and gh API for repository READMEs, never curl. No reference runtime was used to analyze user data.

## Design decision before implementation

Use the frontend-app-builder small-UI-fix exception inside the existing design system. This slice does not introduce a new application shell, full redesign, decorative assets, or image concept. frontend-design guided a single subject-specific improvement: observed source beside actual recorded comparison. A full project-tab / Compare-Recover-Work shell remains separate future work requiring full concept coverage.

Keep existing tokens: background #10151d, panel #191f29, border #303a48, foreground #e7edf5, muted #a6b3c4, accent #42bce8. Keep system UI for chrome and DejaVu Sans Mono / Liberation Mono for addresses/code; existing compact typography and buttons. No new icon family, gradient, badge wall, or animation.

Composition: symbol rail | function identity + source visibility | recorded source / target-candidate alignment, then mismatch receipts. Use a container query on the actual available document width; below 960px stack source and comparison, and allow the whole comparison workspace to scroll on narrow viewports. Source visibility is a real local control. Source is explicitly a function observation; a candidate-bound receipt is required to link it to compiled output.

Allowed added copy: Recorded source; Show/Hide recorded source; Function observation. A candidate-bound receipt is needed to link this source to compiled output.; Reading/Refreshing recorded evidence; Inspected target address; Navigate to address; No recorded evidence is available for this function. Existing diff/proof copy remains.

## Implemented behavior and contracts

- ComparePanel receives the existing Selection and is keyed by its existing query serialization so a new function cannot retain the previous inspected difference address.
- Reuse useFunctionEvidence, sourceWitness, sourceExtent, SourceEditor (read-only, allowDraft=false), InstructionDiff, DiffEvidence and existing proof parsers.
- Keep the same /dashboard/api/workbench/function and /functions reads. SourceEditor retains its existing runtime-config read for IDE links; no new API contract or backend scheduler.
- Accept both existing functions and results list response shapes, as other workstation consumers do.
- Display recorded sourcePath, target program/slug and function address without relabeling decompiler observation as compiled candidate source.
- Keep recorded evidence visible while its existing polling hook refreshes. Error text remains visible when a refresh fails.
- Difference navigation sets an inspected address locally. Only the explicit Navigate to address button changes shared selection; lastFunctionAddr retains function scope. Before this change, Previous/Next difference called onSelect immediately and could replace the selected function with an interior instruction address.
- Existing candidate/target receipt and verified matchingPhase checks are unchanged. No fresh comparison, source equivalence, whole-image rebuild, runtime behavior or recovery completion is claimed.

## Verification and fidelity limits

Inline TypeScript createSourceFile parsed the changed TSX with zero syntax diagnostics; no emit. git diff --check passed for the changed tracked file. These are read-only source checks, not typecheck/build/runtime acceptance. No test files were created or run.

A separate Playwright CLI session named vite-reference-workbench opened the existing 8080/react route, as explicitly requested by the task. It initially loaded Cockpit with a visible Cockpit API unreachable state for /dashboard/api/cockpit/summary and one console error. No Retry or operation control was invoked. This is observed existing-runtime state; it is not attributed to the unbuilt source change.

Read-only navigation to /react/?view=Compare#workstation loaded the existing Compare screen and its empty-function state. It served /react/assets/index-CZZun0Jh.js and still showed the existing binary sessions, extensive analysis tabs, Functions sidebar, evidence inspector and Activity dock. Nine console errors were observed by the browser session; their causes were not diagnosed in this slice. This confirms a packaged route, not activation of the changed TSX/CSS. No target/function was selected and no job control was used.

No source build/activation was authorized. Therefore changed-source screenshots, responsive interaction acceptance, and concept-to-render view_image comparison are unavailable. Do not claim faithful live verification. No accepted image concept exists for this narrow exception.

Fidelity ledger:
1. Palette: reuses named workstation variables; rendering not verified.
2. Typography: reuses existing SourceEditor and global code fonts; rendering not verified.
3. Container model: symbol rail retained; source/diff grid uses actual container width; mobile behavior remains unverified.
4. Copy/evidence: explicit observation/candidate distinction added; no new proof claim.
5. Motion: no new animation; existing reduced-motion policy applies.
6. Selection: source and diff share existing selection and response; explicit address navigation is source-reviewed, not browser-accepted.
7. Existing global shell, project tabs, activity ownership and dirty styles are preserved, not declared complete.

## Remaining work and review priorities

This is not completion of the requested complete reference-inspired Vite application. Existing WorkstationApp still records binary-keyed sessions and many analysis destinations. Project-tab identity, a consolidated Compare/Recover/Work shell, project-wide logical member browsing, directed relationship graph, contextual capability evidence, import targeting, and real event-to-source/byte visualizations need dedicated changes and current backend contract review. Existing LogicalNavigator/MatchReview, AnalysisView, preparation/activity hooks, project locator normalization, and source/diff boundaries should be reused.

Independent review should inspect: function scope when navigating interior addresses; source/candidate wording; absence of mutation APIs; retained user edits; CSS scroll behavior with both global sidebars; keyboard access to source toggle and explicit navigation; actual compiled bundle behavior once builds/activation are authorized. Current dist is not a receipt for this source.

## Actual incremental before/after diff

Captured from git diff for the entry-clean CompareView plus /dev/null comparison for the new stylesheet. Generated directly in memory and embedded here; no temporary test file or patch file.

```diff
diff --git a/src/agentdecompile_recovery/corpus/dashboard/frontend/src/workstation/CompareView.tsx b/src/agentdecompile_recovery/corpus/dashboard/frontend/src/workstation/CompareView.tsx
index 59042e65..3a3d840a 100644
--- a/src/agentdecompile_recovery/corpus/dashboard/frontend/src/workstation/CompareView.tsx
+++ b/src/agentdecompile_recovery/corpus/dashboard/frontend/src/workstation/CompareView.tsx
@@ -1,20 +1,42 @@
 import {useEffect, useMemo, useState} from 'react';
 import {API,query,type Data,type Selection} from '../contracts';
 import {ErrorLine} from '../ui';
-import {useFunctionEvidence} from '../SourceEditor';
+import {SourceEditor,sourceExtent,sourceWitness,useFunctionEvidence} from '../SourceEditor';
 import {DiffEvidence} from '../views/DiffEvidence';
 import {diffMismatches,diffReceipts,instructionDiffRows,matchingPhase} from '../integration/boundaries';
 import {InstructionDiff} from '../views/InstructionDiff';
+import './compare.css';
 
 /** Compare tab body. Reads the same recorded proof fields as the matching surface. */
-export function ComparePanel({detail,loading,error,hasFunction,onSelect}:{detail:Data;loading:boolean;error:string;hasFunction:boolean;onSelect:(patch:Partial<Selection>)=>void}) {
+export function ComparePanel({detail,loading,error,hasFunction,onSelect,selection}:{detail:Data;loading:boolean;error:string;hasFunction:boolean;onSelect:(patch:Partial<Selection>)=>void;selection?:Selection}) {
   const rows = useMemo(() => instructionDiffRows(detail), [detail]);
+  const [inspectedAddress,setInspectedAddress]=useState('');
+  const [showSource,setShowSource]=useState(true);
+  const source=sourceWitness(detail);
+  const sourcePath=typeof detail.sourcePath==='string'?detail.sourcePath:'';
+  const hasEvidence=Object.keys(detail).length>0;
   if(!hasFunction)return <div className="ws-document"><p role="status">Select a function to see its recorded byte diff.</p></div>;
-  return <div className="ws-document">
+  return <div className="ws-document compare-document">
+    <header className="compare-context">
+      <div><strong>{detail.name||detail.function?.name||selection?.addr||'Selected function'}</strong><small>{selection?.program||selection?.slug||'Recorded target'}{selection?.addr?` · ${selection.addr}`:''}</small></div>
+      {selection&&<button type="button" aria-pressed={showSource} onClick={()=>setShowSource(value=>!value)}>{showSource?'Hide recorded source':'Show recorded source'}</button>}
+    </header>
     <ErrorLine error={error}/>
-    {loading&&<p role="status">Reading recorded diff…</p>}
-    {!loading && !error && <InstructionDiff rows={rows} verified={matchingPhase('',detail,false)==='objdiff-verified'} onNavigate={addr=>onSelect({addr})}/>}
-    <DiffEvidence mismatches={diffMismatches(detail)} receipts={diffReceipts(detail)} onNavigate={mismatch=>{if(mismatch.address)onSelect({addr:mismatch.address});}}/>
+    {loading&&<p role="status">{hasEvidence?'Refreshing recorded evidence…':'Reading recorded evidence…'}</p>}
+    {hasEvidence&&<div className={`compare-evidence-panes${showSource&&selection?' with-source':''}`}>
+      {showSource&&selection&&<section className="compare-source" aria-label="Recorded source for selected function">
+        <h3>Recorded source</h3>
+        <p className="muted">Function observation. A candidate-bound receipt is needed to link this source to compiled output.</p>
+        {sourcePath&&<code className="compare-source-path">{sourcePath}</code>}
+        <SourceEditor selection={selection} value={source} sourcePath={sourcePath} extent={sourceExtent(detail)} allowDraft={false}/>
+      </section>}
+      <section className="compare-diff" aria-label="Recorded comparison for selected function">
+        <InstructionDiff rows={rows} verified={matchingPhase('',detail,false)==='objdiff-verified'} onNavigate={setInspectedAddress}/>
+        {inspectedAddress&&<div className="compare-location"><span>Inspected target address <code>{inspectedAddress}</code></span><button type="button" onClick={()=>onSelect({addr:inspectedAddress,lastFunctionAddr:selection?.lastFunctionAddr||selection?.addr||''})}>Navigate to address</button></div>}
+        <DiffEvidence mismatches={diffMismatches(detail)} receipts={diffReceipts(detail)} onNavigate={mismatch=>{if(mismatch.address)setInspectedAddress(mismatch.address);}}/>
+      </section>
+    </div>}
+    {!loading&&!error&&!hasEvidence&&<p role="status">No recorded evidence is available for this function.</p>}
     <p className="muted">This shows recorded objdiff receipts for the selected function. It does not run a new diff.</p>
   </div>;
 }
@@ -27,7 +49,7 @@ function ComparisonSymbols({selection,revision,active,onSelect}:{selection:Selec
   const params=new URLSearchParams(query({...selection,addr:''}));
   params.set('q',filter);params.set('offset',String(offset));params.set('limit','200');
   const evidence=useFunctionEvidence(active?`${API}/functions?${params}`:null,revision);
-  const rows:Data[]=Array.isArray(evidence.data.results)?evidence.data.results:[];
+  const rows:Data[]=Array.isArray(evidence.data.functions)?evidence.data.functions:Array.isArray(evidence.data.results)?evidence.data.results:[];
   const total=typeof evidence.data.total==='number'?evidence.data.total:null;
   return <nav className="compare-symbols" aria-label="Comparison symbol tree">
     <label>Symbols<input type="search" value={filter} placeholder="Filter function names" onChange={event=>{setFilter(event.target.value);setOffset(0);}}/></label>
@@ -45,5 +67,5 @@ export function CompareView({active=true,selection,revision,enabled,onSelect}:{a
   const hasFunction=Boolean(selection.addr);
   const detail=useFunctionEvidence(active&&enabled&&hasFunction?`${API}/function?${query(selection)}`:null,revision);
   if(!enabled)return <div className="ws-document"><p role="status">Open a recorded binary to see its byte diff.</p></div>;
-  return <div className="compare-workspace"><ComparisonSymbols selection={selection} revision={revision} active={active&&enabled} onSelect={onSelect}/><ComparePanel detail={detail.data} loading={detail.loading} error={detail.error} hasFunction={hasFunction} onSelect={onSelect}/></div>;
+  return <div className="compare-workspace"><ComparisonSymbols selection={selection} revision={revision} active={active&&enabled} onSelect={onSelect}/><ComparePanel key={query(selection)} selection={selection} detail={detail.data} loading={detail.loading} error={detail.error} hasFunction={hasFunction} onSelect={onSelect}/></div>;
 }
diff --git a/src/agentdecompile_recovery/corpus/dashboard/frontend/src/workstation/compare.css b/src/agentdecompile_recovery/corpus/dashboard/frontend/src/workstation/compare.css
new file mode 100644
index 00000000..4a8521e2
--- /dev/null
+++ b/src/agentdecompile_recovery/corpus/dashboard/frontend/src/workstation/compare.css
@@ -0,0 +1,14 @@
+.compare-document{min-width:0;overflow:auto;container-type:inline-size}
+.compare-context{display:flex;align-items:center;justify-content:space-between;gap:12px;border-bottom:1px solid var(--border);padding-bottom:12px;margin-bottom:12px}
+.compare-context>div{min-width:0;overflow-wrap:anywhere}
+.compare-context button{flex:none}
+.compare-evidence-panes{display:grid;grid-template-columns:minmax(0,1fr);gap:16px;margin-bottom:16px}
+.compare-source,.compare-diff{min-width:0}
+.compare-source-path{display:block;overflow-wrap:anywhere;color:var(--muted);margin-bottom:8px;font-size:11px}
+.compare-source .source-editor{background:var(--bg-panel)}
+.compare-source .source-editor-host{height:360px;min-height:180px}
+.compare-source .source-editor-toolbar{font-size:11px}
+.compare-location{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;padding:8px 0;border-block:1px solid var(--border);margin-block:8px}
+.compare-symbols [aria-current=true]{border-color:var(--accent);color:var(--accent)}
+@container(min-width:960px){.compare-evidence-panes.with-source{grid-template-columns:minmax(280px,2fr) minmax(0,3fr)}}
+@media(max-width:800px){.compare-workspace{overflow:auto;grid-template-rows:auto minmax(300px,1fr)}.compare-context{align-items:flex-start;flex-wrap:wrap}.compare-document{overflow:visible}.compare-source .source-editor-toolbar button{min-height:36px!important}.compare-source .source-editor-host{height:260px}}

```

