import { API, type Data } from "./contracts";
import { projectStore, type PendingSyncRecord } from "./storage/projectStore";

let revision = 0;
let saveChain: Promise<Data | void> = Promise.resolve(undefined);
let flushInstalled = false;
let payloadReader: (() => Data) | null = null;

const JSON_HEADERS = {
  "Content-Type": "application/json",
  "X-Requested-With": "fetch",
};

/** Load the durable session snapshot without blocking first paint. */
export function loadClientSessions(): Data {
  try {
    const raw = window.localStorage.getItem("agentdecompile.sessions");
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object") return parsed as Data;
    }
  } catch { /* storage may be unavailable in private/static contexts */ }
  return { active: "", sessions: [] };
}

export function setSessionRevision(value: number) {
  revision = value;
}

function runSave(payload: Data, keepalive: boolean): Promise<Data | void> {
  return fetch(API + "/sessions", {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify({ ...payload, revision }),
    keepalive,
  }).then(async (response) => {
    const body = await response.text();
    if (!response.ok) throw new Error(body || `Session save failed (${response.status})`);
    let result: Partial<Data> & { revision?: number } = {};
    if (body.trim()) {
      try { result = JSON.parse(body) as Partial<Data> & { revision?: number }; }
      catch { throw new Error("Session save returned invalid JSON"); }
    }
    revision = Number(result.revision || revision);
    return result;
  });
}

function resetChain(task: Promise<Data | void>) {
  saveChain = task.catch(() => undefined);
}

function syncRecord(payload: Data): PendingSyncRecord {
  return {
    id: crypto.randomUUID(),
    stream: "session",
    revision,
    payload,
    createdAt: new Date().toISOString(),
  };
}

export function queueSessionSave(payload: Data): Promise<Data | void> {
  const task = saveChain.then(() => runSave(payload, true)).catch(async (error) => {
    try {
      await projectStore.enqueue(syncRecord(payload));
    } catch {
      // The original network error remains authoritative when local persistence is unavailable.
    }
    throw error;
  });
  resetChain(task);
  return task;
}

export function flushSessionSave(payload: Data) {
  resetChain(saveChain.then(() => runSave(payload, true)));
}

export function installSessionFlush(getPayload: () => Data) {
  payloadReader = getPayload;
  if (flushInstalled) return;
  flushInstalled = true;
  const flush = () => {
    if (payloadReader) flushSessionSave(payloadReader());
  };
  window.addEventListener("pagehide", flush);
  window.addEventListener("beforeunload", flush);
}

/** Replay durable local session writes after a disconnected or failed save. */
export async function replaySessionOutbox(): Promise<void> {
  const records = await projectStore.outbox("session");
  for (const record of records) {
    try {
      await runSave(record.payload as Data, true);
      await projectStore.acknowledgeOutbox(record.id);
    } catch {
      break;
    }
  }
}
