"""Detector classification and bounded routing canaries (failure-prevention design, sections 2 and 4).

FP-23: detection is a fallible dependency. A detector timeout, stale reading, unknown schema
or malformed response is ``detector_unknown``, never healthy or failed by inference. It
quarantines only the decision paths that need that detector's evidence; an alternate
qualified adapter or unrelated work continues. The raw result is kept unclassified.

FP-30: a routing change runs as a preauthorized bounded canary. Its baseline, limits and
abort thresholds are fixed before activation. Crossing a threshold, or losing the metrics,
restores the baseline route and closes the canary with every observation retained. A canary
never touches acceptance: a faster route must still earn the same independent claims.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

HEALTHY, FAILED, UNKNOWN = "healthy", "failed", "detector_unknown"


@dataclass(frozen=True)
class DetectorSpec:
    detector_id: str
    schema_version: int
    freshness_s: float
    outcomes: frozenset = frozenset({HEALTHY, FAILED})


def classify(spec: DetectorSpec, result: Any, *, now: float | None = None) -> dict:
    """Return ``{"detector_id", "detector_health", "raw", "reason"}``; unknown on any doubt."""
    now = time.time() if now is None else now
    verdict = {"detector_id": spec.detector_id, "raw": result}
    if not isinstance(result, Mapping):
        return {**verdict, "detector_health": UNKNOWN, "reason": "malformed_result"}
    if result.get("timed_out"):
        return {**verdict, "detector_health": UNKNOWN, "reason": "detector_timeout"}
    if result.get("schema_version") != spec.schema_version:
        return {**verdict, "detector_health": UNKNOWN, "reason": "unknown_schema_version"}
    observed = result.get("observed_at")
    if not isinstance(observed, (int, float)) or not math.isfinite(observed) or now - observed > spec.freshness_s \
            or observed > now + 1:
        return {**verdict, "detector_health": UNKNOWN, "reason": "stale_or_unordered_reading"}
    outcome = result.get("outcome")
    if outcome not in spec.outcomes:
        return {**verdict, "detector_health": UNKNOWN, "reason": "unrecognised_outcome"}
    return {**verdict, "detector_health": outcome, "reason": "classified"}


@dataclass
class DecisionGate:
    """Which decisions may proceed, given the latest classification per detector."""
    requires: Mapping[str, tuple[str, ...]]            # decision -> detector ids whose evidence it needs
    alternates: Mapping[str, tuple[str, ...]] = field(default_factory=dict)  # detector -> qualified alternates
    latest: dict[str, dict] = field(default_factory=dict)

    def observe(self, classified: dict) -> None:
        self.latest[classified["detector_id"]] = classified

    def _usable(self, detector: str) -> str | None:
        for candidate in (detector, *self.alternates.get(detector, ())):
            if self.latest.get(candidate, {}).get("detector_health") in (HEALTHY, FAILED):
                return candidate
        return None

    def decide(self, decision: str) -> dict:
        blocked = [d for d in self.requires.get(decision, ()) if self._usable(d) is None]
        if blocked:
            return {"decision": decision, "allowed": False, "state": "quarantined",
                    "reason": "detector evidence unknown: " + ", ".join(blocked)}
        used = {d: self._usable(d) for d in self.requires.get(decision, ())}
        failed = [d for d, u in used.items() if self.latest[u]["detector_health"] == FAILED]
        return {"decision": decision, "allowed": True, "evidence": used, "detectorFailures": failed}


@dataclass
class RoutingCanary:
    """A preauthorized, bounded canary for one routing change."""
    baseline: str
    candidate: str
    max_attempts: int
    max_duration_s: float
    max_cost: float
    max_error_rate: float
    started_at: float = field(default_factory=time.time)
    observations: list[dict] = field(default_factory=list)
    state: str = "active"            # active | rolled_back | completed
    closed_reason: str = ""

    def route(self) -> str:
        return self.candidate if self.state == "active" else self.baseline

    def observe(self, *, ok: bool | None, cost: float | None, now: float | None = None) -> str:
        """Record one canary attempt; ``ok``/``cost`` None means the metric is unavailable."""
        now = time.time() if now is None else now
        if self.state != "active":
            return self.route()
        self.observations.append({"ok": ok, "cost": cost, "at": now})
        if ok is None or cost is None:
            return self._close("rolled_back", "metrics unavailable: expansion stopped, baseline restored")
        errors = sum(1 for o in self.observations if o["ok"] is False)
        spent = sum(o["cost"] for o in self.observations)
        if spent > self.max_cost:
            return self._close("rolled_back", f"cost {spent:g} exceeded {self.max_cost:g}")
        if now - self.started_at > self.max_duration_s:
            return self._close("rolled_back", f"duration exceeded {self.max_duration_s:g}s")
        if errors / len(self.observations) > self.max_error_rate:
            return self._close("rolled_back", f"error rate {errors}/{len(self.observations)} exceeded")
        if len(self.observations) >= self.max_attempts:
            return self._close("completed", "attempt budget reached within thresholds; no improvement claimed")
        return self.route()

    def _close(self, state: str, reason: str) -> str:
        self.state, self.closed_reason = state, reason
        return self.route()
