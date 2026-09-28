import type {
  EvidenceRecord,
  Freshness,
  FunctionRecord,
  InstructionRecord,
  NormalizedAnalysisModel,
  XrefRecord,
} from "../analysis/contracts";

export type ProjectIndexMatch = {
  kind: "function" | "instruction" | "evidence";
  id: string;
  label: string;
  revisionId: string;
};

export type RelationshipQuery = {
  address?: string;
  direction?: "incoming" | "outgoing" | "both";
  kind?: XrefRecord["kind"];
};

export class ProjectIndex {
  private functions: FunctionRecord[] = [];
  private instructions: InstructionRecord[] = [];
  private evidence: EvidenceRecord[] = [];
  private xrefs: XrefRecord[] = [];
  private freshness: Freshness = { state: "unknown", version: "" };
  private semanticEnabled = false;

  replace(model: NormalizedAnalysisModel): void {
    this.functions = model.functions;
    this.instructions = model.instructions;
    this.evidence = model.evidence;
    this.xrefs = model.xrefs;
    this.freshness = model.freshness ?? {
      state: "fresh",
      version: model.revision?.id ?? model.artifactHash ?? model.projectId,
      revisionId: model.revision?.id,
      indexedAt: new Date().toISOString(),
    };
  }

  setSemanticEnabled(enabled: boolean): void {
    this.semanticEnabled = enabled;
  }

  status(): { freshness: Freshness; semanticEnabled: boolean } {
    return { freshness: { ...this.freshness }, semanticEnabled: this.semanticEnabled };
  }

  exactSearch(query: string, limit = 100): { matches: ProjectIndexMatch[]; freshness: Freshness } {
    const needle = query.trim().toLowerCase();
    if (!needle) return { matches: [], freshness: this.status().freshness };
    const matches: ProjectIndexMatch[] = [];
    const add = (kind: ProjectIndexMatch["kind"], id: string, label: string, revisionId: string) => {
      if (matches.length < limit && label.toLowerCase().includes(needle)) matches.push({ kind, id, label, revisionId });
    };
    this.functions.forEach((record) => add("function", record.id, `${record.name ?? ""} ${record.address.offset} ${record.logicalId ?? ""}`, record.revisionId));
    this.instructions.forEach((record) => add("instruction", record.id, `${record.address.offset} ${record.mnemonic ?? ""} ${record.operands ?? ""}`, record.revisionId));
    this.evidence.forEach((record) => add("evidence", record.id, record.summary, record.source.revisionId));
    return { matches, freshness: this.status().freshness };
  }

  relationships(query: RelationshipQuery): { records: XrefRecord[]; freshness: Freshness } {
    const direction = query.direction ?? "both";
    return {
      records: this.xrefs.filter((record) => {
        if (query.kind && record.kind !== query.kind) return false;
        if (!query.address) return true;
        const outgoing = record.from.offset === query.address;
        const incoming = record.to.offset === query.address;
        return direction === "outgoing" ? outgoing : direction === "incoming" ? incoming : outgoing || incoming;
      }),
      freshness: this.status().freshness,
    };
  }
}
