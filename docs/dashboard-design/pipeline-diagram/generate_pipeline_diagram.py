#!/usr/bin/env python3
"""Generate the AgentDecompile recovery-pipeline overview SVG from pipeline-model.json.

Design rules: left->right = dependency order; vertical stacking = concurrency;
six colour families, each also named by an uppercase word (never colour alone);
five concurrent lanes (A–E); every stage card answers try / how / in->out / gate;
locks mark shared-state serialisation points; dashed = failover or labelled ↺ feedback;
ladders = fallback stacks.  No product, binary or project names anywhere.

Content (every drawn string) lives in pipeline-model.json; this file owns layout and
palette only.  Each model node is wrapped in <g id="<node id>"> and emitted in reading
order; a text-box collision check runs before the file is written.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

from diagram_common import Canvas, esc, load_model, text_width, write_svg

M = load_model()
DIAGRAM = "agentdecompile-recovery-pipeline"
D = M["diagrams"][DIAGRAM]
N = M.node
FAMWORD = {k: v["word"] for k, v in M["families"].items()}

W = 4400
c = Canvas()

# ---- palette (graphite, restrained) ----
BG = "#16181c"; PANEL = "#20232a"; LINE = "#3a3f4a"; INK = "#d8dbe0"; MUTED = "#98a0ad"; STRONG = "#f2f4f7"
FAM = {  # lane families: (header fill, ink)
    "identity": ("#2b4a7a", "#8cbaff"),   # blue
    "recovery": ("#25503e", "#7fd6a4"),   # green
    "unify":    ("#5a4420", "#f0c060"),   # amber
    "runtime":  ("#1f4d4f", "#67d3d0"),   # teal
    "verify":   ("#452a5a", "#c9a4f0"),   # purple
    "intake":   ("#2c2f36", "#b0b6c2"),   # gray (intake / cross-cutting)
}
GATE = "#f0c060"; LOCK = "#ef968b"; FAIL = "#ef968b"; OK = "#7fd6a4"
FONT = "Inter, 'Segoe UI', system-ui, sans-serif"
MONO = "ui-monospace, Consolas, monospace"


def rect(x, y, w, h, fill, stroke=LINE, rx=4, sw=1.2, dash=None, opacity=1):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    c.raw(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d} opacity="{opacity}"/>')


def text(x, y, s, size=13, fill=INK, weight="normal", anchor="start", mono=False, italic=False):
    if not s:
        return  # never emit empty <text> spacer nodes
    fam = MONO if mono else FONT
    st = ' font-style="italic"' if italic else ""
    c.raw(f'<text x="{x}" y="{y}" font-family="{fam}" font-size="{size}" fill="{fill}" font-weight="{weight}" text-anchor="{anchor}"{st}>{esc(s)}</text>')


def lines(x, y, items, size=12, fill=INK, lh=None, bullet="", mono=False):
    lh = lh or size + 5
    for i, s in enumerate(items):
        text(x, y + i*lh, (bullet + s) if bullet else s, size, fill, mono=mono)
    return y + len(items)*lh


def head(x, y, dx, dy, color):
    """explicit arrowhead polygon (Figma's SVG import drops <marker>)"""
    L = math.hypot(dx, dy) or 1.0
    ux, uy = dx / L, dy / L
    px, py = -uy, ux
    bx, by = x - ux * 10, y - uy * 10
    c.raw(f'<polygon points="{x:.1f},{y:.1f} {bx+px*4:.1f},{by+py*4:.1f} {bx-px*4:.1f},{by-py*4:.1f}" fill="{color}"/>')


def arrow(x1, y1, x2, y2, color=MUTED, dash=None, width=2):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    c.raw(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{width}"{d}/>')
    head(x2, y2, x2 - x1, y2 - y1, color)


def gate(x, y, label=None, sub=None):
    """diamond gate marker; label and sub-label sit directly below it"""
    s = 18
    c.raw(f'<polygon points="{x},{y-s} {x+s},{y} {x},{y+s} {x-s},{y}" fill="{BG}" stroke="{GATE}" stroke-width="2"/>')
    text(x, y+4, "G", 11, GATE, "bold", "middle")
    text(x, y+s+14, label, 10.5, GATE, "bold", "middle")
    text(x, y+s+27, sub, 10, MUTED, anchor="middle", italic=True)


def lock(x, y, label):
    c.raw(f'<rect x="{x-9}" y="{y-6}" width="18" height="14" rx="2" fill="{LOCK}" opacity="0.9"/>')
    c.raw(f'<path d="M{x-5},{y-6} V{y-10} A5,5 0 0 1 {x+5},{y-10} V{y-6}" fill="none" stroke="{LOCK}" stroke-width="2.2"/>')
    text(x+14, y+4, label, 10.5, LOCK, "bold")


def header_band(x, y, w, fill):
    c.raw(f'<rect x="{x}" y="{y}" width="{w}" height="30" rx="6" fill="{fill}"/>')
    c.raw(f'<rect x="{x}" y="{y+22}" width="{w}" height="8" fill="{fill}"/>')


def card(x, y, w, h, fam, num, title, tryline, how, io, gatetxt=None, tag=None, gate_id=None, famword=None):
    fill, accent = FAM[fam]
    rect(x, y, w, h, PANEL, LINE, 6)
    header_band(x, y, w, fill)
    if num: text(x+10, y+20, num, 13, STRONG, "bold")
    text(x + (44 if num else 10), y+20, title, 13.5, STRONG, "bold")
    if famword: text(x+w-10, y+20, famword, 9.5, STRONG, "bold", "end")
    if tag: text(x+w-10, y+37, tag, 9.5, accent, "bold", "end")
    yy = y + 48
    text(x+10, yy, "Trying to:", 10.5, accent, "bold"); yy += 15
    yy = lines(x+10, yy, tryline, 11.5, INK, 15)
    yy += 4
    text(x+10, yy, "How:", 10.5, accent, "bold"); yy += 15
    yy = lines(x+10, yy, how, 11, INK, 14.5, bullet="• ")
    if io:
        yy += 4
        text(x+10, yy, "In → out:", 10.5, accent, "bold"); yy += 15
        yy = lines(x+10, yy, io, 11, MUTED, 14.5)
    if gatetxt:
        yy += 4
        with c.node(gate_id):
            text(x+10, yy, "Gate: ", 10.5, GATE, "bold")
            text(x+46, yy, gatetxt, 11, GATE)
    return yy


def lane_header(x, y, w, fam, title, sub, famword=None):
    fill, accent = FAM[fam]
    c.raw(f'<rect x="{x}" y="{y}" width="{w}" height="34" rx="4" fill="{fill}" opacity="0.85"/>')
    text(x+12, y+22, title, 14, STRONG, "bold")
    if famword:
        text(x + 12 + text_width(title, 14, True) + 12, y+22, famword, 10, STRONG, "bold")
    text(x+w-12, y+22, sub, 11.5, accent, anchor="end", italic=True)


def concurrency_bracket(x, y1, y2, label):
    c.raw(f'<path d="M{x+14},{y1} H{x} V{y2} H{x+14}" fill="none" stroke="{FAM["unify"][1]}" stroke-width="2.5"/>')
    c.raw(f'<text transform="translate({x-8},{(y1+y2)/2}) rotate(-90)" font-family="{FONT}" font-size="12.5" font-weight="bold" fill="{FAM["unify"][1]}" text-anchor="middle">{esc(label)}</text>')


# ================================================================== canvas + header
rect(0, 0, W, "{H}", BG, BG, 0, 0)  # height patched once the layout is known

c.sec("Header")
hdr = N("overview-header")
with c.node("overview-header"):
    text(40, 52, hdr["title"], 30, STRONG, "bold")
    text(40, 84, hdr["subtitle"], 14, MUTED)
    # the "Design target:" prefix carries the meaning; italic is decoration only
    text(40, 108, hdr["design_target"], 14, FAM["unify"][1], italic=True)
    text(40, 128, hdr["scale_note"], 12.5, MUTED, italic=True)
htr = N("how-to-read")
with c.node("how-to-read"):
    rect(2700, 22, 1660, 112, PANEL, FAM["unify"][1], 6)
    text(2712, 44, htr["title"], 12, FAM["unify"][1], "bold")
    lines(2712, 64, htr["items"] + [htr["key"]], 11.5, INK, 16)

c.sec("Row 0 - intake and the 8-stage ladder")
# ================================================================== ROW 0: intake + 8 stages
Y0 = 150
mp = N("main-pipeline")
with c.node("main-pipeline"):
    lane_header(40, Y0, W-80, "recovery", mp["title"], mp["subtitle"])

CW, CH, GAP = 400, 380, 34
GATE_GAP = 164          # stage 4 -> 5: room for the gate diamond and its labels
cy = Y0 + 50
SX = []
x = 40
for i in range(9):
    SX.append(x)
    x += CW + (GATE_GAP if i == 4 else GAP)
MID = cy + CH/2
BELOW = cy + CH           # bottom edge of the stage row
FEED_Y = BELOW + 62       # 7–8 feedback runs below the stage-4 failover loop


def feedback(edge_id):
    e = M.edge(edge_id)
    color = FAM["identity" if edge_id == "feedback-1-2" else "verify"][1]
    with c.node(edge_id):
        if edge_id == "feedback-1-2":
            x1, x2, yy = SX[2] + 172, SX[1] + 200, BELOW + 12
            arrow(x1, yy, x2, yy, color, "4 4")
            text((x1 + x2) / 2, yy + 16, e["label"], 11, color, anchor="middle")
        else:  # from stage 7 down, left under the failover loop, up into stage 3
            xs, xt = SX[7] + 122, SX[3] + 218
            c.raw(f'<path d="M{xs},{BELOW} V{FEED_Y} H{xt} V{BELOW}" fill="none" stroke="{color}" stroke-width="2" stroke-dasharray="4 4"/>')
            head(xt, BELOW, 0, -1, color)
            text(SX[6] + CW/2, FEED_Y - 6, e["label"], 11, color, anchor="middle")


for i in range(9):
    st = N(f"stage-{i}")
    cx = SX[i]
    with c.node(st["id"]):
        card(cx, cy, CW, CH, st["family"], st["n"], st["title"], st["try"], st["how"], st["io"],
             gatetxt=N(st["gate_id"])["title"] if st["gate_id"] else None, tag=st.get("tag"),
             gate_id=st["gate_id"], famword=FAMWORD[st["family"]])
        if i == 4:  # failover loop under stage 4, read right after its gate
            e = M.edge("stage-4-failover")
            with c.node("stage-4-failover"):
                c.raw(f'<path d="M{cx+300},{BELOW} V{BELOW+26} H{cx+80} V{BELOW}" fill="none" stroke="{FAIL}" stroke-width="2" stroke-dasharray="6 4"/>')
                head(cx+80, BELOW, 0, -1, FAIL)
                text(cx+190, BELOW+42, e["label"], 10.5, FAIL, anchor="middle", italic=True)
    if i == 2:
        feedback("feedback-1-2")
    if i < 8:
        arrow(cx+CW, MID, SX[i+1], MID)
    if i == 4:  # the gate sits on the 4 -> 5 dependency arrow; labels stay inside the widened gap
        g = N("gate-4-5")
        with c.node("gate-4-5"):
            gate(cx + CW + GATE_GAP/2, MID, g["title"], g["sub"])
feedback("feedback-7-8")

c.sec("Row 1 - concurrent lanes")
# ================================================================== ROW 1: concurrent lanes
Y1 = BELOW + 96
LX, LW = 60, W - 100
LCH, LG = 216, 14
LANE_H = {"lane-A": 216, "lane-B": 248, "lane-C": 216, "lane-D": 248, "lane-E": 248}
lanes_end = Y1 + sum(42 + h + 16 for h in LANE_H.values())
with c.node("lanes"):
    concurrency_bracket(30, Y1, lanes_end - 16, N("lanes")["title"])


def lane(y, ln, lch):
    fam = ln["family"]
    with c.node(ln["id"]):
        lane_header(LX, y, LW, fam, f"LANE {ln['letter']} · {ln['title']}", ln["subtitle"], FAMWORD[fam])
        connects = ln["connects"]
        c.raw(f'<rect x="{LX+LW-10-len(connects)*6.6}" y="{y-16}" width="{len(connects)*6.6+10}" height="18" rx="3" fill="{BG}" stroke="{FAM[fam][1]}"/>')
        text(LX+LW-5, y-3, connects, 10.5, FAM[fam][1], "bold", "end")
        n = len(ln["cards"])
        lcw = min(500, (LW - (n-1)*LG) / n)
        x = LX
        yy = y + 42
        for cd in ln["cards"]:
            with c.node(cd["id"]):
                card(x, yy, lcw, lch, fam, "", cd["title"], cd["try"], cd["how"], cd["io"], cd.get("gate"), cd.get("tag"))
            x += lcw + LG
        rem = LX + LW - x
        if ln["outputs"] and rem > 320:
            fill, accent = FAM[fam]
            rect(x, yy, rem, lch, BG, accent, 6, dash="5 4")
            text(x+14, yy+24, "OUTPUTS  →  who consumes them", 12, accent, "bold")
            lines(x+14, yy+48, ln["outputs"], 11.5, INK, 17, bullet="→ ")
    return y + 42 + lch + 16


y = Y1
for lid, lch in LANE_H.items():
    y = lane(y, N(lid), lch)
assert y == lanes_end

c.sec("Row 2 - exhaustive resolution ladders")
# ================================================================== ROW 2: ladders + locks + export
Y2 = y + 40
with c.node("ladders"):
    text(40, Y2 + 22, N("ladders")["title"], 15, STRONG, "bold")

LDX = 40; LDW = 460; LDH = 366; LDG = 14


def ladder(x, y, ld):
    fill, accent = FAM[ld["family"]]
    with c.node(ld["id"]):
        rect(x, y, LDW, LDH, PANEL, LINE, 6)
        header_band(x, y, LDW, fill)
        text(x+10, y+20, f"{ld['letter']} · {ld['title']}", 13, STRONG, "bold")
        text(x+LDW-10, y+20, FAMWORD[ld["family"]], 9.5, STRONG, "bold", "end")
        yy = y + 46
        for i, mb in enumerate(ld["members"]):
            with c.node(mb["id"]):
                c.raw(f'<circle cx="{x+18}" cy="{yy-4}" r="9" fill="{fill}" stroke="{accent}" stroke-width="1.2"/>')
                text(x+18, yy, str(mb["n"]), 10, STRONG, "bold", "middle")
                bracket = mb.get("label", mb["slug"])
                text(x+34, yy, f"[{bracket}] {mb['text']}" if bracket else mb["text"], 11, INK)
                if i < len(ld["members"])-1:
                    c.raw(f'<line x1="{x+18}" y1="{yy+6}" x2="{x+18}" y2="{yy+18}" stroke="{FAIL}" stroke-width="1.5" stroke-dasharray="3 3"/>')
            yy += 24
        for j, f in enumerate(reversed(ld["outcomes"])):
            text(x+10, y+LDH-14 - j*14, f, 10.5, FAIL, "bold")


ly = Y2 + 40
for k, letter in enumerate("ABCDEF"):
    ladder(LDX + (LDW+LDG)*k, ly, N(f"ladder-{letter}"))

c.sec("Row 2 - locks and failover rules")
# locks + failover rule panel
PX = LDX + (LDW+LDG)*6 + 20; PW = W - PX - 40
lk = N("locks")
with c.node("locks"):
    rect(PX, ly, PW, 200, PANEL, LINE, 6)
    text(PX+12, ly+24, lk["title"], 12.5, LOCK, "bold")
    for i in range(1, 6):
        with c.node(f"lock-{i}"):
            lock(PX+22, ly+28+24*i, N(f"lock-{i}")["title"])
    text(PX+12, ly+182, lk["note"], 10.5, MUTED, italic=True)

fr = N("failover-rule")
with c.node("failover-rule"):
    rect(PX, ly+216, PW, 150, PANEL, FAIL, 6, dash="6 4")
    text(PX+12, ly+240, fr["title"], 12.5, FAIL, "bold")
    lines(PX+12, ly+262, fr["lines"], 11, INK, 15)

c.sec("Terminal band - what you get")
# terminal band: WHAT YOU GET
TY = ly + max(LDH, 366) + 30
ex = N("export-target")
with c.node("export-target"):
    lane_header(40, TY, W-80, "unify", ex["title"], ex["subtitle"], FAMWORD["unify"])
bx = 40; bw = (W-80 - 6*16)/7; by = TY + 44; bh = 150
for eid in ("export-hookpack", "export-lua", "export-headers", "export-readiness",
            "export-divergence", "export-receipts", "export-projects"):
    card_ = N(eid)
    with c.node(eid):
        rect(bx, by, bw, bh, PANEL, FAM["unify"][1], 6, sw=1.6)
        text(bx+12, by+26, card_["title"], 14, STRONG, "bold")
        lines(bx+12, by+52, card_["lines"], 11.5, INK, 17)
    bx += bw + 16

c.sec("Footer - legend and determinism basis")
# ================================================================== footer: legend + basis band
FY = TY + 44 + bh + 24
lg = N("legend")
with c.node("legend"):
    rect(40, FY, W-80, 70, PANEL, LINE, 6)
    text(52, FY+24, lg["title"], 12.5, STRONG, "bold")
    lx = 130
    for le in [n for n in M.nodes_of(DIAGRAM) if n.get("parent") == "legend"]:
        label = le["title"]
        glyph = le["glyph"]
        with c.node(le["id"]):
            if glyph == "arrow":
                arrow(lx, FY+20, lx+60, FY+20); gx = lx + 68
            elif glyph == "arrow-dashed-6-4":
                arrow(lx, FY+20, lx+60, FY+20, FAIL, "6 4"); gx = lx + 68
            elif glyph == "arrow-dashed-4-4":
                arrow(lx, FY+20, lx+60, FY+20, MUTED, "4 4"); gx = lx + 68
            elif glyph == "gate-diamond":
                gate(lx+18, FY+20); gx = lx + 44
            elif glyph == "lock":
                lock(lx+9, FY+22, label); gx = None
            elif glyph == "bracket":
                c.raw(f'<path d="M{lx+14},{FY+8} H{lx} V{FY+32} H{lx+14}" fill="none" stroke="{FAM["unify"][1]}" stroke-width="2.5"/>'); gx = lx + 22
            elif glyph == "box-dashed-5-4":
                rect(lx, FY+10, 34, 18, BG, INK, 3, dash="5 4"); gx = lx + 42
            elif glyph == "swatch":
                fam = le["family"]
                c.raw(f'<rect x="{lx}" y="{FY+10}" width="18" height="18" rx="3" fill="{FAM[fam][0]}" stroke="{FAM[fam][1]}"/>'); gx = lx + 24
            else:
                raise SystemExit(f"unknown legend glyph {glyph!r}")
            if gx is not None:
                text(gx, FY+24, label, 11, INK)
                lx = gx + text_width(label, 11, False) + 26
            else:
                lx = lx + 23 + text_width(label, 10.5, True) + 26
    assert lx <= W - 40, f"legend overflows the canvas ({lx})"
    text(52, FY+52, lg["note"], 11.5, MUTED, italic=True)

H = FY + 70 + 30
c.body[0] = c.body[0].replace('height="{H}"', f'height="{H}"')
svg = c.render(width=W, height=H, diagram_id=DIAGRAM, title=D["title"], desc=D["desc"], first_sec="Canvas background")

path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name(D["svg"])
write_svg(svg, path, D["svg"])
