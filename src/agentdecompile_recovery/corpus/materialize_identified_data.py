"""Move remaining program-keyed data files into their executable folders."""

from __future__ import annotations

import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from . import corpus_config
from .package_binaries import OUT, ROOT, SAFE, artifact_key


def destination(repo_path: str, *parts: str) -> pathlib.Path:
    return OUT / SAFE.sub("_", artifact_key(repo_path)) / pathlib.Path(*parts)


def move(source: pathlib.Path, target: pathlib.Path, moved: list[str]) -> None:
    if not source.exists():
        return
    if target.exists():
        raise RuntimeError(f"destination exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))
    moved.append(f"{source.relative_to(ROOT)} -> {target.relative_to(ROOT)}")


def main() -> None:
    leaf_to_repo = dict(corpus_config.load_maps().get("leaf_to_repo") or {})
    aliases = {
        "JadeEmpire.exe (1)": "/JE/JadeEmpire.exe",
        "k1_android_ARM64 (1)": "/K1/k1_android_ARM64",
        "k1_win_gog_swkotor.exe (1)": "/K1/k1_win_gog_swkotor.exe",
        "k2_linux_swkotor2.elf (1)": "/TSL/k2_linux_swkotor2.elf",
        "k2_win_CD_1.0_swkotor2.exe (1)": "/TSL/k2_win_CD_1.0_swkotor2.exe",
        "k1_win_gog_swkotor.exe.keep": "/K1/k1_win_gog_swkotor.exe.keep",
    }
    moved: list[str] = []
    for source in sorted((ROOT / "data" / "coverage-mirror").glob("*.jsonl*")):
        stem = source.name.removesuffix(".broken-bak")
        leaf = stem.removesuffix(".jsonl")
        repo_path = leaf_to_repo.get(leaf) or aliases.get(leaf)
        if repo_path:
            move(source, destination(repo_path, "evidence", "historical_coverage", source.name), moved)
    for source in sorted((ROOT / "data" / "corpus" / "programs").glob("*.json")):
        repo_path = leaf_to_repo.get(source.stem)
        if repo_path:
            move(source, destination(repo_path, "metadata", "corpus_program.json"), moved)
    shims = ROOT / "data" / "quarantine" / "asm_shims_k1"
    move(shims, destination("/K1/k1_win_gog_swkotor.exe", "historical", "rejected_asm_shims"), moved)
    move(ROOT / "data" / "quarantine" / "asm_shims_k1_manifest.json",
         destination("/K1/k1_win_gog_swkotor.exe", "historical", "rejected_asm_shims.manifest.json"), moved)
    print({"moved": len(moved)})


if __name__ == "__main__":
    main()
