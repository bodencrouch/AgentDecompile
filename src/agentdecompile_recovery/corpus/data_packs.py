"""Registry for L3 data packs: engine adapters and build profiles as data.

An engine adapter (script-API name to key map, this-kind semantics, site
policy, adapter keys, overlays, aliases, build profiles, mask policy) is
never code in the core. It is a directory under one declared root::

    <root>/<pack_id>/pack.json
    <root>/<pack_id>/<entries...>

``pack.json`` (schema v1)::

    {"schema_version": 1,
     "engine_class": "script-vm-a",
     "arch_class": "x86-32",
     "entries": {"site_policy": "site_policy.json",
                 "adapter_map": "adapter_map.json"}}

Discovery is sorted by directory name. Each pack carries a ``content_hash``
over every file in it (manifest included) and the sorted pack list is the
``data_packs`` field of the determinism basis, so a pack change is a basis
change. Selecting an adapter for a build that no pack covers raises
:class:`MissingAdapter`; nothing here has a default engine or a default
architecture, and the core never enumerates engines.

Root path: explicit argument, else ``corpus_config.data_packs_root()`` (the
``AGENT_DECOMPILE_DATA_PACKS_ROOT`` environment variable or the config
directory's ``data_packs.json``). No root declared means the registry
reports :attr:`RegistryStatus.NO_ROOT` and declares zero packs; there is no
bundled root.

Every pack-related refusal is a :class:`PackError`. :class:`MissingAdapter`
is also a :class:`determinism_basis.BasisError` so the keyed verbs refuse it
by name (exit 2) without learning anything about packs.
"""

from __future__ import annotations

import enum
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Mapping, Protocol, runtime_checkable

from .determinism_basis import BasisError

MANIFEST_NAME = "pack.json"

#: Entry kinds with a consumer on this branch, sorted. The vocabulary is
#: open: a pack may declare kinds nobody reads yet; they still hash.
KNOWN_ENTRY_KINDS = (
    "adapter_map",
    "aliases",
    "api_map",
    "build_profiles",
    "mask_policy",
    "overlay",
    "site_policy",
)

_MANIFEST_KEYS_V1 = ("arch_class", "engine_class", "entries", "schema_version")


# --- refusals ----------------------------------------------------------------


class PackError(ValueError):
    """A pack, a root or a manifest cannot be used as declared."""


class PackRootMissing(PackError):
    """A root was declared but is not a directory."""


class PackSchemaError(PackError):
    """A ``pack.json`` does not satisfy its declared schema."""


class DuplicatePack(PackError):
    """Two packs under one root claim the same ``(engine_class, arch_class)``."""


class MissingEntry(PackError):
    """A pack declares no entry of the requested kind."""

    def __init__(self, pack_id: str, kind: str, declared: tuple[str, ...]):
        self.pack_id = pack_id
        self.kind = kind
        self.declared = declared
        super().__init__(f"missing_entry: pack {pack_id!r} declares no {kind!r} entry (declared: {list(declared)})")


class MissingAdapter(PackError, BasisError):
    """No pack covers ``(engine_class, arch_class)``. Never resolved by a default."""

    def __init__(self, engine_class: str, arch_class: str, searched_root: Path | None):
        self.engine_class = engine_class
        self.arch_class = arch_class
        self.searched_root = searched_root
        where = f"root {root_token(searched_root)}" if searched_root is not None else "no data-pack root declared"
        super().__init__(
            f"missing_adapter: no data pack for engine_class={engine_class!r} arch_class={arch_class!r} ({where})"
        )


class RegistryStatus(str, enum.Enum):
    NO_ROOT = "no_root"  # nothing declared; zero packs; not a refusal
    EMPTY = "empty"  # root declared and present; no pack directory in it
    READY = "ready"  # at least one pack loaded


# --- hashing helpers ---------------------------------------------------------


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def root_token(root: Path | None) -> str | None:
    """Short opaque id for a root path so reports never carry the path itself."""
    if root is None:
        return None
    return _sha256_bytes(str(root).encode("utf-8"))[:16]


def pack_content_hash(root: Path) -> str:
    """sha256 over the sorted ``<relpath> <sha256>`` lines of every file under *root*.

    Files only, POSIX separators, the manifest included; directory order and
    file order on disk never matter.
    """
    root = Path(root)
    lines = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        lines.append(f"{rel} {_sha256_bytes(path.read_bytes())}")
    return _sha256_bytes("\n".join(lines).encode("utf-8"))


# --- the manifest --------------------------------------------------------------


@dataclass(frozen=True)
class PackManifest:
    """One loaded pack. ``entries`` maps entry kind to a path relative to ``root``."""

    pack_id: str
    schema_version: int
    engine_class: str
    arch_class: str
    entries: Mapping[str, str]
    content_hash: str
    root: Path

    @property
    def key(self) -> tuple[str, str]:
        return (self.engine_class, self.arch_class)

    def entry_kinds(self) -> tuple[str, ...]:
        return tuple(sorted(self.entries))

    def entry_path(self, kind: str) -> Path:
        """Absolute path of the *kind* entry, or :class:`MissingEntry`."""
        if kind not in self.entries:
            raise MissingEntry(self.pack_id, kind, self.entry_kinds())
        return self.root / PurePosixPath(self.entries[kind])

    def entry_path_or_none(self, kind: str) -> Path | None:
        return self.entry_path(kind) if kind in self.entries else None

    def basis_entry(self) -> dict:
        return {
            "arch_class": self.arch_class,
            "content_hash": self.content_hash,
            "engine_class": self.engine_class,
            "pack_id": self.pack_id,
            "schema_version": self.schema_version,
        }

    def describe(self) -> dict:
        out = self.basis_entry()
        out["entry_kinds"] = list(self.entry_kinds())
        return out


# --- schema registry -----------------------------------------------------------


@runtime_checkable
class ManifestValidator(Protocol):
    """Turn a raw ``pack.json`` object into a :class:`PackManifest` or refuse."""

    version: int

    def validate(self, raw: dict, root: Path) -> PackManifest: ...


def _class_name(value, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PackSchemaError(f"{where}: must be a non-empty string, got {value!r}")
    text = value.strip()
    if text != value or any(ch.isspace() for ch in text):
        raise PackSchemaError(f"{where}: must not contain whitespace, got {value!r}")
    return text


def _relative_entry(value, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PackSchemaError(f"{where}: must be a non-empty relative path string, got {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or value.startswith(("/", "\\")) or ":" in value.split("/")[0]:
        raise PackSchemaError(f"{where}: must be relative to the pack, got {value!r}")
    if ".." in pure.parts:
        raise PackSchemaError(f"{where}: must not contain '..', got {value!r}")
    return pure.as_posix()


class ManifestValidatorV1:
    """Schema v1: exactly the four top-level keys; entries are relative files that exist."""

    version = 1

    def validate(self, raw: dict, root: Path) -> PackManifest:
        root = Path(root)
        where = f"pack {root.name!r} {MANIFEST_NAME}"
        if not isinstance(raw, dict):
            raise PackSchemaError(f"{where}: top level must be a JSON object")
        unknown = sorted(str(k) for k in raw if k not in _MANIFEST_KEYS_V1)
        if unknown:
            raise PackSchemaError(f"{where}: unknown key(s) {unknown}; allowed {list(_MANIFEST_KEYS_V1)}")
        missing = sorted(k for k in _MANIFEST_KEYS_V1 if k not in raw)
        if missing:
            raise PackSchemaError(f"{where}: missing key(s) {missing}")
        version = raw["schema_version"]
        if isinstance(version, bool) or not isinstance(version, int) or version != self.version:
            raise PackSchemaError(f"{where}: schema_version must be {self.version}, got {version!r}")
        engine_class = _class_name(raw["engine_class"], f"{where} engine_class")
        arch_class = _class_name(raw["arch_class"], f"{where} arch_class")
        raw_entries = raw["entries"]
        if not isinstance(raw_entries, dict):
            raise PackSchemaError(f"{where}: entries must be an object of kind -> relative path")
        entries: dict[str, str] = {}
        for kind in sorted(raw_entries):
            kind_name = _class_name(kind, f"{where} entries key")
            rel = _relative_entry(raw_entries[kind], f"{where} entries[{kind!r}]")
            target = root / PurePosixPath(rel)
            if not target.is_file():
                raise PackSchemaError(f"{where} entries[{kind!r}]: file {rel!r} is missing")
            entries[kind_name] = rel
        return PackManifest(
            pack_id=root.name,
            schema_version=self.version,
            engine_class=engine_class,
            arch_class=arch_class,
            entries=entries,
            content_hash=pack_content_hash(root),
            root=root,
        )


class ManifestValidatorV2:
    """Slot: schema v2 (typed entries with per-entry hashes). No producer yet."""

    version = 2

    def validate(self, raw: dict, root: Path) -> PackManifest:
        raise NotImplementedError("pack schema v2")


#: Schema version -> validator. A manifest names its version; the registry
#: refuses versions with no entry here.
SCHEMAS: dict[int, ManifestValidator] = {
    1: ManifestValidatorV1(),
    2: ManifestValidatorV2(),
}


def load_manifest(pack_dir: Path) -> PackManifest:
    """Read and validate ``<pack_dir>/pack.json`` through :data:`SCHEMAS`."""
    pack_dir = Path(pack_dir)
    manifest = pack_dir / MANIFEST_NAME
    where = f"pack {pack_dir.name!r} {MANIFEST_NAME}"
    if not manifest.is_file():
        raise PackSchemaError(f"{where}: not found")
    try:
        raw = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackSchemaError(f"{where}: unreadable: {exc}") from exc
    if not isinstance(raw, dict):
        raise PackSchemaError(f"{where}: top level must be a JSON object")
    version = raw.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise PackSchemaError(f"{where}: schema_version must be an integer, got {version!r}")
    validator = SCHEMAS.get(version)
    if validator is None:
        raise PackSchemaError(f"{where}: schema_version {version} is not registered (known: {sorted(SCHEMAS)})")
    try:
        return validator.validate(raw, pack_dir)
    except NotImplementedError as exc:
        raise PackSchemaError(f"{where}: {exc} has no loader on this branch") from exc


# --- discovery -----------------------------------------------------------------


@runtime_checkable
class PackDiscovery(Protocol):
    """Enumerate the packs under a root, sorted by pack id."""

    name: str

    def discover(self, root: Path) -> list[PackManifest]: ...


def _check_duplicates(packs: list[PackManifest], *, allow_shadowing: bool) -> None:
    owners: dict[tuple[str, str], list[str]] = {}
    for pack in packs:
        owners.setdefault(pack.key, []).append(pack.pack_id)
    clashes = {k: v for k, v in owners.items() if len(v) > 1}
    if clashes and not allow_shadowing:
        detail = "; ".join(f"{k[0]}/{k[1]} <- {sorted(v)}" for k, v in sorted(clashes.items()))
        raise DuplicatePack(f"duplicate_pack: one (engine_class, arch_class) claimed by several packs: {detail}")


class DirectoryDiscovery:
    """Every immediate subdirectory of the root holding a ``pack.json``.

    Sorted by directory name. Two packs claiming one ``(engine_class,
    arch_class)`` refuse with :class:`DuplicatePack` unless *allow_shadowing*
    is set, in which case :meth:`PackRegistry.select` takes the last by name.
    """

    name = "directory"

    def __init__(self, *, allow_shadowing: bool = False):
        self.allow_shadowing = allow_shadowing

    def discover(self, root: Path) -> list[PackManifest]:
        root = Path(root)
        if not root.is_dir():
            raise PackRootMissing(f"data_packs_root_missing: declared root {root_token(root)} is not a directory")
        packs = [
            load_manifest(child)
            for child in sorted(root.iterdir(), key=lambda p: p.name)
            if child.is_dir() and (child / MANIFEST_NAME).is_file()
        ]
        _check_duplicates(packs, allow_shadowing=self.allow_shadowing)
        return packs


class ArchiveDiscovery:
    """Slot: packs stored inside one zip archive, one directory per pack."""

    name = "archive"

    def __init__(self, *, allow_shadowing: bool = False):
        self.allow_shadowing = allow_shadowing

    def discover(self, root: Path) -> list[PackManifest]:
        raise NotImplementedError("archive discovery")


class ObjectStoreDiscovery:
    """Slot: packs addressed by content hash from a content-addressed store."""

    name = "object_store"

    def __init__(self, *, allow_shadowing: bool = False):
        self.allow_shadowing = allow_shadowing

    def discover(self, root: Path) -> list[PackManifest]:
        raise NotImplementedError("object-store discovery")


# --- selection: build -> (engine_class, arch_class) ---------------------------------


@runtime_checkable
class PackSelector(Protocol):
    """Map one ``binary`` row to the ``(engine_class, arch_class)`` it needs."""

    name: str

    def classes_for(self, row: Mapping) -> tuple[str, str]: ...


class ColumnSelector:
    """Classes from store columns.

    * ``engine_class`` = ``binary.recovery_family`` as recorded by the
      operator catalog (``extract.recovery_family``). The isolating
      placeholder ``unclassified:<hash16>`` is not a classification; it is
      passed through unchanged so :meth:`PackRegistry.select` refuses with
      :class:`MissingAdapter` naming it. A NULL or blank family maps to
      ``"unclassified"`` for the same reason.
    * ``arch_class`` = ``<arch>-<bits>`` lower-cased from ``binary.arch`` and
      ``binary.bits`` (``x86`` + ``32`` -> ``x86-32``). A missing half maps to
      ``"unknown"`` on that side so no pack can match it by accident.
    """

    name = "column"

    def classes_for(self, row: Mapping) -> tuple[str, str]:
        family = str(row.get("recovery_family") or "").strip()
        engine_class = family or "unclassified"
        arch = str(row.get("arch") or "").strip().lower()
        bits = row.get("bits")
        arch_class = f"{arch or 'unknown'}-{int(bits) if bits not in (None, '') else 'unknown'}"
        return engine_class, arch_class


class ManifestSelector:
    """Slot: classes named per build in a pack's ``build_profiles`` entry."""

    name = "manifest"

    def classes_for(self, row: Mapping) -> tuple[str, str]:
        raise NotImplementedError("manifest selector")


class HeuristicSelector:
    """Slot: classes inferred from image features (script-VM signatures)."""

    name = "heuristic"

    def classes_for(self, row: Mapping) -> tuple[str, str]:
        raise NotImplementedError("heuristic selector")


# --- the registry ----------------------------------------------------------------


class PackRegistry:
    """Loaded packs under one root, or no root at all."""

    def __init__(self, root: Path | None, packs: list[PackManifest], *, discovery_name: str = "directory"):
        self.root = Path(root) if root is not None else None
        self._packs = tuple(sorted(packs, key=lambda p: p.pack_id))
        self.discovery_name = discovery_name
        self._by_key: dict[tuple[str, str], PackManifest] = {}
        for pack in self._packs:
            self._by_key[pack.key] = pack  # last by name wins only under allow_shadowing

    @classmethod
    def from_config(cls, root: Path | str | None = None, *, discovery: PackDiscovery | None = None) -> "PackRegistry":
        """Registry for *root*, else the configured root, else :attr:`RegistryStatus.NO_ROOT`.

        Refuses (:class:`PackError`) when a declared root is not a directory
        or any pack under it fails validation. Never substitutes a bundled root.
        """
        from .corpus_config import data_packs_root

        resolved = data_packs_root(root)
        if resolved is None:
            return cls(None, [])
        disc = discovery or DirectoryDiscovery()
        return cls(resolved, disc.discover(resolved), discovery_name=disc.name)

    @property
    def root_declared(self) -> bool:
        return self.root is not None

    @property
    def status(self) -> RegistryStatus:
        if self.root is None:
            return RegistryStatus.NO_ROOT
        return RegistryStatus.READY if self._packs else RegistryStatus.EMPTY

    def packs(self) -> tuple[PackManifest, ...]:
        return self._packs

    def select(self, engine_class: str, arch_class: str) -> PackManifest:
        """The pack for ``(engine_class, arch_class)`` or :class:`MissingAdapter`. No default."""
        pack = self._by_key.get((str(engine_class), str(arch_class)))
        if pack is None:
            raise MissingAdapter(str(engine_class), str(arch_class), self.root)
        return pack

    def select_for(self, row: Mapping, selector: PackSelector | None = None) -> PackManifest:
        engine_class, arch_class = (selector or ColumnSelector()).classes_for(row)
        return self.select(engine_class, arch_class)

    @staticmethod
    def entry_path(pack: PackManifest, kind: str) -> Path:
        return pack.entry_path(kind)

    def basis_entries(self) -> list[dict]:
        """Sorted ``[{pack_id, engine_class, arch_class, schema_version, content_hash}]``.

        ``[]`` both with no root and with an empty root; ``package_basis``
        records ``data_packs_root_declared`` beside it so the two hash apart.
        """
        return [p.basis_entry() for p in self._packs]

    def describe(self) -> dict:
        """CLI report. The root appears as an opaque token, never as a path."""
        packs = [p.describe() for p in self._packs]
        kinds = sorted({k for p in self._packs for k in p.entry_kinds()})
        return {
            "discovery": self.discovery_name,
            "entry_kinds": kinds,
            "known_entry_kinds": list(KNOWN_ENTRY_KINDS),
            "pack_count": len(packs),
            "packs": packs,
            "root": {"declared": self.root_declared, "token": root_token(self.root)},
            "schemas": sorted(SCHEMAS),
            "status": self.status.value,
        }


def describe(root: Path | str | None = None) -> dict:
    """:meth:`PackRegistry.describe` for the configured or given root."""
    return PackRegistry.from_config(root).describe()


def format_describe(report: dict) -> str:
    """Plain lines for the CLI; ``--json`` prints the dict instead."""
    root = report["root"]
    lines = [
        f"status: {report['status']}",
        f"root: {'declared, token ' + str(root['token']) if root['declared'] else 'not declared'}",
        f"packs: {report['pack_count']}",
    ]
    for pack in report["packs"]:
        lines.append(
            f"  {pack['pack_id']}: engine_class={pack['engine_class']} arch_class={pack['arch_class']} "
            f"schema={pack['schema_version']} hash={pack['content_hash'][:16]} "
            f"entries={','.join(pack['entry_kinds']) or '-'}"
        )
    return "\n".join(lines)
