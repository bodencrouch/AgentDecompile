"""Shared export-consistency gates for bundle publication and UI consumers.

These gates establish artifact identity and cross-reference consistency only.
They cannot manufacture runtime acceptance or qualify an evidence producer.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .hookpack_v2 import FORMAT, STATUSES, canonical_bytes, read_hookpack
from .determinism_basis import BASIS_HASH_EXCLUDED, _without


class ExportValidationError(ValueError):
    """An export set is incomplete, inconsistent, or has an unmet gate."""


def _require(condition, reason):
    if not condition:
        raise ExportValidationError(reason)


def _digest(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _load(value):
    return value if isinstance(value, dict) else json.loads(Path(value).read_text(encoding="utf-8"))


def validate_export_set(pack, *, lua_source=None, headers=(), readiness=None,
                        require_caves=False) -> dict:
    """Validate provided artifacts and return an identity-only verification receipt.

    ``headers`` contains {manifest: dict, content: bytes} records. A provided Lua
    source must be byte-identical to the default-threshold deterministic renderer.
    Omitted optional inputs are not silently marked verified. Bundle publishers
    must separately require their complete artifact set.
    """
    try:
        original = _load(pack)
        _require(isinstance(original, dict) and original.get("format") == FORMAT, "v2_pack_required")
        _require(_digest(original.get("pack_sha256")), "pack_digest_required")
        value = read_hookpack(original)
        declared = original.get("basis")
        _require(isinstance(declared, dict) and bool(declared), "basis_required")
        _require(_digest(original.get("corpus_manifest_hash")), "corpus_manifest_digest_required")
        _require(declared.get("corpus_manifest_hash") == original["corpus_manifest_hash"], "corpus_manifest_basis_mismatch")
        builds = {b["slug"]: b for b in original["binaries"]}
        for slug, binary in builds.items():
            _require(_digest(binary.get("content_sha256") or binary.get("sha256")), "build_digest_required:" + slug)
        checked = ["pack"]
        for entity in value["entities"]:
            for field_build in entity.get("shape", {}).get("fields", {}):
                _require(field_build in builds, "field_build_unknown:" + entity["key"])
            for instance in entity.get("instances", []):
                abi = instance.get("abi")
                if abi is not None:
                    confidence = abi.get("confidence")
                    _require(type(confidence) in (int, float) and 0 <= confidence <= 1, "invalid_abi_confidence:" + entity["key"])
                _require(instance["status"] == entity["status"][instance["build"]], "instance_rollup_mismatch:" + entity["key"])
        for cave in original.get("caves", []):
            slug = cave.get("build")
            _require(slug in builds, "cave_build_unknown")
            claim = cave.get("claim", {})
            _require(claim.get("build_sha256") == (builds[slug].get("content_sha256") or builds[slug].get("sha256")), "cave_build_identity_mismatch")
            _require(claim.get("cave_id") == cave.get("id") and bool(cave.get("id")), "cave_claim_identity_mismatch")
            capacity = cave.get("capacity")
            _require(type(capacity) is int and capacity > 0, "cave_capacity_invalid")
            encoded = bytes.fromhex(cave.get("original_bytes", ""))
            _require(len(encoded) == capacity, "cave_original_bytes_incomplete")
            restoration = cave.get("restoration", {})
            _require(restoration.get("original_bytes") == cave["original_bytes"] and restoration.get("verify_before_install") is True and restoration.get("verify_after_restore") is True and restoration.get("release_requires_quiescence") is True, "cave_restoration_incomplete")
            _require(cave.get("live_allocation_allowed") is False, "static_cave_cannot_authorize_live_allocation")
            for coverage in cave.get("coverage", []):
                _require(coverage.get("build") in builds and coverage.get("status") in STATUSES, "cave_coverage_invalid")
        if require_caves:
            receipts = original.get("cave_discovery", [])
            _require(isinstance(receipts, list), "cave_discovery_receipts_required")
            by_build = {r.get("build"): r for r in receipts}
            _require(len(by_build) == len(receipts) and set(by_build) == set(builds), "cave_discovery_build_coverage_incomplete")
            for slug, receipt in sorted(by_build.items()):
                _require(receipt.get("status") == "complete", "cave_discovery_blocked:" + slug + ":" + str(receipt.get("reason", "missing_evidence")))
                _require(_digest(receipt.get("evidence_sha256")) and receipt.get("image_sha256") == (builds[slug].get("content_sha256") or builds[slug].get("sha256")), "cave_discovery_evidence_required:" + slug)
            checked.append("cave_discovery_receipt_identity")
        if lua_source is not None:
            from .export_lua_bindings import render_lua_bindings
            supplied = lua_source.encode("utf-8") if isinstance(lua_source, str) else lua_source
            _require(isinstance(supplied, bytes), "lua_bytes_required")
            _require(supplied == render_lua_bindings(original).encode("utf-8"), "lua_pack_cross_reference_or_content_mismatch")
            checked.append("lua")
        seen_headers = set()
        for header in headers:
            manifest, content = header["manifest"], header["content"]
            _require(isinstance(content, bytes), "header_bytes_required")
            _require(manifest.get("format") == "agentdecompile.types-header/v1", "header_format_unknown")
            identity = manifest.get("build", {})
            slug = identity.get("slug")
            _require(slug in builds and slug not in seen_headers, "header_build_unknown_or_duplicate")
            seen_headers.add(slug)
            _require(identity.get("content_sha256") == (builds[slug].get("content_sha256") or builds[slug].get("sha256")), "header_build_identity_mismatch")
            _require(manifest.get("basis") == declared, "header_basis_mismatch")
            basis_bytes = json.dumps(_without(declared, BASIS_HASH_EXCLUDED), sort_keys=True, separators=(",", ":")).encode()
            _require(manifest.get("basis_hash") == hashlib.sha256(basis_bytes).hexdigest(), "header_basis_hash_mismatch")
            artifact = manifest.get("artifact", {})
            _require(artifact.get("sha256") == hashlib.sha256(content).hexdigest() and artifact.get("bytes") == len(content), "header_artifact_mismatch")
            _require(manifest.get("toolchain", {}).get("identity_hash") == declared.get("toolchain_identity_hash"), "header_toolchain_mismatch")
            text = content.decode("utf-8")
            from .build_types_header import SIZECHECK_RE
            layout = manifest.get("layout", {})
            _require(layout.get("packing") == 1 and "#pragma pack(push, 1)" in text and "#pragma pack(pop)" in text, "header_packing_missing")
            _require(type(layout.get("size_assertions")) is int and layout["size_assertions"] == len(SIZECHECK_RE.findall(text)), "header_size_assertions_mismatch")
            checked.append("header:" + slug)
        if readiness is not None:
            from .readiness_report import build_readiness_report
            _require(_load(readiness) == build_readiness_report(original), "readiness_pack_cross_reference_mismatch")
            checked.append("readiness")
        return {"format": "agentdecompile.export-validation/v1", "pack_sha256": original["pack_sha256"],
                "basis_sha256": hashlib.sha256(canonical_bytes(declared)).hexdigest(),
                "checked": checked, "scope": "artifact_identity_and_cross_reference_consistency",
                "runtime_verification": "not_run"}
    except ExportValidationError:
        raise
    except (ValueError, KeyError, TypeError, AttributeError, OSError) as exc:
        raise ExportValidationError("invalid_export_set:" + str(exc)) from exc
