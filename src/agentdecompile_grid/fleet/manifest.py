"""The fleet manifest as objects: node ids, roles, lanes, key ids, canary results.

Every save is a new immutable object whose record carries ``prev`` (the previous manifest's ref),
and the named pointer ``fleet/manifest`` moves to the newest, so the manifest is a chain any
node can walk (``history``) and ``fleet status`` is a read of one pointer plus one object.
Nothing here trusts a node because it is in the manifest; membership is bookkeeping.

Acceptance tests named for the final verification phase (U129):
  * ``test_manifest_roundtrip``: save → load yields equal entries; a second save links ``prev``
    to the first ref and ``history`` walks both.
  * ``test_fleet_status_reads_pointer``: ``fleet_status`` returns one row per node with role,
    lanes, state and proven capabilities from the canary report.
  * ``test_down_recorded``: ``mark`` to ``down`` keeps the node with its last state and the time.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import Any, Iterator, Mapping, Sequence

from ..core import GRID_SCHEMA_VERSION, ObjectRef, ObjectStore, canonical_json

MANIFEST_POINTER = "fleet/manifest"
NODE_STATES = ("pending", "up", "down", "failed")


@dataclass(frozen=True)
class NodeEntry:
    node_id: str
    provider: str
    role: str
    lanes: tuple[str, ...] = ()
    key_id: str = ""
    capabilities: tuple[str, ...] = ()
    canaries: Mapping[str, Any] = field(default_factory=dict)
    state: str = "pending"
    labels: Mapping[str, str] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_record(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id, "provider": self.provider, "role": self.role, "lanes": list(self.lanes), "key_id": self.key_id, "capabilities": list(self.capabilities),
            "canaries": dict(self.canaries), "state": self.state, "labels": dict(self.labels), "created_at": self.created_at, "updated_at": self.updated_at,
        }

    @classmethod
    def from_record(cls, rec: Mapping[str, Any]) -> "NodeEntry":
        return cls(
            node_id=str(rec["node_id"]), provider=str(rec.get("provider", "")), role=str(rec.get("role", "fleet")), lanes=tuple(rec.get("lanes", ())), key_id=str(rec.get("key_id", "")),
            capabilities=tuple(rec.get("capabilities", ())), canaries=dict(rec.get("canaries", {})), state=str(rec.get("state", "pending")), labels=dict(rec.get("labels", {})),
            created_at=float(rec.get("created_at", 0.0)), updated_at=float(rec.get("updated_at", 0.0)),
        )


@dataclass
class FleetManifest:
    entries: dict[str, NodeEntry] = field(default_factory=dict)
    prev: ObjectRef | None = None
    saved_at: float = 0.0
    fabric_id: str = ""

    # -- mutation
    def upsert(self, entry: NodeEntry, *, now: float) -> NodeEntry:
        if entry.state not in NODE_STATES:
            raise ValueError(f"node state must be one of {NODE_STATES}")
        existing = self.entries.get(entry.node_id)
        stored = replace(entry, created_at=existing.created_at if existing and existing.created_at else (entry.created_at or now), updated_at=now)
        self.entries[entry.node_id] = stored
        return stored

    def mark(self, node_id: str, state: str, *, now: float, **changes: Any) -> NodeEntry:
        if node_id not in self.entries:
            raise KeyError(f"no node {node_id!r} in the manifest")
        if state not in NODE_STATES:
            raise ValueError(f"node state must be one of {NODE_STATES}")
        updated = replace(self.entries[node_id], state=state, updated_at=now, **changes)
        self.entries[node_id] = updated
        return updated

    def record_canaries(self, node_id: str, key_id: str, report: Mapping[str, Any], capabilities: Sequence[str], *, now: float) -> NodeEntry:
        return self.mark(node_id, "up", now=now, key_id=key_id, canaries=dict(report), capabilities=tuple(sorted(capabilities)))

    def rename(self, placeholder: str, node_id: str, *, now: float) -> NodeEntry:
        """A manual-provider placeholder becomes the real node id (state ``up``)."""
        if placeholder not in self.entries:
            raise KeyError(f"no node {placeholder!r} in the manifest")
        entry = self.entries.pop(placeholder)
        renamed = replace(entry, node_id=node_id, state="up", updated_at=now, labels={**dict(entry.labels), "placeholder": placeholder})
        self.entries[node_id] = renamed
        return renamed

    # -- persistence
    def to_record(self) -> dict[str, Any]:
        return {"schema": GRID_SCHEMA_VERSION, "kind": "fleet-manifest", "fabric_id": self.fabric_id, "prev": str(self.prev) if self.prev else "", "saved_at": self.saved_at, "nodes": [e.to_record() for _, e in sorted(self.entries.items())]}

    @classmethod
    def from_record(cls, rec: Mapping[str, Any]) -> "FleetManifest":
        entries = {str(n["node_id"]): NodeEntry.from_record(n) for n in rec.get("nodes", ())}
        prev = ObjectRef(rec["prev"]) if rec.get("prev") else None
        return cls(entries, prev, float(rec.get("saved_at", 0.0)), str(rec.get("fabric_id", "")))

    def save(self, objects: ObjectStore, *, now: float, pointer: str = MANIFEST_POINTER) -> ObjectRef:
        current = objects.get_named(pointer)
        self.prev = ObjectRef(current.decode("utf-8").strip()) if current else self.prev
        self.saved_at = now
        ref = objects.put(canonical_json(self.to_record()))
        objects.put_named(pointer, str(ref).encode("utf-8"))
        return ref

    @classmethod
    def load(cls, objects: ObjectStore, *, pointer: str = MANIFEST_POINTER) -> "FleetManifest":
        current = objects.get_named(pointer)
        if not current:
            return cls()
        return cls.from_record(json.loads(objects.get(ObjectRef(current.decode("utf-8").strip())).decode("utf-8")))

    @classmethod
    def history(cls, objects: ObjectStore, *, pointer: str = MANIFEST_POINTER, limit: int = 64) -> Iterator[tuple[ObjectRef, "FleetManifest"]]:
        current = objects.get_named(pointer)
        ref = ObjectRef(current.decode("utf-8").strip()) if current else None
        seen = 0
        while ref is not None and seen < limit:
            manifest = cls.from_record(json.loads(objects.get(ref).decode("utf-8")))
            yield ref, manifest
            ref = manifest.prev
            seen += 1


def fleet_status(objects: ObjectStore, *, pointer: str = MANIFEST_POINTER) -> list[dict[str, Any]]:
    """``fleet status``: one row per node from the current manifest."""
    manifest = FleetManifest.load(objects, pointer=pointer)
    rows = []
    for node_id, entry in sorted(manifest.entries.items()):
        rows.append({
            "node_id": node_id, "provider": entry.provider, "role": entry.role, "lanes": list(entry.lanes), "state": entry.state, "key_id": entry.key_id,
            "capabilities": list(entry.capabilities), "canaries": {k: v.get("state") for k, v in entry.canaries.items()} if entry.canaries else {},
            "labels": dict(entry.labels), "updated_at": entry.updated_at,
        })
    return rows


__all__ = ["FleetManifest", "MANIFEST_POINTER", "NODE_STATES", "NodeEntry", "fleet_status"]
