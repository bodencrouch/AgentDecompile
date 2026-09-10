import { useCallback, useEffect, useState } from "react";
import { API, request } from "./contracts";
import type { Notify } from "./contracts";

interface CorpusDbStatus {
  ok: boolean;
  current: string | null;
  exists: boolean;
  candidates: string[];
}

/**
 * No AGENT_DECOMPILE_CORPUS_DB is required to start the server. When the
 * corpus db the pages want to read from doesn't exist yet, this banner lets
 * the user point at one already on disk instead of editing env vars.
 */
export function CorpusDbPicker({ notify }: { notify: Notify }) {
  const [status, setStatus] = useState<CorpusDbStatus | null>(null);
  const [customPath, setCustomPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  const refresh = useCallback(() => {
    request<CorpusDbStatus>(`${API}/corpus-db`)
      .then(setStatus)
      .catch(() => setStatus(null));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const select = useCallback(
    (path: string) => {
      if (!path.trim()) return;
      setBusy(true);
      request<CorpusDbStatus>(`${API}/corpus-db`, {
        method: "POST",
        body: JSON.stringify({ path: path.trim() }),
      })
        .then((next) => {
          setStatus(next);
          notify(`Using corpus db: ${next.current}`, "info");
        })
        .catch((err) => notify(String(err.message || err), "error"))
        .finally(() => setBusy(false));
    },
    [notify],
  );

  // A new project creates its corpus index during fact extraction. Do not
  // interrupt that automatic path with an empty database chooser; only offer
  // this control when the server has discovered a real alternative to select.
  if (dismissed || !status || status.exists || status.candidates.length === 0) return null;

  return (
    <div className="error corpus-db-picker">
      <div>
        No corpus database found{status.current ? ` at ${status.current}` : ""}.
        Pick an existing db from disk, or continue without one — pages that
        need it will just show as empty.
      </div>
      {status.candidates.length > 0 && (
        <div className="corpus-db-picker-candidates">
          {status.candidates.map((path) => (
            <button key={path} disabled={busy} onClick={() => select(path)}>
              {path}
            </button>
          ))}
        </div>
      )}
      <div className="corpus-db-picker-custom">
        <input
          placeholder="/path/to/corpus.db"
          value={customPath}
          onChange={(event) => setCustomPath(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") select(customPath);
          }}
        />
        <button disabled={busy || !customPath.trim()} onClick={() => select(customPath)}>
          Use path
        </button>
        <button disabled={busy} onClick={() => setDismissed(true)}>
          Dismiss
        </button>
      </div>
    </div>
  );
}
