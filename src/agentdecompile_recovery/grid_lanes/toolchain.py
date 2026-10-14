"""Toolchain manifest identity (U132) and the join canary's lane side (U163).

A toolchain is named by the **declared manifest** of its tree, never by where it sits or when
it was copied.  ``ToolchainManifest.entries`` is the sorted tuple of ``(relative path, sha256 of
the bytes)``; ``identity_hash_for`` is the sha256 of exactly those pairs.  No host state, no
install path, no file time and no size enters the hash, so two copies of one tree at different
paths and mtimes give one identity, and one flipped byte in any declared file gives another.
Files a manifest does not declare are ignored by design (``verify_tree`` counts them as
``extra_ignored``): a node may keep logs or caches next to the tree without changing its name.

The **probe** (``ProbeSpec``) is the canary fingerprint and stays *outside* the identity: which
translation unit in the tree to compile, the pinned masked-object hash the compile must reach,
the compiler argv template, and the masker and probe-compiler names.  Changing the pin re-keys
the canary, not the toolchain.

Registries (each with the working implementation named first):

* ``MANIFEST_SOURCES`` -- ``file`` (``FileManifest``, a JSON file, working), ``object``
  (``ObjectManifest``, the JSON fetched from the object store by hash, working), ``archive``
  (``ArchiveManifest``, a manifest read out of a packed toolchain object, slot).
* ``PROBE_COMPILERS`` -- ``native`` (``NativeCompiler``: the argv template run directly under the
  deadline, working), ``compatibility-layer`` (``CompatibilityLayerCompiler``, slot; contract in
  its docstring), ``container`` (``ContainerCompiler``, slot).
* ``OBJECT_MASKERS`` -- ``masked-coff`` (``MaskedCoff``: delegates to
  ``compile.masked_coff_sha256``, the one masking rule the compile lane's ``verify`` compares --
  there is no second masker), ``masked-elf`` (``MaskedElf``, slot).

``register_toolchain(identity_hash, root, manifest=...)`` binds a proved root into the compile
lane's existing ``TOOLCHAINS`` registry (``compile.py``); the mapping lives there, this module
only checks the identity before handing over.  Importing this module binds ``lane_hook`` into
``agentdecompile_grid.worker.canaries.ToolchainCanary.HOOKS`` so ``adgrid join --toolchain-path``
reaches it by name; the grid package never imports this one.

Manifest JSON (``MANIFEST_SCHEMA``)::

    {"schema": "agentdecompile.toolchain-manifest.v1",
     "entries": [["bin/cc", "<sha256>"], ["probe/probe.c", "<sha256>"], ...],
     "probe": {"tu_relpath": "probe/probe.c", "expected_masked_hash": "<sha256>",
               "compiler_argv_template": ["{root}/bin/cc", "{source}", "{output}"],
               "env_template": {"TOOLCHAIN_ROOT": "{root}"},
               "compiler": "native", "masker": "masked-coff"}}

Only ``{root}``, ``{source}``, ``{output}`` and ``{scratch}`` are substituted, per argv element,
never through a shell.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Protocol, runtime_checkable

from agentdecompile_grid.core import NotConfigured, ObjectRef, ObjectStore, Refused, Registry

from ._common import run_argv

MANIFEST_SCHEMA = "agentdecompile.toolchain-manifest.v1"
MANIFEST_FILENAME = "toolchain-manifest.json"


# --------------------------------------------------------------------------- manifest
def _clean_relpath(rel: str) -> str:
    p = PurePosixPath(str(rel).replace(os.sep, "/"))
    if p.is_absolute() or not p.parts or any(part in ("..", "") for part in p.parts):
        raise Refused(f"toolchain-manifest-bad-relpath:{hashlib.sha256(str(rel).encode()).hexdigest()[:12]}")
    return p.as_posix()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclasses.dataclass(frozen=True)
class ProbeSpec:
    """The canary fingerprint: outside the identity, compared on every join."""

    tu_relpath: str
    expected_masked_hash: str
    compiler_argv_template: tuple[str, ...]
    env_template: tuple[tuple[str, str], ...] = ()
    compiler: str = "native"
    masker: str = "masked-coff"

    @classmethod
    def from_mapping(cls, m: Mapping[str, Any]) -> "ProbeSpec":
        argv = tuple(str(a) for a in (m.get("compiler_argv_template") or ()))
        if not argv:
            raise Refused("toolchain-manifest-probe-argv-missing")
        env = tuple(sorted((str(k), str(v)) for k, v in (m.get("env_template") or {}).items()))
        return cls(
            tu_relpath=_clean_relpath(m.get("tu_relpath", "")), expected_masked_hash=str(m.get("expected_masked_hash", "")),
            compiler_argv_template=argv, env_template=env, compiler=str(m.get("compiler") or "native"),
            masker=str(m.get("masker") or "masked-coff"),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "tu_relpath": self.tu_relpath, "expected_masked_hash": self.expected_masked_hash,
            "compiler_argv_template": list(self.compiler_argv_template), "env_template": dict(self.env_template),
            "compiler": self.compiler, "masker": self.masker,
        }


def identity_hash_for(entries: "ToolchainManifest | Mapping[str, str] | Any") -> str:
    """sha256 over the sorted ``(relpath, sha256)`` pairs and nothing else (U132).

    Accepts a ``ToolchainManifest``, a ``{relpath: sha256}`` mapping or an iterable of pairs.
    Each pair contributes ``relpath\\0sha256``; pairs are joined by ``\\n``.  Duplicate paths are
    refused: an identity must name one byte string per path.
    """
    if isinstance(entries, ToolchainManifest):
        pairs = entries.entries
    elif isinstance(entries, Mapping):
        pairs = tuple((str(k), str(v)) for k, v in entries.items())
    else:
        pairs = tuple((str(k), str(v)) for k, v in entries)
    normalised = sorted((_clean_relpath(rel), sha.lower()) for rel, sha in pairs)
    if len({rel for rel, _ in normalised}) != len(normalised):
        raise Refused("toolchain-manifest-duplicate-relpath")
    return hashlib.sha256(b"\n".join(rel.encode("utf-8") + b"\0" + sha.encode("ascii") for rel, sha in normalised)).hexdigest()


@dataclasses.dataclass(frozen=True)
class ToolchainManifest:
    """The declared tree: sorted ``(relpath, sha256)`` entries and the probe that fingerprints it."""

    entries: tuple[tuple[str, str], ...]
    probe: ProbeSpec | None = None

    def __post_init__(self) -> None:
        cleaned = tuple(sorted((_clean_relpath(rel), str(sha).lower()) for rel, sha in self.entries))
        object.__setattr__(self, "entries", cleaned)
        if len({rel for rel, _ in cleaned}) != len(cleaned):
            raise Refused("toolchain-manifest-duplicate-relpath")

    @property
    def identity_hash(self) -> str:
        return identity_hash_for(self)

    @property
    def paths(self) -> frozenset[str]:
        return frozenset(rel for rel, _ in self.entries)

    def sha256_of(self, relpath: str) -> str | None:
        return dict(self.entries).get(_clean_relpath(relpath))

    def with_probe(self, probe: ProbeSpec | Mapping[str, Any] | None) -> "ToolchainManifest":
        spec = probe if isinstance(probe, ProbeSpec) or probe is None else ProbeSpec.from_mapping(probe)
        return dataclasses.replace(self, probe=spec)

    @classmethod
    def from_tree(cls, root: str | Path, *, exclude: tuple[str, ...] = (MANIFEST_FILENAME,), probe: ProbeSpec | Mapping[str, Any] | None = None) -> "ToolchainManifest":
        """Declare a manifest from a tree: every regular file's bytes, no path, no time, no mode."""
        resolved = Path(root).expanduser().resolve()
        if not resolved.is_dir():
            raise Refused(f"toolchain-root-missing:{hashlib.sha256(str(resolved).encode()).hexdigest()[:12]}")
        entries: list[tuple[str, str]] = []
        for path in sorted(p for p in resolved.rglob("*") if p.is_file()):
            rel = path.relative_to(resolved).as_posix()
            if rel in exclude:
                continue
            entries.append((rel, _sha256_file(path)))
        return cls(tuple(entries)).with_probe(probe)

    @classmethod
    def from_mapping(cls, m: Mapping[str, Any]) -> "ToolchainManifest":
        if m.get("schema") != MANIFEST_SCHEMA:
            raise Refused(f"toolchain-manifest-schema:{m.get('schema')!s}"[:80])
        raw = m.get("entries")
        if not isinstance(raw, (list, tuple)) or not raw:
            raise Refused("toolchain-manifest-entries-missing")
        entries = []
        for item in raw:
            if isinstance(item, Mapping):
                entries.append((str(item.get("path", "")), str(item.get("sha256", ""))))
            else:
                rel, sha = item
                entries.append((str(rel), str(sha)))
        probe = m.get("probe")
        return cls(tuple(entries)).with_probe(probe if isinstance(probe, Mapping) else None)

    @classmethod
    def from_bytes(cls, data: bytes) -> "ToolchainManifest":
        try:
            return cls.from_mapping(json.loads(data.decode("utf-8")))
        except (ValueError, UnicodeDecodeError) as exc:
            raise Refused(f"toolchain-manifest-unreadable:{exc.__class__.__name__}") from exc

    def to_mapping(self) -> dict[str, Any]:
        out: dict[str, Any] = {"schema": MANIFEST_SCHEMA, "entries": [list(e) for e in self.entries]}
        if self.probe is not None:
            out["probe"] = self.probe.to_mapping()
        return out

    def to_bytes(self) -> bytes:
        return json.dumps(self.to_mapping(), sort_keys=True, indent=1).encode("utf-8") + b"\n"


@dataclasses.dataclass(frozen=True)
class TreeReport:
    missing: tuple[str, ...]
    mismatched: tuple[str, ...]
    extra_ignored: int
    checked: int

    @property
    def ok(self) -> bool:
        return not self.missing and not self.mismatched

    def to_mapping(self) -> dict[str, Any]:
        return {"missing": list(self.missing), "mismatched": list(self.mismatched), "extra_ignored": self.extra_ignored, "checked": self.checked, "ok": self.ok}


def verify_tree(root: str | Path, manifest: ToolchainManifest) -> TreeReport:
    """Every declared entry present with the declared bytes; undeclared files are counted, not judged."""
    resolved = Path(root).expanduser().resolve()
    if not resolved.is_dir():
        raise Refused(f"toolchain-root-missing:{hashlib.sha256(str(resolved).encode()).hexdigest()[:12]}")
    missing: list[str] = []
    mismatched: list[str] = []
    for rel, sha in manifest.entries:
        path = resolved / rel
        if not path.is_file():
            missing.append(rel)
        elif _sha256_file(path) != sha:
            mismatched.append(rel)
    declared = manifest.paths
    extra = sum(1 for p in resolved.rglob("*") if p.is_file() and p.relative_to(resolved).as_posix() not in declared)
    return TreeReport(tuple(missing), tuple(mismatched), extra, len(manifest.entries))


# --------------------------------------------------------------------------- manifest sources
MANIFEST_SOURCES = Registry("toolchain manifest source")


class FileManifest:
    """``file``: a manifest JSON on this node (working)."""

    name = "file"

    @staticmethod
    def load(source: str | Path, objects: ObjectStore | None = None) -> ToolchainManifest:
        path = Path(source).expanduser()
        if path.is_dir():
            path = path / MANIFEST_FILENAME
        if not path.is_file():
            raise Refused(f"toolchain-manifest-missing:{hashlib.sha256(str(path).encode()).hexdigest()[:12]}")
        return ToolchainManifest.from_bytes(path.read_bytes())


class ObjectManifest:
    """``object``: the manifest JSON fetched from the object store by its hash (working)."""

    name = "object"

    @staticmethod
    def load(source: str | ObjectRef, objects: ObjectStore | None = None) -> ToolchainManifest:
        ref = ObjectRef(str(source))
        if objects is None:
            raise NotConfigured("object manifest needs an object store to fetch from")
        if not objects.exists(ref):
            raise Refused(f"toolchain-manifest-object-missing:{ref.hex[:12]}")
        return ToolchainManifest.from_bytes(objects.get(ref))


class ArchiveManifest:
    """``archive`` (slot): a manifest read out of a packed toolchain object.

    Contract: the packed object is content-addressed, carries ``MANIFEST_FILENAME`` at its root,
    and unpacks to a temp root the canary then proves through the same ``verify_tree`` +
    probe path as an owned install (U163: a fetched toolchain passes the same canary).
    """

    name = "archive"

    @staticmethod
    def load(source: str | ObjectRef, objects: ObjectStore | None = None) -> ToolchainManifest:
        raise NotConfigured("archive manifest source is a slot: it needs the packed-toolchain unpacker (content-addressed archive with toolchain-manifest.json at its root)")


MANIFEST_SOURCES.register("file", FileManifest)
MANIFEST_SOURCES.register("object", ObjectManifest)
MANIFEST_SOURCES.register("archive", ArchiveManifest)


def load_manifest(source: str | Path | ObjectRef | ToolchainManifest, *, objects: ObjectStore | None = None) -> ToolchainManifest:
    """A path (file or a tree holding ``toolchain-manifest.json``) or a ``sha256:`` ref -> manifest."""
    if isinstance(source, ToolchainManifest):
        return source
    text = str(source)
    if text.startswith("sha256:"):
        return MANIFEST_SOURCES.get("object").load(text, objects)
    return MANIFEST_SOURCES.get("file").load(text, objects)


# --------------------------------------------------------------------------- probe compilers
@dataclasses.dataclass(frozen=True)
class ProbeRun:
    returncode: int
    timed_out: bool
    elapsed_s: float
    stderr_sha256: str
    produced: bool


@runtime_checkable
class ProbeCompiler(Protocol):
    name: str

    def compile(self, root: Path, source: Path, output: Path, *, scratch: Path, deadline_s: float) -> ProbeRun: ...


class _Template(dict):
    def __missing__(self, key: str) -> str:
        raise Refused(f"toolchain-probe-template-key:{key[:32]}")


def render_argv(template: tuple[str, ...], *, root: Path, source: Path, output: Path, scratch: Path) -> list[str]:
    values = _Template(root=str(root), source=str(source), output=str(output), scratch=str(scratch))
    return [str(a).format_map(values) for a in template]


class NativeCompiler:
    """``native``: run the probe's argv template directly under the deadline (working)."""

    name = "native"

    def __init__(self, argv_template: tuple[str, ...], env_template: Mapping[str, str] | tuple[tuple[str, str], ...] = ()) -> None:
        self.argv_template = tuple(argv_template)
        self.env_template = tuple(env_template.items()) if isinstance(env_template, Mapping) else tuple(env_template)

    @classmethod
    def from_probe(cls, probe: ProbeSpec) -> "NativeCompiler":
        return cls(probe.compiler_argv_template, probe.env_template)

    def compile(self, root: Path, source: Path, output: Path, *, scratch: Path, deadline_s: float) -> ProbeRun:
        argv = render_argv(self.argv_template, root=root, source=source, output=output, scratch=scratch)
        env = dict(os.environ)
        env.update({k: v for k, v in render_env(self.env_template, root=root, source=source, output=output, scratch=scratch)})
        env.setdefault("TOOLCHAIN_ROOT", str(root))
        outcome = run_argv(argv, cwd=scratch, timeout_s=deadline_s, env=env)
        produced = output.is_file() and output.stat().st_size > 0
        return ProbeRun(outcome.returncode, outcome.timed_out, outcome.elapsed_s, outcome.stderr_sha256, produced)


def render_env(template: tuple[tuple[str, str], ...], **values: Path) -> list[tuple[str, str]]:
    mapping = _Template({k: str(v) for k, v in values.items()})
    return [(k, str(v).format_map(mapping)) for k, v in template]


class CompatibilityLayerCompiler:
    """``compatibility-layer`` (slot): the target toolchain runs under a persistent compatibility
    server rather than a fresh process per probe.

    Contract: one server process per node, started once by the first canary that needs it,
    health-checked before every probe (a dead server is restarted once, then the probe is
    refused by name), and reused by every later probe and compile on the node; the server's
    prefix directory is content-addressed alongside the toolchain so it never enters the
    identity.  ``compile`` then submits the rendered argv to the live server under the same
    deadline as ``NativeCompiler``.
    """

    name = "compatibility-layer"

    def __init__(self, argv_template: tuple[str, ...], env_template: Mapping[str, str] | tuple[tuple[str, str], ...] = ()) -> None:
        self.argv_template = tuple(argv_template)
        self.env_template = tuple(env_template.items()) if isinstance(env_template, Mapping) else tuple(env_template)

    @classmethod
    def from_probe(cls, probe: ProbeSpec) -> "CompatibilityLayerCompiler":
        return cls(probe.compiler_argv_template, probe.env_template)

    def compile(self, root: Path, source: Path, output: Path, *, scratch: Path, deadline_s: float) -> ProbeRun:
        raise NotConfigured("compatibility-layer probe compiler is a slot: it needs the persistent per-node server (start once, health-check, reuse) and its prefix directory")


class ContainerCompiler:
    """``container`` (slot): the probe runs inside a pinned container image holding the toolchain.

    Contract: the image is content-addressed and named in the probe's ``env_template``; the
    root is bind-mounted read-only; the deadline is enforced from outside the container.
    """

    name = "container"

    def __init__(self, argv_template: tuple[str, ...], env_template: Mapping[str, str] | tuple[tuple[str, str], ...] = ()) -> None:
        self.argv_template = tuple(argv_template)
        self.env_template = tuple(env_template.items()) if isinstance(env_template, Mapping) else tuple(env_template)

    @classmethod
    def from_probe(cls, probe: ProbeSpec) -> "ContainerCompiler":
        return cls(probe.compiler_argv_template, probe.env_template)

    def compile(self, root: Path, source: Path, output: Path, *, scratch: Path, deadline_s: float) -> ProbeRun:
        raise NotConfigured("container probe compiler is a slot: it needs a pinned container image and a runtime on this node")


PROBE_COMPILERS = Registry("probe compiler")
PROBE_COMPILERS.register("native", NativeCompiler)
PROBE_COMPILERS.register("compatibility-layer", CompatibilityLayerCompiler)
PROBE_COMPILERS.register("container", ContainerCompiler)


# --------------------------------------------------------------------------- object maskers
@runtime_checkable
class ObjectMasker(Protocol):
    name: str

    def masked_hash(self, data: bytes) -> str: ...


class MaskedCoff:
    """``masked-coff``: the compile lane's own rule (``compile.masked_coff_sha256``: the file
    header's ``TimeDateStamp`` zeroed; anonymous objects and short inputs refused).  Delegating
    keeps one masker: the canary pin and ``compile-attempt``'s receipt field agree by construction."""

    name = "masked-coff"

    def masked_hash(self, data: bytes) -> str:
        from .compile import masked_coff_sha256

        return masked_coff_sha256(data)


class MaskedElf:
    """``masked-elf`` (slot): the same idea for ELF relocatables (section-header timestamps do not
    exist there; the fields to mask are ``.comment`` and build-id notes)."""

    name = "masked-elf"

    def masked_hash(self, data: bytes) -> str:
        raise NotConfigured("masked-elf masker is a slot: it needs the ELF note/.comment masking rule pinned next to the compile lane's verify")


OBJECT_MASKERS = Registry("object masker")
OBJECT_MASKERS.register("masked-coff", MaskedCoff)
OBJECT_MASKERS.register("masked-elf", MaskedElf)


# --------------------------------------------------------------------------- registration
def manifest_for_root(root: str | Path) -> ToolchainManifest:
    """The in-tree ``toolchain-manifest.json`` when present, else a manifest declared from the tree."""
    path = Path(root).expanduser() / MANIFEST_FILENAME
    return FileManifest.load(path) if path.is_file() else ToolchainManifest.from_tree(root)


def register_toolchain(identity_hash: str, root: str | Path, *, manifest: ToolchainManifest | None = None,
                       script: str | Path | None = None, layer_prefix: str | Path | None = None, replace: bool = True) -> Any:
    """Bind *root* (proved by canary) under *identity_hash* in the compile lane's ``TOOLCHAINS``.

    The manifest's identity must equal *identity_hash*; a mismatch is refused by name before the
    registry is touched.  *layer_prefix* is the compatibility layer's prefix directory when the
    toolchain runs under one (it never enters the identity).  Returns the compile lane's
    ``ToolchainRoot``.
    """
    from . import compile as compile_lane

    declared = manifest if manifest is not None else manifest_for_root(root)
    if declared.identity_hash != identity_hash:
        raise Refused(f"toolchain-identity-mismatch:{identity_hash[:12]}!={declared.identity_hash[:12]}")
    return compile_lane.register_toolchain(root, manifest=declared, script=script, wineprefix=layer_prefix, replace=replace)


# --------------------------------------------------------------------------- the canary's lane hook
class ToolchainLaneHook:
    """What ``ToolchainCanary`` asks a lane for: manifest, tree check, compiler, masker, binding."""

    name = "toolchain"

    def configure(self, *, root: str | Path | None, manifest_source: Any, objects: ObjectStore | None,
                  script: str | Path | None = None, layer_prefix: str | Path | None = None) -> dict[str, Any]:
        if root is None or not Path(root).expanduser().is_dir():
            raise NotConfigured("toolchain canary needs --toolchain-path <dir> (an owned install or a fetched toolchain unpacked to a temp root)")
        resolved = Path(root).expanduser().resolve()
        manifest = load_manifest(manifest_source, objects=objects) if manifest_source else manifest_for_root(resolved)
        if manifest.probe is None:
            raise NotConfigured("toolchain canary needs a manifest with a probe block (tu_relpath, expected_masked_hash, compiler_argv_template)")
        compiler_cls = PROBE_COMPILERS.get(manifest.probe.compiler) if manifest.probe.compiler in PROBE_COMPILERS else None
        if compiler_cls is None:
            raise NotConfigured(f"toolchain canary: unknown probe compiler {manifest.probe.compiler!r}; known {PROBE_COMPILERS.names()}")
        masker_cls = OBJECT_MASKERS.get(manifest.probe.masker) if manifest.probe.masker in OBJECT_MASKERS else None
        if masker_cls is None:
            raise NotConfigured(f"toolchain canary: unknown masker {manifest.probe.masker!r}; known {OBJECT_MASKERS.names()}")

        def on_proven(identity_hash: str) -> dict[str, Any]:
            tc = register_toolchain(identity_hash, resolved, manifest=manifest, script=script, layer_prefix=layer_prefix)
            return {"registered": True, "files": tc.files}

        return {
            "manifest": manifest, "root": resolved, "verify_tree": verify_tree,
            "compiler": compiler_cls.from_probe(manifest.probe), "masker": masker_cls(), "on_proven": on_proven,
        }


lane_hook = ToolchainLaneHook()


def _bind_hook() -> None:
    from agentdecompile_grid.worker.canaries import ToolchainCanary

    ToolchainCanary.HOOKS.register(lane_hook.name, lane_hook, replace=True)


_bind_hook()


def describe() -> dict[str, Any]:
    return {
        "manifest_schema": MANIFEST_SCHEMA, "manifest_filename": MANIFEST_FILENAME,
        "manifest_sources": {"working": ["file", "object"], "slots": ["archive"]},
        "probe_compilers": {"working": ["native"], "slots": ["compatibility-layer", "container"]},
        "object_maskers": {"working": ["masked-coff"], "slots": ["masked-elf"]},
        "identity": "sha256 over sorted (relpath\\0sha256) pairs joined by \\n; probe excluded",
    }


__all__ = [
    "ArchiveManifest", "CompatibilityLayerCompiler", "ContainerCompiler", "FileManifest", "MANIFEST_FILENAME", "MANIFEST_SCHEMA",
    "MANIFEST_SOURCES", "MaskedCoff", "MaskedElf", "NativeCompiler", "OBJECT_MASKERS", "ObjectManifest", "ObjectMasker", "PROBE_COMPILERS",
    "ProbeCompiler", "ProbeRun", "ProbeSpec", "ToolchainLaneHook", "ToolchainManifest", "TreeReport", "describe", "identity_hash_for",
    "lane_hook", "load_manifest", "manifest_for_root", "register_toolchain", "render_argv", "verify_tree",
]
