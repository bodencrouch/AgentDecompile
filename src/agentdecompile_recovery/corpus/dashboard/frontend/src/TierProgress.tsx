import {API,type Data,type Selection} from './contracts';
import {ErrorLine,useData} from './ui';
import './tier-progress.css';

export function tierSegments(report:Data,provider:Data={}) {
  const total=report.measures?.total_functions;
  const verified=report.tiers?.['verified-byte-exact']?.functions;
  const advisory=report.tiers?.['advisory-ghidra']?.functions;
  if(![total,advisory].every(value=>Number.isSafeInteger(value)&&value>=0)||advisory>total)return null;
  const verifiedAvailable=provider.status==='connected'&&Number.isSafeInteger(verified)&&verified>=0&&verified+advisory<=total;
  return {total,verified:verifiedAvailable?verified:null,advisory,verifiedWidth:verifiedAvailable&&total?verified*100/total:0,advisoryWidth:total?advisory*100/total:0};
}
export function TierProgress({selection,revision}:{selection:Selection;revision:number}) {
  const version=selection.binaryHash||'';
  const params=new URLSearchParams({slug:selection.slug,version,corpusIdentity:selection.corpusIdentity||''});
  const result=useData(selection.slug?`${API}/progress-report?${params}`:null,revision);
  const report=result.data.report||{},provider=result.data.matrix_projection?.provider||{},basis=result.data.matrix_projection?.binary;
  const exact=Boolean(basis&&basis.slug===selection.slug&&basis.version===version&&basis.content_sha256===version&&result.data.matrix_projection?.corpus_identity===(selection.corpusIdentity||''));
  const segments=exact&&!result.loading&&!result.error?tierSegments(report,provider):null;
  if(!selection.slug)return null;
  return <section className="tier-progress" aria-label="Separate verified and advisory progress"><h3>Recorded source coverage</h3>
    <ErrorLine error={result.error}/>{result.loading&&<p role="status">Reading inventory accounting…</p>}
    {segments&&<><div className="tier-track" role="img" aria-label={`${segments.verified===null?'Verified count unavailable':segments.verified+' accepted byte-exact receipts'}; ${segments.advisory} advisory source records; ${segments.total} inventory members`}>{segments.verified!==null&&<span className="tier-verified" style={{width:`${segments.verifiedWidth}%`}}/>}<span className="tier-advisory" style={{width:`${segments.advisoryWidth}%`}}/></div>
      <p>{segments.verified===null?<strong>Verified unavailable</strong>:<><strong>{segments.verified}</strong> accepted byte-exact receipts</>} · <strong>{segments.advisory}</strong> advisory source records · {segments.total} inventory members</p></>}
    {!result.loading&&!result.error&&!segments&&<p>No reconciled tier counts are available.</p>}
    {!result.loading&&provider.reason&&<p>{provider.reason}</p>}
    {!result.loading&&!result.error&&report.accounting&&<p>Member accounting: {report.accounting.status}. Byte extents: {report.accounting.byte_accounting}. Function counts do not establish whole-image parity.</p>}
    {!result.loading&&!result.error&&report.binary&&<small>{report.binary.slug} · version {report.binary.version} · report {report.report_sha256}</small>}
  </section>;
}
