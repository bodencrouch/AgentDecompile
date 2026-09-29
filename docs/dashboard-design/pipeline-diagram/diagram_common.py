#!/usr/bin/env python3
"""Shared helpers for the recovery design diagrams (document authoring only).

* ``load_model`` reads ``pipeline-model.json``, the single content model.
* ``Canvas`` collects SVG lines, wraps model nodes in ``<g id="...">``, draws routed
  (horizontal/vertical) arrows with ``elbow`` and emits an accessible root
  (``role="img"``, ``aria-labelledby``, ``lang``, ``<title>``, ``<desc>``).
* ``text_width``/``text_bbox`` are the text-geometry estimate shared with
  ``svg_to_drawio.py``; ``collisions`` uses them to find overlapping text boxes that
  belong to different nodes.
* ``dejavu_metrics`` reads real advance widths from the installed DejaVu TrueType files
  (no extra dependency).  With it, ``collisions`` measures real text extents and
  ``overflows`` finds text that spills out of its card, band, pill or panel.

Generators call ``write_svg``: the estimate check always runs, and the DejaVu-metrics
overlap and overflow checks run whenever the fonts are installed (output never depends
on them).  Run ``python diagram_common.py check <file.svg> ...`` to repeat all checks on
existing SVG files.  Nothing here exercises AgentDecompile.
"""
from __future__ import annotations

import html
import json
import re
import struct
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


# ---------------------------------------------------------------- real DejaVu metrics
DEJAVU_DIR = Path("/usr/share/fonts/truetype/dejavu")
DEJAVU_FILES = {("sans", False): "DejaVuSans.ttf", ("sans", True): "DejaVuSans-Bold.ttf",
                ("mono", False): "DejaVuSansMono.ttf", ("mono", True): "DejaVuSansMono-Bold.ttf"}


class TrueTypeWidths:
    """Advance widths from a TrueType file's cmap/hmtx tables (kerning ignored: conservative)."""

    def __init__(self, path: Path):
        data = path.read_bytes()
        u16 = lambda o: struct.unpack(">H", data[o:o + 2])[0]
        tables = {}
        for i in range(u16(4)):
            tag, _chk, off, _len = struct.unpack(">4sIII", data[12 + 16 * i:28 + 16 * i])
            tables[tag.decode("latin-1")] = off
        self.upem = u16(tables["head"] + 18)
        nhm = u16(tables["hhea"] + 34)
        self.adv = [u16(tables["hmtx"] + 4 * i) for i in range(nhm)]
        base = tables["cmap"]
        subs = {}
        for i in range(u16(base + 2)):
            pid, eid, off = struct.unpack(">HHI", data[base + 4 + 8 * i:base + 12 + 8 * i])
            subs[(pid, eid)] = base + off
        self.cmap: dict[int, int] = {}
        for key in ((3, 10), (0, 4), (3, 1), (0, 3)):
            if key not in subs:
                continue
            off = subs[key]
            fmt = u16(off)
            if fmt == 12:
                for i in range(struct.unpack(">I", data[off + 12:off + 16])[0]):
                    a, b, g = struct.unpack(">III", data[off + 16 + 12 * i:off + 28 + 12 * i])
                    for cp in range(a, b + 1):
                        self.cmap[cp] = g + cp - a
                break
            if fmt == 4:
                seg2 = u16(off + 6)
                ends, starts = off + 14, off + 16 + seg2
                deltas, ranges = starts + seg2, starts + 2 * seg2
                for i in range(seg2 // 2):
                    end, start, delta, ro = u16(ends + 2 * i), u16(starts + 2 * i), u16(deltas + 2 * i), u16(ranges + 2 * i)
                    for cp in range(start, end + 1):
                        if cp == 0xFFFF:
                            continue
                        if ro == 0:
                            g = (cp + delta) & 0xFFFF
                        else:
                            g = u16(ranges + 2 * i + ro + 2 * (cp - start))
                            g = (g + delta) & 0xFFFF if g else 0
                        self.cmap[cp] = g
                break

    def width(self, s: str, size: float) -> float:
        total = 0
        for ch in s:
            g = self.cmap.get(ord(ch), 0)
            total += self.adv[g] if g < len(self.adv) else self.adv[-1]
        return total * size / self.upem

    def missing(self, s: str) -> set[str]:
        return {ch for ch in s if ord(ch) not in self.cmap}


class DejaVuMetrics:
    def __init__(self, font_dir: Path = DEJAVU_DIR):
        self.fonts = {k: TrueTypeWidths(font_dir / v) for k, v in DEJAVU_FILES.items()}

    def font(self, a: dict) -> TrueTypeWidths:
        mono = "mono" in a.get("font-family", "").split(",")[0].lower()
        return self.fonts[("mono" if mono else "sans", a.get("font-weight") == "bold")]


def dejavu_metrics(font_dir: Path = DEJAVU_DIR) -> DejaVuMetrics | None:
    if all((font_dir / f).exists() for f in DEJAVU_FILES.values()):
        return DejaVuMetrics(font_dir)
    return None


def real_bbox(a: dict, s: str, m: DejaVuMetrics) -> tuple[float, float, float, float]:
    """Measured footprint: DejaVu advance width, ascent 0.76 x size, descent 0.24 x size."""
    size = float(a["font-size"])
    tw = m.font(a).width(s, size)
    if "transform" in a:
        tm = re.search(r"translate\(([-\d.]+),([-\d.]+)\)\s*rotate\(([-\d.]+)\)", a["transform"])
        tx, ty = float(tm.group(1)), float(tm.group(2))
        return (tx - 0.76 * size, ty - tw / 2, size, tw)  # rotate(-90), anchor middle
    bx, by = float(a["x"]), float(a["y"])
    anchor = a.get("text-anchor", "start")
    x = bx - tw if anchor == "end" else bx - tw / 2 if anchor == "middle" else bx
    return (x, by - 0.76 * size, tw, size)


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


def collisions(svg: str, tol: float = 1.0, metrics: DejaVuMetrics | None = None,
               same_node: bool = False) -> list[tuple[str, str, str, str]]:
    """Pairs of overlapping text boxes that belong to different nodes.

    A text outside any <g id> is its own node.  Boxes must overlap by more than ``tol``
    pixels in both directions to count.  Without ``metrics`` the svg_to_drawio.py
    estimate is used; with ``metrics`` the measured DejaVu extents are used, and
    ``same_node=True`` also checks texts of one node against each other (for example a
    card title against its family word).
    """
    boxes = []
    for i, t in enumerate(svg_texts(svg)):
        if not t["text"].strip():
            continue
        owner = t["path"][-1] if t["path"] else f"(ungrouped text #{i})"
        box = real_bbox(t["attrs"], t["text"], metrics) if metrics else text_bbox(t["attrs"], t["text"])
        boxes.append((box, owner, t["text"]))
    boxes.sort(key=lambda b: b[0][1])
    hits = []
    for i, ((x1, y1, w1, h1), o1, s1) in enumerate(boxes):
        for (x2, y2, w2, h2), o2, s2 in boxes[i + 1:]:
            if y2 >= y1 + h1 - tol:
                break
            if o1 == o2 and not same_node:
                continue
            ox = min(x1 + w1, x2 + w2) - max(x1, x2)
            oy = min(y1 + h1, y2 + h2) - max(y1, y2)
            if ox > tol and oy > tol:
                hits.append((o1, s1, o2, s2))
    return hits


def overflows(svg: str, metrics: DejaVuMetrics, tol: float = 0.5) -> list[str]:
    """Text whose measured extent leaves the smallest rect containing its anchor point
    (the card, header band, pill or panel it sits in; the canvas otherwise), plus any
    character the DejaVu fonts cannot draw."""
    rects = []
    for line in svg.splitlines():
        line = line.strip()
        if line.startswith("<rect"):
            a = dict(ATTR.findall(line))
            rects.append(tuple(float(a[k]) for k in ("x", "y", "width", "height")))
    found = []
    for t in svg_texts(svg):
        a, s = t["attrs"], t["text"]
        lost = metrics.font(a).missing(s)
        if lost:
            found.append(f"no DejaVu glyph for {sorted(lost)} in {s!r}")
        if "transform" in a:
            continue
        x, y, w, h = real_bbox(a, s, metrics)
        px, py = float(a["x"]), float(a["y"]) - 0.35 * float(a["font-size"])
        inside = [r for r in rects if r[0] <= px <= r[0] + r[2] and r[1] <= py <= r[1] + r[3]]
        if not inside:
            found.append(f"text anchor outside the canvas: {s!r}")
            continue
        rx, ry, rw, rh = min(inside, key=lambda r: r[2] * r[3])
        over = max(rx - x, (x + w) - (rx + rw), ry - y, (y + h) - (ry + rh))
        if over > tol:
            owner = t["path"][-1] if t["path"] else "(ungrouped)"
            found.append(f"[{owner}] {s!r} overflows its {rw:g}x{rh:g} box at ({rx:g},{ry:g}) by {over:.1f}px")
    return found


def layout_problems(svg: str) -> list[str]:
    """Estimate overlaps between nodes always; when DejaVu is installed, also measured
    overlaps between any two texts and measured overflows."""
    fmt = lambda kind, hits: [f"{kind}: [{a}] {sa!r}  overlaps  [{b}] {sb!r}" for a, sa, b, sb in hits]
    problems = fmt("estimate", collisions(svg))
    m = dejavu_metrics()
    if m is not None:
        problems += fmt("DejaVu", collisions(svg, tol=0.5, metrics=m, same_node=True)) + overflows(svg, m)
    return problems


def assert_no_collisions(svg: str, name: str) -> None:
    problems = layout_problems(svg)
    if problems:
        raise SystemExit(f"{name}: {len(problems)} layout problem(s):\n  " + "\n  ".join(problems))
    if dejavu_metrics() is None:
        print(f"{name}: DejaVu fonts not found in {DEJAVU_DIR}; measured checks skipped", file=sys.stderr)


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

    def elbow(self, points: list[tuple[int, int]], color: str, width: int = 3, head: bool = True) -> None:
        """Axis-aligned polyline (``<path d="M.. H.. V..">``, the form svg_to_drawio.py turns into a
        connector with waypoints) plus, when ``head``, a block arrowhead at the last point pointing
        along the last segment.  A path without a head is a feeder that joins another arrow."""
        (px, py), d = points[0], [f"M{points[0][0]},{points[0][1]}"]
        for x, y in points[1:]:
            assert (x == px) != (y == py), f"segment {(px, py)} -> {(x, y)} is not horizontal or vertical"
            d.append(f"H{x}" if y == py else f"V{y}")
            px, py = x, y
        self.body.append(f'<path d="{" ".join(d)}" fill="none" stroke="{color}" stroke-width="{width}"/>')
        if head:
            (ax, ay), (bx, by) = points[-2], points[-1]
            dx, dy = (bx > ax) - (bx < ax), (by > ay) - (by < ay)
            if dx:
                tri = [(bx, by), (bx - 11 * dx, by - 6), (bx - 11 * dx, by + 6)]
            else:
                tri = [(bx, by), (bx - 6, by - 11 * dy), (bx + 6, by - 11 * dy)]
            self.body.append(f'<polygon points="{" ".join(f"{x},{y}" for x, y in tri)}" fill="{color}"/>')

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
    measured = "estimate + DejaVu metrics" if dejavu_metrics() else "estimate only (DejaVu fonts not found)"
    for p in argv[1:]:
        problems = layout_problems(Path(p).read_text(encoding="utf-8"))
        print(f"{p}: {len(problems)} layout problem(s) [{measured}]")
        for line in problems:
            print("  " + line)
        bad += bool(problems)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
