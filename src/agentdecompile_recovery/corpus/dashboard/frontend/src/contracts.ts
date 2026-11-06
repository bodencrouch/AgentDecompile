export type Data = Record<string, any>;
export {
  ANALYSIS_SCHEMA_VERSION,
  unsupportedCapability,
  type Address,
  type ActionDescriptor,
  type AnalysisJob,
  type ActionParityMatrix,
  type ArtifactFormat,
  type ArtifactRecord,
  type BasicBlockRecord,
  type BinaryRecord,
  type CapabilityStatus,
  type ClaimBoundary,
  type DecompilerResult,
  type EvidenceRecord,
  type FindingRecord,
  type Freshness,
  type FreshnessState,
  type FunctionRecord,
  type InstructionRecord,
  type NormalizedAnalysisModel,
  type Pagination,
  type JobCheckpoint,
  type ProviderCapability,
  type ProviderResult,
  type ProviderResultStatus,
  type Region,
  type Revision,
  type RevisionConflict,
  type SharedContext,
  type StructuredFailure,
  type XrefRecord,
  actionParityIssues,
} from "./analysis/contracts";
export interface Selection {
  slug: string;
  program: string;
  addr: string;
  logicalId: string;
  /** Opaque database-file identity; not a content revision or equivalence proof. */
  corpusIdentity?: string;
  locator: string;
  projectId?: string;
  binaryHash?: string;
  functionId?: string;
  /** Last explicitly inspected function; data-address navigation leaves it intact. */
  lastFunctionAddr?: string;
  region?: import("./analysis/contracts").Region;
  evidenceIds?: string[];
}
export const emptySelection: Selection = {
  slug: "",
  program: "",
  addr: "",
  logicalId: "",
  locator: "",
};
/** Older project links put the project database path in the program field. */
export function normalizeSelection(value: Partial<Selection>): Selection {
  const selection = { ...emptySelection, ...value };
  if (!selection.locator && /^(?:\/|[A-Za-z]:[\\/]).*\.(?:gpr|rep)\/?$/i.test(selection.program)) {
    return { ...emptySelection, locator: selection.program };
  }
  return selection;
}
export type Notify = (
  message: string,
  level?: "info" | "error" | "warning",
  details?: Data,
) => void;
export interface ActionRequest {
  id: string;
  params?: Data;
  targets?: Selection[];
}
export type OnAction = (
  id: string,
  params?: Data,
  targets?: Selection[],
) => void;
export interface SurfaceProps {
  selection: Selection;
  onSelect: (patch: Partial<Selection>) => void;
  onAction: OnAction;
  onInspectSource?: () => void;
  notify: Notify;
  revision: number;
  onBrowseFunctions?: (scope: {
    slugs: string[];
    program?: string;
    locator?: string;
    filter: "all" | "named" | "bound" | "real-c";
  }) => void;
}
export const API = "/dashboard/api/workbench";
export async function request<T = Data>(
  url: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: {
      ...(init.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      ...init.headers,
    },
  });
  const raw = await response.text();
  const accepted = response.ok || response.status === 202;
  let data: Data = {};
  if (raw.trim()) {
    try {
      data = JSON.parse(raw) as Data;
    } catch {
      throw new Error(
        raw.trim().length < 80
          ? `Incomplete JSON from server (${response.status})`
          : `Invalid JSON from server (${response.status})`,
      );
    }
  } else if (!accepted) {
    throw new Error(`Request failed (${response.status})`);
  }
  if (!accepted || data.ok === false) {
    const detail = Array.isArray(data.detail)
      ? data.detail
          .map((item: Data) => `${(item.loc || []).join(".")}: ${item.msg}`)
          .join("; ")
      : data.detail;
    throw new Error(
      data.error ||
        detail ||
        (data.errors || []).join("; ") ||
        `Request failed (${response.status})`,
    );
  }
  return data as T;
}
export function query(
  selection: Partial<Selection>,
  extras: Data = {},
): string {
  const params = new URLSearchParams();
  Object.entries({ ...selection, ...extras }).forEach(([key, value]) => {
    if (value !== "" && value !== undefined && value !== null)
      params.set(key === "logicalId" ? "logical_id" : key === "corpusIdentity" ? "corpus_identity" : key, String(value));
  });
  return params.toString();
}
export function functionKey(selection: Selection): string {
  return [
    selection.locator,
    selection.slug,
    selection.program,
    selection.binaryHash,
    selection.functionId,
    selection.addr,
    selection.logicalId,
    selection.corpusIdentity,
    selection.region?.start.offset,
    selection.region?.end?.offset,
  ].join("\u001f");
}

export function recordedSelection(job: Data, fallback: Selection): Selection {
  const p = job.params || {};
  const program = p.programPath || p.program || fallback.program;
  const same = program === fallback.program && (!p.locator || p.locator === fallback.locator);
  return {locator: p.locator || (same ? fallback.locator : ""), program,
    slug: p.slug || (same ? fallback.slug : ""),
    addr: p.functionIdentifier || p.addressOrSymbol || p.address_or_symbol || p.address || p.addr || "",
    logicalId: String(p.logical_id || "")};
}
