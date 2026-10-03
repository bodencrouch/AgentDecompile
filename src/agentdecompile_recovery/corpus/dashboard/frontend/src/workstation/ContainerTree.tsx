import {useEffect,useState} from 'react';
import type {Selection} from '../contracts';
import {projectStore} from '../storage/projectStore';
import {createArtifactParserSession} from '../workers/artifactParser';
import type {ArtifactInspection,ArtifactNode} from '../workers/artifactParser.worker';
import {ErrorLine} from '../ui';

export function ContainerTree({selection,revision,onSelect}:{selection:Selection;revision:number;onSelect:(patch:Partial<Selection>)=>void}) {
  const [nodes,setNodes]=useState<ArtifactNode[]>([]),[error,setError]=useState(''),[loading,setLoading]=useState(false);
  useEffect(()=>{
    let alive=true;const parser=createArtifactParserSession(id=>alive&&id===selection.binaryHash);
    setNodes([]);setError('');setLoading(Boolean(selection.binaryHash));
    if(selection.binaryHash)void projectStore.loadArtifact(selection.binaryHash).then(async artifact=>{
      if(!artifact)throw new Error('Original artifact bytes are not stored in this browser. Open the local file to inspect its format tree.');
      const result=await parser.run<ArtifactInspection>({id:crypto.randomUUID(),operation:'inspect-artifact',revisionId:selection.binaryHash!,payload:artifact.bytes,limits:{maxArtifactBytes:512*1024*1024,timeoutMs:10000}});
      if(result.status!=='completed')throw new Error(result.failure?.message||result.status);
      if(alive)setNodes(result.value?.structure||[]);
    }).catch(cause=>{if(alive)setError(String(cause.message||cause));}).finally(()=>{if(alive)setLoading(false);parser.terminate();});
    return()=>{alive=false;parser.terminate();};
  },[selection.binaryHash,revision]);
  function node(row:ArtifactNode):React.ReactNode {return <li key={row.id}>{row.children?.length?<details open><summary>{row.name} · {row.size} bytes</summary><ul>{row.children.map(node)}</ul></details>:<><strong>{row.name}</strong> · {row.kind} · {row.size} bytes {row.offset===null?<span>No stored file bytes</span>:<button disabled={Boolean(selection.slug||selection.program)} title={selection.slug||selection.program?"File offsets cannot replace a live program address":undefined} onClick={()=>onSelect({addr:`0x${row.offset!.toString(16)}`,lastFunctionAddr:''})}>Select file offset 0x{row.offset.toString(16)}</button>}</>}</li>;}
  return <div className="ws-document"><h2>Artifact format tree</h2><p>Bounded local ELF and PE section metadata from the existing parser worker. Offsets refer to file bytes. This does not establish function identity or runtime readiness.</p><ErrorLine error={error}/>{loading&&<p role="status">Reading section structure…</p>}{!selection.binaryHash&&<p>Open a local ELF or PE artifact to inspect its format tree. Archive expansion is not supported.</p>}<ul>{nodes.map(node)}</ul>{!loading&&!error&&selection.binaryHash&&!nodes.length&&<p>No section structure was returned.</p>}</div>;
}
