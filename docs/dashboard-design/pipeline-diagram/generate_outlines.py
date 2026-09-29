#!/usr/bin/env python3
"""Write the text outlines of the four recovery diagrams from pipeline-model.json.

The outlines are the primary accessible reading form of the diagrams.  Every heading
(and every item that is a node) carries an explicit ``<a id="<node id>"></a>`` anchor so
the GUI and docs can deep-link.  Symbols that carry meaning are spelled out in words.

Run the four diagram generators first: this script also verifies that
  1. every content string in the model appears in the generated SVG (no drift), and
  2. the SVG ``<g id>`` sequence equals the outline's node-anchor sequence
     (same ids, same reading order).
Document authoring only; nothing here exercises AgentDecompile.
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

from diagram_common import HERE, load_model, svg_texts

M = load_model()
FAMILIES = M["families"]
EXTRA_ANCHORS = {"relationships"}

# ------------------------------------------------------------------ words for symbols
PHRASES = [
    ("1↔1", "one-to-one"),
    ("↺ feedback", "feedback"),
    ("↺", "feedback"),
    ("≠", "is not"),
    ("↔", "refines, both ways,"),
    ("∥ ", "in parallel: "),
    ("∥", "in parallel"),
    (" × ", " by "),
    ("≤", "at most"),
    ("OUTPUTS → who consumes them", "OUTPUTS and who consumes them"),
    ("→", "then"),
    (" · ", ", "),
    (" • ", ", "),
]
EN_RANGE = re.compile(r"(?<=\w)–(?=\w)")


def words(s: str) -> str:
    for a, b in PHRASES:
        s = s.replace(a, b)
    s = EN_RANGE.sub(" to ", s)
    s = re.sub(r" {2,}", " ", s).strip()
    return s.replace("*", r"\*")


def joined(lines_: list[str]) -> str:
    return words(" ".join(s.strip() for s in lines_))


def bullets(how: list[str]) -> list[str]:
    """Merge '  '-prefixed continuation lines into the previous bullet."""
    out: list[str] = []
    for s in how:
        if s.startswith("  ") and out:
            out[-1] += " " + s.strip()
        else:
            out.append(s.strip())
    return [words(s) for s in out]


def anchor(node_id: str) -> str:
    return f'<a id="{node_id}"></a>'


def family_text(fam: str) -> str:
    f = FAMILIES[fam]
    return f"{f['legend']} ({f['word']})"


# ------------------------------------------------------------------ naming
def name(n: dict) -> str:
    k = n.get("kind")
    if k == "stage":
        return f"Stage {n['n']}: {n['title']}"
    if k == "gate":
        return f"Gate of stage {n['stage'].split('-')[1]}"
    if k == "gate_marker":
        a, b = (s.split("-")[1] for s in n["between"])
        return f"Gate between stage {a} and stage {b}"
    if k == "lane":
        return f"Lane {n['letter']}"
    if k == "ladder":
        return f"Ladder {n['letter']}: {n['title']}"
    if k == "lock":
        return f"Lock {n['n']}: {n['title']}"
    if k == "contract":
        if "-step-" in n["id"]:
            return f"Step {n['label']}: {n['title']}"
        return f"{n['label']}: {n['title']}"
    if k == "step":
        return f"Step {n['n']}: {n['title']}"
    if k == "milestone":
        return f"{n['n']}: {n['title']}"
    section_names = {"main-pipeline": "Main pipeline", "lanes": "Concurrent lanes A to E",
                     "ladders": "Bounded resolution ladders A to F", "locks": "Ownership locks",
                     "failover-rule": "Failover rule", "export-target": "Export target", "legend": "Legend",
                     "how-to-read": "How to read this in 20 seconds"}
    return section_names.get(n["id"], n["title"])


def link(node_id: str, here: str) -> str:
    n = M.node(node_id)
    target = f"#{node_id}"
    if n["diagram"] != here:
        target = M["diagrams"][n["diagram"]]["outline"] + target
    return f"[{words(name(n))}]({target})"


EDGE_VERB = {"depends_on": "depends on", "feedback": "feeds back to", "failover": "fails over within",
             "gates": "gates", "consumes": "consumes", "feeds": "feeds", "wraps": "wraps",
             "produces": "produces", "consumed_by": "is consumed by", "serialized_by": "is serialized by"}


# ------------------------------------------------------------------ writer
class Doc:
    def __init__(self, diagram: str):
        self.diagram = diagram
        self.lines: list[str] = []
        self.anchors: list[str] = []

    def _mark(self, node_id: str | None) -> str:
        if node_id is None:
            return ""
        self.anchors.append(node_id)
        return anchor(node_id)

    def h(self, level: int, node_id: str | None, title: str) -> None:
        self.lines += ["#" * level + " " + self._mark(node_id) + words(title), ""]

    def p(self, s: str, node_id: str | None = None) -> None:
        self.lines += [self._mark(node_id) + s, ""]

    def li(self, s: str, node_id: str | None = None, indent: int = 0, marker: str = "-") -> None:
        self.lines.append("  " * indent + f"{marker} " + self._mark(node_id) + s)

    def end_list(self) -> None:
        self.lines.append("")


def card_body(d: Doc, cd: dict, gate_id: str | None = None, stage: bool = False) -> None:
    if stage:
        d.li(f"Family: {family_text(cd['family'])}")
    if cd.get("tag"):
        d.li(f"Tag: {words(cd['tag'])}")
    d.li(f"Trying to: {joined(cd['try'])}")
    d.li("How:")
    for b in bullets(cd["how"]):
        d.li(b, indent=1)
    if cd["io"]:
        d.li("In to out:")
        for s in cd["io"]:
            d.li(words(s), indent=1)
    if stage:
        if gate_id:
            d.li(f"Gate: {words(M.node(gate_id)['title'])}", node_id=gate_id)
            for e in M["edges"]:
                if e.get("follows") == gate_id:
                    d.li(words(e["spoken"]), node_id=e["id"])
        else:
            d.li("Gate: none (this stage has no gate)")
    elif cd.get("gate"):
        d.li(f"Gate: {words(cd['gate'])}")
    d.end_list()


def relationships(d: Doc) -> None:
    d.h(2, "relationships", "Relationships")
    d.p("Typed edges from pipeline-model.json that involve this diagram. \"(drawn arrow)\" marks an arrow in "
        "the diagram; \"(inferred)\" marks an edge read from diagram text, followed by whether that text states "
        "it directly or it is an interpretation to review, and the text it is based on.")
    for e in M["edges"]:
        a, b = M.node(e["from"]), M.node(e["to"])
        if d.diagram not in (a["diagram"], b["diagram"]):
            continue
        if e.get("drawn"):
            note = " (drawn arrow)"
        elif e.get("inferred"):
            note = f" (inferred) — {e['inference']}: {words(e['basis'])}"
        else:
            raise SystemExit(f"edge {e['from']} {e['type']} {e['to']} is neither drawn nor marked inferred")
        d.li(f"{link(e['from'], d.diagram)} {EDGE_VERB[e['type']]} {link(e['to'], d.diagram)}{note}")
    d.end_list()


def preamble(d: Doc, header_id: str) -> None:
    dg = M["diagrams"][d.diagram]
    d.lines += ["<!-- Generated by generate_outlines.py from pipeline-model.json; do not edit by hand. -->", ""]
    d.h(1, header_id, M.node(header_id)["title"])
    d.p(f"Text outline of [{dg['svg']}]({dg['svg']}); the primary accessible reading form of that diagram. "
        "Each anchor equals the node id in `pipeline-model.json`, the `<g id>` in the SVG and the object id in "
        f"the `.drawio` file. Symbols that carry meaning are spelled out in words.")
    d.p(f"Summary: {words(dg['desc'])}")


# ------------------------------------------------------------------ overview
def overview() -> Doc:
    d = Doc("agentdecompile-recovery-pipeline")
    hdr = M.node("overview-header")
    preamble(d, "overview-header")
    for k in ("subtitle", "design_target", "scale_note"):
        d.p(words(hdr[k]))

    htr = M.node("how-to-read")
    d.h(2, "how-to-read", name(htr))
    for s in htr["items"]:
        d.lines.append(words(s))
    d.end_list()
    d.p(words(htr["key"]))

    mp = M.node("main-pipeline")
    d.h(2, "main-pipeline", name(mp))
    d.p(f"{words(mp['title'])}. {words(mp['subtitle'])}. Stages run left to right in dependency order.")
    for i in range(9):
        st = M.node(f"stage-{i}")
        d.h(3, st["id"], name(st))
        card_body(d, st, st["gate_id"], stage=True)
        if i == 4:
            g = M.node("gate-4-5")
            d.h(3, g["id"], f"{name(g)}: {g['title']}")
            d.p(f"A gate diamond on the dependency arrow from stage 4 to stage 5. Label: {words(g['title'])}. "
                f"Condition: {words(g['sub'])}.")
        for e in M["edges"]:
            if e.get("follows") == st["id"]:
                a, b = M.node(e["from"]), M.node(e["to"])
                d.h(3, e["id"], f"Feedback arrow from {name(a).split(':')[0].lower()} back to {name(b).split(':')[0].lower()}")
                d.p(words(e["spoken"]))

    ln = M.node("lanes")
    d.h(2, "lanes", name(ln))
    d.p(words(ln["title"]) + ".")
    for letter in "ABCDE":
        lane = M.node(f"lane-{letter}")
        d.h(3, lane["id"], f"Lane {letter}: {lane['title']}")
        d.li(f"Family: {family_text(lane['family'])}")
        d.li(f"Connects: {words(lane['connects'])}")
        d.li(f"Scope: {words(lane['subtitle'])}")
        d.li("Outputs and who consumes them:")
        for s in lane["outputs"]:
            d.li(words(s), indent=1)
        d.end_list()
        for cd in lane["cards"]:
            d.h(4, cd["id"], cd["title"])
            card_body(d, cd)

    ld = M.node("ladders")
    d.h(2, "ladders", name(ld))
    d.p(words(ld["title"]))
    for letter in "ABCDEF":
        lad = M.node(f"ladder-{letter}")
        d.h(3, lad["id"], name(lad))
        d.p(f"Family: {family_text(lad['family'])}. Members are tried in order; the locator kind, when the diagram "
            "shows one, comes first.")
        for mb in lad["members"]:
            if mb["slug"]:
                shown = mb.get("label")
                lead = f"{words(shown)} ({mb['slug']})" if shown else mb["slug"]
                s = f"{lead}: {words(mb['text'])}"
            else:
                s = words(mb["text"])
            d.li(s, node_id=mb["id"], marker=f"{mb['n']}.")
        d.end_list()
        d.p("Terminal outcomes:")
        for s in lad["outcomes"]:
            d.li(words(s))
        d.end_list()

    lk = M.node("locks")
    d.h(2, "locks", name(lk))
    d.p(f"{words(lk['title'])}. Each lock below is a one-owner serialization point.")
    for i in range(1, 6):
        d.li(words(M.node(f"lock-{i}")["title"]), node_id=f"lock-{i}", marker=f"{i}.")
    d.end_list()
    d.p(words(lk["note"]))

    fr = M.node("failover-rule")
    d.h(2, "failover-rule", name(fr))
    d.p(joined(fr["lines"]))

    ex = M.node("export-target")
    d.h(2, "export-target", name(ex))
    d.p(f"{words(ex['title'])}. {words(ex['subtitle'])}.")
    for n in M.nodes_of(d.diagram):
        if n.get("parent") == "export-target":
            d.h(3, n["id"], n["title"])
            d.p(joined(n["lines"]))

    lg = M.node("legend")
    d.h(2, "legend", name(lg))
    glyph_words = {"arrow": "Solid arrow", "arrow-dashed-6-4": "Dashed arrow (dash 6 4)",
                   "arrow-dashed-4-4": "Dashed arrow (dash 4 4)", "gate-diamond": "Diamond marked G",
                   "lock": "Padlock", "bracket": "Bracket", "box-dashed-5-4": "Dashed box (dash 5 4)"}
    for n in M.nodes_of(d.diagram):
        if n.get("parent") != "legend":
            continue
        if n["glyph"] == "swatch":
            g = f"Colour swatch named by the header word {FAMILIES[n['family']]['word']}"
        else:
            g = glyph_words[n["glyph"]]
        d.li(f"{g}: {words(n['title'])}", node_id=n["id"])
    d.end_list()
    d.p(words(lg["note"]))
    relationships(d)
    return d


# ------------------------------------------------------------------ companions
def contract_section(d: Doc, n: dict, level: int = 2) -> None:
    d.h(level, n["id"], name(n))
    for r in n["rows"]:
        d.li(words(r))
    d.end_list()


def companion(diagram: str, header_id: str) -> Doc:
    d = Doc(diagram)
    preamble(d, header_id)
    hdr = M.node(header_id)
    for k in ("subtitle", "status", "tagline"):
        if k in hdr:
            d.p(words(hdr[k]))
    for n in M.nodes_of(diagram):
        k = n["kind"]
        if n["id"] == header_id or n.get("parent") in ("exec-binding", "cap-milestones"):
            continue
        if k == "contract":
            contract_section(d, n)
        elif k == "step":
            d.h(2, n["id"], name(n))
            for r in n["rows"]:
                d.li(words(r))
            d.end_list()
        elif k == "section":
            d.h(2, n["id"], n["title"])
            for ch in M.nodes_of(diagram):
                if ch.get("parent") != n["id"]:
                    continue
                if ch["kind"] == "contract":
                    contract_section(d, ch, 3)
                else:  # milestone
                    d.h(3, ch["id"], name(ch))
                    d.li(f"Status: {words(ch['status'])}")
                    d.li(f"Scope: {joined(ch['body'])}")
                    d.li(joined(ch["proof"]))
                    d.end_list()
        elif k == "note":
            d.p(words(n["title"]), node_id=n["id"])
            if "contract" in n:
                d.p(words(n["contract"]))
        elif k == "example":
            d.h(2, n["id"], n["title"])
            for s in n["lines"]:
                d.p(words(s))
            d.p(f"Status: {words(n['status'])}")
        elif k == "panel":
            d.h(2, n["id"], n["title"])
            d.p(joined(n["lines"]))
        else:
            raise SystemExit(f"no outline renderer for {n['id']} ({k})")
    relationships(d)
    return d


# ------------------------------------------------------------------ verification
SKIP_KEYS = {"id", "diagram", "kind", "family", "parent", "gate_id", "glyph", "stage", "between", "n", "letter"}


def model_strings(obj, out: list[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in SKIP_KEYS or (k == "slug" and "label" in obj):
                continue
            model_strings(v, out)
    elif isinstance(obj, list):
        for v in obj:
            model_strings(v, out)
    elif isinstance(obj, str) and obj:
        out.append(obj)


def model_ids(diagram: str) -> set[str]:
    ids = set()
    for n in M.nodes_of(diagram):
        ids.add(n["id"])
        ids.update(s["id"] for s in n.get("cards", []) + n.get("members", []))
    for e in M["edges"]:
        if e.get("id") and M.node(e["from"])["diagram"] == diagram:
            ids.add(e["id"])
    return ids


def verify(diagram: str, doc: Doc) -> list[str]:
    dg = M["diagrams"][diagram]
    svg = (HERE / dg["svg"]).read_text(encoding="utf-8")
    problems = []
    texts = [t["text"] for t in svg_texts(svg)]
    title = html.unescape(re.search(r"<title[^>]*>(.*?)</title>", svg).group(1))
    desc = html.unescape(re.search(r"<desc[^>]*>(.*?)</desc>", svg, re.S).group(1))
    if title != dg["title"]:
        problems.append(f"<title> differs from the model: {title!r}")
    if desc != dg["desc"]:
        problems.append("<desc> differs from the model")
    strings: list[str] = []
    for n in M.nodes_of(diagram):
        model_strings(n, strings)
    for e in M["edges"]:
        if e.get("drawn") and e.get("label") and M.node(e["from"])["diagram"] == diagram:
            strings.append(e["label"])
    if diagram == "agentdecompile-recovery-pipeline":
        strings += [f["word"] for f in FAMILIES.values()] + [f["legend"] for f in FAMILIES.values()]
    for s in strings:
        if not any(s in t for t in texts):
            problems.append(f"model string not drawn in {dg['svg']}: {s!r}")
    svg_ids = re.findall(r'<g id="([^"]+)">', svg)
    ids = model_ids(diagram)
    if set(svg_ids) != ids:
        problems.append(f"SVG ids vs model: missing {sorted(ids - set(svg_ids))}, extra {sorted(set(svg_ids) - ids)}")
    doc_ids = [a for a in doc.anchors if a not in EXTRA_ANCHORS]
    if doc_ids != svg_ids:
        first = next((i for i, (a, b) in enumerate(zip(doc_ids, svg_ids)) if a != b), min(len(doc_ids), len(svg_ids)))
        problems.append(f"outline anchor order differs from SVG <g id> order at #{first}: "
                        f"{doc_ids[first:first+3]} vs {svg_ids[first:first+3]}")
    return problems


def main() -> int:
    docs = [(overview(), "agentdecompile-recovery-pipeline"),
            (companion("execution-contracts", "exec-header"), "execution-contracts"),
            (companion("resilience-contracts", "resil-header"), "resilience-contracts"),
            (companion("autonomous-capabilities", "cap-header"), "autonomous-capabilities")]
    problems = []
    for doc, diagram in docs:
        problems += verify(diagram, doc)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    for doc, diagram in docs:
        text = "\n".join(doc.lines).rstrip() + "\n"
        path = HERE / M["diagrams"][diagram]["outline"]
        path.write_text(text, encoding="utf-8")
        print(path, len(text.encode("utf-8")), "bytes;", len(doc.anchors), "anchors; verified against", M["diagrams"][diagram]["svg"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
