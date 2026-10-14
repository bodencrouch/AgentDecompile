import { preparationResponse } from "./preparationResponse";
import { useEffect, useState } from "react";
import { API, request, type Data } from "./contracts";

export type PreparationFeed = {
  runs: Data[];
  error: string;
  loading: boolean;
  lastConnectedAt: number;
  now: number;
};

const ACTIVE_STATUSES = new Set(["queued", "running", "waiting", "cancelling"]);
const IDLE_POLL_MS = 15_000;
const HIDDEN_POLL_MS = 60_000;
const MAX_ERROR_BACKOFF_MS = 60_000;

export function usePreparationRuns(pollMs = 2000): PreparationFeed {
  const [runs, setRuns] = useState<Data[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [lastConnectedAt, setLastConnectedAt] = useState(0);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    let inFlight = false;
    let wakeOnCompletion = false;
    let failures = 0;
    let currentRuns = runs;
    const fastPollMs = Math.max(250, pollMs);

    function nextDelay() {
      if (document.hidden) return HIDDEN_POLL_MS;
      if (failures > 0) {
        return Math.min(MAX_ERROR_BACKOFF_MS, fastPollMs * 2 ** Math.min(failures, 8));
      }
      return currentRuns.some((run) => ACTIVE_STATUSES.has(String(run.status)))
        ? fastPollMs
        : IDLE_POLL_MS;
    }

    async function poll() {
      if (!alive) return;
      if (inFlight) {
        wakeOnCompletion = true;
        return;
      }
      inFlight = true;
      wakeOnCompletion = false;
      try {
        const data = await request(API + "/preparations", { signal: AbortSignal.timeout(30000) });
        const received = preparationResponse(data);
        if (alive) {
          currentRuns = received;
          setRuns(received);
          setLastConnectedAt(Date.now());
          setError("");
        }
        failures = 0;
      } catch (e) {
        failures += 1;
        if (alive) setError(String(e));
      } finally {
        inFlight = false;
        if (alive) {
          setLoading(false);
          setNow(Date.now());
          const delay = wakeOnCompletion && !document.hidden ? 0 : nextDelay();
          wakeOnCompletion = false;
          timer = setTimeout(poll, delay);
        }
      }
    }

    function onVisibilityChange() {
      clearTimeout(timer);
      if (document.hidden) {
        if (!inFlight) timer = setTimeout(poll, HIDDEN_POLL_MS);
        return;
      }
      if (inFlight) wakeOnCompletion = true;
      else void poll();
    }

    document.addEventListener("visibilitychange", onVisibilityChange);
    void poll();
    const clock = setInterval(() => { if (alive) setNow(Date.now()); }, 1000);
    return () => {
      alive = false;
      document.removeEventListener("visibilitychange", onVisibilityChange);
      clearTimeout(timer);
      clearInterval(clock);
    };
  }, [pollMs]);

  return { runs, error, loading, lastConnectedAt, now };
}
