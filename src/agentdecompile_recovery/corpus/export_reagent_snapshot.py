"""Export selected cached decompilations for ReAgent without live analysis.

The output is a provider input proposal, never recovery acceptance. Cache program
names and row hashes do not verify which original binary produced the analysis.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Sequence


def _address(value: str | int) -> str:
    if isinstance(value, bool):
        raise ValueError("Addresses must be hexadecimal strings or integers")
    try:
        number = value if isinstance(value, int) else int(value, 16)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid address: {value!r}") from exc
    if number < 0 or number >= 2**64:
        raise ValueError("Address outside unsigned 64-bit range")
    return f"{number:08x}"


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _row_value(value: object) -> object:
    return {"sqlite_blob_hex": value.hex()} if isinstance(value, bytes) else value


def _write(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def export_reagent_snapshot(*, knowledge_db: Path, program: str,
                            addresses: Sequence[str | int], output_dir: Path,
                            max_functions: int = 100) -> dict:
    """Materialize a bounded SQLite snapshot, then publish its manifest last.

    Uses the existing (program, entry_hex) cache lookup contract. No caller-supplied
    binary digest is promoted into provenance. Missing or unsupported evidence is
    exported as ReAgent schema-1 gaps. An incomplete output has no manifest and
    must not be consumed; the reserved directory is retained for diagnosis.
    """
    if not program or not isinstance(program, str):
        raise ValueError("An exact cache program name is required")
    if type(max_functions) is not int or not 1 <= max_functions <= 1000:
        raise ValueError("max_functions must be between 1 and 1000")
    if not addresses or len(addresses) > max_functions:
        raise ValueError("Selected addresses must be nonempty and within max_functions")
    selected = sorted({_address(value) for value in addresses})
    if len(selected) != len(addresses):
        raise ValueError("Duplicate selected addresses after normalization")
    knowledge_db = Path(knowledge_db).resolve(strict=True)
    output_dir = Path(output_dir).absolute()
    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError(f"Snapshot destination already exists: {output_dir}")

    # Match the existing cache exporter: indexed point reads at the program's
    # recorded address width, with one read transaction for coherent row contents.
    con = sqlite3.connect(knowledge_db.as_uri() + "?mode=ro", uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    rows: dict[str, dict] = {}
    try:
        con.execute("PRAGMA query_only=ON")
        con.execute("BEGIN")
        columns = {row[1] for row in con.execute("PRAGMA table_info(func_knowledge)")}
        if not {"program", "entry_hex", "decompiled", "asm"} <= columns:
            raise ValueError("Unsupported func_knowledge schema: required cache columns missing")
        sample = con.execute("SELECT entry_hex FROM func_knowledge WHERE program=? LIMIT 1", (program,)).fetchone()
        width = len(sample[0]) if sample else 8
        for address in selected:
            key = f"{int(address, 16):0{width}x}"
            matches = con.execute("SELECT * FROM func_knowledge WHERE program=? AND entry_hex=? LIMIT 2", (program, key)).fetchall()
            if len(matches) > 1:
                raise ValueError(f"Ambiguous cache rows for {program}:{address}")
            if matches:
                rows[address] = {name: _row_value(matches[0][name]) for name in matches[0].keys()}
        con.commit()
    finally:
        con.close()

    output_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
    index: dict = {}
    entries: list[dict] = []
    gaps: list[dict] = []
    files: dict[str, str] = {}
    def gap(address: str, reason: str) -> dict:
        return {"function": address, "reason": reason, "origin": "AgentDecompile func_knowledge cache", "kind": "unavailable"}
    for address in selected:
        row = rows.get(address)
        if row is None:
            missing = gap(address, "Selected function is absent under the cache program/address key")
            gaps.append(missing)
            entries.append({"address": address, "state": "missing"})
            continue
        row_gaps = [gap(address, "Original binary identity is not verified by this cache export")]
        # This cache contract stores code/assembly, not a complete context export.
        # Absent evidence stays absent; do not turn unknown calls into empty sets.
        for field in ("callers", "callees", "cfg", "pcode", "data_refs", "strings"):
            row_gaps.append(gap(address, f"{field} is not exported by this cache adapter"))
        name = row.get("name") or row.get("function_name") or f"FUN_{address}"
        payload: dict = {"schema_version": 1, "address": address, "name": str(name), "gaps": row_gaps}
        for field in ("signature", "calling_convention"):
            if isinstance(row.get(field), str) and row[field].strip():
                payload[field] = row[field]
            else:
                row_gaps.append(gap(address, f"Cached {field} is unavailable"))
        code = row.get("decompiled")
        if isinstance(code, str) and code.strip():
            payload["decompiled"] = code
        else:
            row_gaps.append(gap(address, "Cached decompiled source is unavailable"))
        asm = row.get("asm")
        if isinstance(asm, str) and asm.strip():
            payload["assembly"] = asm.splitlines()
        else:
            row_gaps.append(gap(address, "Cached assembly is unavailable"))
        row_digest = _digest(_json_bytes(row))
        payload["agentdecompile_provenance"] = {"program": program, "row_sha256": row_digest, "binary_binding": "unverified"}
        data = _json_bytes(payload)
        filename = address + ".json"
        _write(output_dir / filename, data)
        files[filename] = _digest(data)
        index[address] = {"name": str(name)}
        entries.append({"address": address, "state": "exported", "row_sha256": row_digest,
                        "recorded_metadata": {key: value for key, value in row.items() if key not in ("decompiled", "asm")}})
        gaps.extend(row_gaps)
    index_data = _json_bytes(index)
    _write(output_dir / "_index.json", index_data)
    files["_index.json"] = _digest(index_data)
    manifest = {"schema_version": 1, "kind": "agentdecompile-reagent-snapshot", "provider_schema": "ghidra-json/1",
                "program": program, "cache_path": str(knowledge_db), "selected_addresses": selected,
                "cache_columns": sorted(columns), "rows": entries, "files": files, "gaps": gaps,
                "binary_binding": {"state": "unverified", "reason": "Cache rows and program labels alone do not corroborate original binary identity"},
                "acceptance": "none; provider input proposal only"}
    manifest["materialized_rows_sha256"] = _digest(_json_bytes({address: rows[address] for address in sorted(rows)}))
    _write(output_dir / ".manifest.pending", _json_bytes(manifest))
    os.replace(output_dir / ".manifest.pending", output_dir / "manifest.json")
    fd = os.open(output_dir, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    parent_fd = os.open(output_dir.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)
    return manifest
