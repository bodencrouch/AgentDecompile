"""U139: decompile chunks with program affinity and continuation behind ``decompile-chunk``.

A chunk is a checkpoint (a packed program object, the pin of an ``analysis-slice``) plus a
sorted list of function entries.  The job decompiles each entry in that order, normalises the
text (``corpus.ghidra_bulk.sanitize_body`` in ``semantic`` mode: no invented layout or ABI, no
compiler on the path, pure Python -- the same text on every node), and emits **one object per
function** keyed by ``(entry, normalized_text_sha256)`` plus a **chunk manifest**.

**Continuation invariant.**  A chunk that hits its deadline mid-way flushes the covered subset
(``progress.json`` is rewritten atomically after every function, so a SIGTERM at the deadline
loses at most the function in flight) and names the rest: ``continuation_spec(spec, remaining)``
is a task of the same kind over the same checkpoint and the remaining entries in the same
order.  Because every row is a pure function of ``(checkpoint, entry, options)`` and a manifest
is sorted by entry, ``merge_manifests(partial, full_over_remaining)`` equals the manifest a
single uninterrupted run would have produced (``test_decompile_chunk_partial_plus_continuation_
equals_full``): same rows, same covered set, ``remaining == []``, ``complete == True``.  The
job also stops *cleanly* when less than one per-function budget remains, so most partials are
written by the job itself rather than by the kill.

**Affinity** (``ChunkAffinity``): ``SameNodeForSameSlice`` (working) keys a chunk's placement on
its checkpoint -- the partition subject is the checkpoint's object prefix, so every chunk of one
slice sits on one partition head and a node that has the checkpoint materialised keeps taking
that head; ``rank(holders)`` orders candidate nodes with the holders first.  It is a
*preference*: the only hard capability stays ``analyzer:<version>:<options_hash>`` (a
``program:<ref>`` capability would be a gate no canary proves).  ``LocalityByCache`` is the slot
that would rank by measured cache warmth.

The analyzer runs in a subprocess (``python -m agentdecompile_recovery.grid_lanes.analyzer_decompile
<job.json>``) with the task's deadline as a real kill and ``exit_after_jvm`` at the end (H14);
``execute_chunk_job`` is the in-JVM body.
"""
from __future__ import annotations

import dataclasses
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, ClassVar, Iterable, Mapping, Protocol, Sequence

from agentdecompile_grid.core import ObjectRef, Refused, TaskSpec, canonical_json, digest

from ._common import not_present
from .analyzer_import import IMPORTERS, PackedProgramImporter, analyzer_version, check_options, hex_addr, parse_addr

CHUNK_JOB_SCHEMA = "agentdecompile.grid.decompile-chunk.job.v1"
MANIFEST_SCHEMA = "agentdecompile.grid.decompile-chunk.manifest.v1"
PROGRESS_FILE = "progress.json"
FUNCTIONS_DIR = "fn"
REFUSAL_FILE = "refusal.json"
DEFAULT_PER_FUNCTION_S = 20
NORMALIZE_MODE = "semantic"


# --------------------------------------------------------------------------- rows and manifests
ROW_FIELDS = ("entry", "name", "size", "prototype", "calling_convention", "normalized_text_sha256", "error", "timed_out")


def function_key(entry: int, normalized_text_sha256: str) -> str:
    """The per-function object key ``<entry hex>:<sha256 of the normalised text>``."""
    return f"{hex_addr(entry)}:{normalized_text_sha256}"


def canonical_row(row: Mapping[str, Any]) -> dict[str, Any]:
    entry = parse_addr(row["entry"])
    text_sha = row.get("normalized_text_sha256")
    return {
        "entry": hex_addr(entry), "name": row.get("name") or None, "size": int(row.get("size") or 0),
        "prototype": row.get("prototype") or None, "calling_convention": row.get("calling_convention") or None,
        "normalized_text_sha256": str(text_sha) if text_sha else None,
        "error": row.get("error") or None, "timed_out": bool(row.get("timed_out", False)),
        "key": function_key(entry, str(text_sha)) if text_sha else None,
    }


def sorted_entries(entries: Iterable[Any]) -> list[int]:
    return sorted({parse_addr(e) for e in entries})


def chunk_manifest(entries: Sequence[Any], rows: Iterable[Mapping[str, Any]], *, checkpoint: str, options_hash: str) -> dict[str, Any]:
    """The manifest: every requested entry, the rows produced (sorted by entry), covered and
    remaining entry lists, ``complete`` when nothing remains."""
    wanted = sorted_entries(entries)
    by_entry = {parse_addr(r["entry"]): canonical_row(r) for r in rows if parse_addr(r["entry"]) in set(wanted)}
    covered = sorted(by_entry)
    remaining = [e for e in wanted if e not in by_entry]
    return {
        "schema": MANIFEST_SCHEMA, "checkpoint": str(checkpoint), "options_hash": str(options_hash), "normalize_mode": NORMALIZE_MODE,
        "entries": [hex_addr(e) for e in wanted], "rows": [by_entry[e] for e in covered],
        "covered": [hex_addr(e) for e in covered], "remaining": [hex_addr(e) for e in remaining], "complete": not remaining,
    }


def merge_manifests(partial: Mapping[str, Any], continuation: Mapping[str, Any]) -> dict[str, Any]:
    """The manifest of *partial* plus a continuation over its remaining entries.  Both must name
    the same checkpoint and options; the continuation's entries must be within the partial's
    remaining set (a continuation never re-covers what the partial already covered)."""
    for field in ("checkpoint", "options_hash", "normalize_mode"):
        if partial.get(field) != continuation.get(field):
            raise Refused(f"manifest-merge-mismatch:{field}")
    remaining = set(partial.get("remaining", ()))
    extra = sorted(set(continuation.get("entries", ())) - remaining)
    if extra:
        raise Refused(f"manifest-merge-continuation-outside-remaining:{len(extra)}")
    rows = list(partial.get("rows", ())) + list(continuation.get("rows", ()))
    return chunk_manifest(partial["entries"], rows, checkpoint=str(partial["checkpoint"]), options_hash=str(partial["options_hash"]))


def manifest_hash(manifest: Mapping[str, Any]) -> str:
    return digest(canonical_json(manifest))


def continuation_spec(spec: TaskSpec, remaining: Sequence[Any], entries_ref: ObjectRef) -> TaskSpec:
    """The continuation task: same kind, version, checkpoint, params, projection and basis; the
    ``entries`` input replaced by the object holding *remaining* (sorted).  Its id is a pure
    function of that content, so a second node that also stopped at the same point names the
    same continuation."""
    if not remaining:
        raise Refused("continuation-without-remaining")
    inputs = {**{k: ObjectRef(v) for k, v in spec.inputs.items()}, "entries": ObjectRef(entries_ref)}
    return dataclasses.replace(spec, inputs=inputs, partition="")


def entries_object_bytes(entries: Iterable[Any]) -> bytes:
    return canonical_json([hex_addr(e) for e in sorted_entries(entries)])


# --------------------------------------------------------------------------- affinity
class ChunkAffinity(Protocol):
    """Where a chunk prefers to run.  ``subject(checkpoint)`` is the partition subject the planner
    uses; ``rank(checkpoint, holders)`` orders candidate node keys, preferred first."""

    name: ClassVar[str]

    def subject(self, checkpoint: ObjectRef) -> str: ...

    def rank(self, checkpoint: ObjectRef, holders: Mapping[str, Iterable[str]]) -> list[str]: ...


@dataclasses.dataclass(frozen=True)
class SameNodeForSameSlice:
    """Working: all chunks of one checkpoint share a partition subject (the checkpoint's object
    prefix), and nodes that hold the checkpoint object rank first, ties by key id."""

    name: ClassVar[str] = "same-node-for-same-slice"

    def subject(self, checkpoint: ObjectRef) -> str:
        return ObjectRef(checkpoint).hex[:12]

    def rank(self, checkpoint: ObjectRef, holders: Mapping[str, Iterable[str]]) -> list[str]:
        target = ObjectRef(checkpoint).hex
        has = {node for node, held in holders.items() if any(ObjectRef(h).hex == target for h in held)}
        return sorted(has) + sorted(set(holders) - has)


@dataclasses.dataclass(frozen=True)
class LocalityByCache:
    """Slot: rank by measured cache warmth (materialised checkpoint age, open-program residency)."""

    name: ClassVar[str] = "locality-by-cache"

    def subject(self, checkpoint: ObjectRef) -> str:
        raise not_present("LocalityByCache (rank by measured cache warmth)")

    def rank(self, checkpoint: ObjectRef, holders: Mapping[str, Iterable[str]]) -> list[str]:
        raise not_present("LocalityByCache (rank by measured cache warmth)")


AFFINITIES: dict[str, Any] = {a.name: a for a in (SameNodeForSameSlice, LocalityByCache)}


def chunk_affinity(name: str | None = None) -> ChunkAffinity:
    chosen = name or SameNodeForSameSlice.name
    if chosen not in AFFINITIES:
        raise Refused(f"chunk-affinity-unknown:{chosen}:known {sorted(AFFINITIES)}")
    return AFFINITIES[chosen]()


# --------------------------------------------------------------------------- the in-JVM job
def normalize_text(code: str) -> str:
    from ..corpus.ghidra_bulk import sanitize_body

    return sanitize_body(code or "", mode=NORMALIZE_MODE)


def _write_json(path: Path, value: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(canonical_json(value))
    os.replace(tmp, path)


def _decompile_one(program, decompiler, entry: int, per_function_s: int, monitor) -> tuple[dict[str, Any], str | None]:
    address = program.getAddressFactory().getDefaultAddressSpace().getAddress(entry)
    fn = program.getFunctionManager().getFunctionAt(address)
    if fn is None:
        return {"entry": entry, "error": "missing-function"}, None
    row: dict[str, Any] = {
        "entry": entry, "name": str(fn.getName()), "size": int(fn.getBody().getNumAddresses()),
        "prototype": str(fn.getPrototypeString(False, False)), "calling_convention": str(fn.getCallingConventionName() or ""),
    }
    result = decompiler.decompileFunction(fn, int(per_function_s), monitor)
    if not result.decompileCompleted():
        message = str(result.getErrorMessage() or "")
        row.update({"error": "decompile-failed", "timed_out": "timed out" in message.lower() or "timeout" in message.lower()})
        return row, None
    decompiled = result.getDecompiledFunction()
    text = normalize_text(str(decompiled.getC()) if decompiled is not None else "")
    row["normalized_text_sha256"] = digest(text.encode("utf-8"))
    return row, text


def execute_chunk_job(job: Mapping[str, Any]) -> dict[str, Any]:
    """Open the checkpoint in a private temp project, decompile the entries in order, flush
    ``progress.json`` after each one, stop cleanly when the wall budget cannot fit another
    function.  Returns the progress payload; refusals as ``{"refused": <reason>}``."""
    from ..corpus import ghidra_env

    if job.get("schema") != CHUNK_JOB_SCHEMA:
        return {"refused": "chunk-job-schema"}
    out_dir = Path(str(job["out_dir"]))
    out_dir.mkdir(parents=True, exist_ok=True)
    fn_dir = out_dir / FUNCTIONS_DIR
    fn_dir.mkdir(exist_ok=True)
    started = time.monotonic()
    try:
        check_options(str(job.get("options_hash") or ""))
        entries = sorted_entries(job.get("entries") or ())
        if not entries:
            raise Refused("chunk-without-entries")
        per_function_s = max(1, int(job.get("per_function_s") or DEFAULT_PER_FUNCTION_S))
        deadline_s = float(job.get("deadline_s") or 0)
        if not ghidra_env.start():
            raise Refused("analyzer-not-present")
        version = analyzer_version() or ""
        expected = str(job.get("analyzer_version") or "")
        if expected and expected != version:
            raise Refused(f"analyzer-version-mismatch:{version}!={expected}")
        importer = IMPORTERS.get(str(job.get("importer") or PackedProgramImporter.name))
        if importer is None:
            raise Refused(f"importer-unknown:{job.get('importer')}")
        progress: dict[str, Any] = {
            "schema": CHUNK_JOB_SCHEMA, "analyzer_version": version, "rows": [], "remaining": [hex_addr(e) for e in entries],
            "stopped": None,
        }
        _write_json(out_dir / PROGRESS_FILE, progress)
        project, program = importer().open(Path(str(job["checkpoint"])), out_dir / "project", "checkpoint")
        try:
            from ghidra.app.decompiler import DecompInterface, DecompileOptions  # type: ignore[import-not-found]

            decompiler = DecompInterface()
            decompiler.setOptions(DecompileOptions())
            if not decompiler.openProgram(program):
                raise Refused("decompiler-open-failed")
            try:
                for i, entry in enumerate(entries):
                    elapsed = time.monotonic() - started
                    if deadline_s > 0 and deadline_s - elapsed < per_function_s + 2:
                        progress["stopped"] = "wall-budget"
                        break
                    row, text = _decompile_one(program, decompiler, entry, per_function_s, ghidra_env.monitor())
                    if text is not None:
                        (fn_dir / f"{hex_addr(entry)}.c").write_text(text, encoding="utf-8")
                    progress["rows"].append(canonical_row(row))
                    progress["remaining"] = [hex_addr(e) for e in entries[i + 1:]]
                    _write_json(out_dir / PROGRESS_FILE, progress)
            finally:
                decompiler.dispose()
        finally:
            try:
                project.close(program)
            finally:
                project.close()
        progress["wall_s"] = round(time.monotonic() - started, 3)
        _write_json(out_dir / PROGRESS_FILE, progress)
        return progress
    except Refused as exc:
        _write_json(out_dir / REFUSAL_FILE, {"refused": exc.reason, "candidates": list(exc.candidates)})
        return {"refused": exc.reason}


def driver_argv(job_path: Path) -> list[str]:
    return [sys.executable, "-m", "agentdecompile_recovery.grid_lanes.analyzer_decompile", str(job_path)]


def main(argv: Sequence[str] | None = None) -> int:
    from ..corpus import ghidra_env

    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        sys.stderr.write("usage: analyzer_decompile <job.json>\n")
        return 64
    job = json.loads(Path(args[0]).read_text("utf-8"))
    rc = 0
    try:
        progress = execute_chunk_job(job)
        rc = 2 if "refused" in progress else 0
    finally:
        ghidra_env.exit_after_jvm(rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "AFFINITIES", "CHUNK_JOB_SCHEMA", "ChunkAffinity", "DEFAULT_PER_FUNCTION_S", "FUNCTIONS_DIR", "LocalityByCache", "MANIFEST_SCHEMA",
    "NORMALIZE_MODE", "PROGRESS_FILE", "ROW_FIELDS", "SameNodeForSameSlice", "canonical_row", "chunk_affinity", "chunk_manifest",
    "continuation_spec", "driver_argv", "entries_object_bytes", "execute_chunk_job", "function_key", "main", "manifest_hash",
    "merge_manifests", "normalize_text", "sorted_entries",
]
