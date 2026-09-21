import { describe, expect, it } from "vitest";
import type { ArtifactRecord } from "../analysis/contracts";
import { matchRecordedArtifact } from "./LocalArtifactPanel";

const artifact: ArtifactRecord = {
  id: "a".repeat(64),
  hash: "a".repeat(64),
  name: "game.exe",
  format: "pe",
  architecture: "x86",
  byteLength: 42,
  createdAt: "2026-09-10T00:00:00.000Z",
  provenance: {
    provider: "local-artifact-parser",
    artifactHash: "a".repeat(64),
    observedAt: "2026-09-10T00:00:00.000Z",
  },
};

describe("matchRecordedArtifact", () => {
  it("opens only a unique exact SHA-256 binary match", () => {
    const binary = { kind: "binary", slug: "k1", sha256: "A".repeat(64) };
    expect(matchRecordedArtifact(artifact, [binary, { kind: "project", sha256: artifact.hash }]))
      .toEqual({ state: "unique", binary });
  });

  it("keeps duplicate corpus records ambiguous", () => {
    const binaries = [
      { kind: "binary", slug: "one", sha256: artifact.hash },
      { kind: "binary", slug: "two", sha256: artifact.hash },
    ];
    expect(matchRecordedArtifact(artifact, binaries)).toEqual({ state: "ambiguous", binaries });
  });

  it("does not infer identity from a name or partial hash", () => {
    expect(matchRecordedArtifact(artifact, [
      { kind: "binary", name: artifact.name, sha256: artifact.hash.slice(0, 12) },
    ])).toEqual({ state: "unseen" });
  });
});
