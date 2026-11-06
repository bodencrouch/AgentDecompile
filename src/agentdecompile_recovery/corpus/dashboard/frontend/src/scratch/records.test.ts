import { expect, test, vi } from "vitest";
import { emptySelection } from "../contracts";
import { projectStore } from "../storage/projectStore";
import { candidateHash, loadScratches, parseScratch, presetCompatible, resultBelongs, saveScratch, translationUnit, type Scratch } from "./records";

const scratch: Scratch = { schema: 1, id: "scratch-one", revision: 4, title: "Local add", platform: "x86", preset: "configured", symbol: "add", target: "ret", source: "int add(void) { return VALUE; }", context: "#define VALUE 1", createdAt: "2026-09-11T00:00:00Z", binding: { selection: { ...emptySelection, addr: "00401000", binaryHash: "a".repeat(64) }, artifactHash: "a".repeat(64), targetRevision: "b".repeat(64) } };
test("scratch round-trip preserves context, rejects stale receipts in every phase, and restricts preset targets", async () => {
  const artifact = vi.spyOn(projectStore, "saveArtifact").mockResolvedValue();
  const membership = vi.spyOn(projectStore, "saveMembership").mockResolvedValue();
  try {
    await saveScratch(scratch);
    vi.spyOn(projectStore, "memberships").mockResolvedValue([membership.mock.calls[0][0]]);
    vi.spyOn(projectStore, "loadArtifact").mockResolvedValue(artifact.mock.calls[0][0]);
    expect(await loadScratches()).toEqual({ scratches: [scratch], warnings: [] });
    expect(translationUnit(scratch)).toBe("#define VALUE 1\n\nint add(void) { return VALUE; }");
    const hash = await candidateHash(scratch);
    expect(hash).not.toBe(await candidateHash({ ...scratch, context: "#define VALUE 2" }));
    const attempt = { id: scratch.id, revision: scratch.revision, hash };
    const result = { candidateRevision: hash, artifactHash: scratch.binding!.artifactHash, targetRevision: scratch.binding!.targetRevision, function: scratch.symbol, compilerPreset: scratch.preset };
    expect(resultBelongs(scratch, attempt, result)).toBe(true);
    expect(resultBelongs({ ...scratch, revision: 5 }, attempt, result)).toBe(false);
    expect(resultBelongs({ ...scratch, id: "another-scratch" }, attempt, result)).toBe(false);
    expect(resultBelongs(scratch, attempt, { ...result, targetRevision: "c".repeat(64) })).toBe(false);
    expect(resultBelongs(scratch, attempt, { ...result, compilerPreset: "other" })).toBe(false);
    expect(resultBelongs(scratch, attempt, { ...result, phase: "objdiff-verified", receipt: { ...result, artifactHash: "c".repeat(64) } })).toBe(false);
    for (const phase of ["mismatch", "failed", "objdiff-verified"]) {
      expect(resultBelongs(scratch, attempt, { ...result, phase, receipt: { ...result } })).toBe(true);
      for (const key of ["candidateRevision", "targetRevision", "artifactHash", "function", "compilerPreset"]) {
        expect(resultBelongs(scratch, attempt, { ...result, phase, receipt: { ...result, [key]: "unrelated" } })).toBe(false);
      }
    }
    expect(presetCompatible(scratch, { targets: [{ function: "add", targetRevision: "b".repeat(64) }] })).toBe(true);
    expect(presetCompatible(scratch, { targets: [{ function: "add", targetRevision: "c".repeat(64) }] })).toBe(false);
    expect(presetCompatible(scratch, { targets: [{ function: "other", targetRevision: "b".repeat(64) }] })).toBe(false);
    expect(parseScratch(JSON.parse(JSON.stringify({ ...scratch, binding: null })))).toMatchObject({ binding: null });
    expect(parseScratch({ ...scratch, title: "", target: "" })).toMatchObject({ target: "" });
    for (const broken of [null, {}, { ...scratch, revision: -1 }, { ...scratch, target: 12 }, { ...scratch, binding: {} }]) expect(() => parseScratch(broken)).toThrow();
    artifact.mockRejectedValueOnce(new Error("Quota exceeded"));
    await expect(saveScratch(scratch)).rejects.toThrow("Quota exceeded");
    expect((await loadScratches()).warnings.join(" ")).toContain("Quota exceeded");
    await saveScratch(scratch);
  } finally { vi.restoreAllMocks(); }
});

test("a remount load waits for the shared slow-write queue and sees the newest draft", async () => {
  let release!: () => void, started!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  const beginning = new Promise<void>(resolve => { started = resolve; });
  let stored: Parameters<typeof projectStore.saveArtifact>[0] | undefined;
  const key = `agentdecompile.local-scratches.v1:${scratch.id}`;
  vi.spyOn(projectStore, "saveArtifact").mockImplementationOnce(async value => { started(); await gate; stored = value; })
    .mockImplementation(async value => { stored = value; });
  vi.spyOn(projectStore, "saveMembership").mockResolvedValue();
  vi.spyOn(projectStore, "memberships").mockResolvedValue([{ id: key, projectId: "agentdecompile.local-scratches.v1", artifactHash: key, createdAt: scratch.createdAt }]);
  vi.spyOn(projectStore, "loadArtifact").mockImplementation(async () => stored);
  try {
    const olderWrite = saveScratch(scratch);
    await beginning;
    const newest = { ...scratch, revision: 5, source: "int add(void) { return 2; }" };
    const newerWrite = saveScratch(newest);
    let loaded = false;
    const remount = loadScratches().then(result => { loaded = true; return result; });
    await Promise.resolve(); expect(loaded).toBe(false);
    release(); await Promise.all([olderWrite, newerWrite]);
    expect(await remount).toEqual({ scratches: [newest], warnings: [] });
  } finally { release(); vi.restoreAllMocks(); }
});

test("corrupt and missing entries preserve healthy scratches and expose warnings without writes", async () => {
  const projectId = "agentdecompile.local-scratches.v1";
  const keys = [scratch.id, "corrupt", "missing"].map(id => `${projectId}:${id}`);
  vi.spyOn(projectStore, "memberships").mockResolvedValue(keys.map(key => ({ id: key, projectId, artifactHash: key, createdAt: scratch.createdAt })));
  vi.spyOn(projectStore, "loadArtifact").mockImplementation(async key => key === keys[2] ? undefined : {
    hash: key, name: key, createdAt: scratch.createdAt,
    bytes: new TextEncoder().encode(key === keys[0] ? JSON.stringify(scratch) : "invalid JSON").buffer,
  });
  const write = vi.spyOn(projectStore, "saveArtifact");
  try {
    const result = await loadScratches();
    expect(result.scratches).toEqual([scratch]);
    expect(result.warnings).toHaveLength(2);
    expect(result.warnings.join(" ")).toContain("missing");
    expect(result.warnings.join(" ")).toContain("corrupt");
    expect(write).not.toHaveBeenCalled();
  } finally { vi.restoreAllMocks(); }
});
