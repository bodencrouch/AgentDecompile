import {useEffect, useState} from 'react';
import {API, emptySelection, request, type Data} from '../contracts';
import {DependencyGraph} from '../DependencyGraph';
import {PreparationProgress, selectPreparation} from '../PreparationActivity';
import {useEntityActivity} from '../activity';
import {usePreparationRuns} from '../usePreparationRuns';
import './spectator.css';

const noop = () => {};

/** Read-only spectator session (R46/AE16).
 *
 * Mirrors the operator's current preparation/activity state over the same
 * local activity feed the operator's own dock uses. There is no selection
 * control, no action dialog and no write-capable chrome anywhere in this
 * component — every control the operator's workstation offers is simply
 * absent here, not disabled, so there is nothing for a spectator to bypass
 * on this side even before the backend's own write rejection applies.
 */
export function SpectatorView() {
  const [heartbeatError, setHeartbeatError] = useState('');
  const [revoked, setRevoked] = useState(false);
  const preparation = usePreparationRuns();
  const graph = useEntityActivity('', '', '', true);
  const run = selectPreparation(preparation.runs, emptySelection);
  useEffect(() => {
    let alive = true;
    async function beat() {
      try {
        const data: Data = await request(`${API}/spectator/touch`, { method: 'POST' });
        if (!alive) return;
        if (data.ok) { setHeartbeatError(''); setRevoked(false); }
        else setRevoked(true);
      } catch (e) {
        if (!alive) return;
        // A 403 from the write guard means this token was revoked or
        // spectating was disabled; request() throws on non-2xx.
        if (/\(403\)/.test(String(e))) setRevoked(true);
        else setHeartbeatError(e instanceof Error ? e.message : String(e));
      }
    }
    void beat();
    const timer = window.setInterval(beat, 15000);
    return () => { alive = false; window.clearInterval(timer); };
  }, []);
  return <div className="spectator-view" aria-label="Spectator session (read-only)">
    <header><strong>AgentDecompile — spectating</strong><span role="status">Read-only. No write action is available in this session.</span></header>
    {revoked && <p role="alert">Spectating was disabled or this token was revoked. This view can no longer follow the operator's session.</p>}
    {!revoked && heartbeatError && <p role="alert">{heartbeatError}</p>}
    {!revoked && <>
      <DependencyGraph entities={graph.entities} connection={graph.connection} error={graph.error}/>
      {run
        ? <PreparationProgress run={run} selection={emptySelection} notify={noop} error={preparation.error} loading={preparation.loading} lastConnectedAt={preparation.lastConnectedAt} now={preparation.now} readOnly/>
        : <p role="status">{preparation.loading ? 'Reading preparation state…' : 'No active preparation to follow yet.'}</p>}
    </>}
  </div>;
}
