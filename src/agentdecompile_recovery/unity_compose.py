"""Compose a re-openable Unity project out of what the export tools already emit.

The governing rule here is **compose what the tools emit; synthesize only what
nothing emits.** It exists because the opposite was tried and cost real work: a
previous reconstruction hand-wrote ``EditorBuildSettings.asset`` scene entries
with invented GUIDs while AssetRipper had *already* emitted that exact file with
the correct build order and the correct GUIDs, and separately hand-copied
per-scene lighting folders and a whole asset category that were sitting in the
export the whole time. Hand-synthesis of emitted artifacts does not just waste
effort -- an invented GUID silently unbinds a scene reference, and nothing in
the pipeline notices until the Editor opens with empty scenes.

So this module copies, in bulk, the parts of an AssetRipper ``ExportedProject/``
that are known-good:

* ``ProjectSettings/`` -- including ``EditorBuildSettings.asset`` (scene build
  order *and* GUIDs) and ``ProjectVersion.txt`` (the editor version to open with).
* ``Packages/manifest.json`` -- the ``com.unity.modules.*`` built-ins. This is a
  *base to augment*, never a file to write from scratch: AssetRipper cannot infer
  third-party/non-module packages, which is what :func:`augment_package_manifest`
  adds from assembly evidence (``unity_probe``'s ``impliedPackages``).
* ``Assets/`` -- the typed category folders, the ``.unity`` scenes with their
  ``.meta`` files and per-scene lighting subfolders, and ``Plugins/*.dll`` each
  with a generated ``.dll.meta``.

Only two things are genuinely synthesized, because no tool emits them: the
plugin import policy (:func:`write_plugin_meta_policy`) and package entries for
assemblies AssetRipper does not map.

Composition is additive by design -- the target may be a real git repo with real
work in it, so nothing is deleted or wiped, and a pre-existing project of a
different editor version is reported as a warning instead of being overwritten.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil

from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

from .tools import ToolchainError
from .unity_assets import find_unity_data_dir

# Subtrees of an AssetRipper `ExportedProject/` that map 1:1 into a Unity project.
EXPORTED_SUBTREES: tuple[str, ...] = ("Assets", "ProjectSettings", "Packages")

# The three files/dirs Unity needs before it will open a directory as a project
# at a known version. Everything else is content; these are the gate.
OPENABLE_MARKERS: tuple[str, ...] = (
    "Assets",
    "ProjectSettings/ProjectVersion.txt",
    "Packages/manifest.json",
)

# ILSpy `-p` emits a compilable *MSBuild* project. Inside `Assets/` those files
# are not merely useless, they break the Editor compile: duplicate assembly
# attributes and Unity's own generated type table collide with the real ones.
ILSPY_PROJECT_ARTIFACTS: tuple[str, ...] = (
    "AssemblyInfo.cs",
    "UnitySourceGeneratedAssemblyMonoScriptTypes_v1.cs",
)
ILSPY_PROJECT_SUFFIXES: tuple[str, ...] = (".csproj", ".sln", ".user")

# StreamingAssets ships either loose in the install root or under `*_Data`, and
# Unity only recognises it at exactly `Assets/StreamingAssets`.
STREAMING_ASSETS_DIRNAME = "StreamingAssets"

_EDITOR_VERSION_RE = re.compile(r"^m_EditorVersion:\s*(\S+)", re.MULTILINE)
_VALIDATE_REFERENCES_RE = re.compile(r"^(?P<indent>[ \t]*)validateReferences:\s*\d+\s*$", re.MULTILINE)
_PLUGIN_IMPORTER_RE = re.compile(r"^(?P<indent>[ \t]*)PluginImporter:\s*$", re.MULTILINE)

_PLUGIN_META_TEMPLATE = """fileFormatVersion: 2
guid: {guid}
PluginImporter:
  externalObjects: {{}}
  serializedVersion: 2
  iconMap: {{}}
  executionOrder: {{}}
  defineConstraints: []
  isPreloaded: 0
  isOverridable: 0
  isExplicitlyReferenced: 0
  validateReferences: 0
  platformData:
  - first:
      Any:
    second:
      enabled: 1
      settings: {{}}
  userData:
  assetBundleName:
  assetBundleVariant:
"""


# --------------------------------------------------------------------------
# pure helpers
# --------------------------------------------------------------------------


def meta_guid_for(relative_path: str) -> str:
    """Deterministic Unity ``.meta`` GUID (32 lowercase hex) for a path.

    Derived from the path rather than randomly so that re-running composition
    produces the same GUID: a GUID that changes between runs rebinds every
    reference to the plugin and looks, to the Editor, like a different asset.
    """

    digest = hashlib.md5(relative_path.encode("utf-8"), usedforsecurity=False)
    return digest.hexdigest()


def patch_validate_references(text: str) -> tuple[str, bool]:
    """Force ``validateReferences: 0`` in a ``.dll.meta`` body.

    Returns ``(new_text, changed)``. Pure so the meta-rewriting rule can be
    tested without touching a filesystem.
    """

    match = _VALIDATE_REFERENCES_RE.search(text)
    if match:
        if match.group(0).strip().endswith("0"):
            return text, False
        replacement = f"{match.group('indent')}validateReferences: 0"
        return _VALIDATE_REFERENCES_RE.sub(replacement, text, count=1), True

    importer = _PLUGIN_IMPORTER_RE.search(text)
    if importer:
        indent = f"{importer.group('indent')}  "
        insert_at = importer.end()
        return f"{text[:insert_at]}\n{indent}validateReferences: 0{text[insert_at:]}", True

    return text, False


def _valid_plugin_scalar(value: str) -> bool:
    """Check quoted scalars and balanced flow collections without altering them."""

    single_quoted = r"'(?:[^']|'')*'"
    double_quoted = r'"(?:[^"\\]|\\(?:[0abtnvfre "/\\N_LP]|x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|U[0-9a-fA-F]{8}))*"'
    quoted = rf"(?:{single_quoted}|{double_quoted})"
    if value.startswith(("'", '"')):
        return re.fullmatch(rf"{quoted}[ \t]*(?:#.*)?", value) is not None
    if value.startswith(("{", "[")):
        closing: list[str] = []
        index = 0
        while index < len(value):
            char = value[index]
            if char == "#" and index > 0 and value[index - 1].isspace():
                return False  # a comment cannot supply an outstanding delimiter
            if char in "\"'" and index > 0 and value[index - 1] in "{[:, \t":
                scalar = re.match(quoted, value[index:])
                if scalar is None:
                    return False
                index += scalar.end()
                if index < len(value) and value[index] not in " \t,:]}":
                    return False
                continue
            if char in "{[":
                closing.append("}" if char == "{" else "]")
            elif char in "}]":
                if not closing or closing.pop() != char:
                    return False
                if not closing:
                    return re.fullmatch(r"[ \t]*(?:#.*)?", value[index + 1:]) is not None
            index += 1
        return False  # the outer collection must close on this line
    return True


def _source_assembly_plugin_meta(text: str) -> str | None:
    """Disable auto-reference of an original DLL also supplied as source.

    Preserve the GUID and importer settings. Only a GUID-only meta (optionally
    with fileFormatVersion) may be expanded; ambiguous or malformed headers
    and policy fields are left untouched. Return None for unsupported/malformed
    metadata so callers can distinguish it from an already configured meta.
    """

    lines = text.splitlines(keepends=True)
    headers: dict[str, str] = {}
    importer_index: int | None = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if line.startswith((" ", "\t")):
            indent = line[:len(line) - len(line.lstrip())]
            if importer_index is None or "\t" in indent or len(indent) % 2:
                return None
            # Accept Unity's block mappings/sequences, but do not repair broken
            # lines or incomplete inline collections by adding policy fields.
            if stripped.startswith("- ") and stripped[2:].lstrip().startswith(("'", '"', "{", "[")):
                if not _valid_plugin_scalar(stripped[2:].lstrip()):
                    return None
                continue
            entry = re.fullmatch(r"(?:- )?[^:\s][^:]*:[ \t]*(.*)", stripped)
            if entry is None:
                if not stripped.startswith("- ") or not _valid_plugin_scalar(stripped[2:].lstrip()):
                    return None
                continue
            if not _valid_plugin_scalar(entry[1]):
                return None
            continue
        header = re.fullmatch(r"(fileFormatVersion|guid|PluginImporter):[ \t]*(.*)", stripped)
        if header is None or header[1] in headers:
            return None
        key, value = header.groups()
        headers[key] = value
        if key == "PluginImporter":
            if value:
                return None
            importer_index = index
        elif importer_index is not None:
            return None

    guid = headers.get("guid", "")
    if not re.fullmatch(r"[0-9a-fA-F]{32}", guid):
        return None
    if headers.get("fileFormatVersion", "2") != "2":
        return None
    newline = "\r\n" if "\r\n" in text else "\n"
    if importer_index is None:
        patched = _PLUGIN_META_TEMPLATE.format(guid=guid).replace(
            "  isExplicitlyReferenced: 0", "  isExplicitlyReferenced: 1"
        )
        return patched.replace("\n", newline)

    # Edit only direct importer fields, never similarly named platform settings.
    replacements: dict[int, str] = {}
    missing: list[str] = []
    for key, value in (("isExplicitlyReferenced", "1"), ("validateReferences", "0")):
        fields = [
            index for index in range(importer_index + 1, len(lines))
            if re.match(rf"  {key}[ \t]*:", lines[index])
        ]
        if len(fields) > 1:
            return None
        if not fields:
            missing.append(f"  {key}: {value}{newline}")
            continue
        index = fields[0]
        field = re.fullmatch(rf"  {key}:[ \t]*[01]([ \t]*(?:#[^\r\n]*)?)(\r?\n)?", lines[index])
        if field is None:
            return None
        replacements[index] = f"  {key}: {value}{field[1]}{field[2] or ''}"

    for index, replacement in replacements.items():
        lines[index] = replacement
    if missing:
        if not lines[importer_index].endswith("\n"):
            lines[importer_index] += newline
        lines[importer_index + 1:importer_index + 1] = missing
    return "".join(lines)


def patch_source_assembly_plugin(text: str) -> tuple[str, bool]:
    """Apply the source/DLL policy, preserving malformed or configured metadata."""

    patched = _source_assembly_plugin_meta(text)
    return (text, False) if patched is None else (patched, patched != text)


def read_editor_version(project_settings_dir: Path) -> str | None:
    """Read ``m_EditorVersion`` out of a ``ProjectSettings/ProjectVersion.txt``."""

    path = project_settings_dir / "ProjectVersion.txt"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = _EDITOR_VERSION_RE.search(text)
    return match.group(1) if match else None


def _is_within(root: Path, candidate: Path) -> bool:
    """True when ``candidate`` resolves inside ``root`` (symlink escapes included)."""

    try:
        candidate.resolve().relative_to(root.resolve())
    except (ValueError, OSError):
        return False
    return True


def _ilspy_project_artifact(relative: Path) -> bool:
    """Files ILSpy emits for MSBuild that must not land inside ``Assets/``."""

    if relative.suffix.lower() in ILSPY_PROJECT_SUFFIXES:
        return True
    return relative.name in ILSPY_PROJECT_ARTIFACTS


def _has_usable_cs_source(assembly_dir: Path) -> bool:
    """Require nonempty readable source that will survive the ILSpy exclusion."""

    for source in assembly_dir.rglob("*.cs"):
        if not source.is_file() or _ilspy_project_artifact(source.relative_to(assembly_dir)):
            continue
        try:
            if source.read_text(encoding="utf-8-sig").strip():
                return True
        except (OSError, UnicodeError):
            continue
    return False


# --------------------------------------------------------------------------
# tree merge
# --------------------------------------------------------------------------


def merge_tree(
    src: Path,
    dst: Path,
    *,
    overwrite: bool = True,
    exclude: Callable[[Path], bool] | None = None,
) -> dict[str, int]:
    """Recursively merge ``src`` into ``dst``, preserving structure.

    Additive: an existing ``dst`` keeps every file the source does not provide.
    ``exclude`` receives each entry's path *relative to* ``src`` and returns True
    to skip it. Returns counts: ``copied``, ``skipped``, ``excluded``,
    ``directories``, ``bytes``, ``escaped`` (entries refused for resolving
    outside ``dst``), and ``sourceMissing`` (1 when ``src`` is not a directory).
    """

    src = Path(src)
    dst = Path(dst)
    counts: dict[str, int] = {
        "copied": 0,
        "skipped": 0,
        "excluded": 0,
        "directories": 0,
        "bytes": 0,
        "escaped": 0,
        "sourceMissing": 0,
    }
    if not src.is_dir():
        counts["sourceMissing"] = 1
        return counts

    dst.mkdir(parents=True, exist_ok=True)
    for entry in sorted(src.rglob("*")):
        relative = entry.relative_to(src)
        if exclude is not None and exclude(relative):
            counts["excluded"] += 1
            continue
        target = dst / relative
        if entry.is_dir():
            if not _is_within(dst, target.parent):
                counts["escaped"] += 1
                continue
            target.mkdir(parents=True, exist_ok=True)
            counts["directories"] += 1
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if not _is_within(dst, target.parent):
            counts["escaped"] += 1
            continue
        if target.exists() and not overwrite:
            counts["skipped"] += 1
            continue
        try:
            shutil.copy2(entry, target)
        except OSError:
            counts["skipped"] += 1
            continue
        counts["copied"] += 1
        with suppress(OSError):  # size is reporting only; a failed stat never fails the merge
            counts["bytes"] += target.stat().st_size
    return counts


# --------------------------------------------------------------------------
# package manifest
# --------------------------------------------------------------------------


def augment_package_manifest(
    manifest_path: Path,
    extra_packages: dict[str, str],
    *,
    scoped_registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge ``extra_packages`` into AssetRipper's emitted ``manifest.json``.

    The emitted manifest is the **base**, never a template: it already carries
    the ``com.unity.modules.*`` built-ins for this exact build, and an existing
    pin is always kept over an incoming ``"*"`` -- a version the export knows
    beats a version we guessed. ``extra_packages`` covers what AssetRipper
    cannot infer (third-party and non-module first-party packages, from
    ``unity_probe``'s ``impliedPackages``).

    ``scoped_registry`` is optional and only needed for packages hosted outside
    Unity's registry (OpenUPM); it is appended if no registry with the same URL
    is already declared. ``dependencies`` is written back sorted so re-runs
    produce stable diffs.
    """

    manifest_path = Path(manifest_path)
    existed = manifest_path.is_file()
    unparseable = False
    backup: Path | None = None
    manifest: dict[str, Any] = {}

    if existed:
        try:
            loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            unparseable = True
            loaded = None
        if isinstance(loaded, dict):
            manifest = loaded
        else:
            unparseable = unparseable or loaded is not None
        if unparseable:
            # Never destroy a file we could not understand.
            backup = manifest_path.with_suffix(".json.unparseable.bak")
            try:
                shutil.copy2(manifest_path, backup)
            except OSError:
                backup = None

    dependencies = manifest.get("dependencies")
    if not isinstance(dependencies, dict):
        dependencies = {}

    added: list[str] = []
    preserved: list[str] = []
    for name, version in sorted((extra_packages or {}).items()):
        if name in dependencies:
            preserved.append(name)
            continue
        dependencies[name] = version
        added.append(name)

    manifest["dependencies"] = {key: dependencies[key] for key in sorted(dependencies)}

    registry_added = False
    if scoped_registry:
        registries = manifest.get("scopedRegistries")
        if not isinstance(registries, list):
            registries = []
        url = scoped_registry.get("url")
        known = {
            entry.get("url")
            for entry in registries
            if isinstance(entry, dict)
        }
        if url not in known:
            registries.append(dict(scoped_registry))
            registry_added = True
        manifest["scopedRegistries"] = registries

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=False) + "\n", encoding="utf-8")

    return {
        "manifestPath": str(manifest_path),
        "existed": existed,
        "synthesized": not existed,
        "unparseableBase": unparseable,
        "backupPath": str(backup) if backup else None,
        "added": added,
        "preserved": preserved,
        "scopedRegistryAdded": registry_added,
        "dependencyCount": len(manifest["dependencies"]),
    }


# --------------------------------------------------------------------------
# plugin import policy
# --------------------------------------------------------------------------


def write_plugin_meta_policy(
    plugins_dir: Path,
    *,
    source_assemblies: set[str] | None = None,
) -> list[str]:
    """Ensure every ``.dll`` under ``plugins_dir`` imports with reference validation off.

    Shipped third-party binaries reference types Unity cannot resolve at import
    time (editor-only assemblies, other games' SDKs, assemblies stripped from
    the build). With ``validateReferences: 1`` the Editor floods the console with
    reference errors and then refuses to load the plugin at all -- so the
    project fails to compile for a reason that has nothing to do with the code.
    Setting ``validateReferences: 0`` is the one piece of import policy no export
    tool emits, which is why it is synthesized here.

    AssetRipper already emits a ``.dll.meta`` beside each plugin; those are
    patched in place. A missing ``.meta`` gets a minimal generated one whose GUID
    is derived from the plugin's path (md5, 32 lowercase hex) so repeated runs
    keep the same GUID instead of rebinding every reference.

    Original DLLs in ``ShippedManaged`` whose stems match ``source_assemblies``
    also get ``isExplicitlyReferenced: 1`` to avoid compiling against both the
    source and binary definitions. Their malformed metadata is never replaced.

    Returns the paths of the ``.meta`` files created or modified.
    """

    plugins_dir = Path(plugins_dir)
    source_assemblies = source_assemblies or set()
    touched: list[str] = []
    if not plugins_dir.is_dir():
        return touched

    for dll in sorted(plugins_dir.rglob("*.dll")):
        if not dll.is_file():
            continue
        meta = Path(f"{dll}.meta")
        relative = dll.relative_to(plugins_dir).as_posix()
        source_duplicate = (
            dll.stem in source_assemblies
            and dll.relative_to(plugins_dir).parts[0] == "ShippedManaged"
        )
        if not meta.exists():
            patched = _PLUGIN_META_TEMPLATE.format(guid=meta_guid_for(relative))
            if source_duplicate:
                patched, _ = patch_source_assembly_plugin(patched)
            meta.write_text(patched, encoding="utf-8")
            touched.append(str(meta))
            continue
        try:
            if source_duplicate:
                with meta.open(encoding="utf-8", newline="") as stream:
                    text = stream.read()
            else:
                text = meta.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeError):  # noqa: S112 - unreadable/malformed metadata is preserved
            continue
        patched, changed = (
            patch_source_assembly_plugin(text) if source_duplicate else patch_validate_references(text)
        )
        if changed:
            if source_duplicate:
                with meta.open("w", encoding="utf-8", newline="") as stream:
                    stream.write(patched)
            else:
                meta.write_text(patched, encoding="utf-8")
            touched.append(str(meta))
    return touched


def _source_assembly_plugin_receipt(
    plugins_dir: Path, source_assemblies: set[str], touched: list[str],
) -> dict[str, Any]:
    """Report configured policies even when this invocation changed no metadata."""

    configured: list[str] = []
    skipped: list[str] = []
    shipped_dir = plugins_dir / "ShippedManaged"
    for dll in sorted(shipped_dir.rglob("*.dll")):
        if not dll.is_file() or dll.stem not in source_assemblies:
            continue
        meta = Path(f"{dll}.meta")
        try:
            with meta.open(encoding="utf-8", newline="") as stream:
                text = stream.read()
        except (OSError, UnicodeError):
            skipped.append(str(meta))
            continue
        patched = _source_assembly_plugin_meta(text)
        if patched is None or patched != text:
            skipped.append(str(meta))
        else:
            configured.append(str(meta))
    return {
        "sourceAssemblyPolicy": "isExplicitlyReferenced: 1; validateReferences: 0",
        "explicitlyReferencedCount": len(configured),
        "explicitlyReferencedMetaPaths": configured[:200],
        "explicitlyReferencedMetaPathsTruncated": max(0, len(configured) - 200),
        "explicitlyReferencedChangedCount": len(set(configured) & set(touched)),
        "explicitlyReferencedSkippedCount": len(skipped),
        "explicitlyReferencedSkippedMetaPaths": skipped[:200],
        "explicitlyReferencedSkippedMetaPathsTruncated": max(0, len(skipped) - 200),
    }


# --------------------------------------------------------------------------
# script tree reconciliation
# --------------------------------------------------------------------------


def _cs_index(root: Path) -> dict[str, Path]:
    if not root.is_dir():
        return {}
    return {path.relative_to(root).as_posix().lower(): path for path in root.rglob("*.cs") if path.is_file()}


def resolve_script_conflicts(exported_scripts_dir: Path, ilspy_scripts_dir: Path) -> dict[str, Any]:
    """Decide which script tree wins where AssetRipper and ILSpy both emit a type.

    AssetRipper emits its own ``Assets/Scripts/Assembly-CSharp`` tree, but those
    are structural stubs recovered from MonoScript metadata -- field layout, not
    method bodies. ILSpy decompiles the real IL, so **ILSpy wins for any type
    present in both**, applied by layering the ILSpy tree over the exported one
    with overwrite enabled.

    This function is read-only: it reports. Same-path collisions are resolved by
    that overwrite, but a type emitted at *different* relative paths by the two
    tools leaves two definitions in the project and will fail to compile
    (CS0101). Those are reported as ``duplicateTypeRisks`` rather than silently
    deleted, because guessing which of two files is the real type is exactly the
    kind of hand-synthesis this module exists to avoid.
    """

    exported_scripts_dir = Path(exported_scripts_dir)
    ilspy_scripts_dir = Path(ilspy_scripts_dir)
    exported = _cs_index(exported_scripts_dir)
    ilspy = _cs_index(ilspy_scripts_dir)

    same_path = sorted(set(exported) & set(ilspy))

    exported_stems: dict[str, list[str]] = {}
    for key in exported:
        exported_stems.setdefault(Path(key).stem, []).append(key)
    ilspy_stems: dict[str, list[str]] = {}
    for key in ilspy:
        ilspy_stems.setdefault(Path(key).stem, []).append(key)

    same_path_set = set(same_path)
    risks: list[dict[str, Any]] = []
    for stem in sorted(set(exported_stems) & set(ilspy_stems)):
        exported_paths = [key for key in exported_stems[stem] if key not in same_path_set]
        ilspy_paths = [key for key in ilspy_stems[stem] if key not in same_path_set]
        if exported_paths and ilspy_paths:
            risks.append({"type": stem, "exported": exported_paths, "ilspy": ilspy_paths})

    return {
        "policy": "ilspy-wins",
        "resolution": "ilspy tree layered over exported tree with overwrite",
        "exportedScriptsDir": str(exported_scripts_dir),
        "ilspyScriptsDir": str(ilspy_scripts_dir),
        "exportedFileCount": len(exported),
        "ilspyFileCount": len(ilspy),
        "supersededCount": len(same_path),
        "supersededFiles": same_path[:200],
        "supersededTruncated": max(0, len(same_path) - 200),
        "exportedOnlyCount": len(set(exported) - set(ilspy)),
        "ilspyOnlyCount": len(set(ilspy) - set(exported)),
        "duplicateTypeRiskCount": len(risks),
        "duplicateTypeRisks": risks[:50],
        "claimBoundary": (
            "counted by file path and type name only; identical paths do not prove identical "
            "types, and duplicateTypeRisks are reported, not resolved"
        ),
    }


# --------------------------------------------------------------------------
# main entry point
# --------------------------------------------------------------------------


def _find_streaming_assets(install_root: Path) -> Path | None:
    """Locate shipped StreamingAssets (loose in the install root, or under ``*_Data``)."""

    loose = install_root / STREAMING_ASSETS_DIRNAME
    if loose.is_dir():
        return loose
    try:
        data_dir = find_unity_data_dir(install_root)
    except OSError:
        return None
    if data_dir is not None:
        candidate = data_dir / STREAMING_ASSETS_DIRNAME
        if candidate.is_dir():
            return candidate
    return None


def compose_unity_project(
    exported_project: Path,
    target_project: Path,
    *,
    managed_source: Path | None = None,
    extra_packages: dict[str, str] | None = None,
    install_root: Path | None = None,
) -> dict[str, Any]:
    """Assemble a re-openable Unity project at ``target_project``.

    Merges ``ExportedProject/{Assets,ProjectSettings,Packages}`` into the target,
    augments the emitted package manifest, layers ILSpy source over the exported
    script stubs, applies the plugin import policy, and copies shipped
    StreamingAssets when ``install_root`` is given.

    Additive only. An existing ``ProjectSettings/ProjectVersion.txt`` naming a
    different editor version is preserved and reported in ``warnings`` -- the
    target may be someone's real project, and silently rewriting the version it
    opens with is how you trigger an irreversible asset upgrade.
    """

    exported_project = Path(exported_project).resolve()
    target_project = Path(target_project).resolve()

    if not exported_project.is_dir():
        raise ToolchainError(
            "unity-export-missing",
            detail=f"exported project is not a directory: {exported_project}",
        )
    if not any((exported_project / name).is_dir() for name in EXPORTED_SUBTREES):
        raise ToolchainError(
            "unity-export-incomplete",
            detail=(
                f"{exported_project} contains none of {list(EXPORTED_SUBTREES)}; "
                "point at the ExportedProject/ directory the exporter wrote"
            ),
        )
    if target_project.exists() and not target_project.is_dir():
        raise ToolchainError(
            "unity-target-not-a-directory",
            detail=f"target project path exists and is not a directory: {target_project}",
        )

    warnings: list[str] = []
    target_project.mkdir(parents=True, exist_ok=True)

    # Capture the target's pre-existing identity before anything is merged.
    existing_version = read_editor_version(target_project / "ProjectSettings")
    exported_version = read_editor_version(exported_project / "ProjectSettings")
    version_conflict = bool(existing_version and exported_version and existing_version != exported_version)
    preserved_version_text: str | None = None
    if version_conflict:
        try:
            preserved_version_text = (target_project / "ProjectSettings" / "ProjectVersion.txt").read_text(
                encoding="utf-8"
            )
        except OSError:
            preserved_version_text = None
        warnings.append(
            f"target already holds a Unity project at editor version {existing_version}; the export "
            f"declares {exported_version}. The existing ProjectVersion.txt was preserved -- reconcile "
            "the versions before opening, or compose into an empty directory."
        )

    trees: dict[str, dict[str, int]] = {}
    for name in EXPORTED_SUBTREES:
        trees[name] = merge_tree(exported_project / name, target_project / name, overwrite=True)
        if trees[name]["sourceMissing"]:
            warnings.append(f"export has no {name}/ subtree")

    if version_conflict and preserved_version_text is not None:
        (target_project / "ProjectSettings" / "ProjectVersion.txt").write_text(
            preserved_version_text, encoding="utf-8"
        )

    # Packages: augment the emitted manifest, never regenerate it.
    packages = augment_package_manifest(
        target_project / "Packages" / "manifest.json",
        extra_packages or {},
    )
    if packages["synthesized"]:
        warnings.append(
            "no Packages/manifest.json was emitted by the exporter; a minimal one was synthesized "
            "and will not list this build's com.unity.modules.* built-ins"
        )

    # Scripts: ILSpy output layered over AssetRipper's stub tree.
    scripts: dict[str, Any] = {"applied": False, "reason": "no managed source provided"}
    script_tree: dict[str, int] | None = None
    source_assemblies: set[str] = set()
    if managed_source is not None:
        managed_source = Path(managed_source).resolve()
        target_scripts = target_project / "Assets" / "Scripts"
        if not managed_source.is_dir():
            warnings.append(f"managed source tree not found: {managed_source}")
            scripts = {"applied": False, "reason": f"managed source not a directory: {managed_source}"}
        else:
            source_assemblies = {
                path.name for path in managed_source.iterdir()
                if path.is_dir() and _has_usable_cs_source(path)
            }
            scripts = resolve_script_conflicts(target_scripts, managed_source)
            scripts["applied"] = True
            script_tree = merge_tree(
                managed_source,
                target_scripts,
                overwrite=True,
                exclude=_ilspy_project_artifact,
            )
            trees["Assets/Scripts"] = script_tree

    # Plugins: the one import policy no exporter emits.
    plugins_dir = target_project / "Assets" / "Plugins"
    metas_before = {str(path) for path in plugins_dir.rglob("*.dll.meta")} if plugins_dir.is_dir() else set()
    plugin_metas = write_plugin_meta_policy(plugins_dir, source_assemblies=source_assemblies)
    generated = [path for path in plugin_metas if path not in metas_before]
    source_assembly_plugins = _source_assembly_plugin_receipt(plugins_dir, source_assemblies, plugin_metas)

    # StreamingAssets ship outside the serialized data and must land at this exact path.
    streaming: dict[str, Any] = {"copied": False, "source": None}
    if install_root is not None:
        install_root = Path(install_root).resolve()
        source = _find_streaming_assets(install_root) if install_root.is_dir() else None
        if source is None:
            streaming = {"copied": False, "source": None, "reason": "no StreamingAssets in install root"}
        else:
            counts = merge_tree(source, target_project / "Assets" / STREAMING_ASSETS_DIRNAME, overwrite=True)
            trees[f"Assets/{STREAMING_ASSETS_DIRNAME}"] = counts
            streaming = {"copied": True, "source": str(source), "fileCount": counts["copied"]}

    # Sibling AuxiliaryFiles/path_id_map.json is not a Unity asset -- record it for
    # a later GUID-repair stage rather than copying it into Assets/.
    path_id_map = exported_project.parent / "AuxiliaryFiles" / "path_id_map.json"
    if not path_id_map.is_file():
        alternate = exported_project / "AuxiliaryFiles" / "path_id_map.json"
        path_id_map = alternate if alternate.is_file() else path_id_map

    markers = {
        "assets": (target_project / "Assets").is_dir(),
        "projectVersion": (target_project / "ProjectSettings" / "ProjectVersion.txt").is_file(),
        "packageManifest": (target_project / "Packages" / "manifest.json").is_file(),
    }
    missing = [name for name, present in zip(OPENABLE_MARKERS, markers.values(), strict=True) if not present]
    ready = not missing

    return {
        "schema": "agentdecompile.unity-compose.v1",
        "status": "complete" if ready else "partial",
        "exportedProject": str(exported_project),
        "targetProject": str(target_project),
        "trees": trees,
        "totalFilesCopied": sum(counts["copied"] for counts in trees.values()),
        "packages": packages,
        "plugins": {
            "metasTouched": len(plugin_metas),
            "metaPaths": plugin_metas[:200],
            "metaPathsTruncated": max(0, len(plugin_metas) - 200),
            "policy": "validateReferences: 0",
            "patchedCount": len(plugin_metas) - len(generated),
            "generatedCount": len(generated),
            **source_assembly_plugins,
        },
        "scripts": scripts,
        "streamingAssets": streaming,
        "auxiliaryFiles": {"pathIdMap": str(path_id_map) if path_id_map.is_file() else None},
        "openable": {
            **markers,
            "ready": ready,
            "missing": missing,
            "editorVersion": read_editor_version(target_project / "ProjectSettings"),
            "exportEditorVersion": exported_version,
        },
        "preExistingProject": {
            "detected": bool(existing_version),
            "editorVersion": existing_version,
            "versionConflict": version_conflict,
            "projectVersionPreserved": version_conflict and preserved_version_text is not None,
        },
        "warnings": warnings,
        "claimBoundary": (
            "composition copies files and reconciles manifests only -- it does not prove the project "
            "opens, imports, or compiles. A Unity batchmode open is the stage that proves that; until "
            "it runs, unresolved script references and duplicate types remain undetected."
        ),
    }
