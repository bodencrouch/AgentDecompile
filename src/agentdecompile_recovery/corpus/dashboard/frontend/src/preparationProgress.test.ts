import { describe, expect, it } from "vitest";
import { matchingStageSummary, stageDisplayProgress, stageProgressLabel } from "./preparationProgress";

describe("stageDisplayProgress", () => {
  it("keeps pair totals visible while inventory sub-work runs", () => {
    const { primary, secondary } = stageDisplayProgress({
      key: "matching",
      status: "running",
      completed: 97,
      total: 459,
      workProgress: { completed: 13, total: 28, unit: "binary inventories" },
    });
    expect(primary).toEqual({ completed: 97, total: 459, unit: "comparisons", currentTarget: undefined });
    expect(secondary).toEqual({ completed: 13, total: 28, unit: "binary inventories", currentTarget: undefined });
    expect(stageProgressLabel(primary!)).toBe("97 / 459 comparisons");
  });

  it("summarizes matching stage for recovery banners", () => {
    expect(matchingStageSummary({
      stages: [{
        key: "matching",
        status: "running",
        completed: 97,
        total: 459,
        workProgress: { completed: 13, total: 28, unit: "binary inventories" },
      }],
    })).toBe("97 / 459 comparisons · 13 / 28 binary inventories (running)");
  });

  it("falls back to secondary-only progress when primary is not measured", () => {
    const { primary, secondary } = stageDisplayProgress({
      key: "matching",
      status: "running",
      completed: 0,
      total: 459,
      workProgress: { completed: 4, total: 28, unit: "binary inventories" },
    });
    expect(primary).toEqual({ completed: 0, total: 459, unit: "comparisons", currentTarget: undefined });
    expect(secondary?.unit).toBe("binary inventories");
  });
});
