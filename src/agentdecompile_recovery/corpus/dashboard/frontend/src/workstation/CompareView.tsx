import {useEffect, useMemo, useState} from 'react';
import {API,query,type Data,type Selection} from '../contracts';
import {ErrorLine} from '../ui';
import {useFunctionEvidence} from '../SourceEditor';
import {DiffEvidence} from '../views/DiffEvidence';
import {diffMismatches,diffReceipts,instructionDiffRows,matchingPhase} from '../integration/boundaries';
import {InstructionDiff} from '../views/InstructionDiff';

/** Compare tab body. Reads the same recorded proof fields as the matching surface. */
export function ComparePanel({detail,loading,error,hasFunction,onSelect}:{detail:Data;loading:boolean;error:string;hasFunction:boolean;onSelect:(patch:Partial<Selection>)=>void}) {
  const rows = useMemo(() => instructionDiffRows(detail), [detail]);
  if(!hasFunction)return <div className="ws-document"><p role="status">Select a function to see its recorded byte diff.</p></div>;
  return <div className="ws-document">
    <ErrorLine error={error}/>
    {loading&&<p role="status">Reading recorded diff…</p>}
    {!loading && !error && <InstructionDiff rows={rows} verified={matchingPhase('',detail,false)==='objdiff-verified'} onNavigate={addr=>onSelect({addr})}/>}
    <DiffEvidence mismatches={diffMismatches(detail)} receipts={diffReceipts(detail)} onNavigate={mismatch=>{if(mismatch.address)onSelect({addr:mismatch.address});}}/>
    <p className="muted">This shows recorded objdiff receipts for the selected function. It does not run a new diff.</p>
  </div>;
}

function ComparisonSymbols({selection,revision,active,onSelect}:{selection:Selection;revision:number;active:boolean;onSelect:(patch:Partial<Selection>)=>void}) {
  const [filter,setFilter]=useState('');
  const [offset,setOffset]=useState(0);
  const scope=JSON.stringify([selection.locator,selection.slug,selection.program]);
  useEffect(()=>{setOffset(0);setFilter('');},[scope]);
  const params=new URLSearchParams(query({...selection,addr:''}));
  params.set('q',filter);params.set('offset',String(offset));params.set('limit','200');
  const evidence=useFunctionEvidence(active?`${API}/functions?${params}`:null,revision);
  const rows:Data[]=Array.isArray(evidence.data.results)?evidence.data.results:[];
  const total=typeof evidence.data.total==='number'?evidence.data.total:null;
  return <nav className="compare-symbols" aria-label="Comparison symbol tree">
    <label>Symbols<input type="search" value={filter} placeholder="Filter function names" onChange={event=>{setFilter(event.target.value);setOffset(0);}}/></label>
    <ErrorLine error={evidence.error}/>
    {evidence.loading?<p role="status">Reading symbols…</p>:evidence.data.queued?<p role="status">Live read queued. {evidence.data.sessionReason}</p>:<>
      <ul>{rows.map((row,index)=><li key={`${row.addr||row.address}:${index}`}><button type="button" disabled={!row.addr&&!row.address} aria-current={String(row.addr||row.address)===selection.addr?'true':undefined} onClick={()=>onSelect({addr:String(row.addr||row.address||''),lastFunctionAddr:String(row.addr||row.address||'')})}>{row.name||row.addr||row.address||'Unnamed function'} <small>{row.addr||row.address}</small></button></li>)}</ul>
      {!rows.length&&!evidence.error&&<p>No symbols returned for this filter.</p>}
      <div className="symbol-pages"><button disabled={!offset} onClick={()=>setOffset(Math.max(0,offset-200))}>Previous</button><span>{rows.length?offset+1:0}–{offset+rows.length}{total===null?'':` of ${total}`}</span><button disabled={total===null?rows.length<200:offset+rows.length>=total} onClick={()=>setOffset(offset+200)}>Next</button></div>
    </>}
  </nav>;
}

/** Fetches only while the tab is visible, so a retained hidden panel does not poll. */
export function CompareView({active=true,selection,revision,enabled,onSelect}:{active?:boolean;selection:Selection;revision:number;enabled:boolean;onSelect:(patch:Partial<Selection>)=>void}) {
  const hasFunction=Boolean(selection.addr);
  const detail=useFunctionEvidence(active&&enabled&&hasFunction?`${API}/function?${query(selection)}`:null,revision);
  if(!enabled)return <div className="ws-document"><p role="status">Open a recorded binary to see its byte diff.</p></div>;
  return <div className="compare-workspace"><ComparisonSymbols selection={selection} revision={revision} active={active&&enabled} onSelect={onSelect}/><ComparePanel detail={detail.data} loading={detail.loading} error={detail.error} hasFunction={hasFunction} onSelect={onSelect}/></div>;
}
