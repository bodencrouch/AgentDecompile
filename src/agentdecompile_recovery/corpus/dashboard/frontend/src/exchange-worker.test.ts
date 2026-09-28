import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Lease, WorkerCommand, WorkerEvent } from "./exchange-protocol";

type WorkerScope = { onmessage: ((event: MessageEvent<WorkerCommand>) => void) | null };
type FetchHandler = (url: string, init?: RequestInit) => Response | Promise<Response>;

const config = { provider: "openai" as const, model: "test-model", apiKey: "secret-only-in-memory" };
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
const noContent = () => new Response(null, { status: 204 });
const lease = (seconds = 30): Lease => ({
  unit: { unitId: "unit-1", lane: "rewrite", payload: { functionName: "f", candidateSource: "int f(void) { return 1; }", alignedDiff: [] } },
  leaseToken: "lease-token",
  fence: 7,
  leaseExpiresAt: Date.now() / 1000 + seconds,
  leaseSeconds: seconds,
});

let scope: WorkerScope;
let events: WorkerEvent[];

async function install(handler: FetchHandler) {
  scope = { onmessage: null };
  events = [];
  vi.stubGlobal("self", scope);
  vi.stubGlobal("postMessage", (event: WorkerEvent) => events.push(event));
  vi.stubGlobal("fetch", vi.fn((input: string | URL, init?: RequestInit) => handler(String(input), init)));
  vi.stubGlobal("crypto", { randomUUID: () => "submission-id" });
  vi.resetModules();
  await import("./exchange-worker");
}

function start(visible = true) {
  scope.onmessage?.({ data: { type: "start", config, visible } } as MessageEvent<WorkerCommand>);
}

function stop() {
  scope.onmessage?.({ data: { type: "stop" } } as MessageEvent<WorkerCommand>);
}

async function settle() {
  await Promise.resolve();
  await Promise.resolve();
  await vi.advanceTimersByTimeAsync(0);
}

function calls(path: string) {
  return (fetch as ReturnType<typeof vi.fn>).mock.calls.filter(([url]) => String(url).endsWith(path));
}

beforeEach(() => vi.useFakeTimers({ now: new Date("2026-09-10T12:00:00Z") }));
afterEach(() => {
  stop();
  vi.clearAllTimers();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.resetModules();
});

describe("browser rewrite worker acceptance", () => {
  it("waits after a 204 claim without calling a provider", async () => {
    await install(url => url.endsWith("/enroll") ? json({ workerId: "worker-1" }) : noContent());

    start();
    await settle();

    expect(calls("/claim")).toHaveLength(1);
    expect((fetch as ReturnType<typeof vi.fn>).mock.calls.some(([url]) => String(url).startsWith("https://api.openai.com/"))).toBe(false);
    expect(events.at(-1)).toMatchObject({ type: "status", state: "waiting" });
  });

  it("submits one changed fenced C proposal", async () => {
    const held = lease();
    await install(url => {
      if (url.endsWith("/enroll")) return json({ workerId: "worker-1" });
      if (url.endsWith("/claim")) return calls("/claim").length === 1 ? json(held) : noContent();
      if (url.startsWith("https://api.openai.com/")) return json({ choices: [{ message: { content: "```c\nint f(void) { return 2; }\n```" } }] });
      if (url.endsWith("/submit")) return json({ accepted: true, verdict: "candidate" });
      throw new Error(`unexpected request ${url}`);
    });

    start();
    await settle();

    expect(calls("/submit")).toHaveLength(1);
    expect(JSON.parse(calls("/submit")[0][1]?.body as string)).toEqual({
      workerId: "worker-1", leaseToken: "lease-token", fence: 7, idempotencyKey: "submission-id",
      artifact: { source: "int f(void) { return 2; }" }, verdict: "candidate",
    });
    expect(events).toContainEqual({ type: "proposal", unitId: "unit-1", state: "awaiting-verification", proposals: 1 });
  });

  it("retries a coordinator submission with the identical body", async () => {
    const held = lease();
    let submits = 0;
    await install(url => {
      if (url.endsWith("/enroll")) return json({ workerId: "worker-1" });
      if (url.endsWith("/claim")) return calls("/claim").length === 1 ? json(held) : noContent();
      if (url.startsWith("https://api.openai.com/")) return json({ choices: [{ message: { content: "```c\nint f(void) { return 2; }\n```" } }] });
      if (url.endsWith("/submit")) return ++submits === 1 ? json({ error: "busy" }, 503) : json({ accepted: true, verdict: "candidate" });
      throw new Error(`unexpected request ${url}`);
    });

    start();
    await settle();
    await vi.advanceTimersByTimeAsync(5_000);

    const submissions = calls("/submit");
    expect(submissions).toHaveLength(2);
    expect(submissions[1][1]?.body).toBe(submissions[0][1]?.body);
    expect(JSON.parse(submissions[0][1]?.body as string).idempotencyKey).toBe("submission-id");
  });

  it("stops cleanly when the exchange is disabled", async () => {
    await install(url => url.endsWith("/enroll") ? json({ workerId: "worker-1" }) : json({ error: "disabled" }, 404));

    start();
    await settle();
    await vi.advanceTimersByTimeAsync(30_000);

    expect(calls("/claim")).toHaveLength(1);
    expect(events).toContainEqual(expect.objectContaining({ type: "status", state: "disabled" }));
  });

  it("cancels provider work after a rejected heartbeat and never submits", async () => {
    const held = lease(3);
    let providerSignal: AbortSignal | undefined;
    await install((url, init) => {
      if (url.endsWith("/enroll")) return json({ workerId: "worker-1" });
      if (url.endsWith("/claim")) return calls("/claim").length === 1 ? json(held) : noContent();
      if (url.endsWith("/heartbeat")) return json({ error: "expired" }, 410);
      if (url.startsWith("https://api.openai.com/")) {
        providerSignal = init?.signal ?? undefined;
        return new Promise<Response>((_, reject) => providerSignal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError"))));
      }
      throw new Error(`unexpected request ${url}`);
    });

    start();
    await settle();
    await vi.advanceTimersByTimeAsync(1_000);
    await settle();

    expect(providerSignal?.aborted).toBe(true);
    expect(calls("/submit")).toHaveLength(0);
    expect(events).toContainEqual(expect.objectContaining({ type: "status", state: "error", message: expect.stringContaining("Lease renewal was rejected") }));
  });

  it("cancels provider work once the lease expires during a transient heartbeat failure", async () => {
    const held = lease(2);
    let providerSignal: AbortSignal | undefined;
    await install((url, init) => {
      if (url.endsWith("/enroll")) return json({ workerId: "worker-1" });
      if (url.endsWith("/claim")) return calls("/claim").length === 1 ? json(held) : noContent();
      if (url.endsWith("/heartbeat")) return json({ error: "temporary outage" }, 503);
      if (url.startsWith("https://api.openai.com/")) {
        providerSignal = init?.signal ?? undefined;
        return new Promise<Response>((_, reject) => providerSignal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError"))));
      }
      throw new Error(`unexpected request ${url}`);
    });

    start();
    await settle();
    await vi.advanceTimersByTimeAsync(3_000);
    await settle();

    expect(providerSignal?.aborted).toBe(true);
    expect(calls("/submit")).toHaveLength(0);
  });

  it("holds a failed provider lease until expiry and stops on bad credentials", async () => {
    const held = lease(5);
    await install(url => {
      if (url.endsWith("/enroll")) return json({ workerId: "worker-1" });
      if (url.endsWith("/claim")) return calls("/claim").length === 1 ? json(held) : noContent();
      if (url.startsWith("https://api.openai.com/")) return json({ error: "unavailable" }, 500);
      throw new Error(`unexpected request ${url}`);
    });

    start();
    await settle();
    await vi.advanceTimersByTimeAsync(4_999);

    expect(calls("/submit")).toHaveLength(0);
    expect(calls("/claim")).toHaveLength(1);

    await vi.advanceTimersByTimeAsync(1);
    await settle();
    expect(calls("/claim")).toHaveLength(2);

    stop();
    const credentialLease = lease(30);
    await install(url => {
      if (url.endsWith("/enroll")) return json({ workerId: "worker-2" });
      if (url.endsWith("/claim")) return calls("/claim").length === 1 ? json(credentialLease) : noContent();
      if (url.startsWith("https://api.openai.com/")) return json({ error: "bad key" }, 401);
      throw new Error(`unexpected request ${url}`);
    });

    start();
    await settle();
    await vi.advanceTimersByTimeAsync(60_000);

    expect(calls("/submit")).toHaveLength(0);
    expect(calls("/claim")).toHaveLength(1);
  });

  it("does not claim while hidden but completes an in-flight lease and heartbeat", async () => {
    const hiddenLease = lease(12);
    let resolveProvider: ((response: Response) => void) | undefined;
    await install((url) => {
      if (url.endsWith("/enroll")) return json({ workerId: "worker-1" });
      if (url.endsWith("/claim")) return calls("/claim").length === 1 ? json(hiddenLease) : noContent();
      if (url.endsWith("/heartbeat")) return json({ leaseExpiresAt: Date.now() / 1000 + 12, leaseSeconds: 12 });
      if (url.startsWith("https://api.openai.com/")) return new Promise<Response>(resolve => { resolveProvider = resolve; });
      if (url.endsWith("/submit")) return json({ accepted: true, verdict: "candidate" });
      throw new Error(`unexpected request ${url}`);
    });

    start(false);
    await settle();
    expect(calls("/claim")).toHaveLength(0);

    scope.onmessage?.({ data: { type: "visibility", visible: true } } as MessageEvent<WorkerCommand>);
    await vi.advanceTimersByTimeAsync(1_000);
    await settle();
    expect(calls("/claim")).toHaveLength(1);

    scope.onmessage?.({ data: { type: "visibility", visible: false } } as MessageEvent<WorkerCommand>);
    await vi.advanceTimersByTimeAsync(4_000);
    expect(calls("/heartbeat")).toHaveLength(1);
    resolveProvider?.(json({ choices: [{ message: { content: "```c\nint f(void) { return 2; }\n```" } }] }));
    await settle();

    expect(calls("/submit")).toHaveLength(1);
    expect(calls("/claim")).toHaveLength(1);
  });

  it.each([-3_600_000, 3_600_000])("waits the full failed lease with browser clock offset %i", async offset => {
    const held = lease(5);
    vi.setSystemTime(Date.now() + offset);
    await install(url => {
      if (url.endsWith("/enroll")) return json({ workerId: "worker-1" });
      if (url.endsWith("/claim")) return calls("/claim").length === 1 ? json(held) : noContent();
      if (url.startsWith("https://api.openai.com/")) return json({ error: "unavailable" }, 500);
      throw new Error(`unexpected request ${url}`);
    });
    start();
    await settle();
    vi.setSystemTime(Date.now() - offset * 2);
    await vi.advanceTimersByTimeAsync(4_999);
    expect(calls("/claim")).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(calls("/claim")).toHaveLength(2);
    expect(calls("/submit")).toHaveLength(0);
  });

  it.each([undefined, 0, -1, "5"])("stops safely when the coordinator omits a usable lease duration: %s", async seconds => {
    await install(url => {
      if (url.endsWith("/enroll")) return json({ workerId: "worker-1" });
      if (url.endsWith("/claim")) return json({ ...lease(5), leaseSeconds: seconds });
      throw new Error(`unexpected request ${url}`);
    });
    start();
    await settle();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(calls("/claim")).toHaveLength(1);
    expect((fetch as ReturnType<typeof vi.fn>).mock.calls).toHaveLength(2);
    expect(events.at(-1)).toMatchObject({ type: "status", state: "error", message: expect.stringContaining("invalid lease duration") });
  });

  it("observes a late heartbeat renewal before releasing a failed provider lease", async () => {
    const held = lease(3);
    let resolveHeartbeat: ((response: Response) => void) | undefined;
    let resolveProvider: ((response: Response) => void) | undefined;
    await install(url => {
      if (url.endsWith("/enroll")) return json({ workerId: "worker-1" });
      if (url.endsWith("/claim")) return calls("/claim").length === 1 ? json(held) : noContent();
      if (url.endsWith("/heartbeat")) return new Promise<Response>(resolve => { resolveHeartbeat = resolve; });
      if (url.startsWith("https://api.openai.com/")) return new Promise<Response>(resolve => { resolveProvider = resolve; });
      throw new Error(`unexpected request ${url}`);
    });
    start();
    await settle();
    await vi.advanceTimersByTimeAsync(1_000);
    expect(calls("/heartbeat")).toHaveLength(1);
    resolveProvider?.(json({ error: "unavailable" }, 500));
    await settle();
    await vi.advanceTimersByTimeAsync(1_000);
    resolveHeartbeat?.(json({ leaseExpiresAt: held.leaseExpiresAt + 2, leaseSeconds: 3 }));
    await settle();
    vi.setSystemTime(Date.now() + 3_600_000);
    await vi.advanceTimersByTimeAsync(2_999);
    expect(calls("/claim")).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(calls("/claim")).toHaveLength(2);
  });

  it("does not wait for a stale heartbeat after an accepted submission", async () => {
    const held = lease(3);
    let resolveHeartbeat: ((response: Response) => void) | undefined;
    let resolveProvider: ((response: Response) => void) | undefined;
    await install(url => {
      if (url.endsWith("/enroll")) return json({ workerId: "worker-1" });
      if (url.endsWith("/claim")) return calls("/claim").length === 1 ? json(held) : noContent();
      if (url.endsWith("/heartbeat")) return new Promise<Response>(resolve => { resolveHeartbeat = resolve; });
      if (url.startsWith("https://api.openai.com/")) return new Promise<Response>(resolve => { resolveProvider = resolve; });
      if (url.endsWith("/submit")) return json({ accepted: true, verdict: "candidate" });
      throw new Error(`unexpected request ${url}`);
    });

    start();
    await settle();
    await vi.advanceTimersByTimeAsync(1_000);
    expect(calls("/heartbeat")).toHaveLength(1);
    resolveProvider?.(json({ choices: [{ message: { content: "```c\nint f(void) { return 2; }\n```" } }] }));
    await settle();

    expect(calls("/submit")).toHaveLength(1);
    expect(calls("/claim")).toHaveLength(2);
    resolveHeartbeat?.(json({ leaseExpiresAt: held.leaseExpiresAt + 3, leaseSeconds: 3 }));
    await settle();
  });
});
