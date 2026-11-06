"""Content binding for local comparison observations, not recovery acceptance.

Only producers which observed compilation may bind that observed source. Consumers
must not attach a digest to historical success merely because a file exists now.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping


def bind_source(row: dict, source_bytes: bytes) -> dict:
    """Bind a producer observation to its exact source bytes without upgrading it."""
    return {**row, "sourceSha256": hashlib.sha256(source_bytes).hexdigest(),
            "comparisonScope": "local-function"}


def source_binding(row: Mapping, source_bytes: bytes) -> dict:
    """Check only source freshness; no semantic, target or contribution verdict."""
    digest = row.get("sourceSha256")
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        return {"current": False, "reason": "missing_or_invalid_source_digest"}
    if hashlib.sha256(source_bytes).hexdigest() != digest:
        return {"current": False, "reason": "source_digest_mismatch"}
    return {"current": True, "reason": "source_digest_matches"}


def source_file_binding(row: Mapping) -> dict:
    """Recheck a stored source reference at consumption time; never mutate it.

    Streaming avoids loading entire sources. No mtime cache can upgrade a stale
    observation. This only observes bytes during this read, not future reads.
    """
    from pathlib import Path
    digest = row.get("source_sha256")
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        return {"current": False, "reason": "missing_or_invalid_source_digest"}
    path = row.get("path")
    if not isinstance(path, str) or not path:
        return {"current": False, "reason": "missing_source_path"}
    try:
        with Path(path).open("rb") as stream:
            hasher = hashlib.sha256()
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
            actual = hasher.hexdigest()
    except (OSError, ValueError):
        return {"current": False, "reason": "source_unreadable"}
    if actual != digest:
        return {"current": False, "reason": "source_digest_mismatch"}
    return {"current": True, "reason": "source_digest_matches"}


def target_binding(observation: Mapping, *, expected_path=None,
                   expected_address=None, cache=None) -> dict:
    """Check recorded target bytes against an invocation-pinned file snapshot.

    Without an explicit expected target this checks the recorded target only;
    it supplies no semantic identity verdict. A reused cache is not a fresh disk
    observation. Region address is a checked claim, not independently recomputed
    VA-to-file mapping. Producer metadata is never modified.
    """
    from pathlib import Path
    def refuse(reason):
        return {'current': False, 'reason': reason}
    def valid_digest(value):
        return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None
    if not isinstance(observation, Mapping):
        return refuse('invalid_target_observation')
    snapshot = observation.get('targetSnapshot')
    region = observation.get('targetRegion')
    if not isinstance(snapshot, Mapping) or not isinstance(region, Mapping):
        return refuse('missing_target_snapshot_or_region')
    if (not valid_digest(snapshot.get('sha256')) or not valid_digest(region.get('sha256'))
            or type(snapshot.get('size')) is not int or snapshot['size'] <= 0
            or any(type(region.get(key)) is not int or region[key] < 0 for key in ('address', 'offset'))
            or type(region.get('size')) is not int or region['size'] <= 0
            or not isinstance(snapshot.get('path'), str) or not snapshot['path']):
        return refuse('invalid_target_snapshot_or_region')
    if region['offset'] + region['size'] > snapshot['size']:
        return refuse('target_region_out_of_bounds')
    if expected_address is not None:
        if type(expected_address) is not int or expected_address < 0:
            return refuse('invalid_expected_target_address')
        if region['address'] != expected_address:
            return refuse('target_address_mismatch')
    try:
        path = Path(snapshot['path']).resolve()
        if expected_path is not None and Path(expected_path).resolve() != path:
            return refuse('target_path_mismatch')
    except (OSError, ValueError, TypeError, RuntimeError):
        return refuse('invalid_target_path')
    snapshots = {} if cache is None else cache
    key = ('target-binding-v1', str(path))
    try:
        if key not in snapshots:
            raw = path.read_bytes()
            snapshots[key] = (raw, hashlib.sha256(raw).hexdigest())
        raw, digest = snapshots[key]
    except (OSError, ValueError, TypeError):
        return refuse('target_unreadable')
    if len(raw) != snapshot['size'] or digest != snapshot['sha256']:
        return refuse('target_snapshot_mismatch')
    piece = raw[region['offset']:region['offset'] + region['size']]
    if hashlib.sha256(piece).hexdigest() != region['sha256']:
        return refuse('target_region_mismatch')
    return {'current': True, 'reason': 'target_snapshot_and_region_match',
            'scope': 'invocation-pinned-target-bytes',
            'semanticIdentityVerified': False, 'addressMappingVerified': False,
            'capturedTarget': {'path': str(path), 'sha256': digest, 'size': len(raw)}}
