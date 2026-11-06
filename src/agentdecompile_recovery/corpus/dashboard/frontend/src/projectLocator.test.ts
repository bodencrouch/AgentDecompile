import { describe, expect, it } from "vitest";
import { mergeExplorerProjects } from "./explorerProjects";
import {
  canonicalProjectLocator,
  projectLocatorsMatch,
} from "./projectLocator";

describe("project locator keys", () => {
  it("normalizes trailing slashes and separators", () => {
    expect(canonicalProjectLocator("/tmp/demo.gpr/")).toBe("/tmp/demo.gpr");
    expect(canonicalProjectLocator("\\tmp\\demo.gpr\\")).toBe("/tmp/demo.gpr");
  });

  it("collapses dot segments", () => {
    expect(canonicalProjectLocator("/tmp/./demo.gpr")).toBe("/tmp/demo.gpr");
    expect(canonicalProjectLocator("/tmp/foo/../demo.gpr")).toBe("/tmp/demo.gpr");
  });

  it("matches equivalent spellings", () => {
    expect(projectLocatorsMatch("/tmp/demo.gpr/", "/tmp/demo.gpr")).toBe(true);
    expect(projectLocatorsMatch("/tmp/other.gpr", "/tmp/demo.gpr")).toBe(false);
  });
});

describe("mergeExplorerProjects", () => {
  it("keeps hidden projects out of the tree", () => {
    const rows = mergeExplorerProjects({
      projects: [
        { locator: "/tmp/a.gpr", title: "a", hidden: true },
        { locator: "/tmp/b.gpr", title: "b", hidden: false },
      ],
      binaries: [],
    });
    expect(rows.map((row) => row.locator)).toEqual(["/tmp/b.gpr"]);
  });

  it("pins live workflow locators even when hidden or missing from sessions", () => {
    const rows = mergeExplorerProjects({
      projects: [{ locator: "/work/repos.gpr", title: "repos", hidden: true }],
      binaries: [],
      liveLocators: ["/work/repos.gpr/", "/work/_odyssey.gpr"],
    });
    expect(rows.map((row) => row.locator).sort()).toEqual([
      "/work/_odyssey.gpr",
      "/work/repos.gpr",
    ]);
    expect(rows.every((row) => row.liveWorkflow && !row.hidden)).toBe(true);
  });
});
