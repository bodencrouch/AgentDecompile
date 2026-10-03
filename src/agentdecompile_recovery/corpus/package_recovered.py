"""Package only functions whose source_claim is recovered."""

from __future__ import annotations

import re
from pathlib import Path

from .coverage_evidence import source_binding
from .package_readable import map_source_path, package_readable
from .source_claims import is_real_c, is_recovered_source
from .semantic_identity import CLAIM_SCOPE, STABS_CLAIM_SCOPE, recorded_target_name

_SAFE_NAME = re.compile(r"[^A-Za-z0-9_.+-]")


def _safe_seg(s: str) -> str:
    s = _SAFE_NAME.sub("_", s).strip("._")
    return s or "unnamed"


def names_agree(recovered: str, best: str | None) -> bool:
    if not best:
        return False
    if recovered == best:
        return True
    last = best.split("::")[-1]
    return recovered == last


def dest_for(src: str | None, program: str, name: str, addr: int | None,
             out_dir: Path) -> Path:
    if src:
        rel = map_source_path(src)
        stem = Path(rel)
        if stem.suffix:
            stem = stem.with_suffix("")
        dest_dir = Path(out_dir) / stem
    else:
        dest_dir = Path(out_dir) / "unsorted" / _safe_seg(program)
    dest_dir.mkdir(parents=True, exist_ok=True)
    base = dest_dir / f"{_safe_seg(name)}.c"
    if base.exists():
        extra = f"{addr:x}" if addr is not None else _safe_seg(program)
        base = dest_dir / f"{_safe_seg(name)}_{extra}.c"
    return base


def package_from_store(con, out_dir: Path) -> dict:
    """Export readable source snapshots with a matching stored observation digest.

    This checks source freshness only, not linked-image or semantic acceptance.
    Legacy rows remain candidates; packaging never fabricates their digest.
    """
    written = named_files = target_local_files = 0
    rejected = []
    try:
        columns = {row[1] for row in con.execute("PRAGMA table_info(recovered_function)")}
        digest_column = "source_sha256" if "source_sha256" in columns else "NULL AS source_sha256"
        semantic_columns = ", ".join(column if column in columns else f"NULL AS {column}" for column in
                                     ("target_sha256", "semantic_status", "semantic_reason", "semantic_evidence"))
        rows = list(con.execute(
            "SELECT program, name, path, addr, size, binary_id, " + digest_column + ", " + semantic_columns
            + " FROM recovered_function WHERE real_c=1"
        ))
    except Exception as exc:
        return {"files": 0, "named_files": 0, "target_local_files": 0, "source_binding_rejections": [], "error": str(exc)}
    for row in rows:
        rejection = {"program": row["program"], "name": row["name"], "path": row["path"]}
        try:
            source_bytes = Path(row["path"]).read_bytes()
        except OSError:
            rejected.append({**rejection, "reason": "source_unavailable"})
            continue
        binding = source_binding({"sourceSha256": row["source_sha256"]}, source_bytes)
        if not binding["current"]:
            rejected.append({**rejection, "reason": binding["reason"]})
            continue
        try:
            text = source_bytes.decode("utf-8")
        except UnicodeDecodeError:
            rejected.append({**rejection, "reason": "source_not_utf8"})
            continue
        if not is_real_c(text):
            rejected.append({**rejection, "reason": "source_not_readable_c"})
            continue
        witnessed_name = recorded_target_name(dict(row))
        if witnessed_name is None and (type(row["addr"]) is not int or row["addr"] < 0):
            rejected.append({**rejection, "reason": "target_address_unavailable"})
            continue
        output_name = witnessed_name or f"sub_{row['addr']:08x}"
        dest = dest_for(None, row["program"], output_name, row["addr"], Path(out_dir))
        # Check and export the same snapshot, preserving bytes and user files.
        collision = 0
        first_dest = dest
        while True:
            try:
                with dest.open("xb") as stream:
                    stream.write(source_bytes)
                break
            except FileExistsError:
                collision += 1
                dest = first_dest.with_name(f"{first_dest.stem}_{collision}.c")
        written += 1
        named_files += witnessed_name is not None
        target_local_files += witnessed_name is None
    return {"files": written, "named_files": named_files, "target_local_files": target_local_files,
            "named_claim": f"recorded ingestion-time {CLAIM_SCOPE} or {STABS_CLAIM_SCOPE}; target not rechecked during packaging",
            "source_binding_rejections": rejected}


def package_recovered(functions: list[dict], out_dir: Path, *, binary_id: str) -> dict:
    kept = [
        row
        for row in functions
        if row.get("source_claim") == "recovered"
        or is_recovered_source(row.get("source") or row.get("body") or "")
    ]
    return package_readable(kept, out_dir, binary_id=binary_id)
