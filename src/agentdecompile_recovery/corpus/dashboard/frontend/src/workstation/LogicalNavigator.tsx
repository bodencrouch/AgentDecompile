import {useState} from 'react';
import {API,type Data,type Selection} from '../contracts';
import {ErrorLine,RecordView,useData} from '../ui';
import {memberSelection} from './navigation';

export function LogicalNavigator({selection,binaries,revision,onSelect,onMember}:{selection:Selection;binaries:Data[];revision:number;onSelect:(patch:Partial<Selection>)=>void;onMember:(selection:Selection)=>void}) {
  const [filter,setFilter]=useState(''),[search,setSearch]=useState(''),[pages,setPages]=useState<number[]>([0]);
  const list=useData(`/dashboard/browse-block?block=logical&lq=${encodeURIComponent(search)}&logical_after=${pages.at(-1)||0}`,revision);
  const detail=useData(selection.logicalId?`${API}/logical/${encodeURIComponent(selection.logicalId)}`:null,revision);
  const members:Data[]=detail.data.members||[];
  const missing=binaries.filter(binary=>!members.some(member=>binary.slug===member.slug||binary.aliasSlugs?.includes(member.slug)));
  return <div className="ws-document"><h2>Shared logical codebase</h2>
    <p>Identities below belong to the server’s current corpus. The API does not identify that corpus or scope it to a selected project. Member evidence does not establish accepted equivalence or byte accuracy.</p>
    <form className="ws-toolbar" onSubmit={event=>{event.preventDefault();setSearch(filter);setPages([0]);}}><label>Find a logical entity <input value={filter} onChange={event=>setFilter(event.target.value)}/></label><button>Search identities</button></form>
    <ErrorLine error={list.error}/>{(list.data.errors||[]).map((error:string,index:number)=><ErrorLine key={index} error={error}/>)}
    <div className="ws-records" aria-busy={list.loading}>{(list.data.rows||[]).map((row:Data)=><div className="ws-record" key={row.id}><button aria-pressed={selection.logicalId===String(row.id)} onClick={()=>onSelect({logicalId:String(row.id)})}><span>{row.name||`Identity ${row.id}`}</span><small>{row.members??'?'} members · confidence {row.confidence??'not recorded'}</small></button></div>)}</div>
    {!list.loading&&!(list.data.rows||[]).length&&<p>No logical identities returned. Concrete functions remain available in the function navigator.</p>}
    <div className="ws-toolbar"><button disabled={pages.length===1} onClick={()=>setPages(old=>old.slice(0,-1))}>Previous identities</button><button disabled={!list.data.more||list.loading} onClick={()=>setPages(old=>[...old,Number(list.data.rows?.at(-1)?.id)||0])}>Next identities</button></div>
    {selection.logicalId&&<section aria-label="Logical entity members"><h3>{detail.data.name||`Identity ${selection.logicalId}`}</h3><ErrorLine error={detail.error}/>{(detail.data.errors||[]).map((error:string,index:number)=><ErrorLine key={index} error={error}/>)}
      {detail.loading&&<p role="status">Reading members…</p>}
      <table className="ws-table"><thead><tr><th>Build / address</th><th>Relationship evidence</th><th>Inspection target</th></tr></thead><tbody>{members.map((member,index)=>{
        const target=memberSelection(member,binaries,selection);
        const ambiguous=members.filter(row=>row.slug===member.slug).length>1;
        return <tr key={`${member.slug}:${member.addr}:${index}`}><td><strong>{member.slug}</strong><br/><code>{member.addr||'No address'}</code></td><td>{ambiguous?'Multiple recorded members in this build; relationship ambiguous. ':''}{member.method||'Method not recorded'} · confidence {member.confidence??'not recorded'}<details><summary>Evidence / divergence</summary><RecordView value={member.evidence??{status:'No divergence or acceptance verdict supplied'}}/></details></td><td><button disabled={!target.slug||!target.addr||detail.loading||Boolean(detail.error)||(detail.data.errors||[]).length>0} onClick={()=>onMember(target)}>Inspect member</button><small>{target.program?`${target.locator} · ${target.program}`:'No unique project binding; corpus browsing only'}</small></td></tr>;
      })}</tbody></table>
      {!detail.loading&&!members.length&&<p>No members returned for this identity.</p>}
      {missing.length>0&&<details><summary>Builds without a returned member ({missing.length})</summary><p>This does not establish that a build is unmatched; the API supplies no negative-match or divergence verdict.</p><ul>{missing.map((binary,index)=><li key={binary.slug||index}>{binary.name||binary.slug||binary.sha256}</li>)}</ul></details>}
    </section>}
  </div>;
}
