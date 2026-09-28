import type {
  ArtifactRecord,
  BinaryRecord,
  EvidenceRecord,
  NormalizedAnalysisModel,
  ProviderResult,
  Revision,
} from "../analysis/contracts";
import { ProjectIndex } from "../index/projectIndex";
import { artifactParserCapability, createArtifactParserSession } from "../workers/artifactParser";
import type { ArtifactInspection } from "../workers/artifactParser.worker";
import { ingestArtifact, type ArtifactCandidate, type ArtifactIngestLimits } from "./artifactIngest";
import { projectStore } from "../storage/projectStore";

/**
 * Small composition root for the local-first slice. Views consume its model;
 * parser, IndexedDB, and index details do not leak into the selection bus.
 */
export class LocalProjectRuntime {
  readonly index = new ProjectIndex();
  private revisionId = "";
  private model: NormalizedAnalysisModel;

  constructor(readonly projectId: string) {
    this.model = {
      schemaVersion: 1,
      projectId,
      artifacts: [], binaries: [], functions: [], instructions: [], basicBlocks: [],
      xrefs: [], decompilerResults: [], findings: [], evidence: [],
      capabilities: [artifactParserCapability],
    };
  }

  current(): NormalizedAnalysisModel {
    return this.model;
  }

  async restore(): Promise<NormalizedAnalysisModel | undefined> {
    const snapshot = await projectStore.loadLatestSnapshot(this.projectId);
    if (!snapshot) return undefined;
    this.model = snapshot.model;
    this.revisionId = snapshot.revision.id;
    this.index.replace(this.model);
    return this.model;
  }

  async ingest(
    candidate: ArtifactCandidate,
    limits?: ArtifactIngestLimits,
  ): Promise<ProviderResult<NormalizedAnalysisModel>> {
    const inspectionRevisionId = crypto.randomUUID();
    const session = createArtifactParserSession((revisionId) => revisionId === inspectionRevisionId);
    const inspection = await session.run<ArtifactInspection>({
      id: crypto.randomUUID(), operation: "inspect-artifact", revisionId: inspectionRevisionId,
      payload: candidate.bytes, limits: { maxArtifactBytes: limits?.maxArtifactBytes ?? 512 * 1024 * 1024, timeoutMs: 10_000 },
    }).finally(() => session.terminate());
    if (inspection.status !== "completed") return inspection as unknown as ProviderResult<NormalizedAnalysisModel>;

    const artifact = await ingestArtifact(this.projectId, candidate, artifactParserCapability, limits);
    if (artifact.status !== "completed" || !artifact.value) return artifact as unknown as ProviderResult<NormalizedAnalysisModel>;
    const revision: Revision = {
      id: artifact.value.hash, sourceHash: artifact.value.hash, schemaVersion: 1,
      createdAt: artifact.createdAt, provenance: artifact.value.provenance,
    };
    this.revisionId = revision.id;
    this.model = this.withArtifact(artifact.value, revision, inspection.value);
    this.index.replace(this.model);
    await projectStore.saveSnapshot({ projectId: this.projectId, revision, model: this.model, capabilities: this.model.capabilities });
    return { ...artifact, revisionId: revision.id, value: this.model };
  }

  private withArtifact(
    artifact: ArtifactRecord,
    revision: Revision,
    inspection: ArtifactInspection | undefined,
  ): NormalizedAnalysisModel {
    const artifacts = [...this.model.artifacts.filter((item) => item.hash !== artifact.hash), artifact];
    const binary: BinaryRecord = {
      id: artifact.hash,
      artifactHash: artifact.hash,
      name: artifact.name,
      architecture: artifact.architecture,
      format: artifact.format,
      projectIds: [this.projectId],
      revisionId: revision.id,
    };
    const binaries = [...this.model.binaries.filter((item) => item.artifactHash !== artifact.hash), binary];
    const parserEvidence: EvidenceRecord = {
      id: `local-parser:${artifact.hash}`,
      claim: "identity",
      summary: `${artifact.name} is a ${artifact.architecture} ${artifact.format.toUpperCase()} artifact with ${artifact.byteLength.toLocaleString()} bytes. The bounded local parser observed ${inspection?.strings.length ?? 0} printable strings.`,
      source: {
        artifactHash: artifact.hash,
        revisionId: revision.id,
        provider: artifactParserCapability.id,
        providerVersion: artifactParserCapability.version,
      },
      confidence: 1,
      gaps: ["Local metadata inspection does not establish functions, behavior, source recovery, or byte-equivalent matching."],
    };
    const evidence = [...this.model.evidence.filter((item) => item.source.artifactHash !== artifact.hash), parserEvidence];
    return {
      ...this.model,
      artifactHash: artifact.hash,
      revision,
      artifacts,
      binaries,
      evidence,
      freshness: { state: "fresh", version: revision.id, revisionId: revision.id, indexedAt: revision.createdAt },
    };
  }
}
