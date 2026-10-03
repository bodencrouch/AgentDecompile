import type {EntityActivity} from './activity';
import './dependency-graph.css';

/** Levels derive only from recorded edges. Unknown dependencies remain explicit. */
export function dependencyLevels(entities: EntityActivity[]) {
  const pending = new Map(entities.map(entity => [entity.id, entity]));
  const done = new Set<string>();
  const levels: EntityActivity[][] = [];
  while (pending.size) {
    const ready = [...pending.values()].filter(entity => entity.dependencies.every(id => !pending.has(id) || done.has(id)));
    if (!ready.length) break;
    ready.sort((a,b) => a.id.localeCompare(b.id));
    levels.push(ready);
    for (const entity of ready) {pending.delete(entity.id); done.add(entity.id);}
  }
  return {levels, cyclic: [...pending.values()].sort((a,b) => a.id.localeCompare(b.id))};
}

export function DependencyGraph({entities,connection,error}:{entities:EntityActivity[];connection:string;error:string}) {
  const {levels,cyclic}=dependencyLevels(entities);
  const names=new Map(entities.map(entity=>[entity.id,entity.name||entity.id]));
  function node(entity:EntityActivity) {return <article key={entity.id} className="dependency-node" data-state={entity.status}>
    <header><strong>{entity.name||entity.id}</strong><span>{entity.stage||'Stage not recorded'} · {entity.status}</span></header>
    {entity.dependencies.length ? <ul aria-label="Recorded prerequisites">{entity.dependencies.map(id=><li key={id}><span aria-hidden="true">↳ </span>{names.get(id)||id}{!names.has(id)&&' (outside this snapshot)'}</li>)}</ul> : <p>No recorded prerequisites</p>}
    {entity.action&&<p>{entity.action}</p>}
    {entity.error&&<p className="error">{entity.error}</p>}
    {entity.queue.reason&&<p>Waiting: {entity.queue.reason}</p>}
    {entity.nextFallback&&<p>Next: {entity.nextFallback}</p>}
    {entity.progress.kind==='measured'&&entity.progress.total!=null&&entity.progress.total>0&&<progress value={entity.progress.completed||0} max={entity.progress.total} aria-label={`${entity.name} measured work`}/>}
    <small>{entity.attempts==null?'Attempts not recorded':`${entity.attempts} recorded attempts`}</small>
  </article>;}
  return <section className="dependency-graph" aria-label="Recorded execution dependencies">
    <h3>Execution dependencies</h3><p>Edges name recorded prerequisites. Independent columns may run concurrently when ownership and capacity allow.</p>
    {error&&<p className="error" role="status">{error} · Showing the last received graph.</p>}
    {connection!=='live'&&<p role="status">Activity feed: {connection}</p>}
    {!entities.length&&<p>No dependency snapshot is available for this selection.</p>}
    <div className="dependency-levels">{levels.map((level,index)=><div className="dependency-level" key={index} aria-label={`Dependency depth ${index}`}>{level.map(node)}</div>)}</div>
    {!!cyclic.length&&<div role="status"><p>These recorded dependencies contain a cycle or depend on one; scheduling readiness is unknown.</p><div className="dependency-level">{cyclic.map(node)}</div></div>}
  </section>;
}
