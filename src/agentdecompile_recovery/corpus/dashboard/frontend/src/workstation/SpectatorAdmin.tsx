import {useEffect, useState} from 'react';
import {API, request, type Data} from '../contracts';
import {ErrorLine} from '../ui';

/** Operator-side spectator controls (R46/AE16).
 *
 * Spectating starts disabled; enabling it and creating a token are both
 * explicit operator actions here. A created token is shown exactly once —
 * this component never re-displays a past token, so sharing it is a
 * one-time, deliberate act, matching the token's own "shown once" design.
 */
export function SpectatorAdmin() {
  const [status, setStatus] = useState<Data>({});
  const [token, setToken] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function refresh() {
    try { setStatus(await request(`${API}/spectator/status`)); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }
  useEffect(() => { void refresh(); const timer = window.setInterval(() => void refresh(), 5000); return () => window.clearInterval(timer); }, []);
  async function toggle(next: boolean) {
    if (busy) return; setBusy(true); setError(''); setToken('');
    try { setStatus(await request(`${API}/spectator/enable`, { method: 'POST', body: JSON.stringify({ enabled: next }) })); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }
  async function createToken() {
    if (busy) return; setBusy(true); setError('');
    try { const result = await request(`${API}/spectator/token`); setToken(String(result.token || '')); await refresh(); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }
  async function revokeAll() {
    if (busy) return; setBusy(true); setError(''); setToken('');
    try { setStatus(await request(`${API}/spectator/revoke-all`, { method: 'POST' })); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }
  const link = token ? `${location.origin}${location.pathname}?spectate=${encodeURIComponent(token)}` : '';
  return <div className="spectator-admin">
    <p>Spectating is local, opt-in, and off by default. A spectator session mirrors this workspace's current preparation state read-only; the backend rejects any write request carrying a spectator token, independent of what this dialog or the spectator's own view allows.</p>
    <label><input type="checkbox" checked={Boolean(status.enabled)} disabled={busy} onChange={e => void toggle(e.target.checked)}/> Allow a local spectator to follow this session</label>
    <p role="status">{status.enabled ? `${Number(status.activeViewers || 0)} active viewer(s) · ${Number(status.tokenCount || 0)} issued token(s)` : 'Spectating is off.'}</p>
    {Boolean(status.enabled) && <>
      <button type="button" disabled={busy} onClick={() => void createToken()}>Create spectator link…</button>
      {link && <p className="spectator-link">Share this link once — it will not be shown again: <code>{link}</code> <button type="button" onClick={() => { void navigator.clipboard.writeText(link).catch(() => {}); }}>Copy</button></p>}
      <button type="button" disabled={busy || !Number(status.tokenCount || 0)} onClick={() => void revokeAll()}>Revoke all spectator tokens</button>
    </>}
    <ErrorLine error={error}/>
  </div>;
}
