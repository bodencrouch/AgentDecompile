import { canonicalProjectLocator } from "./projectLocator";

export type ExplorerProject = Record<string, any>;

/** Build the Projects & binaries tree roots, always including live workflow locators. */
export function mergeExplorerProjects(opts: {
  projects: ExplorerProject[];
  binaries: ExplorerProject[];
  selectionLocator?: string;
  liveLocators?: string[];
}): ExplorerProject[] {
  const map = new Map<string, ExplorerProject>();
  const live = new Set(
    (opts.liveLocators || [])
      .map((value) => canonicalProjectLocator(value))
      .filter(Boolean),
  );

  for (const project of opts.projects) {
    const locator = canonicalProjectLocator(project.locator);
    if (locator && !map.has(locator)) map.set(locator, { ...project, locator });
  }
  for (const binary of opts.binaries) {
    for (const binding of binary.projectBindings || []) {
      const locator = canonicalProjectLocator(binding.locator);
      if (locator && !map.has(locator)) {
        map.set(locator, {
          ...binding,
          locator,
          title: String(binding.locator || "").split("/").pop(),
        });
      }
    }
  }
  const selected = canonicalProjectLocator(opts.selectionLocator);
  if (selected && !map.has(selected)) {
    map.set(selected, {
      locator: selected,
      title: selected.split("/").pop(),
    });
  }
  for (const locator of live) {
    const existing = map.get(locator);
    if (existing) {
      map.set(locator, { ...existing, liveWorkflow: true, hidden: false });
    } else {
      map.set(locator, {
        locator,
        title: locator.split("/").pop(),
        liveWorkflow: true,
        hidden: false,
      });
    }
  }

  return [...map.values()].filter(
    (project) =>
      !project.hidden || live.has(canonicalProjectLocator(project.locator)),
  );
}
