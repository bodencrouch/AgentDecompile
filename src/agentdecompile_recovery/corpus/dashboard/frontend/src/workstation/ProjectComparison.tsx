import {useEffect,useRef,useState} from 'react';
import {API,request,type Data,type Selection} from '../contracts';
import {RecordView} from '../ui';
import {coverageRows,matrixTierCell} from './coverageMatrix';
import './project-comparison.css';

/** Explicit, bounded reads for the selected identity's project members only. */
export function ProjectComparison({selection,builds,members,name,canInspect,onInspect}:{selection:Selection;builds:Data[];members:Data[];name:string;canInspect:boolean;onInspect:(member:Data)=>void}) {
  const [loaded,setLoaded]=useState(false),[loading,setLoading]=useState(false);
  const [reports,setReports]=useState<Record<string,Data>>({});
  const controller=useRef<AbortController|undefined>(undefined);
  useEffect(()=>()=>controller.current?.abort(),[]);
  const rows=coverageRows(members,builds).filter(row=>row.inLibrary);
  const hashOf=(binary:Data)=>String(binary.content_sha256||binary.contentSha256||binary.sha256||'');
  async function load(){
    controller.current?.abort();
    const attempt=new AbortController();controller.current=attempt;
    setLoaded(true);setLoading(true);setReports({});
    // Missing membership/hash remains unknown; do not turn it into a corpus scan.
    const queue=rows.filter(row=>row.members.length&&row.binary?.slug&&/^[a-f0-9]{64}$/.test(hashOf(row.binary)));
    let next=0;
    async function worker(){
      while(next<queue.length&&!attempt.signal.aborted){
        const binary=queue[next++].binary!;
        const slug=String(binary.slug),version=hashOf(binary);
        const params=new URLSearchParams({slug,version,corpusIdentity:selection.corpusIdentity!,logicalId:selection.logicalId});
        let report:Data;
        try{report=await request(`${API}/progress-report?${params}`,{signal:AbortSignal.any([attempt.signal,AbortSignal.timeout(15000)])});}
        catch(error){report={error:String(error)};}
        if(!attempt.signal.aborted)setReports(previous=>({...previous,[slug]:report}));
      }
    }
    await Promise.all([worker(),worker()]);
    if(!attempt.signal.aborted)setLoading(false);
  }
  return <section className="project-comparison" aria-label="Project-wide function comparison">
    <header><div><h3>Compare this function across the project</h3><p>{name||`Logical identity ${selection.logicalId}`}</p></div><button type="button" disabled={loading||!builds.length||!selection.logicalId||!selection.corpusIdentity} onClick={()=>void load()}>{loading?'Loading scoped evidence…':loaded?'Reload project comparison':'Load project comparison'}</button></header>
    <p>Loads recorded tier evidence only for this identity's project members. No analysis or matching is started.</p>
    {!loaded?<p className="muted">The comparison is not loaded. Project bindings above define which builds will appear.</p>:<>
      <div className="project-comparison-scroll" role="region" aria-label="Aligned evidence across project builds" tabIndex={0}>
        <table><caption>One logical function, each recorded project build. Scroll horizontally to compare builds.</caption>
          <thead><tr><th scope="col">Recorded evidence</th>{rows.map(row=><th scope="col" key={row.key}>{row.build}<small>{[row.binary?.platform,row.binary?.architecture,row.binary?.format].filter(Boolean).join(' · ')||'Build metadata not recorded'}</small><code>{String(row.binary?.slug||'')}</code></th>)}</tr></thead>
          <tbody>
            <tr><th scope="row">Function counterparts</th>{rows.map(row=><td key={row.key}>{row.members.length?<ul>{row.members.map((member,index)=><li key={`${member.slug}:${member.addr}:${index}`}><button type="button" disabled={!canInspect||!member.slug||!member.addr} onClick={()=>onInspect(member)} title="Inspect this recorded counterpart"><code>{String(member.addr||'Address unavailable')}</code></button></li>)}</ul>:<><strong>Unknown</strong><small>No member returned; absence is not established.</small></>}{row.members.length>1&&<small>Multiple counterparts returned; correspondence is ambiguous.</small>}</td>)}</tr>
            <tr><th scope="row">Membership basis</th>{rows.map(row=><td key={row.key}>{row.members.length?row.members.map((member,index)=><details key={`${member.slug}:${member.addr}:${index}`}><summary>{String(member.method||'Method not recorded')} · {String(member.addr||'No address')}</summary><p>Confidence {String(member.confidence??'not recorded')}</p><RecordView value={member.evidence??{status:'Evidence not supplied'}}/></details>):'Not supplied'}</td>)}</tr>
            <tr><th scope="row">Recovery acceptance</th>{rows.map(row=>{
              const binary=row.binary!,slug=String(binary.slug||''),hash=hashOf(binary);
              const report=reports[slug];
              const tier=matrixTierCell(report,{logicalId:selection.logicalId,corpusIdentity:selection.corpusIdentity!,slug,contentSha256:hash,expectedVersion:hash});
              const unavailable=!row.members.length?'No member returned; no tier read requested.':!/^[a-f0-9]{64}$/.test(hash)?'Exact build hash unavailable; no tier read requested.':!report&&loading?'Reading scoped report…':tier.reason||tier.verified.reason;
              return <td key={row.key}>{tier.status==='available'&&tier.verified.status==='available'?<><strong>{tier.verified.functions?`${tier.verified.functions} in accepted recovery tier`:'No accepted recovery members in this report'}</strong><small>Not a cross-build equivalence or whole-image claim.</small><details><summary>Report basis</summary><code>{tier.basis}</code></details></>:<><strong>Unknown</strong><small>{unavailable||'Acceptance unavailable.'}</small></>}</td>;
            })}</tr>
            <tr><th scope="row">Relationship verdict</th>{rows.map(row=><td key={row.key}><strong>Unknown</strong><small>No scoped absent, candidate, accepted-counterpart or divergent verdict is supplied by this membership API.</small></td>)}</tr>
          </tbody>
        </table>
      </div>
      <p className="project-comparison-boundary">Unknown is not absent. Membership, confidence and recovery acceptance do not establish a byte match between builds. Candidate, accepted-counterpart and divergent states require their own recorded relationship verdicts.</p>
    </>}
  </section>;
}
