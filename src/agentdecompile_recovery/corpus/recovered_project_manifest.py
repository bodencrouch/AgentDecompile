"""Relocatable recovered-project manifest and its validator (P2-f).

``agentdecompile.recovered-project/v1`` records, per translation unit, the
source path and digest, the target image digest (which must equal the
manifest's image), the function/region placements it owns in that image,
the relocation expectations of each placement (records in the
``coff_fixup_roundtrip`` receipt format), the toolchain identity and the
unit's provenance. Every path is relative to the project root, so the tree
can be moved or shipped without editing the manifest.

The toolchain is either ``pinned`` to a sha256 identity or explicitly
``unpinned`` with a reason. Nothing here invents a pinned identity: the
package basis still says ``pinned:none`` for toolchains (U54), and that
string is refused as an identity.

:func:`validate` checks the manifest against a project root and the image
bytes and returns a deterministic receipt. It does not compile, link or
compare a rebuilt image. An ``accepted`` receipt means the manifest is
self-consistent, relocatable and current; it is not a rebuild claim.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path, PurePosixPath

from . import coff_fixup_roundtrip as _fixup

SCHEMA = "agentdecompile.recovered-project/v1"
RECEIPT_SCHEMA = "agentdecompile.recovered-project-validation/v1"
MANIFEST_NAME = "recovered_project.json"

PROVENANCES = ("placeholder", "recovered", "reused")
TOOLCHAIN_STATES = ("pinned", "unpinned")

#: Relocation type name -> field width, from the roundtrip module's table.
RELOCATION_WIDTHS = {spec[0]: spec[1] for spec in _fixup.RELOCATIONS.values()}
RELOCATION_KEYS = ("offset", "symbol", "target", "type")

CLAIM_BOUNDARY = ("Manifest consistency, relocatability and currency only. "
                  "No compile, link or whole-image comparison ran.")

_HEX64 = re.compile(r"[0-9a-f]{64}")
_ABSOLUTE = re.compile(r"^(?:/|~[/\\]|[A-Za-z]:[\\/]|\\\\)")


class ManifestError(ValueError):
    """A named reason a manifest cannot be built. ``reason`` is stable."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(reason if not detail else f"{reason}: {detail}")
        self.reason = reason


def sha256_hex(data: bytes) -> str:
    """Lowercase hex sha256, the digest form every manifest field uses."""
    return hashlib.sha256(data).hexdigest()


_sha256 = sha256_hex

def _is_hex64(value) -> bool:
    return isinstance(value, str) and _HEX64.fullmatch(value) is not None


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=True).encode("ascii") + b"\n"


# ------------------------------------------------------------------ builders


def image_identity(image: bytes, *, image_base: int, size_of_image: int) -> dict:
    """The target image by content digest plus its mapped VA range."""
    return {"sha256": _sha256(image), "image_base": int(image_base), "size_of_image": int(size_of_image)}


def pinned_toolchain(identity_sha256: str, *, compiler: str, linker: str | None = None,
                     flags: tuple[str, ...] | list[str] = ()) -> dict:
    """A toolchain pinned to a real identity digest. ``pinned:none`` is refused."""
    if not _is_hex64(identity_sha256):
        raise ManifestError("toolchain_identity_invalid", repr(identity_sha256))
    return {"state": "pinned", "identity_sha256": identity_sha256, "compiler": compiler,
            "linker": linker, "flags": list(flags)}


def unpinned_toolchain(reason: str) -> dict:
    """The explicit absence of a toolchain identity, with the reason."""
    return {"state": "unpinned", "reason": reason}


def relocations_from_receipt(receipt: dict) -> list[dict]:
    """Relocation expectations from a ``coff_fixup_roundtrip`` receipt."""
    if not isinstance(receipt, dict) or receipt.get("schema") != _fixup.SCHEMA:
        raise ManifestError("relocation_receipt_schema")
    if receipt.get("refusal") is not None or receipt.get("relocations") is None:
        raise ManifestError("relocation_receipt_refused", str(receipt.get("refusal")))
    if receipt.get("byte_equal_at_origin") is not True:
        raise ManifestError("relocation_receipt_not_byte_equal", str(receipt.get("byte_equal_at_origin")))
    return sorted((dict(r) for r in receipt["relocations"]), key=lambda r: (r["offset"], r["type"]))


def placement(symbol: str, va: int, size: int, *, relocations: list[dict] | None = None,
              relocation_receipt: dict | None = None) -> dict:
    """One placed function/region. A roundtrip receipt must describe this exact VA and size."""
    out = {"symbol": symbol, "va": int(va), "size": int(size), "relocations": list(relocations or [])}
    if relocation_receipt is not None:
        records = relocations_from_receipt(relocation_receipt)
        if relocation_receipt.get("place_va") != out["va"] or relocation_receipt.get("region_size") != out["size"]:
            raise ManifestError("relocation_receipt_mismatch",
                                f"receipt at {relocation_receipt.get('place_va')}+{relocation_receipt.get('region_size')}")
        out["relocations"] = records
        out["relocation_receipt_sha256"] = _sha256(json.dumps(relocation_receipt, sort_keys=True).encode())
    return out


def unit(unit_id: str, *, source_path: str, source_sha256: str, image_sha256: str, provenance: str,
         toolchain: dict, placements: list[dict]) -> dict:
    """One translation unit. ``toolchain`` and ``image_sha256`` have no default on purpose."""
    if provenance not in PROVENANCES:
        raise ManifestError("invalid_provenance", repr(provenance))
    return {"id": unit_id, "source": {"path": source_path, "sha256": source_sha256},
            "image_sha256": image_sha256,
            "provenance": provenance, "toolchain": copy.deepcopy(toolchain),
            "placements": sorted(copy.deepcopy(list(placements)), key=lambda p: (p["va"], p["symbol"]))}


def _sorted_units(units) -> list[dict]:
    units = copy.deepcopy(list(units))
    seen: set = set()
    for u in units:
        if u["id"] in seen:
            raise ManifestError("duplicate_unit", str(u["id"]))
        seen.add(u["id"])
    return sorted(units, key=lambda u: u["id"])


def build_manifest(*, project: str, image: dict, units, rebuildable: bool,
                   basis_hash: str | None) -> dict:
    """Canonical manifest: units sorted by id, placements by VA."""
    return {"schema": SCHEMA, "project": project, "image": dict(image),
            "basis_hash": basis_hash, "claims": {"rebuildable": bool(rebuildable)},
            "units": _sorted_units(units)}


def merge_manifests(shards) -> dict:
    """Merge shard manifests that share every header field (U148)."""
    shards = list(shards)
    if not shards:
        raise ManifestError("no_shards")
    header = {k: v for k, v in shards[0].items() if k != "units"}
    units = []
    for shard in shards:
        if {k: v for k, v in shard.items() if k != "units"} != header:
            raise ManifestError("shard_header_mismatch")
        units.extend(shard["units"])
    return {**copy.deepcopy(header), "units": _sorted_units(units)}


def dumps(manifest: dict) -> bytes:
    return _canonical(manifest)


def write(manifest: dict, project_root: Path) -> Path:
    path = Path(project_root) / MANIFEST_NAME
    path.write_bytes(dumps(manifest))
    return path


def load(project_root: Path) -> dict:
    return json.loads((Path(project_root) / MANIFEST_NAME).read_bytes())


# ------------------------------------------------------------------ validator


def _relocatable(path) -> bool:
    if not isinstance(path, str) or not path or "\\" in path or _ABSOLUTE.match(path):
        return False
    parts = PurePosixPath(path).parts
    return ".." not in parts and "." not in parts


def _leaks(node, where: str, skip: set[str]):
    """JSON pointers of string values that look like absolute host paths."""
    if where in skip:
        return
    if isinstance(node, str):
        if _ABSOLUTE.match(node):
            yield where
    elif isinstance(node, dict):
        for key in sorted(node):
            yield from _leaks(node[key], f"{where}.{key}", skip)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            yield from _leaks(item, f"{where}[{i}]", skip)


def _check_relocations(place: dict, unit_id, refuse) -> int:
    relocs = place.get("relocations", [])
    if not isinstance(relocs, list):
        refuse("invalid_relocation", unit_id, f"{place.get('symbol')}: not a list")
        return 0
    spans = []
    for rel in relocs:
        if not isinstance(rel, dict) or tuple(sorted(rel)) != RELOCATION_KEYS or not _is_int(rel.get("offset")):
            refuse("invalid_relocation", unit_id, f"{place.get('symbol')}: record shape")
            continue
        width = RELOCATION_WIDTHS.get(rel["type"])
        if width is None:
            refuse("unknown_relocation_type", unit_id, f"{place.get('symbol')}+{rel['offset']}: {rel['type']}")
            continue
        if rel["offset"] < 0 or rel["offset"] + width > place["size"]:
            refuse("relocation_outside_placement", unit_id, f"{place.get('symbol')}+{rel['offset']}")
            continue
        spans.append((rel["offset"], width))
    spans.sort()
    max_end = None
    for off, w in spans:
        if max_end is not None and off < max_end:
            refuse("overlapping_relocations", unit_id, f"{place.get('symbol')}+{off}")
        end = off + w
        if max_end is None or end > max_end:
            max_end = end
    return len(relocs)


def validate(manifest: dict, project_root: Path, image: bytes) -> dict:
    """Check *manifest* against the tree at *project_root* and the *image* bytes.

    Every fault is reported; the receipt lists them sorted by (reason, unit,
    detail). The receipt never records *project_root* or any absolute path,
    so a moved tree yields the same bytes.
    """
    refusals: list[dict] = []

    def refuse(reason: str, unit_id=None, detail: str = "") -> None:
        refusals.append({"reason": reason, "unit": unit_id, "detail": detail})

    observed = _sha256(image)
    receipt = {"schema": RECEIPT_SCHEMA, "manifest_schema": manifest.get("schema"),
               "manifest_sha256": _sha256(dumps(manifest)), "image_sha256_observed": observed,
               "rebuildable_claim": None, "counts": None, "claimBoundary": CLAIM_BOUNDARY}
    if manifest.get("schema") != SCHEMA:
        refuse("schema_mismatch", None, str(manifest.get("schema")))
        return _finish(receipt, refusals)

    root = Path(project_root)
    img = manifest.get("image") or {}
    base, extent = img.get("image_base"), img.get("size_of_image")
    image_ok = _is_int(base) and _is_int(extent) and extent > 0 and _is_hex64(img.get("sha256"))
    if not image_ok:
        refuse("invalid_image_identity")
    elif img["sha256"] != observed:
        refuse("stale_image_digest", None, f"manifest {img['sha256'][:16]} observed {observed[:16]}")

    claims = manifest.get("claims")
    rebuildable = claims.get("rebuildable") if isinstance(claims, dict) else None
    receipt["rebuildable_claim"] = rebuildable
    if not isinstance(rebuildable, bool):
        refuse("invalid_rebuildable_claim", None, repr(rebuildable))
    elif rebuildable and not _is_hex64(manifest.get("basis_hash")):
        refuse("basis_unrecorded_in_rebuildable_project")

    raw_units = manifest.get("units")
    if raw_units is None:
        refuse("no_units")
        units: list = []
    elif not isinstance(raw_units, list):
        refuse("invalid_units", None, type(raw_units).__name__)
        units = []
    elif not raw_units:
        refuse("no_units")
        units = []
    else:
        units = raw_units
    counts = {"units": len(units), "placements": 0, "placed_bytes": 0, "relocations": 0,
              "provenance": {p: 0 for p in PROVENANCES}, "toolchain": {s: 0 for s in TOOLCHAIN_STATES}}
    seen_ids: set = set()
    seen_paths: set = set()
    placed: list[tuple[int, int, str, str]] = []
    skip = set()
    for index, u in enumerate(units):
        if not isinstance(u, dict):
            refuse("invalid_unit", None, repr(u)[:80])
            continue
        uid = u.get("id")
        skip.add(f"$.units[{index}].source.path")  # judged by the relocatable-path rule
        skip.add(f"$.units[{index}].toolchain.flags")  # compiler switches (e.g. "/O2"), not paths
        if uid in seen_ids:
            refuse("duplicate_unit", uid)
        seen_ids.add(uid)

        source = u.get("source")
        if not isinstance(source, dict):
            refuse("invalid_unit_source", uid, repr(source)[:80])
            source = {}
        path = source.get("path")
        if not _relocatable(path):
            refuse("non_relocatable_path", uid, "source path is absolute, escaping or empty")
        else:
            if path in seen_paths:
                refuse("duplicate_unit_source", uid, path)
            seen_paths.add(path)
            file = root / path
            if not file.is_file():
                refuse("missing_source", uid, path)
            elif _sha256(file.read_bytes()) != source.get("sha256"):
                refuse("stale_source_digest", uid, path)

        if image_ok and u.get("image_sha256") != img["sha256"]:
            refuse("unit_image_mismatch", uid)

        if u.get("provenance") in PROVENANCES:
            counts["provenance"][u["provenance"]] += 1
        else:
            refuse("invalid_provenance", uid, str(u.get("provenance")))

        tool = u.get("toolchain")
        state = tool.get("state") if isinstance(tool, dict) else None
        if state not in TOOLCHAIN_STATES:
            refuse("toolchain_state_missing", uid)
        else:
            counts["toolchain"][state] += 1
            if state == "pinned" and not _is_hex64(tool.get("identity_sha256")):
                refuse("toolchain_identity_invalid", uid)
            if state == "unpinned" and rebuildable is True:
                refuse("unpinned_toolchain_in_rebuildable_project", uid)

        raw_placements = u.get("placements")
        if raw_placements is None:
            raw_placements = []
        elif not isinstance(raw_placements, list):
            refuse("invalid_placements", uid, type(raw_placements).__name__)
            raw_placements = []
        for place in raw_placements:
            if not isinstance(place, dict):
                refuse("invalid_placement", uid, repr(place)[:80])
                continue
            va, size, sym = place.get("va"), place.get("size"), str(place.get("symbol"))
            if not (_is_int(va) and _is_int(size) and size > 0):
                refuse("invalid_placement", uid, sym)
                continue
            counts["placements"] += 1
            counts["placed_bytes"] += size
            if image_ok and (va < base or va + size > base + extent):
                refuse("placement_outside_image", uid, f"{sym} 0x{va:x}+0x{size:x}")
            placed.append((va, size, str(uid), sym))
            counts["relocations"] += _check_relocations(place, uid, refuse)

    placed.sort()
    max_end = None
    max_end_owner = None
    for va, size, uid, sym in placed:
        if max_end is not None and va < max_end:
            refuse("overlapping_placements", uid, f"{sym} 0x{va:x} overlaps {max_end_owner}")
        end = va + size
        if max_end is None or end > max_end:
            max_end = end
            max_end_owner = f"{uid}:{sym}"

    for pointer in _leaks(manifest, "$", skip):
        refuse("absolute_path_leak", None, pointer)

    receipt["counts"] = counts
    return _finish(receipt, refusals)


def _finish(receipt: dict, refusals: list[dict]) -> dict:
    refusals.sort(key=lambda r: (r["reason"], str(r["unit"]), r["detail"]))
    receipt["refusals"] = refusals
    receipt["verdict"] = "refused" if refusals else "accepted"
    return receipt


def receipt_bytes(receipt: dict) -> bytes:
    """Canonical receipt bytes: sorted keys, no timestamps, no host paths."""
    return _canonical(receipt)
