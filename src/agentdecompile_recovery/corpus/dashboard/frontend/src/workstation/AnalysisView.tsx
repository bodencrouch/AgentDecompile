import {useEffect,useState} from 'react';
import {API,query,type Data,type SurfaceProps} from '../contracts';
import {useData,ErrorLine,RecordView} from '../ui';
import {SourceEditor,sourceWitness,sourceExtent,useFunctionEvidence} from '../SourceEditor';
import {useTool} from '../CodeBrowser';
import {projectStore} from '../storage/projectStore';
import {createArtifactParserSession} from '../workers/artifactParser';
import type {ArtifactInspection} from '../workers/artifactParser.worker';
import {fileOffset,hexPageSelection,referenceParams,addressOf,type AnalysisTab} from './navigation';

export function AnalysisView({tab,props,onEvidence}:{tab:AnalysisTab;props:SurfaceProps;onEvidence:(data:Data)=>void}) {
  const {selection,revision,onSelect}=props;
  const local=Boolean(selection.binaryHash&&!selection.slug&&!selection.program);
  const needsFunction=['Disassembly','Decompiler','Graph'].includes(tab);
  const detail=useFunctionEvidence(!local&&needsFunction&&selection.addr?`${API}/function?${query(selection)}`:null,revision);
  const raw=detail.data, normalized=raw.listing?{...raw,...raw.listing,function:raw.selected}:raw;
  const overview=useData(!local&&tab==='Info'&&(selection.slug||selection.program)?`${API}/workspace?${query(selection)}`:null,revision);
  useEffect(()=>{if(detail.error)props.notify(detail.error,'error');if(overview.error)props.notify(overview.error,'error');},[detail.error,overview.error,props.notify]);
  useEffect(()=>{onEvidence(local?{provider:'Local artifact parser',binaryHash:selection.binaryHash,status:'Metadata only; no source or match proof'}:normalized);},[raw,selection.binaryHash,local,onEvidence]);
  if(tab==='Providers')return <ProviderView revision={revision} onAction={props.onAction}/>;
  if(local)return <LocalBytes tab={tab} hash={selection.binaryHash!} addr={selection.addr} revision={revision} onSelect={onSelect}/>;
  if(tab==='Scripts')return <div className="ws-empty"><h2>Script console</h2><p>Review script, target, and approval before execution. Output is retained in Logs.</p><button disabled={!selection.program} onClick={()=>props.onAction('mcp.execute-script',{code:'print(currentProgram.getName())'})}>Open script editor</button></div>;
  if(!selection.slug&&!selection.program)return <div className="ws-empty"><h2>Open a binary to begin</h2><p>Choose recorded analysis or inspect an ELF or PE file locally. New scratch is available without a binary.</p></div>;
  if(tab==='Info')return <div className="ws-document"><ErrorLine error={overview.error}/>{overview.loading&&<p role="status">Reading binary information…</p>}<BinaryInfo data={overview.data.overview||overview.data} selection={selection}/></div>;
  if(tab==='Xrefs')return <ReferencesView key={`${selection.locator}:${selection.program}:${selection.addr}`} props={props}/>;
  if(needsFunction){
    if(!selection.addr)return <div className="ws-empty">Select a function or jump to an address.</div>;
    const graph=normalized.graph||normalized;
    return <div className="ws-analysis-document"><ErrorLine error={detail.error}/>{(tab==='Disassembly'||tab==='Decompiler')?<SourceEditor selection={selection} value={tab==='Decompiler'?sourceWitness(normalized):normalized.assembly?.text||normalized.disassembly?.text||''} kind={tab==='Decompiler'?'source':'assembly'} sourcePath={normalized.sourcePath||''} loading={detail.loading} extent={tab==='Decompiler'?sourceExtent(normalized):normalized.assembly?.reason||'Recorded assembly · no byte-verification claim'} onInspectSymbol={symbol=>props.notify(`Search for ${symbol} in Functions to navigate to its recorded address.`)}/>:<div className="ws-document"><h2>{tab==='Graph'?'Call graph':'Cross references'} · {normalized.function?.name||selection.addr}</h2><ErrorLine error={graph.callersError||graph.calleesError||''}/>{detail.loading&&<p role="status">Reading references…</p>}{tab==='Graph'&&<CallGraph graph={graph} center={normalized.function||{addr:selection.addr}} onSelect={r=>onSelect({addr:addressOf(r),logicalId:String(r.logicalId||r.logical_id||'')})}/>}<div className={tab==='Graph'?'ws-graph':''}>{['callers','callees'].map(side=><section key={side}><h3>{side==='callers'?'Incoming calls':'Outgoing calls'}</h3><Rows rows={graph[side]||[]} onSelect={r=>onSelect({addr:addressOf(r),logicalId:String(r.logicalId||r.logical_id||'')})}/></section>)}</div><p className="muted">Recorded, bounded reference sample. Missing edges do not establish absence of calls.</p></div>}</div>;
  }
  return <LiveAnalysis key={`${tab}:${selection.slug}:${selection.program}:${selection.locator}`} tab={tab} props={props}/>;
}
function Rows({rows,onSelect}:{rows:Data[];onSelect:(r:Data)=>void}) {
  return rows.length?<div className="ws-records">{rows.map((r,i)=><div className="ws-record" key={i}>{addressOf(r)?<button onClick={()=>onSelect(r)}><code>{addressOf(r)}</code><span>{r.name||r.symbol||r.value||r.string||r.comment||r.label||'Reference'}</span></button>:<RecordView value={r}/>}</div>)}</div>:<p className="muted">No records returned.</p>;
}
function LiveAnalysis({tab,props}:{tab:AnalysisTab;props:SurfaceProps}) {
  const [filter,setFilter]=useState(''),[search,setSearch]=useState(''),[offset,setOffset]=useState(0);
  const targets:Record<string,[string,Data]>={
    Hex:['inspect-memory',{mode:'read',addressOrSymbol:props.selection.addr,length:256}],
    Strings:['manage-strings',{mode:search?'search':'list',query:search,offset,limit:80}],
    Imports:['manage-symbols',{mode:'imports',query:search,offset,limit:80}],
    Exports:['manage-symbols',{mode:'exports',query:search,offset,limit:80}],
    Sections:['inspect-memory',{mode:'blocks'}],
    Flags:['manage-bookmarks',{mode:'search',query:search,offset,limit:80}],
    Types:['manage-data-types',{mode:'list',categoryPath:search,offset,limit:80}],
  };
  const [tool,params]=targets[tab]||targets.Sections;
  const enabled=Boolean(props.selection.program&&(tab!=='Hex'||props.selection.addr));
  const result=useTool(tool,params,props,enabled);
  useEffect(()=>{if(result.error)props.notify(result.error,'error');},[result.error,props.notify]);
  const rows=['results','strings','symbols','imports','exports','blocks','bookmarks','types','dataTypes'].map(k=>result.data[k]).find(Array.isArray)||[];
  return <div className="ws-document"><form className="ws-toolbar" onSubmit={e=>{e.preventDefault();setSearch(filter);setOffset(0);}}>{!['Hex','Sections'].includes(tab)&&<><input aria-label={`Filter ${tab}`} placeholder={tab==='Types'?'Type category path':`Filter ${tab.toLowerCase()}`} value={filter} onChange={e=>setFilter(e.target.value)}/><button>Search</button></>}<span role="status">{enabled?result.status:'A live program'+(tab==='Hex'?' and address':'')+' must be selected for this view.'}</span></form><ErrorLine error={result.error}/>{tab==='Hex'?<pre className="ws-code">{result.data.hex||result.data.output||'No byte data returned.'}</pre>:<Rows rows={rows} onSelect={r=>props.onSelect({addr:addressOf(r)})}/>}<div className="ws-toolbar">{!['Hex','Sections'].includes(tab)&&<><button disabled={!offset} onClick={()=>setOffset(Math.max(0,offset-80))}>Previous</button><span>{offset+rows.length?`${offset+1}–${offset+rows.length}`:'0'} records</span><button disabled={rows.length<80} onClick={()=>setOffset(offset+80)}>Next</button></>}{tab==='Flags'&&<button disabled={!props.selection.addr||!props.selection.program} onClick={()=>props.onAction('mcp.manage-bookmarks',{mode:'set',addressOrSymbol:props.selection.addr})}>Add bookmark</button>}</div><p className="muted">Browse up to 800 references. Narrow the address or direction for larger sets.</p><details><summary>Response and provenance {result.jobId&&`· Job ${result.jobId}`}</summary><RecordView value={result.data}/></details></div>;
}
function BinaryInfo({data,selection}:{data:Data;selection:SurfaceProps['selection']}) {
  const fields: [string,unknown][]=[['Program',data.program||data.name||selection.program||selection.slug],['Project',data.path||selection.locator],['Architecture',data.architecture||data.language],['Format',data.format],['Image base',data.imageBase],['Function count',data.functionCount],['Named functions',data.namedCount],['SHA256',data.sha256||selection.binaryHash]];
  return <><h2>Binary information</h2><dl className="ws-metadata">{fields.map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value===undefined||value===null||value===''?'Not recorded':String(value)}</dd></div>)}</dl>{Array.isArray(data.memory)&&<><h3>Memory sections</h3><table className="ws-table"><thead><tr><th>Name</th><th>Start</th><th>End / size</th><th>Permissions</th></tr></thead><tbody>{data.memory.map((r:Data,i:number)=><tr key={i}><td>{r.name||'Unnamed'}</td><td><code>{r.start||r.address||'Not recorded'}</code></td><td>{r.end||r.size||'Not recorded'}</td><td>{r.permissions||[r.read?'R':'',r.write?'W':'',r.execute?'X':''].join('')||'Not recorded'}</td></tr>)}</tbody></table></>}<details><summary>Raw metadata and provenance</summary><RecordView value={data}/></details></>;
}
function CallGraph({graph,center,onSelect}:{graph:Data;center:Data;onSelect:(r:Data)=>void}) {
  const [limit,setLimit]=useState(8);
  const callers:Data[]=graph.callers||[],callees:Data[]=graph.callees||[];
  const height=Math.max(160,Math.max(Math.min(callers.length,limit),Math.min(callees.length,limit))*54+20);
  if(!callers.length&&!callees.length)return <p>No recorded call edges for this selection.</p>;
  return <><p>Incoming calls → selected function → outgoing calls. Select a node to navigate; the lists below provide the same navigation.</p><div className="ws-graph-svg"><svg viewBox={`0 0 900 ${height}`} aria-label="Recorded call relationships"><defs><marker id="ws-arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3 z" fill="currentColor"/></marker></defs>{[[callers,0],[callees,620]].map(([items,x])=>(items as Data[]).slice(0,limit).map((node,i)=><g key={String(x)+i}><line x1={x===0?270:600} y1={x===0?i*54+30:height/2} x2={x===0?300:620} y2={x===0?height/2:i*54+30} markerEnd="url(#ws-arrow)"/><foreignObject x={x as number} y={i*54+10} width="270" height="44"><button disabled={!addressOf(node)} onClick={()=>onSelect(node)} title={`${node.name||'Reference'} ${addressOf(node)}`}>{node.name||addressOf(node)}</button></foreignObject></g>))}<foreignObject x="300" y={height/2-20} width="300" height="44"><button className="center" onClick={()=>onSelect(center)} disabled={!addressOf(center)}>{center.name||addressOf(center)}</button></foreignObject></svg></div>{Math.max(callers.length,callees.length)>limit&&<button onClick={()=>setLimit(n=>n+16)}>Show more recorded nodes</button>}</>;
}
function ProviderView({revision,onAction}:{revision:number;onAction:SurfaceProps['onAction']}) {
  const result=useData('/api/v1/actions',revision);
  const [search,setSearch]=useState('');
  const actions:Data[]=result.data.actions||[];
  const rows=actions.filter(a=>`${a.id} ${a.title} ${a.group} ${a.summary}`.toLowerCase().includes(search.toLowerCase()));
  return <div className="ws-document"><h2>Providers and actions</h2><label>Search actions <input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Name, provider, or purpose"/></label><ErrorLine error={result.error}/><p>{result.loading?'Loading action catalog…':`${rows.length} of ${actions.length} actions`} · Availability comes from the catalog; advertised actions are not proof of a connected engine.</p><table className="ws-table"><thead><tr><th>Action</th><th>Provider / group</th><th>Status</th><th>Run</th></tr></thead><tbody>{rows.map(a=><tr key={a.id}><td>{a.title||a.id}<small>{a.summary||a.description||a.id}</small></td><td>{a.provider||a.group||'Not specified'}</td><td>{a.availability?.reason||a.status||(a.available===false?'Unavailable':'Advertised')}</td><td><button disabled={a.available===false} onClick={()=>onAction(a.id)}>Review…</button></td></tr>)}</tbody></table>{!result.loading&&!rows.length&&<p>No actions returned for this filter.</p>}<details><summary>Catalog provenance</summary><RecordView value={result.data}/></details></div>;
}
function LocalBytes({tab,hash,addr,revision,onSelect}:{tab:AnalysisTab;hash:string;addr:string;revision:number;onSelect:SurfaceProps['onSelect']}) {
  const [bytes,setBytes]=useState<Uint8Array>(),[strings,setStrings]=useState<string[]>([]),[error,setError]=useState(''),[search,setSearch]=useState(''),[metadata,setMetadata]=useState<Data>({});
  const offset=fileOffset(addr);
  useEffect(()=>{
    if(!['Hex','Strings','Info'].includes(tab))return;
    let live=true;
    const parser=createArtifactParserSession(()=>live);
    setBytes(undefined);setStrings([]);setError('');
    void projectStore.loadArtifact(hash).then(async artifact=>{
      if(!artifact)throw new Error('This artifact is not stored in this browser. Open the original file to restore it.');
      if(live){setBytes(new Uint8Array(artifact.bytes));setMetadata({name:artifact.name,format:artifact.format,architecture:artifact.architecture,sha256:artifact.hash,byteLength:artifact.bytes.byteLength});}
      if(tab==='Strings'){
        const result=await parser.run<ArtifactInspection>({id:crypto.randomUUID(),operation:'inspect-artifact',revisionId:hash,payload:artifact.bytes,limits:{maxArtifactBytes:512*1024*1024,timeoutMs:10000}});
        if(result.status!=='completed')throw new Error(result.failure?.message||result.status);
        if(live)setStrings(result.value?.strings||[]);
      }
    }).catch(e=>{if(live)setError(String(e.message));}).finally(()=>parser.terminate());
    return()=>{live=false;parser.terminate();};
  },[hash,tab,revision]);
  if(!['Hex','Strings','Info','Providers'].includes(tab))return <div className="ws-empty"><h2>Local metadata only</h2><p>The local parser does not produce functions, assembly, decompilation, or references. Open a recorded binary for analysis. Hex and Strings inspect stored bytes.</p></div>;
  const lines:string[]=[];
  if(tab==='Hex'&&bytes)for(let i=offset;i<Math.min(offset+1024,bytes.length);i+=16){const row=bytes.slice(i,i+16);lines.push(`${i.toString(16).padStart(8,'0')}  ${Array.from(row,b=>b.toString(16).padStart(2,'0')).join(' ').padEnd(47)}  ${Array.from(row,b=>b>=32&&b<=126?String.fromCharCode(b):'.').join('')}`);}
  return <div className="ws-document"><ErrorLine error={error}/><p>Local artifact · SHA256 <code>{hash}</code></p>{tab==='Hex'?<><p>File offsets (hexadecimal), not virtual addresses · {bytes?.length.toLocaleString()||'…'} bytes</p><pre className="ws-code">{lines.join('\n')||'No bytes at this offset.'}</pre><div className="ws-toolbar"><button disabled={!offset} onClick={()=>onSelect(hexPageSelection(addr,-1))}>Previous 1 KiB</button><button disabled={!bytes||offset+1024>=bytes.length} onClick={()=>onSelect(hexPageSelection(addr,1))}>Next 1 KiB</button></div></>:tab==='Strings'?<><label>Filter strings <input value={search} onChange={e=>setSearch(e.target.value)}/></label><p>Bounded local parser sample: at most 250 printable strings of at least 4 characters.</p><pre className="ws-code">{strings.filter(s=>s.toLowerCase().includes(search.toLowerCase())).join('\n')||'No strings returned.'}</pre></>:<><BinaryInfo data={metadata} selection={{slug:'',program:'',locator:'',addr:'',logicalId:'',binaryHash:hash}}/><p>Browser artifact parser · {bytes?.length.toLocaleString()||'Unknown'} bytes. Identity evidence only; no verified source or match receipt.</p></>}</div>;
}

export function ReferencesView({props}:{props:SurfaceProps}) {
  const [mode,setMode]=useState<'to'|'from'|'function'>('to'),[offset,setOffset]=useState(0);
  const result=useTool('get-references',referenceParams(props.selection.addr,mode,offset),props,Boolean(props.selection.program&&props.selection.addr));
  useEffect(()=>{if(result.error)props.notify(result.error,'error');},[result.error,props.notify]);
  const rows:Data[]=Array.isArray(result.data.references)?result.data.references.slice(offset,offset+80):[];
  const jump=(addr:string)=>props.onSelect({addr,logicalId:''});
  return <div className="ws-document"><h2>Cross references · {props.selection.addr||'Select an address'}</h2><div className="ws-toolbar"><label>Direction <select aria-label="Reference direction" value={mode} onChange={e=>{setMode(e.target.value as typeof mode);setOffset(0);}}><option value="to">To this address</option><option value="from">From this address</option><option value="function">Within this function</option></select></label><span role="status">{result.status||'Select a live program and address.'}</span></div><p>Includes recorded data, string/global, instruction, and call references. Select either endpoint to inspect it.</p><ErrorLine error={result.error}/><table className="ws-table"><thead><tr><th>From</th><th>To</th><th>Reference type</th><th>Containing function</th></tr></thead><tbody>{rows.map((row,i)=><tr key={i}><td>{row.fromAddress?<button onClick={()=>jump(String(row.fromAddress))}><code>{row.fromAddress}</code></button>:'Not recorded'}</td><td>{row.toAddress?<button onClick={()=>jump(String(row.toAddress))}><code>{row.toAddress}</code></button>:'Not recorded'}</td><td>{row.type||'Not recorded'}{row.indirect&&<small>Indirect · {row.via||row.note||'See provenance'}</small>}</td><td>{row.function||'Not recorded'}</td></tr>)}</tbody></table>{!rows.length&&<p>{result.status==='loaded'?'No references returned.':'No reference evidence loaded.'}</p>}<div className="ws-toolbar"><button disabled={!offset} onClick={()=>setOffset(n=>Math.max(0,n-80))}>Previous references</button><span>{rows.length?`${offset+1}–${offset+rows.length}`:'0'} references</span><button disabled={rows.length<80||offset>=720} onClick={()=>setOffset(n=>n+80)}>Next references</button></div><p className="muted">Browse up to 800 references. Narrow the address or direction for larger sets.</p><details><summary>Response and provenance {result.jobId&&`· Job ${result.jobId}`}</summary><RecordView value={result.data}/></details></div>;
}
