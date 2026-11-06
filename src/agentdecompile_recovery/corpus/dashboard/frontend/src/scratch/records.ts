import type { Data, Selection } from "../contracts";
import { projectStore } from "../storage/projectStore";

export type Scratch = {
  schema: 1; id: string; revision: number; title: string; platform: string;
  preset: string; symbol: string; target: string; context: string; source: string;
  createdAt: string; binding: { selection: Selection; artifactHash: string; targetRevision: string } | null;
};
const projectId = "agentdecompile.local-scratches.v1";
const hashPattern = /^[a-f0-9]{64}$/;
// One owner across React mounts; loads wait for edits already accepted here.
let writes: Promise<void> = Promise.resolve();
const pendingDrafts = new Map<string, Scratch>();
const writeWarnings = new Map<string, string>();
export function parseScratch(value: unknown): Scratch {
  const s = value as Scratch;
  if (!s || s.schema !== 1 || !Number.isSafeInteger(s.revision) || s.revision < 0
    || ![s.id, s.title, s.platform, s.preset, s.symbol, s.target, s.context, s.source, s.createdAt].every(v => typeof v === "string")
    || !s.id
    || (s.binding !== null && (!s.binding || !hashPattern.test(s.binding.artifactHash)
      || !hashPattern.test(s.binding.targetRevision) || !s.binding.selection
      || ![s.binding.selection.slug, s.binding.selection.program, s.binding.selection.addr,
        s.binding.selection.logicalId, s.binding.selection.locator].every(v => typeof v === "string")
      || !s.binding.selection.addr))) throw new Error("Invalid scratch record; stored data was not overwritten.");
  return s;
}
export function translationUnit(s: Pick<Scratch, "context" | "source">) {
  return s.context ? `${s.context}\n\n${s.source}` : s.source;
}
export async function candidateHash(s: Pick<Scratch, "context" | "source">) {
  const hash = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(translationUnit(s)));
  return Array.from(new Uint8Array(hash), byte => byte.toString(16).padStart(2, "0")).join("");
}
export function resultBelongs(s: Scratch, attempt: { id: string; revision: number; hash: string }, result: Data) {
  return s.id === attempt.id && s.revision === attempt.revision && !!s.binding
    && result.candidateRevision === attempt.hash && result.targetRevision === s.binding.targetRevision
    && result.artifactHash === s.binding.artifactHash && result.function === s.symbol
    && result.compilerPreset === s.preset
    && (result.phase !== "objdiff-verified" || !!result.receipt)
    && (result.receipt == null || typeof result.receipt === "object" && !Array.isArray(result.receipt)
      && result.receipt.artifactHash === s.binding.artifactHash
      && result.receipt.targetRevision === s.binding.targetRevision
      && result.receipt.candidateRevision === attempt.hash
      && result.receipt.function === s.symbol && result.receipt.compilerPreset === s.preset
      && result.receipt.compilerPresetFingerprint === result.compilerPresetFingerprint);
}
export function presetCompatible(s: Scratch, descriptor: Data): boolean {
  return !!s.binding && Array.isArray(descriptor.targets) && descriptor.targets.some((t: Data) =>
    t?.function === s.symbol && t.targetRevision === s.binding!.targetRevision);
}
export async function saveScratch(scratch: Scratch) {
  const s = parseScratch(structuredClone(scratch));
  const key = `${projectId}:${s.id}`;
  pendingDrafts.set(s.id, s);
  const operation = writes.then(async () => {
    await projectStore.saveArtifact({ hash: key, name: `${s.title}.scratch.json`,
      bytes: new TextEncoder().encode(JSON.stringify(s)).buffer, createdAt: s.createdAt });
    await projectStore.saveMembership({ id: key, projectId, artifactHash: key, createdAt: s.createdAt });
    if (pendingDrafts.get(s.id) === s) pendingDrafts.delete(s.id);
    writeWarnings.delete(s.id);
  }).catch(error => {
    writeWarnings.set(s.id, `${s.title || s.id}: not saved. Download JSON before closing. ${String(error)}`);
    throw error;
  });
  writes = operation.catch(() => {});
  return operation;
}
export async function loadScratches(): Promise<{ scratches: Scratch[]; warnings: string[] }> {
  await writes;
  const warnings: string[] = [];
  const rows = new Map<string, Scratch>();
  try {
    const entries = await projectStore.memberships(projectId);
    const loaded = await Promise.allSettled(entries.map(async entry => {
      const artifact = await projectStore.loadArtifact(entry.artifactHash);
      if (!artifact) throw new Error("Saved record is missing; original membership preserved.");
      const s = parseScratch(JSON.parse(new TextDecoder().decode(artifact.bytes)));
      if (`${projectId}:${s.id}` !== entry.artifactHash) throw new Error("Scratch identity differs from its stored key; original preserved.");
      return s;
    }));
    loaded.forEach((result, i) => {
      if (result.status === "fulfilled") rows.set(result.value.id, result.value);
      else warnings.push(`${entries[i].id}: ${String(result.reason)}`);
    });
  } catch (error) { warnings.push(`Scratch storage unavailable: ${String(error)}`); }
  for (const [id, s] of pendingDrafts) rows.set(id, s);
  return { scratches: [...rows.values()], warnings: [...warnings, ...writeWarnings.values()] };
}
