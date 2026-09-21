"""Build the logical-function identity layer from name evidence."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict

from . import canon, match

BACKFILL_HINT = "run `corpus.backfill --pass content_sha256` on the store first"

GENERIC = re.compile(
    r"^(map|set|list|vector|string|pair|iterator|allocator|_?init|_?fini|main|"
    r"entry|start|operator[^A-Za-z]|__.*)$"
)


def eligible(row) -> bool:
    key = row["canon_key"]
    if not key or canon.is_library(key):
        return False
    if canon.from_fid(row["plate"]):
        return False
    name = row["name"] if "name" in row.keys() else None
    if canon.is_eh_clone(name, row["plate"]):
        return False
    if not row["canon_class"] and GENERIC.match(row["canon_method"] or ""):
        return False
    return True


def content_hash_index(con, binary_ids) -> dict[int, str]:
    """``binary.id`` -> ``content_sha256`` for the builds in *binary_ids*.

    The content hash is the only build key the cascade may order or tie-break
    on (never a rowid, never a slug). A build without one, or two builds
    sharing one, leaves that key undefined, so this refuses instead of
    falling back: ``ValueError`` names the offending slugs (sorted) and the
    backfill verb that supplies the hash.
    """
    ids = sorted({int(i) for i in binary_ids})
    if not ids:
        return {}
    marks = ",".join("?" for _ in ids)
    rows = con.execute(
        f"SELECT id, slug, content_sha256 FROM binary WHERE id IN ({marks})", ids
    ).fetchall()
    index: dict[int, str] = {}
    missing: list[str] = []
    by_hash: dict[str, list[str]] = defaultdict(list)
    seen: set[int] = set()
    for row in rows:
        seen.add(int(row["id"]))
        digest = str(row["content_sha256"] or "").strip()
        if not digest:
            missing.append(str(row["slug"]))
            continue
        index[int(row["id"])] = digest
        by_hash[digest].append(str(row["slug"]))
    # A referenced id with no binary row has no hash either.
    missing.extend(f"binary id {i} (no binary row)" for i in ids if i not in seen)
    if missing:
        raise ValueError(
            "binary.content_sha256 is NULL or blank for "
            + ", ".join(sorted(missing))
            + f"; the cascade keys on it and refuses to guess; {BACKFILL_HINT}"
        )
    dupes = {h: sorted(slugs) for h, slugs in by_hash.items() if len(slugs) > 1}
    if dupes:
        detail = "; ".join(f"{h[:16]}: {', '.join(slugs)}" for h, slugs in sorted(dupes.items()))
        raise ValueError(
            "binary.content_sha256 is shared by more than one build, so it is not a "
            f"total key: {detail}. Register each image once."
        )
    return index


def build(con) -> dict[str, int]:
    con.execute("DELETE FROM identity")
    con.execute("DELETE FROM logical_function")
    con.commit()

    excluded = tuple(sorted(canon.DRM_EXCLUDED))
    if excluded:
        marks = ",".join("?" for _ in excluded)
        scope_where = f"WHERE f.canon_key IS NOT NULL AND b.repo_path NOT IN ({marks})"
        params = excluded
    else:
        scope_where = "WHERE f.canon_key IS NOT NULL"
        params = ()
    # Refuse before the driving SELECT: an ORDER BY over a NULL hash would
    # sort silently, which is the fallback design decision 3 forbids.
    content_hash_index(
        con,
        (
            r[0]
            for r in con.execute(
                f"SELECT DISTINCT f.binary_id FROM func f JOIN binary b ON b.id=f.binary_id {scope_where}",
                params,
            )
        ),
    )
    rows = con.execute(
        f"""SELECT f.binary_id, f.addr, f.canon_key, f.canon_class, f.canon_method,
                  f.canon_arity, f.name_origin, f.is_thunk, f.n_instr, f.n_blocks,
                  f.cyclomatic, f.n_callees, f.size, f.signature, f.plate,
                  f.strings, f.consts, f.param_count, f.name,
                  b.game, b.slug, b.role, b.content_sha256
             FROM func f JOIN binary b ON b.id=f.binary_id
            {scope_where}
            ORDER BY f.canon_key, b.content_sha256, f.addr""",
        params,
    ).fetchall()

    # Rows arrive sorted by (canon_key, content_sha256, addr), so every dict
    # built below in insertion order (groups, subgroups, sub_by_bin) is totally
    # ordered on build-invariant keys and logical ids are assigned in
    # canon_key order. binary.id never reaches a persisted value here.
    groups: dict[str, list] = defaultdict(list)
    for row in rows:
        if eligible(row):
            groups[row["canon_key"]].append(row)

    n_logical = 0
    n_bound = 0
    counters: Counter = Counter()
    logicals = []
    identities = []

    for key, members in groups.items():
        arities = {m["canon_arity"] for m in members if m["canon_arity"] is not None}
        subgroups: dict[object, list] = defaultdict(list)
        if len(arities) > 1:
            for m in members:
                subgroups[m["canon_arity"]].append(m)
        else:
            subgroups[None] = members

        for arity, sub in subgroups.items():
            # Keyed by the build's content hash, never by binary.id.
            sub_by_bin: dict[str, list] = defaultdict(list)
            for m in sub:
                sub_by_bin[m["content_sha256"]].append(m)

            if all(len(v) == 1 for v in sub_by_bin.values()):
                n_logical += 1
                _emit(logicals, identities, n_logical, key, arity, sub, 0.99, "name-unique", {})
                n_bound += len(sub)
                counters["name-unique"] += len(sub)
                continue

            for scored_members, note in resolve_ambiguous(sub_by_bin):
                n_logical += 1
                _emit_scored(logicals, identities, n_logical, key, arity, scored_members, note)
                n_bound += len(scored_members)
                for _m, _c, meth in scored_members:
                    counters[meth] += 1

    con.executemany(
        """INSERT INTO logical_function(id, canon_key, canon_class, canon_method, game,
                                        best_name, best_signature, source_file, object_file,
                                        n_members, notes)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        logicals,
    )
    con.executemany(
        "INSERT OR REPLACE INTO identity(logical_id,binary_id,addr,confidence,method,evidence)"
        " VALUES(?,?,?,?,?,?)",
        identities,
    )
    con.commit()
    return {"logical": n_logical, "bound": n_bound, **dict(counters)}


def _feat(m):
    return (
        set(json.loads(m["strings"] or "[]")),
        set(json.loads(m["consts"] or "[]")),
    )


def _similar(a, b) -> float:
    sa, ca = _feat(a)
    sb, cb = _feat(b)
    parts = [
        0.30 * match.relsim(a["n_instr"], b["n_instr"]),
        0.25 * match.relsim(a["n_blocks"], b["n_blocks"]),
        0.15 * match.relsim(a["cyclomatic"], b["cyclomatic"]),
        0.10 * match.relsim(a["n_callees"], b["n_callees"]),
    ]
    score = sum(parts)
    weight = 0.80
    if sa or sb:
        score += 0.14 * match.jaccard(sa, sb)
        weight += 0.14
    if ca or cb:
        score += 0.06 * match.jaccard(ca, cb)
        weight += 0.06
    return score / weight


def resolve_ambiguous(sub_by_bin: dict[str, list]):
    """Split a same-name group using structure. Prefer donor/anchor roles.

    *sub_by_bin* is keyed by ``binary.content_sha256``; the reference build
    and the slot order tie-break on that hash, never on a rowid.
    """

    def rank(digest):
        role = (sub_by_bin[digest][0]["role"] or "") if "role" in sub_by_bin[digest][0].keys() else ""
        pri = 0 if role in ("donor", "anchor") else 1
        return (len(sub_by_bin[digest]), pri, digest)

    ref_hash = min(sub_by_bin, key=rank)
    slots = [
        [(m, 0.97, "name-reference")]
        for m in sorted(sub_by_bin[ref_hash], key=lambda m: (-(m["n_instr"] or 0), m["content_sha256"], m["addr"]))
    ]

    for digest in sorted(sub_by_bin):
        lst = sub_by_bin[digest]
        if digest == ref_hash:
            continue
        pairs = []
        for mi, m in enumerate(lst):
            for si, slot in enumerate(slots):
                pairs.append((_similar(slot[0][0], m), si, mi))
        pairs.sort(reverse=True)
        used_slot, used_m = set(), set()
        best_for_m: dict[int, list[float]] = defaultdict(list)
        for s, si, mi in pairs:
            best_for_m[mi].append(s)
        for s, si, mi in pairs:
            if si in used_slot or mi in used_m:
                continue
            scores = sorted(best_for_m[mi], reverse=True)
            margin = scores[0] - scores[1] if len(scores) > 1 else 1.0
            used_slot.add(si)
            used_m.add(mi)
            if s >= 0.75 and margin >= 0.05:
                conf, meth = 0.95, "name-disambiguated"
            elif s >= 0.60:
                conf, meth = 0.80, "name-weak"
            else:
                conf, meth = 0.55, "name-ambiguous"
            slots[si].append((lst[mi], conf, meth))
        for mi, m in enumerate(lst):
            if mi not in used_m:
                slots.append([(m, 0.50, "name-unplaced")])

    for slot in slots:
        yield slot, {"slot_size": len(slot)}


def _emit_scored(logicals, identities, lid, key, arity, scored, note):
    members = [m for m, _c, _meth in scored]
    best = _best_signature(members)
    logicals.append(
        (
            lid,
            key,
            members[0]["canon_class"],
            members[0]["canon_method"],
            _game_of(members),
            best[0],
            best[1],
            None,
            None,
            len(members),
            json.dumps({"arity": arity, **note}),
        )
    )
    for m, conf, meth in scored:
        identities.append(
            (
                lid,
                m["binary_id"],
                m["addr"],
                conf,
                meth,
                json.dumps({"canon_key": key, "origin": m["name_origin"]}),
            )
        )


def _emit(logicals, identities, lid, key, arity, members, conf, method, note):
    best = _best_signature(members)
    logicals.append(
        (
            lid,
            key,
            members[0]["canon_class"],
            members[0]["canon_method"],
            _game_of(members),
            best[0],
            best[1],
            None,
            None,
            len(members),
            json.dumps({"arity": arity, "method": method, **note}),
        )
    )
    for m in members:
        identities.append(
            (
                lid,
                m["binary_id"],
                m["addr"],
                conf,
                method,
                json.dumps({"canon_key": key, "origin": m["name_origin"]}),
            )
        )


def _game_of(members) -> str | None:
    games = {m["game"] for m in members if m["game"]}
    if len(games) == 1:
        return games.pop()
    return "SHARED" if games else None


def _best_signature(members) -> tuple[str | None, str | None]:
    name = members[0]["canon_key"]
    # First-wins picks below run over (content_sha256, addr) order, not slot
    # or insertion order, so the chosen prototype is a function of the
    # members' bytes and never of build-ingest order.
    ordered = sorted(members, key=lambda m: (m["content_sha256"], m["addr"]))
    sig = None
    for m in ordered:
        if m["name_origin"] == "mangled" and m["plate"]:
            return name, m["plate"].splitlines()[0]
    for m in ordered:
        if m["name_origin"] == "plate" and m["plate"]:
            sig = m["plate"].splitlines()[0]
            break
    if sig is None:
        for m in ordered:
            if m["signature"]:
                sig = m["signature"]
                break
    return name, sig
