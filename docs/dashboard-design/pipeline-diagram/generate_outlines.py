#!/usr/bin/env python3
"""Write the text outlines of the four recovery diagrams from pipeline-model.json.

The outlines are the primary accessible reading form of the diagrams.  Every heading
(and every item that is a node) carries an explicit ``<a id="<node id>"></a>`` anchor so
the GUI and docs can deep-link.  Symbols that carry meaning are spelled out in words.
Every node also names its in-app location, ``?node=<id>``, as code text.  It becomes a
link only when an explicit app base is configured (``--app-base PATH`` or the
PIPELINE_OUTLINE_APP_BASE environment variable), for a backend-served rendering.  The base
must be a root-relative path, so no host, port or project parameter is ever emitted, and such
a rendering must be written with ``--out-dir`` so the committed outlines stay link-free.
Stage and lane sections list their catalog verbs (from ``catalog_verbs``), and the two
companion outlines end with the lifecycle crosswalks, marked as interpretations.

Run the four diagram generators first: this script also verifies that
  1. every content string in the model appears in the generated SVG (no drift),
  2. the SVG ``<g id>`` sequence equals the outline's node-anchor sequence
     (same ids, same reading order),
  3. catalog_verbs, lifecycle_states, crosswalks and edge flags reference real nodes and
     states, and each stage and lane section lists exactly the verbs the map gives it.
Document authoring only; nothing here exercises AgentDecompile.
"""
from __future__ import annotations

import argparse
import html
import os
import re
import sys
from pathlib import Path

from diagram_common import HERE, load_model, svg_texts

M = load_model()
FAMILIES = M["families"]
EXTRA_ANCHORS = {"relationships", "crosswalks"}
APP_BASE_ENV = "PIPELINE_OUTLINE_APP_BASE"
APP_BASE_OK = re.compile(r"/(?!/)[A-Za-z0-9._~/-]*")  # root-relative path: no scheme, host, port, query or fragment
APP_BASE: str | None = None

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


def in_app(node_id: str) -> str:
    """The node's in-app location; resolved by the app against the active project."""
    loc = f"?node={node_id}"
    return f"In the app: `{loc}`" if APP_BASE is None else f"In the app: [`{loc}`]({APP_BASE}{loc})"


def with_in_app(s: str, node_id: str) -> str:
    s = s.rstrip()
    return s + (" " if s.endswith((".", ":", ";", "!", "?")) else ". ") + in_app(node_id)


def verbs_line(node_id: str, key: str) -> str:
    """Catalog verbs of a stage (key 'stages') or lane (key 'lanes'), derived from catalog_verbs."""
    quotes, sources = [], []
    for v in M["catalog_verbs"].values():
        if node_id in v[key]:
            if v["quote"] not in quotes:
                quotes.append(v["quote"])
            if v["source"] not in sources:
                sources.append(v["source"])
    if not quotes:
        return "Catalog verbs: unmapped (no recorded mapping)"
    return f"Catalog verbs ({'; '.join(sources)}): " + "; ".join(words(q) for q in quotes)


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
        if node_id is not None and node_id not in EXTRA_ANCHORS:
            self.lines += [in_app(node_id), ""]

    def p(self, s: str, node_id: str | None = None) -> None:
        if node_id is not None:
            s = with_in_app(s, node_id)
        self.lines += [self._mark(node_id) + s, ""]

    def li(self, s: str, node_id: str | None = None, indent: int = 0, marker: str = "-") -> None:
        if node_id is not None:
            s = with_in_app(s, node_id)
        self.lines.append("  " * indent + f"{marker} " + self._mark(node_id) + s)

    def end_list(self) -> None:
        self.lines.append("")


def card_body(d: Doc, cd: dict, gate_id: str | None = None, stage: bool = False) -> None:
    if stage:
        d.li(f"Family: {family_text(cd['family'])}")
        d.li(verbs_line(cd["id"], "stages"))
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


def review_note(x: dict) -> str:
    """The recorded review of an interpretation: the authority that corroborates it, or that none does."""
    r = x.get("review")
    if not r:
        return ""
    if r["verdict"] == "corroborated":
        s = f"; review {r['date']}: corroborated by {r['source']}"
    else:
        s = f"; review {r['date']}: {r['verdict']}"
    return s + (f" ({words(r['note'])})" if r.get("note") else "")


def relationships(d: Doc) -> None:
    d.h(2, "relationships", "Relationships")
    d.p("Typed edges from pipeline-model.json that involve this diagram. \"(drawn arrow)\" marks an arrow in "
        "the diagram, followed by the diagram text that states it when it was first read from text; \"(inferred)\" "
        "marks an edge read from diagram text and not drawn, followed by whether that text states it directly or it "
        "is an interpretation to review, and the text it is based on.")
    for e in M["edges"]:
        a, b = M.node(e["from"]), M.node(e["to"])
        if d.diagram not in (a["diagram"], b["diagram"]):
            continue
        if e.get("drawn"):
            note = " (drawn arrow)" + (f" — {e['inference']}: {words(e['basis'])}" if e.get("basis") else "")
        elif e.get("inferred"):
            note = f" (inferred) — {e['inference']}: {words(e['basis'])}" + review_note(e)
        else:
            raise SystemExit(f"edge {e['from']} {e['type']} {e['to']} is neither drawn nor marked inferred")
        d.li(f"{link(e['from'], d.diagram)} {EDGE_VERB[e['type']]} {link(e['to'], d.diagram)}{note}")
    d.end_list()


def crosswalks(d: Doc) -> None:
    """Lifecycle states read as the design steps of this diagram; interpretations only."""
    items = [c for c in M["crosswalks"] if M.node(c["to"])["diagram"] == d.diagram]
    if not items:
        return
    d.h(2, "crosswalks", "Crosswalks (interpretation)")
    d.p("Each line reads one lifecycle state as the design step it instantiates. These are interpretations of the "
        "design text, not the runtime's state machine: a lifecycle rail shows the backend's states only. Each basis "
        "quotes the task acceptance design, followed by the step text it was matched to.")
    for lc in dict.fromkeys(c["lifecycle"] for c in items):
        ls = M["lifecycle_states"][lc]
        d.p(f"{lc} states (names from `{ls['source']}`)." + (f" {words(ls['note'])}" if ls.get("note") else ""))
        mapped = []
        for c in items:
            if c["lifecycle"] != lc:
                continue
            mapped.append(c["state"])
            d.li(f"State `{c['state']}` is read as {link(c['to'], d.diagram)} (interpretation). "
                 f"Basis: {words(c['basis'])} Matches {words(c['matches'])}."
                 + (f" Review{review_note(c)[len('; review'):]}." if c.get("review") else ""))
        d.end_list()
        unmapped = [s for s in ls["states"] if s not in mapped]
        if unmapped:
            d.p("No crosswalk, because no supporting text was found: " + ", ".join(f"`{s}`" for s in unmapped) + ".")


def preamble(d: Doc, header_id: str) -> None:
    dg = M["diagrams"][d.diagram]
    d.lines += ["<!-- Generated by generate_outlines.py from pipeline-model.json; do not edit by hand. -->", ""]
    d.h(1, header_id, M.node(header_id)["title"])
    d.p(f"Text outline of [{dg['svg']}]({dg['svg']}); the primary accessible reading form of that diagram. "
        "Each anchor equals the node id in `pipeline-model.json`, the `<g id>` in the SVG and the object id in "
        "the `.drawio` file, whose single link per object points back to this anchor. \"In the app\" gives each "
        "node's location in the workbench, which resolves it against the active project. Symbols that carry "
        "meaning are spelled out in words.")
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
        d.li(verbs_line(lane["id"], "lanes"))
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
    crosswalks(d)
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


def verify_model() -> list[str]:
    """Cross-references of the non-node sections: catalog_verbs, lifecycle_states, crosswalks, edge flags."""
    problems = []
    stage_ids = {n["id"] for n in M["nodes"] if n["kind"] == "stage"}
    lane_ids = {n["id"] for n in M["nodes"] if n["kind"] == "lane"}
    for verb, v in M["catalog_verbs"].items():
        if not (set(v) >= {"stages", "lanes", "source", "quote"} and verb and verb in v["quote"]):
            problems.append(f"catalog verb {verb!r}: needs stages, lanes, source and a quote naming the verb")
            continue
        bad = sorted(set(v["stages"]) - stage_ids) + sorted(set(v["lanes"]) - lane_ids)
        if bad:
            problems.append(f"catalog verb {verb!r} maps to unknown stage or lane ids {bad}")
    for c in M["crosswalks"]:
        where = f"crosswalk {c.get('lifecycle')}.{c.get('state')}"
        states = M["lifecycle_states"].get(c.get("lifecycle"), {}).get("states", [])
        if c.get("state") not in states:
            problems.append(f"{where}: state is not in lifecycle_states")
        if c.get("to") not in M.by_id:
            problems.append(f"{where}: unknown step {c.get('to')!r}")
            continue
        if c.get("inference") != "interpretation" or not c.get("basis") or not c.get("source"):
            problems.append(f"{where}: needs inference 'interpretation', a quoted basis and its source")
        n = M.node(c["to"])
        for q in re.findall(r"'([^']+)'", c.get("matches", "")):
            if q != n["title"] and q not in n.get("rows", []):
                problems.append(f"{where}: matched text {q!r} is not in {c['to']}")
    for e in M["edges"]:
        where = f"edge {e['from']} {e['type']} {e['to']}"
        if bool(e.get("drawn")) == bool(e.get("inferred")):
            problems.append(f"{where}: must be exactly one of drawn or inferred")
        if e.get("drawn") and e.get("inference", "stated") != "stated":
            problems.append(f"{where}: only edges stated by diagram text are drawn")
    return problems


def section_lines(doc: Doc, node_id: str) -> list[str]:
    start = next(i for i, s in enumerate(doc.lines) if anchor(node_id) in s)
    end = next((j for j in range(start + 1, len(doc.lines)) if doc.lines[j].startswith("#")), len(doc.lines))
    return doc.lines[start:end]


def verify_verbs(doc: Doc) -> list[str]:
    """Each stage and lane section lists exactly the verbs catalog_verbs maps to it."""
    problems = []
    for n in M.nodes_of(doc.diagram):
        key = {"stage": "stages", "lane": "lanes"}.get(n["kind"])
        if key is None:
            continue
        want = {verb for verb, v in M["catalog_verbs"].items() if n["id"] in v[key]}
        line = next((s for s in section_lines(doc, n["id"]) if s.startswith("- Catalog verbs")), None)
        if line is None:
            problems.append(f"{n['id']}: outline section has no catalog verbs line")
        elif set(re.findall(r"`([^`]+)`", line)) != want or (not want and "unmapped" not in line):
            problems.append(f"{n['id']}: outline verbs line {line!r} differs from catalog_verbs {sorted(want)}")
    return problems


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


def main(argv: list[str] | None = None) -> int:
    global APP_BASE
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--app-base", default=os.environ.get(APP_BASE_ENV) or None,
                    help=f"root-relative app path (e.g. /dashboard) that turns each in-app location into a link; "
                         f"default ${APP_BASE_ENV}, unset means code text only")
    ap.add_argument("--out-dir", type=Path, default=HERE, help="where to write the outlines (default: this directory)")
    args = ap.parse_args(argv)
    if args.app_base is not None:
        if not APP_BASE_OK.fullmatch(args.app_base):
            raise SystemExit(f"app base {args.app_base!r} must be a root-relative path such as /dashboard: no scheme, "
                             "host, port, query or fragment, so no host, port or project parameter is ever emitted")
        if args.out_dir.resolve() == HERE:
            raise SystemExit("an app base is for a served rendering: pass --out-dir so the committed outlines keep "
                             "their in-app locations as code text")
        APP_BASE = args.app_base
    docs = [(overview(), "agentdecompile-recovery-pipeline"),
            (companion("execution-contracts", "exec-header"), "execution-contracts"),
            (companion("resilience-contracts", "resil-header"), "resilience-contracts"),
            (companion("autonomous-capabilities", "cap-header"), "autonomous-capabilities")]
    problems = verify_model()
    for doc, diagram in docs:
        problems += verify(diagram, doc) + verify_verbs(doc)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for doc, diagram in docs:
        text = "\n".join(doc.lines).rstrip() + "\n"
        path = args.out_dir / M["diagrams"][diagram]["outline"]
        path.write_text(text, encoding="utf-8")
        print(path, len(text.encode("utf-8")), "bytes;", len(doc.anchors), "anchors; verified against", M["diagrams"][diagram]["svg"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
