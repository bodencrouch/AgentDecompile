"""Run a full-image build and write a fail-closed terminal receipt.

``objdiff-cli`` compares object files, not PE executables.  A terminal K1
receipt therefore has two required scopes from one fresh build invocation:

* the build command produces a candidate PE and a fresh function-level objdiff
  receipt; and
* this command compares that build-command-produced PE with the shipped target.

The command deliberately never accepts an exact-placement/assembly-floor copy
as its candidate: candidate and target must be different paths, and both the
candidate and objdiff receipt must have a modification time after the build
started. It records build-command provenance but does not claim compiler
provenance until a direct compiler/link integration supplies it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_objdiff(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"unreadable objdiff receipt: {exc}"
    results = doc.get("results")
    if not isinstance(results, list) or not results:
        return None, "objdiff receipt has no nonempty results list"
    total = doc.get("total")
    if not isinstance(total, int) or total != len(results):
        return None, "objdiff receipt is partial or has an inconsistent total"
    matched = sum(bool(row.get("ok")) for row in results if isinstance(row, dict))
    byte_exact = doc.get("byteExact")
    if not isinstance(byte_exact, int) or byte_exact != matched:
        return None, "objdiff receipt has an inconsistent byteExact count"
    if matched != total:
        return None, f"objdiff receipt has {total - matched} nonzero-difference functions"
    return {
        "path": str(path),
        "sha256": _sha256(path),
        "resultCount": total,
        "matchedCount": matched,
    }, None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fresh compiler + objdiff + whole-file receipt")
    ap.add_argument("--target", type=Path, required=True, help="shipped PE")
    ap.add_argument("--candidate", type=Path, required=True, help="full PE produced by --build-command")
    ap.add_argument("--objdiff-receipt", type=Path, required=True,
                    help="fresh verify-byteexact JSON produced by --build-command")
    ap.add_argument("--out", type=Path, required=True, help="terminal receipt JSON")
    ap.add_argument("--cwd", type=Path, default=Path.cwd())
    ap.add_argument("--timeout", type=int, default=7200)
    ap.add_argument("--build-command", nargs=argparse.REMAINDER, required=True,
                    help="argv after --; must freshly create --candidate and --objdiff-receipt")
    args = ap.parse_args(argv)

    target = args.target.resolve()
    candidate = args.candidate.resolve()
    objdiff = args.objdiff_receipt.resolve()
    started_ns = time.time_ns()
    errors: list[str] = []
    if not target.is_file():
        errors.append(f"target missing: {target}")
    if target == candidate:
        errors.append("candidate must not be the shipped target path")
    command = list(args.build_command)
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        errors.append("--build-command requires an argv after --")

    build: dict[str, Any] = {"argv": command, "startedNs": started_ns}
    if not errors:
        try:
            proc = subprocess.run(command, cwd=args.cwd, capture_output=True, text=True,
                                  timeout=args.timeout, check=False)
            build.update({"returncode": proc.returncode, "stdout": proc.stdout[-8000:],
                          "stderr": proc.stderr[-8000:]})
            if proc.returncode != 0:
                errors.append(f"build command failed with exit {proc.returncode}")
        except subprocess.TimeoutExpired:
            build["timedOut"] = True
            errors.append(f"build command exceeded {args.timeout}s")
        except OSError as exc:
            errors.append(f"could not start build command: {exc}")

    candidate_info: dict[str, Any] | None = None
    if candidate.is_file():
        st = candidate.stat()
        candidate_info = {"path": str(candidate), "size": st.st_size,
                          "mtimeNs": st.st_mtime_ns, "sha256": _sha256(candidate)}
        if st.st_mtime_ns < started_ns:
            errors.append("candidate was not freshly written by this build invocation")
    else:
        errors.append(f"candidate missing after build: {candidate}")

    objdiff_info, objdiff_error = _load_objdiff(objdiff) if objdiff.is_file() else (None, None)
    if not objdiff.is_file():
        errors.append(f"objdiff receipt missing after build: {objdiff}")
    elif objdiff.stat().st_mtime_ns < started_ns:
        errors.append("objdiff receipt was not freshly written by this build invocation")
    elif objdiff_error:
        errors.append(objdiff_error)

    target_info: dict[str, Any] | None = None
    if target.is_file():
        target_info = {"path": str(target), "size": target.stat().st_size, "sha256": _sha256(target)}
    byte_identical = bool(candidate_info and target_info
                          and candidate_info["size"] == target_info["size"]
                          and candidate_info["sha256"] == target_info["sha256"])
    if not byte_identical:
        errors.append("candidate whole file differs from shipped target")
    # ``--build-command`` is intentionally argv-only (never a shell string),
    # but an arbitrary command can still copy the target. Keep this wrapper
    # fail-closed until a direct compiler/link integration replaces it.
    errors.append("direct compiler/link provenance is not implemented for this build command")

    receipt = {
        "schema": "agentdecompile.full-image-compiler-objdiff-receipt.v1",
        "startedNs": started_ns,
        "target": target_info,
        "candidate": candidate_info,
        "build": build,
        "objdiff": objdiff_info,
        "wholeFileByteIdentical": byte_identical,
        "buildCommandProducedWholeImage": bool(candidate_info and candidate_info["mtimeNs"] >= started_ns),
        "compilerProducedWholeImage": False,
        "verified": False,
        "errors": errors,
        "claimBoundary": ("verified=true proves only fresh build-command provenance plus object-level "
                          "objdiff evidence and whole-file equality. compilerProducedWholeImage remains "
                          "false until this gate invokes a direct compiler/link integration."),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"verified": receipt["verified"], "wholeFileByteIdentical": byte_identical,
                      "errors": errors, "out": str(args.out)}, indent=2))
    return 0 if receipt["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
