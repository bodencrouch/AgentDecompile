import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { DiffEvidence, receiptLabel } from "./DiffEvidence";

describe("DiffEvidence", () => {
  it("labels recorded difference counts without inventing zero", () => {
    expect(receiptLabel({ id: "proof", status: "matched", differences: 0 })).toBe("proof · matched · 0 differences");
    expect(receiptLabel({ id: "partial", status: "incomplete", differences: null })).toBe("partial · incomplete");
    expect(receiptLabel({ id: "partial", status: "incomplete", differences: "" })).toBe("partial · incomplete");
  });

  it("renders revisions, mismatch detail, and unavailable source honestly", () => {
    const html = renderToStaticMarkup(createElement(DiffEvidence, {
      mismatches: [{ id: "m1", summary: "operand differs", expected: "01" }],
      receipts: [{
        id: "receipt-1", status: "mismatched", differences: 2,
        targetRevision: "123456789012extra", compiledRevision: "abcdefghijklmore",
        mismatchHistogram: { ARGUMENT_MISMATCH: 2 }, sourceExists: false,
      }],
    }));
    expect(html).toContain("actual: not recorded");
    expect(html).toContain("receipt-1 · mismatched · 2 differences · source unavailable");
    expect(html).toContain("target 123456789012 · compiled abcdefghijkl");
    expect(html).toContain("ARGUMENT_MISMATCH: 2");
  });

  it("renders the explicit empty receipt state", () => {
    const html = renderToStaticMarkup(createElement(DiffEvidence, { mismatches: [] }));
    expect(html).toContain("No mismatch regions were recorded.");
    expect(html).toContain("No provider receipt is available.");
  });
});
