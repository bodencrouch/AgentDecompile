"""Emit one run-results JSON covering every binary that has recovered_function rows.

Stored source classifications are context, not fresh compilation or comparison
receipts. This export never upgrades them to byte verification.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .count_reconciliation import gate_blocks_publish, run_gate_for_all_binaries
from .ingest_recovered import RECOVERED_FUNCTION_DDL, ensure_recovered_function  # noqa: F401
from .store import connect
from .semantic_identity import CLAIM_SCOPE, recorded_export_name


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(ts))


def match_source(logical_id: int | None, evidence: str | None) -> str:
    if (evidence or "").startswith("seed-validation-byte-exact:"):
        return "recorded-seed-evidence"
    if logical_id:
        return "recorded-source-with-advisory-logical-correlation"
    return "recorded-source"


def build(con) -> dict:
    ensure_recovered_function(con)
    columns = {row[1] for row in con.execute("PRAGMA table_info(recovered_function)")}
    extra = ", ".join(column if column in columns else f"NULL AS {column}" for column in
                      ("binary_id", "target_sha256", "semantic_status", "semantic_reason", "semantic_evidence"))
    rows = con.execute("SELECT program, name, addr, size, convention, real_c, logical_id, path, evidence, "
                       + extra + " FROM recovered_function ORDER BY program, addr").fetchall()

    now = time.time()
    results = []
    for row in rows:
        real_c = bool(row["real_c"])
        named = recorded_export_name(dict(row)) is not None
        identity_note = (f"Recorded ingestion-time {CLAIM_SCOPE}; target was not rechecked by this report."
                         if named else f"No accepted target export witness: {row['semantic_reason'] or 'historical_unverified'}.")
        if row["logical_id"] is not None:
            identity_note += f" Logical function {row['logical_id']} is advisory cross-build correlation."
        note = "Byte comparison was not performed by this report. Stored source classification does not establish byte identity."
        results.append(
            {
                "promptPath": f"{row['program']}/{row['name']}",
                "functionName": row["name"],
                "success": False,
                "real_c": real_c,
                "compiled": None,
                "byte_exact": None,
                "provenance": {"path": row["path"], "address": row["addr"], "evidence": row["evidence"], "logical_id": row["logical_id"], "logical_id_role": "advisory cross-build correlation", "claim": "stored source classification", "target_sha256": row["target_sha256"], "semantic_status": row["semantic_status"], "semantic_reason": row["semantic_reason"], "semantic_evidence": row["semantic_evidence"]},
                "totalDurationMs": 0,
                "matchSource": match_source(row["logical_id"], row["evidence"]),
                "setupPhase": {
                    "attemptNumber": 1,
                    "success": True,
                    "durationMs": 0,
                    "startTimestamp": None,
                    "pluginResults": [
                        {
                            "pluginId": "get-context",
                            "pluginName": "Get Context",
                            "status": "success",
                            "durationMs": 0,
                            "output": f"source: {row['program']}",
                            "sections": [],
                        }
                    ],
                },
                "attempts": [
                    {
                        "attemptNumber": 1,
                        "success": False,
                        "durationMs": 0,
                        "startTimestamp": None,
                        "pluginResults": [
                            {
                                "pluginId": "byte-compare",
                                "pluginName": "Byte Compare",
                                "status": "skipped",
                                "durationMs": 0,
                                "output": note,
                                "sections": [],
                            },
                            {
                                "pluginId": "real-c-check",
                                "pluginName": "Real C Check",
                                "status": "skipped",
                                "durationMs": 0,
                                "output": ("recorded as assembly-free; source was not rechecked by this report" if real_c else "not recorded as assembly-free source"),
                                "sections": [],
                            },
                        ],
                    }
                ],
                "postMatchPhase": {
                    "attemptNumber": 1,
                    "success": True,
                    "durationMs": 0,
                    "startTimestamp": None,
                    "pluginResults": [
                        {
                            "pluginId": "identity",
                            "pluginName": "Recorded Target PE Export Identity",
                            "status": "success" if named else "skipped",
                            "durationMs": 0,
                            "output": identity_note,
                            "sections": [],
                        }
                    ],
                },
            }
        )

    n = len(results)
    n_real = sum(1 for r in results if r["real_c"])
    per_binary: dict[str, dict] = {}
    for row in con.execute("SELECT program, COUNT(*) n, SUM(real_c) real FROM recovered_function GROUP BY program"):
        per_binary[row["program"]] = {"functions": row["n"], "real_c": row["real"] or 0}

    # R49/KTD8: the count-reconciliation gate runs before any publish action (U29)
    # is enabled. A failing gate blocks publishing entirely; it never just warns.
    reconciliation = run_gate_for_all_binaries(con)
    blocked_binaries = [binary_id for binary_id, gate in reconciliation.items() if gate_blocks_publish(gate)]

    return {
        "version": 1,
        "timestamp": _iso(now),
        "config": {
            "promptsDir": "recovered_function",
            "maxRetries": 1,
            "stallThreshold": 1,
            "ttftTimeoutMs": 0,
            "compilerScript": "era-exact compiler per binary",
            "getContextScript": "n/a — aggregated report, not a live pipeline run",
            "target": "unknown",
            "model": "aggregated-corpus-record",
        },
        "results": results,
        "summary": {
            "totalPrompts": n,
            "successfulPrompts": 0,
            "successRate": None,
            "recordedRealC": n_real,
            "verifiedInThisReport": 0,
            "byteExact": None,
            "avgAttempts": 0,
            "totalDurationMs": 0,
            "note": (f"{n} stored source records across {len(per_binary)} binaries. {n_real} are classified as real C. This export did not compile source or compare bytes; historical evidence is retained without promoting its claims."),
            "perBinary": per_binary,
        },
        "countReconciliation": {
            "perBinary": reconciliation,
            "publishGate": "blocked" if blocked_binaries else "open",
            "blockedBinaryIds": blocked_binaries,
            "note": ("R49/AE15: exhaustive-accounting gate over each binary's func inventory. "
                     "A blocked gate names the unreconciled bucket(s) and member count per binary "
                     "under perBinary[<binary_id>].errors; it never invents a missing count."),
        },
    }


def write_report(store_path: Path | str, dest: Path | str) -> dict:
    """Build the report from *store_path* and write it to *dest* (both required)."""
    con = connect(store_path)
    try:
        dump = build(con)
    finally:
        con.close()
    path = Path(dest)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dump), encoding="utf-8")
    dump["out"] = str(path)
    return dump
