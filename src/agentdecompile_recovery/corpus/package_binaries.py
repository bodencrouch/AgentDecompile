"""Materialize one organized folder with one subfolder per executable binary.

``output/binaries`` is the sole consumer-facing binary collection. It begins
as a safe link-based inventory and can then be materialized with
``kx.materialize_binaries``. A reader can therefore open one binary directory
and see all available source, byte evidence, extracted input, STABS, and corpus
metadata without navigating the warehouse's historical pipeline layout.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
from collections import Counter
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from . import canon, corpus_config, db

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "output" / "binaries"
AUTHORITATIVE = ROOT / "output" / "kotor_authoritative"
SAFE = re.compile(r"[^A-Za-z0-9_.+-]")


def link(target: pathlib.Path, destination: pathlib.Path) -> bool:
    """Create a relative link when a known artifact exists."""
    if not target.exists():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(os.path.relpath(target, destination.parent), destination)
    return True


def artifact_key(repo_path: str) -> str:
    return repo_path.strip("/").replace("/", "__")


def slug_for(repo_path: str) -> str:
    return SAFE.sub("_", artifact_key(repo_path))


def load_json(path: pathlib.Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def representation_dir(root: pathlib.Path, slug: str) -> pathlib.Path | None:
    """Find a per-program representation despite old inconsistent slugging."""
    direct = root / slug
    if direct.exists():
        return direct
    normalized = SAFE.sub("_", slug)
    for candidate in root.iterdir() if root.exists() else ():
        if candidate.is_dir() and SAFE.sub("_", candidate.name) == normalized:
            return candidate
    return None


def project_manifests(root: pathlib.Path) -> dict[str, list[pathlib.Path]]:
    """Index experiment runs by their explicit manifest program field."""
    out: dict[str, list[pathlib.Path]] = {}
    for manifest in root.rglob("manifest.json") if root.exists() else ():
        program = load_json(manifest, {}).get("program")
        if isinstance(program, str):
            out.setdefault(program, []).append(manifest.parent)
    return out


def main() -> None:
    if OUT.exists():
        raise SystemExit(f"refusing to overwrite existing collection: {OUT}")
    con = db.connect(ROOT / "db" / "kotorxid.sqlite", read_only=True)
    rows = [dict(r) for r in con.execute("SELECT * FROM binary ORDER BY repo_path")]
    # The database also contains one imported repository-directory placeholder.
    # It is not an executable and must not get a binary folder.
    rows = [row for row in rows if pathlib.PurePosixPath(row["repo_path"]).name != "repos"]
    known = {row["repo_path"] for row in rows}
    for repo_path in (ROOT / "scripts" / "programs.txt").read_text().splitlines():
        repo_path = repo_path.strip()
        if repo_path and repo_path not in known:
            rows.append({"repo_path": repo_path, "slug": slug_for(repo_path), "id": None,
                         "role": None, "game": None, "platform": None, "arch": None,
                         "bits": None, "format": None, "md5": None, "image_base": None,
                         "func_count": None, "named_count": None})

    selection = load_json(AUTHORITATIVE / "metadata" / "selection.json", {})
    selected = dict(selection.get("verified_c") or {})
    coverage = {x.get("repo_path"): x for x in load_json(
        ROOT / "output" / "exact_universal" / "_coverage.json", [])}
    maps = corpus_config.load_maps()
    repo_to_leaf = {v: k for k, v in dict(maps.get("leaf_to_repo") or {}).items()}
    stabs_dir = ROOT / "extract" / "stabs"
    mizuchi_runs = project_manifests(ROOT / "output" / "mizuchi_projects")
    real_c_runs = project_manifests(ROOT / "output" / "experiment_real_c")
    recovered_index = load_json(ROOT / "output" / "kotor_recovered" / "INDEX.json", {})

    OUT.mkdir(parents=True)
    index: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda x: x["repo_path"]):
        repo_path = row["repo_path"]
        slug = row.get("slug") or slug_for(repo_path)
        folder = OUT / slug
        folder.mkdir()
        key = artifact_key(repo_path)
        function_count = None
        identity_count = 0
        if row.get("id") is not None:
            function_count = con.execute(
                "SELECT COUNT(*) FROM func WHERE binary_id=?", (row["id"],)).fetchone()[0]
            identity_count = con.execute(
                "SELECT COUNT(*) FROM identity WHERE binary_id=?", (row["id"],)).fetchone()[0]
        c_rows = list(selected.get(slug) or [])
        raw = ROOT / "extract" / "raw" / key
        funcbytes = ROOT / "extract" / "funcbytes" / f"{key}.jsonl"
        asm = ROOT / "output" / "kotor_reconstructed" / "src" / slug
        leaf = repo_to_leaf.get(repo_path)
        coverage_file = ROOT / "data" / "mizuchi_home" / "reports" / "coverage" / f"{leaf}.jsonl" if leaf else pathlib.Path()

        links = {
            "raw_image": link(raw, folder / "artifacts" / "raw_image"),
            "function_bytes": link(funcbytes, folder / "artifacts" / "function_bytes.jsonl"),
            "assembler_fallback": link(asm, folder / "source" / "asm"),
            "coverage_ledger": link(coverage_file, folder / "evidence" / "coverage.jsonl") if leaf else False,
        }
        stabs_files = [p for p in stabs_dir.glob("*") if key in p.name]
        for file in stabs_files:
            link(file, folder / "evidence" / "stabs" / file.name)
        verified_dir = AUTHORITATIVE / "src" / slug / "verified_c"
        links["verified_c"] = link(verified_dir, folder / "source" / "verified_c")

        # Keep every historical representation accessible, but label it by what
        # it is.  Only verified_c and asm participate in the authoritative
        # representation described above.
        for label, root, destination in (
            ("ghidra_cexport", ROOT / "extract" / "cexport", folder / "analysis" / "ghidra_cexport"),
            ("legacy_exact", ROOT / "output" / "exact", folder / "historical" / "exact"),
            ("legacy_exact_universal", ROOT / "output" / "exact_universal", folder / "historical" / "exact_universal"),
            ("legacy_export_asm", ROOT / "output" / "export_asm", folder / "historical" / "export_asm"),
            ("legacy_export_cpp", ROOT / "output" / "export_cpp", folder / "historical" / "export_cpp"),
            ("legacy_readable", ROOT / "output" / "kotor_readable", folder / "historical" / "readable"),
            ("legacy_source", ROOT / "output" / "kotor_source", folder / "historical" / "source"),
            ("legacy_unified", ROOT / "output" / "kotor_unified", folder / "historical" / "unified"),
        ):
            source = representation_dir(root, slug)
            links[label] = link(source, destination) if source else False
        links["ghidra_import"] = link(
            ROOT / "output" / "ghidra_import" / f"{slug}.jsonl",
            folder / "evidence" / "ghidra_import.jsonl")
        imported = pathlib.Path(repo_path)
        links["imported_executable"] = link(imported, folder / "artifacts" / "imported_executable") if imported.is_file() else False
        # The only buildable tree has a direct program-name correspondence.
        links["buildable_experiment"] = link(
            ROOT / "output" / "buildable" / pathlib.PurePosixPath(repo_path).name,
            folder / "experiments" / "buildable")
        permuter = representation_dir(ROOT / "output" / "permuter", slug)
        links["permuter_experiment"] = link(permuter, folder / "experiments" / "permuter") if permuter else False
        workspace = representation_dir(ROOT / "output" / "workspaces", slug)
        links["legacy_workspace"] = link(workspace, folder / "historical" / "workspace") if workspace else False
        # Roundtrip images are individual files rather than per-binary folders.
        roundtrip = ROOT / "output" / "roundtrip" / f"{slug}.image.S"
        if not roundtrip.exists():
            for candidate in (ROOT / "output" / "roundtrip").glob("*.image.S"):
                if SAFE.sub("_", candidate.name.removesuffix(".image.S")) == SAFE.sub("_", slug):
                    roundtrip = candidate
                    break
        links["roundtrip_image"] = link(roundtrip, folder / "historical" / "roundtrip.image.S")
        # This old package is global/sorted by source path, not per-binary. Its
        # index is therefore linked as a scoped evidence record instead of
        # pretending that its whole directory belongs to one program.
        links["historical_recovered_index"] = bool(leaf and leaf in (recovered_index.get("by_program") or {}))
        if links["historical_recovered_index"]:
            link(ROOT / "output" / "kotor_recovered" / "INDEX.json",
                 folder / "historical" / "recovered_candidates.index.json")
        for run in mizuchi_runs.get(repo_path, []):
            link(run, folder / "experiments" / "mizuchi_projects" / run.name)
        for run in real_c_runs.get(repo_path, []):
            link(run, folder / "experiments" / "real_c" / run.name)
        links["mizuchi_project_runs"] = bool(mizuchi_runs.get(repo_path))
        links["real_c_project_runs"] = bool(real_c_runs.get(repo_path))

        status = ("deferred_drm_ciphertext" if repo_path in canon.DRM_EXCLUDED else
                  "complete_assembler_with_selected_verified_c" if links["assembler_fallback"] else
                  "metadata_or_import_only")
        metadata = {
            "repo_path": repo_path,
            "slug": slug,
            "status": status,
            "database": row,
            "function_count_live": function_count,
            "identity_count_live": identity_count,
            "recorded_exact_coverage": coverage.get(repo_path),
            "selected_verified_c_count": len(c_rows),
            "artifact_links": links,
            "drm_excluded": repo_path in canon.DRM_EXCLUDED,
        }
        (folder / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
        lines = [f"# {slug}", "", f"Repository program: `{repo_path}`", "",
                 f"Status: **{status}**", "",
                 "## Available representation", ""]
        for label, present in links.items():
            lines.append(f"- `{label}`: {'available' if present else 'not available'}")
        lines += ["", f"- Extracted functions: **{function_count if function_count is not None else 'unknown'}**",
                  f"- Identity bindings: **{identity_count}**",
                  f"- Selected ledger-verified readable C/C++ functions: **{len(c_rows)}**", "",
                  "`source/verified_c/` overrides the corresponding addresses in `source/asm/`. "
                  "All unselected functions use the byte-preserving assembler fallback.", "",
                  "Everything under `analysis/`, `historical/`, and `experiments/` is retained as provenance "
                  "or investigation material; it is not asserted to be the final authoritative representation.", ""]
        (folder / "README.md").write_text("\n".join(lines))
        index.append({"slug": slug, "repo_path": repo_path, "status": status,
                      "functions": function_count, "selected_verified_c": len(c_rows)})

    summary = Counter(x["status"] for x in index)
    (OUT / "INDEX.json").write_text(json.dumps({"binaries": index, "status_counts": summary}, indent=2) + "\n")
    (OUT / "README.md").write_text(
        "# Binary collection\n\n"
        "One immediate subfolder per executable/program known to the warehouse. Each folder collects "
        "the authoritative metadata and every binary-addressable representation: raw input, "
        "extracted function bytes, STABS, coverage evidence, selected binmatched readable source, and "
        "complete assembler fallback. Links intentionally point at the one authoritative artifact rather "
        "than duplicating it. The small set of global, non-binary-addressable historical workspaces is "
        "listed separately in `UNMAPPED-GLOBAL-ARTIFACTS.md`; none is discarded.\n\n"
        f"Programs: **{len(index)}**. Statuses: `{dict(summary)}`.\n")
    (OUT / "UNMAPPED-GLOBAL-ARTIFACTS.md").write_text(
        "# Global artifacts not safely assignable to one binary\n\n"
        "This collection does not hide or delete these paths. They are global, mixed-program, scratch, "
        "or source-path-sorted, so linking them wholesale into a single executable folder would make "
        "the organization less accurate. The binary-addressable portions are linked from their respective "
        "program folders.\n\n"
        "- `data/mizuchi_home/`, `data/workspace/`, and `data/recovered-source-mirror/`: recovery ledgers, "
        "mixed run state, and unverified mirrors.\n"
        "- `data/quarantine/` and `data/tmp*`: rejected candidates and generated scratch fragments.\n"
        "- `output/kotor_recovered/`: one old source-path-sorted package. Its per-program counts are linked "
        "through its index only; its files do not encode a safe one-to-one binary directory mapping.\n"
        "- `output/roundtrip/_roundtrip.json`: cross-binary report; each individual image file is linked "
        "where its filename identifies a binary.\n"
        "- `output/mizuchi_projects/`: only runs with an explicit manifest `program` field are linked.\n"
        "- `output/workspaces/`, `output/exact*`, `output/export_*`, `output/kotor_*`, and `output/permuter/`: "
        "their per-binary subtrees are linked when they encode a program slug.\n")
    print(json.dumps({"binaries": len(index), "statuses": dict(summary)}, sort_keys=True))


if __name__ == "__main__":
    main()
