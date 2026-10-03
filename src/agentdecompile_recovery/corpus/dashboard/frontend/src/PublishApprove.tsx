import {useState} from 'react';
import {API,request,type Selection} from './contracts';
import {ErrorLine,useData} from './ui';

// R50/U29: publishing is its own explicit, separately approved step. It
// never runs as a side effect of generating a report, and a confirmed
// approval never reads as a completed publish -- the gate-and-approve
// mechanism here stops short of any outbound network call.
export function PublishApprove({selection,revision}:{selection:Selection;revision:number}) {
  const [confirming,setConfirming]=useState(false);
  const [actionError,setActionError]=useState('');
  const [bump,setBump]=useState(0);
  const result=useData(selection.slug?`${API}/publish-status`:null,revision+bump);
  const status=result.data.status as string|undefined;
  const gate=result.data.gate||{};
  const blocked=gate.status==='blocked';

  async function approve() {
    setConfirming(false);
    setActionError('');
    try {
      await request(`${API}/publish-approve`,{method:'POST',body:JSON.stringify({confirm:true})});
      setBump(value=>value+1);
    } catch (error) {
      setActionError(String((error as Error).message));
    }
  }

  if(!selection.slug)return null;
  return <section className="publish-approve" aria-label="Publish approval">
    <h3>Approve publishing</h3>
    <ErrorLine error={result.error}/>
    {result.loading&&<p role="status">Reading publish gate…</p>}
    {!result.loading&&!result.error&&blocked&&<p>Publish is disabled. {(gate.blockedBinaryIds||[]).length} binary id(s) failed the count-reconciliation gate: {JSON.stringify(gate.blockedDetail)}</p>}
    {!result.loading&&!result.error&&!blocked&&status==='approved_unsent'&&<p><strong>{result.data.label}</strong></p>}
    {!result.loading&&!result.error&&!blocked&&status==='approvable'&&!confirming&&
      <button type="button" onClick={()=>setConfirming(true)}>Approve publish</button>}
    {!result.loading&&!result.error&&!blocked&&status==='approvable'&&confirming&&
      <div role="group" aria-label="Confirm publish approval">
        <p>Confirm publish approval. This does not send anything.</p>
        <button type="button" onClick={approve}>Confirm</button>
        <button type="button" onClick={()=>setConfirming(false)}>Cancel</button>
      </div>}
    <ErrorLine error={actionError}/>
  </section>;
}
