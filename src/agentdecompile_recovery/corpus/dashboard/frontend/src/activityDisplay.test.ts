import { describe, expect, it } from "vitest";
import { activityHeadline, activityTarget } from "./activityDisplay";

describe("activityTarget", () => {
  it("shows comparison endpoints for match-pair jobs", () => {
    expect(activityTarget({
      actionId: "corpus.match-pair",
      params: { src: "/K1/k1_android_ARMEABI", dst: "/TSL/k2_win_CD_1.0b_swkotor2.exe" },
    })).toBe("k1_android_ARMEABI → k2_win_CD_1.0b_swkotor2.exe");
  });

  it("falls back to a program path for ordinary jobs", () => {
    expect(activityTarget({ params: { programPath: "JadeEmpire.exe" } })).toBe("JadeEmpire.exe");
  });
});

describe("activityHeadline", () => {
  it("summarizes live comparisons instead of total history", () => {
    expect(activityHeadline([
      { actionId: "corpus.match-pair", status: "running" },
      { actionId: "corpus.match-pair", status: "queued" },
      { actionId: "corpus.match-pair", status: "queued" },
      { actionId: "corpus.match-pair", status: "failed" },
      { actionId: "workbench.prepare", status: "running" },
    ])).toBe("1 comparing · 2 queued · 1 other active");
  });
});
