import type { Data } from "./contracts";
import { canonicalProjectLocator } from "./projectLocator";

const programKey = (value: unknown) => String(value || "").replace(/^\/+/, "");

/**
 * Keep a live project usable while its corpus rows are still being written.
 * The preparation receipt is authoritative for the programs Ghidra already owns.
 */
export function workflowProgramMembers(project: Data, binaries: Data[], runs: Data[]): Data[] {
  const locator = canonicalProjectLocator(project.locator);
  const run = (runs || []).find((item) => canonicalProjectLocator(item.locator) === locator);
  if (!run) return [];
  const programs = Array.isArray(run.programs) && run.programs.length
    ? run.programs
    : Object.keys(run.executionProgramPaths || {});
  const known = new Set<string>();
  return programs.map((value: unknown) => {
    const program = String(value || "");
    const key = programKey(program);
    const existing = binaries.find((binary) =>
      binary.slug === key || binary.aliasSlugs?.includes(key) ||
      (binary.projectBindings || []).some((binding: Data) =>
        canonicalProjectLocator(binding.locator) === locator && programKey(binding.program) === key,
      ),
    );
    if (existing) return { ...existing, program };
    return {
      id: `program:${locator}:${key}`,
      slug: "",
      label: key,
      program,
      locator,
      imported: true,
      kind: "binary",
      workflowOnly: true,
      projectBindings: [{ locator, program }],
      platform: "Recorded Ghidra program",
      protection: run.checkpoints?.[program]?.protection || { status: "unknown", encryption: "unknown", drm: "unknown" },
      funcs: Number(run.checkpoints?.[program]?.workSize || 0),
      libraryId: `program:${locator}:${key}`,
      identityStatus: "recorded-program",
    };
  }).filter((item) => {
    const key = programKey(item.program);
    if (!key || known.has(key)) return false;
    known.add(key);
    return true;
  });
}
