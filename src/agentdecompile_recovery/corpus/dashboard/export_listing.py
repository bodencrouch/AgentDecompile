"""Read-only, scoped access to complete content-addressed export bundles."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
from pathlib import Path, PurePosixPath
from urllib.parse import urlencode

MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_ARTIFACT_BYTES = 32 * 1024 * 1024
MAX_BUNDLE_BYTES = 128 * 1024 * 1024
MAX_ARTIFACTS = 512
MAX_BUNDLES = 128
DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class ExportReadError(ValueError):
    """A requested bundle cannot be read with verified identity."""


def _root() -> Path:
    configured = (os.environ.get("AGENT_DECOMPILE_EXPORT_ROOT") or "").strip()
    if configured:
        return Path(configured).expanduser().absolute()
    from .pages import _work_dir
    work = _work_dir()
    if work is None:
        raise ExportReadError("Export root is unavailable")
    return (work / "exports").absolute()


def _parts(path: str) -> tuple[str, ...]:
    if not isinstance(path, str) or not path or "\\" in path or "\x00" in path:
        raise ExportReadError("Invalid artifact path")
    value = PurePosixPath(path)
    if value.is_absolute() or any(p in (".", "..", "") for p in path.split("/")) or str(value) != path:
        raise ExportReadError("Artifact path must be a canonical relative path")
    return value.parts


def _read(root: Path, relative: str, limit: int) -> bytes:
    """Walk beneath an opened root without following symlinks, including at leaf."""
    parts = _parts(relative)
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        leaf = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            info = os.fstat(leaf)
            if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
                raise ExportReadError("Artifact is not a bounded regular file")
            with os.fdopen(leaf, "rb", closefd=False) as stream:
                data = stream.read(limit + 1)
            if len(data) > limit:
                raise ExportReadError("Artifact exceeds read limit")
            return data
        finally:
            os.close(leaf)
    finally:
        os.close(fd)


def _verified_bundle(root: Path, bundle_id: str) -> tuple[dict, dict[str, bytes], dict]:
    if not isinstance(bundle_id, str) or not DIGEST.fullmatch(bundle_id):
        raise ExportReadError("Invalid bundle identity")
    manifest = json.loads(_read(root, bundle_id + "/bundle.json", MAX_MANIFEST_BYTES))
    if not isinstance(manifest, dict) or manifest.get("format") != "agentdecompile.export-bundle/v1" or manifest.get("status") != "complete":
        raise ExportReadError("Unsupported bundle format")
    basis = manifest.get("basis")
    if not isinstance(basis, dict) or not basis or basis.get("corpus_manifest_hash") != manifest.get("corpus_manifest_hash"):
        raise ExportReadError("Bundle basis is missing or inconsistent")
    if manifest.get("bundle_sha256") != bundle_id:
        raise ExportReadError("Bundle identity does not match its directory")
    content = {k: v for k, v in manifest.items() if k != "bundle_sha256"}
    encoded = (json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n").encode()
    if hashlib.sha256(encoded).hexdigest() != bundle_id:
        raise ExportReadError("Bundle manifest digest mismatch")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not 0 < len(artifacts) <= MAX_ARTIFACTS:
        raise ExportReadError("Bundle artifact inventory is absent or exceeds limits")
    loaded = {}
    total = 0
    pack = readiness = None
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise ExportReadError("Artifact inventory row is not an object")
        path = artifact.get("path")
        _parts(path)
        if path == "bundle.json" or path in loaded:
            raise ExportReadError("Duplicate or self-referencing artifact")
        size = artifact.get("size")
        if type(size) is not int or size < 0 or size > MAX_ARTIFACT_BYTES:
            raise ExportReadError("Artifact size is invalid or exceeds limits")
        total += size
        if total > MAX_BUNDLE_BYTES:
            raise ExportReadError("Bundle exceeds verified-read byte budget")
        data = _read(root, bundle_id + "/" + path, min(MAX_ARTIFACT_BYTES, size))
        if len(data) != size or hashlib.sha256(data).hexdigest() != artifact.get("sha256"):
            raise ExportReadError("Artifact content mismatch: " + path)
        loaded[path] = data
        if path.endswith(".json"):
            value = json.loads(data)
            if isinstance(value, dict) and value.get("format") == "agentdecompile.hookpack/v2":
                if pack is not None:
                    raise ExportReadError("Multiple v2 packs in bundle")
                pack = value
            if isinstance(value, dict) and value.get("format") == "agentdecompile.readiness/v1":
                if readiness is not None:
                    raise ExportReadError("Multiple readiness reports in bundle")
                readiness = value
    if pack is None or readiness is None:
        raise ExportReadError("Bundle is missing required pack or readiness artifacts")
    if pack.get("basis") != basis or pack.get("binaries") != manifest.get("binaries"):
        raise ExportReadError("Pack identity disagrees with bundle manifest")
    roles = {}
    for artifact in artifacts:
        roles.setdefault(artifact.get("role"), []).append(artifact["path"])
    required_roles = {"hookpack-v1", "hookpack-v2", "lua-bindings", "types-header",
                      "types-header-manifest", "readiness", "readiness-human",
                      "divergence", "cave-plans", "operation-contracts", "receipt"}
    if not required_roles <= roles.keys() or len(roles["lua-bindings"]) != 1:
        raise ExportReadError("Bundle is missing required artifact roles")
    from ..divergence_report import build_divergence_report
    if len(roles["divergence"]) != 1:
        raise ExportReadError("Bundle divergence inventory is ambiguous")
    divergence = json.loads(loaded[roles["divergence"][0]])
    if divergence != build_divergence_report(pack) or divergence.get("status") != "complete":
        raise ExportReadError("Bundle divergence evidence is incomplete or inconsistent")
    headers = []
    for name in roles["types-header"]:
        manifest_name = name + ".manifest.json"
        if manifest_name not in roles["types-header-manifest"]:
            raise ExportReadError("Header manifest is missing")
        headers.append({"manifest": json.loads(loaded[manifest_name]), "content": loaded[name]})
    if {h["manifest"].get("build", {}).get("slug") for h in headers} != {b["slug"] for b in pack["binaries"]}:
        raise ExportReadError("Header build coverage is incomplete")
    from ..export_validation import validate_export_set
    validate_export_set(pack, lua_source=loaded[roles["lua-bindings"][0]], headers=headers,
                        readiness=readiness, require_caves=True)
    return manifest, loaded, readiness


def _scope(slug: str, locator: str) -> set[str] | None:
    if not locator:
        return {slug} if slug else None
    from .common import corpus_read_snapshot, CorpusReadError
    try:
        with corpus_read_snapshot() as (connection, _corpus):
            rows = connection.execute("SELECT b.slug FROM binary b JOIN program_binding p ON p.source_path=b.repo_path WHERE p.locator=? ORDER BY b.slug", (locator,)).fetchall()
    except (CorpusReadError, sqlite3.Error) as exc:
        raise ExportReadError("Project export scope unavailable: " + str(exc)) from exc
    bound = {str(row[0]) for row in rows}
    return bound & {slug} if slug else bound


def list_export_bundles(*, slug: str = "", locator: str = "") -> dict:
    result = {"ok": True, "slug": slug, "locator": locator, "bundles": [], "errors": []}
    try:
        allowed = _scope(slug, locator)
        if allowed == set():
            result.update(status="unbound", reason="No corpus build is bound to the selected project and binary")
            return result
        root = _root()
        if not root.exists():
            result.update(status="empty", reason="No published export bundles")
            return result
        candidates = []
        with os.scandir(root) as entries:
            for scanned, entry in enumerate(entries, 1):
                if scanned > 4096:
                    raise ExportReadError("Export root entry count exceeds bounded listing limit")
                if DIGEST.fullmatch(entry.name) and entry.is_dir(follow_symlinks=False):
                    candidates.append(entry.name)
                    if len(candidates) > MAX_BUNDLES:
                        raise ExportReadError("Bundle inventory exceeds bounded listing limit")
        for bundle_id in sorted(candidates):
            try:
                manifest, _loaded, readiness = _verified_bundle(root, bundle_id)
                slugs = {b["slug"] for b in manifest["binaries"]}
                if allowed is not None and not slugs & allowed:
                    continue
                builds = [b for b in readiness["builds"] if allowed is None or b["build"] in allowed]
                entities = [e for e in readiness["entities"] if allowed is None or e["build"] in allowed]
                artifacts = [{**artifact, "href": f"/dashboard/api/workbench/exports/{bundle_id}/download?" + urlencode({"path": artifact["path"]})} for artifact in manifest["artifacts"]]
                result["bundles"].append({"id": bundle_id, "bundle_sha256": bundle_id,
                    "basis": manifest["basis"], "corpus_manifest_hash": manifest["corpus_manifest_hash"],
                    "binaries": [b for b in manifest["binaries"] if allowed is None or b["slug"] in allowed],
                    "artifacts": artifacts, "readiness": {"builds": builds, "entities": entities},
                    "scope_receipts": manifest.get("scope_receipts", []), "verification": "content_hashes_and_pack_cross_references"})
            except (OSError, ValueError, KeyError, TypeError) as exc:
                result["errors"].append({"bundle": bundle_id, "reason": str(exc)})
        result["status"] = "available" if result["bundles"] else "empty"
        return result
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        result.update(ok=False, status="unavailable", reason=str(exc), error=str(exc))
        return result


def read_export_artifact(bundle_id: str, artifact_path: str) -> tuple[bytes, str]:
    """Return only inventoried, digest-rechecked bytes from a complete bundle."""
    _parts(artifact_path)
    _manifest, loaded, _readiness = _verified_bundle(_root(), bundle_id)
    if artifact_path not in loaded:
        raise ExportReadError("Artifact is not present in the verified bundle inventory")
    return loaded[artifact_path], PurePosixPath(artifact_path).name
