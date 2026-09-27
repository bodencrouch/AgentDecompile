"""U138: JVM-free facts over an analysis slice's checkpoint -- the ``FactsReader`` Protocol.

An ``analysis-slice`` result is a packed program object (the checkpoint) plus two exported facts
objects, ``inventory.json`` and ``references.json`` (``analyzer_import``).  Consumers -- the
decompile-chunk planner, the knowledge view, a slice planner over an earlier inventory -- read
those facts here **without booting the JVM**: this module imports nothing from the analyzer and
nothing that does.

* ``ExportedFactsReader`` (working) -- the inventory and references as the run exported them
  (object refs through an ``ObjectStore``, or local files); sorted, canonical, hash-checkable.
* ``PackedProgramFactsReader`` (working for what the packed format exposes) -- the **function
  inventory** read straight out of the packed program's database through the pure-Python
  ``ghidra_db`` reader (entries and stored names; the packed database carries no body sizes the
  reader decodes, so ``size`` is 0 there); references are *not* decoded from the packed format --
  ``ghidra_db`` has no reference-table accessor -- so ``references()`` on this reader answers from
  the exported ``references.json`` when one is given and refuses by name otherwise.
  ``cross_check`` compares the packed program's entry set with the exported inventory's, the
  JVM-free check that the checkpoint and the facts belong together.
* ``FullDatabaseFactsReader`` -- slot: types, comments, references decoded from the database.

Every reader yields the same rows: ``FunctionFact(entry, size, name)`` sorted by entry and
``ReferenceFact(source, target, kind)`` sorted by ``(source, target, kind)``; ``inventory_hash()``
is ``analyzer_import.inventory_hash`` over the rows, the value the two-key pin compares.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any, ClassVar, Iterable, Mapping, Protocol, Sequence

from agentdecompile_grid.core import ObjectRef, ObjectStore, Refused

from ._common import get_json, not_present
from .analyzer_import import canonical_inventory, canonical_references, hex_addr, inventory_hash, parse_addr


@dataclasses.dataclass(frozen=True, order=True)
class FunctionFact:
    entry: int
    size: int = 0
    name: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {"entry": hex_addr(self.entry), "size": int(self.size), "name": self.name}


@dataclasses.dataclass(frozen=True, order=True)
class ReferenceFact:
    source: int
    target: int
    kind: str = "other"

    def to_json(self) -> dict[str, Any]:
        return {"from": hex_addr(self.source), "to": hex_addr(self.target), "kind": self.kind}


def function_facts(rows: Iterable[Mapping[str, Any]]) -> list[FunctionFact]:
    return [FunctionFact(parse_addr(r["entry"]), int(r.get("size") or 0), r.get("name") or None) for r in canonical_inventory(rows)]


def reference_facts(rows: Iterable[Mapping[str, Any]]) -> list[ReferenceFact]:
    return [ReferenceFact(parse_addr(r["from"]), parse_addr(r["to"]), str(r["kind"])) for r in canonical_references(rows)]


class FactsReader(Protocol):
    """What a consumer may ask of a checkpoint's facts without a JVM."""

    name: ClassVar[str]

    def inventory(self) -> list[FunctionFact]: ...

    def references(self) -> list[ReferenceFact]: ...

    def inventory_hash(self) -> str: ...


def _load_rows(objects: ObjectStore | None, source: Any) -> list[dict[str, Any]]:
    """A JSON list from an object ref (``sha256:``), a path, or an in-memory sequence."""
    if isinstance(source, (list, tuple)):
        return [dict(r) for r in source]
    text = str(source)
    if text.startswith("sha256:"):
        if objects is None:
            raise Refused("facts-object-needs-store")
        ref = ObjectRef(text)
        if not objects.exists(ref):
            raise Refused(f"facts-object-missing:{ref.hex[:12]}")
        value = get_json(objects, ref)
    else:
        path = Path(text)
        if not path.is_file():
            raise Refused("facts-file-missing")
        value = json.loads(path.read_text("utf-8"))
    if not isinstance(value, list):
        raise Refused("facts-not-a-list")
    return [dict(r) for r in value]


@dataclasses.dataclass(frozen=True)
class ExportedFactsReader:
    """Working: the facts a slice run exported (``inventory.json`` / ``references.json``)."""

    name: ClassVar[str] = "exported"
    inventory_source: Any
    references_source: Any = None
    objects: ObjectStore | None = None

    def inventory(self) -> list[FunctionFact]:
        return function_facts(_load_rows(self.objects, self.inventory_source))

    def references(self) -> list[ReferenceFact]:
        if self.references_source is None:
            raise Refused("facts-references-not-given")
        return reference_facts(_load_rows(self.objects, self.references_source))

    def inventory_hash(self) -> str:
        return inventory_hash(r.to_json() for r in self.inventory())

    def call_edges(self) -> list[tuple[int, int]]:
        """``(caller, callee)`` pairs: call references whose target is a function entry."""
        entries = {f.entry for f in self.inventory()}
        return sorted({(r.source, r.target) for r in self.references() if r.kind == "call" and r.target in entries})


@dataclasses.dataclass(frozen=True)
class PackedProgramFactsReader:
    """Working for what the packed format exposes: entries and stored names straight from the
    packed program's database (``ghidra_db``, pure Python).  Sizes are 0 (not decoded); references
    come from the exported ``references.json`` when given."""

    name: ClassVar[str] = "packed-program"
    packed_path: Path
    references_source: Any = None
    objects: ObjectStore | None = None

    def inventory(self) -> list[FunctionFact]:
        from ..ghidra_db import GhidraProgram, open_packed_database

        rows: list[dict[str, Any]] = []
        with open_packed_database(self.packed_path) as buffer_file:
            program = GhidraProgram(buffer_file.path)
            try:
                for fn in program.functions():
                    if fn.entry is None:
                        continue
                    rows.append({"entry": fn.entry, "size": 0, "name": fn.name if fn.has_non_autogen_name else None})
            finally:
                program.close()
        return function_facts(rows)

    def references(self) -> list[ReferenceFact]:
        if self.references_source is None:
            raise not_present("PackedProgramFactsReader.references (reference tables are not decoded from the packed database; pass the exported references.json)")
        return reference_facts(_load_rows(self.objects, self.references_source))

    def inventory_hash(self) -> str:
        return inventory_hash(r.to_json() for r in self.inventory())

    def cross_check(self, exported: Sequence[FunctionFact]) -> dict[str, Any]:
        """Entry sets of the packed program and the exported inventory: equal, or the difference
        named (``{equal, only_packed, only_exported}``)."""
        packed = {f.entry for f in self.inventory()}
        given = {f.entry for f in exported}
        return {
            "equal": packed == given,
            "only_packed": [hex_addr(e) for e in sorted(packed - given)],
            "only_exported": [hex_addr(e) for e in sorted(given - packed)],
        }


@dataclasses.dataclass(frozen=True)
class FullDatabaseFactsReader:
    """Slot: types, comments and references decoded from the packed database itself."""

    name: ClassVar[str] = "full-database"
    packed_path: Path

    def inventory(self) -> list[FunctionFact]:
        raise not_present("FullDatabaseFactsReader (full database decode)")

    def references(self) -> list[ReferenceFact]:
        raise not_present("FullDatabaseFactsReader (full database decode)")

    def inventory_hash(self) -> str:
        raise not_present("FullDatabaseFactsReader (full database decode)")


FACTS_READERS: dict[str, Any] = {r.name: r for r in (ExportedFactsReader, PackedProgramFactsReader, FullDatabaseFactsReader)}


def describe_readers() -> dict[str, Any]:
    return {
        "protocol": "FactsReader: inventory() -> [FunctionFact], references() -> [ReferenceFact], inventory_hash() -> sha256",
        "working": [ExportedFactsReader.name, PackedProgramFactsReader.name + " (inventory: entries + stored names; references from exported json)"],
        "slots": [FullDatabaseFactsReader.name],
        "jvm": "never booted by any reader",
    }


__all__ = [
    "ExportedFactsReader", "FACTS_READERS", "FactsReader", "FullDatabaseFactsReader", "FunctionFact", "PackedProgramFactsReader",
    "ReferenceFact", "describe_readers", "function_facts", "reference_facts",
]
