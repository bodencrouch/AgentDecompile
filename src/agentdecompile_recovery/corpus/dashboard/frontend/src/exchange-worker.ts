/// <reference lib="webworker" />
import { EXCHANGE, type ContributorConfig, type Lease, type WorkerCommand, type WorkerEvent, exchangeError, extractRewriteSource, retryDelay, rewritePrompt } from "./exchange-protocol";

let stopped = true, visible = true, workerId = "", config: ContributorConfig | null = null, proposals = 0;
let controller: AbortController | null = null;
const emit = (state: Extract<WorkerEvent, { type: "status" }>["state"], message: string) => postMessage({ type: "status", state, message, proposals } satisfies WorkerEvent);
const pause = (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms));
async function api(path: string, body?: unknown): Promise<unknown> {
  const response = await fetch(EXCHANGE + path, { method: body === undefined ? "GET" : "POST", headers: body === undefined ? undefined : { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body), signal: controller?.signal });
  if (response.status === 204) return null;
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw exchangeError(response.status, payload);
  return payload;
}
async function provider(prompt: string): Promise<string> {
  if (!config) throw new Error("contributor is not configured");
  const provider = config.provider;
  const endpoint = provider === "openai" ? "https://api.openai.com/v1/chat/completions" : "https://api.anthropic.com/v1/messages";
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const body = provider === "openai"
    ? { model: config.model, messages: [{ role: "user", content: prompt }] }
    : { model: config.model, max_tokens: 4096, messages: [{ role: "user", content: prompt }] };
  headers[provider === "openai" ? "Authorization" : "x-api-key"] = provider === "openai" ? `Bearer ${config.apiKey}` : config.apiKey;
  if (provider === "anthropic") headers["anthropic-version"] = "2023-06-01";
  const response = await fetch(endpoint, { method: "POST", headers, body: JSON.stringify(body), signal: controller?.signal });
  if (!response.ok) throw new Error(`provider request failed (${response.status})`);
  const result = await response.json() as { choices?: { message?: { content?: string } }[]; content?: { text?: string }[] };
  return provider === "openai" ? String(result.choices?.[0]?.message?.content || "") : String(result.content?.[0]?.text || "");
}
async function heartbeat(lease: Lease, alive: { value: boolean }) {
  const seconds = Math.max(1_000, Math.floor((lease.leaseExpiresAt - Date.now() / 1000) * 333));
  while (alive.value && !stopped) { await pause(seconds); if (alive.value && !stopped) await api("/heartbeat", { workerId, leaseToken: lease.leaseToken }); }
}
async function run() {
  try {
    emit("enrolling", "Enrolling browser rewrite worker…");
    const enrolled = await api("/enroll", { capabilities: ["llm"], agent: "AgentDecompile browser rewrite worker" }) as { workerId: string };
    workerId = enrolled.workerId;
    while (!stopped) {
      if (!visible) { emit("waiting", "Paused while this tab is hidden."); await pause(1_000); continue; }
      emit("waiting", "Waiting for rewrite work…");
      let lease: Lease | null;
      try { lease = await api("/claim", { workerId, lanes: ["rewrite"] }) as Lease | null; }
      catch (error) { const delay = retryDelay((error as { status?: number }).status || 0); if (delay === null) { emit("disabled", "Exchange is not enabled on this server."); return; } await pause(delay || 1_500); continue; }
      if (!lease) { await pause(3_000); continue; }
      const alive = { value: true }; void heartbeat(lease, alive).catch(() => {});
      try {
        emit("generating", "Generating a readable C proposal…");
        const source = extractRewriteSource(await provider(rewritePrompt(lease.unit.payload)), String(lease.unit.payload.candidateSource || ""));
        if (!source) throw new Error("provider did not return a changed fenced C function");
        const body = { workerId, leaseToken: lease.leaseToken, fence: lease.fence, idempotencyKey: crypto.randomUUID(), artifact: { source }, verdict: "candidate" };
        emit("submitting", "Submitting proposal for coordinator verification…");
        let accepted = false;
        while (!stopped) { try { await api("/submit", body); accepted = true; break; } catch (error) { const delay = retryDelay((error as { status?: number }).status || 0); if (delay === null || delay === 0) break; await pause(delay); } }
        if (accepted) {
          proposals++; postMessage({ type: "proposal", unitId: lease.unit.unitId, state: "awaiting-verification", proposals } satisfies WorkerEvent);
        }
      } catch (error) { emit("error", `This lease was not submitted: ${String(error)}`); await pause(2_000); }
      finally { alive.value = false; }
    }
  } catch (error) { emit("error", String(error)); }
}
self.onmessage = event => {
  const command = event.data as WorkerCommand;
  if (command.type === "visibility") { visible = command.visible; return; }
  if (command.type === "stop") { stopped = true; controller?.abort(); config = null; workerId = ""; emit("stopped", "Contribution stopped; any active lease will safely expire."); return; }
  stopped = false; visible = command.visible; config = command.config; controller = new AbortController(); void run();
};
