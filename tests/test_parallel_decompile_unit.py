"""JVM-free tests for the batch-decompile bookkeeping (fake runner drives dispose, backpressure, stale, status mapping)."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence
from typing import Any

import pytest

from agentdecompile_cli.mcp_utils.parallel_decompile import (
    STATUS_CANCELLED,
    STATUS_ERROR,
    STATUS_OK,
    STATUS_TIMEOUT,
    BatchResult,
    BatchRunnerError,
    BatchSummary,
    ReadOnlyViolation,
    classify_decompile,
    decompile_functions,
    decompile_functions_iter,
    result_from_decompile_results,
    result_queue_maxsize,
)

pytestmark = pytest.mark.unit


class FakeProgram:
    def __init__(self, *, transaction: object | None = None, modification: int = 7) -> None:
        self._transaction = transaction
        self.modification = modification

    def getCurrentTransactionInfo(self) -> object | None:
        return self._transaction

    def getModificationNumber(self) -> int:
        return self.modification

    def getName(self) -> str:
        return "fake"


class FakeRunner:
    """Emits one result per item from a worker thread, like the Java pool would."""

    instances: list[FakeRunner] = []

    def __init__(self, program: Any, *, threads: int, timeout_s: int, options_configurer: Any, monitor: Any, statuses: dict[int, str] | None = None, fail_wait: bool = False, emit_delay: float = 0.0, on_item: Callable[[int], None] | None = None) -> None:
        self.program = program
        self.threads = threads
        self.timeout_s = timeout_s
        self.options_sha256 = "deadbeef"
        self.disposed = 0
        self.submitted: list[int] = []
        self.statuses = statuses or {}
        self.fail_wait = fail_wait
        self.emit_delay = emit_delay
        self.on_item = on_item
        self._thread: threading.Thread | None = None
        self._emit: Callable[[BatchResult], bool] | None = None
        self.dropped = 0
        FakeRunner.instances.append(self)

    def submit(self, functions: Sequence[Any], emit: Callable[[BatchResult], bool]) -> None:
        self.submitted = list(functions)
        self._emit = emit

        def _work() -> None:
            for item in self.submitted:
                if self.on_item is not None:
                    self.on_item(item)
                if self.emit_delay:
                    time.sleep(self.emit_delay)
                status = self.statuses.get(item, STATUS_OK)
                result = BatchResult(addr=item, name=f"fn_{item:x}", status=status, c_text=f"int fn_{item:x}(void) {{ return {item}; }}" if status == STATUS_OK else None, signature=f"int fn_{item:x}(void)" if status == STATUS_OK else None, error=None if status == STATUS_OK else status, elapsed_ms=1.0)
                if not emit(result):
                    self.dropped += 1

        self._thread = threading.Thread(target=_work, daemon=True)
        self._thread.start()

    def wait(self) -> None:
        if self._thread is not None:
            self._thread.join()
        if self.fail_wait:
            raise RuntimeError("worker exploded")

    def dispose(self) -> None:
        self.disposed += 1


def make_factory(**runner_kwargs: Any) -> Callable[..., FakeRunner]:
    def factory(program: Any, **kwargs: Any) -> FakeRunner:
        return FakeRunner(program, **kwargs, **runner_kwargs)

    return factory


@pytest.fixture(autouse=True)
def _reset_instances() -> None:
    FakeRunner.instances.clear()


def test_happy_path_counts_and_summary() -> None:
    seen: list[BatchResult] = []
    summary = decompile_functions(FakeProgram(), range(10), threads=3, timeout_s=5, on_result=seen.append, runner_factory=make_factory())
    assert isinstance(summary, BatchSummary)
    assert summary.attempted == 10
    assert summary.completed == 10
    assert summary.timed_out == 0
    assert summary.errored == 0
    assert summary.cancelled == 0
    assert summary.threads == 3
    assert summary.stale is False
    assert summary.options_sha256 == "deadbeef"
    assert summary.modification_before == summary.modification_after == 7
    assert sorted(r.addr for r in seen) == list(range(10))
    assert all(r.c_text and r.signature for r in seen)
    runner = FakeRunner.instances[0]
    assert runner.disposed == 1
    assert runner.threads == 3
    assert runner.timeout_s == 5


def test_status_mapping_into_summary() -> None:
    statuses = {1: STATUS_TIMEOUT, 2: STATUS_ERROR, 3: STATUS_CANCELLED}
    summary = decompile_functions(FakeProgram(), [0, 1, 2, 3, 4], threads=2, runner_factory=make_factory(statuses=statuses))
    assert summary.attempted == 5
    assert summary.completed == 2
    assert summary.timed_out == 1
    assert summary.errored == 1
    assert summary.cancelled == 1
    assert summary.statuses == {STATUS_OK: 2, STATUS_TIMEOUT: 1, STATUS_ERROR: 1, STATUS_CANCELLED: 1}


def test_refuses_open_transaction_before_creating_runner() -> None:
    with pytest.raises(ReadOnlyViolation):
        decompile_functions(FakeProgram(transaction=object()), [1], threads=2, runner_factory=make_factory())
    assert FakeRunner.instances == []


def test_stale_when_modification_number_moves() -> None:
    program = FakeProgram(modification=3)

    def bump(_item: int) -> None:
        program.modification = 4

    summary = decompile_functions(program, [1, 2], threads=1, runner_factory=make_factory(on_item=bump))
    assert summary.stale is True
    assert summary.modification_before == 3
    assert summary.modification_after == 4


def test_dispose_runs_when_input_iterator_raises() -> None:
    def broken() -> Any:
        yield 1
        raise ValueError("iterator broke")

    with pytest.raises(ValueError, match="iterator broke"):
        decompile_functions(FakeProgram(), broken(), threads=2, runner_factory=make_factory())
    assert len(FakeRunner.instances) == 1
    assert FakeRunner.instances[0].disposed == 1
    assert FakeRunner.instances[0].submitted == []


def test_dispose_runs_when_consumer_raises_midway() -> None:
    def consumer(result: BatchResult) -> None:
        if result.addr == 2:
            raise RuntimeError("consumer bailed")

    with pytest.raises(RuntimeError, match="consumer bailed"):
        decompile_functions(FakeProgram(), range(40), threads=2, runner_factory=make_factory(), on_result=consumer)
    runner = FakeRunner.instances[0]
    assert runner.disposed == 1
    # the worker was still emitting when we aborted; every remaining emit must have been dropped, not deadlocked
    runner.wait()
    assert runner.dropped >= 1


def test_dispose_runs_when_generator_closed_early() -> None:
    gen = decompile_functions_iter(FakeProgram(), range(50), threads=2, runner_factory=make_factory(emit_delay=0.001))
    first = next(gen)
    assert first.status == STATUS_OK
    gen.close()
    runner = FakeRunner.instances[0]
    assert runner.disposed == 1
    runner.wait()
    assert runner.dropped + 1 + runner.submitted.count(-1) <= 50


def test_runner_wait_failure_surfaces_after_dispose() -> None:
    with pytest.raises(BatchRunnerError, match="worker exploded"):
        decompile_functions(FakeProgram(), range(5), threads=2, runner_factory=make_factory(fail_wait=True))
    assert FakeRunner.instances[0].disposed == 1


def test_backpressure_bounds_in_flight_results() -> None:
    threads = 2
    maxsize = result_queue_maxsize(threads)
    assert maxsize == 8
    observed_max = 0
    lock = threading.Lock()
    produced = 0
    consumed = 0

    def on_item(_item: int) -> None:
        nonlocal produced
        with lock:
            produced += 1

    def consumer(_result: BatchResult) -> None:
        nonlocal consumed, observed_max
        time.sleep(0.002)
        with lock:
            consumed += 1
            # results emitted but not yet consumed can never exceed the bounded queue (+1 being handed over)
            in_flight = produced - consumed
            observed_max = max(observed_max, in_flight)

    summary = decompile_functions(FakeProgram(), range(100), threads=threads, runner_factory=make_factory(on_item=on_item), on_result=consumer)
    assert summary.completed == 100
    assert observed_max <= maxsize + 1


def test_empty_batch_disposes_and_returns_zero_summary() -> None:
    summary = decompile_functions(FakeProgram(), [], threads=4, runner_factory=make_factory())
    assert summary.attempted == 0
    assert summary.completed == 0
    assert FakeRunner.instances[0].disposed == 1


def test_classify_decompile_mapping() -> None:
    assert classify_decompile(completed=True, timed_out=False, cancelled=False, error_message="") == STATUS_OK
    assert classify_decompile(completed=False, timed_out=True, cancelled=False, error_message="") == STATUS_TIMEOUT
    assert classify_decompile(completed=False, timed_out=False, cancelled=True, error_message="") == STATUS_CANCELLED
    assert classify_decompile(completed=False, timed_out=False, cancelled=False, error_message="boom") == STATUS_ERROR
    assert classify_decompile(completed=False, timed_out=False, cancelled=False, error_message="") == STATUS_ERROR
    # timeout wins over the "completed" flag; that mirrors DecompileResults where a timed-out process has no C
    assert classify_decompile(completed=True, timed_out=True, cancelled=False, error_message="") == STATUS_TIMEOUT


class _Entry:
    def __init__(self, offset: int) -> None:
        self._offset = offset

    def getOffset(self) -> int:
        return self._offset


class _Function:
    def __init__(self, offset: int, name: str) -> None:
        self._entry = _Entry(offset)
        self._name = name

    def getEntryPoint(self) -> _Entry:
        return self._entry

    def getName(self, qualified: bool = False) -> str:
        return self._name


class _Decompiled:
    def __init__(self, c: str, sig: str) -> None:
        self._c, self._sig = c, sig

    def getC(self) -> str:
        return self._c

    def getSignature(self) -> str:
        return self._sig


class _Results:
    def __init__(self, *, completed: bool, timed_out: bool = False, cancelled: bool = False, error: str = "", decompiled: _Decompiled | None = None) -> None:
        self._completed, self._timed_out, self._cancelled, self._error, self._decompiled = completed, timed_out, cancelled, error, decompiled

    def decompileCompleted(self) -> bool:
        return self._completed

    def isTimedOut(self) -> bool:
        return self._timed_out

    def isCancelled(self) -> bool:
        return self._cancelled

    def getErrorMessage(self) -> str:
        return self._error

    def getDecompiledFunction(self) -> _Decompiled | None:
        return self._decompiled


def test_result_from_decompile_results_ok_and_error_shapes() -> None:
    fn = _Function(0x401000, "main")
    ok = result_from_decompile_results(fn, _Results(completed=True, decompiled=_Decompiled("int main(void)\n{\n  return 0;\n}\n", "int main(void)")), 12.5)
    assert ok.status == STATUS_OK
    assert ok.addr == 0x401000
    assert ok.name == "main"
    assert ok.c_text.startswith("int main")
    assert ok.signature == "int main(void)"
    assert ok.elapsed_ms == 12.5
    timed = result_from_decompile_results(fn, _Results(completed=False, timed_out=True, error="Decompiler process timed out"), 60000.0)
    assert timed.status == STATUS_TIMEOUT
    assert timed.c_text is None
    assert "timed out" in (timed.error or "")
    err = result_from_decompile_results(fn, _Results(completed=False, error="Low-level Error: bad"), 3.0)
    assert err.status == STATUS_ERROR
    assert err.error == "Low-level Error: bad"
    none_c = result_from_decompile_results(fn, _Results(completed=True, decompiled=None), 1.0)
    assert none_c.status == STATUS_ERROR
    assert none_c.to_dict()["addr"] == 0x401000
