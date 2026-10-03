"""Publish only complete, validated, content-addressed export trees.

All required exporters must pass. In particular, a missing decode/cave producer
or function divergence basis blocks publication rather than becoming an optional
artifact. Recovered source variants belong to the separate recovery program and
receive an explicit not_in_scope receipt. WASM pack/bindings/harness delivery is
unscoped: browser compute donation and local-analysis WASM do not qualify it.

A bundle's directory name is SHA-256 of canonical bundle.json without its own
bundle_sha256 field. Canonical JSON uses sorted keys, compact separators, ASCII
escaping, no NaN, and a trailing newline. Every listed artifact has a byte digest
and size; consumers verify both before use. A complete export is not live-game,
source-parity, compilation, or detour acceptance.
"""
from __future__ import annotations

import hashlib
import errno
import json
import os
from pathlib import Path
import shutil
import tempfile

from .hookpack_v2 import build_hookpack_v2, canonical_bytes

FORMAT = "agentdecompile.export-bundle/v1"


class BundleExportError(ValueError):
    """A named required prerequisite or artifact validation failed."""


def _json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))


def bundle_identity(manifest: dict) -> str:
    value = dict(manifest)
    value.pop("bundle_sha256", None)
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def verify_bundle(directory: Path | str) -> dict:
    """Verify a closed artifact inventory and refuse symlinks or path escapes."""
    root = Path(directory)
    manifest_path = root / "bundle.json"
    if root.is_symlink() or manifest_path.is_symlink():
        raise BundleExportError("bundle_symlink_refused")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format") != FORMAT or manifest.get("bundle_sha256") != bundle_identity(manifest):
        raise BundleExportError("bundle_manifest_identity_mismatch")
    expected = {"bundle.json"}
    for artifact in manifest.get("artifacts", []):
        name = artifact.get("path")
        if not isinstance(name, str):
            raise BundleExportError("artifact_path_missing")
        relative = Path(name)
        if relative.is_absolute() or not relative.parts or any(p in (".", "..") for p in relative.parts) or name in expected:
            raise BundleExportError("artifact_path_invalid_or_duplicate")
        path = root / relative
        if any(parent.is_symlink() for parent in (path, *path.parents) if parent != root.parent):
            raise BundleExportError("artifact_symlink_refused")
        payload = path.read_bytes()
        if len(payload) != artifact.get("size") or hashlib.sha256(payload).hexdigest() != artifact.get("sha256"):
            raise BundleExportError("artifact_digest_mismatch:" + name)
        expected.add(name)
    actual = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise BundleExportError("artifact_symlink_refused")
        if path.is_file():
            actual.add(path.relative_to(root).as_posix())
    if expected != actual:
        raise BundleExportError("bundle_inventory_mismatch")
    return manifest


def export_bundle(con, out: Path | str, *, site_policy=None, adapter_map=None,
                  operation_contract=None, cave_evidence=None,
                  verify_cave_receipt=None) -> dict:
    """Run required exporters in a private staging tree, then publish once.

    ``out`` is the export-store root. A SQLite savepoint keeps all store reads on
    the same snapshot and preserves any transaction owned by the caller.
    """
    from .build_types_header import build_header
    from .divergence_report import build_divergence_report
    from .export_hookpack import export_hookpack
    from .export_lua_bindings import render_lua_bindings
    from .export_validation import validate_export_set
    from .readiness_report import build_readiness_report, render_readiness_report

    staging = None
    snapshot_open = True
    con.execute("SAVEPOINT agentdecompile_export_bundle")
    try:
        # v1 independently binds operation contracts. The v2 reader currently
        # refuses a v1 binding; never smuggle it into v2 as a qualified operation.
        pack = build_hookpack_v2(con, site_policy=site_policy, adapter_map=adapter_map,
                                 cave_evidence=cave_evidence,
                                 verify_cave_receipt=verify_cave_receipt)
        try:
            validate_export_set(pack, require_caves=True,
                                verify_cave_receipt=verify_cave_receipt)
        except ValueError as exc:
            raise BundleExportError("hookpack/caves: " + str(exc)) from exc
        divergence = build_divergence_report(pack)
        if divergence["status"] != "complete":
            reasons = sorted({r["reason"] for r in divergence["pairs"] if r["status"] == "blocked"})
            raise BundleExportError("divergence: " + "; ".join(reasons))
        lua = render_lua_bindings(pack)
        readiness = build_readiness_report(pack)
        validate_export_set(pack, lua_source=lua, readiness=readiness, require_caves=True,
                            verify_cave_receipt=verify_cave_receipt)
        rows = con.execute("SELECT id,slug,content_sha256 FROM binary ORDER BY content_sha256,slug").fetchall()
        if not rows:
            raise BundleExportError("headers: no builds")
        hashes = [row["content_sha256"] for row in rows]
        if len(set(hashes)) != len(hashes):
            raise BundleExportError("headers: duplicate build content hashes require canonicalization")
        for row in rows:
            try:
                count = con.execute("SELECT COUNT(*) FROM ghidra_type WHERE binary_id=? AND definition IS NOT NULL AND definition<>''", (row["id"],)).fetchone()[0]
            except Exception as exc:
                raise BundleExportError("headers: captured type definitions unavailable") from exc
            if not count:
                raise BundleExportError("headers: no captured type definitions for " + row["slug"])
        root = Path(out)
        root.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".bundle-", dir=root))
        roles = {}
        def put(name, value, role):
            _json(staging / name, value)
            roles[name] = role
        # Fixed exporter order, independent of the caller's dictionary order.
        export_hookpack(con, staging / "hookpack-v1.json", site_policy=site_policy,
                        adapter_map=adapter_map, operation_contract=operation_contract, format="v1")
        v1 = json.loads((staging / "hookpack-v1.json").read_text(encoding="utf-8"))
        if v1.get("format") != "agentdecompile.hookpack/v1" or v1.get("basis") != pack["basis"]:
            raise BundleExportError("hookpack-v1: format or basis mismatch")
        roles["hookpack-v1.json"] = "hookpack-v1"
        put("hookpack-v2.json", pack, "hookpack-v2")
        (staging / "bindings.lua").write_bytes(lua.encode("utf-8"))
        roles["bindings.lua"] = "lua-bindings"
        headers = []
        for row in rows:
            name = "headers/" + row["content_sha256"] + "/types.h"
            receipt = build_header(con, row["id"], staging / name, program=row["slug"])
            metadata = json.loads(Path(receipt["manifest"]).read_text(encoding="utf-8"))
            headers.append({"manifest": metadata, "content": (staging / name).read_bytes()})
            roles[name] = "types-header"
            roles[name + ".manifest.json"] = "types-header-manifest"
        validate_export_set(pack, lua_source=lua, headers=headers, readiness=readiness, require_caves=True,
                            verify_cave_receipt=verify_cave_receipt)
        put("readiness.json", readiness, "readiness")
        (staging / "readiness.md").write_bytes(render_readiness_report(readiness).encode("utf-8"))
        roles["readiness.md"] = "readiness-human"
        put("divergence.json", divergence, "divergence")
        put("caves.json", {"format": "agentdecompile.cave-plans/v1", "basis": pack["basis"],
            "caves": pack.get("caves", []), "discovery": pack.get("cave_discovery", []),
            "live_allocation_allowed": False}, "cave-plans")
        put("operations.json", {"format": "agentdecompile.bound-operations/v1",
            "operations": v1.get("operations", []), "basis": pack["basis"],
            "status": "declared" if v1.get("operations") else "no_declared_operations",
            "runtime_verification": "not_run"}, "operation-contracts")
        # Receipts bind each exporter artifact to the immutable input pack and
        # basis. Receipt files themselves are then hashed by the bundle manifest.
        for name in sorted(roles):
            payload = (staging / name).read_bytes()
            artifact_hash = hashlib.sha256(payload).hexdigest()
            inputs = {"basis": pack["basis"], "pack_sha256": pack["pack_sha256"],
                      "artifact": name, "artifact_sha256": artifact_hash}
            receipt_key = hashlib.sha256(canonical_bytes(inputs)).hexdigest()
            put("receipts/" + receipt_key + ".json", {"format": "agentdecompile.export-receipt/v1",
                "receipt_key": receipt_key, "inputs": inputs, "validation": "artifact_consistency",
                "runtime_verification": "not_run"}, "receipt")
        artifacts = []
        for name in sorted(roles):
            payload = (staging / name).read_bytes()
            artifacts.append({"path": name, "sha256": hashlib.sha256(payload).hexdigest(),
                              "size": len(payload), "role": roles[name]})
        manifest = {"format": FORMAT, "status": "complete", "basis": pack["basis"],
            "corpus_manifest_hash": pack["corpus_manifest_hash"], "binaries": pack["binaries"],
            "artifacts": artifacts, "scope_receipts": [
                {"artifact": "recovered-source-variants", "status": "not_in_scope",
                 "reason": "Byte-accurate and max-C source recovery have separate acceptance gates."},
                {"artifact": "wasm", "status": "not_in_scope",
                 "reason": "WASM-consumable pack, bindings and game harness are unscoped; browser compute providers do not establish this capability."}]}
        manifest["bundle_sha256"] = bundle_identity(manifest)
        _json(staging / "bundle.json", manifest)
        verify_bundle(staging)
        # Flush every private artifact before the atomic directory publication.
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                with path.open("rb") as stream:
                    os.fsync(stream.fileno())
        con.execute("RELEASE SAVEPOINT agentdecompile_export_bundle")
        snapshot_open = False
        destination = root / manifest["bundle_sha256"]
        cache_hit = destination.exists()
        if cache_hit:
            if verify_bundle(destination) != manifest:
                raise BundleExportError("existing_bundle_does_not_match")
        else:
            try:
                os.rename(staging, destination)
                staging = None
            except OSError as exc:
                if exc.errno not in (errno.EEXIST, errno.ENOTEMPTY):
                    raise
                if verify_bundle(destination) != manifest:
                    raise BundleExportError("concurrent_bundle_does_not_match")
                cache_hit = True
        return {"status": "complete", "wrote": str(destination), "manifest": str(destination / "bundle.json"),
                "bundle_sha256": manifest["bundle_sha256"], "artifacts": len(artifacts), "cache_hit": cache_hit}
    except Exception:
        if snapshot_open:
            con.execute("ROLLBACK TO SAVEPOINT agentdecompile_export_bundle")
            con.execute("RELEASE SAVEPOINT agentdecompile_export_bundle")
        raise
    finally:
        if staging is not None:
            shutil.rmtree(staging)
