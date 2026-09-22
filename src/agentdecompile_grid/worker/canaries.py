"""Capability canaries: a capability exists only after a fixed piece of work hashes to its pin.

``core.Canary`` is the protocol (``capability``, ``prove(objects, scratch) -> (ok, evidence)``) and
``core.CANARIES`` the registry.  One canary works everywhere (``python``: canonical-encode and hash
a pinned fixture); the others are declared with their config schema and raise ``NotConfigured``
naming the probe object or binary they need:

* ``python``               working — pinned fixture digest (canonical JSON + a byte pattern).
* ``toolchain``            compile a fixed translation unit under ``toolchain_path``; the masked
                           object hash must equal the pin.  Capability ``toolchain:<identity_hash>``.
* ``analyzer``             open a fixture packed program headless; hash its function inventory.
                           Capability ``analyzer:<version>:<options_hash>``.
* ``parity``               run the hash-pinned parity checker on a fixture pair; the receipt must
                           equal the pin.  Capability ``parity:<checker_hash>``.
* ``browser``              proven only by the browser lane's own wasm fixture; never on a node.

``run_canaries`` gives every canary a backstop wall-clock deadline (canaries that spawn processes
must enforce their own through the sandbox; this is the last line) and returns a ``CanaryReport``;
``prove_all(identity, objects, scratch)`` returns the proven capability list.

Acceptance tests named for the final verification phase (U125):
  * ``test_python_canary_pins``: the python canary passes on this interpreter and fails when the
    pin is perturbed by one hex digit.
  * ``test_capability_only_after_pin``: a toolchain canary whose masked hash differs from the pin
    yields no ``toolchain:<hash>`` capability and a failed report row naming ``pin-mismatch``.
  * ``test_declared_canaries_name_their_needs``: each declared canary's ``NotConfigured`` message
    names the probe object, binary or path it needs and ``describe()`` lists ``needs``.
  * ``test_canary_deadline``: a canary that never returns is reported as ``timeout`` within the
    backstop deadline and proves nothing.
"""
from __future__ import annotations

import hashlib
import os
import platform
import shlex
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from ..core import CANARIES, GRID_SCHEMA_VERSION, Canary, NodeIdentity, NotConfigured, ObjectRef, ObjectStore, canonical_json, digest

PYTHON_FIXTURE: Mapping[str, Any] = {
    "schema": GRID_SCHEMA_VERSION,
    "fixture": "python-canary",
    "ints": [0, 1, -1, 2**31, 2**53, -(2**63), 2**64 + 1],
    "floats": [0.0, 0.1, 0.1 + 0.2, 1e-7, 1.5e300, 3.141592653589793, -2.5e-15],
    "text": "grid ✓ — ünïcödé ☃ \U0001F600 tab\tnl\n",
    "nested": {"b": [1, {"a": None, "t": True, "f": False}], "a": "", "z": {}},
    "order": {"10": 1, "9": 2, "b": 3, "B": 4, "a": 5},
}
PYTHON_FIXTURE_BYTES = bytes(range(256)) * 64
PYTHON_CANARY_DIGEST = "2d3ad952c89f59389fd5b7137681ea80df2d1176be6099bfc107f1c95f9eabe9"
DEFAULT_CANARY_DEADLINE_S = 120.0


def python_fixture_digest() -> str:
    return digest(canonical_json(PYTHON_FIXTURE) + digest(PYTHON_FIXTURE_BYTES).encode("ascii"))


# --------------------------------------------------------------------------- working: python
class PythonCanary:
    capability = "python"
    name = "python"

    def __init__(self, expected: str = PYTHON_CANARY_DIGEST) -> None:
        self.expected = expected

    def prove(self, objects: ObjectStore, scratch: str) -> tuple[bool, Mapping[str, Any]]:
        got = python_fixture_digest()
        evidence = {
            "digest": got, "expected": self.expected,
            "python": platform.python_version(), "implementation": platform.python_implementation(), "machine": platform.machine(),
        }
        return got == self.expected, evidence

    def describe(self) -> Mapping[str, Any]:
        return {"name": self.name, "capability": self.capability, "status": "working", "needs": [], "pin": self.expected}


# --------------------------------------------------------------------------- declared: toolchain
class ToolchainCanary:
    """Compile ``probe_ref`` (a fixed translation unit object) with the toolchain at
    ``toolchain_path``; ``masker`` strips timestamps/paths from the object; the masked hash must
    equal ``expected_masked_hash``.  Every join therefore measures cross-host compile determinism
    for free (design §1.5).  Capability ``toolchain:<identity_hash>``.

    ``compile_command`` is a template: ``{toolchain} {source} {output}`` are substituted, the
    command runs in ``scratch`` with the deadline; nothing else is interpolated."""

    name = "toolchain"
    CONFIG_SCHEMA: Mapping[str, str] = {
        "toolchain_path": "directory holding the era-exact toolchain tree (content hash = identity)",
        "identity_hash": "toolchain_identity_hash (content address of the toolchain tree; grid_lanes/toolchain)",
        "probe_ref": "ObjectRef of the fixed probe translation unit",
        "expected_masked_hash": "sha256 hex of the masked probe object under this toolchain",
        "compile_command": "shell template with {toolchain} {source} {output}",
        "masker": "callable(bytes) -> bytes stripping non-deterministic fields (verify/masked_coff, U127)",
    }

    def __init__(self, *, toolchain_path: str | None = None, identity_hash: str = "", probe_ref: ObjectRef | str | None = None, expected_masked_hash: str = "",
                 compile_command: str = "", masker: Callable[[bytes], bytes] | None = None, deadline_s: float = 60.0, runner: Callable[..., "subprocess.CompletedProcess[bytes]"] = subprocess.run) -> None:
        self.toolchain_path = toolchain_path
        self.identity_hash = identity_hash
        self.probe_ref = ObjectRef(probe_ref) if probe_ref else None
        self.expected_masked_hash = expected_masked_hash
        self.compile_command = compile_command
        self.masker = masker
        self.deadline_s = deadline_s
        self.runner = runner

    @property
    def capability(self) -> str:
        return f"toolchain:{self.identity_hash}" if self.identity_hash else "toolchain:"

    def _missing(self) -> list[str]:
        needs = []
        if not self.toolchain_path:
            needs.append("toolchain_path (--toolchain-path <dir>)")
        elif not os.path.isdir(self.toolchain_path):
            needs.append(f"toolchain_path {self.toolchain_path!r} is not a directory")
        if not self.identity_hash:
            needs.append("identity_hash (toolchain_identity_hash of the tree)")
        if self.probe_ref is None:
            needs.append("probe_ref (the fixed probe translation unit object)")
        if not self.expected_masked_hash:
            needs.append("expected_masked_hash (the pinned masked object hash)")
        if not self.compile_command:
            needs.append("compile_command template")
        if self.masker is None:
            needs.append("masker (masked object hasher from verify/masked_coff)")
        return needs

    def prove(self, objects: ObjectStore, scratch: str) -> tuple[bool, Mapping[str, Any]]:
        needs = self._missing()
        if needs:
            raise NotConfigured("toolchain canary needs: " + "; ".join(needs))
        assert self.probe_ref is not None and self.masker is not None and self.toolchain_path is not None
        if not objects.exists(self.probe_ref):
            raise NotConfigured(f"toolchain canary needs the probe object {self.probe_ref} in the object store (fetch it from a fleet mirror)")
        source = Path(scratch) / "probe.c"
        output = Path(scratch) / "probe.obj"
        source.write_bytes(objects.get(self.probe_ref))
        cmd = self.compile_command.format(toolchain=shlex.quote(self.toolchain_path), source=shlex.quote(str(source)), output=shlex.quote(str(output)))
        try:
            proc = self.runner(cmd, shell=True, cwd=scratch, capture_output=True, timeout=self.deadline_s, start_new_session=True)
        except subprocess.TimeoutExpired:
            return False, {"failure": "timeout", "deadline_s": self.deadline_s}
        if proc.returncode != 0 or not output.exists():
            return False, {"failure": "compile-failed", "returncode": proc.returncode, "stderr_digest": digest(proc.stderr or b"")}
        got = hashlib.sha256(self.masker(output.read_bytes())).hexdigest()
        ok = got == self.expected_masked_hash
        return ok, {"masked_hash": got, "expected": self.expected_masked_hash, "failure": "" if ok else "pin-mismatch", "identity_hash": self.identity_hash}

    def describe(self) -> Mapping[str, Any]:
        needs = self._missing()
        return {"name": self.name, "capability": self.capability, "status": "working" if not needs else "declared", "needs": needs, "config_schema": dict(self.CONFIG_SCHEMA)}


# --------------------------------------------------------------------------- declared: analyzer, parity, browser
class AnalyzerCanary:
    """Open a fixture packed program headless with the analyzer bundle; the canonical function
    inventory hash must equal the pin.  Capability ``analyzer:<version>:<options_hash>``."""

    name = "analyzer"
    CONFIG_SCHEMA: Mapping[str, str] = {
        "bundle_ref": "ObjectRef of the analyzer bundle (JRE + analyzer, content-addressed toolchain object)",
        "version": "analyzer version string", "options_hash": "hash of the analysis options (basis field)",
        "fixture_ref": "ObjectRef of the fixture packed program", "expected_inventory_hash": "pinned canonical function-inventory hash",
        "headless_command": "shell template with {bundle} {fixture} {output}",
    }

    def __init__(self, **config: Any) -> None:
        self.config = dict(config)

    @property
    def capability(self) -> str:
        return f"analyzer:{self.config.get('version', '')}:{self.config.get('options_hash', '')}"

    def prove(self, objects: ObjectStore, scratch: str) -> tuple[bool, Mapping[str, Any]]:
        missing = [k for k in self.CONFIG_SCHEMA if not self.config.get(k)]
        raise NotConfigured("analyzer canary is declared only; it needs " + ", ".join(missing or self.CONFIG_SCHEMA) + " and the headless runner from grid_lanes/analysis (U137)")

    def describe(self) -> Mapping[str, Any]:
        return {"name": self.name, "capability": self.capability, "status": "declared", "needs": [k for k in self.CONFIG_SCHEMA if not self.config.get(k)], "config_schema": dict(self.CONFIG_SCHEMA)}


class ParityCanary:
    """Run the hash-pinned parity checker on a fixture pair; the canonical receipt must equal the
    pin.  A node with a different checker binary advertises a *different* capability
    (``parity:<its hash>``) and is never offered tasks keyed to the pinned one."""

    name = "parity"
    CONFIG_SCHEMA: Mapping[str, str] = {
        "checker_path": "path of the parity checker binary", "checker_hash": "sha256 of the binary (pinned release)",
        "fixture_pair_ref": "ObjectRef of the fixture object pair", "expected_receipt_hash": "pinned canonical receipt hash",
        "check_command": "shell template with {checker} {left} {right} {output}",
    }

    def __init__(self, **config: Any) -> None:
        self.config = dict(config)

    @property
    def capability(self) -> str:
        return f"parity:{self.config.get('checker_hash', '')}"

    def prove(self, objects: ObjectStore, scratch: str) -> tuple[bool, Mapping[str, Any]]:
        path = self.config.get("checker_path")
        if path and os.path.isfile(path):
            actual = hashlib.sha256(Path(path).read_bytes()).hexdigest()
            if self.config.get("checker_hash") and actual != self.config["checker_hash"]:
                return False, {"failure": "checker-hash-mismatch", "checker_hash": actual, "expected": self.config["checker_hash"]}
        missing = [k for k in self.CONFIG_SCHEMA if not self.config.get(k)]
        raise NotConfigured("parity canary is declared only; it needs " + ", ".join(missing or self.CONFIG_SCHEMA) + " and the checker runner from grid_lanes/parity (U136)")

    def describe(self) -> Mapping[str, Any]:
        return {"name": self.name, "capability": self.capability, "status": "declared", "needs": [k for k in self.CONFIG_SCHEMA if not self.config.get(k)], "config_schema": dict(self.CONFIG_SCHEMA)}


class BrowserCanary:
    name = "browser"
    capability = "browser"

    def prove(self, objects: ObjectStore, scratch: str) -> tuple[bool, Mapping[str, Any]]:
        raise NotConfigured("browser capability is proven by the browser lane's wasm fixture (worker/browser, U154), never on a node")

    def describe(self) -> Mapping[str, Any]:
        return {"name": self.name, "capability": self.capability, "status": "declared", "needs": ["browser lane (U154)"]}


CANARIES.register("python", PythonCanary())
CANARIES.register("toolchain", ToolchainCanary())
CANARIES.register("analyzer", AnalyzerCanary())
CANARIES.register("parity", ParityCanary())
CANARIES.register("browser", BrowserCanary())


# --------------------------------------------------------------------------- running them
@dataclass(frozen=True)
class CanaryOutcome:
    name: str
    capability: str
    state: str                       # proven | failed | not-configured | timeout | error
    evidence: Mapping[str, Any] = field(default_factory=dict)
    elapsed_s: float = 0.0
    message: str = ""


@dataclass(frozen=True)
class CanaryReport:
    outcomes: tuple[CanaryOutcome, ...]

    @property
    def proven(self) -> list[str]:
        return sorted({o.capability for o in self.outcomes if o.state == "proven"})

    def by_state(self, state: str) -> list[CanaryOutcome]:
        return [o for o in self.outcomes if o.state == state]

    def to_record(self) -> dict[str, Any]:
        return {o.name: {"capability": o.capability, "state": o.state, "evidence": dict(o.evidence), "elapsed_s": round(o.elapsed_s, 3), "message": o.message} for o in self.outcomes}


def _run_one(name: str, canary: Canary, objects: ObjectStore, scratch: str, deadline_s: float, clock: Callable[[], float]) -> CanaryOutcome:
    box: dict[str, Any] = {}

    def target() -> None:
        try:
            box["result"] = canary.prove(objects, scratch)
        except NotConfigured as exc:
            box["not_configured"] = str(exc)
        except Exception as exc:  # a canary that raises proves nothing; the class is recorded, never the text
            box["error"] = exc.__class__.__name__

    started = clock()
    thread = threading.Thread(target=target, name=f"canary-{name}", daemon=True)
    thread.start()
    thread.join(deadline_s)
    elapsed = clock() - started
    capability = str(getattr(canary, "capability", name))
    if thread.is_alive():
        return CanaryOutcome(name, capability, "timeout", {"deadline_s": deadline_s}, elapsed, f"canary {name} exceeded {deadline_s:.0f}s")
    if "not_configured" in box:
        return CanaryOutcome(name, capability, "not-configured", {}, elapsed, box["not_configured"])
    if "error" in box:
        return CanaryOutcome(name, capability, "error", {"exception": box["error"]}, elapsed, f"canary {name} raised {box['error']}")
    ok, evidence = box["result"]
    return CanaryOutcome(name, capability, "proven" if ok else "failed", dict(evidence), elapsed, "" if ok else str(evidence.get("failure", "pin-mismatch")))


def run_canaries(objects: ObjectStore, scratch: str, *, canaries: Mapping[str, Canary] | None = None, only: Iterable[str] | None = None, deadline_s: float = DEFAULT_CANARY_DEADLINE_S, clock: Callable[[], float] | None = None) -> CanaryReport:
    """Run every registered canary (or ``only`` those named) with a backstop deadline each."""
    import time

    clock = clock or time.monotonic
    pool: Mapping[str, Canary] = canaries if canaries is not None else dict(CANARIES.items())
    names = [n for n in pool if only is None or n in set(only)]
    Path(scratch).mkdir(parents=True, exist_ok=True)
    outcomes = []
    for name in names:
        sub = Path(scratch) / f"canary-{name}"
        sub.mkdir(parents=True, exist_ok=True)
        outcomes.append(_run_one(name, pool[name], objects, str(sub), deadline_s, clock))
    return CanaryReport(tuple(outcomes))


def prove_all(identity: NodeIdentity, objects: ObjectStore, scratch: str, *, canaries: Mapping[str, Canary] | None = None, only: Iterable[str] | None = None, deadline_s: float = DEFAULT_CANARY_DEADLINE_S) -> list[str]:
    """Proven capability list for ``identity`` (its role does not change what can be proven; a
    fleet node that fails the toolchain canary has no toolchain capability, design §1.4)."""
    return run_canaries(objects, scratch, canaries=canaries, only=only, deadline_s=deadline_s).proven


def describe_canaries(canaries: Mapping[str, Canary] | None = None) -> dict[str, Mapping[str, Any]]:
    pool: Mapping[str, Canary] = canaries if canaries is not None else dict(CANARIES.items())
    return {name: (c.describe() if hasattr(c, "describe") else {"name": name, "capability": getattr(c, "capability", name)}) for name, c in pool.items()}


__all__ = [
    "AnalyzerCanary", "BrowserCanary", "CanaryOutcome", "CanaryReport", "DEFAULT_CANARY_DEADLINE_S", "PYTHON_CANARY_DIGEST", "PYTHON_FIXTURE",
    "PYTHON_FIXTURE_BYTES", "ParityCanary", "PythonCanary", "ToolchainCanary", "describe_canaries", "prove_all", "python_fixture_digest", "run_canaries",
]
