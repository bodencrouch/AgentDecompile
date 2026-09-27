"""Read external diagnostic reports without granting recovery acceptance.

Schemas follow the pinned upstream reccmp report serializer and ReAgent benchmark
command. Raw report identity is recorded; a standalone file cannot establish which
binary, candidate, invocation or provider produced it. The eventual execution
adapter must bind those separately before any independent acceptance decision.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

MAX_REPORT_BYTES = 16 * 1024 * 1024
SCHEMA_BASELINES = {
    "reagent-benchmark": "d12cea338c61898b06a86fe8adb25275fa9d5615",
    "reccmp-compare": "e91a51bfadfbb600adfdc750589ac40ae9742883",
}


class InvalidReport(ValueError):
    pass


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidReport(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _integer(value, name):
    if type(value) is not int or value < 0:
        raise InvalidReport(f"{name} must be a nonnegative integer")
    return value


def _number(value, name):
    try:
        valid = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise InvalidReport(f"{name} must be finite numeric data")
    return value


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise InvalidReport(f"{name} must be nonempty text")
    return value


def _benchmark(data):
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise InvalidReport("unsupported ReAgent benchmark schema_version")
    rows = data.get("results")
    if not isinstance(rows, list) or not rows:
        raise InvalidReport("benchmark results must be nonempty")
    if _integer(data.get("total"), "total") != len(rows):
        raise InvalidReport("benchmark total does not match results")
    checks = []
    expectations = 0
    for row in rows:
        if not isinstance(row, dict):
            raise InvalidReport("benchmark result must be an object")
        name = _text(row.get("name"), "name")
        for key in ("matched", "expected_match"):
            if type(row.get(key)) is not bool:
                raise InvalidReport(f"{key} must be a boolean")
        cases = _integer(row.get("cases_run"), "cases_run")
        duration = _number(row.get("duration_s"), "duration_s")
        if duration < 0:
            raise InvalidReport("duration_s must be nonnegative")
        findings = row.get("findings")
        if not isinstance(findings, list) or any(not isinstance(x, str) for x in findings):
            raise InvalidReport("findings must be a list of strings")
        expected = row["matched"] == row["expected_match"]
        expectations += expected
        checks.append({"kind": "differential-output", "name": name,
                       "outcome": ("matched" if row["matched"] else "mismatched") if cases else "unknown",
                       "scope": "reported harness cases only", "cases_run": cases,
                       "expected_match": row["expected_match"], "expectation_met": expected,
                       "findings": findings, "duration_s": duration})
    if _integer(data.get("expectations_met"), "expectations_met") != expectations:
        raise InvalidReport("expectations_met contradicts individual results")
    return checks, {"reported_cases": sum(x["cases_run"] for x in checks),
                    "expectations_met": expectations, "total": len(rows),
                    "eligible_case_denominator": "unknown; original fixture and manifest are not bound"}


def _reccmp(data):
    if type(data.get("format")) is not int or data["format"] != 1:
        raise InvalidReport("unsupported reccmp report format")
    _text(data.get("file"), "file")
    _number(data.get("timestamp"), "timestamp")
    rows = data.get("data")
    if not isinstance(rows, list) or not rows:
        raise InvalidReport("comparison data must be nonempty; empty is not zero mismatches")
    checks = []
    for row in rows:
        if not isinstance(row, dict):
            raise InvalidReport("comparison row must be an object")
        address = _text(row.get("address"), "address")
        name = _text(row.get("name"), "name")
        matching = _number(row.get("matching"), "matching")
        if not 0 <= matching <= 1:
            raise InvalidReport("matching must be in [0, 1]")
        checks.append({"kind": "reccmp-comparison-score", "address": address,
                       "name": name, "matching": matching, "outcome": "observed",
                       "scope": "provider comparison; not whole-image equality",
                       "provider_details": {key: row[key] for key in
                           ("recomp", "stub", "library", "effective", "diff", "type") if key in row}})
    coverage = {"reported_rows": len(rows), "eligible_denominator": "unknown",
                "omitted_entities": "unmatched entities may be absent from this format"}
    if "function_count" in data:
        coverage["provider_function_count"] = _integer(data["function_count"], "function_count")
    return checks, coverage


def normalize_report(raw: bytes, provider: str) -> dict:
    if provider not in SCHEMA_BASELINES:
        raise InvalidReport("unsupported report provider")
    if not raw or len(raw) > MAX_REPORT_BYTES:
        raise InvalidReport("report is empty or exceeds the bounded report size")
    try:
        data = json.loads(raw, object_pairs_hook=_object,
                          parse_float=lambda value: _number(float(value), "JSON number"),
                          parse_constant=lambda value: (_ for _ in ()).throw(InvalidReport(f"invalid JSON constant: {value}")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise InvalidReport(str(exc)) from exc
    if not isinstance(data, dict):
        raise InvalidReport("report root must be an object")
    checks, coverage = _benchmark(data) if provider == "reagent-benchmark" else _reccmp(data)
    return {"schema": "agentdecompile.external-validation/v1", "provider": provider,
            "adapter_schema_baseline": SCHEMA_BASELINES[provider],
            "provider_revision": None, "report_state": "normalized",
            "execution_state": "unknown", "raw_report_sha256": hashlib.sha256(raw).hexdigest(),
            "raw_report_bytes": len(raw), "proposal_only": True, "recovery_accepted": False,
            "provenance_verified": False, "checks": checks, "coverage": coverage,
            "gaps": ["invocation and actual provider revision not established by a standalone report",
                     "original/candidate/PDB/source identities and report freshness require execution-adapter evidence",
                     "independent acceptance and required binary/runtime checks remain outstanding"]}


def read_report(path: Path, provider: str) -> dict:
    with path.open("rb") as stream:
        raw = stream.read(MAX_REPORT_BYTES + 1)
    return normalize_report(raw, provider)
