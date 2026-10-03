"""Per-binary inventory panel.

Shows every row of the `binary` table: build coverage, which builds are
excluded from the denominators, and a cross-check against an independent
inventory file. Builds of one program on other platforms share code, so a
symbol recovered in one build can be inherited by the others; that is why the
panel groups rows instead of only listing them.

Two denominators are shown side by side. Builds listed in the configured
exclusion list (AGENT_DECOMPILE_EXCLUDED_REPO_PATHS) and byte-identical copies
(same md5) cannot contribute matchable functions, so a total that includes them
makes full coverage read as a shortfall.

All figures come from one collector, `_collect()`. `render()` draws it as HTML
and `as_payload()` returns it as plain data, so the two cannot drift. Numbers
are read live from the corpus database and from the external recovery root's
reports/inventory.json. The `binary` table is small; the `func` table is never
touched here.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from urllib.parse import quote

from agentdecompile_recovery.corpus.dashboard.panels.common import (
    DRM_EXCLUDED,
    as_external,
    esc,
    fnum,
    fpct,
    kv,
    live_db,
    load_json,
    missing,
    panel,
    query_db,
    rel,
    table,
    tag,
)
from agentdecompile_recovery.corpus.dashboard.panels.viz import bars, donut

try:  # count_link is landing in common.py from another author.
    from agentdecompile_recovery.corpus.dashboard.panels.common import count_link
except ImportError:  # the panel still renders, with plain links
    count_link = None


def _details(inner: str, summary: str = "raw numbers") -> str:
    """The chart is the finding; the table is what a reader asks for next.

    Rule C (10-relationship-layout.md): a table is only ever the *expansion* of
    a visual, so it starts collapsed rather than competing with the chart for
    the reader's first look.
    """
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

TITLE = "Binaries — builds, coverage and exclusions"

# The external recovery root writes this after each import pass. It is a
# second, independent census of the same Ghidra projects, so it is the only
# cheap way to notice that one of the two sources has gone stale.
def _inventory_path():
    return as_external() / "reports" / "inventory.json"

# Recovery targets the x86 family first: that is where the decompiler and the
# byte-exact ladder work.
X86_ARCHES = {"x86", "x86_64", "x64", "i386", "i686", "amd64"}

# A source disagreement below this is import-order noise, not staleness.
INVENTORY_TOLERANCE = 0.01

# Game codes come from the data; sort order is alphabetical, unknown last.

FORMAT_SHORT = {
    "Portable Executable (PE)": "PE",
    "Executable and Linking Format (ELF)": "ELF",
    "Mac OS X Mach-O": "Mach-O",
    "Xbox Executable Format (XBE)": "XBE",
}

COLUMNS = ("repo_path", "slug", "game", "platform", "arch", "bits", "format",
           "md5", "func_count", "named_count")


def _mtime(path):
    try:
        return os.stat(path).st_mtime if path is not None else None
    except OSError:
        return None


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _game_key(game):
    return (game is None, str(game or ""))


def _count(value):
    """NULL means never measured; keep it so the cell reads "not attempted", not 0."""
    return int(value) if value is not None else None


def _load_rows():
    """Return (rows, error). The binary table is small, so a full select is cheap."""
    sql = f"SELECT {', '.join(COLUMNS)} FROM binary"
    raw, err = query_db(sql)
    if err:
        return [], err
    rows = [dict(zip(COLUMNS, r)) for r in raw]
    for r in rows:
        r["repo_path"] = str(r.get("repo_path") or "")
        r["is_x86"] = str(r.get("arch") or "").strip().lower() in X86_ARCHES
    rows.sort(key=lambda r: (_game_key(r["game"]),
                             str(r.get("platform") or ""),
                             r["repo_path"]))
    return rows, None


def _duplicates(rows) -> dict[str, str]:
    """Map duplicate repo_path -> the copy it duplicates, keyed on md5.

    Derived from the md5 column rather than a hardcoded filename, so a second
    saved copy anywhere in the corpus is caught the same way. A ".keep" sidecar
    is always the copy, never the file the repo works from.
    """
    by_md5: dict[str, list[dict]] = {}
    for r in rows:
        md5 = str(r.get("md5") or "").strip().lower()
        if md5:
            by_md5.setdefault(md5, []).append(r)
    dups: dict[str, str] = {}
    for group in by_md5.values():
        if len(group) < 2:
            continue
        ordered = sorted(group, key=lambda r: (r["repo_path"].endswith(".keep"),
                                               len(r["repo_path"]),
                                               r["repo_path"]))
        for r in ordered[1:]:
            dups[r["repo_path"]] = ordered[0]["repo_path"]
    return dups


def _collect_inventory(rows, path) -> dict:
    """Cross-check func_count against inventory.json. Never fabricates numbers."""
    src = rel(path)
    out = {"source": src, "at": _mtime(path), "state": "missing", "error": None,
           "tolerance": INVENTORY_TOLERANCE, "listed": 0, "checked": 0,
           "flagged": [], "only_in_inventory": [], "only_in_database": []}
    data, err = load_json(path)
    if err:
        out["error"] = err
        return out
    if not isinstance(data, list):
        out["state"] = "failed"
        out["error"] = "inventory.json did not contain a list of programs"
        return out
    inv = {}
    for entry in data:
        if isinstance(entry, dict) and entry.get("name"):
            inv[str(entry["name"])] = entry
    for r in rows:
        name = os.path.basename(r["repo_path"])
        entry = inv.get(name)
        if entry is None:
            continue
        out["checked"] += 1
        db_n = int(r.get("func_count") or 0)
        try:
            inv_n = int(entry.get("functions") or 0)
        except (TypeError, ValueError):
            continue
        denom = db_n or inv_n
        if not denom:
            continue
        drift = abs(db_n - inv_n) / denom
        if drift > INVENTORY_TOLERANCE:
            out["flagged"].append({"slug": r.get("slug"), "name": name,
                                   "db_func_count": db_n, "inventory_functions": inv_n,
                                   "drift": drift})
    db_names = {os.path.basename(r["repo_path"]) for r in rows}
    out["listed"] = len(inv)
    out["only_in_inventory"] = sorted(set(inv) - db_names)
    out["only_in_database"] = sorted(db_names - set(inv))
    stale = out["flagged"] or out["only_in_inventory"] or out["only_in_database"]
    out["state"] = "partial" if stale else "proven"
    return out


def _collect() -> dict:
    """Gather every figure once. render() and as_payload() both read this."""
    now = time.time()
    db_path = live_db()
    out = {"at": now, "errors": [], "database": {"source": rel(db_path), "at": _mtime(db_path)},
           "rows": [], "totals": None, "exclusions": [], "duplicates": [],
           "inventory": None}
    rows, err = _load_rows()
    if err:
        out["errors"].append(err)
        return out
    if not rows:
        out["errors"].append("the binary table is empty")
        return out

    dups = _duplicates(rows)
    by_path = {r["repo_path"]: r for r in rows}
    # A path can be configured as excluded and also be a duplicate; configured wins.
    def reason(path):
        if path in DRM_EXCLUDED:
            return "configured"
        if path in dups:
            return "duplicate"
        return None

    for r in rows:
        why = reason(r["repo_path"])
        out["rows"].append({
            "slug": r.get("slug"), "repo_path": r["repo_path"], "game": r.get("game"),
            "platform": r.get("platform"), "arch": r.get("arch"), "bits": r.get("bits"),
            "format": r.get("format"), "md5": r.get("md5"),
            "func_count": _count(r.get("func_count")),
            "named_count": _count(r.get("named_count")),
            "is_x86": r["is_x86"], "exclusion": why,
            "duplicate_of": dups.get(r["repo_path"]),
            "state": "excluded" if why else "unproven",
            "source": "binary",
        })

    live = [r for r in out["rows"] if not r["exclusion"]]
    total_funcs = sum(r["func_count"] or 0 for r in out["rows"])
    live_funcs = sum(r["func_count"] or 0 for r in live)
    games: dict = {}
    for r in out["rows"]:
        g = games.setdefault(r["game"], {"game": r["game"], "builds": 0, "platforms": set()})
        g["builds"] += 1
        g["platforms"].add(r["platform"])
    out["totals"] = {
        "source": "binary", "at": out["database"]["at"],
        "binaries": len(rows),
        "functions_all": total_funcs,
        "functions_matchable": live_funcs,
        "functions_excluded": total_funcs - live_funcs,
        "named_matchable": sum(r["named_count"] or 0 for r in live),
        # Duplicates still count here; only the configured list is off the
        # priority list. The x86 section heading in render() uses the same rule.
        "x86_priority": len([r for r in out["rows"]
                             if r["is_x86"] and r["exclusion"] != "configured"]),
        "x86_rows": len([r for r in out["rows"] if r["is_x86"]]),
        "other_arch_rows": len([r for r in out["rows"] if not r["is_x86"]]),
        "coverage_ratio": (live_funcs / total_funcs) if total_funcs else None,
        "games": [{"game": g["game"], "builds": g["builds"],
                   "platforms": len(g["platforms"])}
                  for g in sorted(games.values(), key=lambda g: _game_key(g["game"]))],
    }
    for r in out["rows"]:
        if r["exclusion"] == "configured":
            out["exclusions"].append({"slug": r["slug"], "repo_path": r["repo_path"],
                                      "func_count": r["func_count"], "reason": "configured",
                                      "source": "AGENT_DECOMPILE_EXCLUDED_REPO_PATHS",
                                      "state": "excluded"})
    for path in DRM_EXCLUDED:
        if path not in by_path:
            out["errors"].append(f"configured exclusion not in the binary table: {path}")
    for path, canonical in sorted(dups.items()):
        r, other = by_path.get(path), by_path.get(canonical)
        entry = {"slug": r.get("slug") if r else None, "repo_path": path,
                 "func_count": _count(r.get("func_count")) if r else None,
                 "duplicate_of": canonical,
                 "duplicate_of_slug": other.get("slug") if other else None,
                 "md5": r.get("md5") if r else None, "source": "binary.md5",
                 "state": "excluded"}
        out["duplicates"].append(entry)
        if path not in DRM_EXCLUDED:
            out["exclusions"].append({**entry, "reason": "duplicate"})
    out["inventory"] = _collect_inventory(rows, _inventory_path())
    if out["inventory"]["error"]:
        out["errors"].append("inventory cross-check: " + out["inventory"]["error"])
    return out


# ---------------------------------------------------------------- HTML draw

def _fmt_cell(value) -> str:
    text = str(value or "")
    short = FORMAT_SHORT.get(text)
    if not short:
        return esc(text) or "-"
    return f'<span title="{esc(text)}">{esc(short)}</span>'


def _status_cell(row) -> str:
    if row["exclusion"] == "configured":
        return tag("excluded", "warn") + ' <span class="sub">configured exclusion</span>'
    if row["exclusion"] == "duplicate":
        other = os.path.basename(row["duplicate_of"] or "")
        return tag("duplicate", "warn") + f' <span class="sub">same md5 as {esc(other)}</span>'
    if row["is_x86"]:
        return tag("recovery priority", "prio")
    return tag("port / reference")


def _funcs_bars(rows) -> str:
    """One bar per binary, sorted by function count.

    State carries only the "counts in no denominator" fact (excluded). href_fn
    opens the same /binary/<slug> route the table row's link uses.
    """
    data = [(r.get("slug") or r["repo_path"], r["func_count"] or 0, r["state"]) for r in rows]
    return bars(data, href_fn=lambda slug, *_: _bin_href(slug))


def _funcs_donut(totals) -> str:
    return donut(
        [("matchable", totals["functions_matchable"], "proven"),
         ("excluded (configured or duplicate)", totals["functions_excluded"], "excluded")],
        total=totals["functions_all"], title="Functions: matchable vs excluded",
    )


def _binary_table(rows) -> str:
    body = []
    for r in rows:
        arch = str(r.get("arch") or "?")
        bits = r.get("bits")
        arch_txt = f"{arch} / {bits}-bit" if bits else arch
        slug = r.get("slug")
        body.append([
            f'<a href="{esc(_bin_href(slug))}"><code>{esc(r["repo_path"])}</code></a>',
            esc(r.get("game") or "?"),
            esc(r.get("platform") or "?"),
            esc(arch_txt),
            _fmt_cell(r.get("format")),
            _clink(r["func_count"], _fn_href(slug), title="every function in this build"),
            _clink(r["named_count"], _fn_href(slug, "&named=1"),
                   title="functions that carry a real name"),
            _status_cell(r),
        ])
    return table(
        ["Binary", "Game", "Platform", "Arch", "Format", "Functions", "Named", "Status"],
        body, numeric={5, 6},
    )


def _totals_block(c) -> str:
    t = c["totals"]
    game_txt = ", ".join(
        f'{g["game"] or "?"}: {g["builds"]} builds on {g["platforms"]} '
        f'platform{"" if g["platforms"] == 1 else "s"}' for g in t["games"])
    return _funcs_donut(t) + kv([
        ("Binaries in the corpus", fnum(t["binaries"])),
        ("Builds per game", esc(game_txt)),
        ("x86 / x64 recovery priority", fnum(t["x86_priority"])),
        ("Functions, all binaries", _clink(t["functions_all"], "/functions")),
        ("Functions, excluding the unmatchable",
         f'<b>{_clink(t["functions_matchable"], "/functions")}</b>'),
        ("Difference the exclusions make", fnum(t["functions_excluded"])),
        ("Full coverage scored against the raw total",
         fpct(t["functions_matchable"], t["functions_all"])),
        ("Functions already named across the matchable set",
         _clink(t["named_matchable"], "/functions")),
    ])


def _exclusions_block(c) -> str:
    if not c["exclusions"]:
        return missing("no exclusions found in the binary table")
    body = []
    for e in c["exclusions"]:
        slug = e.get("slug")
        name = f'<code>{esc(e["repo_path"])}</code>'
        cell = f'<a href="{esc(_bin_href(slug))}">{name}</a>' if slug else name
        if e["reason"] == "configured":
            why = ("Listed in the configured exclusion list. Nothing in it is "
                   "counted, on purpose.")
        else:
            canon = e["duplicate_of"]
            cslug = e.get("duplicate_of_slug")
            canon_cell = (f'<a href="{esc(_bin_href(cslug))}"><code>{esc(canon)}</code></a>'
                          if cslug else f'<code>{esc(canon)}</code>')
            why = (f"Byte-identical to {canon_cell} (same md5). "
                   "Counting both would double every function it holds.")
        body.append([cell,
                     _clink(e["func_count"], _fn_href(slug)) if slug else "-", why])
    note = ('<p class="sub">These rows are removed from every denominator by '
            'design. Their absence is a decision, not a gap.</p>')
    return note + table(["Excluded binary", "Functions", "Why"], body, numeric={1})


def _inventory_block(c, rows_total) -> str:
    inv = c["inventory"]
    if inv["error"]:
        return missing(f"Inventory cross-check {inv['error']}")
    parts = [f'<p class="sub">{inv["checked"]} of {rows_total} binaries cross-checked against '
             f'{esc(os.path.basename(inv["source"]))} ({inv["listed"]} programs listed). '
             f'Tolerance {inv["tolerance"] * 100:.0f}%.</p>']
    if inv["flagged"]:
        body = [[f'<a href="{esc(_bin_href(f["slug"]))}"><code>{esc(f["name"])}</code></a>',
                 _clink(f["db_func_count"], _fn_href(f["slug"])),
                 fnum(f["inventory_functions"]),
                 f'<span class="bad">{f["drift"] * 100:.2f}%</span>'] for f in inv["flagged"]]
        parts.append(table(["Binary", "Database func_count", "inventory.json functions",
                            "Disagreement"], body, numeric={1, 2, 3}))
        parts.append('<p class="miss">A disagreement means one source is stale. '
                     'Re-run the import that feeds the smaller count before trusting '
                     'either number.</p>')
    else:
        parts.append('<p class="sub good">Both sources agree on every binary.</p>')
    if inv["only_in_inventory"]:
        parts.append('<p class="miss">In inventory.json but not in the database: '
                     f'{esc(", ".join(inv["only_in_inventory"]))}</p>')
    if inv["only_in_database"]:
        parts.append('<p class="miss">In the database but not in inventory.json: '
                     f'{esc(", ".join(inv["only_in_database"]))}</p>')
    return "".join(parts)


def render() -> str:
    try:
        c = _collect()
        if c["errors"] and not c["rows"]:
            return panel(missing(c["errors"][0]))
        rows = c["rows"]
        x86 = [r for r in rows if r["is_x86"]]
        x86_live = [r for r in x86 if r["exclusion"] != "configured"]
        other = [r for r in rows if not r["is_x86"]]

        intro = (
            f'<p class="sub">{len(rows)} builds in the corpus. Rows that share a game '
            'are the same program built for another platform or storefront, so a '
            'function named in one build is a function the others can inherit. '
            'The Named column shows how unevenly the builds were reverse engineered; '
            'that unevenness is what cross-matching converts into coverage.</p>'
        )
        blocks = [
            panel(intro + _totals_block(c)),
            panel('<h3 style="margin-top:0">Functions per binary, sorted</h3>'
                  '<p class="sub">Every row in the table below, as one chart. '
                  '"excluded" bars are configured exclusions and duplicate copies. '
                  'They render for provenance and count in no denominator.'
                  '</p>' + _funcs_bars(rows)),
            panel(f'<h3 style="margin-top:0">x86 and x64 — recovery priority '
                  f'({len(x86_live)} of {len(x86)} rows)</h3>'
                  '<p class="sub">The decompiler and the byte-exact ladder target this '
                  'family first. Rows tagged below stay listed for provenance and '
                  'count in no denominator.</p>'
                  + _details(_binary_table(x86))),
        ]
        if other:
            blocks.append(panel(
                f'<h3 style="margin-top:0">Other architectures ({len(other)} binaries)</h3>'
                '<p class="sub">Different instruction set, same source tree. These '
                'can carry symbol names the desktop builds stripped.</p>'
                + _details(_binary_table(other))))
        blocks.append(panel('<h3 style="margin-top:0">Excluded on purpose</h3>'
                            + _exclusions_block(c)))
        blocks.append(panel('<h3 style="margin-top:0">Cross-check against the external inventory</h3>'
                            + _inventory_block(c, len(rows))))
        return "".join(blocks)
    except Exception as exc:  # noqa: BLE001 - a panel must degrade, never crash
        return panel(missing(f"binary inventory unavailable: {exc}"))


def as_payload() -> dict:
    """Structured facts for the workbench. Same collector as render(); no markup."""
    try:
        c = _collect()
    except Exception as exc:  # noqa: BLE001 - never fabricate; report the gap
        return {"at": _iso(time.time()), "errors": [f"binary inventory unavailable: {exc}"],
                "database": None, "totals": None, "binaries": [], "exclusions": [],
                "duplicates": [], "inventory": None}
    def stamp(d):
        if not isinstance(d, dict):
            return d
        d = dict(d)
        if "at" in d:
            d["at"] = _iso(d["at"])
        return d
    return {
        "at": _iso(c["at"]),
        "errors": list(c["errors"]),
        "database": stamp(c["database"]),
        "totals": stamp(c["totals"]),
        "binaries": c["rows"],
        "exclusions": c["exclusions"],
        "duplicates": c["duplicates"],
        "inventory": stamp(c["inventory"]),
    }
