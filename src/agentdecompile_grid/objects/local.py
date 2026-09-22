"""agentdecompile_grid.objects.local — ``LocalDirStore``: the fully working, on-disk object store.

Layout under ``root``::

    layout.json                    frozen {hash_algorithm, shard_width, shard_depth}
    objects/<ab>/<hex>             immutable, write-once (see base.atomic_write_once)
    named/<name>                   mutable pointers, atomically replaced, never torn
    pins/<owner>.json              in-flight pins registered by workers (PinRegistry)
    corrupt/<hex>                  quarantined objects whose bytes stopped hashing to their name
    gc.lock                        exclusive GC lock (AlreadyOwned when held)

Guarantees:

* ``put`` is idempotent and write-once; a caller-supplied ``expect`` ref that disagrees with the
  bytes is refused (``IntegrityError``) before anything touches the disk.
* ``get`` re-hashes when ``verify_on_read`` and quarantines a corrupt file so the next read
  misses (a layered store then refetches from an upper layer).
* Listing is deterministic: sorted, temp files and internals skipped.
* At ``size_cap_bytes`` a ``put`` that would overflow runs GC and raises ``StoreFull`` by name
  when the unpinned set cannot make room.
* Names are validated (no traversal); names may contain ``/`` and are enumerated recursively.

Acceptance tests (named here, landed in the verification phase):

* ``test_local_put_get_roundtrip_and_idempotent_put`` — second put of the same bytes returns the
  same ref, writes nothing new, listing has one entry.
* ``test_local_listing_sorted_and_prefix_filtered`` — ``list("ab")`` equals the sorted subset.
* ``test_local_layout_mismatch_is_named`` — reopening with another shard width raises ``LayoutMismatch``.
* ``test_local_corrupt_object_is_quarantined`` — a flipped byte makes ``get`` raise ``IntegrityError``
  and ``exists`` become False.
* ``test_local_named_pointer_roundtrip_and_enumeration`` — ``results/<id>/<key>`` pointers list under
  ``results/<id>/`` in sorted order.
* ``test_local_store_full_named_error`` — with a cap and pinned data ``put`` raises ``StoreFull``.
"""
from __future__ import annotations

import contextlib
import json
import os
import shutil
import time
from typing import Any, ContextManager, Iterable, Iterator, Mapping, Sequence

from ..core import AlreadyOwned, ObjectRef, canonical_json
from . import gc as gc_module
from .base import (
    CORRUPT_DIR, GC_LOCK_FILE, LAYOUT_FILE, NAMED_DIR, OBJECTS_DIR, PINS_DIR,
    BaseObjectStore, ExclusiveFileLock, FsyncPolicy, IntegrityError, InvalidName, Layout, ObjectMissing, ObjectStat,
    StoreFull, atomic_replace, atomic_write_once, is_temp_name, ref_prefix_hex, schema_from_dataclass, validate_name,
    validate_owner, validate_ref,
)

PIN_SCHEMA_VERSION = 1


class LocalDirStore(BaseObjectStore):
    """Content-addressed store in a local directory.  Working; the reference implementation."""

    name = "local"
    kind = "object-store"
    status = "working"

    def __init__(self, root: str | os.PathLike[str], *, shard_width: int = 2, shard_depth: int = 1,
                 fsync: FsyncPolicy | str = FsyncPolicy.DATA, write_once_strategy: str = "link",
                 verify_on_read: bool = True, touch_on_read: bool = False, quarantine_corrupt: bool = True,
                 size_cap_bytes: int = 0, gc_policy: str = "lru", gc_low_water: float = 0.9, gc_grace_s: int = 300,
                 gc_max_scan_bytes: int = 1_048_576, gc_walk_depth: int = 2, create: bool = True) -> None:
        self.root = os.path.abspath(os.fspath(root))
        self.fsync = FsyncPolicy(fsync)
        self.write_once_strategy = write_once_strategy
        self.verify_on_read = verify_on_read
        self.touch_on_read = touch_on_read
        self.quarantine_corrupt = quarantine_corrupt
        self.size_cap_bytes = int(size_cap_bytes)
        self.gc_policy = gc_policy
        self.gc_low_water = float(gc_low_water)
        self.gc_grace_s = int(gc_grace_s)
        self.gc_max_scan_bytes = int(gc_max_scan_bytes)
        self.gc_walk_depth = int(gc_walk_depth)
        self._usage: tuple[int, int] | None = None
        wanted = Layout(shard_width=shard_width, shard_depth=shard_depth)
        self.layout = self._open_layout(wanted, create=create)

    @classmethod
    def from_config(cls, cfg: Any, *, root: str | None = None, create: bool = True) -> "LocalDirStore":
        """Build from a ``GridConfig`` (``objects.*`` fields; root = objects.local.root or paths.objects)."""
        o = cfg.objects
        root = root or o.local.root or cfg.resolved_paths().objects
        return cls(root, shard_width=o.shard_width, shard_depth=o.shard_depth, fsync=o.fsync,
                   write_once_strategy=o.write_once_strategy, verify_on_read=o.verify_on_read,
                   touch_on_read=o.touch_on_read, size_cap_bytes=o.size_cap_bytes, gc_policy=o.gc_policy,
                   gc_low_water=o.gc_low_water, gc_grace_s=o.gc_grace_s, gc_max_scan_bytes=o.gc_max_scan_bytes,
                   gc_walk_depth=o.gc_walk_depth, create=create)

    # ---- layout ------------------------------------------------------------------------------
    def _open_layout(self, wanted: Layout, *, create: bool) -> Layout:
        marker = os.path.join(self.root, LAYOUT_FILE)
        if os.path.isfile(marker):
            with open(marker, "rb") as fh:
                existing = Layout.from_json(fh.read())
            existing.check(wanted, f"object store {self.root}")
            return existing
        if not create:
            raise ObjectMissing(f"object store {self.root} does not exist (no {LAYOUT_FILE}) and create=False")
        os.makedirs(os.path.join(self.root, OBJECTS_DIR), exist_ok=True)
        os.makedirs(os.path.join(self.root, NAMED_DIR), exist_ok=True)
        os.makedirs(os.path.join(self.root, PINS_DIR), exist_ok=True)
        atomic_write_once(marker, wanted.to_json(), fsync=self.fsync, strategy="replace", tag="layout")
        with open(marker, "rb") as fh:  # another creator may have raced us with a different layout
            existing = Layout.from_json(fh.read())
        existing.check(wanted, f"object store {self.root}")
        return existing

    def path_for(self, ref: ObjectRef) -> str:
        """Absolute path of an object (whether or not it exists)."""
        return os.path.join(self.root, *self.layout.relpath(ref).split("/"))

    def _named_path(self, name: str) -> str:
        return os.path.join(self.root, NAMED_DIR, *validate_name(name).split("/"))

    # ---- core protocol -----------------------------------------------------------------------
    def put(self, data: bytes, *, expect: ObjectRef | None = None) -> ObjectRef:
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError("put() takes bytes")
        data = bytes(data)
        ref = self.expected_ref(data, expect)
        path = self.path_for(ref)
        if os.path.exists(path):
            return ref
        if self.size_cap_bytes > 0:
            self._make_room(len(data))
        written = atomic_write_once(path, data, fsync=self.fsync, strategy=self.write_once_strategy, tag=ref.hex[:12])
        if written and self._usage is not None:
            self._usage = (self._usage[0] + len(data), self._usage[1] + 1)
        return ref

    def get(self, ref: ObjectRef) -> bytes:
        path = self.path_for(ref)
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except FileNotFoundError:
            raise ObjectMissing(f"{self.name}: no object {ref} under {self.root}") from None
        try:
            self.check_integrity(ref, data)
        except IntegrityError:
            if self.quarantine_corrupt:
                self._quarantine(ref, path)
            raise
        if self.touch_on_read:
            with contextlib.suppress(OSError):
                os.utime(path, None)
        return data

    def exists(self, ref: ObjectRef) -> bool:
        return os.path.isfile(self.path_for(ref))

    def size(self, ref: ObjectRef) -> int:
        try:
            return os.stat(self.path_for(ref)).st_size
        except FileNotFoundError:
            raise ObjectMissing(f"{self.name}: no object {ref} under {self.root}") from None

    def list(self, prefix: str = "") -> Iterator[ObjectRef]:
        hexprefix = ref_prefix_hex(prefix)
        base = os.path.join(self.root, OBJECTS_DIR)
        yield from (ObjectRef(f"sha256:{h}") for h in self._walk_hexes(base, hexprefix, 0))

    def _walk_hexes(self, directory: str, hexprefix: str, level: int) -> Iterator[str]:
        try:
            entries = sorted(os.scandir(directory), key=lambda e: e.name)
        except FileNotFoundError:
            return
        width, depth = self.layout.shard_width, self.layout.shard_depth
        for entry in entries:
            if is_temp_name(entry.name) or entry.name.startswith("."):
                continue
            if level < depth:
                if not entry.is_dir(follow_symlinks=False):
                    continue
                shard = entry.name
                lo, hi = level * width, (level + 1) * width
                want = hexprefix[lo:hi]
                if want and not (shard.startswith(want) if len(want) < width else shard == want):
                    continue
                yield from self._walk_hexes(entry.path, hexprefix, level + 1)
            else:
                if entry.is_file(follow_symlinks=False) and len(entry.name) == 64 and entry.name.startswith(hexprefix):
                    yield entry.name

    def put_named(self, name: str, data: bytes) -> None:
        path = self._named_path(name)
        if os.path.isdir(path):
            raise InvalidName(f"named pointer {name!r} is a directory of other pointers")
        atomic_replace(path, bytes(data), fsync=self.fsync, tag="named")

    def get_named(self, name: str) -> bytes | None:
        try:
            with open(self._named_path(name), "rb") as fh:
                return fh.read()
        except FileNotFoundError:
            return None
        except IsADirectoryError:
            raise InvalidName(f"named pointer {name!r} is a directory of other pointers ({name}/<key>); "
                              f"a per-task summary lives at {name}.index (tasks.results.result_index_name)") from None

    # ---- NamedIndexStore ---------------------------------------------------------------------
    def list_named(self, prefix: str = "") -> Iterator[str]:
        """All pointer names starting with ``prefix`` (a name prefix, e.g. ``results/<id>/``), sorted."""
        base = os.path.join(self.root, NAMED_DIR)
        for name in self._walk_names(base, ""):
            if name.startswith(prefix):
                yield name

    def _walk_names(self, directory: str, rel: str) -> Iterator[str]:
        try:
            entries = sorted(os.scandir(directory), key=lambda e: e.name)
        except FileNotFoundError:
            return
        for entry in entries:
            if is_temp_name(entry.name) or entry.name.startswith("."):
                continue
            sub = f"{rel}/{entry.name}" if rel else entry.name
            if entry.is_dir(follow_symlinks=False):
                yield from self._walk_names(entry.path, sub)
            elif entry.is_file(follow_symlinks=False):
                yield sub

    def delete_named(self, name: str) -> bool:
        path = self._named_path(name)
        try:
            os.unlink(path)
        except FileNotFoundError:
            return False
        self._prune_empty_dirs(os.path.dirname(path), os.path.join(self.root, NAMED_DIR))
        return True

    # ---- EnumerableStore ---------------------------------------------------------------------
    def stat(self, ref: ObjectRef) -> ObjectStat:
        try:
            st = os.stat(self.path_for(ref))
        except FileNotFoundError:
            raise ObjectMissing(f"{self.name}: no object {ref} under {self.root}") from None
        return ObjectStat(ref=validate_ref(ref), size=st.st_size, mtime=st.st_mtime, atime=st.st_atime)

    def iter_stats(self) -> Iterator[ObjectStat]:
        for ref in self.list():
            try:
                yield self.stat(ref)
            except ObjectMissing:
                continue

    def usage(self, *, refresh: bool = False) -> tuple[int, int]:
        """(bytes, count) of objects; walked once per process, then maintained incrementally."""
        if self._usage is None or refresh:
            total = count = 0
            for s in self.iter_stats():
                total += s.size
                count += 1
            self._usage = (total, count)
        return self._usage

    def evict(self, ref: ObjectRef) -> int:
        path = self.path_for(ref)
        try:
            size = os.stat(path).st_size
            os.unlink(path)
        except FileNotFoundError:
            return 0
        if self._usage is not None:
            self._usage = (max(0, self._usage[0] - size), max(0, self._usage[1] - 1))
        return size

    def gc_lock(self) -> ContextManager[Any]:
        return ExclusiveFileLock(os.path.join(self.root, GC_LOCK_FILE), what="object store GC lock")

    def sweep_temp(self, *, older_than_s: int = 300, now: float | None = None, dry_run: bool = False) -> int:
        """Remove abandoned ``.tmp-*`` files older than ``older_than_s`` under objects/ and named/."""
        now = time.time() if now is None else now
        swept = 0
        for top in (OBJECTS_DIR, NAMED_DIR, PINS_DIR):
            for dirpath, _dirs, files in os.walk(os.path.join(self.root, top)):
                for fn in files:
                    if not is_temp_name(fn):
                        continue
                    full = os.path.join(dirpath, fn)
                    try:
                        if now - os.stat(full).st_mtime >= older_than_s:
                            if not dry_run:
                                os.unlink(full)
                            swept += 1
                    except FileNotFoundError:
                        continue
        return swept

    # ---- PinRegistry -------------------------------------------------------------------------
    def _pin_path(self, owner: str) -> str:
        return os.path.join(self.root, PINS_DIR, f"{validate_owner(owner)}.json")

    def pin(self, owner: str, refs: Iterable[ObjectRef]) -> list[ObjectRef]:
        """Register in-flight pins for ``owner``; returns the refs that are *not* present (fetch them, then use).

        Pin first, verify second: an eviction that raced the caller's earlier existence check is
        reported here instead of surfacing mid-task.
        """
        wanted = sorted({validate_ref(r) for r in refs})
        doc = {"schema": PIN_SCHEMA_VERSION, "owner": owner, "refs": [str(r) for r in wanted]}
        atomic_replace(self._pin_path(owner), canonical_json(doc), fsync=self.fsync, tag="pin")
        return [r for r in wanted if not self.exists(r)]

    def unpin(self, owner: str) -> None:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(self._pin_path(owner))

    def pins(self) -> Mapping[str, Sequence[ObjectRef]]:
        out: dict[str, tuple[ObjectRef, ...]] = {}
        base = os.path.join(self.root, PINS_DIR)
        try:
            entries = sorted(os.scandir(base), key=lambda e: e.name)
        except FileNotFoundError:
            return out
        for entry in entries:
            if not entry.name.endswith(".json") or is_temp_name(entry.name):
                continue
            try:
                with open(entry.path, "rb") as fh:
                    doc = json.loads(fh.read().decode("utf-8"))
            except (OSError, ValueError):
                continue
            refs = doc.get("refs", []) if isinstance(doc, dict) else []
            out[entry.name[:-5]] = tuple(ObjectRef(r) for r in refs if isinstance(r, str))
        return out

    def pinned_refs(self) -> Iterator[ObjectRef]:
        seen: set[ObjectRef] = set()
        for refs in self.pins().values():
            seen.update(refs)
        yield from sorted(seen)

    # ---- GC / cap ----------------------------------------------------------------------------
    def pin_sources(self) -> list[gc_module.PinSource]:
        return gc_module.default_pin_sources(self, depth=self.gc_walk_depth, max_scan_bytes=self.gc_max_scan_bytes)

    def gc(self, *, dry_run: bool = False, target_bytes: int | None = None,
           extra_pins: Sequence[gc_module.PinSource] = ()) -> gc_module.GcReport:
        """Run one sweep under the GC lock (``AlreadyOwned`` if another sweep holds it)."""
        report = gc_module.collect(
            self, cap_bytes=self.size_cap_bytes, low_water=self.gc_low_water, grace_s=self.gc_grace_s,
            policy=self.gc_policy, pin_sources=[*self.pin_sources(), *extra_pins], target_bytes=target_bytes,
            dry_run=dry_run,
        )
        if not dry_run:
            self._usage = None
        return report

    def _make_room(self, incoming: int) -> None:
        used, _count = self.usage()
        if used + incoming <= self.size_cap_bytes:
            return
        target = max(0, int(self.size_cap_bytes * self.gc_low_water) - incoming)
        try:
            report = self.gc(target_bytes=target)
        except AlreadyOwned:
            used, _count = self.usage(refresh=True)
            if used + incoming <= self.size_cap_bytes:
                return
            raise StoreFull(
                f"object store {self.root} is at its cap ({used} + {incoming} > {self.size_cap_bytes} bytes) and "
                f"another process holds the GC lock; retry after it finishes or raise objects.size_cap_bytes")
        used, _count = self.usage(refresh=True)
        if used + incoming > self.size_cap_bytes:
            why = "pinned objects alone exceed the cap" if report.pinned_over_cap else (
                f"{report.skipped_young} object(s) are inside the {self.gc_grace_s}s grace window" if report.skipped_young
                else "nothing unpinned is left to evict")
            raise StoreFull(
                f"object store {self.root} cannot fit {incoming} bytes: {used} of {self.size_cap_bytes} used after GC "
                f"freed {report.freed_bytes} bytes ({why}); raise objects.size_cap_bytes, unpin, or add a layer")

    # ---- helpers -----------------------------------------------------------------------------
    def materialize(self, ref: ObjectRef, dest: str | os.PathLike[str], *, link: bool = True) -> str:
        """Place an object at ``dest`` (hard link when possible, else copy).  For scratch layouts."""
        src = self.path_for(ref)
        if not os.path.isfile(src):
            raise ObjectMissing(f"{self.name}: no object {ref} under {self.root}")
        dest = os.fspath(dest)
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        if link:
            try:
                os.link(src, dest)
                return dest
            except FileExistsError:
                raise
            except OSError:
                pass
        shutil.copyfile(src, dest)
        return dest

    def _quarantine(self, ref: ObjectRef, path: str) -> None:
        qdir = os.path.join(self.root, CORRUPT_DIR)
        os.makedirs(qdir, exist_ok=True)
        with contextlib.suppress(OSError):
            os.replace(path, os.path.join(qdir, f"{ref.hex}-{int(time.time())}"))
        self._usage = None

    @staticmethod
    def _prune_empty_dirs(directory: str, stop: str) -> None:
        directory = os.path.abspath(directory)
        stop = os.path.abspath(stop)
        while directory.startswith(stop) and directory != stop:
            try:
                os.rmdir(directory)
            except OSError:
                return
            directory = os.path.dirname(directory)

    def describe(self) -> dict[str, Any]:
        info = super().describe()
        info.update({
            "root": self.root, "shard_width": self.layout.shard_width, "shard_depth": self.layout.shard_depth,
            "hash_algorithm": self.layout.hash_algorithm, "fsync": self.fsync.value,
            "write_once_strategy": self.write_once_strategy, "touch_on_read": self.touch_on_read,
            "quarantine_corrupt": self.quarantine_corrupt, "size_cap_bytes": self.size_cap_bytes,
            "gc": {"policy": self.gc_policy, "low_water": self.gc_low_water, "grace_s": self.gc_grace_s,
                   "walk_depth": self.gc_walk_depth, "max_scan_bytes": self.gc_max_scan_bytes},
            "supports": ["named-index", "enumerable", "pins", "materialize"],
        })
        return info


def _build_schema() -> dict[str, Any]:
    from ..config import LocalStoreConfig, ObjectsConfig
    schema = schema_from_dataclass(ObjectsConfig, title="local object store")
    schema["properties"] = {k: v for k, v in schema["properties"].items() if k not in ("s3", "mirror", "peer", "layered")}
    schema["properties"]["local"] = schema_from_dataclass(LocalStoreConfig, title="local")
    return schema


LocalDirStore.config_schema = _build_schema()

__all__ = ["LocalDirStore", "PIN_SCHEMA_VERSION"]
