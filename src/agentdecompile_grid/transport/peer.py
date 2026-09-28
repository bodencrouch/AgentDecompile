"""PeerTransport (declared): fleet nodes serving objects to each other over peer HTTP.

Reads only: a fleet node with a public address mirrors restricted and toolchain objects for the
other fleet nodes (design §6.1); records and heads still go through the upstream transport.
Donors never use it (they are outbound-only clients of the static mirror).

Acceptance test named for the final verification phase (U121): ``test_peer_declared`` (accessors
raise ``NotConfigured`` naming the peer object adapter; ``describe()`` lists ``peers``).
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..core import TRANSPORTS, HeadStore, LogStore, NotConfigured, ObjectStore


class PeerTransport:
    name = "peer"
    CONFIG_SCHEMA: Mapping[str, str] = {
        "peers": "list of https://<fleet-node>/ object mirrors (fleet keys only)",
        "upstream": "the transport used for log and heads (this one serves objects only)",
        "timeout_s": "per-request deadline",
    }

    def __init__(self, peers: Sequence[str] = (), *, upstream: Any = None, timeout_s: float = 30.0) -> None:
        self.peers = tuple(peers)
        self.upstream = upstream
        self.timeout_s = timeout_s

    @classmethod
    def from_locator(cls, locator: Mapping[str, Any]) -> "PeerTransport":
        return cls(tuple(locator.get("peers", ())))

    def objects(self) -> ObjectStore:
        raise NotConfigured(f"peer transport objects: needs the 'peer' object store adapter from agentdecompile_grid.objects over peers {list(self.peers) or '(none configured)'}")

    def log(self) -> LogStore:
        if self.upstream is None:
            raise NotConfigured("peer transport serves objects only; pass upstream= for the log")
        return self.upstream.log()

    def heads(self) -> HeadStore:
        if self.upstream is None:
            raise NotConfigured("peer transport serves objects only; pass upstream= for the heads")
        return self.upstream.heads()

    def locator(self) -> dict[str, Any]:
        return {"adapter": "peer", "peers": list(self.peers)}

    def describe(self) -> Mapping[str, Any]:
        return {"name": self.name, "status": "declared", "needs": ["objects.peer adapter"] + ([] if self.peers else ["peers"]), "peers": list(self.peers), "config_schema": dict(self.CONFIG_SCHEMA)}


TRANSPORTS.register("peer", PeerTransport)

__all__ = ["PeerTransport"]
