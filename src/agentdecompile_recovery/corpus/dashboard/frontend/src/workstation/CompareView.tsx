import {API,query,type Data,type Selection} from '../contracts';
import {ErrorLine} from '../ui';
import {useFunctionEvidence} from '../SourceEditor';
import {DiffEvidence} from '../views/DiffEvidence';
import {diffMismatches,diffReceipts} from '../integration/boundaries';

/** Compare tab body. Reads the same recorded proof fields as the matching surface. */
export function ComparePanel({detail,loading,error,hasFunction,onSelect}:{detail:Data;loading:boolean;error:string;hasFunction:boolean;onSelect:(patch:Partial<Selection>)=>void}) {
  if(!hasFunction)return <div className="ws-document"><p role="status">Select a function to see its recorded byte diff.</p></div>;
  return <div className="ws-document">
    <ErrorLine error={error}/>
    {loading&&<p role="status">Reading recorded diff…</p>}
    <DiffEvidence mismatches={diffMismatches(detail)} receipts={diffReceipts(detail)} onNavigate={mismatch=>{if(mismatch.address)onSelect({addr:mismatch.address});}}/>
    <p className="muted">This shows recorded objdiff receipts for the selected function. It does not run a new diff.</p>
  </div>;
}

/** Fetches only while the tab is visible, so a retained hidden panel does not poll. */
export function CompareView({active=true,selection,revision,enabled,onSelect}:{active?:boolean;selection:Selection;revision:number;enabled:boolean;onSelect:(patch:Partial<Selection>)=>void}) {
  const hasFunction=Boolean(selection.addr);
  const detail=useFunctionEvidence(active&&enabled&&hasFunction?`${API}/function?${query(selection)}`:null,revision);
  if(!enabled)return <div className="ws-document"><p role="status">Open a recorded binary to see its byte diff.</p></div>;
  return <ComparePanel detail={detail.data} loading={detail.loading} error={detail.error} hasFunction={hasFunction} onSelect={onSelect}/>;
}
