import { describe, expect, it } from "vitest";
import {
  diffMismatches,
  diffReceipts,
  evidenceRecords,
  matchingProvider,
  sourceDraftKey,
} from "./boundaries";

const selection = {
  locator: "/projects/demo.gpr",
  slug: "demo",
  program: "demo.exe",
  addr: "0x401000",
  logicalId: "",
};

describe("workbench integration boundaries", () => {
  it("uses the existing source draft identity", () => {
    expect(sourceDraftKey(selection)).toBe(
      JSON.stringify([
        "/projects/demo.gpr",
        "demo",
        "demo.exe",
        "0x401000",
        "source",
      ]),
    );
  });

  it("exposes only revision-bound recorded function evidence", () => {
    expect(evidenceRecords({
      evidencePath: "/work/function-evidence/receipt.json",
      evidenceRevision: "revision-1",
      provenance: { tool: "mcp.get-function" },
    }, selection)).toEqual([{
      id: "/work/function-evidence/receipt.json",
      revisionId: "revision-1",
      label: "mcp.get-function function observation",
      kind: "recorded function evidence",
      provider: "mcp.get-function",
      address: "0x401000",
    }]);
    expect(evidenceRecords({ evidencePath: "/work/receipt.json" }, selection)).toEqual([]);
  });

  it("does not manufacture mismatch evidence or provider availability", () => {
    expect(diffMismatches({
      proof: { mismatches: [{ id: "m1", summary: "bytes differ", address: "0x401004" }, {}] },
    })).toEqual([{ id: "m1", summary: "bytes differ", address: "0x401004", region: undefined, expected: undefined, actual: undefined }]);
    expect(diffReceipts({ proof: { receipt: "/work/objdiff.json" } })).toEqual([{ path: "/work/objdiff.json" }]);
    expect(matchingProvider([]).available).toBe(false);
    expect(matchingProvider([{ id: "corpus.objdiff-check" }]).available).toBe(false);
  });
});
