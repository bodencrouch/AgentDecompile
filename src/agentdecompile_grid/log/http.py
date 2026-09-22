"""``HttpLog``: declared adapter for nodes that only have outbound HTTP to a gateway.

Protocol it would run: the gateway fronts an ``S3ObjectLog``-shaped store and exposes
``PUT /log/<partition>/objects/<digest>`` (write-once), ``GET /log/<partition>?since=<seq>``
(a JSONL stream of records in order), ``GET /log/partitions`` and ``GET /log/<partition>/last``.
Ordering stays with the head store (``heads.HttpHeads``: ``PUT /heads/<partition>`` with
``If-Match``); the appender protocol is the same as for S3 and this adapter is likewise
``ordering_authority = "heads"``.  A static mirror (read-only, no PUT) is the same class with
``read_only: true`` and serves ``read`` from files a fleet node published.

Needs ``log.http.base_url``, a token source (``token_env``) and the gateway; until then every
call raises ``NotConfigured`` naming them.

Acceptance tests (named here, written in the verification phase):
  http-declared: ``HttpLog.describe()["status"] == "declared"``, construction raises
  ``NotConfigured`` naming ``base_url``; ``LOG_STORES.get("http")`` resolves.
"""
from __future__ import annotations

from typing import Any
from collections.abc import Iterator, Mapping, Sequence

from agentdecompile_grid.core import NotConfigured, Record


class HttpLog:
    name = "http"
    ordering_authority = "heads"
    REQUIRES = ("log.http.base_url", "log.http.token_env (bearer token variable) unless read_only",
                "a gateway implementing PUT /log/<partition>/objects/<digest>, GET /log/<partition>?since=, GET /log/partitions",
                "an HttpHeads head store on the same gateway")

    def __init__(self, config: Mapping[str, Any] | None = None) -> None:
        self.config = dict(config or {})
        self._unavailable()

    def _unavailable(self) -> None:
        missing = [k for k in ("base_url",) if not self.config.get(k)]
        raise NotConfigured(f"HttpLog is declared, not wired: needs {list(self.REQUIRES)}; missing config keys {missing}")

    def append(self, records: Sequence[Record]) -> None:
        self._unavailable()

    def publish(self, records: Sequence[Record]) -> None:
        self._unavailable()

    def read(self, partition: str, since_seq: int = 0) -> Iterator[Record]:
        self._unavailable()
        return iter(())  # pragma: no cover

    def partitions(self) -> Iterator[str]:
        self._unavailable()
        return iter(())  # pragma: no cover

    def last_seq(self, partition: str) -> int:
        self._unavailable()
        return 0  # pragma: no cover

    @classmethod
    def config_schema(cls) -> dict[str, Any]:
        return {"type": "object", "required": ["base_url"], "properties": {
            "adapter": {"const": "http"}, "base_url": {"type": "string"}, "token_env": {"type": "string"},
            "read_only": {"type": "boolean", "default": False, "description": "a static mirror: GET only"},
            "timeout_s": {"type": "number", "default": 30}}}

    @classmethod
    def describe(cls) -> dict[str, Any]:
        return {"name": cls.name, "status": "declared", "requires": list(cls.REQUIRES), "config_schema": cls.config_schema(),
                "ordering_authority": cls.ordering_authority,
                "semantics": "outbound-only HTTP to a gateway over an S3-shaped store; heads order, objects are write-once"}

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> HttpLog:
        return cls(config)


__all__ = ["HttpLog"]
