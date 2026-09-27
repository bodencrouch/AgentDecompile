import { useEffect, useState } from 'react';
import { API } from './contracts';
import type { ClaimProjection } from './ScopedClaims';

export interface EntityActivity {
  claimProjection?: ClaimProjection;
  id: string;
  kind: 'project' | 'binary' | 'function';
  locator: string;
  slug: string;
  addr: string;
  name: string;
  sha256: string | null;
  aliasSlugs?: string[];
  projectBindings?: Array<{ locator: string; program: string }>;
  logicalId?: string;
  status: string;
  stage: string;
  action: string;
  target?: string;
  jobId: string | null;
  progress: { kind: 'measured' | 'indeterminate' | 'idle'; completed: number | null; total: number | null };
  eta: { lowerSeconds: number | null; upperSeconds: number | null; label: string; basis: string; observations: number };
  facets: Array<{ kind: string; label: string; source?: string }>;
  queue: { position: number | null; reason: string };
  error: string;
  updatedAt: number | null;
  proofReceipts: Array<{ path: string; href?: string; label?: string; freshness?: string; freshnessLabel?: string; sourceExists?: boolean; receiptModifiedAt?: number; verified?: boolean }>;
  attempts: number | null;
  dependencies: string[];
  nextFallback: string | null;
  budgetRemainingSeconds: number | null;
}
export interface ActivitySnapshot {
  ok: boolean;
  revision: number;
  entities: EntityActivity[];
  error?: string;
}

/** Keep the last valid snapshot while independently reconnecting the live feed. */
export function useEntityActivity(locator: string, slug: string, program = "", enabled = true) {
  const [state, setState] = useState<{
    entities: EntityActivity[]; revision: number;
    connection: 'connecting' | 'live' | 'polling' | 'disconnected'; error: string;
  }>({ entities: [], revision: 0, connection: 'connecting', error: '' });

  useEffect(() => {
    if (!enabled) {
      setState({entities: [], revision: 0, connection: 'disconnected', error: ''});
      return;
    }
    let disposed = false;
    let eventSource: EventSource | null = null;
    let cursor = 0;
    let connected = false;
    let hasSnapshot = false;
    let polling = false;
    let generation = 0;
    let lastSignal = Date.now();
    const abort = new AbortController();
    const query = new URLSearchParams({ locator, slug, program });
    setState({ entities: [], revision: 0, connection: 'connecting', error: '' });

    const accept = (data: ActivitySnapshot, reset = false): boolean => {
      if (disposed) return false;
      if (!data?.ok || !Array.isArray(data.entities) || !Number.isSafeInteger(data.revision) || data.revision < 0) {
        connected = false;
        hasSnapshot = false;
        setState(old => ({ ...old, connection: 'disconnected', error: data?.error || 'Activity returned an incomplete snapshot' }));
        return false;
      }
      // A reset snapshot is authoritative when the server no longer has our cursor.
      // An older polling response must never overwrite a newer streamed result.
      if (!reset && data.revision < cursor) return false;
      cursor = data.revision;
      hasSnapshot = true;
      setState({ entities: data.entities, revision: data.revision, connection: connected ? 'live' : 'polling', error: '' });
      return true;
    };
    const poll = async () => {
      if (disposed || document.hidden || connected || polling) return;
      polling = true;
      const requestGeneration = generation;
      try {
        const response = await fetch(`${API}/activity?${query}`, {
          signal: AbortSignal.any([abort.signal, AbortSignal.timeout(8000)]),
        });
        const body = await response.text();
        let data: ActivitySnapshot;
        try {
          data = body.trim() ? JSON.parse(body) as ActivitySnapshot : { ok: false, entities: [], revision: 0, error: `Activity returned an empty response (${response.status})` };
        } catch {
          data = { ok: false, entities: [], revision: 0, error: `Activity returned invalid JSON (${response.status})` };
        }
        if (!response.ok || !data.ok) throw new Error(data.error || 'Activity is temporarily unavailable');
        // The current HTTP response is authoritative after the stream lost its
        // connection.  Permit a lower revision here: a restarted server can
        // legitimately begin a new event sequence.
        if (requestGeneration === generation) accept(data, !connected && data.revision < cursor);
      } catch (error) {
        // A slow initial request can time out after the stream already recovered.
        if (!disposed && !connected) setState(old => ({ ...old, connection: 'disconnected', error: error instanceof Error ? error.message : String(error) }));
      } finally { polling = false; }
    };
    const connect = () => {
      if (disposed || document.hidden || typeof EventSource === 'undefined') return;
      eventSource?.close();
      const source = new EventSource(`${API}/activity/events?${query}&after=${cursor}`);
      eventSource = source;
      lastSignal = Date.now();
      const current = () => !disposed && eventSource === source;
      source.onopen = () => {
        if (!current()) return;
        lastSignal = Date.now();
        // Opening HTTP headers is not evidence that a usable snapshot arrived.
      };
      const receive = (event: MessageEvent) => {
        if (!current()) return;
        try {
          const data = JSON.parse(event.data);
          connected = true;
          const reset = event.type === 'snapshot' || event.type === 'reset';
          if (reset) generation += 1;
          if (accept(data, reset)) lastSignal = Date.now();
        } catch {
          connected = false;
          setState(old => ({ ...old, connection: 'disconnected', error: 'Live activity could not be read. Checking saved state.' }));
          void poll();
        }
      };
      source.addEventListener('snapshot', receive as EventListener);
      source.addEventListener('reset', receive as EventListener);
      source.addEventListener('activity', receive as EventListener);
      source.addEventListener('heartbeat', (() => {
        if (!current()) return;
        lastSignal = Date.now();
        if (hasSnapshot) {
          connected = true;
          setState(old => ({ ...old, connection: 'live', error: '' }));
        }
      }) as EventListener);
      source.addEventListener('unavailable', ((event: MessageEvent) => {
        if (!current()) return;
        connected = false;
        lastSignal = Date.now();
        let reason = 'Activity updates are temporarily unavailable';
        try { reason = JSON.parse(event.data).error || reason; } catch { /* Keep the plain fallback. */ }
        setState(old => ({ ...old, connection: 'disconnected', error: reason }));
        void poll();
      }) as EventListener);
      source.onerror = () => {
        if (!current()) return;
        connected = false;
        // EventSource can be buffered by a local proxy even while the bounded
        // snapshot request is succeeding.  Polling is still live state, so do
        // not present it as a broken workspace when we already have a usable
        // snapshot.
        setState(old => ({ ...old, connection: 'polling', error: old.revision ? '' : 'Live feed reconnecting; checking saved activity.' }));
        void poll();
      };
    };
    // A held snapshot cannot prevent opening the event stream.
    connect();
    void poll();
    const onVisibilityChange = () => {
      if (disposed) return;
      if (document.hidden) {
        // The server snapshots once per active scope, but a hidden tab should
        // not remain an observer or keep fallback requests in flight.
        eventSource?.close();
        eventSource = null;
        connected = false;
        setState(old => ({ ...old, connection: 'disconnected', error: '' }));
        return;
      }
      setState(old => ({ ...old, connection: 'connecting', error: '' }));
      connect();
      void poll();
    };
    document.addEventListener('visibilitychange', onVisibilityChange);
    const timer = window.setInterval(() => {
      if (disposed || document.hidden) return;
      if (eventSource && Date.now() - lastSignal > 20000) {
        connected = false;
        setState(old => old.revision
          ? { ...old, connection: 'polling', error: '' }
          : { ...old, connection: 'disconnected', error: 'Activity updates have not supplied an initial snapshot yet.' });
        connect();
      }
      void poll();
    }, 5000);
    return () => { disposed = true; document.removeEventListener('visibilitychange', onVisibilityChange); abort.abort(); eventSource?.close(); window.clearInterval(timer); };
  }, [locator, slug, program, enabled]);
  return state;
}
