import { useEffect, useState } from "react";
import { API, request, type Data } from "./contracts";

export type PreparationFeed = {
  runs: Data[];
  error: string;
  loading: boolean;
  lastConnectedAt: number;
  now: number;
};

export function usePreparationRuns(pollMs = 2000): PreparationFeed {
  const [runs, setRuns] = useState<Data[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [lastConnectedAt, setLastConnectedAt] = useState(0);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const data = await request(API + "/preparations", { signal: AbortSignal.timeout(30000) });
        if (alive) {
          setRuns(data.runs || []);
          setLastConnectedAt(Date.now());
          setError("");
        }
      } catch (e) {
        if (alive) setError(String(e));
      } finally {
        if (alive) {
          setLoading(false);
          setNow(Date.now());
          timer = setTimeout(poll, pollMs);
        }
      }
    }
    void poll();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [pollMs]);

  return { runs, error, loading, lastConnectedAt, now };
}
