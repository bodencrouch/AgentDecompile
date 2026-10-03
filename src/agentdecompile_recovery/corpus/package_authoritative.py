"""Package current source-bound historical local comparisons and ASM fallback.

The compatibility names ``verified_c`` and ``kotor_authoritative`` describe this
local selection tree, not independently accepted recovery. Readable C requires
producer-bound source bytes, recorded target checks and canonical placement;
semantic identity, independent address mapping, linked-source contribution and
fresh whole-image acceptance remain unavailable. ASM is a separate representation
floor, never readable-C or whole-image acceptance credit.

Inputs are explicit. ASM directories retain the existing relative symlink layout;
portable recipes and atomic bundle publication are separate, unfinished work.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import pathlib
import re
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing
from typing import Any

from . import canon, corpus_config
from .ingest_recovered import load_coverage_index, parse_recovered
from .source_claims import is_real_c

HDR_ADDR = re.compile(r"\baddress\s*:\s*0x([0-9a-fA-F]+)", re.I)
SYM_ADDR = re.compile(r"\bF_([0-9a-fA-F]{6,16})\b")
SAFE = re.compile(r"[^A-Za-z0-9_.+-]")
INDEPENDENT_ACCEPTANCE = {
    "status": "unavailable",
    "semantic_identity": "unverified",
    "address_mapping": "unverified",
    "linked_source_contribution": "unverified",
    "fresh_whole_image": "unverified",
}


def _safe_name(name: str) -> str:
    return SAFE.sub("_", name).strip("._") or "unnamed"


def _coverage_by_key(coverage_dir: pathlib.Path) -> dict[tuple[str, str], dict[str, Any]]:
    return load_coverage_index(coverage_dir)


def _read_database(path: pathlib.Path) -> sqlite3.Connection:
    """Read an existing compatible inventory without creating or migrating it."""
    if not path.is_file():
        raise SystemExit(f"missing canonical database: {path}")
    con = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        for table, required in {
            "binary": {"id", "repo_path", "slug", "arch", "bits", "format"},
            "func": {"binary_id", "addr", "size", "name", "source_file", "n_instr"},
        }.items():
            columns = {row[1] for row in con.execute(f"PRAGMA table_info({table})")}
            if not required <= columns:
                raise SystemExit(f"incompatible canonical database: {table} missing {sorted(required - columns)}")
    except BaseException:
        con.close()
        raise
    return con


def _binary_map(con: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    return {row["repo_path"]: row for row in con.execute(
        "SELECT id, repo_path, slug, arch, bits, format FROM binary")}


def _canonical_paths(path: pathlib.Path) -> list[str]:
    return list(dict.fromkeys(line.strip() for line in path.read_text().splitlines()
                             if line.strip() and not line.lstrip().startswith("#")))


def _source_snapshot(candidate: dict[str, Any], coverage: dict[str, Any] | None
                     ) -> tuple[bytes | None, str | None]:
    """Retain one producer-bound snapshot; never repair stale evidence by hashing."""
    if coverage is None or coverage.get("byteExact") is not True:
        return None, "missing_positive_observation"
    region = coverage.get("targetRegion") or {}
    snapshot = coverage.get("targetSnapshot") or {}
    if (candidate.get("source_sha256") != coverage.get("sourceSha256")
            or candidate.get("target_sha256") != snapshot.get("sha256")
            or candidate.get("addr") != region.get("address")
            or candidate.get("target_offset") != region.get("offset")
            or candidate.get("size") != region.get("size")
            or candidate.get("machine_code") != str(coverage.get("originalBytes") or "").lower()):
        return None, "candidate_observation_mismatch"
    digest = candidate.get("source_sha256")
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        return None, "missing_or_invalid_source_digest"
    try:
        source = pathlib.Path(candidate["path"]).read_bytes()
    except OSError:
        return None, "source_unreadable"
    if hashlib.sha256(source).hexdigest() != digest:
        return None, "source_digest_mismatch"
    text = source.decode("utf-8", errors="replace")
    if candidate.get("real_c") != 1 or not is_real_c(text):
        return None, "not_readable_c"
    addr = candidate.get("addr")
    if type(addr) is not int or addr < 0:
        return None, "missing_checked_target_address"
    if any(int(match.group(1), 16) != addr for match in HDR_ADDR.finditer(text[:1600])):
        return None, "header_target_address_mismatch"
    if any(int(match.group(1), 16) != addr
           for match in SYM_ADDR.finditer(str(coverage.get("symbol") or ""))):
        return None, "symbol_target_address_mismatch"
    return source, None


def build(out: pathlib.Path | None = None, *, workspace: pathlib.Path,
          recovered_dir: pathlib.Path, coverage_dir: pathlib.Path,
          config_dir: pathlib.Path | None = None) -> dict[str, Any]:
    """Write the local observation overlay; no recovery or acceptance is run."""
    workspace = pathlib.Path(workspace).resolve()
    recovered_dir = pathlib.Path(recovered_dir).resolve()
    coverage_dir = pathlib.Path(coverage_dir).resolve()
    config_dir = pathlib.Path(config_dir).resolve() if config_dir is not None else None
    output_path = pathlib.Path(out) if out is not None else workspace / "output" / "kotor_authoritative"
    if output_path.exists() or output_path.is_symlink():
        raise SystemExit(f"refusing to overwrite existing output: {output_path}")
    out = output_path.resolve()
    asm_origin = workspace / "output" / "kotor_reconstructed" / "src"
    programs_path = workspace / "scripts" / "programs.txt"
    for path, label in ((workspace, "workspace"), (recovered_dir, "recovered source directory"),
                        (coverage_dir, "coverage directory"), (asm_origin, "assembler origin")):
        if not path.is_dir():
            raise SystemExit(f"missing {label}: {path}")
    if not programs_path.is_file():
        raise SystemExit(f"missing canonical programs: {programs_path}")
    if out.exists() or out.is_symlink():
        raise SystemExit(f"refusing to overwrite existing output: {out}")
    with closing(_read_database(workspace / "db" / "kotorxid.sqlite")) as con:
        return _build(out, workspace, recovered_dir, coverage_dir, config_dir,
                      asm_origin, programs_path, con)


def _build(out, workspace, recovered_dir, coverage_dir, config_dir,
           asm_origin, programs_path, con) -> dict[str, Any]:
    binaries = _binary_map(con)
    canonical_paths = _canonical_paths(programs_path)
    slugs = {path: binaries[path]["slug"] if path in binaries else path.strip("/").replace("/", "__")
             for path in canonical_paths if path not in canon.DRM_EXCLUDED}
    for slug in slugs.values():
        if not (asm_origin / slug).is_dir():
            raise SystemExit(f"missing assembler source tree: {asm_origin / slug}")
    maps = corpus_config.load_maps(config_dir)
    leaf_to_repo = dict(maps.get("leaf_to_repo") or {})
    # Both parser and manifest consume this one pinned ledger read.
    coverage_by_key = copy.deepcopy(_coverage_by_key(coverage_dir))
    rejected: list[dict[str, Any]] = []
    candidates = parse_recovered(recovered_dir, coverage_dir, rejected=rejected,
                                 coverage_index=coverage_by_key)
    for refusal in rejected:
        observation = coverage_by_key.get((refusal["program"], refusal["function"]))
        if observation is not None:
            refusal["coverage"] = observation
    selected: dict[str, list[dict[str, Any]]] = defaultdict(list)
    sources: dict[tuple[str, int], bytes] = {}
    for candidate in candidates:
        coverage = coverage_by_key.get((candidate["program"], candidate["name"]))
        diagnostic = {"program": candidate["program"], "name": candidate["name"],
                      "path": candidate["path"], "source_sha256": candidate.get("source_sha256"),
                      "target_sha256": candidate.get("target_sha256"), "coverage": coverage}
        source, reason = _source_snapshot(candidate, coverage)
        repo_path = leaf_to_repo.get(candidate["program"])
        binary = binaries.get(repo_path or "")
        if reason is None and (binary is None or repo_path not in slugs):
            reason = "no canonical binary mapping"
        addr = candidate.get("addr")
        function = None
        if reason is None:
            function = con.execute(
                "SELECT addr, size, name, source_file FROM func WHERE binary_id=? AND addr=?",
                (binary["id"], addr)).fetchone()
            if function is None:
                reason = "address absent from canonical function table"
            elif (binary["slug"], addr) in sources:
                reason = "duplicate selected address"
        if reason is not None:
            rejected.append({**diagnostic, "address": addr, "reason": reason})
            continue
        sources[(binary["slug"], addr)] = source
        selected[binary["slug"]].append({
            "address": f"0x{addr:08x}", "name": candidate["name"],
            "function_name": function["name"], "size": function["size"],
            "source_file": function["source_file"], "address_basis": "checked-target-region",
            "coverage": coverage, "evidence": candidate.get("evidence"),
            "original_source": candidate["path"], "sha256": candidate["source_sha256"],
            "source_sha256": candidate["source_sha256"], "target_sha256": candidate["target_sha256"],
            "local_comparison": "source-bound historical local-function observation",
            "readable_c": True, "canonical_placement": "function-table address present",
            "independent_acceptance": dict(INDEPENDENT_ACCEPTANCE),
        })

    (out / "src").mkdir(parents=True)
    (out / "metadata").mkdir(parents=True)
    for repo_path, slug in slugs.items():
        dest = out / "src" / slug / "asm"
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(os.path.relpath(asm_origin / slug, dest.parent), dest)
        c_dir = dest.parent / "verified_c"
        for item in sorted(selected.get(slug, []), key=lambda x: x["address"]):
            c_dir.mkdir(parents=True, exist_ok=True)
            addr = int(item["address"], 16)
            dest_c = c_dir / f"{addr:08x}_{_safe_name(item['name'])}.c"
            dest_c.write_bytes(sources[(slug, addr)])
            item["path"] = dest_c.relative_to(out).as_posix()

    per_binary = []
    for repo_path in canonical_paths:
        row = binaries.get(repo_path)
        slug = row["slug"] if row else repo_path.strip("/").replace("/", "__")
        if repo_path in canon.DRM_EXCLUDED:
            per_binary.append({"repo_path": repo_path, "slug": slug, "status": "deferred_drm_ciphertext"})
            continue
        nfunc = con.execute("SELECT COUNT(*) FROM func WHERE binary_id=? AND n_instr>0 AND size>0",
                            (row["id"],)).fetchone()[0] if row else None
        per_binary.append({
            "repo_path": repo_path, "slug": slug,
            "status": "selected" if row else "assembler_only_metadata_missing",
            "function_count": nfunc, "verified_c_count": len(selected.get(slug, [])),
            "local_readable_c_selection_count": len(selected.get(slug, [])),
            "assembler_fallback": f"src/{slug}/asm",
            "selection_rule": "local selected C addresses override assembler; all other addresses use assembler",
            "independent_acceptance": dict(INDEPENDENT_ACCEPTANCE),
        })
    selection = {
        "schema_version": 1,
        "purpose": "Source-bound historical local-function C selection with separate assembler fallback.",
        "admission_rule": "producer source digest + recorded target checks + readable-C snapshot + canonical placement",
        "compatibility_fields": "verified_c and verified_c_count mean local readable-C selection only, not accepted recovery",
        "input_basis": {"workspace": str(workspace), "recovered_dir": str(recovered_dir),
                        "coverage_dir": str(coverage_dir), "config_dir": str(config_dir) if config_dir else None},
        "assembler_origin": str(asm_origin), "assembler_scope": "separate representation floor; no C acceptance credit",
        "independent_acceptance": dict(INDEPENDENT_ACCEPTANCE),
        "bundle_scope": "direct writes and external relative ASM symlinks; atomic portable bundle unqualified",
        "binaries": per_binary,
        "verified_c": {slug: sorted(items, key=lambda x: x["address"]) for slug, items in sorted(selected.items())},
        "rejected_candidates": rejected,
    }
    (out / "metadata" / "selection.json").write_text(json.dumps(selection, indent=2) + "\n")
    with (out / "metadata" / "selected-c.jsonl").open("w") as fh:
        for items in selection["verified_c"].values():
            for item in items:
                fh.write(json.dumps(item, sort_keys=True) + "\n")
    _write_readme(out, selection)
    return {"binaries": len(per_binary), "verified_c": sum(len(items) for items in selected.values()),
            "rejected": len(rejected)}


def _write_readme(out: pathlib.Path, selection: dict[str, Any]) -> None:
    counts = Counter(x["status"] for x in selection["binaries"])
    total_c = sum(len(x) for x in selection["verified_c"].values())
    lines = [
        "# Local comparison source representation", "",
        "This tree selects current producer-bound source snapshots from historical local-function",
        "comparison observations. Readable-C classification and canonical function-table placement",
        "are additional selection checks. Recorded target checks pin the recorded bytes only;",
        "independent target identity and VA-to-file address mapping remain unverified.", "",
        f"- Canonical binaries: **{len(selection['binaries'])}**",
        f"- Local readable-C selections: **{total_c}**",
        f"- DRM-deferred binaries: **{counts['deferred_drm_ciphertext']}**", "",
        "- `src/<binary>/verified_c/`: compatibility name for checked local source snapshots.",
        "- `src/<binary>/asm/`: relative symlink to the separate assembler representation floor.",
        "- `metadata/selection.json`: input basis, selection, proof limits and parser/package refusals.",
        "- `metadata/selected-c.jsonl`: original observations and digests for each retained snapshot.", "",
        "`verified_c` and `verified_c_count` denote local selection, not independently accepted source.",
        "Selected C addresses override ASM labels for representation purposes. ASM is not counted as",
        "readable C, linked-source contribution or whole-image recovery acceptance.", "",
        "Independent semantic identity, linked-source contribution and fresh whole-image acceptance",
        "are unavailable. There is no claim that this mixed tree links in one compiler invocation.",
        "Direct output writes and external ASM symlinks have no atomic-publication or clean-host",
        "portable-recipe qualification. Those bundle requirements remain open.", "",
    ]
    (out / "README.md").write_text("\n".join(lines))


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=pathlib.Path, required=True)
    parser.add_argument("--recovered-dir", type=pathlib.Path, required=True)
    parser.add_argument("--coverage-dir", type=pathlib.Path, required=True)
    parser.add_argument("--out", type=pathlib.Path, default=None)
    parser.add_argument("--config-dir", type=pathlib.Path, default=None)
    args = parser.parse_args()
    result = build(args.out, workspace=args.workspace, recovered_dir=args.recovered_dir,
                   coverage_dir=args.coverage_dir, config_dir=args.config_dir)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
