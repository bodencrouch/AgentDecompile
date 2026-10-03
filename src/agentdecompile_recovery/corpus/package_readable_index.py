"""Write the top-level README and VS Code workspace for a readable-source tree.

Kept separate from the generator so the index can be regenerated after a
partial rebuild without re-emitting function bodies. *root* is required.
"""

from __future__ import annotations

import json
from pathlib import Path

README = """# Readable decompiled source

Binaries laid out under original source paths where those are known, with
struct/union/enum layouts in `include/types.h` per binary.

## Open it

```bash
code readable.code-workspace
```

## What each authority tier means

| tier | meaning |
|---|---|
| `verified-byte-exact` | recompiled and matched the shipped bytes. Proof. |
| `advisory-ghidra` | Ghidra decompilation. Readable, **not** verified against anything. |

Every function states its tier in its own header comment, and `MANIFEST.json`
in each binary directory records it machine-readably. The two are never merged
into a single "recovered" number.

## What this is not

These files are **not expected to compile**. Class declarations were never
recovered — only struct layouts.

## Per binary

"""


def _as_count(value, default: int = 0) -> int:
    """Coerce a manifest field to a count, tolerating a list (len) or junk (default).

    Manifests from other producers (e.g. ``corpus package``'s generic
    workspace MANIFEST.json, which uses ``files`` for a list of paths rather
    than a count) must not crash index generation; they just contribute 0/len.
    """
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, (list, tuple, set)):
        return len(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _manifest_counts(directory: Path, manifest: dict) -> dict:
    functions = manifest.get("functions")
    if isinstance(functions, list):
        verified = sum(1 for f in functions if (f.get("authority") or "") == "verified-byte-exact")
        advisory = sum(1 for f in functions if (f.get("authority") or "") == "advisory-ghidra")
        return {
            "functions_written": _as_count(manifest.get("functions_written"), len(functions)),
            "verified_byte_exact": _as_count(manifest.get("verified_byte_exact"), verified),
            "advisory_ghidra": _as_count(manifest.get("advisory_ghidra"), advisory),
            "types_exported": _as_count(manifest.get("types_exported"), 0),
            "files": _as_count(manifest.get("files"), len({f.get("source_file") for f in functions})),
        }
    return {
        "functions_written": _as_count(manifest.get("functions_written"), 0),
        "verified_byte_exact": _as_count(manifest.get("verified_byte_exact"), 0),
        "advisory_ghidra": _as_count(manifest.get("advisory_ghidra"), 0),
        "types_exported": _as_count(manifest.get("types_exported"), 0),
        "files": _as_count(manifest.get("files"), 0),
    }


def write_index(root: Path | str) -> dict:
    """Regenerate README + workspace file under *root* (required)."""
    dest = Path(root)
    if not dest.exists():
        raise FileNotFoundError(dest)
    rows, folders = [], []
    for directory in sorted(p for p in dest.iterdir() if p.is_dir()):
        mf = directory / "MANIFEST.json"
        if not mf.exists():
            continue
        counts = _manifest_counts(directory, json.loads(mf.read_text(encoding="utf-8")))
        rows.append(
            f"| `{directory.name}` | {counts['functions_written']:,} | "
            f"{counts['verified_byte_exact']:,} | {counts['advisory_ghidra']:,} | "
            f"{counts['types_exported']:,} | {counts['files']:,} |"
        )
        folders.append({"name": directory.name, "path": directory.name})

    text = README + (
        "| binary | functions | verified byte-exact | advisory | types | files |\n"
        "|---|---:|---:|---:|---:|---:|\n" + "\n".join(rows) + "\n"
    )
    (dest / "README.md").write_text(text, encoding="utf-8")
    workspace = dest / "readable.code-workspace"
    workspace.write_text(
        json.dumps(
            {
                "folders": folders,
                "settings": {
                    "C_Cpp.errorSquiggles": "disabled",
                    "C_Cpp.intelliSenseEngine": "default",
                    "files.associations": {"*.c": "cpp"},
                    "search.exclude": {"**/MANIFEST.json": True},
                },
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    return {"binaries": len(rows), "readme": str(dest / "README.md"), "workspace": str(workspace)}
