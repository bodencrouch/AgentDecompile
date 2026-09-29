#!/usr/bin/env python3
"""Author the execution-and-evidence companion SVG from pipeline-model.json.

Design artifacts only; no pipeline execution or runtime checks.  Content lives in the
model; this file owns layout and palette.  Each model node is a <g id> in reading order.
"""
import sys
from pathlib import Path

from diagram_common import Canvas, esc, load_model, write_svg

M = load_model()
DIAGRAM = "execution-contracts"
D = M["diagrams"][DIAGRAM]
N = M.node
W, H = 1800, 1510
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
        rect(x, y, w, h); text(x+16, y+29, f"{nd['label']} · {nd['title']}", 20, ROLE[nd["family"]], True)
        for i, row in enumerate(nd["rows"]): text(x+16, y+60+i*25, row)


def arrow(x1, y1, x2, y2, color='#8cbaff'):
    c.raw(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="3"/>')
    if x1 == x2: points = f'{x2},{y2} {x2-6},{y2-11} {x2+6},{y2-11}'
    else: points = f'{x2},{y2} {x2-11},{y2-6} {x2-11},{y2+6}'
    c.raw(f'<polygon points="{points}" fill="{color}"/>')


rect(0, 0, W, H, '#16181c', '#16181c')
hd = N("exec-header")
with c.node("exec-header"):
    text(35, 43, hd["title"], 32, '#f2f4f7', True)
    text(35, 76, hd["status"], 18, '#f0c060')
    text(35, 107, hd["tagline"], 18)
c.sec("Task and acceptance contract")
box(35, 135, 550, 240, "exec-step-1")
arrow(585, 255, 625, 255)
box(625, 135, 550, 240, "exec-step-2")
arrow(1175, 255, 1215, 255)
box(1215, 135, 550, 240, "exec-step-3")
c.sec("Independent binding evidence")
with c.node("exec-binding"):
    text(35, 423, N("exec-binding")["title"], 24, '#f2f4f7', True)
    box(35, 445, 550, 205, "contract-bytes")
    box(625, 445, 550, 205, "contract-identity")
    box(1215, 445, 550, 205, "contract-operation")
c.sec("Acceptance and readiness fork")
with c.node("exec-proof-flow"):  # starts right of the receipts bus that drops into box 4 at x=310
    text(625, 690, N("exec-proof-flow")["title"], 16, '#98a0ad')
# Drawn model edges (inference 'stated'): accept-4 consumes contract-bytes, -identity and -operation,
# as one receipts bus into box 4; cap-5A and cap-5B each depend_on accept-4, as a fork out of box 4.
c.elbow([(1490, 650), (1490, 664), (900, 664)], '#8cbaff', head=False)
c.elbow([(900, 650), (900, 664), (310, 664)], '#8cbaff', head=False)
arrow(310, 650, 310, 710)
box(35, 710, 550, 215, "accept-4")
arrow(585, 817, 625, 817)
c.elbow([(605, 817), (605, 964), (1710, 964), (1710, 925)], '#8cbaff')
box(625, 710, 550, 215, "cap-5A")
box(1215, 710, 550, 215, "cap-5B")
with c.node("exec-separate-outputs"):
    text(1181, 946, N("exec-separate-outputs")["title"], 16, '#98a0ad')
c.sec("Failure containment and continuation")
box(35, 980, 550, 235, "fence")
box(625, 980, 550, 235, "quarantine")
box(1215, 980, 550, 235, "continue")
c.sec("Design challenge and future evidence")
ch = N("challenge-late-worker")
with c.node("challenge-late-worker"):
    rect(35, 1250, 1730, 215)
    text(52, 1282, ch["title"], 23, '#f2f4f7', True)
    for i, s in enumerate(ch["lines"]): text(52, 1316 + i*33, s, 19)
    text(52, 1421, ch["status"], 18, '#f0c060')
with c.node("exec-footer"):
    text(35, 1492, N("exec-footer")["title"], 16, '#98a0ad')

svg = c.render(width=W, height=H, diagram_id=DIAGRAM, title=D["title"], desc=D["desc"], first_sec="Canvas")
path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name(D["svg"])
write_svg(svg, path, D["svg"])
