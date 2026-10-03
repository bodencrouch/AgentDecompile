"""Source recovery: Ghidra C -> decomp-permuter -> byte-exact real C.

This panel reports the pipeline in `kx/permuter_harness.py` (run sampling) and
`scripts/compile_tally.py` (compile-failure census). There is no language model
in that loop: Ghidra emits C that behaves right but compiles to different bytes,
decomp-permuter mutates it, and a variant is kept only when its bytes equal the
original function's bytes.

Two properties are tracked separately everywhere on this page, because merging
them is what produced months of misleading results:

* `real_c`     -- the source contains no `__asm` / `naked` / `_emit` / `.byte`
* `byte_exact` -- the compiled bytes equal the original function's bytes

A byte-exact `__asm` shim is the original machine code copied into a C wrapper;
it recovers nothing. So the headline number here is always real-C AND byte-exact,
and any raw byte-exact count is labelled with how many asm shims it contains.

Every figure is read live from a file under `output/`. Nothing is cached and
nothing is hardcoded; a missing artifact is reported as missing.
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

if __package__ in (None, ""):
    # The dashboard loader puts the repo root on sys.path; this keeps the module
    # importable when it is exercised directly from a checkout instead.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agentdecompile_recovery.corpus.dashboard.panels.common import (  # noqa: E402
    ago,
    as_root,
    esc,
    fnum,
    fpct,
    load_json,
    missing,
    panel,
    query_db,
    table_exists,
    rel,
    table,
    tag,
)
from agentdecompile_recovery.corpus.dashboard.panels.viz import bars, donut, stacked_bar  # noqa: E402

try:  # count_link is landing in common.py from another author.
    from agentdecompile_recovery.corpus.dashboard.panels.common import count_link
except ImportError:  # the panel still renders, with plain links
    count_link = None


def _details(inner: str, summary: str = "raw numbers") -> str:
    """Collapsed-by-default expansion of a chart (10-relationship-layout.md
    Rule C: "a table is only ever the expansion of a visual, never a
    replacement" — visible on click, not open by default)."""
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


def _file_link(path: Path) -> str:
    return f'<a href="/artifact?p={esc(rel(path))}"><code>{esc(rel(path))}</code></a>'


def _slugs() -> dict[str, str]:
    """repo_path -> slug, so a sampled function's build is one click away."""
    rows, err = query_db("SELECT repo_path, slug FROM binary")
    return {} if err else {str(r[0]): str(r[1]) for r in rows}


def _build_links(repo_paths) -> str:
    slugs = _slugs()
    out = []
    for repo in repo_paths:
        slug = slugs.get(str(repo))
        out.append(f'<a href="{esc(_bin_href(slug))}">{esc(repo)}</a>' if slug
                   else esc(repo))
    return ", ".join(out) if out else "?"

TITLE = "Source recovery — Ghidra C → permuter → byte-exact"

# Artifact locations resolve through as_root() at call time, so a root that is
# set after import is still honoured. The run-file names are the harness's
# output names; AGENT_DECOMPILE_RECOVERY_RUN_FILES (comma list of paths
# relative to the root) overrides them for a differently laid-out checkout.
DEFAULT_RUN_FILES = ("output/permuter/sample_results.json",
                     "output/permuter/smoke_results.json")
DEFAULT_EXPERIMENT_DIRS = ("output/ladder", "output/ab_test")
COMPILE_TALLY_REL = "output/permuter/compile_tally.json"
COVERAGE_REL = "output/exact_universal/_coverage.json"
RECENT_LIMIT = 50
EXPERIMENT_LIMIT = 40


def _env_list(name: str, default: tuple) -> tuple:
    raw = os.environ.get(name, "")
    items = tuple(p.strip() for p in raw.split(",") if p.strip())
    return items or default


def _paths() -> dict:
    root = as_root()
    return {
        "root": root,
        "permuter": root / "output" / "permuter",
        "tally": root / COMPILE_TALLY_REL,
        "coverage": root / COVERAGE_REL,
        "runs": tuple(root / p for p in _env_list(
            "AGENT_DECOMPILE_RECOVERY_RUN_FILES", DEFAULT_RUN_FILES)),
        "experiments": tuple(root / p for p in _env_list(
            "AGENT_DECOMPILE_RECOVERY_EXPERIMENT_DIRS", DEFAULT_EXPERIMENT_DIRS)),
    }


# A run-results file carries every prompt, every attempt and every plugin
# payload, so it can reach hundreds of MB. Only the small `summary` object is
# needed here, and a huge file is skipped rather than parsed on a request path.
MAX_RESULT_BYTES = 32 << 20

ERR_CODE = re.compile(r"\b(C\d{4})\b")

# Outcome strings are assigned in kx/permuter_harness.py; the gloss is here so
# the page explains itself without the reader opening that file.
OUTCOME_GLOSS = {
    "ghidra_c_matched": "Ghidra's C already compiled to the original bytes",
    "permuter_matched": "a mutated variant compiled to the original bytes",
    "permuter_close": "permuter produced a variant, bytes still differ",
    "permuter_no_output": "permuter ran and produced nothing",
    "permuter_timeout": "permuter hit its time limit",
    "base_c_does_not_compile": "MSVC rejected the decompiled C, permuter never ran",
    "no_ghidra_c": "no decompiled C available for the function",
    "no_target_bytes": "original bytes could not be read",
}


def _band_key(band: str):
    head = str(band).split("-", 1)[0].strip()
    try:
        return (0, int(head))
    except ValueError:
        return (1, str(band))


def _mtime(path: Path):
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _safe(build, title: str) -> str:
    """One unreadable artifact must cost its own section, not the whole page."""
    try:
        return build()
    except Exception as exc:  # noqa: BLE001
        return panel(missing(f"could not build this section: {exc}"), title)


def _byte_exact(row: dict) -> bool:
    # A permuter-produced variant records `byte_exact`; an unmutated Ghidra body
    # records `base_byte_exact`. Either one is a byte match, and neither one on
    # its own says whether the source is real C.
    return bool(row.get("byte_exact") or row.get("base_byte_exact"))


def _real_c(row: dict) -> bool:
    if "real_c" in row:
        return bool(row.get("real_c"))
    return bool(row.get("base_real_c"))


def _fig(value, source, at, state, **extra) -> dict:
    """One figure: a value, where it came from, how fresh it is, and its state."""
    out = {"value": value, "source": source, "at": at, "state": state}
    out.update(extra)
    return out


def _absent(source) -> dict:
    return _fig(None, source, None, "missing")


def _int(v):
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _load_list(path: Path, errors: list):
    """(rows, mtime, state) for a JSON list artifact; problems go to *errors*."""
    mtime = _mtime(path)
    if mtime is None:
        return None, None, "missing"
    if _size(path) > MAX_RESULT_BYTES:
        errors.append(f"{rel(path)} is larger than {MAX_RESULT_BYTES >> 20} MB; skipped")
        return None, mtime, "excluded"
    data, err = load_json(path)
    if err:
        errors.append(err)
        return None, mtime, "failed"
    if not isinstance(data, list) or not data:
        errors.append(f"{rel(path)} holds no results")
        return None, mtime, "missing"
    return data, mtime, "ok"


def _collect_run(paths: dict, slugs: dict, errors: list) -> dict:
    dated = [(p, _mtime(p)) for p in paths["runs"]]
    dated = [(p, m) for p, m in dated if m is not None]
    if not dated:
        return {"state": "missing", "chosen": None, "candidates": 0,
                "wanted": [rel(p) for p in paths["runs"]]}
    chosen, mtime = max(dated, key=lambda pm: pm[1])
    rows, _m, state = _load_list(chosen, errors)
    base = {"chosen": chosen, "mtime": mtime, "candidates": len(dated),
            "state": "missing" if state != "ok" else "proven"}
    if state != "ok":
        base["load_state"] = state
        return base
    rows = [r for r in rows if isinstance(r, dict)]
    total = len(rows)
    recovered = sum(1 for r in rows if r.get("real_c_and_byte_exact"))
    byte_hits = sum(1 for r in rows if _byte_exact(r))
    bands: dict[str, list[int]] = {}
    outcomes: dict[str, int] = {}
    builds: dict[str, list[int]] = {}
    for r in rows:
        slot = bands.setdefault(str(r.get("band", "?")), [0, 0, 0])
        slot[0] += 1
        slot[1] += bool(r.get("real_c_and_byte_exact"))
        slot[2] += bool(_byte_exact(r))
        key = str(r.get("outcome", "?"))
        outcomes[key] = outcomes.get(key, 0) + 1
        if r.get("repo_path"):
            b = builds.setdefault(str(r["repo_path"]), [0, 0, 0])
            b[0] += 1
            b[1] += bool(r.get("real_c_and_byte_exact"))
            b[2] += bool(_byte_exact(r))
    recent = []
    for r in rows:
        if not r.get("real_c_and_byte_exact"):
            continue
        repo = r.get("repo_path")
        addr = r.get("addr", r.get("address"))
        recent.append({
            "slug": slugs.get(str(repo)) if repo else None,
            "repo_path": repo,
            "addr": addr if isinstance(addr, (int, str)) and not isinstance(addr, bool) else None,
            "name": r.get("name") or r.get("function") or None,
            "band": r.get("band"),
            "outcome": r.get("outcome"),
        })
    base.update({
        "total": total, "recovered": recovered, "byte_hits": byte_hits,
        "shims": max(0, byte_hits - recovered),
        "compiles": sum(1 for r in rows if r.get("base_compiles")),
        "real_c_src": sum(1 for r in rows if _real_c(r)),
        "seconds": sum(float(r.get("permuter_seconds") or 0) for r in rows),
        "bands": bands, "outcomes": outcomes, "builds": builds,
        # Result files list functions in run order; the newest are last.
        "recent": list(reversed(recent))[:RECENT_LIMIT],
        "recent_total": len(recent),
    })
    return base


def _collect_tally(paths: dict, errors: list) -> dict:
    path = paths["tally"]
    rows, mtime, state = _load_list(path, errors)
    out = {"path": path, "mtime": mtime, "state": state}
    if rows is None:
        return out
    rows = [r for r in rows if isinstance(r, dict)]
    total = len(rows)
    ok = sum(1 for r in rows if r.get("ok"))
    counts: dict[str, int] = {}
    examples: dict[str, str] = {}
    for r in rows:
        if r.get("ok"):
            continue
        errs = r.get("errors") or []
        seen = set()
        for line in errs:
            match = ERR_CODE.search(str(line))
            code = match.group(1) if match else "(no code)"
            seen.add(code)
            examples.setdefault(code, str(line))
        if not errs:
            seen.add("(no message captured)")
        for code in seen:
            counts[code] = counts.get(code, 0) + 1
    out.update({
        "total": total, "ok": ok, "failed": total - ok,
        "counts": counts, "examples": examples,
        "binaries": sorted({str(r["repo_path"]) for r in rows if r.get("repo_path")}),
        "sizes": [int(r["size"]) for r in rows if isinstance(r.get("size"), int)],
    })
    return out


def _collect_experiments(paths: dict) -> list[dict]:
    out: list[dict] = []
    for base in paths["experiments"]:
        if not base.is_dir():
            continue
        try:
            arms = sorted(p for p in base.iterdir() if p.is_dir())
        except OSError:
            continue
        for arm in arms:
            try:
                files = sorted(arm.glob("run-results-*.json"))
            except OSError:
                continue
            files = [f for f in files if 0 < _size(f) <= MAX_RESULT_BYTES]
            if not files:
                continue
            latest = max(files, key=lambda f: _mtime(f) or 0)
            data, err = load_json(latest)
            if err or not isinstance(data, dict):
                continue
            summary = data.get("summary")
            if not isinstance(summary, dict):
                continue
            manifest, _ = load_json(arm / "manifest.json")
            program = str(manifest.get("program") or "") if isinstance(manifest, dict) else ""
            config = data.get("config")
            model = str(config.get("model") or "") if isinstance(config, dict) else ""
            ms = summary.get("totalDurationMs")
            attempts = summary.get("avgAttempts")
            out.append({
                "name": f"{base.name} / {arm.name}",
                "program": program.rsplit("/", 1)[-1],
                "model": model,
                "prompts": _int(summary.get("totalPrompts")),
                "succeeded": _int(summary.get("successfulPrompts")),
                "avg_attempts": float(attempts) if isinstance(attempts, (int, float)) else None,
                "seconds": float(ms) / 1000 if isinstance(ms, (int, float)) else None,
                "source": rel(latest),
                "at": _mtime(latest),
            })
            if len(out) >= EXPERIMENT_LIMIT:
                return out
    return out


def _collect_db(errors: list) -> dict:
    """Corpus-wide and per-build real-C counts from recovered_function.real_c.

    real_c is the column kx/realc.py writes. It says nothing about bytes.
    """
    builds, err = query_db("SELECT id, slug, repo_path, game, platform, func_count "
                           "FROM binary ORDER BY slug", ignore_missing=True)
    if err:
        errors.append(err)
        builds = []
    present = table_exists("recovered_function")
    per: dict = {}
    allrow = (None, None)
    if present:
        rows, err = query_db("SELECT binary_id, COUNT(*) FROM recovered_function "
                             "WHERE real_c=1 GROUP BY binary_id", ignore_missing=True)
        if err:
            errors.append(err)
        per = {r[0]: r[1] or 0 for r in rows or []}
        rows, err = query_db("SELECT COUNT(*), COUNT(DISTINCT logical_id) "
                             "FROM recovered_function WHERE real_c=1", ignore_missing=True)
        if err:
            errors.append(err)
        allrow = tuple(rows[0]) if rows else (None, None)
    return {"builds": builds or [], "present": present, "per": per, "all": allrow,
            "unplaced": per.pop(None, 0)}


def _collect_coverage(paths: dict, errors: list) -> dict:
    """The ASM floor: assembly re-emitted per function. Never real C."""
    path = paths["coverage"]
    rows, mtime, state = _load_list(path, errors)
    by_repo = ({str(r.get("repo_path")): r for r in rows if isinstance(r, dict)}
               if rows else {})
    return {"path": path, "mtime": mtime, "state": state, "by_repo": by_repo}


def _db_mtime():
    try:
        from agentdecompile_recovery.corpus.dashboard.common import live_db
        target = live_db()
        return _mtime(Path(str(target))) if target else None
    except Exception:  # noqa: BLE001
        return None


def collect() -> dict:
    """Gather every fact once. render() and as_payload() both read this."""
    errors: list[str] = []
    paths = _paths()
    slugs = _slugs()
    return {
        "at": time.time(),
        "errors": errors,
        "paths": paths,
        "slugs": slugs,
        "run": _collect_run(paths, slugs, errors),
        "tally": _collect_tally(paths, errors),
        "experiments": _collect_experiments(paths),
        "db": _collect_db(errors),
        "coverage": _collect_coverage(paths, errors),
    }


# --------------------------------------------------------------------------
# Structured payload (no markup)
# --------------------------------------------------------------------------

def as_payload() -> dict:
    d = collect()
    run, tally, db, cov = d["run"], d["tally"], d["db"], d["coverage"]
    db_at = _db_mtime()
    db_src = "binary + recovered_function tables"
    run_src = rel(run["chosen"]) if run.get("chosen") else ", ".join(run.get("wanted", []))
    ran = run.get("state") == "proven"

    def run_fig(key, state="proven"):
        return (_fig(run[key], run_src, run["mtime"], state, of=run["total"])
                if ran else _absent(run_src))

    real_c = (_fig(db["all"][0], db_src, db_at, "partial" if db["all"][0] else "unproven",
                   logical=db["all"][1], unplaced=db["unplaced"])
              if db["present"] else _absent("recovered_function table"))
    asm_total = None
    if cov["by_repo"]:
        asm_total = sum(int(r.get("byte_exact") or 0) for r in cov["by_repo"].values()
                        if not r.get("excluded"))
    asm_floor = (_fig(asm_total, rel(cov["path"]), cov["mtime"], "partial",
                      note="assembly per function; not recovered C")
                 if asm_total is not None else _absent(rel(cov["path"])))

    builds = []
    for b in db["builds"]:
        bid, slug, repo = b[0], b[1], b[2]
        c = cov["by_repo"].get(str(repo)) or {}
        r = run.get("builds", {}).get(str(repo)) if ran else None
        excluded = bool(c.get("excluded"))
        rc = db["per"].get(bid, 0) if db["present"] else None
        builds.append({
            "slug": slug, "game": b[3] or "", "platform": b[4] or "",
            "func_count": b[5] or 0,
            "real_c": _fig(rc, db_src, db_at,
                           "missing" if rc is None else ("partial" if rc else "unproven")),
            "byte_exact": (_fig(r[1], run_src, run["mtime"], "proven" if r[1] else "unproven",
                                sampled=r[0], raw_byte_hits=r[2]) if r else _absent(run_src)),
            "asm_floor": (_fig(_int(c.get("byte_exact")), rel(cov["path"]), cov["mtime"],
                               "excluded" if excluded else "partial",
                               functions=_int(c.get("functions")), failed=_int(c.get("failed")))
                          if c else _absent(rel(cov["path"]))),
        })

    tstate = tally["state"]
    comp = _absent(rel(tally["path"]))
    if tstate == "ok":
        comp = _fig(tally["ok"], rel(tally["path"]), tally["mtime"],
                    "partial" if tally["ok"] else "failed",
                    of=tally["total"], failed=tally["failed"],
                    errors=[{"code": c, "functions": n, "example": tally["examples"].get(c, "")[:160]}
                            for c, n in sorted(tally["counts"].items(), key=lambda kv: (-kv[1], kv[0]))[:20]])
    elif tstate in ("failed", "excluded"):
        comp = _fig(None, rel(tally["path"]), tally["mtime"], tstate)

    run_block = {"state": run.get("state", "missing"), "source": run_src,
                 "at": run.get("mtime"), "candidates": run.get("candidates", 0)}
    if ran:
        run_block.update({
            "sampled": run["total"],
            "byte_exact_raw": run["byte_hits"],
            "byte_exact_shim_only": run["shims"],
            "seconds": round(run["seconds"], 1),
            "bands": [{"band": k, "sampled": v[0], "real_c_and_byte_exact": v[1],
                       "byte_exact_raw": v[2]}
                      for k, v in sorted(run["bands"].items(), key=lambda kv: _band_key(kv[0]))],
            "outcomes": [{"outcome": k, "functions": n, "gloss": OUTCOME_GLOSS.get(k, "")}
                         for k, n in sorted(run["outcomes"].items(), key=lambda kv: (-kv[1], kv[0]))],
        })

    recent = []
    if ran:
        recent = [dict(r, source=run_src, at=run["mtime"], state="proven") for r in run["recent"]]

    return {
        "at": d["at"],
        "errors": list(d["errors"]),
        # Four separate facts. Nothing below is a sum of another field.
        "real_c": real_c,
        "byte_exact": {
            "real_c_and_byte_exact": run_fig("recovered"),
            "sampled": run_fig("total"),
            "compiles_unmodified": run_fig("compiles", "partial"),
            "real_c_source_bodies": run_fig("real_c_src", "partial"),
        },
        "asm_floor": asm_floor,
        "compile": comp,
        "run": run_block,
        "builds": builds,
        "recent": recent,
        "recent_total": run.get("recent_total", 0) if ran else 0,
        "experiments": [dict(e, state="partial") for e in d["experiments"]],
    }


# --------------------------------------------------------------------------
# HTML (donor view)
# --------------------------------------------------------------------------

def _render_run(d: dict) -> str:
    run, slugs = d["run"], d["slugs"]
    title = "Real C and byte-exact, by size band"
    if run["state"] == "missing" and not run.get("chosen"):
        names = " or ".join(run["wanted"])
        return panel(missing(f"no permuter run recorded yet ({names} missing)"), title)
    if run["state"] != "proven":
        return panel(missing(f"{rel(run['chosen'])} holds no readable results"), title)

    chosen, mtime = run["chosen"], run["mtime"]
    total, recovered, byte_hits = run["total"], run["recovered"], run["byte_hits"]
    shims, compiles, real_c_src = run["shims"], run["compiles"], run["real_c_src"]
    bands, outcomes = run["bands"], run["outcomes"]
    binaries = sorted(run["builds"])

    band_rows = [
        [esc(band), fnum(s[0]), fnum(s[1]), fpct(s[1], s[0]), fnum(s[2])]
        for band, s in sorted(bands.items(), key=lambda kv: _band_key(kv[0]))
    ]
    band_rows.append([
        "<b>all</b>", f"<b>{fnum(total)}</b>", f"<b>{fnum(recovered)}</b>",
        f"<b>{fpct(recovered, total)}</b>", f"<b>{fnum(byte_hits)}</b>",
    ])
    outcome_rows = [
        [esc(name), fnum(count), fpct(count, total), esc(OUTCOME_GLOSS.get(name, ""))]
        for name, count in sorted(outcomes.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))
    slug = slugs.get(binaries[0]) if len(binaries) == 1 else ""
    recovered_cell = (
        _clink(recovered, _fn_href(slug, "&real_c=1"),
               title="every real-C body recovered in this build")
        if slug else fnum(recovered))
    shim_cell = (_clink(shims, _fn_href(slug, "&shim=1")) if slug and shims
                 else fnum(shims))
    shim_note = (f"includes {shim_cell} __asm/naked shim"
                 f"{'' if shims == 1 else 's'} — not recovered source"
                 if shims else "no __asm/naked shims in this sample")
    where = ", ".join(
        f'<a href="{esc(_bin_href(slugs[r]))}">{esc(r)}</a>' if slugs.get(r) else esc(r)
        for r in binaries) or "?"
    band_rows[-1][2] = f"<b>{recovered_cell}</b>"

    head = (
        f'<p class="headline">{recovered_cell} / {fnum(total)} sampled functions '
        f'real C <em>and</em> byte-exact '
        f'<span class="hl">({fpct(recovered, total)})</span></p>'
        f'<p class="sub">Source: {_file_link(chosen)} &middot; '
        f'written {esc(stamp)} ({esc(ago(mtime))}) &middot; '
        f'freshest of {fnum(run["candidates"])} run file(s) on disk.</p>'
        f'<p class="sub">Raw byte-exact (source not checked): '
        f'<b>{fnum(byte_hits)}</b> — {shim_note}. '
        f'Ghidra C compiled as-is for {fnum(compiles)} of {fnum(total)}; '
        f'{fnum(real_c_src)} bodies were free of asm. '
        f'Permuter time {run["seconds"]:,.1f}s. Binaries: {where}.</p>'
    )
    misleading_donut = donut(
        [("real C + byte exact", recovered, "proven"),
         ("byte-exact shim only (not real C)", shims, "partial"),
         ("not byte exact", max(0, total - byte_hits), "failed")],
        total=total, title="What the sample actually proved",
    )
    band_chart = bars(
        [(band, s[1], "proven") for band, s in
         sorted(bands.items(), key=lambda kv: _band_key(kv[0]))],
        sort=False,
    )
    outcome_chart = bars(
        [(name, count, "proven" if name in ("ghidra_c_matched", "permuter_matched")
          else "unproven") for name, count in outcomes.items()],
    )
    body = (
        head + misleading_donut
        + '<p class="sub" style="margin:14px 0 6px">Real C + byte-exact, per size '
          "band:</p>" + band_chart
        + _details(table(["Band (bytes)", "Sampled", "Real C + byte-exact", "Rate",
                          "Byte-exact incl. shims"], band_rows, numeric={1, 2, 3, 4}))
        + '<p class="sub" style="margin:14px 0 6px">Outcomes recorded by '
          '<code>kx/permuter_harness.py</code>:</p>' + outcome_chart
        + _details(table(["Outcome", "Functions", "Share", "Meaning"],
                         outcome_rows, numeric={1, 2}))
    )
    return panel(body, title)


def _render_tally(d: dict) -> str:
    t = d["tally"]
    title = "Raw compile rate (Ghidra C, unmodified)"
    if t["state"] != "ok":
        return panel(missing(f"{rel(t['path'])} is {t['state']}"), title)
    total, ok, failed, counts = t["total"], t["ok"], t["failed"], t["counts"]
    code_rows = [
        [esc(code), fnum(count), fpct(count, failed),
         f'<code>{esc(t["examples"].get(code, "")[:110])}</code>']
        for code, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    sizes = t["sizes"]
    span = (f"{fnum(min(sizes))}–{fnum(max(sizes))} bytes" if sizes else "size unknown")
    rate_class = "good" if total and ok / total >= 0.5 else "warnt"
    compile_split = stacked_bar([("compiles unmodified", ok, "proven"),
                                 ("fails to compile", failed, "failed")])
    error_chart = bars([(code, count, "failed") for code, count in counts.items()])
    body = (
        f'<p class="headline"><span class="{rate_class}">{fpct(ok, total)}</span> '
        f'of Ghidra C compiles unmodified</p>'
        f'<p class="sub">{fnum(ok)} of {fnum(total)} sampled functions '
        f'({esc(span)}) built against era-exact MSVC with no mutation. '
        f'{fnum(failed)} failed. This is the ceiling on what the permuter stage '
        f'ever gets to work on — it says nothing about byte-exactness.</p>'
        f'<p class="sub">Source: {_file_link(t["path"])} '
        f'({esc(ago(t["mtime"]))}) &middot; '
        + ", ".join(
            f'<a href="{esc(_bin_href(d["slugs"][r]))}">{esc(r)}</a>'
            if d["slugs"].get(r) else esc(r) for r in t["binaries"]) + '</p>'
        + compile_split
        + ('<p class="sub" style="margin:14px 0 6px">MSVC error codes blocking '
           "the failures, by how many functions each one blocks:</p>"
           + error_chart if counts else "")
        + _details(table(["MSVC error", "Functions blocked", "Share of failures",
                          "Example message"], code_rows, numeric={1, 2}))
    )
    return panel(body, title)


def _render_experiments(d: dict) -> str:
    rows = d["experiments"]
    if not rows:
        return ""
    chart = bars([(r["name"], r["succeeded"] or 0, "proven") for r in rows])
    table_rows = [[
        esc(r["name"]), esc(r["program"] or "?"), esc(r["model"] or "?"),
        fnum(r["prompts"]), fnum(r["succeeded"]), fpct(r["succeeded"], r["prompts"]),
        f'{r["avg_attempts"]:.2f}' if r["avg_attempts"] is not None else "-",
        f'{r["seconds"]:,.0f}s' if r["seconds"] is not None else "-",
        esc(ago(r["at"])),
    ] for r in rows]
    body = (
        '<p class="sub">Earlier model-loop experiments, read from each arm\'s '
        '<code>run-results-*.json</code> <code>summary</code> object. Their '
        '<code>success</code> flag is the runner\'s compile-and-diff verdict; it '
        'does not record the real-C check, so it is not comparable to the '
        'real-C-and-byte-exact rate above.</p>'
        + chart
        + _details(table(["Experiment", "Program", "Model", "Prompts", "Succeeded",
                          "Rate", "Avg attempts", "Wall time", "File age"],
                         table_rows, numeric={3, 4, 5, 6, 7}))
    )
    return panel(body, "Earlier experiments (model loop)")


def render() -> str:
    try:
        d = collect()
        parts = [
            _safe(lambda: _render_run(d), "Real C and byte-exact, by size band"),
            _safe(lambda: _render_tally(d), "Raw compile rate (Ghidra C, unmodified)"),
            _safe(lambda: _render_experiments(d), "Earlier experiments (model loop)"),
        ]
        note = (
            '<p class="sub" style="margin-bottom:14px">'
            + tag("no LLM in this loop", "ok")
            + ' Ghidra decompiles, decomp-permuter mutates, the era-exact '
              'compiler rebuilds, and a variant is kept only when its bytes '
              'match the original. <b>Byte-exact and real C are separate '
              'properties</b>: a byte-exact <code>__asm</code>/<code>naked</code>'
              ' body is the original machine code in a C wrapper and recovers '
              'nothing, so the headline metric is always both together.</p>'
        )
        return note + "".join(p for p in parts if p)
    except Exception as exc:  # noqa: BLE001
        return missing(f"recovery panel failed to render: {exc}")
