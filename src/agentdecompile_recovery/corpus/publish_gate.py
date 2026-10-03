"""Explicit, separately approved publish step (R50/U29).

Publishing recovery statistics anywhere outside this repo is its own
operator-approved action; it never runs as a side effect of generating
`report.json` (U26) or of a passing count-reconciliation gate (U28) alone.

This module decides whether publish is *approvable* and records an operator's
approval. It never performs an outbound network call: decomp.dev's own
license is unestablished (see FRONTEND_INTENT.md's Scope Boundaries), so the
actual delivery is deferred follow-up work. A confirmed approval is always
labeled with `APPROVED_UNSENT_LABEL` -- it must never read as a completed
publish.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .count_reconciliation import gate_blocks_publish, run_gate_for_all_binaries

APPROVED_UNSENT_LABEL = "Approved. Publishing is not connected yet."


def default_approval_path(db_path: Path) -> Path:
    """Where an approval receipt for *db_path* lives absent an explicit override."""
    return Path(db_path).parent / "publish-approval.json"


def gate_summary(con) -> dict:
    """Run U28's gate for every binary in *con* and summarize the publish-blocking view.

    Per AE15/R49, a failing gate names the unreconciled bucket(s); this never
    invents a missing count and never softens a failure into a warning.
    """
    reconciliation = run_gate_for_all_binaries(con)
    blocked = {
        binary_id: gate for binary_id, gate in reconciliation.items()
        if gate_blocks_publish(gate)
    }
    return {
        "status": "blocked" if blocked else "open",
        "blockedBinaryIds": sorted(blocked),
        "blockedDetail": {
            str(binary_id): gate.get("errors", gate) for binary_id, gate in blocked.items()
        },
        "perBinary": reconciliation,
    }


def read_approval(approval_file: Path) -> dict | None:
    """Read a previously recorded approval receipt, if one exists and parses."""
    path = Path(approval_file)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def publish_status(con, approval_file: Path) -> dict:
    """Read-only: current gate state plus any recorded approval. Never sends anything."""
    gate = gate_summary(con)
    approval = read_approval(approval_file)
    if gate["status"] == "blocked":
        status = "blocked"
    elif approval is not None:
        status = "approved_unsent"
    else:
        status = "approvable"
    return {
        "ok": True,
        "status": status,
        "label": APPROVED_UNSENT_LABEL if status == "approved_unsent" else None,
        "gate": gate,
        "approval": approval,
    }


def approve_publish(con, approval_file: Path, *, confirm: bool, corpus_identity: str = "") -> dict:
    """Record an explicit operator approval once the gate passes.

    Refuses outright (no receipt written) when the gate is blocked or when the
    caller omitted the explicit confirmation -- mirroring the dashboard's
    existing dangerous-action confirm contract without duplicating it here.
    Never performs an outbound network call.
    """
    if not confirm:
        return {
            "ok": False,
            "error": "publish requires explicit operator confirmation; set confirm=true",
        }
    gate = gate_summary(con)
    if gate["status"] == "blocked":
        return {
            "ok": False,
            "error": "count-reconciliation gate is blocked; publish refused",
            "gate": gate,
        }
    record = {
        "status": "approved_unsent",
        "label": APPROVED_UNSENT_LABEL,
        "approvedAt": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        "corpusIdentity": corpus_identity,
        "gate": gate,
        "note": (
            "Operator approved publishing after a passing count-reconciliation "
            "gate. No outbound network call was made; decomp.dev delivery is "
            "deferred follow-up work."
        ),
    }
    path = Path(approval_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return {
        "ok": True,
        "status": "approved_unsent",
        "label": APPROVED_UNSENT_LABEL,
        "gate": gate,
        "approval": record,
    }
