"""Qualified catalog-only native verifier. Direct CLI callers retain their API.

This is a local session/owned-output contract, not a hostile-filesystem sandbox.
Compiler installation and serving Python modules must remain administrator-owned
and stable during an attempt. No Wine, wrappers, custom flags or detached writers
are qualified. JSON parameters never enroll a new compiler or resource tree.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile

ACTION = "recover.verify-package"
PROFILE = "native-clang-package-owned-output-v1"
COMPILER = Path("/usr/bin/clang-22")
RESOURCE = Path("/usr/lib/clang/22")
# Fedora clang 22.1.8-4.fc44: full relative-name/size/content manifest, including
# headers and runtime libraries, not only the driver ELF dependency closure.
RESOURCE_SHA256 = "6036e8b23653482eeea26c2eab7b8be790bb8c02136283a612801d417f4f5ecb"
TARGETS = {"i686-pc-windows-msvc", "x86_64-pc-windows-msvc"}
_BOOTSTRAP = ("import sys;sys.dont_write_bytecode=True;"
              "sys.path.insert(0,sys.argv.pop(1));"
              "from agentdecompile_recovery.native_verify_contract import child_main;"
              "child_main(sys.argv[1])")


def clean_environment(scratch: Path | None = None) -> dict[str, str]:
    env = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C",
           "LLVM_DISABLE_SYMBOLIZATION": "1"}
    if scratch is not None:
        env.update({key: str(scratch) for key in
                    ("HOME", "TMPDIR", "TMP", "TEMP", "XDG_CACHE_HOME")})
    return env


def _absolute(value, root: Path) -> Path:
    # Match the existing verifier: subprocess argv has literal ~, not a shell.
    path = Path(value)
    return (path if path.is_absolute() else root / path).resolve()


def freeze_parameters(params: dict, root: Path) -> dict:
    result = freeze_paths(params, root)
    selected = result.get("clang") or "clang"
    resolved = shutil.which(str(selected), path="/usr/bin:/bin")
    if not resolved or Path(resolved).resolve() != COMPILER.resolve():
        raise ValueError("unsupported catalog native verification compiler wrapper or executable")
    result["clang"] = str(COMPILER)
    _options(result)
    return result


def freeze_paths(params: dict, root: Path) -> dict:
    """Derive claims even for historical unsupported profiles; never qualify them."""
    from .package_verify import resolve_manifest_path
    result = dict(params)
    if not root.is_absolute() or not result.get("package"):
        raise ValueError("native verification requires original execution root and package")
    package = resolve_manifest_path(_absolute(result["package"], root)).resolve()
    result["package"] = str(package)
    result["out-dir"] = str(_absolute(result.get("out-dir") or package.parent / "verification", root))
    return result


def _options(params: dict) -> dict:
    compiler = params.get("compiler") or "clang"
    target = params.get("clang-target", "i686-pc-windows-msvc")
    if (compiler != "clang" or params.get("clang") != str(COMPILER)
            or target not in TARGETS or params.get("clang-arg") or params.get("code-compare")
            or params.get("msvc-root") or params.get("wineprefix") or params.get("argv")):
        raise ValueError("unsupported catalog native verification profile (custom flags, wrappers, Wine and code comparison are not qualified)")
    timeout = params.get("timeout", 30)
    if isinstance(timeout, bool) or int(timeout) <= 0:
        raise ValueError("native verification timeout must be positive")
    return {"package": str(params["package"]), "out_dir": str(params["out-dir"]),
            "clang_target": target, "timeout": int(timeout),
            "object_compile": params.get("no-object") not in (True, "true", "1", "yes", "on")}


def guarded_command(params: dict) -> list[str]:
    options = _options(params)
    for name in ("package", "out_dir"):
        if not Path(options[name]).is_absolute() or str(Path(options[name]).resolve()) != options[name]:
            raise ValueError("native verifier paths must be frozen before dispatch")
    # Use the root of the actually imported implementation, including installed
    # products. -I -S prevents PYTHONPATH, user site and .pth/sitecustomize startup.
    module_root = str(Path(__file__).resolve().parent.parent)
    payload = {"profile": PROFILE, "implementation": implementation_identity(), **options}
    return [sys.executable, "-I", "-S", "-c", _BOOTSTRAP, module_root,
            json.dumps(payload, sort_keys=True, separators=(",", ":"))]


def command_matches(argv, params: dict) -> bool:
    try:
        return argv == guarded_command(params)
    except (OSError, ValueError, TypeError, KeyError):
        return False


def implementation_identity() -> dict:
    root = Path(__file__).resolve().parent
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in
            ("native_verify_contract.py", "package_verify.py", "corpus/source_contribution.py")}


def _check_toolchain() -> None:
    from .corpus.source_contribution import _toolchain
    _toolchain(COMPILER)
    rows = []
    paths = []
    for path in RESOURCE.rglob("*"):
        paths.append(path)
        if len(paths) > 512:
            raise ValueError("unapproved oversized clang resource tree")
    total_size = 0
    for path in sorted(paths):
        if path.is_symlink():
            raise ValueError("unsupported symlink in clang resource tree")
        if path.is_file():
            size = path.stat().st_size
            total_size += size
            if total_size > 58_349_963:
                raise ValueError("unapproved oversized clang resource tree")
            rows.append({"path": str(path.relative_to(RESOURCE)), "size": size,
                         "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        elif not path.is_dir():
            raise ValueError("unsupported clang resource entry")
    digest = hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if digest != RESOURCE_SHA256:
        raise ValueError("unapproved clang driver resource tree")


class NativePolicy:
    def __init__(self, output: Path):
        self.output = output
        self.inputs: set[Path] = set()
        self.scratch: Path | None = None

    def _output_file(self, path: Path) -> None:
        if path.parent != self.output or path.resolve() != path or path in self.inputs:
            raise ValueError("native verifier output aliases an input or leaves owned tree")
        if path.exists() or path.is_symlink():
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError("native verifier output must be a private regular file")

    def validate_source(self, source: Path, metadata: Path, meta: dict,
                        effective_args: list[str], language: str) -> None:
        if effective_args or language not in {"c", "c++"}:
            raise ValueError("unsupported effective native compiler arguments or language")
        hints = meta.get("compilerProfileHints")
        if hints and (not isinstance(hints, dict) or hints.get("args")
                      or hints.get("compiler") not in (None, "", "clang")):
            raise ValueError("unsupported metadata compiler profile")
        selected_inputs = [source, metadata]
        target_slice = meta.get("targetSlice")
        if isinstance(target_slice, dict):
            from .package_verify import resolve_target_slice_path
            path = resolve_target_slice_path({**target_slice, "metadataPath": str(metadata)})
            if path is not None:
                selected_inputs.append(path)
        for path in selected_inputs:
            resolved = path.resolve()
            if resolved == self.output or self.output in resolved.parents:
                raise ValueError("native output tree contains selected package input")
            self.inputs.add(resolved)
        for suffix in (".verify.c", ".verify.cpp", ".o", ".syntax.stdout.txt",
                       ".syntax.stderr.txt", ".object.stdout.txt", ".object.stderr.txt"):
            self._output_file(self.output / (source.stem + suffix))

    def prepare(self, manifest_path: Path, manifest: dict) -> None:
        from .package_verify import resolve_package_path, read_json, source_language_for, effective_compiler_args
        if self.output.resolve() != self.output:
            raise ValueError("native output tree changed since admission")
        self.inputs.add(manifest_path.resolve())
        if manifest_path.resolve() == self.output or self.output in manifest_path.resolve().parents:
            raise ValueError("native output tree contains manifest")
        self._output_file(self.output / "verification.json")
        stems = set()
        for fn in manifest.get("functions", []):
            source = resolve_package_path(manifest_path.parent, fn.get("source"))
            metadata = resolve_package_path(manifest_path.parent, fn.get("metadata"))
            meta = read_json(metadata)
            language = source_language_for(source, meta)
            self.validate_source(source, metadata, meta,
                                 effective_compiler_args([], "clang", language, meta), language)
            if source.stem in stems:
                raise ValueError("duplicate native verifier output stem")
            stems.add(source.stem)
        # All metadata and selected-input/output checks precede any output write.
        _check_toolchain()
        self.output.mkdir(parents=True, exist_ok=True)
        self.scratch = Path(tempfile.mkdtemp(prefix=".native-verify-", dir=self.output))

    def command(self, source: Path, target: str, language: str) -> list[str]:
        if target not in TARGETS or language not in {"c", "c++"}:
            raise ValueError("unsupported native compiler semantics")
        return [str(COMPILER), "--no-default-config", "-resource-dir", str(RESOURCE),
                "-fno-crash-diagnostics", "-fno-modules", "-fno-implicit-modules",
                "-fno-implicit-module-maps", "-fintegrated-as", "-nostdinc", "-isystem", str(RESOURCE / "include"),
                "-x", language, "-std=gnu++98" if language == "c++" else "-std=gnu89",
                "-Wno-everything", "-fno-builtin", "-target", target, str(source)]

    def run(self, command: list[str], timeout: int):
        if self.scratch is None:
            raise ValueError("native verifier policy was not prepared")
        return subprocess.run(command, text=True, capture_output=True, check=False,
                              timeout=timeout, cwd=self.output, env=clean_environment(self.scratch))


def child_main(raw: str) -> None:
    import resource
    # A compiler crash must not cause an OS core writer outside the claim.
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    from .package_verify import verify_recovered_source_package
    options = json.loads(raw)
    if options.pop("profile", None) != PROFILE:
        raise ValueError("unknown native verifier profile")
    if options.pop("implementation", None) != implementation_identity():
        raise ValueError("native verifier implementation changed after admission")
    # Revalidate typed/allowed options in the actual owned child. Neither a
    # passed digest nor a parent inspection is authority for effective flags.
    normalized = _options({"package": options["package"], "out-dir": options["out_dir"],
                           "clang": str(COMPILER),
                           "clang-target": options["clang_target"], "timeout": options["timeout"],
                           "no-object": not options["object_compile"]})
    if options != normalized:
        raise ValueError("noncanonical native verifier options")
    package, output = Path(options.pop("package")), Path(options.pop("out_dir"))
    if not package.is_absolute() or not output.is_absolute():
        raise ValueError("native verifier requires absolute frozen paths")
    report = verify_recovered_source_package(package, out_dir=output, clang=str(COMPILER),
                                            _native_policy=NativePolicy(output), **options)
    # Diagnostic actual-child observation only. JobStore never consumes this
    # JSON as clearance authority; its default executor/session binding owns that.
    report["nativeExecution"] = {
        "profile": PROFILE, "executable": sys.executable,
        "modules": {name: {"path": str(Path(sys.modules[name].__file__).resolve()),
                           "sha256": hashlib.sha256(Path(sys.modules[name].__file__).read_bytes()).hexdigest()}
                    for name in ("agentdecompile_recovery.native_verify_contract",
                                 "agentdecompile_recovery.package_verify",
                                 "agentdecompile_recovery.corpus.source_contribution")},
        "resourceTreeSha256": RESOURCE_SHA256,
    }
    print(json.dumps(report, sort_keys=True))
    raise SystemExit(0 if report.get("status") in {"syntax-ok", "object-ok"} else 1)
