"""Compile recovered units and link a complete executable.

Priority 1 of the corpus pipeline: one donor project becomes a real linked
image. Object files alone are not a complete executable. Byte-accuracy is a
later, separate stage.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .recovered_c_preamble import PREAMBLE


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
    obj.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [cl, "/nologo", "/c", str(source), f"/Fo{obj}"],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return {
        "ok": proc.returncode == 0 and obj.is_file(),
        "source": str(source),
        "object": str(obj),
        "returncode": proc.returncode,
        "stderr": (proc.stderr or proc.stdout or "")[-2000:],
        "toolchain": "msvc",
    }


def compile_unit(compiler: str, source: Path, obj: Path, *, timeout: int = 60) -> dict[str, Any]:
    obj.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [compiler, "-c", str(source), "-o", str(obj)],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return {
        "ok": proc.returncode == 0 and obj.is_file(),
        "source": str(source),
        "object": str(obj),
        "returncode": proc.returncode,
        "stderr": (proc.stderr or "")[-2000:],
    }


STUB_MARK = "STABS-attributed compilation unit"


def _read_head(path: Path, n: int = 500) -> str:
    with path.open("rb") as handle:
        return handle.read(n).decode("utf-8", errors="replace")


def iter_compile_units(root: Path) -> list[Path]:
    """Source files that are compile units, not STABS index stubs."""
    units: list[Path] = []
    for path in sorted(Path(root).rglob("*.c")):
        if path.name.startswith("_"):
            continue
        head = _read_head(path)
        if STUB_MARK in head and "address: 0x" not in head:
            continue
        units.append(path)
    return units


def object_is_current(source: Path, obj: Path) -> bool:
    """True when a prior object is newer than its source and non-empty."""
    if not obj.is_file():
        return False
    try:
        return obj.stat().st_size > 0 and obj.stat().st_mtime >= source.stat().st_mtime
    except OSError:
        return False


LINK_FLAGS = ("/nologo", "/FORCE", "/OPT:NOREF")


def link_stamp_path(output: Path) -> Path:
    return Path(output).parent / ".link-stamp"


def link_flags_text(flags: tuple[str, ...] | list[str] = LINK_FLAGS) -> str:
    return "\n".join(flags) + "\n"


def stamp_matches(output: Path, flags: tuple[str, ...] | list[str] = LINK_FLAGS) -> bool:
    stamp = link_stamp_path(output)
    try:
        return stamp.is_file() and stamp.read_text(encoding="utf-8") == link_flags_text(flags)
    except OSError:
        return False


def write_link_stamp(output: Path, flags: tuple[str, ...] | list[str] = LINK_FLAGS) -> None:
    path = link_stamp_path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(link_flags_text(flags), encoding="utf-8")


def image_is_current(
    objects: list[Path],
    output: Path,
    *,
    flags: tuple[str, ...] | list[str] = LINK_FLAGS,
) -> bool:
    """True when the linked image is newer than every object and flags match.

    A missing or stale `.link-stamp` forces one relink so a 40 KB main-only
    stub is not kept after `/OPT:NOREF` is added.
    """
    if not objects:
        return False
    try:
        if not output.is_file() or output.stat().st_size <= 0:
            return False
        if not stamp_matches(output, flags):
            return False
        exe_mtime = output.stat().st_mtime
        for obj in objects:
            if obj.stat().st_mtime > exe_mtime:
                return False
        return True
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
    preamble: str = "", env=None,
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
            dir=source.parent,
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
        proc = subprocess.run(
            ["bash", str(script), str(compile_source), str(compile_obj), name or source.stem],
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
            check=False,
        )
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
        "stderr": (proc.stderr or proc.stdout or "")[-2000:],
        "toolchain": "script",
        "stagedInput": staged_source is not None,
    }


def _win_z_path(path: Path) -> str:
    text = str(Path(path).resolve())
    if text.startswith("/"):
        return "Z:" + text.replace("/", "\\")
    return text


def link_msvc(
    objects: list[Path],
    output: Path,
    *,
    vcroot: Path,
    wineprefix: str,
    timeout: int = 3600,
) -> dict[str, Any]:
    """Link COFF objects with VC7 ``link.exe`` via Wine. Not byte-accuracy."""
    if not objects:
        return {"ok": False, "reason": "no object files", "output": str(output)}
    output = Path(output)
    if image_is_current(objects, output):
        return {
            "ok": True,
            "output": str(output),
            "skipped": True,
            "objectCount": len(objects),
            "reason": "image newer than all objects",
            "claimBoundary": (
                "A linked image proves the generated project builds. It does not "
                "prove byte-accuracy against a shipped binary."
            ),
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    link = Path(vcroot) / "bin" / "link.exe"
    if not link.is_file():
        return {"ok": False, "reason": f"no link.exe at {link}", "output": str(output)}
    rsp = output.parent / "objects.rsp"
    rsp.write_text("\n".join(_win_z_path(p) for p in objects) + "\n", encoding="utf-8")
    env = os.environ.copy()
    env["WINEPREFIX"] = wineprefix
    env.pop("WINEARCH", None)
    env.setdefault("WINEDEBUG", "-all")
    libdir = Path(vcroot) / "lib"
    env["LIB"] = _win_z_path(libdir)
    proc = subprocess.run(
        [
            "wine",
            str(link),
            *LINK_FLAGS,
            f"/LIBPATH:{_win_z_path(libdir)}",
            "kernel32.lib",
            "libc.lib",
            f"/OUT:{_win_z_path(output)}",
            f"@{_win_z_path(rsp)}",
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=env,
    )
    ok = proc.returncode == 0 and output.is_file() and output.stat().st_size > 0
    if ok:
        write_link_stamp(output, LINK_FLAGS)
    return {
        "ok": ok,
        "output": str(output),
        "returncode": proc.returncode,
        "stderr": (proc.stderr or proc.stdout or "")[-2000:],
        "objectCount": len(objects),
        "linkFlags": list(LINK_FLAGS),
        "claimBoundary": (
            "A linked image proves the generated project builds. It does not "
            "prove byte-accuracy against a shipped binary."
        ),
    }


def compile_and_link_tree(
    src_dir: Path,
    output: Path,
    *,
    compiler: str | None = None,
    sample: int | None = None,
    obj_dir: Path | None = None,
    workers: int = 2,
    entrypoint: bool = False,
    vcroot: Path | str | None = None,
    wineprefix: str | None = None,
) -> dict[str, Any]:
    """Compile each unit, then link one image. Not a byte-accuracy claim."""
    cc = compiler or os.environ.get("AGENT_DECOMPILE_MSVC_COMPILER") or find_c_compiler()
    if not cc:
        return {"ok": False, "reason": "no C compiler on PATH", "output": str(output)}
    units = iter_compile_units(src_dir)
    if sample is not None:
        units = units[: max(0, sample)]
    work = Path(obj_dir) if obj_dir is not None else Path(output).parent / "obj"
    src_root = Path(src_dir).resolve()
    if entrypoint:
        main_c = work / "_main.c"
        write_entrypoint(main_c)
        units = [main_c, *units]
    script = Path(cc).suffix == ".sh" or Path(cc).name.startswith("compile-")
    # Bind compiler wrappers to the same operator-selected environment as
    # link.exe without changing process-global state across worker threads.
    compile_env = os.environ.copy()
    if wineprefix:
        compile_env["WINEPREFIX"] = str(wineprefix)
    if vcroot:
        compile_env["VCROOT"] = str(vcroot)

    def _one(src: Path) -> tuple[Path, dict[str, Any]]:
        try:
            rel = src.resolve().relative_to(src_root)
        except ValueError:
            rel = Path(src.name)
        obj = work / rel.with_suffix(".obj")
        if object_is_current(src, obj):
            return obj, {
                "ok": True,
                "source": str(src),
                "object": str(obj),
                "skipped": True,
                "toolchain": "cached",
            }
        timeout = 90
        try:
            size = src.stat().st_size
        except OSError:
            size = 0
        if size > 80_000:
            timeout = 300
        if script:
            result = compile_unit_script(str(cc), src, obj, name=src.stem, timeout=timeout,
                                         preamble=PREAMBLE, env=compile_env)
        else:
            result = compile_unit(str(cc), src, obj, timeout=timeout)
        return obj, result

    objects: list[Path] = []
    failures: list[dict[str, Any]] = []
    skipped = 0
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for obj, result in pool.map(_one, units):
            done += 1
            if result.get("skipped"):
                skipped += 1
            if result["ok"]:
                objects.append(obj)
            else:
                failures.append({"source": result.get("source"), "stderr": result["stderr"][:400]})
            if done % 100 == 0 or done == len(units):
                print(
                    f"compile-link {done}/{len(units)}  "
                    f"obj={len(objects)} skip={skipped} fail={len(failures)}",
                    flush=True,
                )

    vc = Path(vcroot or os.environ.get("AGENT_DECOMPILE_VCROOT") or "")
    prefix = wineprefix or os.environ.get("WINEPREFIX") or ""
    out = Path(output)
    if objects and image_is_current(objects, out):
        print(
            f"compile-link skip link: {out} is newer than {len(objects)} objects",
            flush=True,
        )
        linked = {
            "ok": True,
            "output": str(out),
            "skipped": True,
            "objectCount": len(objects),
            "reason": "image newer than all objects",
            "claimBoundary": (
                "A linked image proves the generated project builds. It does not "
                "prove byte-accuracy against a shipped binary."
            ),
        }
    elif script and vc.is_dir() and prefix:
        linked = link_msvc(objects, out, vcroot=vc, wineprefix=prefix)
    else:
        linked = link_executable(str(cc), objects, out)
    return {
        "ok": bool(linked.get("ok")),
        "compiler": cc,
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


def link_executable(
    compiler: str,
    objects: list[Path],
    output: Path,
    *,
    timeout: int = 60,
) -> dict[str, Any]:
    if not objects:
        return {"ok": False, "reason": "no object files", "output": str(output)}
    if image_is_current(objects, Path(output)):
        return {
            "ok": True,
            "output": str(output),
            "skipped": True,
            "objectCount": len(objects),
            "reason": "image newer than all objects",
            "claimBoundary": (
                "A linked image proves the generated project builds. It does not "
                "prove byte-accuracy against a shipped binary."
            ),
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [compiler, *[str(path) for path in objects], "-o", str(output)],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    ok = proc.returncode == 0 and output.is_file() and output.stat().st_size > 0
    if ok:
        write_link_stamp(output, LINK_FLAGS)
    return {
        "ok": ok,
        "output": str(output),
        "returncode": proc.returncode,
        "stderr": (proc.stderr or "")[-2000:],
        "objectCount": len(objects),
        "linkFlags": list(LINK_FLAGS),
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
