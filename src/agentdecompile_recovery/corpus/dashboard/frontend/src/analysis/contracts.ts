export const ANALYSIS_SCHEMA_VERSION = 1 as const;

export type ClaimBoundary =
  | "identity"
  | "code-equality"
  | "behavioral-equivalence"
  | "source-recovery"
  | "objdiff-proof";

export type CapabilityStatus = "available" | "pending" | "unsupported" | "unavailable";
export type ProviderResultStatus =
  | "queued"
  | "running"
  | "paused"
  | "completed"
  | "partial"
  | "disconnected"
  | "resync"
  | "resumable"
  | "cancelling"
  | "blocked"
  | "pending"
  | "unsupported"
  | "unavailable"
  | "failed"
  | "cancelled";
export type FreshnessState = "fresh" | "stale" | "building" | "unknown";

export type Address = {
  binaryHash: string;
  offset: string;
  space?: string;
};

export type Region = {
  start: Address;
  end?: Address;
  label?: string;
};

export type Provenance = {
  provider: string;
  providerVersion?: string;
  artifactHash?: string;
  revisionId?: string;
  observedAt: string;
};

export type Revision = {
  id: string;
  sourceHash: string;
  schemaVersion: number;
  createdAt: string;
  parentId?: string;
  provenance?: Provenance;
};

export type Pagination = {
  offset: number;
  limit: number;
  total?: number;
  nextOffset?: number;
};

export type Freshness = {
  state: FreshnessState;
  version: string;
  indexedAt?: string;
  revisionId?: string;
  reason?: string;
};

export type ArtifactFormat = "elf" | "pe" | "macho" | "wasm" | "unknown";
export type ArtifactRecord = {
  id: string;
  hash: string;
  name: string;
  format: ArtifactFormat;
  architecture: string;
  byteLength: number;
  createdAt: string;
  provenance: Provenance;
};

export type BinaryRecord = {
  id: string;
  artifactHash: string;
  name: string;
  architecture: string;
  format: ArtifactFormat;
  projectIds: string[];
  revisionId: string;
};

export type FunctionRecord = {
  id: string;
  name?: string;
  address: Address;
  logicalId?: string;
  binaryHash: string;
  revisionId: string;
  region?: Region;
  provenance?: Provenance;
};

export type InstructionRecord = {
  id: string;
  address: Address;
  bytes: string;
  mnemonic?: string;
  operands?: string;
  functionId?: string;
  revisionId: string;
};

export type BasicBlockRecord = {
  id: string;
  functionId: string;
  region: Region;
  successorIds: string[];
  revisionId: string;
};

export type XrefRecord = {
  id: string;
  from: Address;
  to: Address;
  kind: "call" | "jump" | "read" | "write" | "data" | "unknown";
  revisionId: string;
};

export type DecompilerResult = {
  id: string;
  functionId: string;
  provider: string;
  providerVersion?: string;
  text?: string;
  status: ProviderResultStatus;
  revisionId: string;
  provenance: Provenance;
};

export type FindingRecord = {
  id: string;
  title: string;
  summary: string;
  severity?: "info" | "low" | "medium" | "high" | "critical";
  region?: Region;
  evidenceIds: string[];
  revisionId: string;
  provenance: Provenance;
};

export type EvidenceRecord = {
  id: string;
  claim: ClaimBoundary;
  summary: string;
  source: {
    artifactHash: string;
    revisionId: string;
    provider: string;
    providerVersion?: string;
    addresses?: Address[];
    region?: Region;
  };
  confidence?: number;
  hypotheses?: string[];
  alternatives?: string[];
  gaps?: string[];
};

export type ProviderCapability = {
  id: string;
  label: string;
  status: CapabilityStatus;
  version?: string;
  reason?: string;
  operations?: string[];
  freshness?: Freshness;
};

export type StructuredFailure = {
  code: string;
  message: string;
  provider?: string;
  retryable: boolean;
  details?: Record<string, unknown>;
  causedBy?: string;
};

export type ProviderResult<T> = {
  id: string;
  provider: string;
  status: ProviderResultStatus;
  capability: ProviderCapability;
  revisionId: string;
  createdAt: string;
  freshness: Freshness;
  value?: T;
  failure?: StructuredFailure;
  pagination?: Pagination;
};

export type AnalysisJob = {
  id: string;
  batchId?: string;
  providerAttemptId?: string;
  idempotencyKey?: string;
  provider: string;
  status: ProviderResultStatus;
  revisionId: string;
  createdAt: string;
  updatedAt: string;
  progress?: { completed: number; total?: number; message?: string };
  checkpointCursor?: string;
  checkpoints?: JobCheckpoint[];
  lease?: { ownerId: string; expiresAt: string; heartbeatAt?: string };
  cancellation?: { requestedAt: string; acknowledgedAt?: string };
  receiptIds?: string[];
  resumable?: boolean;
};

/** Ordered, durable progress marker: completion must always be established by a receipt. */
export type JobCheckpoint = {
  cursor: string;
  createdAt: string;
  message?: string;
  progress?: { completed: number; total?: number };
  partialEvidenceIds?: string[];
};

export type SharedContext = {
  projectId: string;
  artifactHash?: string;
  binaryHash?: string;
  revisionId?: string;
  selectionId?: string;
  address?: Address;
  logicalId?: string;
  region?: Region;
  evidenceIds: string[];
  capabilities?: ProviderCapability[];
  freshness?: Freshness;
  permissions?: string[];
  approvalIds?: string[];
  jobSummaries?: Pick<AnalysisJob, "id" | "batchId" | "providerAttemptId" | "status" | "revisionId" | "checkpointCursor">[];
  pagination?: Pagination;
};

export type ActionDescriptor = {
  id: string;
  label: string;
  kind: "primitive" | "workflow";
  mutable: boolean;
  approvalRequired: boolean;
  capabilityId?: string;
  mcpAction?: string;
  cliAction?: string;
  apiAction?: string;
  humanOnlyReason?: string;
};

/** The shared action inventory is the parity matrix consumed by UI and agents. */
export type ActionParityMatrix = Record<string, ActionDescriptor>;

export function actionParityIssues(actions: readonly ActionDescriptor[]): string[] {
  return actions.flatMap((action) => {
    const machineRoutes = [action.mcpAction, action.cliAction, action.apiAction].filter(Boolean);
    if (action.humanOnlyReason) {
      return machineRoutes.length ? [`${action.id}: human-only actions cannot advertise machine routes`] : [];
    }
    return machineRoutes.length ? [] : [`${action.id}: missing MCP, CLI, or API action`];
  });
}

export type Approval = {
  id: string;
  actionId: string;
  status: "pending" | "approved" | "rejected" | "expired";
  createdAt: string;
};

export type RevisionConflict = {
  id: string;
  localRevisionId: string;
  remoteRevisionId: string;
  reason: string;
  resolution?: "local" | "remote" | "manual";
};

export type NormalizedAnalysisModel = {
  schemaVersion: typeof ANALYSIS_SCHEMA_VERSION;
  projectId: string;
  artifactHash?: string;
  revision?: Revision;
  artifacts: ArtifactRecord[];
  binaries: BinaryRecord[];
  functions: FunctionRecord[];
  instructions: InstructionRecord[];
  basicBlocks: BasicBlockRecord[];
  xrefs: XrefRecord[];
  decompilerResults: DecompilerResult[];
  findings: FindingRecord[];
  evidence: EvidenceRecord[];
  capabilities: ProviderCapability[];
  freshness?: Freshness;
};

export function unsupportedCapability(
  id: string,
  label: string,
  reason: string,
): ProviderCapability {
  return { id, label, status: "unsupported", reason };
}

export function unavailableProviderResult<T>(
  id: string,
  provider: string,
  revisionId: string,
  reason: string,
  capability: ProviderCapability = {
    id: provider,
    label: provider,
    status: "unavailable",
    reason,
  },
): ProviderResult<T> {
  return {
    id,
    provider,
    status: capability.status === "available" ? "pending" : capability.status,
    capability,
    revisionId,
    createdAt: new Date().toISOString(),
    freshness: { state: "unknown", version: revisionId, reason },
    failure: { code: "provider-unavailable", message: reason, provider, retryable: true },
  };
}
