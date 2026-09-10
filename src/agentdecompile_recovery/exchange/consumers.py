"""Deliver donated rewrites to trusted local requests, preserving the proof gate."""

from __future__ import annotations

import asyncio
import hashlib
import heapq
import json
import logging
import os

from pathlib import Path

from .producers import ACCEPTED_DIRNAME, MAX_DRAIN_PER_CALL, SPOOL_DIRNAME
from .store import STATUS_AWAITING_VERIFICATION, ExchangeStore, derive_unit_id

logger = logging.getLogger(__name__)


def _route_batch(directory: Path, after: str, limit: int) -> list[Path]:
    # Bound memory and queue writes; all directory I/O runs off the event loop.
    # The cursor rotates past busy/pending destinations so they cannot starve
    # later records. Restarting the cursor is safe because delivery is idempotent.
    with os.scandir(directory) as entries:
        return heapq.nsmallest(
            limit,
            (Path(entry.path) for entry in entries if entry.name > after and entry.name.endswith(".json") and entry.is_file()),
        )


class RewriteConsumer:
    """One maintenance consumer per server store; never trusts submitted paths."""

    def __init__(self, store: ExchangeStore):
        self.store = store
        self._after = ""
        self._lock = asyncio.Lock()

    async def drain(self, *, limit: int = MAX_DRAIN_PER_CALL) -> int:
        if limit <= 0 or self._lock.locked():
            return 0
        async with self._lock:
            directory = self.store.state_path.parent / SPOOL_DIRNAME / ACCEPTED_DIRNAME
            try:
                paths = await asyncio.to_thread(_route_batch, directory, self._after, limit)
                if not paths and self._after:
                    paths = await asyncio.to_thread(_route_batch, directory, "", limit)
                self._after = paths[-1].name if paths else ""
            except FileNotFoundError:
                return 0
            except OSError:
                logger.warning("exchange: could not read rewrite routes", exc_info=True)
                return 0
            forwarded = 0
            for path in paths:
                try:
                    forwarded += await self._forward(path)
                except (OSError, ValueError, TypeError, ImportError):
                    logger.warning("exchange: rewrite transfer deferred for %s", path.name, exc_info=True)
            return forwarded

    async def _forward(self, path: Path) -> int:
        # Only producer-controlled accepted records select filesystem targets.
        record = json.loads(await asyncio.to_thread(path.read_text, encoding="utf-8"))
        if not isinstance(record, dict) or record.get("lane") != "rewrite":
            return 0
        payload, routing = record.get("payload"), record.get("routing")
        if not isinstance(payload, dict) or not isinstance(routing, dict):
            return 0
        work_dir, request_id = routing.get("workDir"), routing.get("requestId")
        function_name, candidate = payload.get("functionName"), payload.get("candidateSource")
        if not all(isinstance(value, str) and value for value in (work_dir, request_id, function_name, candidate)):
            return 0
        if not Path(work_dir).is_absolute():
            return 0
        from ..rewrite_queue import STATUS_PENDING, derive_request_id, find_entry, import_exchange_result

        if request_id != derive_request_id(function_name, candidate):
            return 0
        unit_id = derive_unit_id("rewrite", payload)
        if record.get("unitId") != unit_id:
            return 0
        unit = await self.store.unit_state(unit_id)
        if unit is None or unit["status"] != STATUS_AWAITING_VERIFICATION or unit["payload"] != payload:
            return 0
        submission = unit.get("submission")
        if not isinstance(submission, dict):
            return 0
        artifact = submission.get("artifact")
        source = artifact.get("source") if isinstance(artifact, dict) else None
        if not isinstance(source, str) or not source.strip() or "\x00" in source or len(source.encode("utf-8")) > 64 * 1024:
            return 0
        fingerprint = submission.get("fingerprint")
        if not isinstance(fingerprint, str) or not fingerprint:
            return 0
        destination = hashlib.sha256(json.dumps({"workDir": work_dir, "requestId": request_id}, sort_keys=True).encode()).hexdigest()
        if destination in submission.get("forwarded", {}):
            # A restored/recreated queue may have lost an earlier delivery.
            # Retry only a pending request; consumed or locally claimed work
            # must remain untouched. The locked import rechecks its payload.
            entry = await asyncio.to_thread(find_entry, Path(work_dir), request_id)
            if entry is None or entry.get("status") != STATUS_PENDING:
                return 0
        receipt = f"{unit_id}:{fingerprint}:{destination}"
        transferred = await asyncio.to_thread(
            import_exchange_result, Path(work_dir), request_id, payload=payload, source=source, receipt=receipt
        )
        if not transferred:
            return 0
        return int(await self.store.acknowledge_forwarded(unit_id, fingerprint=fingerprint, destination=destination))
