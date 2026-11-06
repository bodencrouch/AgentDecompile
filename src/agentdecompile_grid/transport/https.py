"""HttpsTransport (declared): outbound-only HTTPS on 443; static GETs; presigned write-once PUTs; no inbound port.

Wire contract this adapter implements when the object/log adapters it needs land (design §6.1):

* objects  ``GET  {base}/objects/<hex[:2]>/<hex>``          static, cacheable, mirrorable
           ``PUT  <presigned url>`` with ``If-None-Match: *``  write-once, size-capped, scoped to
           the expected hash; the presigned url comes from ``POST {presign}`` signed by the node key
* log      ``GET  {base}/log/<partition>/<seq>.json``      records are objects too
* heads    ``PUT  {base}/heads/<partition>`` with ``If-Match: <etag>`` — the only live RPC
* nodes never accept a connection; nodes never talk to each other (peer mirrors are ``peer``)

``objects()``, ``log()`` and ``heads()`` raise ``NotConfigured`` naming the object store adapter
(``mirror``/``s3`` from ``agentdecompile_grid.objects``) and the presign endpoint they need.

Acceptance test named for the final verification phase (U121/U122): ``test_https_declared``
(every accessor raises ``NotConfigured`` whose message names 'presign' and the adapter name;
``describe()`` lists the config schema).
"""
from __future__ import annotations

from typing import Any, Mapping

from ..core import TRANSPORTS, HeadStore, LogStore, NotConfigured, ObjectStore, Signer


class HttpsTransport:
    name = "https"
    CONFIG_SCHEMA: Mapping[str, str] = {
        "base_url": "https://<fabric-host>/ — static object and log reads",
        "presign_url": "endpoint returning presigned write-once PUT urls for this key",
        "heads_url": "conditional-PUT head endpoint (bucket If-Match or the fleet head table)",
        "key_id": "this node's key id (requests are signed by the node key)",
        "timeout_s": "per-request deadline (default 30)",
        "ca_bundle": "optional CA bundle path",
    }

    def __init__(self, base_url: str = "", *, presign_url: str = "", heads_url: str = "", key_id: str = "", signer: Signer | None = None, timeout_s: float = 30.0, ca_bundle: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.presign_url = presign_url
        self.heads_url = heads_url
        self.key_id = key_id
        self.signer = signer
        self.timeout_s = timeout_s
        self.ca_bundle = ca_bundle

    @classmethod
    def from_locator(cls, locator: Mapping[str, Any]) -> "HttpsTransport":
        return cls(str(locator.get("base_url", "")), presign_url=str(locator.get("presign_url", "")), heads_url=str(locator.get("heads_url", "")), key_id=str(locator.get("key_id", "")))

    def _missing(self) -> list[str]:
        return [k for k in ("base_url", "presign_url", "heads_url") if not getattr(self, k)]

    def objects(self) -> ObjectStore:
        raise NotConfigured(f"https transport objects: needs the 'mirror' (static GET) and presigned write-once PUT object store adapter from agentdecompile_grid.objects and config {self._missing() or 'complete'}; base_url={self.base_url!r}")

    def log(self) -> LogStore:
        raise NotConfigured(f"https transport log: needs the static-read log adapter from agentdecompile_grid.log over {self.base_url!r}/log and the presign endpoint {self.presign_url!r}")

    def heads(self) -> HeadStore:
        raise NotConfigured(f"https transport heads: needs the conditional-PUT head adapter (If-Match) at {self.heads_url!r}")

    def locator(self) -> dict[str, Any]:
        return {"adapter": "https", "base_url": self.base_url, "presign_url": self.presign_url, "heads_url": self.heads_url, "key_id": self.key_id}

    def describe(self) -> Mapping[str, Any]:
        return {"name": self.name, "status": "declared", "needs": self._missing() + ["objects.mirror adapter", "objects presigned PUT adapter", "log static-read adapter", "heads conditional-PUT adapter"], "config_schema": dict(self.CONFIG_SCHEMA), "inbound_ports": 0}


TRANSPORTS.register("https", HttpsTransport)

__all__ = ["HttpsTransport"]
