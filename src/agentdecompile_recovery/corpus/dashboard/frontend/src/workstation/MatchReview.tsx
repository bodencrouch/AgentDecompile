import {useCallback, useEffect, useRef, useState} from 'react';
import {API, request, type Data, type Notify} from '../contracts';

/*
 * One review client for the workstation and the full app. The static
 * /dashboard window (static/workbench-app.js) mirrors the same contract:
 *   GET  {API}/match-review?after_id=N&limit=M -> rows[{match, binaries, token}], total, nextAfterId, selection
 *   POST {API}/match-decide-batch {selection, entries[{matchId, token, decision}]} -> 202 {job_id, pending}
 *   GET  /api/v1/jobs/{id} -> job.status, job.log (JSON result of the decision)
 * A 202 is only a pending job. A row counts as decided only when the job ends
 * "ok" with acceptance "review-decision-only" and lists that match. The
 * backend cannot undo a decision, so every decision is confirmed first.
 */
interface ReviewRow {match: Data; binaries: Data[]; token: string}
interface ReviewPage {rows: ReviewRow[]; total: number; nextAfterId: number|null; selection: string}
interface MethodAvailability {channel: string; label: string; state: string; reason: string; enabled?: boolean; availability?: string; providerReason?: string}
interface AvailabilityRow {matchId: number; srcBinary: number; dstBinary: number; srcAddr: number; run: string; channels: MethodAvailability[]}
interface ReviewDecision {matchId: number; status: string; revision: number}
/** A submitted decision whose result is not known yet. Its rows stay locked. */
interface OpenJob {id: string; tokens: string[]; matchIds: number[]}
type Decision = 'accept'|'reject';
const EMPTY: ReviewPage = {rows: [], total: 0, nextAfterId: null, selection: ''};
const PAGE_SIZE = 50;

const REVIEW_ERRORS: Record<string, string> = {
  stale_basis: 'A row changed after you loaded it, or was already decided. Nothing was saved. Refresh the rows and decide again.',
  context_changed: 'The selected database changed after these rows loaded. Nothing was saved. Refresh the rows and decide again.',
  busy: 'The database is busy. Nothing was saved. Try again shortly.',
  unavailable: 'The review database is unavailable. Nothing was saved.',
  review_schema_required: 'This database has no review tables yet. Run its schema migration first.',
  review_schema_corrupt: 'The review tables in this database are damaged. Nothing was saved.',
  schema_required: 'This database needs a schema migration before review.',
  duplicate_match: 'The same match was submitted twice. Nothing was saved.',
  malformed_request: 'The server refused the request format. Refresh the rows and try again.',
  malformed_context: 'The request had no current selection. Refresh the rows and try again.',
  request_too_large: 'Too many rows in one request. Decide fewer rows at a time.',
  unsafe_database_alias: 'The review database path is a link or has extra hard links. Review is refused for it.',
  corrupt_basis: 'One review row has damaged data, so the whole review list could not load. Nothing was saved.',
  basis_too_large: 'One review row has too much recorded data, so the whole review list could not load. Nothing was saved.',
  cancelled: 'The decision was cancelled before it ran. Nothing was saved.',
  ranked_cursor_retired: 'This link used the old score-ranked page cursor. Rows are now listed by match ID.',
};
const REFRESH_CODES = new Set(['stale_basis', 'context_changed', 'malformed_context', 'ranked_cursor_retired']);

/** Plain text for a review error code. Unknown text, such as an owner refusal, passes through. */
export function reviewErrorText(code: unknown): string {
  const text = String(code ?? '').trim();
  return REVIEW_ERRORS[text] || text || 'The review request failed.';
}

/** The job ended without saying whether it saved. The server may have committed. */
export class ReviewOutcomeUnknown extends Error {}
/** The job ended with a refusal. Nothing was saved. */
export class ReviewRefused extends Error {
  constructor(readonly code: string) {super(reviewErrorText(code));}
  get refreshRequired() {return REFRESH_CODES.has(this.code);}
}

function delay(signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const abort = () => {clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError'));};
    const timer = setTimeout(() => {signal.removeEventListener('abort', abort); resolve();}, 750);
    signal.addEventListener('abort', abort, {once: true});
    if (signal.aborted) abort();
  });
}

/** Poll one decision job. Returns its decisions, or null if it is still running. */
export async function observeReviewJob(jobId: string, signal: AbortSignal): Promise<ReviewDecision[]|null> {
  for (let attempt = 0; attempt < 40; attempt++) {
    const response = await fetch(`/api/v1/jobs/${encodeURIComponent(jobId)}`, {signal, cache: 'no-store'});
    if (response.status === 404) {
      throw new ReviewOutcomeUnknown('The server no longer knows this decision job. Refresh the rows to see whether it was saved.');
    }
    let body: Data = {};
    try {body = await response.json();} catch {body = {};}
    if (!response.ok) throw new Error(`Could not read the decision job (${response.status}). Check its result again.`);
    const job: Data = body.job || {};
    if (['ok', 'failed', 'cancelled', 'interrupted'].includes(job.status)) {
      let result: Data = {};
      try {result = JSON.parse(job.log || '{}');} catch {result = {};}
      if (job.status === 'ok' && result.ok === true && result.acceptance === 'review-decision-only'
          && Array.isArray(result.decisions)) return result.decisions as ReviewDecision[];
      if (typeof result.error === 'string' && result.error) throw new ReviewRefused(result.error);
      throw new ReviewOutcomeUnknown(`The decision job ended as "${job.status}" without a result. It may have been saved. Refresh the rows to see the current state.`);
    }
    await delay(signal);
  }
  return null;
}

/** Submit exact observed rows. Returns the job ID of the pending decision. */
export async function submitReviewDecision(rows: ReviewRow[], selection: string, decision: Decision,
                                           signal?: AbortSignal): Promise<string> {
  if (!selection || !rows.length || rows.some(row => !Number.isSafeInteger(row.match.id) || !row.token)) {
    throw new ReviewRefused('malformed_context');
  }
  let reply: Data;
  try {
    reply = await request(`${API}/match-decide-batch`, {
      method: 'POST', signal,
      body: JSON.stringify({selection, entries: rows.map(row => ({matchId: row.match.id, token: row.token, decision}))}),
    });
  } catch (reason) {
    if (reason instanceof DOMException) throw reason;
    const message = reason instanceof Error ? reason.message : String(reason);
    throw REVIEW_ERRORS[message] ? new ReviewRefused(message) : new Error(message);
  }
  const jobId = reply.job_id || reply.job?.id;
  if (!jobId) throw new Error('The server returned no decision job. Refresh the rows before you decide again.');
  return String(jobId);
}

function outcomeText(decisions: ReviewDecision[]): string {
  return decisions.map(item => item.status === 'verify'
    ? `Match ${item.matchId} moved to verification.`
    : item.status === 'rejected' ? `Match ${item.matchId} rejected.`
    : `Match ${item.matchId} is now "${item.status}".`).join(' ');
}

function confirmText(rows: ReviewRow[], decision: Decision): string {
  const ids = rows.map(row => String(row.match.id));
  const list = ids.length > 6 ? `${ids.slice(0, 6).join(', ')} and ${ids.length - 6} more` : ids.join(', ');
  const noun = rows.length === 1 ? 'match' : `${rows.length} matches`;
  return decision === 'accept'
    ? `Move ${noun} (${list}) to verification? This cannot be undone here.`
    : `Reject ${noun} (${list})? This cannot be undone here.`;
}

const address = (value: unknown) => typeof value === 'number' && Number.isSafeInteger(value)
  ? `0x${value.toString(16)}` : String(value ?? 'Unavailable');

export function MatchReview({active, revision, heading = true, notify}:
    {active: boolean; revision: number; heading?: boolean; notify?: Notify}) {
  const [page, setPage] = useState<ReviewPage>(EMPTY);
  const [view, setView] = useState<'review'|'fleet'>('review');
  const [pairFilter, setPairFilter] = useState('');
  const [scoreFloor, setScoreFloor] = useState('');
  const [methods, setMethods] = useState<Record<number, AvailabilityRow>>({});
  const [methodsStatus, setMethodsStatus] = useState('');
  const [afterId, setAfterId] = useState(0);
  const [history, setHistory] = useState<number[]>([]);
  const [refresh, setRefresh] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [watching, setWatching] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [jobs, setJobs] = useState<OpenJob[]>([]);
  const [confirm, setConfirm] = useState<{rows: ReviewRow[]; decision: Decision}|null>(null);
  const observation = useRef<AbortController|null>(null);
  const confirmRef = useRef<HTMLDivElement|null>(null);
  /* Tracks mount state across an await so a resumed callback (e.g. send())
     does not touch state or start a fresh observe() after unmount. A new
     AbortController created after unmount would not be aborted by the
     cleanup below, so this cannot be replaced by the abort signal alone. */
  const mountedRef = useRef(true);

  useEffect(() => () => {observation.current?.abort(); mountedRef.current = false;}, []);
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    setLoading(true);
    request<ReviewPage>(`${API}/match-review?after_id=${afterId}&limit=${PAGE_SIZE}`, {signal: controller.signal})
      .then(data => {
        if (controller.signal.aborted) return;
        setPage(data); setError(''); setConfirm(null);
        // Keep checked rows that are still on this page with the same token.
        const present = new Set((data.rows || []).map(row => row.token));
        setSelected(old => new Set([...old].filter(token => present.has(token))));
      })
      .catch(reason => {
        if (controller.signal.aborted) return;
        setPage(EMPTY); setSelected(new Set()); setConfirm(null);
        setError(reviewErrorText(reason?.message || reason));
      })
      .finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [active, revision, refresh, afterId]);

  useEffect(() => {
    setMethods({});
    if (!active || !page.rows.length || !page.selection) {setMethodsStatus(''); return;}
    const controller = new AbortController();
    setMethodsStatus('Loading recorded method availability…');
    const ids = page.rows.map(row => row.match.id).join(',');
    request<{rows: AvailabilityRow[]}>(`${API}/matching-availability?match_ids=${encodeURIComponent(ids)}&selection=${encodeURIComponent(page.selection)}`, {signal: controller.signal})
      .then(data => {
        if (controller.signal.aborted) return;
        const observed: Record<number, AvailabilityRow> = {};
        for (const item of data.rows || []) {
          const row = page.rows.find(candidate => candidate.match.id === item.matchId);
          if (row && row.match.src_binary === item.srcBinary && row.match.dst_binary === item.dstBinary
              && row.match.src_addr === item.srcAddr && row.match.run === item.run) observed[item.matchId] = item;
        }
        setMethods(observed); setMethodsStatus('');
      })
      .catch(reason => {
        if (!controller.signal.aborted) setMethodsStatus(`Method availability unavailable: ${reviewErrorText(reason?.message || reason)}`);
      });
    return () => controller.abort();
  }, [active, page, revision]);

  useEffect(() => {
    if (!confirm) return;
    confirmRef.current?.scrollIntoView({block: 'nearest'});
    confirmRef.current?.querySelector<HTMLButtonElement>('button')?.focus({preventScroll: true});
  }, [confirm]);

  const reload = useCallback(() => setRefresh(value => value + 1), []);
  const closeJob = useCallback((jobId: string) => setJobs(old => old.filter(job => job.id !== jobId)), []);

  const observe = useCallback(async (jobId: string) => {
    const controller = new AbortController(); observation.current?.abort(); observation.current = controller;
    setWatching(jobId); setError('');
    try {
      const decisions = await observeReviewJob(jobId, controller.signal);
      if (controller.signal.aborted) return;
      if (decisions) {
        const text = outcomeText(decisions);
        closeJob(jobId); setMessage(text); notify?.(text, 'info'); reload();
      } else {
        setMessage(`Job ${jobId} is still running. Its rows stay locked until you check its result or refresh the rows.`);
      }
    } catch (reason) {
      if (controller.signal.aborted || (reason instanceof DOMException && reason.name === 'AbortError')) return;
      setMessage('');
      const text = reason instanceof Error ? reason.message : String(reason);
      setError(text);
      if (reason instanceof ReviewRefused || reason instanceof ReviewOutcomeUnknown) {
        closeJob(jobId); notify?.(text, 'error');
        if (!(reason instanceof ReviewRefused) || reason.refreshRequired) reload();
      }
      // Any other failure only means the job could not be read. Keep it open.
    } finally {
      if (!controller.signal.aborted) setWatching('');
    }
  }, [closeJob, notify, reload]);

  const locked = new Set(jobs.flatMap(job => job.tokens));
  const busy = loading || submitting || Boolean(watching);
  const eligible = (row: ReviewRow) => Number.isSafeInteger(row.match.id) && Boolean(row.token && page.selection)
    && !locked.has(row.token);
  const pairKey = (row: ReviewRow) => `${row.match.src_binary}:${row.match.dst_binary}`;
  const visibleRows = page.rows.filter(row => (!pairFilter || pairKey(row) === pairFilter)
    && (!scoreFloor || Number(row.match.score) >= Number(scoreFloor)));
  const pairs = [...new Map(page.rows.map(row => [pairKey(row), row])).entries()];
  const chosen = visibleRows.filter(row => selected.has(row.token) && eligible(row));
  const selectable = visibleRows.filter(eligible);
  const allChosen = selectable.length > 0 && selectable.every(row => selected.has(row.token));

  function ask(rows: ReviewRow[], decision: Decision) {
    if (!rows.length || busy) return;
    setError(''); setConfirm({rows, decision});
  }

  async function send() {
    if (!confirm || busy) return;
    const {rows, decision} = confirm;
    setConfirm(null); setSubmitting(true); setError(''); setMessage('Sending the decision…');
    try {
      const jobId = await submitReviewDecision(rows, page.selection, decision);
      if (!mountedRef.current) return;
      const tokens = rows.map(row => row.token);
      setJobs(old => [...old, {id: jobId, tokens, matchIds: rows.map(row => Number(row.match.id))}]);
      setSelected(old => new Set([...old].filter(token => !tokens.includes(token))));
      setMessage(`Decision sent as job ${jobId}. Waiting for the server to record it.`);
      setSubmitting(false);
      await observe(jobId);
    } catch (reason) {
      if (!mountedRef.current) return;
      setMessage('');
      const text = reason instanceof Error ? reason.message : String(reason);
      setError(text); notify?.(text, 'error');
      if (reason instanceof ReviewRefused && reason.refreshRequired) reload();
    } finally {if (mountedRef.current) setSubmitting(false);}
  }

  function stopWaiting() {
    const jobId = watching;
    observation.current?.abort(); setWatching('');
    setMessage(`Stopped waiting for job ${jobId}. It may still save. Its rows stay locked until you check its result or refresh the rows.`);
  }

  function refreshRows() {
    // The rows show the current state after a refresh, so open jobs no longer lock them.
    if (jobs.length) setMessage(`Rows refreshed. Job${jobs.length === 1 ? '' : 's'} ${jobs.map(job => job.id).join(', ')} may still save; decided rows leave the list.`);
    setJobs([]); reload();
  }

  return <section aria-labelledby={heading ? 'match-review-heading' : undefined} aria-label={heading ? undefined : 'Match review'} className="ws-match-review">
    {heading && <h2 id="match-review-heading">Match review</h2>}
    <p>Accept moves a candidate to verification. It does not prove matching source or runtime behaviour.</p>
    {error && <p role="alert">{error}</p>}
    {message && <p role="status">{message}</p>}
    {jobs.map(job => <p key={job.id}>Decision job <a href={`/api/v1/jobs/${encodeURIComponent(job.id)}`} target="_blank" rel="noreferrer">{job.id}</a>
      {' '}for match{job.matchIds.length === 1 ? '' : 'es'} {job.matchIds.join(', ')}{' '}
      {watching === job.id
        ? <button onClick={stopWaiting}>Stop waiting</button>
        : <button disabled={busy} onClick={() => observe(job.id)}>Check result</button>}</p>)}
    {confirm && <div ref={confirmRef} className="review-confirm" role="group" aria-label="Confirm match decision">
      <p>{confirmText(confirm.rows, confirm.decision)}</p>
      <button onClick={() => setConfirm(null)}>Cancel</button>{' '}
      <button onClick={send}>{confirm.decision === 'accept' ? 'Confirm accept' : 'Confirm reject'}</button>
    </div>}
    <div className="ws-toolbar" role="group" aria-label="Review view">
      <button aria-pressed={view === 'review'} onClick={() => setView('review')}>Match review</button>
      <button aria-pressed={view === 'fleet'} onClick={() => setView('fleet')}>Lane E fleet roster</button>
      <label>Build pair <select value={pairFilter} onChange={event => {setPairFilter(event.target.value); setConfirm(null);}}>
        <option value="">All pairs on this page</option>
        {pairs.map(([key, row]) => <option key={key} value={key}>{row.binaries[0]?.row?.slug || row.match.src_binary} → {row.binaries[1]?.row?.slug || row.match.dst_binary}</option>)}
      </select></label>
      <label>Minimum score <select value={scoreFloor} onChange={event => {setScoreFloor(event.target.value); setConfirm(null);}}>
        <option value="">All scores</option><option value="0.5">0.50</option><option value="0.7">0.70</option><option value="0.9">0.90</option>
      </select></label>
    </div>
    {view === 'fleet' && <p>Donor → recipient decisions in the current review selection. Filters and batch selection apply to this page; they do not submit compute work.</p>}
    {methodsStatus && <p role="status">{methodsStatus}</p>}
    <div className="ws-toolbar">
      <button disabled={loading || submitting} onClick={refreshRows}>Refresh rows</button>
      <button disabled={busy || Boolean(confirm) || !chosen.length} onClick={() => ask(chosen, 'accept')}>Accept selected</button>
      <button disabled={busy || Boolean(confirm) || !chosen.length} onClick={() => ask(chosen, 'reject')}>Reject selected</button>
      <span>{loading ? 'Loading…' : `${page.total} candidates awaiting review, listed by match ID`}</span>
    </div>
    <table><thead><tr>
      <th><input type="checkbox" aria-label="Select all visible rows on this page" checked={allChosen} disabled={busy || !selectable.length}
        onChange={event => {const checked = event.target.checked; setSelected(old => {const next = new Set(old); selectable.forEach(row => checked ? next.add(row.token) : next.delete(row.token)); return next;});}}/></th>
      <th>Match</th><th>{view === 'fleet' ? 'Donor' : 'Source'}</th><th>{view === 'fleet' ? 'Recipient' : 'Destination'}</th><th>Score / margin</th><th>Evidence</th>{view === 'fleet' && <th>Recorded matching methods</th>}<th>Decision</th></tr></thead>
      <tbody>{visibleRows.map(row => <tr key={row.token}>
        <td><input type="checkbox" aria-label={`Select match ${row.match.id}`} checked={selected.has(row.token)} disabled={busy || !eligible(row)}
          onChange={event => {const checked = event.target.checked; setSelected(old => {const next = new Set(old); checked ? next.add(row.token) : next.delete(row.token); return next;});}}/></td>
        <td>{String(row.match.id)}</td>
        <td>{row.binaries[0]?.row?.slug || row.match.src_binary}<br/><code>{address(row.match.src_addr)}</code></td>
        <td>{row.binaries[1]?.row?.slug || row.match.dst_binary}<br/><code>{address(row.match.dst_addr)}</code></td>
        <td>{String(row.match.score)} / {String(row.match.margin)}</td>
        <td><details><summary>{row.match.relation || 'Relation unavailable'}</summary><pre>{row.match.evidence || 'No recorded evidence'}</pre><p>Run: {row.match.run}</p></details></td>
        {view === 'fleet' && <td>{methods[row.match.id]
          ? <details><summary>{methods[row.match.id].channels.filter(method => method.state === 'ran').map(method => method.channel).join(', ') || 'No recorded contributing methods'}</summary>
            <ul>{methods[row.match.id].channels.map(method => <li key={method.channel}>
              <strong>{method.channel} · {method.label}</strong>: {method.enabled === false ? 'available, off' : method.state}
              {' — '}{method.reason.replaceAll('_', ' ')}{method.providerReason && <>; {method.providerReason.replaceAll('_', ' ')}</>}
            </li>)}</ul></details>
          : <span>{methodsStatus || 'No availability receipt for this row'}</span>}</td>}
        <td>{locked.has(row.token) ? <span>Waiting for its job</span> : <>
          <button disabled={busy || Boolean(confirm) || !eligible(row)} onClick={() => ask([row], 'accept')}>Accept</button>{' '}
          <button disabled={busy || Boolean(confirm) || !eligible(row)} onClick={() => ask([row], 'reject')}>Reject</button></>}</td>
      </tr>)}</tbody>
    </table>
    {!loading && page.rows.length > 0 && !visibleRows.length && <p>No candidates on this page match these filters.</p>}
    {!loading && !error && !page.rows.length && <p>{afterId ? 'No review candidates after this match ID.' : 'No review candidates.'}</p>}
    <button disabled={loading || !afterId} onClick={() => {setHistory([]); setAfterId(0);}}>Go to first page</button>{' '}
    <button disabled={loading || !history.length} onClick={() => {setAfterId(history[history.length - 1]); setHistory(history.slice(0, -1));}}>Show previous page</button>{' '}
    <button disabled={loading || page.nextAfterId === null} onClick={() => {setHistory([...history, afterId]); setAfterId(page.nextAfterId!);}}>Show next page</button>
  </section>;
}
