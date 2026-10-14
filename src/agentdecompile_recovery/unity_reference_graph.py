"""Deterministic, resumable export of Unity serialized-file PPtr references.

This module inventories serialized references only. It never dereferences a
PPtr, exports an asset, or asks UnityPy to decode texture pixels. UnityPy is
optional and is imported only when :func:`export_reference_graph` is called.
"""

from __future__ import annotations

import gc
import hashlib
import json
import os
import sqlite3
import tempfile

from collections.abc import Iterable
from pathlib import Path
from typing import Any

SCHEMA = "agentdecompile.unity-reference-graph.v2"
CHECKPOINT_SCHEMA = "agentdecompile.unity-reference-graph-checkpoint.v3"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(_json_bytes(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _atomic_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            for row in rows:
                stream.write(_json_bytes(row))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _source_identity(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path.resolve(strict=True)),
        "name": path.name,
        "sizeBytes": stat.st_size,
        "sha256": _sha256(path),
    }


def _plain(value: Any) -> Any:
    """Convert UnityPy scalar wrappers to JSON values without resolving them."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return value.hex()
    if hasattr(value, "hex") and callable(value.hex):
        try:
            return value.hex()
        except Exception:  # noqa: BLE001 - keep unusual values representable
            return str(value)
    return str(value)


def _walk_references(value: Any, path: str = "") -> Iterable[tuple[str, int, int]]:
    """Yield PPtr-shaped typetree mappings and their deterministic field paths."""
    if isinstance(value, dict):
        if "m_FileID" in value and "m_PathID" in value:
            try:
                yield path or "$", int(value["m_FileID"]), int(value["m_PathID"])
            except (TypeError, ValueError):
                # A malformed pointer is represented as a per-object decoding
                # failure by the caller, rather than silently coerced.
                raise ValueError(f"invalid PPtr values at {path or '$'}")
            return
        for key in sorted(value, key=lambda item: str(item)):
            child = f"{path}.{key}" if path else str(key)
            yield from _walk_references(value[key], child)
    elif isinstance(value, tuple):
        # Typetree pair nodes can mix scalar keys and container values, so do
        # not infer tuple contents from the first member.
        for index, child_value in enumerate(value):
            if isinstance(child_value, (dict, list, tuple)):
                yield from _walk_references(child_value, f"{path}[{index}]")
    elif isinstance(value, list):
        # Unity arrays are homogeneous: the first element distinguishes large
        # scalar arrays from arrays of object/PPtr containers.
        if value and isinstance(value[0], (dict, list, tuple)):
            for index, child_value in enumerate(value):
                if isinstance(child_value, (dict, list, tuple)):
                    yield from _walk_references(child_value, f"{path}[{index}]")


def _inspect_typetree_for_references(object_reader: Any) -> tuple[str, str | None]:
    """Classify a complete UnityPy TypeTree without decoding object data.

    ``pointer-free`` is returned only when every node has the expected
    TypeTreeNode shape and no PPtr or dynamic-reference node occurs anywhere.
    Unknown or incomplete trees return ``fallback`` so callers fully decode.
    """
    try:
        root = object_reader._get_typetree_node()
        if root is None:
            return "fallback", "TypeTreeNode is absent"
        stack = [root]
        saw_pptr = False
        saw_dynamic = False
        seen: set[int] = set()
        while stack:
            node = stack.pop()
            if id(node) in seen:
                continue
            seen.add(id(node))
            node_type = getattr(node, "m_Type", None)
            node_name = getattr(node, "m_Name", None)
            children = getattr(node, "m_Children", None)
            if (
                not isinstance(node_type, str)
                or not node_type
                or not isinstance(node_name, str)
                or not isinstance(children, (list, tuple))
            ):
                return "fallback", "TypeTreeNode has unknown or incomplete structure"
            folded_type = node_type.casefold()
            folded_label = f"{node_type} {node_name}".casefold()
            if folded_type == "pair" and len(children) != 2:
                return "fallback", "pair node must have exactly two children"
            if folded_type == "array" and len(children) != 2:
                return "fallback", "Array node must have exactly two children"
            if children and getattr(children[0], "m_Type", None) == "Array":
                array_children = getattr(children[0], "m_Children", None)
                if not isinstance(array_children, (list, tuple)) or len(array_children) != 2:
                    return "fallback", "vector Array child is incomplete"
            saw_pptr |= folded_type.startswith("pptr")
            saw_dynamic |= any(
                marker in folded_label
                for marker in ("referencedobject", "managedreferencesregistry")
            )
            stack.extend(children)
        if saw_dynamic:
            return "dynamic", None
        if saw_pptr:
            return "pptr-capable", None
        return "pointer-free", None
    except Exception as exc:  # noqa: BLE001 - unknown trees must use full decoding
        return "fallback", f"{type(exc).__name__}: {exc}"


def _name_from_typetree_prefix(object_reader: Any) -> tuple[bool, Any]:
    """Read only a root-specific prefix through its direct name field.

    Returns ``(False, None)`` when the shape is ambiguous or the fast parse
    cannot be used, allowing the caller to fall back to a full typetree read.
    This intentionally bypasses UnityPy's root-signature-only peek cache.
    """
    try:
        from UnityPy.helpers.TypeTreeNode import TypeTreeNode

        root = object_reader._get_typetree_node()
        if root is None:
            return False, None
        candidates = [
            (index, child)
            for index, child in enumerate(root.m_Children)
            if child.m_Name in ("m_Name", "name")
        ]
        if len(candidates) != 1:
            return False, None
        index, name_node = candidates[0]
        prefix = TypeTreeNode(
            root.m_Level,
            root.m_Type,
            root.m_Name,
            root.m_ByteSize,
            root.m_Version,
            root.m_Children[: index + 1],
        )
        parsed = object_reader.parse_as_dict(prefix, check_read=False)
        if not isinstance(parsed, dict) or name_node.m_Name not in parsed:
            return False, None
        return True, parsed[name_node.m_Name]
    except Exception:  # noqa: BLE001 - name extraction is an optimization
        return False, None


def _external_reference(externals: list[Any], file_id: int) -> dict[str, Any] | None:
    # Unity fileID zero means this serialized file; positive values are
    # one-based indexes into the SerializedFile external table.
    if file_id == 0:
        return None
    index = file_id - 1
    if index < 0 or index >= len(externals):
        return {"index": index, "mappingStatus": "unmatched"}
    external = externals[index]
    return {
        "index": index,
        "path": _plain(getattr(external, "path", None)),
        "guid": _plain(getattr(external, "guid", None)),
        "type": _plain(getattr(external, "type", None)),
        "mappingStatus": "matched",
    }


def _lenient_typetree_candidate(
    object_reader: Any, externals: list[Any]
) -> tuple[Any, list[dict[str, Any]]]:
    """Build fallback fields locally so a traversal error cannot leak edges."""
    decoded = object_reader.read_typetree(check_read=False)
    if not isinstance(decoded, dict):
        raise TypeError("lenient typetree result is not a mapping")
    owner_name = _plain(decoded.get("m_Name"))
    references = []
    for field_path, file_id, target_path_id in _walk_references(decoded):
        if target_path_id == 0:
            continue
        references.append({
            "fieldPath": field_path,
            "m_FileID": file_id,
            "m_PathID": target_path_id,
            "externalFile": _external_reference(externals, file_id),
        })
    references.sort(key=lambda ref: (ref["fieldPath"], ref["m_FileID"], ref["m_PathID"]))
    return owner_name, references


def _same_filesystem_path(left: Path, right: Path) -> bool:
    """Compare normalized paths and existing filesystem identities."""
    if left.resolve(strict=False) == right.resolve(strict=False):
        return True
    try:
        return left.exists() and right.exists() and os.path.samefile(left, right)
    except OSError:
        return False


def _validate_artifact_paths(
    sources: list[Path], output: Path, receipt: Path, checkpoint: Path
) -> None:
    artifacts = (("output_jsonl", output), ("receipt_path", receipt), ("checkpoint", checkpoint))
    for label, artifact in artifacts:
        for source in sources:
            if _same_filesystem_path(artifact, source):
                raise ValueError(f"{label} must not resolve to or alias a source file: {artifact}")
    for index, (left_name, left) in enumerate(artifacts):
        for right_name, right in artifacts[index + 1 :]:
            if _same_filesystem_path(left, right):
                raise ValueError(f"{left_name} and {right_name} must resolve to distinct paths")


def _object_key(source: dict[str, Any], path_id: int, *, duplicate_hash: bool = False) -> str:
    # Preserve the live single-source checkpoint key exactly. Only duplicate
    # content hashes need a path component to distinguish serialized owners.
    if not duplicate_hash:
        return f"{source['sha256']}:{path_id}"
    path_and_id = json.dumps([source["path"], path_id], ensure_ascii=False, separators=(",", ":"))
    return f"{source['sha256']}:{path_and_id}"


def export_reference_graph(
    source_files: Iterable[str | os.PathLike[str]],
    output_jsonl: str | os.PathLike[str],
    *,
    receipt_path: str | os.PathLike[str] | None = None,
    resume: bool = True,
) -> dict[str, Any]:
    """Export one object record per Unity object, including its PPtr edges.

    A sibling SQLite checkpoint (``<output>.checkpoint.sqlite3``) records each
    object as it is processed. Successful object records are retained on
    resume; failed objects and failed source loads are retried. The JSONL is
    atomically regenerated in source/PathID order from checkpoint records.
    """
    sources_by_path = {str(Path(item).resolve(strict=True)): Path(item).resolve(strict=True) for item in source_files}
    sources = sorted(sources_by_path.values(), key=lambda item: str(item))
    if not sources:
        raise ValueError("at least one serialized Unity source file is required")
    identities = [_source_identity(path) for path in sources]
    output = Path(output_jsonl).resolve()
    receipt = Path(receipt_path).resolve() if receipt_path else output.with_suffix(output.suffix + ".receipt.json")
    checkpoint = output.with_suffix(output.suffix + ".checkpoint.sqlite3")
    selection = [{key: identity[key] for key in ("path", "sizeBytes", "sha256")} for identity in identities]
    source_hash_counts: dict[str, int] = {}
    for identity in identities:
        source_hash_counts[identity["sha256"]] = source_hash_counts.get(identity["sha256"], 0) + 1
    _validate_artifact_paths(sources, output, receipt, checkpoint)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not resume and checkpoint.exists():
        checkpoint.unlink()
    connection = sqlite3.connect(checkpoint)
    connection.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    connection.execute("CREATE TABLE IF NOT EXISTS records (record_key TEXT PRIMARY KEY, source_path TEXT NOT NULL, path_id INTEGER NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL)")
    connection.execute("CREATE TABLE IF NOT EXISTS source_failures (source_path TEXT PRIMARY KEY, payload TEXT NOT NULL)")
    stored = connection.execute("SELECT value FROM metadata WHERE key = 'selection'").fetchone()
    if stored is not None and json.loads(stored[0]) != selection:
        connection.close()
        raise ValueError(f"checkpoint does not match selected source identities: {checkpoint}")
    stored_schema = connection.execute("SELECT value FROM metadata WHERE key = 'schema'").fetchone()
    if stored_schema is not None and stored_schema[0] != CHECKPOINT_SCHEMA:
        connection.close()
        raise ValueError(f"checkpoint schema is not supported: {checkpoint}")
    if stored is None:
        connection.execute("INSERT INTO metadata(key, value) VALUES ('schema', ?)", (CHECKPOINT_SCHEMA,))
        connection.execute("INSERT INTO metadata(key, value) VALUES ('selection', ?)", (_json_bytes(selection).decode("utf-8").strip(),))
        connection.commit()

    from .unity_assets import _require_unitypy

    unitypy = _require_unitypy()
    source_counts: dict[str, int] = {}
    _atomic_json(receipt, {
        "schema": SCHEMA,
        "status": "running",
        "unityPyVersion": getattr(unitypy, "__version__", None),
        "sourceCount": len(identities),
        "sources": identities,
        "checkpoint": str(checkpoint),
        "claimBoundary": "serialized Unity object typetrees and PPtr metadata only; no pointer dereference, texture pixel decode, asset export, project import, or source mutation",
    })
    for source, identity in zip(sources, identities, strict=True):
        try:
            environment = unitypy.load(str(source))
            serialized = getattr(environment, "file", None)
            if serialized is None:
                candidates = [item for item in environment.files.values() if hasattr(item, "objects")]
                if len(candidates) != 1:
                    raise ValueError(f"UnityPy loaded {len(candidates)} serialized files; expected one")
                serialized = candidates[0]
            header = getattr(serialized, "header", None)
            declared_size = getattr(header, "file_size", None)
            if declared_size is not None and int(declared_size) != identity["sizeBytes"]:
                raise ValueError(
                    f"UnityPy header declares {declared_size} bytes for a {identity['sizeBytes']}-byte source"
                )
            objects = sorted(serialized.objects.values(), key=lambda item: int(item.path_id))
            if not objects:
                raise ValueError("UnityPy returned a serialized file with no indexed objects")
            source_counts[identity["path"]] = len(objects)
            externals = list(getattr(serialized, "externals", ()) or ())
            for object_index, object_reader in enumerate(objects, start=1):
                path_id = int(object_reader.path_id)
                key = _object_key(
                    identity,
                    path_id,
                    duplicate_hash=source_hash_counts[identity["sha256"]] > 1,
                )
                previous = connection.execute("SELECT status FROM records WHERE record_key = ?", (key,)).fetchone()
                if previous is not None and previous[0] in {"decoded", "partial"}:
                    continue
                object_type = _plain(getattr(getattr(object_reader, "type", None), "name", None))
                row: dict[str, Any] = {
                    "schema": SCHEMA,
                    "recordType": "object",
                    "source": identity,
                    "owner": {"pathId": path_id, "type": object_type, "name": None},
                    "status": "decoded",
                    "references": [],
                }
                tree_mode, tree_error = _inspect_typetree_for_references(object_reader)
                decoded: Any = None
                try:
                    if tree_mode == "pointer-free":
                        name_ok, name_value = _name_from_typetree_prefix(object_reader)
                        if name_ok:
                            row["scanMode"] = "pointer-free-typetree"
                            row["typeTreeMode"] = tree_mode
                            row["owner"]["name"] = _plain(name_value)
                        else:
                            tree_mode = "fallback"
                            tree_error = "root-specific name-prefix parse unavailable; using full typetree"
                    if tree_mode != "pointer-free" or not row.get("scanMode"):
                        row["scanMode"] = "full-read-typetree"
                        row["typeTreeMode"] = tree_mode
                        if tree_error is not None:
                            row["typeTreeInspectionError"] = tree_error
                        decoded = object_reader.read_typetree()
                        row["owner"]["name"] = _plain(decoded.get("m_Name")) if isinstance(decoded, dict) else None
                        for field_path, file_id, target_path_id in _walk_references(decoded):
                            if target_path_id == 0:
                                continue
                            row["references"].append({
                                "fieldPath": field_path,
                                "m_FileID": file_id,
                                "m_PathID": target_path_id,
                                "externalFile": _external_reference(externals, file_id),
                            })
                        row["references"].sort(key=lambda ref: (ref["fieldPath"], ref["m_FileID"], ref["m_PathID"]))
                except Exception as exc:  # noqa: BLE001 - retain strict failure and try bounded salvage
                    row["strictError"] = f"{type(exc).__name__}: {exc}"
                    row["references"] = []
                    try:
                        candidate_name, candidate_references = _lenient_typetree_candidate(
                            object_reader, externals
                        )
                        row["owner"]["name"] = candidate_name
                        row["references"] = candidate_references
                        row["status"] = "partial"
                        row["scanMode"] = "lenient-read-typetree"
                    except Exception as fallback_exc:  # noqa: BLE001 - retain both failure stages
                        row["status"] = "failed"
                        row["fallbackError"] = f"{type(fallback_exc).__name__}: {fallback_exc}"
                        row["error"] = (
                            f"{row['strictError']}; lenient fallback failed: {row['fallbackError']}"
                        )
                connection.execute(
                    "INSERT INTO records(record_key, source_path, path_id, status, payload) VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(record_key) DO UPDATE SET source_path=excluded.source_path, path_id=excluded.path_id, status=excluded.status, payload=excluded.payload",
                    (key, identity["path"], path_id, row["status"], _json_bytes(row).decode("utf-8").strip()),
                )
                del decoded
                del object_reader
                if object_index % 128 == 0:
                    connection.commit()
                if object_index % 4096 == 0:
                    gc.collect()
            connection.execute("DELETE FROM source_failures WHERE source_path = ?", (identity["path"],))
            connection.commit()
        except Exception as exc:  # noqa: BLE001 - preserve incomplete source evidence
            failure = {
                "source": identity,
                "error": f"{type(exc).__name__}: {exc}",
            }
            connection.execute(
                "INSERT INTO source_failures(source_path, payload) VALUES (?, ?) "
                "ON CONFLICT(source_path) DO UPDATE SET payload=excluded.payload",
                (identity["path"], _json_bytes(failure).decode("utf-8").strip()),
            )
            connection.commit()

    source_failures = [json.loads(payload) for (payload,) in connection.execute("SELECT payload FROM source_failures ORDER BY source_path")]
    source_by_path = {identity["path"]: identity for identity in identities}
    object_record_count = 0
    failed_objects = 0
    partial_objects = 0
    reference_count = 0
    scan_mode_counts = {
        "pointer-free-typetree": 0,
        "full-read-typetree": 0,
        "lenient-read-typetree": 0,
    }
    unclassified_mode_count = 0
    type_tree_mode_counts: dict[str, int] = {}

    def current_records() -> Iterable[dict[str, Any]]:
        nonlocal object_record_count, failed_objects, partial_objects, reference_count, unclassified_mode_count
        for record_key, source_path, path_id, payload in connection.execute(
            "SELECT record_key, source_path, path_id, payload FROM records ORDER BY source_path, path_id, record_key"
        ):
            identity = source_by_path.get(source_path)
            if identity is None:
                continue
            duplicate_hash = source_hash_counts[identity["sha256"]] > 1
            if record_key != _object_key(identity, path_id, duplicate_hash=duplicate_hash):
                # Ignore only stale ambiguous keys from an earlier duplicate-
                # content export; do not alter/migrate the checkpoint itself.
                continue
            row = json.loads(payload)
            object_record_count += 1
            failed_objects += row.get("status") == "failed"
            partial_objects += row.get("status") == "partial"
            reference_count += len(row.get("references", ()))
            scan_mode = row.get("scanMode")
            if scan_mode in scan_mode_counts:
                scan_mode_counts[scan_mode] += 1
            else:
                unclassified_mode_count += 1
            type_tree_mode = row.get("typeTreeMode", "unclassified")
            type_tree_mode_counts[type_tree_mode] = type_tree_mode_counts.get(type_tree_mode, 0) + 1
            yield row

    _atomic_jsonl(output, current_records())
    expected_objects = sum(source_counts.values())
    status = "complete" if not failed_objects and not partial_objects and not source_failures and object_record_count == expected_objects else "incomplete"
    result = {
        "schema": SCHEMA,
        "status": status,
        "unityPyVersion": getattr(unitypy, "__version__", None),
        "sourceCount": len(identities),
        "sources": identities,
        "sourceObjectCounts": source_counts,
        "objectRecordCount": object_record_count,
        "failedObjectCount": failed_objects,
        "partialObjectCount": partial_objects,
        "referenceCount": reference_count,
        "scanModeCounts": scan_mode_counts,
        "unclassifiedScanModeCount": unclassified_mode_count,
        "typeTreeModeCounts": type_tree_mode_counts,
        "sourceFailures": source_failures,
        "outputJsonl": str(output),
        "checkpoint": str(checkpoint),
        "claimBoundary": "serialized Unity object typetrees and PPtr metadata only; no pointer dereference, texture pixel decode, asset export, project import, or source mutation",
    }
    _atomic_json(receipt, result)
    connection.close()
    return result
