import { useCallback, useEffect, useState } from "react";
import type { Data } from "./contracts";

type Section = "drafts" | "notes" | "meta";
let cache: Data | null = null;

function clientId() {
  const key = "agentdecompile.client-id";
  let value = sessionStorage.getItem(key);
  if (!value) {
    value = crypto.randomUUID();
    sessionStorage.setItem(key, value);
  }
  return value;
}

function stateKey() {
  return `agentdecompile.workspace:${clientId()}`;
}

function load(): Data {
  if (cache) return cache;
  try {
    const stored = JSON.parse(sessionStorage.getItem(stateKey()) || "null");
    cache = { drafts: stored?.drafts || {}, notes: stored?.notes || {}, meta: stored?.meta || {} };
  } catch {
    cache = { drafts: {}, notes: {}, meta: {} };
  }
  return cache;
}

function persist() {
  try {
    sessionStorage.setItem(stateKey(), JSON.stringify(load()));
  } catch {
    /* Private browsing or quota exhaustion leaves current-tab memory intact. */
  }
}

export function clientLocalKey(key: string) {
  return `agentdecompile.client:${clientId()}:${key}`;
}

export function readClientLocal<T>(key: string, fallback: T): T {
  try {
    return JSON.parse(sessionStorage.getItem(clientLocalKey(key)) || "null") ?? fallback;
  } catch {
    return fallback;
  }
}

export function writeClientLocal(key: string, value: unknown) {
  try {
    sessionStorage.setItem(clientLocalKey(key), JSON.stringify(value));
  } catch {
    /* Private browsing or quota exhaustion leaves React state intact. */
  }
}

export function workspaceKey(...parts: string[]) {
  return parts.filter(Boolean).join(":");
}

export async function ensureWorkspaceState(): Promise<Data> {
  return load();
}

export function patchWorkspaceState(section: Section, key: string, value: unknown) {
  const state = load();
  state[section] = { ...(state[section] || {}), [key]: value };
  persist();
}

export async function flushWorkspaceState(): Promise<void> { persist(); }
export function workspaceSyncFailure(): string { return ""; }
export async function replayWorkspaceOutbox(): Promise<void> {
  // Client-local UI state is deliberately never replayed into the shared backend.
}

export async function readWorkspaceDraft(key: string): Promise<string | null> {
  const entry = load().drafts?.[key];
  if (typeof entry === "string") return entry;
  return entry && typeof entry === "object" && typeof entry.text === "string" ? entry.text : null;
}

export function installWorkspaceFlush() {
  // sessionStorage writes are synchronous; no lifecycle flush is required.
}

export function useWorkspacePref<T>(section: Section, key: string, fallback: T) {
  const [value, setValue] = useState<T>(fallback);
  useEffect(() => {
    const stored = load()[section]?.[key];
    if (stored !== undefined) setValue(stored as T);
  }, [section, key]);
  const save = useCallback((next: T) => {
    setValue(next);
    patchWorkspaceState(section, key, next);
  }, [section, key]);
  return [value, save] as const;
}

export function useWorkspaceDraft(key: string) {
  const save = useCallback((text: string) => {
    patchWorkspaceState("drafts", key, { text, updatedAt: Date.now() });
  }, [key]);
  return { save, read: () => readWorkspaceDraft(key) };
}
