import type {
  Freshness,
  ProviderCapability,
  ProviderResult,
  StructuredFailure,
} from "../analysis/contracts";

export type WorkerOperation = "inspect-artifact" | "build-index";

export type WorkerLimits = {
  maxArtifactBytes: number;
  timeoutMs: number;
};

export type WorkerRequest<T = unknown> = {
  id: string;
  operation: WorkerOperation;
  revisionId: string;
  payload: T;
  limits: WorkerLimits;
};

export type WorkerProgress = {
  id: string;
  revisionId: string;
  completed: number;
  total?: number;
  message?: string;
};

export type WorkerSuccess<T> = {
  kind: "result";
  id: string;
  revisionId: string;
  value: T;
  freshness: Freshness;
};

export type WorkerFailure = {
  kind: "error";
  id: string;
  revisionId: string;
  failure: StructuredFailure;
};

export type WorkerMessage<T> =
  | { kind: "progress"; progress: WorkerProgress }
  | WorkerSuccess<T>
  | WorkerFailure;

export type WorkerProviderResult<T> = ProviderResult<T> & {
  capability: ProviderCapability;
};
