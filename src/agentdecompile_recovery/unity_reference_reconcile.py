"""Read-only reconciliation of Unity placeholder references against graph evidence.

The Task 1 graph and AssetRipper's name/type/PathID map contain no authenticated
source-object to exported-object binding. Consequently this input contract cannot
establish exact recovery, even for a single numeric candidate.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from bisect import bisect_right
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .unity_project_audit import (
    BLOCK_FIELD,
    BLOCK_SCALAR,
    BUILTIN_GUIDS,
    FILE_ID,
    HEX_GUID,
    META_GUID,
    REFERENCE_MAP,
    UNITY_DOCUMENT,
    YAML_EXTENSIONS,
    _mapping_start,
)

SCHEMA = "agentdecompile.unity-reference-reconcile.v1"
GRAPH_SCHEMAS = {"agentdecompile.unity-reference-graph.v1", "agentdecompile.unity-reference-graph.v2"}
ANCHOR = re.compile(r"(?m)^--- !u!(\d+) &(-?\d+)(?: stripped)?[ \t]*\r?$")
CLAIM_BOUNDARY = (
    "Read-only PPtr syntax and identity-evidence audit, not full Unity YAML/Editor validation. "
    "No reference repair, ID normalization, or source mutation. Numeric PathID/fileID, "
    "name, class, type, similarity and synthetic/repeated GUID are never identity proof. "
    "Task 1 graphs and the existing name/type/PathID map provide no direct binding to "
    "exported YAML/meta targets; exact is therefore unavailable for this input contract. "
    "Partial objects are candidate evidence only. Raw source hashes are receipt claims, "
    "not freshly verified source bytes. Only the explicitly requested report is written."
)


def _mask_reference_text(content: str) -> str:
    """Mask scalar text, with a fast path for long plain serialized data lines."""
    output = []
    quote: str | None = None
    scalar_indent: int | None = None
    for line in content.splitlines(keepends=True):
        indent = len(line) - len(line.lstrip(" \t"))
        if scalar_indent is not None:
            if not line.strip() or indent > scalar_indent:
                output.append(re.sub(r"[^\n]", " ", line))
                continue
            scalar_indent = None
        if quote is None and not any(char in line for char in "\"'#"):
            output.append(line)
            if BLOCK_SCALAR.fullmatch(line.rstrip("\r\n")):
                scalar_indent = indent
            continue
        masked = list(line)
        index = 0
        while index < len(line):
            char = line[index]
            if quote:
                masked[index] = " " if char != "\n" else "\n"
                if quote == '"' and char == "\\" and index + 1 < len(line):
                    index += 1
                    masked[index] = " " if line[index] != "\n" else "\n"
                elif char == quote:
                    if quote == "'" and index + 1 < len(line) and line[index + 1] == "'":
                        index += 1
                        masked[index] = " "
                    else:
                        quote = None
            elif char in "\"'" and (index == 0 or line[index - 1].isspace() or line[index - 1] in ":[{,"):
                quote = char
                masked[index] = " "
            elif char == "#" and (index == 0 or line[index - 1].isspace()):
                masked[index:] = ["\n" if item == "\n" else " " for item in line[index:]]
                break
            index += 1
        clean = "".join(masked)
        if quote is None and BLOCK_SCALAR.fullmatch(clean.rstrip("\r\n")):
            scalar_indent = indent
        output.append(clean)
    return "".join(output)


def _identity(path: Path, data: bytes) -> dict[str, Any]:
    return {"path": str(path), "sizeBytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def parse_unity_references(content: str) -> dict[str, Any]:
    """Preserve literal IDs, anchors and locations; diagnose malformed PPtr syntax.

    Comments, quoted strings and block scalars are masked before structural scans.
    Both flow and block PPtr mappings are supported. This is intentionally not a
    general YAML validator; unsupported/malformed reference shapes are retained.
    """
    clean = _mask_reference_text(content)
    line_starts = [0, *(m.end() for m in re.finditer("\n", clean))]

    def line_number(offset: int) -> int:
        return bisect_right(line_starts, offset)

    anchors = [
        {"classID": m[1], "fileID": m[2], "line": line_number(m.start())}
        for m in ANCHOR.finditer(clean)
    ]
    errors: list[dict[str, Any]] = []
    references: list[dict[str, Any]] = []
    anchor_lines = [a["line"] for a in anchors]

    def record(fields: dict[str, str], offset: int) -> None:
        line = line_number(offset)
        if "guid" not in fields:
            return
        if not HEX_GUID.fullmatch(fields["guid"]) or not FILE_ID.fullmatch(fields.get("fileID", "")):
            errors.append({"line": line, "reason": "invalid external PPtr GUID/fileID", "fields": fields.copy()})
            return
        if "type" in fields and not fields["type"].isdigit():
            errors.append({"line": line, "reason": "invalid external PPtr type", "fields": fields.copy()})
            return
        if int(fields["fileID"]) == 0:
            return
        owner_index = bisect_right(anchor_lines, line) - 1
        owner = anchors[owner_index] if owner_index >= 0 else None
        references.append({
            **fields, "line": line, "column": offset - clean.rfind("\n", 0, offset),
            "ownerAnchor": owner,
            "fieldContext": content[content.rfind("\n", 0, offset) + 1:offset].strip(),
        })

    flow_spans: list[tuple[int, int]] = []
    for match in REFERENCE_MAP.finditer(clean):
        if not _mapping_start(clean, match.start()):
            continue
        fields: dict[str, str] = {}
        malformed = False
        for part in match[1].split(","):
            key, separator, value = part.strip().partition(":")
            if not separator or key in fields:
                malformed = True
            fields[key] = value.strip()
        if "guid" in fields:
            flow_spans.append((match.start(), match.end()))
            if malformed or set(fields) - {"fileID", "guid", "type"}:
                errors.append({"line": line_number(match.start()), "reason": "malformed PPtr mapping"})
            else:
                record(fields, match.start())

    fields = {}
    indent: int | None = None
    start = 0
    offset = 0
    flow_starts = [span[0] for span in flow_spans]
    for line in clean.splitlines(keepends=True):
        flow_index = bisect_right(flow_starts, offset) - 1
        if flow_index >= 0 and offset < flow_spans[flow_index][1]:
            record(fields, start)
            fields = {}
            indent = None
            offset += len(line)
            continue
        match = BLOCK_FIELD.fullmatch(line.rstrip("\r\n"))
        if match:
            current_indent = len(match[1]) + (2 if match.group("dash") else 0)
            key = match[3]
            if indent != current_indent or match.group("dash") or key in fields:
                if key in fields and indent == current_indent and not match.group("dash"):
                    errors.append({"line": line_number(offset), "reason": "duplicate block PPtr field"})
                record(fields, start)
                fields = {}
            if not fields:
                start = offset + len(match[1])
            fields[key] = match[4]
            indent = current_indent
        elif line.strip():
            record(fields, start)
            fields = {}
            indent = None
            if re.match(r"^\s*(?:-\s+)?(?:fileID|guid|type):", line):
                errors.append({"line": line_number(offset), "reason": "unsupported or malformed block PPtr field"})
        offset += len(line)
    record(fields, start)
    stack: list[str] = []
    pairs = {"}": "{", "]": "["}
    for delimiter in re.finditer(r"[{}\[\]]", clean):
        offset = delimiter.start()
        char = delimiter[0]
        if char in "{[" and (_mapping_start(clean, offset) or stack):
            stack.append(char)
        elif char in "}]" and stack:
            if stack.pop() != pairs[char]:
                errors.append({"line": line_number(offset), "reason": "mismatched flow delimiter"})
    if stack:
        errors.append({"reason": "unterminated flow collection"})
    if len({a["fileID"] for a in anchors}) != len(anchors):
        errors.append({"reason": "duplicate YAML object anchor"})
    if len(anchors) != len(UNITY_DOCUMENT.findall(clean)):
        errors.append({"reason": "unsupported Unity document header"})
    return {"anchors": anchors, "references": sorted(references, key=lambda r: (r["line"], r["column"])), "errors": errors}


def _receipt_path(graph: Path) -> Path:
    appended = graph.with_suffix(graph.suffix + ".receipt.json")
    replaced = graph.with_suffix(".receipt.json")
    existing = [p for p in (appended, replaced) if p.exists()]
    if len(existing) > 1:
        raise ValueError(f"multiple sibling receipts for {graph}; specify --graph-receipt")
    return existing[0] if existing else appended


def read_graph(graph: Path, receipt_path: Path) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    """Stream graph records and retain numeric collisions only as rejected evidence."""
    errors: list[dict[str, Any]] = []
    provenance: dict[str, Any] = {"graphPath": str(graph), "receiptPath": str(receipt_path), "errors": errors}
    candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    receipt: dict[str, Any] = {}
    try:
        data = receipt_path.read_bytes()
        provenance["receiptIdentity"] = _identity(receipt_path, data)
        loaded = json.loads(data)
        if not isinstance(loaded, dict):
            raise ValueError("receipt must be an object")
        receipt = loaded
        provenance["receipt"] = receipt
        if receipt.get("schema") not in GRAPH_SCHEMAS or receipt.get("status") not in {"complete", "incomplete"}:
            raise ValueError("unsupported receipt schema/status")
        if Path(receipt.get("outputJsonl", "")).resolve() != graph:
            raise ValueError("receipt outputJsonl does not bind selected graph")
    except (OSError, ValueError, TypeError) as exc:
        errors.append({"reason": f"receipt: {exc}"})
    sources = {}
    declared_sources = receipt.get("sources")
    if not isinstance(declared_sources, list):
        errors.append({"reason": "receipt sources must be a list"})
    else:
        for source in declared_sources:
            if (not isinstance(source, dict) or not isinstance(source.get("path"), str)
                    or not isinstance(source.get("sha256"), str)
                    or re.fullmatch(r"[0-9a-f]{64}", source["sha256"]) is None
                    or type(source.get("sizeBytes")) is not int or source["sizeBytes"] < 0):
                errors.append({"reason": "invalid receipt source identity"})
                continue
            if source["path"] in sources:
                errors.append({"reason": "duplicate receipt source identity"})
            sources[source["path"]] = source
    if receipt.get("sourceCount") != len(sources):
        errors.append({"reason": "receipt sourceCount differs from source inventory"})
    failed_sources: set[str] = set()
    declared_failures = receipt.get("sourceFailures", [])
    if not isinstance(declared_failures, list):
        errors.append({"reason": "receipt sourceFailures must be a list"})
        declared_failures = []
    for failure in declared_failures:
        failed_source = failure.get("source") if isinstance(failure, dict) else None
        if not isinstance(failed_source, dict) or not isinstance(failed_source.get("path"), str):
            errors.append({"reason": "receipt contains an invalid source failure identity"})
            continue
        failed_path = failed_source["path"]
        if failed_path not in sources or failed_source != sources[failed_path]:
            errors.append({"reason": "source failure identity is absent from or differs from receipt sources", "path": failed_path})
            continue
        if failed_path in failed_sources:
            errors.append({"reason": "duplicate failed source identity", "path": failed_path})
        failed_sources.add(failed_path)
    counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    seen: set[tuple[str, str]] = set()
    digest = hashlib.sha256()
    size = 0
    references = 0
    try:
        with graph.open("rb") as stream:
            for line_number, line in enumerate(stream, 1):
                digest.update(line)
                size += len(line)
                try:
                    row = json.loads(line)
                    if not isinstance(row, dict) or row.get("schema") not in GRAPH_SCHEMAS or row.get("recordType") != "object":
                        raise ValueError("unsupported graph record")
                    source, owner = row["source"], row["owner"]
                    if not isinstance(source, dict) or not isinstance(owner, dict) or type(owner.get("pathId")) is not int:
                        raise ValueError("invalid source/owner identity")
                    if source != sources.get(source.get("path")):
                        raise ValueError("source identity differs from receipt")
                    status = row.get("status")
                    if status not in {"decoded", "partial", "failed"} or not isinstance(row.get("references"), list):
                        raise ValueError("invalid object status/references")
                    for ref in row["references"]:
                        if (not isinstance(ref, dict) or not isinstance(ref.get("fieldPath"), str)
                                or type(ref.get("m_FileID")) is not int
                                or type(ref.get("m_PathID")) is not int):
                            raise ValueError("invalid graph PPtr edge")
                    key = (source["path"], str(owner["pathId"]))
                    if key in seen:
                        errors.append({"line": line_number, "reason": "duplicate source object identity"})
                    seen.add(key)
                    counts[status] += 1
                    source_counts[source["path"]] += 1
                    references += len(row["references"])
                    candidates[str(owner["pathId"])].append({
                        "graph": str(graph), "line": line_number, "source": source,
                        "owner": owner, "status": status,
                        "strictError": row.get("strictError"), "error": row.get("error"),
                        "reason": "numeric equality only; rejected as identity proof",
                        "eligibleForExact": False,
                    })
                except (ValueError, KeyError, TypeError) as exc:
                    errors.append({"line": line_number, "reason": str(exc)})
    except OSError as exc:
        errors.append({"reason": f"graph: {exc}"})
    for field, actual in (("objectRecordCount", sum(counts.values())), ("partialObjectCount", counts["partial"]), ("failedObjectCount", counts["failed"]), ("referenceCount", references)):
        if receipt.get(field) != actual:
            errors.append({"reason": f"receipt {field} differs from observed count", "observed": actual, "declared": receipt.get(field)})
    if receipt.get("sourceObjectCounts") != dict(source_counts):
        errors.append({"reason": "receipt sourceObjectCounts differs from observed inventory"})
    observed_sources = set(source_counts)
    overlap = observed_sources & failed_sources
    missing_sources = set(sources) - observed_sources - failed_sources
    if overlap:
        errors.append({"reason": "receipt source has both graph records and a source failure", "paths": sorted(overlap)})
    if missing_sources:
        errors.append({"reason": "declared receipt sources have neither graph records nor explicit failures", "paths": sorted(missing_sources)})
    undeclared_sources = (observed_sources | failed_sources) - set(sources)
    if undeclared_sources:
        errors.append({"reason": "observed or failed sources are not declared by receipt", "paths": sorted(undeclared_sources)})
    provenance.update({"graphIdentity": {"path": str(graph), "sha256": digest.hexdigest(), "sizeBytes": size}, "observedStatusCounts": dict(sorted(counts.items())), "observedObjectCount": sum(counts.values())})
    provenance["complete"] = receipt.get("status") == "complete" and not errors and not counts["partial"] and not counts["failed"] and not receipt.get("sourceFailures")
    return provenance, candidates


def reconcile_unity_references(
    project_root: Path, graph_files: list[Path], *,
    receipt_files: list[Path] | None = None, path_id_map: Path | None = None,
) -> dict[str, Any]:
    """Build a deterministic report without opening any file for writing."""
    root = project_root.resolve(strict=True)
    assets = root / "Assets"
    if assets.is_symlink() or not assets.is_dir():
        raise ValueError("project must have a regular Assets directory")
    if not graph_files or (receipt_files is not None and len(receipt_files) != len(graph_files)):
        raise ValueError("provide graphs and, if explicit, one receipt per graph in matching order")
    graph_pairs = [(g.resolve(), r.resolve() if r else _receipt_path(g.resolve())) for g, r in zip(graph_files, receipt_files or [None] * len(graph_files), strict=True)]
    graphs = []
    raw_candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for graph, receipt in sorted(set(graph_pairs)):
        provenance, candidates = read_graph(graph, receipt)
        graphs.append(provenance)
        for key, rows in candidates.items():
            raw_candidates[key].extend(rows)
    errors: list[dict[str, Any]] = []
    metas: dict[str, list[str]] = defaultdict(list)
    files: list[dict[str, Any]] = []
    occurrences = []
    skipped = []
    paths = []

    def walk_error(error: OSError) -> None:
        errors.append({"path": str(error.filename), "reason": str(error)})

    for directory, dirs, names in os.walk(assets, followlinks=False, onerror=walk_error):
        base = Path(directory)
        for name in sorted(dirs):
            if (base / name).is_symlink():
                errors.append({"path": str(base / name), "reason": "symlink directory excluded; scan incomplete"})
        dirs[:] = sorted(name for name in dirs if not (base / name).is_symlink())
        paths.extend(base / name for name in sorted(names))
    for path in sorted(paths):
        relative = path.relative_to(root).as_posix()
        try:
            if path.is_symlink() or not path.is_file():
                errors.append({"path": relative, "reason": "non-regular entry excluded"})
                continue
            with path.open("rb") as stream:
                prefix = stream.read(4096)
                is_meta = path.suffix.lower() == ".meta"
                is_yaml = b"%YAML" in prefix or b"--- !u!" in prefix
                if not is_meta and not is_yaml:
                    skipped.append({"path": relative, "reason": "binary/non-Unity-YAML asset"})
                    if path.suffix.lower() in YAML_EXTENSIONS and b"\x00" not in prefix:
                        errors.append({"path": relative, "reason": "serialized asset without supported Unity YAML header"})
                    continue
                data = prefix + stream.read()
            identity = _identity(path, data)
            content = data.decode("utf-8-sig")
            entry = {**identity, "relativePath": relative, "kind": "meta" if is_meta else "yaml"}
            files.append(entry)
            if is_meta:
                matches = META_GUID.findall(content)
                entry["guids"] = matches
                entry["fileFormatVersions"] = re.findall(r"(?m)^fileFormatVersion:\s*(\d+)\s*$", content)
                if len(matches) != 1:
                    errors.append({"path": relative, "reason": "meta must contain exactly one GUID"})
                else:
                    metas[matches[0]].append(relative)
                continue
            parsed = parse_unity_references(content)
            entry["anchors"] = parsed["anchors"]
            entry["serializedVersions"] = re.findall(r"(?m)^\s*serializedVersion:\s*(\d+)\s*$", content)
            errors.extend({"path": relative, **error} for error in parsed["errors"])
            occurrences.extend({"path": relative, **ref} for ref in parsed["references"])
        except (OSError, UnicodeError) as exc:
            errors.append({"path": relative, "reason": str(exc)})

    map_provenance: dict[str, Any] | None = None
    map_candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if path_id_map is not None:
        map_path = path_id_map.resolve()
        map_provenance = {"path": str(map_path), "identityProof": False}
        try:
            data = map_path.read_bytes()
            map_provenance.update(_identity(map_path, data))
            mapping = json.loads(data)
            if not isinstance(mapping, dict) or not isinstance(mapping.get("Files"), list):
                raise ValueError("expected AssetRipper Files/Assets map")
            for file_index, group in enumerate(mapping["Files"]):
                if not isinstance(group, dict) or not isinstance(group.get("Assets"), list):
                    raise ValueError("invalid map file group")
                for asset_index, item in enumerate(group["Assets"]):
                    if not isinstance(item, dict) or type(item.get("PathID")) is not int:
                        raise ValueError("invalid map asset PathID")
                    map_candidates[str(item["PathID"])].append({"fileIndex": file_index, "assetIndex": asset_index, "file": group.get("Name"), "asset": item, "eligibleForExact": False, "reason": "name/type/PathID inventory lacks direct YAML/meta identity binding"})
            map_provenance["assetCount"] = sum(map(len, map_candidates.values()))
        except (OSError, ValueError, TypeError) as exc:
            errors.append({"path": str(map_path), "reason": f"map: {exc}"})
    candidate_groups = {}
    placeholders = []
    for occurrence in occurrences:
        guid = occurrence["guid"]
        if guid in BUILTIN_GUIDS:
            continue
        local = metas.get(guid, [])
        synthetic = guid == "0" * 32 or len(set(guid)) == 1
        if len(local) == 1 and not synthetic and (root / local[0]).with_suffix("").exists():
            continue
        key = f"{guid}:{occurrence['fileID']}"
        if key not in candidate_groups:
            candidates = raw_candidates.get(occurrence["fileID"], [])
            mapped = map_candidates.get(occurrence["fileID"], [])
            candidate_groups[key] = {"guid": guid, "fileID": occurrence["fileID"], "localMetaPaths": local, "numericGraphCandidates": candidates, "numericMapCandidates": mapped, "directIdentityProofCount": 0, "reasons": ["no authenticated source-object to YAML/meta binding", "numeric collisions are diagnostic evidence only", "partial objects cannot support exact", "synthetic/repeated GUID cannot support exact"], "classification": "ambiguous" if len(local) > 1 else "unresolved"}
        placeholders.append({**occurrence, "candidateGroup": key, "classification": candidate_groups[key]["classification"]})
    totals = Counter(p["classification"] for p in placeholders)
    complete = not errors and all(g["complete"] for g in graphs)
    return {
        "schema": SCHEMA, "projectRoot": str(root), "claimBoundary": CLAIM_BOUNDARY,
        "status": "complete" if complete else "incomplete", "scanComplete": not errors,
        "graphs": graphs, "pathIdMap": map_provenance, "filesScanned": files,
        "skippedFiles": skipped, "errors": errors,
        "metaGuidIndex": dict(sorted(metas.items())), "candidateGroups": dict(sorted(candidate_groups.items())),
        "placeholderReferences": placeholders,
        "totals": {"yamlFiles": sum(f["kind"] == "yaml" for f in files), "metaFiles": sum(f["kind"] == "meta" for f in files), "anchors": sum(len(f.get("anchors", [])) for f in files), "graphObjects": sum(g["observedObjectCount"] for g in graphs), "placeholderReferences": len(placeholders), "distinctTargetFileIDs": len({p["fileID"] for p in placeholders}), "exact": 0, "ambiguous": totals["ambiguous"], "unresolved": totals["unresolved"], "unresolvedIncludingAmbiguous": len(placeholders)},
    }


def write_reconciliation_report(report: dict[str, Any], output: Path, *, protected_inputs: list[Path]) -> None:
    """Write only the selected output, rejecting project descendants and aliases."""
    target = output.resolve()
    root = Path(report["projectRoot"])
    if target == root or root in target.parents:
        raise ValueError("report output must be outside the Unity project")
    for path in protected_inputs:
        source = path.resolve()
        if target == source or (target.exists() and source.exists() and os.path.samefile(target, source)):
            raise ValueError("report output aliases an input")
    if target.exists() and target.stat().st_nlink > 1:
        raise ValueError("report output has hard-link aliases")
    # No mkdir, temporary file, checkpoint, or project mutation.
    target.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
