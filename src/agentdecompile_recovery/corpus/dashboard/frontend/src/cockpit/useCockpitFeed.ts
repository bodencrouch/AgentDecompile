import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import { POLL_MS, STREAM_URL, fetchCells, fetchSummary, type ActivityEvent, type CellsDiff, type Hello, type Summary } from './api';
import { feedReducer, initialFeed } from './state';

const SSE_RETRY_MS = 30000;

function parse<T>(event: MessageEvent): T | undefined {
  try {
    return JSON.parse(String(event.data)) as T;
  } catch {
    return undefined;
  }
}

/**
 * Live feed: EventSource on /stream; whenever the stream is not open the
 * summary is polled every 5 s. A closed stream is retried every 30 s.
 */
export function useCockpitFeed(selectedProgram: string | undefined) {
  const [state, dispatch] = useReducer(feedReducer, initialFeed);
  const streamOpen = useRef(false);
  const selectedRef = useRef(selectedProgram);
  selectedRef.current = selectedProgram;
  const cellsLoading = useRef(new Set<string>());
  const [cellsError, setCellsError] = useState<Record<string, string>>({});

  const loadCells = useCallback(async (programId: string) => {
    if (cellsLoading.current.has(programId)) return;
    cellsLoading.current.add(programId);
    try {
      const cells = await fetchCells(programId);
      dispatch({ type: 'cells', cells, now: Date.now() });
      setCellsError(old => {
        if (!(programId in old)) return old;
        const next = { ...old };
        delete next[programId];
        return next;
      });
    } catch (error) {
      setCellsError(old => ({ ...old, [programId]: String((error as Error)?.message || error) }));
    } finally {
      cellsLoading.current.delete(programId);
    }
  }, []);

  const pollOnce = useCallback(async () => {
    try {
      const summary = await fetchSummary();
      dispatch({ type: 'summary', summary, now: Date.now() });
      if (!streamOpen.current) dispatch({ type: 'connection', connection: 'polling' });
      return summary;
    } catch (error) {
      if (!streamOpen.current) dispatch({ type: 'connection', connection: 'offline', error: String((error as Error)?.message || error) });
      return undefined;
    }
  }, []);

  useEffect(() => {
    let alive = true;
    let es: EventSource | undefined;
    let pollTimer: ReturnType<typeof setTimeout> | undefined;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let lastGenerated = '';

    const schedulePoll = (delay = POLL_MS) => {
      if (pollTimer || !alive) return;
      pollTimer = setTimeout(async () => {
        pollTimer = undefined;
        if (!alive || streamOpen.current) return;
        const summary = await pollOnce();
        // Without a stream there are no cell diffs: reload the open program when the corpus changed.
        if (summary && summary.generated !== lastGenerated) {
          if (lastGenerated && selectedRef.current) void loadCells(selectedRef.current);
          lastGenerated = summary.generated;
        }
        schedulePoll();
      }, delay);
    };

    const openStream = () => {
      if (!alive || typeof EventSource === 'undefined') {
        schedulePoll(0);
        return;
      }
      es?.close();
      const source = new EventSource(STREAM_URL);
      es = source;
      source.onopen = () => {
        streamOpen.current = true;
      };
      source.addEventListener('hello', event => {
        streamOpen.current = true;
        const hello = parse<Hello>(event as MessageEvent);
        if (hello) dispatch({ type: 'hello', hello });
        else dispatch({ type: 'connection', connection: 'live' });
      });
      source.addEventListener('summary', event => {
        const summary = parse<Summary>(event as MessageEvent);
        if (summary) {
          lastGenerated = summary.generated;
          dispatch({ type: 'summary', summary, now: Date.now() });
        }
      });
      source.addEventListener('cells', event => {
        const diff = parse<CellsDiff>(event as MessageEvent);
        if (diff) dispatch({ type: 'diff', diff, now: Date.now() });
      });
      source.addEventListener('activity', event => {
        const activity = parse<ActivityEvent>(event as MessageEvent);
        if (activity) dispatch({ type: 'activity', event: activity, now: Date.now() });
      });
      source.onerror = () => {
        streamOpen.current = false;
        schedulePoll(0);
        if (source.readyState === EventSource.CLOSED) {
          clearTimeout(retryTimer);
          retryTimer = setTimeout(openStream, SSE_RETRY_MS);
        }
      };
    };

    void pollOnce().then(summary => {
      if (summary) lastGenerated = summary.generated;
    });
    openStream();
    return () => {
      alive = false;
      streamOpen.current = false;
      es?.close();
      clearTimeout(pollTimer);
      clearTimeout(retryTimer);
    };
  }, [pollOnce, loadCells]);

  // A fresh summary means the API answered again: allow failed cell loads to retry.
  useEffect(() => setCellsError(old => (Object.keys(old).length ? {} : old)), [state.summary?.generated]);

  useEffect(() => {
    if (selectedProgram && !state.cells[selectedProgram] && !cellsError[selectedProgram]) void loadCells(selectedProgram);
  }, [selectedProgram, state.cells, cellsError, loadCells]);

  const retry = useCallback(() => {
    dispatch({ type: 'connection', connection: 'connecting' });
    setCellsError({});
    void pollOnce();
  }, [pollOnce]);

  return { state, retry, cellsError: selectedProgram ? cellsError[selectedProgram] : undefined };
}
