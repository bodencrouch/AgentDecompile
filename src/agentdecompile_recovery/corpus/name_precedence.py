"""Decide which name wins when 24 forks merge onto one logical function.

The rule this enforces, stated by the user and non-negotiable: `FUN_00401000`
must never overwrite a name a human wrote. Merging knowledge across forks is
only worth doing if it raises the quality of a name; a merge that replaces
`CSWSCreature::UpdateActions` with a placeholder destroys the most valuable
data in the project, and it would do so silently.

Placeholders are not "weaker names", they are the *absence* of a name. Ghidra
mints `FUN_<addr>` for every function it finds, so they are the majority of the
corpus and would win any merge decided by recency, by count, or by whichever
fork happened to be processed last.

The ladder, highest first:

    1 human       hand-written annotations
    2 stabs       Mac debug records: real symbol plus the original .cpp path
    3 symbol      Android C++ symbol tables, demangled
    4 derived     Ghidra named it from a string, import or signature match
    5 placeholder FUN_/sub_/LAB_/Unwind_/thunk_ — the absence of a name

A placeholder may fill an empty slot. It may never displace tiers 1-4.

Ties inside a tier are broken by richer information, then by longer name, then
by binary id — deterministic, so re-running cannot reshuffle results.

Every decision records the winning tier and the runners-up, because "why is
this function called that?" has to stay answerable after the merge.

    ./venv/bin/python kx/name_precedence.py --report
    ./venv/bin/python kx/name_precedence.py --apply
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from . import db, ghidra_env as ge

OUT = ge.resolve_workspace() / "output" / "names"

# Ghidra's auto-generated names. `Unwind_` and `switchD` are its exception and
# jump-table artefacts; `thunk_` prefixes a forwarder. None of them carry
# meaning a person supplied.
PLACEHOLDER_RE = re.compile(
    r"""^(?:
          FUN_[0-9a-fA-F]+
        | SUB_[0-9a-fA-F]+ | sub_[0-9a-fA-F]+
        | LAB_[0-9a-fA-F]+ | loc_[0-9a-fA-F]+
        | Unwind[_@][0-9a-fA-F]+
        | switchD_[0-9a-fA-F]+
        | caseD_[0-9a-fA-F]+
        | DAT_[0-9a-fA-F]+
        | thunk_FUN_[0-9a-fA-F]+
        | entry | _entry
      )$""",
    re.X,
)

HUMAN = 1
STABS = 2
SYMBOL = 3
DERIVED = 4
PLACEHOLDER = 5
TIER_NAME = {HUMAN: "human", STABS: "stabs", SYMBOL: "symbol",
             DERIVED: "derived", PLACEHOLDER: "placeholder"}


def is_placeholder(name: str | None) -> bool:
    return not name or bool(PLACEHOLDER_RE.match(name.strip()))


def tier_of(row: dict) -> int:
    """Classify one func row into the precedence ladder.

    `name_origin` records how Ghidra came by the name. `mangled` means a real
    C++ symbol table entry. `plate` and `namespace` mean the name came from a
    comment block or an enclosing namespace, which a person usually authored.
    `bare` and `none` are the default paths, where placeholders live.
    """
    name = (row.get("name") or "").strip()
    origin = (row.get("name_origin") or "").strip().lower()

    # A hand correction remains authoritative even when the same row also has
    # compiler debug information.  Conversely, a placeholder with a misleading
    # origin is still only a placeholder.
    if not is_placeholder(name) and origin in ("plate", "namespace"):
        return HUMAN
    # A STABS entry names the function AND the .cpp it was compiled from, which
    # no other source in this corpus provides.
    if (row.get("stabs_name") or "").strip():
        return STABS
    if is_placeholder(name):
        return PLACEHOLDER
    if origin == "mangled":
        return SYMBOL
    return DERIVED


def resolved_name(row: dict) -> str | None:
    """Return the actual name represented by the row's winning tier."""
    if tier_of(row) == STABS:
        return (row.get("stabs_name") or "").strip() or None
    return row.get("name")


def rank(row: dict) -> tuple:
    """Sort key: lower is better. Deterministic all the way down."""
    t = tier_of(row)
    has_src = 1 if (row.get("source_file") or "").strip() else 0
    has_sig = 1 if (row.get("signature") or "").strip() else 0
    name = resolved_name(row) or ""
    # Negatives so that "more information" and "longer name" sort earlier.
    return (t, -has_src, -has_sig, -len(name), row.get("binary_id") or 0)


def resolve(rows: list[dict]) -> dict:
    """Pick the best name for one logical function from its members."""
    if not rows:
        return {}
    ordered = sorted(rows, key=rank)
    win = ordered[0]
    wt = tier_of(win)
    return {
        "name": resolved_name(win),
        "tier": wt,
        "tier_name": TIER_NAME[wt],
        "from_binary_id": win.get("binary_id"),
        "source_file": win.get("source_file"),
        "stabs_name": win.get("stabs_name"),
        "signature": win.get("signature"),
        "n_members": len(rows),
        "runners_up": [
            {"name": resolved_name(r), "tier": TIER_NAME[tier_of(r)],
             "binary_id": r.get("binary_id")}
            for r in ordered[1:4]
        ],
        # The whole point: did a real name exist anywhere in this group?
        "would_have_been_overwritten": bool(
            wt == PLACEHOLDER and any(tier_of(r) < PLACEHOLDER for r in rows)),
        "rescued_placeholder": bool(
            wt < PLACEHOLDER and any(tier_of(r) == PLACEHOLDER for r in rows)),
    }


SCHEMA = """
CREATE TABLE IF NOT EXISTS logical_name (
    logical_id  INTEGER PRIMARY KEY,
    name        TEXT,
    tier        INTEGER,
    tier_name   TEXT,
    from_binary_id INTEGER,
    source_file TEXT,
    signature   TEXT,
    n_members   INTEGER,
    detail      TEXT
);
"""


def run(apply: bool) -> None:
    con = db.connect()
    con.executescript(SCHEMA)

    # Pull only bound functions, joined through identity. This is indexed and
    # avoids a full scan of the 500 MB func table.
    rows = con.execute("""
        SELECT i.logical_id, f.binary_id, f.addr, f.name, f.name_origin,
               f.source_file, f.stabs_name, f.signature
        FROM identity i
        JOIN func f ON f.binary_id = i.binary_id AND f.addr = i.addr
        ORDER BY i.logical_id
    """).fetchall()

    groups: dict[int, list[dict]] = {}
    for r in rows:
        groups.setdefault(r["logical_id"], []).append(dict(r))

    tiers = Counter()
    rescued = 0
    multi = 0
    out_rows = []
    for lid, members in groups.items():
        res = resolve(members)
        tiers[res["tier_name"]] += 1
        rescued += res["rescued_placeholder"]
        if len(members) > 1:
            multi += 1
        out_rows.append((lid, res["name"], res["tier"], res["tier_name"],
                         res["from_binary_id"], res["source_file"],
                         res["signature"], res["n_members"],
                         json.dumps({"runners_up": res["runners_up"]})))

    if apply:
        con.executemany(
            "INSERT OR REPLACE INTO logical_name"
            "(logical_id,name,tier,tier_name,from_binary_id,source_file,"
            " signature,n_members,detail) VALUES (?,?,?,?,?,?,?,?,?)", out_rows)
        con.commit()

    summary = {
        "logical_functions_named": len(groups),
        "multi_build_groups": multi,
        "by_tier": dict(tiers),
        "placeholders_rescued_by_a_real_name": rescued,
        "rule": "human > stabs > symbol > derived > placeholder; "
                "a placeholder never displaces a real name",
        "applied": bool(apply),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "name_precedence_summary.json").write_text(json.dumps(summary, indent=1))

    for k, v in summary.items():
        print(f"  {k:<42} {v}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="write the resolved names into logical_name")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    run(apply=a.apply)
