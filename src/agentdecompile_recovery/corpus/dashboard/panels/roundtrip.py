"""Rebuild proof: whole-file roundtrip, byte-exact emission, and export packages.

Two different claims live on this page and they must never be confused:

  * BYTE-EXACT (this panel) means the emitter can reproduce the original machine
    code. A function counted here is shipped as `__declspec(naked)` / `.byte`
    shims — original opcodes wrapped in C. It proves the byte mapping and the
    emitter are correct. It is NOT decompilation and NOT recovered source: no
    control flow, no types, no expressions were recovered for these counts.
  * RECOVERED SOURCE means real, readable C reconstructed from the binary. It is
    a much smaller number and a different panel owns it.

Quoting the byte-exact figure as "decompilation progress" would be a lie, so
every surface here is labelled at the point the number appears, not in a
footnote someone can scroll past.

All figures are read live from artifacts on disk; nothing is hardcoded.
"""

from __future__ import annotations

import time

from datetime import datetime, timezone
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
    panel,
    query_db,
    rel,
    table,
    tag,
    tail_lines,
)
from agentdecompile_recovery.corpus.dashboard.panels.viz import bars, stacked_bar

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


def _file_link(path: Path) -> str:
    return f'<a href="/artifact?p={esc(rel(path))}"><code>{esc(rel(path))}</code></a>'


def _slugs() -> dict[str, str]:
    """repo_path -> slug. Every manifest here keys its rows on repo_path."""
    rows, err = query_db("SELECT repo_path, slug FROM binary")
    return {} if err else {str(r[0]): str(r[1]) for r in rows}


def _bin_cell(repo, slugs) -> str:
    slug = slugs.get(str(repo))
    if not slug:
        return esc(repo or "?")
    return f'<a href="{esc(_bin_href(slug))}">{esc(repo)}</a>'

TITLE = "Rebuild proof — roundtrip and export packages"

from agentdecompile_recovery.corpus.dashboard.common import as_root

ROUNDTRIP_JSON = as_root() / "output" / "roundtrip" / "_roundtrip.json"
COVERAGE_JSON = as_root() / "output" / "exact_universal" / "_coverage.json"
ASM_MANIFEST = as_root() / "output" / "export_asm" / "_manifest.json"
CPP_MANIFEST = as_root() / "output" / "export_cpp" / "_manifest.json"
BUILD_MANIFEST = as_root() / "output" / "reconstructed" / "build_manifest.json"
ROUNDTRIP_LOG = as_root() / "logs" / "roundtrip.log"
EXPORT_LOG = as_root() / "logs" / "export_packages.log"

# Ghidra stores the imported file verbatim as FileBytes; the .xbe databases have
# none, so there is no image to rebuild. Named here so the two failures read as a
# known upstream limitation rather than an emitter bug.
NO_FILEBYTES_HINT = "raw image not exported"


def _rows(data):
    """Manifests are lists of dicts, but a half-written file can be anything."""
    return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []


def _total(rows, field: str) -> int:
    out = 0
    for r in rows:
        try:
            out += int(r.get(field) or 0)
        except (TypeError, ValueError):
            continue
    return out


def _short_hash(value) -> str:
    text = str(value or "")
    return f'<code>{esc(text[:12])}</code>' if text else "-"


def _log_block(path: Path, lines: list[str]) -> str:
    if not lines:
        return missing(f"no log yet ({rel(path)})")
    body = esc("\n".join(lines))
    return (f'<div class="sub" style="margin-bottom:4px">{_file_link(path)}</div>'
            f'<div class="log">{body}</div>')


def _receipt_verdict(r: dict) -> str:
    """One rebuild record's verdict. The HTML table and the payload both read it."""
    if r.get("identical") is True:
        return "proven"
    if r.get("error"):
        return "unproven"
    return "failed"


_RECEIPT_TAGS = {"proven": ("identical", "ok"), "unproven": ("no image", "warn"),
                 "failed": ("mismatch", "dead")}


def _coverage_verdict(fn: int, ex: int, bad: int) -> str:
    if not fn:
        return "unproven"
    if ex == fn and not bad:
        return "proven"
    if not ex and bad:
        return "failed"
    return "partial"


def _section_roundtrip(g: dict) -> str:
    data, err = g["roundtrip"]["data"], g["roundtrip"]["err"]
    if err:
        return panel(missing(err), "Whole-file roundtrip")
    rows = _rows(data)
    if not rows:
        return panel(missing(f"{rel(ROUNDTRIP_JSON)} holds no records"), "Whole-file roundtrip")

    graded = [(r, _receipt_verdict(r)) for r in rows]
    ok = [r for r, verdict in graded if verdict == "proven"]
    bad = [r for r, verdict in graded if verdict != "proven"]
    rebuilt_bytes = _total(ok, "rebuilt_size")

    slugs = g["slugs"]
    body = []
    for r, verdict in sorted(graded, key=lambda rv: str(rv[0].get("binary", ""))):
        note = r.get("error") or ""
        body.append([
            _bin_cell(r.get("binary"), slugs),
            tag(*_RECEIPT_TAGS[verdict]),
            esc(r.get("container") or note or "-"),
            fnum(r.get("size")),
            fnum(r.get("rebuilt_size")),
            _short_hash(r.get("sha256_original")),
            _short_hash(r.get("sha256_rebuilt")),
            _clink(r.get("functions"), _fn_href(slugs.get(str(r.get("binary"))))),
            f'{r["pct_attributed"]:.1f}%' if isinstance(r.get("pct_attributed"), (int, float)) else "-",
        ])

    head = (
        f'<p class="headline">{fnum(len(ok))} / {fnum(len(rows))} binaries rebuild '
        f'<span class="hl">byte-identical</span></p>'
        f'<p class="sub">Every emitted region is reassembled into a whole file and its SHA-256 '
        f'compared with the original. {fnum(rebuilt_bytes)} bytes reproduced exactly. '
        f'Source: {_file_link(ROUNDTRIP_JSON)}</p>'
    )

    # "no image" (Xbox databases have no FileBytes to reassemble) is a known
    # upstream limitation, not an emitter failure, so it earns its own state
    # rather than being merged into "mismatch" — see the limitation box below.
    no_image = [r for r, verdict in graded if verdict == "unproven"]
    mismatch = [r for r, verdict in graded if verdict == "failed"]
    head += stacked_bar([
        ("byte-identical", len(ok), "proven"),
        ("no image (known limitation)", len(no_image), "partial"),
        ("mismatch", len(mismatch), "failed"),
    ])

    limitation = ""
    if bad:
        names = ", ".join(_bin_cell(r.get("binary"), slugs) for r in bad)
        reasons = {str(r.get("error") or "no verdict recorded") for r in bad}
        filebytes = all(NO_FILEBYTES_HINT in str(r.get("error") or "") for r in bad)
        why = (
            "Ghidra keeps each imported file verbatim as FileBytes; these databases have none, "
            "so the raw image cannot be read back and there is nothing to reassemble. This is a "
            "known limitation of the Xbox imports, not an emitter failure — their functions still "
            "export and still count as byte-exact below."
            if filebytes else
            "Recorded reason: " + "; ".join(esc(x) for x in sorted(reasons))
        )
        limitation = (
            f'<div class="panel" style="margin-top:14px">'
            f'<div class="ptitle"><b>Known limitation</b>{tag("explained", "warn")}</div>'
            f'<p class="sub">{names} — {why}</p></div>'
        )

    tbl = _details(table(
        ["Binary", "Verdict", "Container", "Size", "Rebuilt", "SHA-256 original",
         "SHA-256 rebuilt", "Functions", "Bytes in named fns"],
        body,
        numeric={3, 4, 7, 8},
    ))
    return head + limitation + '<div class="panel" style="margin-top:14px">' + tbl + "</div>"


def _section_byte_exact(g: dict) -> str:
    data, err = g["coverage"]["data"], g["coverage"]["err"]
    if err:
        return panel(missing(err), "Byte-exact emission")
    rows = _rows(data)
    if not rows:
        return panel(missing(f"{rel(COVERAGE_JSON)} holds no records"), "Byte-exact emission")

    functions = _total(rows, "functions")
    exact = _total(rows, "byte_exact")
    failed = _total(rows, "failed")
    skipped = _total(rows, "skipped_unmappable")
    seconds = sum(float(r.get("seconds") or 0) for r in rows)

    slugs = g["slugs"]
    body = []
    for r in sorted(rows, key=lambda r: -(r.get("functions") or 0)):
        fn, ex = r.get("functions") or 0, r.get("byte_exact") or 0
        rate_cls = "good" if fn and ex == fn else "warnt"
        mspf = r.get("ms_per_function")
        body.append([
            _bin_cell(r.get("repo_path"), slugs),
            esc(r.get("container", "-")),
            esc(r.get("target", "-")),
            _clink(fn, _fn_href(slugs.get(str(r.get("repo_path"))))),
            fnum(ex),
            f'<span class="{"bad" if r.get("failed") else ""}">{fnum(r.get("failed"))}</span>',
            f'<span class="{rate_cls}">{fpct(ex, fn)}</span>',
            f"{float(mspf):.3f}" if isinstance(mspf, (int, float)) else "-",
        ])

    warn = (
        '<div class="panel" style="border-color:#5a4d2c">'
        '<div class="ptitle"><b>What this number is</b>'
        + tag("not decompilation", "warn") + "</div>"
        '<p class="sub">These functions are emitted as <b>byte-exact machine code wrapped in C</b> '
        '(<code>__declspec(naked)</code> + <code>_emit</code> / <code>.byte</code>). Re-assembling '
        'them reproduces the original opcodes bit for bit, which proves the emitter and the '
        'address-to-byte mapping are correct. It is <b>not recovered source</b>: no control flow, '
        'types, or expressions are reconstructed by this pass. Readable C is tracked on its own '
        'panel and is a far smaller number.</p></div>'
    )

    head = (
        f'<p class="headline">{fnum(exact)} / {fnum(functions)} functions '
        f'<span class="hl">byte-exact</span> <span style="font-size:.45em;color:#7d8aa0">'
        f'as asm shims, not source</span></p>'
        f'<p class="sub">{fnum(len(rows))} binaries, {fnum(failed)} failed, {fnum(skipped)} skipped '
        f'as unmappable, {seconds:,.1f}s of mapper time. Source: {_file_link(COVERAGE_JSON)}</p>'
    )

    # Per-binary byte-exact count, sorted — the workhorse per-build comparison.
    # State mirrors the same good/warnt split the table cell already uses for
    # its rate, rather than inventing a second scale for the same fact.
    chart_rows = []
    for r in rows:
        fn, ex = r.get("functions") or 0, r.get("byte_exact") or 0
        state = "proven" if fn and ex == fn else "partial"
        slug = slugs.get(str(r.get("repo_path")))
        chart_rows.append((slug or r.get("repo_path") or "?", ex, state))
    chart = bars(chart_rows, href_fn=lambda slug, *_: _bin_href(slug))

    tbl = _details(table(
        ["Binary", "Container", "Target", "Functions", "Byte-exact", "Failed", "Rate", "ms/fn"],
        body,
        numeric={3, 4, 5, 6, 7},
    ))
    return head + warn + chart + '<div class="panel">' + tbl + "</div>"


def _section_packages(g: dict) -> str:
    asm, asm_err = g["asm"]["data"], g["asm"]["err"]
    cpp, cpp_err = g["cpp"]["data"], g["cpp"]["err"]
    asm_rows, cpp_rows = _rows(asm), _rows(cpp)
    if not asm_rows and not cpp_rows:
        return panel(missing(asm_err or cpp_err or "no export manifests found"), "Export packages")

    # Prefer the .S manifest as the row source; fall back to the .cpp one so a
    # half-finished export still renders something truthful.
    rows = asm_rows or cpp_rows
    same = bool(asm_rows) and bool(cpp_rows) and asm_rows == cpp_rows

    asm_pkgs, cpp_pkgs = g["asm"]["pkgs"], g["cpp"]["pkgs"]

    slugs = g["slugs"]
    body = []
    for r in sorted(rows, key=lambda r: str(r.get("binary", ""))):
        slug = slugs.get(str(r.get("binary"))) or r.get("slug")
        body.append([
            _bin_cell(r.get("binary"), slugs),
            f'{esc(r.get("bits", "-"))}-bit',
            _clink(r.get("functions"), _fn_href(slug)),
            _clink(r.get("named"), _fn_href(slug, "&named=1")),
            fnum(r.get("asm_files")),
            fnum(r.get("cpp_files")),
            # A count of source *files*, not of functions, so no function filter
            # describes it.
            fnum(r.get("original_source_files")),
        ])

    summary = kv([
        ("binaries in manifest", fnum(len(rows))),
        (".S assembly packages on disk", fnum(asm_pkgs)),
        (".cpp/.h readable packages on disk", fnum(cpp_pkgs)),
        ("total export projects", fnum(asm_pkgs + cpp_pkgs)),
        ("functions packaged", fnum(_total(rows, "functions"))),
        ("named functions", fnum(_total(rows, "named"))),
        (".S files written", fnum(_total(rows, "asm_files"))),
        (".cpp files written", fnum(_total(rows, "cpp_files"))),
        ("original source paths recovered", fnum(_total(rows, "original_source_files"))),
    ])

    notes = []
    if same:
        notes.append("Both manifests record the same rows — each binary ships one .S package and "
                     "one .cpp/.h package built from the same function set.")
    else:
        if asm_err:
            notes.append(f"export_asm manifest: {asm_err}")
        if cpp_err:
            notes.append(f"export_cpp manifest: {cpp_err}")
        if asm_rows and cpp_rows:
            notes.append("The two manifests differ; rows below come from "
                         f"{rel(ASM_MANIFEST if asm_rows else CPP_MANIFEST)}.")
    notes.append("The manifests record file and function counts only — no package byte sizes, so "
                 "none are shown.")

    # Named functions per binary, sorted — how far the package's own names
    # reach, since a shipped package is only as useful as what carries a name.
    chart = bars(
        [(slugs.get(str(r.get("binary"))) or r.get("binary") or "?",
          r.get("named") or 0, "proven") for r in rows],
        href_fn=lambda slug, *_: _bin_href(slug),
    )
    tbl = _details(table(
        ["Binary", "Bits", "Functions", "Named", ".S files", ".cpp files", "Original src paths"],
        body,
        numeric={2, 3, 4, 5, 6},
    ))
    return (
        '<div class="grid3"><div class="panel">'
        '<div class="ptitle"><b>Shipped packages</b></div>' + summary +
        "".join(f'<p class="sub" style="margin-top:8px">{esc(n)}</p>' for n in notes) +
        '</div></div><div class="panel">' + chart + tbl + "</div>"
    )


def _section_reconstructed(g: dict) -> str:
    data, err = g["build"]["data"], g["build"]["err"]
    if err:
        return panel(missing(err), "Reconstructed tree")
    rows = _rows(data)
    if not rows:
        return panel(missing(f"{rel(BUILD_MANIFEST)} holds no records"), "Reconstructed tree")

    functions = _total(rows, "functions")
    named = _total(rows, "named")
    attributed = _total(rows, "attributed_source_files")
    tus = _total(rows, "translation_units")

    summary = kv([
        ("binaries", fnum(len(rows))),
        ("functions in tree", fnum(functions)),
        ("named functions", f'{fnum(named)} ({fpct(named, functions)})'),
        ("translation units", fnum(tus)),
        ("attributed source files", fnum(attributed)),
    ])

    slugs = g["slugs"]
    body = []
    for r in sorted(rows, key=lambda r: -(r.get("functions") or 0)):
        slug = slugs.get(str(r.get("binary"))) or r.get("target")
        body.append([
            _bin_cell(r.get("binary"), slugs),
            esc(r.get("arch", "-")),
            esc(r.get("triple", "-")),
            _clink(r.get("functions"), _fn_href(slug)),
            _clink(r.get("named"), _fn_href(slug, "&named=1")),
            fnum(r.get("translation_units")),
            fnum(r.get("attributed_source_files")),
        ])

    chart = bars(
        [(slugs.get(str(r.get("binary"))) or r.get("binary") or "?",
          r.get("named") or 0, "proven") for r in rows],
        href_fn=lambda slug, *_: _bin_href(slug),
    )
    tbl = _details(table(
        ["Binary", "Arch", "Triple", "Functions", "Named", "TUs", "Attributed src files"],
        body,
        numeric={3, 4, 5, 6},
    ))
    note = ('<p class="sub" style="margin-top:8px">Names and original file paths come from symbols '
            'and debug data left in the binaries. A named function is still an asm shim unless a '
            'recovered-C pass has replaced it.</p>')
    return ('<div class="grid3"><div class="panel">'
            '<div class="ptitle"><b>Reconstructed tree</b></div>' + summary + note +
            f'<p class="sub">Source: {_file_link(BUILD_MANIFEST)}</p></div></div>'
            '<div class="panel">' + chart + tbl + "</div>")


def _section_logs(g: dict) -> str:
    return (
        '<div class="grid3">'
        f'<div class="panel"><div class="ptitle"><b>roundtrip job</b></div>{_log_block(ROUNDTRIP_LOG, g["logs"]["roundtrip"][-8:])}</div>'
        f'<div class="panel"><div class="ptitle"><b>export packages job</b></div>{_log_block(EXPORT_LOG, g["logs"]["export"][-8:])}</div>'
        "</div>"
    )


LOG_CAP = 100  # lines per log in the payload
LOG_LINE_CAP = 400  # characters per line; a runaway line must not bloat the payload


def _pkg_dirs(path: Path) -> int | None:
    """Packages are directories next to the manifest; a cheap listing keeps the
    on-disk count honest without touching the (very large) package contents."""
    try:
        return sum(1 for p in path.parent.iterdir() if p.is_dir())
    except OSError:
        return None


def _source(path: Path, *, pkgs: bool = False) -> dict:
    data, err = load_json(path)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = None
    out = {"path": path, "data": data, "err": err, "mtime": mtime}
    if pkgs:
        out["pkgs"] = _pkg_dirs(path) or 0
    return out


def _gather() -> dict:
    """One bounded read of every source. render() and as_payload() both use it."""
    logs, log_mtime = {}, {}
    for key, path in (("roundtrip", ROUNDTRIP_LOG), ("export", EXPORT_LOG)):
        logs[key] = tail_lines(path, nlines=LOG_CAP)
        try:
            log_mtime[key] = path.stat().st_mtime
        except OSError:
            log_mtime[key] = None
    return {
        "roundtrip": _source(ROUNDTRIP_JSON),
        "coverage": _source(COVERAGE_JSON),
        "asm": _source(ASM_MANIFEST, pkgs=True),
        "cpp": _source(CPP_MANIFEST, pkgs=True),
        "build": _source(BUILD_MANIFEST),
        "slugs": _slugs(),
        "logs": logs,
        "log_mtime": log_mtime,
    }


def _safe(fn, label: str) -> str:
    """A panel that throws shows an error box instead of data, which helps nobody."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        return panel(missing(f"{label} unavailable: {exc}"), label)


def render() -> str:
    g = _gather()
    parts = [
        _safe(lambda: _section_roundtrip(g), "Whole-file roundtrip"),
        '<h2>Byte-exact emission (asm shims, not recovered source)</h2>',
        _safe(lambda: _section_byte_exact(g), "Byte-exact emission"),
        "<h2>Export packages</h2>",
        _safe(lambda: _section_packages(g), "Export packages"),
        "<h2>Reconstructed tree</h2>",
        _safe(lambda: _section_reconstructed(g), "Reconstructed tree"),
        "<h2>Job logs</h2>",
        _safe(lambda: _section_logs(g), "Job logs"),
    ]
    return "".join(parts)


# --------------------------------------------------------------------------
# Structured payload. Plain data only: no markup, no absolute paths.
# Each evidence class is its own block with its own source and state.
# --------------------------------------------------------------------------

def _iso(mtime) -> str | None:
    if not mtime:
        return None
    return datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _age(mtime) -> int | None:
    return max(0, int(time.time() - mtime)) if mtime else None


def _meta(src: dict, path: Path) -> dict:
    return {"source": rel(path), "at": _iso(src["mtime"]), "age_s": _age(src["mtime"])}


def _fig(value, path: Path, mtime, state: str) -> dict:
    return {"value": value, "source": rel(path), "at": _iso(mtime), "state": state}


def _agg(states: list[str]) -> str:
    live = [s for s in states if s != "excluded"]
    if not live:
        return "missing"
    if all(s == "proven" for s in live):
        return "proven"
    if any(s in ("proven", "partial") for s in live):
        return "partial"
    if any(s == "failed" for s in live):
        return "failed"
    return "unproven"


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _excluded(repo) -> bool:
    return str(repo) in {str(x) for x in (DRM_EXCLUDED or ())}


def _with_exclusion(repo, verdict: str) -> str:
    # Only the payload marks a configured exclusion. The HTML tables show the
    # underlying verdict for those rows.
    return "excluded" if _excluded(repo) else verdict


def _block(src: dict, path: Path, errors: list[str], label: str):
    """Common block head and the (rows, state-if-unreadable) decision."""
    block = {**_meta(src, path), "state": "missing", "note": None, "rows": []}
    rows = _rows(src["data"])
    if src["err"]:
        block["note"] = str(src["err"])
        if not str(src["err"]).startswith("not available yet"):
            errors.append(f"{label}: {src['err']}")
    elif not rows:
        block["note"] = f"{rel(path)} holds no records"
    return block, rows


def _receipts(g: dict, slugs: dict, errors: list[str]) -> dict:
    src = g["roundtrip"]
    block, rows = _block(src, ROUNDTRIP_JSON, errors, "image_receipts")
    block["claim"] = "Whole-image rebuild: SHA-256 of the rebuilt file against the original."
    out, states, ok = [], [], []
    for r in sorted(rows, key=lambda r: str(r.get("binary", ""))):
        repo = r.get("binary")
        verdict = _receipt_verdict(r)
        if verdict == "proven":
            ok.append(r)
        state = _with_exclusion(repo, verdict)
        states.append(state)
        out.append({
            "slug": slugs.get(str(repo)),
            "binary": repo,
            "state": state,
            "container": r.get("container"),
            "note": r.get("error"),
            "size": _num(r.get("size")),
            "rebuilt_size": _num(r.get("rebuilt_size")),
            "sha256_original": r.get("sha256_original"),
            "sha256_rebuilt": r.get("sha256_rebuilt"),
            "functions": _num(r.get("functions")),
            "pct_attributed": _num(r.get("pct_attributed")),
        })
    if rows:
        mt = src["mtime"]
        block["state"] = _agg(states)
        block["figures"] = {
            "binaries": _fig(len(rows), ROUNDTRIP_JSON, mt, "proven"),
            "identical": _fig(len(ok), ROUNDTRIP_JSON, mt, block["state"]),
            "no_image": _fig(states.count("unproven"), ROUNDTRIP_JSON, mt, "unproven"),
            "mismatch": _fig(states.count("failed"), ROUNDTRIP_JSON, mt, "failed" if states.count("failed") else "proven"),
            "bytes_reproduced": _fig(_total(ok, "rebuilt_size"), ROUNDTRIP_JSON, mt, "proven" if ok else "unproven"),
        }
    block["rows"] = out
    return block


def _coverage(g: dict, slugs: dict, errors: list[str]) -> dict:
    src = g["coverage"]
    block, rows = _block(src, COVERAGE_JSON, errors, "universal_coverage")
    block["claim"] = ("Per-function byte equality of asm shims. Not a whole-image rebuild proof "
                      "and not recovered C.")
    out, states = [], []
    for r in sorted(rows, key=lambda r: -(_num(r.get("functions")) or 0)):
        fn, ex, bad = _num(r.get("functions")) or 0, _num(r.get("byte_exact")) or 0, _num(r.get("failed")) or 0
        state = _with_exclusion(r.get("repo_path"), _coverage_verdict(fn, ex, bad))
        states.append(state)
        out.append({
            "slug": slugs.get(str(r.get("repo_path"))),
            "binary": r.get("repo_path"),
            "state": state,
            "container": r.get("container"),
            "target": r.get("target"),
            "functions": fn,
            "byte_exact": ex,
            "failed": bad,
            "skipped_unmappable": _num(r.get("skipped_unmappable")),
            "ms_per_function": _num(r.get("ms_per_function")),
        })
    if rows:
        mt, st = src["mtime"], _agg(states)
        block["state"] = st
        block["figures"] = {
            "binaries": _fig(len(rows), COVERAGE_JSON, mt, "proven"),
            "functions": _fig(_total(rows, "functions"), COVERAGE_JSON, mt, st),
            "byte_exact": _fig(_total(rows, "byte_exact"), COVERAGE_JSON, mt, st),
            "failed": _fig(_total(rows, "failed"), COVERAGE_JSON, mt, "failed" if _total(rows, "failed") else "proven"),
            "skipped_unmappable": _fig(_total(rows, "skipped_unmappable"), COVERAGE_JSON, mt, "partial" if _total(rows, "skipped_unmappable") else "proven"),
        }
    block["rows"] = out
    return block


def _package(g: dict, key: str, path: Path, files_field: str, claim: str, slugs: dict,
             errors: list[str], label: str, extra: tuple[str, ...] = ()) -> dict:
    """One package class, read only from its own manifest."""
    src = g[key]
    block, rows = _block(src, path, errors, label)
    block["claim"] = claim
    block["packages_on_disk"] = _fig(src["pkgs"], path, src["mtime"],
                                     "proven" if src["pkgs"] else "missing")
    out, states = [], []
    for r in sorted(rows, key=lambda r: str(r.get("binary", ""))):
        files = _num(r.get(files_field)) or 0
        state = _with_exclusion(r.get("binary"), "proven" if files else "missing")
        states.append(state)
        row = {
            "slug": slugs.get(str(r.get("binary"))) or r.get("slug"),
            "binary": r.get("binary"),
            "state": state,
            "bits": _num(r.get("bits")),
            "functions": _num(r.get("functions")),
            "named": _num(r.get("named")),
            files_field: files,
        }
        for f in extra:
            row[f] = _num(r.get(f))
        out.append(row)
    if rows:
        mt = src["mtime"]
        block["state"] = _agg(states)
        block["figures"] = {
            "binaries": _fig(len(rows), path, mt, "proven"),
            "functions": _fig(_total(rows, "functions"), path, mt, block["state"]),
            "named": _fig(_total(rows, "named"), path, mt, block["state"]),
            files_field: _fig(_total(rows, files_field), path, mt, block["state"]),
        }
    block["rows"] = out
    return block


def _reconstructed(g: dict, slugs: dict, errors: list[str]) -> dict:
    src = g["build"]
    block, rows = _block(src, BUILD_MANIFEST, errors, "reconstructed_build")
    block["claim"] = ("Reconstructed tree manifest. A named function is still an asm shim "
                      "unless a recovered-C pass replaced it.")
    out, states = [], []
    for r in sorted(rows, key=lambda r: -(_num(r.get("functions")) or 0)):
        fn, tus = _num(r.get("functions")) or 0, _num(r.get("translation_units")) or 0
        state = _with_exclusion(r.get("binary"), "partial" if fn and tus else "unproven")
        states.append(state)
        out.append({
            "slug": slugs.get(str(r.get("binary"))) or r.get("target"),
            "binary": r.get("binary"),
            "state": state,
            "arch": r.get("arch"),
            "triple": r.get("triple"),
            "functions": fn,
            "named": _num(r.get("named")),
            "translation_units": tus,
            "attributed_source_files": _num(r.get("attributed_source_files")),
        })
    if rows:
        mt = src["mtime"]
        block["state"] = _agg(states)
        block["figures"] = {
            "binaries": _fig(len(rows), BUILD_MANIFEST, mt, "proven"),
            "functions": _fig(_total(rows, "functions"), BUILD_MANIFEST, mt, block["state"]),
            "named": _fig(_total(rows, "named"), BUILD_MANIFEST, mt, block["state"]),
            "translation_units": _fig(_total(rows, "translation_units"), BUILD_MANIFEST, mt, block["state"]),
            "attributed_source_files": _fig(_total(rows, "attributed_source_files"), BUILD_MANIFEST, mt, block["state"]),
        }
    block["rows"] = out
    return block


def _logs(g: dict) -> list[dict]:
    out = []
    for key, label, path in (("roundtrip", "roundtrip job", ROUNDTRIP_LOG),
                             ("export", "export packages job", EXPORT_LOG)):
        lines = [ln[:LOG_LINE_CAP] for ln in g["logs"][key][-LOG_CAP:]]
        mt = g["log_mtime"][key]
        out.append({
            "id": key,
            "label": label,
            "source": rel(path),
            "at": _iso(mt),
            "age_s": _age(mt),
            "state": "proven" if lines else "missing",
            "lines": lines,
        })
    return out


def as_payload() -> dict:
    """Structured twin of render(). One block per evidence class; never merged."""
    g = _gather()
    slugs = g["slugs"]
    errors: list[str] = []
    return {
        "at": _iso(time.time()),
        "errors": errors,
        "image_receipts": _receipts(g, slugs, errors),
        "universal_coverage": _coverage(g, slugs, errors),
        "assembly_package": _package(
            g, "asm", ASM_MANIFEST, "asm_files",
            "Assembly floor: original opcodes wrapped as .S. Not recovered C.",
            slugs, errors, "assembly_package"),
        "cpp_package": _package(
            g, "cpp", CPP_MANIFEST, "cpp_files",
            "Readable .cpp/.h package. Counts here are separate from the assembly package.",
            slugs, errors, "cpp_package", extra=("original_source_files",)),
        "reconstructed_build": _reconstructed(g, slugs, errors),
        "logs": _logs(g),
    }
