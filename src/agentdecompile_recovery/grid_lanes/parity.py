"""``parity-check``: the object-diff check of one candidate object against its target (§3.4).

Inputs: ``target`` (the pinned target ``.o`` from ``mkobj-target``) and ``candidate`` (a COFF
object, normally a verified ``compile-attempt`` output).  Params: ``symbol`` (optional),
``verifier_id`` -- ``parity:<sha256>`` for the native checker binary or ``parity-wasm:<sha256>``
for the node + wasm bundle -- and ``timeout_s``.  Capability: the ``verifier_id`` itself, so a
node with a different checker build advertises a different capability and is never offered a
task keyed to the pinned one (U125).

Sides are **named**: the native CLI is rendered ``-1 <target> -2 <candidate>`` and the node
helper ``<candidate as base> <target>``, so the reversed-order call at seed_validation.py:353-357
cannot recur.  Output: ``receipt`` -- the ``agentdecompile.verify-objdiff.v1`` report parsed
fail-closed by ``objdiff_verification.parse_objdiff_report`` (empty output is never a match),
with the raw checker text spilled to its own ``raw`` object and ``grade`` = ``matched`` |
``mismatched`` | ``error``.  Budget SMALL (MEASURED 0.06 s native floor, 0.5-1.2 s node).
The bare ``subprocess.run`` of objdiff_check.py:42 gets the deadline it lacks.

``verify`` authenticates proposal bytes and independently reproduces the checker observation.
``parity-binding-v1`` names this predicate; complete target-region parity and runtime admission
remain absent. Historical task IDs, receipts and eight-column replay retain their v1 shape.

Acceptance tests (named, landed with U136):

* ``test_parity_task_id_same_for_native_and_wasm_pinned_ids``;
* ``test_parity_receipt_byte_identical_same_verifier`` -- two runs, one ``receipt`` ref;
* ``test_parity_stub_never_returns_yields_timeout_within_budget``;
* ``test_parity_sides_named`` -- swapping inputs changes ``sides`` and the task id;
* ``test_parity_empty_output_fails_closed``;
* ``test_parity_checker_missing_refuses_by_name``.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import os
import re
import shutil
import selectors
import signal
import stat
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping

from agentdecompile_grid.core import (
    BudgetClass,
    ObjectRef,
    ObjectStore,
    Refused,
    Registry,
    ResultStatus,
    TaskResult,
    TaskSpec,
    Verification,
    VerificationOutcome,
    canonical_json,
    digest,
    task_kind,
)
from agentdecompile_grid.objects.base import validate_ref
from agentdecompile_grid.objects.local import LocalDirStore
from agentdecompile_grid.view.applier import ensure_tables, view_hook

from ._common import (
    PlannableKind,
    RunOutcome,
    assert_portable,
    get_json,
    make_result,
    scrub_paths,
)

RECEIPT_SCHEMA = "agentdecompile.verify-objdiff.v1"
NATIVE_PREFIX = "parity:"
WASM_PREFIX = "parity-wasm:"
_ROWS = re.compile(r"rows identical:\s*(\d+),\s*differing:\s*(\d+)")
_RESULT = re.compile(r"RESULT:\s*(MATCH 100%|MISMATCH \(([0-9.]+)%\))")


# --------------------------------------------------------------------------- checkers
@dataclasses.dataclass(frozen=True)
class ParityChecker:
    verifier_id: str
    flavour: str                 # "native" | "node"
    path: Path                   # native binary, or the node script
    node: Path | None = None
    wasm_root: Path | None = None

    def argv(self, target: Path, candidate: Path, symbol: str) -> list[str]:
        if self.flavour == "native":
            return [str(self.path), "diff", "-1", str(target), "-2", str(candidate), "-o", "-", "--format", "json-pretty"]
        argv = [str(self.node), str(self.path), str(candidate), str(target)]
        if symbol:
            argv.append(symbol)
        return argv

    def env(self) -> dict[str, str]:
        env = dict(os.environ)
        if self.flavour == "node" and self.wasm_root is not None:
            env["AGENT_DECOMPILE_OBJDIFF_WASM_ROOT"] = str(self.wasm_root)
        return env


PARITY_CHECKERS = Registry("parity checker")


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def register_native(path: str | Path, *, replace: bool = True) -> ParityChecker:
    """Register the native checker binary; its id is ``parity:<sha256 of the binary>``."""
    binary = Path(path).expanduser().resolve()
    if not binary.is_file():
        raise Refused("parity-checker-missing:native")
    checker = ParityChecker(verifier_id=NATIVE_PREFIX + _file_sha256(binary), flavour="native", path=binary)
    PARITY_CHECKERS.register(checker.verifier_id, checker, replace=replace)
    return checker


def register_node(script: str | Path, wasm_root: str | Path, *, node: str | None = None, replace: bool = True) -> ParityChecker:
    """Register the node helper + wasm bundle; id = ``parity-wasm:<sha256 over script, js, wasm>``."""
    script_path = Path(script).expanduser().resolve()
    root = Path(wasm_root).expanduser().resolve()
    node_path = Path(node or shutil.which("node") or "")
    if not script_path.is_file() or not node_path.is_file():
        raise Refused("parity-checker-missing:node")
    dist = root / "node_modules" / "objdiff-wasm" / "dist"
    parts = [_file_sha256(script_path)]
    for name in ("objdiff.js", "objdiff.core.wasm"):
        candidate = dist / name
        if not candidate.is_file():
            raise Refused(f"parity-checker-missing:wasm:{name}")
        parts.append(_file_sha256(candidate))
    checker = ParityChecker(
        verifier_id=WASM_PREFIX + digest("\n".join(parts).encode()), flavour="node",
        path=script_path, node=node_path, wasm_root=root,
    )
    PARITY_CHECKERS.register(checker.verifier_id, checker, replace=replace)
    return checker


def discover_checkers() -> list[ParityChecker]:
    """Register whatever this host has (env / PATH); used when no canary ran."""
    found: list[ParityChecker] = []
    native = os.environ.get("AGENT_DECOMPILE_OBJDIFF", "").strip() or shutil.which("objdiff")
    if native:
        try:
            found.append(register_native(native))
        except Refused:
            pass
    from ..corpus.objdiff_check import default_script

    script = default_script()
    wasm_root = os.environ.get("AGENT_DECOMPILE_OBJDIFF_WASM_ROOT", "").strip()
    if script is not None and wasm_root:
        try:
            found.append(register_node(script, wasm_root))
        except Refused:
            pass
    return found


def resolve_checker(verifier_id: str, *, deadline: float | None = None) -> ParityChecker:
    if deadline is not None:
        return _resolve_selected(verifier_id, deadline)
    if verifier_id in PARITY_CHECKERS:
        return PARITY_CHECKERS.get(verifier_id)
    for checker in discover_checkers():
        if checker.verifier_id == verifier_id:
            return checker
    raise Refused(f"parity-checker-not-present:{verifier_id[:24]}")


# --------------------------------------------------------------------------- node text parsing
def parse_node_report(returncode: int, output: str) -> dict[str, Any]:
    """The node helper's text into the ``verify-objdiff.v1`` shape, fail-closed like the parser."""
    text = output if isinstance(output, str) else ""
    rows = _ROWS.search(text)
    result = _RESULT.search(text)
    if not text.strip() or rows is None or result is None or returncode not in (0, 1):
        return {
            "schema": RECEIPT_SCHEMA, "status": "error", "differences": -1,
            "message": "node checker produced no verdict" if text.strip() else "node checker produced empty output",
            "objdiffExit": returncode, "detailLevel": "row",
        }
    differing = int(rows.group(2))
    matched = returncode == 0 and differing == 0 and result.group(1) == "MATCH 100%"
    return {
        "schema": RECEIPT_SCHEMA, "status": "matched" if matched else "mismatched",
        "differences": 0 if matched else max(differing, 1), "message": "Object files match" if matched else "Object files do not match",
        "objdiffExit": returncode, "detailLevel": "row", "rowsIdentical": int(rows.group(1)), "rowsDiffering": differing,
        "matchPercent": 100.0 if matched else float(result.group(2) or 0.0),
    }


# --------------------------------------------------------------------------- authenticated observation
INPUT_LIMIT = 64 * 1024 * 1024
RECEIPT_LIMIT = 1024 * 1024
RAW_LIMIT = 4 * 1024 * 1024
STDERR_LIMIT = 1024 * 1024
ARTIFACT_LIMIT = 256 * 1024 * 1024
CHUNK_SIZE = 64 * 1024
METHOD = "parity-binding-v1"


class _BindingFailure(Exception):
    def __init__(self, reason: str, role: str | None = None):
        super().__init__(reason)
        self.reason, self.role = reason, role


def _tick(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise _BindingFailure("deadline_exceeded")
    return remaining


def _ref(value: Any) -> ObjectRef:
    # validate_ref's historical regex permits a trailing newline; require exact length too.
    if not isinstance(value, str) or len(value) != 71:
        raise ValueError("invalid ref")
    return validate_ref(value)


def _validate_spec(spec: TaskSpec) -> tuple[str, str, float]:
    try:
        if (spec.kind != "parity-check" or type(spec.kind_version) is not int or spec.kind_version != 1
                or spec.budget != BudgetClass.SMALL or not isinstance(spec.basis_hash, str) or not spec.basis_hash
                or not isinstance(spec.inputs, Mapping) or set(spec.inputs) != {"target", "candidate"}
                or not isinstance(spec.params, Mapping) or set(spec.params) - {"verifier_id", "symbol", "timeout_s"}):
            raise ValueError
        for ref in spec.inputs.values():
            _ref(ref)
        verifier_id = spec.params.get("verifier_id")
        if not isinstance(verifier_id, str) or not re.fullmatch(r"(?:parity:|parity-wasm:)[0-9a-f]{64}", verifier_id):
            raise ValueError
        symbol = spec.params.get("symbol")
        symbol = "" if symbol is None else symbol
        if not isinstance(symbol, str) or "\0" in symbol:
            raise ValueError
        if len(symbol.encode("utf-8")) > 4096:
            raise _BindingFailure("limit_exceeded")
        timeout = spec.params.get("timeout_s")
        if timeout is not None and (type(timeout) not in (int, float) or (type(timeout) is float and not math.isfinite(timeout))):
            raise ValueError
        duration = 60.0 if timeout is None or timeout <= 0 else float(min(timeout, 60))
        # Force the unchanged identity projection before any evidence I/O.
        spec.task_id
        return verifier_id, symbol, duration
    except _BindingFailure:
        raise
    except Exception as exc:
        raise _BindingFailure("invalid_spec") from exc


def _supported_store(objects: ObjectStore) -> None:
    if (type(objects) is not LocalDirStore or os.name != "posix"
            or not all(hasattr(os, name) for name in ("O_NOFOLLOW", "O_DIRECTORY", "waitid", "WNOWAIT"))
            or os.open not in os.supports_dir_fd or objects.size_cap_bytes > 0):
        # Capped LocalDirStore.put can invoke GC; publication must not do that here.
        raise _BindingFailure("transport_unsupported")


def _stream(source, limit: int, deadline: float, *, dest: Path | None = None, retain: bool = False):
    _tick(deadline)
    info = os.fstat(source.fileno())
    if not stat.S_ISREG(info.st_mode):
        raise OSError("not a regular file")
    if info.st_size > limit:
        raise _BindingFailure("limit_exceeded")
    total, hasher, blocks = 0, hashlib.sha256(), []
    output = dest.open("xb") if dest is not None else None
    try:
        while True:
            _tick(deadline)
            chunk = source.read(min(CHUNK_SIZE, limit + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise _BindingFailure("limit_exceeded")
            hasher.update(chunk)
            if output is not None:
                output.write(chunk)
            if retain:
                blocks.append(chunk)
    finally:
        if output is not None:
            output.close()
    _tick(deadline)
    return hasher.hexdigest(), total, b"".join(blocks)


def _local_read(objects: LocalDirStore, ref: ObjectRef, limit: int, deadline: float, role: str,
                *, dest: Path | None = None, proposal: bool = False) -> tuple[bytes, int]:
    unavailable = "proposal_unavailable" if proposal else "input_unavailable"
    integrity = "proposal_binding_invalid" if proposal else "input_integrity_failed"
    try:
        _tick(deadline)
        declared = objects.size(ref)
        if type(declared) is not int or declared < 0:
            raise OSError("invalid size")
        if declared > limit:
            raise _BindingFailure("limit_exceeded", role)
        root = Path(objects.root).absolute()
        relative = Path(objects.path_for(ref)).absolute().relative_to(root)
        if not relative.parts or ".." in relative.parts:
            raise OSError("invalid location")
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in relative.parts[:-1]:
                _tick(deadline)
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                os.close(directory)
                directory = child
            descriptor = os.open(relative.parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            with os.fdopen(descriptor, "rb", buffering=0) as source:
                actual, size, data = _stream(source, limit, deadline, dest=dest, retain=dest is None)
        finally:
            os.close(directory)
        if actual != ref.hex or size != declared:
            raise _BindingFailure(integrity, role)
        return data, size
    except _BindingFailure as exc:
        if exc.role is None and exc.reason == "limit_exceeded":
            exc.role = role
        raise
    except Exception as exc:
        raise _BindingFailure(unavailable, role) from exc


def _file_identity(path: Path, limit: int, deadline: float) -> tuple[str, int]:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb", buffering=0) as source:
        hexdigest, size, _ = _stream(source, limit, deadline)
        return hexdigest, size


def _resolve_selected(verifier_id: str, deadline: float) -> ParityChecker:
    """Resolve existing registrations/discovery without unbounded registration reads."""
    _tick(deadline)
    if verifier_id in PARITY_CHECKERS:
        checker = PARITY_CHECKERS.get(verifier_id)
    elif verifier_id.startswith(NATIVE_PREFIX):
        native = os.environ.get("AGENT_DECOMPILE_OBJDIFF", "").strip() or shutil.which("objdiff")
        if not native:
            raise _BindingFailure("checker_unavailable", "checker")
        checker = ParityChecker(verifier_id, "native", Path(native))
    else:
        from ..corpus.objdiff_check import default_script

        script = default_script()
        root = os.environ.get("AGENT_DECOMPILE_OBJDIFF_WASM_ROOT", "").strip()
        node = shutil.which("node")
        if script is None or not root or not node:
            raise _BindingFailure("checker_unavailable", "checker")
        checker = ParityChecker(verifier_id, "node", script, Path(node), Path(root))
    expected_flavour = "native" if verifier_id.startswith(NATIVE_PREFIX) else "node"
    if checker.flavour != expected_flavour:
        raise _BindingFailure("checker_identity_mismatch", "checker")
    # Pin path selection for this operation, not runtime identity/admission.
    node_path = None
    if checker.flavour == "node":
        selected = shutil.which(str(checker.node)) if checker.node is not None else None
        if selected is None:
            raise _BindingFailure("checker_unavailable", "checker")
        node_path = Path(selected).resolve(strict=True)
    return dataclasses.replace(checker, path=checker.path.resolve(strict=True), node=node_path,
                               wasm_root=checker.wasm_root.resolve(strict=True) if checker.wasm_root else None)


def _checker_files(checker: ParityChecker) -> tuple[Path, ...]:
    if checker.flavour == "native":
        return (checker.path,)
    if checker.wasm_root is None:
        raise _BindingFailure("checker_unavailable", "checker")
    dist = checker.wasm_root / "node_modules" / "objdiff-wasm" / "dist"
    return (checker.path, (dist / "objdiff.js").resolve(strict=True),
            (dist / "objdiff.core.wasm").resolve(strict=True))


def _checker_identity(checker: ParityChecker, files: tuple[Path, ...], deadline: float):
    try:
        identities = tuple(_file_identity(path, ARTIFACT_LIMIT, deadline) for path in files)
    except _BindingFailure as exc:
        if exc.reason == "limit_exceeded":
            exc.role = "checker"
        raise
    except Exception as exc:
        raise _BindingFailure("checker_unavailable", "checker") from exc
    hashes = [value[0] for value in identities]
    verifier_id = NATIVE_PREFIX + hashes[0] if checker.flavour == "native" else WASM_PREFIX + digest("\n".join(hashes).encode())
    return verifier_id, identities


def _await_group_exit(group: int, deadline: float) -> None:
    """After reap, existence can only refuse completion, never authorize a signal.

    A reused group is conservatively unavailable. Signal 0 sends no signal, and
    this loop never terminates anything after releasing the child PID anchor.
    """
    while True:
        try:
            os.killpg(group, 0)
        except ProcessLookupError:
            return
        except OSError as exc:
            raise _BindingFailure("execution_unavailable") from exc
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise _BindingFailure("execution_unavailable")
        time.sleep(min(0.01, remaining))


def _capture(checker: ParityChecker, target: Path, candidate: Path, symbol: str, deadline: float) -> RunOutcome:
    """Bound both pipes and reserve cleanup time. Never reap before the last group signal.

    waitid(WNOWAIT) keeps our child PID reserved, even after exit, so its process group
    cannot be confused with a recycled PID. No poll()/communicate() or post-reap killpg.
    A hostile checker escaping its session is outside P1's runtime admission claim.
    """
    started = time.monotonic()
    remaining = _tick(deadline)
    run_until = deadline - min(1.0, remaining / 4)
    argv = checker.argv(target, candidate, symbol)
    proc = subprocess.Popen(argv, cwd=target.parent, env=checker.env(), stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    limits = {"stdout": RAW_LIMIT, "stderr": STDERR_LIMIT}
    failure = None
    signalled = False
    reaped = False
    try:
        with selectors.DefaultSelector() as selector:
            for name in buffers:
                pipe = getattr(proc, name)
                os.set_blocking(pipe.fileno(), False)
                selector.register(pipe, selectors.EVENT_READ, name)
            while True:
                # A live child or an unreaped zombie is our ownership anchor.
                exited = os.waitid(os.P_PID, proc.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None
                if exited and not signalled:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    signalled = True
                if exited and not selector.get_map():
                    break
                now = time.monotonic()
                if failure is None and now >= run_until:
                    failure = "deadline_exceeded"
                if failure is not None and not signalled:
                    os.killpg(proc.pid, signal.SIGKILL)
                    signalled = True
                if now >= deadline:
                    raise _BindingFailure("execution_unavailable")
                for key, _ in selector.select(min(0.05, deadline - now)):
                    name = key.data
                    available = limits[name] + 1 - len(buffers[name])
                    if available <= 0:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                        continue
                    chunk = os.read(key.fd, min(CHUNK_SIZE, available))
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    buffers[name].extend(chunk)
                    if len(buffers[name]) > limits[name]:
                        failure = "output_limit_exceeded"
            proc.wait(timeout=_tick(deadline))
            reaped = True
            _await_group_exit(proc.pid, deadline)
        if failure:
            raise _BindingFailure(failure)
        return RunOutcome(tuple(argv), proc.returncode, bytes(buffers["stdout"]).decode("utf-8", "replace"),
                          bytes(buffers["stderr"]).decode("utf-8", "replace"), time.monotonic() - started, False)
    finally:
        if not reaped:
            # Never signal if waitid cannot prove this is still our unreaped child.
            try:
                os.waitid(os.P_PID, proc.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except (ChildProcessError, OSError) as exc:
                raise _BindingFailure("execution_unavailable") from exc
            finally:
                try:
                    proc.wait(timeout=max(0.0, deadline - time.monotonic()))
                    _await_group_exit(proc.pid, deadline)
                except (subprocess.TimeoutExpired, OSError) as exc:
                    raise _BindingFailure("execution_unavailable") from exc
                finally:
                    for name in buffers:
                        getattr(proc, name).close()
        else:
            proc.stdout.close()
            proc.stderr.close()


def _normalize(spec: TaskSpec, flavour: str, returncode: int, stdout: str) -> bytes:
    if flavour == "native":
        from ..objdiff_verification import parse_objdiff_report

        report = parse_objdiff_report(returncode, stdout)
    else:
        report = parse_node_report(returncode, stdout)
    receipt = {k: v for k, v in report.items() if k != "output"}
    receipt.update({
        "kind": "parity-check", "kind_version": 1, "verifier_id": spec.params["verifier_id"], "verifier": flavour,
        "sides": {name: ObjectRef(spec.inputs[name]).hex for name in ("target", "candidate")},
        "symbol": spec.params.get("symbol") or "", "grade": str(report.get("status", "error")), "basis_hash": spec.basis_hash,
    })
    if "message" in receipt:
        receipt["message"] = scrub_paths(str(receipt["message"]))
    assert_portable(receipt)
    return canonical_json(receipt)


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _invalid_number(value):
    raise ValueError("nonfinite number")


def _authenticate(spec: TaskSpec, result: TaskResult, objects: LocalDirStore, deadline: float) -> tuple[bytes, dict]:
    try:
        if (result.task_id != spec.task_id or result.basis_hash != spec.basis_hash or result.status != ResultStatus.OK
                or result.reason != "" or not isinstance(result.outputs, Mapping) or set(result.outputs) != {"receipt", "raw"}):
            raise ValueError
        refs = {name: _ref(value) for name, value in result.outputs.items()}
    except Exception as exc:
        raise _BindingFailure("proposal_binding_invalid") from exc
    receipt_bytes, _ = _local_read(objects, refs["receipt"], RECEIPT_LIMIT, deadline, "receipt", proposal=True)
    raw, _ = _local_read(objects, refs["raw"], RAW_LIMIT, deadline, "raw", proposal=True)
    _tick(deadline)
    try:
        receipt = json.loads(receipt_bytes.decode("utf-8"), object_pairs_hook=_unique_pairs, parse_constant=_invalid_number)
        if not isinstance(receipt, dict) or canonical_json(receipt) != receipt_bytes:
            raise ValueError
        grade, differences, code = receipt.get("grade"), receipt.get("differences"), receipt.get("objdiffExit")
        flavour = "native" if spec.params["verifier_id"].startswith(NATIVE_PREFIX) else "node"
        if (receipt.get("schema") != RECEIPT_SCHEMA or receipt.get("kind") != "parity-check"
                or type(receipt.get("kind_version")) is not int or receipt["kind_version"] != 1
                or type(code) is not int or type(differences) is not int or grade != receipt.get("status")
                or grade not in ("matched", "mismatched", "error")
                or (grade == "matched" and (differences != 0 or code != 0))
                or (grade == "mismatched" and (differences < 1 or code not in ((0,) if flavour == "native" else (0, 1))))
                or (grade == "error" and differences != -1)):
            raise ValueError
    except _BindingFailure:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError) as exc:
        raise _BindingFailure("proposal_binding_invalid", "receipt") from exc
    # Parser failures are verifier unavailability, not evidence of a dishonest proposal.
    try:
        expected = _normalize(spec, flavour, code, raw.decode("utf-8", "replace"))
    except Exception as exc:
        raise _BindingFailure("execution_unavailable") from exc
    if expected != receipt_bytes:
        raise _BindingFailure("proposal_binding_invalid", "raw")
    _tick(deadline)
    return receipt_bytes, receipt


def _publish(objects: LocalDirStore, data: bytes, limit: int, deadline: float, role: str) -> ObjectRef:
    _tick(deadline)
    if len(data) > limit:
        raise _BindingFailure("output_limit_exceeded", role)
    expected = ObjectRef.of_bytes(data)
    ref = objects.put(data)
    _tick(deadline)
    if ref != expected:
        raise _BindingFailure("recomputed_binding_invalid", role)
    try:
        retained, _ = _local_read(objects, expected, limit, deadline, role, proposal=True)
        if retained != data:
            raise _BindingFailure("recomputed_binding_invalid", role)
    except _BindingFailure as exc:
        if exc.reason == "deadline_exceeded":
            raise
        raise _BindingFailure("recomputed_binding_invalid", role) from exc
    return expected


def _observe(spec: TaskSpec, objects: LocalDirStore, scratch: str, deadline: float,
             duration: float, checker: ParityChecker, files: tuple[Path, ...]) -> TaskResult:
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="parity-", dir=scratch) as owned:
        paths = {"target": Path(owned) / "target.o", "candidate": Path(owned) / "candidate.obj"}
        expected = {}
        for role, path in paths.items():
            ref = ObjectRef(spec.inputs[role])
            _, size = _local_read(objects, ref, INPUT_LIMIT, deadline, role, dest=path)
            expected[role] = (ref.hex, size)
        for role, path in paths.items():
            try:
                if _file_identity(path, INPUT_LIMIT, deadline) != expected[role]:
                    raise _BindingFailure("execution_changed", role)
            except _BindingFailure as exc:
                if exc.reason == "deadline_exceeded":
                    raise
                raise _BindingFailure("execution_changed", role) from exc
            except OSError as exc:
                raise _BindingFailure("execution_changed", role) from exc
        try:
            if _checker_files(checker) != files:
                raise _BindingFailure("checker_identity_mismatch", "checker")
        except OSError as exc:
            raise _BindingFailure("checker_unavailable", "checker") from exc
        identity, artifacts = _checker_identity(checker, files, deadline)
        if identity != spec.params["verifier_id"]:
            raise _BindingFailure("checker_identity_mismatch", "checker")
        outcome = _capture(checker, paths["target"], paths["candidate"], spec.params.get("symbol") or "", deadline)
        for role, path in paths.items():
            try:
                if _file_identity(path, INPUT_LIMIT, deadline) != expected[role]:
                    raise _BindingFailure("execution_changed", role)
            except _BindingFailure as exc:
                if exc.reason == "deadline_exceeded":
                    raise
                raise _BindingFailure("execution_changed", role) from exc
            except OSError as exc:
                raise _BindingFailure("execution_changed", role) from exc
        try:
            if _checker_files(checker) != files:
                raise _BindingFailure("execution_changed", "checker")
            after_id, after_artifacts = _checker_identity(checker, files, deadline)
            if after_id != spec.params["verifier_id"] or after_artifacts != artifacts:
                raise _BindingFailure("execution_changed", "checker")
        except _BindingFailure as exc:
            if exc.reason == "deadline_exceeded":
                raise
            raise _BindingFailure("execution_changed", "checker") from exc
        except OSError as exc:
            raise _BindingFailure("execution_changed", "checker") from exc
        receipt = _normalize(spec, checker.flavour, outcome.returncode, outcome.stdout)
        raw = outcome.stdout.encode("utf-8", "replace")
        outputs = {"receipt": _publish(objects, receipt, RECEIPT_LIMIT, deadline, "receipt"),
                   "raw": _publish(objects, raw, RAW_LIMIT, deadline, "raw")}
        result = make_result(spec, outputs, elapsed_s=time.monotonic() - started,
                             metrics={"checker_wall_s": round(outcome.elapsed_s, 3), "deadline_s": duration,
                                      "stderr_sha256": outcome.stderr_sha256})
        try:
            _authenticate(spec, result, objects, deadline)
        except _BindingFailure as exc:
            if exc.reason == "deadline_exceeded":
                raise
            raise _BindingFailure("recomputed_binding_invalid", exc.role) from exc
    _tick(deadline)
    return result


def _resolved_files(verifier_id: str, deadline: float):
    try:
        checker = resolve_checker(verifier_id, deadline=deadline)
        files = _checker_files(checker)
        _tick(deadline)
        return checker, files
    except _BindingFailure:
        raise
    except Exception as exc:
        raise _BindingFailure("checker_unavailable", "checker") from exc


# --------------------------------------------------------------------------- the kind
@task_kind
class ParityCheck(PlannableKind):
    name = "parity-check"
    version = 1
    basis_field_set = "parity"        # toolchain + masking rule (§2.8)
    budget = BudgetClass.SMALL
    capabilities = ("parity:<hash> | parity-wasm:<hash>",)   # template; the spec carries verifier_id
    INPUTS: Mapping[str, str] = {"target": "pinned target object (.o from mkobj-target)", "candidate": "candidate COFF object"}
    PARAMS_SCHEMA: Mapping[str, str] = {
        "verifier_id": "parity:<sha256 of native binary> or parity-wasm:<sha256 of script+js+wasm>",
        "symbol": "optional function symbol to compare",
        "timeout_s": "optional kill deadline; capped at SMALL (60 s)",
    }
    OUTPUTS: Mapping[str, str] = {
        "receipt": "verify-objdiff.v1 report (fail-closed), sides named, grade = status",
        "raw": "raw checker stdout (never parsed from stderr)",
    }
    OUTPUT_ROLES: Mapping[str, str] = {"receipt": "public", "raw": "public"}   # §6.3 object role tags

    @staticmethod
    def required_capabilities(spec: TaskSpec) -> tuple[str, ...]:
        return (str(spec.params.get("verifier_id", "")),)

    def run(self, spec: TaskSpec, objects: ObjectStore, scratch: str) -> TaskResult:
        try:
            verifier_id, _, duration = _validate_spec(spec)
            deadline = time.monotonic() + duration
            _supported_store(objects)
            checker, files = _resolved_files(verifier_id, deadline)
            return _observe(spec, objects, scratch, deadline, duration, checker, files)
        except _BindingFailure as exc:
            raise Refused("parity_" + exc.reason) from exc
        except Exception as exc:
            raise Refused("parity_execution_unavailable") from exc

    def verify(self, spec: TaskSpec, result: TaskResult, objects: ObjectStore, scratch: str) -> Verification:
        evidence = {}
        outcome = VerificationOutcome.UNVERIFIABLE
        # A malformed selected spec may not have a computable identity. Its refusal
        # still belongs to the supplied proposal; no new task identity is invented.
        task_id = result.task_id
        try:
            verifier_id, _, duration = _validate_spec(spec)
            task_id = spec.task_id
            deadline = time.monotonic() + duration
            _supported_store(objects)
            proposed_bytes, proposed = _authenticate(spec, result, objects, deadline)
            checker, files = _resolved_files(verifier_id, deadline)
            recomputed = _observe(spec, objects, scratch, deadline, duration, checker, files)
            try:
                repeated_bytes, _ = _authenticate(spec, recomputed, objects, deadline)
            except _BindingFailure as exc:
                if exc.reason == "deadline_exceeded":
                    raise
                raise _BindingFailure("recomputed_binding_invalid", exc.role) from exc
            equal = proposed_bytes == repeated_bytes
            _tick(deadline)
            outcome = VerificationOutcome.VERIFIED if equal else VerificationOutcome.REFUTED
            evidence = {
                "reason": "receipt_equal" if equal else "receipt_differs", "compared": ["receipt"],
                "predicate": "authenticated-checker-observation-v1",
                "comparison_scope": "native-reported-code" if checker.flavour == "native" else "node-reported-symbol-rows",
                "checker_identity_scope": "registered-artifacts-v1", "target_region_complete": False,
                "runtime_admission": "not_evaluated", "grade": proposed["grade"],
                "proposal_outputs": {k: str(v) for k, v in sorted(result.outputs.items())},
                "recomputed_outputs": {k: str(v) for k, v in sorted(recomputed.outputs.items())},
            }
        except _BindingFailure as exc:
            outcome = VerificationOutcome.REFUTED if exc.reason == "proposal_binding_invalid" else VerificationOutcome.UNVERIFIABLE
            evidence = {"reason": exc.reason}
            if exc.role is not None:
                evidence["role"] = exc.role
        except Exception:
            evidence = {"reason": "execution_unavailable"}
        return Verification(task_id=task_id, result_ref=ObjectRef.of_value(result.to_record()), outcome=outcome,
                            verifier_key="", method=METHOD, evidence=evidence)

    @classmethod
    def describe(cls) -> dict[str, Any]:
        return {
            "kind": cls.name, "version": cls.version, "budget": cls.budget.value, "capabilities": list(cls.capabilities),
            "inputs": dict(cls.INPUTS), "params": dict(cls.PARAMS_SCHEMA), "outputs": dict(cls.OUTPUTS), "output_roles": dict(cls.OUTPUT_ROLES),
            "verify": "authenticate and independently reproduce checker observation; complete region/runtime admission not evaluated",
            "checkers_registered": PARITY_CHECKERS.names(), "status": "working",
            "sides": {"native": "-1 <target> -2 <candidate>", "node": "<candidate as base> <target> [symbol]"},
        }


# --------------------------------------------------------------------------- view hook
PARITY_RECEIPT_SQL = """
CREATE TABLE IF NOT EXISTS grid_parity_receipt (
    task_id          TEXT PRIMARY KEY,
    target_sha256    TEXT NOT NULL,
    candidate_sha256 TEXT NOT NULL,
    symbol           TEXT NOT NULL,
    verifier_id      TEXT NOT NULL,
    grade            TEXT NOT NULL,
    differences      INTEGER NOT NULL,
    basis_hash       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_grid_parity_candidate ON grid_parity_receipt(candidate_sha256);
"""


@view_hook(ParityCheck.name)
def apply_parity_receipt(kind: str, result: TaskResult, objects: ObjectStore, con) -> int:
    ref = result.outputs.get("receipt")
    if ref is None or not objects.exists(ref) or result.status != ResultStatus.OK:
        return 0
    r = get_json(objects, ref)
    sides = r.get("sides") or {}
    ensure_tables(con, PARITY_RECEIPT_SQL)
    con.execute(
        "INSERT OR REPLACE INTO grid_parity_receipt VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            result.task_id, str(sides.get("target", "")), str(sides.get("candidate", "")), str(r.get("symbol", "")),
            str(r.get("verifier_id", "")), str(r.get("grade", "error")), int(r.get("differences", -1)),
            str(r.get("basis_hash", result.basis_hash)),
        ),
    )
    return 1


__all__ = [
    "NATIVE_PREFIX", "PARITY_CHECKERS", "ParityCheck", "ParityChecker", "RECEIPT_SCHEMA", "WASM_PREFIX",
    "discover_checkers", "parse_node_report", "register_native", "register_node", "resolve_checker",
]
