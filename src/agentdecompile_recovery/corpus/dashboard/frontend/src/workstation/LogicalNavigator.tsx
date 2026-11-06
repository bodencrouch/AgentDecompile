import {useEffect,useRef,useState} from 'react';
import {API,request,type Data,type Selection} from '../contracts';
import {ErrorLine,RecordView,useData} from '../ui';
import {memberSelection} from './navigation';

export function LogicalNavigator({selection,binaries,corpus,revision,onSelect,onMember}:{selection:Selection;binaries:Data[];corpus:ReturnType<typeof useData>;revision:number;onSelect:(patch:Partial<Selection>)=>void;onMember:(selection:Selection)=>void}) {
  const [filter,setFilter]=useState(''),[search,setSearch]=useState(''),[pages,setPages]=useState<number[]>([0]);
  const [inspecting,setInspecting]=useState(false),[inspectionError,setInspectionError]=useState('');
  const current=String(corpus.data.corpus?.identity||'');
  const expected=selection.corpusIdentity||current;
  const compatible=Boolean(current&&expected===current&&!corpus.loading&&!corpus.error);
  const legacy=Boolean(selection.logicalId&&!selection.corpusIdentity);
  const detailUrl=selection.logicalId&&selection.corpusIdentity?`${API}/logical/${encodeURIComponent(selection.logicalId)}?corpus_identity=${encodeURIComponent(selection.corpusIdentity)}`:null;
  const list=useData(compatible?`/dashboard/browse-block?block=logical&limit=50&lq=${encodeURIComponent(search)}&logical_after=${pages.at(-1)||0}&corpus_identity=${encodeURIComponent(expected)}`:null,revision);
  const detail=useData(compatible?detailUrl:null,revision);
  const detailReady=compatible&&!legacy&&!list.error&&!detail.loading&&!detail.error&&!inspectionError&&detail.data.corpus?.identity===expected;
  const members:Data[]=detailReady?detail.data.members||[]:[];
  const generation=useRef(0);
  useEffect(()=>{generation.current++;setInspectionError('');setInspecting(false);return()=>{generation.current++;};},[selection,expected,revision]);
  async function inspect(member:Data){
    const attempt=++generation.current;
    setInspecting(true);setInspectionError('');
    try{
      const fresh=await request(detailUrl!);
      if(attempt!==generation.current)return;
      if(fresh.corpus?.identity!==expected||!(fresh.members||[]).some((row:Data)=>row.slug===member.slug&&row.addr===member.addr))throw new Error('The corpus or member changed. Refresh and select the member again.');
      onMember(memberSelection(member,binaries,selection));
    }catch(error){if(attempt===generation.current)setInspectionError(String(error));}
    finally{if(attempt===generation.current)setInspecting(false);}
  }
  const missing=detailReady?binaries.filter(binary=>!members.some(member=>binary.slug===member.slug||binary.aliasSlugs?.includes(member.slug))):[];
  return <div className="ws-document"><h2>Shared logical codebase</h2>
    <p>Reading corpus <code>{corpus.data.corpus?.path||corpus.data.current||'Unavailable'}</code>. This is the server-selected corpus, not a project-scoped lookup. Member evidence does not establish accepted equivalence or byte accuracy.</p>
    <ErrorLine error={corpus.error||inspectionError}/>
    {legacy&&<p role="status">This saved logical ID has no database identity. Select an identity from the list explicitly to bind it to this corpus.</p>}
    {selection.corpusIdentity&&current!==selection.corpusIdentity&&!corpus.loading&&<p role="alert">The selected identity belongs to another or unavailable corpus. Member inspection is blocked.</p>}
    {!current&&!corpus.loading&&<p role="status">No readable corpus database is selected.</p>}
    {selection.corpusIdentity&&<button onClick={()=>{setPages([0]);onSelect({locator:selection.locator,projectId:selection.projectId,slug:'',program:'',binaryHash:'',addr:'',logicalId:'',corpusIdentity:''});}}>Browse current corpus</button>}
    <form className="ws-toolbar" onSubmit={event=>{event.preventDefault();setSearch(filter);setPages([0]);}}><label>Find a logical entity <input value={filter} onChange={event=>setFilter(event.target.value)}/></label><button>Search identities</button></form>
    <ErrorLine error={list.error}/>{(list.data.errors||[]).map((error:string,index:number)=><ErrorLine key={index} error={error}/>)}
    <div className="ws-records" aria-busy={list.loading}>{(list.data.rows||[]).map((row:Data)=><div className="ws-record" key={row.id}><button disabled={!compatible||list.loading||Boolean(list.error)||list.data.corpus?.identity!==expected} aria-pressed={selection.logicalId===String(row.id)&&selection.corpusIdentity===expected} onClick={()=>onSelect({logicalId:String(row.id),corpusIdentity:expected})}><span>{row.name||`Identity ${row.id}`}</span><small>{row.members??'?'} members · confidence {row.confidence??'not recorded'}</small></button></div>)}</div>
    {!list.loading&&!(list.data.rows||[]).length&&<p>No logical identities returned. Concrete functions remain available in the function navigator.</p>}
    <div className="ws-toolbar"><button disabled={pages.length===1||list.loading} onClick={()=>setPages(old=>old.slice(0,-1))}>Previous identities</button><button disabled={!list.data.more||list.loading||Boolean(list.error)} onClick={()=>setPages(old=>[...old,Number(list.data.rows?.at(-1)?.id)||0])}>Next identities</button></div>
    {selection.logicalId&&<section aria-label="Logical entity members"><h3>{detail.data.name||`Identity ${selection.logicalId}`}</h3><ErrorLine error={detail.error}/>{(detail.data.errors||[]).map((error:string,index:number)=><ErrorLine key={index} error={error}/>)}
      {detail.loading&&<p role="status">Reading members…</p>}
      <table className="ws-table"><thead><tr><th>Build / address</th><th>Relationship evidence</th><th>Inspection target</th></tr></thead><tbody>{members.map((member,index)=>{
        const target=memberSelection(member,binaries,selection);
        const ambiguous=members.filter(row=>row.slug===member.slug).length>1;
        return <tr key={`${member.slug}:${member.addr}:${index}`}><td><strong>{member.slug}</strong><br/><code>{member.addr||'No address'}</code></td><td>{ambiguous?'Multiple recorded members in this build; relationship ambiguous. ':''}{member.method||'Method not recorded'} · confidence {member.confidence??'not recorded'}<details><summary>Evidence / divergence</summary><RecordView value={member.evidence??{status:'No divergence or acceptance verdict supplied'}}/></details></td><td><button disabled={!target.slug||!target.addr||!detailReady||inspecting||(detail.data.errors||[]).length>0} onClick={()=>void inspect(member)}>Inspect member</button><small>{target.program?`${target.locator} · ${target.program}`:'No unique project binding; corpus browsing only'}</small></td></tr>;
      })}</tbody></table>
      {!detail.loading&&!members.length&&<p>No members returned for this identity.</p>}
      {missing.length>0&&<details><summary>Builds without a returned member ({missing.length})</summary><p>This does not establish that a build is unmatched; the API supplies no negative-match or divergence verdict.</p><ul>{missing.map((binary,index)=><li key={binary.slug||index}>{binary.name||binary.slug||binary.sha256}</li>)}</ul></details>}
    </section>}
  </div>;
}
