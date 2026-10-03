import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ComparePanel } from "./CompareView";
import { analysisTabs, readRoute } from "./navigation";
import { emptySelection } from "../contracts";

const onSelect = () => {};

describe("Compare tab", () => {
  it("is a first-class analysis tab that survives a shared URL", () => {
    expect(analysisTabs).toContain("Compare");
    const fallback = { selection: emptySelection, tab: "Info" as const };
    expect(readRoute("?view=Compare", fallback).tab).toBe("Compare");
    expect(readRoute("?view=compare", fallback).tab).toBe("Compare");
  });

  it("renders recorded mismatches and receipts from the function proof", () => {
    const html = renderToStaticMarkup(createElement(ComparePanel, {
      hasFunction: true, loading: false, error: "", onSelect,
      detail: { proof: {
        mismatches: [{ id: "m1", summary: "operand differs", address: "0x401010", expected: "8b 45", actual: "8b 4d" }],
        receipts: [{ id: "receipt-1", status: "mismatched", differences: 1 }],
      } },
    }));
    expect(html).toContain("operand differs");
    expect(html).toContain(" · 0x401010");
    expect(html).toContain("expected: 8b 45");
    expect(html).toContain("receipt-1 · mismatched · 1 differences");
    expect(html).toContain("It does not run a new diff.");
  });

  it("reads the verification alias and a single receipt path", () => {
    const html = renderToStaticMarkup(createElement(ComparePanel, {
      hasFunction: true, loading: false, error: "", onSelect,
      detail: { verification: { receipt: "target/objdiff/fn.json" } },
    }));
    expect(html).toContain("No mismatch regions were recorded.");
    expect(html).toContain("Provider receipts (1)");
    expect(html).toContain("target/objdiff/fn.json");
  });

  it("asks for a function before reading anything", () => {
    const html = renderToStaticMarkup(createElement(ComparePanel, {
      hasFunction: false, loading: false, error: "", onSelect, detail: {},
    }));
    expect(html).toContain("Select a function to see its recorded byte diff.");
    expect(html).not.toContain("Mismatch evidence");
  });

  it("shows the loading state without inventing a result", () => {
    const html = renderToStaticMarkup(createElement(ComparePanel, {
      hasFunction: true, loading: true, error: "", onSelect, detail: {},
    }));
    expect(html).toContain("Reading recorded diff");
    expect(html).toContain("No provider receipt is available.");
  });
});
