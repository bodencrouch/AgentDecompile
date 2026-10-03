"""Per-function Ghidra knowledge, merged into the corpus knowledge store.

Every binary in the corpus carries different reverse-engineering work:
hand-named functions in one, debug paths in another, a full C++ symbol table
in a third. Knowledge that exists in only one build is worth more than
knowledge repeated in all of them, so the merge has to preserve what each
binary knows individually. That is the "named" column here, which separates a
symbol-rich build from a stripped one.

The per-function export replaced the whole-program dump. The older C export
emitted one file per program, and most of its entries can be exception
funclets rather than functions, so real coverage can sit under half the
program. The per-function export writes one JSON per function (decompiled C,
an asm listing, instructions with bytes and relocations, calling convention,
signature, file offset). Both coverage numbers here are measured from the two
artifacts, not quoted.

The cost of that completeness is shape: many tiny JSON files per program on a
shared spinning disk. The ingest script pays the seek cost once per binary
into the knowledge store; this panel reports that store, never the file tree.

`as_payload()` and `render()` share one collector (`_collect`), so the HTML and
the JSON describe the same measurements.
"""

from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path
from urllib.parse import quote

from agentdecompile_recovery.corpus.dashboard.panels.common import (
    DRM_EXCLUDED,
    GHIDRA_SERVER_HOST,
    GHIDRA_SERVER_PORT,
    KNOWLEDGE_DB,
    as_external,
    as_root,
    ago,
    esc,
    fnum,
    fpct,
    kv,
    missing,
    panel,
    query_db,
    rel,
    table,
    tag,
    tcp_up,
)
from agentdecompile_recovery.corpus import corpus_env
from agentdecompile_recovery.corpus.dashboard.panels.viz import bars, donut, stacked_bar

TITLE = "Ghidra knowledge merge"

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


def _slugs() -> dict[str, str]:
    """Program name and repo_path -> slug. The export keys its work on the file name."""
    rows, err = query_db("SELECT repo_path, slug FROM binary")
    if err:
        return {}
    out = {}
    for repo, slug in rows:
        out[str(repo)] = str(slug)
        out[Path(str(repo)).name] = str(slug)
    return out

# The batch scripts that need the Ghidra server. Both resume by skipping work
# they believe already exists, so a dead server makes them exit 0 with nothing
# done — the only trace is in these per-job logs.
BATCH_LOG_DIRS = (as_root() / "logs" / "bsim", as_root() / "logs" / "cexport")
SERVER_FAIL_RE = re.compile(
    r"Connection to server failed|Unavailable \(BSimLaunchable\)"
    r"|No signature files found|Invalid Ghidra URL")
MAX_LOG_BYTES = 1 << 20

# The export comparison is measured on one configured program, since that is
# where both artifacts exist side by side.
def _coverage_program(status_rows=None) -> str:
    name = (
        os.environ.get("KNOWLEDGE_COVERAGE_PROGRAM")
        or os.environ.get("CORPUS_PROGRAM")
        or ""
    ).strip()
    if name:
        return name
    if status_rows:
        return str(status_rows[0][0] or "")
    return ""
MAX_DUMP_BYTES = 128 << 20
FUN_RE = re.compile(rb"\bFUN_[0-9a-fA-F]{6,}")
UNWIND_RE = re.compile(rb"\bUnwind_[0-9A-Za-z_]+")

# Ghidra's own placeholder names. Anything else is work a human (or a symbol
# table) put into that specific fork.
AUTO_NAME_SQL = ("name IS NOT NULL AND name NOT LIKE 'FUN!_%' ESCAPE '!' "
                 "AND name NOT LIKE 'Unwind!_%' ESCAPE '!' "
                 "AND name NOT LIKE 'thunk!_FUN!_%' ESCAPE '!'")


# --------------------------------------------------------------------------
# deep aggregate — the only query here that has to touch the full table
# --------------------------------------------------------------------------

# decompiled/asm/n_instructions/n_refs sit at the end of each record, behind the
# overflow pages that hold the C text, so summing them is a full table read:
# about a minute cold, seconds once the page cache holds it. That cannot run inside a page
# request, so it runs on a background thread and the page shows its age. The
# result is keyed on the cache file's (mtime, size): the ingest rewrites the
# file whenever it adds a program, so a matching key means the numbers still
# describe exactly this file and cannot be stale.
_DEEP_LOCK = threading.Lock()
_DEEP: dict = {"key": None, "rows": {}, "ts": 0.0, "seconds": 0.0,
               "error": None, "running": False}

DEEP_SQL = """
SELECT program,
       COUNT(*)                    AS n,
       SUM(decompiled IS NOT NULL) AS n_decomp,
       SUM(asm IS NOT NULL)        AS n_asm,
       SUM(n_instructions)         AS instrs,
       SUM(n_refs)                 AS refs
FROM func_knowledge
GROUP BY program
"""


def _db_key(path: Path | None):
    if path is None:
        return None
    try:
        st = path.stat()
    except OSError:
        return None
    return (int(st.st_mtime), st.st_size)


def _deep_worker(key) -> None:
    t0 = time.time()
    rows, err = query_db(DEEP_SQL, db=_knowledge_db())
    elapsed = time.time() - t0
    with _DEEP_LOCK:
        _DEEP["running"] = False
        _DEEP["error"] = err
        if not err:
            _DEEP.update(key=key, ts=time.time(), seconds=elapsed,
                         rows={r[0]: r[1:] for r in rows})


def _deep_snapshot() -> dict:
    """Last full-scan aggregate, starting one if the cache file has changed."""
    key = _db_key(_knowledge_db())
    with _DEEP_LOCK:
        snap = dict(_DEEP)
        stale = key is not None and key != _DEEP["key"]
        if stale and not _DEEP["running"]:
            _DEEP["running"] = True
            snap["running"] = True
            threading.Thread(target=_deep_worker, args=(key,), daemon=True,
                             name="knowledge-deep-scan").start()
    snap["fresh"] = key is not None and key == snap["key"]
    return snap


# --------------------------------------------------------------------------
# whole-program C dump — the artifact the per-function export replaced
# --------------------------------------------------------------------------

# Read once per mtime. Distinct symbol names are counted rather than
# definitions because the dump repeats a name at every call site.
_DUMP_CACHE: dict = {}


def _dump_path(program: str) -> Path:
    return as_external() / "binaries" / program / "ghidra_knowledge" / f"{program}.c"


def _dump_counts(program: str):
    """Return (n_fun, n_unwind, size, error) for the whole-program C dump."""
    path = _dump_path(program)
    try:
        st = path.stat()
    except OSError:
        return None, None, None, f"whole-program dump missing ({path.name})"
    key = (str(path), int(st.st_mtime), st.st_size)
    hit = _DUMP_CACHE.get(key)
    if hit:
        return (*hit, None)
    if st.st_size > MAX_DUMP_BYTES:
        return None, None, st.st_size, f"{path.name} too large to scan live"
    try:
        blob = path.read_bytes()
    except OSError as exc:
        return None, None, st.st_size, f"could not read {path.name}: {exc}"
    counts = (len(set(FUN_RE.findall(blob))), len(set(UNWIND_RE.findall(blob))),
              st.st_size)
    _DUMP_CACHE.clear()
    _DUMP_CACHE[key] = counts
    return (*counts, None)


# --------------------------------------------------------------------------
# collector — one pass of measurements shared by render() and as_payload()
# --------------------------------------------------------------------------

GAP_STATE = {
    "cached": ("cached", "proven"),
    "exported": ("exported, not ingested", "partial"),
    "no_export": ("no export", "failed"),
    "untracked": ("not in export tree", "missing"),
}


def _knowledge_db() -> Path | None:
    return KNOWLEDGE_DB or corpus_env.knowledge_db_path()


def _num(v):
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _scan_batch_logs() -> dict:
    scanned, failed, victims, newest = 0, 0, [], 0.0
    for d in BATCH_LOG_DIRS:
        if not d.is_dir():
            continue
        for log in sorted(d.glob("*.log")):
            scanned += 1
            try:
                newest = max(newest, log.stat().st_mtime)
                with log.open("rb") as fh:
                    text = fh.read(MAX_LOG_BYTES).decode("utf-8", "replace")
            except OSError:
                continue
            if SERVER_FAIL_RE.search(text):
                failed += 1
                victims.append(f"{d.name}/{log.stem}")
    return {
        "source": "logs/bsim, logs/cexport",
        "scanned": scanned,
        "failed": failed,
        "victims": victims,
        "at": newest or None,
        "state": "missing" if not scanned else ("failed" if failed else "proven"),
    }


def _collect() -> dict:
    now = time.time()
    db = _knowledge_db()
    errors: list[str] = []
    out: dict = {"at": now, "errors": errors}

    # Ghidra server — observational TCP probe against configured host/port.
    configured = bool(GHIDRA_SERVER_PORT)
    up = tcp_up(GHIDRA_SERVER_HOST, GHIDRA_SERVER_PORT) if configured else None
    out["server"] = {
        "host": GHIDRA_SERVER_HOST,
        "port": GHIDRA_SERVER_PORT or None,
        "configured": configured,
        "reachable": up,
        "observational": True,
        "at": now,
        "source": "tcp probe (AGENT_DECOMPILE_GHIDRA_SERVER_HOST/PORT)",
        "state": "unproven" if not configured else ("proven" if up else "failed"),
    }
    out["batch_logs"] = _scan_batch_logs()

    # Knowledge store
    status_rows, status_err = (
        query_db("SELECT program, functions_done, functions_total, seconds, complete "
                 "FROM ingest_status ORDER BY program", db=db)
        if db is not None else ([], "knowledge store path is not configured"))
    out["status_rows"], out["status_err"] = status_rows, status_err
    if status_err:
        errors.append(str(status_err))
    st = None
    try:
        st = db.stat() if db is not None else None
    except OSError:
        st = None
    out["db"] = {
        "source": rel(db) if db is not None else None,
        "size_bytes": st.st_size if st else None,
        "at": st.st_mtime if st else None,
        "state": "proven" if st else "missing",
    }

    # Per-program live rows (covering index) and the background deep aggregate.
    live, live_err = (query_db(
        f"SELECT program, COUNT(*), SUM(CASE WHEN {AUTO_NAME_SQL} THEN 1 ELSE 0 END) "
        "FROM func_knowledge GROUP BY program", db=db)
        if db is not None and not status_err else ([], None))
    if live_err:
        errors.append(str(live_err))
    out["live"] = {r[0]: (r[1], r[2]) for r in live}
    out["live_err"] = live_err
    out["deep"] = _deep_snapshot() if db is not None and not status_err else {}

    out["slugs"] = _slugs()

    # Coverage on the configured program
    out["coverage"] = _collect_coverage(status_rows, out["slugs"])

    # Gaps
    out["gaps"] = _collect_gaps(status_rows, out["slugs"])
    if out["gaps"].get("error"):
        errors.append(out["gaps"]["error"])
    return out


def _collect_coverage(status_rows, slugs) -> dict:
    program = _coverage_program(status_rows)
    if not program:
        return {"error": "set CORPUS_PROGRAM or KNOWLEDGE_COVERAGE_PROGRAM", "state": "missing"}
    n_fun, n_unwind, size, err = _dump_counts(program)
    per_func = next((r[1] for r in status_rows if r[0] == program), None)
    bins, _ = query_db("SELECT id, repo_path FROM binary")
    bid = next((b[0] for b in bins if Path(str(b[1])).name == program), None)
    real = None
    if bid is not None:
        rows, _ = query_db("SELECT COUNT(*) FROM func WHERE binary_id=?", (bid,))
        real = rows[0][0] if rows else None
    path = _dump_path(program)
    try:
        at = path.stat().st_mtime
    except OSError:
        at = None
    return {
        "program": program, "slug": slugs.get(program), "error": err,
        "real_functions": real, "dump_functions": n_fun, "dump_unwind": n_unwind,
        "dump_size_bytes": size, "per_function": per_func,
        "dump_source": "external recovery root: binaries/<program>/ghidra_knowledge/<program>.c",
        "dump_at": at,
        "state": "missing" if err else "proven",
    }


def _collect_gaps(status_rows, slugs) -> dict:
    ingested = {r[0]: r[1] for r in status_rows}
    bins, err = query_db("SELECT repo_path FROM binary ORDER BY repo_path")
    if err:
        return {"error": str(err), "items": []}
    if not bins:
        return {"error": "corpus store has no binary rows", "items": []}
    root = as_external() / "binaries"
    try:
        dirs = {d.name for d in root.iterdir() if d.is_dir()}
    except OSError as exc:
        return {"error": f"cannot list {rel(root)}: {exc}", "items": []}
    items, counts, unexplained = [], {k: 0 for k in GAP_STATE}, 0
    for (repo_path,) in bins:
        name = Path(str(repo_path)).name
        excluded = str(repo_path) in DRM_EXCLUDED
        has_dir = name in dirs
        exported = has_dir and (root / name / "ghidra_knowledge" / "functions"
                                / "index.json").exists()
        cached = ingested.get(name)
        key = ("cached" if cached else "exported" if exported
               else "no_export" if has_dir else "untracked")
        counts[key] += 1
        if not cached and not excluded:
            unexplained += 1
        items.append({"repo_path": str(repo_path), "program": name,
                      "slug": slugs.get(str(repo_path)), "key": key,
                      "label": GAP_STATE[key][0],
                      "state": "excluded" if excluded and not cached else GAP_STATE[key][1],
                      "excluded": excluded, "cached": cached or None})
    stray = sorted(dirs - {Path(str(b[0])).name for b in bins})
    return {"items": items, "counts": counts, "unexplained": unexplained,
            "stray_dirs": stray, "total": len(items),
            "source": "binary table + external recovery root binaries/*",
            "at": time.time()}


# --------------------------------------------------------------------------
# JSON payload
# --------------------------------------------------------------------------


def as_payload() -> dict:
    """Structured facts for the workbench. No markup."""
    c = _collect()
    rows = c["status_rows"] or []
    done = sum(r[1] or 0 for r in rows)
    total = sum(r[2] or 0 for r in rows)
    seconds = sum(r[3] or 0.0 for r in rows)
    complete = sum(1 for r in rows if r[4])
    db = c["db"]
    scale = {"state": "missing", "source": "ingest_status", "at": db["at"],
             "error": c["status_err"] or (None if rows else "ingest_status is empty")}
    if rows:
        scale.update(
            programs=len(rows), programs_complete=complete,
            functions_cached=done, functions_offered=total,
            ingest_seconds=seconds,
            state="proven" if complete == len(rows) else "partial")

    deep = c["deep"] or {}
    deep_rows = deep.get("rows") or {}
    programs = []
    for prog, d_, t_, sec, comp in rows:
        n_rows, named = c["live"].get(prog, (None, None))
        d = deep_rows.get(prog)
        programs.append({
            "program": prog, "slug": c["slugs"].get(str(prog)),
            "state": "proven" if comp else "partial",
            "cached": _num(d_), "offered": _num(t_),
            "ingest_seconds": sec, "rows": _num(n_rows), "named": _num(named),
            "decompiled": _num(d[1]) if d else None,
            "asm": _num(d[2]) if d else None,
            "instructions": _num(d[3]) if d else None,
            "refs": _num(d[4]) if d else None,
        })
    if c["status_err"]:
        deep_state = "missing"
    elif deep.get("error"):
        deep_state = "failed"
    elif deep.get("fresh"):
        deep_state = "proven"
    elif deep.get("running"):
        deep_state = "partial"
    else:
        deep_state = "unproven"
    gaps = c["gaps"]
    cov = dict(c["coverage"])
    return {
        "at": c["at"],
        "errors": list(c["errors"]),
        "server": c["server"],
        "batch_logs": c["batch_logs"],
        "store": {"source": db["source"], "size_bytes": db["size_bytes"],
                  "at": db["at"], "state": db["state"]},
        "scale": scale,
        "programs": programs,
        "programs_source": "func_knowledge (live), func_knowledge aggregate (deep columns)",
        "deep": {"state": deep_state, "at": deep.get("ts") or None,
                 "seconds": deep.get("seconds") or None,
                 "running": bool(deep.get("running")), "error": deep.get("error")},
        "coverage": cov,
        "gaps": {k: gaps.get(k) for k in
                 ("items", "counts", "unexplained", "total", "stray_dirs",
                  "source", "at", "error")},
    }


# --------------------------------------------------------------------------
# HTML sections
# --------------------------------------------------------------------------


def _server_section(c) -> str:
    srv, logs = c["server"], c["batch_logs"]
    if not srv["configured"]:
        status = tag("not configured", "warn")
        addr = "Ghidra server"
    else:
        addr = f'Ghidra server {esc(srv["host"])}:{srv["port"]}'
        status = tag("reachable", "ok") if srv["reachable"] else tag("unreachable", "dead")
    head = f'<div class="ptitle"><b>{addr}</b>{status}</div>'
    scanned, failed = logs["scanned"], logs["failed"]
    if not scanned:
        body = missing("no batch job logs under logs/bsim or logs/cexport yet")
    else:
        body = kv([
            ("Batch job logs on disk", fnum(scanned)),
            ("Logs recording a server failure",
             f'<span class="{"bad" if failed else "good"}">{fnum(failed)}</span>'),
            ("Share of jobs that lost the server", fpct(failed, scanned)),
        ])
        if logs["victims"]:
            body += ('<div class="log" style="max-height:150px">'
                     + esc("\n".join(logs["victims"])) + "</div>")
    note = ('<p class="sub" style="margin-top:10px">Both batch scripts resume by '
            'skipping work they think is already done. A dead server makes them '
            'exit clean with nothing produced and no error raised. Every job '
            'listed here finished that way. Check this box before trusting a '
            'bsim or C-export run.</p>')
    return panel(head + body + note)


def _scale_section(c) -> str:
    status_rows, status_err = c["status_rows"], c["status_err"]
    if status_err:
        return panel(missing(status_err))
    if not status_rows:
        return panel(missing("ingest_status is empty — run the knowledge ingest script"))
    done = sum(r[1] or 0 for r in status_rows)
    total = sum(r[2] or 0 for r in status_rows)
    seconds = sum(r[3] or 0.0 for r in status_rows)
    complete = sum(1 for r in status_rows if r[4])
    size = c["db"]["size_bytes"] or 0
    head = ('<div class="ptitle"><b>Cached knowledge</b>'
            + tag(f"{complete}/{len(status_rows)} programs complete",
                  "ok" if complete == len(status_rows) else "warn") + "</div>")
    body = donut(
        [("cached", done, "proven"), ("offered but not yet cached", max(0, total - done), "unproven")],
        total=total, title="Functions ingested vs offered",
    ) + kv([
        ("Functions cached", fnum(done)),
        ("Functions offered by the export", fnum(total)),
        ("Ingested", fpct(done, total)),
        ("Total ingest wall time", f"{seconds / 60:.0f} min"),
        ("Mean read rate", f"{done / seconds:,.0f} files/s" if seconds else "-"),
        (esc(c["db"]["source"] or "knowledge store"), f"{size / (1 << 30):.2f} GB"),
    ])
    note = (f'<p class="sub" style="margin-top:10px">{fnum(done)} per-function '
            f'JSON files, one per function, read once in a sequential walk. '
            f'Downstream tools now do one indexed lookup instead of one disk '
            f'seek per function.</p>')
    return panel(head + body + note)


def _coverage_section(c) -> str:
    cov = c["coverage"]
    program = cov.get("program")
    if not program:
        return missing(cov["error"])
    slug, err = cov["slug"], cov["error"]
    n_fun, n_unwind = cov["dump_functions"], cov["dump_unwind"]
    size, per_func, real = cov["dump_size_bytes"], cov["per_function"], cov["real_functions"]
    label = (f'<a href="{esc(_bin_href(slug))}">{esc(program)}</a>'
             if slug else esc(program))
    head = (f'<div class="ptitle"><b>Coverage: {label}</b>'
            + tag("why the export changed", "warn") + "</div>")
    if err:
        return panel(head + missing(err))
    entries = (n_fun or 0) + (n_unwind or 0)

    def _cov_state(part) -> str:
        try:
            frac = float(part or 0) / float(real) if real else 0.0
        except (TypeError, ValueError, ZeroDivisionError):
            frac = 0.0
        return "proven" if frac >= 0.9 else ("partial" if frac >= 0.5 else "failed")

    chart = bars(
        [("whole-program dump", n_fun or 0, _cov_state(n_fun)),
         ("per-function export", per_func or 0, _cov_state(per_func))],
        sort=False,
    )
    body = chart + _details(table(
        ["Export", "Entries", "Real functions", "Coverage"],
        [
            [f"whole-program C dump ({(size or 0) / (1 << 20):.0f} MB .c)",
             fnum(entries), fnum(n_fun), fpct(n_fun, real)],
            ["per-function ghidra_knowledge export",
             fnum(per_func), fnum(per_func), fpct(per_func, real)],
        ],
        numeric={1, 2, 3},
    ))
    body += kv([
        ("Functions in the corpus store",
         _clink(real, _fn_href(slug)) if slug else fnum(real)),
        ("Dump entries that are Unwind_* funclets, not functions",
         f"{fnum(n_unwind)} ({fpct(n_unwind, entries)})"),
    ])
    body += ('<p class="sub" style="margin-top:10px">The dump names every '
             'exception funclet as if it were a function. Strip those and most '
             'of the program was never covered at all.</p>')
    return panel(head + body)


def _programs_section(c) -> str:
    status_rows, status_err = c["status_rows"], c["status_err"]
    if status_err:
        return panel(missing(status_err))
    if not status_rows:
        return panel(missing("no ingested programs yet"))
    counts, snap, slugs = c["live"], c["deep"] or {}, c["slugs"]
    deep = snap.get("rows") or {}
    rows, chart_rows = [], []
    for prog, done, total, seconds, complete in status_rows:
        n_rows, named = counts.get(prog, (None, None))
        d = deep.get(prog)
        slug = slugs.get(str(prog))
        rows.append([
            f'<a href="{esc(_bin_href(slug))}">{esc(prog)}</a>' if slug else esc(prog),
            tag("done", "ok") if complete else tag("partial", "warn"),
            _clink(done, _fn_href(slug)) if slug else fnum(done),
            fnum(total),
            f"{(seconds or 0):.0f}s",
            f"{done / seconds:,.0f}/s" if seconds else "-",
            fnum(n_rows),
            _clink(named, _fn_href(slug, "&named=1")) if slug else fnum(named),
            fpct(named, n_rows),
            fnum(d[1]) if d else "-",
            fnum(d[2]) if d else "-",
            fnum(d[3]) if d else "-",
            fnum(d[4]) if d else "-",
        ])
        chart_rows.append((slug or prog, done or 0, "proven" if complete else "partial"))
    chart = bars(chart_rows, href_fn=lambda slug, *_: _bin_href(slug))
    head = ('<div class="ptitle"><b>Per-program knowledge</b>'
            + tag(f"{len(status_rows)} programs") + "</div>")
    body = chart + _details(table(
        ["Program", "Status", "Cached", "Offered", "Ingest", "Rate", "Rows",
         "Named", "Named %", "Decompiled", "Asm", "Instructions", "Refs"],
        rows, numeric=set(range(2, 13))))
    if snap.get("error"):
        note = missing(f"deep columns unavailable: {snap['error']}")
    elif snap.get("fresh"):
        note = (f'<p class="sub">Decompiled / asm / instruction / ref totals '
                f'measured {esc(ago(snap["ts"]))} in a single full pass over the '
                f'knowledge table ({snap["seconds"]:.0f}s). They are re-measured '
                f'only when the cache file changes.</p>')
    elif snap.get("running"):
        note = ('<p class="sub">Decompiled / asm / instruction / ref totals are '
                'being measured now — one full pass over the knowledge table, '
                'which takes about a minute on a cold disk. Everything else on '
                'this row is live.</p>')
    else:
        note = missing("deep totals not measured yet")
    if c["live_err"]:
        note += missing(c["live_err"])
    named_note = ('<p class="sub">Named = a function this build carries a real '
                  'name for. It varies by an order of magnitude between builds, '
                  'which is the reason all of them are merged instead of one.</p>')
    return panel(head + body + note + named_note)


def _gaps_section(c) -> str:
    g = c["gaps"]
    if g.get("error"):
        return panel(missing(g["error"]))
    rows, counts = [], g["counts"]
    tag_kind = {"proven": "ok", "partial": "warn", "failed": "dead", "missing": "dead"}
    for it in g["items"]:
        href = it["slug"]
        rows.append([
            f'<a href="{esc(_bin_href(href))}">{esc(it["repo_path"])}</a>'
            if href else esc(it["repo_path"]),
            tag(it["label"], tag_kind.get(GAP_STATE[it["key"]][1], "dead")),
            tag("excluded: encrypted", "warn") if it["excluded"] else "",
            _clink(it["cached"], _fn_href(it["slug"])) if (it["cached"] and it["slug"]) else "-",
        ])
    chart = stacked_bar([
        (GAP_STATE[k][0], counts[k], GAP_STATE[k][1]) for k in GAP_STATE])
    gaps = g["unexplained"]
    head = (f'<div class="ptitle"><b>Knowledge gaps across {g["total"]} binaries</b>'
            + tag(f"{gaps} unexplained gap{'s' if gaps != 1 else ''}",
                  "ok" if not gaps else "dead") + "</div>")
    body = chart + _details(table(["Binary", "Knowledge", "Note", "Functions cached"],
                                  rows, numeric={3}))
    if g["stray_dirs"]:
        body += ('<p class="sub" style="margin-top:8px">Export directories '
                 'the project database does not track: '
                 + esc(", ".join(g["stray_dirs"])) + "</p>")
    return panel(head + body)


# --------------------------------------------------------------------------


def _render() -> str:
    c = _collect()
    intro = ('<p class="sub">Every binary was reverse-engineered differently. '
             'The per-function export captures what Ghidra knows about each '
             'function — C, asm, instructions with bytes and relocations, '
             'calling convention, signature, file offset. This page tracks '
             'that knowledge landing in the corpus knowledge store.</p>')
    top = ('<div class="grid3">' + _server_section(c) + _scale_section(c)
           + _coverage_section(c) + "</div>")
    return intro + top + _programs_section(c) + _gaps_section(c)


def render() -> str:
    try:
        return _render()
    except Exception as exc:  # noqa: BLE001 - a panel must never break the page
        return panel(missing(f"knowledge panel failed: {type(exc).__name__}: {exc}"))
