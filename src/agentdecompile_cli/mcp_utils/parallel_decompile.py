"""Bounded, read-only parallel batch decompile on Ghidra's own parallel machinery.

Ghidra ships ``ghidra.app.decompiler.parallel.DecompilerCallback`` (a
``QCallback`` that borrows ``DecompInterface`` instances from a
``CachingPool``) and ``ghidra.app.util.DecompilerConcurrentQ`` (a
``ConcurrentQ`` over a ``GThreadPool``).  ``DecompilerCallback`` is abstract and
JPype cannot subclass abstract classes, so this module re-creates its two
collaborators in Python: a ``generic.concurrent.QCallback`` that decompiles one
function per call and a ``generic.cache.BasicFactory`` that creates and
disposes ``DecompInterface`` instances for the pool.

Guarantees:

* additive: nothing here touches ``DecompilerLease`` or existing callers;
* bounded: a private ``GThreadPool`` sized to ``threads`` (the shared
  "Parallel Decompiler" pool is never resized) and a bounded result queue of
  ``threads * 4`` entries drained on the caller's thread, so ``on_result``
  never runs on a Java thread and workers block instead of buffering;
* read-only: refuses when a transaction is open on the program, records the
  modification number before and after and flags ``stale`` if it moved, holds
  no lock across the batch;
* disposed: every pooled ``DecompInterface`` (one native ``decompile``
  process each), the queue and the private pool are disposed in ``finally``
  even when the consumer raises or the input iterator fails.

The Java wiring lives in ``_JavaBatchRunner``; the bookkeeping
(``decompile_functions_iter``) only talks to the small ``BatchRunner``
protocol so unit tests can drive dispose / backpressure / stale logic with a
fake runner and no JVM.
"""

from __future__ import annotations

import hashlib
import logging
import queue
import threading
import time
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

logger = logging.getLogger(__name__)

PRIVATE_POOL_NAME = "agentdecompile-batch-decompile"
STATUS_OK = "ok"
STATUS_TIMEOUT = "timeout"
STATUS_ERROR = "error"
STATUS_CANCELLED = "cancelled"
STATUSES = (STATUS_OK, STATUS_TIMEOUT, STATUS_ERROR, STATUS_CANCELLED)
_DRAIN_POLL_S = 0.2
_EMIT_POLL_S = 0.5
_DISPOSE_JOIN_S = 30.0


class ReadOnlyViolation(RuntimeError):
    """Raised when the program has an open transaction; the batch is read-only."""


class BatchRunnerError(RuntimeError):
    """Raised when the runner finished abnormally (unhandled worker exception)."""


@dataclass(slots=True)
class BatchResult:
    addr: int
    name: str
    status: str
    c_text: str | None = None
    signature: str | None = None
    error: str | None = None
    elapsed_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BatchSummary:
    attempted: int = 0
    completed: int = 0
    timed_out: int = 0
    errored: int = 0
    cancelled: int = 0
    wall_s: float = 0.0
    threads: int = 1
    stale: bool = False
    modification_before: int | None = None
    modification_after: int | None = None
    options_sha256: str | None = None
    runner_error: str | None = None
    statuses: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BatchRunner(Protocol):
    """What the bookkeeping needs from a runner.  ``submit`` must return promptly.

    ``emit`` is thread-safe and may be called from any thread; it returns
    ``False`` when the batch is aborting and the result was dropped.
    """

    options_sha256: str | None

    def submit(self, functions: Sequence[Any], emit: Callable[[BatchResult], bool]) -> None: ...

    def wait(self) -> None: ...

    def dispose(self) -> None: ...


RunnerFactory = Callable[..., BatchRunner]


def classify_decompile(*, completed: bool, timed_out: bool, cancelled: bool, error_message: str | None) -> str:
    """Map ``DecompileResults`` flags to a batch status.  Pure so unit tests can pin it."""
    if timed_out:
        return STATUS_TIMEOUT
    if cancelled:
        return STATUS_CANCELLED
    if completed:
        return STATUS_OK
    return STATUS_ERROR


def result_queue_maxsize(threads: int) -> int:
    return max(1, int(threads)) * 4


def check_read_only(program: Any) -> None:
    """Refuse a batch while any transaction is open on ``program``."""
    # PyGhidra leaves a documented stale bootstrap record after import; the
    # snapshot exporter owns the shared, conservative discriminator.
    from agentdecompile_recovery.native_snapshot.exporter import _has_open_transaction

    if _has_open_transaction(program):
        info = program.getCurrentTransactionInfo()
        raise ReadOnlyViolation(f"program {program.getName()!s} has an open transaction ({info!s}); batch decompile is read-only")


def modification_number(program: Any) -> int | None:
    try:
        return int(program.getModificationNumber())
    except Exception:
        return None


def options_sha256_for(ifc: Any) -> str:
    """SHA-256 of ``DecompileOptions.encode(XmlEncode, ifc)``: the bytes the decompiler process receives."""
    from ghidra.program.model.pcode import XmlEncode  # pyright: ignore[reportMissingModuleSource]

    encoder = XmlEncode()
    ifc.getOptions().encode(encoder, ifc)
    return hashlib.sha256(str(encoder.toString()).encode("utf-8")).hexdigest()


def function_addr(function: Any) -> int:
    return int(function.getEntryPoint().getOffset())


def function_name(function: Any) -> str:
    try:
        return str(function.getName(True))
    except Exception:
        return str(function.getName())


def result_from_decompile_results(function: Any, results: Any, elapsed_ms: float) -> BatchResult:
    """Build a ``BatchResult`` from a ``ghidra.app.decompiler.DecompileResults``."""
    addr = function_addr(function)
    name = function_name(function)
    error_message = str(results.getErrorMessage() or "")
    status = classify_decompile(
        completed=bool(results.decompileCompleted()),
        timed_out=bool(results.isTimedOut()),
        cancelled=bool(results.isCancelled()),
        error_message=error_message,
    )
    if status != STATUS_OK:
        return BatchResult(addr=addr, name=name, status=status, error=error_message.strip() or status, elapsed_ms=elapsed_ms)
    decompiled = results.getDecompiledFunction()
    if decompiled is None:
        return BatchResult(addr=addr, name=name, status=STATUS_ERROR, error=error_message.strip() or "decompileCompleted but no DecompiledFunction", elapsed_ms=elapsed_ms)
    return BatchResult(
        addr=addr,
        name=name,
        status=STATUS_OK,
        c_text=str(decompiled.getC()),
        signature=str(decompiled.getSignature()),
        error=None,
        elapsed_ms=elapsed_ms,
    )


# ---------------------------------------------------------------------------
# Bookkeeping (JVM-free)
# ---------------------------------------------------------------------------


class _ResultChannel:
    """Bounded hand-off from worker threads to the consumer thread with abort support."""

    def __init__(self, maxsize: int) -> None:
        self.queue: queue.Queue[BatchResult] = queue.Queue(maxsize=maxsize)
        self.abort = threading.Event()
        self.emitted = 0
        self.dropped = 0
        self._lock = threading.Lock()

    def emit(self, result: BatchResult) -> bool:
        while not self.abort.is_set():
            try:
                self.queue.put(result, timeout=_EMIT_POLL_S)
            except queue.Full:
                continue
            with self._lock:
                self.emitted += 1
            return True
        with self._lock:
            self.dropped += 1
        return False


def decompile_functions_iter(
    program: Any,
    functions: Iterable[Any],
    *,
    threads: int,
    timeout_s: int = 60,
    options_configurer: Callable[[Any, Any], None] | None = None,
    monitor: Any = None,
    runner_factory: RunnerFactory | None = None,
) -> Iterator[BatchResult]:
    """Yield one ``BatchResult`` per function on the caller's thread; ``StopIteration.value`` is the ``BatchSummary``.

    ``runner_factory(program, threads=..., timeout_s=..., options_configurer=..., monitor=...)``
    defaults to the Java runner; tests inject a fake.
    """
    threads = max(1, int(threads))
    timeout_s = max(1, int(timeout_s))
    check_read_only(program)
    factory = runner_factory or _java_runner_factory
    summary = BatchSummary(threads=threads, modification_before=modification_number(program))
    started = time.perf_counter()
    channel = _ResultChannel(result_queue_maxsize(threads))
    runner: BatchRunner | None = None
    waiter: threading.Thread | None = None
    done = threading.Event()
    wait_error: list[BaseException] = []
    try:
        runner = factory(program, threads=threads, timeout_s=timeout_s, options_configurer=options_configurer, monitor=monitor)
        items = list(functions)
        summary.attempted = len(items)
        if items:
            runner.submit(items, channel.emit)

            def _wait() -> None:
                try:
                    runner.wait()
                except BaseException as exc:  # noqa: BLE001 - surfaced to the caller as BatchRunnerError
                    wait_error.append(exc)
                finally:
                    done.set()

            waiter = threading.Thread(target=_wait, name="agentdecompile-batch-wait", daemon=True)
            waiter.start()
        else:
            done.set()
        received = 0
        while received < summary.attempted:
            try:
                item = channel.queue.get(timeout=_DRAIN_POLL_S)
            except queue.Empty:
                if done.is_set() and channel.queue.empty():
                    break
                continue
            received += 1
            _tally(summary, item)
            yield item
        if wait_error:
            summary.runner_error = repr(wait_error[0])
        summary.cancelled += summary.attempted - received
        summary.statuses[STATUS_CANCELLED] = summary.cancelled
    finally:
        channel.abort.set()
        if runner is not None:
            try:
                runner.dispose()
            except Exception as exc:
                logger.warning("batch runner dispose failed: %r", exc)
        if waiter is not None:
            waiter.join(_DISPOSE_JOIN_S)
        summary.wall_s = time.perf_counter() - started
        summary.modification_after = modification_number(program)
        summary.stale = summary.modification_before is not None and summary.modification_after is not None and summary.modification_before != summary.modification_after
        if runner is not None:
            summary.options_sha256 = getattr(runner, "options_sha256", None)
    if wait_error:
        raise BatchRunnerError(f"batch runner failed after {summary.completed}/{summary.attempted} results: {wait_error[0]!r}") from wait_error[0]
    return summary


def _tally(summary: BatchSummary, item: BatchResult) -> None:
    summary.statuses[item.status] = summary.statuses.get(item.status, 0) + 1
    if item.status == STATUS_OK:
        summary.completed += 1
    elif item.status == STATUS_TIMEOUT:
        summary.timed_out += 1
    elif item.status == STATUS_CANCELLED:
        summary.cancelled += 1
    else:
        summary.errored += 1


def decompile_functions(
    program: Any,
    functions: Iterable[Any],
    *,
    threads: int,
    timeout_s: int = 60,
    options_configurer: Callable[[Any, Any], None] | None = None,
    on_result: Callable[[BatchResult], None] | None = None,
    monitor: Any = None,
    runner_factory: RunnerFactory | None = None,
) -> BatchSummary:
    """Decompile ``functions`` on ``threads`` private worker threads; ``on_result`` runs on the caller's thread.

    Returns the ``BatchSummary``.  Raises ``ReadOnlyViolation`` when a transaction is open, ``BatchRunnerError``
    when a worker failed outside the per-function error path.  Everything is disposed before this returns.
    """
    gen = decompile_functions_iter(program, functions, threads=threads, timeout_s=timeout_s, options_configurer=options_configurer, monitor=monitor, runner_factory=runner_factory)
    try:
        while True:
            try:
                result = next(gen)
            except StopIteration as stop:
                return stop.value
            if on_result is not None:
                on_result(result)
    finally:
        gen.close()


# ---------------------------------------------------------------------------
# Java wiring (needs a started JVM)
# ---------------------------------------------------------------------------

_JAVA_CLASSES: dict[str, Any] = {}
_JAVA_CLASSES_LOCK = threading.Lock()


def _java_classes() -> dict[str, Any]:
    """Define the JImplements classes once, after the JVM is up."""
    with _JAVA_CLASSES_LOCK:
        if _JAVA_CLASSES:
            return _JAVA_CLASSES
        import jpype
        from java.util.concurrent import TimeUnit  # pyright: ignore[reportMissingImports]

        @jpype.JImplements("generic.cache.BasicFactory")
        class _PyDecompilerFactory:
            def __init__(self, program: Any, configurer: Callable[[Any, Any], None], owner: _JavaBatchRunner) -> None:
                self._program = program
                self._configurer = configurer
                self._owner = owner

            @jpype.JOverride
            def create(self) -> Any:
                from ghidra.app.decompiler import DecompInterface  # pyright: ignore[reportMissingModuleSource]

                ifc = DecompInterface()
                try:
                    self._configurer(ifc, self._program)
                    if not ifc.openProgram(self._program):
                        raise RuntimeError(f"DecompInterface.openProgram failed: {ifc.getLastMessage()!s}")
                    self._owner._note_created(ifc)
                except Exception:
                    ifc.dispose()
                    raise
                return ifc

            @jpype.JOverride
            def dispose(self, ifc: Any) -> None:
                self._owner._note_disposed()
                try:
                    ifc.dispose()
                except Exception as exc:
                    logger.warning("DecompInterface.dispose failed: %r", exc)

        @jpype.JImplements("generic.concurrent.QCallback")
        class _PyDecompileCallback:
            def __init__(self, pool: Any, timeout_s: int, owner: _JavaBatchRunner) -> None:
                self._pool = pool
                self._timeout_s = int(timeout_s)
                self._owner = owner

            @jpype.JOverride
            def process(self, function: Any, monitor: Any) -> Any:
                from ghidra.util.task import TimeoutTaskMonitor  # pyright: ignore[reportMissingModuleSource]

                emit = self._owner.emit
                if emit is None or self._owner.aborted:
                    return None
                if monitor is not None and monitor.isCancelled():
                    emit(BatchResult(addr=function_addr(function), name=function_name(function), status=STATUS_CANCELLED, error="cancelled before start"))
                    return None
                started = time.perf_counter()
                ifc = None
                try:
                    ifc = self._pool.get()
                    per_function_monitor = TimeoutTaskMonitor.timeoutIn(self._timeout_s, TimeUnit.SECONDS)
                    results = ifc.decompileFunction(function, self._timeout_s, per_function_monitor)
                    elapsed_ms = (time.perf_counter() - started) * 1000.0
                    result = result_from_decompile_results(function, results, elapsed_ms)
                except Exception as exc:
                    elapsed_ms = (time.perf_counter() - started) * 1000.0
                    result = BatchResult(addr=function_addr(function), name=function_name(function), status=STATUS_ERROR, error=repr(exc), elapsed_ms=elapsed_ms)
                finally:
                    if ifc is not None:
                        self._pool.release(ifc)
                emit(result)
                return None

        _JAVA_CLASSES["factory"] = _PyDecompilerFactory
        _JAVA_CLASSES["callback"] = _PyDecompileCallback
        return _JAVA_CLASSES


class _JavaBatchRunner:
    """Ghidra-backed ``BatchRunner``: private ``GThreadPool`` + ``CachingPool`` + ``DecompilerConcurrentQ``."""

    def __init__(self, program: Any, *, threads: int, timeout_s: int, options_configurer: Callable[[Any, Any], None] | None, monitor: Any) -> None:
        from generic.cache import CachingPool  # pyright: ignore[reportMissingImports]
        from generic.concurrent import GThreadPool  # pyright: ignore[reportMissingImports]
        from ghidra.app.util import DecompilerConcurrentQ  # pyright: ignore[reportMissingModuleSource]
        from ghidra.util.task import TaskMonitor  # pyright: ignore[reportMissingModuleSource]

        from agentdecompile_cli.mcp_utils.decompiler_util import _configure_decompiler_for_program

        classes = _java_classes()
        self.program = program
        self.threads = int(threads)
        self.timeout_s = int(timeout_s)
        self.options_sha256: str | None = None
        self.created = 0
        self.disposed = 0
        self.emit: Callable[[BatchResult], bool] | None = None
        self.aborted = False
        self._lock = threading.Lock()
        configurer = options_configurer or _configure_decompiler_for_program
        self._factory = classes["factory"](program, configurer, self)
        self._pool = CachingPool(self._factory)
        self._thread_pool = GThreadPool.getPrivateThreadPool(PRIVATE_POOL_NAME)
        self._thread_pool.setMaxThreadCount(self.threads)
        self._monitor = monitor if monitor is not None else TaskMonitor.DUMMY
        self._callback = classes["callback"](self._pool, self.timeout_s, self)
        self._queue = DecompilerConcurrentQ(self._callback, self._thread_pool, False, self._monitor)
        self._disposed = False

    def _note_created(self, ifc: Any) -> None:
        with self._lock:
            self.created += 1
            if self.options_sha256 is None:
                self.options_sha256 = options_sha256_for(ifc)

    def _note_disposed(self) -> None:
        with self._lock:
            self.disposed += 1

    def submit(self, functions: Sequence[Any], emit: Callable[[BatchResult], bool]) -> None:
        from java.util import ArrayList  # pyright: ignore[reportMissingImports]

        self.emit = emit
        items = ArrayList()
        for function in functions:
            items.add(function)
        self._queue.addAll(items)

    def wait(self) -> None:
        self._queue.waitUntilDone()

    def dispose(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        self.aborted = True
        for label, action in (
            ("queue", self._queue.dispose),
            ("pool", self._pool.dispose),
            ("thread-pool", self._thread_pool.shutdownNow),
        ):
            try:
                action()
            except Exception as exc:
                logger.warning("batch %s dispose failed: %r", label, exc)


def _java_runner_factory(program: Any, **kwargs: Any) -> BatchRunner:
    return _JavaBatchRunner(program, **kwargs)


def serial_decompile_one(program: Any, function: Any, *, timeout_s: int = 60, options_configurer: Callable[[Any, Any], None] | None = None) -> BatchResult:
    """Reference path: one fresh ``DecompInterface``, same configurer, disposed before return (for parity checks)."""
    from ghidra.app.decompiler import DecompInterface  # pyright: ignore[reportMissingModuleSource]
    from ghidra.util.task import TimeoutTaskMonitor  # pyright: ignore[reportMissingModuleSource]
    from java.util.concurrent import TimeUnit  # pyright: ignore[reportMissingImports]

    from agentdecompile_cli.mcp_utils.decompiler_util import _configure_decompiler_for_program

    configurer = options_configurer or _configure_decompiler_for_program
    ifc = DecompInterface()
    try:
        configurer(ifc, program)
        if not ifc.openProgram(program):
            raise RuntimeError(f"DecompInterface.openProgram failed: {ifc.getLastMessage()!s}")
        started = time.perf_counter()
        results = ifc.decompileFunction(function, int(timeout_s), TimeoutTaskMonitor.timeoutIn(int(timeout_s), TimeUnit.SECONDS))
        return result_from_decompile_results(function, results, (time.perf_counter() - started) * 1000.0)
    finally:
        ifc.dispose()


def batch_candidates(program: Any, *, addrs: Iterable[int] | None = None, limit: int | None = None) -> list[Any]:
    """Functions worth sending to the decompiler: non-external, non-thunk, with a body.

    ``addrs`` restricts to those entry offsets (order preserved); ``limit`` truncates.
    """
    fm = program.getFunctionManager()
    wanted = None if addrs is None else {int(a) for a in addrs}
    out: list[Any] = []
    for function in fm.getFunctions(True):
        if function.isExternal() or function.isThunk():
            continue
        body = function.getBody()
        if body is None or body.isEmpty():
            continue
        if wanted is not None and function_addr(function) not in wanted:
            continue
        out.append(function)
        if limit is not None and len(out) >= limit:
            break
    return out
