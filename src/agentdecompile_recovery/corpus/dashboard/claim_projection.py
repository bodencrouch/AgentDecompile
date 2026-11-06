"""Bounded recorded candidate evidence for the selected activity target.

This reader never accepts recovery, imports contribution JSON, or launches work.
Stored local bytes and named witnesses remain historical observations. Only the
source freshness predicate is rechecked here; target/compiler/placement claims
are never inferred from a row's flags or an artifact's filename.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from urllib.parse import urlencode

from ..coverage_evidence import source_binding
from ..semantic_identity import recorded_export_name

MAX_CANDIDATES = 64
MAX_SOURCE_BYTES = 4 * 1024 * 1024
MAX_EVIDENCE_BYTES = 64 * 1024
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_FIELDS = ("program", "name", "binary_id", "addr", "path", "source_sha256",
           "target_sha256", "size", "machine_code", "semantic_status",
           "semantic_reason", "semantic_evidence")


def _digest(value) -> bool:
    return isinstance(value, str) and _SHA.fullmatch(value) is not None


def _bound_target(binary: dict, locator: str, program: str, slug: str) -> str | None:
    if binary.get("kind") == "project" or not _digest(binary.get("sha256")):
        return "selected_target_identity_unavailable"
    if slug and slug not in (binary.get("aliasSlugs") or [binary.get("slug")]):
        return "selected_slug_mismatch"
    bindings = binary.get("projectBindings") or []
    if locator or program:
        if not any((not locator or b.get("locator") == locator) and
                   (not program or str(b.get("program") or "").lstrip("/") == program.lstrip("/"))
                   for b in bindings if isinstance(b, dict)):
            return "selected_program_binding_mismatch"
    if not (slug or program):
        return "select_a_concrete_target"
    return None


def _source_state(row: dict, roots: tuple[Path, ...], budget: dict) -> dict:
    if not _digest(row.get("source_sha256")):
        return {"current": False, "reason": "missing_or_invalid_source_digest"}
    try:
        path = Path(row.get("path") or "").resolve(strict=True)
        allowed = [root.resolve() for root in roots]
        if not any(path.is_relative_to(root) for root in allowed):
            return {"current": False, "reason": "source_outside_configured_evidence_roots"}
        if path.suffix.lower() not in {".c", ".cpp", ".cc", ".cxx"} or not path.is_file():
            return {"current": False, "reason": "source_not_a_supported_regular_file"}
        allowance = min(MAX_SOURCE_BYTES, budget["bytes"])
        if path.stat().st_size > allowance:
            budget["limited"] = True
            return {"current": False, "reason": "source_exceeds_observation_limit"}
        with path.open("rb") as stream:
            before = os.fstat(stream.fileno())
            raw = stream.read(allowance + 1)
            after = os.fstat(stream.fileno())
        budget["bytes"] = max(0, budget["bytes"] - len(raw))
        final = path.stat()
        stamp = lambda stat: (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        if stamp(before) != stamp(after) or stamp(after) != stamp(final):
            return {"current": False, "reason": "source_changed_during_observation"}
        if len(raw) > allowance:
            budget["limited"] = True
            return {"current": False, "reason": "source_exceeds_observation_limit"}
        return source_binding({"sourceSha256": row["source_sha256"]}, raw)
    except (OSError, ValueError, TypeError, RuntimeError):
        return {"current": False, "reason": "source_unreadable"}


def _references(references: list[dict], row: dict, target: str, root: Path | None, budget: dict) -> list[dict]:
    """Links are target/address references, not acceptance inputs or candidate proof."""
    if root is None:
        return []
    from .pages import _resolve_artifact

    found = []
    for reference in references[:1024]:
        if (reference.get("targetSha256") != target or
                str(reference.get("binaryId")) != str(row["binary_id"]) or
                f'0x{row["addr"]:08x}' not in reference.get("addresses", [])):
            continue
        raw = reference.get("path")
        if not isinstance(raw, str) or not raw or Path(raw).is_absolute() or ".." in Path(raw).parts:
            continue
        try:
            expected = (root / raw).resolve(strict=True)
            if not expected.is_relative_to(root.resolve()) or not expected.is_file():
                continue
            served, error = _resolve_artifact(raw)
            if error or served != expected:
                continue
            digest = budget["receipts"].get(str(expected))
            if digest is None:
                allowance = min(1024 * 1024, budget["bytes"])
                if len(budget["receipts"]) >= 16 or expected.stat().st_size > allowance:
                    budget["limited"] = True
                    continue
                with expected.open("rb") as stream:
                    content = stream.read(allowance + 1)
                budget["bytes"] = max(0, budget["bytes"] - len(content))
                if len(content) > allowance:
                    budget["limited"] = True
                    continue
                digest = hashlib.sha256(content).hexdigest()
                budget["receipts"][str(expected)] = digest
        except (OSError, ValueError, RuntimeError):
            continue
        found.append({"id": digest, "path": raw,
                      "href": "/dashboard/artifact?" + urlencode({"p": raw}),
                      "label": "Recorded target/address receipt", "scope": "target-address-reference",
                      "candidateBound": False})
        if len(found) == 4:
            break
    return found


def _candidate(row: dict, target: str, roots: tuple[Path, ...], references: list[dict], root: Path | None, budget: dict) -> dict:
    key = [row.get(name) for name in _FIELDS[:6]]
    source = _source_state(row, roots, budget)
    source_status = "current" if source["current"] else "stale" if source["reason"] == "source_digest_mismatch" else "unknown"
    target_agrees = row.get("target_sha256") == target
    code = row.get("machine_code")
    size = row.get("size")
    region = None
    if isinstance(code, str) and type(size) is int and 0 < size <= MAX_EVIDENCE_BYTES // 2:
        try:
            raw = bytes.fromhex(code)
            if len(raw) == size:
                region = {"address": row["addr"], "size": size, "sha256": hashlib.sha256(raw).hexdigest()}
        except ValueError:
            pass
    raw_status = "recorded" if target_agrees and region and source["current"] else "stale" if source_status == "stale" else "unknown"
    raw_reason = ("candidate_target_digest_mismatch" if not target_agrees else
                  source["reason"] if not source["current"] else
                  "missing_or_invalid_recorded_region" if region is None else
                  "recorded_region_only_comparison_not_revalidated")
    name = recorded_export_name(row) if target_agrees else None
    return {"id": hashlib.sha256(json.dumps(key, separators=(",", ":")).encode()).hexdigest(),
            "candidate": {name: row.get(name) for name in _FIELDS[:6]},
            "targetSha256": target, "recordedTargetSha256": row.get("target_sha256"),
            "address": f'0x{row["addr"]:08x}', "region": region,
            "sourceState": source_status, "sourceReason": source["reason"],
            "claims": [
                {"kind": "raw-local", "state": raw_status, "accepted": False,
                 "scope": "recorded-target-region", "label": "Recorded region bytes",
                 "summary": "Recorded region bytes; comparison and compiler execution not revalidated.",
                 "reason": raw_reason},
                {"kind": "named-identity", "state": "recorded" if name else "unknown", "accepted": False,
                 "scope": "target-pe-export-name-at-va-v1", "label": "Named identity",
                 "summary": f"Recorded PE export: {name}. Target currentness not rechecked." if name else "No coherent target-bound PE export witness.",
                 "reason": "recorded_ingestion_witness_only" if name else "candidate_target_digest_mismatch" if not target_agrees else "named_witness_unavailable_or_incoherent"},
                {"kind": "placed-contribution", "state": "unavailable", "accepted": False,
                 "scope": "anonymous-source-to-target-contribution", "label": "Placed source contribution",
                 "summary": "No trusted serving-process reconstruction observation. Recorded JSON cannot establish contribution.",
                 "reason": "no_trusted_serving_process_observation"}],
            "receipts": _references(references, row, target, root, budget)}


def project_claims(binary: dict, *, db: Path | None, locator: str = "", program: str = "", slug: str = "",
                   source_roots: tuple[Path, ...] = (), references: list[dict] | None = None,
                   root: Path | None = None, limit: int = MAX_CANDIDATES) -> dict:
    """Observe an exact selected inventory target, without schema writes or work admission."""
    result = {"schema": "agentdecompile.activity-claims/v1", "state": "unavailable",
              "targetSha256": binary.get("sha256"), "candidates": [], "truncated": False,
              "limit": min(MAX_CANDIDATES, max(1, limit)), "checkedAt": None,
              "basis": "Recorded inventory target; only source digest checked at consumption",
              "contributionReason": "no_trusted_serving_process_observation"}
    reason = _bound_target(binary, locator, program, slug)
    if reason:
        return {**result, "reason": reason}
    ids = binary.get("binaryIds") or [binary.get("id")]
    ids = sorted({value for value in ids if type(value) is int and value >= 0})
    result["truncated"] = len(ids) > 64
    ids = ids[:64]
    if not ids or db is None:
        return {**result, "reason": "selected_database_identity_unavailable"}
    connection = None
    try:
        connection = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        # Bound a legacy unindexed scan as well as returned rows. No index/schema mutation.
        steps = 0
        def bounded():
            nonlocal steps
            steps += 1
            return steps > 200
        connection.set_progress_handler(bounded, 1000)
        columns = {r[1] for r in connection.execute("PRAGMA table_info(recovered_function)")}
        if not {"program", "name", "binary_id", "addr", "path"}.issubset(columns):
            return {**result, "reason": "recorded_candidate_schema_unavailable"}
        expressions = []
        for field in _FIELDS:
            if field not in columns:
                expressions.append(f"NULL AS {field}")
            elif field not in {"binary_id", "addr", "size"}:
                expressions.append(f"CASE WHEN length({field}) <= {MAX_EVIDENCE_BYTES} THEN {field} ELSE NULL END AS {field}")
            else:
                expressions.append(field)
        placeholders = ",".join("?" for _ in ids)
        rows = list(connection.execute(f"SELECT {','.join(expressions)} FROM recovered_function WHERE binary_id IN ({placeholders}) ORDER BY binary_id,addr,program,name,path,source_sha256 LIMIT ?", (*ids, result["limit"] + 1)))
        result["truncated"] = result["truncated"] or len(rows) > result["limit"]
        candidates = []
        budget = {"bytes": 8 * 1024 * 1024, "limited": False, "receipts": {}}
        for record in rows[:result["limit"]]:
            row = dict(record)
            if (type(row["addr"]) is not int or not 0 <= row["addr"] <= 9007199254740991 or
                    any(not isinstance(row[key], str) for key in ("program", "name", "path")) or
                    any(row[key] is not None and not isinstance(row[key], str)
                        for key in ("source_sha256", "target_sha256", "semantic_status", "semantic_reason", "semantic_evidence"))):
                continue
            candidates.append(_candidate(row, binary["sha256"], source_roots, references or [], root, budget))
        result.update(state="recorded", reason="bounded_recorded_candidates", candidates=candidates,
                      checkedAt=time.time(), observationLimited=budget["limited"],
                      omittedMalformed=len(rows[:result["limit"]]) - len(candidates))
        return result
    except (OSError, ValueError, sqlite3.Error) as exc:
        return {**result, "reason": "candidate_read_unavailable", "diagnostic": type(exc).__name__}
    finally:
        if connection is not None:
            connection.close()
