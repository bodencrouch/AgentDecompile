"""agentdecompile_grid.fleet — the operator's fleet: user-data rendering, provider adapters, the manifest.

``fleet_up`` renders the user-data (its only step is the join command with a fleet invite),
creates nodes through a ``core.PROVIDERS`` adapter and records them in the manifest object;
``fleet_down`` reclaims and records; ``fleet_status`` reads the manifest.  Lane placement is by
canary, never by assumption: a node's lanes in the manifest are what it *asked* for, its
capabilities are what its canaries proved.

Acceptance test named for the final verification phase (U129): ``test_fleet_up_records``
(``fleet_up`` with the manual provider renders one-step user-data, returns two node ids and a
manifest object exists with both as ``pending``; ``fleet_down`` marks them ``down``).
"""
from __future__ import annotations

import time
from typing import Any, Callable, Mapping, Sequence

from ..core import PROVIDERS, ObjectRef, ObjectStore
from . import providers as providers  # noqa: F401  (registers PROVIDERS entries)
from .cloudinit import BASH_TEMPLATE, CLOUD_CONFIG_TEMPLATE, TemplateError, join_command, render_user_data
from .manifest import MANIFEST_POINTER, FleetManifest, NodeEntry, fleet_status
from .providers import AwsProvider, GcpProvider, HetznerProvider, ManualProvider, OciProvider, ProviderError, SshProvider, describe_providers, provider_for


def fleet_up(objects: ObjectStore, invite_url: str, *, provider: str | Any, count: int, role: str = "fleet", lanes: Sequence[str] = (), labels: Mapping[str, str] | None = None,
             provider_config: Mapping[str, Any] | None = None, user_data_format: str | None = None, now: Callable[[], float] = time.time, fabric_id: str = "", **render: Any) -> tuple[Sequence[str], ObjectRef]:
    """Render → create → record.  Returns the node ids and the manifest object ref."""
    adapter = provider_for(provider, **(provider_config or {})) if isinstance(provider, str) else provider
    fmt = user_data_format or ("bash" if getattr(adapter, "name", "") == "ssh" else "cloud-config")
    user_data = render_user_data(invite_url, role=role, lanes=lanes, format=fmt, **render)
    labels = dict(labels or {})
    node_ids = adapter.up(count, user_data, labels)
    manifest = FleetManifest.load(objects)
    manifest.fabric_id = manifest.fabric_id or fabric_id
    stamp = now()
    for node_id in node_ids:
        state = "up" if getattr(adapter, "name", "") == "ssh" else "pending"
        manifest.upsert(NodeEntry(node_id=node_id, provider=getattr(adapter, "name", str(provider)), role=role, lanes=tuple(lanes), state=state, labels=labels), now=stamp)
    return node_ids, manifest.save(objects, now=stamp)


def fleet_bind(objects: ObjectStore, placeholder: str, node_id: str, *, provider: Any = None, now: Callable[[], float] = time.time) -> ObjectRef:
    """After a manual ``up``: the operator pastes back the real node id; the manifest follows."""
    if provider is not None and hasattr(provider, "bind"):
        provider.bind(placeholder, node_id)
    manifest = FleetManifest.load(objects)
    stamp = now()
    manifest.rename(placeholder, node_id, now=stamp)
    return manifest.save(objects, now=stamp)


def fleet_down(objects: ObjectStore, node_ids: Sequence[str], *, provider: str | Any, provider_config: Mapping[str, Any] | None = None, now: Callable[[], float] = time.time) -> ObjectRef:
    adapter = provider_for(provider, **(provider_config or {})) if isinstance(provider, str) else provider
    adapter.down(node_ids)
    manifest = FleetManifest.load(objects)
    stamp = now()
    for node_id in node_ids:
        if node_id in manifest.entries:
            manifest.mark(node_id, "down", now=stamp)
    return manifest.save(objects, now=stamp)


__all__ = [
    "AwsProvider", "BASH_TEMPLATE", "CLOUD_CONFIG_TEMPLATE", "FleetManifest", "GcpProvider", "HetznerProvider", "MANIFEST_POINTER", "ManualProvider", "NodeEntry", "OciProvider",
    "PROVIDERS", "ProviderError", "SshProvider", "TemplateError", "describe_providers", "fleet_bind", "fleet_down", "fleet_status", "fleet_up", "join_command", "provider_for", "render_user_data",
]
