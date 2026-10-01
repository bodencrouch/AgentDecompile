"""Store-backed identity matcher (kotorxid ``kx.match.Binary`` / ``match_binaries``).

Evidence-fusion cascade: identical-image short-circuit, authentic symbols, unique
reloc/instr hashes, rare refs, call-graph, structural islands, optional BSim/ABI
corroboration. Candidate generation is not acceptance. Identity bind is not
objdiff-0 byte proof and does not authorize type/source copy.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Callable, Mapping

from . import canon
from .callgraph_propagate import (
    interesting_const,
    interesting_string,
    propagate_call_graph,
    record_pairs,
    unique_index_anchors,
)
from .channel_confidence import allows_verify, channel_confidence
from .contract_features import contract_compatibility
from .correspondence import enrich_evidence
from .fingerprint_hashes import attach_hashes
from .fuzzy_fingerprint import fuzzy_bits
from .identical_image import short_circuit_match
from .match_islands import island_evidence, leftover_inlines, unique_structural_pairs
from .store import ensure_func_columns
from .symbol_provenance import authentic_named_index
from .match_engine import reverse_ties
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


def dependency_token(content_sha256: str | None, addr: int, *, slug: str | None = None) -> str:
    """The build-invariant token for one function in ``match.evidence``.

    ``<content_sha256[:16]>:<addr>``: the same value however the build rows
    were ingested. A build with no hash cannot be named, so this refuses
    (``ContentHashError``, kind ``missing``) instead of falling back to a
    rowid, which is exactly the value that moved with ingest order (A3).
    """
    digest = str(content_sha256 or "").strip()
    if not digest:
        from .logical import BACKFILL_HINT, ContentHashError

        name = slug if slug is not None else "(unknown build)"
        raise ContentHashError(
            f"binary.content_sha256 is NULL or blank for {name}; the dependency token keys on it "
            f"and refuses to guess; {BACKFILL_HINT}",
            kind="missing",
            slugs=[str(name)],
        )
    return f"{digest[:16]}:{int(addr)}"


def quarantined_source_tokens(con, run: str) -> set[str]:
    """Dependency tokens of every quarantined source function in *run*.

    The one consumer-side producer of the token: ``bind_identities`` and the
    dashboard merge intersect this set with each match's stored
    ``dependencies`` / ``dependency_ancestry``. Built through
    :func:`dependency_token`, so producer and consumers cannot drift; a
    quarantined source on a build with no hash refuses (a silent skip would
    let a quarantined ancestor bind its descendants).
    """
    tokens: set[str] = set()
    rows = con.execute(
        "SELECT m.src_addr, m.evidence, b.slug, b.content_sha256"
        "  FROM match m LEFT JOIN binary b ON b.id=m.src_binary WHERE m.run=?",
        (run,),
    )
    for row in rows:
        if not json.loads(row["evidence"] or "{}").get("quarantine"):
            continue
        tokens.add(dependency_token(row["content_sha256"], int(row["src_addr"]), slug=row["slug"]))
    return tokens


class Binary:
    """In-memory view of one binary's functions and call graph."""

    def __init__(self, con, binary_id: int):
        self.id = binary_id
        ensure_func_columns(con)
        row = con.execute("SELECT * FROM binary WHERE id=?", (binary_id,)).fetchone()
        self.meta = dict(row)
        self.slug = row["slug"]
        self.funcs: dict[int, dict] = {}
        cols = {d[1] for d in con.execute("PRAGMA table_info(func)").fetchall()}
        hash_select = ""
        for col in ("hash_reloc", "hash_instr", "hash_mnemonic", "hash_raw", "symbol_provenance"):
            if col in cols:
                hash_select += f",{col}"
        for rec in con.execute(
            f"""SELECT addr,name,namespace,canon_key,canon_arity,canon_method,canon_class,
                      name_origin,size,is_thunk,n_instr,n_blocks,n_edges,back_edges,
                      cyclomatic,n_callees,indirect_calls,data_refs,mnem,strings,consts,
                      ext_calls,block_hashes,cfg_nodes,cfg_edges,plate,signature,source,param_count,
                      source_file,object_file,calling_convention{hash_select}
                 FROM func WHERE binary_id=? ORDER BY addr""",
            (binary_id,),
        ):
            d = dict(rec)
            d["strings"] = json.loads(d["strings"] or "[]")
            d["consts"] = json.loads(d["consts"] or "[]")
            d["ext_calls"] = json.loads(d["ext_calls"] or "[]")
            d["mnem"] = json.loads(d["mnem"] or "{}")
            d["block_hashes"] = json.loads(d["block_hashes"] or "[]")
            d["cfg_nodes"] = json.loads(d.get("cfg_nodes") or "[]")
            d["cfg_edges"] = [
                (int(edge[0]), int(edge[1]))
                for edge in json.loads(d.get("cfg_edges") or "[]")
                if isinstance(edge, (list, tuple)) and len(edge) == 2
            ]
            if not d.get("hash_reloc"):
                d = attach_hashes(d)
            if canon.is_eh_clone(d["name"], d["plate"]):
                continue
            self.funcs[d["addr"]] = d

        self.decomp: dict[int, dict] = {}
        try:
            decomp_cols = {row[1] for row in con.execute("PRAGMA table_info(decomp)")}
            fp_col = next((c for c in ("pcode_fingerprint", "ast_fingerprint", "pcode_hash", "hash_pcode", "skeleton_hash") if c in decomp_cols), None)
            fp_select = f", {fp_col} AS pcode_fingerprint" if fp_col else ""
            for rec in con.execute(
                f"""SELECT addr,n_tokens,n_lines,max_nest,n_calls,n_locals,n_deref,
                          n_index,n_field,ctrl,ops,skeleton_hash{fp_select}
                     FROM decomp WHERE binary_id=? AND ok=1 ORDER BY addr""",
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
            "SELECT caller_addr, callee_addr FROM calledge WHERE binary_id=? ORDER BY caller_addr, callee_addr",
            (binary_id,),
        ):
            self.callees[a].add(b)
            self.callers[b].add(a)
        self._index()
        # Fuzzy scoring compares the same loaded feature records repeatedly
        # across candidates and rounds. Fill this per-job cache only when
        # scoring reaches a function; anchor-only jobs need no fuzzy work.
        self.fuzzy_bits: dict[int, int] = {}

    def fuzzy_bits_for(self, addr: int) -> int:
        bits = self.fuzzy_bits.get(addr)
        if bits is None:
            bits = fuzzy_bits(self.funcs[addr])
            self.fuzzy_bits[addr] = bits
        return bits

    def _index(self) -> None:
        self.by_string: dict[str, list[int]] = defaultdict(list)
        self.by_const: dict[int, list[int]] = defaultdict(list)
        self.by_ext: dict[str, list[int]] = defaultdict(list)
        self.by_shape: dict[tuple, list[int]] = defaultdict(list)
        self.by_unit: dict[str, list[int]] = defaultdict(list)
        self.by_skeleton: dict[str, list[int]] = defaultdict(list)
        self.by_pcode: dict[str, list[int]] = defaultdict(list)
        self.by_hash_reloc: dict[str, list[int]] = defaultdict(list)
        self.by_hash_instr: dict[str, list[int]] = defaultdict(list)
        self.by_hash_mnemonic: dict[str, list[int]] = defaultdict(list)
        self.by_hash_raw: dict[str, list[int]] = defaultdict(list)
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
                ("hash_raw", self.by_hash_raw),
                ("hash_reloc", self.by_hash_reloc),
                ("hash_instr", self.by_hash_instr),
                ("hash_mnemonic", self.by_hash_mnemonic),
            ):
                digest = f.get(field)
                if not digest:
                    continue
                # Index every occurrence. Ineligible tiny/thunk collisions
                # must still defeat target-wide uniqueness.
                index[digest].append(addr)
        for addr, d in self.decomp.items():
            h = d.get("skeleton_hash")
            if h:
                self.by_skeleton[h].append(addr)
            pcode = d.get("pcode_fingerprint")
            if pcode:
                self.by_pcode[str(pcode)].append(addr)

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
    for field in ("hash_raw", "hash_reloc", "hash_instr", "hash_mnemonic"):
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
    pcode = (sa.decomp.get(src_addr) or {}).get("pcode_fingerprint")
    if pcode:
        for h in sb.by_pcode.get(str(pcode), ())[:200]:
            cands[h] += 4
    return {c for c in cands if c in sb.funcs}


def _classify_store(sa: Binary, sb: Binary) -> str:
    return classify_pair(sa.meta, sb.meta)


def _pcode_receipt(con, src_id: int, dst_id: int) -> dict:
    """Report stored P-code capability without invoking Ghidra or extraction."""
    columns = {row[1] for row in con.execute("PRAGMA table_info(decomp)")}
    fingerprint = next(
        (name for name in ("pcode_fingerprint", "ast_fingerprint", "pcode_hash", "hash_pcode", "skeleton_hash") if name in columns),
        None,
    )
    if fingerprint is None:
        return {"skipped": True, "reason": "pcode_fingerprints_not_extracted"}
    count = con.execute(
        f"SELECT COUNT(*) FROM decomp WHERE binary_id IN (?,?) AND {fingerprint} IS NOT NULL AND {fingerprint}<>''",
        (src_id, dst_id),
    ).fetchone()[0]
    return (
        {"available": True, "storedFingerprintColumn": fingerprint, "storedFingerprintRows": count}
        if count
        else {"skipped": True, "reason": "pcode_fingerprints_not_stored", "storedFingerprintColumn": fingerprint}
    )


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
               FROM bsim_hit WHERE src_binary=? AND dst_binary=?
               ORDER BY src_addr, dst_addr""",
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
    for src, hits in sorted(by_src.items()):
        if src in mapping or src not in sa.funcs:
            continue
        hits = sorted(hits, key=lambda t: (-t[2], -t[1], t[0]))
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
            "score": round(min(0.95, 0.55 + sim * 0.4), 4),
            "margin": round(max(0.1, (sig - second_sig) / 100.0), 4),
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
    seed_provenance: dict | None = None,
    restrict_src: set[int] | None = None,
    use_name_features: bool = True,
    quiet: bool = True,
    progress: Callable[[dict], None] | None = None,
    contract_features: Callable[[str, int], Mapping[str, Any] | None] | None = None,
) -> dict:
    sa, sb = Binary(con, src_id), Binary(con, dst_id)
    early = short_circuit_match(sa, sb)
    if early is not None:
        return early
    same_arch = (sa.meta["arch"], sa.meta["bits"]) == (sb.meta["arch"], sb.meta["bits"])
    pair_class = _classify_store(sa, sb)
    policy = PAIR_POLICY[pair_class]
    supplied_seed = dict(seed or {})
    seed_source = str((seed_provenance or {}).get("source") or "").strip().lower()
    seed_channel = str((seed_provenance or {}).get("channel") or "").strip().lower()
    authentic_seed_sources = {
        "content_sha256", "debug_symbol", "export_symbol",
        "dwarf", "stabs", "pdb",
    }
    src_seed_eligible = {
        a for a, f in sa.funcs.items()
        if not f["is_thunk"] and (f["n_instr"] or 0) >= 4
        and (restrict_src is None or a in restrict_src)
    }
    dst_seed_eligible = {
        a for a, f in sb.funcs.items()
        if not f["is_thunk"] and (f["n_instr"] or 0) >= 4
    }
    seed_pairs_valid = (
        all(src in src_seed_eligible and dst in dst_seed_eligible for src, dst in supplied_seed.items())
        and len(set(supplied_seed.values())) == len(supplied_seed)
    )
    if seed_source in {"debug_symbol", "export_symbol", "dwarf", "stabs", "pdb"}:
        from .symbol_provenance import is_authentic_symbol

        seed_evidence_valid = all(
            is_authentic_symbol(sa.funcs[src])
            and is_authentic_symbol(sb.funcs[dst])
            and sa.funcs[src].get("canon_key")
            and sa.funcs[src].get("canon_key") == sb.funcs[dst].get("canon_key")
            for src, dst in supplied_seed.items()
            if src in sa.funcs and dst in sb.funcs
        )
    elif seed_source == "content_sha256":
        from .identical_image import images_identical

        seed_evidence_valid = images_identical(sa.meta, sb.meta)
    elif seed_source == "exact_bytes":
        seed_evidence_valid = all(
            (sa.funcs[src].get("hash_raw") or "").startswith("B_raw:")
            and sa.funcs[src].get("hash_raw") == sb.funcs[dst].get("hash_raw")
            for src, dst in supplied_seed.items()
            if src in sa.funcs and dst in sb.funcs
        )
        if seed_evidence_valid:
            authentic_seed_sources.add("exact_bytes")
    else:
        seed_evidence_valid = False
    trusted_seed = bool(
        supplied_seed
        and seed_provenance
        and seed_provenance.get("independently_checkable") is True
        and seed_source in authentic_seed_sources
        and seed_evidence_valid
        and seed_channel not in {"caller", "callee", "callgraph", "neighbors", "propagated"}
        and seed_pairs_valid
    )
    mapping: dict[int, int] = dict(supplied_seed) if trusted_seed else {}
    taken = set(mapping.values())
    results: dict[int, dict] = {}
    if supplied_seed and not trusted_seed:
        for src, dst in supplied_seed.items():
            if src not in sa.funcs or dst not in sb.funcs:
                continue
            results[src] = {
                "dst": dst, "score": 0.0, "margin": 0.0, "kind": "seed", "status": "review", "round": "seed",
                "evidence": enrich_evidence(
                    {"primary_channel": "external_seed", "seed_provenance": seed_provenance or {}, "reason": "untrusted_external_seed"},
                    status="review", identity_claim=False, quarantine=True, stage="seed",
                ),
            }

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

    def report(completed: int, *, round_index: int) -> None:
        if progress is not None:
            # Reserve the final unit for the matcher result/post-processing.
            # The job becomes 100% only after its subprocess has terminated.
            progress({
                "phase": "fuzzy_residue",
                "round": round_index,
                "rounds": rounds,
                "roundCompleted": completed,
                "roundTotal": len(src_addrs),
                "completed": round_index * len(src_addrs) + completed,
                "total": rounds * len(src_addrs) + 1,
                "unit": "source functions",
                "finalizing": True,
            })
    # Keep provenance until all cheap anchor channels have voted.  Silently
    # dropping a contradictory proposal would let its descendants look trusted.
    anchor_sets: list[tuple[str, dict[int, int]]] = [
        ("I", unique_index_anchors(sa.candidates_named_authentic(), sb.candidates_named_authentic(), src_eligible=src_eligible, dst_eligible=dst_eligible)),
        ("H", unique_index_anchors(sa.by_hash_raw, sb.by_hash_raw, src_eligible=src_eligible, dst_eligible=dst_eligible, key_ok=lambda key: str(key).startswith("B_raw:"))),
        ("H", unique_index_anchors(sa.by_hash_reloc, sb.by_hash_reloc, src_eligible=src_eligible, dst_eligible=dst_eligible, key_ok=lambda key: bool(key) and len(str(key)) >= 16)),
        ("H", unique_index_anchors(sa.by_hash_instr, sb.by_hash_instr, src_eligible=src_eligible, dst_eligible=dst_eligible, key_ok=lambda key: bool(key) and len(str(key)) >= 16)),
        ("X", unique_index_anchors(sa.by_string, sb.by_string, src_eligible=src_eligible, dst_eligible=dst_eligible, key_ok=interesting_string)),
        ("X", unique_index_anchors(sa.by_const, sb.by_const, src_eligible=src_eligible, dst_eligible=dst_eligible, key_ok=interesting_const)),
    ]
    proposals: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for channel, pairs in anchor_sets:
        for src, dst in pairs.items():
            proposals[src].append((dst, channel))
    by_destination: dict[int, set[int]] = defaultdict(set)
    for src, candidates in proposals.items():
        for dst, _channel in candidates:
            by_destination[dst].add(src)
    quarantined: set[int] = set()
    for src, candidates in proposals.items():
        destinations = {dst for dst, _ in candidates}
        conflicting_destinations = {dst for dst in destinations if len(by_destination[dst]) != 1}
        if len(destinations) != 1 or conflicting_destinations:
            quarantined.add(src)
            mapping.pop(src, None)
            dst = min(destinations)
            results[src] = {
                "dst": dst, "score": 0.0, "margin": 0.0, "kind": "anchor", "status": "review", "round": "anchor",
                "evidence": enrich_evidence({"channels": sorted({channel for _, channel in candidates}), "conflict": "source" if len(destinations) != 1 else "destination"}, kind="anchor", status="ambiguous", alternatives=[{"dst": value} for value in sorted(destinations)], identity_claim=False, quarantine=True, stage="anchor"),
            }
            continue
        dst = next(iter(destinations))
        if src not in mapping and dst not in set(mapping.values()):
            mapping[src] = dst
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
            if addr in quarantined or result.get("evidence", {}).get("quarantine"):
                result["status"] = "review"
                result["evidence"] = enrich_evidence(
                    result.get("evidence", {}), kind="anchor", status="ambiguous",
                    identity_claim=False, quarantine=True, stage="anchor",
                )
                continue
            if trusted_seed and addr in supplied_seed:
                result["evidence"] = enrich_evidence(
                    {
                        **result.get("evidence", {}),
                        "primary_channel": str(seed_provenance.get("channel") or seed_source),
                        "channels": [str(seed_provenance.get("channel") or seed_source)],
                        "seed_provenance": seed_provenance,
                    },
                    kind="anchor", status="verify", identity_claim=True, stage="trusted_seed",
                )
                result["status"] = "verify"
                continue
            raw_digest = sa.funcs[addr].get("hash_raw")
            reloc_digest = sa.funcs[addr].get("hash_reloc")
            code_eq = (
                "raw_bytes" if raw_digest and sb.funcs[result["dst"]].get("hash_raw") == raw_digest
                else "reloc" if reloc_digest and sb.funcs[result["dst"]].get("hash_reloc") == reloc_digest
                else None
            )
            channels = sorted({channel for dst, channel in proposals.get(addr, ()) if dst == result["dst"]})
            result["evidence"] = enrich_evidence(
                {**result.get("evidence", {}), "channels": channels, "primary_channel": channels[0] if channels else "I"},
                kind="anchor",
                status=result.get("status") or "auto",
                code_equality=code_eq,
                identity_claim=True,
                stage="anchor",
            )
    for addr, result in list(results.items()):
        if result.get("kind") != "anchor" or addr not in mapping:
            continue
        ev = result["evidence"]
        confidence = channel_confidence(
            primary=str(ev.get("primary_channel") or "I"), evidence=ev,
            n_instr=sa.funcs[addr].get("n_instr"), margin=result.get("margin"), unique=True,
        )
        if not allows_verify(confidence, unique=True):
            mapping.pop(addr, None)
            result["status"] = "review"
            result["evidence"] = enrich_evidence(ev, kind="anchor", status="review", identity_claim=False, quarantine=True)
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
            with_dependencies=True,
        ),
        id_field="addr",
        left_lookup=sa.funcs,
        right_lookup=sb.funcs,
        pair_class=pair_class,
    )
    dependency_ancestry: dict[int, set[str]] = {}

    def src_token(addr: int) -> str:
        # Persisted tokens key on the source build's content hash, never its
        # rowid (A3). The refusal is lazy: a hash-less build only fails when
        # a callgraph match actually needs a token.
        return dependency_token(sa.meta.get("content_sha256"), addr, slug=sa.slug)

    def tokenise_callgraph_results() -> None:
        """Rewrite fresh callgraph results' raw parent addrs into tokens.

        ``record_pairs`` stores the parents ``propagate_call_graph`` found as
        plain addresses; every result that reaches ``match.evidence`` must
        carry tokens instead, or the identity gate's intersection with the
        quarantine set (also tokens) is empty and a quarantined ancestor
        binds its descendants. Called once after every propagation site;
        ``results`` keeps insertion order, so a parent matched by an earlier
        propagation is tokenised before its child reads the ancestry.
        """
        for src, result in results.items():
            if result.get("kind") != "callgraph" or src in dependency_ancestry:
                continue
            raw_direct = list(result.get("evidence", {}).get("dependencies") or ())
            direct = [src_token(int(parent)) for parent in raw_direct]
            ancestry = set(direct)
            for parent in raw_direct:
                ancestry.update(dependency_ancestry.get(int(parent), ()))
            dependency_ancestry[src] = ancestry
            result["evidence"] = enrich_evidence(
                result["evidence"], kind="callgraph", status="auto",
                dependencies=direct, stage="callgraph",
            )
            result["evidence"]["dependency_ancestry"] = sorted(ancestry)

    tokenise_callgraph_results()
    # CFG MD-index plus mnemonic SPP is a cheap, exact leftover stage.  It
    # precedes BSim and weighted/decompiler residue scoring so fuzzy evidence
    # cannot consume a candidate that has a unique structural correspondence.
    taken = set(mapping.values())
    for src_addr, dst_addr in unique_structural_pairs(
        [sa.funcs[a] for a in src_addrs if a not in mapping],
        [sb.funcs[b] for b in sorted(dst_eligible) if b not in taken],
        id_of=lambda fn: fn["addr"],
    ):
        if src_addr in mapping or dst_addr in taken:
            continue
        mapping[src_addr] = dst_addr
        taken.add(dst_addr)
        ev = island_evidence(sa.funcs[src_addr], sb.funcs[dst_addr])
        results[src_addr] = {
            "dst": dst_addr, "score": 0.8, "margin": 1.0,
            "evidence": enrich_evidence(
                {**ev, "primary_channel": "G", "channels": ["G"]},
                kind="structural", status="verify", identity_claim=True, stage="cfg_spp",
            ),
            "round": "cfg_spp", "kind": "structural", "status": "verify",
        }
    # Exact stored P-code fingerprints are the semantic residue stage.  They
    # run after cheap CFG/SPP and before weighted/fuzzy scoring.
    taken = set(mapping.values())
    pcode_pairs = unique_index_anchors(
        sa.by_pcode, sb.by_pcode,
        src_eligible={a for a in src_eligible if a not in mapping},
        dst_eligible={a for a in dst_eligible if a not in taken},
        key_ok=lambda key: bool(key) and len(str(key)) >= 16,
    )
    for src_addr, dst_addr in pcode_pairs.items():
        if src_addr in mapping or dst_addr in taken:
            continue
        mapping[src_addr] = dst_addr
        taken.add(dst_addr)
        results[src_addr] = {
            "dst": dst_addr, "score": 0.9, "margin": 1.0,
            "evidence": enrich_evidence(
                {"pcode_fingerprint": 1.0, "primary_channel": "M", "channels": ["M"]},
                kind="structural", status="verify", identity_claim=True, stage="pcode_il_ast",
            ),
            "round": "pcode_il_ast", "kind": "structural", "status": "verify",
        }

    # High-significance BSim is a deterministic relational anchor.  Consume it
    # before weighted/fuzzy residue so weaker evidence cannot steal its target.
    pre_bsim_count = len(mapping)
    bsim_receipt = _fuse_bsim(con, sa, sb, mapping, results, pair_class)
    if len(mapping) > pre_bsim_count:
        propagated = record_pairs(
            results,
            propagate_call_graph(
                sa.callees, sa.callers, sb.callees, sb.callers, mapping,
                src_eligible=src_eligible, dst_eligible=dst_eligible,
                with_dependencies=True,
            ), id_field="addr", left_lookup=sa.funcs, right_lookup=sb.funcs,
            round_label="bsim-callgraph", pair_class=pair_class,
        )
        # Not left to the residue loop below: it only converts when a round
        # grows the mapping, and a pair with no residue would persist raw addrs.
        tokenise_callgraph_results()
        if propagated:
            mapping.update({src: int(item["dst"]) for src, item in results.items()
                            if item.get("kind") == "callgraph"
                            and item.get("round") == "bsim-callgraph"
                            and src not in mapping})

    def _contract_veto(a: int, b: int, best: float, second: float, second_b: int | None) -> dict | None:
        """Opt-in calling-contract check for the current best/runner-up pair.

        Returns ``None`` when the top candidate is not vetoed (nothing to
        change). Otherwise returns a dict describing whether the row should
        be dropped entirely (a lone ``Unwind@`` hard negative with no
        alternative) or kept/promoted under review, plus the ``contract``
        evidence block and an ``alternatives`` list carrying each
        candidate's veto reason.
        """
        window: list[dict] = []
        compat_by_addr: dict[int, tuple[str, list[str]]] = {}
        hard_negatives: list[dict] = []
        eligible: list[tuple[int, float]] = []
        candidates = [(b, best)]
        if second_b is not None and second > 0:
            candidates.append((second_b, second))
        src_features = contract_features("src", a)
        for addr, score_val in candidates:
            dst_features = contract_features("dst", addr)
            compat = contract_compatibility(src_features, dst_features)
            verdict = compat.get("verdict")
            reasons = [reason.get("axis") for reason in (compat.get("reasons") or ())]
            is_unwind = "Unwind@" in str(sb.funcs.get(addr, {}).get("name") or "")
            if is_unwind:
                veto = "unwind_target"
                hard_negatives.append({"dst": addr, "score": round(score_val, 4), "veto": veto})
            elif verdict == "incompatible" and "ret_cleanup" in reasons:
                veto = "ret_cleanup"
            else:
                veto = None
            compat_by_addr[addr] = (verdict, reasons)
            window.append({"dst": addr, "contract": verdict, "veto": veto})
            if veto is None:
                eligible.append((addr, score_val))
        best_veto = window[0]["veto"]
        if best_veto is None:
            kept_addr, promoted = b, False
        elif eligible:
            kept_addr, promoted = eligible[0][0], eligible[0][0] != b
        else:
            kept_addr, promoted = b, False
        kept_score = next(score_val for addr, score_val in candidates if addr == kept_addr)
        kept_veto = next(row["veto"] for row in window if row["dst"] == kept_addr)
        verdict, reasons = compat_by_addr[kept_addr]
        drop = not eligible and best_veto == "unwind_target"
        return {
            "drop": drop,
            "vetoed_best": best_veto is not None,
            "kept_addr": kept_addr,
            "kept_score": kept_score,
            "alternatives": [
                {
                    "dst": addr,
                    "score": round(score_val, 4),
                    "veto": next(row["veto"] for row in window if row["dst"] == addr),
                }
                for addr, score_val in candidates
            ],
            "contract": {
                "verdict": verdict,
                "reasons": reasons,
                "veto": kept_veto,
                "vetoed_best": best_veto is not None,
                "promoted": promoted,
                "window": window,
                "hard_negatives": hard_negatives,
            },
        }

    budget_limited = False
    for rnd in range(rounds):
        # Every earlier stage can claim destinations, including BSim and its
        # propagated neighbors. Exclude all of them before scoring residue.
        taken = set(mapping.values())
        new = 0
        scored: list[tuple[float, float, int, int, dict, float, int | None]] = []
        # Mapping is unchanged while this round gathers all scores.  Building
        # its string-keyed copy once per source made large build pairs repeat
        # thousands of identical dict allocations before any candidate ran.
        int_map = {str(k): str(v) for k, v in mapping.items()} if mapping else None
        report(0, round_index=rnd)
        for scanned, a in enumerate(src_addrs, 1):
            if a in mapping:
                if scanned % 64 == 0:
                    report(scanned, round_index=rnd)
                continue
            cands = candidate_pairs(sa, sb, a, mapping)
            cands -= taken
            if not cands:
                if scanned % 64 == 0:
                    report(scanned, round_index=rnd)
                continue
            fa = sa.funcs[a]
            best = second = 0.0
            best_b = None
            second_b = None
            best_ev: dict = {}
            # The source feature record is unchanged for all candidates in
            # this round; only candidate-specific decompilation data is copied.
            fa_score = {**fa, "canon_arity": None} if use_name_features is False else fa
            if sa.decomp.get(a):
                fa_score = {**fa_score, "decomp": sa.decomp[a]}
            for b in sorted(cands):
                raw_fb = sb.funcs[b]
                needs_copy = use_name_features is False or bool(sb.decomp.get(b))
                fb = dict(raw_fb) if needs_copy else raw_fb
                if use_name_features is False:
                    fb["canon_arity"] = None
                if sb.decomp.get(b):
                    fb["decomp"] = sb.decomp[b]
                s, ev = score_features(
                    fa_score,
                    fb,
                    same_arch=same_arch,
                    mapping=int_map,
                    fuzzy_left_bits=sa.fuzzy_bits_for(a),
                    fuzzy_right_bits=sb.fuzzy_bits_for(b),
                )
                ev = dict(ev)
                src_pcode = (sa.decomp.get(a) or {}).get("pcode_fingerprint")
                dst_pcode = (sb.decomp.get(b) or {}).get("pcode_fingerprint")
                if src_pcode and dst_pcode:
                    ev["pcode_fingerprint"] = 1.0 if src_pcode == dst_pcode else 0.0
                    if src_pcode == dst_pcode:
                        ev["channels"] = sorted(set(ev.get("channels") or ()) | {"M"})
                ev["target_candidate_count"] = len(cands)
                ev["target_unique"] = len(cands) == 1
                if s > best:
                    second, second_b, best, best_b, best_ev = best, best_b, s, b, ev
                elif s > second:
                    second, second_b = s, b
            if best_b is not None:
                margin = candidate_margin(best, second, len(cands))
                scored.append((best, margin, a, best_b, best_ev, second, second_b))
            if scanned % 64 == 0:
                report(scanned, round_index=rnd)

        report(len(src_addrs), round_index=rnd)

        scored.sort(key=lambda t: (-t[0], -t[1], t[2], t[3]))
        tied_destinations = reverse_ties(scored)
        for best, margin, a, b, ev, second, second_b in scored:
            if a in mapping or b in taken:
                continue
            if b in tied_destinations:
                # Equal best scores from several sources: order must not choose (U1 RC-07).
                results.setdefault(a, {
                    "dst": b, "score": round(best, 4), "margin": round(margin, 4),
                    "evidence": enrich_evidence(ev, status="ambiguous", identity_claim=False, stage="fuzzy_residue",
                                                alternatives=[{"src": x} for x in sorted(tied_destinations[b])]),
                    "round": rnd, "status": "review", "kind": "ambiguous", "ambiguity": "tied_sources",
                })
                continue
            if contract_features is not None:
                veto_info = _contract_veto(a, b, best, second, second_b)
                if veto_info["drop"]:
                    continue
                if veto_info["vetoed_best"]:
                    kept_addr = veto_info["kept_addr"]
                    if kept_addr in taken:
                        continue
                    results[a] = {
                        "dst": kept_addr,
                        "score": round(veto_info["kept_score"], 4),
                        "margin": round(margin, 4),
                        "evidence": enrich_evidence(
                            {**ev, "contract": veto_info["contract"]},
                            status="review",
                            alternatives=veto_info["alternatives"],
                            identity_claim=False,
                            stage="fuzzy_residue",
                        ),
                        "round": rnd,
                        "status": "review",
                        "kind": "ambiguous" if veto_info["contract"]["promoted"] else "fuzzy",
                    }
                    continue
                ev = {**ev, "contract": veto_info["contract"]}
            confidence = channel_confidence(
                primary=str(ev.get("primary_channel") or "fuzzy"), evidence=ev,
                n_instr=sa.funcs[a].get("n_instr"), margin=margin, unique=True,
            )
            if (_passes(policy["verify"], best, margin, ev.get("_content", 0))
                    and ev.get("compunit") != 0.0
                    # Generated fuzzy candidates are a shortlist, not proof of
                    # target-wide uniqueness.  Keep them review-only unless a
                    # future indexed stage explicitly supplies that proof.
                    and ev.get("target_unique") is True
                    and allows_verify(confidence, unique=True)):
                mapping[a] = b
                taken.add(b)
                results[a] = {
                    "dst": b,
                    "score": round(best, 4),
                    "margin": round(margin, 4),
                    "evidence": enrich_evidence(ev, status="verify", identity_claim=True, stage="fuzzy_residue"),
                    "round": rnd,
                    "kind": "fuzzy",
                }
                new += 1
            elif a not in results or (results[a].get("kind") not in {"callgraph", "anchor", "bsim"} and best > results[a]["score"]):
                alts = [{"dst": b, "score": round(best, 4)}]
                if second_b is not None and second > 0 and abs(best - second) < 0.05:
                    alts.append({"dst": second_b, "score": round(second, 4)})
                    results[a] = {
                        "dst": b,
                        "score": round(best, 4),
                        "margin": round(margin, 4),
                        "evidence": enrich_evidence(ev, status="ambiguous", alternatives=alts, identity_claim=False, stage="fuzzy_residue"),
                        "round": rnd,
                        "status": "review",
                        "kind": "ambiguous",
                    }
                else:
                    results[a] = {
                        "dst": b,
                        "score": round(best, 4),
                        "margin": round(margin, 4),
                        "evidence": enrich_evidence(ev, stage="fuzzy_residue"),
                        "round": rnd,
                        "kind": "fuzzy",
                    }
        if new:
            propagation_dependencies = sorted(mapping)
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
                    with_dependencies=True,
                ),
                id_field="addr",
                left_lookup=sa.funcs,
                right_lookup=sb.funcs,
                round_label=rnd,
                pair_class=pair_class,
            )
            tokenise_callgraph_results()
            taken = set(mapping.values())
            new += grown
        if new == 0:
            break
        budget_limited = rnd == rounds - 1  # the last allowed round was still adding matches

    # Optional embeddings/BSim are deliberately last: they may corroborate
    # residue but never consume candidates before deterministic stages.
    before_bsim = len(mapping)
    late_bsim_receipt = _fuse_bsim(con, sa, sb, mapping, results, pair_class)
    if late_bsim_receipt.get("row_count") is not None:
        bsim_receipt["row_count"] = late_bsim_receipt["row_count"]
        bsim_receipt["ok"] = bool(bsim_receipt.get("ok") or late_bsim_receipt.get("ok"))
        bsim_receipt["hits_used"] = max(int(bsim_receipt.get("hits_used") or 0), int(late_bsim_receipt.get("hits_used") or 0))
    # BSim anchors are just as valuable as exact/fuzzy anchors: propagate
    # their caller/callee relationships before descending to block-level
    # residue.  This keeps the cascade monotonic while allowing a strong
    # significance hit to unlock otherwise-isolated neighbors.
    if len(mapping) > before_bsim:
        grown = record_pairs(
            results,
            propagate_call_graph(
                sa.callees, sa.callers, sb.callees, sb.callers, mapping,
                src_eligible=src_eligible, dst_eligible=dst_eligible,
                with_dependencies=True,
            ),
            id_field="addr", left_lookup=sa.funcs, right_lookup=sb.funcs,
            round_label="bsim-callgraph", pair_class=pair_class,
        )
        # The post-BSim site persisted raw parent addrs: no conversion ran
        # after it, so its rows could never intersect the quarantine set.
        tokenise_callgraph_results()
        if grown:
            bsim_receipt["propagated"] = grown
            mapping.update({src: int(item["dst"]) for src, item in results.items()
                            if item.get("kind") == "callgraph"
                            and item.get("round") == "bsim-callgraph"
                            and src not in mapping})

    # A self-comparison has no disappeared function or grown counterpart and
    # therefore cannot establish a block-level non-1:1 correspondence.
    inlines = [] if src_id == dst_id else leftover_inlines(
        [sa.funcs[a] for a in src_addrs if a not in mapping],
        [sb.funcs[b] for b in sorted(dst_eligible) if b not in mapping.values()],
    )
    for hit in inlines:
        src_addr = hit["missing_id"]
        if src_addr in mapping:
            continue
        relation = str(hit.get("kind") or "inline")
        results[src_addr] = {
            "dst": hit["host_id"],
            "score": 0.5,
            "margin": 1.0,
            "evidence": enrich_evidence(
                {
                    relation: 1.0,
                    "block_count": hit["block_count"],
                    "propagation_kind": relation,
                    "host_unique": hit.get("host_unique") is True,
                    "alternatives": hit.get("alternatives") or [],
                    "fragments": hit.get("fragments") or [],
                    "folded_missing_ids": hit.get("folded_missing_ids") or [],
                    "coverage": hit.get("coverage"),
                },
                kind=relation,
                status="review",
                relation=relation,
                identity_claim=False,
                src_end=hit.get("src_end"),
                dst_end=hit.get("dst_end"),
            ),
            "round": relation,
            "kind": relation,
            "status": "review",
        }
    from .binexport import binexport_available
    from .emulate_verify import unicorn_available
    from .match_outcomes import terminal_outcomes

    return {
        "mapping": mapping,
        "results": results,
        "outcomes": terminal_outcomes(
            sa.funcs, mapping, results,
            scope=[a for a in sa.funcs if restrict_src is None or a in restrict_src],
            budget_limited=budget_limited,
        ),
        "src": sa,
        "dst": sb,
        "pair_class": pair_class,
        "inlines": inlines,
        "optional_channels": {
            "bsim": bsim_receipt,
            "binexport": {"skipped": True, "reason": "no_pairwise_bindiff_adapter", "available": binexport_available()},
            "emulate": {"skipped": True, "reason": "residue_path_not_configured", "available": unicorn_available()},
            "pcode": _pcode_receipt(con, src_id, dst_id),
            "embeddings": {"skipped": True, "reason": "no_embedding_evidence_store"},
            "donor_schedule": {"skipped": True, "reason": "use spanning_forest_pairs at pair-prep"},
            "channel_confidence": {"wired": True, "note": "consult allows_auto/allows_verify when promoting auto"},
        },
    }


__all__ = ["Binary", "candidate_pairs", "match_binaries", "status_for"]
