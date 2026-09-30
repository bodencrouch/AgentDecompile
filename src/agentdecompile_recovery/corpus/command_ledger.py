"""Durable command intents for runtime actions after a lost connection (design section 8, U9 A12).

The intent is written before a command is sent. After a disconnect the coordinator asks the
observer, by command id, whether the effect happened. ``applied`` and ``not_applied`` reconcile
the command; anything else records ``outcome_unknown``. A non-idempotent command in ``sent`` or
``outcome_unknown`` blocks another send of the same action until it is reconciled, so there is
no automatic duplicate. Idempotent commands may be re-sent. Exactly-once is not promised for
an engine command whose effect cannot be observed.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Callable

IDEMPOTENT, NON_IDEMPOTENT = "idempotent", "non_idempotent"
OPEN = ("sent", "outcome_unknown")


class CommandLedger:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, command_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", command_id):
            raise ValueError("command_id")
        return self.root / f"{command_id}.json"

    def _save(self, row: dict) -> None:
        fd, tmp = tempfile.mkstemp(dir=self.root, prefix=".cmd.", suffix=".tmp")
        with os.fdopen(fd, "w") as handle:
            json.dump(row, handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, self._path(row["commandId"]))
        dfd = os.open(self.root, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)

    def get(self, command_id: str) -> dict | None:
        path = self._path(command_id)
        return json.loads(path.read_text()) if path.exists() else None

    def rows(self) -> list[dict]:
        return [json.loads(p.read_text()) for p in sorted(self.root.glob("*.json"))]

    def blocking(self, action: str) -> list[dict]:
        """Unreconciled non-idempotent commands for ``action``."""
        return [r for r in self.rows() if r["action"] == action
                and r["idempotency"] == NON_IDEMPOTENT and r["state"] in OPEN]

    def begin(self, command_id: str, action: str, idempotency: str) -> dict:
        """Record the intent before sending; refuse while the same action is unreconciled."""
        if idempotency not in (IDEMPOTENT, NON_IDEMPOTENT):
            raise ValueError("idempotency")
        if self.get(command_id) is not None:
            return {"send": False, "reason": "command id already used; ids are never reused"}
        if idempotency == NON_IDEMPOTENT:
            open_rows = self.blocking(action)
            if open_rows:
                return {"send": False, "reason": "an earlier command for this action is unreconciled",
                        "blockedBy": [r["commandId"] for r in open_rows], "nextAction": "reconcile"}
        self._save({"commandId": command_id, "action": action, "idempotency": idempotency,
                    "state": "sent", "sentAt": time.time()})
        return {"send": True}

    def complete(self, command_id: str, outcome: dict) -> None:
        row = self.get(command_id) or {}
        self._save({**row, "commandId": command_id, "state": "completed", "outcome": outcome})

    def after_disconnect(self, command_id: str, observe: Callable[[str], str | None]) -> dict:
        """Ask the observer what happened; never replay on doubt."""
        row = self.get(command_id)
        if row is None or row["state"] not in OPEN:
            return row or {}
        try:
            observed = observe(command_id)
        except Exception as exc:  # the observer is a fallible dependency
            observed, row["observerError"] = None, str(exc)
        if observed in ("applied", "not_applied"):
            row.update(state=f"reconciled_{observed}", reconciledBy="observer")
        else:
            row.update(state="outcome_unknown", nextAction="restore_or_reconcile_before_continuing")
        self._save(row)
        return row

    def reconcile(self, command_id: str, observed: str, by: str) -> dict:
        """Explicit reconciliation after restoring or inspecting the runtime."""
        if observed not in ("applied", "not_applied"):
            raise ValueError("observed")
        row = self.get(command_id)
        if row is None:
            raise KeyError(command_id)
        row.update(state=f"reconciled_{observed}", reconciledBy=by)
        self._save(row)
        return row
