"""Fresh direct-compiler full-image receipt.

This is the terminal verification route: it owns a new work directory, invokes
the recovery compiler/link frontdoor, runs a fresh relocation-aware function
receipt from the same sources, then compares the compiler-produced PE with the
shipped PE.  It never starts from or copies the shipped image.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .compile_link import compile_and_link_tree
from .verify_full_image_receipt import _load_objdiff, _sha256
from .verify_recovered_byteexact import main as verify_byteexact_main


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="fresh direct compiler/link plus full-image receipt")
    ap.add_argument("--target", type=Path, required=True)
    ap.add_argument("--src-dir", type=Path, required=True)
    ap.add_argument("--raw", type=Path, required=True)
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--binary-id", type=int, required=True)
    ap.add_argument("--compiler", type=Path, required=True)
    ap.add_argument("--vcroot", type=Path, required=True)
    ap.add_argument("--wineprefix", type=Path, required=True)
    ap.add_argument("--work-dir", type=Path, required=True,
                    help="new, nonexistent directory for this one receipt")
    ap.add_argument("--workers", type=int, default=1)
    args = ap.parse_args(argv)

    target = args.target.resolve()
    work = args.work_dir.resolve()
    errors: list[str] = []
    if not target.is_file():
        errors.append(f"target missing: {target}")
    if not args.src_dir.is_dir():
        errors.append(f"source directory missing: {args.src_dir}")
    if not args.raw.is_file():
        errors.append(f"raw image missing: {args.raw}")
    if not args.db.is_file():
        errors.append(f"database missing: {args.db}")
    if not args.compiler.is_file():
        errors.append(f"compiler wrapper missing: {args.compiler}")
    if not (args.vcroot / "bin" / "link.exe").is_file():
        errors.append(f"VC7 link.exe missing below: {args.vcroot}")
    if work.exists():
        errors.append(f"work directory must not already exist: {work}")
    started_ns = time.time_ns()
    candidate = work / "candidate.exe"
    objdiff = work / "function-objdiff.json"
    build: dict[str, object] = {"startedNs": started_ns, "workDir": str(work)}
    owns_work = False

    if not errors:
        work.mkdir(parents=True)
        owns_work = True
        try:
            linked = compile_and_link_tree(
                args.src_dir, candidate, compiler=str(args.compiler), obj_dir=work / "objects",
                workers=max(1, args.workers), entrypoint=True, vcroot=args.vcroot,
                wineprefix=str(args.wineprefix),
            )
            build["compileLink"] = linked
            verify_rc = verify_byteexact_main([
                "--verified-dir", str(args.src_dir), "--raw", str(args.raw),
                "--compiler", str(args.compiler), "--out", str(objdiff),
                "--workers", str(max(1, args.workers)), "--db", str(args.db),
                "--binary-id", str(args.binary_id), "--no-incremental",
            ])
            build["functionVerifierExit"] = verify_rc
            if not linked.get("ok"):
                errors.append("direct compiler/link did not produce a linked PE")
        except Exception as exc:  # preserve a negative receipt for operator diagnosis
            errors.append(f"direct build raised {exc.__class__.__name__}: {exc}")

    target_info = None
    if target.is_file():
        target_info = {"path": str(target), "size": target.stat().st_size, "sha256": _sha256(target)}
    candidate_info = None
    if candidate.is_file():
        st = candidate.stat()
        candidate_info = {"path": str(candidate), "size": st.st_size,
                          "mtimeNs": st.st_mtime_ns, "sha256": _sha256(candidate)}
        if st.st_mtime_ns < started_ns:
            errors.append("candidate was not written by this direct build")
    else:
        errors.append("direct compiler/link candidate missing")
    objdiff_info, objdiff_error = _load_objdiff(objdiff) if objdiff.is_file() else (None, None)
    if not objdiff.is_file():
        errors.append("fresh function objdiff receipt missing")
    elif objdiff.stat().st_mtime_ns < started_ns:
        errors.append("function objdiff receipt was not written by this direct build")
    elif objdiff_error:
        errors.append(objdiff_error)
    byte_identical = bool(candidate_info and target_info and
                          candidate_info["size"] == target_info["size"] and
                          candidate_info["sha256"] == target_info["sha256"])
    if not byte_identical:
        errors.append("direct compiler/link candidate whole file differs from shipped target")
    verified = not errors
    receipt = {
        "schema": "agentdecompile.direct-compiler-full-image-objdiff-receipt.v1",
        "startedNs": started_ns,
        "target": target_info,
        "candidate": candidate_info,
        "build": build,
        "objdiff": objdiff_info,
        "compilerProducedWholeImage": bool(candidate_info and
                                            isinstance(build.get("compileLink"), dict) and
                                            build["compileLink"].get("ok")),
        "wholeFileByteIdentical": byte_identical,
        "verified": verified,
        "errors": errors,
    }
    out = work / "receipt.json"
    if owns_work:
        out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"verified": verified, "wholeFileByteIdentical": byte_identical,
                      "errors": errors, "out": str(out) if owns_work else None}, indent=2))
    return 0 if verified else 1


if __name__ == "__main__":
    raise SystemExit(main())
