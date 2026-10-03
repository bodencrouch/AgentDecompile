"""Observe Ghidra transaction state without taking ownership of foreign entries."""

from __future__ import annotations

import time

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class TransactionReadiness:
    """A bounded observation of a program's currently open transaction entries."""

    ready: bool
    database_id: int | None
    open_descriptions: tuple[str, ...]
    error: str | None = None

    def diagnostic(self) -> str:
        parts: list[str] = []
        if self.database_id is not None:
            parts.append(f"database transaction {self.database_id}")
        if self.open_descriptions:
            parts.append("open entries: " + ", ".join(repr(value) for value in self.open_descriptions))
        if self.error:
            parts.append(self.error)
        return "; ".join(parts) or "transaction state unavailable"


class TransactionBusyError(RuntimeError):
    """Persistence cannot safely proceed while an unowned entry is open."""


def project_batch_handle(ghidra_project: Any, program: Any) -> int | None:
    """Return the exact batch handle owned by ``GhidraProject.openPrograms``.

    The reflected mapping is the ownership authority. Transaction descriptions and
    ``TransactionInfo.getID()`` are deliberately not used to infer ownership.
    """

    if ghidra_project is None or program is None:
        return None
    try:
        value = project_open_programs_map(ghidra_project).get(program)
        return None if value is None else int(value)
    except Exception:
        return None


def project_open_programs_map(ghidra_project: Any) -> Any:
    """Return GhidraProject's ownership map without interpreting transaction metadata."""

    field = ghidra_project.getClass().getDeclaredField("openPrograms")
    field.setAccessible(True)
    return field.get(ghidra_project)


def observe_transaction_readiness(
    program: Any,
    *,
    owned_batch_handle: int | None = None,
) -> TransactionReadiness:
    """Inspect current entries and decide whether persistence may proceed.

    A direct consumer is ready only when it has no current transaction. A program
    with an exact project-owned batch handle is ready when that batch is the sole
    open entry. Metadata IDs and descriptions are observational only.
    """

    if program is None:
        return TransactionReadiness(True, None, ())
    getter = getattr(program, "getCurrentTransactionInfo", None)
    if not callable(getter):
        getter = getattr(program, "getCurrentTransaction", None)
    if not callable(getter):
        return TransactionReadiness(False, None, (), "program does not expose transaction state")
    try:
        transaction = getter()
    except Exception as exc:
        return TransactionReadiness(False, None, (), f"transaction observation failed: {exc}")
    if transaction is None:
        return TransactionReadiness(True, None, ())

    database_id: int | None = None
    try:
        database_id = int(transaction.getID()) if hasattr(transaction, "getID") else int(transaction)
    except Exception:
        pass

    descriptions: tuple[str, ...] = ()
    get_open = getattr(transaction, "getOpenSubTransactions", None)
    if callable(get_open):
        try:
            descriptions = tuple(str(value) for value in (get_open() or ()))
        except Exception as exc:
            return TransactionReadiness(False, database_id, (), f"open-entry observation failed: {exc}")
    else:
        return TransactionReadiness(False, database_id, (), "open-entry descriptions unavailable")

    ready = owned_batch_handle is not None and len(descriptions) == 1
    return TransactionReadiness(ready, database_id, descriptions)


def wait_for_transaction_readiness(
    program: Any,
    *,
    owned_batch_handle: int | None = None,
    timeout_sec: float = 30.0,
    poll_interval_sec: float = 0.05,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> TransactionReadiness:
    """Wait a bounded interval for a direct or project-owned program to be ready."""

    deadline = monotonic() + max(0.0, timeout_sec)
    while True:
        observation = observe_transaction_readiness(program, owned_batch_handle=owned_batch_handle)
        if observation.ready or monotonic() >= deadline:
            return observation
        sleep(min(max(0.0, poll_interval_sec), max(0.0, deadline - monotonic())))


def require_transaction_readiness(
    program: Any,
    *,
    ghidra_project: Any = None,
    timeout_sec: float = 30.0,
    poll_interval_sec: float = 0.05,
) -> int | None:
    """Require readiness and return the exact project-owned batch handle, if any."""

    batch_handle = project_batch_handle(ghidra_project, program)
    observation = wait_for_transaction_readiness(
        program,
        owned_batch_handle=batch_handle,
        timeout_sec=timeout_sec,
        poll_interval_sec=poll_interval_sec,
    )
    if not observation.ready:
        raise TransactionBusyError(f"program remained busy after {timeout_sec:.3f}s: {observation.diagnostic()}")
    return batch_handle


def save_project_owned_program(
    ghidra_project: Any,
    program: Any,
    *,
    timeout_sec: float = 30.0,
) -> int:
    """Save through ``GhidraProject`` and repair its known failed-save map state.

    GhidraProject.save ends the mapped batch before DomainFile.save, but writes a
    replacement handle only after that save succeeds. If the save raises, the map
    still contains an already-ended handle. We replace that stale value only when
    observation proves no entry is open. Otherwise we remove the exact stale map
    value and leave every live entry untouched, making later operations fail closed.
    """

    open_programs = project_open_programs_map(ghidra_project)
    original_obj = open_programs.get(program)
    if original_obj is None:
        raise TransactionBusyError("program is not owned by GhidraProject.openPrograms")
    original_handle = int(original_obj)
    require_transaction_readiness(
        program,
        ghidra_project=ghidra_project,
        timeout_sec=timeout_sec,
    )
    try:
        ghidra_project.save(program)
    except Exception as save_exc:
        current_obj = open_programs.get(program)
        current_handle = None if current_obj is None else int(current_obj)
        if current_handle == original_handle:
            observation = observe_transaction_readiness(program)
            if observation.ready:
                replacement: int | None = None
                try:
                    replacement = int(program.startTransaction(""))
                    latest_obj = open_programs.get(program)
                    if latest_obj is None or int(latest_obj) != original_handle:
                        raise RuntimeError("GhidraProject batch mapping changed during failed-save repair")
                    try:
                        from java.lang import Integer as JInteger  # pyright: ignore[reportMissingImports]
                    except Exception:
                        JInteger = int
                    open_programs.put(program, JInteger(replacement))
                except Exception as repair_exc:
                    if replacement is not None:
                        try:
                            program.endTransaction(replacement, False)
                        except Exception:
                            pass
                    after_repair_obj = open_programs.get(program)
                    if after_repair_obj is not None and int(after_repair_obj) == original_handle:
                        open_programs.remove(program)
                    if hasattr(save_exc, "add_note"):
                        save_exc.add_note(f"failed to repair GhidraProject batch mapping: {repair_exc}")
            else:
                latest_obj = open_programs.get(program)
                if latest_obj is not None and int(latest_obj) == original_handle:
                    open_programs.remove(program)
        raise

    replacement_handle = project_batch_handle(ghidra_project, program)
    if replacement_handle is None:
        raise TransactionBusyError("GhidraProject.save completed without a replacement batch handle")
    return replacement_handle
