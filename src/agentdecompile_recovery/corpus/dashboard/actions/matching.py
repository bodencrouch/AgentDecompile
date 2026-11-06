"""Atomic candidate compile and objdiff verification for the workbench."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import threading

from pathlib import Path
from typing import Any

from agentdecompile_cli.mcp_utils.decomp_match import build_decomp_match_payload

from agentdecompile_recovery.gnu_c_compiler import GnuCCompiler
from agentdecompile_recovery.objdiff_verification import parse_objdiff_report

SCHEMA = "agentdecompile.workbench-match-candidate.v1"
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_CONTEXT_BYTES = 2 * 1024 * 1024
_FUNCTION = re.compile(r"^[A-Za-z_][A-Za-z0-9_@$?]*$")
_PRESET_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _preset_path(preset_id: str) -> Path:
    if not _PRESET_ID.fullmatch(preset_id):
        raise ValueError("compilerPreset must be an approved preset ID.")
    configured = os.environ.get("AGENT_DECOMPILE_MATCHING_PRESET_ROOT", "").strip()
    if not configured:
        raise ValueError("Matching is unavailable until AGENT_DECOMPILE_MATCHING_PRESET_ROOT is configured.")
    root = Path(configured).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Configured matching preset root is not a directory: {root}")
    path = (root / f"{preset_id}.json").resolve()
    if not _within(path, root) or not path.is_file():
        raise ValueError(f"Approved compiler preset was not found: {preset_id}")
    return path


def _load_preset(path: Path, *, artifact_hash: str, function: str) -> dict[str, Any]:
    try:
        preset_bytes = path.read_bytes()
        data = json.loads(preset_bytes.decode("utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError(f"Compiler preset is not readable JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise TypeError("Compiler preset must be a JSON object.")
    if str(data.get("artifactHash") or "").strip().lower() != artifact_hash:
        raise ValueError("Compiler preset is not bound to the selected artifactHash.")
    script = data.get("compilerScript")
    if not isinstance(script, str) or not script.strip():
        raise ValueError("Compiler preset requires compilerScript.")
    root = Path(str(data.get("projectRoot") or path.parent)).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Compiler preset projectRoot is not a directory: {root}")
    targets = data.get("targets")
    target = targets.get(function) if isinstance(targets, dict) else None
    if not isinstance(target, dict):
        raise TypeError(f"Compiler preset has no target binding for function: {function}")
    target_path = Path(str(target.get("path") or "")).expanduser()
    if not target_path.is_absolute():
        target_path = root / target_path
    target_path = target_path.resolve()
    if not _within(target_path, root) or not target_path.is_file():
        raise ValueError("Compiler preset target must be a file beneath projectRoot.")
    target_revision = str(target.get("sha256") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", target_revision):
        raise ValueError("Compiler preset target requires a SHA-256 revision.")
    target_symbol = str(target.get("symbol") or function).strip()
    if not target_symbol:
        raise ValueError("Compiler preset target requires a symbol.")
    context = ""
    context_path = data.get("contextPath")
    if context_path:
        resolved = Path(str(context_path)).expanduser()
        if not resolved.is_absolute():
            resolved = path.parent / resolved
        resolved = resolved.resolve()
        if not _within(resolved, root) or not resolved.is_file():
            raise ValueError("Compiler preset contextPath must be a file beneath projectRoot.")
        raw = resolved.read_bytes()
        if len(raw) > MAX_CONTEXT_BYTES:
            raise ValueError("Compiler preset context exceeds the 2 MiB limit.")
        context = raw.decode("utf-8")
    try:
        timeout = max(1, min(1800, int(data.get("timeoutSeconds", 300))))
    except (TypeError, ValueError) as exc:
        raise ValueError("Compiler preset timeoutSeconds must be an integer.") from exc
    return {
        "id": str(data.get("id") or path.stem),
        "compilerScript": script,
        "projectRoot": root,
        "contextContent": context,
        "timeoutSeconds": timeout,
        "targetPath": target_path,
        "targetRevision": target_revision,
        "targetSymbol": target_symbol,
        "fingerprint": _sha256_bytes(preset_bytes + b"\0" + context.encode("utf-8")),
    }


def _strict_function_zero(output: str, symbol: str, report: dict[str, Any]) -> bool:
    """Require complete two-sided evidence for the exact requested symbol."""
    if report.get("status") != "matched" or report.get("differences") != 0:
        return False
    if report.get("objdiffExit") != 0 or report.get("fallback"):
        return False
    try:
        parsed = json.loads(output)
    except (TypeError, ValueError):
        return False
    if not isinstance(parsed, dict):
        return False
    rows = []
    for side in ("left", "right"):
        value = parsed.get(side)
        symbols = value.get("symbols") if isinstance(value, dict) else None
        row = next(
            (item for item in symbols or []
             if isinstance(item, dict) and str(item.get("name") or "") == symbol),
            None,
        )
        if (not isinstance(row, dict) or row.get("kind") != "SYMBOL_FUNCTION"
                or row.get("match_percent") != 100):
            return False
        instructions = row.get("instructions")
        if not isinstance(instructions, list) or not instructions:
            return False
        # objdiff 3.7 omits ``diff_kind`` for aligned instructions and only
        # emits the field for an actual difference. Older releases emitted
        # ``DIFF_NONE`` explicitly. Both encodings are valid only after the
        # exact symbol has a 100% two-sided match above.
        if any(
            not isinstance(item, dict)
            or not isinstance(item.get("instruction"), dict)
            or item.get("diff_kind") not in (None, "DIFF_NONE")
            for item in instructions
        ):
            return False
        rows.append(instructions)
    return len(rows[0]) == len(rows[1])


def _result(phase: str, *, artifact_hash: str, function: str, candidate_revision: str,
            target_revision: str | None = None, preset: str | None = None,
            preset_fingerprint: str | None = None,
            stages: list[dict[str, Any]] | None = None, error: str = "",
            receipt: dict[str, Any] | None = None) -> dict[str, Any]:
    verified = phase == "objdiff-verified"
    attempt_id = _sha256_bytes(
        f"{artifact_hash}:{function}:{target_revision or 'unresolved'}:{candidate_revision}:"
        f"{preset or 'unresolved'}:{preset_fingerprint or 'unresolved'}".encode()
    )
    return {
        "schema": SCHEMA,
        "attemptId": attempt_id,
        "phase": phase,
        "artifactHash": artifact_hash,
        "function": function,
        "candidateRevision": candidate_revision,
        "targetRevision": target_revision,
        "compilerPreset": preset,
        "compilerPresetFingerprint": preset_fingerprint,
        "verified": verified,
        "stages": stages or [],
        "receipt": receipt,
        "error": error or None,
        "claimBoundary": (
            "Objdiff reported zero differences for these exact target and candidate revisions."
            if verified else
            "Candidate source, compilation, and job completion are not byte proof; only an objdiff-zero receipt verifies a match."
        ),
    }


def execute(params: dict[str, Any], cancel: threading.Event) -> tuple[int, str]:
    """Compile the submitted draft and verify its object against one target object."""
    source = str(params.get("candidateSource") or "")
    source_bytes = source.encode("utf-8")
    artifact_hash = str(params.get("artifactHash") or "").strip().lower()
    function = str(params.get("function") or "").strip()
    candidate_revision = _sha256_bytes(source_bytes)
    stages: list[dict[str, Any]] = [
        {"phase": "candidate", "status": "ok", "candidateRevision": candidate_revision}
    ]

    try:
        if len(source_bytes) > MAX_SOURCE_BYTES:
            raise ValueError("Candidate source exceeds the 2 MiB limit.")
        if not re.fullmatch(r"[0-9a-f]{64}", artifact_hash):
            raise ValueError("artifactHash must be a SHA-256 hex digest.")
        if not _FUNCTION.fullmatch(function):
            raise ValueError("function must be a safe C symbol name.")
        preset_id = str(params.get("compilerPreset") or "").strip()
        preset = _load_preset(_preset_path(preset_id), artifact_hash=artifact_hash, function=function)
        target_revision = preset["targetRevision"]
        requested_target_revision = str(params.get("targetRevision") or "").strip().lower()
        if requested_target_revision != target_revision:
            raise ValueError(
                "targetRevision does not match the selected target object; refresh the target before retrying."
            )
    except (OSError, TypeError, UnicodeError, ValueError) as exc:
        payload = _result("failed", artifact_hash=artifact_hash, function=function,
                          candidate_revision=candidate_revision, stages=stages, error=str(exc))
        return 1, json.dumps(payload, default=str)

    if cancel.is_set():
        payload = _result("cancelled", artifact_hash=artifact_hash, function=function,
                          candidate_revision=candidate_revision, target_revision=target_revision,
                          preset=preset["id"], preset_fingerprint=preset["fingerprint"],
                          stages=stages, error="Cancelled before compilation.")
        return 1, json.dumps(payload)

    with tempfile.TemporaryDirectory(prefix="agentdecompile-match-") as attempt_dir:
        target = Path(attempt_dir) / "target.o"
        shutil.copy2(preset["targetPath"], target)
        if _sha256_file(target) != target_revision:
            payload = _result("failed", artifact_hash=artifact_hash, function=function,
                              candidate_revision=candidate_revision, target_revision=target_revision,
                              preset=preset["id"], preset_fingerprint=preset["fingerprint"], stages=stages,
                              error="Approved target bytes no longer match the compiler preset revision.")
            return 1, json.dumps(payload)
        compiler = GnuCCompiler(
            preset["compilerScript"], preset["projectRoot"], preset["timeoutSeconds"]
        )
        compiled = compiler.compile(function, source, preset["contextContent"])
        if not compiled.success or compiled.obj_path is None:
            stages.append({
                "phase": "compile",
                "status": "failed",
                "error": compiled.error_message or "Compilation failed.",
                "diagnostics": [vars(item) for item in compiled.compilation_errors],
            })
            payload = _result("compile-failed", artifact_hash=artifact_hash, function=function,
                              candidate_revision=candidate_revision, target_revision=target_revision,
                              preset=preset["id"], preset_fingerprint=preset["fingerprint"], stages=stages,
                              error=compiled.error_message or "Compilation failed.")
            return 1, json.dumps(payload)

        compiled_path = compiled.obj_path
        try:
            compiled_revision = _sha256_file(compiled_path)
            stages.append({"phase": "compile", "status": "ok", "compiledRevision": compiled_revision})
            if cancel.is_set():
                payload = _result("cancelled", artifact_hash=artifact_hash, function=function,
                                  candidate_revision=candidate_revision, target_revision=target_revision,
                                  preset=preset["id"], preset_fingerprint=preset["fingerprint"],
                                  stages=stages, error="Cancelled before objdiff.")
                return 1, json.dumps(payload)
            objdiff = build_decomp_match_payload(
                tool="objdiff",
                objdiff_mode="diff",
                target_object_path=target,
                base_object_path=compiled_path,
                symbol=preset["targetSymbol"],
            )
            scan = objdiff.get("scan") if isinstance(objdiff.get("scan"), dict) else {}
            if scan.get("available") is False:
                stages.append({"phase": "objdiff", "status": "unavailable", "error": scan.get("skipped")})
                payload = _result("provider-unavailable", artifact_hash=artifact_hash, function=function,
                                  candidate_revision=candidate_revision, target_revision=target_revision,
                                  preset=preset["id"], preset_fingerprint=preset["fingerprint"], stages=stages,
                                  error=str(scan.get("skipped") or "objdiff-cli is unavailable."))
                return 1, json.dumps(payload)
            output = str(scan.get("stdout") or "")
            report = parse_objdiff_report(int(scan.get("exitCode", -1)), output)
            status = str(report.get("status") or "error")
            strict_zero = _strict_function_zero(output, preset["targetSymbol"], report)
            stages.append({"phase": "objdiff", "status": status, "differences": report.get("differences")})
            receipt = {
                "schema": "agentdecompile.objdiff-receipt.v1",
                "id": _sha256_bytes(
                    f"{artifact_hash}:{function}:{target_revision}:{candidate_revision}:{compiled_revision}:"
                    f"{preset['id']}:{preset['fingerprint']}".encode()
                ),
                "artifactHash": artifact_hash,
                "function": function,
                "targetRevision": target_revision,
                "candidateRevision": candidate_revision,
                "compiledRevision": compiled_revision,
                "compilerPreset": preset["id"],
                "compilerPresetFingerprint": preset["fingerprint"],
                "status": status if status != "matched" or strict_zero else "incomplete",
                "rawStatus": status,
                "differences": report.get("differences"),
                "objdiffExit": report.get("objdiffExit"),
                "detailLevel": report.get("detailLevel"),
                "mismatchHistogram": report.get("mismatchHistogram") or {},
                "alignedDiff": report.get("alignedDiff") or [],
            }
            if strict_zero:
                payload = _result("objdiff-verified", artifact_hash=artifact_hash, function=function,
                                  candidate_revision=candidate_revision, target_revision=target_revision,
                                  preset=preset["id"], preset_fingerprint=preset["fingerprint"],
                                  stages=stages, receipt=receipt)
                return 0, json.dumps(payload)
            if status == "mismatched":
                payload = _result("mismatch", artifact_hash=artifact_hash, function=function,
                                  candidate_revision=candidate_revision, target_revision=target_revision,
                                  preset=preset["id"], preset_fingerprint=preset["fingerprint"],
                                  stages=stages, receipt=receipt)
                return 0, json.dumps(payload)
            payload = _result("failed", artifact_hash=artifact_hash, function=function,
                              candidate_revision=candidate_revision, target_revision=target_revision,
                              preset=preset["id"], preset_fingerprint=preset["fingerprint"],
                              stages=stages, receipt=receipt,
                              error=(
                                  "Objdiff output lacked complete two-sided zero-difference evidence for the requested symbol."
                                  if status == "matched" else
                                  str(report.get("message") or "Objdiff did not produce usable proof.")
                              ))
            return 1, json.dumps(payload)
        except (OSError, ValueError) as exc:
            stages.append({"phase": "objdiff", "status": "failed", "error": str(exc)})
            payload = _result("failed", artifact_hash=artifact_hash, function=function,
                              candidate_revision=candidate_revision, target_revision=target_revision,
                              preset=preset["id"], preset_fingerprint=preset["fingerprint"],
                              stages=stages, error=str(exc))
            return 1, json.dumps(payload)
        finally:
            shutil.rmtree(compiled_path.parent, ignore_errors=True)
