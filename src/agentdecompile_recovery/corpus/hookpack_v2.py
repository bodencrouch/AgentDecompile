"""Versioned, conservative entity export over captured corpus evidence.

Static address and type witnesses are not runtime locator receipts. Their export
is useful without silently promoting them to portable or callable capabilities.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from .determinism_basis import basis

FORMAT = "agentdecompile.hookpack/v2"
STATUSES = frozenset({"resolved", "pinned", "degraded", "ambiguous", "unresolved", "contested"})
KINDS = frozenset("function patch_point immediate call_site global singleton struct class_ctor vtable rtti string table enum jump_table import export dispatch_table vm_opcode_table tls unwind section resource initializer entry_loop site_frame site_regs allocator library_fn inlined_region integrity_check".split())


def canonical_bytes(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n").encode()


def seal_pack(pack: dict) -> dict:
    """Hash the canonical complete payload excluding only its own hash field."""
    result = copy.deepcopy(pack)
    result.pop("pack_sha256", None)
    result["pack_sha256"] = hashlib.sha256(canonical_bytes(result)).hexdigest()
    return result


def _rows(con, sql, args=()):
    cursor = con.execute(sql, args)
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor]


def _abi(con, bid, addr):
    from .export_hookpack import function_abi
    result = function_abi(con, bid, addr)
    result["convention"] = result.get("callingConvention")
    result["args"] = [{"name": p["name"], "type": p["dataType"], "storage": p["storage"]}
                      for p in result["parameters"]]
    result["ret"] = {"type": result.get("returnType"), "storage": result.get("returnStorage")}
    result["provenance"] = "captured_function_storage"
    return result


def build_hookpack_v2(con, *, site_policy=None, adapter_map=None, operation_contract=None) -> dict:
    from .hookpack_policy import load_site_policy, load_adapter_map, lookup_site, file_sha256
    from .operation_contract import load_operation_contract
    declared = basis(con)
    policy, adapters = load_site_policy(site_policy), load_adapter_map(adapter_map)
    # A v1 operation binding is not transferable to v2 without a refusing consumer.
    if load_operation_contract(operation_contract):
        raise ValueError("v2 operation-contract binding is unavailable; use v1 for this contract")
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    builds = _rows(con, "SELECT * FROM binary ORDER BY slug")
    by_id = {b["id"]: b for b in builds}
    slugs = [b["slug"] for b in builds]
    binaries = []
    for b in builds:
        binaries.append({"slug": b["slug"], "content_sha256": b.get("content_sha256"),
            "sha256": b.get("content_sha256"), "image_base": b.get("image_base"),
            "arch": b.get("arch"), "bits": b.get("bits"), "format": b.get("format"),
            "endian": b.get("endian"), "pointer_size": (b["bits"] // 8 if b.get("bits") else None),
            "basis_hash": b.get("basis_hash"), "unpack_state": "unknown",
            "cfg_instrumented": None, "integrity_checks": "unknown",
            "detour_adapter": {"available": False, "reason": "No qualified architecture adapter receipt"}})
    entities = []
    bound = set()
    logicals = _rows(con, "SELECT * FROM logical_function ORDER BY canon_key, best_name, id")
    groups = []
    for lf in logicals:
        members = _rows(con, "SELECT i.*, f.name, f.signature FROM identity i LEFT JOIN func f ON f.binary_id=i.binary_id AND f.addr=i.addr WHERE i.logical_id=? ORDER BY i.binary_id,i.addr", (lf["id"],))
        fingerprint = sorted((str(by_id[m["binary_id"]].get("content_sha256") or ""), m["addr"]) for m in members)
        suffix = hashlib.sha256(canonical_bytes({"members": fingerprint})).hexdigest()[:16]
        groups.append(("function:" + str(lf.get("canon_key") or ((lf.get("best_name") or "anonymous") + ":" + suffix)), lf.get("best_name") or "", members))
        bound.update((m["binary_id"], m["addr"]) for m in members)
    for f in _rows(con, "SELECT binary_id,addr,name,signature FROM func ORDER BY binary_id,addr"):
        if (f["binary_id"], f["addr"]) not in bound:
            b = by_id[f["binary_id"]]
            groups.append((f"function:{b.get('content_sha256') or b['slug']}:{f['addr']:x}", f.get("name") or "", [f]))
    if len({g[0] for g in groups}) != len(groups):
        raise ValueError("Logical function stable-key collision; reconcile corpus identity before export")
    for key, name, members in groups:
        _, rule = lookup_site(policy["sites"], key, name)
        rule = rule or policy["default"]
        entity = {"key": key, "name": name, "kind": "function", "required": bool(rule["required"]),
                  "previous_keys": [], "shape": {}, "locators": [], "instances": [],
                  "status": {slug: "unresolved" for slug in slugs}, "observed_status": {slug: "unknown" for slug in slugs}}
        counts = {}
        for m in members:
            b = by_id[m["binary_id"]]
            slug = b["slug"]
            counts[slug] = counts.get(slug, 0) + 1
            known = b.get("image_base") is not None and bool(b.get("content_sha256"))
            status = "pinned" if known else "unresolved"
            reason = "Captured build-relative location; portable resolution and runtime use unverified" if known else "Missing image base or content digest"
            abi = _abi(con, m["binary_id"], m["addr"])
            entity["instances"].append({"build": slug, "addr": m["addr"], "status": status,
                "reason": reason, "resolved_by": "module_rva" if known else None, "detourable": False, "abi": abi})
            entity["status"][slug] = status
            if known:
                entity["locators"].append({"kind": "module_rva", "portable": False,
                    "value": m["addr"] - b["image_base"], "build": slug,
                    "verify": {"image_sha256": b["content_sha256"]},
                    "coverage": [{"build": slug, "status": "pinned", "reason": reason}]})
        for slug, count in counts.items():
            if count > 1:
                entity["status"][slug] = "ambiguous"
                for instance in entity["instances"]:
                    if instance["build"] == slug:
                        instance.update(status="ambiguous", reason="Multiple captured instances for this build")
        entity["instances"].sort(key=lambda i: (i["build"], i["addr"]))
        entity["locators"].sort(key=lambda l: (l["build"], l["value"]))
        abis = [i["abi"] for i in entity["instances"]]
        entity["abi"] = copy.deepcopy(abis[0]) if abis and all(a == abis[0] for a in abis) else {"confidence": 0.0, "reason": "Use per-build ABI; captured signatures differ or are absent"}
        _, adapter = lookup_site(adapters["keys"], key, name)
        if adapter:
            entity["adapter_key"] = adapter
        entities.append(entity)
    # Type definitions are build-local witnesses. Same spelling is not cross-build identity.
    if "ghidra_type" in tables:
        for t in _rows(con, "SELECT * FROM ghidra_type ORDER BY binary_id,name"):
            b = by_id.get(t["binary_id"])
            if b is None:
                continue
            fields = _rows(con, "SELECT * FROM ghidra_field WHERE binary_id=? AND type_name=? ORDER BY ordinal", (t["binary_id"], t["name"])) if "ghidra_field" in tables else []
            for field in fields:
                field.pop("binary_id", None)
                field["type"] = json.loads(field.pop("type_json"))
            kind = "enum" if t.get("kind") == "enum" else "struct"
            entities.append({"key": f"{kind}:{b.get('content_sha256') or b['slug']}:{t['name']}",
                "name": t["name"], "kind": kind, "required": False, "previous_keys": [],
                "shape": {"kind": t.get("kind"), "size": t.get("size"), "definition": t.get("definition"), "fields": {b["slug"]: fields}},
                "instances": [{"build": b["slug"], "status": "unresolved", "reason": "Captured type layout; runtime object locator unavailable"}],
                "locators": [], "status": {slug: "unresolved" for slug in slugs}})
    if "stabs_type" in tables:
        for t in _rows(con, "SELECT * FROM stabs_type ORDER BY binary_id,name,kind,stab,source_file,object_file"):
            b = by_id.get(t["binary_id"])
            kind = {"struct": "struct", "union": "struct", "enum": "enum", "s": "struct", "u": "struct", "e": "enum"}.get(t.get("kind"))
            if b is None or kind is None:
                continue
            witness = {k: t.get(k) for k in ("name", "kind", "stab", "source_file", "object_file")}
            witness_id = hashlib.sha256(canonical_bytes(witness)).hexdigest()[:16]
            entities.append({"key": f"{kind}:stabs:{b.get('content_sha256') or b['slug']}:{witness_id}",
                "name": t["name"], "kind": kind, "required": False, "previous_keys": [],
                "shape": {"debug_witness": witness}, "locators": [],
                "instances": [{"build": b["slug"], "status": "unresolved", "reason": "Debug type witness; runtime layout and locator unverified"}],
                "status": {slug: "unresolved" for slug in slugs}})
    # Multiple debug compilation units may repeat the exact same witness.
    entities = list({entity["key"]: entity for entity in entities}.values())
    pack = {"format": FORMAT, "basis": declared, "corpus_manifest_hash": declared["corpus_manifest_hash"],
            "binaries": binaries, "entities": sorted(entities, key=lambda e: e["key"]), "caves": [],
            "limitations": ["Static corpus witnesses do not establish runtime readiness", "Cave qualification requires decode and restoration receipts"],
            "policy_hashes": {"site_policy": file_sha256(site_policy), "adapter_map": file_sha256(adapter_map)}}
    from .cave_discovery import discovery_blocker
    pack["cave_discovery"] = [discovery_blocker(slug) for slug in slugs]
    return seal_pack(pack)


def read_hookpack(source, *, supported_kinds=None) -> dict:
    """Refuse unknown formats/statuses; ignore unknown kinds without promotion."""
    pack = copy.deepcopy(source) if isinstance(source, dict) else json.loads(Path(source).read_text(encoding="utf-8"))
    if not isinstance(pack, dict) or pack.get("format") not in {FORMAT, "agentdecompile.hookpack/v1"}:
        raise ValueError("Unsupported hook pack format")
    if pack["format"] != FORMAT:
        return pack
    if not isinstance(pack.get("basis"), dict) or not isinstance(pack.get("entities"), list):
        raise ValueError("v2 hook pack requires basis and entities")
    if pack.get("pack_sha256") and seal_pack(pack)["pack_sha256"] != pack["pack_sha256"]:
        raise ValueError("Hook pack digest mismatch")
    allowed = KINDS if supported_kinds is None else KINDS & set(supported_kinds)
    binaries = pack.get("binaries")
    if not isinstance(binaries, list) or any(not isinstance(b, dict) or not isinstance(b.get("slug"), str) or not b["slug"] for b in binaries):
        raise ValueError("v2 hook pack requires named binaries")
    slugs = {b["slug"] for b in binaries}
    if len(slugs) != len(binaries):
        raise ValueError("Duplicate build slug")
    accepted = []
    seen = set()
    for entity in pack["entities"]:
        if not isinstance(entity, dict):
            raise ValueError("Entity must be an object")
        if entity.get("kind") not in allowed:
            continue
        if not isinstance(entity.get("key"), str) or not entity["key"] or entity["key"] in seen:
            raise ValueError("Entity key missing or duplicated")
        seen.add(entity["key"])
        statuses = entity.get("status")
        if not isinstance(statuses, dict) or any(s not in STATUSES for s in statuses.values()):
            raise ValueError("Unknown entity status")
        if set(statuses) != slugs:
            raise ValueError("Entity status matrix must cover exactly the declared builds")
        for locator in entity.get("locators", []):
            for coverage in locator.get("coverage", []):
                if coverage.get("status") not in STATUSES or coverage.get("build") not in slugs:
                    raise ValueError("Unknown locator coverage status or build")
        for instance in entity.get("instances", []):
            if instance.get("build") not in slugs or instance.get("status") not in STATUSES:
                raise ValueError("Unknown instance status")
        accepted.append(entity)
    if len(accepted) != len(pack["entities"]):
        # A filtered view is not the original hashed payload. Retain its provenance
        # separately so a second consumer can validate this view without a false hash.
        if pack.get("pack_sha256"):
            pack["source_pack_sha256"] = pack.pop("pack_sha256")
    pack["entities"] = accepted
    return pack
