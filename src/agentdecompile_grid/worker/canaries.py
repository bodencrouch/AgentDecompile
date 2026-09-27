"""Capability canaries: a capability exists only after a fixed piece of work hashes to its pin.

``core.Canary`` is the protocol (``capability``, ``prove(objects, scratch) -> (ok, evidence)``) and
``core.CANARIES`` the registry.  One canary works everywhere (``python``: canonical-encode and hash
a pinned fixture); the others are declared with their config schema and raise ``NotConfigured``
naming the probe object or binary they need:

* ``python``               working — delegates to ``tasks.builtin.PythonCanary``: the ``python-canary``
                           task kind's ``v1`` fixture, whose output ref is pinned once in
                           ``tasks.builtin.CANARY_FIXTURES`` (one pin, one owner; this module keeps its
                           older fixture only as ``python_fixture_digest`` for callers that still use it).
* ``toolchain``            compile a fixed translation unit under ``toolchain_path``; the masked
                           object hash must equal the pin.  Capability ``toolchain:<identity_hash>``.
* ``analyzer``             working (U164) -- a lane hook (``AnalyzerCanary.HOOKS``) resolves the
                           install and a fixture (a packed program object by ref, or the lane's
                           synthetic image) and boots the analyzer in a child under a deadline; the
                           sorted ``(entry, size)`` inventory hash must equal the pin.  Capability
                           ``analyzer:<version>:<options_hash>`` (what the analysis kinds require).
* ``parity``               working (U165) -- a lane hook (``ParityCanary.HOOKS``) resolves the checker
                           (object ref or path, hash verified against the pin) and a fixture pair;
                           the canonical receipt hash must equal the pin.  Capability
                           ``parity:<checker sha256>`` (the ``parity-check`` kind's ``verifier_id``);
                           ``ParityCanary.Objdump`` advertises ``objdump:<sha256>`` next to it and
                           refuses by the name ``mkobj-target`` when the target objdump is absent.
* ``browser``              proven only by the browser lane's own wasm fixture; never on a node.

A canary without a pin never proves: the first run is a failed row named ``unpinned`` carrying the
measured hash so an operator can pin it; a pin that disagrees is ``pin-mismatch``; a lane refusal
(missing checker, missing fixture) is its own name.  Pins are explicit (``--analyzer-pin``,
``--parity-pin``) or an embedding's ``pins`` mapping; a config-file pin table is a slot.

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
  * ``test_analyzer_canary_pins_inventory_hash`` (U164): the synthetic fixture measures one hash
    unpinned, proves once pinned to it, and fails ``pin-mismatch`` on an edited pin.
  * ``test_parity_canary_pins_receipt`` / ``test_parity_checker_missing_refuses_by_name`` (U165).
"""
from __future__ import annotations

import hashlib
import os
import platform
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from ..core import CANARIES, GRID_SCHEMA_VERSION, Canary, NodeIdentity, NotConfigured, ObjectStore, Refused, Registry, canonical_json, digest

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
    """``core.Canary`` for ``python``: runs the ``python-canary`` task kind's pinned fixture
    (``tasks.builtin``) and adds the interpreter facts to the evidence.  The pin lives there."""

    capability = "python"
    name = "python"

    def __init__(self, fixture: str = "v1", basis_hash: str = "canary") -> None:
        self.fixture = fixture
        self.basis_hash = basis_hash

    @property
    def expected(self) -> str:
        from ..tasks.builtin import PythonCanaryKind

        return str(PythonCanaryKind.pinned_ref(self.fixture))

    def prove(self, objects: ObjectStore, scratch: str) -> tuple[bool, Mapping[str, Any]]:
        from ..tasks.builtin import PythonCanary as FixtureCanary

        ok, evidence = FixtureCanary(self.basis_hash, self.fixture).prove(objects, scratch)
        return ok, {**dict(evidence), "python": platform.python_version(), "implementation": platform.python_implementation(), "machine": platform.machine()}

    def describe(self) -> Mapping[str, Any]:
        return {"name": self.name, "capability": self.capability, "status": "working", "needs": [], "pin": self.expected,
                "fixture": self.fixture, "pin_owner": "agentdecompile_grid.tasks.builtin.CANARY_FIXTURES"}


# --------------------------------------------------------------------------- working: toolchain
class ToolchainCanary:
    """Prove ``toolchain:<identity_hash>`` for a tree (U163).

    Inputs: a manifest (duck-typed: ``entries``, ``identity_hash``, ``probe`` with ``tu_relpath``
    and ``expected_masked_hash``) and a root -- an owned install or a fetched toolchain unpacked
    to a temp root, one code path.  Steps: ``verify_tree(root, manifest)`` -> compile the probe
    TU with the probe compiler under the deadline -> ``masker.masked_hash(object bytes)`` -> compare
    to the pin -> bounded parallel trial (``probe_parallel``, default ``os.cpu_count()``) that
    measures this node's concurrency cap -> ``on_proven(identity_hash)`` binds the root for the
    compile lane.  Any mismatch is a named failure (``toolchain-canary: masked hash mismatch for
    <hash[:16]>`` ...) and proves nothing.

    The pieces come from a lane through ``HOOKS`` (a lane registers a hook whose
    ``configure(root=, manifest_source=, objects=)`` returns ``manifest``, ``root``,
    ``verify_tree``, ``compiler``, ``masker`` and ``on_proven``) or are passed explicitly; this
    module names no lane.  The capability stays exactly ``toolchain:<identity_hash>`` (what
    ``compile-attempt`` requires); the measured cap is advertised *additionally* as
    ``toolchain:<identity_hash>:slots=<n>`` through ``slots_canary()`` and recorded in evidence.
    An ``--with toolchain <hash>`` assertion that disagrees with the manifest is refused by name.
    """

    name = "toolchain"
    HOOKS = Registry("toolchain canary hook")
    CONFIG_SCHEMA: Mapping[str, str] = {
        "toolchain_path": "root of the tree: an owned install or a fetched toolchain unpacked to a temp root",
        "manifest_source": "manifest file path, a tree holding toolchain-manifest.json, or a sha256: object ref (lane hook loads it)",
        "identity_hash": "optional asserted identity; must equal the manifest's or the canary refuses",
        "probe_parallel": "bounded parallel probe count for the concurrency cap (default os.cpu_count())",
        "deadline_s": "per-probe compile deadline",
        "manifest/compiler/masker/verify_tree/on_proven": "explicit pieces instead of a HOOKS entry (tests, embedding)",
    }

    def __init__(self, *, toolchain_path: str | os.PathLike[str] | None = None, identity_hash: str = "", manifest_source: Any = None,
                 probe_parallel: int | None = None, deadline_s: float = 60.0, hook: str = "toolchain",
                 manifest: Any = None, compiler: Any = None, masker: Any = None, verify_tree: Callable[..., Any] | None = None,
                 on_proven: Callable[[str], Mapping[str, Any]] | None = None) -> None:
        self.toolchain_path = str(toolchain_path) if toolchain_path is not None else None
        self.asserted_identity = identity_hash
        self.manifest_source = manifest_source
        self.probe_parallel = probe_parallel
        self.deadline_s = deadline_s
        self.hook = hook
        self.manifest = manifest
        self.compiler = compiler
        self.masker = masker
        self.verify_tree = verify_tree
        self.on_proven = on_proven
        self.measured_slots: int | None = None
        self.last_evidence: dict[str, Any] = {}

    # ----------------------------------------------------------------- identity / capability
    @property
    def identity_hash(self) -> str:
        if self.manifest is not None and getattr(self.manifest, "identity_hash", ""):
            return str(self.manifest.identity_hash)
        return self.asserted_identity

    @property
    def capability(self) -> str:
        return f"toolchain:{self.identity_hash}" if self.identity_hash else "toolchain:"

    def slots_canary(self) -> "ToolchainCanary.Slots":
        return ToolchainCanary.Slots(self)

    # ----------------------------------------------------------------- configuration
    def _needs(self) -> list[str]:
        needs = []
        explicit = all(x is not None for x in (self.manifest, self.compiler, self.masker, self.verify_tree))
        if not explicit:
            if not self.toolchain_path:
                needs.append("toolchain_path (--toolchain-path <dir>)")
            elif not os.path.isdir(self.toolchain_path):
                needs.append("toolchain_path is not a directory")
            if self.hook not in self.HOOKS:
                needs.append(f"a lane hook named {self.hook!r} in ToolchainCanary.HOOKS (load the toolchain lane: config lanes / ADGRID_LANES)")
        return needs

    def _configure(self, objects: ObjectStore) -> None:
        if all(x is not None for x in (self.manifest, self.compiler, self.masker, self.verify_tree)):
            return
        cfg = self.HOOKS.get(self.hook).configure(root=self.toolchain_path, manifest_source=self.manifest_source, objects=objects)
        self.manifest = cfg["manifest"]
        self.toolchain_path = str(cfg.get("root", self.toolchain_path))
        self.verify_tree = cfg["verify_tree"]
        self.compiler = cfg["compiler"]
        self.masker = cfg["masker"]
        self.on_proven = cfg.get("on_proven", self.on_proven)

    # ----------------------------------------------------------------- one probe
    def _probe_once(self, scratch: Path) -> tuple[str, dict[str, Any]]:
        """Compile the probe TU in *scratch*; return ``(masked_hash, facts)``; a named failure has ``''``."""
        assert self.manifest is not None and self.compiler is not None and self.masker is not None
        root = Path(self.toolchain_path or "")
        probe = self.manifest.probe
        scratch.mkdir(parents=True, exist_ok=True)
        source = root / probe.tu_relpath
        output = scratch / "probe.obj"
        output.unlink(missing_ok=True)
        run = self.compiler.compile(root, source, output, scratch=scratch, deadline_s=self.deadline_s)
        facts: dict[str, Any] = {"wall_s": round(float(run.elapsed_s), 3), "returncode": run.returncode, "stderr_sha256": run.stderr_sha256}
        if run.timed_out:
            facts["failure"] = f"toolchain-canary: probe timed out after {self.deadline_s:.0f}s for {self.identity_hash[:16]}"
            return "", facts
        if run.returncode != 0 or not run.produced:
            facts["failure"] = f"toolchain-canary: probe compile failed (exit {run.returncode}) for {self.identity_hash[:16]}"
            return "", facts
        data = output.read_bytes()
        facts["object_bytes"] = len(data)
        facts["raw_sha256"] = hashlib.sha256(data).hexdigest()
        try:
            return str(self.masker.masked_hash(data)), facts
        except Exception as exc:   # a masker refusal is a named failure, never a traceback
            facts["failure"] = f"toolchain-canary: masker refused ({exc.__class__.__name__}: {exc}) for {self.identity_hash[:16]}"
            return "", facts

    def _parallel_trial(self, scratch: Path, expected: str) -> dict[str, Any]:
        """Run ``probe_parallel`` probes at once; the cap is how many finished with the pin."""
        wanted = self.probe_parallel if self.probe_parallel and self.probe_parallel > 0 else (os.cpu_count() or 1)
        n = max(1, min(int(wanted), 64))
        results: list[tuple[str, dict[str, Any]] | None] = [None] * n

        def work(i: int) -> None:
            results[i] = self._probe_once(scratch / f"parallel-{i}")

        threads = [threading.Thread(target=work, args=(i,), name=f"toolchain-probe-{i}", daemon=True) for i in range(n)]
        started = time.monotonic()
        for t in threads:
            t.start()
        for t in threads:
            t.join(self.deadline_s + 5.0)
        wall = time.monotonic() - started
        hashes = [r[0] if r is not None else "" for r in results]
        mismatched = sum(1 for h in hashes if h and h != expected)
        passed = sum(1 for h in hashes if h == expected)
        trial = {"requested": n, "passed": passed, "mismatched": mismatched, "wall_s": round(wall, 3)}
        if mismatched:
            trial["failure"] = f"toolchain-canary: masked hash mismatch under parallel load ({mismatched}/{n}) for {self.identity_hash[:16]}"
        elif passed == 0:
            trial["failure"] = f"toolchain-canary: no parallel probe finished within {self.deadline_s:.0f}s for {self.identity_hash[:16]}"
        return trial

    # ----------------------------------------------------------------- the canary
    def prove(self, objects: ObjectStore, scratch: str) -> tuple[bool, Mapping[str, Any]]:
        needs = self._needs()
        if needs:
            raise NotConfigured("toolchain canary needs: " + "; ".join(needs))
        self._configure(objects)
        assert self.manifest is not None and self.verify_tree is not None
        identity = self.identity_hash
        short = identity[:16]
        evidence: dict[str, Any] = {"identity_hash": identity, "entries": len(self.manifest.entries)}
        self.last_evidence = evidence

        def fail(message: str) -> tuple[bool, Mapping[str, Any]]:
            evidence["failure"] = message
            return False, evidence

        if self.asserted_identity and self.asserted_identity != identity:
            return fail(f"toolchain-canary: asserted identity {self.asserted_identity[:16]} is not the manifest's {short}")
        probe = getattr(self.manifest, "probe", None)
        if probe is None or not getattr(probe, "expected_masked_hash", ""):
            return fail(f"toolchain-canary: manifest {short} declares no probe pin")
        expected = str(probe.expected_masked_hash)
        evidence["expected_masked_hash"] = expected
        tree = self.verify_tree(self.toolchain_path, self.manifest)
        evidence["tree"] = tree.to_mapping() if hasattr(tree, "to_mapping") else dict(tree)
        if not getattr(tree, "ok", False):
            return fail(f"toolchain-canary: tree does not match manifest {short}: missing={len(tree.missing)} mismatched={len(tree.mismatched)}")
        if probe.tu_relpath not in getattr(self.manifest, "paths", {rel for rel, _ in self.manifest.entries}):
            return fail(f"toolchain-canary: probe TU is not a declared entry of {short}")
        got, facts = self._probe_once(Path(scratch) / "serial")
        evidence["probe"] = facts
        if not got:
            return fail(str(facts.get("failure", "probe-failed")))
        evidence["masked_hash"] = got
        if got != expected:
            return fail(f"toolchain-canary: masked hash mismatch (pin-mismatch) for {short}")
        trial = self._parallel_trial(Path(scratch), expected)
        evidence["parallel"] = trial
        if trial.get("failure"):
            return fail(str(trial["failure"]))
        self.measured_slots = int(trial["passed"])
        evidence["slots"] = self.measured_slots
        evidence["capability_slots"] = f"{self.capability}:slots={self.measured_slots}"
        if self.on_proven is not None:
            try:
                evidence["binding"] = dict(self.on_proven(identity))
            except NotConfigured:
                raise
            except Exception as exc:
                return fail(f"toolchain-canary: binding refused ({exc.__class__.__name__}: {exc}) for {short}")
        evidence["failure"] = ""
        return True, evidence

    def describe(self) -> Mapping[str, Any]:
        needs = self._needs()
        return {"name": self.name, "capability": self.capability, "status": "working" if not needs else "not-configured", "needs": needs,
                "config_schema": dict(self.CONFIG_SCHEMA), "hooks": self.HOOKS.names(), "probe_parallel": self.probe_parallel or (os.cpu_count() or 1),
                "compatibility_layer": "slot: persistent per-node server, health-checked, reused (lane probe compiler 'compatibility-layer')"}

    # ----------------------------------------------------------------- the additional slots capability
    class Slots:
        """Advertises ``toolchain:<hash>:slots=<n>`` next to the plain capability; never instead of it.
        Reuses the parent's measured cap when the parent already proved, else measures itself."""

        name = "toolchain-slots"

        def __init__(self, parent: "ToolchainCanary") -> None:
            self.parent = parent

        @property
        def capability(self) -> str:
            n = self.parent.measured_slots
            return f"{self.parent.capability}:slots={n if n is not None else 0}"

        def prove(self, objects: ObjectStore, scratch: str) -> tuple[bool, Mapping[str, Any]]:
            parent = self.parent
            if parent.measured_slots is None and parent.last_evidence.get("failure"):
                return False, {"failure": str(parent.last_evidence["failure"]), "identity_hash": parent.identity_hash}
            if parent.measured_slots is None:
                ok, evidence = parent.prove(objects, scratch)
                if not ok:
                    return False, {"failure": str(evidence.get("failure", "toolchain canary failed")), "identity_hash": parent.identity_hash}
            return True, {"slots": parent.measured_slots, "identity_hash": parent.identity_hash, "parallel": dict(parent.last_evidence.get("parallel", {}))}

        def describe(self) -> Mapping[str, Any]:
            return {"name": self.name, "capability": self.capability, "status": "working" if not self.parent._needs() else "not-configured",
                    "needs": self.parent._needs(), "measures": "bounded parallel probe trial; cap = probes that reached the pin"}


# --------------------------------------------------------------------------- working: analyzer
class AnalyzerCanary:
    """Prove ``analyzer:<version>:<options_hash>`` for this node (U164).

    Steps: resolve the install and the fixture through the lane hook (``HOOKS['analyzer']``,
    registered by the lane on import; this module names no lane) -> the hook's ``inventory``
    boots the analyzer in a child under ``deadline_s`` (never in this process: a JVM never
    exits on its own, H14) and returns the function inventory rows ``(entry, size)`` ->
    ``inventory_hash`` = sha256 over the sorted ``"<entry:#x> <size>"`` lines, newline-joined ->
    compare to the pin.  Fixture sources the lane offers: a packed program object by ref
    (``fixture='sha256:...'``, opened as-is) or the lane's deterministic synthetic image (no
    fixture given, auto-analysed with the headless defaults); install sources: the owned
    install (``GHIDRA_INSTALL_DIR``) or an unpacked bundle root (``install_dir``).

    The pin is explicit (``pin`` / ``--analyzer-pin``) or looked up in a ``pins`` mapping
    (``pins['analyzer'][<version>]``); a config-file pin table is a slot (``describe()['pin_source']``).
    Without a pin the first run is ``unpinned``: a failed row carrying the measured hash and
    **no** capability (``test_capability_only_after_pin``); a mismatch is the named failure
    ``pin-mismatch`` and the lane stays closed.  ``options_hash`` comes from the lane (the
    determinism basis' analyzer options field), so the capability is byte-identical to what
    ``analysis-slice`` / ``decompile-chunk`` tasks require.
    """

    name = "analyzer"
    HOOKS = Registry("analyzer canary hook")
    CONFIG_SCHEMA: Mapping[str, str] = {
        "fixture": "sha256: ref of a packed program object (packed source); omit for the lane's synthetic image",
        "install_dir": "unpacked analyzer bundle root (bundle source); omit for the owned install (GHIDRA_INSTALL_DIR)",
        "pin": "pinned inventory hash (--analyzer-pin); omit to measure (unpinned, no capability)",
        "pins": "mapping pins['analyzer'][<version>] -> hash (embedding); config-file pins are a slot",
        "deadline_s": "child probe deadline (boot + open + analysis)",
        "version/options_hash/inventory": "explicit pieces instead of a HOOKS entry (tests, embedding)",
    }

    def __init__(self, *, fixture: str | None = None, install_dir: str | os.PathLike[str] | None = None, pin: str = "",
                 pins: Mapping[str, Any] | None = None, deadline_s: float = 90.0, hook: str = "analyzer",
                 version: str = "", options_hash: str = "", inventory: Callable[[str, float], Any] | None = None) -> None:
        self.fixture = fixture
        self.install_dir = str(install_dir) if install_dir is not None else None
        self.pin = pin.strip()
        self.pins = pins
        self.deadline_s = deadline_s
        self.hook = hook
        self.version = version
        self.options_hash = options_hash
        self.inventory = inventory
        self.last_evidence: dict[str, Any] = {}

    @property
    def capability(self) -> str:
        return f"analyzer:{self.version}:{self.options_hash}"

    @staticmethod
    def inventory_hash(rows: Iterable[tuple[int, int]]) -> str:
        lines = sorted(f"{int(entry):#x} {int(size)}" for entry, size in rows)
        return hashlib.sha256(("\n".join(lines) + "\n").encode("ascii")).hexdigest()

    def expected(self) -> str:
        if self.pin:
            return self.pin
        table = (self.pins or {}).get("analyzer", {}) if self.pins else {}
        return str(table.get(self.version, "") or "").strip() if isinstance(table, Mapping) else ""

    def _needs(self) -> list[str]:
        if self.inventory is not None and self.version:
            return []
        needs = []
        if self.hook not in self.HOOKS:
            needs.append(f"a lane hook named {self.hook!r} in AnalyzerCanary.HOOKS (load the lanes: config lanes / ADGRID_LANES)")
        if self.install_dir and not os.path.isdir(self.install_dir):
            needs.append("install_dir is not a directory")
        return needs

    def _configure(self, objects: ObjectStore, scratch: str) -> dict[str, Any]:
        if self.inventory is not None and self.version:
            return {}
        cfg = self.HOOKS.get(self.hook).configure(fixture=self.fixture, install=self.install_dir, objects=objects, scratch=scratch)
        self.version = str(cfg["version"])
        self.options_hash = str(cfg.get("options_hash", self.options_hash))
        self.inventory = cfg["inventory"]
        return cfg

    def prove(self, objects: ObjectStore, scratch: str) -> tuple[bool, Mapping[str, Any]]:
        needs = self._needs()
        if needs:
            raise NotConfigured("analyzer canary needs: " + "; ".join(needs))
        evidence: dict[str, Any] = {}
        self.last_evidence = evidence

        def fail(message: str) -> tuple[bool, Mapping[str, Any]]:
            evidence["failure"] = message
            return False, evidence

        try:
            cfg = self._configure(objects, scratch)
        except Refused as exc:                    # a lane refusal is a named failure, never a traceback
            return fail(str(exc.reason))
        fixture = cfg.get("fixture")
        install = cfg.get("install")
        evidence.update({
            "version": self.version, "options_hash": self.options_hash,
            "fixture": {"sha256": getattr(fixture, "sha256", ""), "kind": getattr(fixture, "kind", ""), "source": getattr(fixture, "source", "")},
            "install": {"version": getattr(install, "version", self.version), "source": getattr(install, "source", "")},
        })
        assert self.inventory is not None
        run = self.inventory(scratch, self.deadline_s)
        evidence["probe"] = {"wall_s": round(float(getattr(run, "elapsed_s", 0.0)), 3), "boot_s": getattr(run, "boot_s", None),
                             "open_s": getattr(run, "open_s", None), "returncode": getattr(run, "returncode", None),
                             "live_version": getattr(run, "live_version", ""), "stderr_sha256": getattr(run, "stderr_sha256", "")}
        if getattr(run, "timed_out", False):
            return fail(f"analyzer-canary: probe timed out after {self.deadline_s:.0f}s for {self.version}")
        if getattr(run, "failure", ""):
            return fail(str(run.failure))
        rows = list(getattr(run, "rows", ()))
        if not rows:
            return fail(f"analyzer-canary: empty function inventory for {self.version}")
        got = self.inventory_hash(rows)
        evidence["inventory_hash"] = got
        evidence["functions"] = len(rows)
        expected = self.expected()
        evidence["expected_inventory_hash"] = expected
        if not expected:
            return fail("unpinned")
        if got != expected:
            return fail(f"analyzer-canary: inventory hash mismatch (pin-mismatch) for {self.version}")
        evidence["failure"] = ""
        return True, evidence

    def describe(self) -> Mapping[str, Any]:
        needs = self._needs()
        hook = self.HOOKS.get(self.hook) if self.hook in self.HOOKS else None
        sources = hook.describe() if hook is not None and hasattr(hook, "describe") else {
            "fixture_sources": {"working": ["packed", "synthetic"], "slots": ["remote"]},
            "install_sources": {"working": ["owned", "bundle"], "slots": []},
        }
        return {"name": self.name, "capability": self.capability, "status": "working" if not needs else "not-configured", "needs": needs,
                "config_schema": dict(self.CONFIG_SCHEMA), "hooks": self.HOOKS.names(), "pin": self.expected(),
                "pin_source": {"working": ["--analyzer-pin", "pins mapping"], "slots": ["config pins.analyzer.<version>"]},
                "inventory_hash": "sha256 over sorted '<entry:#x> <size>' lines, newline-joined, trailing newline",
                "unpinned": "first run without a pin: failed row 'unpinned' with the measured hash, no capability", **sources}


# --------------------------------------------------------------------------- working: parity
class ParityCanary:
    """Prove ``parity:<checker sha256>`` for this node (U165).

    Steps: resolve the checker through the lane hook (``HOOKS['parity']``) -- a checker binary
    object by ref (its ref is its hash) or a configured path whose bytes must hash to
    ``checker_hash`` when one is asserted; a checker built from source is the lane's slot -> run
    it on the fixture pair (two object refs, or the lane's synthetic pair) under ``deadline_s`` ->
    the canonical receipt's sha256 must equal ``pin``.  The capability is the full
    ``parity:<sha256>`` the ``parity-check`` kind requires (``verifier_id``), so a node with a
    different checker build advertises a different capability and is never offered tasks keyed to
    the pinned one.  A missing checker is the named failure ``parity-checker-missing:native``
    (``test_parity_checker_missing_refuses_by_name``); no receipt pin is ``unpinned`` with the
    measured receipt hash and no capability; a receipt mismatch is ``pin-mismatch``.

    The target ``objdump`` that ``mkobj-target`` needs is a second, declared capability
    (``objdump:<sha256>``) advertised by ``objdump_canary()``; its absence is the named refusal
    ``mkobj-target``, never an exception.
    """

    name = "parity"
    HOOKS = Registry("parity canary hook")
    CONFIG_SCHEMA: Mapping[str, str] = {
        "checker": "checker binary: a path, or a sha256: object ref (--parity-checker)",
        "checker_hash": "asserted sha256 of the checker bytes (--with parity <hash>); a mismatch refuses by name",
        "pin": "pinned canonical receipt hash (--parity-pin); omit to measure (unpinned, no capability)",
        "fixture_pair": "two sha256: refs, target then candidate; omit for the lane's synthetic pair",
        "objdump": "target objdump path for the objdump capability (--parity-objdump)",
        "deadline_s": "checker run deadline",
        "runner/checker_sha256": "explicit pieces instead of a HOOKS entry (tests, embedding)",
    }

    def __init__(self, *, checker: str | None = None, checker_hash: str = "", pin: str = "", fixture_pair: Iterable[str] | None = None,
                 objdump: str | os.PathLike[str] | None = None, deadline_s: float = 60.0, hook: str = "parity",
                 runner: Callable[[str, float], Any] | None = None, checker_sha256: str = "") -> None:
        self.checker = checker
        self.checker_hash = checker_hash.strip()
        self.pin = pin.strip()
        self.fixture_pair = tuple(fixture_pair) if fixture_pair else None
        self.objdump = str(objdump) if objdump is not None else None
        self.deadline_s = deadline_s
        self.hook = hook
        self.runner = runner
        self.checker_sha256 = checker_sha256.strip()
        self.last_evidence: dict[str, Any] = {}

    @property
    def capability(self) -> str:
        return f"parity:{self.checker_sha256 or self.checker_hash}"

    def objdump_canary(self) -> "ParityCanary.Objdump":
        return ParityCanary.Objdump(self)

    def _needs(self) -> list[str]:
        if self.runner is not None and self.checker_sha256:
            return []
        needs = []
        if self.hook not in self.HOOKS:
            needs.append(f"a lane hook named {self.hook!r} in ParityCanary.HOOKS (load the lanes: config lanes / ADGRID_LANES)")
        return needs

    def _configure(self, objects: ObjectStore, scratch: str) -> dict[str, Any]:
        if self.runner is not None and self.checker_sha256:
            return {}
        cfg = self.HOOKS.get(self.hook).configure(checker=self.checker, checker_hash=self.checker_hash, objects=objects, scratch=scratch,
                                                  fixture_pair=self.fixture_pair)
        self.checker_sha256 = str(cfg["checker_sha256"])
        self.runner = cfg["run"]
        return cfg

    def prove(self, objects: ObjectStore, scratch: str) -> tuple[bool, Mapping[str, Any]]:
        needs = self._needs()
        if needs:
            raise NotConfigured("parity canary needs: " + "; ".join(needs))
        evidence: dict[str, Any] = {"asserted_checker_hash": self.checker_hash}
        self.last_evidence = evidence

        def fail(message: str) -> tuple[bool, Mapping[str, Any]]:
            evidence["failure"] = message
            return False, evidence

        try:
            cfg = self._configure(objects, scratch)
        except Refused as exc:                    # missing checker / hash mismatch: named, never a traceback
            return fail(str(exc.reason))
        if self.checker_hash and self.checker_sha256 != self.checker_hash:
            return fail(f"parity-checker-hash-mismatch:{self.checker_sha256[:16]}!={self.checker_hash[:16]}")
        pair = cfg.get("pair")
        evidence.update({"checker_sha256": self.checker_sha256, "checker_source": cfg.get("checker_source", "explicit"),
                         "sides": {"target": getattr(pair, "target_sha256", ""), "candidate": getattr(pair, "candidate_sha256", "")},
                         "pair_source": getattr(pair, "source", "")})
        assert self.runner is not None
        run = self.runner(scratch, self.deadline_s)
        evidence["probe"] = {"wall_s": round(float(getattr(run, "elapsed_s", 0.0)), 3), "returncode": getattr(run, "returncode", None),
                             "stderr_sha256": getattr(run, "stderr_sha256", "")}
        if getattr(run, "timed_out", False):
            return fail(f"parity-canary: checker timed out after {self.deadline_s:.0f}s for {self.checker_sha256[:16]}")
        if getattr(run, "failure", ""):
            return fail(str(run.failure))
        receipt = dict(getattr(run, "receipt", {}) or {})
        if not receipt:
            return fail(f"parity-canary: checker produced no receipt for {self.checker_sha256[:16]}")
        got = digest(canonical_json(receipt))
        evidence["receipt_hash"] = got
        evidence["grade"] = str(receipt.get("grade", receipt.get("status", "error")))
        evidence["expected_receipt_hash"] = self.pin
        if not self.pin:
            return fail("unpinned")
        if got != self.pin:
            return fail(f"parity-canary: receipt hash mismatch (pin-mismatch) for {self.checker_sha256[:16]}")
        evidence["failure"] = ""
        return True, evidence

    def describe(self) -> Mapping[str, Any]:
        needs = self._needs()
        hook = self.HOOKS.get(self.hook) if self.hook in self.HOOKS else None
        sources = hook.describe() if hook is not None and hasattr(hook, "describe") else {
            "checker_sources": {"working": ["object", "path"], "slots": ["built"]},
            "pair_sources": {"working": ["objects", "synthetic"], "slots": []},
            "objdump": {"capability": "objdump:<sha256>", "refusal": "mkobj-target"},
        }
        return {"name": self.name, "capability": self.capability, "status": "working" if not needs else "not-configured", "needs": needs,
                "config_schema": dict(self.CONFIG_SCHEMA), "hooks": self.HOOKS.names(), "pin": self.pin,
                "pin_source": {"working": ["--parity-pin"], "slots": ["config pins.parity.<checker sha256>"]},
                "receipt_hash": "sha256 of the canonical JSON receipt (parity-check shape minus raw output)",
                "unpinned": "first run without a pin: failed row 'unpinned' with the measured receipt hash, no capability", **sources}

    # ----------------------------------------------------------------- the declared objdump capability
    class Objdump:
        """``objdump:<sha256>`` for the target objdump ``mkobj-target`` cuts targets with; absent
        or unusable is the named refusal ``mkobj-target``, never an exception."""

        name = "parity-objdump"

        def __init__(self, parent: "ParityCanary") -> None:
            self.parent = parent
            self.sha256 = ""

        @property
        def capability(self) -> str:
            return f"objdump:{self.sha256}"

        def prove(self, objects: ObjectStore, scratch: str) -> tuple[bool, Mapping[str, Any]]:
            parent = self.parent
            if parent.hook not in parent.HOOKS:
                raise NotConfigured(f"objdump canary needs a lane hook named {parent.hook!r} in ParityCanary.HOOKS (load the lanes: config lanes / ADGRID_LANES)")
            hook = parent.HOOKS.get(parent.hook)
            if not hasattr(hook, "probe_objdump"):
                raise NotConfigured(f"lane hook {parent.hook!r} offers no probe_objdump")
            facts = dict(hook.probe_objdump(parent.objdump, scratch=scratch, deadline_s=parent.deadline_s))
            if facts.get("failure"):
                return False, facts
            self.sha256 = str(facts.get("sha256", ""))
            return bool(self.sha256), {**facts, "failure": "" if self.sha256 else "mkobj-target: target objdump has no hash"}

        def describe(self) -> Mapping[str, Any]:
            return {"name": self.name, "capability": self.capability, "status": "declared" if not self.parent.objdump else "working",
                    "needs": [] if self.parent.objdump else ["--parity-objdump <path> or AGENT_DECOMPILE_OBJDUMP"],
                    "refusal": "mkobj-target"}


# --------------------------------------------------------------------------- declared: browser
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
