import type { ArtifactFormat } from "../analysis/contracts";
import type { WorkerMessage, WorkerRequest } from "./protocol";

export type ArtifactInspection = {
  format: ArtifactFormat;
  architecture: string;
  byteLength: number;
  strings: string[];
};

const architectureByElfMachine: Record<number, string> = {
  3: "x86",
  40: "arm",
  62: "x86_64",
  183: "aarch64",
};
const architectureByPeMachine: Record<number, string> = {
  0x14c: "x86",
  0x8664: "x86_64",
  0x1c0: "arm",
  0xaa64: "aarch64",
};

function asciiStrings(bytes: Uint8Array, maximum = 250): string[] {
  const results: string[] = [];
  let start = -1;
  for (let index = 0; index <= bytes.length; index += 1) {
    const printable = index < bytes.length && bytes[index] >= 0x20 && bytes[index] <= 0x7e;
    if (printable && start < 0) start = index;
    if ((!printable || index === bytes.length) && start >= 0) {
      if (index - start >= 4) results.push(new TextDecoder().decode(bytes.slice(start, index)));
      start = -1;
      if (results.length >= maximum) break;
    }
  }
  return results;
}

function inspect(bytes: Uint8Array): ArtifactInspection {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (bytes.length >= 20 && bytes[0] === 0x7f && bytes[1] === 0x45 && bytes[2] === 0x4c && bytes[3] === 0x46) {
    const littleEndian = bytes[5] !== 2;
    return {
      format: "elf",
      architecture: architectureByElfMachine[view.getUint16(18, littleEndian)] ?? "unknown",
      byteLength: bytes.length,
      strings: asciiStrings(bytes),
    };
  }
  if (bytes.length >= 0x40 && bytes[0] === 0x4d && bytes[1] === 0x5a) {
    const offset = view.getUint32(0x3c, true);
    if (offset + 6 <= bytes.length && bytes[offset] === 0x50 && bytes[offset + 1] === 0x45) {
      return {
        format: "pe",
        architecture: architectureByPeMachine[view.getUint16(offset + 4, true)] ?? "unknown",
        byteLength: bytes.length,
        strings: asciiStrings(bytes),
      };
    }
  }
  throw new Error("Unsupported or malformed artifact; expected ELF or PE");
}

self.onmessage = (event: MessageEvent<WorkerRequest<ArrayBuffer>>) => {
  const request = event.data;
  try {
    if (request.payload.byteLength > request.limits.maxArtifactBytes) {
      const error: WorkerMessage<ArtifactInspection> = {
        kind: "error",
        id: request.id,
        revisionId: request.revisionId,
        failure: {
          code: "artifact-too-large",
          message: "Artifact exceeds the worker memory limit",
          retryable: false,
        },
      };
      self.postMessage(error);
      return;
    }
    const value = inspect(new Uint8Array(request.payload));
    const result: WorkerMessage<ArtifactInspection> = {
      kind: "result",
      id: request.id,
      revisionId: request.revisionId,
      value,
      freshness: { state: "fresh", version: request.revisionId, indexedAt: new Date().toISOString() },
    };
    self.postMessage(result);
  } catch (error) {
    const failure: WorkerMessage<ArtifactInspection> = {
      kind: "error",
      id: request.id,
      revisionId: request.revisionId,
      failure: {
        code: "artifact-parse-failed",
        message: error instanceof Error ? error.message : "Artifact parsing failed",
        retryable: false,
      },
    };
    self.postMessage(failure);
  }
};
