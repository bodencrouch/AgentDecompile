"""agentdecompile_grid.objects.gc — size-capped eviction of *unpinned* local objects.

Mark, then sweep in policy order:

1. **Mark.**  Every ``PinSource`` yields roots.  ``NamedPointerPins`` walks the store's named
   pointers: a pointer holding a bare ref pins that object; a pointer holding a grid document
   (``refs`` / ``outputs`` / ``ref`` keys, see ``base.refs_in_document``) pins what it names; at
   walk depth 2 the referents themselves are read as grid documents (a result record's
   ``outputs`` are pinned by the pointer to the record).  ``InFlightPins`` yields the refs
   workers registered through ``PinRegistry.pin``.  Nothing else is content-sniffed, so the
   pinned set is a deterministic function of the pointers and pin files.
2. **Sweep.**  Unpinned objects older than ``grace_s`` are evicted in the order the
   ``EvictionPolicy`` gives (``lru`` by access time — meaningful only with ``touch_on_read``;
   ``fifo`` by write time; ``largest-first``) until usage is at or under
   ``cap * low_water`` (or ``target_bytes``).  Stale temp files are swept too.

Safety: the sweep runs under the store's exclusive GC lock (``AlreadyOwned`` if another GC
holds it — never blocks, never silently skips).  The worker-side handshake is *pin, then
verify*: ``PinRegistry.pin`` writes the pin file first and returns the refs that are missing,
so a ref evicted between the worker's existence check and its pin is re-fetched, never used
half-present.  If pinned bytes alone exceed the cap, the report says so and ``put`` raises
``StoreFull`` by name.

Acceptance tests (named here, landed in the verification phase):

* ``test_gc_never_evicts_named_referents_or_their_outputs`` — a result record pointed at by
  ``results/<id>/<key>`` and every ref in its ``outputs`` survive a sweep at cap 0.
* ``test_gc_respects_inflight_pins_and_grace`` — pinned refs and refs younger than grace survive;
  an unpinned old ref is evicted first under fifo.
* ``test_gc_lock_contention_is_already_owned`` — a second collector raises ``AlreadyOwned``.
* ``test_store_full_named_error_at_cap`` — with pinned bytes above the cap ``put`` raises ``StoreFull``.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator, Protocol, Sequence, runtime_checkable

from ..core import ObjectRef, ObjectStore, Registry
from .base import EnumerableStore, NamedIndexStore, ObjectMissing, ObjectStat, PinRegistry, refs_in_document

GC_POLICIES = Registry("gc eviction policy")
PIN_SOURCES = Registry("gc pin source")


# --------------------------------------------------------------------------- eviction policies
@runtime_checkable
class EvictionPolicy(Protocol):
    """Orders eviction candidates; the first returned is evicted first."""

    name: str

    def order(self, candidates: Sequence[ObjectStat]) -> Sequence[ObjectStat]: ...


class LRUPolicy:
    """Least recently *accessed* first (access time is only maintained with ``touch_on_read``)."""

    name = "lru"

    def order(self, candidates: Sequence[ObjectStat]) -> Sequence[ObjectStat]:
        return sorted(candidates, key=lambda s: (s.atime, s.mtime, s.ref))


class FIFOPolicy:
    """Oldest *written* first."""

    name = "fifo"

    def order(self, candidates: Sequence[ObjectStat]) -> Sequence[ObjectStat]:
        return sorted(candidates, key=lambda s: (s.mtime, s.ref))


class LargestFirstPolicy:
    """Largest first; frees the cap with the fewest evictions."""

    name = "largest-first"

    def order(self, candidates: Sequence[ObjectStat]) -> Sequence[ObjectStat]:
        return sorted(candidates, key=lambda s: (-s.size, s.mtime, s.ref))


for _policy in (LRUPolicy, FIFOPolicy, LargestFirstPolicy):
    GC_POLICIES.register(_policy.name, _policy)


def eviction_policy(name: str) -> EvictionPolicy:
    return GC_POLICIES.get(name)()


# --------------------------------------------------------------------------- pin sources
@runtime_checkable
class PinSource(Protocol):
    """Yields refs that must not be evicted."""

    name: str

    def iter_pinned_refs(self) -> Iterator[ObjectRef]: ...


class NamedPointerPins:
    """Everything a named pointer names, walked ``depth`` levels through grid documents."""

    name = "named-pointers"

    def __init__(self, store: ObjectStore, *, depth: int = 2, max_scan_bytes: int = 1_048_576, prefix: str = "") -> None:
        if not isinstance(store, NamedIndexStore):
            raise TypeError(f"{type(store).__name__} cannot enumerate named pointers (needs list_named)")
        self.store = store
        self.depth = depth
        self.max_scan_bytes = max_scan_bytes
        self.prefix = prefix

    def iter_pinned_refs(self) -> Iterator[ObjectRef]:
        if self.depth <= 0:
            return
        seen: set[ObjectRef] = set()
        frontier: list[ObjectRef] = []
        for name in self.store.list_named(self.prefix):  # type: ignore[attr-defined]
            data = self.store.get_named(name)
            if data is None:
                continue
            for ref in refs_in_document(data, max_bytes=self.max_scan_bytes):
                if ref not in seen:
                    seen.add(ref)
                    frontier.append(ref)
        level = 1
        while frontier and level < self.depth:
            next_frontier: list[ObjectRef] = []
            for ref in frontier:
                try:
                    data = self.store.get(ref)
                except (ObjectMissing, KeyError, OSError):
                    continue
                for child in refs_in_document(data, max_bytes=self.max_scan_bytes):
                    if child not in seen:
                        seen.add(child)
                        next_frontier.append(child)
            frontier = next_frontier
            level += 1
        yield from sorted(seen)


class InFlightPins:
    """Refs registered through the store's ``PinRegistry`` (tasks currently running)."""

    name = "in-flight"

    def __init__(self, store: ObjectStore) -> None:
        if not isinstance(store, PinRegistry):
            raise TypeError(f"{type(store).__name__} has no pin registry")
        self.store = store

    def iter_pinned_refs(self) -> Iterator[ObjectRef]:
        yield from sorted(set(self.store.pinned_refs()))  # type: ignore[attr-defined]


class StaticPins:
    """A fixed set (manifests, tests, an operator's keep-list)."""

    name = "static"

    def __init__(self, refs: Iterable[ObjectRef]) -> None:
        self.refs = tuple(sorted(set(ObjectRef(r) for r in refs)))

    def iter_pinned_refs(self) -> Iterator[ObjectRef]:
        yield from self.refs


class CompositePins:
    name = "composite"

    def __init__(self, sources: Iterable[PinSource]) -> None:
        self.sources = tuple(sources)

    def iter_pinned_refs(self) -> Iterator[ObjectRef]:
        seen: set[ObjectRef] = set()
        for src in self.sources:
            for ref in src.iter_pinned_refs():
                if ref not in seen:
                    seen.add(ref)
        yield from sorted(seen)


for _src in (NamedPointerPins, InFlightPins, StaticPins, CompositePins):
    PIN_SOURCES.register(_src.name, _src)


def default_pin_sources(store: ObjectStore, *, depth: int = 2, max_scan_bytes: int = 1_048_576) -> list[PinSource]:
    """Named-pointer referents plus in-flight pins, for stores that support each."""
    sources: list[PinSource] = []
    if isinstance(store, NamedIndexStore):
        sources.append(NamedPointerPins(store, depth=depth, max_scan_bytes=max_scan_bytes))
    if isinstance(store, PinRegistry):
        sources.append(InFlightPins(store))
    return sources


# --------------------------------------------------------------------------- collection
@dataclass(frozen=True)
class GcReport:
    """What a sweep did (or would do under ``dry_run``).  Deterministic: refs are sorted."""

    policy: str
    cap_bytes: int
    target_bytes: int
    usage_before: int
    usage_after: int
    count_before: int
    scanned: int
    pinned: int
    pinned_bytes: int
    skipped_young: int
    evicted: tuple[ObjectRef, ...]
    freed_bytes: int
    temp_swept: int
    dry_run: bool
    over_cap: bool                         # True when even after the sweep usage > target
    pinned_over_cap: bool                  # True when pinned bytes alone exceed the cap
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        rec = dict(self.__dict__)
        rec["evicted"] = list(self.evicted)
        rec["notes"] = list(self.notes)
        return rec


def collect(store: EnumerableStore, *, cap_bytes: int, low_water: float = 0.9, grace_s: int = 300,
            policy: str | EvictionPolicy = "fifo", pin_sources: Sequence[PinSource] = (),
            target_bytes: int | None = None, dry_run: bool = False, now: float | None = None,
            sweep_temp: bool = True) -> GcReport:
    """Evict unpinned objects until usage <= target.  Runs under the store's GC lock.

    ``cap_bytes == 0`` means unlimited: nothing is evicted (temp sweep still runs) unless an explicit
    ``target_bytes`` is given.
    """
    pol = eviction_policy(policy) if isinstance(policy, str) else policy
    now = time.time() if now is None else now
    notes: list[str] = []
    with store.gc_lock():
        stats = sorted(store.iter_stats(), key=lambda s: s.ref)
        usage_before = sum(s.size for s in stats)
        count_before = len(stats)
        if target_bytes is None:
            target = int(cap_bytes * low_water) if cap_bytes > 0 else usage_before
        else:
            target = max(0, int(target_bytes))
        pinned: set[ObjectRef] = set()
        for src in pin_sources:
            pinned.update(src.iter_pinned_refs())
        pinned_bytes = sum(s.size for s in stats if s.ref in pinned)
        temp_swept = 0
        if sweep_temp and hasattr(store, "sweep_temp"):
            temp_swept = int(store.sweep_temp(older_than_s=grace_s, now=now, dry_run=dry_run))  # type: ignore[attr-defined]
        candidates: list[ObjectStat] = []
        skipped_young = 0
        for s in stats:
            if s.ref in pinned:
                continue
            if now - s.mtime < grace_s:
                skipped_young += 1
                continue
            candidates.append(s)
        evicted: list[ObjectRef] = []
        freed = 0
        usage = usage_before
        if usage > target:
            for s in pol.order(candidates):
                if usage <= target:
                    break
                if not dry_run:
                    freed_now = store.evict(s.ref)
                else:
                    freed_now = s.size
                if freed_now:
                    evicted.append(s.ref)
                    freed += freed_now
                    usage -= freed_now
        over_cap = usage > target
        pinned_over_cap = cap_bytes > 0 and pinned_bytes > cap_bytes
        if pinned_over_cap:
            notes.append(f"pinned bytes {pinned_bytes} exceed cap {cap_bytes}: nothing evictable can bring the store under cap")
        if over_cap and skipped_young:
            notes.append(f"{skipped_young} object(s) younger than grace {grace_s}s were not considered")
    return GcReport(
        policy=pol.name, cap_bytes=int(cap_bytes), target_bytes=target, usage_before=usage_before, usage_after=usage,
        count_before=count_before, scanned=len(stats), pinned=len(pinned & {s.ref for s in stats}),
        pinned_bytes=pinned_bytes, skipped_young=skipped_young, evicted=tuple(sorted(evicted)), freed_bytes=freed,
        temp_swept=temp_swept, dry_run=dry_run, over_cap=over_cap, pinned_over_cap=pinned_over_cap, notes=tuple(notes),
    )


def describe_policies() -> dict[str, Any]:
    return {"policies": GC_POLICIES.names(), "pin_sources": PIN_SOURCES.names()}


__all__ = [
    "GC_POLICIES", "PIN_SOURCES", "EvictionPolicy", "LRUPolicy", "FIFOPolicy", "LargestFirstPolicy", "eviction_policy",
    "PinSource", "NamedPointerPins", "InFlightPins", "StaticPins", "CompositePins", "default_pin_sources",
    "GcReport", "collect", "describe_policies",
]
