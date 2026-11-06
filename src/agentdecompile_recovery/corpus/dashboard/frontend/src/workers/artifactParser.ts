import type { ProviderCapability } from "../analysis/contracts";
import { DisposableWorkerSession, type WorkerSessionOptions } from "./session";

export const artifactParserCapability: ProviderCapability = {
  id: "local-artifact-parser",
  label: "Local ELF/PE metadata parser",
  status: "available",
  version: "1",
  operations: ["inspect-artifact"],
};

export function createArtifactParserSession(
  isRevisionCurrent: WorkerSessionOptions["isRevisionCurrent"],
): DisposableWorkerSession {
  return new DisposableWorkerSession({
    capability: artifactParserCapability,
    isRevisionCurrent,
    createWorker: () => new Worker(new URL("./artifactParser.worker.ts", import.meta.url), { type: "module" }),
  });
}
