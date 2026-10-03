"""Count-reconciliation gate (R49/KTD8): fail closed before publishing.

Classifies every function address in one binary's `func` inventory into exactly
one of the five exhaustive-accounting buckets (accepted source, candidate
source, preserved region, unclassified, excluded-with-reason), then hands the
assignment to `report_accounting.reconcile_inventory` so the shared exhaustive
rules (unique membership, named exclusion reasons, byte-extent unions) apply
here the same way they apply to the objdiff report. This module only decides
*which* bucket each member belongs to; it never invents a missing count.

A `recovered_function` row only counts toward `accepted_source` once it carries
an address that the `func` inventory can place and a witnessed target export
name (`semantic_identity.recorded_export_name`). A name-only recovered-source
row with no address cannot be placed in an address-keyed inventory; it is
surfaced separately as evidence outside the reconciled count rather than
silently folded into any bucket.
"""

from __future__ import annotations

from .report_accounting import reconcile_inventory
from .semantic_identity import recorded_export_name


def _recovered_by_addr(con, binary_id: int) -> dict:
    columns = {row[1] for row in con.execute("PRAGMA table_info(recovered_function)")}
    optional = ("target_sha256", "semantic_status", "semantic_reason", "semantic_evidence")
    extra = ", ".join(col if col in columns else f"NULL AS {col}" for col in optional)
    rows = con.execute(
        "SELECT addr, name, real_c, logical_id, path, evidence, binary_id, " + extra +
        " FROM recovered_function WHERE binary_id = ? AND addr IS NOT NULL",
        (binary_id,),
    ).fetchall()
    return {row["addr"]: dict(row) for row in rows}


def classify_member(func_row: dict, recovered_row: dict | None) -> tuple[str, str | None]:
    """Return (bucket, reason) for one `func` row; reason is required only for exclusion."""
    if func_row.get("is_thunk"):
        return "excluded_with_reason", "thunk"
    if (func_row.get("source") or "") == "IMPORTED":
        return "excluded_with_reason", "imported_external"
    if recovered_row is not None:
        if recovered_row.get("real_c") and recorded_export_name(recovered_row) is not None:
            return "accepted_source", None
        return "candidate_source", None
    if func_row.get("source") == "USER_DEFINED" or func_row.get("canon_class") is not None or func_row.get("n_instr") is not None:
        return "preserved_region", None
    return "unclassified", None


def build_assignments(con, binary_id: int) -> tuple[list, list[dict]]:
    recovered = _recovered_by_addr(con, binary_id)
    func_rows = con.execute(
        "SELECT addr, size, is_thunk, source, canon_class, n_instr FROM func WHERE binary_id = ?",
        (binary_id,),
    ).fetchall()
    inventory: list = []
    assignments: list[dict] = []
    for row in func_rows:
        member = row["addr"]
        inventory.append(member)
        bucket, reason = classify_member(dict(row), recovered.get(row["addr"]))
        size = row["size"]
        extent = (member, member + size) if isinstance(size, int) and size > 0 else None
        entry = {"member": member, "bucket": bucket, "extent": extent}
        if reason:
            entry["reason"] = reason
        assignments.append(entry)
    return inventory, assignments


def run_gate(con, binary_id: int) -> dict:
    """Run the count-reconciliation gate for one binary's function inventory (R49)."""
    inventory, assignments = build_assignments(con, binary_id)
    result = reconcile_inventory(inventory, assignments)
    result["binary_id"] = binary_id
    result["recovered_function_rows_outside_inventory"] = con.execute(
        "SELECT COUNT(*) FROM recovered_function WHERE binary_id = ? AND addr IS NULL",
        (binary_id,),
    ).fetchone()[0]
    return result


def gate_blocks_publish(gate_result: dict) -> bool:
    """AE15: a failing gate blocks the publish action entirely; it is not a warning."""
    return gate_result.get("status") != "passed"


def run_gate_for_all_binaries(con) -> dict:
    """Run the gate once per binary present in the store; empty store yields {}."""
    has_binary = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='binary'"
    ).fetchone()
    if not has_binary:
        return {}
    binary_ids = [row[0] for row in con.execute("SELECT id FROM binary ORDER BY id")]
    return {binary_id: run_gate(con, binary_id) for binary_id in binary_ids}
