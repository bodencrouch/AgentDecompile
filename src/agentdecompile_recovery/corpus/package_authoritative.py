"""Assemble the one consumer-facing, evidence-gated corpus source tree.

This package is intentionally narrower than the warehouse.  The warehouse keeps
experiments, Ghidra exports, retries, mirrors and archived prompts.  This output
contains exactly two kinds of implementation, selected per concrete function:

* readable C/C++ only when the current coverage ledger says ``byteExact: true``
  and the matching current recovered-source body passes the real-C gate;
* the byte-preserving assembler emitted by ``kotor_reconstructed`` for every
  other function.

The assembler trees are relative symlinks to the authoritative generator output
instead of another 1.5 GiB copy.  ``metadata/selection.json`` is the complete
selection contract: C addresses override the same labels in the assembler tree;
all addresses not listed there use assembler.  It deliberately does not claim
that independently compiled C and the assembler fallback form one linkable
translation unit without the original per-function build environments.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import shutil
import sqlite3
import sys
from collections import Counter, defaultdict
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from . import canon, corpus_config, db
from .ingest_recovered import load_coverage_index, parse_recovered

WORKSPACE = pathlib.Path(__file__).resolve().parent.parent
OUT = WORKSPACE / "output" / "kotor_authoritative"
ASM_ORIGIN = WORKSPACE / "output" / "kotor_reconstructed" / "src"
HDR_ADDR = re.compile(r"\baddress\s*:\s*0x([0-9a-fA-F]+)", re.I)
SYM_ADDR = re.compile(r"\bF_([0-9a-fA-F]{6,16})\b")
SAFE = re.compile(r"[^A-Za-z0-9_.+-]")


def _address_from_row(row: dict[str, Any], coverage: dict[str, Any] | None) -> int | None:
    """Resolve an address only from recorded evidence, never from a guessed name."""
    text = pathlib.Path(row["path"]).read_text(encoding="utf-8", errors="replace")[:1600]
    found = HDR_ADDR.search(text)
    if found:
        return int(found.group(1), 16)
    if coverage:
        symbol = str(coverage.get("symbol") or "")
        found = SYM_ADDR.search(symbol)
        if found:
            return int(found.group(1), 16)
    return row.get("addr")


def _safe_name(name: str) -> str:
    return SAFE.sub("_", name).strip("._") or "unnamed"


def _coverage_by_key() -> dict[tuple[str, str], dict[str, Any]]:
    return load_coverage_index()


def _unique_byte_addresses(slug: str) -> dict[str, int]:
    """Resolve only byte strings that occur at one extracted address.

    Several older ledger rows omitted an address but retained the exact original
    bytes.  Matching those bytes is safe only when the complete extracted
    function-byte stream contains exactly one occurrence in that *same* binary;
    common leaves such as ``return 0`` intentionally remain unresolved.
    """
    path = WORKSPACE / "extract" / "funcbytes" / f"{slug}.jsonl"
    occurrences: dict[str, list[int]] = defaultdict(list)
    if not path.is_file():
        return {}
    with path.open() as fh:
        for line in fh:
            try:
                record = json.loads(line)
                occurrences[str(record["b"]).lower()].append(int(record["a"]))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
    return {body: addresses[0] for body, addresses in occurrences.items()
            if len(addresses) == 1}


def _binary_map(con: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    return {row["repo_path"]: row for row in con.execute(
        "SELECT id, repo_path, slug, arch, bits, format FROM binary")}


def _canonical_paths() -> list[str]:
    return [line.strip() for line in (WORKSPACE / "scripts" / "programs.txt").read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def build(out: pathlib.Path = OUT) -> dict[str, Any]:
    """Write the overlay and metadata; this is packaging, not a test runner."""
    if not ASM_ORIGIN.is_dir():
        raise SystemExit(f"missing authoritative assembler origin: {ASM_ORIGIN}")
    if out.exists():
        raise SystemExit(f"refusing to overwrite existing output: {out}")

    con = db.connect(WORKSPACE / "db" / "kotorxid.sqlite")
    binaries = _binary_map(con)
    canonical_paths = _canonical_paths()
    maps = corpus_config.load_maps()
    leaf_to_repo = dict(maps.get("leaf_to_repo") or {})
    coverage_by_key = _coverage_by_key()
    candidates = parse_recovered()  # ledger-backed byteExact=true only

    selected: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rejected: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    unique_byte_cache: dict[str, dict[str, int]] = {}
    for candidate in candidates:
        repo_path = leaf_to_repo.get(candidate["program"])
        binary = binaries.get(repo_path or "")
        coverage = coverage_by_key.get((candidate["program"], candidate["name"]))
        addr = _address_from_row(candidate, coverage)
        if binary is None:
            rejected.append({"program": candidate["program"], "name": candidate["name"],
                             "reason": "no canonical binary mapping"})
            continue
        address_basis = "recorded-address"
        if addr is None:
            byte_string = str(candidate.get("machine_code") or
                              (coverage or {}).get("originalBytes") or "").lower()
            if binary["slug"] not in unique_byte_cache:
                unique_byte_cache[binary["slug"]] = _unique_byte_addresses(binary["slug"])
            unique_addresses = unique_byte_cache[binary["slug"]]
            addr = unique_addresses.get(byte_string)
            address_basis = "unique-original-byte-match"
        if addr is None:
            rejected.append({"program": candidate["program"], "name": candidate["name"],
                             "reason": "no recorded or unique byte-resolved address"})
            continue
        # The row must resolve to an actual extracted function in that binary.
        function = con.execute(
            "SELECT addr, size, name, source_file FROM func WHERE binary_id=? AND addr=?",
            (binary["id"], addr)).fetchone()
        if function is None:
            rejected.append({"program": candidate["program"], "name": candidate["name"],
                             "address": f"0x{addr:x}", "reason": "address absent from canonical function table"})
            continue
        key = (binary["slug"], addr)
        if key in seen:
            rejected.append({"program": candidate["program"], "name": candidate["name"],
                             "address": f"0x{addr:x}", "reason": "duplicate selected address"})
            continue
        seen.add(key)
        source_path = pathlib.Path(candidate["path"])
        source = source_path.read_bytes()
        selected[binary["slug"]].append({
            "address": f"0x{addr:08x}",
            "name": candidate["name"],
            "function_name": function["name"],
            "size": function["size"],
            "source_file": function["source_file"],
            "address_basis": address_basis,
            "coverage": coverage,
            "evidence": candidate.get("evidence"),
            "original_source": str(source_path),
            "sha256": hashlib.sha256(source).hexdigest(),
        })

    (out / "src").mkdir(parents=True)
    (out / "metadata").mkdir(parents=True)
    for repo_path in canonical_paths:
        row = binaries.get(repo_path)
        if repo_path in canon.DRM_EXCLUDED:
            continue
        if row is None:
            # The .keep artifact has a complete exact representation but no DB
            # record; preserve its assembler tree and make the metadata gap loud.
            slug = repo_path.strip("/").replace("/", "__")
        else:
            slug = row["slug"]
        asm = ASM_ORIGIN / slug
        if not asm.exists():
            rejected.append({"repo_path": repo_path, "reason": "assembler source tree missing"})
            continue
        dest = out / "src" / slug / "asm"
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(os.path.relpath(asm, dest.parent), dest)
        c_dir = out / "src" / slug / "verified_c"
        for item in sorted(selected.get(slug, []), key=lambda x: x["address"]):
            c_dir.mkdir(parents=True, exist_ok=True)
            addr = int(item["address"], 16)
            name = _safe_name(item["name"])
            dest_c = c_dir / f"{addr:08x}_{name}.c"
            shutil.copyfile(item["original_source"], dest_c)
            item["path"] = dest_c.relative_to(out).as_posix()

    per_binary = []
    for repo_path in canonical_paths:
        row = binaries.get(repo_path)
        slug = row["slug"] if row else repo_path.strip("/").replace("/", "__")
        if repo_path in canon.DRM_EXCLUDED:
            per_binary.append({"repo_path": repo_path, "slug": slug,
                               "status": "deferred_drm_ciphertext"})
            continue
        nfunc = con.execute("SELECT COUNT(*) FROM func WHERE binary_id=? AND n_instr>0 AND size>0",
                            (row["id"],)).fetchone()[0] if row else None
        per_binary.append({
            "repo_path": repo_path,
            "slug": slug,
            "status": "selected" if row else "assembler_only_metadata_missing",
            "function_count": nfunc,
            "verified_c_count": len(selected.get(slug, [])),
            "assembler_fallback": f"src/{slug}/asm",
            "selection_rule": "verified_c addresses override assembler; every other function uses assembler",
        })

    selection = {
        "schema_version": 1,
        "purpose": "One authoritative source representation: ledger-verified C with exact assembler fallback.",
        "admission_rule": "coverage byteExact=true + current recovered source + real-C classification + canonical address match",
        "assembler_origin": str(ASM_ORIGIN),
        "binaries": per_binary,
        "verified_c": {slug: sorted(items, key=lambda x: x["address"])
                       for slug, items in sorted(selected.items())},
        "rejected_candidates": rejected,
    }
    (out / "metadata" / "selection.json").write_text(json.dumps(selection, indent=2) + "\n")
    with (out / "metadata" / "selected-c.jsonl").open("w") as fh:
        for items in selection["verified_c"].values():
            for item in items:
                fh.write(json.dumps(item, sort_keys=True) + "\n")
    _write_readme(out, selection)
    return {
        "binaries": len(per_binary),
        "verified_c": sum(len(items) for items in selected.values()),
        "rejected": len(rejected),
    }


def _write_readme(out: pathlib.Path, selection: dict[str, Any]) -> None:
    counts = Counter(x["status"] for x in selection["binaries"])
    total_c = sum(len(x) for x in selection["verified_c"].values())
    lines = [
        "# Authoritative source representation",
        "",
        "This is the one consumer-facing corpus source tree. For each concrete function it selects",
        "ledger-verified readable C/C++ when available; all other functions are represented by the",
        "byte-preserving assembler emitted in `output/kotor_reconstructed`. The assembler directories",
        "are relative symlinks, so this tree does not make another stale 1.5 GiB copy.",
        "",
        f"- Canonical binaries: **{len(selection['binaries'])}**",
        f"- Non-DRM selected binaries: **{counts['selected'] + counts['assembler_only_metadata_missing']}**",
        f"- Ledger-verified readable-C selections: **{total_c}**",
        f"- DRM-deferred binaries: **{counts['deferred_drm_ciphertext']}**",
        "",
        "## Layout",
        "",
        "- `src/<binary>/verified_c/` — source admitted by the coverage-ledger gate.",
        "- `src/<binary>/asm/` — complete byte-preserving fallback tree; selected C addresses override these labels.",
        "- `metadata/selection.json` — exhaustive per-binary selection contract and rejected-candidate ledger.",
        "- `metadata/selected-c.jsonl` — provenance, byte evidence, address, and SHA-256 for every selected C file.",
        "",
        "A source file is selected only when its current coverage ledger record has `byteExact: true`,",
        "the source body is classified as real C rather than an emitter shim, and its recorded address",
        "resolves to the canonical function database. Ghidra-only decompilations, unverified mirrors,",
        "quarantined shims, retries, and duplicate exports are not promoted.",
        "",
        "This is a source representation and selection contract, not a claim that the mixed C/assembly",
        "tree can be linked in one compiler invocation without the original function-specific environments.",
        "",
    ]
    (out / "README.md").write_text("\n".join(lines))


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=pathlib.Path, default=OUT)
    args = parser.parse_args()
    result = build(args.out.resolve())
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
