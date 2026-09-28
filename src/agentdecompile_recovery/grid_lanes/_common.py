"""Shared helpers for the pipeline's grid lanes (import direction: recovery -> grid only).

Everything a lane kind needs that is not the kind itself: the named refusal classes the corpus
verbs already speak (basis, content hash, lock) as ``GridError`` subclasses; slug hashing; a
subprocess runner with a hard kill deadline; result construction; recompute-based verification;
and the ``SubprocessVerb``-style parameter shape the grid's builtin runner understands.

No absolute path and no plaintext slug ever reaches a receipt: ``scrub_paths`` and
``hashed_slug`` are applied before any text leaves a task.
"""
from __future__ import annotations

import dataclasses
import json
import os
import re
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from agentdecompile_grid.core import (
    DEFAULT_DEADLINES_S,
    BudgetClass,
    GridError,
    NotConfigured,
    ObjectRef,
    ObjectStore,
    Refused,
    ResultStatus,
    TaskResult,
    TaskSpec,
    Verification,
    VerificationOutcome,
    canonical_json,
    digest,
)

# --------------------------------------------------------------------------- named refusals
class BasisRefused(Refused):
    """The store cannot declare one basis (``determinism_basis.BasisError``)."""

    exit_code = 10


class ContentHashRefused(Refused):
    """A build the cascade keys on lacks a usable ``content_sha256`` (``logical.ContentHashError``)."""

    exit_code = 11


class Locked(GridError):
    """The store's write lock was held past ``busy_timeout``; reported by name, never waited on."""

    exit_code = 12


class Infra(GridError):
    """Infrastructure failure inside a task (timeout, no object, no diagnostic): writes nothing."""

    exit_code = 13


def hashed_slug(slug: object) -> str:
    """A build name for a message or receipt: ``sha256(slug)[:12]``, never the slug."""
    return digest(str(slug).encode("utf-8"))[:12]


_LOCK_MARKERS = ("locked", "busy", "readonly", "read-only", "unable to open")


def translate_refusal(exc: BaseException) -> GridError | None:
    """The ``GridError`` for a recovery-side refusal, or ``None`` when *exc* is not one.

    Mirrors ``corpus.cli._refusal_line`` without importing it: the three classes the keyed
    verbs share are mapped to named grid errors with hashed build names.
    """
    from ..corpus.determinism_basis import BasisError
    from ..corpus.logical import ContentHashError

    if isinstance(exc, ContentHashError):
        names = ",".join(hashed_slug(s) for s in getattr(exc, "slugs", ()))
        detail = "shared-by" if getattr(exc, "kind", "") == "duplicate" else "missing-for"
        return ContentHashRefused(f"content-hash:{detail}:{len(getattr(exc, 'slugs', ()))}:[{names}]")
    if isinstance(exc, BasisError):
        return BasisRefused(f"basis:{scrub_paths(str(exc))}")
    if isinstance(exc, sqlite3.OperationalError) and any(m in str(exc).lower() for m in _LOCK_MARKERS):
        return Locked(f"locked:{scrub_paths(str(exc))}")
    return None


# --------------------------------------------------------------------------- scrubbing
_ABS_POSIX = re.compile(r"(?<![\w./])/(?:[^/\s'\"()]+/)+[^/\s'\"()]*")
_ABS_WIN = re.compile(r"\b[A-Za-z]:[\\/][^\s'\"()]*")


def scrub_paths(text: str) -> str:
    """Replace absolute path spellings with ``<path>`` so no host layout leaks into a receipt."""
    text = _ABS_WIN.sub("<path>", text)
    return _ABS_POSIX.sub("<path>", text)


def assert_portable(payload: Any) -> None:
    """Refuse a receipt that carries an absolute path (the landed exchange rule, R1)."""
    from ..exchange.store import assert_portable_payload

    try:
        assert_portable_payload(payload)
    except ValueError as exc:
        raise Refused(f"non-portable-receipt:{scrub_paths(str(exc))}") from exc


# --------------------------------------------------------------------------- subprocesses
@dataclasses.dataclass(frozen=True)
class RunOutcome:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    elapsed_s: float
    timed_out: bool

    @property
    def stdout_sha256(self) -> str:
        return digest(self.stdout.encode("utf-8", "replace"))

    @property
    def stderr_sha256(self) -> str:
        return digest(self.stderr.encode("utf-8", "replace"))


def deadline_for(budget: BudgetClass, requested_s: float | None = None) -> float:
    """The kill deadline a task may use: never more than its class allows."""
    cap = DEFAULT_DEADLINES_S[budget]
    if requested_s is None or requested_s <= 0:
        return float(cap)
    return float(min(requested_s, cap)) if cap else float(requested_s)


def run_argv(
    argv: Sequence[str],
    *,
    cwd: str | Path,
    timeout_s: float,
    env: Mapping[str, str] | None = None,
    stdin_bytes: bytes | None = None,
) -> RunOutcome:
    """Run *argv* in its own process group; SIGTERM at the deadline, SIGKILL 5 s later.

    The worker owns the class deadline (design §2.7); this runner is the kind's own guard so a
    kind never outlives its budget even when driven outside the worker (the CLI's ``--once``).
    """
    started = time.monotonic()
    popen_kwargs: dict[str, Any] = {
        "cwd": str(cwd), "stdout": subprocess.PIPE, "stderr": subprocess.PIPE,
        "stdin": subprocess.PIPE if stdin_bytes is not None else subprocess.DEVNULL,
        "env": dict(env) if env is not None else None,
    }
    if os.name != "nt":
        popen_kwargs["start_new_session"] = True
    proc = subprocess.Popen([str(a) for a in argv], **popen_kwargs)
    timed_out = False
    try:
        out, err = proc.communicate(input=stdin_bytes, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_group(proc, signal.SIGTERM if os.name != "nt" else None)
        try:
            out, err = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            _kill_group(proc, signal.SIGKILL if os.name != "nt" else None)
            out, err = proc.communicate()
    elapsed = time.monotonic() - started
    return RunOutcome(
        argv=tuple(str(a) for a in argv), returncode=int(proc.returncode if proc.returncode is not None else -1),
        stdout=(out or b"").decode("utf-8", "replace"), stderr=(err or b"").decode("utf-8", "replace"),
        elapsed_s=elapsed, timed_out=timed_out,
    )


def _kill_group(proc: subprocess.Popen, sig) -> None:
    try:
        if sig is None:
            proc.kill()
        else:
            os.killpg(proc.pid, sig)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except OSError:
            pass


def corpus_cli_argv(verb: str, *args: str) -> list[str]:
    """``python -m agentdecompile_recovery.corpus.cli <verb> ...`` under the running interpreter."""
    return [sys.executable, "-m", "agentdecompile_recovery.corpus.cli", verb, *args]


def subprocess_verb_params(
    *, argv: Sequence[str], outputs: Mapping[str, str], timeout_s: float,
    env: Mapping[str, str] | None = None, cwd: str = "{scratch}",
) -> dict[str, Any]:
    """The ``SubprocessVerb``-style parameter shape (``agentdecompile_grid.tasks.builtin``).

    ``{store}`` / ``{scratch}`` / ``{out}`` placeholders name the materialised input object, the
    scratch directory and the output directory; ``outputs`` maps output names to files under
    ``{out}`` that become objects.  A lane renders this so the grid's builtin runner can execute
    the verb identically to the lane's own ``run``.
    """
    return {
        "argv": [str(a) for a in argv], "cwd": cwd, "timeout_s": float(timeout_s),
        "env": dict(env or {}), "outputs": dict(outputs),
    }


# --------------------------------------------------------------------------- objects / results
def materialize_object(objects: ObjectStore, ref: ObjectRef, path: Path) -> Path:
    """Write the object at *ref* to *path* (a task's scratch copy of an input).

    Uses the store's streaming ``get_path(ref, path)`` when it has one (a store snapshot is
    GB-sized); the Protocol's ``get`` -> bytes otherwise.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    get_path = getattr(objects, "get_path", None)
    if callable(get_path):
        get_path(ref, path)
        return path
    path.write_bytes(objects.get(ref))
    return path


def put_file(objects: ObjectStore, path: Path) -> ObjectRef:
    """Put a file's bytes; streams through ``put_path(path)`` when the store offers it."""
    put_path = getattr(objects, "put_path", None)
    if callable(put_path):
        return ObjectRef(put_path(path))
    return objects.put(path.read_bytes())


def put_json(objects: ObjectStore, value: Any) -> ObjectRef:
    return objects.put(canonical_json(value))


def get_json(objects: ObjectStore, ref: ObjectRef) -> Any:
    return json.loads(objects.get(ref).decode("utf-8"))


def make_result(
    spec: TaskSpec,
    outputs: Mapping[str, ObjectRef],
    *,
    elapsed_s: float,
    status: ResultStatus = ResultStatus.OK,
    reason: str = "",
    candidates: Sequence[Mapping[str, Any]] = (),
    metrics: Mapping[str, Any] | None = None,
    producer_key: str = "",
) -> TaskResult:
    """A ``TaskResult`` for *spec*.  ``producer_key`` is stamped by the worker (it holds the key)."""
    return TaskResult(
        task_id=spec.task_id, status=status, outputs=dict(outputs), producer_key=producer_key,
        basis_hash=spec.basis_hash, elapsed_s=elapsed_s, reason=reason,
        candidates=tuple(candidates), metrics=dict(metrics or {}),
    )


def require_param(spec: TaskSpec, name: str, *, kind: str) -> Any:
    if name not in spec.params:
        raise Refused(f"missing-param:{kind}:{name}")
    return spec.params[name]


def require_input(spec: TaskSpec, name: str, *, kind: str) -> ObjectRef:
    if name not in spec.inputs:
        raise Refused(f"missing-input:{kind}:{name}")
    return ObjectRef(spec.inputs[name])


def check_kind(spec: TaskSpec, kind_name: str, kind_version: int) -> None:
    """Refusal first, at 1 ms: a spec of another kind or version never fetches an input."""
    if spec.kind != kind_name:
        raise Refused(f"kind-mismatch:{spec.kind}!={kind_name}")
    if spec.kind_version != kind_version:
        raise Refused(f"kind-version-mismatch:{spec.kind}:{spec.kind_version}!={kind_version}")
    if not spec.basis_hash:
        raise Refused(f"basis-required:{kind_name}")


def verify_by_recompute(
    kind: Any, spec: TaskSpec, result: TaskResult, objects: ObjectStore, scratch: str,
    *, compare: Sequence[str] | None = None, method: str = "recompute",
) -> Verification:
    """Re-run *kind* on this node and compare the content addresses of its outputs.

    Outputs are content-addressed, so equality of refs is equality of bytes.  A kind whose
    outputs carry per-run noise must keep that noise in ``metrics`` (not in an output) or pass
    *compare* to name the load-bearing outputs.  Refusals during recompute are UNVERIFIABLE with
    the reason in evidence; a capability this node lacks is likewise UNVERIFIABLE, never REFUTED.
    """
    result_refs = {k: str(v) for k, v in result.outputs.items()}
    try:
        recomputed = kind.run(spec, objects, scratch)
    except Refused as exc:
        return Verification(
            task_id=spec.task_id, result_ref=ObjectRef.of_value(result.to_record()),
            outcome=VerificationOutcome.UNVERIFIABLE, verifier_key="", method=method,
            evidence={"reason": exc.reason},
        )
    names = list(compare) if compare else sorted(set(result_refs) | set(recomputed.outputs))
    mismatched = [
        n for n in names if result_refs.get(n) != (str(recomputed.outputs[n]) if n in recomputed.outputs else None)
    ]
    status_same = recomputed.status == result.status and recomputed.reason == result.reason
    outcome = VerificationOutcome.VERIFIED if not mismatched and status_same else VerificationOutcome.REFUTED
    return Verification(
        task_id=spec.task_id, result_ref=ObjectRef.of_value(result.to_record()), outcome=outcome,
        verifier_key="", method=method,
        evidence={
            "compared": names, "mismatched": mismatched,
            "status": {"proposal": result.status.value, "recomputed": recomputed.status.value},
            "recomputed_outputs": {k: str(v) for k, v in sorted(recomputed.outputs.items())},
        },
    )


def not_present(module: str) -> NotConfigured:
    return NotConfigured(f"{module} not present in this checkout yet")


class PlannableKind:
    """Mixin: ``Kind.plan(...)`` is how the grid CLI reaches a lane's planner without importing it.

    ``adgrid publish <kind>`` duck-types ``TASK_KINDS.get(kind).plan`` (the grid never imports
    ``agentdecompile_recovery``); the call goes through ``splitter.plan_tasks``, the one
    chokepoint for the never-awaited rule.  Returns the specs; every spec carries its basis.
    """

    name = ""

    @classmethod
    def plan(
        cls, objects: ObjectStore, store_snapshot: Any, *, basis_hash: str | None = None, shard_size: int = 512,
        max_budget: BudgetClass = BudgetClass.SMALL, scratch: str | None = None, **options: Any,
    ) -> list[TaskSpec]:
        from .splitter import plan_tasks

        return plan_tasks(
            cls.name, store_snapshot, basis_hash, shard_size, objects=objects, max_budget=max_budget,
            scratch=scratch, **options,
        )


__all__ = [
    "BasisRefused", "ContentHashRefused", "Infra", "Locked", "PlannableKind", "RunOutcome", "assert_portable",
    "check_kind", "corpus_cli_argv", "deadline_for", "get_json", "hashed_slug", "make_result",
    "materialize_object", "not_present", "put_file", "put_json", "require_input", "require_param", "run_argv",
    "scrub_paths", "subprocess_verb_params", "translate_refusal", "verify_by_recompute",
]
