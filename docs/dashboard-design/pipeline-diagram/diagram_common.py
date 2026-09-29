#!/usr/bin/env python3
"""Shared helpers for the recovery design diagrams (document authoring only).

* ``load_model`` reads ``pipeline-model.json``, the single content model.
* ``Canvas`` collects SVG lines, wraps model nodes in ``<g id="...">`` and emits an
  accessible root (``role="img"``, ``aria-labelledby``, ``lang``, ``<title>``, ``<desc>``).
* ``text_width``/``text_bbox`` are the text-geometry estimate shared with
  ``svg_to_drawio.py``; ``collisions`` uses them to find overlapping text boxes that
  belong to different nodes.

Run ``python diagram_common.py check <file.svg> ...`` to re-run the collision check on
existing SVG files.  Nothing here exercises AgentDecompile.
"""
from __future__ import annotations

import html
import json
import re
import sys
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODEL_PATH = HERE / "pipeline-model.json"

ATTR = re.compile(r'([a-zA-Z][a-zA-Z0-9-]*)="([^"]*)"')
G_OPEN = re.compile(r'<g id="([^"]+)"[^>]*>$')


class Model(dict):
    """The parsed model plus an id index (``model.node(id)``)."""

    def __init__(self, data: dict):
        super().__init__(data)
        self.by_id: dict[str, dict] = {}
        for n in self["nodes"]:
            self.by_id[n["id"]] = n
            for sub in n.get("cards", []) + n.get("members", []):
                self.by_id[sub["id"]] = sub

    def node(self, node_id: str) -> dict:
        return self.by_id[node_id]

    def nodes_of(self, diagram: str) -> list[dict]:
        return [n for n in self["nodes"] if n["diagram"] == diagram]

    def edge(self, edge_id: str) -> dict:
        return next(e for e in self["edges"] if e.get("id") == edge_id)


def load_model(path: Path = MODEL_PATH) -> Model:
    return Model(json.loads(path.read_text(encoding="utf-8")))


def esc(s: str) -> str:
    return html.escape(s, quote=True)


# ---------------------------------------------------------------- text geometry
def text_width(s: str, size: float, bold: bool) -> float:
    """Estimated rendered width; identical to the estimate svg_to_drawio.py uses."""
    per = 0.60 if bold else 0.56
    return max(10.0, len(s) * size * per + 6)


def text_bbox(a: dict, s: str) -> tuple[float, float, float, float]:
    """Axis-aligned (x, y, w, h) footprint of one <text> element's attributes ``a``.

    Mirrors svg_to_drawio.py: height 1.4 x size, vertical centre 0.35 x size above the
    baseline, anchor start/middle/end, and translate(...) rotate(-90) labels.
    """
    size = float(a["font-size"])
    bold = a.get("font-weight") == "bold"
    tw = text_width(s, size, bold)
    th = round(size * 1.4, 2)
    if "transform" in a:
        tm = re.search(r"translate\(([-\d.]+),([-\d.]+)\)\s*rotate\(([-\d.]+)\)", a["transform"])
        tx, ty, ang = float(tm.group(1)), float(tm.group(2)), float(tm.group(3))
        cx, cy = tx - 0.35 * size, ty
        if abs(abs(ang) - 90) < 1e-6:  # quarter turn: footprint swaps width and height
            return (cx - th / 2, cy - tw / 2, th, tw)
        return (cx - tw / 2, cy - th / 2, tw, th)
    bx, by = float(a["x"]), float(a["y"])
    cy = by - 0.35 * size
    y = cy - th / 2
    anchor = a.get("text-anchor", "start")
    if anchor == "end":
        x = bx - tw
    elif anchor == "middle":
        x = bx - tw / 2
    else:
        x = bx
    return (x, y, tw, th)


def svg_texts(svg: str) -> list[dict]:
    """Every <text> line with its owning node path (innermost <g id> last)."""
    stack: list[str] = []
    found = []
    for line in svg.splitlines():
        line = line.strip()
        m = G_OPEN.match(line)
        if m:
            stack.append(m.group(1))
            continue
        if line == "</g>":
            stack.pop()
            continue
        if line.startswith("<text"):
            a = dict(ATTR.findall(line.split(">", 1)[0]))
            body = html.unescape(re.search(r">(.*)</text>", line).group(1))
            found.append({"attrs": a, "text": body, "path": tuple(stack)})
    return found


def collisions(svg: str, tol: float = 1.0) -> list[tuple[str, str, str, str]]:
    """Pairs of overlapping text boxes that belong to different nodes.

    A text outside any <g id> is its own node.  Boxes must overlap by more than ``tol``
    pixels in both directions to count.
    """
    boxes = []
    for i, t in enumerate(svg_texts(svg)):
        if not t["text"].strip():
            continue
        owner = t["path"][-1] if t["path"] else f"(ungrouped text #{i})"
        boxes.append((text_bbox(t["attrs"], t["text"]), owner, t["text"]))
    boxes.sort(key=lambda b: b[0][1])
    hits = []
    for i, ((x1, y1, w1, h1), o1, s1) in enumerate(boxes):
        for (x2, y2, w2, h2), o2, s2 in boxes[i + 1:]:
            if y2 >= y1 + h1 - tol:
                break
            if o1 == o2:
                continue
            ox = min(x1 + w1, x2 + w2) - max(x1, x2)
            oy = min(y1 + h1, y2 + h2) - max(y1, y2)
            if ox > tol and oy > tol:
                hits.append((o1, s1, o2, s2))
    return hits


def assert_no_collisions(svg: str, name: str) -> None:
    hits = collisions(svg)
    if hits:
        lines = [f"  [{a}] {sa!r}  overlaps  [{b}] {sb!r}" for a, sa, b, sb in hits]
        raise SystemExit(f"{name}: {len(hits)} text collision(s) between different nodes:\n" + "\n".join(lines))


# ---------------------------------------------------------------- canvas
class Canvas:
    """Collects SVG body lines in reading order and tracks <g id> nesting."""

    def __init__(self) -> None:
        self.body: list[str] = []
        self.stack: list[str] = []
        self.ids: list[str] = []

    def raw(self, s: str) -> None:
        self.body.append(s)

    def sec(self, name: str) -> None:
        """draw.io layer marker; only allowed outside every node group."""
        assert not self.stack, f"section {name!r} opened inside node {self.stack[-1]!r}"
        self.body.append(f"<!--SEC:{name}-->")

    @contextmanager
    def node(self, node_id: str | None):
        if node_id is None:
            yield
            return
        assert node_id not in self.ids, f"duplicate node id {node_id}"
        self.ids.append(node_id)
        self.body.append(f'<g id="{esc(node_id)}">')
        self.stack.append(node_id)
        try:
            yield
        finally:
            self.stack.pop()
            self.body.append("</g>")

    def render(self, *, width: int, height: int, diagram_id: str, title: str, desc: str, first_sec: str) -> str:
        assert not self.stack
        head = [
            f"<!--SEC:{first_sec}-->",
            f'<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="{diagram_id}-title {diagram_id}-desc" '
            f'lang="en" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            f'<title id="{diagram_id}-title">{esc(title)}</title>',
            f'<desc id="{diagram_id}-desc">{esc(desc)}</desc>',
        ]
        return "\n".join(head + self.body + ["</svg>"]) + "\n"


def write_svg(svg: str, path: Path, name: str) -> None:
    assert_no_collisions(svg, name)
    path.write_text(svg, encoding="utf-8")
    print(path, len(svg.encode("utf-8")), "bytes")


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] != "check":
        print("usage: python diagram_common.py check <file.svg> ...", file=sys.stderr)
        return 2
    bad = 0
    for p in argv[1:]:
        hits = collisions(Path(p).read_text(encoding="utf-8"))
        print(f"{p}: {len(hits)} text collision(s) between different nodes")
        for a, sa, b, sb in hits:
            print(f"  [{a}] {sa!r}  overlaps  [{b}] {sb!r}")
        bad += bool(hits)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
