import type {Data} from '../contracts';
import {stageDisplayProgress,stageProgressLabel} from '../preparationProgress';
import './work-activity.css';

export type ActivityOperation={job:Data;title:string;target:string;active:boolean};

function recordedTime(value:unknown):string|undefined {
  if(typeof value!=='number'||!Number.isFinite(value)||value<=0)return;
  const date=new Date(value*1000);
  return Number.isFinite(date.getTime())?date.toISOString():undefined;
}

/** Projection of the existing job index; no polling, execution or proof inference. */
export function WorkActivity({operations,lastReceivedAt,error,onJobs}:{operations:ActivityOperation[];lastReceivedAt:number;error:string;onJobs:()=>void}) {
  return <section className="ws-work-activity" aria-label="Recorded workspace operations">
    <header><div><strong>Recorded work</strong><small>Active states across the workspace; recent results for this selection.</small></div><button onClick={onJobs}>Job details</button></header>
    <p className="ws-work-freshness">{lastReceivedAt?<>{error?'Connection unavailable · last received':'Last received'} <time dateTime={new Date(lastReceivedAt).toISOString()}>{new Date(lastReceivedAt).toLocaleTimeString()}</time>. This is a read timestamp, not a worker heartbeat.</>:error?'The job index is unavailable; no recorded snapshot has been received.':'Reading the job index…'}</p>
    {operations.length>0?<ol className="ws-work-lanes">{operations.map(({job,title,target,active})=>{
      const progress=stageDisplayProgress(job).secondary;
      const uncertain=Boolean(job.ownershipUnresolved||job.ownerUnavailable||job.historyOnly);
      const stamp=recordedTime(job.finishedAt||job.startedAt||job.createdAt);
      const stampLabel=job.finishedAt?'Finished':job.startedAt?'Started':'Created';
      const context=job.context||{};
      const locator=job.params?.locator||context.locator;
      return <li key={String(job.id)} className={uncertain?'uncertain':active?'active':'recorded'}>
        <div className="ws-work-state"><strong>{String(job.status||'State unavailable')}</strong>{stamp&&<time dateTime={stamp} title={`${stampLabel} ${stamp}`}>{stampLabel} {new Date(stamp).toLocaleTimeString()}</time>}</div>
        <div className="ws-work-operation"><strong>{title}</strong><code>{target}</code>{locator&&<small>{String(locator)}</small>}
          {progress?<div className="ws-work-counter"><progress value={progress.completed} max={progress.total} aria-label={`Recorded work: ${stageProgressLabel(progress)}`}/><span>{stageProgressLabel(progress)}</span>{progress.currentTarget&&<code>{String(progress.currentTarget)}</code>}</div>:<small>No measured work counter recorded.</small>}
          {uncertain&&<p className="ws-work-caution">{job.historyOnly?'Historical record — not evidence of a running worker.':job.ownershipUnresolved?'Worker ownership unresolved — recorded state is not confirmed execution.':'Worker owner unavailable — recorded state may be stale.'}</p>}
          {job.error&&<details><summary>Recorded diagnostic</summary><pre>{String(job.error)}</pre></details>}
          <small className="ws-work-id">Job {String(job.id)}</small>
        </div>
      </li>;
    })}</ol>:lastReceivedAt>0&&<p>No active states or recent selection results in the received index. Job details includes recorded history.</p>}
    {operations.length>0&&<p className="ws-work-proof">Work counters and successful operations do not establish recovered-source or byte-match proof.</p>}
  </section>;
}
