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
async function provider(prompt: string, signal: AbortSignal): Promise<string> {
  if (!config) throw new Error("contributor is not configured");
  const provider = config.provider;
  const endpoint = provider === "openai" ? "https://api.openai.com/v1/chat/completions" : "https://api.anthropic.com/v1/messages";
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const body = provider === "openai"
    ? { model: config.model, messages: [{ role: "user", content: prompt }] }
    : { model: config.model, max_tokens: 4096, messages: [{ role: "user", content: prompt }] };
  headers[provider === "openai" ? "Authorization" : "x-api-key"] = provider === "openai" ? `Bearer ${config.apiKey}` : config.apiKey;
  if (provider === "anthropic") {
    // Anthropic requires an explicit browser opt-in; the key is never routed
    // through the coordinator and this header prevents accidental browser use.
    headers["anthropic-version"] = "2023-06-01";
    headers["anthropic-dangerous-direct-browser-access"] = "true";
  }
  const response = await fetch(endpoint, { method: "POST", headers, body: JSON.stringify(body), signal });
  if (!response.ok) throw Object.assign(new Error(`provider request failed (${response.status})`), { status: response.status });
  const result = await response.json() as { choices?: { message?: { content?: string } }[]; content?: { text?: string }[] };
  return provider === "openai" ? String(result.choices?.[0]?.message?.content || "") : String(result.content?.[0]?.text || "");
}
async function heartbeat(lease: Lease, alive: { value: boolean; lost: boolean }, leaseController: AbortController) {
  const seconds = Math.max(1_000, Math.floor((lease.leaseExpiresAt - Date.now() / 1000) * 333));
  while (alive.value && !stopped) {
    await pause(seconds);
    if (!alive.value || stopped) return;
    try { await api("/heartbeat", { workerId, leaseToken: lease.leaseToken }); }
    catch (error) {
      const status = (error as { status?: number }).status || 0;
      if (status === 404 || status === 410 || Date.now() / 1000 >= lease.leaseExpiresAt) {
        alive.lost = true;
        leaseController.abort();
        emit("error", "Lease renewal was rejected; cancelled the provider request.");
        return;
      }
      // A transient coordinator failure does not immediately discard paid
      // provider work. Retry within the lease deadline instead of silently
      // ending this heartbeat loop.
      await pause(1_000);
    }
  }
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
      const alive = { value: true, lost: false };
      const leaseController = new AbortController();
      void heartbeat(lease, alive, leaseController).catch(() => {});
      let letLeaseExpire = false;
      try {
        emit("generating", "Generating a readable C proposal…");
        const source = extractRewriteSource(await provider(rewritePrompt(lease.unit.payload), leaseController.signal), String(lease.unit.payload.candidateSource || ""));
        if (alive.lost) throw new Error("lease expired or renewal was rejected");
        if (!source) throw new Error("provider did not return a changed fenced C function");
        const body = { workerId, leaseToken: lease.leaseToken, fence: lease.fence, idempotencyKey: crypto.randomUUID(), artifact: { source }, verdict: "candidate" };
        emit("submitting", "Submitting proposal for coordinator verification…");
        let accepted = false;
        for (let attempt = 0; !stopped && attempt < 4; attempt++) {
          try { await api("/submit", body); accepted = true; break; }
          catch (error) {
            const status = (error as { status?: number }).status || 0;
            // A coordinator validation rejection leaves the lease correctable,
            // but this worker cannot repair an invalid result. Do not hammer it.
            if (status === 422) { letLeaseExpire = true; break; }
            const delay = retryDelay(status);
            if (delay === null) { if (status === 404) { emit("disabled", "Exchange is not enabled on this server."); stopped = true; } break; }
            if (delay === 0) break; // superseded lease: it is safe to claim again.
            await pause(delay);
          }
        }
        if (!accepted && !stopped) letLeaseExpire = true;
        if (accepted) {
          proposals++; postMessage({ type: "proposal", unitId: lease.unit.unitId, state: "awaiting-verification", proposals } satisfies WorkerEvent);
        }
      } catch (error) {
        // Provider/output failure must not submit a terminal verdict. Let this
        // lease expire, rather than claiming other work while it remains held.
        const status = (error as { status?: number }).status || 0;
        // A bad credential will poison every attempt. Stop this worker and
        // allow the single held lease to expire instead of draining the queue.
        if (status === 401 || status === 403) stopped = true;
        else letLeaseExpire = true;
        emit("error", `This lease was not submitted: ${String(error)}`);
      } finally {
        alive.value = false;
        if (letLeaseExpire && !stopped) {
          const remaining = Math.max(0, Math.ceil((lease.leaseExpiresAt - Date.now() / 1000) * 1000));
          emit("waiting", "Attempt was not submitted; waiting for its lease to expire.");
          await pause(remaining);
        }
      }
    }
  } catch (error) { emit("error", String(error)); }
}
self.onmessage = event => {
  const command = event.data as WorkerCommand;
  if (command.type === "visibility") { visible = command.visible; return; }
  if (command.type === "stop") { stopped = true; controller?.abort(); config = null; workerId = ""; emit("stopped", "Contribution stopped; any active lease will safely expire."); return; }
  stopped = false; visible = command.visible; config = command.config; controller = new AbortController(); void run();
};
