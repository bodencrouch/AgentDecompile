import { describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { StageTrace } from "./StageTrace";

describe("StageTrace", () => {
  it("renders placeholder stages when no run is present", () => {
    const html = renderToStaticMarkup(createElement(StageTrace, {}));
    expect(html).toContain("STANDBY");
    expect(html).toContain("Prepare");
    expect(html).toContain("Verify");
  });

  it("marks the running stage as current and shows strategy copy", () => {
    const html = renderToStaticMarkup(
      createElement(StageTrace, {
        run: {
          status: "running",
          currentStage: "matching",
          stages: [
            { key: "analysis", title: "Analyze", status: "completed" },
            {
              key: "matching",
              title: "Match",
              status: "running",
              strategy: "cross-build",
              completed: 12,
              total: 40,
              unit: "comparisons",
            },
            { key: "recover-source", title: "Synthesize", status: "queued" },
          ],
        },
      }),
    );
    expect(html).toContain("LIVE");
    expect(html).toContain("cross-build");
    expect(html).toContain("12 / 40 comparisons");
    expect(html).toContain('aria-current="step"');
    expect(html).toContain("state-running");
  });

  it("renders related and byte chips in the banner when props are set", () => {
    const html = renderToStaticMarkup(
      createElement(StageTrace, {
        run: { status: "running", stages: [{ key: "matching", title: "Match", status: "running" }] },
        relatedCount: 3,
        byteGate: { status: "running", label: "byte audit running" },
      }),
    );
    expect(html).toContain("stage-trace-chips");
    expect(html).toContain("3 related builds");
    expect(html).toContain("stage-trace-related");
    expect(html).toContain("atlas-byte-chip");
    expect(html).toContain("state-running");
    expect(html).toContain("byte audit running");
  });

  it("renders singular related chip copy", () => {
    const html = renderToStaticMarkup(
      createElement(StageTrace, {
        relatedCount: 1,
        byteGate: { status: "completed", label: "byte audit recorded" },
      }),
    );
    expect(html).toContain("1 related build");
    expect(html).not.toContain("1 related builds");
    expect(html).toContain("byte audit recorded");
  });

  it("shows Pause and Stop when canControl and callbacks are set for an active run", () => {
    const html = renderToStaticMarkup(
      createElement(StageTrace, {
        canControl: true,
        runStatus: "running",
        onPause: () => undefined,
        onStop: () => undefined,
        onResume: () => undefined,
      }),
    );
    expect(html).toContain("stage-trace-controls");
    expect(html).toContain(">Pause<");
    expect(html).toContain(">Stop<");
    expect(html).not.toContain(">Resume<");
  });

  it("shows Resume and Stop when canControl and run is paused", () => {
    const html = renderToStaticMarkup(
      createElement(StageTrace, {
        canControl: true,
        runStatus: "paused",
        onPause: vi.fn(),
        onStop: vi.fn(),
        onResume: vi.fn(),
      }),
    );
    expect(html).toContain("stage-trace-controls");
    expect(html).toContain(">Resume<");
    expect(html).toContain(">Stop<");
    expect(html).not.toContain(">Pause<");
  });

  it("omits controls when canControl is false even if callbacks exist", () => {
    const html = renderToStaticMarkup(
      createElement(StageTrace, {
        canControl: false,
        runStatus: "running",
        onPause: () => undefined,
        onStop: () => undefined,
      }),
    );
    expect(html).not.toContain("stage-trace-controls");
    expect(html).not.toContain(">Pause<");
  });
});
