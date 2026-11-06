"""Move program-partitioned recovered-source trees into their binary folders."""

from __future__ import annotations

import json
import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from . import corpus_config
from .package_binaries import OUT, ROOT, SAFE, artifact_key


def main() -> None:
    source_root = ROOT / "data" / "mizuchi_home" / "recovered-source"
    ghidra_root = ROOT / "data" / "mizuchi_home" / "recovered-source-ghidra"
    mirror_root = ROOT / "data" / "recovered-source-mirror"
    maps = corpus_config.load_maps()
    leaf_to_repo = dict(maps.get("leaf_to_repo") or {})
    moved: list[dict[str, str]] = []

    # The parenthesized capture is a duplicate naming variant of the canonical
    # K1 GOG program; preserving its own directory retains that provenance.
    aliases = {"k1_win_gog_swkotor (1).exe": "/K1/k1_win_gog_swkotor.exe"}
    for root, label in ((source_root, "recovered_candidates"),
                        (ghidra_root, "ghidra_recovered_candidates"),
                        (mirror_root, "recovered_source_mirror")):
        if not root.exists():
            continue
        for candidate in sorted(root.iterdir()):
            if not candidate.is_dir():
                continue
            repo_path = leaf_to_repo.get(candidate.name) or aliases.get(candidate.name)
            if repo_path is None:
                continue
            slug = SAFE.sub("_", artifact_key(repo_path))
            destination = OUT / slug / "historical" / label / candidate.name
            if destination.exists() or destination.is_symlink():
                raise RuntimeError(f"destination exists: {destination}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(candidate), str(destination))
            moved.append({"from": str(candidate.relative_to(ROOT)), "to": str(destination.relative_to(ROOT))})

    # The old recovered package has one small global index. Materialize a copy
    # beside every program it summarizes instead of leaving collection links.
    index = ROOT / "output" / "kotor_recovered" / "INDEX.json"
    copied: list[str] = []
    if index.is_file():
        by_program = json.loads(index.read_text()).get("by_program") or {}
        for leaf in by_program:
            repo_path = leaf_to_repo.get(leaf) or aliases.get(leaf)
            if repo_path is None:
                continue
            destination = (OUT / SAFE.sub("_", artifact_key(repo_path)) / "historical" /
                           "recovered_candidates.index.json")
            if destination.is_symlink():
                destination.unlink()
            if not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(index, destination)
                copied.append(str(destination.relative_to(ROOT)))

    report_path = OUT / "CONSOLIDATION.json"
    report = json.loads(report_path.read_text())
    report["recovery_candidate_moves"] = moved
    report["recovery_candidate_index_copies"] = copied
    report["moved_entries"] += len(moved) + len(copied)
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"moved_program_trees": len(moved)}))


if __name__ == "__main__":
    main()
