"""Publish recovery work units into the exchange from the pipeline.

Producers cannot share :class:`~.store.ExchangeStore`'s snapshot. Pipeline
stages run as *subprocesses* -- ``actions/jobs.py`` builds an argv and Popens it
-- while the store is single-process by design: ``_load`` reads the snapshot
once (``if self._loaded: return``) and every mutation writes a whole snapshot
back. A second process holding its own store would load a stale copy and then
overwrite the server's live state wholesale, losing every lease and receipt
written since it started.

So a producer never opens the snapshot. It appends to a spool directory, one
file per unit and destination, and the server drains it in-process. Spooling is
also what makes a producer safe to call from anywhere: the recovery pipeline
must not fail because a contributor-facing feature is misconfigured, so every
error here is swallowed after being logged.

A spool file separates two things the store deliberately keeps apart:

``payload``
    The portable work unit. ``assert_portable_payload`` rejects absolute paths,
    so this carries no ``work_dir`` and no db handle -- only values a stranger
    can act on.
``routing``
    Machine-local addressing the coordinator needs to apply an accepted result
    (which work dir, which rewrite-queue request). This never reaches a
    contributor; it stays on disk beside the coordinator.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import secrets

from itertools import islice
from pathlib import Path
from typing import Any

from .store import ExchangeStore, default_state_path, derive_unit_id

logger = logging.getLogger(__name__)

SPOOL_DIRNAME = "exchange-spool"
ACCEPTED_DIRNAME = "accepted"

#: Bound on a single drain so a large spool cannot stall a claim request.
MAX_DRAIN_PER_CALL = 64


def exchange_enabled() -> bool:
    """Whether producers should publish at all.

    Same switch as the proxy's ``--enable-exchange``: when the exchange is off,
    producing units is pure overhead, so the pipeline pays nothing.
    """

    return os.environ.get("AGENT_DECOMPILE_EXCHANGE_ENABLED", "").strip().lower() in ("true", "1", "yes", "on")


def spool_dir() -> Path:
    """Spool location, derived from the same setting as the snapshot.

    Producer and server agree only when they resolve ``default_state_path()``
    identically. ``AGENTDECOMPILE_EXCHANGE_STATE`` makes that explicit; without
    it the fallback is cwd-relative, and a job subprocess runs with
    ``cwd = live_root()`` which need not match the server's cwd. Operators
    enabling the exchange should set that variable.
    """

    return default_state_path().parent / SPOOL_DIRNAME


def _spool_filename(unit_id: str, routing: dict[str, str]) -> str:
    """Keep destinations distinct without changing portable work identity."""

    destination = hashlib.sha256(json.dumps(routing, sort_keys=True).encode("utf-8")).hexdigest()
    # Unit ids contain ``:``; that is not a legal filename on Windows.
    return f"{unit_id.replace(':', '-')}-{destination}.json"


def offer_rewrite_unit(
    *,
    work_dir: Path | str,
    request_id: str,
    function_name: str,
    entry: str,
    candidate_source: str,
    mismatch_class: str | None = None,
    mismatch_histogram: dict[str, int] | None = None,
    aligned_diff: list[dict[str, Any]] | None = None,
    compiler_profile: str | None = None,
) -> str | None:
    """Spool one `rewrite` unit. Returns its id, or None when nothing was written.

    Mirrors the fields ``rewrite_queue.write_rewrite_request`` already persists,
    because that entry is the thing a contributor acts on: an alternate spelling
    of ``candidate_source`` guided by ``aligned_diff``. Returning None is
    ordinary -- the exchange being disabled is the common case.
    """

    if not exchange_enabled():
        return None
    if not function_name or not candidate_source:
        return None

    # A live queue entry once held the string "{'REPLACEMENT': 2}" -- Python
    # repr that had been stringified upstream. coerce_histogram is what the
    # rewrite queue uses to absorb that, and dict() on such a value raises.
    from ..rewrite_queue import coerce_histogram

    payload: dict[str, Any] = {
        "functionName": function_name,
        "entry": entry,
        "candidateSource": candidate_source,
        "mismatchClass": str(mismatch_class) if mismatch_class else None,
        "mismatchHistogram": coerce_histogram(mismatch_histogram),
        "alignedDiff": list(aligned_diff or []),
        "compilerProfile": compiler_profile,
    }
    unit_id = derive_unit_id("rewrite", payload)
    try:
        # Resolve here, in the producer's cwd. The server may run elsewhere.
        routing = {"workDir": str(Path(work_dir).resolve()), "requestId": request_id}
        record = {"lane": "rewrite", "unitId": unit_id, "payload": payload, "routing": routing}
        target = spool_dir()
        target.mkdir(parents=True, exist_ok=True)
        path = target / _spool_filename(unit_id, routing)
        if path.exists():
            # This exact destination already has an offer. Another work dir
            # or request still needs its own routing record for the same unit.
            return unit_id
        # Write-then-rename: a drain must never observe a half-written file.
        tmp = target / f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
        tmp.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        # Publishing is best-effort. A recovery campaign must not fail because
        # the spool is unwritable.
        logger.warning("exchange: could not spool rewrite unit %s", unit_id, exc_info=True)
        return None
    return unit_id


async def drain_spool(store: ExchangeStore, *, limit: int = MAX_DRAIN_PER_CALL) -> int:
    """Ingest spooled units into `store`. Returns how many were accepted.

    Called on the server side, in the server's own process, so the store stays
    single-writer. An accepted file moves to ``accepted/`` rather than being
    deleted: its ``routing`` is how the coordinator later maps a submitted
    proposal back to the work dir and rewrite-queue request it answers.

    Derives the spool location from `store.state_path`, not the module-level
    `spool_dir()` default -- `routes.create_exchange_router` accepts an
    injected store, and draining a directory unrelated to the store it was
    handed would silently drain the wrong queue for any caller that injects
    one (a test, or a second store on the same host).
    """

    if limit <= 0:
        return 0
    directory = store.state_path.parent / SPOOL_DIRNAME
    accepted = 0
    try:
        entries = await asyncio.to_thread(_spool_entries, directory, limit)
    except FileNotFoundError:
        return 0
    except OSError:
        logger.warning("exchange: could not list spool %s", directory, exc_info=True)
        return 0

    for path in entries:
        try:
            record = await asyncio.to_thread(_read_record, path)
        except (OSError, ValueError):
            # Quarantine rather than delete: an unreadable spool file is
            # evidence, and dropping it silently is the file queue's bug.
            await asyncio.to_thread(_quarantine, path)
            continue
        if not isinstance(record, dict) or not isinstance(record.get("payload"), dict):
            await asyncio.to_thread(_quarantine, path)
            continue
        try:
            await store.offer(lane=str(record.get("lane") or "rewrite"), payload=record["payload"])
        except ValueError:
            # A malformed or non-portable payload is the producer's bug, not a
            # reason to retry forever.
            await asyncio.to_thread(_quarantine, path)
            continue
        except Exception:
            # Capacity or transient failure: leave the file to be retried.
            logger.warning("exchange: could not ingest %s", path.name, exc_info=True)
            continue
        await asyncio.to_thread(_archive, path)
        accepted += 1
    return accepted


def _spool_entries(directory: Path, limit: int) -> list[Path]:
    # Content hashes carry no arrival ordering. Take a bounded batch in directory
    # order, then sort that batch without materializing the entire pending queue.
    # ponytail: non-JSON entries still need traversal; use a separate quarantine
    # directory if rejected-file accumulation becomes a measured scan bottleneck.
    with os.scandir(directory) as entries:
        candidates = (Path(entry.path) for entry in entries if entry.name.endswith(".json") and entry.is_file())
        return sorted(islice(candidates, limit))


def _read_record(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _archive(path: Path) -> None:
    try:
        destination = path.parent / ACCEPTED_DIRNAME
        destination.mkdir(parents=True, exist_ok=True)
        path.replace(destination / path.name)
    except OSError:
        logger.warning("exchange: could not archive %s", path.name, exc_info=True)


def _quarantine(path: Path) -> None:
    try:
        path.replace(path.with_suffix(f".rejected.{secrets.token_hex(4)}"))
    except OSError:
        logger.warning("exchange: could not quarantine %s", path.name, exc_info=True)
