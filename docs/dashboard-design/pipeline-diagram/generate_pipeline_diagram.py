#!/usr/bin/env python3
"""Generate the AgentDecompile recovery-pipeline diagram as a Figma-importable SVG.

Design rules (see chat): left->right = dependency order; vertical stacking = concurrency;
five colour families; five concurrent lanes (A–E); every stage card answers try / how / in->out / gate; locks mark shared-state
serialisation points; dashed = failover; ladders = fallback stacks.
No product, binary or project names anywhere.
"""
from __future__ import annotations
import html

W, H = 4400, 3110  # Revised contracts; preserve distributed-compute lane E.
out: list[str] = []

# ---- palette (graphite, restrained) ----
BG = "#16181c"; PANEL = "#20232a"; LINE = "#3a3f4a"; INK = "#d8dbe0"; MUTED = "#98a0ad"; STRONG = "#f2f4f7"
FAM = {  # lane families
    "identity": ("#2b4a7a", "#8cbaff"),   # blue
    "recovery": ("#25503e", "#7fd6a4"),   # green
    "unify":    ("#5a4420", "#f0c060"),   # amber
    "runtime":  ("#1f4d4f", "#67d3d0"),   # teal
    "verify":   ("#452a5a", "#c9a4f0"),   # purple
    "xcut":     ("#2c2f36", "#b0b6c2"),   # gray
}
GATE = "#f0c060"; LOCK = "#ef968b"; FAIL = "#ef968b"; OK = "#7fd6a4"

def esc(s: str) -> str: return html.escape(s, quote=True)

def rect(x, y, w, h, fill, stroke=LINE, rx=4, sw=1.2, dash=None, opacity=1):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d} opacity="{opacity}"/>')

def text(x, y, s, size=13, fill=INK, weight="normal", anchor="start", mono=False, italic=False):
    fam = "ui-monospace, Consolas, monospace" if mono else "Inter, 'Segoe UI', system-ui, sans-serif"
    st = ' font-style="italic"' if italic else ""
    out.append(f'<text x="{x}" y="{y}" font-family="{fam}" font-size="{size}" fill="{fill}" font-weight="{weight}" text-anchor="{anchor}"{st}>{esc(s)}</text>')

def lines(x, y, items, size=12, fill=INK, lh=None, bullet="", mono=False):
    lh = lh or size + 5
    for i, s in enumerate(items):
        text(x, y + i*lh, (bullet + s) if bullet else s, size, fill, mono=mono)
    return y + len(items)*lh

def head(x, y, dx, dy, color):
    """explicit arrowhead polygon (Figma's SVG import drops <marker>)"""
    import math
    L = math.hypot(dx, dy) or 1.0
    ux, uy = dx / L, dy / L
    px, py = -uy, ux
    bx, by = x - ux * 10, y - uy * 10
    out.append(f'<polygon points="{x:.1f},{y:.1f} {bx+px*4:.1f},{by+py*4:.1f} {bx-px*4:.1f},{by-py*4:.1f}" fill="{color}"/>')

def arrow(x1, y1, x2, y2, color=MUTED, dash=None, width=2, label=None, lcol=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    out.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{width}"{d}/>')
    head(x2, y2, x2 - x1, y2 - y1, color)
    if label:
        mx, my = (x1+x2)/2, (y1+y2)/2 - 6
        text(mx, my, label, 11, lcol or color, anchor="middle", italic=True)

def elbow(x1, y1, x2, y2, color=MUTED, dash=None, width=2):
    """orthogonal path: horizontal then vertical then horizontal"""
    d = f' stroke-dasharray="{dash}"' if dash else ""
    mx = (x1 + x2) / 2
    out.append(f'<path d="M{x1},{y1} H{mx} V{y2} H{x2}" fill="none" stroke="{color}" stroke-width="{width}"{d}/>')
    head(x2, y2, x2 - mx, 0, color)

def gate(x, y, label, sub=None):
    """diamond gate marker"""
    s = 18
    out.append(f'<polygon points="{x},{y-s} {x+s},{y} {x},{y+s} {x-s},{y}" fill="{BG}" stroke="{GATE}" stroke-width="2"/>')
    text(x, y+4, "G", 11, GATE, "bold", "middle")
    text(x, y+s+14, label, 10.5, GATE, "bold", "middle")
    if sub: text(x, y+s+27, sub, 10, MUTED, anchor="middle", italic=True)

def lock(x, y, label):
    out.append(f'<rect x="{x-9}" y="{y-6}" width="18" height="14" rx="2" fill="{LOCK}" opacity="0.9"/>')
    out.append(f'<path d="M{x-5},{y-6} V{y-10} A5,5 0 0 1 {x+5},{y-10} V{y-6}" fill="none" stroke="{LOCK}" stroke-width="2.2"/>')
    text(x+14, y+4, label, 10.5, LOCK, "bold")

def card(x, y, w, h, fam, num, title, tryline, how, io, gatetxt=None, tag=None):
    fill, accent = FAM[fam]
    rect(x, y, w, h, PANEL, LINE, 6)
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="30" rx="6" fill="{fill}"/>')
    out.append(f'<rect x="{x}" y="{y+22}" width="{w}" height="8" fill="{fill}"/>')
    if num: text(x+10, y+20, num, 13, STRONG, "bold")
    text(x + (44 if num else 10), y+20, title, 13.5, STRONG, "bold")
    if tag: text(x+w-10, y+37, tag, 9.5, accent, "bold", "end")
    yy = y + 48
    text(x+10, yy, "Trying to:", 10.5, accent, "bold"); yy += 15
    yy = lines(x+10, yy, tryline, 11.5, INK, 15)
    yy += 4
    text(x+10, yy, "How:", 10.5, accent, "bold"); yy += 15
    yy = lines(x+10, yy, how, 11, INK, 14.5, bullet="• ")
    yy += 4
    text(x+10, yy, "In → out:", 10.5, accent, "bold"); yy += 15
    yy = lines(x+10, yy, io, 11, MUTED, 14.5)
    if gatetxt:
        yy += 4
        text(x+10, yy, "Gate: ", 10.5, GATE, "bold")
        text(x+46, yy, gatetxt, 11, GATE)
    return yy

def lane_header(x, y, w, fam, title, sub):
    fill, accent = FAM[fam]
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="34" rx="4" fill="{fill}" opacity="0.85"/>')
    text(x+12, y+22, title, 14, STRONG, "bold")
    text(x+w-12, y+22, sub, 11.5, accent, anchor="end", italic=True)

def concurrency_bracket(x, y1, y2, label):
    out.append(f'<path d="M{x+14},{y1} H{x} V{y2} H{x+14}" fill="none" stroke="{FAM["unify"][1]}" stroke-width="2.5"/>')
    # rotated label
    out.append(f'<text transform="translate({x-8},{(y1+y2)/2}) rotate(-90)" font-family="Inter, system-ui, sans-serif" font-size="12.5" font-weight="bold" fill="{FAM["unify"][1]}" text-anchor="middle">{esc(label)}</text>')

# ================================================================== canvas
out.append('<!--SEC:Canvas background-->')
out.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
out.append(f'''<defs>
</defs>''')
rect(0, 0, W, H, BG, BG, 0, 0)

out.append('<!--SEC:Header-->')
# ---- header ----
text(40, 52, "AgentDecompile — the recovery pipeline, end to end", 30, STRONG, "bold")
text(40, 84, "Reading order: named stages retain prerequisites; evidence feeds back and verification starts early. "
             "Every card answers: what we're trying to do · how · what goes in and comes out · what gates it.", 14, MUTED)
rect(2700, 22, 1660, 96, PANEL, FAM["unify"][1], 6)
text(2712, 44, "HOW TO READ THIS IN 20 SECONDS", 12, FAM["unify"][1], "bold")
lines(2712, 64, ["1. Follow prerequisites; identity/calibration iterate and parity runs continuously.",
                  "2. Lanes may overlap within ownership, resource and snapshot-dependency limits.",
                  "3. Try applicable lookups; exports state capabilities, uncertainty and evidence."], 11.5, INK, 16)
text(40, 108, "Design target: recover from the best evidence, reuse only what transfers, verify at the level of use — "
              "packs, generated bindings, headers and readiness reports with explicit capability limits.", 14, FAM["unify"][1], italic=True)
text(40, 128, "Runs on a laptop; scales by concurrency, then by donated idle compute and free cloud nodes; task-specific budgets and isolated storage probes; complete prepared inputs enable independent continuation; see execution-contracts companion.", 12.5, MUTED, italic=True)

out.append('<!--SEC:Row 0 - intake and the 8-stage ladder-->')
# ================================================================== ROW 0: intake + 8 stages
Y0 = 140
lane_header(40, Y0, W-80, "recovery", "MAIN PIPELINE — compatible reuse · validated reconstruction · independent claim gates",
            "0 + eight named stages · feedback allowed · reuse valid unchanged receipts")

CW, CH, GAP = 400, 380, 34
cy = Y0 + 50
cx = 40

# Intake / reconcile (priority-zero)
card(cx, cy, CW, CH, "xcut", "0", "Open · add · resume (priority-zero)",
     ["Start from the actual project, never a setup ritual:",
      "open, add or resume admits only missing eligible work;",
      "pause/resume controls admission — no Start ritual."],
     ["reconcile bindings; reuse dependency-valid receipts",
      "gate writes; reads use stable versioned snapshots",
      "the one control is pause/resume (+ scope), never start",
      "checkpoint-trusting; repair only on detected breakage:",
      "  NULL content_sha256 / mixed basis_hash → receipted",
      "  backfill, never auto-run",
      "revisit affected evidence only; no blanket reanalysis",
      "reopen reuses valid work; changed evidence re-keys work"],
     ["in: .gpr / repo / binaries / prior receipts",
      "out: one active project, known state, no duplicate work"],
     gatetxt="mutation-admission only (real owner state)")
arrow(cx+CW, cy+CH/2, cx+CW+GAP, cy+CH/2)
cx += CW + GAP

card(cx, cy, CW, CH, "identity", "1", "Identity",
     ["Decide which functions/entities across builds are",
      "logical entity, implementation variant and instance;",
      "similarity does not prove interchangeable behavior."],
     ["extract facts once; short-circuit identical images",
      "cheap-first cascade: symbols/provenance → exact &",
      "  reloc-normalized hashes → rare refs / C++ meta →",
      "  neighborhood → CFG/SPP → BSim → ABI → optional",
      "  BinDiff/BinExport → optional emulation on residue",
      "require uniqueness + margin; keep ambiguity;",
      "  withdraw bad seeds + unsupported descendants"],
     ["in: analyzed programs, debug info, formats",
      "out: entity / variant / instance + evidence lineage"],
     gatetxt="candidate ≠ acceptance", tag="∥ extraction + indexing run in parallel")
arrow(cx+CW, cy+CH/2, cx+CW+GAP, cy+CH/2)
cx += CW + GAP

card(cx, cy, CW, CH, "recovery", "2", "Incremental calibration",
     ["Establish minimum platform facts, then refine",
      "compiler, ABI and layout hypotheses with",
      "identity and function evidence; version each input."],
     ["compiler/linker + headers/libs + macros + FP mode",
      "scope: build / library / TU / function overrides",
      "group fragments into TUs/LTCG as required",
      "probe legacy switches; record scoped dependencies"],
     ["in: identified builds + toolchain evidence",
      "out: calibration record (part of the basis)"])
arrow(cx+CW, cy+CH/2, cx+CW+GAP, cy+CH/2)
cx += CW + GAP

card(cx, cy, CW, CH, "recovery", "3", "Validated linkable regions",
     ["Reconstruct objects and placement from the image;",
      "keep uncertain boundaries in larger regions;",
      "prove reconstruction before scaling source work."],
     ["bytes + fixups + refs + data + unwind metadata",
      "architecture-specific objects / external assembly",
      "extract → emit → place → compare original bytes",
      "then prove a compiled replacement actually contributes"],
     ["in: calibration + donor build",
      "out: validated region scaffold; floor ≠ recovered C"],
     gatetxt="round trip + independent linked-image oracle")
arrow(cx+CW, cy+CH/2, cx+CW+GAP, cy+CH/2)
cx += CW + GAP

card(cx, cy, CW, CH, "recovery", "4", "C/C++ candidates",
     ["Produce readable candidates; preserve the floor",
      "until replacement acceptance passes."],
     ["recovery unit ≠ compilation unit ≠ comparison unit",
      "compile pass → candidate (real_c is compile-only)",
      "fail → deterministic helpers (sanitizer/preparse) →",
      "  retry → ONE bounded LLM cleanup → retry → keep asm",
      "never repeat valid unchanged work",
      "repair explains preserved machine behavior"],
     ["in: scaffold + decompiler output",
      "out: compiled candidates + scoped compile receipts"],
     gatetxt="compile admits candidate, not replacement", tag="isolated mutable outputs / PDB / Wine state")
arrow(cx+CW, cy+CH/2, cx+CW+GAP, cy+CH/2)
cx += CW + GAP

# failover loop annotation under stage 4
fx = cx - CW - GAP
out.append(f'<path d="M{fx+300},{cy+CH} V{cy+CH+26} H{fx+80} V{cy+CH}" fill="none" stroke="{FAIL}" stroke-width="2" stroke-dasharray="6 4"/>'); head(fx+80, cy+CH, 0, -1, FAIL)
text(fx+190, cy+CH+42, "compile fails → helpers → bounded LLM → retry (dashed = failover, never blocks siblings)", 10.5, FAIL, anchor="middle", italic=True)

card(cx, cy, CW, CH, "recovery", "5", "Propagation (cross-place)",
     ["Reuse a donor candidate only for compatible",
      "recipient implementation variants;",
      "each recipient earns its own acceptance."],
     ["compile + variant/ABI/layout compatibility gate",
      "then byte-exact verify → permuter → LLM last",
      "a logical_id bind alone NEVER authorizes copying",
      "ABI-sensitive types re-validated per recipient",
      "field-level knowledge fusion runs alongside (lane A)"],
     ["in: compile receipts + identity table",
      "out: recipient candidates; separate verification"],
     gatetxt="candidate distribution ≠ accepted source", tag="the cross-match tier")
arrow(cx+CW, cy+CH/2, cx+CW+GAP, cy+CH/2)
gate(cx-GAP/2, cy+CH/2 - 60, "candidate", "compile + compatibility")
cx += CW + GAP

card(cx, cy, CW, CH, "recovery", "6", "Targeted AI (leftovers only)",
     ["Spend model effort ONLY on what deterministic",
      "methods left behind — leaves before callers."],
     ["residue queue, tagged with WHY AI was needed",
      "diagnose behavior/types → ABI → context → codegen",
      "LLM output is a candidate — never a trusted edge",
      "ReAgent checker; record exact proposals + bounds"],
     ["in: residue after 4–5",
      "out: candidate C for review + provenance"],
     gatetxt="candidate only")
arrow(cx+CW, cy+CH/2, cx+CW+GAP, cy+CH/2)
cx += CW + GAP

card(cx, cy, CW, CH, "verify", "7", "Continuous parity",
     ["Compare emitted code/data against validated",
      "targets and independently against linked bytes."],
     ["objdiff local + linked-region checks (LTCG aware)",
      "reccmp: supported MSVC / PDB diagnostics",
      "compile / ABI / tested behavior / local / linked",
      "a function-level zero is NOT whole-image proof"],
     ["in: emitted regions + validated original references",
      "out: separate facts with mapping, bounds + evidence"],
     gatetxt="local zero ≠ full-image or behavior proof")
arrow(cx+CW, cy+CH/2, cx+CW+GAP, cy+CH/2)
cx += CW + GAP

card(cx, cy, CW, CH, "verify", "8", "Whole-image byte identity",
     ["The terminal goal: relink into a file whose",
      "whole-file hash EQUALS the shipped binary."],
     ["early stage-3 round trips; fresh terminal compilation",
      "reproduce section order, padding, headers, IAT, relocs",
      "prove replacement use → whole-file byte/hash check",
      "two variants measured separately: byte-accurate+floor",
      "  vs max-C; never borrow a receipt between them",
      "reconstruction ≠ original-style rebuild; record method"],
     ["in: scoped parity + contribution map + layout recipe",
      "out: rebuilt image + whole-file hash receipt"],
     gatetxt="whole-file hash equality", tag="terminal")

# Feedback is distinct from the forward prerequisite arrows.
arrow(1080, cy+CH+12, 674, cy+CH+12, FAM["identity"][1], "4 4")
text(860, cy+CH+28, "1 ↔ 2: refine scoped hypotheses", 11, FAM["identity"][1], anchor="middle")
arrow(3200, cy+CH+12, 1560, cy+CH+12, FAM["verify"][1], "4 4")
text(2880, cy+CH+29, "7–8 verify early scaffold and candidates", 11, FAM["verify"][1], anchor="middle")

out.append('<!--SEC:Row 1 - concurrent lanes-->')
# ================================================================== ROW 1: concurrent lanes
Y1 = cy + CH + 70
_bracket_at = len(out)

LX, LW = 60, W - 100
LCH, LG = 216, 14

def lane(y, fam, title, sub, cards_, connects=None, outputs=None, lch=None):
    lch = lch or LCH
    lane_header(LX, y, LW, fam, title, sub)
    if connects:
        out.append(f'<rect x="{LX+LW-10-len(connects)*6.6}" y="{y-16}" width="{len(connects)*6.6+10}" height="18" rx="3" fill="{BG}" stroke="{FAM[fam][1]}"/>')
        text(LX+LW-5, y-3, connects, 10.5, FAM[fam][1], "bold", "end")
    n = len(cards_)
    lcw = min(500, (LW - (n-1)*LG) / n)
    x = LX
    yy = y + 42
    for c in cards_:
        num, ttl, tr, how, io, gt, tag = c
        card(x, yy, lcw, lch, fam, num, ttl, tr, how, io, gt, tag)
        x += lcw + LG
    rem = LX + LW - x
    if outputs and rem > 320:
        fill, accent = FAM[fam]
        rect(x, yy, rem, lch, BG, accent, 6, dash="5 4")
        text(x+14, yy+24, "OUTPUTS  →  who consumes them", 12, accent, "bold")
        lines(x+14, yy+48, outputs, 11.5, INK, 17, bullet="→ ")
    return y + 42 + lch + 16

y = Y1
# Lane A — knowledge fusion
y = lane(y, "unify", "LANE A · Knowledge fusion — bidirectional, per field",
         "labels · comments · structs/types · debug-info names flow between every build sharing a logical id; strongest source per field wins; a build donates a FIELD, never everything",
         connects="consumes stage 1 identity · runs beside stages 4–5 · feeds every sibling build", cards_=[
          ("", "Name precedence (per field)", ["Keep the strongest name for every field,", "never let a placeholder win."],
           ["human annotation → debug info / STABS →", "  authentic symbols → analysis names → placeholders", "provenance + rejected alternatives retained"],
           ["in: all builds' names", "out: merged names with origin"], None, "field-level"),
          ("", "Types & layouts", ["Merge struct/type knowledge only where", "compatibility gates allow."],
           ["types/layouts keep their own gates (never auto-copied)", "platform-gated donors: (arch, bits, endian, compiler)", "per-build layouts; unknown spans opaque; no scaling"],
           ["in: per-build type rows", "out: logical structs + field correspondence"], "compatibility gate", None),
          ("", "Comments · bookmarks · evidence", ["Nothing authored is lost; conflicts stay visible."],
           ["per-field precedence merge, never wholesale", "conflicts and human edits preserved", "receipt per merged field"],
           ["in: annotations", "out: merged annotations + conflicts"], None, None),
          ("", "Runs alongside recovery", ["Fusion never waits for source recovery", "and never blocks it."],
           ["overlaps when transactions don't collide", "serialized only at the shared corpus mutation point", "resource-aware admission (measured memory/swap)"],
           ["", ""], None, "concurrent"),
         ], outputs=["merged names / types / comments PER FIELD, each with origin and rejected alternatives",
                     "consumed by stage 5 placement (type-compatibility gate) and by the ABI + struct blocks of the pack",
                     "surfaces in the readiness report as which build donated which field",
                     "never overwrites a stronger field; conflicts stay visible for review"])

# Lane B — cross-build entity unification & export
y = lane(y, "unify", "LANE B · Cross-build entity unification & export — every entity, not just functions",
         "portable signatures · entity catalog · data-root locator families with fallbacks · divergence · codecaves · ABI — feeds the runtime pack",
         connects="consumes stages 1–2 (+ raw images) · feeds lane C and the export bundle", cards_=[
          ("", "Portable signatures (identity ≠ locator)", ["Discover supported entities across related builds;", "record absent, ambiguous and unsupported outcomes."],
           ["identity evidence cascade ≠ runtime locator search", "runtime LOCATOR family: reloc-masked window →", "  anchor-relative (import/export/string) → verify hash", "corpus-computed uniqueness + margin shipped in pack", "library/CRT excluded; identical bodies → anchors"],
           ["in: raw image + decode + reloc table", "out: logical_signature per entity + coverage"], None, "deterministic"),
          ("", "Entity catalog", ["Everything a mod could want, unified:"],
           ["functions · patch points · immediates · call sites", "globals · singletons · structs & fields · vtables · RTTI", "strings · tables · enums · imports/exports · dispatch", "TLS · unwind · sections · resources · integrity checks"],
           ["in: analysis + formats", "out: entities[] with kind, shape, locators"], None, "30 kinds (pack enum)"),
          ("", "Data-root locator families", ["Known build: identity → RVA → live check.", "Unknown build: applicable discovery + refusal."],
           ["symbol → xref-from-identified-function → anchor-rel", "  → masked adjacency → pointer chain → vtable/RTTI", "  known-build RVA is preferred; portable:false", "resolver: verify · memoize per build hash · report", "  member · REFUSE, never zero"],
           ["in: entities + xrefs", "out: per-root recipes + per-build coverage"], "verify before trust", None),
          ("", "Divergence (3-way, never forced)", ["When the surrounding logic is too different,", "SAY so and SHOW it — never fake a match."],
           ["CFG delta + neighborhood symmetric difference", "integer components, rational thresholds (no floats)", "1↔1 · split-or-inlined · diverged", "review lane shows why; nothing propagates silently"],
           ["in: cross-build pairs", "out: relation + class + evidence"], None, None),
          ("", "Codecaves & ABI (Lua-ready)", ["Export what injection needs, portable:", "caves as plan templates, ABI as data."],
           ["cave = anchor-sig + offset + capacity REQUIREMENT +", "  relocation rules + originals + restoration + claim", "ABI: convention · this-kind · per-arg storage · sret", "allocation policy + lifetime checks; refusal supported"],
           ["in: entities + validation rules", "out: caves[] + abi blocks in pack v2"], "exported plan ≠ live detour permission", None),
          ("", "Generic core · adapters", ["No product ever in the core."],
           ["L1 core: any PE/ELF/Mach-O/XBE — masks, CFG, caves", "L2 arch adapter: detour width, relocs, reach", "L3 engine adapter + build profile: script API, this-kind", "names live in external data packs only", "pack.json + sha256 in the basis; missing pack →", "  missing_adapter, never a default"],
           ["", ""], None, "3 layers"),
         ], outputs=["logical_signature per entity + per-build coverage · entities[] catalog (30 kinds, pack enum)",
                     "data-root recipes with ordered fallbacks · divergence class per pair · caves[] + ABI blocks",
                     "all of it lands in hookpack v2 → consumed by lane C (runtime) and the export bundle",
                     "generic core + adapters: a new engine adds an L3 data pack, never core code"], lch=248)

# Lane C — runtime reuse & learn-the-build
y = lane(y, "runtime", "LANE C · Runtime reuse & learn-the-build — branches after identity/ABI evidence, before whole-image recovery",
         "calling original code never counts as recovered source; observations feed back as evidence with provenance",
         connects="branches after stages 1–2 evidence · consumes lane B's pack · feeds evidence back into stage 1", cards_=[
          ("", "Pack → resolve", ["Verify build identity and live evidence before", "authorizing each requested runtime operation."],
           ["try members in order; verify each; memoize by image hash", "known: recorded RVA first → expected live bytes", "unknown: bounded discovery; report uncertainty"],
           ["in: hookpack v2 + live image", "out: located/readable/callable/detourable/writable"], "verify or refuse", None),
          ("", "Preflight → controlled call/install", ["Never write into a process blind."],
           ["capacity + originals + page protection checked live", "tested install/remove + safe trampoline reclamation", "ABI / object lifetime / thread / policy / owner checked", "byte journal rollback ≠ undo of executed side effects"],
           ["in: resolved sites", "out: installed hooks / typed calls"], "quiescence + claim", None),
          ("", "Observe → evidence", ["Turn runtime behavior into corpus evidence."],
           ["traces: calls, args, returns, field changes", "provenance-bearing; refines names/types/behavior", "never promotes source parity"],
           ["in: live behavior", "out: observations with provenance"], None, None),
          ("", "Learn the build", ["Each new build contributes provisional evidence;", "contradictions may lower accepted coverage."],
           ["export per-member resolution results as a build report", "corpus ingests runtime_claim rows — never identity;", "  bind_identities promotes or rejects (receipt + delete)", "residue re-attacked offline (BSim, emulation)"],
           ["in: build report", "out: accepted/rejected evidence; updated coverage"], None, "records uncertainty"),
         ], outputs=["resolved sites per build + WHICH ladder member resolved each (feeds coverage + readiness)",
                     "observations → runtime_claim + observed_status; promotion only through bind_identities",
                     "build reports → provisional claims → independent acceptance or named unresolved outcomes",
                     "never promotes source parity; never counts original bytes as recovered C"])

# Lane D — verification & determinism
y = lane(y, "verify", "LANE D · Verification & determinism — same inputs → byte-identical outputs, under a declared basis",
         "replay recorded proposals and observations under a versioned basis; discovery itself need not be deterministic",
         connects="wraps every stage and lane · gates every export", cards_=[
          ("", "Determinism basis", ["Make 'same result' meaningful."],
           ["decoder/analyzer revision + option set + cspec id", "algorithm / masking / threshold versions", "toolchain identity per build; filler set; seeds", "data-pack hashes; per-binary basis_hash", "refuse on unknown / empty / mixed basis", "corpus hash only for corpus-dependent work"],
           ["in: environment", "out: basis object in every pack"], None, "recorded"),
          ("", "Two gates", ["Prove reproducibility, don't assume it."],
           ["export byte-diff: export twice → identical bytes", "cascade harness: three layouts (canonical · shuffled", "  rows + shuffled binary order · + VACUUM/ANALYZE)", "  + key-stability run → identity, match (incl. id),", "  logical_function, recovery_family equal as sorted row-sets"],
           ["in: store", "out: pass / first differing key"], "both must pass", None),
          ("", "Ordering discipline", ["No hidden order can reach a persisted value."],
           ["every SELECT feeding a decision has a total ORDER BY", "every 'best/first' pick has a total tie-break", "sets/dicts sorted before hashing or serializing", "floats rounded before persistence"],
           ["", ""], None, None),
          ("", "Receipts & re-baseline", ["Change the basis deliberately, never silently."],
           ["receipts hash relevant dependencies + snapshot", "changed input → invalidate affected descendants", "acceptance rejects stale versions; old packs readable"],
           ["", ""], None, None),
         ], outputs=["the basis object stamped into every pack, header, report and receipt",
                     "two pass/fail gates in CI: export byte-diff and the cascade harness",
                     "content-addressed receipts → identical-basis re-runs are cache hits",
                     "basis change → deliberate re-baseline with a recorded supersession, never silent drift"], lch=248)

# Lane E — distributed compute (agentdecompile_grid)
y = lane(y, "xcut", "LANE E · Distributed compute (agentdecompile_grid) — laptop → concurrency → donated idle compute and free cloud nodes",
         "content-addressed objects · per-partition logs · every result a proposal · capability by canary, never by role · SQLite as a materialized view",
         connects="wraps every stage and lane · one-command join · fleet of free cloud nodes", cards_=[
          ("", "Objects & logs", ["Working state supports independent replicas:", "content-addressed, log-structured, network-capable."],
           ["sha256 objects, write-once (If-None-Match / atomic rename)", "per-partition append-only logs of signed, chained records", "heads = one CAS pointer per partition; rebuilt by chain scan", "adapters: local · S3-compatible · static mirror · peer HTTP", "compaction: signed checkpoints; peers prune below them"],
           ["in: inputs, sources, objects, receipts", "out: immutable objects + verifiable partition chains"], "write-once; chain verifies offline", "substrate"),
          ("", "Tasks & frontier", ["Jobs bounded and addressable; resume where inputs exist;", "result exists ≠ independently accepted claim."],
           ["task_id = sha256(kind, version, inputs, params, basis projection)", "frontier from log; admission checks live resources separately", "expired lease fences publication; uncertain resources quarantine", "persistent input-scoped retry budget; deadline ≠ termination", "a basis field change re-keys only the kinds that consume it"],
           ["in: partition chain + checkpoint index", "out: offered tasks · result objects · timeout records"], "basis projection admitted", "never awaited"),
          ("", "Join (one command)", ["Any machine, one verb: laptop, donated idle box,", "free cloud node, browser tab."],
           ["attach-first: find the running local agent, never a second start", "canaries prove capability: python · parity · toolchain · analyzer", "capability decides lanes and fetches — a role never does", "roles decide only mirrors + who signs invites / verifies / applies", "outbound HTTPS only; no inbound port; --idle-only, --cores N"],
           ["in: invite URL + what the node can prove", "out: lanes offered by canary; inputs fetched by task"], "canary hash = pinned value", "capability-only"),
          ("", "Verify (every result a proposal)", ["Trust the hash, never the key — fleet nodes included."],
           ["acceptance requires independent evidence roots, not just keys", "recompute or hash-lookup; byte-exact = recompile + parity", "no quorum, no credit, no reputation; a liar wastes ≤ 4 verifies", "donated .obj / .bin never evidence (byte-emitter refuted)", "verification ordered before generation (no livelock)"],
           ["in: proposals from any key", "out: result-verified / result-refuted records"], "independent evidence lineage", "H8"),
          ("", "Views (SQLite as a materialized view)", ["The corpus store and the similarity index are replays of", "verified records: deletable, rebuildable, never locked by work."],
           ["one applier per view; bounded transactions; ack after commit", "identity / logical / match / knowledge / receipts from deltas", "view-stale is a named state with an age (H11), never a stall", "no worker ever opens a view for writing (H1 by construction)", "adgrid view materialize rebuilds from record 1"],
           ["in: result-verified records", "out: grid_* tables · similarity index · receipts"], "materialize twice → identical dump", "H1 / H11"),
          ("", "Fleet (free cloud nodes)", ["The operator never depends on volunteers: rented", "free-tier nodes join with the same command in cloud-init."],
           ["adgrid fleet up / down / status / replace; manifest as objects", "providers: manual · ssh · declared cloud adapters", "lane placement by canary, never by tier or role", "host failover needs independent replica + capable worker", "host loss: continue only with complete surviving input closure"],
           ["in: provider credentials via the secret path; an invite", "out: nodes that joined; fleet manifest objects"], "user-data = the join command only", "conditional host failover"),
         ], outputs=["one package (CLI adgrid) reusable for any CPU/IO-heavy work; the pipeline's lanes are adapters over it",
                     "planned grid contracts; implementation status belongs to delivery evidence, not this design diagram",
                     "every stage runs as grid tasks: compile / parity / decompile / cascade / export lanes, each a proposal",
                     "timeouts record attempt outcomes, not termination; resource release requires evidence; independent acceptance only"], lch=248)

_tail = out[_bracket_at:]; del out[_bracket_at:]
concurrency_bracket(30, Y1, y - 16, "RUNS CONCURRENTLY WITH STAGES 1–8 (where ownership permits)")
out.extend(_tail)
out.append('<!--SEC:Row 2 - exhaustive resolution ladders-->')
# ================================================================== ROW 2: ladders + locks + entities + export
Y2 = y + 40
text(40, Y2 + 22, "BOUNDED RESOLUTION — try applicable methods; stop with absent / inlined-only / ambiguous / unsupported / insufficient evidence / budget exhausted.", 15, STRONG, "bold")

LDX = 40; LDW = 400; LDH = 470; LDG = 14
def ladder(x, y, fam, title, steps, final):
    fill, accent = FAM[fam]
    rect(x, y, LDW, LDH, PANEL, LINE, 6)
    out.append(f'<rect x="{x}" y="{y}" width="{LDW}" height="30" rx="6" fill="{fill}"/>')
    out.append(f'<rect x="{x}" y="{y+22}" width="{LDW}" height="8" fill="{fill}"/>')
    text(x+10, y+20, title, 13, STRONG, "bold")
    yy = y + 46
    for i, s in enumerate(steps):
        out.append(f'<circle cx="{x+18}" cy="{yy-4}" r="9" fill="{fill}" stroke="{accent}" stroke-width="1.2"/>')
        text(x+18, yy, str(i+1), 10, STRONG, "bold", "middle")
        text(x+34, yy, s, 11, INK)
        if i < len(steps)-1:
            out.append(f'<line x1="{x+18}" y1="{yy+6}" x2="{x+18}" y2="{yy+18}" stroke="{FAIL}" stroke-width="1.5" stroke-dasharray="3 3"/>')
        yy += 24
    finals = [final] if isinstance(final, str) else list(final)
    for j, f in enumerate(reversed(finals)):
        text(x+10, y+LDH-14 - j*14, f, 10.5, FAIL, "bold")

ly = Y2 + 40
ladder(LDX, ly, "identity", "A · Function whose bytes changed",
       ["[anchor_rel] anchor-relative (import/export/string)", "[caller_callsite] via a resolved CALLER (decode its call)", "[callee_order] via resolved CALLEES (order match)", "[data_xref] via data it references (inverse xref)",
        "[vtable_slot] via its vtable slot", "[neighbour_position] positional neighbour (order-preserving)", "[structural] structural match (embedded decoder)", "[region · review-only] region match (inlined / split)", "[symbol] symbol/debug info at runtime", "[offline] emulation, BSim on residue", "[annotation] annotation with provenance (a claim, never resolved)"],
       ["then: unresolved (per-member reasons)", "two verified hits disagree → contested"])
ladder(LDX + (LDW+LDG)*1, ly, "unify", "B · Cave missing or too small",
       ["N candidate caves per anchor", "live cave discovery (validated)", "section slack only with expendability proof", "header / stub space only with explicit proof", "executable allocation if process policy permits", "image extension (on-disk patches)"],
       "then: no_placement / unsupported_dynamic_code")
ladder(LDX + (LDW+LDG)*2, ly, "unify", "C · Data root unresolved",
       ["[known build] identity → RVA → live check", "[unknown] symbol / debug info", "[xref_from_function] xref from identified function", "[data_xref] inverse access-instruction scan", "[anchor_rel] relative to import/export/string", "[masked_window] data-section adjacency",
        "[pointer_chain] from a resolved root", "via constructor / initializer", "[vtable_slot] vtable / RTTI-derived", "value-shape probe + independent confirmation"],
       "then: unresolved — never a silent zero")
ladder(LDX + (LDW+LDG)*3, ly, "unify", "D · Struct field moved / stripped build",
       ["name / debug-info donor", "ACCESSOR DECODE → exact per-build offset", "constructor initializer sequence", "field-access fingerprint match", "sibling-field anchoring", "pointer-width hints only; verify actual layout"],
       "then: ambiguous / insufficient_evidence / absent")
ladder(LDX + (LDW+LDG)*4, ly, "unify", "E · VTable / dispatch slots",
       ["RTTI", "constructor vtable-store decode", "slot matched by METHOD identity", "dispatch entries by HANDLER identity"],
       "then: per-slot unresolved")
ladder(LDX + (LDW+LDG)*5, ly, "runtime", "F · Unknown build",
       ["admit in signature-only mode", "run applicable ladders within declared budget", "record every resolution + residue", "ingest as runtime_claim → bind_identities confirms → KNOWN", "residue re-attacked offline"],
       "coverage may regress when collisions are found")

out.append('<!--SEC:Row 2 - locks and failover rules-->')
# locks + failover rule panel
PX = LDX + (LDW+LDG)*6 + 20; PW = W - PX - 40
rect(PX, ly, PW, 200, PANEL, LINE, 6)
text(PX+12, ly+24, "OWNERSHIP IS RESOURCE-SCOPED (eligible independent work overlaps)", 12.5, LOCK, "bold")
lock(PX+22, ly+52, "writes to one Ghidra program's analysis DB")
lock(PX+22, ly+76, "shared corpus mutation / conflict resolution")
lock(PX+22, ly+100, "shared mutable compiler outputs / Wine context (private outputs may overlap)")
lock(PX+22, ly+124, "one scenario bundle: staged tree + saves + Wine + display + ports + harness")
lock(PX+22, ly+148, "short acceptance commit: current basis + generation + independent proof")
text(PX+12, ly+182, "Atomic resource-set admission; measured process-tree budgets and pressure; external owners remain external.", 10.5, MUTED, italic=True)

rect(PX, ly+216, PW, 150, PANEL, FAIL, 6, dash="6 4")
text(PX+12, ly+240, "FAILOVER RULE", 12.5, FAIL, "bold")
lines(PX+12, ly+262, ["The affected branch stops VISIBLY at its real unmet dependency;", "every eligible sibling lane continues.",
                       "Show the named owner/provider failure, last evidence, chosen fallback,", "one retry owner and persistent budget; deterministic negatives require changed basis.",
                       "Deadline ends attempt, not objective; expired ownership does not free resources;", "quarantine uncertain resources; show wake conditions, progress unknown and aging."], 11, INK, 15)

out.append('<!--SEC:Terminal band - what you get-->')
# terminal band: WHAT YOU GET
TY = ly + LDH + 30
lane_header(40, TY, W-80, "unify", "EXPORT TARGET — reusable recovery projects + vanilla-game bindings; capabilities and unknowns explicit",
            "re-run under the same basis → byte-identical bundle")
bx = 40; bw = (W-80 - 6*16)/7; by = TY + 44; bh = 150
for ttl, body in [
  ("hookpack v2", ["every entity kind, locator families,", "per-build coverage, ABI blocks, caves,", "integrity ranges, basis, pack hash"]),
  ("Generated Lua bindings", ["roots by name · typed struct accessors", "table/handle/bitfield/string helpers", "typed call stubs only for ABIs the", "descriptor layer expresses; else refuse", "NO literal address"]),
  ("Per-build C/C++ headers", ["evidenced per-build layouts;", "opaque unknown spans · prototypes with", "conventions + storage · build manifest"]),
  ("Readiness report", ["per entity × build: resolved(member) /", "pinned(member) / degraded(member, reason) /", "ambiguous / unresolved / contested", "observed_status separate · what a mod", "can do here"]),
  ("Divergence report", ["1↔1 · split-or-inlined · diverged", "field-map, slot and table deltas", "between any two builds"]),
  ("Receipts", ["content-addressed, keyed by", "hash(inputs+basis) · every artifact", "identical-basis re-run = cache hit"]),
  ("Source + comparison projects", ["byte-accurate C+floor and max-C", "with manifests", "reccmp reports + independent image receipts"])]:
    rect(bx, by, bw, bh, PANEL, FAM["unify"][1], 6, sw=1.6)
    text(bx+12, by+26, ttl, 14, STRONG, "bold")
    lines(bx+12, by+52, body, 11.5, INK, 17)
    bx += bw + 16

out.append('<!--SEC:Footer - legend and determinism basis-->')
# ================================================================== footer: legend + basis band
FY = TY + 44 + 150 + 24
rect(40, FY, W-80, 70, PANEL, LINE, 6)
text(52, FY+24, "LEGEND", 12.5, STRONG, "bold")
arrow(130, FY+20, 190, FY+20); text(198, FY+24, "data / dependency flow", 11, INK)
arrow(370, FY+20, 430, FY+20, FAIL, "6 4"); text(438, FY+24, "failover / fallback", 11, INK)
gate(560, FY+20, "", None); text(586, FY+24, "gate — must pass (compile receipt, verify, hash)", 11, INK)
lock(920, FY+22, "serialized — one owner");
out.append(f'<path d="M{1130+14},{FY+8} H{1130} V{FY+32} H{1130+14}" fill="none" stroke="{FAM["unify"][1]}" stroke-width="2.5"/>'); text(1152, FY+24, "bracket — eligible independent work may overlap", 11, INK)
for i,(k,lab) in enumerate([("identity","identity"),("recovery","source recovery"),("unify","cross-build unification & export"),("runtime","runtime reuse / learn"),("verify","verification & determinism"),("xcut","intake / cross-cutting")]):
    x = 1520 + i*260
    out.append(f'<rect x="{x}" y="{FY+10}" width="18" height="18" rx="3" fill="{FAM[k][0]}" stroke="{FAM[k][1]}"/>')
    text(x+24, FY+24, lab, 11, INK)
text(52, FY+52, "DESIGN ONLY · future checks NOT RUN. Companions: execution-contracts.svg — evidence/admission; resilience-contracts.svg — prevention, containment, recovery. Replay records observations + dependencies.", 11.5, MUTED, italic=True)

out.append("</svg>")

import pathlib, sys
path = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(__file__).with_name("agentdecompile-recovery-pipeline.svg")
path.write_text("\n".join(out), encoding="utf-8")
print(path, len("\n".join(out)), "bytes")
