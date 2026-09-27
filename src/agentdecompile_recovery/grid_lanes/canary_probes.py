"""Lane side of the analyzer and parity join canaries (U164 / U165).

The grid's ``AnalyzerCanary`` and ``ParityCanary`` (``worker/canaries.py``) own the pin rule and
the outcome; this module owns everything that needs the pipeline: where a fixture and an
analyzer install come from, how the analyzer is booted, where a checker binary comes from and
how it is run.  Importing this module binds ``analyzer_hook`` / ``parity_hook`` into the two
canaries' ``HOOKS`` registries (the pattern ``toolchain.py`` uses); the grid package never
imports this one.

Registries (working implementation named first):

* ``FIXTURE_SOURCES`` -- ``packed`` (``PackedFixture``: a packed program object fetched from the
  store by ``sha256:`` ref, opened as-is, no analysis, working), ``synthetic`` (``SyntheticFixture``:
  a deterministic minimal image generated here, imported and auto-analysed with the headless
  defaults, working), ``remote`` (``RemoteFixture``, slot).
* ``INSTALL_SOURCES`` -- ``owned`` (``OwnedInstall``: ``GHIDRA_INSTALL_DIR``, working), ``bundle``
  (``FetchedBundle``: an unpacked bundle root handed in explicitly, working).
* ``PAIR_SOURCES`` -- ``objects`` (``ObjectPair``: two ``sha256:`` refs, target then candidate,
  working), ``synthetic`` (``SyntheticPair``: one deterministic minimal relocatable object used
  for both sides, working).
* ``CHECKER_SOURCES`` -- ``object`` (``HashPinnedChecker``: a checker binary object whose sha256
  *is* its ref, working), ``path`` (``PathChecker``: a configured path whose sha256 is verified
  against the pin, working), ``built`` (``BuiltChecker``, slot).

**The analyzer probe runs in a child process.**  A process that booted the analyzer's JVM never
exits on its own (H14), so the node agent must never boot one: ``probe_inventory`` spawns
``python -m agentdecompile_recovery.grid_lanes.canary_probes --inventory ...`` under ``run_argv``'s
deadline (SIGTERM, then SIGKILL) and the child boots through ``corpus.ghidra_env.start`` -- never
bare pyghidra -- reads the function inventory, prints one marked JSON line and ends with
``ghidra_env.exit_after_jvm``.  The inventory row is ``(entry offset, body size)`` for every
non-external function, the shape ``corpus.features.tier1`` reports as ``addr``/``size``; hashing
the sorted rows is the grid side's rule so that the pin lives with the pin.

The parity probe renders the native checker's argv through ``parity.ParityChecker`` (sides
named: ``-1 <target> -2 <candidate>``), parses fail-closed with
``objdiff_verification.parse_objdiff_report`` and returns the same receipt shape ``parity-check``
publishes (minus the raw output); the grid side hashes the canonical receipt.  The target
``objdump`` (what ``mkobj-target`` needs to cut targets) is probed by ``probe_objdump``; its
absence is the named refusal ``mkobj-target``, never an exception.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import struct
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from agentdecompile_grid.core import NotConfigured, ObjectRef, ObjectStore, Refused, Registry

from ._common import RunOutcome, materialize_object, run_argv

CHILD_MARK = "ADGRID-CANARY-INVENTORY:"
CHILD_MODULE = "agentdecompile_recovery.grid_lanes.canary_probes"
OBJDUMP_ENV = "AGENT_DECOMPILE_OBJDUMP"
SYNTHETIC_IMAGE_NAME = "canary-image.elf"
SYNTHETIC_OBJECT_NAME = "canary-object.o"


# --------------------------------------------------------------------------- deterministic fixtures
def synthetic_image_bytes() -> bytes:
    """A minimal static x86-64 ELF executable: ``_start`` calls three leaf functions and exits.

    No section headers, one ``PT_LOAD``; the loader takes the entry point and the analyzer's
    default pass finds the callees.  Every byte is fixed here, so the fixture's sha256 is a
    constant and the inventory the analyzer reports is what the pin measures.
    """
    base = 0x400000
    code_off = 0x78
    # _start: call f1; call f2; call f3; mov eax,60; xor edi,edi; syscall
    f1_off, f2_off, f3_off = code_off + 24, code_off + 30, code_off + 33
    start = b""
    for target in (f1_off, f2_off, f3_off):
        here = code_off + len(start) + 5
        start += b"\xe8" + struct.pack("<i", target - here)
    start += b"\xb8\x3c\x00\x00\x00" + b"\x31\xff" + b"\x0f\x05"
    assert len(start) == 24, len(start)
    f1 = b"\xb8\x01\x00\x00\x00\xc3"                            # mov eax,1; ret
    f2 = b"\x31\xc0\xc3"                                        # xor eax,eax; ret
    f3 = b"\x55\x48\x89\xe5\xb8\x2a\x00\x00\x00\x5d\xc3"        # push rbp; mov rbp,rsp; mov eax,42; pop rbp; ret
    code = start + f1 + f2 + f3
    total = code_off + len(code)
    ehdr = struct.pack(
        "<4sBBBB8xHHIQQQIHHHHHH",
        b"\x7fELF", 2, 1, 1, 0,           # 64-bit, little endian, version, SYSV ABI
        2, 0x3E, 1,                       # ET_EXEC, x86-64, EV_CURRENT
        base + code_off, 64, 0, 0,        # e_entry, e_phoff, e_shoff, e_flags
        64, 56, 1, 64, 0, 0,              # ehsize, phentsize, phnum, shentsize, shnum, shstrndx
    )
    phdr = struct.pack("<IIQQQQQQ", 1, 5, 0, base, base, total, total, 0x1000)   # PT_LOAD, R+X
    return ehdr + phdr + code


def synthetic_object_bytes() -> bytes:
    """A minimal x86-64 ELF relocatable object: ``.text`` holding one global function ``probe``.

    Sections: null, .text, .symtab, .strtab, .shstrtab; symbols: null, section, ``probe``.
    Fixed bytes, so the pair's sha256 is a constant.
    """
    text = b"\x55\x48\x89\xe5\xb8\x2a\x00\x00\x00\x5d\xc3"      # push rbp; mov rbp,rsp; mov eax,42; pop rbp; ret
    strtab = b"\x00probe\x00"
    shstrtab = b"\x00.text\x00.symtab\x00.strtab\x00.shstrtab\x00"
    # symtab: null, STT_SECTION for .text, STT_FUNC GLOBAL probe
    sym = struct.pack("<IBBHQQ", 0, 0, 0, 0, 0, 0)
    sym += struct.pack("<IBBHQQ", 0, 0x03, 0, 1, 0, 0)
    sym += struct.pack("<IBBHQQ", 1, 0x12, 0, 1, 0, len(text))
    ehsize = 64
    off_text = ehsize
    off_symtab = off_text + len(text) + (-len(text) % 8)
    off_strtab = off_symtab + len(sym)
    off_shstr = off_strtab + len(strtab)
    off_sh = off_shstr + len(shstrtab) + (-(off_shstr + len(shstrtab)) % 8)
    ehdr = struct.pack("<4sBBBB8xHHIQQQIHHHHHH", b"\x7fELF", 2, 1, 1, 0, 1, 0x3E, 1, 0, 0, off_sh, 0, 64, 0, 0, 64, 5, 4)
    body = bytearray(ehdr)

    def pad_to(n: int) -> None:
        body.extend(b"\0" * (n - len(body)))

    pad_to(off_text); body.extend(text)
    pad_to(off_symtab); body.extend(sym)
    pad_to(off_strtab); body.extend(strtab)
    pad_to(off_shstr); body.extend(shstrtab)
    pad_to(off_sh)

    def sh(name: int, typ: int, flags: int, off: int, size: int, link: int = 0, info: int = 0, align: int = 1, entsize: int = 0) -> bytes:
        return struct.pack("<IIQQQQIIQQ", name, typ, flags, 0, off, size, link, info, align, entsize)

    body.extend(sh(0, 0, 0, 0, 0))
    body.extend(sh(1, 1, 0x6, off_text, len(text), align=16))                          # .text PROGBITS AX
    body.extend(sh(7, 2, 0, off_symtab, len(sym), link=3, info=2, align=8, entsize=24))  # .symtab
    body.extend(sh(15, 3, 0, off_strtab, len(strtab)))                                  # .strtab
    body.extend(sh(23, 3, 0, off_shstr, len(shstrtab)))                                 # .shstrtab
    return bytes(body)


SYNTHETIC_IMAGE_SHA256 = hashlib.sha256(synthetic_image_bytes()).hexdigest()
SYNTHETIC_OBJECT_SHA256 = hashlib.sha256(synthetic_object_bytes()).hexdigest()


# --------------------------------------------------------------------------- fixture and install sources
@dataclasses.dataclass(frozen=True)
class Fixture:
    path: Path
    kind: str            # "packed" | "image"
    sha256: str
    source: str
    analyze: bool        # packed programs are opened as-is; images are auto-analysed


@dataclasses.dataclass(frozen=True)
class Install:
    root: Path
    version: str
    source: str


FIXTURE_SOURCES = Registry("analyzer canary fixture source")
INSTALL_SOURCES = Registry("analyzer install source")
PAIR_SOURCES = Registry("parity fixture pair source")
CHECKER_SOURCES = Registry("parity checker source")


def _sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _ref(text: str) -> ObjectRef:
    value = str(text).strip()
    return ObjectRef(value if value.startswith("sha256:") else f"sha256:{value}")


class PackedFixture:
    """A packed program object (``sha256:`` ref) written to scratch and opened without analysis."""

    name = "packed"

    def materialize(self, source: str, *, objects: ObjectStore | None, scratch: Path) -> Fixture:
        if objects is None:
            raise NotConfigured("packed fixture needs an object store to fetch the ref from")
        ref = _ref(source)
        if not objects.exists(ref):
            raise Refused(f"analyzer-fixture-missing:{ref.hex[:16]}")
        path = materialize_object(objects, ref, scratch / "fixture.gzf")
        from ..ghidra_db.packed import is_packed_file

        if not is_packed_file(path):
            raise Refused(f"analyzer-fixture-not-packed:{ref.hex[:16]}")
        return Fixture(path=path, kind="packed", sha256=ref.hex, source=self.name, analyze=False)


class SyntheticFixture:
    """The deterministic minimal image from ``synthetic_image_bytes``, imported and auto-analysed."""

    name = "synthetic"

    def materialize(self, source: str, *, objects: ObjectStore | None, scratch: Path) -> Fixture:
        del source, objects
        scratch.mkdir(parents=True, exist_ok=True)
        path = scratch / SYNTHETIC_IMAGE_NAME
        path.write_bytes(synthetic_image_bytes())
        return Fixture(path=path, kind="image", sha256=SYNTHETIC_IMAGE_SHA256, source=self.name, analyze=True)


class RemoteFixture:
    """Slot: a fixture fetched from a remote fabric by ref; hand a ``sha256:`` ref to ``packed`` once
    the object is in the local store."""

    name = "remote"

    def materialize(self, source: str, *, objects: ObjectStore | None, scratch: Path) -> Fixture:
        raise NotConfigured("remote fixture source is a slot; put the packed program in the object store and pass its sha256: ref")


FIXTURE_SOURCES.register(PackedFixture.name, PackedFixture)
FIXTURE_SOURCES.register(SyntheticFixture.name, SyntheticFixture)
FIXTURE_SOURCES.register(RemoteFixture.name, RemoteFixture)


def _install_at(root: Path, source: str) -> Install:
    from ..corpus.determinism_basis import install_analyzer_version

    version = install_analyzer_version(root)
    if not version:
        raise NotConfigured(f"{source} install at the given root has no Ghidra/application.properties with application.version")
    return Install(root=root, version=version, source=source)


class OwnedInstall:
    """The install ``GHIDRA_INSTALL_DIR`` names."""

    name = "owned"

    def resolve(self, root: str | os.PathLike[str] | None) -> Install:
        raw = str(root or os.environ.get("GHIDRA_INSTALL_DIR", "")).strip()
        if not raw:
            raise NotConfigured("analyzer canary needs an install: GHIDRA_INSTALL_DIR or --analyzer-install <unpacked bundle root>")
        path = Path(raw).expanduser().resolve()
        if not path.is_dir():
            raise NotConfigured("analyzer install root is not a directory")
        return _install_at(path, self.name)


class FetchedBundle:
    """An analyzer bundle already unpacked to a root (the bundle's own layout: ``Ghidra/application.properties``)."""

    name = "bundle"

    def resolve(self, root: str | os.PathLike[str] | None) -> Install:
        if not root:
            raise NotConfigured("bundle install source needs the unpacked bundle root (--analyzer-install <dir>)")
        path = Path(root).expanduser().resolve()
        if not path.is_dir():
            raise NotConfigured("bundle root is not a directory")
        return _install_at(path, self.name)


INSTALL_SOURCES.register(OwnedInstall.name, OwnedInstall)
INSTALL_SOURCES.register(FetchedBundle.name, FetchedBundle)


# --------------------------------------------------------------------------- the analyzer probe (parent side)
@dataclasses.dataclass(frozen=True)
class InventoryRun:
    rows: tuple[tuple[int, int], ...]
    timed_out: bool
    returncode: int
    elapsed_s: float
    boot_s: float
    open_s: float
    live_version: str
    stderr_sha256: str
    failure: str = ""


def probe_inventory(fixture: Fixture, install: Install, *, scratch: Path, deadline_s: float) -> InventoryRun:
    """Boot the analyzer in a child under *deadline_s* and read the fixture's function inventory."""
    scratch.mkdir(parents=True, exist_ok=True)
    project_dir = scratch / "project"
    argv = [sys.executable, "-m", CHILD_MODULE, "--inventory", str(fixture.path), "--kind", fixture.kind,
            "--install", str(install.root), "--project-dir", str(project_dir)]
    argv.append("--analyze" if fixture.analyze else "--no-analyze")
    env = dict(os.environ)
    env["GHIDRA_INSTALL_DIR"] = str(install.root)
    env.setdefault("PYTHONUNBUFFERED", "1")
    outcome: RunOutcome = run_argv(argv, cwd=scratch, timeout_s=deadline_s, env=env)
    facts = _child_facts(outcome.stdout)
    failure = ""
    if outcome.timed_out:
        failure = f"analyzer-canary: probe timed out after {deadline_s:.0f}s"
    elif facts is None:
        failure = f"analyzer-canary: probe produced no inventory (exit {outcome.returncode})"
    elif facts.get("failure"):
        failure = f"analyzer-canary: {facts['failure']}"
    rows = tuple((int(e), int(s)) for e, s in (facts or {}).get("inventory", []))
    return InventoryRun(
        rows=rows, timed_out=outcome.timed_out, returncode=outcome.returncode, elapsed_s=outcome.elapsed_s,
        boot_s=float((facts or {}).get("boot_s", 0.0)), open_s=float((facts or {}).get("open_s", 0.0)),
        live_version=str((facts or {}).get("live_version", "")), stderr_sha256=outcome.stderr_sha256, failure=failure,
    )


def _child_facts(stdout: str) -> dict[str, Any] | None:
    for line in reversed(stdout.splitlines()):
        if line.startswith(CHILD_MARK):
            try:
                value = json.loads(line[len(CHILD_MARK):])
            except json.JSONDecodeError:
                return None
            return value if isinstance(value, dict) else None
    return None


# --------------------------------------------------------------------------- the analyzer probe (child side)
def _child_inventory(fixture: Path, kind: str, install: Path, project_dir: Path, analyze: bool) -> int:
    """Runs in the child: boot through ``ghidra_env.start``, open the fixture, print the inventory."""
    from ..corpus import ghidra_env

    started = time.monotonic()
    if not ghidra_env.start(install_dir=str(install), project_path=project_dir):
        print(CHILD_MARK + json.dumps({"failure": "analyzer boot refused (pyghidra or the install is missing)"}), flush=True)
        return 2
    boot_s = time.monotonic() - started
    from java.io import File  # type: ignore[import-not-found]
    from ghidra.base.project import GhidraProject  # type: ignore[import-not-found]

    from ..corpus.extract import live_analyzer_version

    opened = time.monotonic()
    project_dir.mkdir(parents=True, exist_ok=True)
    project = GhidraProject.createProject(str(project_dir), "canary", True)
    rc = 0
    try:
        if kind == "packed":
            project.getRootFolder().createFile("fixture", File(str(fixture)), ghidra_env.monitor())
            program = project.openProgram("/", "fixture", True)
        else:
            program = project.importProgram(File(str(fixture)))
            if analyze:
                GhidraProject.analyze(program)
        try:
            rows = []
            for f in program.getFunctionManager().getFunctions(True):
                if f.isExternal():
                    continue
                rows.append([int(f.getEntryPoint().getOffset()), int(f.getBody().getNumAddresses())])
        finally:
            project.close(program)
        facts = {"inventory": sorted(rows), "boot_s": round(boot_s, 3), "open_s": round(time.monotonic() - opened, 3),
                 "live_version": live_analyzer_version() or "", "analyze": bool(analyze), "kind": kind}
    except Exception as exc:  # noqa: BLE001 -- the parent turns this into a named failure
        facts = {"failure": f"{exc.__class__.__name__} while opening the fixture"}
        rc = 3
    finally:
        try:
            project.close()
        except Exception:  # noqa: BLE001
            pass
    print(CHILD_MARK + json.dumps(facts), flush=True)
    return rc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=CHILD_MODULE, description="analyzer canary child: open a fixture and print its inventory")
    parser.add_argument("--inventory", required=True, help="fixture path")
    parser.add_argument("--kind", choices=("packed", "image"), default="image")
    parser.add_argument("--install", required=True)
    parser.add_argument("--project-dir", required=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--analyze", dest="analyze", action="store_true", default=True)
    group.add_argument("--no-analyze", dest="analyze", action="store_false")
    args = parser.parse_args(argv)
    rc = _child_inventory(Path(args.inventory), args.kind, Path(args.install), Path(args.project_dir), bool(args.analyze))
    from ..corpus import ghidra_env

    ghidra_env.exit_after_jvm(rc)      # a process with a JVM never exits on its own (H14)
    return rc


# --------------------------------------------------------------------------- the analyzer hook
class AnalyzerLaneHook:
    """What ``AnalyzerCanary`` asks the lane for: install, fixture, capability parts, the probe."""

    name = "analyzer"

    def configure(self, *, fixture: str | None, install: str | os.PathLike[str] | None, objects: ObjectStore | None,
                  scratch: str | os.PathLike[str], fixture_source: str | None = None, install_source: str | None = None) -> dict[str, Any]:
        from ..corpus.determinism_basis import ANALYZER_OPTIONS_HASH

        scratch_dir = Path(scratch)
        install_name = install_source or ("bundle" if install else "owned")
        if install_name not in INSTALL_SOURCES:
            raise NotConfigured(f"analyzer canary: unknown install source {install_name!r}; known {INSTALL_SOURCES.names()}")
        resolved = INSTALL_SOURCES.get(install_name)().resolve(install)
        fixture_name = fixture_source or ("packed" if fixture else "synthetic")
        if fixture_name not in FIXTURE_SOURCES:
            raise NotConfigured(f"analyzer canary: unknown fixture source {fixture_name!r}; known {FIXTURE_SOURCES.names()}")
        fx = FIXTURE_SOURCES.get(fixture_name)().materialize(fixture or "", objects=objects, scratch=scratch_dir / "fixture")

        def inventory(scratch_for_run: str | os.PathLike[str], deadline_s: float) -> InventoryRun:
            return probe_inventory(fx, resolved, scratch=Path(scratch_for_run), deadline_s=deadline_s)

        return {
            "version": resolved.version, "options_hash": ANALYZER_OPTIONS_HASH, "install": resolved, "fixture": fx,
            "inventory": inventory,
        }

    def describe(self) -> dict[str, Any]:
        return {
            "fixture_sources": {"working": [PackedFixture.name, SyntheticFixture.name], "slots": [RemoteFixture.name]},
            "install_sources": {"working": [OwnedInstall.name, FetchedBundle.name], "slots": []},
            "synthetic_fixture_sha256": SYNTHETIC_IMAGE_SHA256,
            "probe": "child process; boots through corpus ghidra_env.start, ends with exit_after_jvm (H14)",
        }


# --------------------------------------------------------------------------- parity: pair and checker sources
@dataclasses.dataclass(frozen=True)
class FixturePair:
    target: Path
    candidate: Path
    target_sha256: str
    candidate_sha256: str
    source: str


class ObjectPair:
    """Two ``sha256:`` refs, target then candidate."""

    name = "objects"

    def materialize(self, source: Sequence[str] | None, *, objects: ObjectStore | None, scratch: Path) -> FixturePair:
        if not source or len(source) != 2:
            raise NotConfigured("object pair source needs two refs: target then candidate")
        if objects is None:
            raise NotConfigured("object pair source needs an object store to fetch the refs from")
        refs = [_ref(s) for s in source]
        for ref in refs:
            if not objects.exists(ref):
                raise Refused(f"parity-fixture-missing:{ref.hex[:16]}")
        target = materialize_object(objects, refs[0], scratch / "target.o")
        candidate = materialize_object(objects, refs[1], scratch / "candidate.o")
        return FixturePair(target, candidate, refs[0].hex, refs[1].hex, self.name)


class SyntheticPair:
    """``synthetic_object_bytes`` on both sides: the checker must report a match."""

    name = "synthetic"

    def materialize(self, source: Sequence[str] | None, *, objects: ObjectStore | None, scratch: Path) -> FixturePair:
        del source, objects
        scratch.mkdir(parents=True, exist_ok=True)
        data = synthetic_object_bytes()
        target = scratch / "target.o"
        candidate = scratch / "candidate.o"
        target.write_bytes(data)
        candidate.write_bytes(data)
        return FixturePair(target, candidate, SYNTHETIC_OBJECT_SHA256, SYNTHETIC_OBJECT_SHA256, self.name)


PAIR_SOURCES.register(ObjectPair.name, ObjectPair)
PAIR_SOURCES.register(SyntheticPair.name, SyntheticPair)


class HashPinnedChecker:
    """A checker binary object: its ref is its sha256, so the pin is the ref (an asserted pin must agree)."""

    name = "object"

    def resolve(self, source: str, pin: str, *, objects: ObjectStore | None, scratch: Path) -> Path:
        if objects is None:
            raise NotConfigured("object checker source needs an object store to fetch the ref from")
        ref = _ref(source)
        if pin and pin != ref.hex:
            raise Refused(f"parity-checker-hash-mismatch:{ref.hex[:16]}!={pin[:16]}")
        if not objects.exists(ref):
            raise Refused("parity-checker-missing:native")
        path = materialize_object(objects, ref, scratch / "checker")
        actual = _sha256_path(path)
        if actual != ref.hex:
            raise Refused(f"parity-checker-hash-mismatch:{actual[:16]}!={ref.hex[:16]}")
        path.chmod(0o755)
        return path


class PathChecker:
    """A configured path; its bytes must hash to the pin when one is given."""

    name = "path"

    def resolve(self, source: str, pin: str, *, objects: ObjectStore | None, scratch: Path) -> Path:
        del objects, scratch
        path = Path(source).expanduser()
        if not source or not path.is_file():
            raise Refused("parity-checker-missing:native")
        actual = _sha256_path(path)
        if pin and actual != pin:
            raise Refused(f"parity-checker-hash-mismatch:{actual[:16]}!={pin[:16]}")
        return path.resolve()


class BuiltChecker:
    """Slot: a checker built here from pinned source."""

    name = "built"

    def resolve(self, source: str, pin: str, *, objects: ObjectStore | None, scratch: Path) -> Path:
        raise NotConfigured("built checker source is a slot; hand a checker binary as a sha256: object ref or a path")


CHECKER_SOURCES.register(HashPinnedChecker.name, HashPinnedChecker)
CHECKER_SOURCES.register(PathChecker.name, PathChecker)
CHECKER_SOURCES.register(BuiltChecker.name, BuiltChecker)


@dataclasses.dataclass(frozen=True)
class ReceiptRun:
    receipt: Mapping[str, Any]
    timed_out: bool
    returncode: int
    elapsed_s: float
    stderr_sha256: str
    failure: str = ""


def run_parity_checker(checker: Any, pair: FixturePair, *, scratch: Path, deadline_s: float) -> ReceiptRun:
    """Run the native checker on the pair under *deadline_s*; the receipt is the ``parity-check`` shape minus ``output``."""
    from ..objdiff_verification import parse_objdiff_report
    from .parity import RECEIPT_SCHEMA

    scratch.mkdir(parents=True, exist_ok=True)
    outcome = run_argv(checker.argv(pair.target, pair.candidate, ""), cwd=scratch, timeout_s=deadline_s, env=checker.env())
    if outcome.timed_out:
        return ReceiptRun({}, True, outcome.returncode, outcome.elapsed_s, outcome.stderr_sha256, f"parity-canary: checker timed out after {deadline_s:.0f}s")
    report = parse_objdiff_report(outcome.returncode, outcome.stdout)
    receipt = {k: v for k, v in report.items() if k != "output"}
    receipt.setdefault("schema", RECEIPT_SCHEMA)
    receipt.update({
        "verifier_id": checker.verifier_id, "verifier": checker.flavour, "symbol": "",
        "sides": {"target": pair.target_sha256, "candidate": pair.candidate_sha256}, "grade": str(report.get("status", "error")),
    })
    return ReceiptRun(receipt, False, outcome.returncode, outcome.elapsed_s, outcome.stderr_sha256)


def probe_objdump(path: str | os.PathLike[str] | None, *, scratch: Path, deadline_s: float) -> dict[str, Any]:
    """The target objdump ``mkobj-target`` needs: sha256 and a ``--version`` run, or the refusal by name."""
    raw = str(path or os.environ.get(OBJDUMP_ENV, "")).strip()
    if not raw or not Path(raw).expanduser().is_file():
        return {"failure": f"mkobj-target: target objdump absent (--parity-objdump <path> or {OBJDUMP_ENV})"}
    binary = Path(raw).expanduser().resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    outcome = run_argv([str(binary), "--version"], cwd=scratch, timeout_s=deadline_s)
    facts: dict[str, Any] = {"sha256": _sha256_path(binary), "returncode": outcome.returncode, "wall_s": round(outcome.elapsed_s, 3)}
    if outcome.timed_out:
        facts["failure"] = f"mkobj-target: target objdump timed out after {deadline_s:.0f}s"
    elif outcome.returncode != 0:
        facts["failure"] = f"mkobj-target: target objdump exited {outcome.returncode}"
    else:
        facts["version_line"] = outcome.stdout.splitlines()[0].strip() if outcome.stdout.strip() else ""
    return facts


# --------------------------------------------------------------------------- the parity hook
class ParityLaneHook:
    """What ``ParityCanary`` asks the lane for: the checker (hash verified), the pair, the run."""

    name = "parity"

    def configure(self, *, checker: str | None, checker_hash: str, objects: ObjectStore | None, scratch: str | os.PathLike[str],
                  fixture_pair: Sequence[str] | None = None, checker_source: str | None = None, pair_source: str | None = None) -> dict[str, Any]:
        from .parity import register_native

        scratch_dir = Path(scratch)
        source_name = checker_source or ("object" if checker and _looks_like_ref(checker) else "path")
        if source_name not in CHECKER_SOURCES:
            raise NotConfigured(f"parity canary: unknown checker source {source_name!r}; known {CHECKER_SOURCES.names()}")
        if not checker and source_name == "path":
            checker = os.environ.get("AGENT_DECOMPILE_OBJDIFF", "").strip()
        path = CHECKER_SOURCES.get(source_name)().resolve(checker or "", checker_hash, objects=objects, scratch=scratch_dir / "checker")
        native = register_native(path)
        pair_name = pair_source or ("objects" if fixture_pair else "synthetic")
        if pair_name not in PAIR_SOURCES:
            raise NotConfigured(f"parity canary: unknown pair source {pair_name!r}; known {PAIR_SOURCES.names()}")
        pair = PAIR_SOURCES.get(pair_name)().materialize(fixture_pair, objects=objects, scratch=scratch_dir / "pair")

        def run(scratch_for_run: str | os.PathLike[str], deadline_s: float) -> ReceiptRun:
            return run_parity_checker(native, pair, scratch=Path(scratch_for_run), deadline_s=deadline_s)

        return {"checker_sha256": native.verifier_id.split(":", 1)[1], "verifier_id": native.verifier_id, "checker_source": source_name,
                "pair": pair, "run": run}

    def probe_objdump(self, path: str | os.PathLike[str] | None, *, scratch: str | os.PathLike[str], deadline_s: float) -> dict[str, Any]:
        return probe_objdump(path, scratch=Path(scratch), deadline_s=deadline_s)

    def describe(self) -> dict[str, Any]:
        return {
            "checker_sources": {"working": [HashPinnedChecker.name, PathChecker.name], "slots": [BuiltChecker.name]},
            "pair_sources": {"working": [ObjectPair.name, SyntheticPair.name], "slots": []},
            "synthetic_object_sha256": SYNTHETIC_OBJECT_SHA256,
            "objdump": {"capability": "objdump:<sha256>", "refusal": "mkobj-target", "env": OBJDUMP_ENV},
        }


def _looks_like_ref(text: str) -> bool:
    value = text.strip()
    if value.startswith("sha256:"):
        value = value[7:]
    return len(value) == 64 and all(c in "0123456789abcdef" for c in value)


analyzer_hook = AnalyzerLaneHook()
parity_hook = ParityLaneHook()


def _bind_hooks() -> None:
    from agentdecompile_grid.worker.canaries import AnalyzerCanary, ParityCanary

    AnalyzerCanary.HOOKS.register(analyzer_hook.name, analyzer_hook, replace=True)
    ParityCanary.HOOKS.register(parity_hook.name, parity_hook, replace=True)


_bind_hooks()


def describe() -> dict[str, Any]:
    return {"analyzer": analyzer_hook.describe(), "parity": parity_hook.describe()}


__all__ = [
    "AnalyzerLaneHook", "BuiltChecker", "CHECKER_SOURCES", "FIXTURE_SOURCES", "FetchedBundle", "Fixture", "FixturePair", "HashPinnedChecker",
    "INSTALL_SOURCES", "Install", "InventoryRun", "OBJDUMP_ENV", "ObjectPair", "OwnedInstall", "PAIR_SOURCES", "PackedFixture", "ParityLaneHook",
    "PathChecker", "ReceiptRun", "RemoteFixture", "SYNTHETIC_IMAGE_SHA256", "SYNTHETIC_OBJECT_SHA256", "SyntheticFixture", "SyntheticPair",
    "analyzer_hook", "describe", "main", "parity_hook", "probe_inventory", "probe_objdump", "run_parity_checker", "synthetic_image_bytes",
    "synthetic_object_bytes",
]


if __name__ == "__main__":
    sys.exit(main())
