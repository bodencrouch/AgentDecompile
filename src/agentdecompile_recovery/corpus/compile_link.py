"""Compile recovered units and link a complete executable.

Priority 1 of the corpus pipeline: one donor project becomes a real linked
image. Object files alone are not a complete executable. Byte-accuracy is a
later, separate stage.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any

from .recovered_c_preamble import preamble_for_source


def _compiler_run_attestation(stderr: str | bytes | None, *, sources: list[Path] | None = None,
                              outputs: list[Path] | None = None,
                              process_returncode: int | None = None) -> dict[str, Any]:
    """Use the verifier's canonical parser without creating an import cycle.

    This is intentionally lazy: compile_link is imported by the direct-image
    verifier, while the marker parser lives in that verifier's sibling module.
    The parsed record is always diagnostic-only and incomplete.
    """
    from .verify_recovered_byteexact import _compiler_run_attestation as parse_attestation

    return parse_attestation(stderr, sources=sources, outputs=outputs,
                             process_returncode=process_returncode)


def _diagnostic_tail(value: str | bytes | None, limit: int = 2000) -> str:
    if isinstance(value, bytes):
        return value[-limit:].decode("utf-8", errors="replace")
    return (value or "")[-limit:]


def find_c_compiler() -> str | None:
    for name in ("cc", "gcc", "clang"):
        found = shutil.which(name)
        if found:
            return found
    return None


def find_msvc_compiler() -> dict[str, str] | None:
    """Locate cl.exe from PATH or operator env. No product/tool home is assumed."""
    cl = shutil.which("cl") or shutil.which("cl.exe")
    if cl:
        return {"compiler": cl, "via": "path"}
    return None


def compile_unit_msvc(cl: str, source: Path, obj: Path, *, timeout: int = 60) -> dict[str, Any]:
    from .compiler_msvc71 import source_language

    obj.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            [cl, "/nologo", "/c", ("/Tc" if source_language(source) == "c" else "/Tp") + str(source), f"/Fo{obj}"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        captured = exc.stderr
        return {"ok": False, "source": str(source), "object": str(obj),
                "returncode": None, "timedOut": True,
                "stderr": _diagnostic_tail(captured or exc.output),
                "compilerRunAttestation": _compiler_run_attestation(
                    captured, sources=[source], outputs=[obj]),
                "compilerLaunchState": "timeout-observed-process-started",
                "toolchain": "msvc"}
    captured = proc.stderr or proc.stdout or ""
    return {
        "ok": proc.returncode == 0 and obj.is_file(),
        "source": str(source),
        "object": str(obj),
        "returncode": proc.returncode,
        "stderr": _diagnostic_tail(captured),
        "compilerRunAttestation": _compiler_run_attestation(
            proc.stderr, sources=[source], outputs=[obj], process_returncode=proc.returncode),
        "compilerLaunchState": "process-returned",
        "toolchain": "msvc",
    }


def compile_unit(compiler: str, source: Path, obj: Path, *, timeout: int = 60,
                 compiler_environment: dict[str, str] | None = None) -> dict[str, Any]:
    from .compiler_msvc71 import source_language

    obj.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            [compiler, "-x", source_language(source), "-c", str(source), "-o", str(obj)],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=compiler_environment,
        )
    except subprocess.TimeoutExpired as exc:
        captured = exc.stderr
        return {"ok": False, "source": str(source), "object": str(obj),
                "returncode": None, "timedOut": True,
                "stderr": _diagnostic_tail(captured or exc.output),
                "compilerRunAttestation": _compiler_run_attestation(
                    captured, sources=[source], outputs=[obj]),
                "compilerLaunchState": "timeout-observed-process-started"}
    captured = proc.stderr or ""
    return {
        "ok": proc.returncode == 0 and obj.is_file(),
        "source": str(source),
        "object": str(obj),
        "returncode": proc.returncode,
        "stderr": _diagnostic_tail(captured),
        "compilerRunAttestation": _compiler_run_attestation(
            proc.stderr, sources=[source], outputs=[obj], process_returncode=proc.returncode),
        "compilerLaunchState": "process-returned",
    }


STUB_MARK = "STABS-attributed compilation unit"


def _read_head(path: Path, n: int = 500) -> str:
    with path.open("rb") as handle:
        return handle.read(n).decode("utf-8", errors="replace")


def _is_compile_unit(path: Path) -> bool:
    """Shared eligibility for tree discovery and explicit candidate selection."""
    from .compiler_msvc71 import SOURCE_LANGUAGES

    if (path.suffix.lower() not in SOURCE_LANGUAGES or not path.is_file()
            or path.name.startswith(("_", ".agentdecompile-"))):
        return False
    head = _read_head(path)
    return STUB_MARK not in head or "address: 0x" in head


def iter_compile_units(root: Path) -> list[Path]:
    """Source files that are compile units, not STABS index stubs."""
    units: list[Path] = []
    for directory, directories, filenames in os.walk(root, followlinks=False):
        # Retained normalized diagnostic inputs are observations, not source units.
        directories[:] = [name for name in directories if name != ".compiler-diagnostics"]
        for filename in filenames:
            path = Path(directory) / filename
            if _is_compile_unit(path):
                units.append(path)
    return sorted(units)


def select_compile_units(root: Path, source_paths: list[str] | None = None) -> list[Path]:
    """Resolve explicit root-relative candidates using ordinary unit eligibility.

    No outputs or compiler invocation occur here. An omitted selection retains
    the full-tree ordering; explicit candidates cannot escape through symlinks.
    """
    if source_paths is None:
        return iter_compile_units(root)
    if not source_paths or len(source_paths) > 4096:
        raise ValueError("candidate-selection-capacity")
    root = Path(root).resolve()
    selected: list[Path] = []
    seen: set[Path] = set()
    for value in source_paths:
        if not isinstance(value, str) or not value.strip() or len(value) > 4096:
            raise ValueError("candidate-path-invalid")
        relative = Path(value)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("candidate-path-not-root-relative")
        resolved = (root / relative).resolve()
        if not resolved.is_relative_to(root):
            raise ValueError("candidate-path-outside-source-root")
        if resolved in seen:
            raise ValueError("candidate-path-duplicate")
        if (".compiler-diagnostics" in relative.parts
                or any((root / Path(*relative.parts[:index])).is_symlink()
                       for index in range(1, len(relative.parts)))
                or not _is_compile_unit(root / relative)):
            raise ValueError("candidate-not-eligible-compile-unit")
        seen.add(resolved)
        selected.append(root / relative)
    return sorted(selected)


def _object_basis_path(obj: Path) -> Path:
    return obj.with_name(obj.name + ".agentdecompile-basis")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def object_is_current(obj: Path, basis: str | None) -> bool:
    """Reuse only an object whose bytes and compile basis match its receipt."""
    if basis is None or not obj.is_file():
        return False
    try:
        if obj.stat().st_size <= 0:
            return False
        receipt = json.loads(_object_basis_path(obj).read_text(encoding="utf-8"))
        return (
            isinstance(receipt, dict)
            and receipt.get("schema") == "agentdecompile.compile-object-cache/v1"
            and receipt.get("basis") == basis
            and receipt.get("objectSize") == obj.stat().st_size
            and receipt.get("objectSha256") == _sha256_file(obj)
        )
    except (OSError, UnicodeError, ValueError, TypeError):
        return False


def _compiler_identity(compiler: str, *, vcroot: Path | None, wineprefix: str | None,
                       script: bool, cache_input_manifest: Path | None,
                       compiler_environment: dict[str, str] | None = None) -> str | None:
    """Hash observed compiler inputs and an explicitly declared complete closure.

    Wrapper and toolchain bytes alone do not identify Wine runtime libraries,
    prefix configuration, or other transitive inputs. No manifest means no
    object reuse; compilation may still proceed normally.
    """
    effective_environment = os.environ if compiler_environment is None else compiler_environment
    try:
        if cache_input_manifest is None:
            return None
        manifest_path = Path(cache_input_manifest).resolve()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or manifest.get("complete") is not True:
            return None
        files = manifest.get("files")
        environment = manifest.get("environment", [])
        if (not isinstance(files, list) or not files
                or not all(isinstance(item, str) for item in files)
                or not isinstance(environment, list)
                or not all(isinstance(item, str) for item in environment)):
            return None
        closure = []
        for item in files:
            path = Path(item)
            if not path.is_absolute():
                path = manifest_path.parent / path
            path = path.resolve()
            closure.append((str(path), _sha256_file(path)))
        compiler_path = Path(compiler).resolve()
        compiler_hash = hashlib.sha256(compiler_path.read_bytes()).hexdigest()
        toolchain_hash = None
        compiler_root_value = effective_environment.get("VCROOT") or (str(vcroot) if vcroot is not None else None)
        compiler_root = Path(compiler_root_value).resolve() if compiler_root_value else None
        if compiler_root is not None and compiler_root.is_dir():
            from ..grid_lanes.toolchain import manifest_for_root
            toolchain_hash = manifest_for_root(compiler_root).identity_hash
        if script and toolchain_hash is None:
            return None  # A wrapper alone cannot identify its compiler dependencies.
        wine_path = (shutil.which("wine", path=effective_environment.get("PATH"))
                     or shutil.which("wine64", path=effective_environment.get("PATH")))
        wine_identity = None
        if wine_path:
            wine_binary = Path(wine_path).resolve()
            wine_identity = {"path": str(wine_binary),
                             "sha256": hashlib.sha256(wine_binary.read_bytes()).hexdigest()}
        python_identity = None
        if Path(compiler).suffix.lower() == ".py":
            python_binary = Path(sys.executable).resolve()
            python_identity = {
                "path": str(python_binary),
                "version": sys.version,
                "sha256": _sha256_file(python_binary),
            }
        recipe_hash = hashlib.sha256(Path(__file__).with_name("recovered_c_preamble.py").read_bytes()).hexdigest()
        basis = {
            "compiler": str(compiler_path), "compilerSha256": compiler_hash,
            "toolchainIdentity": toolchain_hash, "wineIdentity": wine_identity,
            "pythonRuntime": python_identity,
            "recipeSha256": recipe_hash,
            "declaredClosure": sorted(closure),
            "manifest": manifest,
            "environment": {key: effective_environment.get(key) for key in (
                "PATH", "VCROOT", "AGENT_DECOMPILE_VCROOT", "INCLUDE", "LIB",
                "CL_OPT", "WINEPREFIX", "WINELOADER", "WINESERVER", "WINEDEBUG",
                *environment) if key != "AGENT_DECOMPILE_COMPILER_LEASE_FD"},
            "wineprefix": wineprefix,
        }
        return hashlib.sha256(json.dumps(basis, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    except Exception:
        return None


def _compile_basis(source: Path, preamble: str, compiler_identity: str | None) -> str | None:
    from .compiler_msvc71 import source_language

    if compiler_identity is None:
        return None
    try:
        basis = {"compilerIdentity": compiler_identity,
                 "sourceLanguage": source_language(source),
                 "sourceSha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                 "preambleSha256": hashlib.sha256(preamble.encode("utf-8")).hexdigest()}
        return hashlib.sha256(json.dumps(basis, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    except OSError:
        return None


def _write_object_basis(obj: Path, basis: str) -> None:
    stamp = _object_basis_path(obj)
    receipt = {
        "schema": "agentdecompile.compile-object-cache/v1",
        "basis": basis,
        "objectSha256": _sha256_file(obj),
        "objectSize": obj.stat().st_size,
    }
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{stamp.name}.", suffix=".tmp", dir=stamp.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(receipt, output, sort_keys=True, separators=(",", ":"))
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, stamp)
    finally:
        temporary.unlink(missing_ok=True)


LINK_FLAGS = ("/nologo", "/OPT:NOREF")


def link_stamp_path(output: Path) -> Path:
    return Path(output).with_name("." + Path(output).name + ".link-stamp")


def link_flags_text(flags: tuple[str, ...] | list[str] = LINK_FLAGS) -> str:
    return "\n".join(flags) + "\n"


def _link_object_inventory(objects: list[Path]) -> list[dict[str, Any]]:
    inventory = []
    for obj in objects:
        captured = _read_observation_bytes(Path(obj))
        if not captured:
            raise ValueError("empty-link-object")
        inventory.append({"path": str(Path(obj).resolve()), "size": len(captured),
                          "sha256": hashlib.sha256(captured).hexdigest()})
    return inventory


def stamp_matches(output: Path, flags: tuple[str, ...] | list[str] = LINK_FLAGS,
                  objects: list[Path] | None = None) -> bool:
    stamp = link_stamp_path(output)
    try:
        receipt = json.loads(_read_observation_bytes(stamp).decode("utf-8"))
        captured = _read_observation_bytes(Path(output), 256 * 1024 * 1024)
        return (isinstance(receipt, dict)
                and receipt.get("schema") == "agentdecompile.link-artifact-cache/v2"
                and receipt.get("flags") == list(flags)
                and receipt.get("outputPath") == str(Path(output).resolve())
                and receipt.get("outputSize") == len(captured)
                and receipt.get("outputSha256") == hashlib.sha256(captured).hexdigest()
                and objects is not None
                and receipt.get("objects") == _link_object_inventory(objects))
    except (OSError, ValueError, UnicodeError, TypeError):
        return False


def write_link_stamp(output: Path, flags: tuple[str, ...] | list[str] = LINK_FLAGS,
                     objects: list[Path] | None = None,
                     expected_inputs: list[dict[str, Any]] | None = None,
                     expected_output: dict[str, Any] | None = None) -> None:
    path = link_stamp_path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    captured = _read_observation_bytes(Path(output), 256 * 1024 * 1024)
    output_digest = hashlib.sha256(captured).hexdigest()
    if expected_output is not None and expected_output != {"size": len(captured), "sha256": output_digest}:
        raise ValueError("linked-output-changed-before-stamp")
    inputs = _link_object_inventory(objects or [])
    if expected_inputs is not None and inputs != expected_inputs:
        raise ValueError("link-input-objects-changed-before-stamp")
    receipt = {"schema": "agentdecompile.link-artifact-cache/v2", "flags": list(flags),
               "outputPath": str(Path(output).resolve()), "outputSize": len(captured),
               "outputSha256": output_digest,
               "objects": inputs,
               "claim": "Artifact/input-inventory cache only; not complete linker or toolchain closure."}
    encoded = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(encoded) > 64 * 1024 * 1024:
        raise ValueError("link-stamp-capacity")
    descriptor, name = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def image_is_current(
    objects: list[Path],
    output: Path,
    *,
    flags: tuple[str, ...] | list[str] = LINK_FLAGS,
) -> bool:
    """Advisory artifact equality only; never authorize automatic link reuse.

    Output bytes and ordered object inventory do not qualify linker, libraries,
    flags/environment or Wine execution closure. Generic callers must relink.
    """
    if not objects:
        return False
    try:
        if not output.is_file() or output.stat().st_size <= 0:
            return False
        return stamp_matches(output, flags, objects)
    except OSError:
        return False


def write_entrypoint(dest: Path) -> Path:
    """Tiny CRT entry so a tree of function TUs can link to an image."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("int main(void) { return 0; }\n", encoding="utf-8")
    return dest


def compile_unit_script(
    script: str, source: Path, obj: Path, *, name: str = "", timeout: int = 90,
    preamble: str = "", compiler_environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    from . import compiler_msvc71

    if Path(script).resolve() != Path(compiler_msvc71.__file__).resolve():
        return _compile_unit_script_leased(script, source, obj, name=name, timeout=timeout,
                                           preamble=preamble, compiler_environment=compiler_environment)
    environment = dict(os.environ if compiler_environment is None else compiler_environment)
    try:
        config = compiler_msvc71._configuration(environment)
        with compiler_msvc71.compiler_prefix_lease(config['winePrefix'], config['environment']) as (environment, descriptor):
            return _compile_unit_script_leased(script, source, obj, name=name, timeout=timeout,
                                               preamble=preamble, compiler_environment=environment,
                                               lease_descriptor=descriptor)
    except (OSError, ValueError, RuntimeError) as exc:
        return {"ok": False, "source": str(source), "object": str(obj),
                "reason": "compiler-prefix-lease-refused", "stderr": str(exc),
                "compilerRunAttestation": _compiler_run_attestation(
                    None, sources=[source], outputs=[obj]),
                "compilerLaunchState": "not-started",
                "previousObjectPreserved": obj.is_file()}


def _compile_unit_script_leased(
    script: str, source: Path, obj: Path, *, name: str = "", timeout: int = 90,
    preamble: str = "", compiler_environment: dict[str, str] | None = None,
    lease_descriptor: int | None = None,
) -> dict[str, Any]:
    """Operator compiler wrapper: ``script <source> <obj> [name]``."""
    obj.parent.mkdir(parents=True, exist_ok=True)
    obj.unlink(missing_ok=True)
    compile_source = source
    compile_obj = obj
    staged_source: Path | None = None
    staged_obj: Path | None = None

    # Wine exposes Unix files through a Windows path. Characters accepted by
    # ext4 (notably ``?`` and ``*`` in recovered C++ names) are rejected by
    # Win32 before cl.exe can open the source. Keep the operator-facing paths
    # and object layout stable, but give the compiler filesystem-safe aliases.
    win32_illegal = '<>:"/\\|?*'
    if preamble or any(char in source.name for char in win32_illegal):
        handle, temp_name = tempfile.mkstemp(
            prefix=".agentdecompile-",
            suffix=source.suffix,
        )
        os.close(handle)
        staged_source = Path(temp_name)
        if preamble:
            staged_source.write_text(preamble + source.read_text(errors="replace"), encoding="utf-8")
        else:
            shutil.copy2(source, staged_source)
        compile_source = staged_source
    if staged_source is not None or any(char in obj.name for char in win32_illegal):
        handle, temp_name = tempfile.mkstemp(
            dir=obj.parent,
            prefix=".agentdecompile-",
            suffix=obj.suffix or ".obj",
        )
        os.close(handle)
        staged_obj = Path(temp_name)
        staged_obj.unlink(missing_ok=True)
        compile_obj = staged_obj

    try:
        driver = ([sys.executable, str(script)] if Path(script).suffix == ".py"
                  else ["bash", str(script)])
        try:
            proc = subprocess.run(
                [*driver, str(compile_source), str(compile_obj), name or source.stem],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                env=compiler_environment,
                pass_fds=() if lease_descriptor is None else (lease_descriptor,),
            )
        except subprocess.TimeoutExpired as exc:
            captured = exc.stderr
            invocation_sources = [compile_source]
            invocation_outputs = [compile_obj]
            return {
                "ok": False,
                "source": str(source),
                "object": str(obj),
                "returncode": None,
                "timedOut": True,
                "stderr": _diagnostic_tail(captured or exc.output),
                "compilerRunAttestation": _compiler_run_attestation(
                    captured, sources=invocation_sources, outputs=invocation_outputs),
                "compilerLaunchState": "timeout-observed-process-started",
                "toolchain": "python-script" if Path(script).suffix == ".py" else "script",
                "stagedInput": staged_source is not None,
            }
        except OSError as exc:
            return {
                "ok": False,
                "source": str(source),
                "object": str(obj),
                "returncode": None,
                "reason": "compiler-launch-failed",
                "stderr": f"compiler launch failed ({exc.__class__.__name__})",
                "compilerRunAttestation": _compiler_run_attestation(
                    None, sources=[compile_source], outputs=[compile_obj]),
                "compilerLaunchState": "not-started",
                "toolchain": "python-script" if Path(script).suffix == ".py" else "script",
                "stagedInput": staged_source is not None,
            }
        if proc.returncode == 0 and staged_obj is not None and staged_obj.is_file():
            os.replace(staged_obj, obj)
    finally:
        if staged_source is not None:
            staged_source.unlink(missing_ok=True)
        if staged_obj is not None:
            staged_obj.unlink(missing_ok=True)
    return {
        "ok": proc.returncode == 0 and obj.is_file() and obj.stat().st_size > 0,
        "source": str(source),
        "object": str(obj),
        "returncode": proc.returncode,
        "stderr": _diagnostic_tail(proc.stderr or proc.stdout or ""),
        "compilerRunAttestation": _compiler_run_attestation(
            proc.stderr, sources=[compile_source], outputs=[compile_obj],
            process_returncode=proc.returncode),
        "compilerLaunchState": "process-returned",
        "toolchain": "python-script" if Path(script).suffix == ".py" else "script",
        "stagedInput": staged_source is not None,
    }


def _win_z_path(path: Path) -> str:
    text = str(Path(path).resolve())
    if text.startswith("/"):
        return "Z:" + text.replace("/", "\\")
    return text


def _perform_link(objects: list[Path], output: Path, command: Any, *,
                  timeout: int, environment: dict[str, str] | None = None,
                  flags: tuple[str, ...] | list[str] = LINK_FLAGS,
                  native_linker: Path | None = None,
                  lease_descriptor: int | None = None) -> dict[str, Any]:
    """Publish only an owned successful link; retain previous output on failure."""
    output = Path(output)
    previous = output.is_file()
    published = False
    boundary = {"automaticLinkReuse": False,
                "linkReusePolicy": "disabled: complete execution input closure unavailable",
                "artifactCacheScope": "Output/object artifact inventory only; linker/toolchain closure uncertified."}
    try:
        link_stamp_path(output).unlink(missing_ok=True)
        inputs = _link_object_inventory(objects)
        linker_bytes = (_read_observation_bytes(native_linker) if native_linker is not None else None)
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".agentdecompile-link-", dir=output.parent) as directory:
            candidate = Path(directory) / output.name
            argv = command(candidate)
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  timeout=timeout, check=False, env=environment,
                                  pass_fds=() if lease_descriptor is None else (lease_descriptor,))
            diagnostic = (proc.stderr or proc.stdout or "")[-2000:]
            if proc.returncode != 0:
                return {"ok": False, "returncode": proc.returncode, "stderr": diagnostic,
                        "reason": "linker-rejected", "freshLinkedCandidate": False,
                        "previousOutputPreserved": previous, **boundary}
            emitted = _read_observation_bytes(candidate, 256 * 1024 * 1024)
            if not emitted:
                raise ValueError("empty-linked-candidate")
            if _link_object_inventory(objects) != inputs:
                raise ValueError("link-input-objects-changed")
            native_capture = None
            if native_linker is not None:
                if _read_observation_bytes(native_linker) != linker_bytes:
                    raise ValueError('native-linker-changed-during-link')
                map_path = candidate.with_name(candidate.name + '.map')
                map_bytes = _read_observation_bytes(map_path, 8 * 1024 * 1024)
                if not map_bytes:
                    raise ValueError('native-link-map-empty')
                map_digest = hashlib.sha256(map_bytes).hexdigest()
                map_output = output.with_name(output.name + '.native-link-' + map_digest + '.map')
                native_capture = {'objects': inputs, 'argv': argv,
                    'linker': {'path': str(native_linker.resolve()), 'size': len(linker_bytes),
                               'sha256': hashlib.sha256(linker_bytes).hexdigest()},
                    'map': {'path': str(map_output.resolve()), 'size': len(map_bytes),
                            'sha256': map_digest},
                    'mapBytes': map_bytes,
                    # Keep the exact bytes from this invocation in the
                    # process-local observation only. The durable record
                    # carries a digest, not authority to reconstruct them.
                    'imageBytes': emitted,
                    'output': {'path': str(output.resolve()), 'size': len(emitted),
                               'sha256': hashlib.sha256(emitted).hexdigest()},
                    'freshLinkedCandidate': True, 'optimizationPolicy': list(flags)}
                # Atomic no-replace enrollment; a concurrent content-address
                # owner is never overwritten after a check-then-publish race.
                try:
                    os.link(map_path, map_output, follow_symlinks=False)
                except FileExistsError:
                    pass
                if _read_observation_bytes(map_output, 8 * 1024 * 1024) != map_bytes:
                    raise ValueError('native-link-map-content-address-conflict')
            os.replace(candidate, output)
            published = True
            write_link_stamp(output, flags, objects, expected_inputs=inputs,
                             expected_output={"size": len(emitted), "sha256": hashlib.sha256(emitted).hexdigest()})
        return {"ok": True, "returncode": proc.returncode, "stderr": diagnostic,
                "freshLinkedCandidate": True, "previousOutputPreserved": False, **boundary,
                **({'_nativeLinkCapture': native_capture} if native_capture is not None else {})}
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        # The stamp was invalidated before any attempted link. A preserved old
        # candidate is diagnostic-only and cannot become a cached success.
        return {"ok": False, "reason": ("link-timeout-owner-unresolved" if isinstance(exc, subprocess.TimeoutExpired)
                                          else "link-observation-refused" if published else "link-failed"),
                "stderr": f"{exc.__class__.__name__}: {str(exc)[-1800:]}",
                "freshLinkedCandidate": False, "candidatePublished": published,
                "previousOutputPreserved": previous and not published,
                "executionOwnership": "unresolved-after-timeout" if isinstance(exc, subprocess.TimeoutExpired) else "no-timeout-observed",
                "descendantOwnershipUnresolved": isinstance(exc, subprocess.TimeoutExpired),
                "requiresOwnerReconciliation": isinstance(exc, subprocess.TimeoutExpired), **boundary}


def link_msvc(
    objects: list[Path],
    output: Path,
    *,
    vcroot: Path,
    wineprefix: str,
    timeout: int = 3600,
    link_observer: Any = None,
    compiler_environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    from .compiler_msvc71 import compiler_prefix_lease

    environment = dict(os.environ if compiler_environment is None else compiler_environment)
    try:
        with compiler_prefix_lease(Path(wineprefix), environment) as (environment, descriptor):
            return _link_msvc_leased(objects, output, vcroot=vcroot, wineprefix=environment['WINEPREFIX'],
                                     timeout=timeout, link_observer=link_observer,
                                     compiler_environment=environment, lease_descriptor=descriptor)
    except (OSError, ValueError, RuntimeError) as exc:
        return {"ok": False, "output": str(output), "reason": "compiler-prefix-lease-refused",
                "detail": str(exc), "freshLinkedCandidate": False,
                "previousOutputPreserved": Path(output).is_file()}


def _link_msvc_leased(
    objects: list[Path], output: Path, *, vcroot: Path, wineprefix: str,
    timeout: int = 3600, link_observer: Any = None,
    compiler_environment: dict[str, str] | None = None, lease_descriptor: int,
) -> dict[str, Any]:
    """Link COFF objects with VC7 ``link.exe`` via Wine. Not byte-accuracy."""
    output = Path(output)
    if not objects:
        link_stamp_path(output).unlink(missing_ok=True)
        return {"ok": False, "reason": "no object files", "output": str(output)}
    link = Path(vcroot) / "bin" / "link.exe"
    if not link.is_file():
        link_stamp_path(output).unlink(missing_ok=True)
        return {"ok": False, "reason": f"no link.exe at {link}", "output": str(output),
                "freshLinkedCandidate": False, "previousOutputPreserved": output.is_file()}
    env = dict(os.environ if compiler_environment is None else compiler_environment)
    if compiler_environment is not None:
        env["VCROOT"] = str(Path(vcroot).resolve())
    env["WINEPREFIX"] = wineprefix
    env.pop("WINEARCH", None)
    env.setdefault("WINEDEBUG", "-all")
    libdir = Path(vcroot) / "lib"
    env["LIB"] = _win_z_path(libdir)
    def command(candidate: Path) -> list[str]:
        rsp = candidate.parent / "objects.rsp"
        rsp.write_text("\n".join('"' + _win_z_path(p) + '"' for p in objects) + "\n", encoding="utf-8")
        return [
            "wine",
            str(link),
            *LINK_FLAGS,
            f"/LIBPATH:{_win_z_path(libdir)}",
            "kernel32.lib",
            "libc.lib",
            f"/OUT:{_win_z_path(candidate)}",
            f"/MAP:{_win_z_path(candidate.with_name(candidate.name + '.map'))}",
            f"@{_win_z_path(rsp)}",
        ]
    result = _perform_link(objects, output, command, timeout=timeout, environment=env,
                           native_linker=link, lease_descriptor=lease_descriptor)
    captured = result.pop('_nativeLinkCapture', None)
    if captured is not None:
        result['nativeLinkArtifacts'] = {
            key: value for key, value in captured.items()
            if key not in ('mapBytes', 'imageBytes')}
        if link_observer is not None:
            from .source_contribution import _issue_native_link_observation
            try:
                link_observer(_issue_native_link_observation(link_msvc, captured))
            except Exception as exc:
                result.update({'ok': False, 'nativeLinkObservationRefusal': str(exc)[:400]})
    return {
        **result,
        "output": str(output),
        "objectCount": len(objects),
        "linkFlags": list(LINK_FLAGS),
        "claimBoundary": (
            "A linked image proves the generated project builds. It does not "
            "prove byte-accuracy against a shipped binary."
        ),
    }


def _read_observation_bytes(path: Path, limit: int = 64 * 1024 * 1024) -> bytes:
    """Bounded stable regular-file capture; a diagnostic, not writer isolation."""
    import stat

    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or not 0 <= before.st_size <= limit:
            raise ValueError("observation-file-capacity-or-type")
        chunks = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise ValueError("observation-file-truncated")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise ValueError("observation-file-grew")
        after = os.fstat(descriptor)
        current = os.stat(path, follow_symlinks=False)
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        identity = tuple(getattr(before, name) for name in fields)
        if any(tuple(getattr(item, name) for name in fields) != identity for item in (after, current)):
            raise ValueError("observation-file-changed")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _observation_context_refusal(source: bytes) -> str | None:
    """Refuse source-relative preprocessing until include closure is captured.

    Staging is safe for self-contained units, not arbitrary include graphs or
    filename-sensitive builtins. This guard is conservative, not a C parser.
    """
    import re

    text = source.decode("utf-8", errors="strict").replace("??/", "\\")
    text = re.sub(r"\\\r?\n", "", text)
    # Translation-phase splicing precedes comments. Preserve newlines so a
    # comment cannot move a preprocessor directive onto another logical line.
    text = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*.*?\*/',
                  lambda match: " " + "\n" * match.group().count("\n"), text, flags=re.DOTALL)
    if re.search(r"(?m)^\s*(?:#|%:|\?\?=)\s*(?:include|include_next|import)\b", text):
        return "observation-include-context-unsupported"
    if re.search(r"(?m)^\s*(?:export\s+)?import\b", text):
        return "observation-module-import-context-unsupported"
    if re.search(r"##|%:%:|\?\?=\?\?=", text):
        return "observation-token-paste-context-unsupported"
    if re.search(r"\b(?:__FILE__|__FILEW__|__BASE_FILE__|__FILE_NAME__|__TIMESTAMP__|__has_include|__has_include_next|__INCLUDE_LEVEL__|__builtin_FILE|__builtin_file|__builtin_source_location)\b", text):
        return "observation-source-path-builtin-unsupported"
    return None


def compile_and_link_tree(
    src_dir: Path,
    output: Path,
    *,
    compiler: str | None = None,
    sample: int | None = None,
    source_paths: list[str] | None = None,
    obj_dir: Path | None = None,
    workers: int = 2,
    entrypoint: bool = False,
    vcroot: Path | str | None = None,
    wineprefix: str | None = None,
    cache_input_manifest: Path | str | None = None,
    unit_observer: Any = None,
    link_observer: Any = None,
    compiler_environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Compile each unit, then link one image. Not a byte-accuracy claim."""
    from .compiler_msvc71 import source_language

    units = select_compile_units(src_dir, source_paths)
    if sample is not None:
        units = units[: max(0, sample)]
    source_selection = {
        "scope": "selected-candidates" if source_paths is not None else ("sampled-tree" if sample is not None else "full-tree"),
        "selectedFiles": [str(source.resolve().relative_to(Path(src_dir).resolve()))
                          if source.resolve().is_relative_to(Path(src_dir).resolve()) else str(source)
                          for source in units],
        "selectedCount": len(units),
        "fullSourceCoverage": source_paths is None and sample is None,
        "claim": "Eligible source inventory selection, not successful compilation or recovery proof.",
    }
    objects: list[Path] = []
    observed_objects: dict[Path, str] = {}
    failures: list[dict[str, Any]] = []
    preflight_source_digests: dict[Path, str] = {}
    next_unit = 0
    generated_entrypoint_units = 0

    def _coverage() -> dict[str, Any]:
        if unit_observer is None:
            return {"sourceSelection": source_selection}
        return {"sourceSelection": source_selection, "observationCoverage": {
            "selectedUnits": len(units), "attemptedUnits": next_unit,
            "successfulUnits": len(objects), "failedUnits": len(failures),
            "notDispatchedUnits": len(units) - next_unit,
            "observedUnits": len(observed_objects),
            "generatedEntrypointUnits": generated_entrypoint_units,
            "countSemantics": "attemptedUnits counts dispatched units, not compiler invocations; generatedEntrypointUnits counts selected generated units."}}

    # Reject statically unsupported observation inputs before launching any
    # compiler workers. Discovering one include/path-context refusal after
    # hundreds of successful compiles strands that work without improving the
    # build. The worker rechecks the source digest before staging it, so a
    # source changed after preflight cannot silently bypass this gate.
    if unit_observer is not None:
        context_refusals: list[dict[str, str]] = []
        read_refusals: list[dict[str, str]] = []
        for source in units:
            try:
                original = _read_observation_bytes(source)
                preflight_source_digests[source] = hashlib.sha256(original).hexdigest()
                refusal = _observation_context_refusal(original)
            except (OSError, UnicodeError, ValueError) as exc:
                read_refusals.append({"source": str(source), "reason": str(exc)[:240]})
                continue
            if refusal is not None:
                context_refusals.append({"source": str(source), "reason": refusal})
        if context_refusals or read_refusals:
            preflight_failures = context_refusals + read_refusals
            coverage = _coverage()
            coverage["observationCoverage"]["preflightRejectedUnits"] = len(preflight_failures)
            coverage["observationCoverage"]["countSemantics"] += (
                " Preflight rejections are reported separately and never count as dispatched compiler units."
            )
            return {
                "ok": False,
                "reason": "observation-source-preflight-refused",
                "output": str(output),
                "linkSkipped": True,
                "freshLinkedCandidate": False,
                "sourceContextPreflight": {
                    "status": "refused",
                    "sourcesScanned": len(units),
                    "refusedCount": len(preflight_failures),
                    "compilerInvocations": 0,
                    "refusals": preflight_failures[:100],
                    "truncatedRefusalCount": max(0, len(preflight_failures) - 100),
                    "claim": "The current lexical observation-context guard ran before compiler dispatch; it is not a complete C/C++ semantic preflight.",
                },
                "preflightFailures": preflight_failures[:100],
                **coverage,
            }

    language = "c++" if "c++" in map(source_language, units) else "c"
    child_environment = None if compiler_environment is None else dict(compiler_environment)
    effective_environment = os.environ if child_environment is None else child_environment
    cc = compiler or effective_environment.get("AGENT_DECOMPILE_MSVC_COMPILER")
    if not cc:
        cc = (next(filter(None, map(shutil.which, ("c++", "g++", "clang++"))), None)
              if language == "c++" else find_c_compiler())
    if not cc:
        return {"ok": False, "reason": f"no {language} compiler on PATH", "output": str(output), **_coverage()}
    work = Path(obj_dir) if obj_dir is not None else Path(output).parent / "obj"
    src_root = Path(src_dir).resolve()
    object_names = set()
    for source in units:
        try:
            relative = source.resolve().relative_to(src_root)
        except ValueError:
            relative = Path(source.name)
        object_name = str(relative.with_suffix(".obj")).casefold()
        if object_name in object_names:
            return {"ok": False, "reason": "ambiguous compile-unit object path",
                    "source": str(source), "object": str(work / relative.with_suffix(".obj")),
                    "output": str(output), **_coverage()}
        object_names.add(object_name)
    # The owned adapter's prefix lease spans source/output mutation, every
    # translation unit, and link. Child wrappers duplicate the captured
    # descriptor from this environment rather than opening separate lifetimes.
    from . import compiler_msvc71

    batch_adapter = (unit_observer is not None
                    and Path(cc).resolve() == Path(compiler_msvc71.__file__).resolve())
    lease_descriptor = None

    attempt_lease = None
    prefix_observation = {}
    if Path(cc).resolve() == Path(compiler_msvc71.__file__).resolve():
        from .wineprefix_clearance import wineprefix_clearance

        environment = dict(effective_environment)
        vcroot_value = vcroot or environment.get("AGENT_DECOMPILE_VCROOT")
        if vcroot_value:
            environment["VCROOT"] = str(vcroot_value)
        if wineprefix:
            environment["WINEPREFIX"] = wineprefix
        try:
            configuration = compiler_msvc71._configuration(environment)
            attempt_lease = compiler_msvc71.compiler_prefix_lease(
                configuration["winePrefix"], configuration["environment"])
            child_environment, lease_descriptor = attempt_lease.__enter__()
        except (OSError, ValueError, RuntimeError) as exc:
            return {"ok": False, "reason": "compiler-prefix-lease-refused",
                    "detail": str(exc), "output": str(output), "linkSkipped": True,
                    "freshLinkedCandidate": False, **_coverage()}
        effective_environment = child_environment
        vcroot = configuration["vcRoot"]
        wineprefix = child_environment["WINEPREFIX"]
        prefix_observation = {
            "source": "whole-compile-link-cooperative-prefix-lease-v1",
            "prefix": wineprefix, "cooperatingWritersOnly": True,
            "allWriterClearanceQualified": False,
            "historicalOwnershipResolved": False,
        }
    try:
        if attempt_lease is not None:
            try:
                prefix_observation["beforeDispatch"] = wineprefix_clearance(wineprefix)
            except (OSError, ValueError, RuntimeError) as exc:
                prefix_observation["beforeDispatch"] = {"state": "unknown", "reason": str(exc)}
            if prefix_observation["beforeDispatch"].get("state") != "clear":
                return {"ok": False, "reason": "compiler-prefix-daemon-not-idle",
                        "output": str(output), "linkSkipped": True,
                        "freshLinkedCandidate": False,
                        "compilerPrefixLease": prefix_observation, **_coverage()}
        if entrypoint:
            main_c = work / "_main.c"
            write_entrypoint(main_c)
            generated_entrypoint = _read_observation_bytes(main_c)
            generated_refusal = _observation_context_refusal(generated_entrypoint)
            if generated_refusal is not None:
                return {"ok": False, "reason": "generated-entrypoint-preflight-refused",
                        "detail": generated_refusal, "output": str(output),
                        "linkSkipped": True, "freshLinkedCandidate": False,
                        **_coverage()}
            preflight_source_digests[main_c] = hashlib.sha256(generated_entrypoint).hexdigest()
            units = [main_c, *units]
            generated_entrypoint_units = 1
        script = Path(cc).suffix in {".py", ".sh"} or Path(cc).name.startswith("compile-")
        vcroot_value = vcroot or effective_environment.get("AGENT_DECOMPILE_VCROOT")
        resolved_vcroot = Path(vcroot_value).resolve() if vcroot_value else None
        resolved_wineprefix = wineprefix or effective_environment.get("WINEPREFIX")
        compiler_identity = _compiler_identity(str(cc), vcroot=resolved_vcroot,
                                               wineprefix=resolved_wineprefix, script=script,
                                               cache_input_manifest=(Path(cache_input_manifest)
                                                                     if cache_input_manifest else None),
                                               compiler_environment=child_environment)

        def _one(src: Path, batch_result: dict[str, Any] | None = None) -> tuple[Path, dict[str, Any]]:
            from .compiler_msvc71 import source_language

            try:
                rel = src.resolve().relative_to(src_root)
            except ValueError:
                rel = Path(src.name)
            obj = work / rel.with_suffix(".obj")
            if unit_observer is not None:
                original = _read_observation_bytes(src)
                expected_digest = preflight_source_digests.get(src)
                if expected_digest is None or hashlib.sha256(original).hexdigest() != expected_digest:
                    return obj, {"ok": False, "source": str(src), "object": str(obj),
                                 "reason": "observation-source-changed-after-preflight",
                                 "stderr": "Source bytes differ from the preflight snapshot; no compiler invocation was made."}
                context_refusal = _observation_context_refusal(original)
                if context_refusal is not None:
                    return obj, {"ok": False, "source": str(src), "object": str(obj),
                                 "reason": context_refusal,
                                 "stderr": context_refusal + ": captured include/path context is not implemented; ordinary builds are unaffected."}
                frontend = source_language(src)
                preamble = (preamble_for_source(original.decode("utf-8", errors="strict"))
                            if script and frontend == "c" else "")
                normalized = preamble.encode("utf-8") + original
                if len(normalized) > 64 * 1024 * 1024:
                    raise ValueError("observation-normalized-input-capacity")
                work.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryDirectory(prefix=".agentdecompile-observation-", dir=work) as directory:
                    captured_source = Path(directory) / ("input" + src.suffix.lower())
                    captured_source.write_bytes(original)
                    basis = _compile_basis(captured_source, preamble, compiler_identity)
                    captured_source.write_bytes(normalized)
                    captured_source.chmod(0o400)
                    reused = object_is_current(obj, basis) and batch_result is None
                    if batch_result is not None:
                        result = dict(batch_result)
                    elif reused:
                        result = {"ok": True, "skipped": True, "toolchain": "cached"}
                    else:
                        _object_basis_path(obj).unlink(missing_ok=True)
                        timeout = 300 if len(original) > 80_000 else 90
                        if script:
                            result = compile_unit_script(str(cc), captured_source, obj, name=src.stem,
                                                         timeout=timeout, preamble="", compiler_environment=child_environment)
                        else:
                            result = compile_unit(str(cc), captured_source, obj, timeout=timeout,
                                                  compiler_environment=child_environment)
                    helper_result = dict(result)
                    result.update({"source": str(src), "object": str(obj)})
                    if result.get("ok"):
                        if _read_observation_bytes(captured_source) != normalized:
                            raise ValueError("observation-compiler-input-changed")
                        emitted = _read_observation_bytes(obj)
                        if not emitted:
                            raise ValueError("observation-empty-object")
                        if not reused and basis is not None:
                            _write_object_basis(obj, basis)
                        result["_unitObservation"] = {
                            "sourcePath": str(src.resolve()), "sourceBytes": original,
                            "objectPath": str(obj.resolve()), "objectBytes": emitted,
                            "sourceSha256": hashlib.sha256(original).hexdigest(),
                            "normalizedInputSha256": hashlib.sha256(normalized).hexdigest(),
                            "normalizedInputBytes": normalized,
                            "objectSha256": hashlib.sha256(emitted).hexdigest(),
                            "sourceLanguage": frontend, "freshCompilation": not reused,
                            "reusedObject": reused, "generatedEntrypoint": bool(entrypoint and src == main_c),
                            "compilerIdentity": compiler_identity,
                            "invocation": {"compiler": str(cc), "script": script,
                                           "frontend": frontend, "compilerExecuted": not reused,
                                           "compilerOptions": effective_environment.get("CL_OPT"),
                                           "compilerRunAttestation": result.get("compilerRunAttestation",
                                                _compiler_run_attestation(
                                                    None, sources=[captured_source], outputs=[obj])),
                                           "compilerLaunchState": result.get("compilerLaunchState",
                                                                              "not-invoked-reused-object" if reused else "unknown"),
                                           "stagedInputPath": str(captured_source),
                                           "adapterLabel": src.stem, "helperResult": helper_result,
                                           "sourcePathChanged": True, "includeClosureCaptured": False,
                                           "sourceContextPolicy": "Conservative lexical guard for self-contained staged units; not complete preprocessing/toolchain closure.",
                                           "claim": "Owned helper observation; not complete toolchain closure."},
                        }
                        from . import compiler_msvc71, source_contribution
                        if script and Path(cc).resolve() == Path(compiler_msvc71.__file__).resolve():
                            event = result["_unitObservation"]
                            event["nativeCompilationObservation"] = source_contribution._issue_native_compile_observation(
                                compile_and_link_tree, event)
                    return obj, result
            source_text = src.read_text(errors="replace") if script and source_language(src) == "c" else ""
            preamble = preamble_for_source(source_text) if script and source_language(src) == "c" else ""
            basis = _compile_basis(src, preamble, compiler_identity)
            if object_is_current(obj, basis):
                return obj, {
                    "ok": True,
                    "source": str(src),
                    "object": str(obj),
                    "skipped": True,
                    "toolchain": "cached",
                }
            try:
                _object_basis_path(obj).unlink(missing_ok=True)
            except OSError as exc:
                return obj, {"ok": False, "source": str(src), "object": str(obj),
                             "returncode": None, "stderr": f"cannot invalidate stale object basis: {exc}"}
            timeout = 90
            try:
                size = src.stat().st_size
            except OSError:
                size = 0
            if size > 80_000:
                timeout = 300
            if script:
                result = compile_unit_script(str(cc), src, obj, name=src.stem, timeout=timeout,
                                             preamble=preamble, compiler_environment=child_environment)
            else:
                result = compile_unit(str(cc), src, obj, timeout=timeout,
                                      compiler_environment=child_environment)
            if result.get("ok") and basis is not None:
                _write_object_basis(obj, basis)
            return obj, result

        def _batch_observed(sources: list[Path]) -> list[tuple[Path, dict[str, Any]]]:
            """Compile a bounded group through the owned adapter's single cl.exe launch.

            Failed aggregate invocations are bisected in source order. Successful
            prefixes are retained; partial objects from failed invocations stay
            private. The first failing TU terminates the group, and unattempted
            suffix members are omitted so the caller can account for them.
            """
            from .compiler_msvc71 import MAX_BATCH_TRANSLATION_UNITS, MIN_BATCH_TRANSLATION_UNITS

            if not MIN_BATCH_TRANSLATION_UNITS <= len(sources) <= MAX_BATCH_TRANSLATION_UNITS:
                return [_one(source) for source in sources]

            by_source: dict[Path, dict[str, Any]] = {}
            for source in sources:
                try:
                    rel = source.resolve().relative_to(src_root)
                except ValueError:
                    rel = Path(source.name)
                obj = work / rel.with_suffix(".obj")
                try:
                    original = _read_observation_bytes(source)
                    expected = preflight_source_digests.get(source)
                    if expected is None or hashlib.sha256(original).hexdigest() != expected:
                        by_source[source] = {"kind": "preparation-failure", "object": obj}
                        continue
                    refusal = _observation_context_refusal(original)
                    if refusal is not None:
                        by_source[source] = {"kind": "preparation-failure", "object": obj}
                        continue
                    frontend = source_language(source)
                    preamble = (preamble_for_source(original.decode("utf-8", errors="strict"))
                                if frontend == "c" else "")
                    basis = _compile_basis(source, preamble, compiler_identity)
                except (OSError, UnicodeError, ValueError):
                    by_source[source] = {"kind": "preparation-failure", "object": obj}
                    continue
                if object_is_current(obj, basis):
                    by_source[source] = {"kind": "cached", "object": obj}
                    continue
                by_source[source] = {"kind": "uncached", "source": source, "object": obj,
                    "original": original, "frontend": frontend, "preamble": preamble,
                    "normalized": preamble.encode("utf-8") + original, "basis": basis}

            def _history_refs(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
                return [{"groupId": attempt["groupId"], "translationUnits": attempt["translationUnits"],
                         "reason": attempt["reason"],
                         "attestationSha256": attempt["attestation"].get("attestationSha256")}
                        for attempt in history]

            def _run_segment(items: list[dict[str, Any]],
                             history: list[dict[str, Any]]) -> list[tuple[Path, dict[str, Any]]]:
                if len(items) < MIN_BATCH_TRANSLATION_UNITS:
                    source = items[0]["source"]
                    try:
                        obj, result = _one(source)
                    except Exception as exc:
                        obj, result = items[0]["object"], {"ok": False, "source": str(source),
                            "object": str(items[0]["object"]), "reason": "worker-exception",
                            "stderr": f"worker exception: {exc.__class__.__name__}"}
                    if history:
                        result["batchFallback"] = {"attempts": _history_refs(history),
                            "failedAggregateAttestations": [entry["attestation"] for entry in history]}
                    return [(obj, result)]

                group_id = uuid.uuid4().hex
                staged_sources: list[Path] = []
                staged_objects: list[Path] = []
                names: list[str] = []
                captured: str | bytes = ""
                launch_state = "not-started"
                returncode: int | None = None
                attestation: dict[str, Any] = _compiler_run_attestation(None)
                invocation_seconds = 0.0
                try:
                    with tempfile.TemporaryDirectory(prefix=".agentdecompile-observation-batch-", dir=work) as directory:
                        root = Path(directory)
                        source_dir, object_dir = root / "sources", root / "objects"
                        source_dir.mkdir()
                        object_dir.mkdir()
                        for index, item in enumerate(items):
                            name = f"unit_{index:02d}{item['source'].suffix.lower()}"
                            staged_source = source_dir / name
                            staged_source.write_bytes(item["normalized"])
                            staged_sources.append(staged_source)
                            staged_objects.append(object_dir / (Path(name).stem + ".obj"))
                            names.append(name)
                        # The adapter now spends one process startup for the
                        # group, but cl.exe still compiles every TU. Budget a
                        # generous 30 seconds per ordinary TU, 300 seconds for
                        # each large TU, plus 60 seconds startup/variance; cap
                        # the bounded group at 30 minutes. This avoids applying
                        # the old 90-second single-TU limit to a 24-unit batch.
                        timeout = min(1_800, 60 + sum(
                            300 if len(item["original"]) > 80_000 else 30 for item in items))
                        compile_started = time.monotonic()
                        proc = subprocess.run(
                            [sys.executable, str(cc), "--batch", str(source_dir), str(object_dir), *names],
                            capture_output=True, text=True, timeout=timeout, check=False,
                            env=child_environment,
                            pass_fds=() if lease_descriptor is None else (lease_descriptor,),
                        )
                        invocation_seconds = round(time.monotonic() - compile_started, 3)
                        captured = proc.stderr or proc.stdout or ""
                        returncode = proc.returncode
                        launch_state = "process-returned"
                        attestation = _compiler_run_attestation(proc.stderr, sources=staged_sources,
                            outputs=staged_objects, process_returncode=returncode)
                        successful = (returncode == 0 and all(path.is_file() and path.stat().st_size > 0
                                                              for path in staged_objects))
                        if successful:
                            published: list[Path] = []
                            try:
                                for item, staged_obj in zip(items, staged_objects, strict=True):
                                    obj = item["object"]
                                    obj.parent.mkdir(parents=True, exist_ok=True)
                                    _object_basis_path(obj).unlink(missing_ok=True)
                                    staged_publish = obj.with_name(f".{obj.name}.{group_id}.tmp")
                                    try:
                                        shutil.copyfile(staged_obj, staged_publish)
                                        os.replace(staged_publish, obj)
                                        published.append(obj)
                                    finally:
                                        staged_publish.unlink(missing_ok=True)
                                for item in items:
                                    if item["basis"] is not None:
                                        _write_object_basis(item["object"], item["basis"])
                            except OSError as exc:
                                for obj in published:
                                    obj.unlink(missing_ok=True)
                                    _object_basis_path(obj).unlink(missing_ok=True)
                                captured = f"batch object publication failed ({exc.__class__.__name__})"
                                launch_state = "publication-failed"
                                successful = False
                            if successful:
                                results = []
                                for index, (item, staged_source, staged_obj) in enumerate(
                                        zip(items, staged_sources, staged_objects, strict=True)):
                                    shared = (attestation if index == 0 else {
                                        "status": "shared-group-reference",
                                        "attestationSha256": attestation.get("attestationSha256"),
                                        "groupId": group_id, "ownerSourceIndex": 0,
                                        "sourceIndex": index, "diagnosticOnly": True,
                                        "originAuthenticated": False, "complete": False})
                                    batch_result = {"ok": True, "returncode": returncode,
                                        "stderr": _diagnostic_tail(captured),
                                        "compilerLaunchState": launch_state,
                                        "toolchain": "python-script-batch",
                                        "compilerRunAttestation": shared,
                                        "compilerRunBinding": {"scope": "shared-batch", "groupId": group_id,
                                            "sourceIndex": index, "outputIndex": index,
                                            "sourceName": staged_source.name, "outputName": staged_obj.name,
                                            "translationUnits": len(items), "diagnosticOnly": True,
                                            "launchState": launch_state,
                                            "independentPerFunctionInvocation": False},
                                        "batchCompile": {"groupId": group_id,
                                            "translationUnits": len(items),
                                            **({"invocationSeconds": invocation_seconds} if index == 0 else {}),
                                            "timingScope": "shared invocation; deduplicate by groupId, do not sum per source"}}
                                    if history:
                                        batch_result["batchFallback"] = {
                                            "attempts": _history_refs(history),
                                            "failedAggregateAttestations": [entry["attestation"]
                                                                             for entry in history]}
                                    try:
                                        results.append(_one(item["source"], batch_result))
                                    except Exception as exc:
                                        results.append((item["object"], {**batch_result, "ok": False,
                                            "reason": "unit-observation-preparation-failed",
                                            "source": str(item["source"]), "object": str(item["object"]),
                                            "stderr": f"worker exception: {exc.__class__.__name__}"}))
                                return results
                    if launch_state != "publication-failed":
                        successful = False
                except subprocess.TimeoutExpired as exc:
                    invocation_seconds = round(time.monotonic() - compile_started, 3)
                    captured = exc.stderr or exc.output or ""
                    launch_state = "timeout-observed-process-started"
                    attestation = _compiler_run_attestation(captured, sources=staged_sources,
                                                            outputs=staged_objects)
                except OSError as exc:
                    invocation_seconds = round(time.monotonic() - compile_started, 3) if "compile_started" in locals() else 0.0
                    captured = f"compiler launch failed ({exc.__class__.__name__})"
                    launch_state = "not-started"
                    attestation = _compiler_run_attestation(None, sources=staged_sources,
                                                            outputs=staged_objects)

                reason = ("batch-object-publication-failed" if launch_state == "publication-failed"
                          else "batch-compile-failed-unattributed")
                attempt = {"groupId": group_id, "translationUnits": len(items),
                    "reason": reason, "returncode": returncode,
                    "invocationSeconds": invocation_seconds, "attestation": attestation}
                next_history = [*history, attempt]
                if launch_state == "not-started" or launch_state == "publication-failed":
                    source = items[0]["source"]
                    return [(items[0]["object"], {"ok": False, "source": str(source),
                        "object": str(items[0]["object"]), "returncode": returncode,
                        "reason": reason, "stderr": _diagnostic_tail(captured),
                        "compilerLaunchState": launch_state, "compilerRunAttestation": attestation,
                        "batchFallback": {"attempts": _history_refs(next_history),
                            "failedAggregateAttestations": [entry["attestation"] for entry in next_history]}})]
                if len(items) == MIN_BATCH_TRANSLATION_UNITS:
                    results = []
                    for item in items:
                        source = item["source"]
                        try:
                            result = _one(source)
                        except Exception as exc:
                            result = (item["object"], {"ok": False, "source": str(source),
                                "object": str(item["object"]), "reason": "worker-exception",
                                "stderr": f"worker exception: {exc.__class__.__name__}"})
                        obj, row = result
                        row["batchFallback"] = {"attempts": _history_refs(next_history),
                            "failedAggregateAttestations": [entry["attestation"] for entry in next_history]}
                        results.append((obj, row))
                        if not row.get("ok"):
                            return results
                    return results
                left_size = len(items) // 2
                left = _run_segment(items[:left_size], next_history)
                if len(left) < left_size or any(not result.get("ok") for _, result in left):
                    return left
                right = _run_segment(items[left_size:], next_history)
                return [*left, *right]

            output: list[tuple[Path, dict[str, Any]]] = []
            pending: list[dict[str, Any]] = []
            for source in sources:
                entry = by_source[source]
                if entry["kind"] == "uncached":
                    pending.append(entry)
                    continue
                if pending:
                    results = _run_segment(pending, []) if len(pending) >= 2 else [_one(pending[0]["source"])]
                    output.extend(results)
                    if len(results) < len(pending) or any(not result.get("ok") for _, result in results):
                        return output
                    pending.clear()
                if entry["kind"] == "cached":
                    try:
                        cached_result = _one(source)
                    except Exception as exc:
                        cached_result = (entry["object"], {"ok": False, "source": str(source),
                            "object": str(entry["object"]), "reason": "cached-observation-failed",
                            "stderr": f"worker exception: {exc.__class__.__name__}"})
                    output.append(cached_result)
                else:
                    try:
                        result = _one(source)
                    except Exception as exc:
                        result = (entry.get("object", work / (source.stem + ".obj")), {
                            "ok": False, "source": str(source), "reason": "worker-exception",
                            "stderr": f"worker exception: {exc.__class__.__name__}"})
                    output.append(result)
                    if not result[1].get("ok"):
                        return output
            if pending:
                results = _run_segment(pending, []) if len(pending) >= 2 else [_one(pending[0]["source"])]
                output.extend(results)
            return output

        skipped = 0
        done = 0
        halted: dict[str, Any] | None = None
        in_flight = {}
        dispatch_width = 1 if batch_adapter else max(1, workers)
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            while next_unit < len(units) or in_flight:
                while (halted is None and next_unit < len(units)
                       and len(in_flight) < dispatch_width):
                    if batch_adapter:
                        from .compiler_msvc71 import MAX_BATCH_TRANSLATION_UNITS
                        group = units[next_unit:next_unit + MAX_BATCH_TRANSLATION_UNITS]
                        future = pool.submit(_batch_observed, group) if len(group) >= 2 else None
                        if future is None:
                            future = pool.submit(lambda item=group[0]: [_one(item)])
                        in_flight[future] = group
                        next_unit += len(group)
                    else:
                        source = units[next_unit]
                        in_flight[pool.submit(_one, source)] = [source]
                        next_unit += 1
                if not in_flight:
                    break
                completed, _ = wait(in_flight, return_when=FIRST_COMPLETED)
                for future in completed:
                    group = in_flight.pop(future)
                    try:
                        results = future.result()
                    except Exception as exc:
                        results = [(None, {"ok": False, "source": str(group[0]),
                                           "stderr": f"worker exception: {exc.__class__.__name__}"})]
                    if batch_adapter and len(results) < len(group):
                        # `_batch_observed` returns a contiguous, source-ordered
                        # prefix ending at the first failing TU. Put the unused
                        # suffix back into coverage as genuinely not attempted.
                        next_unit -= len(group) - len(results)
                    for obj, result in results:
                        source = Path(result.get("source", str(group[0])))
                        done += 1
                        observation = result.pop("_unitObservation", None)
                        if observation is not None:
                            try:
                                observed_digest = observation["objectSha256"]
                                unit_observer(observation)
                                observed_objects[obj] = observed_digest
                            except Exception as exc:
                                result = {"ok": False, "source": str(source),
                                          "stderr": f"unit observation refused: {exc.__class__.__name__}: {str(exc)[:300]}",
                                          "compilerRunAttestation": result.get("compilerRunAttestation",
                                              _compiler_run_attestation(None, sources=[source], outputs=[obj]))}
                        if result.get("skipped"):
                            skipped += 1
                        if result.get("ok"):
                            objects.append(obj)
                        else:
                            failure = {"source": result.get("source", str(source)),
                                       "stderr": str(result.get("stderr", ""))[:400],
                                       "compilerRunAttestation": result.get("compilerRunAttestation",
                                           _compiler_run_attestation(None, sources=[source], outputs=[obj])),
                                       "compilerLaunchState": result.get("compilerLaunchState", "unknown"),
                                       "reason": result.get("reason", "compile-or-observation-failed"),
                                       **({"batchCompile": result["batchCompile"]}
                                          if isinstance(result.get("batchCompile"), dict) else {})}
                            failures.append(failure)
                            if halted is None:
                                halted = {"reason": "first-compile-failure", **failure}
                                print(f"compile-link halted on first failure in {failure['source']}; "
                                      "bounded in-flight results will be retained", flush=True)
                if done % 100 == 0 or done == len(units):
                    print(
                        f"compile-link {done}/{len(units)}  "
                        f"obj={len(objects)} skip={skipped} fail={len(failures)}",
                        flush=True,
                    )

        if halted is not None:
            not_attempted = len(units) - next_unit
            print(f"compile-link stopped: {done}/{len(units)} completed; "
                  f"{not_attempted} not dispatched; link skipped", flush=True)
            return {
                **({"compilerPrefixLease": prefix_observation} if prefix_observation else {}),
                **_coverage(),
                "ok": False,
                "compiler": cc,
                "compilerIdentity": compiler_identity,
                "objectCache": ("declared-complete-input-basis; object-digest-verified"
                                if compiler_identity is not None else "disabled: complete cache input manifest unavailable"),
                "units": len(units),
                "objects": len(objects),
                "skipped": skipped,
                "linkSkipped": True,
                "failed": len(failures),
                "failures": failures[:20],
                "halted": halted,
                "notAttempted": not_attempted,
                "link": {"ok": False, "skipped": True, "reason": "compile failed before link"},
                "claimBoundary": (
                    "A linked image proves the generated project builds. It does not "
                    "prove byte-accuracy against a shipped binary."
                ),
            }

        objects.sort()
        if unit_observer is not None:
            try:
                for obj in objects:
                    if hashlib.sha256(_read_observation_bytes(obj)).hexdigest() != observed_objects.get(obj):
                        raise ValueError("observed-object-changed-before-link")
            except (OSError, ValueError) as exc:
                return {**({"compilerPrefixLease": prefix_observation} if prefix_observation else {}),
                        "ok": False, "reason": "same-build-observation-refused", "detail": str(exc)[:400],
                        "objects": len(objects), "linkSkipped": True,
                        "link": {"ok": False, "skipped": True, "reason": "observed object changed"}, **_coverage()}
        vc = resolved_vcroot or Path("")
        prefix = resolved_wineprefix or ""
        out = Path(output)
        if script and vc.is_dir() and prefix:
            linked = link_msvc(objects, out, vcroot=vc, wineprefix=prefix,
                               link_observer=link_observer, compiler_environment=child_environment)
        else:
            linked = link_executable(str(cc), objects, out, compiler_environment=child_environment)
        if unit_observer is not None:
            try:
                for obj in objects:
                    if hashlib.sha256(_read_observation_bytes(obj)).hexdigest() != observed_objects.get(obj):
                        raise ValueError("observed-object-changed-after-link")
            except (OSError, ValueError) as exc:
                linked = {**linked, "ok": False, "freshLinkedCandidate": False,
                          "reason": linked.get("reason", "same-build-observation-refused"),
                          "objectObservationRefusal": {"reason": "same-build-observation-refused",
                                                       "detail": str(exc)[:400]}}
        return {
            **({"compilerPrefixLease": prefix_observation} if prefix_observation else {}),
            **_coverage(),
            "ok": bool(linked.get("ok")),
            "compiler": cc,
            "compilerIdentity": compiler_identity,
            "objectCache": ("declared-complete-input-basis; object-digest-verified"
                            if compiler_identity is not None else "disabled: complete cache input manifest unavailable"),
            "units": len(units),
            "objects": len(objects),
            "skipped": skipped,
            "linkSkipped": bool(linked.get("skipped")),
            "failed": len(failures),
            "failures": failures[:20],
            "link": linked,
            "claimBoundary": (
                "A linked image proves the generated project builds. It does not "
                "prove byte-accuracy against a shipped binary."
            ),
        }

    finally:
        if attempt_lease is not None:
            try:
                # One bounded observation under the same lease. A clear Wine
                # daemon observation does not qualify unrelated writers.
                try:
                    completion = wineprefix_clearance(wineprefix)
                except (OSError, ValueError, RuntimeError) as exc:
                    completion = {"state": "unknown", "reason": str(exc)}
                prefix_observation["completion"] = completion
                if completion.get("state") != "clear":
                    prefix_observation["ownershipResolved"] = False
            finally:
                attempt_lease.__exit__(None, None, None)

def link_executable(
    compiler: str,
    objects: list[Path],
    output: Path,
    *,
    timeout: int = 60,
    compiler_environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    output = Path(output)
    if not objects:
        link_stamp_path(output).unlink(missing_ok=True)
        return {"ok": False, "reason": "no object files", "output": str(output)}
    environment = None if compiler_environment is None else dict(compiler_environment)
    if shutil.which(compiler, path=None if environment is None else environment.get("PATH")) is None:
        link_stamp_path(output).unlink(missing_ok=True)
        return {"ok": False, "reason": "link driver unavailable", "output": str(output),
                "freshLinkedCandidate": False, "previousOutputPreserved": output.is_file()}
    result = _perform_link(objects, output,
                           lambda candidate: [compiler, *[str(path) for path in objects], "-o", str(candidate)],
                           timeout=timeout, flags=(), environment=environment)
    return {
        **result,
        "output": str(output),
        "objectCount": len(objects),
        "linkFlags": [],
        "claimBoundary": (
            "A linked image proves the generated project builds. It does not "
            "prove byte-accuracy against a shipped binary."
        ),
    }


def compile_source_contribution(**kwargs):
    """Supported exact-placement observation seam, separate from generic linking.

    This invokes the shared owned native-clang adapter. Generic compiler wrappers,
    cached objects and successful link results do not become contribution evidence.
    """
    from .source_contribution import compile_observation
    return compile_observation(**kwargs)
