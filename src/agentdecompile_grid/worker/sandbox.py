"""Sandboxes: where a task kind's ``run``/``verify`` executes, with a hard kill deadline owned by the worker.

``SubprocessSandbox`` (working) launches ``python -m agentdecompile_grid.worker.sandbox <manifest>``
in a **new session** (``start_new_session=True`` → its own process group) so the deadline kills
the whole tree with ``os.killpg``: SIGTERM at the deadline, SIGKILL ``grace_s`` later, and a named
``kill-failed`` outcome if the group still exists after a second grace (a D-state child is
reported, never waited for).  The kill is a two-phase state machine driven by ``poll()``; nothing
blocks the caller's step.  Escapees that call ``setsid`` themselves are the documented limit of
this sandbox; ``ContainerSandbox`` (declared) is the answer to that.

The child applies its own ``resource.setrlimit`` limits (core=0, files, file size, address space,
CPU seconds = deadline + grace as a belt-and-braces bound), gets a fresh scratch directory as
``HOME``/``TMPDIR``/cwd, an environment reduced to an allowlist, imports the modules that register
the task kinds, resolves the object store from a serialisable *locator*
(``{"adapter": "local", "root": ...}`` → ``OBJECT_STORES.get("local")``; ``from_locator`` is
preferred when the adapter offers it), and writes ``result.json`` last, by rename, so a killed
child leaves no partial result and no partial object (object puts are content-addressed).

Manifest (written by the parent):
``{"job_id", "op": run|verify|method, "spec": TaskSpec.to_record(), "result": TaskResult record | null,
  "method": str | null, "key_id", "lineage", "import_modules": [...], "store": locator,
  "deadline_s", "grace_s", "limits": {...}, "scratch"}``

Acceptance tests named for the final verification phase (U124):
  * ``test_sleep_forever_is_killed_at_deadline``: a kind that sleeps forever is killed at its class
    deadline; the outcome is ``timeout`` with ``kill_action`` in {terminated, killed} and the
    RESULT record exists within deadline + 5 s.
  * ``test_killed_child_leaves_no_partial_result``: no ``result.json`` and no partial object after
    a kill.
  * ``test_process_group_killed``: a kind that spawns a grandchild leaves no live grandchild after
    the deadline (same session).
  * ``test_env_allowlist_and_limits``: the child sees only allowlisted variables plus HOME/TMPDIR
    set to scratch, and the configured rlimits are in force.
  * ``test_store_locator_resolves``: a job with a local locator gives the kind a store whose
    ``put`` is visible to the parent.
"""
from __future__ import annotations

import importlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from ..core import OBJECT_STORES, TASK_KINDS, VERIFIERS, BudgetClass, DEFAULT_DEADLINES_S, NotConfigured, ObjectStore, Refused, Registry, ResultStatus, TaskResult, TaskSpec, Verification, canonical_json, digest

DEFAULT_ENV_ALLOWLIST: tuple[str, ...] = (
    "PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "PYTHONPATH", "PYTHONHASHSEED", "PYTHONDONTWRITEBYTECODE", "PYTHONUNBUFFERED",
    "VIRTUAL_ENV", "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE",
)
DEFAULT_LIMITS: Mapping[str, int] = {
    "RLIMIT_CORE": 0,
    "RLIMIT_NOFILE": 1024,
    "RLIMIT_FSIZE": 4 * 1024 * 1024 * 1024,
    "RLIMIT_AS": 0,              # 0 = leave unlimited (the analyzer's JVM needs address space)
}
DEFAULT_GRACE_S = 5.0            # design §2.7: SIGTERM then SIGKILL after 5 s
RESULT_FILE = "result.json"
ERROR_FILE = "error.json"
MANIFEST_FILE = "manifest.json"
STDERR_FILE = "stderr.log"
STDOUT_FILE = "stdout.log"
OPS = ("run", "verify", "method")


class SandboxError(Exception):
    """Named launch failure (interpreter missing, scratch not writable...)."""


# --------------------------------------------------------------------------- job description
@dataclass(frozen=True)
class SandboxJob:
    job_id: str
    op: str                                   # run | verify | method
    spec: TaskSpec
    key_id: str
    lineage: Sequence[str]
    deadline_s: float
    store_locator: Mapping[str, Any]
    import_modules: Sequence[str] = ()
    result: TaskResult | None = None          # for verify/method
    method: str | None = None                 # for method
    grace_s: float = DEFAULT_GRACE_S
    limits: Mapping[str, int] = field(default_factory=lambda: dict(DEFAULT_LIMITS))
    env_extra: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.op not in OPS:
            raise ValueError(f"op must be one of {OPS}, not {self.op!r}")
        if self.op in ("verify", "method") and self.result is None:
            raise ValueError(f"op {self.op!r} needs a result")
        if self.op == "method" and not self.method:
            raise ValueError("op 'method' needs a method name")
        if self.deadline_s <= 0:
            raise ValueError("deadline_s must be positive (UNBOUNDED kinds are refused before a job exists)")

    def manifest(self, scratch: str) -> dict[str, Any]:
        return {
            "job_id": self.job_id, "op": self.op, "spec": self.spec.to_record(), "result": self.result.to_record() if self.result else None,
            "method": self.method, "key_id": self.key_id, "lineage": list(self.lineage), "import_modules": list(self.import_modules),
            "store": dict(self.store_locator), "deadline_s": float(self.deadline_s), "grace_s": float(self.grace_s), "limits": dict(self.limits), "scratch": scratch,
        }


@dataclass(frozen=True)
class JobOutcome:
    status: str                               # ok | error | timeout | kill-failed | launch-failed
    exit_code: int | None
    payload: Mapping[str, Any] | None         # parsed result.json (TaskResult or Verification record)
    elapsed_s: float
    stderr_digest: str = ""
    error_class: str = ""
    kill_action: str = ""                     # "" | terminated | killed | kill-failed


class RunningJob(Protocol):
    job: SandboxJob
    started_at: float

    def poll(self, now: float) -> str: ...            # running | terminating | killing | exited | kill-failed
    def request_kill(self, now: float) -> None: ...  # begin the two-phase kill (idempotent)
    def collect(self, now: float) -> JobOutcome: ... # after poll() said exited/kill-failed
    def cleanup(self) -> None: ...


class Sandbox(Protocol):
    name: str

    def launch(self, job: SandboxJob) -> RunningJob: ...
    def describe(self) -> Mapping[str, Any]: ...


SANDBOXES = Registry("sandbox")


# --------------------------------------------------------------------------- working: subprocess group
class SubprocessJob:
    def __init__(self, job: SandboxJob, proc: subprocess.Popen[bytes], scratch: Path, started_at: float, *, keep_scratch: str, sweep_group_on_exit: bool = True) -> None:
        self.job = job
        self.proc = proc
        self.scratch = scratch
        self.started_at = started_at
        self.keep_scratch = keep_scratch
        self.sweep_group_on_exit = sweep_group_on_exit
        self.term_sent_at: float | None = None
        self.kill_sent_at: float | None = None
        self.kill_action = ""
        self.exited_at: float | None = None
        self._returncode: int | None = None

    # -- state
    @property
    def pgid(self) -> int:
        return self.proc.pid

    def _signal_group(self, sig: int) -> bool:
        try:
            os.killpg(self.pgid, sig)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return False

    def request_kill(self, now: float) -> None:
        if self.term_sent_at is None and self._returncode is None:
            self.term_sent_at = now
            self._signal_group(signal.SIGTERM)

    def poll(self, now: float) -> str:
        if self._returncode is None:
            rc = self.proc.poll()              # reaps the direct child when it has exited
            if rc is not None:
                self._returncode = rc
                self.exited_at = now
                if self.term_sent_at is not None:
                    self.kill_action = self.kill_action or ("killed" if self.kill_sent_at is not None else "terminated")
                if self.term_sent_at is not None or self.sweep_group_on_exit:
                    self._signal_group(signal.SIGKILL)   # nothing a task started outlives it (persistent helpers belong to the agent, not a task)
        if self._returncode is not None:
            return "exited"
        if self.term_sent_at is None:
            return "running"
        if self.kill_sent_at is None:
            if now - self.term_sent_at >= self.job.grace_s:
                self.kill_sent_at = now
                self._signal_group(signal.SIGKILL)
            return "terminating"
        if now - self.kill_sent_at >= self.job.grace_s:
            self.kill_action = "kill-failed"
            return "kill-failed"
        return "killing"

    def collect(self, now: float) -> JobOutcome:
        elapsed = (self.exited_at if self.exited_at is not None else now) - self.started_at
        stderr_digest = digest(_read_bytes(self.scratch / STDERR_FILE))
        if self.kill_action == "kill-failed":
            return JobOutcome("kill-failed", None, None, elapsed, stderr_digest, kill_action="kill-failed")
        if self.term_sent_at is not None:
            return JobOutcome("timeout", self._returncode, None, elapsed, stderr_digest, kill_action=self.kill_action or "terminated")
        payload = _read_json(self.scratch / RESULT_FILE)
        if self._returncode == 0 and payload is not None:
            return JobOutcome("ok", 0, payload, elapsed, stderr_digest)
        error = _read_json(self.scratch / ERROR_FILE) or {}
        return JobOutcome("error", self._returncode, None, elapsed, stderr_digest, error_class=str(error.get("class", "")) or f"exit:{self._returncode}")

    def cleanup(self) -> None:
        keep = self.keep_scratch == "always" or (self.keep_scratch == "on-failure" and (self._returncode not in (0,) or self.term_sent_at is not None))
        if not keep:
            shutil.rmtree(self.scratch, ignore_errors=True)


class SubprocessSandbox:
    name = "subprocess"

    def __init__(self, work_root: str | os.PathLike[str], *, python: str = sys.executable, env_allowlist: Sequence[str] = DEFAULT_ENV_ALLOWLIST,
                 base_env: Mapping[str, str] | None = None, propagate_sys_path: bool = True, keep_scratch: str = "on-failure", sweep_group_on_exit: bool = True,
                 clock: Callable[[], float] = time.monotonic, popen: Callable[..., subprocess.Popen[bytes]] = subprocess.Popen) -> None:
        if keep_scratch not in ("never", "on-failure", "always"):
            raise ValueError("keep_scratch must be never|on-failure|always")
        self.work_root = Path(work_root)
        self.python = python
        self.env_allowlist = tuple(env_allowlist)
        self.base_env = dict(os.environ if base_env is None else base_env)
        self.propagate_sys_path = propagate_sys_path
        self.keep_scratch = keep_scratch
        self.sweep_group_on_exit = sweep_group_on_exit
        self.clock = clock
        self.popen = popen

    def child_env(self, job: SandboxJob, scratch: Path) -> dict[str, str]:
        env = {k: v for k, v in self.base_env.items() if k in self.env_allowlist}
        if self.propagate_sys_path:
            existing = env.get("PYTHONPATH", "")
            entries = [p for p in sys.path if p] + ([existing] if existing else [])
            env["PYTHONPATH"] = os.pathsep.join(dict.fromkeys(entries))
        env["HOME"] = str(scratch)
        env["TMPDIR"] = str(scratch / "tmp")
        env["ADGRID_JOB_ID"] = job.job_id
        env.update({k: str(v) for k, v in job.env_extra.items()})
        return env

    def launch(self, job: SandboxJob) -> SubprocessJob:
        scratch = self.work_root / job.job_id
        try:
            (scratch / "tmp").mkdir(parents=True, exist_ok=False)
        except FileExistsError as exc:
            raise SandboxError(f"scratch {scratch} already exists (job id reused)") from exc
        except OSError as exc:
            raise SandboxError(f"cannot create scratch {scratch}: {exc.__class__.__name__}") from exc
        manifest_path = scratch / MANIFEST_FILE
        _write_atomic(manifest_path, json.dumps(job.manifest(str(scratch)), sort_keys=True).encode("utf-8"))
        stdout = open(scratch / STDOUT_FILE, "wb")
        stderr = open(scratch / STDERR_FILE, "wb")
        try:
            proc = self.popen(
                [self.python, "-m", "agentdecompile_grid.worker.sandbox", str(manifest_path)],
                cwd=str(scratch), env=self.child_env(job, scratch), stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                start_new_session=True, close_fds=True,
            )
        except OSError as exc:
            stdout.close()
            stderr.close()
            raise SandboxError(f"cannot launch {self.python}: {exc.__class__.__name__}") from exc
        finally:
            if not stdout.closed:
                stdout.close()
            if not stderr.closed:
                stderr.close()
        return SubprocessJob(job, proc, scratch, self.clock(), keep_scratch=self.keep_scratch, sweep_group_on_exit=self.sweep_group_on_exit)

    def describe(self) -> Mapping[str, Any]:
        return {"name": self.name, "status": "working", "kills": "process group (SIGTERM, SIGKILL after grace)", "limits": dict(DEFAULT_LIMITS), "env_allowlist": list(self.env_allowlist), "escapes": "children that setsid() themselves (use container)"}


# --------------------------------------------------------------------------- declared: container
class ContainerSandbox:
    """Runs the same child entry inside a rootless container so nothing escapes the kill."""

    name = "container"
    CONFIG_SCHEMA: Mapping[str, str] = {
        "runtime": "podman or docker binary on PATH (rootless)", "image_digest": "content-addressed image holding the slim distribution",
        "work_root": "host directory bind-mounted as scratch", "store_mount": "host object store directory bind-mounted read-write",
    }

    def __init__(self, **config: Any) -> None:
        self.config = dict(config)

    def launch(self, job: SandboxJob) -> RunningJob:
        runtime = self.config.get("runtime") or "podman"
        found = shutil.which(runtime)
        missing = [k for k in self.CONFIG_SCHEMA if not self.config.get(k)]
        raise NotConfigured(f"container sandbox is declared only; needs {runtime!r} on PATH ({'found' if found else 'missing'}) and config {missing or 'complete'}; use SubprocessSandbox")

    def describe(self) -> Mapping[str, Any]:
        return {"name": self.name, "status": "declared", "needs": [k for k in self.CONFIG_SCHEMA if not self.config.get(k)], "config_schema": dict(self.CONFIG_SCHEMA)}


SANDBOXES.register("subprocess", SubprocessSandbox)
SANDBOXES.register("container", ContainerSandbox)


def deadline_for(spec: TaskSpec, overrides: Mapping[str, Any] | None = None) -> float:
    """Kill deadline from the budget class (core ``DEFAULT_DEADLINES_S``), overridable per budget
    value or per kind name (the basis ``timeout_policy`` field).  ``UNBOUNDED`` → ``Refused``."""
    overrides = overrides or {}
    if spec.kind in overrides:
        value = float(overrides[spec.kind])
    elif spec.budget.value in overrides:
        value = float(overrides[spec.budget.value])
    else:
        value = float(DEFAULT_DEADLINES_S[spec.budget])
    if spec.budget == BudgetClass.UNBOUNDED or value <= 0:
        raise Refused(f"budget-unbounded:{spec.kind}")
    return value


# --------------------------------------------------------------------------- child side
def resolve_store(locator: Mapping[str, Any]) -> ObjectStore:
    adapter = str(locator.get("adapter", ""))
    if not adapter:
        raise NotConfigured("store locator has no 'adapter' (expected e.g. {'adapter': 'local', 'root': <dir>})")
    try:
        cls = OBJECT_STORES.get(adapter)
    except KeyError as exc:
        raise NotConfigured(f"object store adapter {adapter!r} is not registered in this process; import agentdecompile_grid.objects (LocalDirStore(root) registers 'local')") from exc
    args = {k: v for k, v in locator.items() if k != "adapter"}
    if hasattr(cls, "from_locator"):
        return cls.from_locator(dict(locator))
    return cls(**args)


def apply_limits(limits: Mapping[str, int], *, cpu_seconds: float | None = None) -> dict[str, str]:
    """``setrlimit`` where available; returns what was applied or why not, by name."""
    applied: dict[str, str] = {}
    try:
        import resource
    except ImportError:
        return {"resource": "unavailable"}
    wanted = dict(limits)
    if cpu_seconds and not wanted.get("RLIMIT_CPU"):
        wanted["RLIMIT_CPU"] = int(cpu_seconds) + 1
    for name, value in wanted.items():
        if not value:
            applied[name] = "unset"
            continue
        res = getattr(resource, name, None)
        if res is None:
            applied[name] = "unsupported"
            continue
        try:
            soft, hard = resource.getrlimit(res)
            new = int(value) if hard == resource.RLIM_INFINITY else min(int(value), hard)
            resource.setrlimit(res, (new, hard))
            applied[name] = str(new)
        except (ValueError, OSError) as exc:
            applied[name] = f"refused:{exc.__class__.__name__}"
    return applied


def _instantiate_kind(name: str) -> Any:
    kind = TASK_KINDS.get(name)
    return kind() if isinstance(kind, type) else kind


def run_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Execute one manifest in-process (the child calls this; the harness may call it directly)."""
    for module in manifest.get("import_modules", ()):
        importlib.import_module(module)
    store = resolve_store(manifest["store"])
    spec = TaskSpec.from_record(manifest["spec"])
    kind = _instantiate_kind(spec.kind)
    scratch = str(manifest["scratch"])
    key_id = str(manifest["key_id"])
    op = manifest["op"]
    started = time.monotonic()
    if op == "run":
        try:
            result = kind.run(spec, store, scratch)
        except Refused as exc:
            result = TaskResult(spec.task_id, ResultStatus.REFUSED, {}, key_id, spec.basis_hash, time.monotonic() - started, reason=exc.reason, candidates=exc.candidates)
        if result.task_id != spec.task_id:
            raise SandboxError(f"kind {spec.kind} returned a result for another task")
        result = replace(result, producer_key=key_id, basis_hash=spec.basis_hash, elapsed_s=result.elapsed_s or (time.monotonic() - started))
        return result.to_record()
    from .records import task_result_from_record, verification_to_record

    result = task_result_from_record(manifest["result"])
    if op == "verify":
        verification = kind.verify(spec, result, store, scratch)
    else:
        importlib.import_module("agentdecompile_grid.verify.methods")      # registers the built-in VERIFIERS in this child
        method = VERIFIERS.get(str(manifest["method"]))
        verification = method(spec, result, store, scratch, key_id)
    if not isinstance(verification, Verification):
        raise SandboxError("verify did not return a Verification")
    verification = replace(verification, verifier_key=key_id)
    return verification_to_record(verification)


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        sys.stderr.write("usage: python -m agentdecompile_grid.worker.sandbox <manifest.json>\n")
        return 64
    manifest_path = Path(argv[0])
    scratch: Path | None = None
    try:
        manifest = json.loads(manifest_path.read_text("utf-8"))
        scratch = Path(manifest["scratch"])
        os.chdir(scratch)
        wall_budget = float(manifest.get("deadline_s", 0)) + float(manifest.get("grace_s", 0))
        applied = apply_limits(manifest.get("limits", {}), cpu_seconds=wall_budget * max(1, os.cpu_count() or 1))   # CPU time sums over threads; a bound against escapees, not the deadline
        _write_atomic(scratch / "limits.json", json.dumps(applied, sort_keys=True).encode("utf-8"))
        payload = run_manifest(manifest)
        _write_atomic(scratch / RESULT_FILE, canonical_json(payload))
        return 0
    except NotConfigured as exc:
        _write_error(scratch, "NotConfigured", str(exc))
        return 3
    except Exception as exc:  # the class is recorded; the message is digested, never shipped
        _write_error(scratch, exc.__class__.__name__, str(exc))
        sys.stderr.write(traceback.format_exc())
        return 1


def _write_error(scratch: Path | None, cls: str, message: str) -> None:
    if scratch is None:
        return
    try:
        _write_atomic(scratch / ERROR_FILE, json.dumps({"class": cls, "message_digest": digest(message.encode("utf-8"))}, sort_keys=True).encode("utf-8"))
    except OSError:
        pass


# --------------------------------------------------------------------------- helpers
def _write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError:
        return b""


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


__all__ = [
    "ContainerSandbox", "DEFAULT_ENV_ALLOWLIST", "DEFAULT_GRACE_S", "DEFAULT_LIMITS", "ERROR_FILE", "JobOutcome", "MANIFEST_FILE", "OPS", "RESULT_FILE",
    "RunningJob", "SANDBOXES", "Sandbox", "SandboxError", "SandboxJob", "SubprocessJob", "SubprocessSandbox", "apply_limits", "deadline_for", "main",
    "resolve_store", "run_manifest",
]


if __name__ == "__main__":  # pragma: no cover - the child entry
    sys.exit(main())
