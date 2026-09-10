import type {
  Freshness,
  ProviderCapability,
  ProviderResult,
  StructuredFailure,
} from "../analysis/contracts";
import type { WorkerMessage, WorkerRequest } from "./protocol";

export type WorkerSessionOptions = {
  createWorker: () => Worker;
  capability: ProviderCapability;
  isRevisionCurrent: (revisionId: string) => boolean;
};

function failureResult<T>(
  request: WorkerRequest,
  capability: ProviderCapability,
  failure: StructuredFailure,
): ProviderResult<T> {
  return {
    id: request.id,
    provider: capability.id,
    status: failure.code === "cancelled" ? "cancelled" : "failed",
    capability,
    revisionId: request.revisionId,
    createdAt: new Date().toISOString(),
    freshness: { state: "unknown", version: request.revisionId, reason: failure.message },
    failure,
  };
}

export class DisposableWorkerSession {
  private worker: Worker | undefined;
  private active = new Map<string, { resolve: (result: ProviderResult<unknown>) => void; revisionId: string }>();

  constructor(private readonly options: WorkerSessionOptions) {}

  run<T>(request: WorkerRequest): Promise<ProviderResult<T>> {
    if (request.limits.maxArtifactBytes <= 0 || request.limits.timeoutMs <= 0) {
      return Promise.resolve(failureResult<T>(request, this.options.capability, {
        code: "invalid-worker-limits",
        message: "Worker resource limits must be positive",
        retryable: false,
      }));
    }
    if (this.options.capability.status !== "available") {
      return Promise.resolve({
        id: request.id,
        provider: this.options.capability.id,
        status: this.options.capability.status,
        capability: this.options.capability,
        revisionId: request.revisionId,
        createdAt: new Date().toISOString(),
        freshness: {
          state: "unknown",
          version: request.revisionId,
          reason: this.options.capability.reason,
        },
        failure: {
          code: `provider-${this.options.capability.status}`,
          message: this.options.capability.reason ?? "Provider is not available",
          provider: this.options.capability.id,
          retryable: this.options.capability.status === "pending",
        },
      });
    }

    const worker = this.ensureWorker();
    return new Promise((resolve) => {
      const timeout = window.setTimeout(() => {
        if (!this.active.delete(request.id)) return;
        this.terminate();
        resolve(failureResult<T>(request, this.options.capability, {
          code: "worker-timeout",
          message: `Worker exceeded its ${request.limits.timeoutMs}ms limit`,
          provider: this.options.capability.id,
          retryable: true,
        }));
      }, request.limits.timeoutMs);
      this.active.set(request.id, { revisionId: request.revisionId, resolve: (result) => {
        window.clearTimeout(timeout);
        resolve(result as ProviderResult<T>);
      }});
      worker.postMessage(request);
    });
  }

  cancel(requestId: string): void {
    const active = this.active.get(requestId);
    if (!active) return;
    this.active.delete(requestId);
    active.resolve({
      id: requestId,
      provider: this.options.capability.id,
      status: "cancelled",
      capability: this.options.capability,
      revisionId: active.revisionId,
      createdAt: new Date().toISOString(),
      freshness: { state: "unknown", version: "", reason: "Cancelled" },
      failure: { code: "cancelled", message: "Worker request cancelled", retryable: true },
    });
    this.terminate();
  }

  restart(): void {
    this.terminate();
  }

  terminate(): void {
    this.worker?.terminate();
    this.worker = undefined;
    for (const [id, active] of this.active) {
      this.active.delete(id);
      active.resolve({
        id,
        provider: this.options.capability.id,
        status: "cancelled",
        capability: this.options.capability,
        revisionId: active.revisionId,
        createdAt: new Date().toISOString(),
        freshness: { state: "unknown", version: "", reason: "Worker terminated" },
        failure: { code: "worker-terminated", message: "Worker terminated", retryable: true },
      });
    }
  }

  private ensureWorker(): Worker {
    if (this.worker) return this.worker;
    const worker = this.options.createWorker();
    worker.onmessage = (event: MessageEvent<WorkerMessage<unknown>>) => {
      const message = event.data;
      if (message.kind === "progress") return;
      const active = this.active.get(message.id);
      if (!active) return;
      this.active.delete(message.id);
      if (!this.options.isRevisionCurrent(message.revisionId)) {
        active.resolve({
          id: message.id,
          provider: this.options.capability.id,
          status: "cancelled",
          capability: this.options.capability,
          revisionId: message.revisionId,
          createdAt: new Date().toISOString(),
          freshness: { state: "stale", version: message.revisionId, reason: "Stale worker result ignored" },
          failure: { code: "stale-revision", message: "Worker result belongs to an older revision", retryable: true },
        });
        return;
      }
      if (message.kind === "error") {
        active.resolve(failureResult({ id: message.id, revisionId: message.revisionId } as WorkerRequest,
          this.options.capability, message.failure));
        return;
      }
      const freshness: Freshness = message.freshness;
      active.resolve({
        id: message.id,
        provider: this.options.capability.id,
        status: "completed",
        capability: this.options.capability,
        revisionId: message.revisionId,
        createdAt: new Date().toISOString(),
        freshness,
        value: message.value,
      });
    };
    worker.onerror = () => this.failActive({
      code: "worker-runtime-failed",
      message: "Worker terminated after an unhandled runtime error",
      provider: this.options.capability.id,
      retryable: true,
    });
    this.worker = worker;
    return worker;
  }

  private failActive(failure: StructuredFailure): void {
    this.worker?.terminate();
    this.worker = undefined;
    for (const [id, active] of this.active) {
      this.active.delete(id);
      active.resolve({
        id,
        provider: this.options.capability.id,
        status: "failed",
        capability: this.options.capability,
        revisionId: active.revisionId,
        createdAt: new Date().toISOString(),
        freshness: { state: "unknown", version: "", reason: failure.message },
        failure,
      });
    }
  }
}
