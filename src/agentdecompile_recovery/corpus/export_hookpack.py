"""Emit a hook pack for the runtime host from the identity store.

A VA is an instance. The pack's identity is the logical site plus the
signature family that hits the most registered builds. expected_bytes
are copied from a registered image when that window is unique. They
are never invented.

Per binary the pack carries the identity the host rebases against
(image_base, sha256). Per site it carries every instance window so a
resolver can try them in turn on an unknown build, plus the kind,
required flag, field extent and adapter key that a site policy and an
adapter map supply. Those two are data files, never core.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from .determinism_basis import basis
from .hookpack_policy import (
    check_adapter_key_collisions,
    file_sha256,
    load_adapter_map,
    load_site_policy,
    lookup_site,
)
from .operation_contract import bind_operations, load_operation_contract


FORMAT = "agentdecompile.hookpack/v1"
FORMAT_V2 = "agentdecompile.hookpack/v2"


def function_abi(con, binary_id: int, addr: int) -> dict:
    """Observed ABI for v2 consumers; never infer storage from a type name.

    v1 emission intentionally does not call this helper, keeping its bytes and
    consumer contract unchanged. Legacy captures remain explicitly uncertain.
    Confidence describes captured metadata, not successful runtime invocation.
    """
    columns = {row[1] for row in con.execute("PRAGMA table_info(func)")}
    if not {"return_storage", "function_properties"} <= columns:
        return {"confidence": 0.0, "reason": "ABI storage was not collected", "parameters": [], "returnStorage": None}
    row = con.execute(
        "SELECT calling_convention, return_type, param_count, return_storage, function_properties "
        "FROM func WHERE binary_id=? AND addr=?", (binary_id, addr),
    ).fetchone()
    if row is None:
        return {"confidence": 0.0, "reason": "Function is absent from the capture", "parameters": [], "returnStorage": None}
    convention, return_type, count, return_json, props_json = row
    properties = json.loads(props_json) if props_json is not None else {}
    returned = json.loads(return_json) if return_json is not None else None
    parameters = [
        {"ordinal": ordinal, "name": name, "dataType": type_name,
         "storage": json.loads(pieces) if pieces is not None else None}
        for ordinal, name, type_name, pieces in con.execute(
            "SELECT ordinal,name,type,pieces_json FROM func_param WHERE binary_id=? AND addr=? ORDER BY ordinal",
            (binary_id, addr),
        )
    ]
    def known_pieces(pieces):
        return isinstance(pieces, list) and bool(pieces) and all(
            isinstance(piece, dict) and isinstance(piece.get("size"), int)
            and not isinstance(piece["size"], bool) and piece["size"] > 0
            and (bool(piece.get("register")) != (isinstance(piece.get("stackOffset"), int)
                                                   and not isinstance(piece.get("stackOffset"), bool)))
            for piece in pieces
        )
    complete = (
        count is not None and count == len(parameters)
        and [p["ordinal"] for p in parameters] == list(range(count))
        and all(p["dataType"] and known_pieces(p["storage"]) for p in parameters)
        and bool(return_type)
        and (known_pieces(returned) or (return_type == "void" and returned == []))
        and convention not in (None, "", "unknown", "__unknown")
        and isinstance(properties, dict) and not properties.get("varArgs")
    )
    trusted_signature = isinstance(properties, dict) and properties.get("signatureSource") in {"USER_DEFINED", "IMPORTED"}
    confidence = 1.0 if complete and trusted_signature else 0.5 if complete else 0.0
    return {
        "callingConvention": convention, "returnType": return_type,
        "returnStorage": returned, "parameters": parameters,
        "properties": properties, "confidence": confidence,
        "reason": "Captured explicit signature and storage" if confidence == 1.0 else
                  "Analyzer-derived signature; runtime ABI unverified" if complete else
                  "ABI storage incomplete or unsupported; typed calls refused",
    }


def _preferred_signature(best: str | None, member_sigs: list[str]) -> dict:
    members = [str(s).strip() for s in member_sigs if s and str(s).strip()]
    best_s = str(best or "").strip()
    if not members:
        return {"kind": "none", "value": ""}
    if best_s and all(sig == best_s for sig in members):
        return {"kind": "shared", "value": best_s, "hits": len(members), "of": len(members)}
    # Count ties resolve by value, not by insertion order.
    value, count = max(Counter(members).items(), key=lambda kv: (kv[1], kv[0]))
    return {
        "kind": "shared" if count == len(members) else "majority",
        "value": value,
        "hits": count,
        "of": len(members),
    }


def _site_key(lf) -> str:
    return (lf["best_name"] or lf["canon_key"] or f"logical_{int(lf['id'])}").replace(" ", "_")


def unique_window(image: bytes, offset: int, size: int, *, min_n: int = 8, max_n: int = 24) -> bytes | None:
    """Shortest unique slice at *offset*, or None if the window is not unique."""
    if offset < 0 or offset >= len(image):
        return None
    limit = min(len(image) - offset, max(int(size or 0), min_n), max_n)
    if limit < min_n:
        return None
    for n in range(min_n, limit + 1):
        window = image[offset : offset + n]
        if image.count(window) == 1:
            return window
    return None


def _raw_image(repo_path: str) -> bytes | None:
    from .ghidra_bulk import raw_image_path

    path = raw_image_path(repo_path or "")
    if not path.is_file():
        return None
    try:
        return path.read_bytes()
    except OSError:
        return None


def _file_offset(image: bytes, addr: int, load_base: int | None = None) -> int | None:
    """File offset of the loaded VA *addr* inside *image*, or None.

    *load_base* is the store's ``binary.image_base``; None means use the
    image header's own base.
    """
    from .exact_universal import mapper_for

    mapper, _kind = mapper_for(image, load_base)
    if mapper is None:
        return None
    return mapper(int(addr))


def _binary_entry(b: dict, image_for) -> dict:
    """One ``binaries[]`` row: the identity the host rebases and verifies against.

    *image_for* is a lazy loader; it is only called when no hash is stored,
    so a backfilled store never touches the raw image for a binary that no
    instance references.
    """
    entry = {
        "slug": b["slug"],
        "game": b["game"],
        "platform": b["platform"],
        "format": b["format"],
        "arch": b.get("arch"),
        "bits": b.get("bits"),
    }
    if b.get("image_base") is not None:
        entry["image_base"] = int(b["image_base"])
    stored = str(b.get("content_sha256") or "").strip()
    if stored:
        entry["sha256"] = stored
        entry["sha256_source"] = "stored"
    else:
        image = image_for()
        if image:
            entry["sha256"] = hashlib.sha256(image).hexdigest()
            entry["sha256_source"] = "computed"
    return entry


def export_hookpack(con, out: Path, *, site_policy=None, adapter_map=None, operation_contract=None, format="v1") -> dict:
    """Write the pack for *con* to *out*.

    *site_policy* and *adapter_map* are optional file paths; see
    :mod:`hookpack_policy` for their shapes. With neither given the pack
    carries default site kinds and no adapter keys.
    """
    if format not in ("v1", "v2", FORMAT, FORMAT_V2):
        raise ValueError(f"Unsupported hook pack format: {format}")
    if format in ("v2", FORMAT_V2):
        from .hookpack_v2 import build_hookpack_v2
        pack = build_hookpack_v2(con, site_policy=site_policy, adapter_map=adapter_map,
                                 operation_contract=operation_contract)
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(pack, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return {"wrote": str(out), "format": FORMAT_V2, "entities": len(pack["entities"]),
                "binaries": len(pack["binaries"]), "pack_sha256": pack["pack_sha256"]}
    policy = load_site_policy(site_policy)
    amap = load_adapter_map(adapter_map)
    operations = load_operation_contract(operation_contract)
    # Basis first: it refuses in about a millisecond, and the site loop
    # below can take minutes on a real store (A5). A store that cannot
    # declare its basis has no pack to build.
    declared_basis = basis(con)
    binaries = {
        int(r["id"]): dict(r)
        for r in con.execute(
            "SELECT id, slug, game, platform, format, arch, bits, repo_path, image_base, content_sha256"
            " FROM binary ORDER BY id"
        )
    }
    raw_by_bid: dict[int, bytes | None] = {}

    def image_for(bid: int) -> bytes | None:
        if bid not in raw_by_bid:
            raw_by_bid[bid] = _raw_image(str((binaries.get(bid) or {}).get("repo_path") or ""))
        return raw_by_bid[bid]

    # Instance order below keys on binary.content_sha256 (design decision 3);
    # refuse up front for every build an identity row references rather than
    # let a NULL sort first silently. Builds no identity references keep the
    # image-derived fallback in _binary_entry.
    from .logical import content_hash_index

    content_hash_index(con, (r[0] for r in con.execute("SELECT DISTINCT binary_id FROM identity")))

    logicals = list(con.execute(
        "SELECT id, best_name, best_signature, canon_class, canon_method, canon_key, n_members"
        " FROM logical_function ORDER BY id"
    ))
    site_keys = Counter(_site_key(lf) for lf in logicals)
    sites: dict[str, dict] = {}
    matched_policy: set[str] = set()
    matched_map: set[str] = set()
    adapter_keys_by_site: dict[str, str] = {}
    for lf in logicals:
        lid = int(lf["id"])
        # instances[] is emitted in this order, so the key must be
        # build-invariant: the build's content hash, then the address.
        members = list(con.execute(
            """SELECT i.binary_id, i.addr, i.confidence, i.method,
                      f.name, f.signature, f.source_file, f.object_file, f.size
                 FROM identity i
                 JOIN binary b ON b.id=i.binary_id
                 LEFT JOIN func f ON f.binary_id=i.binary_id AND f.addr=i.addr
                WHERE i.logical_id=?
                ORDER BY b.content_sha256, i.addr""",
            (lid,),
        ))
        member_sigs = [str(m["signature"]) for m in members if m["signature"]]
        instances = []
        windows: list[bytes] = []
        instance_windows: list[dict] = []
        for m in members:
            bid = int(m["binary_id"])
            b = binaries.get(bid) or {}
            row = {
                "binary": b.get("slug") or str(bid),
                "addr": int(m["addr"] or 0),
                "name": m["name"] or "",
                "confidence": m["confidence"],
                "method": m["method"] or "",
                "source_file": m["source_file"] or "",
            }
            image = image_for(bid)
            if image:
                load_base = b.get("image_base")
                addr = int(m["addr"] or 0)
                # No store base means the header base. Keep the two-argument
                # call for that case so two-argument stand-ins still work.
                off = _file_offset(image, addr) if load_base is None else _file_offset(image, addr, load_base)
                window = unique_window(image, off, int(m["size"] or 0)) if off is not None else None
                if window:
                    hex_win = window.hex().upper()
                    row["expected_bytes"] = hex_win
                    windows.append(window)
                    instance_windows.append({"binary": row["binary"], "expected_bytes": hex_win})
                else:
                    row["window"] = "not_unique"
            else:
                row["window"] = "no_image"
            instances.append(row)
        site_bytes = ""
        if windows:
            counts = Counter(w.hex().upper() for w in windows)
            hex_win, n = counts.most_common(1)[0]
            if n == len(windows):
                site_bytes = hex_win
        base_key = _site_key(lf)
        key = base_key
        if site_keys[key] > 1:
            key = f"{key}__{lid}"
        if key in sites:
            raise ValueError(f"hook pack site key collision: {key}")

        policy_key, site_policy_entry = lookup_site(policy["sites"], key, base_key)
        if policy_key is not None:
            matched_policy.add(policy_key)
        rule = site_policy_entry or policy["default"]
        site = {
            "logical_id": lid,
            "cls": lf["canon_class"] or "",
            "method": lf["canon_method"] or "",
            "signature": _preferred_signature(lf["best_signature"], member_sigs),
            "kind": rule["kind"],
            "required": bool(rule["required"]),
            "instances": instances,
            # Sort by (slug, bytes): one build may carry several instances,
            # and slug alone would leave their order to insertion.
            "instance_windows": sorted(instance_windows, key=lambda w: (w["binary"], w["expected_bytes"])),
        }
        if rule.get("field"):
            site["offset"] = int(rule["field"]["offset"])
            site["size"] = int(rule["field"]["size"])
        if site_bytes:
            site["expected_bytes"] = site_bytes
        if windows:
            hits = max(Counter(w.hex().upper() for w in windows).values())
            site["expected_bytes_agreement"] = {"hits": hits, "of": len(windows)}

        map_key, adapter_key = lookup_site(amap["keys"], key, base_key)
        if map_key is not None:
            matched_map.add(map_key)
            site["adapter_key"] = adapter_key
            adapter_keys_by_site[key] = adapter_key
        alias_key, aliases = lookup_site(amap["aliases"], key, base_key)
        if alias_key is not None:
            matched_map.add(alias_key)
            site["aliases"] = list(aliases)
        sites[key] = site

    # A base-key fallback can hand one adapter key to several suffixed sites.
    # That is the same collision the loader rejects, so reject it here too.
    check_adapter_key_collisions(adapter_keys_by_site, where="hook pack")

    pack = {
        "format": FORMAT,
        "basis": declared_basis,
        "note": "VA is a cache. Resolve with signature; bind by logical_id.",
        "binaries": sorted(
            (_binary_entry(b, lambda bid=bid: image_for(bid)) for bid, b in binaries.items()),
            key=lambda e: e["slug"],
        ),
        "sites": sites,
    }
    if operations:
        by_slug = {
            entry["slug"]: entry
            for entry in pack["binaries"]
        }
        raw_images = {
            str(binary.get("slug") or bid): image_for(bid)
            for bid, binary in binaries.items()
        }
        pack["operations"] = bind_operations(
            operations,
            binaries=by_slug,
            sites=sites,
            raw_images=raw_images,
        )
    if site_policy is not None or adapter_map is not None:
        pack["policy_hashes"] = {
            "site_policy": file_sha256(site_policy),
            "adapter_map": file_sha256(adapter_map),
        }
        map_site_keys = set(amap["keys"]) | set(amap["aliases"])
        pack["policy_unmatched"] = {
            "sites": sorted(set(policy["sites"]) - matched_policy),
            "adapter_keys": sorted(map_site_keys - matched_map),
        }
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(pack, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"wrote": str(out), "sites": len(sites), "binaries": len(binaries), "operations": len(pack.get("operations", []))}
