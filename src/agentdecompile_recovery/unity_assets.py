"""Unity asset extraction via UnityPy (optional `agentdecompile[unity]` extra).

Unity games ship two separable recovery surfaces: managed C# assemblies
(decompile with ILSpy/`ilspycmd` -- see README's "Optional: .NET/IL
decompilation support" section) and serialized asset data (textures, audio,
text, fonts) inside the built player's `*.assets`/`*.resS` files. This module
handles the second surface.

Tools like AssetRipper reconstruct a full re-openable Unity project (scenes,
prefabs, meshes, MonoBehaviour data) but load the entire asset graph into
memory before writing anything out, which can exceed available RAM on large
titles with heavy mesh/blend-shape data. This module trades full project
reconstruction for a bounded-memory alternative: it processes one top-level
data file at a time and reads/exports one object at a time, freeing each
before moving to the next, so peak memory stays roughly constant regardless
of how large the asset file is on disk. Mesh/BlendShapeData export is
intentionally out of scope here for the same reason -- that is exactly the
class of data that makes whole-graph tools OOM, and reconstructing it
correctly (skinned mesh renderers, bone weights, blend shape frames) needs
the fuller project-graph tooling this module deliberately does not attempt.

`UnityPy` is an optional dependency (`agentdecompile[unity]`) and is imported
lazily inside the functions that need it, so importing this module never
requires it to be installed.
"""

from __future__ import annotations

import gc

from pathlib import Path
from typing import Any

EXPORTABLE_TYPES = {"Texture2D", "Sprite", "AudioClip", "TextAsset", "Font"}
MESH_EXPORT_SCHEMA = "agentdecompile.unity-mesh-derivative-export.v1"

# Companion/metadata files alongside the top-level serialized data files.
# UnityPy follows references to *.resS/*.resource automatically when loading
# the owning data file, so these are never scanned directly.
_SKIP_SUFFIXES = (".resS", ".resource", ".json", ".config", ".info")
_SKIP_NAMES = {"ScriptingAssemblies.json", "RuntimeInitializeOnLoads.json"}


def _require_unitypy() -> Any:
    try:
        import UnityPy
    except ImportError as exc:
        raise ImportError(
            "UnityPy is required for Unity asset export. Install it with "
            "`pip install agentdecompile[unity]` (or `pipx install agentdecompile[unity]`)."
        ) from exc
    return UnityPy


def sanitize_asset_name(name: str) -> str:
    """Replace filesystem-unsafe characters; never return an empty string."""

    bad = '\\/:*?"<>|'
    out = "".join("_" if ch in bad else ch for ch in name)
    return out.strip() or "unnamed"


def discover_data_files(data_dir: Path) -> list[Path]:
    """List top-level serialized Unity data files under a `*_Data` directory."""

    out = []
    for path in sorted(data_dir.iterdir()):
        if not path.is_file():
            continue
        if path.name in _SKIP_NAMES:
            continue
        if path.suffix in _SKIP_SUFFIXES:
            continue
        out.append(path)
    return out


def find_unity_data_dir(install_root: Path) -> Path | None:
    """Return the first `*_Data` directory directly under a Unity install root."""

    candidates = [p for p in install_root.iterdir() if p.is_dir() and p.name.endswith("_Data")]
    return candidates[0] if candidates else None


def _export_texture2d(data: Any, dest_dir: Path, path_id: int) -> None:
    name = sanitize_asset_name(data.m_Name) if data.m_Name else f"texture_{path_id}"
    dest = dest_dir / "Texture2D" / f"{name}.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return
    image = data.image
    if image is None:
        return
    image.save(dest)


def _export_sprite(data: Any, dest_dir: Path, path_id: int) -> None:
    name = sanitize_asset_name(data.m_Name) if data.m_Name else f"sprite_{path_id}"
    dest = dest_dir / "Sprite" / f"{name}.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return
    image = data.image
    if image is None:
        return
    image.save(dest)


def _export_audioclip(data: Any, dest_dir: Path, path_id: int) -> None:
    base = sanitize_asset_name(data.m_Name) if data.m_Name else f"audio_{path_id}"
    out_dir = dest_dir / "AudioClip"
    out_dir.mkdir(parents=True, exist_ok=True)
    samples = data.samples
    if not samples:
        return
    if len(samples) == 1:
        (out_dir / f"{base}.wav").write_bytes(next(iter(samples.values())))
        return
    for sub_name, clip_bytes in samples.items():
        (out_dir / f"{sanitize_asset_name(sub_name)}.wav").write_bytes(clip_bytes)


def _export_textasset(data: Any, dest_dir: Path, path_id: int) -> None:
    name = sanitize_asset_name(data.m_Name) if data.m_Name else f"text_{path_id}"
    out_dir = dest_dir / "TextAsset"
    out_dir.mkdir(parents=True, exist_ok=True)
    script = data.m_Script
    payload = script.encode("utf-8", "surrogateescape") if isinstance(script, str) else bytes(script)
    (out_dir / f"{name}.txt").write_bytes(payload)


def _export_font(data: Any, dest_dir: Path, path_id: int) -> None:
    name = sanitize_asset_name(data.m_Name) if data.m_Name else f"font_{path_id}"
    out_dir = dest_dir / "Font"
    out_dir.mkdir(parents=True, exist_ok=True)
    font_data = getattr(data, "m_FontData", None)
    if not font_data:
        return
    (out_dir / f"{name}.ttf").write_bytes(bytes(font_data))


_EXPORTERS = {
    "Texture2D": _export_texture2d,
    "Sprite": _export_sprite,
    "AudioClip": _export_audioclip,
    "TextAsset": _export_textasset,
    "Font": _export_font,
}


def export_data_file(source: Path, dest_dir: Path) -> tuple[int, int, list[str]]:
    """Export supported asset types from one Unity data file.

    Returns ``(exported_count, failed_count, failure_messages)``. Reads and
    frees one object at a time so peak memory does not scale with how many
    objects the file contains.
    """

    unitypy = _require_unitypy()
    exported = 0
    failed = 0
    failures: list[str] = []
    env = unitypy.load(str(source))
    for obj in env.objects:
        type_name = obj.type.name
        if type_name not in EXPORTABLE_TYPES:
            continue
        try:
            data = obj.read()
            _EXPORTERS[type_name](data, dest_dir, obj.path_id)
            exported += 1
        except Exception as exc:  # noqa: BLE001 - keep scanning past one bad object
            failed += 1
            failures.append(f"{type_name} path_id={obj.path_id}: {exc}")
        finally:
            data = None
            gc.collect()
    env = None
    gc.collect()
    return exported, failed, failures


def export_primary_content(install_root: Path, output_dir: Path) -> dict[str, Any]:
    """Export textures, sprites, audio, text assets, and fonts from a Unity
    install directory into ``output_dir``, one type-named subfolder each.

    Does not export meshes, materials, or scene/prefab structure -- use a
    full project-reconstruction tool (e.g. AssetRipper) when that's needed
    and the asset graph fits in available memory.
    """

    install_root = install_root.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    data_dir = find_unity_data_dir(install_root)
    if data_dir is None:
        return {
            "schema": "agentdecompile.unity-primary-content-export.v1",
            "status": "error",
            "reason": "no *_Data directory found under install root",
            "installRoot": str(install_root),
        }

    files = discover_data_files(data_dir)
    per_file: list[dict[str, Any]] = []
    total_exported = 0
    total_failed = 0
    for source in files:
        exported, failed, failures = export_data_file(source, output_dir)
        total_exported += exported
        total_failed += failed
        per_file.append(
            {
                "file": source.name,
                "sizeBytes": source.stat().st_size,
                "exported": exported,
                "failed": failed,
                "failures": failures[:20],
            }
        )

    return {
        "schema": "agentdecompile.unity-primary-content-export.v1",
        "status": "complete",
        "installRoot": str(install_root),
        "dataDir": str(data_dir),
        "outputDir": str(output_dir),
        "filesScanned": len(files),
        "totalExported": total_exported,
        "totalFailed": total_failed,
        "perFile": per_file,
        "claimBoundary": "textures/sprites/audio/text/fonts only -- no meshes, materials, or scene/prefab structure",
    }


def export_mesh_derivatives(
    install_root: Path,
    output_dir: Path,
    *,
    data_files: list[Path] | None = None,
    max_object_mib: int = 192,
    resume: bool = True,
) -> dict[str, Any]:
    """Export bounded OBJ derivatives for serialized Mesh objects.

    UnityPy still indexes the serialized-file object table, but Mesh objects are
    parsed and converted one at a time. Oversized objects are skipped before
    parsing. Existing outputs are reused only when the matching receipt records
    a completed object with the same source file ID, path ID and source range.
    OBJ is intentionally reported as a lossy derivative, not as a Unity asset.
    """

    import hashlib
    import json
    import re

    unitypy = _require_unitypy()
    install_root = install_root.resolve()
    output_dir = output_dir.resolve()
    if max_object_mib < 1:
        raise ValueError("max_object_mib must be at least 1")
    data_dir = find_unity_data_dir(install_root) if install_root.is_dir() else None
    if data_dir is None and data_files is None:
        return {"schema": MESH_EXPORT_SCHEMA, "status": "error", "reason": "no *_Data directory found under install root"}
    sources = [Path(path).resolve() for path in data_files] if data_files else discover_data_files(data_dir)  # type: ignore[arg-type]
    output_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = output_dir / "mesh-derivative-receipt.json"
    previous: dict[str, dict[str, Any]] = {}
    if resume and receipt_path.is_file():
        try:
            old = json.loads(receipt_path.read_text(encoding="utf-8"))
            for entry in old.get("objects", []):
                if entry.get("status") == "exported" and entry.get("output"):
                    previous[f"{entry.get('source')}:{entry.get('pathId')}"] = entry
        except (OSError, ValueError, TypeError):
            previous = {}

    objects_report: list[dict[str, Any]] = []
    totals = {"exported": 0, "skipped": 0, "failed": 0, "resumed": 0}
    source_hashes: dict[Path, str] = {}

    def write_checkpoint(status: str = "running") -> None:
        checkpoint = {
            "schema": MESH_EXPORT_SCHEMA,
            "status": status,
            "sourceRoot": str(install_root),
            "outputDir": str(output_dir),
            "maxObjectMiB": max_object_mib,
            "totals": totals,
            "objects": objects_report,
            "claimBoundary": "lossy OBJ mesh derivatives only; not Unity serialized assets, scene graph, materials, skinning, blend-shape fidelity, or byte-exact source recovery",
        }
        temp_path = receipt_path.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(checkpoint, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp_path.replace(receipt_path)

    for source in sources:
        if not source.is_file():
            objects_report.append({"source": str(source), "status": "failed", "error": "source file does not exist"})
            totals["failed"] += 1
            continue
        digest = hashlib.sha256(source.name.encode("utf-8", "surrogateescape")).hexdigest()[:16]
        env = None
        try:
            env = unitypy.load(str(source))
            mesh_objects = sorted((obj for obj in env.objects if obj.type.name == "Mesh"), key=lambda obj: obj.path_id)
            for obj in mesh_objects:
                key = f"{source.name}:{obj.path_id}"
                previous_entry = previous.get(key)
                if source not in source_hashes:
                    hasher = hashlib.sha256()
                    with source.open("rb") as source_handle:
                        for chunk in iter(lambda: source_handle.read(1024 * 1024), b""):
                            hasher.update(chunk)
                    source_hashes[source] = hasher.hexdigest()
                common = {
                    "source": source.name,
                    "sourceSha256": source_hashes[source],
                    "pathId": obj.path_id,
                    "byteStart": obj.byte_start,
                    "serializedBytes": obj.byte_size,
                }
                if (
                    previous_entry
                    and previous_entry.get("sourceSha256") == source_hashes[source]
                    and previous_entry.get("byteStart") == obj.byte_start
                    and previous_entry.get("serializedBytes") == obj.byte_size
                ):
                    output = output_dir / previous_entry["output"]
                    if output.is_file():
                        objects_report.append({**common, **previous_entry, "status": "exported", "resumed": True})
                        totals["exported"] += 1
                        totals["resumed"] += 1
                        if len(objects_report) % 25 == 0:
                            write_checkpoint()
                        continue
                if obj.byte_size > max_object_mib * 1024 * 1024:
                    objects_report.append({**common, "status": "skipped", "reason": "over-per-object-size-limit"})
                    totals["skipped"] += 1
                    if len(objects_report) % 25 == 0:
                        write_checkpoint()
                    continue
                mesh = None
                try:
                    mesh = obj.parse_as_object()
                    name = str(mesh.m_Name or f"mesh_{obj.path_id}")
                    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")[:90] or "unnamed"
                    filename = f"{digest}_{obj.path_id}_{safe_name}.obj"
                    content = mesh.export("obj")
                    if not content:
                        objects_report.append({**common, "name": name, "status": "skipped", "reason": "empty-or-unsupported-mesh"})
                        totals["skipped"] += 1
                    else:
                        target = output_dir / filename
                        target.write_text(content, encoding="utf-8")
                        objects_report.append({**common, "name": name, "status": "exported", "output": filename, "outputBytes": target.stat().st_size})
                        totals["exported"] += 1
                except Exception as exc:  # noqa: BLE001 - retain object-level failure evidence
                    objects_report.append({**common, "status": "failed", "error": f"{type(exc).__name__}: {exc}"})
                    totals["failed"] += 1
                finally:
                    mesh = None
                    gc.collect()
                if len(objects_report) % 25 == 0:
                    write_checkpoint()
        except Exception as exc:  # noqa: BLE001 - retain file-level failure evidence
            objects_report.append({"source": source.name, "status": "failed", "error": f"{type(exc).__name__}: {exc}"})
            totals["failed"] += 1
        finally:
            env = None
            gc.collect()

    status = "complete" if totals["failed"] == 0 and totals["skipped"] == 0 else "partial"
    write_checkpoint(status)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    return receipt
