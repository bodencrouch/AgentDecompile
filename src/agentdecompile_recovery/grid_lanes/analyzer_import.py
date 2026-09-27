"""U137: headless import, analysis slices and the deterministic two-key pin behind ``analysis-slice``.

Three pieces, each a Protocol with one working implementation and named slots (charter §6c):

* ``ProgramImporter`` -- how a raw image becomes a program in a *private temp project*.
  ``HeadlessImporter`` (working) creates a throwaway project under the task's scratch and imports
  the image with the analyzer's default loader; ``ProjectSnapshotImporter`` (a program already in a
  project snapshot) and ``ServerCheckoutImporter`` (a checkout from a shared repository) are slots.
* ``SlicePlanner`` -- how an image's address space becomes slices with **stable keys**.
  ``ByFunctionCountSlicePlanner`` (working) walks a sorted function inventory and closes a slice
  every ``per_slice`` entries; a slice's key is its address range ``[lo, hi)`` spelled in hex, so
  the same inventory gives the same slices on every node regardless of discovery order.
  ``BySectionSlicePlanner`` and ``ByCallgraphCommunitySlicePlanner`` are slots.
* the **two-key pin** -- ``pin_two_key(sliced, monolithic)``: an analysis slice's checkpoint is a
  packed program whose inventory hash is recorded twice, once by the sliced task (analysis over
  the slice's ranges only) and once by the ``monolithic`` sentinel task the planner emits per image
  (analysis over the whole image, then the inventory restricted to each slice's ranges).  When the
  two agree the pin is that hash; when they diverge the pin is the **lexicographically minimal**
  hash, so every node picks the same one without talking, and the divergence is recorded
  (``{sliced, monolithic, pinned, diverged}``), never hidden.

The analyzer runs in a **subprocess** (``python -m agentdecompile_recovery.grid_lanes.analyzer_import
<job.json>``): the JVM never enters the worker's process, the task's deadline is a real kill
(``_common.run_argv``), and the driver ends with ``ghidra_env.exit_after_jvm`` (H14: a process with
a JVM never exits on its own).  ``execute_slice_job`` is the in-JVM body the driver calls; a caller
that already booted the analyzer may call it directly.

Facts the job exports next to the checkpoint (read JVM-free by ``analyzer_facts``):

* ``inventory.json`` -- ``[{entry, size, name}]`` sorted by entry (``name`` only when the analyzer
  did not generate it; else ``null``);
* ``references.json`` -- ``[{from, to, kind}]`` sorted by ``(from, to, kind)`` for memory
  references whose source address lies in the slice (call / jump / data / other);
* ``facts.json`` -- the analyzer's version, the inventory hash, per-slice hashes (monolithic
  mode), counts.

Address spellings are ``0x`` hex strings everywhere a value crosses into JSON; ``inventory_hash``
is the sha256 of the canonical JSON of the sorted inventory rows.
"""
from __future__ import annotations

import dataclasses
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, ClassVar, Iterable, Mapping, Protocol, Sequence

from agentdecompile_grid.core import NotConfigured, Refused, canonical_json, digest

from ._common import not_present

SLICE_JOB_SCHEMA = "agentdecompile.grid.analysis-slice.job.v1"
MODE_SLICED = "sliced"
MODE_MONOLITHIC = "monolithic"
MODES = (MODE_SLICED, MODE_MONOLITHIC)
PINNED_DEFAULT_OPTIONS = "pinned:headless-defaults"    # determinism_basis.ANALYZER_OPTIONS_HASH: the only option set this checkout knows
REFERENCE_KINDS = ("call", "jump", "data", "other")

INVENTORY_FILE = "inventory.json"
REFERENCES_FILE = "references.json"
FACTS_FILE = "facts.json"
CHECKPOINT_FILE = "checkpoint.gzf"
REFUSAL_FILE = "refusal.json"


# --------------------------------------------------------------------------- addresses and slices
def hex_addr(value: int) -> str:
    return f"0x{int(value):x}"


def parse_addr(value: Any) -> int:
    if isinstance(value, bool):
        raise Refused(f"address-not-a-number:{value!r}")
    if isinstance(value, int):
        return int(value)
    text = str(value).strip().lower()
    try:
        return int(text, 16) if text.startswith("0x") else int(text, 10)
    except ValueError:
        raise Refused(f"address-not-a-number:{text[:32]!r}") from None


@dataclasses.dataclass(frozen=True)
class SliceSpec:
    """One analysis slice: its index and its half-open address ranges ``[lo, hi)`` sorted by ``lo``.

    The *key* of a slice is its ranges, never its index: two planners that produce the same ranges
    produce the same task id (the index is a label the planner assigns in range order)."""

    index: int
    ranges: tuple[tuple[int, int], ...]

    def __post_init__(self) -> None:
        cleaned = tuple(sorted((int(lo), int(hi)) for lo, hi in self.ranges))
        for lo, hi in cleaned:
            if hi <= lo:
                raise Refused(f"slice-range-empty:{hex_addr(lo)}-{hex_addr(hi)}")
        object.__setattr__(self, "ranges", cleaned)

    def contains(self, address: int) -> bool:
        return any(lo <= address < hi for lo, hi in self.ranges)

    def to_json(self) -> dict[str, Any]:
        return {"index": int(self.index), "ranges": [[hex_addr(lo), hex_addr(hi)] for lo, hi in self.ranges]}

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> "SliceSpec":
        ranges = tuple((parse_addr(lo), parse_addr(hi)) for lo, hi in value.get("ranges", ()))
        if not ranges:
            raise Refused("slice-without-ranges")
        return cls(index=int(value.get("index", 0)), ranges=ranges)

    @property
    def key(self) -> str:
        """The stable key: ranges only (``0x10-0x20,0x40-0x80``)."""
        return ",".join(f"{hex_addr(lo)}-{hex_addr(hi)}" for lo, hi in self.ranges)


class SlicePlanner(Protocol):
    """Turn an image's facts into ``SliceSpec`` values ordered by their stable key."""

    name: ClassVar[str]

    def slices(self, inventory: Sequence[Mapping[str, Any]], per_slice: int) -> list[SliceSpec]: ...


@dataclasses.dataclass(frozen=True)
class ByFunctionCountSlicePlanner:
    """Working: close a slice every *per_slice* function entries of the sorted inventory.

    Slice *k* runs from its first entry to the next slice's first entry (the last slice to the end
    of its last function, ``entry + size``), so ranges never overlap, leave no gap between
    functions, and every entry of group *k* lies in slice *k*.  Discovery order plays no part: the
    inventory is sorted by entry first."""

    name: ClassVar[str] = "by-function-count"

    def slices(self, inventory: Sequence[Mapping[str, Any]], per_slice: int) -> list[SliceSpec]:
        if per_slice <= 0:
            raise Refused(f"slice-per-slice-not-positive:{per_slice}")
        rows = sorted(({"entry": parse_addr(r["entry"]), "size": max(1, int(r.get("size") or 1))} for r in inventory), key=lambda r: r["entry"])
        if not rows:
            return []
        groups = [rows[i:i + per_slice] for i in range(0, len(rows), per_slice)]
        out: list[SliceSpec] = []
        for k, group in enumerate(groups):
            lo = group[0]["entry"]
            end = groups[k + 1][0]["entry"] if k + 1 < len(groups) else max(r["entry"] + r["size"] for r in group)
            out.append(SliceSpec(index=k, ranges=((lo, end),)))
        return out


@dataclasses.dataclass(frozen=True)
class BySectionSlicePlanner:
    """Slot: one slice per executable section of the image (needs a JVM-free section parser)."""

    name: ClassVar[str] = "by-section"

    def slices(self, inventory: Sequence[Mapping[str, Any]], per_slice: int) -> list[SliceSpec]:
        raise not_present("BySectionSlicePlanner (slices from the image's executable sections)")


@dataclasses.dataclass(frozen=True)
class ByCallgraphCommunitySlicePlanner:
    """Slot: slices from call-graph communities over ``references.json`` (locality over count)."""

    name: ClassVar[str] = "by-callgraph-community"

    def slices(self, inventory: Sequence[Mapping[str, Any]], per_slice: int) -> list[SliceSpec]:
        raise not_present("ByCallgraphCommunitySlicePlanner (slices from call-graph communities)")


SLICE_PLANNERS: dict[str, Any] = {
    p.name: p for p in (ByFunctionCountSlicePlanner, BySectionSlicePlanner, ByCallgraphCommunitySlicePlanner)
}


def slice_planner(name: str | None = None) -> SlicePlanner:
    chosen = name or ByFunctionCountSlicePlanner.name
    if chosen not in SLICE_PLANNERS:
        raise Refused(f"slice-planner-unknown:{chosen}:known {sorted(SLICE_PLANNERS)}")
    return SLICE_PLANNERS[chosen]()


# --------------------------------------------------------------------------- inventory and the pin
def canonical_inventory(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """``[{entry: "0x..", size: int, name: str|null}]`` sorted by entry, one row per entry."""
    by_entry: dict[int, dict[str, Any]] = {}
    for row in rows:
        entry = parse_addr(row["entry"])
        name = row.get("name")
        by_entry[entry] = {"entry": hex_addr(entry), "size": int(row.get("size") or 0), "name": str(name) if name else None}
    return [by_entry[e] for e in sorted(by_entry)]


def inventory_hash(rows: Iterable[Mapping[str, Any]]) -> str:
    return digest(canonical_json(canonical_inventory(rows)))


def restrict_inventory(rows: Iterable[Mapping[str, Any]], spec: SliceSpec) -> list[dict[str, Any]]:
    return [r for r in canonical_inventory(rows) if spec.contains(parse_addr(r["entry"]))]


def canonical_references(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """``[{from, to, kind}]`` sorted by ``(from, to, kind)``, duplicates dropped."""
    seen: set[tuple[int, int, str]] = set()
    for row in rows:
        kind = str(row.get("kind") or "other")
        if kind not in REFERENCE_KINDS:
            kind = "other"
        seen.add((parse_addr(row["from"]), parse_addr(row["to"]), kind))
    return [{"from": hex_addr(f), "to": hex_addr(t), "kind": k} for f, t, k in sorted(seen)]


def pin_two_key(sliced: str, monolithic: str) -> dict[str, Any]:
    """The two-key pin: both hashes recorded, ``pinned`` = the lexicographically minimal one on
    divergence (deterministic across nodes), ``diverged`` says whether they differed."""
    sliced, monolithic = str(sliced), str(monolithic)
    if not sliced or not monolithic:
        raise Refused("pin-needs-both-keys")
    return {"sliced": sliced, "monolithic": monolithic, "pinned": min(sliced, monolithic), "diverged": sliced != monolithic}


# --------------------------------------------------------------------------- importers
class ProgramImporter(Protocol):
    """Bring a program into a private temp project inside the analyzer's JVM.  ``open`` returns
    ``(project, program)``; the caller releases via ``project.close(program)`` then ``project.close()``."""

    name: ClassVar[str]

    def open(self, source: Path, project_dir: Path, program_name: str) -> tuple[Any, Any]: ...


@dataclasses.dataclass(frozen=True)
class HeadlessImporter:
    """Working: a throwaway project under *project_dir* and the analyzer's default loader over
    the image bytes.  Nothing outside *project_dir* is written."""

    name: ClassVar[str] = "headless-import"

    def open(self, source: Path, project_dir: Path, program_name: str) -> tuple[Any, Any]:
        from ghidra.base.project import GhidraProject  # type: ignore[import-not-found]
        from java.io import File  # type: ignore[import-not-found]

        project_dir.mkdir(parents=True, exist_ok=True)
        project = GhidraProject.createProject(str(project_dir), program_name, False)
        program = project.importProgram(File(str(source)))
        if program is None:
            project.close()
            raise Refused("import-no-loader")
        return project, program


@dataclasses.dataclass(frozen=True)
class PackedProgramImporter:
    """Working: open a packed program (a checkpoint) in a private temp project."""

    name: ClassVar[str] = "packed-program"

    def open(self, source: Path, project_dir: Path, program_name: str) -> tuple[Any, Any]:
        from ghidra.base.project import GhidraProject  # type: ignore[import-not-found]
        from java.io import File  # type: ignore[import-not-found]

        from ..corpus import ghidra_env

        project_dir.mkdir(parents=True, exist_ok=True)
        project = GhidraProject.createProject(str(project_dir), program_name, False)
        project.getRootFolder().createFile(program_name, File(str(source)), ghidra_env.monitor())
        program = project.openProgram("/", program_name, False)
        return project, program


@dataclasses.dataclass(frozen=True)
class ProjectSnapshotImporter:
    """Slot: a program already inside a project snapshot object (no re-import)."""

    name: ClassVar[str] = "project-snapshot"

    def open(self, source: Path, project_dir: Path, program_name: str) -> tuple[Any, Any]:
        raise not_present("ProjectSnapshotImporter (a program inside a project snapshot)")


@dataclasses.dataclass(frozen=True)
class ServerCheckoutImporter:
    """Slot: a checkout from a shared repository (live server state is never a basis)."""

    name: ClassVar[str] = "server-checkout"

    def open(self, source: Path, project_dir: Path, program_name: str) -> tuple[Any, Any]:
        raise not_present("ServerCheckoutImporter (a checkout from a shared repository)")


IMPORTERS: dict[str, Any] = {
    i.name: i for i in (HeadlessImporter, PackedProgramImporter, ProjectSnapshotImporter, ServerCheckoutImporter)
}


# --------------------------------------------------------------------------- the in-JVM job
def analyzer_version() -> str | None:
    from ..corpus.extract import live_analyzer_version

    return live_analyzer_version()


def check_options(options_hash: str) -> None:
    """Only the pinned default option set is known here; anything else is refused by name so a
    task under another option set never runs with defaults and calls it the same thing."""
    if str(options_hash) != PINNED_DEFAULT_OPTIONS:
        raise Refused(f"analyzer-options-unknown:{str(options_hash)[:48]}")


def _address_set(program, spec: SliceSpec):
    from ghidra.program.model.address import AddressSet  # type: ignore[import-not-found]

    space = program.getAddressFactory().getDefaultAddressSpace()
    out = AddressSet()
    for lo, hi in spec.ranges:
        out.addRange(space.getAddress(lo), space.getAddress(hi - 1))
    return out


def _analyze(program, spec: SliceSpec | None) -> None:
    from ghidra.program.flatapi import FlatProgramAPI  # type: ignore[import-not-found]

    try:
        from ghidra.app.script import GhidraScriptUtil  # type: ignore[import-not-found]

        GhidraScriptUtil.acquireBundleHostReference()
    except Exception:  # noqa: BLE001 -- older bundle host; analyzers that need it are skipped
        pass
    flat = FlatProgramAPI(program)
    tx = program.startTransaction("grid analysis")
    ok = False
    try:
        if spec is None:
            flat.analyzeAll(program)
        else:
            flat.analyze(program, _address_set(program, spec))
        ok = True
    finally:
        program.endTransaction(tx, ok)


def _function_rows(program) -> list[dict[str, Any]]:
    from ghidra.program.model.symbol import SourceType  # type: ignore[import-not-found]

    rows: list[dict[str, Any]] = []
    for fn in program.getFunctionManager().getFunctions(True):
        if fn.isExternal():
            continue
        symbol = fn.getSymbol()
        generated = symbol is None or symbol.getSource() == SourceType.DEFAULT
        rows.append({
            "entry": int(fn.getEntryPoint().getOffset()), "size": int(fn.getBody().getNumAddresses()),
            "name": None if generated else str(fn.getName()),
        })
    return canonical_inventory(rows)


def _reference_rows(program, spec: SliceSpec | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    minimum = program.getMinAddress()
    if minimum is None:
        return rows
    for ref in program.getReferenceManager().getReferenceIterator(minimum):
        if not ref.isMemoryReference():
            continue
        source = int(ref.getFromAddress().getOffset())
        if spec is not None and not spec.contains(source):
            continue
        rtype = ref.getReferenceType()
        kind = "call" if rtype.isCall() else "jump" if rtype.isJump() else "data" if rtype.isData() else "other"
        rows.append({"from": source, "to": int(ref.getToAddress().getOffset()), "kind": kind})
    return canonical_references(rows)


def _write_json(path: Path, value: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(canonical_json(value))
    os.replace(tmp, path)


def execute_slice_job(job: Mapping[str, Any]) -> dict[str, Any]:
    """Import, analyse (the slice or the whole image), export the checkpoint and the facts.

    Runs inside a process that booted the analyzer through ``corpus.ghidra_env.start``; returns
    the ``facts`` payload it also wrote to ``out_dir/facts.json``.  Refusals are returned as
    ``{"refused": <reason>}`` (and written to ``refusal.json``) so the driver's exit code and the
    kind's ``run`` can name them without parsing stderr.
    """
    from ..corpus import ghidra_env

    if job.get("schema") != SLICE_JOB_SCHEMA:
        return {"refused": "slice-job-schema"}
    out_dir = Path(str(job["out_dir"]))
    out_dir.mkdir(parents=True, exist_ok=True)
    mode = str(job.get("mode") or MODE_SLICED)
    try:
        if mode not in MODES:
            raise Refused(f"analysis-mode-unknown:{mode}")
        check_options(str(job.get("options_hash") or ""))
        if not ghidra_env.start():
            raise Refused("analyzer-not-present")
        version = analyzer_version() or ""
        expected = str(job.get("analyzer_version") or "")
        if expected and expected != version:
            raise Refused(f"analyzer-version-mismatch:{version}!={expected}")
        spec = SliceSpec.from_json(job["slice"]) if mode == MODE_SLICED else None
        all_slices = [SliceSpec.from_json(s) for s in (job.get("slices") or ())] if mode == MODE_MONOLITHIC else []
        importer = IMPORTERS.get(str(job.get("importer") or HeadlessImporter.name))
        if importer is None:
            raise Refused(f"importer-unknown:{job.get('importer')}")
        started = time.monotonic()
        project, program = importer().open(Path(str(job["image"])), out_dir / "project", "image")
        try:
            _analyze(program, spec)
            rows = _function_rows(program)
            if spec is not None:
                rows = restrict_inventory(rows, spec)
            refs = _reference_rows(program, spec)
            from java.io import File  # type: ignore[import-not-found]

            checkpoint = out_dir / CHECKPOINT_FILE
            project.saveAsPackedFile(program, File(str(checkpoint)), True)
        finally:
            try:
                project.close(program)
            finally:
                project.close()
        _write_json(out_dir / INVENTORY_FILE, rows)
        _write_json(out_dir / REFERENCES_FILE, refs)
        facts: dict[str, Any] = {
            "schema": SLICE_JOB_SCHEMA, "mode": mode, "analyzer_version": version,
            "options_hash": PINNED_DEFAULT_OPTIONS, "inventory_hash": inventory_hash(rows),
            "function_count": len(rows), "reference_count": len(refs),
            "slice": spec.to_json() if spec is not None else None,
            "per_slice": {str(s.index): {"key": s.key, "inventory_hash": inventory_hash(restrict_inventory(rows, s)), "function_count": len(restrict_inventory(rows, s))} for s in all_slices},
            "analysis_wall_s": round(time.monotonic() - started, 3),
        }
        _write_json(out_dir / FACTS_FILE, facts)
        return facts
    except Refused as exc:
        _write_json(out_dir / REFUSAL_FILE, {"refused": exc.reason, "candidates": list(exc.candidates)})
        return {"refused": exc.reason}
    except NotConfigured as exc:
        _write_json(out_dir / REFUSAL_FILE, {"refused": f"not-configured:{exc}"})
        return {"refused": f"not-configured:{exc}"}


def driver_argv(job_path: Path) -> list[str]:
    return [sys.executable, "-m", "agentdecompile_recovery.grid_lanes.analyzer_import", str(job_path)]


def main(argv: Sequence[str] | None = None) -> int:
    """``python -m agentdecompile_recovery.grid_lanes.analyzer_import <job.json>``; exit 0 with
    facts, 2 on a refusal (named in ``refusal.json``).  Always ends through ``exit_after_jvm``."""
    from ..corpus import ghidra_env

    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        sys.stderr.write("usage: analyzer_import <job.json>\n")
        return 64
    job = json.loads(Path(args[0]).read_text("utf-8"))
    rc = 0
    try:
        facts = execute_slice_job(job)
        rc = 2 if "refused" in facts else 0
    finally:
        ghidra_env.exit_after_jvm(rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "ByCallgraphCommunitySlicePlanner", "ByFunctionCountSlicePlanner", "BySectionSlicePlanner", "CHECKPOINT_FILE", "FACTS_FILE",
    "HeadlessImporter", "IMPORTERS", "INVENTORY_FILE", "MODES", "MODE_MONOLITHIC", "MODE_SLICED", "PINNED_DEFAULT_OPTIONS",
    "PackedProgramImporter", "ProgramImporter", "ProjectSnapshotImporter", "REFERENCES_FILE", "REFERENCE_KINDS", "REFUSAL_FILE",
    "SLICE_JOB_SCHEMA", "SLICE_PLANNERS", "ServerCheckoutImporter", "SlicePlanner", "SliceSpec", "canonical_inventory",
    "canonical_references", "check_options", "driver_argv", "execute_slice_job", "hex_addr", "inventory_hash", "main",
    "parse_addr", "pin_two_key", "restrict_inventory", "slice_planner",
]
