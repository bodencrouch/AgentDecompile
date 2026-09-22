"""Directed matcher runs, identity binding, and named-conflict demotion."""

from __future__ import annotations

import json
from collections import Counter
from typing import Callable

from . import match

PINNED_KINDS = frozenset({"structural", "inline", "callgraph", "anchor", "bsim"})


def persist_status(result: dict, pair_class: str, src_key, dst_key, *, n_instr: int | None = None) -> str:
    """Honor cascade-pinned status; otherwise recompute from score policy.

    PINNED means do not re-score — not ignore independent name contradictions.
    Conflicting authentic canon_keys always demote to verify before bind.
    """
    ev = result.get("evidence") or {}
    if ev.get("quarantine") or ev.get("identity_claim") is False:
        return "review"
    name_conflict = bool(src_key and dst_key and src_key != dst_key)
    kind = result.get("kind")
    pinned = result.get("status")
    proposed = pinned if kind in PINNED_KINDS and pinned else match.status_for(
        result["score"], result["margin"], pair_class,
        ev.get("_content", result.get("content", 0)), ev.get("compunit"), False,
    )
    if proposed not in {"auto", "verify"}:
        return proposed
    from .channel_confidence import allows_auto, allows_verify, channel_confidence

    confidence = channel_confidence(
        primary=str(ev.get("primary_channel") or ev.get("channel") or kind or "fuzzy"),
        evidence=ev, n_instr=n_instr, margin=float(result.get("margin") or 0), unique=True,
    )
    if proposed == "auto" and not allows_auto(confidence, unique=True):
        proposed = "verify"
    if proposed == "verify" and not allows_verify(confidence, unique=True):
        return "review"
    return "verify" if name_conflict and proposed == "auto" else proposed


def bid(con, path: str) -> int:
    row = con.execute("SELECT id FROM binary WHERE repo_path=?", (path,)).fetchone()
    if row is None:
        raise KeyError(path)
    return row[0]


def run_pair(
    con, src_path: str, dst_path: str, note: str, run: str,
    *, progress: Callable[[dict], None] | None = None,
) -> dict:
    from .store import ensure_match_columns

    ensure_match_columns(con)
    src_id, dst_id = bid(con, src_path), bid(con, dst_path)
    res = match.match_binaries(
        con, src_id, dst_id, rounds=4, use_name_features=True, progress=progress,
    )
    sa, sb = res["src"], res["dst"]

    con.execute(
        "DELETE FROM match WHERE run=? AND src_binary=? AND dst_binary=?",
        (run, src_id, dst_id),
    )
    rows = []
    counts: Counter = Counter()
    for addr, result in res["results"].items():
        src_key = sa.funcs[addr]["canon_key"]
        dst_key = sb.funcs[result["dst"]]["canon_key"]
        evidence = dict(result["evidence"])
        evidence["cascade_receipt"] = {
            "stage": result.get("round"), "kind": result.get("kind"),
            "optional_channels": res.get("optional_channels", {}),
        }
        status = persist_status(
            result, res["pair_class"], src_key, dst_key,
            n_instr=sa.funcs[addr].get("n_instr"),
        )
        if src_key and dst_key and src_key != dst_key and status == "verify":
            from .correspondence import enrich_evidence

            evidence = enrich_evidence(evidence, kind=result.get("kind"), status="verify", identity_claim=True)
            evidence["reason"] = "authentic_name_conflict"
        if status not in {"auto", "verify"}:
            from .correspondence import enrich_evidence

            evidence = enrich_evidence(evidence, kind=result.get("kind"), status=status, identity_claim=False)
        counts[status] += 1
        relation = str(evidence.get("relation") or "one_to_one")
        ranges = evidence.get("range") or {}
        rows.append(
            (
                run,
                src_id,
                addr,
                dst_id,
                result["dst"],
                result["score"],
                result["margin"],
                json.dumps(evidence),
                status,
                relation,
                ranges.get("src_end"),
                ranges.get("dst_end"),
            )
        )
    # match.id follows insert order. Sort on (src_addr, dst_addr) - the pair's
    # natural key within one directed run - so ids do not inherit the result
    # dict's insertion order.
    rows.sort(key=lambda r: (r[2], r[4]))
    con.executemany(
        """INSERT INTO match(run, src_binary, src_addr, dst_binary, dst_addr,
                             score, margin, evidence, status, relation, src_end, dst_end)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        rows,
    )
    con.commit()
    named_src = sum(1 for addr in res["results"] if sa.funcs[addr]["canon_key"])
    transferable = sum(
        1
        for addr, result in res["results"].items()
        if sa.funcs[addr]["canon_key"]
        and not sb.funcs[result["dst"]]["canon_key"]
        and persist_status(result, res["pair_class"], sa.funcs[addr]["canon_key"], None,
                           n_instr=sa.funcs[addr].get("n_instr"))
        in ("auto", "verify")
    )
    return {
        "src": src_path,
        "dst": dst_path,
        "note": note,
        "counts": dict(counts),
        "named_src_candidates": named_src,
        "transferable": transferable,
        "src_funcs": len(sa.funcs),
        "dst_funcs": len(sb.funcs),
        "dst_already_named": sum(1 for f in sb.funcs.values() if f["canon_key"]),
        "inlines": res.get("inlines") or [],
    }


def bind_identities(con, run: str, *, commit: bool = True) -> int:
    """Attach matched target functions to the source's logical function.

    Every content-hash refusal fires before the first write: a refused run
    keeps the previous bindings and leaves no transaction open (A1).
    """
    from .correspondence import allows_identity_binding, enrich_evidence
    from .logical import content_hash_index
    from .match_store import quarantined_source_tokens

    scope = "FROM match m WHERE m.run=? AND m.status IN ('auto','verify') AND m.relation='one_to_one'"
    # Refuse before the candidate SELECT and before the DELETE below: the
    # first-wins race keys on binary.content_sha256 (design decision 3), and
    # a NULL would otherwise sort first silently.
    content_hash_index(
        con,
        (
            r[0]
            for r in con.execute(
                f"SELECT m.src_binary {scope} UNION SELECT m.dst_binary {scope}", (run, run)
            )
        ),
    )
    # Same token the matcher persists in evidence.dependencies (A3); a
    # quarantined source on a hash-less build refuses here, before any write.
    quarantined_sources = quarantined_source_tokens(con, run)
    con.execute("DELETE FROM identity WHERE method LIKE ?", (f"match:{run}:%",))
    owned = {
        (r[0], r[1])
        for r in con.execute(
            "SELECT binary_id, addr FROM identity"
        )
    }
    cur = con.execute(
        """SELECT m.dst_binary, m.dst_addr, m.score, m.status, m.evidence,
                  i.logical_id, m.src_binary, m.src_addr,
                  bd.content_sha256 AS dst_hash, bs.content_sha256 AS src_hash
             FROM match m
             JOIN identity i ON i.binary_id=m.src_binary AND i.addr=m.src_addr
             JOIN binary bd ON bd.id=m.dst_binary
             JOIN binary bs ON bs.id=m.src_binary
            WHERE m.run=? AND m.status IN ('auto','verify')
              AND m.relation='one_to_one'
            ORDER BY bd.content_sha256, m.dst_addr, i.logical_id, bs.content_sha256, m.src_addr""",
        (run,),
    )
    candidates: list[tuple[float, tuple, dict]] = []
    # Last write wins per (logical_id, binary_id); the ORDER BY makes that the
    # highest addr rather than whichever row the scan happened to yield last.
    logical_members = {
        (row["logical_id"], row["binary_id"]): row["addr"]
        for row in con.execute("SELECT logical_id,binary_id,addr FROM identity ORDER BY logical_id, binary_id, addr")
    }
    conflicts: list[tuple[str, int, int, int]] = []
    for row in cur:
        evidence = json.loads(row["evidence"] or "{}")
        if not allows_identity_binding(evidence, "one_to_one", quarantined_sources):
            continue
        key = (row["dst_binary"], row["dst_addr"])
        if key in owned:
            continue
        conf = (
            round(0.5 + 0.5 * row["score"], 4)
            if row["status"] == "auto"
            else round(0.35 + 0.45 * row["score"], 4)
        )
        cand = (
            row["logical_id"],
            row["dst_binary"],
            row["dst_addr"],
            conf,
            f"match:{run}:{row['status']}",
            row["evidence"],
        )
        candidates.append((conf, cand, dict(row)))
    best: dict[tuple[int, int], tuple] = {}
    selected_logical: dict[tuple[int, int], int] = dict(logical_members)
    # Total order, dst-major by design: the race decides which source claims a
    # destination, so ties at equal confidence break on the destination first,
    # then logical_id, then source. Builds are keyed by content_sha256, never
    # by binary.id, so build-ingest order cannot pick the winner. Changing
    # this key changes which rows win and is a versioned algorithm change,
    # not a refactor.
    candidates.sort(
        key=lambda item: (
            -item[0],
            item[2]["dst_hash"], item[2]["dst_addr"],
            item[2]["logical_id"], item[2]["src_hash"], item[2]["src_addr"],
        )
    )
    for _conf, cand, row in candidates:
        key = (row["dst_binary"], row["dst_addr"])
        logical_key = (row["logical_id"], row["dst_binary"])
        occupied = selected_logical.get(logical_key)
        if key in best or (occupied is not None and occupied != row["dst_addr"]):
            evidence = enrich_evidence(
                json.loads(row["evidence"] or "{}"), status="ambiguous",
                identity_claim=False, quarantine=True, stage="identity_bind",
            )
            evidence["reason"] = "logical_id_binary_conflict"
            evidence["conflicting_addr"] = occupied
            conflicts.append((json.dumps(evidence), row["src_binary"], row["src_addr"], row["dst_addr"]))
            continue
        best[key] = cand
        selected_logical[logical_key] = row["dst_addr"]
    if conflicts:
        con.executemany(
            "UPDATE match SET status='review', evidence=? WHERE run=? AND src_binary=? AND src_addr=? AND dst_addr=?",
            [(ev, run, src_binary, src_addr, dst_addr) for ev, src_binary, src_addr, dst_addr in conflicts],
        )
    payload = list(best.values())
    con.executemany(
        "INSERT OR REPLACE INTO identity(logical_id,binary_id,addr,confidence,method,evidence)"
        " VALUES(?,?,?,?,?,?)",
        payload,
    )
    if commit:
        con.commit()
    return len(payload)


def dedupe_identity_addrs(con, *, commit: bool = True) -> int:
    rows = con.execute(
        """SELECT binary_id, addr, logical_id, confidence, method, rowid
             FROM identity
            WHERE (binary_id, addr) IN (
                SELECT binary_id, addr FROM identity
                 GROUP BY binary_id, addr HAVING COUNT(*) > 1
            )
            ORDER BY binary_id, addr, confidence DESC, rowid"""
    ).fetchall()
    seen: set[tuple[int, int]] = set()
    drop: list[int] = []
    for row in rows:
        key = (row["binary_id"], row["addr"])
        if key in seen:
            drop.append(row["rowid"])
        else:
            seen.add(key)
    if drop:
        con.executemany("DELETE FROM identity WHERE rowid=?", [(i,) for i in drop])
        if commit:
            con.commit()
    return len(drop)


def downgrade_named_conflicts(con, run: str | None = None, *, commit: bool = True) -> int:
    """Demote stored auto matches when independent canonical names disagree."""
    rows = con.execute(
        """SELECT match.rowid, match.evidence FROM match
            WHERE status='auto'
              AND (? IS NULL OR run=?)
              AND EXISTS (
                  SELECT 1
                    FROM func src
                    JOIN func dst
                      ON dst.binary_id=match.dst_binary
                     AND dst.addr=match.dst_addr
                   WHERE src.binary_id=match.src_binary
                     AND src.addr=match.src_addr
                     AND src.canon_key IS NOT NULL
                     AND src.canon_key<>''
                     AND dst.canon_key IS NOT NULL
                     AND dst.canon_key<>''
                     AND src.canon_key<>dst.canon_key
              )""",
        (run, run),
    ).fetchall()
    for row in rows:
        evidence = json.loads(row["evidence"] or "{}")
        evidence["status_band"] = "verified"
        evidence["reason"] = "authentic_name_conflict"
        con.execute("UPDATE match SET status='verify', evidence=? WHERE rowid=?", (json.dumps(evidence), row["rowid"]))
    if commit:
        con.commit()
    return len(rows)


def reclassify_existing(con, run: str) -> tuple[int, int, int]:
    """Reclassify matches and rebuild derived identities in one transaction."""
    con.execute("BEGIN IMMEDIATE")
    try:
        changed = downgrade_named_conflicts(con, run, commit=False)
        bound = bind_identities(con, run, commit=False)
        dropped = dedupe_identity_addrs(con, commit=False)
        con.commit()
        return changed, bound, dropped
    except Exception:
        con.rollback()
        raise


def run_registry_pairs(con, pairs: list[tuple[str, str, str]], run: str = "v1") -> list[dict]:
    """Match each directed (src, dst, note) pair from a corpus registry."""
    summary = []
    for src, dst, note in pairs:
        summary.append(run_pair(con, src, dst, note, run))
    downgrade_named_conflicts(con, run)
    bind_identities(con, run)
    return summary
