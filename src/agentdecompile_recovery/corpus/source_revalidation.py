"""Explicit offline fresh compilation after process loss; JSON never restores trust.

The recipe is a bounded request, not a receipt. Only the returned live observation
can enter acceptance. A fresh private workspace contains all generated outputs.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess

from . import matching_status
from . import source_contribution as sc

SCHEMA = "agentdecompile.source-revalidation/v1"
MAX_RECIPE_BYTES = 256 * 1024
MAX_CANDIDATES = 32
MAX_SOURCE_BYTES = 1024 * 1024
MAX_TARGET_BYTES = 128 * 1024 * 1024
MAX_DATABASE_BYTES = 256 * 1024 * 1024
MAX_FUNCTIONS = 100_000


@dataclass(frozen=True)
class RevalidationResult:
    """Keep process-local authority separate from the JSON-safe diagnostic."""
    observation: sc.ReconstructionObservation
    diagnostic: dict


def _keys(value, expected):
    if type(value) is not dict or set(value) != set(expected):
        raise ValueError("unsupported_recipe_fields")


def _path(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 4096 or "\0" in value:
        raise ValueError("invalid_recipe_path")
    path = Path(value)
    if not path.is_absolute() or str(path.resolve()) != value:
        raise ValueError("recipe_path_must_be_canonical_absolute")
    return path


def _sha(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("invalid_recipe_digest")


def _bounded_file(path, limit):
    # Nonblocking open prevents a substituted FIFO from hanging the coordinator.
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError("input_not_regular_or_too_large")
        raw = handle.read(limit + 1)
        if len(raw) > limit:
            raise ValueError("input_too_large")
        return raw


def _bound(path, expected, limit):
    if hashlib.sha256(_bounded_file(path, limit)).hexdigest() != expected:
        raise ValueError("bound_digest_mismatch")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_recipe_key")
        result[key] = value
    return result


def _recipe(raw):
    if type(raw) is not bytes or len(raw) > MAX_RECIPE_BYTES:
        raise ValueError("recipe_must_be_bounded_json_bytes")
    try:
        doc = json.loads(raw, object_pairs_hook=_pairs)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("malformed_recipe") from exc
    _keys(doc, ("schema", "target", "db", "binaryId", "selection", "candidates"))
    if doc["schema"] != SCHEMA or doc["selection"] != "explicit-independent-v1":
        raise ValueError("unsupported_recipe_schema_or_selection")
    _keys(doc["target"], ("path", "sha256"))
    _path(doc["target"]["path"]); _sha(doc["target"]["sha256"])
    _path(doc["db"])
    # Existing producer DB helpers form SQLite URIs from the path directly.
    if any(char in doc["db"] for char in ("?", "#", "%")):
        raise ValueError("unsupported_database_uri_delimiter")
    if type(doc["binaryId"]) is not int or not 0 <= doc["binaryId"] <= 2**63 - 1:
        raise ValueError("invalid_binary_id")
    candidates = doc["candidates"]
    if type(candidates) is not list or len(candidates) > MAX_CANDIDATES:
        raise ValueError("invalid_candidate_count")
    ids = set()
    for row in candidates:
        _keys(row, ("id", "source", "sha256", "address", "size", "program", "name", "selected"))
        for key in ("id", "program", "name"):
            if not isinstance(row[key], str) or not 1 <= len(row[key]) <= 256:
                raise ValueError("invalid_candidate_identity")
        if row["id"] in ids:
            raise ValueError("duplicate_candidate_id")
        ids.add(row["id"])
        _path(row["source"]); _sha(row["sha256"])
        if (type(row["address"]) is not int or not 0 <= row["address"] <= 2**63 - 1
                or type(row["size"]) is not int or not 1 <= row["size"] <= MAX_SOURCE_BYTES
                or type(row["selected"]) is not bool):
            raise ValueError("invalid_candidate_region_or_selection")
    return doc


def revalidate(*, recipe: bytes, target, db, binary_id: int, workspace) -> RevalidationResult:
    """Request one bounded fresh batch and consume it in matching-status now.

    ``workspace`` must name a nonexistent directory under an existing parent.
    No imported compiler, argv, object, invocation, writer or acceptance fields
    are supported. Selected candidates execute sequentially in stable ID order.
    """
    doc = _recipe(recipe)
    target_path, db_path = Path(target).resolve(strict=True), Path(db).resolve(strict=True)
    if (str(target_path) != doc["target"]["path"] or str(db_path) != doc["db"]
            or type(binary_id) is not int or binary_id != doc["binaryId"]):
        raise ValueError("required_target_database_or_binary_mismatch")
    _bound(target_path, doc["target"]["sha256"], MAX_TARGET_BYTES)
    _bounded_file(db_path, MAX_DATABASE_BYTES)
    with sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True) as connection:
        connection.set_progress_handler(lambda: 1, 1_000_000)
        count = connection.execute("SELECT count(*) FROM func WHERE binary_id=?", (binary_id,)).fetchone()[0]
        if count > MAX_FUNCTIONS:
            raise ValueError("selected_database_too_many_functions")
    root = Path(workspace)
    if not root.is_absolute() or root.parent.resolve(strict=True) != root.parent:
        raise ValueError("workspace_must_have_canonical_existing_parent")
    root.mkdir(mode=0o700)  # Exclusive creation refuses old output/workspaces and symlinks.
    source_index = root / "source-index"
    source_index.mkdir()
    observations = []
    attempts = []
    for row in sorted(doc["candidates"], key=lambda item: item["id"]):
        attempt = {"id": row["id"], "address": row["address"], "state": "rejected",
                   "source": row["source"], "requestedSourceSha256": row["sha256"]}
        attempts.append(attempt)
        if not row["selected"]:
            attempt["reason"] = "intentionally_discarded"
            continue
        try:
            _bound(target_path, doc["target"]["sha256"], MAX_TARGET_BYTES)
            observed = hashlib.sha256(_bounded_file(row["source"], MAX_SOURCE_BYTES)).hexdigest()
            attempt["observedSourceSha256"] = observed
            if observed != row["sha256"]:
                raise ValueError("bound_digest_mismatch")
            sc._db_row(db_path, binary_id, row["address"], row["size"],
                       target_sha256=doc["target"]["sha256"])
            obs = sc.compile_observation(source=row["source"], target=target_path,
                address=row["address"], size=row["size"], workspace=root,
                program=row["program"], name=row["name"], binary_id=binary_id, db=db_path)
            # Recheck the recipe, not just the producer's later input snapshot.
            _bound(row["source"], row["sha256"], MAX_SOURCE_BYTES)
            _bound(target_path, doc["target"]["sha256"], MAX_TARGET_BYTES)
            if obs.record["source"]["sha256"] != row["sha256"] or obs.record["target"]["sha256"] != doc["target"]["sha256"]:
                raise ValueError("producer_recipe_binding_changed")
            observations.append(obs)
            attempt.update(state="freshly-produced", invocation=obs.record["invocation"],
                           object=obs.record["object"], audit=obs.record)
        except (OSError, ValueError, UnicodeError, sqlite3.Error, subprocess.SubprocessError) as exc:
            attempt["reason"] = str(exc)
    _bound(target_path, doc["target"]["sha256"], MAX_TARGET_BYTES)
    output = root / "revalidated.exe"
    image = sc.reconstruct(target=target_path, output=output, observations=observations)
    manifest = root / "matching-status.json"
    matching_status.main(["--target", str(target_path), "--db", str(db_path),
        "--binary-id", str(binary_id), "--src-dir", str(source_index),
        "--out-manifest", str(manifest)], reconstruction_observation=image)
    diagnostic = {"schema": SCHEMA, "evidenceState": "fresh-process-local-observation",
        "recipeSha256": hashlib.sha256(recipe).hexdigest(), "workspace": str(root),
        "output": str(output), "candidates": attempts,
        "matchingStatus": json.loads(manifest.read_bytes()), "reconstruction": image.record}
    (root / "revalidation.json").write_bytes(sc.canonical(diagnostic))
    return RevalidationResult(image, diagnostic)
