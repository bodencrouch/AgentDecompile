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

export interface EntityActivityState {
  entities: EntityActivity[];
  revision: number;
  connection: 'connecting' | 'live' | 'polling' | 'disconnected';
  error: string;
}

const EMPTY_STATE: EntityActivityState = { entities: [], revision: 0, connection: 'connecting', error: '' };
const DISCONNECTED_STATE: EntityActivityState = { ...EMPTY_STATE, connection: 'disconnected' };
const activityFeeds = new Map<string, ScopedActivityFeed>();

function retryAfterMs(value: string | null): number {
  if (!value) return 0;
  const seconds = Number(value);
  if (Number.isFinite(seconds) && seconds >= 0) return seconds * 1_000;
  const date = Date.parse(value);
  return Number.isFinite(date) ? Math.max(0, date - Date.now()) : 0;
}

/** One transport and one fallback poller per selected project/binary scope. */
class ScopedActivityFeed {
  private readonly listeners = new Set<(state: EntityActivityState) => void>();
  private state = EMPTY_STATE;
  private readonly query: URLSearchParams;
  private source: EventSource | null = null;
  private cursor = 0;
  private connected = false;
  private hasSnapshot = false;
  private generation = 0;
  private retryAttempt = 0;
  private retryAt = 0;
  private retryAction: 'fallback' | 'connect' | null = null;
  private retryTimer: number | undefined;
  private interval: number | undefined;
  private pollController: AbortController | null = null;
  private polling = false;
  private lastSignal = Date.now();
  private started = false;

  constructor(locator: string, slug: string, program: string) {
    this.query = new URLSearchParams({ locator, slug, program });
  }

  get isStopped(): boolean { return !this.started; }

  subscribe(listener: (state: EntityActivityState) => void): () => void {
    this.listeners.add(listener);
    listener(this.state);
    if (!this.started) this.start();
    return () => {
      this.listeners.delete(listener);
      if (this.listeners.size === 0) this.stop();
    };
  }

  private emit(state: EntityActivityState): void {
    this.state = state;
    this.listeners.forEach(listener => listener(state));
  }

  private start(): void {
    this.started = true;
    this.emit({ ...this.state, connection: document.hidden ? 'disconnected' : 'connecting', error: '' });
    document.addEventListener('visibilitychange', this.onVisibilityChange);
    this.interval = window.setInterval(this.onTick, 5_000);
    if (!document.hidden) this.connectOrPoll();
  }

  private stop(): void {
    if (!this.started) return;
    this.started = false;
    document.removeEventListener('visibilitychange', this.onVisibilityChange);
    if (this.interval !== undefined) window.clearInterval(this.interval);
    this.interval = undefined;
    this.clearRetry();
    this.source?.close();
    this.source = null;
    this.pollController?.abort();
    this.pollController = null;
    this.connected = false;
    this.polling = false;
    this.generation += 1;
    this.emit({ ...this.state, connection: 'disconnected', error: '' });
  }

  private clearRetry(): void {
    if (this.retryTimer !== undefined) window.clearTimeout(this.retryTimer);
    this.retryTimer = undefined;
    this.retryAt = 0;
    this.retryAction = null;
  }

  private scheduleRetry(message: string, serverDelayMs = 0, action: 'fallback' | 'connect' = 'fallback'): void {
    if (!this.started || this.retryTimer !== undefined) return;
    const backoff = Math.min(60_000, 1_000 * 2 ** Math.min(this.retryAttempt, 6));
    this.retryAttempt += 1;
    const delay = Math.round(Math.max(serverDelayMs, backoff * (0.85 + Math.random() * 0.3)));
    this.retryAt = Date.now() + delay;
    this.retryAction = action;
    this.generation += 1;
    this.pollController?.abort();
    this.pollController = null;
    this.source?.close();
    this.source = null;
    this.connected = false;
    this.emit({
      ...this.state,
      connection: this.hasSnapshot ? 'polling' : 'disconnected',
      error: `${message}. Retrying in ${Math.ceil(delay / 1_000)}s.`,
    });
    this.armRetry(delay);
  }

  private armRetry(delay: number): void {
    if (this.retryTimer !== undefined) window.clearTimeout(this.retryTimer);
    this.retryTimer = window.setTimeout(() => {
      this.retryTimer = undefined;
      // Keep the due action/deadline intact while hidden; visibility restore
      // will re-arm it instead of leaving this feed permanently disconnected.
      if (!this.started || document.hidden) return;
      const action = this.retryAction;
      this.retryAt = 0;
      this.retryAction = null;
      if (action === 'connect') {
        this.connectOrPoll();
      } else {
        void this.poll(typeof EventSource !== 'undefined');
      }
    }, Math.max(0, delay));
  }

  private accept(data: ActivitySnapshot, reset = false): boolean {
    if (!data?.ok || !Array.isArray(data.entities) || !Number.isSafeInteger(data.revision) || data.revision < 0) {
      this.connected = false;
      this.emit({ ...this.state, connection: 'disconnected', error: data?.error || 'Activity returned an incomplete snapshot' });
      return false;
    }
    if (!reset && data.revision < this.cursor) return false;
    this.cursor = data.revision;
    this.hasSnapshot = true;
    this.emit({ entities: data.entities, revision: data.revision, connection: this.connected ? 'live' : 'polling', error: '' });
    return true;
  }

  private connectOrPoll(): void {
    if (!this.started || document.hidden || Date.now() < this.retryAt) return;
    if (typeof EventSource === 'undefined') {
      void this.poll();
      return;
    }
    this.connect();
  }

  private connect(): void {
    if (!this.started || document.hidden || Date.now() < this.retryAt || this.source) return;
    try {
      const query = new URLSearchParams(this.query);
      query.set('after', String(this.cursor));
      const source = new EventSource(`${API}/activity/events?${query}`);
      this.source = source;
      this.lastSignal = Date.now();
      const current = () => this.started && this.source === source;
      const receive = (event: MessageEvent) => {
        if (!current()) return;
        try {
          const data = JSON.parse(event.data) as ActivitySnapshot;
          const reset = event.type === 'snapshot' || event.type === 'reset';
          if (reset) this.generation += 1;
          this.connected = true;
          this.retryAttempt = 0;
          this.clearRetry();
          if (this.accept(data, reset)) this.lastSignal = Date.now();
        } catch {
          this.scheduleRetry('Live activity could not be read');
        }
      };
      source.addEventListener('snapshot', receive as EventListener);
      source.addEventListener('reset', receive as EventListener);
      source.addEventListener('activity', receive as EventListener);
      source.addEventListener('heartbeat', (() => {
        if (!current()) return;
        this.lastSignal = Date.now();
        this.retryAttempt = 0;
        if (this.hasSnapshot) {
          this.connected = true;
          this.emit({ ...this.state, connection: 'live', error: '' });
        }
      }) as EventListener);
      source.addEventListener('unavailable', ((event: MessageEvent) => {
        if (!current()) return;
        let reason = 'Activity updates are temporarily unavailable';
        try { reason = JSON.parse(event.data).error || reason; } catch { /* Keep the plain fallback. */ }
        this.scheduleRetry(reason);
      }) as EventListener);
      source.onerror = () => {
        if (!current()) return;
        this.scheduleRetry('Live activity feed disconnected');
      };
    } catch (error) {
      this.scheduleRetry(error instanceof Error ? error.message : String(error));
    }
  }

  private async poll(reconnectAfterFallback = false): Promise<void> {
    // The stream supplies its own initial snapshot. Poll only when EventSource
    // is unavailable or closed; never race a pending/reconnecting stream.
    if (!this.started || document.hidden || this.connected || this.polling || Date.now() < this.retryAt) return;
    if (this.source && this.source.readyState !== EventSource.CLOSED) return;
    const controller = new AbortController();
    this.pollController = controller;
    this.polling = true;
    const requestGeneration = this.generation;
    try {
      const response = await fetch(`${API}/activity?${this.query}`, {
        signal: AbortSignal.any([controller.signal, AbortSignal.timeout(8_000)]),
      });
      const body = await response.text();
      let data: ActivitySnapshot;
      try {
        data = body.trim() ? JSON.parse(body) as ActivitySnapshot : { ok: false, entities: [], revision: 0, error: `Activity returned an empty response (${response.status})` };
      } catch {
        data = { ok: false, entities: [], revision: 0, error: `Activity returned invalid JSON (${response.status})` };
      }
      if (!response.ok || !data.ok) {
        this.scheduleRetry(
          `${data.error || 'Activity is temporarily unavailable'} (HTTP ${response.status})`,
          retryAfterMs(response.headers.get('Retry-After')),
          typeof EventSource === 'undefined' ? 'fallback' : 'connect',
        );
        return;
      }
      if (requestGeneration === this.generation && this.accept(data, !this.connected && data.revision < this.cursor)) {
        // A successful snapshot fallback does not prove the SSE endpoint has
        // recovered; preserve its reconnect backoff across repeated SSE 429s.
        if (!reconnectAfterFallback) this.retryAttempt = 0;
      }
    } catch (error) {
      if (!controller.signal.aborted && this.started && !this.connected) {
        this.scheduleRetry(
          error instanceof Error ? error.message : String(error),
          0,
          typeof EventSource === 'undefined' ? 'fallback' : 'connect',
        );
      }
    } finally {
      if (this.pollController === controller) this.pollController = null;
      this.polling = false;
      if (reconnectAfterFallback && requestGeneration === this.generation && this.started && !document.hidden) {
        this.scheduleRetry('Reconnecting live activity feed', 0, 'connect');
      }
    }
  }

  private onVisibilityChange = (): void => {
    if (!this.started) return;
    if (document.hidden) {
      this.source?.close();
      this.source = null;
      this.pollController?.abort();
      this.pollController = null;
      this.connected = false;
      this.generation += 1;
      this.emit({ ...this.state, connection: 'disconnected', error: '' });
      return;
    }
    this.emit({ ...this.state, connection: 'connecting', error: '' });
    if (this.retryAt > 0) {
      if (this.retryTimer === undefined) this.armRetry(Math.max(0, this.retryAt - Date.now()));
    } else {
      this.connectOrPoll();
    }
  };

  private onTick = (): void => {
    if (!this.started || document.hidden) return;
    if (this.source && Date.now() - this.lastSignal > 20_000) {
      this.scheduleRetry('Activity updates have not supplied a recent snapshot');
      return;
    }
    if (!this.source) void this.poll();
  };
}

/** Subscribe components to the same transport and preserve its last good snapshot. */
export function useEntityActivity(locator: string, slug: string, program = "", enabled = true) {
  const [state, setState] = useState<EntityActivityState>(enabled ? EMPTY_STATE : DISCONNECTED_STATE);

  useEffect(() => {
    if (!enabled) {
      setState(DISCONNECTED_STATE);
      return;
    }
    const key = JSON.stringify([locator, slug, program]);
    let feed = activityFeeds.get(key);
    if (!feed) {
      feed = new ScopedActivityFeed(locator, slug, program);
      activityFeeds.set(key, feed);
    }
    const current = feed;
    const unsubscribe = current.subscribe(setState);
    return () => {
      unsubscribe();
      if (current.isStopped && activityFeeds.get(key) === current) activityFeeds.delete(key);
    };
  }, [locator, slug, program, enabled]);
  return state;
}
