"""Pack-only readiness projection; unknown environment facts stay unknown."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .hookpack_v2 import FORMAT as PACK_FORMAT, STATUSES, read_hookpack

FORMAT = "agentdecompile.readiness/v1"


def build_readiness_report(source) -> dict:
    pack = read_hookpack(source)
    if pack["format"] != PACK_FORMAT:
        raise ValueError("Readiness reports require a v2 entity hook pack")
    rows = []
    builds = []
    for binary in sorted(pack["binaries"], key=lambda b: b["slug"]):
        slug = binary["slug"]
        counts = Counter()
        required_blocked = []
        for entity in sorted(pack["entities"], key=lambda e: e["key"]):
            status = entity["status"].get(slug, "unresolved")
            counts[status] += 1
            instances = [i for i in entity.get("instances", []) if i.get("build") == slug]
            reasons = sorted({i.get("reason", "") for i in instances if i.get("reason")})
            row = {"entity": entity["key"], "kind": entity["kind"], "build": slug,
                   "status": status, "required": bool(entity.get("required")),
                   "observed_status": entity.get("observed_status", {}).get(slug, "unknown"),
                   "reason": "; ".join(reasons) or ("No build-specific evidence" if status == "unresolved" else "See locator receipt")}
            rows.append(row)
            if row["required"] and status != "resolved":
                required_blocked.append(entity["key"])
        total = sum(counts.values())
        resolved = counts["resolved"]
        summary = (f"{slug}: {resolved} of {total} entities have resolved locators; "
                   f"{len(required_blocked)} required entities remain blocked. "
                   "Runtime operations require their own ABI, lifetime and operation evidence.")
        if not total:
            summary = f"{slug}: no entity evidence is available; no runtime readiness is claimed."
        builds.append({"build": slug, "content_sha256": binary.get("content_sha256") or binary.get("sha256"),
            "counts": {status: counts[status] for status in sorted(STATUSES)},
            "required_blocked": required_blocked, "summary": summary,
            "environment": {"unpack_state": binary.get("unpack_state", "unknown"),
                "cfg_instrumented": binary.get("cfg_instrumented"),
                "integrity_checks": binary.get("integrity_checks", "unknown"),
                "detour_adapter": binary.get("detour_adapter", {"available": False, "reason": "No adapter evidence"})}})
    return {"format": FORMAT, "basis": pack["basis"], "pack_sha256": pack.get("pack_sha256") or pack.get("source_pack_sha256"),
            "corpus_manifest_hash": pack.get("corpus_manifest_hash"), "builds": builds, "entities": rows}


def render_readiness_report(report: dict) -> str:
    def escape(value):
        return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")
    lines = ["# Export readiness", "", "Locator resolution and runtime operation readiness are separate evidence claims.", ""]
    for build in report["builds"]:
        lines.extend(["## " + escape(build["build"]), "", build["summary"], "",
                      "Environment: `" + json.dumps(build["environment"], sort_keys=True) + "`", ""])
    lines.extend(["| Entity | Build | Status | Required | Reason |", "| --- | --- | --- | --- | --- |"])
    for row in report["entities"]:
        lines.append("| " + " | ".join(escape(row[k]) for k in ("entity", "build", "status", "required", "reason")) + " |")
    return "\n".join(lines) + "\n"


def export_readiness_report(pack, out) -> dict:
    report = build_readiness_report(pack)
    target = Path(out)
    markdown = target.with_suffix(".md")
    if markdown == target:
        raise ValueError("Readiness JSON output must not use the .md extension")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown.write_text(render_readiness_report(report), encoding="utf-8")
    return {"wrote": str(target), "markdown": str(markdown), "format": FORMAT,
            "builds": len(report["builds"]), "entities": len(report["entities"])}
