import type { Data, Selection } from "./contracts";
import { canonicalProjectLocator } from "./projectLocator";

const LIVE_STATUSES = new Set([
  "queued",
  "running",
  "paused",
  "cancelling",
  "disconnected",
  "resync",
  "resumable",
]);

const binaryKey = (b: Data) =>
  String(b.libraryId || (b.sha256 ? `sha256:${b.sha256}` : b.id || b.slug));

/** Variant-group node id suffix under a project (matches PersistentExplorer). */
export function variantGroupKey(b: Data): string {
  const g = b.variant_group;
  if (g?.status === "related") return String(g.id);
  if (g?.status === "insufficient") return `separate:${binaryKey(b)}`;
  return "unmatched";
}

function binaryBoundToLocator(b: Data, locator: string): boolean {
  const key = canonicalProjectLocator(locator);
  if (!key || b.kind === "unresolved") return false;
  if (
    (b.projectBindings || []).some(
      (x: Data) => canonicalProjectLocator(x.locator) === key,
    )
  )
    return true;
  if (b.imported && canonicalProjectLocator(b.locator) === key) return true;
  return false;
}

function programForLocator(b: Data, locator: string): string {
  const key = canonicalProjectLocator(locator);
  const binding = (b.projectBindings || []).find(
    (p: Data) => canonicalProjectLocator(p.locator) === key,
  );
  return String(binding?.program || b.program || "").replace(/^\//, "");
}

/**
 * Auto-open helper for Atlas empty landing.
 * Returns the sole live preparation run that has a locator; otherwise null
 * (zero or multiple → keep the chooser / landing buttons).
 */
export function pickLiveWorkflowToOpen(runs: Data[]): Data | null {
  const live = (runs || []).filter(
    (run) => LIVE_STATUSES.has(String(run.status)) && run.locator,
  );
  return live.length === 1 ? live[0] : null;
}

export type BinaryRecommendation = { slug: string; program: string };

/**
 * Prefer selection.slug / selection.program when set; otherwise the first
 * binary in `builds` bound to selection.locator (projectBindings or imported path).
 *
 * AtlasApp: after `pickLiveWorkflowToOpen`, call this so `requestOpen` gets a
 * concrete binary when the live run only carried a project locator.
 */
export function recommendProjectBinary(
  selection: Pick<Selection, "locator" | "slug" | "program"> | Partial<Selection>,
  builds: Data[],
): BinaryRecommendation | null {
  const slug = String(selection.slug || "");
  const program = String(selection.program || "").replace(/^\//, "");
  if (slug || program) return { slug, program };

  const locator = canonicalProjectLocator(selection.locator);
  if (!locator) return null;

  const binary = (builds || []).find(
    (b) => b.kind !== "unresolved" && binaryBoundToLocator(b, locator),
  );
  if (!binary) return null;
  return {
    slug: String(binary.slug || ""),
    program: programForLocator(binary, locator),
  };
}

/**
 * Tree keys that should be force-expanded when a project (and optional binary)
 * is selected — project root plus the variant group that contains the binary.
 */
export function explorerExpandKeysForSelection(
  selection: Pick<Selection, "locator" | "slug" | "program"> | Partial<Selection>,
  builds: Data[],
): string[] {
  const locator = canonicalProjectLocator(selection.locator);
  if (!locator) return [];
  const projectId = `project:${locator}`;
  const keys = [projectId];

  const recommended = recommendProjectBinary(selection, builds);
  const slug = recommended?.slug || "";
  const program = recommended?.program || "";
  if (!slug && !program) return keys;

  const binary = (builds || []).find((b) => {
    if (!binaryBoundToLocator(b, locator)) return false;
    if (slug && (b.slug === slug || b.aliasSlugs?.includes(slug))) return true;
    if (program && programForLocator(b, locator) === program) return true;
    return false;
  });
  if (binary) keys.push(`${projectId}:${variantGroupKey(binary)}`);
  return keys;
}
