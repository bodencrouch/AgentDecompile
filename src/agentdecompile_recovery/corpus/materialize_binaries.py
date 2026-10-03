"""Physically consolidate every binary-addressable warehouse artifact.

This is intentionally a one-way organization pass. It moves, rather than
copies, known per-binary artifacts into ``output/binaries/<slug>`` and replaces
the collection's temporary links with real files/directories. It never moves a
mixed-program workspace whose manifest does not name a program.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import sys
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from . import corpus_config, db
from .package_binaries import ROOT, OUT, SAFE, artifact_key, project_manifests, representation_dir


def replace_link_and_move(source: pathlib.Path | None, destination: pathlib.Path,
                          moved: list[dict[str, str]]) -> None:
    """Replace the expected collection symlink with the actual source object."""
    if source is None or not source.exists():
        return
    if destination.is_symlink():
        destination.unlink()
    elif destination.exists():
        raise RuntimeError(f"destination already materialized: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    moved.append({"from": str(source.relative_to(ROOT)), "to": str(destination.relative_to(ROOT))})


def main() -> None:
    if not OUT.is_dir():
        raise SystemExit(f"missing collection: {OUT}")
    con = db.connect()
    rows = [dict(r) for r in con.execute("SELECT * FROM binary ORDER BY repo_path")]
    rows = [r for r in rows if pathlib.PurePosixPath(r["repo_path"]).name != "repos"]
    known = {r["repo_path"] for r in rows}
    # Some canonical payloads are intentionally catalogued in programs.txt but
    # do not have a database row. They must still be physically consolidated.
    for program in (ROOT / "scripts" / "programs.txt").read_text().splitlines():
        program = program.strip()
        if program and program not in known:
            rows.append({"repo_path": program, "slug": SAFE.sub("_", artifact_key(program))})
    maps = corpus_config.load_maps()
    repo_to_leaf = {v: k for k, v in dict(maps.get("leaf_to_repo") or {}).items()}
    mizuchi = project_manifests(ROOT / "output" / "mizuchi_projects")
    real_c = project_manifests(ROOT / "output" / "experiment_real_c")
    moved: list[dict[str, str]] = []
    by_binary: dict[str, int] = defaultdict(int)

    for row in rows:
        repo_path = row["repo_path"]
        slug = row.get("slug") or SAFE.sub("_", artifact_key(repo_path))
        folder = OUT / slug
        if not folder.is_dir():
            raise RuntimeError(f"missing binary folder: {folder}")
        key = artifact_key(repo_path)
        leaf = repo_to_leaf.get(repo_path)
        operations: list[tuple[pathlib.Path | None, pathlib.Path]] = [
            (ROOT / "extract" / "raw" / key, folder / "artifacts" / "raw_image"),
            (ROOT / "extract" / "funcbytes" / f"{key}.jsonl", folder / "artifacts" / "function_bytes.jsonl"),
            (ROOT / "output" / "kotor_reconstructed" / "src" / slug, folder / "source" / "asm"),
            (ROOT / "output" / "kotor_authoritative" / "src" / slug / "verified_c", folder / "source" / "verified_c"),
            (ROOT / "output" / "ghidra_import" / f"{slug}.jsonl", folder / "evidence" / "ghidra_import.jsonl"),
            (ROOT / "output" / "buildable" / pathlib.PurePosixPath(repo_path).name, folder / "experiments" / "buildable"),
        ]
        if leaf:
            operations.append((ROOT / "data" / "mizuchi_home" / "reports" / "coverage" / f"{leaf}.jsonl",
                               folder / "evidence" / "coverage.jsonl"))
        imported = pathlib.Path(repo_path)
        if imported.is_file():
            operations.append((imported, folder / "artifacts" / "imported_executable"))
        for label, root, dest in (
            ("ghidra_cexport", ROOT / "extract" / "cexport", folder / "analysis" / "ghidra_cexport"),
            ("exact", ROOT / "output" / "exact", folder / "historical" / "exact"),
            ("exact_universal", ROOT / "output" / "exact_universal", folder / "historical" / "exact_universal"),
            ("export_asm", ROOT / "output" / "export_asm", folder / "historical" / "export_asm"),
            ("export_cpp", ROOT / "output" / "export_cpp", folder / "historical" / "export_cpp"),
            ("readable", ROOT / "output" / "kotor_readable", folder / "historical" / "readable"),
            ("source", ROOT / "output" / "kotor_source", folder / "historical" / "source"),
            ("unified", ROOT / "output" / "kotor_unified", folder / "historical" / "unified"),
            ("workspace", ROOT / "output" / "workspaces", folder / "historical" / "workspace"),
            ("permuter", ROOT / "output" / "permuter", folder / "experiments" / "permuter"),
        ):
            del label
            operations.append((representation_dir(root, slug), dest))
        for stabs in (ROOT / "extract" / "stabs").glob("*"):
            if key in stabs.name:
                operations.append((stabs, folder / "evidence" / "stabs" / stabs.name))
        for candidate in (ROOT / "output" / "roundtrip").glob("*.image.S"):
            if SAFE.sub("_", candidate.name.removesuffix(".image.S")) == SAFE.sub("_", slug):
                operations.append((candidate, folder / "historical" / "roundtrip.image.S"))
                break
        for run in mizuchi.get(repo_path, []):
            operations.append((run, folder / "experiments" / "mizuchi_projects" / run.name))
        for run in real_c.get(repo_path, []):
            operations.append((run, folder / "experiments" / "real_c" / run.name))
        before = len(moved)
        for source, destination in operations:
            replace_link_and_move(source, destination, moved)
        by_binary[slug] += len(moved) - before

    report = {
        "purpose": "physical binary-addressable artifact consolidation",
        "moved_entries": len(moved),
        "moved_by_binary": dict(sorted(by_binary.items())),
        "moved": moved,
        "not_moved": [
            "Mixed-program/recovery-root data remains outside this collection until it has explicit binary provenance.",
            "The source-path-sorted output/kotor_recovered package remains global; only its scoped index is linked.",
            "Rejected candidates, temporary fragments, and cross-binary report files remain global evidence.",
        ],
    }
    (OUT / "CONSOLIDATION.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"moved_entries": len(moved), "binaries_touched": sum(bool(v) for v in by_binary.values())}))


if __name__ == "__main__":
    main()
