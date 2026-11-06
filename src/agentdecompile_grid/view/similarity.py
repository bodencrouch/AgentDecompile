"""Declared applier for the similarity index (the signature database) as a materialized view.

Design §2.4: the similarity index is a view like the SQLite store -- ``adgrid view materialize
--applier similarity`` replays verified merged-signature objects (``bsim-merge`` results, §3.7)
through the index's own commit verb, one program at a time, keyed ``(xml hash, cluster url)``.
Losing the cluster is a rebuild, never a loss of pipeline state.

This adapter is *declared*: it carries the config schema and ``describe()`` and refuses by name
until the commit verb is reachable from the grid side (the commit path today lives in the
recovery dashboard, catalog.py:418, and U141 lands the range variant and the pinned template).
Nothing here imports the recovery package.

Acceptance tests (named, landed with U141/U128):

* ``test_similarity_applier_declared`` -- ``describe()`` lists the schema; ``apply`` raises
  ``NotConfigured`` naming ``cluster_url`` / ``commit_verb``;
* ``test_similarity_view_rebuild_lists_same_programs`` -- dropping the index and
  re-materialising reproduces the executable and function inventory (U128 acceptance).
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from ..core import APPLIERS, NotConfigured, ObjectStore, Record


class SimilarityIndexApplier:
    """Replays verified merged-signature objects into the similarity index via its commit verb."""

    name = "similarity"
    CONFIG_SCHEMA: Mapping[str, str] = {
        "cluster_url": "url of the similarity index cluster (a database-server-backed service)",
        "template_id": "pinned signature template name (mandatory; live server state is not a basis)",
        "commit_verb": "argv template of the index commit verb; receives the merged XML object path",
        "commit_timeout_s": "kill deadline per commit (MEASURED 3.3-9.6 s per program)",
        "kinds": "task kinds whose verified outputs are committed (default: bsim-merge)",
    }
    KINDS = ("bsim-merge",)

    def __init__(self, config: Mapping[str, Any] | None = None, *, partition: str = "") -> None:
        self.config = dict(config or {})
        self.partition = partition

    def _missing(self) -> list[str]:
        return [key for key in ("cluster_url", "template_id", "commit_verb") if not self.config.get(key)]

    def apply(self, records: Iterable[Record], objects: ObjectStore) -> int:
        missing = self._missing()
        raise NotConfigured(
            "similarity index applier is declared, not wired: "
            + (f"missing config {missing}; " if missing else "")
            + "the commit verb (catalog.py:418) is not reachable from the grid in this checkout yet (U141)"
        )

    def position(self) -> Mapping[str, int]:
        return {self.partition: 0} if self.partition else {}

    @classmethod
    def describe(cls) -> dict[str, Any]:
        return {
            "applier": cls.name,
            "status": "declared",
            "config_schema": dict(cls.CONFIG_SCHEMA),
            "kinds": list(cls.KINDS),
            "keyed_by": ["merged_xml_sha256", "cluster_url"],
            "not_configured": "commit verb unreachable from the grid side until U141",
        }


APPLIERS.register(SimilarityIndexApplier.name, SimilarityIndexApplier)

__all__ = ["SimilarityIndexApplier"]
