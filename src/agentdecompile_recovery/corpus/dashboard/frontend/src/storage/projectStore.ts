import type {
  ArtifactFormat,
  NormalizedAnalysisModel,
  ProviderCapability,
  Revision,
} from "../analysis/contracts";

const DATABASE_NAME = "agentdecompile-projects";
const DATABASE_VERSION = 2;
const ARTIFACTS_STORE = "artifacts";
const SNAPSHOTS_STORE = "snapshots";
const MEMBERSHIPS_STORE = "memberships";
const OUTBOX_STORE = "outbox";

export type StoredArtifact = {
  hash: string;
  name: string;
  bytes: ArrayBuffer;
  createdAt: string;
  format?: ArtifactFormat;
  architecture?: string;
  sourceName?: string;
};

export type ArtifactMembership = {
  id: string;
  projectId: string;
  artifactHash: string;
  sourceLocator?: string;
  createdAt: string;
};

export type PendingSyncRecord = {
  id: string;
  stream: "workspace" | "session";
  revision: number;
  payload: Record<string, unknown>;
  createdAt: string;
};

export type ProjectStoreStatus =
  | { state: "available"; version: number }
  | { state: "read-only"; version: number; reason: string }
  | { state: "migration-failed"; version: number; reason: string };

export type ProjectSnapshot = {
  projectId: string;
  revision: Revision;
  model: NormalizedAnalysisModel;
  capabilities?: ProviderCapability[];
};

let status: ProjectStoreStatus = { state: "available", version: DATABASE_VERSION };

function openDatabase(): Promise<IDBDatabase> {
  if (typeof indexedDB === "undefined") {
    const error = new Error("IndexedDB is unavailable; local mode is read-only");
    status = { state: "read-only", version: DATABASE_VERSION, reason: error.message };
    return Promise.reject(error);
  }
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
    request.onerror = () => {
      const error = request.error ?? new Error("Unable to open project store");
      status = { state: "migration-failed", version: DATABASE_VERSION, reason: error.message };
      reject(error);
    };
    request.onblocked = () => {
      const error = new Error("Project store migration is blocked by another open tab");
      status = { state: "migration-failed", version: DATABASE_VERSION, reason: error.message };
      reject(error);
    };
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(ARTIFACTS_STORE)) {
        database.createObjectStore(ARTIFACTS_STORE, { keyPath: "hash" });
      }
      if (!database.objectStoreNames.contains(SNAPSHOTS_STORE)) {
        database.createObjectStore(SNAPSHOTS_STORE, { keyPath: ["projectId", "revisionId", "schemaVersion"] });
      }
      if (!database.objectStoreNames.contains(MEMBERSHIPS_STORE)) {
        database.createObjectStore(MEMBERSHIPS_STORE, { keyPath: "id" });
      }
      if (!database.objectStoreNames.contains(OUTBOX_STORE)) {
        database.createObjectStore(OUTBOX_STORE, { keyPath: "id" });
      }
    };
    request.onsuccess = () => {
      status = { state: "available", version: DATABASE_VERSION };
      resolve(request.result);
    };
  });
}

function write<T>(storeName: string, value: T): Promise<void> {
  return openDatabase().then(
    (database) =>
      new Promise((resolve, reject) => {
        const transaction = database.transaction(storeName, "readwrite");
        const close = () => database.close();
        transaction.onerror = () => {
          close();
          reject(transaction.error ?? new Error("Project store write failed"));
        };
        transaction.onabort = () => {
          close();
          reject(transaction.error ?? new Error("Project store write aborted"));
        };
        transaction.oncomplete = () => {
          close();
          resolve();
        };
        transaction.objectStore(storeName).put(value);
      }),
  );
}

function read<T>(storeName: string, key: IDBValidKey | IDBKeyRange): Promise<T | undefined> {
  return openDatabase().then(
    (database) =>
      new Promise((resolve, reject) => {
        const transaction = database.transaction(storeName, "readonly");
        const request = transaction.objectStore(storeName).get(key);
        request.onerror = () => {
          database.close();
          reject(request.error ?? new Error("Project store read failed"));
        };
        request.onsuccess = () => {
          database.close();
          resolve(request.result as T | undefined);
        };
      }),
  );
}

function remove(storeName: string, key: IDBValidKey | IDBKeyRange): Promise<void> {
  return openDatabase().then(
    (database) =>
      new Promise((resolve, reject) => {
        const transaction = database.transaction(storeName, "readwrite");
        transaction.onerror = () => {
          database.close();
          reject(transaction.error ?? new Error("Project store delete failed"));
        };
        transaction.oncomplete = () => {
          database.close();
          resolve();
        };
        transaction.objectStore(storeName).delete(key);
      }),
  );
}

function list<T>(storeName: string): Promise<T[]> {
  return openDatabase().then(
    (database) =>
      new Promise((resolve, reject) => {
        const transaction = database.transaction(storeName, "readonly");
        const request = transaction.objectStore(storeName).getAll();
        request.onerror = () => {
          database.close();
          reject(request.error ?? new Error("Project store list failed"));
        };
        request.onsuccess = () => {
          database.close();
          resolve(request.result as T[]);
        };
      }),
  );
}

async function removeWhere<T>(
  storeName: string,
  predicate: (value: T) => boolean,
): Promise<void> {
  const records = await list<T>(storeName);
  await Promise.all(records.filter(predicate).map((record) => {
    const key = (record as { id?: string }).id;
    return key === undefined ? Promise.resolve() : remove(storeName, key);
  }));
}

export const projectStore = {
  status(): ProjectStoreStatus {
    return { ...status };
  },

  saveArtifact(artifact: StoredArtifact): Promise<void> {
    return write(ARTIFACTS_STORE, artifact);
  },

  loadArtifact(hash: string): Promise<StoredArtifact | undefined> {
    return read<StoredArtifact>(ARTIFACTS_STORE, hash);
  },

  saveSnapshot(snapshot: ProjectSnapshot): Promise<void> {
    return write(SNAPSHOTS_STORE, {
      ...snapshot,
      revisionId: snapshot.revision.id,
      schemaVersion: snapshot.model.schemaVersion,
    });
  },

  loadSnapshot(
    projectId: string,
    revision: Revision,
    schemaVersion = revision.schemaVersion,
  ): Promise<ProjectSnapshot | undefined> {
    return read<ProjectSnapshot>(SNAPSHOTS_STORE, [projectId, revision.id, schemaVersion]);
  },

  async loadLatestSnapshot(projectId: string): Promise<ProjectSnapshot | undefined> {
    const snapshots = await list<ProjectSnapshot>(SNAPSHOTS_STORE);
    return snapshots
      .filter((snapshot) => snapshot.projectId === projectId)
      .sort((left, right) => right.revision.createdAt.localeCompare(left.revision.createdAt))[0];
  },

  saveMembership(membership: ArtifactMembership): Promise<void> {
    return write(MEMBERSHIPS_STORE, membership);
  },

  memberships(projectId: string): Promise<ArtifactMembership[]> {
    return list<ArtifactMembership>(MEMBERSHIPS_STORE)
      .then((records) => records.filter((record) => record.projectId === projectId));
  },

  enqueue(record: PendingSyncRecord): Promise<void> {
    return write(OUTBOX_STORE, record);
  },

  outbox(stream?: PendingSyncRecord["stream"]): Promise<PendingSyncRecord[]> {
    return list<PendingSyncRecord>(OUTBOX_STORE)
      .then((records) => records
        .filter((record) => !stream || record.stream === stream)
        .sort((left, right) => left.createdAt.localeCompare(right.createdAt)));
  },

  acknowledgeOutbox(id: string): Promise<void> {
    return remove(OUTBOX_STORE, id);
  },

  purgeArtifact(hash: string): Promise<void> {
    return Promise.all([
      remove(ARTIFACTS_STORE, hash),
      removeWhere<ArtifactMembership>(MEMBERSHIPS_STORE, (membership) => membership.artifactHash === hash),
    ]).then(() => undefined);
  },

  async exportProject(projectId: string): Promise<{
    memberships: ArtifactMembership[];
    snapshots: ProjectSnapshot[];
  }> {
    const memberships = await this.memberships(projectId);
    const snapshots = (await list<ProjectSnapshot>(SNAPSHOTS_STORE))
      .filter((snapshot) => snapshot.projectId === projectId)
      .map(({ model, revision, capabilities }) => ({ projectId, model, revision, capabilities }));
    return { memberships, snapshots };
  },

  async purgeProject(projectId: string): Promise<void> {
    await removeWhere<ArtifactMembership>(MEMBERSHIPS_STORE, (membership) => membership.projectId === projectId);
    const snapshots = await list<ProjectSnapshot>(SNAPSHOTS_STORE);
    await Promise.all(snapshots
      .filter((snapshot) => snapshot.projectId === projectId)
      .map((snapshot) => remove(SNAPSHOTS_STORE, [
        snapshot.projectId,
        snapshot.revision.id,
        snapshot.model.schemaVersion,
      ])));
  },
};
