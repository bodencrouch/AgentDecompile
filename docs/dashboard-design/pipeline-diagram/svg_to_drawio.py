#!/usr/bin/env python3
"""Convert the generated pipeline SVG into a native, editable draw.io (diagrams.net) file.

Every SVG primitive becomes a real mxGraph cell: rects -> rounded rectangles, text -> text cells,
line/path + arrowhead -> connectors with block arrows, circles -> ellipses, diamonds -> rhombus,
lock shackles -> rounded outlines.  <!--SEC:name--> comments become draw.io layers, and every card,
band and panel is grouped with its contents so it moves as one unit.  Output is deterministic:
no timestamps, ids are sequential in document order.
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path
from xml.sax.saxutils import quoteattr

SRC = Path(sys.argv[1])
OUT = Path(sys.argv[2])
TITLE = sys.argv[3] if len(sys.argv) > 3 else "AgentDecompile recovery pipeline"

svg = SRC.read_text(encoding="utf-8")
m = re.search(r'<svg[^>]*width="(\d+)" height="(\d+)"', svg)
W, H = int(m.group(1)), int(m.group(2))
BG = re.search(r'<rect x="0" y="0" width="\d+" height="\d+"[^>]*fill="(#[0-9a-f]{6})"', svg).group(1)

# ------------------------------------------------------------------ parse
ATTR = re.compile(r'([a-zA-Z][a-zA-Z0-9-]*)="([^"]*)"')


def attrs(tag: str) -> dict:
    return dict(ATTR.findall(tag))


elements: list[dict] = []  # {sec, kind, ...}
sec = "Canvas"
for line in svg.splitlines():
    line = line.strip()
    if not line:
        continue
    mm = re.match(r"<!--SEC:(.*?)-->", line)
    if mm:
        sec = mm.group(1)
        continue
    if line.startswith("<rect"):
        a = attrs(line)
        elements.append({"sec": sec, "kind": "rect", **a})
    elif line.startswith("<text"):
        a = attrs(line)
        body = re.search(r">(.*)</text>", line).group(1)
        a["text"] = html.unescape(body)
        elements.append({"sec": sec, "kind": "text", **a})
    elif line.startswith("<line"):
        elements.append({"sec": sec, "kind": "line", **attrs(line)})
    elif line.startswith("<path"):
        elements.append({"sec": sec, "kind": "path", **attrs(line)})
    elif line.startswith("<polygon"):
        elements.append({"sec": sec, "kind": "polygon", **attrs(line)})
    elif line.startswith("<circle"):
        elements.append({"sec": sec, "kind": "circle", **attrs(line)})

# ------------------------------------------------------------------ helpers
_ids = 1


def nid() -> str:
    global _ids
    _ids += 1
    return f"c{_ids}"


def f(v) -> float:
    return float(v)


def fmt(v: float) -> str:
    return ("%.2f" % v).rstrip("0").rstrip(".")


def text_width(s: str, size: float, bold: bool) -> float:
    per = 0.60 if bold else 0.56
    return max(10.0, len(s) * size * per + 6)


def style(**kw) -> str:
    return ";".join(f"{k}={v}" for k, v in kw.items() if v is not None) + ";"


def parse_path_points(d: str) -> list[tuple[float, float]] | None:
    """Only H/V polylines (M x,y H x V y H x ...) are converted to waypoints."""
    toks = re.findall(r"([MHVLZ])\s*([-\d.,\s]*)", d)
    pts: list[tuple[float, float]] = []
    x = y = 0.0
    for cmd, arg in toks:
        nums = [f(n) for n in re.split(r"[,\s]+", arg.strip()) if n]
        if cmd == "M":
            x, y = nums[0], nums[1]
            pts.append((x, y))
        elif cmd == "H":
            x = nums[0]
            pts.append((x, y))
        elif cmd == "V":
            y = nums[0]
            pts.append((x, y))
        elif cmd == "L":
            x, y = nums[0], nums[1]
            pts.append((x, y))
        else:
            return None
    return pts


def poly_points(p: str) -> list[tuple[float, float]]:
    return [(f(a), f(b)) for a, b in (pt.split(",") for pt in p.split())]


# ------------------------------------------------------------------ build cells (absolute coords first)
cells: list[dict] = []  # {id, sec, xml_fn, bbox, is_container, z}


def add(sec: str, bbox: tuple[float, float, float, float], xml, container=False, is_edge=False, name=""):
    cells.append({"id": nid(), "sec": sec, "bbox": bbox, "xml": xml, "container": container, "edge": is_edge, "name": name})


i = 0
n = len(elements)
while i < n:
    e = elements[i]
    k = e["kind"]
    if k == "rect":
        x, y, w, h = f(e["x"]), f(e["y"]), f(e["width"]), f(e["height"])
        rx = f(e.get("rx", 0))
        fill = e.get("fill", "none")
        stroke = e.get("stroke", "none")
        sw = f(e.get("stroke-width", 1))
        if sw == 0:
            stroke = "none"
        op = f(e.get("opacity", 1))
        dash = e.get("stroke-dasharray")
        st = style(
            rounded=1 if rx else 0, absoluteArcSize=1 if rx else None, arcSize=fmt(rx * 2) if rx else None,
            fillColor=fill, strokeColor=stroke, strokeWidth=fmt(sw) if stroke != "none" else None,
            opacity=int(round(op * 100)) if op < 1 else None,
            dashed=1 if dash else None, dashPattern=dash if dash else None, fixDash=1 if dash else None,
            html=1, whiteSpace="wrap",
        )
        is_bg = (x == 0 and y == 0 and w == W)
        container = (not is_bg) and ((stroke != "none" and h >= 60 and w >= 200) or (h == 34 and w >= 4000))
        add(e["sec"], (x, y, w, h), lambda cid, par, gx, gy, st=st, x=x, y=y, w=w, h=h: (
            f'<mxCell id="{cid}" value="" style="{st}" vertex="1" parent="{par}">'
            f'<mxGeometry x="{fmt(x-gx)}" y="{fmt(y-gy)}" width="{fmt(w)}" height="{fmt(h)}" as="geometry"/></mxCell>'),
            container=container, name="Background" if is_bg else "Panel")
        i += 1
    elif k == "text":
        s = e["text"]
        if not s.strip():
            i += 1
            continue
        size = f(e["font-size"])
        bold = e.get("font-weight") == "bold"
        italic = e.get("font-style") == "italic"
        anchor = e.get("text-anchor", "start")
        color = e.get("fill", "#000000")
        tw = text_width(s, size, bold)
        th = round(size * 1.4, 2)
        rot = None
        if "transform" in e:
            tm = re.search(r"translate\(([-\d.]+),([-\d.]+)\)\s*rotate\(([-\d.]+)\)", e["transform"])
            tx, ty, ang = f(tm.group(1)), f(tm.group(2)), f(tm.group(3))
            # visual centre of an anchor-middle text at the origin is (0, -0.35*size) before rotation
            cx, cy = tx - 0.35 * size, ty  # rotate(-90): (x, y) -> (y, -x)
            x, y = cx - tw / 2, cy - th / 2
            rot = ang
            align = "center"
        else:
            bx, by = f(e["x"]), f(e["y"])
            cy = by - 0.35 * size
            y = cy - th / 2
            if anchor == "end":
                x, align = bx - tw, "right"
            elif anchor == "middle":
                x, align = bx - tw / 2, "center"
            else:
                x, align = bx, "left"
        fs = (1 if bold else 0) + (2 if italic else 0)
        st = style(text=None, html=1, strokeColor="none", fillColor="none", align=align, verticalAlign="middle",
                   whiteSpace="nowrap", overflow="visible", fontFamily="Inter", fontSize=fmt(size), fontColor=color,
                   fontStyle=fs if fs else None, spacing=0, spacingLeft=0, spacingRight=0, spacingTop=0, spacingBottom=0,
                   rotation=fmt(rot) if rot is not None else None)
        st = "text;" + st
        val = html.escape(s, quote=False)
        anchor_pt = (f(e["x"]), f(e["y"])) if "transform" not in e else (x + tw / 2, y + th / 2)
        add(e["sec"], (x, y, tw, th), lambda cid, par, gx, gy, st=st, x=x, y=y, w=tw, h=th, val=val: (
            f'<mxCell id="{cid}" value={quoteattr(val)} style="{st}" vertex="1" parent="{par}">'
            f'<mxGeometry x="{fmt(x-gx)}" y="{fmt(y-gy)}" width="{fmt(w)}" height="{fmt(h)}" as="geometry"/></mxCell>'),
            name="Text")
        cells[-1]["anchor"] = anchor_pt
        i += 1
    elif k in ("line", "path"):
        if k == "line":
            pts = [(f(e["x1"]), f(e["y1"])), (f(e["x2"]), f(e["y2"]))]
        else:
            d = e["d"]
            if "A" in d:  # lock shackle: rounded outline, drawn beneath the previous rect (the lock body)
                pm = re.match(r"M([\d.]+),([\d.]+) V([\d.]+) A([\d.]+),[\d.]+ 0 0 1 ([\d.]+),([\d.]+) V([\d.]+)", d)
                x0, y0, ytop, r, x1 = f(pm.group(1)), f(pm.group(2)), f(pm.group(3)), f(pm.group(4)), f(pm.group(5))
                sx, sy, sw_, sh = x0, ytop - r, x1 - x0, (y0 - (ytop - r)) + r
                st = style(rounded=1, absoluteArcSize=1, arcSize=fmt(2 * r), fillColor="none",
                           strokeColor=e.get("stroke"), strokeWidth=e.get("stroke-width", "2"), html=1)
                cell = {"id": nid(), "sec": e["sec"], "bbox": (sx, sy, sw_, sh), "container": False, "edge": False, "name": "Lock shackle",
                        "xml": lambda cid, par, gx, gy, st=st, x=sx, y=sy, w=sw_, h=sh: (
                            f'<mxCell id="{cid}" value="" style="{st}" vertex="1" parent="{par}">'
                            f'<mxGeometry x="{fmt(x-gx)}" y="{fmt(y-gy)}" width="{fmt(w)}" height="{fmt(h)}" as="geometry"/></mxCell>')}
                # insert before the lock body (previous rect) so the body hides the shackle's lower half
                j = len(cells) - 1
                while j >= 0 and cells[j]["name"] != "Panel":
                    j -= 1
                cells.insert(j if j >= 0 else len(cells), cell)
                i += 1
                continue
            pts = parse_path_points(d)
        head = None
        if i + 1 < n and elements[i + 1]["kind"] == "polygon":
            pp = poly_points(elements[i + 1]["points"])
            if len(pp) == 3:
                head = pp
        stroke = e.get("stroke", "#000000")
        sw = e.get("stroke-width", "1")
        dash = e.get("stroke-dasharray")
        if head:
            tip = head[0]
            pts[-1] = tip
        st = style(edgeStyle="none", html=1, strokeColor=stroke, strokeWidth=sw, endArrow="block" if head else "none",
                   endFill=1 if head else None, endSize=6 if head else None, dashed=1 if dash else None,
                   dashPattern=dash if dash else None, fixDash=1 if dash else None, rounded=0)
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        bbox = (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
        mid = pts[1:-1]
        def edge_xml(cid, par, gx, gy, st=st, pts=pts, mid=mid):
            s0, t0 = pts[0], pts[-1]
            way = "".join(f'<mxPoint x="{fmt(px-gx)}" y="{fmt(py-gy)}"/>' for px, py in mid)
            arr = f'<Array as="points">{way}</Array>' if way else ""
            return (f'<mxCell id="{cid}" value="" style="{st}" edge="1" parent="{par}"><mxGeometry relative="1" as="geometry">'
                    f'<mxPoint x="{fmt(s0[0]-gx)}" y="{fmt(s0[1]-gy)}" as="sourcePoint"/>'
                    f'<mxPoint x="{fmt(t0[0]-gx)}" y="{fmt(t0[1]-gy)}" as="targetPoint"/>{arr}</mxGeometry></mxCell>')
        add(e["sec"], bbox, edge_xml, is_edge=True, name="Connector")
        i += 2 if head else 1
    elif k == "polygon":
        pp = poly_points(e["points"])
        xs = [p[0] for p in pp]; ys = [p[1] for p in pp]
        x, y, w, h = min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
        if len(pp) == 4:  # diamond gate
            st = style(rhombus=None, html=1, fillColor=e.get("fill", "none"), strokeColor=e.get("stroke", "none"),
                       strokeWidth=e.get("stroke-width", "1"))
            st = "rhombus;" + st
        else:  # stray arrowhead without a preceding line: draw as a triangle
            st = "triangle;" + style(html=1, fillColor=e.get("fill", "#000"), strokeColor="none")
        add(e["sec"], (x, y, w, h), lambda cid, par, gx, gy, st=st, x=x, y=y, w=w, h=h: (
            f'<mxCell id="{cid}" value="" style="{st}" vertex="1" parent="{par}">'
            f'<mxGeometry x="{fmt(x-gx)}" y="{fmt(y-gy)}" width="{fmt(w)}" height="{fmt(h)}" as="geometry"/></mxCell>'),
            name="Gate diamond")
        i += 1
    elif k == "circle":
        cx, cy, r = f(e["cx"]), f(e["cy"]), f(e["r"])
        st = "ellipse;" + style(html=1, fillColor=e.get("fill", "none"), strokeColor=e.get("stroke", "none"),
                                strokeWidth=e.get("stroke-width", "1"))
        add(e["sec"], (cx - r, cy - r, 2 * r, 2 * r), lambda cid, par, gx, gy, st=st, x=cx - r, y=cy - r, w=2 * r: (
            f'<mxCell id="{cid}" value="" style="{st}" vertex="1" parent="{par}">'
            f'<mxGeometry x="{fmt(x-gx)}" y="{fmt(y-gy)}" width="{fmt(w)}" height="{fmt(w)}" as="geometry"/></mxCell>'),
            name="Step dot")
        i += 1
    else:
        i += 1

# ------------------------------------------------------------------ layers + groups
sections: list[str] = []
for c in cells:
    if c["sec"] not in sections:
        sections.append(c["sec"])
layer_ids = {s: ("1" if idx == 0 else f"L{idx}") for idx, s in enumerate(sections)}


def inside(c, box, tol=2.0) -> bool:
    bx, by, bw, bh = box["bbox"]
    if "anchor" in c:  # text: judge by its anchor point (estimated widths are generous)
        ax, ay = c["anchor"]
        return bx - tol <= ax <= bx + bw + tol and by - tol <= ay <= by + bh + tol
    x, y, w, h = c["bbox"]
    return x >= bx - tol and y >= by - tol and x + w <= bx + bw + tol and y + h <= by + bh + tol


out: list[str] = []
out.append('<mxfile host="local" agent="svg_to_drawio.py" version="24.7.17">')
out.append(f'  <diagram id="pipeline" name={quoteattr(TITLE)}>')
out.append(f'    <mxGraphModel dx="0" dy="0" grid="0" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" '
           f'page="0" pageScale="1" pageWidth="{W}" pageHeight="{H}" background="{BG}" math="0" shadow="0">')
out.append("      <root>")
out.append('        <mxCell id="0"/>')
for s in sections:
    lid = layer_ids[s]
    if lid == "1":
        out.append(f'        <mxCell id="1" value={quoteattr(s)} style="locked=1;" parent="0"/>')
    else:
        out.append(f'        <mxCell id="{lid}" value={quoteattr(s)} style="" parent="0"/>')

grouped = 0
for s in sections:
    lid = layer_ids[s]
    sec_cells = [c for c in cells if c["sec"] == s]
    containers = sorted([c for c in sec_cells if c["container"]], key=lambda c: -(c["bbox"][2] * c["bbox"][3]))
    assigned: dict[str, dict] = {}
    for box in containers:
        if box["id"] in assigned:
            continue
        members = [c for c in sec_cells if c is not box and not c["container"] and c["id"] not in assigned and inside(c, box)]
        if not members:
            continue
        gid = nid()
        xs = [box["bbox"][0]] + [c["bbox"][0] for c in members]
        ys = [box["bbox"][1]] + [c["bbox"][1] for c in members]
        x2 = [box["bbox"][0] + box["bbox"][2]] + [c["bbox"][0] + c["bbox"][2] for c in members]
        y2 = [box["bbox"][1] + box["bbox"][3]] + [c["bbox"][1] + c["bbox"][3] for c in members]
        gx, gy, gw, gh = min(xs), min(ys), max(x2) - min(xs), max(y2) - min(ys)
        # the group's origin is its box; children carry coordinates relative to it
        grp = {"gid": gid, "gx": gx, "gy": gy, "gw": gw, "gh": gh, "members": [box] + members}
        for c in grp["members"]:
            assigned[c["id"]] = grp
        grouped += 1
    emitted_groups: set[str] = set()
    for c in sec_cells:
        grp = assigned.get(c["id"])
        if grp is None:
            out.append("        " + c["xml"](c["id"], lid, 0, 0))
            continue
        if grp["gid"] not in emitted_groups:
            emitted_groups.add(grp["gid"])
            out.append(f'        <mxCell id="{grp["gid"]}" value="" style="group" vertex="1" connectable="0" parent="{lid}">'
                       f'<mxGeometry x="{fmt(grp["gx"])}" y="{fmt(grp["gy"])}" width="{fmt(grp["gw"])}" height="{fmt(grp["gh"])}" as="geometry"/></mxCell>')
            for mcell in grp["members"]:
                out.append("        " + mcell["xml"](mcell["id"], grp["gid"], grp["gx"], grp["gy"]))
out.append("      </root>")
out.append("    </mxGraphModel>")
out.append("  </diagram>")
out.append("</mxfile>")
OUT.write_text("\n".join(out) + "\n", encoding="utf-8")

print(json.dumps({"cells": len(cells), "layers": sections, "groups": grouped, "out": str(OUT)}, indent=1))
