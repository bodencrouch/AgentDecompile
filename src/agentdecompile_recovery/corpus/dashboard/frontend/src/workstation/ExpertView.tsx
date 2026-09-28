import {useMemo,useState} from 'react';
import {API,query,type Data,type Selection} from '../contracts';
import {useFunctionEvidence,sourceWitness,sourceExtent} from '../SourceEditor';
import {ErrorLine,RecordView} from '../ui';
import {addressOf} from './navigation';

/** Expert inspection follows the shell selection; it owns no program/session state. */
export function ExpertView({selection,revision,onSelect}:{selection:Selection;revision:number;onSelect:(patch:Partial<Selection>)=>void}) {
  const result=useFunctionEvidence(selection.addr&&(selection.slug||selection.program)?`${API}/function?${query(selection)}`:null,revision);
  const [filter,setFilter]=useState('');
  const detail=result.data.listing?{...result.data,...result.data.listing,function:result.data.selected}:result.data;
  const assembly=String(detail.assembly?.text||detail.disassembly?.text||'');
  const lines=useMemo(()=>assembly.split('\n').map((text,index)=>({text,line:index+1})).filter(row=>row.text&&(!filter||row.text.toLowerCase().includes(filter.toLowerCase()))),[assembly,filter]);
  const graph=detail.graph||detail;
  if(!selection.addr)return <div className="ws-document"><p>Select a function in the shared navigator to inspect its instructions and references.</p></div>;
  return <div className="ws-document expert-view"><h2>Expert inspection · {detail.function?.name||selection.addr}</h2>
    <p>Recorded evidence for the shared address <code>{selection.addr}</code>. Navigating a reference updates every analysis view.</p>
    <ErrorLine error={result.error}/>{result.loading&&<p role="status">Reading function evidence…</p>}
    {!result.loading&&result.data.queued&&<p role="status">Live reader queued. {result.data.sessionReason}</p>}
    {!result.loading&&!result.error&&!result.data.queued&&<>
      <div className="expert-columns"><section><h3>Instructions</h3><label>Filter instructions <input type="search" value={filter} onChange={event=>setFilter(event.target.value)}/></label>
        {!assembly?<p>No disassembly evidence is available for this function.</p>:<pre>{lines.map(row=><span key={row.line}>{String(row.line).padStart(5)}  {row.text}{'\n'}</span>)}</pre>}
        {assembly&&!lines.length&&<p>No instruction matches this filter.</p>}
      </section><section><h3>Source witness</h3><p>{sourceExtent(detail)}</p><pre>{sourceWitness(detail)||'No recovered or decompiled source witness is available.'}</pre></section></div>
      <div className="expert-columns">{['callers','callees'].map(side=><section key={side}><h3>{side==='callers'?'Incoming references':'Outgoing references'}</h3>
        <ErrorLine error={graph[`${side}Error`]||''}/>
        {!(graph[side]||[]).length&&<p>No references returned in this bounded snapshot.</p>}
        <ul>{(graph[side]||[]).map((row:Data,index:number)=><li key={index}>{addressOf(row)?<button onClick={()=>onSelect({addr:addressOf(row),logicalId:String(row.logicalId||row.logical_id||'')})}><code>{addressOf(row)}</code> {row.name||row.symbol||'Reference'}</button>:<RecordView value={row}/>}</li>)}</ul>
      </section>)}</div>
      <details><summary>Raw function and proof metadata</summary><RecordView value={{function:detail.function,proof:detail.proof,verification:detail.verification,provenance:detail.provenance}}/></details>
    </>}
  </div>;
}
