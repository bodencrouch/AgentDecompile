"""Delta objects (``agentdecompile.delta.v1``): the one shape through which a lane changes a store table.

A lane never writes an identity table.  It computes a **delta** -- a value: the target table,
the key columns, the rows (sorted by key) and where they came from -- puts it in the object
store and names its ref in a result output called ``delta`` (or ``delta.<label>``).  Once that
result is VERIFIED by an independent key, the view applier loads the delta, validates it, and
hands it to the registered ``DeltaBinder`` of the same name (``applier.DELTA_BINDERS``), which is
the only code that touches the table, inside the applier's transaction, under a
``ConflictPolicy``.  RESULT records bind nothing; a delta the applier has already bound (the
receipt table ``grid_applied_deltas``, keyed by content hash) is skipped by name.

Determinism rules a delta object obeys, checked by ``validate_delta``:

* canonical JSON, keys sorted (``core.canonical_json``); ``delta_ref`` is the content address
  of ``Delta.to_record()`` and equals the ref a lane gets from ``put_json(objects, record)``;
* ``rows`` are sorted by the tuple of ``key_columns`` and carry no duplicate key; every key
  value is a ``str`` or ``int`` (never a float, never ``None``);
* no row and no key column names a build by slug, repo path or product: the name-bearing
  columns (``NAME_BEARING_COLUMNS``) are refused by name.  Builds are named by
  ``content_sha256``; a build without one goes by its hashed slug (``slug:<sha256(slug)[:12]>``);
* store rowids never enter a delta (``ROWID_COLUMNS``): the binder resolves hashes to ids
  inside the store at bind time.

``provenance`` names the task that produced the delta (``task_id``, ``kind``, ``basis_hash``,
``producer_key``) so two deltas of one row set from two tasks are two objects with two refs, and
the receipt says which verified task bound which rows.

Nothing here imports the recovery package or names a store table: the schema is generic; the
table-aware binders live with the lanes.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from ..core import ObjectRef, ObjectStore, canonical_json

DELTA_SCHEMA = "agentdecompile.delta.v1"

#: Result output names whose object is a delta the applier binds: ``delta`` or ``delta.<label>``.
DELTA_OUTPUT = "delta"

#: Columns that name a build or a product in plain text.  Never in a delta (row or key).
NAME_BEARING_COLUMNS: frozenset[str] = frozenset({"slug", "repo_path", "game", "platform", "variant", "raw_image"})

#: Store-local row identifiers.  A delta names rows by hash; the binder resolves these inside the store.
ROWID_COLUMNS: frozenset[str] = frozenset({"id", "rowid", "binary_id", "logical_id", "src_binary", "dst_binary", "from_binary_id"})

PROVENANCE_FIELDS: tuple[str, ...] = ("task_id", "kind", "basis_hash", "producer_key")


def is_delta_output(name: str) -> bool:
    """Whether a result output name carries a delta ref (``delta`` or ``delta.<label>``)."""
    return name == DELTA_OUTPUT or name.startswith(DELTA_OUTPUT + ".")


def row_key(row: Mapping[str, Any], key_columns: Sequence[str]) -> tuple[Any, ...]:
    return tuple(row.get(col) for col in key_columns)


def _sort_key(row: Mapping[str, Any], key_columns: Sequence[str]) -> tuple[tuple[int, str], ...]:
    """A total order over key values of mixed ``int``/``str``: ints first, then strings."""
    out = []
    for value in row_key(row, key_columns):
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            out.append((2, repr(value)))
        elif isinstance(value, int):
            out.append((0, f"{value:020d}" if value >= 0 else f"-{-value:019d}"))
        else:
            out.append((1, value))
    return tuple(out)


def sort_rows(rows: Iterable[Mapping[str, Any]], key_columns: Sequence[str]) -> tuple[dict[str, Any], ...]:
    """The rows in delta order (by ``key_columns``), each with its own keys sorted."""
    return tuple(dict(sorted(dict(r).items())) for r in sorted(rows, key=lambda r: _sort_key(r, key_columns)))


@dataclass(frozen=True)
class Delta:
    """One verified change set for one store table.  Frozen; ``to_record()`` is what is hashed."""

    binder: str
    target_table: str
    key_columns: tuple[str, ...]
    rows: tuple[Mapping[str, Any], ...]
    provenance: Mapping[str, Any] = field(default_factory=dict)
    schema: str = DELTA_SCHEMA

    @classmethod
    def build(
        cls, *, binder: str, target_table: str, key_columns: Sequence[str], rows: Iterable[Mapping[str, Any]],
        task_id: str, kind: str, basis_hash: str, producer_key: str = "",
    ) -> "Delta":
        """A delta with its rows sorted and its provenance in the fixed field order."""
        keys = tuple(str(c) for c in key_columns)
        return cls(
            binder=str(binder), target_table=str(target_table), key_columns=keys, rows=sort_rows(rows, keys),
            provenance={"task_id": str(task_id), "kind": str(kind), "basis_hash": str(basis_hash), "producer_key": str(producer_key)},
        )

    def to_record(self) -> dict[str, Any]:
        return {
            "schema": self.schema, "binder": self.binder, "target_table": self.target_table,
            "key_columns": list(self.key_columns), "rows": [dict(r) for r in self.rows],
            "provenance": {k: self.provenance.get(k, "") for k in PROVENANCE_FIELDS},
        }

    @classmethod
    def from_record(cls, rec: Mapping[str, Any]) -> "Delta":
        rows = rec.get("rows")
        return cls(
            schema=str(rec.get("schema", "")), binder=str(rec.get("binder", "")), target_table=str(rec.get("target_table", "")),
            key_columns=tuple(str(c) for c in (rec.get("key_columns") or ())),
            rows=tuple(dict(r) for r in rows) if isinstance(rows, list) else (),
            provenance=dict(rec.get("provenance") or {}),
        )

    def to_bytes(self) -> bytes:
        return canonical_json(self.to_record())

    @property
    def task_id(self) -> str:
        return str(self.provenance.get("task_id", ""))

    def keys(self) -> list[tuple[Any, ...]]:
        return [row_key(r, self.key_columns) for r in self.rows]


def delta_ref(delta: Delta) -> ObjectRef:
    """The content address of the delta's canonical bytes (what ``put_delta`` stores)."""
    return ObjectRef.of_bytes(delta.to_bytes())


def put_delta(objects: ObjectStore, delta: Delta) -> ObjectRef:
    return objects.put(delta.to_bytes())


def load_delta(objects: ObjectStore, ref: ObjectRef | str) -> Delta:
    """The delta at *ref*; ``ValueError`` names the ref when the object is not a delta record."""
    ref = ObjectRef(ref)
    try:
        rec = json.loads(objects.get(ref).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"delta-not-json:{ref.hex[:12]}") from exc
    if not isinstance(rec, Mapping):
        raise ValueError(f"delta-not-a-mapping:{ref.hex[:12]}")
    return Delta.from_record(rec)


def validate_delta(delta: Delta, *, binders: Iterable[str] | None = None) -> list[str]:
    """Refusals by name; an empty list means the delta may be bound.

    *binders* is the registry's name list; when given, a binder the registry does not know is
    ``delta-binder-unknown:<name>``.  Rows are checked for order, duplicate keys, key types and
    name-bearing / rowid columns; row *values* are not interpreted here (the binder states which
    columns it writes and refuses the rest).
    """
    refusals: list[str] = []
    if delta.schema != DELTA_SCHEMA:
        refusals.append(f"delta-schema:{delta.schema[:40] or '<empty>'}")
    if not delta.binder:
        refusals.append("delta-binder-missing")
    elif binders is not None and delta.binder not in set(binders):
        refusals.append(f"delta-binder-unknown:{delta.binder}")
    if not delta.target_table:
        refusals.append("delta-target-table-missing")
    if not delta.key_columns:
        refusals.append("delta-key-columns-missing")
    for col in delta.key_columns:
        if col in NAME_BEARING_COLUMNS:
            refusals.append(f"delta-key-name-bearing:{col}")
        if col in ROWID_COLUMNS:
            refusals.append(f"delta-key-rowid:{col}")
    for name in PROVENANCE_FIELDS[:3]:   # producer_key may be empty until the worker stamps it
        if not str(delta.provenance.get(name, "")):
            refusals.append(f"delta-provenance-missing:{name}")
    bad_columns: set[str] = set()
    seen: set[tuple[Any, ...]] = set()
    previous: tuple[tuple[int, str], ...] | None = None
    ordered = True
    for index, row in enumerate(delta.rows):
        if not isinstance(row, Mapping):
            refusals.append(f"delta-row-not-a-mapping:{index}")
            continue
        for col in row:
            if col in NAME_BEARING_COLUMNS or col in ROWID_COLUMNS:
                bad_columns.add(col)
        for col in delta.key_columns:
            value = row.get(col)
            if col not in row or value is None:
                refusals.append(f"delta-row-missing-key:{index}:{col}")
            elif isinstance(value, bool) or not isinstance(value, (int, str)):
                refusals.append(f"delta-row-key-type:{index}:{col}:{type(value).__name__}")
        key = row_key(row, delta.key_columns)
        if key in seen:
            refusals.append(f"delta-rows-duplicate-key:{index}")
        seen.add(key)
        current = _sort_key(row, delta.key_columns)
        if previous is not None and current < previous:
            ordered = False
        previous = current
    if not ordered:
        refusals.append("delta-rows-unsorted")
    for col in sorted(bad_columns):
        refusals.append(f"delta-name-bearing-column:{col}" if col in NAME_BEARING_COLUMNS else f"delta-rowid-column:{col}")
    return refusals


def describe_schema() -> dict[str, Any]:
    return {
        "schema": DELTA_SCHEMA,
        "fields": {
            "binder": "name of the DELTA_BINDERS entry that binds the rows",
            "target_table": "the store table the binder writes",
            "key_columns": "columns that identify a row (hashes, addresses; never rowids or names)",
            "rows": "sorted by key_columns; each row's keys sorted",
            "provenance": list(PROVENANCE_FIELDS),
        },
        "output_name": f"{DELTA_OUTPUT} or {DELTA_OUTPUT}.<label>",
        "refused_columns": {"name_bearing": sorted(NAME_BEARING_COLUMNS), "rowid": sorted(ROWID_COLUMNS)},
    }


__all__ = [
    "DELTA_OUTPUT", "DELTA_SCHEMA", "Delta", "NAME_BEARING_COLUMNS", "PROVENANCE_FIELDS", "ROWID_COLUMNS",
    "delta_ref", "describe_schema", "is_delta_output", "load_delta", "put_delta", "row_key", "sort_rows", "validate_delta",
]
