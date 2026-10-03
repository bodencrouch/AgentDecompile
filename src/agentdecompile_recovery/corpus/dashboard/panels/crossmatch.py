"""Cross-build identity layer and BSim: how a name in one build reaches the others.

Every number here is read live from the corpus database, the BSim directory, the
logs directory and the identity output directory. Nothing is cached here and
nothing is hardcoded to a project: roots come from the dashboard config helpers.

Two rules shape what this panel shows rather than what would look better:

1. Precision beats recall, so a count is never shown without the confidence or
   score that earned it. A large binding count is not a large trustworthy count,
   and the page must not let anyone read it that way.
2. The `func` table is large and often on an external disk. Nothing here touches
   it. Func-side denominators come from `binary.func_count`, a stored per-binary
   integer, and where that is not good enough the number is reported as
   unavailable instead of being bought with a minutes-long scan.

Identity (the same function bound across builds) and source propagation (reuse
candidates carried between builds) are separate facts. They are collected in
separate keys and their counts are never merged.

`_collect()` gathers the facts once. `render()` draws them as HTML and
`as_payload()` returns them as JSON-safe data, so the two cannot drift.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import quote

from agentdecompile_recovery.corpus.dashboard.panels.common import (
    DRM_EXCLUDED,
    esc,
    fnum,
    fpct,
    kv,
    load_json,
    missing,
    query_db,
    rel,
    table,
    tag,
)
from agentdecompile_recovery.corpus.dashboard.panels.viz import bars, donut, heatmap, stacked_bar
from agentdecompile_recovery.corpus.dashboard.common import as_root, live_db

try:  # count_link is landing in common.py from another author.
    from agentdecompile_recovery.corpus.dashboard.panels.common import count_link
except ImportError:  # the panel still renders, with plain links
    count_link = None

TITLE = "Cross-matching: bridging the builds"

# Relative locations under the dashboard root. The BSIM database and batch log
# names are discovered by pattern, because their file names are project choices.
_BSIM_REL = "bsim"
_JOB_LOGS_REL = ("logs", "bsim")
_LOGS_REL = "logs"
_REUSE_SUMMARY_REL = ("output", "identity", "identity_reuse_summary.json")
_REUSE_CANDIDATES_REL = ("output", "identity", "reuse_candidates.jsonl")
_MATCH_REPORT_REL = ("reports", "_gen_matches.md")
_MATCH_REPORT_ROW = re.compile(
    r"^\| `([^`]+)` \| `([^`]+)` \| [^|]+ \| ([\d,]+) \|", re.MULTILINE)

# A binding at or below this confidence is a lead, not an identification. The
# threshold exists so a weak method cannot hide inside a large row count.
TRUST_FLOOR = 0.70
STRONG_FLOOR = 0.90

# Markers the BSIM launcher prints. The launcher exits 0 on several of these,
# which is exactly why the batch log cannot be trusted on its own.
BSIM_FAILURES = (
    ("Connection to server failed", "Ghidra server unreachable"),
    ("Invalid Ghidra URL", "program URL did not resolve"),
    ("No signature files found", "job wrote no signature files"),
    ("contains no functions with signatures", "program had zero signable functions"),
)
BSIM_SUCCESS = "Writing signatures for"

_DB_TABLES_NOTE = "corpus database"


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def _root_join(*parts: str) -> Path:
    return as_root().joinpath(*parts)


def _mtime(path: Path | None) -> float | None:
    try:
        return path.stat().st_mtime if path is not None else None
    except OSError:
        return None


def _db_at() -> float | None:
    return _mtime(live_db())


def _human_bytes(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:,.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:,.1f} GB"


def _conf_state(avg) -> str:
    """Map a confidence average onto the page's verification-state vocabulary."""
    try:
        v = float(avg)
    except (TypeError, ValueError):
        return "unproven"
    if v >= STRONG_FLOOR:
        return "proven"
    if v >= TRUST_FLOOR:
        return "partial"
    return "failed"


def _num(v):
    """JSON-safe number: None stays None, floats are rounded."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return int(f) if f.is_integer() and not isinstance(v, float) else round(f, 4)


def _share(part, whole):
    try:
        return round(float(part) / float(whole), 4) if whole else None
    except (TypeError, ValueError):
        return None


def _bin_href(slug) -> str:
    return "/binary/" + quote(str(slug or ""), safe="")


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


def _file_link(path: Path) -> str:
    """Every artifact this panel quotes is one click from the number it fed."""
    return f'<a href="/artifact?p={esc(rel(path))}"><code>{esc(rel(path))}</code></a>'


def _conf(value) -> str:
    """Colour a confidence/score so a weak average cannot read as a strong one."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "-"
    cls = "good" if v >= STRONG_FLOOR else ("warnt" if v >= TRUST_FLOOR else "bad")
    return f'<span class="{cls}">{v:.3f}</span>'


def _details(inner: str, summary: str = "raw numbers") -> str:
    """Collapsed-by-default expansion of a chart: a table is the expansion of a
    visual, never a replacement."""
    return f'<details><summary>{esc(summary)}</summary>{inner}</details>'


def _read_log_lines(path: Path, nbytes: int = 1 << 20) -> list[str]:
    """Last nbytes of a log as lines."""
    try:
        with path.open("rb") as fh:
            size = fh.seek(0, os.SEEK_END)
            fh.seek(max(0, size - nbytes))
            data = fh.read()
        return [ln.rstrip() for ln in data.decode("utf-8", "replace").splitlines() if ln.strip()]
    except OSError:
        return []


def _count_lines(path: Path) -> int | None:
    """Newline count without parsing. The candidates file may be large."""
    try:
        total = 0
        with path.open("rb") as fh:
            while True:
                chunk = fh.read(1 << 20)
                if not chunk:
                    break
                total += chunk.count(b"\n")
        return total
    except OSError:
        return None


def _binaries() -> tuple[list[dict], str | None]:
    """One small query (a few dozen rows) shared by every section."""
    placeholders = ",".join("?" for _ in DRM_EXCLUDED)
    sql = "SELECT id, slug, repo_path, game, platform, func_count FROM binary"
    params: tuple = ()
    if DRM_EXCLUDED:
        sql += f" WHERE repo_path NOT IN ({placeholders})"
        params = tuple(DRM_EXCLUDED)
    rows, err = query_db(sql + " ORDER BY slug", params)
    if err:
        return [], err
    return [
        {"id": r[0], "slug": str(r[1]), "repo_path": str(r[2] or ""), "game": r[3] or "",
         "platform": r[4] or "", "func_count": r[5]}
        for r in rows
    ], None


# --------------------------------------------------------------------------
# fact collectors: one per section, each returns plain data
# --------------------------------------------------------------------------

def _logical_facts() -> dict:
    out = {"source": "table logical_function, identity", "at": _db_at(), "state": "missing",
           "error": None}
    totals, err = query_db(
        "SELECT COUNT(*), "
        "SUM(CASE WHEN source_file IS NOT NULL AND source_file <> '' THEN 1 ELSE 0 END) "
        "FROM logical_function"
    )
    if err or not totals:
        out["error"] = f"logical_function: {err or 'no rows returned'}"
        return out
    n_logical, n_src = totals[0][0] or 0, totals[0][1] or 0
    out.update(state="proven", total=n_logical, with_source_file=n_src,
               with_source_file_share=_share(n_src, n_logical))

    spread, s_err = query_db(
        "SELECT n, COUNT(*) FROM (SELECT logical_id, COUNT(DISTINCT binary_id) n "
        "FROM identity GROUP BY logical_id) GROUP BY n ORDER BY n"
    )
    out["spread_error"] = s_err
    if not s_err:
        order = ["1 build", "2 builds", "3-4 builds", "5-8 builds", "9+ builds"]
        counts = dict.fromkeys(order, 0)
        multi = 0
        for n, count in spread:
            if n <= 1:
                counts["1 build"] += count
            else:
                multi += count
                key = ("2 builds" if n == 2 else "3-4 builds" if n <= 4
                       else "5-8 builds" if n <= 8 else "9+ builds")
                counts[key] += count
        out["spread"] = [
            {"label": k, "count": counts[k], "share": _share(counts[k], n_logical),
             "state": "partial" if k == "1 build" else "proven"}
            for k in order
        ]
        out["multi_build"] = multi
        out["multi_build_share"] = _share(multi, n_logical)
        out["single_build"] = counts["1 build"]
        out["single_build_share"] = _share(counts["1 build"], n_logical)

    games, g_err = query_db(
        "SELECT ng, COUNT(*) FROM (SELECT i.logical_id, COUNT(DISTINCT b.game) ng "
        "FROM identity i JOIN binary b ON b.id = i.binary_id GROUP BY i.logical_id) "
        "GROUP BY ng ORDER BY ng"
    )
    out["cross_game_error"] = g_err
    if not g_err:
        cg = sum(c for ng, c in games if ng and ng > 1)
        out["cross_game"] = cg
        out["cross_game_share"] = _share(cg, n_logical)
    return out


def _identity_facts(binaries: list[dict], bins_err: str | None) -> dict:
    out = {"source": "table identity", "at": _db_at(), "state": "missing", "error": None}
    head, err = query_db(
        "SELECT COUNT(*), COUNT(DISTINCT binary_id || ':' || addr), COUNT(DISTINCT logical_id), "
        "COUNT(DISTINCT binary_id) FROM identity"
    )
    if err or not head:
        out["error"] = f"identity: {err or 'no rows returned'}"
        return out
    n_rows, n_addr, n_logical, n_bins = (head[0][0] or 0, head[0][1] or 0,
                                         head[0][2] or 0, head[0][3] or 0)
    out.update(state="proven", rows=n_rows, bound_addresses=n_addr, logical_ids=n_logical,
               binaries_with_bindings=n_bins)

    # Denominator: binary.func_count (a stored integer per binary), never func.
    total_funcs = total_bins = None
    if not bins_err and binaries:
        counts = [b["func_count"] for b in binaries if b["func_count"] is not None]
        total_funcs = sum(counts) if counts else None
        total_bins = len(binaries)
    out["total_functions"] = total_funcs
    out["bound_share"] = _share(n_addr, total_funcs) if total_funcs else None
    out["denominator_note"] = (
        None if total_funcs else
        "per-function bind rate unavailable: it needs a denominator from the large "
        "`func` table, which is too slow to scan on a page load")
    out["binaries_total"] = total_bins
    out["binaries_without_bindings"] = (total_bins - n_bins
                                        if total_bins and n_bins < total_bins else 0)

    methods, m_err = query_db(
        "SELECT method, COUNT(*), AVG(confidence), MIN(confidence), MAX(confidence) "
        "FROM identity GROUP BY method ORDER BY AVG(confidence) DESC"
    )
    out["methods_error"] = m_err
    out["trust_floor"] = TRUST_FLOOR
    if not m_err:
        out["methods"] = [
            {"method": m or "(null)", "count": c, "share": _share(c, n_rows),
             "avg_confidence": _num(avg), "min_confidence": _num(lo),
             "max_confidence": _num(hi), "state": _conf_state(avg),
             "lead_only": (avg or 0) < TRUST_FLOOR}
            for m, c, avg, lo, hi in methods
        ]
        weak = sum(c for _, c, avg, _, _ in methods if (avg or 0) < TRUST_FLOOR)
        out["weak_bindings"] = weak
        out["weak_share"] = _share(weak, n_rows)

    per_bin, p_err = query_db(
        "SELECT binary_id, COUNT(*), COUNT(DISTINCT logical_id) FROM identity GROUP BY binary_id")
    out["per_binary_error"] = p_err
    out["per_binary"] = {} if p_err else {r[0]: (r[1], r[2]) for r in per_bin}
    return out


_GATE = {
    "auto": ("accepted without review", "proven"),
    "verify": ("queued for verification", "partial"),
    "review": ("queued for human review", "partial"),
    "unresolved": ("no confident target", "failed"),
    "rejected": ("discarded", "failed"),
}


def _match_facts() -> dict:
    out = {"source": "table match", "at": _db_at(), "state": "missing", "error": None}
    rows, err = query_db(
        "SELECT status, COUNT(*), AVG(score), MIN(score), MAX(score) "
        "FROM match GROUP BY status ORDER BY COUNT(*) DESC"
    )
    if err or not rows:
        out["error"] = f"match: {err or 'no rows yet'}"
        return out
    total = sum(r[1] or 0 for r in rows)
    auto = sum(r[1] or 0 for r in rows if (r[0] or "") == "auto")
    needs = sum(r[1] or 0 for r in rows if (r[0] or "") in ("review", "verify"))
    out.update(
        state="partial", total=total, auto=auto, auto_share=_share(auto, total),
        awaiting_human=needs, awaiting_human_share=_share(needs, total),
        statuses=[
            {"status": s or "(null)", "count": c, "share": _share(c, total),
             "avg_score": _num(avg), "min_score": _num(lo), "max_score": _num(hi),
             "meaning": _GATE.get(s or "", ("", ""))[0],
             "state": _GATE.get(s or "", ("", "unproven"))[1]}
            for s, c, avg, lo, hi in rows
        ],
    )
    return out


def _bsim_paths() -> dict:
    bsim = _root_join(_BSIM_REL)
    db = None
    if bsim.is_dir():
        try:
            dbs = sorted(bsim.glob("*.mv.db"))
            db = dbs[0] if dbs else None
        except OSError:
            db = None
    batch = None
    logs = _root_join(_LOGS_REL)
    if logs.is_dir():
        try:
            cands = sorted(logs.glob("bsim*.log"), key=lambda p: p.stat().st_mtime)
            batch = cands[-1] if cands else None
        except OSError:
            batch = None
    return {"dir": bsim, "sigs": bsim / "sigs", "db": db, "batch": batch,
            "jobs": _root_join(*_JOB_LOGS_REL)}


def _bsim_facts(binaries: list[dict], bins_err: str | None) -> dict:
    p = _bsim_paths()
    slugs = [b["slug"] for b in binaries] if not bins_err else []
    # Same shape on every path: an absent BSim directory is "no build signed
    # yet", not a different payload the readers have to special-case.
    out = {"source": rel(p["dir"]), "at": _mtime(p["dir"]), "state": "missing", "error": None,
           "database": None, "signed": [], "empty": [], "errors": [],
           "covered": 0, "corpus_binaries": len(slugs), "covered_share": _share(0, len(slugs)),
           "lacking": list(slugs), "per_binary": {s: "unproven" for s in slugs}, "alias": {},
           "logs": {"state": "missing", "errors": [], "batch": None, "jobs": [], "by_cause": [],
                    "undercounted": False}}
    if not p["dir"].exists():
        out["error"] = f"not available yet ({rel(p['dir'])} missing)"
        return out

    if p["db"] is not None:
        try:
            st = p["db"].stat()
            out["database"] = {"source": rel(p["db"]), "at": st.st_mtime, "bytes": st.st_size,
                               "state": "proven"}
        except OSError as exc:
            out["database"] = {"source": rel(p["db"]), "at": None, "bytes": None,
                               "state": "failed", "error": f"unreadable: {exc}"}
    else:
        out["database"] = {"source": rel(p["dir"]), "at": None, "bytes": None,
                           "state": "missing", "error": "no BSim database file found"}

    if p["sigs"].exists():
        try:
            for entry in sorted(p["sigs"].iterdir()):
                if entry.is_dir():
                    (out["signed"] if any(entry.iterdir()) else out["empty"]).append(entry.name)
        except OSError as exc:
            out["errors"].append(f"could not list {rel(p['sigs'])}: {exc}")
    else:
        out["errors"].append(f"no signature sets yet ({rel(p['sigs'])} missing)")

    sset = set(out["signed"])
    eset = set(out["empty"])
    have = [s for s in slugs if s in sset]
    out["covered"] = len(have)
    out["corpus_binaries"] = len(slugs)
    out["covered_share"] = _share(len(have), len(slugs))
    out["lacking"] = [s for s in slugs if s not in sset]
    out["state"] = ("proven" if slugs and len(have) == len(slugs)
                    else "partial" if have else "unproven")
    out["per_binary"] = {
        s: ("proven" if s in sset else "failed" if s in eset else "unproven") for s in slugs}
    # Signature-set names that are not a build slug (names come from repo names).
    alias = {}
    for b in binaries:
        for key in (b["slug"], b["repo_path"], os.path.basename(b["repo_path"])):
            alias[key] = b["slug"]
    out["alias"] = alias
    out["logs"] = _bsim_log_facts(p)
    return out


def _bsim_log_facts(p: dict) -> dict:
    """Reconcile the batch log against the per-job logs. The launcher exits 0
    after a connection failure, so judge from the per-job logs."""
    out = {"state": "missing", "errors": [], "batch": None, "jobs": [], "by_cause": [],
           "undercounted": False}
    batch = p["batch"]
    ok = fail = skip = 0
    done = False
    if batch is not None and batch.exists():
        for line in _read_log_lines(batch):
            if line.startswith("[ok]"):
                ok += 1
            elif line.startswith("[FAIL]"):
                fail += 1
            elif line.startswith("[skip]"):
                skip += 1
            elif "BATCH DONE" in line:
                done = True
        out["batch"] = {"source": rel(batch), "at": _mtime(batch), "ok": ok, "fail": fail,
                        "skip": skip, "done_marker": done}
    else:
        out["errors"].append("not available yet (no BSIM batch log found under logs)")

    jobs = []
    if p["jobs"].is_dir():
        try:
            for log in sorted(p["jobs"].glob("*.log")):
                lines = _read_log_lines(log)
                blob = "\n".join(lines)
                hit = next(((m, why) for m, why in BSIM_FAILURES if m in blob), None)
                if hit:
                    marker, cause = hit
                    detail = next((ln for ln in reversed(lines) if marker in ln),
                                  next((ln for ln in reversed(lines) if "ERROR" in ln), cause))
                    state = "failed"
                elif BSIM_SUCCESS in blob:
                    cause, detail, state = "signatures written", "", "proven"
                else:
                    cause, detail, state = "no verdict in log", "", "unproven"
                jobs.append({"name": log.stem, "state": state, "cause": cause,
                             "line": detail[:240], "source": rel(log), "at": _mtime(log)})
        except OSError as exc:
            out["errors"].append(f"could not list {rel(p['jobs'])}: {exc}")
    elif batch is not None:
        out["errors"].append(f"per-job logs unavailable ({rel(p['jobs'])} missing)")

    out["jobs"] = jobs
    failed = [j for j in jobs if j["state"] == "failed"]
    out["passed"] = sum(1 for j in jobs if j["state"] == "proven")
    out["failed"] = len(failed)
    out["no_verdict"] = sum(1 for j in jobs if j["state"] == "unproven")
    if out["batch"] and len(failed) > out["batch"]["fail"]:
        out["undercounted"] = True
    by_cause: dict[str, int] = {}
    for j in failed:
        by_cause[j["cause"]] = by_cause.get(j["cause"], 0) + 1
    out["by_cause"] = [{"cause": c, "count": n} for c, n in
                       sorted(by_cause.items(), key=lambda kvp: -kvp[1])]
    out["newest_failure"] = max(failed, key=lambda j: j["at"] or 0) if failed else None
    if jobs:
        out["state"] = "failed" if failed else ("proven" if out["passed"] else "unproven")
    elif out["batch"]:
        out["state"] = "unproven"
    return out


def _reuse_facts() -> dict:
    """Source propagation: reuse candidates carried between builds. Not identity."""
    summary = _root_join(*_REUSE_SUMMARY_REL)
    cands = _root_join(*_REUSE_CANDIDATES_REL)
    out = {"source": rel(summary), "at": _mtime(summary), "state": "missing", "error": None,
           "candidates_file": None}
    data, err = load_json(summary)
    if err:
        out["error"] = err
    elif not isinstance(data, dict):
        out["error"] = f"{rel(summary)} is not a JSON object"
    else:
        scanned = data.get("recovered_functions_scanned")
        exact = data.get("recovered_byte_exact")
        no_id = data.get("recovered_without_identity")
        rows = data.get("reuse_rows")
        high = data.get("high_confidence_rows")
        same = data.get("same_size_rows")
        out.update(
            scanned=_num(scanned), byte_exact=_num(exact), without_identity=_num(no_id),
            reuse_rows=_num(rows), high_confidence=_num(high), same_size=_num(same),
        )
        out["state"] = ("proven" if rows else "unproven" if scanned else "missing")
        out["no_candidates"] = bool(scanned and not (rows or 0))
        out["no_candidates_reason"] = (
            ("all scanned recovered functions are bound to no logical id"
             if no_id and no_id == scanned else
             "no recovered function cleared the reuse test")
            if out["no_candidates"] else None)
    if cands.exists():
        try:
            size = cands.stat().st_size
        except OSError:
            size = 0
        out["candidates_file"] = {
            "source": rel(cands), "at": _mtime(cands), "bytes": size,
            "rows": None if not size else _count_lines(cands),
            "state": "unproven" if not size else "proven"}
    else:
        out["candidates_file"] = {"source": rel(cands), "at": None, "bytes": None,
                                  "rows": None, "state": "missing",
                                  "error": f"not available yet ({rel(cands)} missing)"}
    return out


def _matrix_facts(binaries: list[dict], bins_err: str | None) -> dict:
    """Build x build candidate pairings. Read from the offline matcher's bounded
    summary so a cache miss does not regroup the whole match table."""
    report = _root_join(*_MATCH_REPORT_REL)
    out = {"source": rel(report), "at": _mtime(report), "state": "missing", "error": None}
    try:
        text = report.read_text(encoding="utf-8")
    except OSError as exc:
        out["error"] = f"match matrix summary unavailable ({rel(report)}: {exc})"
        return out
    pairs: dict[tuple[str, str], int] = {}
    for src, dst, count in _MATCH_REPORT_ROW.findall(text):
        pairs[(src, dst)] = pairs.get((src, dst), 0) + int(count.replace(",", ""))
    if not pairs:
        out["error"] = f"match matrix summary has no rows ({rel(report)})"
        return out
    if bins_err:
        out["error"] = f"binary slugs: {bins_err}"
        return out
    aliases: dict[str, str] = {}
    for b in binaries:
        short = b["slug"].split("__", 1)[-1]
        for key in (b["slug"], short, b["repo_path"], os.path.basename(b["repo_path"])):
            aliases[key] = b["slug"]
    cells: dict[tuple[str, str], int] = {}
    for (src, dst), count in pairs.items():
        key = (aliases.get(src, src), aliases.get(dst, dst))
        cells[key] = cells.get(key, 0) + count
    rows = sorted({r for r, _ in cells})
    cols = sorted({c for _, c in cells})
    known = {b["slug"] for b in binaries}
    values = [[cells.get((r, c), 0) for c in cols] for r in rows]
    out.update(
        state="partial", rows=rows, cols=cols, values=values,
        max=max((v for row in values for v in row), default=0),
        total=sum(cells.values()),
        row_totals=[sum(row) for row in values],
        col_totals=[sum(values[i][j] for i in range(len(rows))) for j in range(len(cols))],
        unknown_slugs=sorted((set(rows) | set(cols)) - known),
        meaning="candidate pairings, not identities")
    return out


def _collect() -> dict:
    """Gather every figure once. Both render() and as_payload() read this."""
    binaries, bins_err = _binaries()
    errors: list[str] = []
    if bins_err:
        errors.append(f"binary: {bins_err}")
    facts = {
        "binaries_list": binaries,
        "binaries_error": bins_err,
        "logical": _logical_safe(_logical_facts),
        "identity": _logical_safe(lambda: _identity_facts(binaries, bins_err)),
        "match": _logical_safe(_match_facts),
        "bsim": _logical_safe(lambda: _bsim_facts(binaries, bins_err)),
        "reuse": _logical_safe(_reuse_facts),
        "matrix": _logical_safe(lambda: _matrix_facts(binaries, bins_err)),
    }
    for key in ("logical", "identity", "match", "bsim", "reuse", "matrix"):
        f = facts[key]
        if f.get("error"):
            errors.append(f"{key}: {f['error']}")
    facts["errors"] = errors
    return facts


def _logical_safe(fn) -> dict:
    """A section must degrade, never raise."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        return {"state": "failed", "error": f"section failed: {type(exc).__name__}: {exc}",
                "source": "", "at": None}


# --------------------------------------------------------------------------
# payload
# --------------------------------------------------------------------------

def as_payload() -> dict:
    """Structured facts for the workbench. No markup; numbers are numbers."""
    f = _collect()
    lg, idn, mt, bs, ru, mx = (f["logical"], f["identity"], f["match"], f["bsim"],
                               f["reuse"], f["matrix"])

    def keep(d: dict, drop: tuple = ()) -> dict:
        return {k: v for k, v in d.items() if k not in drop}

    identity = keep(idn, ("per_binary",))
    bsim = keep(bs, ("alias", "signed", "empty", "lacking", "per_binary"))
    if "signed" in bs:
        bsim["signature_sets"] = (
            [{"name": n, "slug": bs["alias"].get(n, ""), "state": "proven"} for n in bs["signed"]]
            + [{"name": n, "slug": bs["alias"].get(n, ""), "state": "failed",
                "note": "job created the directory and produced nothing"} for n in bs["empty"]])
        bsim["lacking_slugs"] = bs["lacking"]

    per_ident = idn.get("per_binary") or {}
    per_bsim = bs.get("per_binary") or {}
    row_idx = {s: i for i, s in enumerate(mx.get("rows") or [])}
    col_idx = {s: i for i, s in enumerate(mx.get("cols") or [])}
    binaries = []
    for b in f["binaries_list"]:
        bound = per_ident.get(b["id"])
        slug = b["slug"]
        binaries.append({
            "slug": slug,
            "game": b["game"],
            "platform": b["platform"],
            "func_count": _num(b["func_count"]),
            "identity_bindings": _num(bound[0]) if bound else None,
            "identity_logical_ids": _num(bound[1]) if bound else None,
            "identity_state": ("missing" if idn.get("per_binary_error") or not idn.get("per_binary")
                               and idn.get("state") != "proven" else
                               "proven" if bound else "unproven"),
            "bsim_state": per_bsim.get(slug, "missing" if not per_bsim else "unproven"),
            "match_as_source": _num(mx["row_totals"][row_idx[slug]]) if slug in row_idx else None,
            "match_as_target": _num(mx["col_totals"][col_idx[slug]]) if slug in col_idx else None,
        })

    return {
        "at": _db_at(),
        "errors": list(f["errors"]),
        "slug_key": "slug",
        "logical": keep(lg),
        "identity": identity,
        "matches": keep(mt),
        "bsim": bsim,
        "propagation": keep(ru),
        "matrix": keep(mx),
        "binaries": binaries,
        "notes": {
            "identity_vs_propagation": (
                "identity counts bindings of one function across builds; propagation counts "
                "reuse candidates carried between builds. They are separate and never summed."),
            "trust_floor": TRUST_FLOOR,
        },
    }


# --------------------------------------------------------------------------
# HTML sections, drawn from the collected facts
# --------------------------------------------------------------------------

def _explainer() -> str:
    return (
        '<p class="note">A <b>logical function</b> is an address-independent identity. The same '
        "function sits at a different address in every build, but all of those addresses bind to "
        "a single logical id. That binding is the whole point: a name, signature or recovered "
        "body written once against one build propagates to every other build that shares the "
        "logical id, instead of being re-derived for each.</p>"
        '<p class="note">The <code>identity</code> table holds those bindings '
        "(logical id &rarr; binary + address, with a method and a confidence). The "
        "<code>match</code> table holds candidate pairings that have not yet become identities. "
        "<b>Read both with their confidence attached</b>: the honest number is always smaller "
        "than the row count.</p>"
    )


def _logical_section(f: dict) -> str:
    lg = f["logical"]
    if lg.get("error"):
        return missing(lg["error"])
    n = lg["total"]
    pairs = [
        ("logical functions", fnum(n)),
        ("with a source_file attributed",
         f"{fnum(lg['with_source_file'])} &middot; {fpct(lg['with_source_file'], n)}"),
    ]
    if "spread" in lg:
        pairs.append(("reach 2+ builds (actually bridge)",
                      f'<span class="good">{fnum(lg["multi_build"])}</span> &middot; '
                      f'{fpct(lg["multi_build"], n)}'))
        pairs.append(("reach exactly 1 build (bridge nothing)",
                      f'<span class="warnt">{fnum(lg["single_build"])}</span> &middot; '
                      f'{fpct(lg["single_build"], n)}'))
    if "cross_game" in lg:
        pairs.append(("cross a game boundary",
                      f"{fnum(lg['cross_game'])} &middot; {fpct(lg['cross_game'], n)}"))
    out = [kv(pairs)]
    if lg.get("spread_error"):
        out.append(missing(f"build-spread histogram unavailable: {lg['spread_error']}"))
    else:
        out.append(bars([(s["label"], s["count"], s["state"]) for s in lg["spread"]], sort=False))
        rows = [[s["label"], fnum(s["count"]), fpct(s["count"], n)] for s in lg["spread"]]
        out.append(_details(table(["builds reached", "logical functions", "share"],
                                  rows, numeric={1, 2})))
        nine = next((s["count"] for s in lg["spread"] if s["label"] == "9+ builds"), 0)
        out.append(
            '<p class="note">Reach is the payoff multiplier. A name written against one of the '
            f'{fnum(nine)} logical functions that reach nine or more builds lands in all of them '
            "at once; a name written against a single-build logical function lands once.</p>")
    return "".join(out)


def _identity_section(f: dict) -> str:
    idn = f["identity"]
    if idn.get("error"):
        return missing(idn["error"])
    n_rows = idn["rows"]
    pairs = [
        ("identity rows", fnum(n_rows)),
        ("distinct (binary, addr) bound", _clink(idn["bound_addresses"], "/functions?bound=1")),
        ("distinct logical ids covered", fnum(idn["logical_ids"])),
        ("binaries with at least one binding", fnum(idn["binaries_with_bindings"])),
    ]
    if idn.get("total_functions"):
        pairs.append(("bound share of all functions (binary.func_count sum)",
                      f"{fpct(idn['bound_addresses'], idn['total_functions'])} of "
                      f"{fnum(idn['total_functions'])}"))
    if idn.get("binaries_without_bindings"):
        pairs.append(("binaries with no bindings",
                      f'<span class="warnt">{fnum(idn["binaries_without_bindings"])}</span>'))
    out = [kv(pairs)]
    if idn.get("denominator_note"):
        out.append(missing(idn["denominator_note"]))
    if idn.get("methods_error"):
        out.append(missing(f"identity method breakdown unavailable: {idn['methods_error']}"))
        return "".join(out)
    ms = idn["methods"]
    out.append(bars([(m["method"], m["count"], m["state"]) for m in ms], href_fn=None))
    rows = []
    for m in ms:
        badge = " " + tag("lead only", "warn") if m["lead_only"] else ""
        rows.append([
            esc(m["method"]) + badge, fnum(m["count"]), fpct(m["count"], n_rows),
            _conf(m["avg_confidence"]),
            f"{(m['min_confidence'] or 0):.2f}&ndash;{(m['max_confidence'] or 0):.2f}",
        ])
    out.append(_details(table(
        ["method", "bindings", "share", "avg confidence", "range"], rows,
        numeric={1, 2, 3, 4})))
    out.append(
        f'<p class="note"><b>{fnum(idn["weak_bindings"])} of {fnum(n_rows)} bindings '
        f'({fpct(idn["weak_bindings"], n_rows)}) come from methods whose average confidence is '
        f"below {TRUST_FLOOR:.2f}.</b> Those are candidate leads carried in the same table as "
        "identifications, not identifications. The <code>name-*</code> methods bind on name "
        "evidence; the <code>match:*</code> methods are promotions out of the matcher, and carry "
        "its score forward.</p>")
    return "".join(out)


def _match_section(f: dict) -> str:
    mt = f["match"]
    if mt.get("error"):
        return missing(mt["error"])
    total, auto, needs = mt["total"], mt["auto"], mt["awaiting_human"]
    tbl = []
    for s in mt["statuses"]:
        kind = {"proven": "ok", "partial": "warn", "failed": "dead"}.get(s["state"], "")
        count_cell = _clink(s["count"], "/review") if s["status"] == "review" else fnum(s["count"])
        tbl.append([
            esc(s["status"]) + (" " + tag(s["meaning"], kind) if s["meaning"] else ""),
            count_cell, fpct(s["count"], total), _conf(s["avg_score"]),
            f"{(s['min_score'] or 0):.2f}&ndash;{(s['max_score'] or 0):.2f}",
        ])
    return "".join([
        stacked_bar([(s["status"], s["count"], s["state"]) for s in mt["statuses"]]),
        kv([
            ("match rows", fnum(total)),
            ("auto-accepted (no human needed)",
             f'<span class="good">{fnum(auto)}</span> &middot; {fpct(auto, total)}'),
            ("still awaiting a human",
             f'<span class="warnt">{_clink(needs, "/review")}</span> &middot; '
             f"{fpct(needs, total)}"),
        ]),
        _details(table(["status", "matches", "share", "avg score", "range"], tbl,
                       numeric={1, 2, 3, 4})),
        '<p class="note"><b>The largest bucket is not the trustworthy one.</b> Only '
        f"{fnum(auto)} matches ({fpct(auto, total)}) cleared the bar to be accepted without a "
        f'human; {fnum(needs)} sit in <a href="/review">review</a> or verify queues. A high '
        "average score inside a review bucket does not promote it.</p>",
    ])


def _bsim_section(f: dict) -> str:
    bs = f["bsim"]
    out = [
        '<p class="note">BSim is a structural function-similarity index: it decompiles each '
        "function, reduces it to a feature vector, and finds near neighbours in other programs. "
        "A signature set per binary is a prerequisite for any all-pairs cross-query.</p>"]
    if bs.get("error"):
        return "".join(out) + missing(bs["error"])
    for e in bs["errors"]:
        out.append(missing(e))
    db = bs["database"]
    if db.get("bytes") is not None:
        db_line = f"{_human_bytes(db['bytes'])} &middot; {_file_link(_bsim_paths()['db'])}"
    elif db.get("state") == "failed":
        db_line = f'<span class="bad">{esc(db.get("error"))}</span>'
    else:
        db_line = f'<span class="warnt">absent ({esc(db["source"])})</span>'
    pairs = [("BSim database", db_line), ("signature sets with content", fnum(len(bs["signed"])))]
    if bs["empty"]:
        pairs.append(("signature dirs created but empty",
                      f'<span class="bad">{fnum(len(bs["empty"]))}</span>'))
    total = bs["corpus_binaries"]
    if total:
        pairs.append(("corpus binaries covered",
                      f'<span class="{"good" if bs["covered"] == total else "warnt"}">'
                      f'{fnum(bs["covered"])}</span> of {fnum(total)} &middot; '
                      f'{fpct(bs["covered"], total)}'))
        out.append(donut(
            [("signatures present", bs["covered"], "proven"),
             ("no signatures yet", total - bs["covered"], "unproven")],
            total=total, title="BSim signature coverage"))
    out.append(kv(pairs))

    def name_cell(name: str) -> str:
        slug = bs["alias"].get(name, "")
        return f'<a href="{esc(_bin_href(slug))}">{esc(name)}</a>' if slug else esc(name)

    if bs["signed"] or bs["empty"]:
        srows = [[name_cell(n), tag("signatures present", "ok")] for n in bs["signed"]]
        srows += [[name_cell(n), tag("empty: job produced nothing", "dead")] for n in bs["empty"]]
        out.append(_details(table(["signature set", "state"], srows)))
    if bs["lacking"]:
        out.append(
            f'<p class="note"><b>{fnum(len(bs["lacking"]))} corpus binaries have no BSim '
            "signatures</b>, so they cannot take part in any cross-query: "
            + ", ".join(f'<a href="{esc(_bin_href(s))}"><code>{esc(s)}</code></a>'
                        for s in bs["lacking"]) + ".</p>")
    return "".join(out) + _bsim_logs_html(bs["logs"])


def _bsim_logs_html(lg: dict) -> str:
    out = [missing(e) for e in lg["errors"]]
    batch, jobs = lg["batch"], lg["jobs"]
    if not jobs and not batch:
        return "".join(out)
    pairs = []
    if batch:
        pairs.append((
            f"{batch['source']} says",
            f"ok {fnum(batch['ok'])} &middot; fail {fnum(batch['fail'])} &middot; "
            f"skip {fnum(batch['skip'])}"
            + ("" if batch["done_marker"] else ' &middot; <span class="warnt">no BATCH DONE line</span>')
            + f' &middot; <a href="/artifact?p={esc(batch["source"])}"><code>{esc(batch["source"])}</code></a>'))
    if jobs:
        pairs.append(("per-job logs inspected", fnum(len(jobs))))
        pairs.append(("jobs that wrote signatures", f'<span class="good">{fnum(lg["passed"])}</span>'))
        pairs.append(("jobs that failed",
                      f'<span class="{"bad" if lg["failed"] else "good"}">{fnum(lg["failed"])}</span>'))
        if lg["no_verdict"]:
            pairs.append(("jobs with no verdict",
                          f'<span class="warnt">{fnum(lg["no_verdict"])}</span>'))
    out.append(kv(pairs))
    failed = [j for j in jobs if j["state"] == "failed"]
    if failed:
        if lg["undercounted"]:
            out.append(
                f'<p class="note"><b class="bad">The batch log undercounts failures: it records '
                f'{fnum(batch["fail"])}, the per-job logs show {fnum(lg["failed"])}.</b> The BSim '
                "launcher exits 0 after a connection failure, so the batch script marks those jobs "
                "ok. Judge a run from the per-job logs.</p>")
        out.append(bars([(c["cause"], c["count"], "failed") for c in lg["by_cause"]]))
        out.append(_details(table(["failure cause", "jobs"],
                                  [[esc(c["cause"]), fnum(c["count"])] for c in lg["by_cause"]],
                                  numeric={1})))
        nf = lg["newest_failure"]
        out.append(f'<p class="note">Most recent failure &mdash; <code>{esc(nf["name"])}</code>: '
                   f'<span class="bad">{esc(nf["line"])}</span></p>')
        out.append(_details(table(
            ["failed job", "cause", "log line"],
            [[f'<a href="/artifact?p={esc(j["source"])}"><code>{esc(j["source"])}</code></a>',
              esc(j["cause"]), esc(j["line"][:150])]
             for j in sorted(failed, key=lambda j: -(j["at"] or 0))]),
            "per-job failure log lines"))
    elif jobs:
        out.append(f'<p class="note">All {fnum(lg["passed"])} inspected jobs wrote signatures.</p>')
    return "".join(out)


def _reuse_section(f: dict) -> str:
    ru = f["reuse"]
    out = [
        '<p class="note">The concrete payoff of cross-matching: a function whose C body was '
        "verified byte-exact in one build, carried into another build through its logical id. "
        "This is source propagation. It is counted apart from identity above.</p>"]
    if ru.get("error"):
        out.append(missing(ru["error"]))
    else:
        rows, high = ru.get("reuse_rows"), ru.get("high_confidence")
        pairs = [("recovered functions scanned", fnum(ru.get("scanned"))),
                 ("byte-exact in their own build", fnum(ru.get("byte_exact")))]
        if ru.get("without_identity") is not None:
            cls = "bad" if ru["without_identity"] else "good"
            pairs.append(("recovered but bound to no logical id",
                          f'<span class="{cls}">{fnum(ru["without_identity"])}</span>'))
        pairs.append(("reuse candidates emitted",
                      f'<span class="{"good" if (rows or 0) else "warnt"}">{fnum(rows)}</span>'))
        if high is not None:
            pairs.append(("of those, high confidence", fnum(high)))
        if ru.get("same_size") is not None:
            pairs.append(("of those, same size in the target build", fnum(ru["same_size"])))
        summary = _root_join(*_REUSE_SUMMARY_REL)
        pairs.append(("read from", _file_link(summary)))
        if rows:
            out.append(stacked_bar([("high confidence", high or 0, "proven"),
                                    ("lower confidence", max(0, rows - (high or 0)), "partial")]))
        out.append(kv(pairs))
        if ru.get("no_candidates"):
            out.append(
                '<p class="note"><b class="bad">No reuse candidates yet.</b> '
                f"{fnum(ru['scanned'])} recovered functions were scanned and "
                f"{fnum(ru.get('byte_exact'))} are byte-exact, but {esc(ru['no_candidates_reason'])}."
                " With no identity there is no second build to carry the body into.</p>")
        elif rows:
            out.append(
                f'<p class="note">{fnum(high)} of {fnum(rows)} candidates are high confidence '
                f"({fpct(high or 0, rows)}). Judge the payoff by that column, not by the "
                "candidate count.</p>")
    cf = ru.get("candidates_file") or {}
    path = _root_join(*_REUSE_CANDIDATES_REL)
    if cf.get("state") == "missing":
        out.append(missing(cf.get("error") or f"not available yet ({rel(path)} missing)"))
    else:
        out.append(kv([(rel(path),
                        ("empty file" if not cf.get("bytes")
                         else f"{fnum(cf.get('rows'))} rows &middot; {_human_bytes(cf['bytes'])}")
                        + " &middot; " + _file_link(path))]))
    return "".join(out)


def _matrix_section(f: dict) -> str:
    mx = f["matrix"]
    if mx.get("error"):
        return missing(mx["error"])
    chart = heatmap(mx["values"], mx["rows"], mx["cols"],
                    href_fn=lambda r, *_: _bin_href(r))
    report = _root_join(*_MATCH_REPORT_REL)
    note = (
        f'<p class="note">Density from the offline summary {_file_link(report)}: '
        f"{fnum(len(mx['rows']))} builds queried as a source against {fnum(len(mx['cols']))} "
        "builds that have appeared as a target. These are candidate pairings, not identities; "
        "see the match queue for how many clear the bar. A binary missing from the row axis has "
        "not been run as a source yet; one missing from the column axis has never been matched "
        "against.</p>")
    return chart + note


_SECTIONS = (
    ("What a logical function is", lambda f: _explainer()),
    ("Cross-match density: build x build (table `match`)", _matrix_section),
    ("Logical functions: the address-independent layer", _logical_section),
    ("Identity bindings: logical id to a real address", _identity_section),
    ("Match queue: candidates that are not identities yet", _match_section),
    ("BSim: structural similarity index", _bsim_section),
    ("Reuse: what cross-matching bought", _reuse_section),
)


def render() -> str:
    f = _collect()
    parts = []
    for heading, fn in _SECTIONS:
        try:
            body = fn(f)
        except Exception as exc:  # noqa: BLE001 - a panel must degrade, never raise
            body = missing(f"section failed: {type(exc).__name__}: {exc}")
        parts.append(
            f'<div class="panel"><div class="ptitle"><b>{esc(heading)}</b></div>{body}</div>')
    return "".join(parts)
