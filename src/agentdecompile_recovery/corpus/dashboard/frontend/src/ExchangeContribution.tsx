import { useEffect, useRef, useState } from "react";
import { DialogFrame } from "./Actions";
import { EXCHANGE, PROVIDERS, type ProviderId, type WorkerEvent, type WorkerState } from "./exchange-protocol";
import { usePref } from "./ui";

type Roster = { units?: { total?: number; byStatus?: Record<string, number>; byLane?: Record<string, number> }; throughput?: { submissions?: number } };
const models: Record<ProviderId, string> = { openai: "gpt-4.1-mini", anthropic: "claude-sonnet-4-20250514" };

/** An opt-in, proposal-only browser worker. It is intentionally self-contained for both shells. */
export function ExchangeContribution() {
  const worker = useRef<Worker | null>(null);
  const [open, setOpen] = useState(false);
  const [provider, setProvider] = usePref<ProviderId>("exchange.provider", "openai");
  const [model, setModel] = usePref("exchange.model", models[provider]);
  const [apiKey, setApiKey] = useState("");
  const [state, setState] = useState<WorkerState>("stopped");
  const [message, setMessage] = useState("Contribution is stopped.");
  const [proposals, setProposals] = useState(0);
  const [roster, setRoster] = useState<Roster>({});

  const stop = () => {
    worker.current?.postMessage({ type: "stop" });
    worker.current?.terminate();
    worker.current = null;
    setApiKey("");
    setState("stopped");
    setMessage("Contribution stopped; the API key was cleared from this page.");
  };
  const close = () => { stop(); setOpen(false); };

  useEffect(() => () => stop(), []);
  useEffect(() => {
    if (!open || state === "stopped") return;
    const onVisibility = () => worker.current?.postMessage({ type: "visibility", visible: !document.hidden });
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [open, state]);
  useEffect(() => {
    if (!open || state === "stopped" || document.hidden) return;
    let disposed = false;
    const refresh = async () => {
      try {
        const response = await fetch(`${EXCHANGE}/roster`);
        if (!response.ok) throw new Error(`Roster request failed (${response.status})`);
        const next = await response.json() as Roster;
        if (!disposed) setRoster(next);
      } catch (error) {
        if (!disposed) setMessage(`Roster unavailable: ${String(error)}`);
      }
    };
    void refresh();
    const timer = window.setInterval(() => { if (!document.hidden) void refresh(); }, 5_000);
    return () => { disposed = true; window.clearInterval(timer); };
  }, [open, state]);

  const start = () => {
    if (!apiKey.trim()) { setMessage("Enter an API key to start this opt-in contributor."); return; }
    stop();
    const next = new Worker(new URL("./exchange-worker.ts", import.meta.url), { type: "module" });
    worker.current = next;
    next.onmessage = ({ data }: MessageEvent<WorkerEvent>) => {
      if (data.type === "status") { setState(data.state); setMessage(data.message); setProposals(data.proposals); }
      else { setProposals(data.proposals); setState("waiting"); setMessage(`Proposal submitted for ${data.unitId}; awaiting verification.`); }
    };
    next.onerror = () => { setState("error"); setMessage("The browser contributor stopped unexpectedly."); };
    setState("enrolling");
    setMessage("Starting browser contributor…");
    next.postMessage({ type: "start", config: { provider, model: model.trim() || models[provider], apiKey: apiKey.trim() }, visible: !document.hidden });
  };
  const awaiting = roster.units?.byStatus?.["awaiting-verification"] || 0;

  return <>
    <button className="exchange-contribution-trigger" onClick={() => setOpen(true)}>Contribute compute</button>
    {open && <DialogFrame title="Contribute compute" onClose={close} footer={<><button onClick={close}>Close</button>{state === "stopped" ? <button className="exchange-primary" onClick={start}>Start contributing</button> : <button onClick={stop}>Stop contributing</button>}</>}>
      <section className="exchange-contribution" aria-describedby="exchange-boundary">
        <p id="exchange-boundary">This tab sends rewrite evidence directly to the selected provider only after Start. It submits proposals for coordinator verification; it does not compile, match, or verify results.</p>
        <label>Provider<select value={provider} disabled={state !== "stopped"} onChange={e => { const next = e.target.value as ProviderId; setProvider(next); setModel(models[next]); }}>{Object.entries(PROVIDERS).map(([id, value]) => <option key={id} value={id}>{value.label}</option>)}</select></label>
        <label>Model<input value={model} disabled={state !== "stopped"} onChange={e => setModel(e.target.value)} required /></label>
        <label>API key<input type="password" value={apiKey} disabled={state !== "stopped"} onChange={e => setApiKey(e.target.value)} autoComplete="off" required /></label>
        <p className="exchange-status" role="status" aria-live="polite"><strong>{state}</strong> · {message}</p>
        <dl className="exchange-roster"><div><dt>Proposals this tab</dt><dd>{proposals}</dd></div><div><dt>Awaiting verification</dt><dd>{awaiting}</dd></div><div><dt>Rewrite units</dt><dd>{roster.units?.byLane?.rewrite || 0}</dd></div></dl>
        <p className="muted">The API key is never saved. Closing or stopping clears it. Hidden tabs pause claims and roster polling.</p>
      </section>
    </DialogFrame>}
  </>;
}
