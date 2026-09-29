#!/usr/bin/env python3
"""Generate the autonomous-capability companion SVG from pipeline-model.json.

Replaces the former hand-authored SVG with the same layout and colours, rendered in
DejaVu Sans, with generic (non-product) names and no empty spacer <text> nodes.
Design artifact only; generating it does not exercise the product.
"""
import sys
from pathlib import Path

from diagram_common import Canvas, esc, load_model, write_svg

M = load_model()
DIAGRAM = "autonomous-capabilities"
D = M["diagrams"][DIAGRAM]
N = M.node
W, H = 1800, 1440
ROLE = {"step": "#8cbaff", "bytes": "#7fd6a4", "gate": "#f0c060", "operation": "#67d3d0",
        "acceptance": "#c9a4f0", "contain": "#ef968b"}
STRONG = "#f2f4f7"; INK = "#d8dbe0"; ARROW = "#7fd6a4"; CLAIM = "#f0c060"
c = Canvas()


def rect(x, y, w, h, stroke="#495364", fill="#20232a", rx=12):
    c.raw(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}"/>')


def text(x, y, s, size, fill=INK):
    c.raw(f'<text x="{x}" y="{y}" fill="{fill}" font-family="DejaVu Sans, sans-serif" font-size="{size}">{esc(s)}</text>')


c.raw(f'<rect x="0" y="0" width="{W}" height="{H}" fill="#16181c"/>')
c.sec("Desired workflow")
hd = N("cap-header")
with c.node("cap-header"):
    text(35, 55, hd["title"], 34, STRONG)
    text(35, 91, hd["subtitle"], 21, ROLE["step"])
    text(35, 125, hd["tagline"], 17)
for i in range(6):
    st = N(f"cap-step-{i+1}")
    x = 35 + i * 290
    with c.node(st["id"]):
        rect(x, 158, 270, 128)
        text(x + 15, 192, f"{st['n']} {st['title']}", 20, ROLE[st["family"]])
        for j, row in enumerate(st["rows"]):
            text(x + 15, 225 + j * 24, row, 15)
    if i < 5:
        text(x + 272, 228, "→", 17, ARROW)
with c.node("cap-banner"):
    rect(35, 305, 1730, 57)
    text(53, 340, N("cap-banner")["title"], 19, CLAIM)
c.sec("Milestones and evidence boundaries")
with c.node("cap-milestones"):
    text(35, 408, N("cap-milestones")["title"], 21, STRONG)
    for k in range(8):
        ms = N(f"milestone-M{k}")
        x = 35 + (k % 4) * 435
        y = 435 if k < 4 else 765
        color = ROLE[ms["family"]]
        with c.node(ms["id"]):
            rect(x, y, 425, 308, stroke=color)
            text(x + 17, y + 36, f"{ms['n']}  {ms['title']}", 23, STRONG)
            text(x + 17, y + 67, ms["status"], 13, color)
            for j, row in enumerate(ms["body"]):
                text(x + 17, y + 100 + j * 25, row, 17)
            skip = len(ms["body"]) + 1  # one blank line of spacing, not an empty <text>
            for j, row in enumerate(ms["proof"]):
                text(x + 17, y + 100 + (skip + j) * 25, row, 17)
c.sec("Proof and human boundary")
demo = N("cap-demo")
with c.node("cap-demo"):
    rect(35, 1115, 1115, 210, stroke=ROLE[demo["family"]])
    text(55, 1152, demo["title"], 22, ROLE[demo["family"]])
    for j, row in enumerate(demo["lines"]):
        text(55, 1187 + j * 27, row, 18)
hum = N("cap-human")
with c.node("cap-human"):
    rect(1170, 1115, 595, 210, stroke=ROLE[hum["family"]])
    text(1190, 1152, hum["title"], 22, ROLE[hum["family"]])
    for j, row in enumerate(hum["lines"]):
        text(1190, 1187 + j * 27, row, 17)
ft = N("cap-footer")
with c.node("cap-footer"):
    text(35, 1370, ft["title"], 19, CLAIM)
    text(35, 1406, ft["contract"], 17)

svg = c.render(width=W, height=H, diagram_id=DIAGRAM, title=D["title"], desc=D["desc"], first_sec="Canvas")
path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name(D["svg"])
write_svg(svg, path, D["svg"])
