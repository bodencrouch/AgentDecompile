import { useEffect, useRef, useState } from 'react';
import { API, query, request, type Data, type SurfaceProps } from './contracts';
import { binaryIdentityKey, shouldAutoOpenFunction } from './atlasAutoOpen';
import './atlas-analysis.css';

const numeric=(value:unknown)=>typeof value==='number'&&Number.isFinite(value)?value.toLocaleString(undefined,{maximumFractionDigits:3}):'Awaiting recorded count';
const sourceLabel=(value:unknown)=>value==='advisory-source'?'C witness':value==='assembly-substrate'?'Assembly substrate':value==='assembly-only'?'Assembly listing':'Not recorded';
const featureLabel=(value:string)=>({n_instructions:'Instructions',n_edges:'Control-flow edges',n_blocks:'Basic blocks',n_calls:'Calls',n_callees:'Callees',n_callers:'Callers',n_constants:'Constants',n_strings:'Strings',size:'Byte size',instructions:'Instructions',edges:'Control-flow edges',blocks:'Basic blocks',cyclomatic:'Cyclomatic complexity'} as Record<string,string>)[value]||value.replaceAll('_',' ');
const methodText=(value:unknown)=>Array.isArray(value)?value.map(v=>featureLabel(String(v))).join(', '):typeof value==='string'?value:'';
const canonical=(value:unknown)=>String(value||'').toLowerCase().replace(/^0x0*/,'');
function useAnalysisData(url:string|null,revision:number) {
  const [state,setState]=useState<{key:string|null;data:Data;loading:boolean;error:string}>({key:null,data:{},loading:false,error:''});
  const loadingRef=useRef(false),wantedRevision=useRef(revision),loadedRevision=useRef(revision),retryAt=useRef(0),failures=useRef(0);
  const [refresh,setRefresh]=useState(0);wantedRevision.current=revision;
  useEffect(()=>{const timer=setInterval(()=>{if(!loadingRef.current&&(wantedRevision.current!==loadedRevision.current||(retryAt.current>0&&Date.now()>=retryAt.current)))setRefresh(n=>n+1);},5000);return()=>clearInterval(timer);},[]);
  useEffect(()=>{
    retryAt.current=0;
    if(!url){loadingRef.current=false;loadedRevision.current=wantedRevision.current;setState({key:null,data:{},loading:false,error:''});return;}
    const controller=new AbortController();loadingRef.current=true;loadedRevision.current=wantedRevision.current;
    setState(old=>({key:url,data:old.key===url?old.data:{},loading:true,error:''}));
    const failed=(error:string)=>{loadingRef.current=false;failures.current+=1;retryAt.current=Date.now()+Math.min(60000,5000*2**Math.min(failures.current,4));setState(old=>({...old,key:url,loading:false,error}));};
    void request(url,{signal:AbortSignal.any([controller.signal,AbortSignal.timeout(20000)])}).then(data=>{if(!controller.signal.aborted){if(data.error){failed(String(data.error));return;}loadingRef.current=false;failures.current=0;setState({key:url,data,loading:false,error:''});}}).catch(e=>{if(!controller.signal.aborted)failed(e instanceof Error?e.message:String(e));});
    return()=>controller.abort();
  },[url,refresh]);
  return state.key===url?state:{key:url,data:{},loading:Boolean(url),error:''};
}
export function AtlasAnalysis(props:SurfaceProps) {
  const [search,setSearch]=useState(''),[offset,setOffset]=useState(0),[sort,setSort]=useState('score-desc');
  const [browseOnly,setBrowseOnly]=useState(false);
  const openedForKey=useRef<string|null>(null);
  const selected=Boolean(props.selection.slug||props.selection.program),limit=60;
  const binaryKey=binaryIdentityKey(props.selection);
  useEffect(()=>{setOffset(0);setSearch('');setBrowseOnly(false);},[props.selection.slug,props.selection.program,props.selection.locator]);
  const data=useAnalysisData(selected?API+'/analysis?'+query({...props.selection,addr:'',logicalId:''},{view:'scoring',q:search,offset,limit,sort}):null,props.revision);
  const rows:Data[]=data.data.results||[];
  const basis=methodText(data.data.model?.features||data.data.model?.basis)||'Advisory structure scores, not byte proof';
  const rankingProminent=browseOnly||!props.selection.addr;
  const topRow=rows[0];
  const onSelect=props.onSelect;
  useEffect(()=>{
    if(data.loading||data.error)return;
    if(!shouldAutoOpenFunction({browseOnly,addr:String(props.selection.addr||''),rowCount:rows.length,binaryKey,openedForKey:openedForKey.current}))return;
    if(!topRow?.addr)return;
    openedForKey.current=binaryKey;
    onSelect({addr:String(topRow.addr),logicalId:String(topRow.logicalId||'')});
  },[browseOnly,binaryKey,data.loading,data.error,rows.length,topRow,props.selection.addr,onSelect]);
  return <section className={'atlas-analysis'+(rankingProminent?' ranking-prominent':'')+(browseOnly?' browse-only':'')} aria-label="Function ranking">
    <div className="analysis-heading">
      <div>
        <h2>{browseOnly?'Ranked functions':'Pick a function'}</h2>
        <p>{props.selection.program||props.selection.slug||'Choose a binary in the explorer'}</p>
      </div>
      <div className="analysis-heading-actions">
        {selected&&!browseOnly&&(
          <button type="button" className="analysis-browse-link" onClick={()=>setBrowseOnly(true)}>
            Browse ranked list
          </button>
        )}
        {browseOnly&&(
          <button type="button" className="analysis-browse-link" onClick={()=>setBrowseOnly(false)}>
            Hide ranking
          </button>
        )}
        <span>{basis}</span>
      </div>
    </div>
    {!selected?<div className="analysis-empty"><h3>Choose a binary</h3><p>Open a build in the explorer, then select a function here or in the tree.</p></div>:(
      <>
        <div className="analysis-toolbar"><label>Find function<input name="analysis-function-search" autoComplete="off" aria-label="Search analysis functions" value={search} onChange={e=>{setSearch(e.target.value);setOffset(0);}} placeholder="Filter by name or address…"/></label><label>Order<select name="analysis-function-sort" aria-label="Sort function scoring" value={sort} onChange={e=>{setSort(e.target.value);setOffset(0);}}><option value="score-desc">Higher complexity first</option><option value="score-asc">Lower complexity first</option><option value="address">Address</option></select></label><span role="status">{data.loading?'Loading…':`${numeric(data.data.total)} functions`}</span></div>
        {data.error&&<p className="analysis-error" role="alert">{data.error}</p>}
        <div className="analysis-score-table"><table><thead><tr><th>Rank</th><th>Tier</th><th>Function</th><th>Score</th><th>Source</th><th>Instructions</th></tr></thead><tbody>{rows.map(row=><tr key={row.addr} className={canonical(row.addr)===canonical(props.selection.addr)?'selected':''}><td>{row.rank??'—'}</td><td><span data-tier={row.tier||'unknown'}>{row.tier||'Not scored'}</span></td><td><button type="button" onClick={()=>{setBrowseOnly(false);props.onSelect({addr:row.addr,logicalId:String(row.logicalId||'')});}}><strong>{row.name||row.addr}</strong><code>{row.addr}</code></button></td><td>{numeric(row.score)}</td><td>{sourceLabel(row.sourceState)}</td><td>{numeric(row.metrics?.instructions)}</td></tr>)}</tbody></table>{!rows.length&&!data.loading&&<p className="analysis-empty">{data.data.reason||'No scored function records yet.'}</p>}</div>
        <footer className="analysis-pagination"><button type="button" disabled={offset===0||data.loading} onClick={()=>setOffset(Math.max(0,offset-limit))}>Previous</button><span>{rows.length?offset+1:0}–{offset+rows.length} of {numeric(data.data.total)}</span><button type="button" disabled={!data.data.hasMore||data.loading} onClick={()=>setOffset(offset+limit)}>Next</button></footer>
      </>
    )}
  </section>;
}
