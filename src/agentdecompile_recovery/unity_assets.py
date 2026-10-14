"""Unity asset extraction via UnityPy (optional `agentdecompile[unity]` extra).

Unity games ship two separable recovery surfaces: managed C# assemblies
(decompile with ILSpy/`ilspycmd` -- see README's "Optional: .NET/IL
decompilation support" section) and serialized asset data (textures, audio,
text, fonts) inside the built player's `*.assets`/`*.resS` files. This module
handles that surface and also offers bounded raw/OBJ Mesh derivatives.

Tools like AssetRipper reconstruct a full re-openable Unity project (scenes,
prefabs, meshes, MonoBehaviour data) but load the entire asset graph into
memory before writing anything out, which can exceed available RAM on large
titles with heavy mesh/blend-shape data. The bounded exporters process one
top-level data file at a time and release each decoded object before moving
to the next. Mesh output is limited to exact serialized byte ranges or lossy
OBJ geometry; reconstructing Unity references, skinned mesh renderers, bone
weights, and blend shape frames still needs fuller project-graph tooling.

`UnityPy` is an optional dependency (`agentdecompile[unity]`) and is imported
lazily inside the functions that need it, so importing this module never
requires it to be installed.
"""

from __future__ import annotations

import gc
import hashlib
import json
import os
import tempfile

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
    _patch_unitypy_empty_stream_path()
    return UnityPy


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _patch_unitypy_empty_stream_path() -> None:
    """Handle Unity's empty StreamingInfo path as inline or absent data.

    Unity uses an empty path with size zero for uninitialized streamed
    textures. UnityPy otherwise treats that path as an external filename and
    attempts to open the containing data directory.
    """

    import UnityPy.helpers.ResourceReader as resource_reader

    original = resource_reader.get_resource_data
    if getattr(original, "_agentdecompile_empty_path", False):
        return

    def patched(res_path: str, assets_file: Any, offset: int, size: int) -> bytes:
        if not res_path:
            if size == 0:
                return b""
            return resource_reader._get_resource_data(assets_file.reader, offset, size)
        return original(res_path, assets_file, offset, size)

    patched._agentdecompile_empty_path = True  # type: ignore[attr-defined]
    resource_reader.get_resource_data = patched
    # AudioClipConverter imports the function directly, so update that alias
    # as well when UnityPy has loaded it already.
    try:
        import UnityPy.export.AudioClipConverter as audio_converter

        audio_converter.get_resource_data = patched
    except ImportError:
        pass


def sanitize_asset_name(name: str) -> str:
    """Replace filesystem-unsafe characters; never return an empty string."""

    bad = '\\/:*?"<>|'
    out = "".join("_" if ch in bad else ch for ch in name)
    return out.strip() or "unnamed"


def _asset_output_stem(data: Any, fallback: str, path_id: int) -> str:
    source_file = getattr(getattr(data, "object_reader", None), "assets_file", None)
    source_name = Path(str(getattr(source_file, "name", "data"))).name
    source_stem = sanitize_asset_name(Path(source_name).stem)
    return f"{source_stem}_{fallback}_{path_id}"


def discover_data_files(data_dir: Path) -> list[Path]:
    """List top-level serialized Unity data files under a `*_Data` directory."""

    if data_dir.is_symlink():
        raise ValueError(f"Unity data directory must not be a symlink: {data_dir}")
    data_root = data_dir.resolve(strict=True)
    out = []
    for path in sorted(data_dir.iterdir()):
        if path.is_symlink() or not path.is_file():
            continue
        if path.resolve(strict=True).parent != data_root:
            continue
        if path.name in _SKIP_NAMES:
            continue
        if path.suffix in _SKIP_SUFFIXES:
            continue
        out.append(path)
    return out


def discover_resource_companions(data_dir: Path) -> list[Path]:
    """List regular top-level resource companions without following symlinks."""

    if data_dir.is_symlink():
        raise ValueError(f"Unity data directory must not be a symlink: {data_dir}")
    data_root = data_dir.resolve(strict=True)
    return [
        path
        for path in sorted(data_dir.iterdir())
        if not path.is_symlink()
        and path.is_file()
        and path.suffix in {".resS", ".resource"}
        and path.resolve(strict=True).parent == data_root
    ]


def find_unity_data_dir(install_root: Path) -> Path | None:
    """Return the first `*_Data` directory directly under a Unity install root."""

    candidates = [p for p in install_root.iterdir() if p.is_dir() and not p.is_symlink() and p.name.endswith("_Data")]
    return candidates[0] if candidates else None


def _export_texture2d(data: Any, dest_dir: Path, path_id: int) -> bool:
    name = sanitize_asset_name(data.m_Name) if data.m_Name else f"texture_{path_id}"
    dest = dest_dir / "Texture2D" / f"{_asset_output_stem(data, name, path_id)}.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    image = data.image
    if image is None or image.size == (0, 0):
        return False
    _save_png_atomically(image, dest)
    return True


def _texture2d_pixel_count(data: Any) -> int:
    """Return parsed Texture2D dimensions, rejecting invalid sizes without decoding."""

    width = int(getattr(data, "m_Width", 0) or 0)
    height = int(getattr(data, "m_Height", 0) or 0)
    if width <= 0 or height <= 0:
        raise ValueError(f"invalid Texture2D dimensions: {width}x{height}")
    return width * height


def _sprite_texture_pixel_counts(data: Any) -> list[tuple[str, int, int, int]]:
    """Resolve a Sprite's color and alpha texture dimensions without decoding."""

    # UnityPy's Sprite exporter uses atlas render data when the Sprite points
    # to an atlas. Inspect that same record here; checking only m_RD can miss
    # the actual backing (and alpha) textures that image access will decode.
    render_data = data.m_RD
    atlas_pointer = getattr(data, "m_SpriteAtlas", None)
    atlas_tags = getattr(data, "m_AtlasTags", None)
    if atlas_pointer:
        try:
            atlas = atlas_pointer.read() if hasattr(atlas_pointer, "read") else atlas_pointer
            render_key = data.m_RenderDataKey
            render_data = next(
                value
                for key, value in atlas.m_RenderDataMap
                if key == render_key
            )
        except Exception as exc:  # noqa: BLE001 - never decode if atlas metadata is uncertain
            raise ValueError(f"Sprite atlas render data could not be resolved: {exc}") from exc
    elif atlas_tags:
        # UnityPy falls back to scanning atlas assets by tag and then selects
        # render data. If the explicit pointer is absent, do not guess which
        # texture it will decode.
        raise ValueError("Sprite atlas tag has no explicit atlas pointer")

    textures = []
    for label, pointer in (
        ("texture", getattr(render_data, "texture", None)),
        (
            "alphaTexture",
            getattr(render_data, "alphaTexture", getattr(render_data, "alpha_texture", None)),
        ),
    ):
        if pointer is None:
            continue
        # A zero path ID is Unity's null PPtr. Sprite alpha is optional, so
        # omit that pointer without attempting to dereference it. The primary
        # texture remains required and follows the normal fail-closed path.
        if label == "alphaTexture" and getattr(pointer, "m_PathID", None) == 0:
            continue
        try:
            texture = pointer.read() if hasattr(pointer, "read") else pointer
        except Exception as exc:  # noqa: BLE001 - a Sprite must not trigger image decoding as fallback
            raise ValueError(f"Sprite {label} could not be resolved: {exc}") from exc
        if texture is None:
            if label == "texture":
                raise ValueError("Sprite backing texture could not be resolved")
            continue
        width = int(getattr(texture, "m_Width", 0) or 0)
        height = int(getattr(texture, "m_Height", 0) or 0)
        if width <= 0 or height <= 0:
            raise ValueError(f"invalid Sprite {label} dimensions: {width}x{height}")
        textures.append((label, width, height, width * height))
    if not textures:
        raise ValueError("Sprite backing texture could not be resolved")
    return textures


def _export_sprite(data: Any, dest_dir: Path, path_id: int) -> bool:
    name = sanitize_asset_name(data.m_Name) if data.m_Name else f"sprite_{path_id}"
    dest = dest_dir / "Sprite" / f"{_asset_output_stem(data, name, path_id)}.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    image = data.image
    if image is None or image.size == (0, 0):
        return False
    _save_png_atomically(image, dest)
    return True


def _save_png_atomically(image: Any, dest: Path) -> None:
    fd, temporary = tempfile.mkstemp(prefix=f".{dest.name}.", suffix=".tmp", dir=dest.parent)
    os.close(fd)
    try:
        image.save(temporary, format="PNG")
        os.replace(temporary, dest)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _export_audioclip(data: Any, dest_dir: Path, path_id: int) -> bool:
    base = sanitize_asset_name(data.m_Name) if data.m_Name else f"audio_{path_id}"
    out_dir = dest_dir / "AudioClip"
    out_dir.mkdir(parents=True, exist_ok=True)
    resource = getattr(data, "m_Resource", None)
    inline = getattr(data, "m_AudioData", None)
    if inline is not None and len(inline) > 0:
        payload = bytes(inline)
        stream_source = "inline"
        offset = 0
    elif resource is not None and getattr(data, "object_reader", None) is not None and resource.m_Size > 0:
        from UnityPy.helpers.ResourceReader import get_resource_data

        payload = get_resource_data(
            resource.m_Source,
            data.object_reader.assets_file,
            resource.m_Offset,
            resource.m_Size,
        )
        stream_source = resource.m_Source
        offset = resource.m_Offset
    else:
        return False

    source_file = getattr(getattr(data, "object_reader", None), "assets_file", None)
    source_file_name = sanitize_asset_name(Path(str(getattr(source_file, "name", "data"))).name)
    stem = f"{source_file_name}_{base}_{path_id}"
    (out_dir / f"{stem}.audio.bin").write_bytes(payload)

    decoded_samples: list[tuple[str, bytes]] = []
    decode_error: str | None = None
    decoded_by: str | None = None
    try:
        samples = data.samples
        if samples:
            for index, (sample_name, sample_bytes) in enumerate(samples.items()):
                sample_path = Path(sample_name)
                suffix = sample_path.suffix or ".audio"
                sample_stem = sanitize_asset_name(sample_path.stem or base)
                decoded_samples.append((f"{sample_stem}_{index:04d}{suffix}", sample_bytes))
            decoded_by = "UnityPy"
    except Exception as exc:  # noqa: BLE001 - attempt FSB5 after preserving original bytes
        decode_error = f"{type(exc).__name__}: {exc}"

    if not decoded_samples:
        try:
            import fsb5

            bank = fsb5.FSB5(payload)
            extension = bank.get_sample_extension().lstrip(".")
            decoded_samples = [
                (f"{sanitize_asset_name(sample.name)}_{index:04d}.{extension}", bank.rebuild_sample(sample))
                for index, sample in enumerate(bank.samples)
            ]
            decoded_by = "fsb5"
            decode_error = None
        except Exception as exc:  # noqa: BLE001 - raw payload remains preserved
            if decode_error is None:
                decode_error = f"{type(exc).__name__}: {exc}"

    for sample_name, sample_bytes in decoded_samples:
        (out_dir / f"{stem}_{sample_name}").write_bytes(sample_bytes)
    (out_dir / f"{stem}.audio.json").write_text(
        json.dumps(
            {
                "name": getattr(data, "m_Name", None),
                "pathId": path_id,
                "source": stream_source,
                "offset": offset,
                "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "compressionFormat": getattr(data, "m_CompressionFormat", None),
                "channels": getattr(data, "m_Channels", None),
                "frequency": getattr(data, "m_Frequency", None),
                "bitsPerSample": getattr(data, "m_BitsPerSample", None),
                "lengthSeconds": getattr(data, "m_Length", None),
                "payloadEncoding": "original Unity AudioClip payload; preserved byte-for-byte",
                "decodedSamples": [name for name, _ in decoded_samples],
                "decodedBy": decoded_by,
                "decodeError": decode_error,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return True


def _export_textasset(data: Any, dest_dir: Path, path_id: int) -> bool:
    name = sanitize_asset_name(data.m_Name) if data.m_Name else f"text_{path_id}"
    out_dir = dest_dir / "TextAsset"
    out_dir.mkdir(parents=True, exist_ok=True)
    script = data.m_Script
    payload = script.encode("utf-8", "surrogateescape") if isinstance(script, str) else bytes(script)
    (out_dir / f"{_asset_output_stem(data, name, path_id)}.txt").write_bytes(payload)
    return True


def _export_font(data: Any, dest_dir: Path, path_id: int) -> bool:
    name = sanitize_asset_name(data.m_Name) if data.m_Name else f"font_{path_id}"
    out_dir = dest_dir / "Font"
    out_dir.mkdir(parents=True, exist_ok=True)
    font_data = getattr(data, "m_FontData", None)
    if not font_data:
        return False
    (out_dir / f"{_asset_output_stem(data, name, path_id)}.ttf").write_bytes(bytes(font_data))
    return True


_EXPORTERS = {
    "Texture2D": _export_texture2d,
    "Sprite": _export_sprite,
    "AudioClip": _export_audioclip,
    "TextAsset": _export_textasset,
    "Font": _export_font,
}


def rebuild_preserved_fsb5_audio(primary_content_dir: Path) -> dict[str, Any]:
    """Decode preserved FSB5 payloads without re-reading Unity's huge assets.

    The original `.audio.bin` files and their stream metadata remain untouched;
    rebuilt samples are written beside them using the codec extension emitted
    by the FSB5 header.
    """

    import fsb5

    audio_dir = primary_content_dir.resolve() / "AudioClip"
    if not audio_dir.is_dir():
        return {
            "schema": "agentdecompile.unity-fsb5-decode.v1",
            "status": "error",
            "reason": f"AudioClip output directory not found: {audio_dir}",
            "outputDir": str(audio_dir),
        }

    files = sorted(audio_dir.glob("*.audio.bin"))
    decoded_clips = 0
    decoded_samples = 0
    already_decoded = 0
    failed = 0
    failures: list[dict[str, str]] = []
    for payload_path in files:
        metadata_path = payload_path.with_suffix(".json")
        try:
            payload = payload_path.read_bytes()
            metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.is_file() else {}
            if metadata.get("decodedBy") or metadata.get("decodedSamples"):
                already_decoded += 1
                continue
            expected_sha256 = metadata.get("sha256")
            if expected_sha256 and hashlib.sha256(payload).hexdigest() != expected_sha256:
                raise ValueError("preserved AudioClip payload SHA-256 does not match its metadata")
            bank = fsb5.FSB5(payload)
            extension = bank.get_sample_extension().lstrip(".")
            pending = [
                (
                    f"{payload_path.stem}_{sanitize_asset_name(sample.name)}_{index:04d}.{extension}",
                    bank.rebuild_sample(sample),
                )
                for index, sample in enumerate(bank.samples)
            ]
            for output_name, sample_bytes in pending:
                output_path = audio_dir / output_name
                if output_path.exists():
                    if output_path.read_bytes() != sample_bytes:
                        raise FileExistsError(f"refusing to overwrite different decoded sample: {output_path.name}")
                else:
                    output_path.write_bytes(sample_bytes)
            metadata["decodedSamples"] = [name for name, _ in pending]
            metadata["decodeError"] = None
            metadata["decodedBy"] = "fsb5"
            metadata_path.write_text(
                json.dumps(metadata, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            decoded_clips += 1
            decoded_samples += len(pending)
        except Exception as exc:  # noqa: BLE001 - retain raw payload and report per clip
            failed += 1
            failures.append({"file": payload_path.name, "error": f"{type(exc).__name__}: {exc}"})

    return {
        "schema": "agentdecompile.unity-fsb5-decode.v1",
        "status": "partial" if failed else "complete",
        "outputDir": str(audio_dir),
        "payloadCount": len(files),
        "alreadyDecoded": already_decoded,
        "decodedClips": decoded_clips,
        "decodedSamples": decoded_samples,
        "failed": failed,
        "failures": failures[:100],
        "claimBoundary": "decoded FSB5 samples emitted beside untouched original .audio.bin payloads",
    }


def export_data_file(
    source: Path,
    dest_dir: Path,
    object_types: set[str] | None = None,
    max_texture_pixels: int | None = None,
) -> tuple[int, int, int, list[str], list[dict[str, Any]]]:
    """Export supported asset types from one Unity data file.

    Returns exported/failed/skipped counts, failure messages, and skip records. Reads and
    frees one object at a time so peak memory does not scale with how many
    objects the file contains.
    """

    unitypy = _require_unitypy()
    exported = 0
    skipped = 0
    failed = 0
    failures: list[str] = []
    skipped_objects: list[dict[str, Any]] = []
    selected_types = EXPORTABLE_TYPES if object_types is None else object_types
    env = unitypy.load(str(source))
    for obj in env.objects:
        type_name = obj.type.name
        if type_name not in selected_types:
            continue
        try:
            data = obj.read()
            if max_texture_pixels is not None and type_name in {"Texture2D", "Sprite"}:
                try:
                    texture_dimensions = (
                        [("texture", int(getattr(data, "m_Width", 0) or 0), int(getattr(data, "m_Height", 0) or 0), _texture2d_pixel_count(data))]
                        if type_name == "Texture2D"
                        else _sprite_texture_pixel_counts(data)
                    )
                except Exception as exc:  # noqa: BLE001 - uncertainty must fail closed before image access
                    skipped += 1
                    skipped_objects.append(
                        {
                            "pathId": obj.path_id,
                            "type": type_name,
                            "reason": "invalid-texture-dimensions" if type_name == "Texture2D" else "unresolvable-sprite-texture",
                            "detail": str(exc),
                            "maxTexturePixels": max_texture_pixels,
                        }
                    )
                    continue
                over_limit = [entry for entry in texture_dimensions if entry[3] > max_texture_pixels]
                if over_limit:
                    skipped += 1
                    skipped_objects.append(
                        {
                            "pathId": obj.path_id,
                            "type": type_name,
                            "reason": "over-texture-pixel-limit" if type_name == "Texture2D" else "over-sprite-texture-pixel-limit",
                            "textures": [
                                {"role": label, "width": width, "height": height, "pixels": pixels}
                                for label, width, height, pixels in texture_dimensions
                            ],
                            "maxTexturePixels": max_texture_pixels,
                        }
                    )
                    continue
            if _EXPORTERS[type_name](data, dest_dir, obj.path_id):
                exported += 1
            else:
                skipped += 1
        except Exception as exc:  # noqa: BLE001 - keep scanning past one bad object
            failed += 1
            failures.append(f"{type_name} path_id={obj.path_id}: {exc}")
        finally:
            data = None
            gc.collect()
    env = None
    gc.collect()
    return exported, failed, skipped, failures, skipped_objects


def export_primary_content(
    install_root: Path,
    output_dir: Path,
    data_files: list[Path] | None = None,
    object_types: set[str] | None = None,
    max_texture_pixels: int | None = None,
) -> dict[str, Any]:
    """Export textures, sprites, audio, text assets, and fonts from a Unity
    install directory into ``output_dir``, one type-named subfolder each.

    Does not export meshes, materials, or scene/prefab structure -- use a
    full project-reconstruction tool (e.g. AssetRipper) when that's needed
    and the asset graph fits in available memory.
    """

    install_root = install_root.resolve()
    output_dir = output_dir.resolve()
    selected_types = EXPORTABLE_TYPES if object_types is None else set(object_types)
    unknown_types = selected_types - EXPORTABLE_TYPES
    if unknown_types:
        raise ValueError(f"unsupported Unity object type(s): {', '.join(sorted(unknown_types))}")
    if not selected_types:
        raise ValueError("at least one Unity object type must be selected")
    if max_texture_pixels is not None and (
        isinstance(max_texture_pixels, bool)
        or not isinstance(max_texture_pixels, int)
        or max_texture_pixels < 1
    ):
        raise ValueError("max_texture_pixels must be a positive integer")
    output_dir.mkdir(parents=True, exist_ok=True)

    data_dir = find_unity_data_dir(install_root)
    if data_dir is None:
        return {
            "schema": "agentdecompile.unity-primary-content-export.v1",
            "status": "error",
            "reason": "no *_Data directory found under install root",
            "installRoot": str(install_root),
        }

    discovered = discover_data_files(data_dir)
    if data_files:
        allowed = {p.resolve(): p for p in discovered}
        files = []
        for requested in data_files:
            candidate = requested if requested.is_absolute() else data_dir / requested
            resolved = candidate.resolve()
            if resolved not in allowed:
                raise ValueError(
                    f"Unity data file must name a discovered top-level data file under {data_dir}: {requested}"
                )
            if resolved not in {p.resolve() for p in files}:
                files.append(allowed[resolved])
    else:
        files = discovered
    per_file: list[dict[str, Any]] = []
    total_exported = 0
    total_failed = 0
    total_skipped = 0
    skipped_objects: list[dict[str, Any]] = []
    for source in files:
        exported, failed, skipped, failures, file_skips = export_data_file(
            source, output_dir, selected_types, max_texture_pixels
        )
        total_exported += exported
        total_failed += failed
        total_skipped += skipped
        skipped_objects.extend({"file": source.name, **entry} for entry in file_skips)
        per_file.append(
            {
                "file": source.name,
                "sizeBytes": source.stat().st_size,
                "exported": exported,
                "failed": failed,
                "skipped": skipped,
                "failures": failures[:20],
            }
        )

    return {
        "schema": "agentdecompile.unity-primary-content-export.v1",
        "status": "partial" if total_failed or total_skipped else "complete",
        "installRoot": str(install_root),
        "dataDir": str(data_dir),
        "outputDir": str(output_dir),
        "filesScanned": len(files),
        "totalExported": total_exported,
        "totalFailed": total_failed,
        "totalSkipped": total_skipped,
        "selectedFiles": [source.name for source in files],
        "selectedTypes": sorted(selected_types),
        "maxTexturePixels": max_texture_pixels,
        "skippedObjects": skipped_objects,
        "perFile": per_file,
        "claimBoundary": "textures/sprites/audio/text/fonts only; decoder failures preserve original compressed audio bytes plus metadata; no meshes, materials, or scene/prefab structure",
    }


def export_mesh_derivatives(
    install_root: Path,
    output_dir: Path,
    data_files: list[Path] | None = None,
    *,
    export_format: str = "obj",
    max_object_mib: int = 192,
    resume: bool = True,
) -> dict[str, Any]:
    """Export raw source byte ranges or lossy OBJ derivatives, one Mesh at a time.

    UnityPy still builds an in-memory object index for each selected serialized
    file; this limit bounds per-Mesh decoding, not total parser/index memory.
    """

    import re

    unitypy = _require_unitypy()
    install_root = install_root.resolve()
    output_dir = output_dir.resolve()
    if max_object_mib < 1:
        raise ValueError("max_object_mib must be at least 1")
    if export_format not in {"obj", "raw"}:
        raise ValueError("export_format must be 'obj' or 'raw'")
    data_dir = find_unity_data_dir(install_root)
    if data_dir is None:
        return {"schema": MESH_EXPORT_SCHEMA, "status": "error", "reason": "no *_Data directory found under install root"}
    discovered = discover_data_files(data_dir)
    if data_files:
        allowed = {p.resolve(): p for p in discovered}
        sources = []
        for requested in data_files:
            candidate = requested if requested.is_absolute() else data_dir / requested
            resolved = candidate.resolve()
            if resolved not in allowed:
                raise ValueError(f"Unity data file must name a discovered top-level data file under {data_dir}: {requested}")
            if resolved not in {p.resolve() for p in sources}:
                sources.append(allowed[resolved])
    else:
        sources = discovered

    selected_data_files = sorted(str(source.resolve(strict=True)) for source in sources)
    install_root = install_root.resolve(strict=True)
    data_dir = data_dir.resolve(strict=True)

    def overlaps(left: Path, right: Path) -> bool:
        return left == right or left in right.parents or right in left.parents

    if overlaps(output_dir, install_root) or overlaps(output_dir, data_dir):
        raise ValueError(
            f"mesh export output directory must not overlap the Unity install root or *_Data directory: {output_dir}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = output_dir / "mesh-derivative-receipt.json"
    old_entries: dict[str, dict[str, Any]] = {}
    if resume and receipt_path.is_file():
        try:
            old = json.loads(receipt_path.read_text(encoding="utf-8"))
            old_selection = old.get("selectedDataFiles")
            if old_selection is None:
                # Older receipts did not persist selection explicitly. Infer
                # only the source paths actually recorded; this safely resumes
                # a single-file legacy run without treating a partial scan as
                # a complete all-files selection.
                old_selection = sorted(
                    {
                        str(Path(entry["sourcePath"]).resolve())
                        for entry in old.get("objects", [])
                        if isinstance(entry, dict) and entry.get("sourcePath")
                    }
                )
            same_run = (
                old.get("schema") == MESH_EXPORT_SCHEMA
                and old.get("sourceRoot") == str(install_root)
                and old.get("outputDir") == str(output_dir)
                and old.get("exportFormat") == export_format
                and old.get("maxObjectMiB") == max_object_mib
                and old_selection == selected_data_files
            )
            if same_run:
                old_entries = {
                    f"{entry.get('sourcePath')}:{entry.get('pathId')}": entry
                    for entry in old.get("objects", [])
                    if entry.get("status") == "exported" and entry.get("output")
                }
        except (OSError, ValueError, TypeError):
            old_entries = {}

    entries: list[dict[str, Any]] = []
    totals = {"exported": 0, "skipped": 0, "failed": 0, "resumed": 0}
    mesh_objects_seen = 0
    files_scanned = 0
    hashes: dict[Path, str] = {}

    def write_receipt(status: str = "running") -> None:
        record = {
            "schema": MESH_EXPORT_SCHEMA,
            "status": status,
            "sourceRoot": str(install_root),
            "outputDir": str(output_dir),
            "selectedDataFiles": selected_data_files,
            "maxObjectMiB": max_object_mib,
            "exportFormat": export_format,
            "filesScanned": files_scanned,
            "meshObjectsSeen": mesh_objects_seen,
            "totals": totals,
            "objects": entries,
            "claimBoundary": "raw mode copies the exact source byte range for each Mesh and records source hash, path ID and byte range, but does not recreate Unity references or include externally streamed resource bytes; OBJ mode is lossy and does not preserve Unity serialization, materials, scene references or complete skinning/blend-shape fidelity",
        }
        temporary = receipt_path.with_suffix(".json.tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(record, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(receipt_path)
        if os.name == "posix":
            directory_fd = os.open(receipt_path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)

    write_receipt()
    for source in sources:
        env = None
        try:
            if source not in hashes:
                hasher = hashlib.sha256()
                with source.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        hasher.update(chunk)
                hashes[source] = hasher.hexdigest()
            file_key = hashlib.sha256(source.name.encode("utf-8", "surrogateescape")).hexdigest()[:16]
            env = unitypy.load(str(source))
            files_scanned += 1
            mesh_objects = sorted((obj for obj in env.objects if obj.type.name == "Mesh"), key=lambda obj: obj.path_id)
            mesh_objects_seen += len(mesh_objects)
            for obj in mesh_objects:
                common = {"source": source.name, "sourcePath": str(source), "sourceSha256": hashes[source], "pathId": obj.path_id, "byteStart": obj.byte_start, "serializedBytes": obj.byte_size}
                old_entry = old_entries.get(f"{source}:{obj.path_id}")
                old_name = old_entry.get("output") if old_entry else None
                old_output = output_dir / old_name if isinstance(old_name, str) and Path(old_name).name == old_name else None
                if (
                    old_entry
                    and old_entry.get("sourceSha256") == hashes[source]
                    and old_entry.get("byteStart") == obj.byte_start
                    and old_entry.get("serializedBytes") == obj.byte_size
                    and old_output is not None
                    and old_output.is_file()
                    and old_output.stat().st_size == old_entry.get("outputBytes")
                    and _sha256_file(old_output) == old_entry.get("outputSha256")
                ):
                    entries.append({**common, **old_entry, "status": "exported", "resumed": True})
                    totals["exported"] += 1
                    totals["resumed"] += 1
                elif obj.byte_size > max_object_mib * 1024 * 1024:
                    entries.append({**common, "status": "skipped", "reason": "over-per-object-size-limit"})
                    totals["skipped"] += 1
                else:
                    mesh = None
                    try:
                        if export_format == "raw":
                            with source.open("rb") as source_handle:
                                source_handle.seek(obj.byte_start)
                                content = source_handle.read(obj.byte_size)
                            if len(content) != obj.byte_size:
                                raise ValueError(
                                    f"raw source range returned {len(content)} bytes != serialized size {obj.byte_size}"
                                )
                            name = f"mesh_{obj.path_id}"
                            filename = f"{file_key}_{obj.path_id}.mesh.bin"
                        else:
                            mesh = obj.parse_as_object()
                            name = str(mesh.m_Name or f"mesh_{obj.path_id}")
                            safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")[:90] or "unnamed"
                            filename = f"{file_key}_{obj.path_id}_{safe_name}.obj"
                            content = mesh.export("obj")
                            if not content:
                                entries.append({**common, "name": name, "status": "skipped", "reason": "empty-or-unsupported-mesh"})
                                totals["skipped"] += 1
                                content = None
                        if content is not None:
                            target = output_dir / filename
                            temporary = target.with_suffix(target.suffix + ".tmp")
                            if export_format == "raw":
                                temporary.write_bytes(content)
                            else:
                                temporary.write_text(content, encoding="utf-8")
                            temporary.replace(target)
                            entries.append({**common, "name": name, "status": "exported", "exportFormat": export_format, "output": filename, "outputBytes": target.stat().st_size, "outputSha256": _sha256_file(target)})
                            totals["exported"] += 1
                    except Exception as exc:  # noqa: BLE001 - preserve per-object failure evidence
                        entries.append({**common, "status": "failed", "error": f"{type(exc).__name__}: {exc}"})
                        totals["failed"] += 1
                    finally:
                        mesh = None
                        gc.collect()
                write_receipt()
        except Exception as exc:  # noqa: BLE001 - preserve per-file failure evidence
            entries.append({"source": source.name, "status": "failed", "error": f"{type(exc).__name__}: {exc}"})
            totals["failed"] += 1
        finally:
            env = None
            gc.collect()
            write_receipt()
    status = "complete" if sources and files_scanned == len(sources) and mesh_objects_seen > 0 and totals["failed"] == 0 and totals["skipped"] == 0 else "partial"
    write_receipt(status)
    return json.loads(receipt_path.read_text(encoding="utf-8"))
