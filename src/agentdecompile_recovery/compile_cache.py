"""Compile/objdiff artifact cache keyed by target slice digest and compiler profile."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from functools import lru_cache
from pathlib import Path
from typing import Any

SCHEMA = "agentdecompile.compile-cache-entry.v1"
DIAGNOSTIC_SCHEMA = "agentdecompile.compile-diagnostic-cache.v1"
TOOLCHAIN_IDENTITY_SCHEMA = "agentdecompile.source-synthesis-cache-profile.v2"
MAX_TOOLCHAIN_FILES = 16
MAX_TOOLCHAIN_FILE_BYTES = 256 * 1024 * 1024
MAX_TOOLCHAIN_TOTAL_BYTES = 1024 * 1024 * 1024


@lru_cache(maxsize=128)
def _cached_file_digest(
    path: str,
    device: int,
    inode: int,
    size: int,
    mtime_ns: int,
    ctime_ns: int,
) -> str | None:
    """Hash one bounded, resolved regular-file input; stat changes invalidate it."""
    try:
        before = os.stat(path, follow_symlinks=True)
        expected = (device, inode, size, mtime_ns, ctime_ns)
        actual = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
        if actual != expected or not stat.S_ISREG(before.st_mode) or size > MAX_TOOLCHAIN_FILE_BYTES:
            return None
        digest = hashlib.sha256()
        read = 0
        with open(path, "rb") as stream:
            while True:
                chunk = stream.read(min(1024 * 1024, MAX_TOOLCHAIN_FILE_BYTES + 1 - read))
                if not chunk:
                    break
                read += len(chunk)
                if read > MAX_TOOLCHAIN_FILE_BYTES:
                    return None
                digest.update(chunk)
            after = os.fstat(stream.fileno())
        final = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        return digest.hexdigest() if final == expected and read == size else None
    except OSError:
        return None


def bounded_file_identity(path: Path) -> dict[str, Any] | None:
    """Return a content identity for a resolved tool input, or fail closed."""
    try:
        resolved = path.expanduser().resolve(strict=True)
        info = resolved.stat()
    except (OSError, RuntimeError):
        return None
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_TOOLCHAIN_FILE_BYTES:
        return None
    digest = _cached_file_digest(
        str(resolved), info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns
    )
    if digest is None:
        return None
    return {"path": str(resolved), "size": info.st_size, "sha256": digest}


def advisory_toolchain_identity(
    *,
    files: dict[str, Path | None],
    settings: dict[str, Any],
    environment: dict[str, str],
) -> str | None:
    """Build a bounded reuse key; deliberately not a complete provenance receipt.

    `None` entries represent tools known to be absent. Required tool paths must
    be supplied as Paths and hash successfully. Environment values are never
    serialized, only SHA-256 digests of an explicit caller-selected allowlist.
    """
    if len(files) > MAX_TOOLCHAIN_FILES:
        return None
    identities: dict[str, Any] = {}
    total = 0
    for label, path in sorted(files.items()):
        if path is None:
            identities[label] = {"available": False}
            continue
        identity = bounded_file_identity(path)
        if identity is None:
            return None
        total += int(identity["size"])
        if total > MAX_TOOLCHAIN_TOTAL_BYTES:
            return None
        identities[label] = {"available": True, **identity}
    env_digests = {
        key: hashlib.sha256(value.encode("utf-8", errors="surrogatepass")).hexdigest()
        for key, value in sorted(environment.items())
    }
    material = {
        "schema": TOOLCHAIN_IDENTITY_SCHEMA,
        "claim": "bounded advisory cache identity only; not complete toolchain provenance or full-image proof",
        "files": identities,
        "settings": settings,
        "environmentDigests": env_digests,
    }
    return json.dumps(material, sort_keys=True, separators=(",", ":"))


def source_has_bounded_compile_inputs(source: str, flags: list[str]) -> bool:
    """Allow reuse only when preprocessing is self-contained and deterministic.

    Local macro/conditional directives are part of the hashed source and are
    safe to reuse. Directives that can read additional files or change compiler
    state are rejected, as are flags that inject untracked inputs.
    """
    if any(token in source for token in ("__FILE__", "__DATE__", "__TIME__", "__TIMESTAMP__", "__COUNTER__")):
        return False
    # Exclude #if/#elif because implementations such as __has_include can
    # inspect filesystem state without an include directive appearing.
    local_directives = {"define", "undef", "ifdef", "ifndef", "else", "endif"}
    for line in source.splitlines():
        stripped = line.lstrip()
        if not stripped.startswith(("#", "%:")) and not stripped.startswith("??="):
            continue
        directive = re.match(r"(?:#|%:|\?\?=)\s*([A-Za-z_][A-Za-z0-9_]*)\b", stripped)
        if directive is None or directive.group(1) not in local_directives:
            return False
    normalized = [flag.casefold() for flag in flags]
    return not any(
        flag.startswith(("/fi", "/yu", "/yc", "-include", "-include-pch", "-imacros", "-fmodule-file", "/reference", "/module:reference", "/ifcsearchdir", "@", "--config"))
        or (flag.startswith("/fp") and not flag.startswith("/fp:"))
        for flag in normalized
    )


def has_stable_compile_objdiff_result(records: list[dict[str, Any]]) -> bool:
    """Allow cache persistence only for completed, explicit compiler+objdiff rows."""
    if not records:
        return False
    for record in records:
        if not isinstance(record, dict) or record.get("status") not in {
            "matched", "mismatched", "code-slice-matched"
        }:
            return False
        if record.get("objdiffExit") != 0 or record.get("fallback") or record.get("diagnosticFallback"):
            return False
        differences = record.get("differences")
        if not isinstance(differences, int) or differences < 0:
            return False
        if record.get("status") in {"matched", "code-slice-matched"} and differences != 0:
            return False
        if record.get("status") == "mismatched" and differences == 0:
            return False
        target_compile = record.get("targetCompile")
        candidate_compile = record.get("candidateCompile")
        if not isinstance(target_compile, dict) or target_compile.get("status") != "ok":
            return False
        if not isinstance(candidate_compile, dict) or candidate_compile.get("status") != "ok":
            return False
    return True


def is_deterministic_compiler_diagnostic(result: dict[str, Any], text: str) -> bool:
    """Cache only a compiler-invoked, explicit C/C++/ASM diagnostic."""
    if result.get("status") == "ok" or result.get("compilerInvoked") is not True:
        return False
    return_code = result.get("returnCode")
    if not isinstance(return_code, int) or return_code <= 0 or return_code == 124:
        return False
    lowered = text.casefold()
    if any(marker in lowered for marker in ("timed out", "timeout", "failed to start", "could not start", "wine: ", "err:", "not found")):
        return False
    import re

    return re.search(r"\b(?:fatal\s+)?error\s+[CA]\d{4}\s*:", text, re.IGNORECASE) is not None


def cache_dir(work_dir: Path) -> Path:
    return work_dir.resolve() / "source-synthesis" / "compile-cache"


def cache_key(
    *,
    target_slice_sha: str,
    source_sha: str,
    compiler_profile: str,
    compiler_lane: str = "c",
    flags: str = "",
    toolchain_identity: str = "",
) -> str:
    material = "|".join(
        [
            target_slice_sha or "",
            source_sha or "",
            compiler_profile or "default",
            compiler_lane or "c",
            flags or "",
            toolchain_identity or "",
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def entry_path(cache_root: Path, key: str) -> Path:
    return cache_root / f"{key}.json"


def diagnostic_key(*, source_sha: str, compiler: str, flags: list[str], toolchain: str = "") -> str:
    """Stable key for a compiler result; target bytes are intentionally excluded."""
    material = json.dumps([source_sha, compiler, flags, toolchain], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def diagnostic_lookup(cache_root: Path, key: str) -> dict[str, Any] | None:
    path = cache_root / f"diagnostic-{key}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    return (
        data
        if isinstance(data, dict)
        and data.get("schema") == DIAGNOSTIC_SCHEMA
        and data.get("cacheKey") == key
        else None
    )


def diagnostic_store(cache_root: Path, key: str, result: dict[str, Any]) -> Path:
    cache_root.mkdir(parents=True, exist_ok=True)
    path = cache_root / f"diagnostic-{key}.json"
    path.write_text(json.dumps({"schema": DIAGNOSTIC_SCHEMA, "cacheKey": key, "result": result}, sort_keys=True) + "\n", encoding="utf-8")
    return path


def lookup(cache_root: Path, key: str) -> dict[str, Any] | None:
    path = entry_path(cache_root, key)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("schema") != SCHEMA or data.get("cacheKey") != key:
        return None
    records = data.get("records")
    if not isinstance(records, list):
        return None
    return data


def store(
    cache_root: Path,
    key: str,
    *,
    records: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
) -> Path:
    cache_root.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": SCHEMA,
        "cacheKey": key,
        "records": records,
        "metadata": metadata or {},
    }
    path = entry_path(cache_root, key)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def target_slice_sha256(row: dict[str, Any]) -> str:
    target_slice = row.get("targetSlice") if isinstance(row.get("targetSlice"), dict) else {}
    for key in ("sha256", "targetSha256", "bodySha256"):
        value = target_slice.get(key) or row.get(key)
        if value:
            return str(value)
    body = target_slice.get("bytes") or row.get("bytes") or row.get("bodyBytes")
    if body is None:
        return ""
    if isinstance(body, str):
        try:
            body_bytes = bytes.fromhex(body.replace(" ", ""))
        except ValueError:
            body_bytes = body.encode("utf-8", errors="replace")
    elif isinstance(body, (bytes, bytearray)):
        body_bytes = bytes(body)
    else:
        body_bytes = str(body).encode("utf-8", errors="replace")
    return hashlib.sha256(body_bytes).hexdigest()
