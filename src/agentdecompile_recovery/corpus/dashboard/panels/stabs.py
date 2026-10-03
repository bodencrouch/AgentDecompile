"""Original source names: STABS records, shipped symbol tables, and how far a
recovered `.cpp` path travels.

The naming problem in this project is not "invent a plausible name". It is
"find the name the original programmer typed". Two shipped artifacts can still
carry that information, and neither is a Windows build:

* builds linked with STABS debug records left in the binary, which name the
  original compilation unit (`N_SO`/`N_OSO`) and every function in it
  (`N_FUN`), plus file statics (`N_STSYM`) and globals (`N_GSYM`);
* builds that ship a full C++ symbol table, so class and method names survive
  even though no source path does.

Because the binaries in the corpus are forks of one codebase, a path recovered
from a build that has a STABS index attaches to the same function in other
builds through the cross-build identity layer. This panel reports the recovery
and its reach, and the fraction of the corpus still carrying no original path.

Every number is read on request from `extract/stabs/` and the corpus store.
`_collect()` gathers them once; `render()` turns that into HTML and
`as_payload()` returns it as plain data for the workbench.
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

if __package__ in (None, ""):
    # Keeps the module importable from a bare checkout, the way the loader does.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agentdecompile_recovery.corpus.dashboard.panels.common import (  # noqa: E402
    DRM_EXCLUDED,
    ago,
    esc,
    fnum,
    fpct,
    load_json,
    missing,
    panel,
    query_db,
    rel,
    table,
    tag,
)
from agentdecompile_recovery.corpus.dashboard.panels.viz import bars, donut, heatmap  # noqa: E402

try:  # count_link is landing in common.py from another author.
    from agentdecompile_recovery.corpus.dashboard.panels.common import count_link
except ImportError:  # the panel still renders, with plain links
    count_link = None


def _details(inner: str, summary: str = "raw numbers") -> str:
    """Collapsed-by-default expansion of a chart (10-relationship-layout.md
    Rule C). Visible on click, not open by default."""
    return f'<details><summary>{esc(summary)}</summary>{inner}</details>'


def _bin_href(slug) -> str:
    return "/binary/" + quote(str(slug or ""), safe="")


def _fn_href(slug, extra: str = "") -> str:
    return "/functions?binary=" + quote(str(slug or ""), safe="") + extra


def _clink(n, href: str, unit: str | None = None, title: str | None = None) -> str:
    """A count is the control that opens the set it counts."""
    if count_link is not None:
        try:
            return count_link(n, href, unit=unit, title=title)
        except Exception:  # noqa: BLE001 - a helper must never cost the panel
            pass
    if n is None:
        return "-"
    tip = f' title="{esc(title)}"' if title else ""
    return f'<a href="{esc(href)}"{tip}>{fnum(n)}</a>'


def _file_link(path: Path, label: str | None = None) -> str:
    return (f'<a href="/artifact?p={esc(rel(path))}">'
            f'{esc(label or rel(path))}</a>')


def _slugs() -> dict[str, str]:
    """repo_path and file name -> slug, so any label here can reach its build."""
    rows, err = query_db("SELECT repo_path, slug FROM binary")
    if err:
        return {}
    out = {}
    for repo, slug in rows:
        out[str(repo)] = str(slug)
        out[str(repo).rsplit("/", 1)[-1]] = str(slug)
    return out

TITLE = "Original source names — STABS, symbols and provenance"

from agentdecompile_recovery.corpus.dashboard.common import as_root, DB_PATH
STABS_DIR = as_root() / "extract" / "stabs"
STABS_INDEX = STABS_DIR / "_index.json"
PROVENANCE_SUMMARY = as_root() / "output" / "names" / "function_provenance_by_binary.json"

# What each STABS record type is worth to this project, so the page explains
# itself without the reader opening kx/machostabs.py.
STAB_GLOSS = {
    "N_SO": "compilation-unit boundary (the original .cpp path)",
    "N_OSO": "the .o that unit was linked from",
    "N_FUN": "function name, address and byte length",
    "N_STSYM": "file-scope static",
    "N_GSYM": "global",
    "N_BNSYM": "function start marker",
    "N_ENSYM": "function end marker",
    "N_SOL": "included source file for a line range",
    "N_OPT": "compiler options stamp (all a stripped build keeps)",
}

# The record_counts object sits in the first few hundred bytes of each parsed
# dump. The per-function dumps run to megabytes of detail; parsing one
# on a request path would blow the render budget for a header-sized fact.
HEAD_BYTES = 96 << 10
RECORD_BLOCK = re.compile(r'"record_counts"\s*:\s*\{([^}]*)\}')
RECORD_PAIR = re.compile(r'"(\w+)"\s*:\s*(\d+)')

# Ghidra's placeholder names. A function whose name still matches one of these
# was never named by anyone, in any build.
PLACEHOLDER_SQL = (
    "name LIKE 'FUN\\_%' ESCAPE '\\' "
    "OR name LIKE 'thunk\\_FUN\\_%' ESCAPE '\\' "
    "OR name LIKE 'sub\\_%' ESCAPE '\\' "
    "OR name LIKE 'LAB\\_%' ESCAPE '\\'"
)

HAS_SRC = "source_file IS NOT NULL AND source_file <> ''"


def _stat(path: Path):
    try:
        st = path.stat()
        return st.st_size, st.st_mtime
    except OSError:
        return None, None


def _human_bytes(n) -> str:
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "-"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:,.0f} {unit}" if unit == "B" else f"{n:,.1f} {unit}"
        n /= 1024
    return f"{n:,.1f} GB"


def _record_counts(path: Path) -> dict[str, int]:
    """Merge every `record_counts` block in a dump's header window."""
    counts: dict[str, int] = {}
    try:
        with path.open("rb") as fh:
            head = fh.read(HEAD_BYTES).decode("utf-8", "replace")
    except OSError:
        return counts
    for block in RECORD_BLOCK.findall(head):
        for name, value in RECORD_PAIR.findall(block):
            try:
                counts[name] = counts.get(name, 0) + int(value)
            except ValueError:
                continue
    return counts


def _index_slices(data) -> list[tuple[str, str, dict]]:
    """(label, repo_path, slice) triples, tolerant of index shape drift."""
    if isinstance(data, dict):
        items = list(data.items())
    elif isinstance(data, list):
        items = [(str(d.get("slug") or d.get("binary") or i), d)
                 for i, d in enumerate(data) if isinstance(d, dict)]
    else:
        return []
    out: list[tuple[str, str, dict]] = []
    for key, entry in items:
        if not isinstance(entry, dict):
            continue
        repo = str(entry.get("repo_path") or entry.get("path") or "")
        slices = entry.get("slices")
        if not isinstance(slices, list) or not slices:
            slices = [entry]  # a flat, sliceless shape still carries the counts
        for sl in slices:
            if isinstance(sl, dict):
                out.append((str(key), repo, sl))
    return out


TOP_SOURCES_CAP = 50        # payload cap
TOP_SOURCES_RENDER = 25     # rows the HTML shows
SMALL_TABLES = ("binary", "logical_function", "identity", "match", "eval", "decomp")


def _db_at():
    """mtime of the corpus store: the freshness of every query-backed figure."""
    if DB_PATH is None:
        return None
    try:
        return Path(DB_PATH).stat().st_mtime
    except OSError:
        return None


def _db_source() -> str:
    return rel(Path(DB_PATH)) if DB_PATH else "corpus store (unset)"


def _sect(source: str, at, err: str | None = None, **data) -> dict:
    """One collected section. `state` is explicit: ok, empty or missing."""
    out = {"source": source, "at": at, "state": "ok", "error": None}
    if err:
        out["state"] = "missing"
        out["error"] = str(err)
    out.update(data)
    return out


def _empty(sec: dict, msg: str) -> dict:
    sec["state"] = "empty"
    sec["error"] = msg
    return sec


def _int(v):
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _collect_index() -> dict:
    src = rel(STABS_INDEX)
    _, at = _stat(STABS_INDEX)
    data, err = load_json(STABS_INDEX)
    sec = _sect(src, at, err if (err or data is None) else None,
                slices=[], totals={})
    if sec["state"] != "ok":
        sec["error"] = sec["error"] or f"{src} is empty"
        return sec
    slices = _index_slices(data)
    if not slices:
        return _empty(sec, f"{src} has no recognisable entries")
    slugs = _slugs()
    tot = {"symbols": 0, "stabs_records": 0, "units": 0, "functions": 0}
    for label, repo, sl in slices:
        units, funcs = sl.get("units"), sl.get("functions")
        units = len(units) if isinstance(units, list) else _int(units)
        funcs = len(funcs) if isinstance(funcs, list) else _int(funcs)
        n_sym, n_stabs = _int(sl.get("n_symbols")), _int(sl.get("n_stabs"))
        for key, v in (("symbols", n_sym), ("stabs_records", n_stabs),
                       ("units", units), ("functions", funcs)):
            tot[key] += v or 0
        sec["slices"].append({
            "label": label,
            "name": repo or label,
            "slug": slugs.get(str(repo)) or slugs.get(str(label)),
            "arch": sl.get("arch") or None,
            "symbols": n_sym,
            "stabs_records": n_stabs,
            "units": units,
            "functions": funcs,
            "dump": rel(STABS_DIR / f"{label}.json"),
            "state": "units_and_paths" if (units or 0) > 0 else "stripped",
        })
    sec["totals"] = tot
    return sec


def _collect_record_types() -> dict:
    src = rel(STABS_DIR)
    _, at = _stat(STABS_DIR)
    sec = _sect(src, at, columns=[], dumps=[], totals={})
    if not STABS_DIR.is_dir():
        sec["state"], sec["error"] = "missing", f"{src} missing"
        return sec
    dumps = sorted(p for p in STABS_DIR.glob("*.json") if p.name != "_index.json")
    if not dumps:
        return _empty(sec, f"no per-binary dumps under {src}")
    per_file = {p: _record_counts(p) for p in dumps}
    totals: dict[str, int] = {}
    for counts in per_file.values():
        for name, value in counts.items():
            totals[name] = totals.get(name, 0) + value
    if not totals:
        return _empty(sec, "no record_counts block found in any dump header")
    cols = [n for n, _ in sorted(totals.items(), key=lambda kv: -kv[1])][:10]
    sec["columns"] = [{"type": c, "gloss": STAB_GLOSS.get(c), "total": totals[c]}
                      for c in cols]
    sec["totals"] = {c: totals[c] for c in cols}
    for p, counts in per_file.items():
        _, mt = _stat(p)
        sec["dumps"].append({"file": p.name, "source": rel(p), "at": mt,
                             "counts": {c: counts.get(c) for c in cols}})
    return sec


def _collect_files() -> dict:
    src = rel(STABS_DIR)
    _, at = _stat(STABS_DIR)
    sec = _sect(src, at, files=[], total_bytes=0)
    if not STABS_DIR.is_dir():
        sec["state"], sec["error"] = "missing", f"{src} missing"
        return sec
    entries = sorted(p for p in STABS_DIR.iterdir() if p.is_file())
    if not entries:
        return _empty(sec, f"{src} is empty")
    for p in entries:
        size, mt = _stat(p)
        sec["total_bytes"] += size or 0
        sec["files"].append({"name": p.name, "source": rel(p),
                             "bytes": size, "at": mt})
    return sec


def _collect_provenance() -> dict:
    sec = _sect("table binary + " + rel(PROVENANCE_SUMMARY), _db_at(),
                binaries=[], platforms=[], totals={}, source_counts_known=False)
    bins, err = query_db(
        "SELECT id, repo_path, slug, platform, game, arch, func_count, named_count "
        "FROM binary ORDER BY platform, slug")
    if err:
        sec["state"], sec["error"] = "missing", str(err)
        return sec
    if not bins:
        return _empty(sec, "table `binary` has no rows")
    snapshot, _snap_err = load_json(PROVENANCE_SUMMARY)
    by_slug = snapshot.get("by_slug", snapshot) if isinstance(snapshot, dict) else {}
    if not isinstance(by_slug, dict):
        by_slug = {}
    _, snap_at = _stat(PROVENANCE_SUMMARY)
    sec["summary_at"] = snap_at
    sec["summary_source"] = rel(PROVENANCE_SUMMARY)
    agg: dict = {}
    for _bid, repo, slug, platform, game, arch, func_count, named_count in bins:
        total = _int(func_count)
        named = _int(named_count)
        placeholder = max(0, total - named) if total is not None and named is not None else None
        saved = by_slug.get(str(slug), {})
        with_src = _int(saved.get("with_source_file")) if isinstance(saved, dict) else None
        excluded = str(repo) in DRM_EXCLUDED
        sec["binaries"].append({
            "slug": slug, "repo_path": repo, "platform": platform, "game": game,
            "arch": arch, "functions": total, "placeholders": placeholder,
            "with_source_path": with_src,
            "state": "excluded" if excluded else "counted",
        })
        if not excluded and total is not None and placeholder is not None:
            s = agg.setdefault(platform or "?", {"builds": 0, "functions": 0,
                                                 "placeholders": 0, "with_source_path": 0,
                                                 "_known": 0})
            s["builds"] += 1
            s["functions"] += total
            s["placeholders"] += placeholder
            if with_src is not None:
                s["with_source_path"] += with_src
                s["_known"] += 1
    known_all = bool(agg) and all(s["_known"] == s["builds"] for s in agg.values())
    sec["source_counts_known"] = known_all
    for plat, s in sorted(agg.items(), key=lambda kv: -kv[1]["with_source_path"]):
        ok = s["_known"] == s["builds"]
        sec["platforms"].append({
            "platform": plat, "builds": s["builds"], "functions": s["functions"],
            "placeholders": s["placeholders"],
            "with_source_path": s["with_source_path"] if ok else None})
    sec["totals"] = {k: sum(s[k] for s in agg.values())
                     for k in ("builds", "functions", "placeholders")}
    sec["totals"]["with_source_path"] = (
        sum(s["with_source_path"] for s in agg.values()) if known_all else None)
    return sec


def _collect_logical() -> dict:
    sec = _sect("table logical_function", _db_at(), figures={}, games=[])
    totals, err = query_db(
        "SELECT COUNT(*), "
        f"SUM({HAS_SRC}), "
        "SUM(object_file IS NOT NULL AND object_file <> ''), "
        "COUNT(DISTINCT CASE WHEN source_file <> '' THEN source_file END), "
        "COUNT(DISTINCT CASE WHEN object_file <> '' THEN object_file END) "
        "FROM logical_function")
    if err:
        sec["state"], sec["error"] = "missing", str(err)
        return sec
    if not totals or not totals[0][0]:
        return _empty(sec, "table `logical_function` is empty")
    total, with_src, with_obj, n_files, n_objs = (v or 0 for v in totals[0])
    src, at = sec["source"], sec["at"]
    sec["figures"] = {k: {"value": v, "source": src, "at": at} for k, v in (
        ("logical_functions", total), ("with_source_path", with_src),
        ("with_object_file", with_obj), ("distinct_source_files", n_files),
        ("distinct_object_files", n_objs))}
    per_game, gerr = query_db(
        "SELECT game, COUNT(*), "
        f"SUM({HAS_SRC}) "
        "FROM logical_function GROUP BY game ORDER BY 2 DESC")
    if gerr:
        sec["games_error"] = str(gerr)
    for game, n, named in per_game or []:
        sec["games"].append({"game": game, "logical_functions": n or 0,
                             "with_source_path": named or 0})
    return sec


def _collect_reach() -> dict:
    sec = _sect("tables identity, logical_function, binary", _db_at(),
                platforms=[], methods=[])
    reach, err = query_db(
        "SELECT b.platform, COUNT(DISTINCT i.logical_id) "
        "FROM logical_function lf "
        "JOIN identity i ON i.logical_id = lf.id "
        "JOIN binary b ON b.id = i.binary_id "
        f"WHERE lf.{HAS_SRC} "
        "GROUP BY b.platform")
    if err:
        sec["state"], sec["error"] = "missing", str(err)
        return sec
    present, perr = query_db(
        "SELECT b.platform, COUNT(DISTINCT i.logical_id) "
        "FROM identity i JOIN binary b ON b.id = i.binary_id "
        "GROUP BY b.platform")
    if perr:
        sec["state"], sec["error"] = "missing", str(perr)
        return sec
    if not reach:
        return _empty(sec, "no source-attributed identities recorded yet")
    seen = dict(present or [])
    for platform, named in sorted(reach, key=lambda r: -r[1]):
        sec["platforms"].append({"platform": platform, "present": seen.get(platform, 0),
                                 "with_source_path": named})
    methods, merr = query_db(
        "SELECT method, COUNT(*) FROM identity GROUP BY method "
        "ORDER BY 2 DESC LIMIT 12")
    sec["methods"] = [{"method": m, "rows": n} for m, n in methods or []]
    if merr:
        sec["methods_error"] = str(merr)
    return sec


def _collect_top_sources() -> dict:
    sec = _sect("table logical_function", _db_at(), paths=[], cap=TOP_SOURCES_CAP)
    rows, err = query_db(
        "SELECT source_file, COUNT(*) c FROM logical_function "
        f"WHERE {HAS_SRC} GROUP BY source_file ORDER BY c DESC LIMIT {TOP_SOURCES_CAP}")
    if err:
        sec["state"], sec["error"] = "missing", str(err)
        return sec
    if not rows:
        return _empty(sec, "no logical function carries a source path yet")
    sec["paths"] = [{"path": str(p), "logical_functions": c} for p, c in rows]
    return sec


def _collect_symbol_tables() -> dict:
    sec = _sect("sqlite_master", _db_at(), tables=[], dedicated_symbol_tables=[])
    names, err = query_db(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    if err:
        sec["state"], sec["error"] = "missing", str(err)
        return sec
    if not names:
        return _empty(sec, "no tables found")
    tables = [str(n[0]) for n in names]
    sec["dedicated_symbol_tables"] = [
        t for t in tables if any(k in t.lower() for k in ("symbol", "stab", "name", "sym"))]
    for t in tables:
        if t in SMALL_TABLES:
            counts, cerr = query_db(f'SELECT COUNT(*) FROM "{t}"')
            if counts:
                sec["tables"].append({"table": t, "rows": counts[0][0], "state": "counted"})
            else:
                sec["tables"].append({"table": t, "rows": None, "state": "error",
                                      "error": str(cerr)})
        else:
            # Large tables (func, calledge) are never scanned on a request.
            sec["tables"].append({"table": t, "rows": None, "state": "not_counted"})
    return sec


def _collect() -> dict:
    started = time.time()
    sections = {
        "index": _collect_index(),
        "record_types": _collect_record_types(),
        "files": _collect_files(),
        "logical": _collect_logical(),
        "reach": _collect_reach(),
        "provenance": _collect_provenance(),
        "top_sources": _collect_top_sources(),
        "symbol_tables": _collect_symbol_tables(),
    }
    errors = [f"{k}: {v['error']}" for k, v in sections.items() if v["state"] == "missing"]
    sections["at"] = time.time()
    sections["elapsed_s"] = round(sections["at"] - started, 3)
    sections["corpus_db"] = _db_source()
    sections["errors"] = errors
    return sections


def as_payload() -> dict:
    """Plain data for the workbench: no markup, numbers as numbers."""
    return _collect()


# ---------------------------------------------------------------- HTML ----

def _miss(sec: dict, heading: str) -> str | None:
    if sec["state"] == "ok":
        return None
    return panel(missing(sec["error"] or "no data"), heading)


def _render_index(sec: dict) -> str:
    heading = "STABS mining index (extract/stabs/_index.json)"
    m = _miss(sec, heading)
    if m:
        return m
    rows, chart_rows = [], []
    for s in sec["slices"]:
        carries = s["state"] == "units_and_paths"
        name = s["name"]
        rows.append([
            f'<a href="{esc(_bin_href(s["slug"]))}">{esc(name)}</a>' if s["slug"] else esc(name),
            esc(s["arch"] or "?"),
            fnum(s["symbols"]), fnum(s["stabs_records"]), fnum(s["units"]),
            _clink(s["functions"], f"/artifact?p={s['dump']}",
                   title="the parsed dump these records came from"),
            tag("units + paths", "ok") if carries else tag("stripped", "dead"),
        ])
        chart_rows.append((name, s["functions"] or 0, "proven" if carries else "unproven"))
    t = sec["totals"]
    rows.append(["<b>all slices</b>", "", f"<b>{fnum(t['symbols'])}</b>",
                 f"<b>{fnum(t['stabs_records'])}</b>", f"<b>{fnum(t['units'])}</b>",
                 f"<b>{fnum(t['functions'])}</b>", ""])
    body = (
        '<p class="sub">One row per Mach-O slice. <b>Units</b> are original '
        'compilation units named by <code>N_SO</code>/<code>N_OSO</code> — each '
        'one is a real <code>.cpp</code> path and the <code>.o</code> it linked '
        'from. <b>Functions</b> are <code>N_FUN</code> records with a name, an '
        'address and a byte length.</p>'
        + bars(chart_rows, href_fn=None)
        + _details(table(["Binary", "Arch", "Symbols", "STABS records",
                          "Compilation units", "Functions", "Debug info"],
                        rows, numeric={2, 3, 4, 5}))
    )
    return panel(body, heading)


def _render_record_types(sec: dict) -> str:
    heading = "Which record types each dump actually contains"
    m = _miss(sec, heading)
    if m:
        return m
    cols = [c["type"] for c in sec["columns"]]
    rows = []
    for d in sec["dumps"]:
        rows.append([f'<a href="/artifact?p={esc(d["source"])}">{esc(d["file"])}</a>']
                    + [fnum(d["counts"][c]) if d["counts"][c] is not None else "-"
                       for c in cols])
    rows.append([f"<b>{len(sec['dumps'])} dumps</b>"]
                + [f"<b>{fnum(sec['totals'].get(c))}</b>" for c in cols])
    gloss = "".join(
        f'<div><code>{esc(c["type"])}</code></div><div>{esc(c["gloss"] or "-")}</div>'
        for c in sec["columns"])
    matrix = [[d["counts"][c] or 0 for c in cols] for d in sec["dumps"]]
    chart = heatmap(matrix, [d["file"] for d in sec["dumps"]], cols, href_fn=None)
    body = (
        '<p class="sub">Read from the header of each dump, not from the index — '
        'this is what the parser found in the binary itself.</p>'
        + chart
        + _details(table(["Dump"] + cols, rows, numeric=set(range(1, len(cols) + 1))))
        + f'<div class="kv" style="margin-top:10px">{gloss}</div>'
        + '<p class="sub" style="margin-top:8px">Line-number, parameter and '
        'local-variable record types that do not appear above are not in these '
        'dumps, so these builds carry function-level debug info only: names, '
        'addresses, sizes, source files and object files.</p>'
    )
    return panel(body, heading)


def _render_files(sec: dict) -> str:
    heading = "What is on disk under extract/stabs/"
    m = _miss(sec, heading)
    if m:
        return m
    rows = [[f'<a href="/artifact?p={esc(f["source"])}">{esc(f["name"])}</a>',
             _human_bytes(f["bytes"]), esc(ago(f["at"]))] for f in sec["files"]]
    rows.append([f"<b>{len(sec['files'])} files</b>",
                 f"<b>{_human_bytes(sec['total_bytes'])}</b>", ""])
    return panel(table(["File", "Size", "Modified"], rows, numeric={1, 2}), heading)


def _render_provenance(sec: dict) -> str:
    heading = "Name provenance per binary (stored extraction facts)"
    m = _miss(sec, heading)
    if m:
        return m
    rows, chart_rows = [], []
    for b in sec["binaries"]:
        slug, total, ph, ws = b["slug"], b["functions"], b["placeholders"], b["with_source_path"]
        rows.append([
            f'<a href="{esc(_bin_href(slug))}">{esc(b["repo_path"] or slug)}</a>'
            + (" " + tag("DRM, excluded", "warn") if b["state"] == "excluded" else ""),
            esc(b["platform"] or "?"), esc(b["game"] or "?"), esc(b["arch"] or "?"),
            _clink(total, _fn_href(slug), title="every function in this build"),
            _clink(ph, _fn_href(slug, "&placeholder=1"), title="functions nobody has ever named"),
            fpct(ph, total),
            _clink(ws, _fn_href(slug, "&has_source_file=1"),
                   title="functions attributed to an original .cpp"),
            fpct(ws, total),
        ])
        if b["state"] != "excluded" and total is not None and ph is not None and ws is not None:
            chart_rows.append((slug or b["repo_path"], ws, "proven" if ws else "unproven"))
    plat_rows = [
        [esc(p["platform"]), fnum(p["builds"]), fnum(p["functions"]),
         fnum(p["placeholders"]), fpct(p["placeholders"], p["functions"]),
         fnum(p["with_source_path"]) if p["with_source_path"] is not None else "-",
         fpct(p["with_source_path"], p["functions"]) if p["with_source_path"] is not None else "-"]
        for p in sec["platforms"]]
    t = sec["totals"]
    ws_all = t.get("with_source_path")
    plat_rows.append([
        "<b>all (excluded builds omitted)</b>", f"<b>{fnum(t.get('builds'))}</b>",
        f"<b>{fnum(t.get('functions'))}</b>", f"<b>{fnum(t.get('placeholders'))}</b>",
        f"<b>{fpct(t.get('placeholders'), t.get('functions'))}</b>",
        f"<b>{fnum(ws_all) if ws_all is not None else '-'}</b>",
        f"<b>{fpct(ws_all, t.get('functions')) if ws_all is not None else '-'}</b>"])
    plat_chart = (bars(
        [(p["platform"], p["with_source_path"] or 0, "proven" if p["with_source_path"] else "unproven")
         for p in sec["platforms"]]
    ) if chart_rows else missing(
        f"Per-binary source-path counts need the offline summary {sec['summary_source']}; "
        "the dashboard will not scan the function corpus to invent them."))
    bin_chart = (bars(chart_rows, href_fn=lambda slug, *_: _bin_href(slug)) if chart_rows else "")
    body = (
        '<p class="sub">Rolled up by platform first. <b>FUN_ placeholders</b> '
        'counts functions whose name is still <code>FUN_xxxxxxxx</code>, '
        '<code>sub_</code> or <code>LAB_</code> — nobody, in any build, has ever '
        'named them. <b>With a .cpp path</b> counts functions carrying a '
        '<code>source_file</code>, which only STABS mining can originate.</p>'
        + '<p class="sub" style="margin-top:8px">Functions with a real .cpp path, '
          "by platform:</p>"
        + plat_chart
        + _details(table(["Platform", "Builds", "Functions", "FUN_ placeholders", "%",
                          "With a .cpp path", "%"], plat_rows, numeric={1, 2, 3, 4, 5, 6}))
        + '<p class="sub" style="margin:14px 0 0">Per binary. A build with a '
        'non-zero path count and no STABS index of its own received those '
        'paths through the cross-build identity layer.</p>'
        + bin_chart
        + _details(table(["Binary", "Platform", "Game", "Arch", "Functions",
                          "FUN_ placeholders", "%", "With a .cpp path", "%"],
                        rows, numeric={4, 5, 6, 7, 8}))
    )
    return panel(body, heading)


def _render_logical(sec: dict) -> str:
    heading = "Logical functions carrying a real original source path"
    m = _miss(sec, heading)
    if m:
        return m
    f = {k: v["value"] for k, v in sec["figures"].items()}
    total, with_src = f["logical_functions"], f["with_source_path"]
    game_rows = [[esc(g["game"] or "?"), fnum(g["logical_functions"]),
                  fnum(g["with_source_path"]),
                  fpct(g["with_source_path"], g["logical_functions"])] for g in sec["games"]]
    game_chart = bars([(g["game"], g["with_source_path"],
                        "proven" if g["with_source_path"] else "unproven")
                       for g in sec["games"]])
    body = (
        f'<p class="sub">{fnum(with_src)} of {fnum(total)} logical functions '
        f'({fpct(with_src, total)}) carry an original <code>.cpp</code> path. '
        f'The rest are still unattributed.</p>'
        + donut(
            [("with a .cpp path", with_src, "proven"),
             ("unattributed", max(0, total - with_src), "unproven")],
            total=total, title="Original-path attribution")
        + '<div class="kv">'
        + f'<div>logical functions</div><div>{fnum(total)}</div>'
        + f'<div>with a source path</div><div>{fnum(with_src)} ({fpct(with_src, total)})</div>'
        + f'<div>with an object file</div><div>{fnum(f["with_object_file"])} ({fpct(f["with_object_file"], total)})</div>'
        + f'<div>distinct .cpp files named</div><div>{fnum(f["distinct_source_files"])}</div>'
        + f'<div>distinct .o files named</div><div>{fnum(f["distinct_object_files"])}</div>'
        + '</div>'
        + (game_chart + _details(table(["Game", "Logical functions", "With a source path", "%"],
                                       game_rows, numeric={1, 2, 3}))
           if game_rows else missing(sec.get("games_error") or "no per-game breakdown"))
    )
    return panel(body, heading)


def _render_reach(sec: dict) -> str:
    heading = "How far a recovered path travels (table `identity`)"
    m = _miss(sec, heading)
    if m:
        return m
    rows = [[esc(p["platform"] or "?"), fnum(p["present"]), fnum(p["with_source_path"]),
             fpct(p["with_source_path"], p["present"])] for p in sec["platforms"]]
    chart_rows = [(p["platform"] or "?", p["with_source_path"],
                   "proven" if p["with_source_path"] else "unproven") for p in sec["platforms"]]
    method_rows = [[esc(x["method"] or "?"), fnum(x["rows"])] for x in sec["methods"]]
    method_chart = bars([(x["method"] or "?", x["rows"], "unproven") for x in sec["methods"]])
    body = (
        '<p class="sub">Each row: logical functions bound to at least one '
        'function in that platform, and how many of them carry a <code>.cpp</code> '
        'path. Only builds with a STABS index shipped those paths; the other rows '
        'are transferred identity.</p>'
        + bars(chart_rows, sort=False)
        + _details(table(["Platform", "Logical functions present", "…with a .cpp path",
                          "%"], rows, numeric={1, 2, 3}))
        + (('<p class="sub" style="margin:14px 0 0">How each binding was made '
            '(<code>identity.method</code>).</p>'
            + method_chart
            + _details(table(["Binding method", "Rows"], method_rows, numeric={1})))
           if method_rows else missing(sec.get("methods_error") or "no binding methods recorded"))
    )
    return panel(body, heading)


def _render_top_sources(sec: dict) -> str:
    heading = "Biggest original source files by logical functions attributed"
    m = _miss(sec, heading)
    if m:
        return m
    out, chart_rows = [], []
    for item in sec["paths"][:TOP_SOURCES_RENDER]:
        text, count = item["path"], item["logical_functions"]
        head, _, name = text.rpartition("/")
        label = (f'<code>{esc(name or text)}</code>'
                 f'<div class="sub">{esc(head)}</div>' if head
                 else f'<code>{esc(text)}</code>')
        out.append([label, fnum(count)])
        chart_rows.append((name or text, count, "proven"))
    return panel(
        f'<p class="sub">Top {TOP_SOURCES_RENDER} by <code>GROUP BY source_file</code> over '
        '<code>logical_function</code>. These are the paths exactly as the '
        'linker recorded them.</p>'
        + bars(chart_rows)
        + _details(table(["Original source file", "Logical functions"], out, numeric={1})),
        heading)


def _render_symbol_tables(sec: dict) -> str:
    heading = "Symbol storage in the corpus store"
    m = _miss(sec, heading)
    if m:
        return m
    rows = []
    for t in sec["tables"]:
        if t["state"] == "counted":
            n = fnum(t["rows"])
        elif t["state"] == "not_counted":
            n = "not counted (too large to scan)"
        else:
            n = esc(t.get("error") or "error")
        rows.append([f"<code>{esc(t['table'])}</code>", n])
    sym = sec["dedicated_symbol_tables"]
    note = (
        '<p class="sub">A dedicated symbol table '
        + ("exists: " + ", ".join(f"<code>{esc(t)}</code>" for t in sym)
           if sym else
           "does not exist. Symbol-derived names live as columns on "
           "<code>func</code> (<code>name</code>, <code>source</code>, "
           "<code>source_file</code>, <code>object_file</code>) and are promoted "
           "to <code>logical_function</code>")
        + '.</p>')
    return panel(note + table(["Table", "Rows"], rows, numeric={1}), heading)


def render() -> str:
    try:
        d = _collect()
        lead = (
            '<p class="sub" style="margin-bottom:14px">'
            + tag("real names, not invented ones", "ok")
            + ' Two kinds of shipped artifact can still carry what the original '
            'programmers typed. Builds linked with <b>STABS</b> debug records '
            'left in place name every compilation unit (<code>N_SO</code>, '
            '<code>N_OSO</code>) and every function in it (<code>N_FUN</code>), '
            'plus file statics (<code>N_STSYM</code>) and globals '
            '(<code>N_GSYM</code>). Builds that ship a full C++ symbol table keep '
            'classes and methods but not source paths. Builds with neither get '
            'paths only through the cross-build identity layer, which attaches a '
            'path mined from one build to the matching function in another.</p>')
        parts = [
            _render_index(d["index"]),
            _render_record_types(d["record_types"]),
            _render_files(d["files"]),
            _render_logical(d["logical"]),
            _render_reach(d["reach"]),
            _render_provenance(d["provenance"]),
            _render_top_sources(d["top_sources"]),
            _render_symbol_tables(d["symbol_tables"]),
        ]
        foot = (f'<p class="sub" style="margin-top:10px">Panel built in '
                f'{d["elapsed_s"]:.2f}s, entirely from '
                f'<code>{esc(rel(STABS_DIR))}</code> and '
                f'<code>{esc(str(DB_PATH) if DB_PATH else "AGENT_DECOMPILE_CORPUS_DB unset")}</code>.</p>')
        return lead + "".join(p for p in parts if p) + foot
    except Exception as exc:  # noqa: BLE001
        return missing(f"stabs panel failed to render: {exc}")
