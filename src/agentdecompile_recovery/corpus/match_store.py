"""Store-backed identity matcher (kotorxid ``kx.match.Binary`` / ``match_binaries``).

Evidence-fusion cascade: identical-image short-circuit, authentic symbols, unique
reloc/instr hashes, rare refs, call-graph, structural islands, optional BSim/ABI
corroboration. Candidate generation is not acceptance. Identity bind is not
objdiff-0 byte proof and does not authorize type/source copy.
"""

from __future__ import annotations

import json
from collections import defaultdict

from . import canon
from .callgraph_propagate import (
    absorb_anchors,
    interesting_const,
    interesting_string,
    propagate_call_graph,
    record_pairs,
    unique_index_anchors,
)
from .correspondence import enrich_evidence
from .fingerprint_hashes import attach_hashes
from .identical_image import short_circuit_match
from .match_islands import island_evidence, leftover_inlines, unique_structural_pairs
from .store import ensure_func_columns
from .symbol_provenance import authentic_named_index
from .match_engine import (
    MAX_CONST_DF,
    MAX_STRING_DF,
    PAIR_POLICY,
    _basename,
    _passes,
    candidate_margin,
    classify_pair,
    score_features,
    shape_key,
    status_for,
)


class Binary:
    """In-memory view of one binary's functions and call graph."""

    def __init__(self, con, binary_id: int):
        self.id = binary_id
        ensure_func_columns(con)
        row = con.execute("SELECT * FROM binary WHERE id=?", (binary_id,)).fetchone()
        self.meta = dict(row)
        self.slug = row["slug"]
        self.funcs: dict[int, dict] = {}
        cols = {d[0] for d in con.execute("PRAGMA table_info(func)").fetchall()}
        hash_select = ""
        for col in ("hash_reloc", "hash_instr", "hash_mnemonic", "hash_raw", "symbol_provenance"):
            if col in cols:
                hash_select += f",{col}"
        for rec in con.execute(
            f"""SELECT addr,name,namespace,canon_key,canon_arity,canon_method,canon_class,
                      name_origin,size,is_thunk,n_instr,n_blocks,n_edges,back_edges,
                      cyclomatic,n_callees,indirect_calls,data_refs,mnem,strings,consts,
                      ext_calls,block_hashes,plate,signature,source,param_count,
                      source_file,object_file,calling_convention{hash_select}
                 FROM func WHERE binary_id=?""",
            (binary_id,),
        ):
            d = dict(rec)
            d["strings"] = json.loads(d["strings"] or "[]")
            d["consts"] = json.loads(d["consts"] or "[]")
            d["ext_calls"] = json.loads(d["ext_calls"] or "[]")
            d["mnem"] = json.loads(d["mnem"] or "{}")
            d["block_hashes"] = json.loads(d["block_hashes"] or "[]")
            if not d.get("hash_reloc"):
                d = attach_hashes(d)
            if canon.is_eh_clone(d["name"], d["plate"]):
                continue
            self.funcs[d["addr"]] = d

        self.decomp: dict[int, dict] = {}
        try:
            for rec in con.execute(
                """SELECT addr,n_tokens,n_lines,max_nest,n_calls,n_locals,n_deref,
                          n_index,n_field,ctrl,ops,skeleton_hash
                     FROM decomp WHERE binary_id=? AND ok=1""",
                (binary_id,),
            ):
                d = dict(rec)
                d["ctrl"] = json.loads(d["ctrl"] or "{}")
                d["ops"] = json.loads(d["ops"] or "{}")
                self.decomp[d["addr"]] = d
        except Exception:
            pass

        self.callees: dict[int, set[int]] = defaultdict(set)
        self.callers: dict[int, set[int]] = defaultdict(set)
        for a, b in con.execute(
            "SELECT caller_addr, callee_addr FROM calledge WHERE binary_id=?", (binary_id,)
        ):
            self.callees[a].add(b)
            self.callers[b].add(a)
        self._index()

    def _index(self) -> None:
        self.by_string: dict[str, list[int]] = defaultdict(list)
        self.by_const: dict[int, list[int]] = defaultdict(list)
        self.by_ext: dict[str, list[int]] = defaultdict(list)
        self.by_shape: dict[tuple, list[int]] = defaultdict(list)
        self.by_unit: dict[str, list[int]] = defaultdict(list)
        self.by_skeleton: dict[str, list[int]] = defaultdict(list)
        self.by_hash_reloc: dict[str, list[int]] = defaultdict(list)
        self.by_hash_instr: dict[str, list[int]] = defaultdict(list)
        self.by_hash_mnemonic: dict[str, list[int]] = defaultdict(list)
        for addr, f in self.funcs.items():
            for s in f["strings"]:
                self.by_string[s].append(addr)
            for c in f["consts"]:
                self.by_const[c].append(addr)
            for e in f["ext_calls"]:
                self.by_ext[e].append(addr)
            self.by_shape[shape_key(f)].append(addr)
            unit = _basename(f.get("source_file"))
            if unit:
                self.by_unit[unit].append(addr)
            for field, index in (
                ("hash_reloc", self.by_hash_reloc),
                ("hash_instr", self.by_hash_instr),
                ("hash_mnemonic", self.by_hash_mnemonic),
            ):
                digest = f.get(field)
                if not digest:
                    continue
                # Auto-seed indexes require non-tiny bodies; mnemonic stays
                # candidate-generation only (never absorb_anchors).
                if field != "hash_mnemonic" and (f.get("n_instr") or 0) < 8:
                    continue
                index[digest].append(addr)
        for addr, d in self.decomp.items():
            h = d.get("skeleton_hash")
            if h:
                self.by_skeleton[h].append(addr)

    def candidates_named(self) -> dict[str, list[int]]:
        """Legacy: all canon keys. Prefer ``candidates_named_authentic`` for channel I."""
        out: dict[str, list[int]] = defaultdict(list)
        for addr, f in self.funcs.items():
            if f["canon_key"] and not canon.is_library(f["canon_key"]):
                out[f["canon_key"]].append(addr)
        return out

    def candidates_named_authentic(self) -> dict[str, list[int]]:
        return authentic_named_index(self.funcs)


def candidate_pairs(sa: Binary, sb: Binary, src_addr: int, mapping: dict[int, int]) -> set[int]:
    f = sa.funcs[src_addr]
    from collections import Counter

    cands: Counter = Counter()
    for s in f["strings"]:
        hits = sb.by_string.get(s)
        if hits and len(hits) <= MAX_STRING_DF:
            for h in hits:
                cands[h] += 3
    for c in f["consts"]:
        hits = sb.by_const.get(c)
        if hits and len(hits) <= MAX_CONST_DF:
            for h in hits:
                cands[h] += 2
    for e in f["ext_calls"]:
        hits = sb.by_ext.get(e)
        if hits and len(hits) <= MAX_CONST_DF:
            for h in hits:
                cands[h] += 1
    for field in ("hash_reloc", "hash_instr", "hash_mnemonic"):
        digest = f.get(field)
        if not digest:
            continue
        index = getattr(sb, f"by_{field}", {})
        hits = index.get(digest)
        if hits and len(hits) <= MAX_CONST_DF:
            for h in hits:
                cands[h] += 4
    for callee in sa.callees.get(src_addr, ()):
        mapped = mapping.get(callee)
        if mapped is not None:
            for h in sb.callers.get(mapped, ()):
                cands[h] += 2
    for caller in sa.callers.get(src_addr, ()):
        mapped = mapping.get(caller)
        if mapped is not None:
            for h in sb.callees.get(mapped, ()):
                cands[h] += 2
    unit = _basename(f.get("source_file"))
    if unit:
        for h in sb.by_unit.get(unit, ())[:400]:
            cands[h] += 2
    if not cands:
        for h in sb.by_shape.get(shape_key(f), ())[:200]:
            cands[h] += 1
    skel = (sa.decomp.get(src_addr) or {}).get("skeleton_hash")
    if skel:
        for h in sb.by_skeleton.get(skel, ())[:200]:
            cands[h] += 2
    return {c for c in cands if c in sb.funcs}


def _classify_store(sa: Binary, sb: Binary) -> str:
    return classify_pair(sa.meta, sb.meta)


def _fuse_bsim(con, sa: Binary, sb: Binary, mapping: dict[int, int], results: dict, pair_class: str) -> dict:
    """Optional BSim significance corroboration when a bsim_hit table exists.

    Returns a skip/ok receipt. Missing table is explicit skip, not silent green.
    Similarity is normalized to [0,1]. kind=bsim (PINNED) with status=verify.
    """
    receipt: dict = {"ok": False, "skipped": False, "hits_used": 0}
    try:
        from agentdecompile_recovery.symbol_map import BSIM_TRUSTED_SIGNIFICANCE
    except Exception:
        BSIM_TRUSTED_SIGNIFICANCE = 30.0
    try:
        rows = con.execute(
            """SELECT src_addr, dst_addr, similarity, significance
               FROM bsim_hit WHERE src_binary=? AND dst_binary=?""",
            (sa.id, sb.id),
        ).fetchall()
    except Exception as exc:
        receipt.update(skipped=True, reason="missing_bsim_hit_table", error=type(exc).__name__)
        return receipt
    taken = set(mapping.values())
    by_src: dict[int, list] = defaultdict(list)
    for src, dst, sim, sig in rows:
        sim_f = float(sim or 0)
        if sim_f > 1.0:
            sim_f = sim_f / 100.0
        by_src[int(src)].append((int(dst), max(0.0, min(1.0, sim_f)), float(sig or 0)))
    for src, hits in by_src.items():
        if src in mapping or src not in sa.funcs:
            continue
        hits = sorted(hits, key=lambda t: (-t[2], -t[1]))
        if not hits:
            continue
        best_dst, sim, sig = hits[0]
        if best_dst in taken or best_dst not in sb.funcs:
            continue
        if sig < BSIM_TRUSTED_SIGNIFICANCE:
            continue
        second_sig = hits[1][2] if len(hits) > 1 else 0.0
        if len(hits) > 1 and (sig - second_sig) < 5.0:
            continue
        tiny = (sa.funcs[src].get("n_instr") or 0) < 8
        if tiny and sim >= 0.99:
            continue
        unique = len([h for h in hits if h[2] >= BSIM_TRUSTED_SIGNIFICANCE]) == 1
        if not unique:
            continue
        mapping[src] = best_dst
        taken.add(best_dst)
        results[src] = {
            "dst": best_dst,
            "score": min(0.95, 0.55 + sim * 0.4),
            "margin": max(0.1, (sig - second_sig) / 100.0),
            "evidence": enrich_evidence(
                {"bsim": sim, "bsim_significance": sig, "channel": "S"},
                kind="bsim",
                status="verify",
                identity_claim=True,
            ),
            "round": "bsim",
            "kind": "bsim",
            "status": "verify",
        }
        receipt["hits_used"] += 1
    receipt["ok"] = True
    receipt["row_count"] = len(rows)
    return receipt


def match_binaries(
    con,
    src_id: int,
    dst_id: int,
    rounds: int = 3,
    seed: dict[int, int] | None = None,
    restrict_src: set[int] | None = None,
    use_name_features: bool = True,
    quiet: bool = True,
) -> dict:
    sa, sb = Binary(con, src_id), Binary(con, dst_id)
    early = short_circuit_match(sa, sb)
    if early is not None:
        return early
    same_arch = (sa.meta["arch"], sa.meta["bits"]) == (sb.meta["arch"], sb.meta["bits"])
    pair_class = _classify_store(sa, sb)
    policy = PAIR_POLICY[pair_class]
    mapping: dict[int, int] = dict(seed or {})
    taken = set(mapping.values())
    results: dict[int, dict] = {}

    src_addrs = [
        a
        for a, f in sa.funcs.items()
        if not f["is_thunk"] and (f["n_instr"] or 0) >= 4 and (restrict_src is None or a in restrict_src)
    ]
    dst_eligible = {
        a
        for a, f in sb.funcs.items()
        if not f["is_thunk"] and (f["n_instr"] or 0) >= 4
    }
    src_eligible = set(src_addrs)
    absorb_anchors(
        mapping,
        unique_index_anchors(
            sa.candidates_named_authentic(),
            sb.candidates_named_authentic(),
            src_eligible=src_eligible,
            dst_eligible=dst_eligible,
        ),
    )
    for left_idx, right_idx in (
        (sa.by_hash_reloc, sb.by_hash_reloc),
        (sa.by_hash_instr, sb.by_hash_instr),
    ):
        absorb_anchors(
            mapping,
            unique_index_anchors(
                left_idx,
                right_idx,
                src_eligible=src_eligible,
                dst_eligible=dst_eligible,
                key_ok=lambda key: bool(key) and len(str(key)) >= 16,
            ),
        )
    absorb_anchors(
        mapping,
        unique_index_anchors(
            sa.by_string,
            sb.by_string,
            src_eligible=src_eligible,
            dst_eligible=dst_eligible,
            key_ok=interesting_string,
        ),
    )
    absorb_anchors(
        mapping,
        unique_index_anchors(
            sa.by_const,
            sb.by_const,
            src_eligible=src_eligible,
            dst_eligible=dst_eligible,
            key_ok=interesting_const,
        ),
    )
    record_pairs(
        results,
        [(src, dst, "anchor") for src, dst in mapping.items()],
        id_field="addr",
        left_lookup=sa.funcs,
        right_lookup=sb.funcs,
        round_label="anchor",
        pair_class=pair_class,
    )
    for addr, result in list(results.items()):
        if result.get("kind") == "anchor":
            digest = sa.funcs[addr].get("hash_reloc")
            code_eq = "reloc" if digest and sb.funcs[result["dst"]].get("hash_reloc") == digest else None
            result["evidence"] = enrich_evidence(
                result.get("evidence"),
                kind="anchor",
                status=result.get("status") or "auto",
                code_equality=code_eq,
                identity_claim=True,
            )
    record_pairs(
        results,
        propagate_call_graph(
            sa.callees,
            sa.callers,
            sb.callees,
            sb.callers,
            mapping,
            src_eligible=src_eligible,
            dst_eligible=dst_eligible,
        ),
        id_field="addr",
        left_lookup=sa.funcs,
        right_lookup=sb.funcs,
        pair_class=pair_class,
    )
    taken = set(mapping.values())
    bsim_receipt = _fuse_bsim(con, sa, sb, mapping, results, pair_class)
    taken = set(mapping.values())

    for rnd in range(rounds):
        new = 0
        scored: list[tuple[float, float, int, int, dict, float, int | None]] = []
        # Mapping is unchanged while this round gathers all scores.  Build its
        # string-keyed view once instead of once per source function.
        int_map = {str(k): str(v) for k, v in mapping.items()} if mapping else None
        for a in src_addrs:
            if a in mapping:
                continue
            cands = candidate_pairs(sa, sb, a, mapping)
            cands -= taken
            if not cands:
                continue
            fa = sa.funcs[a]
            best = second = 0.0
            best_b = None
            second_b = None
            best_ev: dict = {}
            for b in cands:
                fb = dict(sb.funcs[b])
                if use_name_features is False:
                    fa_score = {**fa, "canon_arity": None}
                    fb = {**fb, "canon_arity": None}
                else:
                    fa_score = fa
                if sa.decomp.get(a):
                    fa_score = {**fa_score, "decomp": sa.decomp[a]}
                if sb.decomp.get(b):
                    fb = {**fb, "decomp": sb.decomp[b]}
                s, ev = score_features(fa_score, fb, same_arch=same_arch, mapping=int_map)
                ev = dict(ev)
                if s > best:
                    second, second_b, best, best_b, best_ev = best, best_b, s, b, ev
                elif s > second:
                    second, second_b = s, b
            if best_b is not None:
                margin = candidate_margin(best, second, len(cands))
                scored.append((best, margin, a, best_b, best_ev, second, second_b))

        scored.sort(key=lambda t: (-t[0], -t[1]))
        for best, margin, a, b, ev, second, second_b in scored:
            if a in mapping or b in taken:
                continue
            if _passes(policy["verify"], best, margin, ev.get("_content", 0)) and ev.get("compunit") != 0.0:
                mapping[a] = b
                taken.add(b)
                results[a] = {
                    "dst": b,
                    "score": best,
                    "margin": margin,
                    "evidence": enrich_evidence(ev, status="verify", identity_claim=True),
                    "round": rnd,
                }
                new += 1
            elif a not in results or (results[a].get("kind") not in {"callgraph", "anchor", "bsim"} and best > results[a]["score"]):
                alts = [{"dst": b, "score": best}]
                if second_b is not None and second > 0 and abs(best - second) < 0.05:
                    alts.append({"dst": second_b, "score": second})
                    results[a] = {
                        "dst": b,
                        "score": best,
                        "margin": margin,
                        "evidence": enrich_evidence(ev, status="ambiguous", alternatives=alts, identity_claim=False),
                        "round": rnd,
                        "status": "review",
                        "kind": "ambiguous",
                    }
                else:
                    results[a] = {
                        "dst": b,
                        "score": best,
                        "margin": margin,
                        "evidence": enrich_evidence(ev),
                        "round": rnd,
                    }
        if new:
            grown = record_pairs(
                results,
                propagate_call_graph(
                    sa.callees,
                    sa.callers,
                    sb.callees,
                    sb.callers,
                    mapping,
                    src_eligible=src_eligible,
                    dst_eligible=dst_eligible,
                ),
                id_field="addr",
                left_lookup=sa.funcs,
                right_lookup=sb.funcs,
                round_label=rnd,
                pair_class=pair_class,
            )
            taken = set(mapping.values())
            new += grown
        if new == 0:
            break

    unmatched_src = [sa.funcs[a] for a in src_addrs if a not in mapping]
    unmatched_dst = [sb.funcs[b] for b in dst_eligible if b not in taken]
    for src_addr, dst_addr in unique_structural_pairs(unmatched_src, unmatched_dst, id_of=lambda fn: fn["addr"]):
        if src_addr in mapping or dst_addr in taken:
            continue
        mapping[src_addr] = dst_addr
        taken.add(dst_addr)
        ev = island_evidence(sa.funcs[src_addr], sb.funcs[dst_addr])
        results[src_addr] = {
            "dst": dst_addr,
            "score": 0.8,
            "margin": 1.0,
            "evidence": enrich_evidence(ev, kind="structural", status="verify", identity_claim=True),
            "round": "structural",
            "kind": "structural",
            "status": "verify",
        }
    inlines = leftover_inlines(
        [sa.funcs[a] for a in src_addrs if a not in mapping],
        [sb.funcs[b] for b in taken],
    )
    for hit in inlines:
        src_addr = hit["missing_id"]
        if src_addr in results:
            continue
        results[src_addr] = {
            "dst": hit["host_id"],
            "score": 0.5,
            "margin": 1.0,
            "evidence": enrich_evidence(
                {
                    "inline": 1.0,
                    "block_count": hit["block_count"],
                    "propagation_kind": "inline",
                },
                kind="inline",
                status="review",
                relation="inline",
                identity_claim=False,
            ),
            "round": "inline",
            "kind": "inline",
            "status": "review",
        }
    from .binexport import binexport_available
    from .emulate_verify import unicorn_available

    return {
        "mapping": mapping,
        "results": results,
        "src": sa,
        "dst": sb,
        "pair_class": pair_class,
        "inlines": inlines,
        "optional_channels": {
            "bsim": bsim_receipt,
            "binexport": {"skipped": True, "reason": "prep_only", "available": binexport_available()},
            "emulate": {"skipped": True, "reason": "residue_path_not_configured", "available": unicorn_available()},
            "donor_schedule": {"skipped": True, "reason": "use spanning_forest_pairs at pair-prep"},
            "channel_confidence": {"wired": True, "note": "consult allows_auto/allows_verify when promoting auto"},
        },
    }


__all__ = ["Binary", "candidate_pairs", "match_binaries", "status_for"]
