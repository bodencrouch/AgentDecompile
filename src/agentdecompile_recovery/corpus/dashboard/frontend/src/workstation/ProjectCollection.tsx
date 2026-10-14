import type {Data,Selection} from '../contracts';
import {canonicalProjectLocator} from '../projectLocator';
import {RecordView} from '../ui';
import {memberSelection} from './navigation';
import './project-collection.css';

/** Only recorded bindings establish project membership; filenames do not. */
export function collectionBuilds(binaries:Data[],selection:Selection):Data[] {
  const locator=canonicalProjectLocator(selection.locator);
  return binaries.filter(binary=>(binary.projectBindings||[]).some((binding:Data)=>
    locator?canonicalProjectLocator(binding.locator)===locator:
      Boolean(selection.projectId&&(binding.projectId||binding.project_id)===selection.projectId)));
}
const contains=(binary:Data,member:Data)=>binary.slug===member.slug||Boolean(binary.aliasSlugs?.includes(member.slug));
const buildName=(binary:Data)=>String(binary.name||binary.label||binary.slug||'Unnamed build');

export function ProjectCollection({selection,binaries,members,identityName,sourceFile,objectFile,ready,loading,error,relationshipReady,relationshipLoading,canInspect,onInspect,onBuild}:{
  selection:Selection;binaries:Data[];members:Data[];identityName:string;sourceFile:string;objectFile:string;ready:boolean;loading:boolean;error:string;relationshipReady:boolean;relationshipLoading:boolean;canInspect:boolean;
  onInspect:(member:Data,outsideProject?:boolean)=>void;onBuild:(selection:Selection)=>void;
}){
  const builds=ready?collectionBuilds(binaries,selection):[];
  const related=builds.filter(binary=>members.some(member=>contains(binary,member)));
  const withoutMembership=builds.filter(binary=>!members.some(member=>contains(binary,member)));
  const outside=ready?members.filter(member=>!builds.some(binary=>contains(binary,member))):[];
  const bound=Boolean(selection.locator||selection.projectId);
  const hasRelationship=Boolean(selection.logicalId&&relationshipReady);
  function membership(member:Data,index:number,external=false){
    const siblings=members.filter(row=>row.slug===member.slug);
    const target=memberSelection(member,binaries,external?{...selection,locator:'',projectId:''}:selection);
    return <li key={`${member.slug}:${member.addr}:${index}`} className="collection-member">
      <button type="button" disabled={!canInspect||!member.slug||!member.addr} onClick={()=>onInspect(member,external)} title="Inspect this recorded function implementation"><code>{String(member.addr||'Address unavailable')}</code><span>{String(member.name||member.slug||'Recorded member')}</span></button>
      <small>{String(member.method||'Method not recorded')} · confidence {String(member.confidence??'not recorded')}</small>
      <small>{target.program?`${target.locator} · ${target.program}`:'No unique project binding; corpus observation only'}</small>
      {siblings.length>1&&<small>Multiple recorded members in this build; correspondence is ambiguous.</small>}
      <details><summary>Relationship evidence</summary><RecordView value={member.evidence??{status:'No divergence or acceptance verdict supplied'}}/></details>
    </li>;
  }
  return <section className="project-collection" aria-label="Selected project collection">
    <header><h2>{bound?'Project collection':'Corpus relationships'}</h2><code>{selection.locator||selection.projectId||'No project binding selected'}</code></header>
    {loading&&<p role="status">Reading recorded project bindings…</p>}
    {error&&<p role="alert">{error}</p>}
    {!ready&&!loading&&!error&&<p>Project relationships are unavailable until the corpus identity is verified.</p>}
    {ready&&bound&&!builds.length&&<p>{!selection.locator&&selection.projectId?'This project ID has no unambiguous locator in the saved corpus context. Open the project by its locator to inspect recorded membership.':'No project-bound builds were returned. This does not establish an empty project; open its existing program inventory to inspect its contents.'}</p>}
    {ready&&bound&&builds.length>0&&<>
      {selection.logicalId&&!relationshipReady&&<p role="status">{relationshipLoading?'Reading recorded logical membership…':'Recorded membership is unavailable for this identity.'}</p>}
      {hasRelationship&&<div className="collection-relationship" aria-label="Recorded logical membership across project builds">
        <div className="collection-identity"><strong>{identityName||`Identity ${selection.logicalId}`}</strong><code>logical {selection.logicalId}</code><span>Recorded membership</span><small>Branches link this identity to returned functions. They do not establish accepted equivalence or byte accuracy.</small>{(sourceFile||objectFile)&&<details><summary>Logical record paths</summary>{sourceFile&&<p>Source <code>{sourceFile}</code></p>}{objectFile&&<p>Object <code>{objectFile}</code></p>}</details>}</div>
        {related.length?<ol className="collection-branches">{related.map((binary,index)=><li key={`${binary.slug}:${index}`} className="collection-build"><h3>{buildName(binary)}</h3><small>{[binary.platform,binary.architecture,binary.format].filter(Boolean).join(' · ')||'Build metadata not recorded'}</small><ul>{members.filter(member=>contains(binary,member)).map((member,index)=>membership(member,index))}</ul></li>)}</ol>:<p>No member of this logical identity was returned for the project's recorded builds.</p>}
      </div>}
      {!selection.logicalId&&<p>Select a logical entity below to see its recorded implementations across these builds.</p>}
      {withoutMembership.length>0&&<section className="collection-roster" aria-label="Project build roster"><h3>{hasRelationship?'Project builds without returned membership':'Builds in this project'}</h3>{hasRelationship&&<p className="muted">No returned membership is not a negative-match verdict.</p>}<ul>{withoutMembership.map((binary,index)=>{
        const target=memberSelection({slug:binary.slug},binaries,{...selection,logicalId:''});
        return <li key={`${binary.slug}:${index}`}><button type="button" disabled={!target.program||!target.locator||!ready} onClick={()=>onBuild(target)} title="Inspect this build's recorded analysis">{buildName(binary)}</button><span>{[binary.platform,binary.architecture,binary.format].filter(Boolean).join(' · ')||'Build metadata not recorded'}</span><small>{target.program||'No unique project/program binding for inspection'}</small></li>;
      })}</ul></section>}
    </>}
    {outside.length>0&&<details className="collection-outside" open={!bound}><summary>{bound?'Related corpus members outside these project bindings':'Recorded corpus members'}</summary><p>These are corpus relationships; they are not evidence of membership in the selected project.</p><ul>{outside.map((member,index)=>membership(member,index,true))}</ul></details>}
  </section>;
}
