"""AgentDecompile-owned VC7.1/Wine adapter with truthful compiler status.

The adapter is versioned with the verifier. The VC toolkit, Wine installation,
and Wine prefix remain external dependencies and are not claimed complete by
this module alone.

Usage: python -m agentdecompile_recovery.corpus.compiler_msvc71
       <source.c> <output.obj> [function-name] [cl flags...]
       python -m agentdecompile_recovery.corpus.compiler_msvc71
       --batch <source-dir> <object-dir> <2-24 source basenames>
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
import stat
import time
from contextlib import contextmanager
from pathlib import Path


DEFAULT_PROJECTS_ROOT = Path(__file__).resolve().parents[4] / "agentdecompile_projects"
DEFAULT_VC_RELATIVE = Path(
    "wine_vc71/drive_c/Program Files/Microsoft Visual C++ Toolkit 2003"
)
DEFAULT_WINE_PREFIX_RELATIVE = Path("wine64_nvme")
MIN_BATCH_TRANSLATION_UNITS = 2
MAX_BATCH_TRANSLATION_UNITS = 24
SOURCE_LANGUAGES = {'.c': 'c', '.cpp': 'c++'}
PREFIX_LEASE_ENV = 'AGENT_DECOMPILE_COMPILER_LEASE_FD'


@contextmanager
def compiler_prefix_lease(prefix: Path, environment: dict[str, str]):
    """Nonblocking cooperative physical-prefix lease, inherited by direct children.

    Closing our descriptor does not unlock a surviving inherited descriptor.
    Wine may close descriptors or use existing daemons: this is not proof of
    daemon lifetime, unmanaged-writer clearance or historical-owner clearance.
    The prefix must be trusted against directory/lock replacement after yield;
    this cooperative lock does not exclude hostile filesystem writers.
    """
    import fcntl

    prefix = Path(prefix).resolve(strict=True)
    directory = prefix / '.agentdecompile-compiler'
    directory.mkdir(mode=0o700, exist_ok=True)
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    descriptor = None
    try:
        lock_fd = os.open('owner.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
                          0o600, dir_fd=directory_fd)
        try:
            expected = os.fstat(lock_fd)
            if not stat.S_ISREG(expected.st_mode) or expected.st_uid != os.getuid() or expected.st_nlink != 1:
                raise ValueError('compiler-prefix-lease-file-invalid')
            inherited = environment.get(PREFIX_LEASE_ENV)
            if inherited is None:
                descriptor, lock_fd = lock_fd, None
            else:
                if not inherited.isdecimal() or len(inherited) > 10:
                    raise ValueError('compiler-prefix-lease-descriptor-invalid')
                descriptor = os.dup(int(inherited))
                actual = os.fstat(descriptor)
                if (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
                    raise ValueError('compiler-prefix-lease-descriptor-mismatch')
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError('compiler-prefix-busy') from exc
            opened_directory = os.fstat(directory_fd)
            current_directory = os.stat(directory, follow_symlinks=False)
            current_lock = os.stat('owner.lock', dir_fd=directory_fd, follow_symlinks=False)
            leased_lock = os.fstat(descriptor)
            if (not stat.S_ISDIR(current_directory.st_mode)
                    or (current_directory.st_dev, current_directory.st_ino)
                    != (opened_directory.st_dev, opened_directory.st_ino)
                    or not stat.S_ISREG(current_lock.st_mode)
                    or (current_lock.st_dev, current_lock.st_ino)
                    != (leased_lock.st_dev, leased_lock.st_ino)):
                raise ValueError('compiler-prefix-lease-path-replaced')
            child_environment = dict(environment)
            child_environment['WINEPREFIX'] = str(prefix)
            child_environment[PREFIX_LEASE_ENV] = str(descriptor)
            yield child_environment, descriptor
        finally:
            if lock_fd is not None:
                os.close(lock_fd)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(directory_fd)


def source_language(path: Path) -> str:
    """The input suffix owns frontend selection for each translation unit."""
    try:
        return SOURCE_LANGUAGES[path.suffix.lower()]
    except KeyError as exc:
        raise ValueError(f'Unsupported source suffix: {path.suffix}') from exc


def source_argument(path: Path) -> str:
    # Per-file switches override global /TC and /TP without guessing EH, ABI
    # or optimization flags. MSVC permits the filename directly after /Tc/Tp.
    return ('/Tc' if source_language(path) == 'c' else '/Tp') + _winpath(path)


def _configuration(environment):
    """Resolve once for both actual compilation and its input observation."""
    effective = dict(environment)
    projects_root = Path(effective.get('AGENT_DECOMPILE_PROJECTS_ROOT',
                                      str(DEFAULT_PROJECTS_ROOT))).resolve()
    vc_root = Path(effective.get('VCROOT', str(projects_root / DEFAULT_VC_RELATIVE))).resolve()
    wine_prefix = Path(effective.get('WINEPREFIX',
                                    str(projects_root / DEFAULT_WINE_PREFIX_RELATIVE))).resolve()
    effective['WINEPREFIX'] = str(wine_prefix)
    effective.pop('WINEARCH', None)
    effective.setdefault('WINEDEBUG', '-all')
    wine = shutil.which('wine', path=effective.get('PATH')) or shutil.which('wine64', path=effective.get('PATH'))
    return {'projectsRoot': projects_root, 'vcRoot': vc_root, 'winePrefix': wine_prefix,
            'wine': wine, 'environment': effective,
            'flags': shlex.split(effective.get('CL_OPT', '/O2 /Gd'))}


def observe_compiler_inputs(environment, tail):
    """Read-only versioned inputs for the exact adapter configuration.

    An observed SDK tree is not an observed compiler read-set. Preserve the
    unresolved runtime/search-path inputs rather than fabricate completeness.
    """
    from agentdecompile_recovery.corpus.toolchain_identity import observe_input_files, RELEVANT_ENV_KEYS

    config = _configuration(environment)
    vc_root, prefix = config['vcRoot'], config['winePrefix']
    own = Path(__file__).resolve()
    files = {'adapter': own, 'identityObserver': own.with_name('toolchain_identity.py'),
             'preambleRecipe': own.with_name('recovered_c_preamble.py'),
             'pythonRuntime': Path(sys.executable),
             'prefixSystemRegistry': prefix / 'system.reg',
             'prefixUserRegistry': prefix / 'user.reg',
             'prefixDefaultRegistry': prefix / 'userdef.reg'}
    if config['wine']:
        files['wineLauncher'] = Path(config['wine'])
    gaps = ['compiler_dynamic_reads_unobserved', 'wine_loaded_modules_unobserved',
            'host_runtime_libraries_unobserved', 'source_local_header_search_unobserved',
            'input_snapshot_not_frozen']
    if not config['wine']:
        gaps.append('wine_launcher_unavailable')
    selectors = {'AGENT_DECOMPILE_PROJECTS_ROOT', 'VCROOT', 'CL_OPT',
                 'WINELOADER', 'WINESERVER', 'WINEPATH', 'PATH', 'LD_LIBRARY_PATH',
                 'LD_PRELOAD', *RELEVANT_ENV_KEYS}
    observed_environment = {name: value for name, value in config['environment'].items()
                            if name in selectors}
    flags = ['/nologo', '/c', *config['flags'], '/I' + _winpath(vc_root / 'include'), *tail]
    if any(str(flag).startswith('@') for flag in flags):
        gaps.append('response_file_inputs_unobserved')
    if observed_environment.get('INCLUDE') or any(str(flag).upper().startswith(('/I', '/FI')) for flag in tail):
        gaps.append('additional_header_search_unobserved')
    return observe_input_files(files, {'compilerBin': vc_root / 'bin', 'sdkInclude': vc_root / 'include'},
        observed_environment, {'PROJECTS': config['projectsRoot'], 'VCROOT': vc_root, 'WINEPREFIX': prefix},
        {'adapter': 'agentdecompile.msvc71/v2', 'compiler': str(vc_root / 'bin' / 'cl.exe'),
         'wine': config['wine'], 'flags': flags, 'winePrefix': str(prefix),
         'sourceLanguages': SOURCE_LANGUAGES, 'frontendSelection': 'per-file /Tc or /Tp',
         'outputMode': 'separate-translation-units', 'batchSizeLimit': MAX_BATCH_TRANSLATION_UNITS}, gaps)


def _winpath(path: Path) -> str:
    return "Z:" + str(path.resolve()).replace("/", "\\")


def _run_cl(sources: list[Path], outputs: list[Path], tail: list[str]) -> int:
    config = _configuration(os.environ)
    try:
        with compiler_prefix_lease(config['winePrefix'], config['environment']) as (environment, descriptor):
            return _run_cl_leased(sources, outputs, tail, environment, descriptor)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'MSVC prefix lease refused: {exc}', file=sys.stderr)
        return 2


def _run_cl_leased(sources: list[Path], outputs: list[Path], tail: list[str],
                   environment: dict[str, str], descriptor: int) -> int:
    try:
        source_arguments = [source_argument(source) for source in sources]
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if len(sources) != len(outputs) or not sources:
        print("source/object mapping must be nonempty and one-to-one", file=sys.stderr)
        return 2
    if len({source.name for source in sources}) != len(sources):
        print("source basenames must be unique", file=sys.stderr)
        return 2
    if len({str(output.resolve()).casefold() for output in outputs}) != len(outputs):
        print("object paths must be unique under Windows case-insensitive naming", file=sys.stderr)
        return 2

    config = _configuration(environment)
    vc_root = config['vcRoot']
    cl = vc_root / "bin" / "cl.exe"
    include = vc_root / "include"
    if not cl.is_file():
        print(f"VC7.1 not found at: {cl}", file=sys.stderr)
        return 2
    wine = config['wine']
    if not wine:
        print("Wine executable not found on PATH", file=sys.stderr)
        return 2

    environment = config['environment']
    flags = config['flags']
    # With multiple translation units MSVC's /Fo argument names an output
    # directory. Each source has a unique basename, so cl.exe deterministically
    # maps it to a distinct <basename>.obj without combining translation units.
    if len(sources) == 1:
        outputs[0].unlink(missing_ok=True)
        output_argument = f"/Fo{_winpath(outputs[0])}"
    else:
        output_dir = outputs[0].parent.resolve()
        if any(output.parent.resolve() != output_dir for output in outputs):
            print("batch object outputs must share one private directory", file=sys.stderr)
            return 2
        for output in outputs:
            output.unlink(missing_ok=True)
        output_argument = f"/Fo{_winpath(output_dir)}\\"
    command = [wine, str(cl), "/nologo", "/c", *flags,
               f"/I{_winpath(include)}", *tail, output_argument,
               *source_arguments]
    if __package__:
        from .compiler_run_attestation import observe_invocation_inputs
    else:  # Direct script invocation puts this file's directory on sys.path.
        from compiler_run_attestation import observe_invocation_inputs

    try:
        files_before = observe_invocation_inputs(
            compiler=cl, wine=Path(wine), sources=sources, environment=environment)
    except (OSError, ValueError, TypeError) as exc:
        # Attestation failure is recorded as a gap; it must not prevent compile.
        files_before = ([], ["prelaunch_file_observation_failed:" + type(exc).__name__])
    started_ns = time.monotonic_ns()
    try:
        completed = subprocess.run(command, env=environment, text=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   errors="replace", check=False, pass_fds=(descriptor,))
    except OSError as exc:
        finished_ns = time.monotonic_ns()
        _emit_run_attestation(command, environment, cl, Path(wine), sources, outputs,
                               started_ns, None, type(exc).__name__, finished_ns, files_before)
        # OSError text may disclose argv paths; the attestation already records
        # a redacted argv shape and its exact digest without storing path text.
        print(f"could not start MSVC/Wine ({type(exc).__name__})", file=sys.stderr)
        return 2
    finished_ns = time.monotonic_ns()
    _emit_run_attestation(command, environment, cl, Path(wine), sources, outputs,
                          started_ns, completed.returncode, finished_ns=finished_ns,
                          files_before=files_before)
    if completed.stdout:
        source_labels = {source.name for source in sources}
        for line in completed.stdout.replace("\r", "").splitlines():
            if line not in source_labels:
                print(line, file=sys.stderr)
    if completed.returncode != 0:
        print(f"cl.exe failed with status {completed.returncode} for batch: "
              f"{', '.join(source.name for source in sources)}", file=sys.stderr)
        return completed.returncode
    missing = [output for output in outputs
               if not output.is_file() or output.stat().st_size == 0]
    if missing:
        print("cl.exe returned success but did not produce nonempty objects for: "
              + ", ".join(path.name for path in missing), file=sys.stderr)
        return 1
    return 0


def _emit_run_attestation(command, environment, compiler, wine, sources, outputs,
                          started_ns, return_code, launch_error=None, finished_ns=None,
                          files_before=None):
    """Retain bounded invocation provenance without changing compile status."""
    if __package__:
        from .compiler_run_attestation import SINK_ENV, emit_attestation, make_attestation
    else:  # Keep attestation behavior identical in verifier direct-script mode.
        from compiler_run_attestation import SINK_ENV, emit_attestation, make_attestation

    try:
        record = make_attestation(argv=command, environment=environment,
                                  compiler=compiler, wine=wine, sources=sources,
                                  outputs=outputs, started_ns=started_ns,
                                  return_code=return_code, launch_error=launch_error,
                                  finished_ns=finished_ns,
                                  files_before=files_before or ([], ["prelaunch_file_observation_missing"]))
        emit_attestation(record, sink_directory=environment.get(SINK_ENV))
    except (OSError, ValueError, TypeError) as exc:
        # Evidence capture is deliberately non-authoritative: an attestation
        # sink problem must not turn a successful compiler invocation into a
        # compile failure or silently promote an incomplete record.
        print("AGENT_DECOMPILE_COMPILER_RUN_ATTESTATION_CAPTURE_FAILED="
              + type(exc).__name__, file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "--batch":
        # Amortize Wine/MSVC process startup across tiny recovered functions,
        # while keeping each invocation bounded for failure attribution.
        if not (3 + MIN_BATCH_TRANSLATION_UNITS <= len(arguments)
                <= 3 + MAX_BATCH_TRANSLATION_UNITS):
            print("batch mode requires source-dir, object-dir, and 2-24 source basenames",
                  file=sys.stderr)
            return 2
        _, source_dir, object_dir, *basenames = arguments
        if not MIN_BATCH_TRANSLATION_UNITS <= len(basenames) <= MAX_BATCH_TRANSLATION_UNITS:
            print("batch mode requires source-dir, object-dir, and 2-24 source basenames",
                  file=sys.stderr)
            return 2
        if any(Path(name).name != name or Path(name).suffix.lower() not in SOURCE_LANGUAGES for name in basenames):
            print("batch sources must be exact C/C++ basenames", file=sys.stderr)
            return 2
        source_root, object_root = Path(source_dir).resolve(), Path(object_dir).resolve()
        sources = [source_root / name for name in basenames]
        outputs = [object_root / (Path(name).stem + ".obj") for name in basenames]
        if len({output.name.casefold() for output in outputs}) != len(outputs):
            print("batch source basenames collide at the Windows object output path", file=sys.stderr)
            return 2
        if any(not source.is_file() or source.parent != source_root for source in sources):
            print("batch source is missing or outside the private source directory", file=sys.stderr)
            return 2
        object_root.mkdir(parents=True, exist_ok=True)
        return _run_cl(sources, outputs, [])
    if len(arguments) < 2:
        print(__doc__.splitlines()[0], file=sys.stderr)
        return 2
    source, output, *tail = arguments
    # The optional third argument is a symbol label, not a compiler flag.
    if tail:
        tail.pop(0)

    source_path, output_path = Path(source).resolve(), Path(output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return _run_cl([source_path], [output_path], tail)


if __name__ == "__main__":
    raise SystemExit(main())
