"""Read-only matching-method availability from recorded evidence.

A method being installed, eligible or configured is not a recorded execution.
This module performs no extraction, scheduling, migration or provider probes.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

METHODS = {
    "I": "Authentic symbols", "H": "Byte and instruction hashes", "X": "References and C++ metadata",
    "G": "Call graph and structure", "K": "P-code and decompiler skeleton",
    "S": "BSim", "T": "ABI evidence", "M": "BinDiff / BinExport", "D": "Emulation",
    "AI": "Optional AI / embeddings", "contract": "Calling-contract veto",
}
OPTIONAL = {"K": "pcode", "S": "bsim", "M": "binexport", "D": "emulate", "AI": "embeddings", "contract": "contract_veto"}
NOT_BUILT = {"no_pairwise_bindiff_adapter", "no_embedding_evidence_store"}


def _object(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value or "{}")
    except (ValueError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def project_channels(evidence: Mapping[str, Any] | str | None) -> list[dict]:
    """Project one row without converting availability into a success claim."""
    ev = _object(evidence)
    cascade = _object(ev.get("cascade_receipt"))
    optional = _object(cascade.get("optional_channels"))
    observed = set()
    for value in (ev.get("primary_channel"), ev.get("channel")):
        if isinstance(value, str) and value in METHODS:
            observed.add(value)
    if isinstance(ev.get("channels"), list):
        observed.update(value for value in ev["channels"] if isinstance(value, str) and value in METHODS)
    # Old rows may identify the algorithm only by their typed evidence field.
    for key, channel in (("bsim", "S"), ("pcode_fingerprint", "K"), ("abi", "T")):
        if isinstance(ev.get(key), (int, float)) and ev[key] > 0:
            observed.add(channel)
    rows = []
    for channel, label in METHODS.items():
        receipt = _object(optional.get(OPTIONAL.get(channel, "")))
        reason = str(receipt.get("reason") or "no_method_execution_receipt")
        row = {"channel": channel, "label": label, "state": "unavailable", "reason": reason}
        if channel in observed:
            row.update(state="ran", reason="recorded_match_evidence")
        elif reason in NOT_BUILT:
            row.update(state="not-built")
        elif receipt.get("state") == "unavailable" or receipt.get("available") is False:
            row.update(state="unavailable")
        elif receipt.get("skipped"):
            row.update(state="skipped")
        elif receipt.get("available") is True:
            row.update(state="skipped", availability="available", reason="available_without_execution_receipt")
        if channel == "S" and receipt.get("ok") is True and channel not in observed:
            row.update(state="skipped", availability="available",
                       reason="pair_query_recorded_without_function_evidence", pairReason=reason)
        if channel == "contract" and receipt:
            enabled = receipt.get("enabled") is True
            provider = _object(receipt.get("provider"))
            row.update(enabled=enabled, shadowEvaluated=int(receipt.get("evaluated") or 0),
                       changedDecisions=int(receipt.get("changed_decisions") or 0))
            if not enabled:
                row.update(state="skipped", reason="operator_disabled", availability="available")
            elif _object(ev.get("contract_shadow")):
                row.update(state="ran", reason="recorded_contract_evaluation")
            elif receipt.get("evaluated", 0):
                row.update(state="skipped", reason="pair_shadow_has_no_function_receipt")
            if provider.get("state") == "unavailable":
                row["providerReason"] = provider.get("reason")
        if channel == "X":
            metadata = _object(optional.get("cpp_metadata"))
            if metadata:
                row["metadata"] = metadata
        rows.append(row)
    return rows


def availability_for_matches(con, match_ids: list[int]) -> dict:
    """Project up to 50 exact match IDs from the already-selected database."""
    if len(match_ids) > 50 or any(type(value) is not int or value <= 0 for value in match_ids):
        raise ValueError("match_ids must contain at most 50 positive integers")
    ids = sorted(set(match_ids))
    if not ids:
        return {"rows": [], "missingMatchIds": []}
    placeholders = ",".join("?" for _ in ids)
    rows = con.execute(
        f"SELECT id,src_binary,dst_binary,src_addr,run,evidence FROM match WHERE id IN ({placeholders}) ORDER BY id", ids,
    ).fetchall()
    results = [{"matchId": row[0], "srcBinary": row[1], "dstBinary": row[2], "srcAddr": row[3],
                "run": row[4], "channels": project_channels(row[5])} for row in rows]
    present = {row["matchId"] for row in results}
    return {"rows": results, "missingMatchIds": [key for key in ids if key not in present]}


def pair_availability(con, src_id: int, dst_id: int, *, src_addr: int | None = None,
                      run: str | None = None, schedule: Mapping | None = None) -> dict:
    """Inspect a pair/function; absent rows never imply a scheduler decision.

    ``schedule`` must be a caller-supplied persisted receipt with selected,
    reason and (optionally) the immutable scheduling basis. This function
    deliberately does not reconstruct past scheduling from today's corpus.
    """
    params: list = [src_id, dst_id]
    clauses = ["src_binary=?", "dst_binary=?"]
    if src_addr is not None:
        clauses.append("src_addr=?")
        params.append(src_addr)
    if run is not None:
        clauses.append("run=?")
        params.append(run)
    records = con.execute("SELECT id,run,evidence FROM match WHERE " + " AND ".join(clauses) + " ORDER BY id", params)
    channels: dict[str, list[dict]] = {key: [] for key in METHODS}
    runs, count = set(), 0
    for row in records:
        count += 1
        runs.add(row[1])
        for method in project_channels(row[2]):
            channels[method["channel"]].append(method)
    result = {"srcBinary": src_id, "dstBinary": dst_id, "srcAddr": src_addr,
              "run": run, "recordedRuns": sorted(runs, key=lambda x: str(x)), "matchRows": count,
              "state": "ran" if count else "unavailable",
              "reason": "recorded_match_rows" if count else "no_recorded_match_run"}
    if schedule is not None:
        result["schedule"] = dict(schedule)
        if not count and schedule.get("selected") is False:
            result.update(state="not-scheduled", reason=str(schedule.get("reason") or "pair_not_selected"))
    result["channels"] = []
    for channel, observations in channels.items():
        if not observations:
            method = {"channel": channel, "label": METHODS[channel], "state": "unavailable", "reason": "no_method_execution_receipt"}
        else:
            # Preserve mixed reasons across rows; never turn an old receipt
            # into a claim that every function or every run used the method.
            rank = {"ran": 0, "skipped": 1, "unavailable": 2, "not-built": 3}
            method = dict(min(observations, key=lambda item: rank[item["state"]]))
            method["observations"] = sorted({(item["state"], item["reason"]) for item in observations})
            method["scope"] = "at_least_one_recorded_match"
        result["channels"].append(method)
    return result
