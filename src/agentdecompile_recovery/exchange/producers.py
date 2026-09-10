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

from .store import ExchangeStore, _sync_directory, default_state_path, derive_unit_id

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


def _ensure_directory(directory: Path) -> None:
    """Durably create ``directory``, retaining setup intent across a restart.

    A visible directory is not necessarily anchored after a failed ancestor
    fsync.  Record an intent in the nearest existing parent before ``mkdir``;
    a retry discovers that exact marker and completes the same sync chain
    before any routing file may be published or its pending copy removed.
    """

    directory = directory.absolute()
    marker_name = ".exchange-spool-init-" + hashlib.sha256(os.fsencode(directory)).hexdigest() + ".pending"
    ancestors = (directory, *directory.parents)
    anchor = next((parent for parent in ancestors if (parent / marker_name).exists()), None)
    if anchor is None:
        anchor = next(parent for parent in ancestors if parent.is_dir())
        if anchor == directory:
            return
    marker = anchor / marker_name
    with marker.open("a", encoding="utf-8") as stream:
        stream.flush()
        os.fsync(stream.fileno())
    _sync_directory(anchor)
    directory.mkdir(parents=True, exist_ok=True)
    for parent in ancestors:
        _sync_directory(parent)
        if parent == anchor:
            break
    marker.unlink()
    _sync_directory(anchor)


def _sync_directory_tree(directory: Path) -> None:
    """Persist a replacement or unlink in an already anchored directory."""

    _sync_directory(directory)


def _recover_pending_state_directory(state_path: Path) -> None:
    """Finish a store mkdir intent before publishing below its state directory.

    Pipeline producers can run after the server died in
    ``ExchangeStore._prepare_state_directory``: the visible state directory is
    then not necessarily anchored in its parent.  The store's marker is an
    explicit cross-process recovery contract, so honor that same marker before
    treating ``state_path.parent`` as an existing safe spool ancestor.
    """

    state_path = state_path.absolute()
    directory = state_path.parent
    marker_name = ".exchange-init-" + hashlib.sha256(os.fsencode(state_path)).hexdigest() + ".pending"
    ancestors = (directory, *directory.parents)
    anchor = next((parent for parent in ancestors if (parent / marker_name).exists()), None)
    if anchor is None:
        return
    for parent in ancestors:
        _sync_directory(parent)
        if parent == anchor:
            break
    marker = anchor / marker_name
    marker.unlink()
    _sync_directory(anchor)


def _write_record(path: Path, record: dict[str, Any]) -> None:
    """Write a spool record before making its route visible to the server."""

    tmp = path.parent / f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
    try:
        with tmp.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True))
            stream.flush()
            os.fsync(stream.fileno())
        tmp.replace(path)
        _sync_directory_tree(path.parent)
    finally:
        tmp.unlink(missing_ok=True)


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
        state_path = default_state_path()
        _recover_pending_state_directory(state_path)
        target = state_path.parent / SPOOL_DIRNAME
        _ensure_directory(target)
        path = target / _spool_filename(unit_id, routing)
        if path.exists():
            # This exact destination already has an offer. Another work dir
            # or request still needs its own routing record for the same unit.
            _sync_directory_tree(target)
            return unit_id
        _write_record(path, record)
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
        if await asyncio.to_thread(_archive, path) is not False:
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


def _archive(path: Path) -> bool:
    """Anchor a routing record in ``accepted`` before removing its spool copy."""

    try:
        destination = path.parent / ACCEPTED_DIRNAME
        _ensure_directory(destination)
        archived = destination / path.name
        if archived.exists():
            if archived.read_bytes() != path.read_bytes():
                raise OSError(f"refusing to overwrite different accepted record {archived}")
            _sync_directory_tree(destination)
        else:
            # Do not rename the sole routing record. A crash after rename and
            # before the accepted directory is synced strands an otherwise
            # durable store offer with no local destination to consume.
            tmp = destination / f".{archived.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
            try:
                with path.open("rb") as source, tmp.open("xb") as output:
                    while chunk := source.read(1024 * 1024):
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                tmp.replace(archived)
                _sync_directory_tree(destination)
            finally:
                tmp.unlink(missing_ok=True)
        try:
            path.unlink()
            _sync_directory(path.parent)
        except OSError:
            # The accepted copy is durable. A retained pending copy can be
            # re-offered idempotently after a crash, so it is safe to report
            # this unit accepted while surfacing cleanup trouble.
            logger.warning("exchange: could not remove archived spool record %s", path.name, exc_info=True)
        return True
    except OSError:
        logger.warning("exchange: could not archive %s", path.name, exc_info=True)
        return False


def _quarantine(path: Path) -> None:
    try:
        path.replace(path.with_suffix(f".rejected.{secrets.token_hex(4)}"))
    except OSError:
        logger.warning("exchange: could not quarantine %s", path.name, exc_info=True)
