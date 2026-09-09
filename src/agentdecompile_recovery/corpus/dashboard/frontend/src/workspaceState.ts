import { useCallback, useEffect, useState } from "react";
import { API, request, type Data } from "./contracts";
import { projectStore, type PendingSyncRecord } from "./storage/projectStore";

type Section = "drafts" | "notes" | "meta";
let revision = 0;
let loaded = false;
let loadFailed = false;
let loadPromise: Promise<Data> | null = null;
let cache: Data = { drafts: {}, notes: {}, meta: {} };
const pending: Partial<Record<Section, Data>> = {};
let flushTimer: ReturnType<typeof setTimeout> | null = null;
let flushChain = Promise.resolve();
let flushInstalled = false;
let lastSyncFailure = "";

const JSON_HEADERS = {
  "Content-Type": "application/json",
  "X-Requested-With": "fetch",
};

export function workspaceKey(...parts: string[]) {
  return parts.filter(Boolean).join(":");
}

export async function ensureWorkspaceState(): Promise<Data> {
  if (loaded) return cache;
  if (!loadPromise) {
    loadPromise = request(API + "/workspace-state")
      .then((data) => {
        revision = Number(data.revision || 0);
        cache = {
          drafts: data.drafts || {},
          notes: data.notes || {},
          meta: data.meta || {},
        };
        loaded = true;
        loadFailed = false;
        return cache;
      })
      .catch(() => {
        loadFailed = true;
        loaded = false;
        loadPromise = null;
        cache = { drafts: {}, notes: {}, meta: {} };
        return cache;
      });
  }
  return loadPromise;
}

function scheduleFlush() {
  if (flushTimer) clearTimeout(flushTimer);
  flushTimer = setTimeout(() => void flushWorkspaceState(), 150);
}

export function patchWorkspaceState(
  section: Section,
  key: string,
  value: unknown,
) {
  if (!pending[section]) pending[section] = {};
  pending[section]![key] = value;
  scheduleFlush();
}

function buildPendingBody(): Data | null {
  const body: Data = { revision };
  for (const section of ["drafts", "notes", "meta"] as const) {
    if (pending[section] && Object.keys(pending[section]!).length)
      body[section] = pending[section];
  }
  if (!body.drafts && !body.notes && !body.meta) return null;
  return body;
}

function restorePending(body: Data) {
  for (const section of ["drafts", "notes", "meta"] as const) {
    const chunk = body[section];
    if (!chunk) continue;
    pending[section] = { ...(pending[section] || {}), ...chunk };
  }
}

function workspaceOutboxRecord(body: Data): PendingSyncRecord {
  return {
    id: crypto.randomUUID(),
    stream: "workspace",
    revision: Number(body.revision || revision),
    payload: body,
    createdAt: new Date().toISOString(),
  };
}

function clearPendingFromBody(body: Data) {
  for (const section of ["drafts", "notes", "meta"] as const) {
    if (body[section]) pending[section] = undefined;
  }
}

function flushWorkspaceStateImmediate() {
  const body = buildPendingBody();
  if (!body) return;
  void fetch(API + "/workspace-state", {
    method: "PATCH",
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
    keepalive: true,
  });
}

export async function flushWorkspaceState(): Promise<void> {
  if (flushTimer) {
    clearTimeout(flushTimer);
    flushTimer = null;
  }
  const body = buildPendingBody();
  if (!body) return;
  flushChain = flushChain.then(async () => {
    try {
      const result = await request(API + "/workspace-state", {
        method: "PATCH",
        body: JSON.stringify(body),
        keepalive: true,
      });
      clearPendingFromBody(body);
      revision = Number(result.revision || revision);
      cache = {
        drafts: result.drafts || cache.drafts || {},
        notes: result.notes || cache.notes || {},
        meta: result.meta || cache.meta || {},
      };
    } catch {
      restorePending(body);
      lastSyncFailure = "Workspace state is queued locally until the server is available";
      try {
        await projectStore.enqueue(workspaceOutboxRecord(body));
      } catch {
        // Server drafts remain in memory if IndexedDB is unavailable.
      }
    }
  });
  await flushChain;
}

export function workspaceSyncFailure(): string {
  return lastSyncFailure;
}

/** Replay the durable workspace outbox in revision order after reconnecting. */
export async function replayWorkspaceOutbox(): Promise<void> {
  const records = await projectStore.outbox("workspace");
  for (const record of records) {
    try {
      const result = await request(API + "/workspace-state", {
        method: "PATCH",
        body: JSON.stringify(record.payload),
        keepalive: true,
      });
      revision = Number(result.revision || revision);
      cache = {
        drafts: result.drafts || cache.drafts || {},
        notes: result.notes || cache.notes || {},
        meta: result.meta || cache.meta || {},
      };
      lastSyncFailure = "";
      await projectStore.acknowledgeOutbox(record.id);
    } catch {
      break;
    }
  }
}

export async function readWorkspaceDraft(key: string): Promise<string | null> {
  const state = await ensureWorkspaceState();
  const entry = state.drafts?.[key];
  if (typeof entry === "string") return entry;
  if (entry && typeof entry === "object" && typeof entry.text === "string")
    return entry.text;
  try {
    return localStorage.getItem("agentdecompile.editor.draft:" + key);
  } catch {
    return null;
  }
}

export function installWorkspaceFlush() {
  if (flushInstalled) return;
  flushInstalled = true;
  const flush = () => flushWorkspaceStateImmediate();
  window.addEventListener("pagehide", flush);
  window.addEventListener("beforeunload", flush);
}

export function useWorkspacePref<T>(section: Section, key: string, fallback: T) {
  const [value, setValue] = useState<T>(fallback);
  useEffect(() => {
    let alive = true;
    void ensureWorkspaceState().then((state) => {
      if (!alive || loadFailed) return;
      const stored = state[section]?.[key];
      if (stored !== undefined) setValue(stored as T);
    });
    return () => {
      alive = false;
    };
  }, [section, key]);
  const save = useCallback(
    (next: T) => {
      setValue(next);
      patchWorkspaceState(section, key, next);
      try {
        localStorage.setItem("ad.react." + section + "." + key, JSON.stringify(next));
      } catch {
        /* Browser storage may be disabled. */
      }
    },
    [section, key],
  );
  return [value, save] as const;
}

export function useWorkspaceDraft(key: string) {
  const save = useCallback(
    (text: string) => {
      patchWorkspaceState("drafts", key, { text, updatedAt: Date.now() });
      try {
        localStorage.setItem("agentdecompile.editor.draft:" + key, text);
      } catch {
        /* Browser storage may be disabled. */
      }
    },
    [key],
  );
  return { save, read: () => readWorkspaceDraft(key) };
}
