import type {
  ArtifactFormat,
  ArtifactRecord,
  ProviderCapability,
  ProviderResult,
} from "../analysis/contracts";
import { projectStore, type StoredArtifact } from "../storage/projectStore";

export type ArtifactIngestLimits = {
  maxArtifactBytes: number;
  allowedFormats: readonly ArtifactFormat[];
};

export type ArtifactCandidate = {
  name: string;
  bytes: ArrayBuffer;
  sourceLocator?: string;
  declaredType?: string;
  sourceKind?: "regular" | "directory" | "symlink" | "device";
};

export type ArtifactValidation =
  | { ok: true; format: ArtifactFormat; architecture: string }
  | { ok: false; code: string; message: string };

export const defaultArtifactIngestLimits: ArtifactIngestLimits = {
  maxArtifactBytes: 512 * 1024 * 1024,
  allowedFormats: ["elf", "pe"],
};

function inspectFormat(bytes: ArrayBuffer): { format: ArtifactFormat; architecture: string } {
  const data = new Uint8Array(bytes);
  const view = new DataView(bytes);
  if (data.length >= 20 && data[0] === 0x7f && data[1] === 0x45 && data[2] === 0x4c && data[3] === 0x46) {
    const littleEndian = data[5] !== 2;
    const machine = view.getUint16(18, littleEndian);
    return { format: "elf", architecture: ({ 3: "x86", 40: "arm", 62: "x86_64", 183: "aarch64" } as Record<number, string>)[machine] ?? "unknown" };
  }
  if (data.length >= 0x40 && data[0] === 0x4d && data[1] === 0x5a) {
    const offset = view.getUint32(0x3c, true);
    if (offset + 6 <= data.length && data[offset] === 0x50 && data[offset + 1] === 0x45) {
      const machine = view.getUint16(offset + 4, true);
      return { format: "pe", architecture: ({ 0x14c: "x86", 0x8664: "x86_64", 0x1c0: "arm", 0xaa64: "aarch64" } as Record<number, string>)[machine] ?? "unknown" };
    }
  }
  return { format: "unknown", architecture: "unknown" };
}

export function validateArtifact(
  candidate: ArtifactCandidate,
  limits: ArtifactIngestLimits = defaultArtifactIngestLimits,
): ArtifactValidation {
  if (!candidate.name || candidate.name.includes("\0")) {
    return { ok: false, code: "unsafe-name", message: "Artifact name is required and must not contain NUL" };
  }
  if (candidate.sourceLocator?.split(/[\\/]/).includes("..")) {
    return { ok: false, code: "unsafe-path", message: "Artifact source path must not contain traversal segments" };
  }
  if (candidate.sourceKind && candidate.sourceKind !== "regular") {
    return { ok: false, code: "unsafe-source", message: "Only regular artifact files can be analyzed locally" };
  }
  if (/\.(?:zip|7z|rar|tar|gz|bz2|xz)$/i.test(candidate.name)) {
    return { ok: false, code: "archive-unsupported", message: "Archives are not expanded by the local artifact runtime" };
  }
  if (candidate.bytes.byteLength === 0) {
    return { ok: false, code: "empty-artifact", message: "Artifact is empty" };
  }
  if (candidate.bytes.byteLength > limits.maxArtifactBytes) {
    return { ok: false, code: "artifact-too-large", message: "Artifact exceeds the local storage limit" };
  }
  const inspection = inspectFormat(candidate.bytes);
  if (!limits.allowedFormats.includes(inspection.format)) {
    return {
      ok: false,
      code: "unsupported-format",
      message: `Artifact format ${inspection.format} is not available in this runtime`,
    };
  }
  return { ok: true, ...inspection };
}

async function sha256(bytes: ArrayBuffer): Promise<string> {
  if (!globalThis.crypto?.subtle) throw new Error("Web Crypto is unavailable; artifact hashing cannot proceed");
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((value) => value.toString(16).padStart(2, "0")).join("");
}

export async function ingestArtifact(
  projectId: string,
  candidate: ArtifactCandidate,
  capability: ProviderCapability,
  limits = defaultArtifactIngestLimits,
): Promise<ProviderResult<ArtifactRecord>> {
  const validation = validateArtifact(candidate, limits);
  const now = new Date().toISOString();
  if (!validation.ok) {
    return {
      id: crypto.randomUUID(),
      provider: capability.id,
      status: "failed",
      capability,
      revisionId: "",
      createdAt: now,
      freshness: { state: "unknown", version: "", reason: validation.message },
      failure: { code: validation.code, message: validation.message, retryable: false },
    };
  }
  try {
    const hash = await sha256(candidate.bytes);
    const stored: StoredArtifact = {
      hash,
      name: candidate.name,
      bytes: candidate.bytes,
      createdAt: now,
      format: validation.format,
      architecture: validation.architecture,
      sourceName: candidate.sourceLocator,
    };
    await projectStore.saveArtifact(stored);
    await projectStore.saveMembership({
      id: `${projectId}:${hash}`,
      projectId,
      artifactHash: hash,
      sourceLocator: candidate.sourceLocator,
      createdAt: now,
    });
    return {
      id: crypto.randomUUID(),
      provider: capability.id,
      status: "completed",
      capability,
      revisionId: hash,
      createdAt: now,
      freshness: { state: "fresh", version: hash, revisionId: hash, indexedAt: now },
      value: {
        id: hash,
        hash,
        name: candidate.name,
        format: validation.format,
        architecture: validation.architecture,
        byteLength: candidate.bytes.byteLength,
        createdAt: now,
        provenance: { provider: capability.id, providerVersion: capability.version, artifactHash: hash, observedAt: now },
      },
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : "Artifact persistence failed";
    return {
      id: crypto.randomUUID(),
      provider: capability.id,
      status: "failed",
      capability,
      revisionId: "",
      createdAt: now,
      freshness: { state: "unknown", version: "", reason: message },
      failure: { code: "artifact-persistence-failed", message, provider: capability.id, retryable: true },
    };
  }
}
