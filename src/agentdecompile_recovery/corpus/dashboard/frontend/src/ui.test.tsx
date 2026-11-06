import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { ResizeBar, resizeKeyboardDelta } from "./ui";

describe("resizeKeyboardDelta", () => {
  it("maps arrow keys to normal and accelerated steps", () => {
    expect(resizeKeyboardDelta("ArrowLeft")).toBe(-16);
    expect(resizeKeyboardDelta("ArrowUp", true)).toBe(-64);
    expect(resizeKeyboardDelta("ArrowRight")).toBe(16);
    expect(resizeKeyboardDelta("ArrowDown", true)).toBe(64);
    expect(resizeKeyboardDelta("Home")).toBeNull();
  });
});

describe("ResizeBar", () => {
  it("exposes the current bounded pane size", () => {
    const html = renderToStaticMarkup(
      createElement(ResizeBar, {
        axis: "x",
        label: "Resize navigator",
        min: 224,
        max: 480,
        value: 288,
        onResize: () => undefined,
      }),
    );

    expect(html).toContain('role="separator"');
    expect(html).toContain('aria-orientation="vertical"');
    expect(html).toContain('aria-valuemin="224"');
    expect(html).toContain('aria-valuemax="480"');
    expect(html).toContain('aria-valuenow="288"');
  });

  it("resets and collapses or restores only when explicitly configured", () => {
    const onReset = vi.fn();
    const onCollapse = vi.fn();
    const onRestore = vi.fn();
    const preventDefault = vi.fn();
    const base = {
      axis: "x" as const,
      label: "Resize navigator",
      onResize: vi.fn(),
      onReset,
      onCollapse,
      onRestore,
    };

    ResizeBar(base).props.onKeyDown({ key: "Home", shiftKey: false, preventDefault });
    ResizeBar(base).props.onKeyDown({ key: "Enter", shiftKey: false, preventDefault });
    ResizeBar({ ...base, collapsed: true }).props.onKeyDown({
      key: "Enter",
      shiftKey: false,
      preventDefault,
    });

    expect(onReset).toHaveBeenCalledOnce();
    expect(onCollapse).toHaveBeenCalledOnce();
    expect(onRestore).toHaveBeenCalledOnce();
    expect(preventDefault).toHaveBeenCalledTimes(3);
  });
});
