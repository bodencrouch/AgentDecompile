"""Pack-only cross-build differences; absent decode evidence remains blocked."""
from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

from .divergence import compare_graphs
from .hookpack_v2 import FORMAT as PACK_FORMAT, read_hookpack

FORMAT = "agentdecompile.divergence/v1"


def _delta(left, right):
    """Stable keyed shape differences without forcing entity correspondence."""
    keys = sorted(set(left) | set(right))
    return [{"key": key, "A": left.get(key), "B": right.get(key)} for key in keys if left.get(key) != right.get(key)]


def build_divergence_report(source) -> dict:
    pack = read_hookpack(source)
    if pack["format"] != PACK_FORMAT:
        raise ValueError("Divergence reports require a v2 hook pack")
    builds = sorted(b["slug"] for b in pack["binaries"])
    policy = pack["basis"].get("threshold_params", {}).get("divergence")
    rows = []
    for entity in sorted(pack["entities"], key=lambda e: e["key"]):
        for build_a, build_b in combinations(builds, 2):
            row = {"entity": entity["key"], "kind": entity["kind"], "build_A": build_a, "build_B": build_b,
                   "status_A": entity["status"][build_a], "status_B": entity["status"][build_b]}
            shape = entity.get("shape") or {}
            available = {}
            for name in ("fields", "slots", "entries"):
                per_build = shape.get(name) or {}
                available[name] = {"A": build_a in per_build, "B": build_b in per_build}
                def keyed(build):
                    values = per_build.get(build, [])
                    if isinstance(values, dict):
                        return values
                    result = {}
                    for ordinal, item in enumerate(values):
                        key = str(item.get("name", item.get("ordinal", ordinal)))
                        if key in result:
                            raise ValueError(f"duplicate {name} shape key: {key}")
                        result[key] = item
                    return result
                row[name + "_delta"] = _delta(keyed(build_a), keyed(build_b))
            row["shape_evidence"] = available
            if entity["kind"] in ("function", "class_ctor", "library_fn"):
                a = [i for i in entity.get("instances", []) if i.get("build") == build_a]
                b = [i for i in entity.get("instances", []) if i.get("build") == build_b]
                try:
                    if len(a) != 1 or len(b) != 1:
                        raise ValueError("single_qualified_graph_per_build_required")
                    pair_class = a[0].get("pair_class", b[0].get("pair_class", "default"))
                    thresholds = policy.get(pair_class) if isinstance(policy, dict) and "version" not in policy else policy
                    metric = compare_graphs(a[0].get("divergence_graph"), b[0].get("divergence_graph"), thresholds)
                    row.update(status="complete", metric=metric)
                except ValueError as exc:
                    row.update(status="blocked", reason=str(exc), metric=None)
            else:
                comparable = any(v["A"] and v["B"] for v in available.values())
                row.update(status="complete" if comparable else "blocked", metric=None,
                           reason="shape_comparison_only; no function correspondence claimed" if comparable
                           else "build_pair_shape_evidence_unavailable")
            rows.append(row)
    blocked = sum(r["status"] == "blocked" for r in rows)
    return {"format": FORMAT, "basis": pack["basis"], "pack_sha256": pack.get("pack_sha256") or pack.get("source_pack_sha256"),
            "corpus_manifest_hash": pack.get("corpus_manifest_hash"), "status": "blocked" if blocked else "complete",
            "blocked_pairs": blocked, "pairs": rows,
            "evidence_contract": "Function classification requires decode-derived masked block multisets and recorded rational thresholds; existing analyzer CFG counts do not qualify."}


def export_divergence_report(pack, out) -> dict:
    report = build_divergence_report(pack)
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + "\n", encoding="utf-8")
    return {"wrote": str(target), "format": FORMAT, "status": report["status"],
            "pairs": len(report["pairs"]), "blocked_pairs": report["blocked_pairs"]}
