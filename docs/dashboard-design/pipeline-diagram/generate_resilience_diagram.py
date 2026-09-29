#!/usr/bin/env python3
"""Generate the design-only resilience companion SVG from pipeline-model.json.

No product operations.  Content lives in the model; this file owns layout and palette.
Each model node is a <g id> in reading order.
"""
import sys
from pathlib import Path

from diagram_common import Canvas, esc, load_model, write_svg

M = load_model()
DIAGRAM = "resilience-contracts"
D = M["diagrams"][DIAGRAM]
N = M.node
W, H = 1800, 1435
ROLE = {"step": "#8cbaff", "bytes": "#7fd6a4", "gate": "#f0c060", "operation": "#67d3d0",
        "acceptance": "#c9a4f0", "contain": "#ef968b"}
c = Canvas()


def rect(x, y, w, h, fill='#20232a', stroke='#495364'):
    c.raw(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{fill}" stroke="{stroke}"/>')


def text(x, y, s, size=17, color='#d8dbe0', bold=False):
    c.raw(f'<text x="{x}" y="{y}" font-family="DejaVu Sans, sans-serif" font-size="{size}" fill="{color}" font-weight="{"bold" if bold else "normal"}">{esc(s)}</text>')


def box(x, y, w, h, node_id):
    nd = N(node_id)
    with c.node(node_id):
        rect(x, y, w, h); text(x+16, y+30, f"{nd['label']} · {nd['title']}", 21, ROLE[nd["family"]], True)
        for i, row in enumerate(nd["rows"]): text(x+16, y+63+i*26, row)


def arrow(x1, y1, x2, y2):
    c.raw(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#8cbaff" stroke-width="3"/>')
    c.raw(f'<polygon points="{x2},{y2} {x2-11},{y2-6} {x2-11},{y2+6}" fill="#8cbaff"/>')


rect(0, 0, W, H, '#16181c', '#16181c')
hd = N("resil-header")
with c.node("resil-header"):
    text(35, 43, hd["title"], 32, '#f2f4f7', True)
    text(35, 78, hd["status"], 18, '#f0c060')
    text(35, 109, hd["tagline"], 18)
c.sec("Failure lifecycle")
box(35, 140, 550, 260, "resil-step-1")
arrow(585, 269, 625, 269)
box(625, 140, 550, 260, "resil-step-2")
arrow(1175, 269, 1215, 269)
box(1215, 140, 550, 260, "resil-step-3")
c.sec("Acceptance and preventive feedback")
with c.node("resil-acceptance"):  # starts right of the 3 -> 4 arrow, which drops into step 4 at x=310
    text(360, 449, N("resil-acceptance")["title"], 21, '#f2f4f7', True)
# Drawn model edge (inference 'stated'): resil-step-4 depends_on resil-step-3.  The step 6 -> 1
# feedback stays an undrawn interpretation until its review concludes.
c.elbow([(1490, 400), (1490, 416), (310, 416), (310, 480)], '#8cbaff')
box(35, 480, 550, 260, "resil-step-4")
arrow(585, 610, 625, 610)
box(625, 480, 550, 260, "resil-step-5")
arrow(1175, 610, 1215, 610)
box(1215, 480, 550, 260, "resil-step-6")
c.sec("Failure containment boundaries")
box(35, 790, 550, 285, "control-plane")
box(625, 790, 550, 285, "data-provider")
box(1215, 790, 550, 285, "policy-canary")
c.sec("Worked interruption and evidence boundary")
wi = N("worked-interruption")
with c.node("worked-interruption"):
    rect(35, 1115, 1730, 285)
    text(52, 1150, wi["title"], 23, '#f2f4f7', True)
    for i, s in enumerate(wi["lines"]): text(52, 1189 + i*35, s, 19)
    text(52, 1371, wi["status"], 18, '#f0c060')

svg = c.render(width=W, height=H, diagram_id=DIAGRAM, title=D["title"], desc=D["desc"], first_sec="Canvas")
path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name(D["svg"])
write_svg(svg, path, D["svg"])
