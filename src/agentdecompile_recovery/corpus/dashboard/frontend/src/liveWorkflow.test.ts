import { describe, expect, it } from "vitest";
import {
  explorerExpandKeysForSelection,
  pickLiveWorkflowToOpen,
  recommendProjectBinary,
  variantGroupKey,
} from "./liveWorkflow";

describe("pickLiveWorkflowToOpen", () => {
  it("returns the sole live run that has a locator", () => {
    const run = { id: "a", status: "running", locator: "/tmp/demo.gpr" };
    expect(
      pickLiveWorkflowToOpen([
        { id: "done", status: "completed", locator: "/tmp/other.gpr" },
        run,
        { id: "idle", status: "queued" },
      ]),
    ).toBe(run);
  });

  it("returns null when zero or multiple live locators", () => {
    expect(pickLiveWorkflowToOpen([])).toBeNull();
    expect(
      pickLiveWorkflowToOpen([{ id: "x", status: "paused", locator: "/a.gpr" }]),
    ).toEqual({ id: "x", status: "paused", locator: "/a.gpr" });
    expect(
      pickLiveWorkflowToOpen([
        { id: "1", status: "queued", locator: "/a.gpr" },
        { id: "2", status: "running", locator: "/b.gpr" },
      ]),
    ).toBeNull();
  });

  it("treats paused as live and ignores finished statuses", () => {
    expect(
      pickLiveWorkflowToOpen([
        { id: "c", status: "completed", locator: "/c.gpr" },
        { id: "f", status: "failed", locator: "/f.gpr" },
        { id: "p", status: "paused", locator: "/p.gpr/" },
      ]),
    ).toMatchObject({ id: "p", locator: "/p.gpr/" });
  });
});

describe("recommendProjectBinary", () => {
  const builds = [
    {
      kind: "binary",
      slug: "alpha",
      sha256: "aa",
      projectBindings: [{ locator: "/work/game.gpr", program: "/Alpha.exe" }],
    },
    {
      kind: "binary",
      slug: "beta",
      sha256: "bb",
      projectBindings: [{ locator: "/work/game.gpr/", program: "Beta.exe" }],
    },
    {
      kind: "binary",
      slug: "other",
      sha256: "cc",
      projectBindings: [{ locator: "/work/other.gpr", program: "Other.exe" }],
    },
  ];

  it("keeps an explicit slug or program", () => {
    expect(
      recommendProjectBinary(
        { locator: "/work/game.gpr", slug: "beta", program: "" },
        builds,
      ),
    ).toEqual({ slug: "beta", program: "" });
    expect(
      recommendProjectBinary(
        { locator: "/work/game.gpr", slug: "", program: "Beta.exe" },
        builds,
      ),
    ).toEqual({ slug: "", program: "Beta.exe" });
  });

  it("picks the first bound binary when selection has no slug/program", () => {
    expect(
      recommendProjectBinary(
        { locator: "/work/game.gpr/", slug: "", program: "" },
        builds,
      ),
    ).toEqual({ slug: "alpha", program: "Alpha.exe" });
  });

  it("returns null when nothing is bound to the locator", () => {
    expect(
      recommendProjectBinary(
        { locator: "/missing.gpr", slug: "", program: "" },
        builds,
      ),
    ).toBeNull();
  });
});

describe("explorerExpandKeysForSelection", () => {
  it("expands the project and matching variant group", () => {
    const builds = [
      {
        kind: "binary",
        slug: "alpha",
        sha256: "aa",
        variant_group: { status: "related", id: "family-1" },
        projectBindings: [{ locator: "/tmp/demo.gpr", program: "Alpha.exe" }],
      },
    ];
    expect(
      explorerExpandKeysForSelection(
        { locator: "/tmp/demo.gpr/", slug: "alpha", program: "" },
        builds,
      ),
    ).toEqual(["project:/tmp/demo.gpr", "project:/tmp/demo.gpr:family-1"]);
    expect(variantGroupKey(builds[0])).toBe("family-1");
  });

  it("expands only the project when no binary is known", () => {
    expect(
      explorerExpandKeysForSelection(
        { locator: "/tmp/empty.gpr", slug: "", program: "" },
        [],
      ),
    ).toEqual(["project:/tmp/empty.gpr"]);
  });
});
