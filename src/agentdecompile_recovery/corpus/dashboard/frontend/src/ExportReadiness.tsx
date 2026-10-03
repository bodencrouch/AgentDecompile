import {useState} from 'react';
import {API,query,type Data,type Selection} from './contracts';
import {ErrorLine,useData} from './ui';

export function ExportReadiness({selection,revision}:{selection:Selection;revision:number}) {
  const result=useData(`${API}/exports?${query(selection)}`,revision);
  const [filter,setFilter]=useState('');
  const bundles:Data[]=Array.isArray(result.data.bundles)?result.data.bundles:[];
  return <section aria-label="Export readiness" className="export-readiness">
    <h3>Export bundles</h3>
    <p>Pipeline outputs from a declared corpus basis. Locator readiness, supported runtime operations and recovered-source parity have separate evidence.</p>
    <ErrorLine error={result.error}/>
    {result.loading&&<p role="status">Reading verified export manifests…</p>}
    {!result.loading&&!result.error&&!bundles.length&&<p role="status">{result.data.reason||'No complete export bundle is recorded for this selection. There is nothing to download yet.'}</p>}
    {!!bundles.length&&<label>Find entity readiness <input type="search" value={filter} onChange={event=>setFilter(event.target.value)} placeholder="Entity, build or status"/></label>}
    {bundles.map(bundle=><article key={bundle.bundle_sha256}>
      <h4>Bundle <code>{String(bundle.bundle_sha256).slice(0,16)}</code></h4>
      {(bundle.readiness?.builds||[]).map((build:Data)=><p key={build.build}>{build.summary}</p>)}
      <details><summary>Per-entity locator readiness</summary>
        <table className="ws-table"><thead><tr><th>Entity</th><th>Build</th><th>Status</th><th>Reason</th></tr></thead><tbody>
          {(bundle.readiness?.entities||[]).filter((row:Data)=>!filter||`${row.entity} ${row.build} ${row.status}`.toLowerCase().includes(filter.toLowerCase())).map((row:Data)=><tr key={`${row.entity}:${row.build}`}><td>{row.entity}</td><td>{row.build}</td><td><span data-readiness={row.status}>{row.status}</span></td><td>{row.reason}</td></tr>)}
        </tbody></table>
      </details>
      <ul>{(bundle.artifacts||[]).map((artifact:Data)=><li key={artifact.path}><a href={artifact.href} download>{artifact.path}</a> · {artifact.size} bytes <small>SHA-256 {artifact.sha256}</small></li>)}</ul>
      {(bundle.scope_receipts||[]).map((receipt:Data)=><p key={receipt.artifact}>{receipt.artifact}: {receipt.status} · {receipt.reason}</p>)}
    </article>)}
    {(result.data.errors||[]).map((error:Data|string,index:number)=><ErrorLine key={index} error={typeof error==='string'?error:`${error.bundle||'Bundle'}: ${error.reason||'Unavailable'}`}/>)}
  </section>;
}
