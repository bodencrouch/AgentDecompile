import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CoverageMatrix, coverageRows, coverageText } from "./coverageMatrix";

const binaries = [
  { slug: "k1-gog", name: "swkotor.exe (GOG)" },
  { slug: "k1-steam", name: "swkotor.exe (Steam)", aliasSlugs: ["k1-steam-old"] },
  { slug: "k1-xbox", name: "default.xbe" },
];
const members = [
  { slug: "k1-gog", addr: "0x401000", method: "exact-bytes", confidence: 1 },
  { slug: "k1-steam-old", addr: "0x402000", method: "", confidence: null },
  { slug: "k1-steam", addr: "0x402100", method: "callgraph", confidence: 0.7 },
  { slug: "k1-mac", addr: "0x1000", method: "string-anchor", confidence: 0.5 },
];

describe("coverage by build", () => {
  it("keeps zero, one and many members distinct", () => {
    expect(coverageText(0)).toBe("No member returned");
    expect(coverageText(1)).toBe("1 member returned");
    expect(coverageText(2)).toBe("2 members returned");
  });

  it("builds one row per library build plus builds only seen in members", () => {
    const rows = coverageRows(members, binaries);
    expect(rows.map((row) => [row.build, row.coverage, row.inLibrary])).toEqual([
      ["swkotor.exe (GOG)", "1 member returned", true],
      ["swkotor.exe (Steam)", "2 members returned", true],
      ["default.xbe", "No member returned", true],
      ["k1-mac", "1 member returned", false],
    ]);
    expect(rows[1].addresses).toBe("0x402000, 0x402100");
    expect(rows[1].methods).toBe("Method not recorded · confidence not recorded; callgraph · confidence 0.7");
    expect(rows[0].methods).toBe("exact-bytes · confidence 1");
  });

  it("renders a read-only table and never claims a locator status", () => {
    const html = renderToStaticMarkup(createElement(CoverageMatrix, { members, binaries }));
    expect(html).toContain("3 of 4 builds return a member for this identity.");
    expect(html).toContain("Locator status is not shown.");
    expect(html).toContain("Not in the binary library");
    expect(html).not.toContain("<button");
    for (const status of ["resolved", "unresolved", "ambiguous", "contested", "pinned", "degraded"])
      expect(html.toLowerCase()).not.toContain(status);
  });

  it("renders the empty state", () => {
    const html = renderToStaticMarkup(createElement(CoverageMatrix, { members: [], binaries: [] }));
    expect(html).toContain("0 of 0 builds return a member");
    expect(html).toContain("No builds to compare.");
  });
});
