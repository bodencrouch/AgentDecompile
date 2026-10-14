"""Drive AssetRipper headlessly to reconstruct a Unity project tree.

AssetRipper's GUI build doubles as a local HTTP service (``--headless --port N``)
whose routes -- ``/LoadFolder``, ``/LoadFile``, ``/Export/UnityProject`` -- are the
only supported way to script it: there is no batch CLI that both loads a player
and writes an ``ExportedProject``. This module is the Python port of a
PowerShell driver that was proven against a shipped title, and it exists to
defend three concrete failure modes that cost real runs:

* **Leaked processes.** A failure between launch and export used to leave an
  AssetRipper holding the port, so the next run silently talked to a stale
  instance loaded with the *previous* game. Termination happens in ``finally``.
* **Racing the server.** POSTing before the listener is up fails with a bare
  connection refused. Readiness is gated on ``GET /openapi.json`` returning 200,
  not merely on the TCP port opening.
* **Mid-export death.** AssetRipper loads the whole asset graph into memory
  before writing anything; on a 15 GiB title that ended in an
  ``OutOfMemoryException`` partway through, leaving a plausible-looking but
  scene-less output tree. The staged plan from
  :func:`~agentdecompile_recovery.unity_probe.build_unity_plan` shrinks the
  input, and an early process exit is detected, classified, and reported rather
  than mistaken for success.

Success is not "the command returned". It is
``ExportedProject/ProjectSettings/ProjectVersion.txt`` existing on disk -- the
first file Unity itself requires to open the result -- and that check is what the
receipt reports.

Standard library only: adding an HTTP client dependency for four form POSTs
would be a permanent cost for a temporary convenience.
"""

from __future__ import annotations

import re
import socket
import secrets
import shlex
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import PurePosixPath

from pathlib import Path
from typing import Any

from .tools import ToolchainError
from .unity_assets import find_unity_data_dir

# AssetRipper answers a successful form POST with a 302 back to its own UI.
# urllib treats that as an error once redirects are disabled, so the codes that
# mean "accepted" have to be enumerated rather than inferred.
_ACCEPTED_STATUS = frozenset({200, 201, 204, 301, 302, 303, 307, 308})

# Substrings that mean the process died for lack of memory rather than for a
# bug in the input. Mixed .NET and OS-level spellings: the managed exception
# when AssetRipper notices, the allocator abort when it does not, and the Linux
# OOM killer's own wording when the kernel decides first.
_OOM_MARKERS = (
    "outofmemoryexception",
    "out of memory",
    "insufficient memory",
    "bad_alloc",
    "cannot allocate memory",
    "killed process",
    "oom-killer",
)

# SIGKILL. The Linux OOM killer's signature, and indistinguishable from a manual
# `kill -9` -- so it is reported as a *suspected* memory failure, never asserted.
_SIGKILL_RETURNCODE = -9

# 128+9: the same SIGKILL as reported by a shell (`$?`) or a container runtime
# rather than by `Popen.returncode`. Accepted because misclassifying an OOM kill
# as an ordinary failure sends the whole diagnosis down the wrong path, while a
# false positive only over-states a value already named "suspected".
_SHELL_SIGKILL_RETURNCODE = 137

_STARTUP_TIMEOUT = 120.0
_LOG_TAIL_BYTES = 8192

_SCHEMA = "agentdecompile.unity-export.v1"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Stop urllib from replaying a POST as a GET against AssetRipper's UI.

    Following the 302 would re-enter the web UI, which on some builds re-runs
    work or returns a 404 that masks an otherwise successful export.
    """

    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def pick_free_port() -> int:
    """Ask the OS for a currently-unused loopback port.

    Bind-then-release races anything else on the host that binds in the same
    instant; that is acceptable because the alternative -- a hardcoded default
    port -- collides deterministically with a leaked AssetRipper from an earlier
    run, which is the failure this avoids.
    """

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _split_base_url(base_url: str) -> tuple[str, int]:
    parts = urllib.parse.urlsplit(base_url)
    return parts.hostname or "127.0.0.1", int(parts.port or 80)


def _tcp_open(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_for_assetripper(
    base_url: str, *, timeout: float, process: subprocess.Popen[bytes] | None = None
) -> bool:
    """Block until AssetRipper's HTTP API answers, or ``timeout`` elapses.

    The readiness signal is ``GET /openapi.json`` returning 200, not an open TCP
    port: the listener accepts connections before the routes are mapped, so a
    port-only check hands back a server that 404s the very next request.
    """

    host, port = _split_base_url(base_url)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            return False
        if _tcp_open(host, port, 0.4):
            try:
                with urllib.request.urlopen(f"{base_url}/openapi.json", timeout=10) as response:
                    if int(response.status) == 200 and (process is None or process.poll() is None):
                        return True
            except (urllib.error.URLError, OSError):
                pass
        time.sleep(0.3)
    return False


def _form_post(url: str, fields: dict[str, str], *, timeout: float) -> int:
    """POST ``application/x-www-form-urlencoded`` and return the status code.

    ``quote`` (not ``quote_plus``) matches the escaping the proven PowerShell
    driver used, so paths containing spaces travel as ``%20`` exactly as they did
    in the runs this port is derived from.
    """

    body = urllib.parse.urlencode(fields, quote_via=urllib.parse.quote).encode("ascii")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        if exc.code in _ACCEPTED_STATUS:
            return int(exc.code)
        raise


def find_exported_project(output_dir: Path) -> Path | None:
    """Locate the ``ExportedProject`` tree AssetRipper nests under its output.

    AssetRipper writes ``<dest>/ExportedProject`` alongside ``AuxiliaryFiles``,
    but ``CreateSubfolder`` and version differences add a level, so the direct
    child is checked first and a bounded search follows. A destination that is
    itself a Unity project (``Assets`` + ``ProjectSettings``) is accepted last.
    """

    direct = output_dir / "ExportedProject"
    if direct.is_dir():
        return direct
    if output_dir.is_dir():
        for depth in ("*/ExportedProject", "*/*/ExportedProject"):
            for candidate in sorted(output_dir.glob(depth)):
                if candidate.is_dir():
                    return candidate
    if (output_dir / "Assets").is_dir() and (output_dir / "ProjectSettings").is_dir():
        return output_dir
    return None


def project_version_file(exported_project: Path) -> Path:
    """The file whose presence is this stage's success signal."""

    return exported_project / "ProjectSettings" / "ProjectVersion.txt"


def _tail(path: Path, limit: int = _LOG_TAIL_BYTES) -> str:
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - limit))
            return handle.read().decode("utf-8", "replace").strip()
    except OSError:
        return ""


def looks_like_memory_failure(text: str, returncode: int | None = None) -> bool:
    """Classify a dead AssetRipper as a memory failure from its own output.

    Pure string inspection so the classification can be unit-tested against
    captured logs without running anything.
    """

    lowered = text.lower()
    if any(marker in lowered for marker in _OOM_MARKERS):
        return True
    return returncode in {_SIGKILL_RETURNCODE, _SHELL_SIGKILL_RETURNCODE}


def _stop_process(process: subprocess.Popen[bytes] | None, *, grace: float = 0.0) -> tuple[int | None, bool]:
    """Terminate, then kill. Returns ``(returncode, exited_on_its_own)``.

    The second value matters: our own ``terminate()`` leaves a non-zero exit code
    (``-15``) that is indistinguishable from a crash unless we record that the
    process was still alive when we asked it to stop. Reporting that as an early
    death would mask the actual error.

    ``grace`` covers the case that motivates all of this: a server that dies
    mid-request has not been reaped by the time the client sees the dropped
    connection, so an immediate ``poll()`` reports it alive and its real exit
    code -- the OOM evidence -- is lost. Callers pass a grace only when something
    already went wrong, so a healthy run never waits.

    Never raises; this runs on the failure path too.
    """

    if process is None:
        return None, False
    if process.poll() is None and grace > 0:
        try:
            process.wait(timeout=grace)
        except (subprocess.TimeoutExpired, OSError):
            pass
    if process.poll() is not None:
        return process.returncode, True
    try:
        process.terminate()
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
            process.wait(timeout=10)
        except (subprocess.TimeoutExpired, OSError):
            pass
    except OSError:
        pass
    return process.returncode, False


def _load_route(load_path: Path) -> str:
    """``/LoadFile`` for a single player executable, ``/LoadFolder`` otherwise."""

    return "/LoadFile" if load_path.is_file() else "/LoadFolder"


def _validate_remote_paths(input_path: str | None, output_path: str | None) -> tuple[str, str]:
    """Validate remote paths before passing them to AssetRipper or rsync's shell."""

    if not input_path or not output_path:
        raise ValueError("remote AssetRipper mode requires both remote input and output paths")
    paths = []
    for label, value in (("input", input_path), ("output", output_path)):
        path = PurePosixPath(value)
        if not path.is_absolute() or value == "/" or not re.fullmatch(r"/[A-Za-z0-9_./-]+", value):
            raise ValueError(f"remote {label} path must be a non-root absolute POSIX path using only letters, digits, '.', '_', '/', and '-': {value!r}")
        if ".." in path.parts:
            raise ValueError(f"remote {label} path must not contain '..': {value!r}")
        paths.append(path)
    source, destination = paths
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError("remote AssetRipper input and output paths must not overlap")
    return str(source), str(destination)


def _validate_remote_host(host: str) -> str:
    if not host or host.count("@") > 1 or ":" in host:
        raise ValueError("remote SSH host must be a hostname or user@IPv4 value; IPv6 and shell syntax are not accepted")
    if "@" in host:
        user, hostname = host.split("@", 1)
        if not user or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", user):
            raise ValueError(f"invalid SSH username in remote host: {host!r}")
    else:
        hostname = host
    if not hostname or hostname.startswith("-") or not re.fullmatch(r"[A-Za-z0-9_.-]+", hostname):
        raise ValueError(f"invalid SSH host in remote host: {host!r}")
    if re.fullmatch(r"[0-9.]+", hostname):
        import ipaddress

        try:
            ipaddress.IPv4Address(hostname)
        except ipaddress.AddressValueError as exc:
            raise ValueError(f"invalid IPv4 address in remote host: {hostname!r}") from exc
    elif any(not label or label.startswith("-") or label.endswith("-") for label in hostname.split(".")):
        raise ValueError(f"invalid hostname in remote host: {hostname!r}")
    return host


def _copy_remote_export(host: str, remote_path: str, destination: Path, *, ssh_port: int) -> str:
    """Copy a remote export back with resumable, IPv4-only rsync-over-SSH."""

    import shutil

    rsync = shutil.which("rsync")
    if rsync is None:
        raise RuntimeError("rsync is required to retrieve the remote AssetRipper project")
    destination.mkdir(parents=True, exist_ok=True)
    command = [
        rsync,
        "-a",
        "--partial",
        "--append-verify",
        "--checksum",
        "--human-readable",
        "--stats",
        "-e",
        f"ssh -4 -p {ssh_port} -o ServerAliveInterval=30 -o ServerAliveCountMax=6",
        f"{host}:{remote_path.rstrip('/')}/",
        f"{destination}/",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-2000:]
        raise RuntimeError(f"rsync of remote AssetRipper output failed (exit {result.returncode}): {detail}")
    return (result.stdout or "").strip()


def _verify_remote_export_copy(host: str, remote_path: str, local_path: Path, *, ssh_port: int) -> str:
    """Checksum-compare the complete remote export tree to its local copy."""

    import shutil

    rsync = shutil.which("rsync")
    if rsync is None:
        raise RuntimeError("rsync is required to verify the retrieved AssetRipper project")
    result = subprocess.run(
        [
            rsync,
            "-rlnc",
            "--delete",
            "--itemize-changes",
            "--out-format=ADRECOVER_OUTPUT_DIFF:%i %n%L",
            "--stats",
            "-e",
            f"ssh -4 -p {ssh_port} -o ServerAliveInterval=30 -o ServerAliveCountMax=6",
            f"{host}:{remote_path.rstrip('/')}/",
            f"{local_path}/",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-2000:]
        raise RuntimeError(f"remote output checksum comparison failed (exit {result.returncode}): {detail}")
    differences = [line for line in result.stdout.splitlines() if line.startswith("ADRECOVER_OUTPUT_DIFF:")]
    if differences:
        detail = "\n".join(differences[:20])
        raise RuntimeError(
            f"local output differs from the remote export ({len(differences)} itemized differences). "
            f"First differences:\n{detail}"
        )
    return result.stdout.strip()


def _find_remote_project_version(host: str, remote_path: str, *, ssh_port: int) -> str:
    """Require AssetRipper's expected project marker to exist on the remote tree."""

    command = (
        f"find {remote_path} -maxdepth 6 -type f "
        "-path '*/ProjectSettings/ProjectVersion.txt' -print -quit"
    )
    result = subprocess.run(
        ["ssh", "-4", "-p", str(ssh_port), host, command],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-2000:]
        raise RuntimeError(f"could not inspect remote AssetRipper project marker (exit {result.returncode}): {detail}")
    marker = result.stdout.strip().splitlines()
    if not marker:
        raise RuntimeError("remote AssetRipper output contains no ProjectSettings/ProjectVersion.txt")
    return marker[0]


def _prepare_remote_export_dir(
    host: str, input_path: str, output_base_path: str, run_id: str, *, ssh_port: int
) -> tuple[str, str]:
    output_path = f"{output_base_path.rstrip('/')}/{run_id}"
    # Paths have already been restricted to a conservative POSIX alphabet, so
    # the fixed shell command cannot be altered by user-supplied metacharacters.
    remote_command = (
        f"input_real=$(realpath -e -- {input_path}) && "
        f"base_real=$(realpath -m -- {output_base_path}) && "
        "[ \"$input_real\" != / ] && [ \"$base_real\" != / ] && [ -d \"$input_real\" ] && "
        "case \"$input_real/\" in \"$base_real/\"*) echo 'remote input/output overlap' >&2; exit 23;; esac && "
        "case \"$base_real/\" in \"$input_real/\"*) echo 'remote input/output overlap' >&2; exit 23;; esac && "
        "mkdir -p -- \"$base_real\" && "
        f"mkdir -- \"$base_real/{run_id}\" && "
        f"output_real=$(realpath -e -- \"$base_real/{run_id}\") && "
        "case \"$input_real/\" in \"$output_real/\"*) echo 'remote input/output overlap' >&2; exit 23;; esac && "
        "case \"$output_real/\" in \"$input_real/\"*) echo 'remote input/output overlap' >&2; exit 23;; esac && "
        "printf '%s\\n%s\\n' \"$input_real\" \"$output_real\""
    )
    result = subprocess.run(
        ["ssh", "-4", "-p", str(ssh_port), host, remote_command],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-2000:]
        raise RuntimeError(f"could not resolve remote input/output directories (exit {result.returncode}): {detail}")
    resolved = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(resolved) < 2:
        raise RuntimeError("remote path resolution returned incomplete output")
    resolved_input, resolved_output = map(PurePosixPath, resolved[-2:])
    if resolved_input == resolved_output or resolved_input in resolved_output.parents or resolved_output in resolved_input.parents:
        raise RuntimeError("canonical remote AssetRipper input and output paths overlap; refusing to export")
    return str(resolved_input), str(resolved_output)


def _verify_remote_input(local_input: Path, host: str, remote_input: str, *, ssh_port: int) -> str:
    """Compare the local install tree with remote using read-only metadata checks.

    Remote checksum scans can wedge on high-latency or unhealthy disks. The
    source transfer is already performed with rsync append-verify; this check
    gates export on the complete relative-path inventory and file sizes. This
    intentionally cannot detect same-size content changes or metadata drift.
    """

    import shutil

    rsync = shutil.which("rsync")
    if rsync is None:
        raise RuntimeError("rsync is required to verify the remote AssetRipper input")
    if not local_input.is_dir():
        raise RuntimeError(f"remote full export requires a local install directory for comparison: {local_input}")
    result = subprocess.run(
        [
            rsync,
            "-rln",
            "--size-only",
            "--delete",
            "--itemize-changes",
            "--out-format=ADRECOVER_INPUT_DIFF:%i %n%L",
            "--stats",
            "-e",
            f"ssh -4 -p {ssh_port} -o ServerAliveInterval=30 -o ServerAliveCountMax=6",
            f"{local_input}/",
            f"{host}:{remote_input.rstrip('/')}/",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-2000:]
        raise RuntimeError(f"remote input inventory comparison failed (exit {result.returncode}): {detail}")
    differences = [line for line in result.stdout.splitlines() if line.startswith("ADRECOVER_INPUT_DIFF:")]
    if differences:
        detail = "\n".join(differences[:20])
        raise RuntimeError(
            f"remote input path/size inventory differs from the local install tree ({len(differences)} itemized differences); "
            f"no export started. First differences:\n{detail}"
        )
    return result.stdout.strip()


def _staged_containers(plan: dict[str, Any] | None) -> list[str]:
    export = (plan or {}).get("export") or {}
    included = export.get("includedContainers") or []
    return [str(name) for name in included]


def export_unity_project(
    install_root: Path,
    output_dir: Path,
    *,
    assetripper_cli: Path | None,
    plan: dict[str, Any] | None = None,
    staging_dir: Path | None = None,
    port: int | None = None,
    load_timeout: float = 7200,
    export_timeout: float = 7200,
    startup_timeout: float = _STARTUP_TIMEOUT,
    remote_host: str | None = None,
    remote_input_path: str | None = None,
    remote_output_path: str | None = None,
    remote_port: int = 18086,
    ssh_port: int = 22,
) -> dict[str, Any]:
    """Export a shipped Unity player to an ``ExportedProject`` tree.

    When ``plan["export"]["mode"] == "staged"`` the plan's included containers are
    symlinked into a staging tree and AssetRipper is pointed at that instead of
    the real install: identical routes, a fraction of the asset graph, and the
    difference between finishing and dying of memory exhaustion on a large title.

    Everything this writes lives under ``output_dir``: AssetRipper's destination
    at ``output_dir/assetripper``, the staging tree at ``output_dir/_staging``,
    and process logs beside them. The staging tree is deliberately *not* nested
    inside the destination, because headless AssetRipper clears a non-empty
    destination without asking and would delete the tree it is reading from.
    """

    started = time.monotonic()
    install_root = install_root.resolve()
    output_dir = output_dir.resolve()
    remote_mode = remote_host is not None

    if remote_mode:
        remote_host = _validate_remote_host(remote_host or "")
        remote_input_path, remote_output_path = _validate_remote_paths(remote_input_path, remote_output_path)
        if not 1 <= remote_port <= 65535 or not 1 <= ssh_port <= 65535:
            raise ValueError("remote AssetRipper and SSH ports must be between 1 and 65535")
    elif remote_input_path is not None or remote_output_path is not None:
        raise ValueError("remote input/output paths require --unity-assetripper-remote-host")

    if not remote_mode and assetripper_cli is None:
        raise ToolchainError(
            "assetripper-missing",
            detail="no AssetRipper binary found (set AGENTDECOMPILE_ASSETRIPPER_CLI or install under target/assetripper)",
        )
    if not remote_mode:
        assetripper_cli = Path(assetripper_cli).expanduser().resolve()  # type: ignore[arg-type]
        if not assetripper_cli.is_file():
            raise ToolchainError("assetripper-missing", detail=f"not a file: {assetripper_cli}")

    if not install_root.exists():
        return {
            "schema": _SCHEMA,
            "status": "error",
            "reason": f"install root does not exist: {install_root}",
            "installRoot": str(install_root),
            "claimBoundary": "nothing was exported; this receipt describes a rejected input, not a failed export",
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    remote_run_id = f"run-{int(time.time())}-{secrets.token_hex(8)}" if remote_mode else None
    remote_output_base_path = remote_output_path
    export_dest = output_dir / (f"assetripper-{remote_run_id}" if remote_run_id else "assetripper")
    export_dest.mkdir(parents=True, exist_ok=not remote_mode)
    log_suffix = f"-{remote_run_id}" if remote_run_id else ""
    stdout_log = output_dir / f"assetripper{log_suffix}.stdout.log"
    stderr_log = output_dir / f"assetripper{log_suffix}.stderr.log"

    requested_mode = str(((plan or {}).get("export") or {}).get("mode") or "full")
    # A remote worker may still need a memory-bounded staged plan. Applying the
    # plan is explicit in the receipt; omitted containers are never presented
    # as recovered. Full mode remains the default when the plan says it fits.
    mode = requested_mode
    staged_containers: list[str] = []
    staging: dict[str, Any] | None = None
    load_path = install_root

    if mode == "staged":
        data_dir = find_unity_data_dir(install_root) if install_root.is_dir() else None
        if data_dir is None:
            return {
                "schema": _SCHEMA,
                "status": "error",
                "reason": "staged export requested but no *_Data directory was found under the install root",
                "mode": mode,
                "installRoot": str(install_root),
                "claimBoundary": "nothing was exported; a staged plan cannot be applied to a non-standard player layout",
            }
        staged_containers = _staged_containers(plan)
        if not remote_mode:
            from .unity_probe import stage_export_tree  # deferred: unity_probe imports tools

            staging_root = (staging_dir or (output_dir / "_staging")).resolve()
            staging = stage_export_tree(data_dir, staging_root, staged_containers)
            load_path = staging_root

    local_port = port or pick_free_port()
    base_url = f"http://127.0.0.1:{local_port}"
    route = "/LoadFolder" if remote_mode else _load_route(load_path)
    request_load_path = remote_input_path if remote_mode else str(load_path)
    request_export_path = remote_output_path if remote_mode else str(export_dest)

    process: subprocess.Popen[bytes] | None = None
    tunnel: subprocess.Popen[bytes] | None = None
    load_seconds = 0.0
    export_seconds = 0.0
    load_status: int | None = None
    export_status: int | None = None
    failure: str | None = None
    copy_log = ""
    output_verification_log = ""
    input_verification_log = ""
    input_verified = False
    output_transfer_verified = False
    resolved_remote_input = remote_input_path
    resolved_remote_output: str | None = None
    remote_staging_dir: str | None = None
    resolved_remote_load_path: str | None = None
    remote_version_file: str | None = None

    try:
        if remote_mode:
            resolved_remote_input, resolved_remote_output = _prepare_remote_export_dir(
                str(remote_host), str(remote_input_path), str(remote_output_path), str(remote_run_id), ssh_port=ssh_port
            )
            input_verification_log = _verify_remote_input(
                install_root, str(remote_host), resolved_remote_input, ssh_port=ssh_port
            )
            input_verified = True
            if mode == "staged":
                data_dir = find_unity_data_dir(install_root)
                if data_dir is None:
                    raise RuntimeError("staged export requested but no local *_Data directory was found")
                data_name = data_dir.name
                remote_staging_dir = f"{remote_output_base_path.rstrip('/')}/_staging-{remote_run_id}"
                remote_data_dir = f"{remote_staging_dir}/{data_name}"
                quote = shlex.quote
                remote_stage_parts = [
                    "set -eu",
                    f"mkdir -- {quote(remote_staging_dir)}",
                    f"mkdir -- {quote(remote_data_dir)}",
                ]
                for name in staged_containers:
                    if not name or PurePosixPath(name).name != name or name in {".", ".."}:
                        raise ValueError(f"invalid Unity container basename in staged plan: {name!r}")
                    source = f"{resolved_remote_input}/{data_name}/{name}"
                    link = f"{remote_data_dir}/{name}"
                    remote_stage_parts.append(f"ln -s -- {quote(source)} {quote(link)}")
                managed_source = f"{resolved_remote_input}/{data_name}/Managed"
                managed_link = f"{remote_data_dir}/Managed"
                remote_stage_parts.extend(
                    [
                        f"if [ -d {quote(managed_source)} ]; then ln -s -- {quote(managed_source)} {quote(managed_link)}; fi",
                        f"printf '%s\\n' {quote(remote_staging_dir)}",
                    ]
                )
                remote_stage_command = "; ".join(remote_stage_parts)
                stage_result = subprocess.run(
                    ["ssh", "-4", "-p", str(ssh_port), str(remote_host), remote_stage_command],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if stage_result.returncode != 0:
                    detail = (stage_result.stderr or stage_result.stdout).strip()[-2000:]
                    raise RuntimeError(f"could not stage remote AssetRipper input: {detail}")
                resolved_remote_load_path = stage_result.stdout.strip().splitlines()[-1]
                request_load_path = resolved_remote_load_path
            else:
                request_load_path = resolved_remote_input
            request_export_path = resolved_remote_output
        with stdout_log.open("wb") as out_handle, stderr_log.open("wb") as err_handle:
            if remote_mode:
                tunnel = subprocess.Popen(
                    [
                        "ssh", "-4", "-N", "-p", str(ssh_port),
                        "-o", "ExitOnForwardFailure=yes",
                        "-o", "ServerAliveInterval=30",
                        "-o", "ServerAliveCountMax=6",
                        "-L", f"127.0.0.1:{local_port}:127.0.0.1:{remote_port}",
                        str(remote_host),
                    ],
                    stdout=out_handle,
                    stderr=err_handle,
                )
            else:
                process = subprocess.Popen(
                    [str(assetripper_cli), "--headless", "--port", str(local_port)],
                    stdout=out_handle,
                    stderr=err_handle,
                )

        owned_process = tunnel if remote_mode else process
        if not wait_for_assetripper(base_url, timeout=startup_timeout, process=owned_process):
            if remote_mode and tunnel is not None and tunnel.poll() is not None:
                failure = f"SSH tunnel exited with code {tunnel.returncode} before the remote AssetRipper API became ready"
            else:
                failure = (
                    f"AssetRipper did not answer GET {base_url}/openapi.json within {startup_timeout:.0f}s"
                )
        else:
            phase_started = time.monotonic()
            try:
                load_status = _form_post(
                    f"{base_url}{route}",
                    {"Path": str(request_load_path)},
                    timeout=load_timeout,
                )
            except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError) as exc:
                failure = f"POST {route} failed: {exc}"
            finally:
                load_seconds = time.monotonic() - phase_started
            if remote_mode and failure is None and load_status != 302:
                failure = f"remote AssetRipper LoadFolder returned HTTP {load_status}; expected its synchronous 302 completion redirect"

            if failure is None:
                phase_started = time.monotonic()
                try:
                    export_status = _form_post(
                        f"{base_url}/Export/UnityProject",
                        {"Path": str(request_export_path)},
                        timeout=export_timeout,
                    )
                except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError) as exc:
                    failure = f"POST /Export/UnityProject failed: {exc}"
                finally:
                    export_seconds = time.monotonic() - phase_started
                if remote_mode and failure is None and export_status != 302:
                    failure = (
                        f"remote AssetRipper export returned HTTP {export_status}; "
                        "expected its synchronous 302 completion redirect"
                    )
            if failure is None and remote_mode:
                try:
                    remote_version_file = _find_remote_project_version(
                        str(remote_host), str(resolved_remote_output), ssh_port=ssh_port
                    )
                    copy_log = _copy_remote_export(
                        str(remote_host), str(resolved_remote_output), export_dest, ssh_port=ssh_port
                    )
                    output_verification_log = _verify_remote_export_copy(
                        str(remote_host), str(resolved_remote_output), export_dest, ssh_port=ssh_port
                    )
                    output_transfer_verified = True
                except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
                    failure = f"retrieving remote AssetRipper output failed: {exc}"
    finally:
        owned_process = tunnel if remote_mode else process
        returncode, exited_on_its_own = _stop_process(owned_process, grace=5.0 if failure else 0.0)

    stderr_tail = _tail(stderr_log)
    stdout_tail = _tail(stdout_log)
    combined = f"{stdout_tail}\n{stderr_tail}"

    exported_project = find_exported_project(export_dest)
    version_file = project_version_file(exported_project) if exported_project else None
    has_project_version = bool(version_file and version_file.is_file())

    # Only a process that was already gone when we went to stop it died on its
    # own; anything else carries our terminate()'s exit code and says nothing.
    died_early = (
        not remote_mode and exited_on_its_own and returncode not in (None, 0) and not has_project_version
    )
    memory_suspected = died_early and looks_like_memory_failure(combined, returncode)

    remote_completion_verified = remote_mode and export_status == 302
    completion_gate = not remote_mode or remote_completion_verified
    if has_project_version and failure is None and completion_gate and (
        not remote_mode or output_transfer_verified
    ):
        status = "complete"
        reason = None
    else:
        status = "error"
        if memory_suspected:
            reason = (
                "AssetRipper died before finishing the export and its output indicates memory "
                f"exhaustion (exit {returncode}); re-run with a staged plan or a smaller memory "
                "budget so fewer containers are loaded at once"
            )
        elif died_early:
            reason = f"AssetRipper exited early with code {returncode} before writing ProjectVersion.txt"
        elif failure is not None:
            reason = failure
        else:
            reason = (
                "export returned without writing ExportedProject/ProjectSettings/ProjectVersion.txt; "
                "the output tree is not an openable Unity project"
            )

    receipt: dict[str, Any] = {
        "schema": _SCHEMA,
        "status": status,
        "reason": reason,
        "mode": mode,
        "installRoot": str(install_root),
        "loadPath": str(request_load_path),
        "remoteLoadPath": request_load_path if remote_mode else None,
        "remoteStagingDir": remote_staging_dir,
        "remoteStagedLoadPath": resolved_remote_load_path,
        "loadRoute": route,
        "outputDir": str(output_dir),
        "exportDir": str(export_dest),
        "exportedProject": str(exported_project) if exported_project else None,
        "projectVersionFile": str(version_file) if version_file else None,
        "hasProjectVersion": has_project_version,
        "stagedContainers": staged_containers,
        "stagedContainerCount": len(staged_containers),
        "stagingDir": staging["stagingDir"] if staging else None,
        "stagingLinkCount": staging["linkCount"] if staging else 0,
        "port": local_port,
        "assetRipper": str(assetripper_cli) if assetripper_cli else None,
        "remoteAssetRipper": remote_host,
        "remoteInputPath": resolved_remote_input,
        "remoteInputVerified": input_verified,
        "remoteInputVerification": input_verification_log[-2000:],
        "remoteOutputBasePath": remote_output_base_path,
        "remoteOutputPath": resolved_remote_output,
        "remoteProjectVersionFile": remote_version_file,
        "remotePort": remote_port if remote_mode else None,
        "remoteOutputTransferVerified": output_transfer_verified,
        "remoteOutputTreeVerification": output_verification_log[-2000:],
        "modeOverrideReason": None,
        "requestedMode": requested_mode,
        "remoteOutputTransferLog": copy_log[-2000:],
        "loadStatus": load_status,
        "exportStatus": export_status,
        "remoteExportResponseAccepted": bool(remote_mode and export_status in _ACCEPTED_STATUS),
        "remoteExportCompletionVerified": remote_completion_verified if remote_mode else None,
        # Null when we stopped a healthy server ourselves: the exit code would be
        # our own SIGTERM and reads as a crash to anyone scanning the receipt.
        "exitCode": returncode if not remote_mode and exited_on_its_own else None,
        "exitedOnItsOwn": exited_on_its_own if not remote_mode else None,
        "tunnelExitCode": returncode if remote_mode and exited_on_its_own else None,
        "tunnelExitedOnItsOwn": exited_on_its_own if remote_mode else None,
        "remoteServiceProcessStatus": "external process not owned or observed" if remote_mode else None,
        "diedEarly": died_early,
        "memoryFailureSuspected": memory_suspected,
        "loadSeconds": round(load_seconds, 3),
        "exportSeconds": round(export_seconds, 3),
        "elapsedSeconds": round(time.monotonic() - started, 3),
        "stdoutLog": str(stdout_log),
        "stderrLog": str(stderr_log),
        "stderrTail": stderr_tail[-2000:],
        "claimBoundary": (
            "ProjectVersion.txt proves AssetRipper wrote a project skeleton -- not that the project "
            "opens, compiles, or that its scenes are complete; a staged export additionally omits "
            "every container outside stagedContainers, whose assets remain unresolved references"
        ),
    }
    return receipt
