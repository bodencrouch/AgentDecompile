"""agentdecompile_grid.transport — how a node reaches objects, log and heads.

``local`` works (objects/log/heads under one root, injected or built through the registries);
``https`` (outbound-only, presigned write-once PUT, static GET, no inbound port) and ``peer``
(fleet object mirrors) are declared with their config schema.  ``transport_for(url)`` picks by
scheme: a path or ``file://`` is local, ``https://`` is https.
"""
from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlsplit

from ..core import TRANSPORTS, NotConfigured
from .https import HttpsTransport
from .local import ChainAppender, HeadContention, LocalTransport
from .peer import PeerTransport


def transport_for(url_or_path: str, **kwargs: Any) -> Any:
    """Pick a transport for a fabric url.  ``file:///root`` or a plain path → ``LocalTransport.from_root``;
    ``https://host/...`` → ``HttpsTransport`` (declared: its accessors raise ``NotConfigured``)."""
    parts = urlsplit(url_or_path)
    if parts.scheme in ("", "file"):
        path = parts.path if parts.scheme == "file" else url_or_path
        root = path.split("/g/", 1)[0] if "/g/" in path else path
        return LocalTransport.from_root(os.path.expanduser(root), **kwargs)
    if parts.scheme == "https":
        base = f"{parts.scheme}://{parts.netloc}/"
        return HttpsTransport(base, **kwargs)
    if parts.scheme == "http":
        raise NotConfigured("plain http fabrics are not allowed: every node is an outbound-only https client (design §6.1)")
    try:
        cls = TRANSPORTS.get(parts.scheme)
    except KeyError as exc:
        raise NotConfigured(f"no transport for scheme {parts.scheme!r}; known: {TRANSPORTS.names()}") from exc
    return cls.from_locator({"adapter": parts.scheme, "url": url_or_path, **kwargs})


def from_locator(locator: dict[str, Any]) -> Any:
    cls = TRANSPORTS.get(str(locator.get("adapter", "")))
    return cls.from_locator(locator)


__all__ = ["ChainAppender", "HeadContention", "HttpsTransport", "LocalTransport", "PeerTransport", "from_locator", "transport_for"]
