"""Compiler-profile corpus selection and sweep primitives.

This module turns already verified matched examples into compiler-forensics
evidence. It is intentionally not a source-recovery claim: matching source still
requires each promoted function to pass its own objdiff gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .package_verify import compile_with_msvc, prepare_msvc_invocation, write_bound_msvc_wrapper
from .corpus import toolchain_identity
from .source_parity_synthesize import run_objdiff


DEFAULT_FLAGS = [
    ("od_oyminus_gsminus", ["/Od", "/Oy-", "/GS-"]),
    ("od_gz_oyminus_gsminus", ["/Od", "/GZ", "/Oy-", "/GS-"]),
    ("od_rtc1_oyminus_gsminus", ["/Od", "/RTC1", "/Oy-", "/GS-"]),
    ("od_g7_oyminus_gsminus", ["/Od", "/G7", "/Oy-", "/GS-"]),
    ("od_oi_oyminus_gsminus", ["/Od", "/Oi", "/Oy-", "/GS-"]),
    ("o1_oyminus_gsminus", ["/O1", "/Oy-", "/GS-"]),
    ("o2_oyminus_gsminus", ["/O2", "/Oy-", "/GS-"]),
    ("o2_oy_gsminus", ["/O2", "/Oy", "/GS-"]),
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_case_inputs(selected: list[dict[str, Any]], scratch: Path, *, receipt_paths: tuple[Path, ...] = ()) -> None:
    """Reject unsafe output components and inputs threatened by scratch writes."""
    for row in selected:
        validate_output_name(row.get("name"), "case")
        evidence_dir = Path(str(row.get("outDir", "")))
        for path in (Path(str(row.get("candidateSource") or evidence_dir / "candidate.c")), evidence_dir / "target.obj"):
            resolved = path.resolve()
            if resolved.is_relative_to(scratch.resolve()) or resolved in {receipt.resolve() for receipt in receipt_paths}:
                raise ValueError("Calibration source and target inputs must be outside the scratch output subtree.")


def validate_output_name(name: Any, label: str) -> None:
    if not isinstance(name, str) or not name.strip() or name in {".", ".."} or any(char in name for char in ("/", "\\", "\x00")):
        raise ValueError(f"Each {label} name must be one nonempty safe output path component.")


def admit_measured_profile(
    *,
    matched_examples: Path | None,
    out_dir: Path,
    profile_path: Path,
    program_fingerprint: str,
    architecture: str,
    timeout: int = 120,
    max_cases: int = 6,
    profiles: list[str] | None = None,
    flag_sets: list[str] | None = None,
    wine: str = "wine",
    wineprefix: Path | None = None,
    probe_inventory: Path | None = None,
    target_receipt: Path | None = None,
) -> dict[str, Any]:
    """Create a target-bound compiler profile only from zero-diff probes.

    The profile corpus is x86/MSVC-specific.  An absent or unsuitable corpus
    writes an explicit admission receipt and deliberately leaves the target
    without a compiler profile.
    """
    out_dir = out_dir.expanduser().resolve()
    if max_cases < 1 or timeout < 1:
        raise ValueError("Measured calibration requires positive max-cases and timeout.")
    profile_path = profile_path.expanduser().resolve()
    profile_out = (out_dir / "profile-corpus").resolve()
    if not profile_out.is_relative_to(out_dir) or profile_out == out_dir:
        raise ValueError("Profile corpus must remain within its reserved out-dir subtree.")
    if profile_path == out_dir or not profile_path.is_relative_to(out_dir) or profile_path.is_relative_to(profile_out):
        raise ValueError("Admission profile must be inside out-dir and outside its profile-corpus subtree.")
    if profile_path in {out_dir / "compiler-profile-admission.json", out_dir / "compiler-profile-compile.sh"}:
        raise ValueError("Admission profile must not overwrite its receipt or compile wrapper.")
    if profile_path.is_dir() or any(parent.exists() and not parent.is_dir() for parent in profile_path.parents):
        raise ValueError("Admission profile must name a file with directory parents.")
    if profiles is not None and any(not value.split("=", 1)[-1].strip() for value in profiles):
        raise ValueError("Each compiler profile must specify a compiler root.")
    profiles = [f"{name}={root}" for name, root in (parse_profile(value) for value in profiles)] if profiles is not None else None
    for label, configurations in (("compiler profile", [parse_profile(value) for value in profiles] if profiles is not None else []), ("flag set", [parse_flag_set(value) for value in flag_sets] if flag_sets is not None else [])):
        names = [name for name, _ in configurations]
        for name in names:
            validate_output_name(name, label)
        if len(names) != len(set(names)):
            raise ValueError(f"Each {label} must have a unique name.")
        if any(not value for _, value in configurations):
            raise ValueError(f"Each {label} must have a nonempty configuration.")
    if wineprefix is not None:
        wineprefix = wineprefix.expanduser().resolve()
    if profiles:
        for value in profiles:
            _, root = parse_profile(value)
            if not (root / "bin" / "cl.exe").is_file():
                raise ValueError(f"Compiler profile has no bin/cl.exe: {root}")
    if (probe_inventory is None) != (target_receipt is None):
        raise ValueError("--probe-inventory and --target-receipt must be supplied together.")
    input_identities = {}
    if matched_examples is not None:
        matched_examples = matched_examples.expanduser().resolve()
        if matched_examples.is_relative_to(profile_out):
            raise ValueError("Admission evidence must be outside the cleaned profile-corpus subtree.")
    receipt_path = out_dir / "compiler-profile-admission.json"
    admission_outputs = (profile_path, receipt_path, out_dir / "compiler-profile-compile.sh")
    if matched_examples is not None and matched_examples in {path.resolve() for path in admission_outputs}:
        raise ValueError("Admission outputs must not overwrite caller matched examples.")
    if probe_inventory is not None:
        from .source_parity_probes import prepare_probes
        if profile_path.is_relative_to(out_dir / "calibration-probes"):
            raise ValueError("Admission profile must be outside generated calibration-probes.")
        matched_examples, input_identities = prepare_probes(
            probe_inventory, target_receipt, out_dir, program_fingerprint, architecture, max_cases,
        )
    if matched_examples is not None and matched_examples in {path.resolve() for path in admission_outputs}:
        raise ValueError("Admission outputs must not overwrite matched examples.")
    if matched_examples is not None and matched_examples.is_file():
        validate_case_inputs(
            select_cases(list(iter_jsonl(matched_examples)), max_cases),
            profile_out,
            receipt_paths=admission_outputs,
        )
    base = {
        "schema": "agentdecompile.measured-compiler-profile-admission.v1",
        "programFingerprint": program_fingerprint,
        "architecture": architecture,
        "profilePath": str(profile_path),
        "claimBoundary": "A measured compiler profile guides compilation; it is not a source or byte-identity claim.",
    }
    if not program_fingerprint:
        result = {**base, "state": "awaiting-program-fingerprint", "reason": "The analyzed program has no stable fingerprint for compiler-profile binding."}
        write_json(receipt_path, result)
        return result
    from .source_parity_probes import x86_32, validate_bound_rows, recheck
    if not x86_32(architecture):
        result = {**base, "state": "not-applicable", "reason": "No x86/MSVC profile sweep is defined for this architecture."}
        write_json(receipt_path, result)
        return result
    if matched_examples is None or not matched_examples.is_file():
        result = {**base, "state": "awaiting-known-source-evidence", "reason": "No verified candidate-source and target-object probe corpus is available for this program."}
        write_json(receipt_path, result)
        return result

    bound_rows = list(iter_jsonl(matched_examples))
    input_identities.update(validate_bound_rows(bound_rows, program_fingerprint, architecture))
    input_identities[matched_examples] = _sha256(matched_examples)
    for path in input_identities:
        if path.resolve().is_relative_to(profile_out) or path.resolve() in {output.resolve() for output in admission_outputs}:
            raise ValueError(f"Calibration evidence overlaps cleaned scratch or admission output: {path}")
    profile_out.mkdir(parents=True, exist_ok=True)
    attempt_dir = Path(tempfile.mkdtemp(prefix="attempt-", dir=profile_out))
    sweep_argv = [
        "--matched-examples", str(matched_examples),
        "--out-dir", str(attempt_dir),
        "--max-cases", str(max_cases),
        "--timeout", str(timeout),
        "--wine", wine,
    ]
    if wineprefix is not None:
        sweep_argv.extend(["--wineprefix", str(wineprefix)])
    for value in profiles or []:
        sweep_argv.extend(["--profile", value])
    for value in flag_sets or []:
        sweep_argv.extend(["--flag-set", value])
    sweep_parser = profile_parser()
    exit_code = execute_sweep(sweep_parser.parse_args(sweep_argv), sweep_parser, prune_disqualified=True)
    summary_path = attempt_dir / "summary.json"
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        summary = {}
    attempt_evidence = {"profileCorpusAttempt": str(attempt_dir)}
    for key, path in (("summary", summary_path), ("selection", attempt_dir / "selected-cases.json"),
                      ("summaryJsonl", attempt_dir / "runs/summary.jsonl")):
        attempt_evidence[key] = str(path)
        if path.is_file():
            attempt_evidence[f"{key}Sha256"] = _sha256(path)
    base.update(attempt_evidence)
    selected = int(summary.get("selectedCases") or 0)
    try:
        selection = json.loads(Path(summary["selectedCasesPath"]).read_text(encoding="utf-8"))
        case_names = [row["name"] for row in selection["cases"]]
        selection_valid = (
            selection.get("selectedCount") == selected
            and len(case_names) == selected
            and all(isinstance(name, str) and name.strip() for name in case_names)
            and len(set(case_names)) == selected
        )
    except (OSError, ValueError, KeyError, TypeError):
        case_names = []
        selection_valid = False
    if not selection_valid:
        result = {**base, "state": "insufficient-evidence", "reason": "Calibration requires an unambiguous selection receipt with a distinct name for every probe.", "summary": str(summary_path)}
        write_json(receipt_path, result)
        return result
    rows = list(iter_jsonl(Path(str(summary.get("summaryJsonl") or attempt_dir / "runs/summary.jsonl"))))
    # `run_objdiff()` records an objdump comparison only as diagnostic fallback
    # when objdiff itself fails.  A calibration profile must be grounded in the
    # native objdiff receipt, because later promotion relies on that same gate.
    exact = [row for row in rows if native_exact(row) and row.get("bindingValid") is True
             and isinstance(row.get("binding"), dict)
             and row["binding"].get("schema") == "agentdecompile.msvc-invocation-binding/v1"
             and toolchain_identity.verify(row["binding"].get("evidence", {}))]
    expected_cases = set(case_names)
    coverage: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in exact:
        key = (str(row.get("profile") or ""), str(row.get("flagSet") or ""))
        if all(key) and row.get("case") in expected_cases:
            coverage[key].add(row["case"])
    # Count distinct selected probes, never receipt rows. Multiple configurations
    # can legitimately match the same corpus; that does not invalidate any of them.
    winners = sorted(key for key, cases in coverage.items() if cases == expected_cases
        and len({row["binding"].get("bindingSha256") for row in exact
                 if (row.get("profile"), row.get("flagSet")) == key}) == 1)
    if exit_code or not selected:
        reason = "The profile corpus did not select any usable known-source probes." if not selected else "Compiler profile probing did not complete."
        result = {**base, "state": "insufficient-evidence", "reason": reason, "summary": str(summary_path), "selectedCases": selected}
        write_json(receipt_path, result)
        return result
    if not winners:
        result = {
            **base, "state": "insufficient-evidence",
            "reason": "No single compiler and flag set produced zero-diff output for every selected probe.",
            "summary": str(summary_path), "selectedCases": selected, "zeroDiffByProfile": {f"{key[0]} {key[1]}": len(cases) for key, cases in coverage.items()},
        }
        write_json(receipt_path, result)
        return result

    winner = winners[0]
    winner_count = len(coverage[winner])

    roots = {str(row.get("name")): row.get("root") for row in summary.get("compilerProfiles") or []}
    flag_sets = {str(row.get("name")): list(row.get("args") or []) for row in summary.get("flagSets") or []}
    compiler_root_value = roots.get(winner[0])
    compiler_root = Path(compiler_root_value) if isinstance(compiler_root_value, str) and compiler_root_value.strip() else None
    flags = flag_sets.get(winner[1])
    if compiler_root is None or not compiler_root.is_absolute() or not compiler_root.is_dir() or not flags:
        result = {**base, "state": "insufficient-evidence", "reason": "The zero-diff probe result lacks a reusable compiler root or flags.", "summary": str(summary_path)}
        write_json(receipt_path, result)
        return result
    wrapper = out_dir / "compiler-profile-compile.sh"
    recheck(input_identities)
    binding = next(row["binding"] for row in exact
                   if (row.get("profile"), row.get("flagSet")) == winner)
    try:
        prepared = prepare_msvc_invocation(source=Path("candidate.c"), args=flags,
            msvc_root=compiler_root, wine=wine, wineprefix=wineprefix, strict_c=True)
        toolchain_identity.compare_live_binding(binding, **{key: prepared[key] for key in
            ("command", "env", "requested_args", "policy")})
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {**base, "state": "insufficient-evidence",
                  "reason": f"Winning compiler binding failed live revalidation: {exc}"}
        write_json(receipt_path, result)
        return result
    write_bound_msvc_wrapper(wrapper=wrapper, args=flags, timeout=timeout,
        msvc_root=compiler_root, wine=wine, wineprefix=wineprefix, binding=binding)
    profile = {
        "schema": "agentdecompile.measured-compiler-profile.v1",
        "programFingerprint": program_fingerprint,
        "architecture": architecture,
        "compilerScript": str(wrapper),
        "compilerRoot": str(compiler_root),
        "profile": winner[0],
        "flagSet": winner[1],
        "compilerArgs": flags,
        "binding": binding,
        "wine": wine,
        "wineprefix": str(wineprefix) if wineprefix is not None else None,
        "profileCorpusSummary": str(summary_path),
        "profileCorpusSummarySha256": _sha256(summary_path),
        "profileCorpusAttempt": str(attempt_dir),
        "profileCorpusSelection": attempt_evidence["selection"],
        "profileCorpusSelectionSha256": attempt_evidence["selectionSha256"],
        "profileCorpusSummaryJsonl": attempt_evidence["summaryJsonl"],
        "profileCorpusSummaryJsonlSha256": attempt_evidence["summaryJsonlSha256"],
        "zeroDiffProbeCount": winner_count,
        "selectedProbeCount": selected,
        "zeroDiffConfigurations": [{"profile": key[0], "flagSet": key[1]} for key in winners],
        "probeManifest": str(matched_examples),
        "probeManifestSha256": input_identities[matched_examples],
        "originalTargetSha256": bound_rows[0]["targetSha256"],
        "claimBoundary": "This configuration won actual zero-diff calibration probes. Each recovered function still requires its own objdiff receipt.",
    }
    write_json(profile_path, profile)
    result = {**base, "state": "admitted", "summary": str(summary_path), "summarySha256": profile["profileCorpusSummarySha256"], "compilerProfile": str(profile_path), "zeroDiffProbes": winner_count}
    write_json(receipt_path, result)
    return result


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")


def selectable(row: dict[str, Any]) -> bool:
    out_dir = Path(str(row.get("outDir", "")))
    candidate = Path(str(row.get("candidateSource") or out_dir / "candidate.c"))
    target = out_dir / "target.obj"
    from .source_parity_probes import SCHEMA
    hypothesis = row.get("schema") == SCHEMA and row.get("hypothesis") is True
    available = (candidate.exists() and target.exists()) or (hypothesis and row.get("_probe_metadata") is True)
    return (bool(row.get("matched")) or hypothesis) and available


def diversity_key(row: dict[str, Any]) -> tuple[str, str]:
    kind = str(row.get("kind", "unknown"))
    tags = set(row.get("tags", []))
    if "fastcall-accessor" in tags:
        family = "fastcall-accessor"
    elif "absolute-global" in tags:
        family = "absolute-global"
    elif "stdcall-ret" in tags:
        family = "stdcall"
    elif "cdecl-ret" in tags:
        family = "cdecl"
    elif "compiler-profile-probe" in tags:
        family = "compiler-profile-probe"
    else:
        family = "other"
    return (family, kind)


def select_cases(rows: list[dict[str, Any]], max_cases: int) -> list[dict[str, Any]]:
    candidates = [row for row in rows if selectable(row)]
    buckets: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for row in candidates:
        family, kind = diversity_key(row)
        buckets[family][kind].append(row)
    for family_buckets in buckets.values():
        for bucket in family_buckets.values():
            bucket.sort(key=lambda row: (-int(row.get("bodyBytes") or 0), str(row.get("entry"))))

    selected: list[dict[str, Any]] = []
    family_order = ["fastcall-accessor", "absolute-global", "stdcall", "cdecl", "compiler-profile-probe", "other"]
    while len(selected) < max_cases:
        progressed = False
        for family in [item for item in family_order if item in buckets] + sorted(set(buckets) - set(family_order)):
            for kind in sorted(buckets[family]):
                bucket = buckets[family][kind]
                if not bucket:
                    continue
                selected.append(bucket.pop(0))
                progressed = True
                break
            if len(selected) >= max_cases:
                break
        if not progressed:
            break
    return selected


def parse_profile(value: str, *, base: Path | None = None) -> tuple[str, Path]:
    if "=" in value:
        name, root = value.split("=", 1)
    else:
        root_path = Path(value)
        name = root_path.name or "msvc"
        root = value
    root_path = Path(root).expanduser()
    if base is not None and not root_path.is_absolute():
        root_path = base / root_path
    return name.strip() or "msvc", root_path.resolve()


def parse_flag_set(value: str) -> tuple[str, list[str]]:
    if "=" in value:
        name, flags = value.split("=", 1)
    else:
        flags = value
        name = "_".join(part.strip("/-").lower() for part in flags.replace(",", " ").split() if part) or "custom"
    return name.strip() or "custom", [part for part in flags.replace(",", " ").split() if part]


def default_profiles(*, base: Path | None = None) -> list[tuple[str, Path]]:
    profiles: list[tuple[str, Path]] = []
    env_root = os.environ.get("VC_ROOT")
    if env_root:
        profiles.append(parse_profile(f"env-vc-root={env_root}", base=base))
    vc71 = Path("target/toolchain-acquire/vctoolkit2003/msitools-extract/Program Files/Microsoft Visual C++ Toolkit 2003")
    if base is not None:
        vc71 = base / vc71
    if (vc71 / "bin" / "cl.exe").exists():
        profiles.append(("vc71", vc71.resolve()))
    vc80 = Path("/run/media/brunner56/MyBook/Toolchains/msvc8.0-main")
    if (vc80 / "bin" / "cl.exe").exists():
        profiles.append(("vc80", vc80.resolve()))
    return profiles


def compiler_banner(evidence: dict[str, Any]) -> str:
    return str(evidence.get("components", {}).get("compiler", {}).get("version_text")
               or evidence.get("reason") or "Compiler version evidence unavailable")[:1000]


def native_exact(row: dict[str, Any]) -> bool:
    """The common native objdiff gate for pruning and measured admission."""
    try:
        return (row.get("status") == "matched" and row.get("differences") is not None
                and int(row["differences"]) == 0 and int(row.get("objdiffExit", -1)) == 0)
    except (ValueError, TypeError):
        return False


def summarize(summary_jsonl: Path) -> dict[str, Any]:
    rows = list(iter_jsonl(summary_jsonl))
    by_profile_flag: Counter[str] = Counter()
    matched = 0
    mismatched = 0
    compile_failed = 0
    missing_input = 0
    pruned = 0
    best_by_case: dict[str, dict[str, Any]] = {}
    for row in rows:
        status = row.get("status")
        if status == "pruned":
            pruned += 1
            continue
        if status == "matched" and row.get("differences") == 0:
            matched += 1
            by_profile_flag[f"{row.get('profile')} {row.get('flagSet')}"] += 1
        elif status == "compile-failed":
            compile_failed += 1
        elif status == "missing-input":
            missing_input += 1
        else:
            mismatched += 1

        case = str(row.get("case"))
        score = 100.0 if status == "matched" and row.get("differences") == 0 else float(row.get("bestMatchPercent") or -1)
        current = best_by_case.get(case)
        if current is None or score > float(current.get("score", -1)):
            best_by_case[case] = {
                "case": case,
                "score": score,
                "status": status,
                "profile": row.get("profile"),
                "flagSet": row.get("flagSet"),
                "compilerArgs": row.get("compilerArgs"),
            }
    return {
        "attempts": len(rows) - pruned,
        "receiptRows": len(rows),
        "prunedReceipts": pruned,
        "compileCalls": len(rows) - pruned - missing_input,
        "compileExecutions": sum(row.get("compilerInvoked") is True for row in rows
                                 if row.get("status") not in {"pruned", "missing-input"}),
        "matchedAttempts": matched,
        "mismatchedAttempts": mismatched,
        "compileFailedAttempts": compile_failed,
        "missingInputAttempts": missing_input,
        "profileFlagMatches": dict(by_profile_flag.most_common()),
        "bestByCase": sorted(best_by_case.values(), key=lambda row: row["case"]),
    }


def select_report(selected: list[dict[str, Any]], matched_examples: Path, max_cases: int) -> dict[str, Any]:
    return {
        "schema": "agentdecompile.source-parity-profile-corpus-selection.v1",
        "matchedExamples": str(matched_examples),
        "maxCases": max_cases,
        "selectedCount": len(selected),
        "cases": [
            {
                "name": row.get("name"),
                "entry": row.get("entry"),
                "kind": row.get("kind"),
                "tags": row.get("tags", []),
                "outDir": row.get("outDir"),
                "candidateSource": row.get("candidateSource"),
            }
            for row in selected
        ],
        "selectionRule": "round-robin by instruction family and matched kind, preferring larger examples inside each bucket",
    }


def run_sweep(
    *,
    selected: list[dict[str, Any]],
    out_dir: Path,
    profiles: list[tuple[str, Path]],
    flag_sets: list[tuple[str, list[str]]],
    wine: str,
    wineprefix: Path | None,
    timeout: int,
    clean: bool,
    prune_disqualified: bool = False,
) -> Path:
    runs_dir = out_dir / "runs"
    if clean and runs_dir.exists():
        shutil.rmtree(runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)
    summary_jsonl = runs_dir / "summary.jsonl"
    summary_jsonl.write_text("", encoding="utf-8")

    if not profiles:
        for row in selected:
            append_jsonl(
                summary_jsonl,
                {
                    "schema": "agentdecompile.source-parity-profile-corpus-attempt.v1",
                    "case": row.get("name"),
                    "status": "missing-input",
                    "reason": "no compiler profiles available; pass --profile NAME=VC_ROOT or set VC_ROOT",
                },
            )
        return summary_jsonl

    evidence_cache: dict[str, dict[str, Any]] = {}
    disqualified: dict[tuple[str, str], dict[str, Any]] = {}
    for row in selected:
        case_name = str(row.get("name"))
        out_case_dir = Path(str(row.get("outDir", "")))
        candidate = Path(str(row.get("candidateSource") or out_case_dir / "candidate.c"))
        target = out_case_dir / "target.obj"
        source_snapshot = candidate.read_bytes() if candidate.is_file() else None
        if not candidate.exists() or not target.exists():
            append_jsonl(
                summary_jsonl,
                {
                    "schema": "agentdecompile.source-parity-profile-corpus-attempt.v1",
                    "case": case_name,
                    "status": "missing-input",
                    "candidate": str(candidate),
                    "target": str(target),
                },
            )
            continue
        for profile_name, msvc_root in profiles:
            preparation = prepare_msvc_invocation(source=Path("candidate.c"), args=[],
                msvc_root=msvc_root, wine=wine, wineprefix=wineprefix, strict_c=True)
            evidence_key = json.dumps([preparation["command"][:2], preparation["env"]], sort_keys=True)
            if evidence_key not in evidence_cache:
                evidence_cache[evidence_key] = toolchain_identity.capture(
                    {"compiler": toolchain_identity.ToolSpec(Path(preparation["command"][1])),
                     "linker": None, "assembler": None}, env=preparation["env"],
                    wine=toolchain_identity.WineHost(Path(preparation["env"]["WINEPREFIX"]),
                                                     preparation["command"][0]),
                    roots={"COMPILER_ROOT": preparation["root"]}, timeout=min(timeout, 30),
                    environment_is_effective=True)
            evidence = evidence_cache[evidence_key]
            banner = compiler_banner(evidence)
            for flag_name, flags in flag_sets:
                configuration = (profile_name, flag_name)
                if configuration in disqualified:
                    append_jsonl(summary_jsonl, {
                        "schema": "agentdecompile.source-parity-profile-corpus-attempt.v1",
                        "case": case_name, "profile": profile_name, "flagSet": flag_name,
                        "status": "pruned", "reason": "Configuration failed the native-exact gate on an earlier selected case.",
                        "failingReceipt": disqualified[configuration], "banner": banner,
                    })
                    continue
                run_dir = runs_dir / case_name / profile_name / flag_name
                run_dir.mkdir(parents=True, exist_ok=True)
                source = run_dir / "candidate.c"
                source.write_bytes(source_snapshot)
                candidate_obj = run_dir / "candidate.obj"
                preparation = None
                try:
                    preparation = prepare_msvc_invocation(source=source, args=flags,
                        msvc_root=msvc_root, wine=wine, wineprefix=wineprefix, strict_c=True)
                    binding = toolchain_identity.bind_invocation(evidence, **{key: preparation[key]
                        for key in ("command", "env", "requested_args", "policy")})
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    append_jsonl(summary_jsonl, {"case": case_name, "profile": profile_name,
                        "flagSet": flag_name, "status": "compile-failed", "compilerInvoked": False,
                        "compilerArgs": list(flags), "requestedArgs": list(flags),
                        "command": preparation["command"] if preparation is not None else None,
                        "binding": None, "bindingValid": False,
                        "reason": str(exc), "toolchainEvidence": evidence})
                    continue
                compile_result = compile_with_msvc(
                    source=source,
                    object_path=candidate_obj,
                    out_dir=run_dir,
                    stem="candidate",
                    args=flags,
                    timeout=timeout,
                    msvc_root=msvc_root,
                    wine=wine,
                    wineprefix=wineprefix,
                    expected_binding=binding,
                )
                if compile_result.get("status") != "ok":
                    append_jsonl(
                        summary_jsonl,
                        {
                            "schema": "agentdecompile.source-parity-profile-corpus-attempt.v1",
                            "case": case_name,
                            "profile": profile_name,
                            "flagSet": flag_name,
                            "compilerArgs": flags,
                            "command": compile_result.get("command"),
                            "binding": compile_result.get("binding"),
                            "bindingValid": compile_result.get("bindingValid"),
                            "status": "compile-failed",
                            "reason": compile_result.get("reason"),
                            "compileExit": compile_result.get("returnCode"),
                            "compilerInvoked": compile_result.get("compilerInvoked"),
                            "compilerRoot": str(msvc_root),
                            "banner": banner,
                            "compileStderrTail": compile_result.get("stderrTail"),
                        },
                    )
                    if prune_disqualified:
                        disqualified[configuration] = {"summaryJsonl": str(summary_jsonl), "case": case_name,
                            "profile": profile_name, "flagSet": flag_name, "status": "compile-failed"}
                    continue
                verify = run_objdiff(target, candidate_obj, run_dir, timeout=timeout)
                append_jsonl(
                    summary_jsonl,
                    {
                        "schema": "agentdecompile.source-parity-profile-corpus-attempt.v1",
                        "case": case_name,
                        "profile": profile_name,
                        "flagSet": flag_name,
                        "compilerArgs": flags,
                        "command": compile_result.get("command"),
                        "binding": compile_result.get("binding"),
                        "bindingValid": compile_result.get("bindingValid"),
                        "status": verify.get("status"),
                        "differences": verify.get("differences"),
                        "bestMatchPercent": verify.get("bestMatchPercent"),
                        "objdiffExit": verify.get("objdiffExit"),
                        "compilerInvoked": compile_result.get("compilerInvoked"),
                        "compilerRoot": str(msvc_root),
                        "object": str(candidate_obj),
                        "verify": str(run_dir / "verify.json"),
                        "banner": banner,
                    },
                )
                if prune_disqualified and not native_exact(verify):
                    disqualified[configuration] = {"summaryJsonl": str(summary_jsonl), "case": case_name,
                        "profile": profile_name, "flagSet": flag_name, "verify": str(run_dir / "verify.json")}
    return summary_jsonl


def profile_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--matched-examples", type=Path, default=Path("target/source-parity-index/default/matched-examples.jsonl"))
    parser.add_argument("--out-dir", type=Path, default=Path("target/source-parity-profile/default"))
    parser.add_argument("--max-cases", type=int, default=6)
    parser.add_argument("--select-only", "--dry-run", dest="select_only", action="store_true", help="Select corpus cases without compiling.")
    parser.add_argument("--profile", action="append", default=[], help="Compiler profile as NAME=VC_ROOT. Repeat for multiple toolchains.")
    parser.add_argument("--flag-set", action="append", default=[], help="Flag set as NAME='/O2 /Oy /GS-'. Repeat for custom matrix.")
    parser.add_argument("--wine", default="wine")
    parser.add_argument("--wineprefix", type=Path)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--clean", action="store_true")
    parser.mutating = True
    parser.add_argument("--profile-path", type=Path, help="Write a measured admission profile inside out-dir.")
    parser.add_argument("--program-fingerprint")
    parser.add_argument("--architecture")
    parser.add_argument("--probe-inventory", type=Path, help="Produce bounded source hypotheses from explicit function inventory.")
    parser.add_argument("--target-receipt", type=Path, help="Original-executable authority receipt; requires probe inventory.")
    return parser


def validate_frozen_catalog_parameters(params: dict[str, Any]) -> None:
    """Validate receipt completeness without consulting current defaults."""
    if params.get("argv") not in (None, "", []):
        raise ValueError("Calibration resource binding does not accept argv overrides.")
    for key in ("_calibration-execution-root", "matched-examples", "out-dir"):
        value = params.get(key)
        if not isinstance(value, str) or not value or not Path(value).is_absolute() or str(Path(value).resolve()) != value:
            raise ValueError(f"Calibration requires a frozen canonical {key}.")
    for key in ("select-only", "clean"):
        if type(params.get(key)) is not bool:
            raise ValueError(f"Calibration requires a frozen boolean {key}.")
    for key in ("max-cases", "timeout"):
        if type(params.get(key)) is not int or params[key] < 1:
            raise ValueError(f"Calibration requires a positive frozen {key}.")
    profile_path = params.get("profile-path")
    if bool(params.get("probe-inventory")) != bool(params.get("target-receipt")):
        raise ValueError("Probe inventory and original-target receipt must be supplied together.")
    for key in ("probe-inventory", "target-receipt"):
        value = params.get(key)
        if value and (not isinstance(value, str) or not Path(value).is_absolute() or str(Path(value).resolve()) != value):
            raise ValueError(f"Calibration requires frozen canonical {key}.")
    if params.get("probe-inventory") and not profile_path:
        raise ValueError("Probe bootstrap requires measured --profile-path admission.")
    if profile_path not in (None, ""):
        if not isinstance(profile_path, str) or not Path(profile_path).is_absolute() or str(Path(profile_path).resolve()) != profile_path or not Path(profile_path).is_relative_to(Path(params["out-dir"])):
            raise ValueError("Measured profile must be canonical and inside its reserved output directory.")
        if params["select-only"]:
            raise ValueError("Measured admission cannot select only.")
        for key in ("program-fingerprint", "architecture"):
            if not isinstance(params.get(key), str) or not params[key].strip():
                raise ValueError(f"Measured admission requires explicit {key}.")
    if params["select-only"]:
        return
    for key in ("wine", "wineprefix"):
        value = params.get(key)
        if not isinstance(value, str) or not value or not Path(value).is_absolute() or str(Path(value).resolve()) != value:
            raise ValueError(f"Calibration requires a frozen canonical {key}.")
    for key, parser in (("profile", parse_profile), ("flag-set", parse_flag_set)):
        values = params.get(key)
        if not isinstance(values, list) or not values or any(not isinstance(value, str) or "=" not in value for value in values):
            raise ValueError(f"Calibration requires explicit frozen {key} values.")
        names = []
        for value in values:
            name, content = value.split("=", 1)
            validate_output_name(name, key)
            if not content.strip():
                raise ValueError(f"Calibration {key} content cannot be empty.")
            if key == "profile" and (not Path(content).is_absolute() or str(Path(content).resolve()) != content):
                raise ValueError("Calibration profile must be NAME=absolute-root.")
            parsed_name, _ = parser(value)
            if parsed_name != name:
                raise ValueError(f"Calibration {key} name must be canonical.")
            names.append(name)
        if len(names) != len(set(names)):
            raise ValueError(f"Each calibration {key} must have a unique name.")


def freeze_catalog_parameters(params: dict[str, Any], execution_root: Path) -> dict[str, Any]:
    """Capture the CLI policy once before resource admission and child launch."""
    if not execution_root.is_absolute():
        raise ValueError("Calibration requires an absolute captured execution root.")
    root = execution_root.resolve()
    if params.get("_calibration-execution-root") == str(root):
        catalog_resource_claims(params)
        if params.get('select-only') is not True:
            from .corpus.wineprefix_clearance import prefix_identity
            if params.get('_calibration-prefix-identity') != prefix_identity(params['wineprefix']):
                raise ValueError('Frozen calibration prefix identity is missing or changed.')
        return dict(params)
    frozen = dict(params)
    defaults = vars(profile_parser().parse_args([]))
    for name, value in defaults.items():
        key = name.replace("_", "-")
        if frozen.get(key) in (None, ""):
            frozen[key] = value
    select_only = frozen.get("select-only") in (True, "true", "1", "yes", "on")
    frozen["select-only"] = select_only
    frozen["clean"] = frozen.get("clean") in (True, "true", "1", "yes", "on")
    for key in ("max-cases", "timeout"):
        value = frozen[key]
        if isinstance(value, bool):
            raise ValueError(f"Calibration requires a positive {key}.")
        try:
            frozen[key] = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Calibration requires a positive {key}.") from exc
        if str(frozen[key]) != str(value):
            raise ValueError(f"Calibration requires an integer {key}.")
    def path(value: Any) -> str:
        selected = Path(str(value)).expanduser()
        return str((selected if selected.is_absolute() else root / selected).resolve())
    for key in ("matched-examples", "out-dir", "profile-path", "probe-inventory", "target-receipt"):
        if frozen.get(key) not in (None, ""):
            frozen[key] = path(frozen[key])
    if frozen.get("argv"):
        raise ValueError("Calibration resource binding does not accept argv overrides.")
    if frozen.get("profile-path"):
        if select_only or not params.get("profile") or not params.get("wineprefix"):
            raise ValueError("Measured admission requires explicit profile and wineprefix and cannot select only.")
        if not Path(frozen["profile-path"]).is_relative_to(Path(frozen["out-dir"])):
            raise ValueError("Measured profile must be inside its reserved output directory.")
    if not select_only:
        from .corpus.wineprefix_clearance import prefix_identity
        if not params.get("wineprefix"):
            raise ValueError("Compilation requires an explicit independently provisioned wineprefix.")
        profiles = ([parse_profile(value, base=root) for value in frozen["profile"]]
                    if frozen["profile"] else default_profiles(base=root))
        if not profiles:
            raise ValueError("No compiler profiles available to freeze; provide an explicit profile.")
        frozen["profile"] = [f"{name}={compiler_root}" for name, compiler_root in profiles]
        flags = ([parse_flag_set(value) for value in frozen["flag-set"]]
                 if frozen["flag-set"] else DEFAULT_FLAGS)
        frozen["flag-set"] = [f"{name}={' '.join(values)}" for name, values in flags]
        frozen["wineprefix"] = path(frozen["wineprefix"])
        frozen["_calibration-prefix-identity"] = prefix_identity(frozen["wineprefix"])
        wine = str(frozen["wine"])
        if "/" in wine:
            wine = path(wine)
        search_path = os.pathsep.join(path(entry or ".") for entry in os.get_exec_path())
        executable = shutil.which(wine, path=search_path)
        if executable is None:
            raise ValueError("Calibration Wine command must resolve to an executable.")
        frozen["wine"] = str(Path(executable).resolve())
    frozen["_calibration-execution-root"] = str(root)
    validate_frozen_catalog_parameters(frozen)
    return frozen


def catalog_resource_claims(params: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    """Read frozen values without rediscovering today's compiler environment."""
    validate_frozen_catalog_parameters(params)
    captured_root = params.get("_calibration-execution-root")
    if not captured_root or not Path(str(captured_root)).is_absolute():
        raise ValueError("Historical calibration has no frozen execution-root binding.")
    claims = [("output", params.get("out-dir"))]
    if params.get("select-only") not in (True, "true", "1", "yes", "on"):
        profiles = params.get("profile")
        if not isinstance(profiles, list) or not profiles or not params.get("wineprefix") or not params.get("wine") or not Path(str(params["wine"])).is_absolute():
            raise ValueError("Historical calibration parameters are not frozen.")
        claims.append(("wineprefix", params["wineprefix"]))
        for value in profiles:
            if "=" not in value:
                raise ValueError("Calibration profile must be NAME=absolute-root.")
            claims.append(("compiler", value.split("=", 1)[1]))
    for _, value in claims:
        if not value or not Path(str(value)).is_absolute() or str(Path(str(value)).resolve()) != str(value):
            raise ValueError("Calibration resource paths must be frozen and canonical.")
    return tuple(sorted(set(claims)))


def main(argv: list[str] | None = None) -> int:
    parser = profile_parser()
    args = parser.parse_args(argv)
    if (args.probe_inventory is None) != (args.target_receipt is None):
        parser.error("--probe-inventory and --target-receipt must be supplied together.")
    if args.probe_inventory is not None and args.profile_path is None:
        parser.error("Probe bootstrap requires --profile-path measured admission.")

    if args.profile_path is not None:
        if args.select_only:
            parser.error("--profile-path cannot be combined with --select-only/--dry-run.")
        if not args.program_fingerprint or not args.program_fingerprint.strip() or not args.architecture or not args.architecture.strip():
            parser.error("Admission requires explicit --program-fingerprint and --architecture.")
        if not args.profile or args.wineprefix is None:
            parser.error("Admission requires explicit --profile and --wineprefix.")
        if not args.wine or args.max_cases < 1 or args.timeout < 1:
            parser.error("Admission requires a Wine command and positive max-cases and timeout.")
        wine_executable = shutil.which(args.wine)
        if wine_executable is None:
            parser.error("Admission Wine command must resolve to an executable.")
        try:
            result = admit_measured_profile(
                matched_examples=args.matched_examples,
                out_dir=args.out_dir,
                profile_path=args.profile_path,
                program_fingerprint=args.program_fingerprint,
                architecture=args.architecture,
                max_cases=args.max_cases,
                timeout=args.timeout,
                profiles=args.profile,
                flag_sets=args.flag_set,
                wine=str(Path(wine_executable).resolve()),
                wineprefix=args.wineprefix,
                probe_inventory=args.probe_inventory,
                target_receipt=args.target_receipt,
            )
        except ValueError as exc:
            parser.error(str(exc))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("state") == "admitted" else 1

    return execute_sweep(args, parser)


def execute_sweep(args: argparse.Namespace, parser: argparse.ArgumentParser, *, prune_disqualified: bool = False) -> int:
    """Shared sweep execution; standalone diagnostics retain the full matrix."""
    rows = list(iter_jsonl(args.matched_examples))
    selected = select_cases(rows, args.max_cases)
    profiles = ([parse_profile(value) for value in args.profile] if args.profile else default_profiles()) if not args.select_only else []
    flag_sets = ([parse_flag_set(value) for value in args.flag_set] if args.flag_set else DEFAULT_FLAGS) if not args.select_only else []
    try:
        for label, configurations in (("compiler profile", profiles), ("flag set", flag_sets)):
            names = [name for name, _ in configurations]
            for name in names:
                validate_output_name(name, label)
            if len(names) != len(set(names)):
                raise ValueError(f"Each {label} must have a unique name so calibration receipts identify one configuration.")
        if not args.select_only:
            validate_case_inputs(
                selected,
                args.out_dir / "runs",
                receipt_paths=(args.out_dir / "selected-cases.json", args.out_dir / "summary.json"),
            )
            if args.matched_examples.resolve() in {
                (args.out_dir / "selected-cases.json").resolve(),
                (args.out_dir / "summary.json").resolve(),
            } or args.matched_examples.resolve().is_relative_to((args.out_dir / "runs").resolve()):
                raise ValueError("Matched examples must be outside sweep cleanup and receipt outputs.")
    except ValueError as exc:
        parser.error(str(exc))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    selected_path = args.out_dir / "selected-cases.json"
    write_json(selected_path, select_report(selected, args.matched_examples, args.max_cases))

    if args.select_only:
        summary = {
            "schema": "agentdecompile.source-parity-profile-corpus-summary.v1",
            "status": "selected-only",
            "selectedCases": len(selected),
            "selectedCasesPath": str(selected_path),
            "claimBoundary": "compiler-profile corpus selection is not source recovery; accepted source still requires per-function objdiff zero",
        }
        write_json(args.out_dir / "summary.json", summary)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    summary_jsonl = run_sweep(
        selected=selected,
        out_dir=args.out_dir,
        profiles=profiles,
        flag_sets=flag_sets,
        wine=args.wine,
        wineprefix=args.wineprefix,
        timeout=args.timeout,
        clean=args.clean,
        prune_disqualified=prune_disqualified,
    )
    summary = {
        "schema": "agentdecompile.source-parity-profile-corpus-summary.v1",
        "status": "complete",
        "selectedCases": len(selected),
        "selectedCasesPath": str(selected_path),
        "summaryJsonl": str(summary_jsonl),
        "evidence": summarize(summary_jsonl),
        "compilerProfiles": [{"name": name, "root": str(root)} for name, root in profiles],
        "flagSets": [{"name": name, "args": flags} for name, flags in flag_sets],
        "claimBoundary": "compiler-profile scores guide future candidate generation; accepted source still requires per-function objdiff zero",
    }
    write_json(args.out_dir / "summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
