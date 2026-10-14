"""Per-check verification outcomes for one function, each in its own scope (U1 RC-05, D09).

Each check writes only the scope it observed. A compile success, a ReAgent "GREEN" benchmark
or a byte match never sets any other scope: arithmetic, FP/NaN, methods, globals, indirect
calls and exception metadata stay ``unknown`` until a check of that kind reports. Outcomes
are retained as recorded, including failures and unknowns; a later report for the same scope
is appended, never merged into a different one.
"""
from __future__ import annotations

from typing import Any, Mapping

SCOPES = ("compile", "byte_equality", "differential_output", "arithmetic", "fp_nan",
          "methods", "globals", "indirect_calls", "exception_metadata")
OUTCOMES = frozenset({"passed", "failed", "unknown", "unsupported"})


class FactSheet:
    def __init__(self, function_key: str) -> None:
        self.function_key = function_key
        self.history: dict[str, list[dict[str, Any]]] = {scope: [] for scope in SCOPES}

    def record(self, scope: str, outcome: str, *, source: str, detail: Mapping[str, Any] | None = None) -> None:
        if scope not in SCOPES:
            raise ValueError(f"unknown verification scope: {scope}")
        if outcome not in OUTCOMES:
            raise ValueError(f"unknown outcome: {outcome}")
        self.history[scope].append({"outcome": outcome, "source": source, "detail": dict(detail or {})})

    def outcome(self, scope: str) -> str:
        rows = self.history[scope]
        return rows[-1]["outcome"] if rows else "unknown"

    def summary(self) -> dict[str, Any]:
        return {"function": self.function_key, "scopes": {s: self.outcome(s) for s in SCOPES},
                "promotion": "none: each scope reflects only checks of that kind"}

    # Adapters for the producers that exist today.
    def ingest_compile(self, result: Mapping[str, Any]) -> None:
        self.record("compile", "passed" if result.get("ok") else "failed", source="compiler",
                    detail={"returncode": result.get("returncode")})

    def ingest_reagent(self, normalized: Mapping[str, Any]) -> None:
        """A normalized ReAgent benchmark (external_validation) sets differential output only."""
        for check in normalized.get("checks") or []:
            if check.get("kind") != "differential-output":
                continue
            outcome = {"matched": "passed", "mismatched": "failed"}.get(check.get("outcome"), "unknown")
            self.record("differential_output", outcome, source="reagent-benchmark",
                        detail={"name": check.get("name"), "cases_run": check.get("cases_run"),
                                "scope": check.get("scope")})
