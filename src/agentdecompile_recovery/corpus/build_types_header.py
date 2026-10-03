"""Emit recovered game types as a compilable header.

Field names starting with a digit or that are C keywords are renamed. Size-check
assertions are retained and counted. Enum constants are prefixed with the enum
name so they cannot rewrite later type identifiers.
"""

from __future__ import annotations

import re
import hashlib
import json
import os
import tempfile

from .determinism_basis import basis, BASIS_HASH_EXCLUDED, _without
from pathlib import Path

C_KEYWORDS = {
    "auto", "break", "case", "char", "const", "continue", "default", "do",
    "double", "else", "enum", "extern", "float", "for", "goto", "if", "int",
    "long", "register", "return", "short", "signed", "sizeof", "static",
    "struct", "switch", "typedef", "union", "unsigned", "void", "volatile",
    "while", "class", "new", "delete", "this", "operator", "template",
}

FIELD_RE = re.compile(r"(^\s+[A-Za-z_][\w \*]*?\s+\*?)([A-Za-z_0-9]+)(\s*(?:\[[^\]]*\])?\s*;)", re.M)
SIZECHECK_RE = re.compile(r"typedef\s+char\s+_sizecheck_\w+\[[^\]]*\];\s*")
DEFINE_RE = re.compile(r"^#define\s+(\w+)(\s)", re.M)


def sanitise(defn: str, type_name: str) -> tuple[str, bool, int]:
    """Return (compilable definition, had_sizecheck, n_constants_prefixed)."""

    def field(match: re.Match) -> str:
        name = match.group(2)
        if name[0].isdigit() or name in C_KEYWORDS:
            name = "f_" + name
        return match.group(1) + name + match.group(3)

    had = bool(SIZECHECK_RE.search(defn))
    defn = FIELD_RE.sub(field, defn)
    n_const = 0
    if DEFINE_RE.search(defn):
        seen: set[str] = set()
        lines = []
        for line in defn.splitlines():
            match = DEFINE_RE.match(line)
            if not match:
                lines.append(line)
                continue
            n_const += 1
            nm = f"{type_name}_{match.group(1)}"
            if nm in seen:
                val = re.search(r"\((-?\d+)\)\s*\)\s*$", line)
                nm = f"{nm}_{val.group(1)}" if val else f"{nm}_dup"
            seen.add(nm)
            lines.append(f"#define {nm}{match.group(2)}{line[match.end():]}")
        defn = "\n".join(lines)
    return defn, had, n_const


def build_header(con, binary_id: int, out: Path | str, *, program: str = "") -> dict:
    """Write the header and ``<out>.manifest.json`` from one declared basis.

    ``program`` remains accepted for existing callers; host-specific source
    paths are excluded from artifact bytes in favor of the stable build slug.
    The receipt records analysis layout, not a successful native compilation.
    """
    declared_basis = basis(con)
    build = con.execute("SELECT slug, content_sha256 FROM binary WHERE id=?", (int(binary_id),)).fetchone()
    if build is None or not re.fullmatch(r"[0-9a-fA-F]{64}", str(build["content_sha256"] or "")):
        raise ValueError("header manifest requires the build content SHA-256")
    rows = con.execute(
        "SELECT name, kind, size, definition FROM ghidra_type"
        " WHERE binary_id=? AND definition IS NOT NULL AND definition<>''"
        " ORDER BY name",
        (int(binary_id),),
    ).fetchall()
    parts, n_sizecheck, n_const = [], 0, 0
    for row in rows:
        text, had, nc = sanitise(row["definition"], row["name"])
        n_sizecheck += had
        n_const += nc
        parts.append(text.rstrip() + "\n")

    dest = Path(out)
    label = str(build["slug"]).replace("*/", "* /").replace("\n", " ").replace("\r", " ")
    header = (
        "/* Recovered game types for " + label + ".\n"
        " * Field offsets and sizes are analysis of the shipped binary.\n"
        " * They are evidence about layout, NOT recovered source.\n"
        " * Enum constants are prefixed with their enum's name.\n"
        " */\n\n"
    )
    payload = (header + "#pragma once\n#pragma pack(push, 1)\n\n" + "\n".join(parts)
               + "\n#pragma pack(pop)\n").encode("utf-8")
    basis_payload = json.dumps(_without(declared_basis, BASIS_HASH_EXCLUDED),
                               sort_keys=True, separators=(",", ":")).encode("utf-8")
    toolchain = declared_basis["toolchain_identity_hash"]
    manifest = {
        "format": "agentdecompile.types-header/v1",
        "build": {"slug": build["slug"], "content_sha256": build["content_sha256"].lower()},
        "basis": declared_basis,
        "basis_hash": hashlib.sha256(basis_payload).hexdigest(),
        "toolchain": {"identity_hash": toolchain,
                      "status": "unrecorded" if toolchain in ("pinned:none", "unknown", "none") else "recorded"},
        "artifact": {"name": dest.name, "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)},
        "layout": {"size_assertions": n_sizecheck, "packing": 1,
                   "compiled_verification": "not_run"},
    }
    manifest_dest = dest.with_name(dest.name + ".manifest.json")
    manifest_payload = (json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode("utf-8")
    # Publish the receipt last. Readers must verify its artifact digest: a
    # crash between replacements cannot turn a stale receipt into acceptance.
    dest.parent.mkdir(parents=True, exist_ok=True)
    staged = []
    try:
        for target, content in ((dest, payload), (manifest_dest, manifest_payload)):
            fd, temporary = tempfile.mkstemp(prefix="." + target.name + ".", dir=dest.parent)
            staged.append((temporary, target))
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        for temporary, target in staged:
            os.replace(temporary, target)
    finally:
        for temporary, _ in staged:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
    return {
        "types": len(rows),
        "had_sizecheck": n_sizecheck,
        "enum_constants": n_const,
        "out": str(dest),
        "bytes": len(payload),
        "manifest": str(manifest_dest),
        "sha256": manifest["artifact"]["sha256"],
        "basis_hash": manifest["basis_hash"],
        "toolchain_status": manifest["toolchain"]["status"],
    }
