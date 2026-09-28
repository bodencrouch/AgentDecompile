"""Materialize binary-keyed Mizuchi seeds and enrichment records."""

from __future__ import annotations

import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from . import corpus_config
from .package_binaries import OUT, ROOT, SAFE, artifact_key


def main() -> None:
    source = ROOT / "output" / "mizuchi"
    leaf_to_repo = dict(corpus_config.load_maps().get("leaf_to_repo") or {})
    moved = 0
    seeds = source / "seeds"
    if seeds.exists():
        for item in sorted(seeds.iterdir()):
            target = OUT / item.name / "historical" / "mizuchi_seeds"
            if target.parent.parent.parent.is_dir() and not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(item), str(target))
                moved += 1
    enrichment = source / "enrichment"
    if enrichment.exists():
        for item in sorted(enrichment.glob("*.json")):
            repo_path = leaf_to_repo.get(item.stem)
            if repo_path is None:
                continue
            slug = SAFE.sub("_", artifact_key(repo_path))
            target = OUT / slug / "metadata" / "mizuchi_enrichment.json"
            if target.exists():
                raise RuntimeError(f"destination exists: {target}")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(item), str(target))
            moved += 1
    print({"moved": moved})


if __name__ == "__main__":
    main()
