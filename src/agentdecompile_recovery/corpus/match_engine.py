"""Multi-signal identity matcher ported from kotorxid `kx/match.py`.

Does not compare raw bytes or absolute addresses. Candidates are blocked by
shared strings, constants, imports, compilation unit, and decompiled shape.
Acceptance uses measured per-pair-class (score, margin, content-channel) triples.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any, Iterable

from .callgraph_propagate import (
    absorb_anchors,
    record_pairs,
    interesting_const,
    interesting_string,
    propagate_call_graph,
    unique_index_anchors,
)
from .fuzzy_fingerprint import fuzzy_similarity
from .match_islands import island_evidence, leftover_inlines, unique_structural_pairs

MAX_STRING_DF = 12
MAX_CONST_DF = 12

WEIGHTS = {
    "strings": 3.0,
    "consts": 1.6,
    "ext": 1.2,
    "struct": 2.0,
    "mnem": 1.4,
    "neighbors": 2.4,
    "arity": 0.5,
    "compunit": 2.8,
    "decomp": 2.6,
    "fuzzy_hash": 1.0,
}
CONTENT_CHANNELS = ("strings", "consts", "ext", "neighbors", "compunit", "decomp", "fuzzy_hash")
CONTENT_FLOOR = 0.5
CONTENT_FLOORS = {"decomp": 0.90, "fuzzy_hash": 0.86}

PAIR_POLICY = {
    "same_platform": {"auto": (0.70, 0.06, 1), "verify": (0.62, 0.04, 1), "review": (0.55, 0.00, 0)},
    "cross_format": {"auto": (0.70, 0.12, 2), "verify": (0.70, 0.06, 1), "review": (0.60, 0.00, 0)},
    "cross_arch": {"auto": (0.70, 0.12, 2), "verify": (0.70, 0.08, 1), "review": (0.65, 0.00, 0)},
    "cross_game": {"auto": (0.75, 0.12, 2), "verify": (0.75, 0.08, 1), "review": (0.70, 0.00, 0)},
}


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def relsim(x, y) -> float:
    x = x or 0
    y = y or 0
    if x == y:
        return 1.0
    m = max(abs(x), abs(y))
    if m == 0:
        return 1.0
    return max(0.0, 1.0 - abs(x - y) / m)


def cosine(a: dict, b: dict) -> float:
    if not a or not b:
        return 0.0
    # Sorted iteration: float accumulation order must not follow hash order.
    keys = sorted(set(a) | set(b))
    na = math.sqrt(sum(v * v for _, v in sorted(a.items())))
    nb = math.sqrt(sum(v * v for _, v in sorted(b.items())))
    if not na or not nb:
        return 0.0
    return sum(a.get(k, 0) * b.get(k, 0) for k in keys) / (na * nb)


def shape_key(fn: dict[str, Any]) -> tuple:
    n_blocks = fn.get("n_blocks") or 0
    n_instr = fn.get("n_instr") or 0
    return (
        n_blocks,
        fn.get("cyclomatic") or 0,
        min(fn.get("n_callees") or 0, 12),
        0 if n_instr <= 0 else int(math.log(n_instr, 1.25)),
    )


def _basename(path: str | None) -> str | None:
    if not path:
        return None
    return path.replace("\\", "/").rsplit("/", 1)[-1].lower()


def classify_pair(left_meta: dict[str, Any], right_meta: dict[str, Any]) -> str:
    same_arch = (left_meta.get("arch"), left_meta.get("bits")) == (
        right_meta.get("arch"),
        right_meta.get("bits"),
    )
    if left_meta.get("game") and right_meta.get("game") and left_meta.get("game") != right_meta.get("game"):
        return "cross_game"
    if not same_arch:
        return "cross_arch"
    if left_meta.get("format") == right_meta.get("format"):
        return "same_platform"
    return "cross_format"


def _content_count(ev: dict[str, float]) -> int:
    return sum(
        1
        for key in CONTENT_CHANNELS
        if ev.get(key, 0.0) >= CONTENT_FLOORS.get(key, CONTENT_FLOOR)
    )


def _passes(tier: tuple, score: float, margin: float, content: int) -> bool:
    smin, mmin, cmin = tier
    return score >= smin and margin >= mmin and (content or 0) >= cmin


def candidate_margin(best: float, second: float, n_cands: int) -> float:
    """Sole candidate uses its score as margin; otherwise best minus second."""
    return (best - second) if n_cands > 1 else best


def status_for(
    score: float | str,
    margin: float | None = None,
    pair_class: str | float | None = None,
    content: int = 99,
    compunit: float | None = None,
    canonical_name_conflict: bool = False,
) -> str:
    """Classify a scored pair. Compunit 0.0 and independent name conflicts veto auto.

    Accepts both the store-style call ``status_for(score, margin, pair_class, …)``
    and the older list-style ``status_for(pair_class, score, margin, content)``.
    """
    if isinstance(score, str):
        pair_class, score, margin = score, margin, pair_class
    if pair_class is None:
        pair_class = "same_platform"
    if margin is None:
        margin = 0.0
    policy = PAIR_POLICY[str(pair_class)]
    veto = compunit == 0.0
    if not veto and not canonical_name_conflict and _passes(policy["auto"], score, margin, content):
        return "auto"
    if not veto and _passes(policy["verify"], score, margin, content):
        return "verify"
    if _passes(policy["review"], score, margin, content):
        return "review"
    return "unresolved"


DECOMP_SCALARS = ("n_tokens", "n_lines", "max_nest", "n_calls", "n_locals", "n_deref", "n_index", "n_field")


def decomp_similarity(a: dict, b: dict) -> float:
    if a.get("skeleton_hash") and a["skeleton_hash"] == b.get("skeleton_hash"):
        return 1.0
    ctrl = cosine(a.get("ctrl") or {}, b.get("ctrl") or {})
    ops = cosine(a.get("ops") or {}, b.get("ops") or {})
    scal = sum(relsim(a.get(k), b.get(k)) for k in DECOMP_SCALARS) / len(DECOMP_SCALARS)
    return 0.40 * ctrl + 0.30 * ops + 0.30 * scal


def score_features(
    fa: dict[str, Any],
    fb: dict[str, Any],
    *,
    same_arch: bool = True,
    mapping: dict[Any, Any] | None = None,
    fuzzy_left_bits: int | None = None,
    fuzzy_right_bits: int | None = None,
) -> tuple[float, dict[str, float]]:
    ev: dict[str, float] = {}
    a_str, b_str = set(fa.get("strings") or []), set(fb.get("strings") or [])
    if a_str or b_str:
        ev["strings"] = jaccard(a_str, b_str)
    a_c, b_c = set(fa.get("consts") or []), set(fb.get("consts") or [])
    if a_c or b_c:
        ev["consts"] = jaccard(a_c, b_c)
    a_e, b_e = set(fa.get("ext_calls") or []), set(fb.get("ext_calls") or [])
    if a_e or b_e:
        ev["ext"] = jaccard(a_e, b_e)

    if same_arch:
        ev["struct"] = (
            0.35 * relsim(fa.get("n_blocks"), fb.get("n_blocks"))
            + 0.25 * relsim(fa.get("cyclomatic"), fb.get("cyclomatic"))
            + 0.20 * relsim(fa.get("n_callees"), fb.get("n_callees"))
            + 0.20 * relsim(fa.get("n_instr"), fb.get("n_instr"))
        )
        ma, mb = fa.get("mnem") or {}, fb.get("mnem") or {}
        if ma and mb:
            ta = sum(ma.values()) or 1
            tb = sum(mb.values()) or 1
            ev["mnem"] = cosine({k: v / ta for k, v in ma.items()}, {k: v / tb for k, v in mb.items()})
    else:
        ev["struct"] = (
            0.45 * relsim(fa.get("n_blocks"), fb.get("n_blocks"))
            + 0.30 * relsim(fa.get("cyclomatic"), fb.get("cyclomatic"))
            + 0.25 * relsim(fa.get("n_callees"), fb.get("n_callees"))
        )

    if mapping:
        ca = set(fa.get("callee_addrs") or fa.get("callees") or [])
        cb = set(fb.get("callee_addrs") or fb.get("callees") or [])
        mapped = {mapping[x] for x in ca if x in mapping}
        if mapped or cb:
            ev["neighbors"] = jaccard(mapped, cb)

    da, db = fa.get("decomp"), fb.get("decomp")
    if da and db:
        ev["decomp"] = decomp_similarity(da, db)

    fuzzy = fuzzy_similarity(fa, fb, left_bits=fuzzy_left_bits, right_bits=fuzzy_right_bits)
    if fuzzy:
        ev["fuzzy_hash"] = fuzzy

    su_a, su_b = _basename(fa.get("source_file") or fa.get("sourceFile")), _basename(
        fb.get("source_file") or fb.get("sourceFile")
    )
    if su_a and su_b:
        ev["compunit"] = 1.0 if su_a == su_b else 0.0

    if fa.get("canon_arity") is not None and fb.get("canon_arity") is not None:
        ev["arity"] = 1.0 if fa["canon_arity"] == fb["canon_arity"] else 0.0

    abi = abi_compatibility(fa, fb)
    if abi is not None:
        ev["abi"] = abi

    num = sum(WEIGHTS.get(k, 0.0) * v for k, v in ev.items() if not str(k).startswith("_"))
    den = sum(WEIGHTS.get(k, 0.0) for k in ev if not str(k).startswith("_") and k in WEIGHTS)
    # ABI is a soft discriminator: mismatch penalizes but must not erase
    # strong content channels (cross-compiler / STABS vs Ghidra arity noise).
    if "abi" in ev:
        num += 0.4 * ev["abi"]
        den += 0.4
        if ev["abi"] <= 0.0 and den:
            num *= 0.55
    ev["_content"] = float(_content_count(ev))
    return (num / den if den else 0.0), ev


def abi_compatibility(fa: dict[str, Any], fb: dict[str, Any]) -> float | None:
    """Return 1.0 compatible, 0.0 hard-incompatible, or None when insufficient data.

    ABI alone never auto-matches; it only bonuses or rejects candidates.
    """
    ca, cb = fa.get("canon_arity"), fb.get("canon_arity")
    pa, pb = fa.get("param_count"), fb.get("param_count")
    arity_a = ca if ca is not None else pa
    arity_b = cb if cb is not None else pb
    if arity_a is None or arity_b is None:
        cc_a = (fa.get("calling_convention") or "").strip().lower()
        cc_b = (fb.get("calling_convention") or "").strip().lower()
        if cc_a and cc_b and cc_a != "unknown" and cc_b != "unknown":
            return 1.0 if cc_a == cc_b else 0.0
        return None
    if int(arity_a) != int(arity_b):
        return 0.0
    cc_a = (fa.get("calling_convention") or "").strip().lower()
    cc_b = (fb.get("calling_convention") or "").strip().lower()
    if cc_a and cc_b and cc_a != "unknown" and cc_b != "unknown" and cc_a != cc_b:
        return 0.0
    return 1.0


def _fid(fn: dict[str, Any]) -> str:
    return str(fn.get("id") or fn.get("addr"))


def _callees_of(fn: dict[str, Any]) -> set[str]:
    return {str(x) for x in (fn.get("callee_addrs") or fn.get("callees") or [])}


def _callers_of(fn: dict[str, Any]) -> set[str]:
    return {str(x) for x in (fn.get("caller_addrs") or fn.get("callers") or [])}


class FeatureIndex:
    def __init__(self, functions: Iterable[dict[str, Any]]):
        self.funcs = {_fid(fn): fn for fn in functions}
        self.by_string: dict[str, list[str]] = defaultdict(list)
        self.by_const: dict[Any, list[str]] = defaultdict(list)
        self.by_ext: dict[str, list[str]] = defaultdict(list)
        self.by_shape: dict[tuple, list[str]] = defaultdict(list)
        self.by_unit: dict[str, list[str]] = defaultdict(list)
        self.by_skeleton: dict[str, list[str]] = defaultdict(list)
        # Exact/normalized fingerprints are candidate anchors only when the
        # fingerprint is unique on both sides.  Keep separate indexes so the
        # provenance of an accepted anchor is never lost.
        self.by_hash_raw: dict[str, list[str]] = defaultdict(list)
        self.by_hash_reloc: dict[str, list[str]] = defaultdict(list)
        self.by_hash_instr: dict[str, list[str]] = defaultdict(list)
        self.by_hash_mnemonic: dict[str, list[str]] = defaultdict(list)
        self.callees: dict[str, set[str]] = defaultdict(set)
        self.callers: dict[str, set[str]] = defaultdict(set)
        for fid, fn in self.funcs.items():
            for s in fn.get("strings") or []:
                self.by_string[s].append(fid)
            for c in fn.get("consts") or []:
                self.by_const[c].append(fid)
            for e in fn.get("ext_calls") or []:
                self.by_ext[e].append(fid)
            self.by_shape[shape_key(fn)].append(fid)
            unit = _basename(fn.get("source_file") or fn.get("sourceFile"))
            if unit:
                self.by_unit[unit].append(fid)
            skel = (fn.get("decomp") or {}).get("skeleton_hash")
            if skel:
                self.by_skeleton[skel].append(fid)
            for field, target in (
                ("hash_raw", self.by_hash_raw),
                ("hash_reloc", self.by_hash_reloc),
                ("hash_instr", self.by_hash_instr),
                ("hash_mnemonic", self.by_hash_mnemonic),
            ):
                value = str(fn.get(field) or "")
                if value and (field != "hash_raw" or value.startswith("B_raw:")):
                    target[value].append(fid)
            for callee in _callees_of(fn):
                self.callees[fid].add(callee)
                self.callers[callee].add(fid)
            for caller in _callers_of(fn):
                self.callers[fid].add(caller)
                self.callees[caller].add(fid)

    def candidates(self, src: dict[str, Any], mapping: dict[str, str] | None = None) -> set[str]:
        votes: Counter[str] = Counter()
        for s in src.get("strings") or []:
            hits = self.by_string.get(s) or []
            if len(hits) <= MAX_STRING_DF:
                votes.update({h: 3 for h in hits})
        for c in src.get("consts") or []:
            hits = self.by_const.get(c) or []
            if len(hits) <= MAX_CONST_DF:
                votes.update({h: 2 for h in hits})
        for e in src.get("ext_calls") or []:
            hits = self.by_ext.get(e) or []
            if len(hits) <= MAX_CONST_DF:
                votes.update({h: 1 for h in hits})
        if mapping:
            src_id = _fid(src)
            for callee in self.callees.get(src_id, ()):
                mapped = mapping.get(callee)
                if mapped is not None:
                    for hit in self.callers.get(mapped, ()):
                        votes[hit] += 2
            for caller in self.callers.get(src_id, ()):
                mapped = mapping.get(caller)
                if mapped is not None:
                    for hit in self.callees.get(mapped, ()):
                        votes[hit] += 2
        unit = _basename(src.get("source_file") or src.get("sourceFile"))
        if unit:
            for hit in self.by_unit.get(unit, ())[:400]:
                votes[hit] += 2
        skel = (src.get("decomp") or {}).get("skeleton_hash")
        if skel:
            for hit in self.by_skeleton.get(skel, ())[:200]:
                votes[hit] += 2
        if not votes:
            for hit in self.by_shape.get(shape_key(src), ())[:200]:
                votes[hit] += 1
        if not votes:
            return set(self.funcs)
        return {hit for hit in votes if hit in self.funcs}


def match_binaries(
    left: list[dict[str, Any]],
    right: list[dict[str, Any]],
    *,
    left_meta: dict[str, Any] | None = None,
    right_meta: dict[str, Any] | None = None,
    tier: str = "auto",
    rounds: int = 3,
) -> list[dict[str, Any]]:
    """Score blocked pairs across greedy rounds and keep those that clear policy."""
    pair_class = classify_pair(left_meta or {}, right_meta or {})
    same_arch = pair_class in ("same_platform", "cross_format") or (
        (left_meta or {}).get("arch") == (right_meta or {}).get("arch")
    )
    index = FeatureIndex(right)
    left_index = FeatureIndex(left)
    mapping: dict[str, str] = {}
    taken: set[str] = set()
    results: dict[str, dict[str, Any]] = {}
    src_ids = [
        fid
        for fid, fn in left_index.funcs.items()
        if not fn.get("is_thunk") and (fn.get("n_instr") or 0) >= 4
    ]
    dst_eligible = {
        fid
        for fid, fn in index.funcs.items()
        if not fn.get("is_thunk") and (fn.get("n_instr") or 0) >= 4
    }
    src_eligible = set(src_ids)
    from .symbol_provenance import authentic_named_index

    left_names = {k: [str(x) for x in v] for k, v in authentic_named_index(left_index.funcs).items()}
    right_names = {k: [str(x) for x in v] for k, v in authentic_named_index(index.funcs).items()}
    absorb_anchors(mapping, unique_index_anchors(left_names, right_names, src_eligible=src_eligible, dst_eligible=dst_eligible))
    hash_channels: dict[str, str] = {}
    for channel, left_hashes, right_hashes in (
        ("hash_raw", left_index.by_hash_raw, index.by_hash_raw),
        ("hash_reloc", left_index.by_hash_reloc, index.by_hash_reloc),
        ("hash_instr", left_index.by_hash_instr, index.by_hash_instr),
        ("hash_mnemonic", left_index.by_hash_mnemonic, index.by_hash_mnemonic),
    ):
        before = set(mapping)
        absorb_anchors(
            mapping,
            unique_index_anchors(
                left_hashes,
                right_hashes,
                src_eligible=src_eligible,
                dst_eligible=dst_eligible,
            ),
        )
        for src in set(mapping) - before:
            hash_channels[src] = channel
    absorb_anchors(
        mapping,
        unique_index_anchors(
            left_index.by_string,
            index.by_string,
            src_eligible=src_eligible,
            dst_eligible=dst_eligible,
            key_ok=interesting_string,
        ),
    )
    absorb_anchors(
        mapping,
        unique_index_anchors(
            left_index.by_const,
            index.by_const,
            src_eligible=src_eligible,
            dst_eligible=dst_eligible,
            key_ok=interesting_const,
        ),
    )
    record_pairs(
        results,
        [(src, dst, "anchor") for src, dst in mapping.items()],
        left_lookup=left_index.funcs,
        right_lookup=index.funcs,
        round_label="anchor",
        pair_class=pair_class,
    )
    for src, channel in hash_channels.items():
        row = results.get(src)
        if row is None:
            continue
        row["anchor_channel"] = channel
        row["method"] = channel
        evidence = row.setdefault("evidence", {})
        evidence[channel] = 1.0
        evidence["anchor_channel"] = channel
        row.setdefault("signals", {})[channel] = 1.0
    record_pairs(
        results,
        propagate_call_graph(
            left_index.callees,
            left_index.callers,
            index.callees,
            index.callers,
            mapping,
            src_eligible=src_eligible,
            dst_eligible=dst_eligible,
        ),
        left_lookup=left_index.funcs,
        right_lookup=index.funcs,
        pair_class=pair_class,
    )
    taken = set(mapping.values())

    # Consume unique CFG/MD-index + mnemonic-SPP pairs before scoring fuzzy
    # residue.  These are deterministic structural anchors and must not lose
    # their destination to a weaker locality fingerprint.
    unmatched_src = [left_index.funcs[sid] for sid in src_ids if sid not in mapping]
    unmatched_dst = [index.funcs[did] for did in dst_eligible if did not in taken]
    for sid, bid in unique_structural_pairs(unmatched_src, unmatched_dst, id_of=_fid):
        if sid in mapping or bid in taken:
            continue
        mapping[sid] = bid
        taken.add(bid)
        fa, fb = left_index.funcs[sid], index.funcs[bid]
        ev = island_evidence(fa, fb)
        results[sid] = {
            "left_id": fa.get("id"),
            "right_id": fb.get("id"),
            "score": 0.8,
            "margin": 1.0,
            "content": int(ev.get("_content") or 1),
            "pair_class": pair_class,
            "status": "verify",
            "signals": {k: v for k, v in ev.items() if not str(k).startswith("_")},
            "kind": "structural",
        }
    if mapping:
        record_pairs(
            results,
            propagate_call_graph(
                left_index.callees,
                left_index.callers,
                index.callees,
                index.callers,
                mapping,
                src_eligible=src_eligible,
                dst_eligible=dst_eligible,
            ),
            left_lookup=left_index.funcs,
            right_lookup=index.funcs,
            round_label="structural",
            pair_class=pair_class,
        )
        taken = set(mapping.values())

    for rnd in range(rounds):
        scored: list[tuple[float, float, str, str, dict[str, float]]] = []
        for sid in src_ids:
            if sid in mapping:
                continue
            fa = left_index.funcs[sid]
            cands = index.candidates(fa, mapping) - taken
            if not cands:
                continue
            best = second = 0.0
            best_b: str | None = None
            best_ev: dict[str, float] = {}
            for bid in sorted(cands):
                score, ev = score_features(fa, index.funcs[bid], same_arch=same_arch, mapping=mapping)
                if score > best:
                    second, best, best_b, best_ev = best, score, bid, ev
                elif score > second:
                    second = score
            if best_b is not None:
                margin = candidate_margin(best, second, len(cands))
                scored.append((best, margin, sid, best_b, best_ev))

        scored.sort(key=lambda row: (-row[0], -row[1], row[2], row[3]))
        new = 0
        for best, margin, sid, bid, ev in scored:
            if sid in mapping or bid in taken:
                continue
            content = int(ev.get("_content") or 0)
            left_key = left_index.funcs[sid].get("canon_key")
            right_key = index.funcs[bid].get("canon_key")
            conflict = bool(left_key and right_key and left_key != right_key)
            status = status_for(
                best,
                margin,
                pair_class,
                content,
                compunit=ev.get("compunit"),
                canonical_name_conflict=conflict,
            )
            if status == "unresolved":
                prev = results.get(sid)
                if prev is None or best > prev["score"]:
                    results[sid] = {
                        "left_id": left_index.funcs[sid].get("id"),
                        "right_id": index.funcs[bid].get("id"),
                        "score": round(best, 4),
                        "margin": round(margin, 4),
                        "content": content,
                        "pair_class": pair_class,
                        "status": status,
                        "signals": {k: v for k, v in ev.items() if not k.startswith("_")},
                        "kind": "identity",
                    }
                continue
            if ev.get("compunit") != 0.0 and _passes(PAIR_POLICY[pair_class]["verify"], best, margin, content):
                mapping[sid] = bid
                taken.add(bid)
                new += 1
            if sid in results and results[sid].get("kind") in {"callgraph", "anchor"}:
                continue
            results[sid] = {
                "left_id": left_index.funcs[sid].get("id"),
                "right_id": index.funcs[bid].get("id"),
                "score": round(best, 4),
                "margin": round(margin, 4),
                "content": content,
                "pair_class": pair_class,
                "status": status,
                "signals": {k: v for k, v in ev.items() if not k.startswith("_")},
                "kind": "identity",
            }
        if new:
            grown = record_pairs(
                results,
                propagate_call_graph(
                    left_index.callees,
                    left_index.callers,
                    index.callees,
                    index.callers,
                    mapping,
                    src_eligible=src_eligible,
                    dst_eligible=dst_eligible,
                ),
                left_lookup=left_index.funcs,
                right_lookup=index.funcs,
                round_label=rnd,
                pair_class=pair_class,
            )
            taken = set(mapping.values())
            new += grown
        if new == 0:
            break

    unmatched_src = [left_index.funcs[sid] for sid in src_ids if sid not in mapping]
    unmatched_dst = [index.funcs[did] for did in dst_eligible if did not in taken]
    for sid, bid in unique_structural_pairs(unmatched_src, unmatched_dst, id_of=_fid):
        if sid in mapping or bid in taken:
            continue
        mapping[sid] = bid
        taken.add(bid)
        fa, fb = left_index.funcs[sid], index.funcs[bid]
        ev = island_evidence(fa, fb)
        results[sid] = {
            "left_id": fa.get("id"),
            "right_id": fb.get("id"),
            "score": 0.8,
            "margin": 1.0,
            "content": int(ev.get("_content") or 1),
            "pair_class": pair_class,
            "status": "verify",
            "signals": {k: v for k, v in ev.items() if not str(k).startswith("_")},
            "kind": "structural",
        }
    for hit in leftover_inlines(
        [left_index.funcs[sid] for sid in src_ids if sid not in mapping],
        [index.funcs[did] for did in dst_eligible if did not in taken],
    ):
        results.setdefault(
            str(hit["missing_id"]),
            {
                "left_id": hit["missing_id"],
                "right_id": hit["host_id"],
                "score": 0.5,
                "margin": 1.0,
                "content": 1,
                "pair_class": pair_class,
                "status": "review",
                "signals": {"inline": 1.0, "block_count": hit["block_count"]},
                "kind": "inline",
            },
        )
    # Identity/structural rows are one-to-one.  A destination collision is
    # ambiguous evidence, not two accepted matches; keep the strongest row
    # deterministically and demote the rest.  Inline/fold/split evidence is
    # intentionally excluded because it describes non-1:1 compiler effects.
    identity_rows = [
        row for row in results.values()
        if row["status"] != "unresolved" and row.get("kind") != "inline"
    ]
    by_destination: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for row in identity_rows:
        by_destination[row.get("right_id")].append(row)
    for rows in by_destination.values():
        if len(rows) < 2:
            continue
        winner = max(rows, key=lambda row: (float(row.get("score") or 0.0), float(row.get("margin") or 0.0), str(row.get("left_id"))))
        for row in rows:
            if row is not winner:
                row["status"] = "unresolved"
                row["ambiguity"] = "destination_collision"
    accepted = [row for row in results.values() if row["status"] != "unresolved"]
    if tier == "auto":
        accepted = [row for row in accepted if row["status"] == "auto"]
    return accepted
