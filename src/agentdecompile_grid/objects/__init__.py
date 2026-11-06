"""agentdecompile_grid.objects — content-addressed object store adapters.

Importing this package registers every adapter in ``core.OBJECT_STORES``:

==============  ====================  ========  ==================================================
registry name   class                 status    notes
==============  ====================  ========  ==================================================
``local``       ``LocalDirStore``     working   sharded dir, write-once, names, pins, GC, cap
``s3``          ``S3CompatibleStore`` declared  conditional PUT, presigned URLs; needs boto3 + bucket
``static-mirror`` ``StaticMirrorStore`` working reads over HTTP(S); writes are ``ReadOnly``
``peer``        ``PeerHTTPStore``     declared  outbound-only client of a node's read endpoint
``layered``     ``LayeredStore``      working   read-through over ordered layers, cache-first writes
==============  ====================  ========  ==================================================

``open_store(cfg)`` builds the adapter named by ``cfg.adapters.objects`` (``layered`` composes
the adapters named in ``cfg.objects.layered.layers``).  ``describe_adapters()`` is what the CLI
prints for ``adgrid objects adapters``.
"""
from __future__ import annotations

from typing import Any, Mapping

from ..core import OBJECT_STORES, NotConfigured, ObjectStore
from . import gc
from .base import (
    BaseObjectStore, EnumerableStore, FsyncPolicy, IntegrityError, InvalidName, InvalidRef, Layout, LayoutMismatch,
    NamedIndexStore, ObjectMissing, ObjectStat, PinRegistry, ReadOnly, StoreFull, can_list_named, describe_store, is_ref,
    validate_name, validate_ref,
)
from .layered import LayeredStore, PartialWrite
from .local import LocalDirStore
from .peer import PeerHTTPStore
from .s3 import S3CompatibleStore
from .static import StaticMirrorStore, write_mirror_index

ADAPTERS: tuple[type[BaseObjectStore], ...] = (LocalDirStore, S3CompatibleStore, StaticMirrorStore, PeerHTTPStore, LayeredStore)

for _cls in ADAPTERS:
    if _cls.name not in OBJECT_STORES:
        OBJECT_STORES.register(_cls.name, _cls)


def open_store(cfg: Any, *, adapter: str | None = None, env: Mapping[str, str] | None = None) -> ObjectStore:
    """Build the object store the configuration names (or ``adapter``), recursively for ``layered``."""
    name = adapter or cfg.adapters.objects
    if name == "local":
        return LocalDirStore.from_config(cfg)
    if name == "s3":
        return S3CompatibleStore.from_config(cfg)
    if name == "static-mirror":
        return StaticMirrorStore.from_config(cfg)
    if name == "peer":
        return PeerHTTPStore.from_config(cfg, env=env)
    if name == "layered":
        layer_names = list(cfg.objects.layered.layers)
        if "layered" in layer_names:
            raise NotConfigured("objects.layered.layers cannot contain 'layered'")
        layers = [open_store(cfg, adapter=layer, env=env) for layer in layer_names]
        return LayeredStore.from_config(cfg, layers)
    cls = OBJECT_STORES.get(name)  # third-party registration
    if hasattr(cls, "from_config"):
        return cls.from_config(cfg)
    raise NotConfigured(f"object store adapter {name!r} has no from_config(); construct it directly")


def describe_adapters() -> dict[str, Any]:
    """Name, status and config schema of every registered adapter (no I/O)."""
    out: dict[str, Any] = {}
    for name, cls in OBJECT_STORES.items():
        out[name] = {"class": getattr(cls, "__name__", str(cls)), "status": getattr(cls, "status", "unknown"),
                     "kind": getattr(cls, "kind", "object-store"), "config_schema": getattr(cls, "config_schema", {})}
    return out


__all__ = [
    "ADAPTERS", "open_store", "describe_adapters", "describe_store", "gc",
    "BaseObjectStore", "LocalDirStore", "S3CompatibleStore", "StaticMirrorStore", "PeerHTTPStore", "LayeredStore",
    "PartialWrite", "write_mirror_index",
    "EnumerableStore", "NamedIndexStore", "PinRegistry", "ObjectStat", "Layout", "FsyncPolicy",
    "IntegrityError", "InvalidName", "InvalidRef", "LayoutMismatch", "ObjectMissing", "ReadOnly", "StoreFull",
    "is_ref", "validate_name", "validate_ref", "can_list_named",
]
