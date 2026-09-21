"""Sort the old recovered package by the binary named in each source header."""

from __future__ import annotations

import pathlib
import re
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from . import corpus_config
from .package_binaries import OUT, ROOT, SAFE, artifact_key

PATTERN = re.compile(r"recovered from ([^\s*]+)")


def main() -> None:
    root = ROOT / "output" / "kotor_recovered"
    leaves = dict(corpus_config.load_maps().get("leaf_to_repo") or {})
    aliases = {"k1_win_gog_swkotor.exe.keep": "/K1/k1_win_gog_swkotor.exe.keep"}
    moved = 0
    unresolved: list[str] = []
    for source in list(root.rglob("*.c")):
        match = PATTERN.search(source.read_text(errors="replace")[:2048])
        if not match:
            unresolved.append(str(source.relative_to(root)))
            continue
        repo_path = leaves.get(match.group(1)) or aliases.get(match.group(1))
        if repo_path is None:
            unresolved.append(str(source.relative_to(root)))
            continue
        slug = SAFE.sub("_", artifact_key(repo_path))
        relative = source.relative_to(root)
        target = OUT / slug / "historical" / "old_recovered" / relative
        if target.exists():
            raise RuntimeError(f"destination exists: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        moved += 1
    (OUT / "OLD-RECOVERED-UNRESOLVED.txt").write_text("\n".join(unresolved) + "\n")
    print({"moved": moved, "unresolved": len(unresolved)})


if __name__ == "__main__":
    main()
