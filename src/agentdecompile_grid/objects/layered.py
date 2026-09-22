"""agentdecompile_grid.objects.layered — ``LayeredStore``: read-through over an ordered list of stores.

This is how a laptop uses ``local + mirror`` and a fleet node uses ``local + s3``.

* **Reads** try layers in order; a hit in layer *k* is promoted into the writable layers before
  it (``promote_on_read``), re-hashed on the way in.  ``exists``/``size`` are first-hit.
  ``list`` is the sorted union; a layer that cannot list (``NotConfigured``) is skipped.
* **Writes** always land in the first layer first (the local cache, durable immediately).
  ``write_policy``: ``all`` (default) = then every other writable layer, read-only layers
  (``ReadOnly``) skipped; ``first`` = stop at the first layer (only when an outbox propagates);
  ``all-strict`` = every layer must accept.  A later layer that fails is recorded in ``pending``
  (``on_layer_failure=record``) so ``flush_pending()`` can replay it — or raises ``PartialWrite``
  (``on_layer_failure=raise``).  Either way the object is durable in the first layer before
  anything else happens.
* **Named pointers** are the mutable thing, so which layer answers matters.  ``named_authority``
  = ``first`` (default: read-your-own-writes on a laptop; the local layer is written on
  ``put_named`` and answers ``get_named``), ``last`` (the shared layer wins; use when several
  nodes write the same names through S3), or an index.  Others are fallbacks in order.
  ``put_named`` goes to the first layer and then to every other writable layer (never
  ``first``-only: a pointer that stays local would be invisible to the grid).
* ``list_named`` unions every layer that can enumerate; ``delete_named`` deletes everywhere it can.

Acceptance tests (named here, landed in the verification phase):

* ``test_layered_read_through_promotes_and_verifies`` — an object only in the mirror becomes local
  after one ``get``; a corrupt mirror object is not promoted.
* ``test_layered_write_first_then_flush_pending`` — with the second layer failing, ``put`` succeeds,
  ``pending`` holds the ref, ``flush_pending`` clears it once the layer recovers.
* ``test_layered_named_read_your_own_writes`` — ``put_named`` then ``get_named`` returns the new
  value even when the mirror holds an older one.
* ``test_layered_read_only_layer_is_skipped_not_failed`` — local + mirror: ``put`` does not raise.
"""
from __future__ import annotations

import threading
from typing import Any, Iterator, Sequence

from ..core import GridError, NotConfigured, ObjectRef, ObjectStore
from .base import (
    BaseObjectStore, IntegrityError, NamedIndexStore, ObjectMissing, ReadOnly, describe_store, schema_from_dataclass,
    validate_ref,
)


class PartialWrite(GridError):
    """The first layer accepted the write but a later layer did not (``on_layer_failure=raise``)."""

    def __init__(self, message: str, ref: ObjectRef | None, failures: Sequence[tuple[str, str]]) -> None:
        super().__init__(message)
        self.ref = ref
        self.failures = tuple(failures)


class LayeredStore(BaseObjectStore):
    """Ordered layers; first = cache and primary write target."""

    name = "layered"
    kind = "object-store"
    status = "working"

    def __init__(self, layers: Sequence[ObjectStore], *, write_policy: str = "all", promote_on_read: bool = True,
                 named_authority: str | int = "first", on_layer_failure: str = "record", verify_on_read: bool = True) -> None:
        if not layers:
            raise NotConfigured("LayeredStore needs at least one layer (objects.layered.layers)")
        if write_policy not in ("first", "all", "all-strict"):
            raise NotConfigured(f"objects.layered.write_policy must be first | all | all-strict, got {write_policy!r}")
        if on_layer_failure not in ("record", "raise"):
            raise NotConfigured(f"objects.layered.on_layer_failure must be record | raise, got {on_layer_failure!r}")
        self.layers: tuple[ObjectStore, ...] = tuple(layers)
        self.write_policy = write_policy
        self.promote_on_read = promote_on_read
        self.on_layer_failure = on_layer_failure
        self.verify_on_read = verify_on_read
        self.named_authority = self._authority_index(named_authority)
        self._pending: dict[str, set[ObjectRef]] = {}
        self._pending_named: dict[str, dict[str, bytes]] = {}
        self._lock = threading.Lock()

    @classmethod
    def from_config(cls, cfg: Any, layers: Sequence[ObjectStore]) -> "LayeredStore":
        lc = cfg.objects.layered
        return cls(layers, write_policy=lc.write_policy, promote_on_read=lc.promote_on_read,
                   named_authority=lc.named_authority, on_layer_failure=lc.on_layer_failure,
                   verify_on_read=cfg.objects.verify_on_read)

    def _authority_index(self, spec: str | int) -> int:
        n = len(self.layers)
        if isinstance(spec, int):
            idx = spec
        elif spec == "first":
            idx = 0
        elif spec == "last":
            idx = n - 1
        elif isinstance(spec, str) and spec.isdigit():
            idx = int(spec)
        else:
            raise NotConfigured(f"objects.layered.named_authority must be first | last | <index>, got {spec!r}")
        if not 0 <= idx < n:
            raise NotConfigured(f"objects.layered.named_authority index {idx} is outside the {n} configured layer(s)")
        return idx

    @property
    def primary(self) -> ObjectStore:
        return self.layers[0]

    def _layer_name(self, store: ObjectStore) -> str:
        return getattr(store, "name", type(store).__name__)

    # ---- reads -------------------------------------------------------------------------------
    def get(self, ref: ObjectRef) -> bytes:
        validate_ref(ref)
        errors: list[str] = []
        for idx, layer in enumerate(self.layers):
            try:
                data = layer.get(ref)
            except (ObjectMissing, KeyError):
                continue
            except IntegrityError as exc:
                errors.append(f"{self._layer_name(layer)}: {exc}")
                continue
            except (NotConfigured, OSError) as exc:
                errors.append(f"{self._layer_name(layer)}: {exc}")
                continue
            self.check_integrity(ref, data)
            if idx > 0 and self.promote_on_read:
                self._promote(ref, data, upto=idx)
            return data
        detail = f" ({'; '.join(errors)})" if errors else ""
        raise ObjectMissing(f"layered: no layer holds {ref}{detail}")

    def _promote(self, ref: ObjectRef, data: bytes, *, upto: int) -> None:
        for layer in self.layers[:upto]:
            try:
                layer.put(data, expect=ref) if isinstance(layer, BaseObjectStore) else layer.put(data)
            except (ReadOnly, NotConfigured, OSError):
                continue

    def exists(self, ref: ObjectRef) -> bool:
        validate_ref(ref)
        for layer in self.layers:
            try:
                if layer.exists(ref):
                    return True
            except (NotConfigured, OSError):
                continue
        return False

    def size(self, ref: ObjectRef) -> int:
        validate_ref(ref)
        for layer in self.layers:
            try:
                return layer.size(ref)
            except (ObjectMissing, KeyError, NotConfigured, OSError):
                continue
        raise ObjectMissing(f"layered: no layer holds {ref}")

    def list(self, prefix: str = "") -> Iterator[ObjectRef]:
        seen: set[ObjectRef] = set()
        for layer in self.layers:
            try:
                seen.update(layer.list(prefix))
            except (NotConfigured, OSError):
                continue
        yield from sorted(seen)

    # ---- writes ------------------------------------------------------------------------------
    def put(self, data: bytes, *, expect: ObjectRef | None = None) -> ObjectRef:
        data = bytes(data)
        ref = self.expected_ref(data, expect)
        primary = self.primary
        ref = primary.put(data, expect=ref) if isinstance(primary, BaseObjectStore) else primary.put(data)
        if self.write_policy == "first":
            return ref
        failures: list[tuple[str, str]] = []
        for layer in self.layers[1:]:
            try:
                layer.put(data, expect=ref) if isinstance(layer, BaseObjectStore) else layer.put(data)
            except ReadOnly as exc:
                if self.write_policy == "all-strict":
                    failures.append((self._layer_name(layer), str(exc)))
            except (NotConfigured, OSError, GridError) as exc:
                failures.append((self._layer_name(layer), str(exc)))
        if failures:
            self._record_failure(ref, failures)
        return ref

    def _record_failure(self, ref: ObjectRef | None, failures: Sequence[tuple[str, str]], *, named: tuple[str, bytes] | None = None) -> None:
        if self.on_layer_failure == "raise":
            what = f"named pointer {named[0]!r}" if named else f"object {ref}"
            raise PartialWrite(f"layered: {what} is durable in {self._layer_name(self.primary)} but "
                               + "; ".join(f"{n} failed: {m}" for n, m in failures), ref, failures)
        with self._lock:
            for layer_name, _msg in failures:
                if named:
                    self._pending_named.setdefault(layer_name, {})[named[0]] = named[1]
                elif ref is not None:
                    self._pending.setdefault(layer_name, set()).add(ref)

    @property
    def pending(self) -> dict[str, list[ObjectRef]]:
        """Refs per layer name that still need propagation (``on_layer_failure=record``)."""
        with self._lock:
            return {name: sorted(refs) for name, refs in sorted(self._pending.items()) if refs}

    @property
    def pending_named(self) -> dict[str, list[str]]:
        with self._lock:
            return {name: sorted(items) for name, items in sorted(self._pending_named.items()) if items}

    def flush_pending(self) -> dict[str, int]:
        """Retry every recorded propagation from the primary layer; returns {layer: still_pending}."""
        with self._lock:
            snapshot = {name: sorted(refs) for name, refs in self._pending.items()}
            snapshot_named = {name: dict(items) for name, items in self._pending_named.items()}
        remaining: dict[str, int] = {}
        by_name = {self._layer_name(layer): layer for layer in self.layers}
        for layer_name, refs in snapshot.items():
            layer = by_name.get(layer_name)
            for ref in refs:
                ok = False
                if layer is not None:
                    try:
                        data = self.primary.get(ref)
                        layer.put(data, expect=ref) if isinstance(layer, BaseObjectStore) else layer.put(data)
                        ok = True
                    except (ReadOnly,):
                        ok = True  # became read-only: nothing to propagate
                    except (GridError, OSError, KeyError):
                        ok = False
                if ok:
                    with self._lock:
                        self._pending.get(layer_name, set()).discard(ref)
            remaining[layer_name] = len(self._pending.get(layer_name, ()))
        for layer_name, items in snapshot_named.items():
            layer = by_name.get(layer_name)
            for name, data in items.items():
                ok = False
                if layer is not None:
                    try:
                        layer.put_named(name, data)
                        ok = True
                    except ReadOnly:
                        ok = True
                    except (GridError, OSError):
                        ok = False
                if ok:
                    with self._lock:
                        self._pending_named.get(layer_name, {}).pop(name, None)
            remaining[layer_name] = remaining.get(layer_name, 0) + len(self._pending_named.get(layer_name, {}))
        return remaining

    # ---- named pointers ----------------------------------------------------------------------
    def put_named(self, name: str, data: bytes) -> None:
        data = bytes(data)
        self.primary.put_named(name, data)
        failures: list[tuple[str, str]] = []
        for layer in self.layers[1:]:
            try:
                layer.put_named(name, data)
            except ReadOnly as exc:
                if self.write_policy == "all-strict":
                    failures.append((self._layer_name(layer), str(exc)))
            except (NotConfigured, OSError, GridError) as exc:
                failures.append((self._layer_name(layer), str(exc)))
        if failures:
            self._record_failure(None, failures, named=(name, data))

    def get_named(self, name: str) -> bytes | None:
        order = [self.named_authority] + [i for i in range(len(self.layers)) if i != self.named_authority]
        for idx in order:
            try:
                data = self.layers[idx].get_named(name)
            except (NotConfigured, OSError):
                continue
            if data is not None:
                return data
        return None

    def list_named(self, prefix: str = "") -> Iterator[str]:
        seen: set[str] = set()
        any_index = False
        for layer in self.layers:
            if isinstance(layer, NamedIndexStore):
                any_index = True
                try:
                    seen.update(layer.list_named(prefix))
                except (NotConfigured, OSError):
                    continue
        if not any_index:
            raise NotConfigured("no layer of this LayeredStore can enumerate named pointers; add a LocalDirStore layer")
        yield from sorted(seen)

    def delete_named(self, name: str) -> bool:
        deleted = False
        for layer in self.layers:
            if isinstance(layer, NamedIndexStore):
                try:
                    deleted = layer.delete_named(name) or deleted
                except (ReadOnly, NotConfigured, OSError):
                    continue
        return deleted

    def describe(self) -> dict[str, Any]:
        info = super().describe()
        info.update({
            "write_policy": self.write_policy, "promote_on_read": self.promote_on_read,
            "named_authority": self.named_authority, "on_layer_failure": self.on_layer_failure,
            "layers": [describe_store(layer) for layer in self.layers],
            "pending": {k: len(v) for k, v in self.pending.items()},
            "pending_named": {k: len(v) for k, v in self.pending_named.items()},
            "supports": ["read-through", "promote", "named-index" if any(isinstance(l, NamedIndexStore) for l in self.layers) else "named-read"],
        })
        return info


def _build_schema() -> dict[str, Any]:
    from ..config import LayeredStoreConfig
    return schema_from_dataclass(LayeredStoreConfig, title="layered object store")


LayeredStore.config_schema = _build_schema()

__all__ = ["LayeredStore", "PartialWrite"]
