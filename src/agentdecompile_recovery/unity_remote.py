"""Run AssetRipper on a remote host and retrieve an isolated Unity export.

The remote AssetRipper service is never started or stopped here. This adapter
copies a game folder to a unique remote input directory, forwards a local IPv4
loopback port to the already-running service, and copies the resulting output
to a unique local directory. It can also attach to an exact retained run and
wait for its completion log without issuing another export. Remote run
directories are deliberately retained, including after failures.
"""

from __future__ import annotations

import math
import os
import re
import shlex
import subprocess
import time
import urllib.error
import urllib.request
import uuid

from pathlib import Path, PurePosixPath
from typing import Any

from .unity_export import (
    _form_post,
    find_exported_project,
    pick_free_port,
    project_version_file,
)

_SCHEMA = "agentdecompile.unity-remote-export.v1"
_FORBIDDEN_PORTS = frozenset({5174, 8080})
_REMOTE_ROOT_RE = re.compile(r"^/[A-Za-z0-9._/-]+$")
_RUN_OUTPUT_SUFFIX_RE = re.compile(r"^[0-9a-f]{32}/output$")
_SSH_TARGET_RE = re.compile(r"^(?:[A-Za-z0-9_.-]+@)?[A-Za-z0-9][A-Za-z0-9.-]*$")
_HOST_KEY_ALIAS_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]*$")
_STAT_PATTERNS = {
    "fileCount": re.compile(r"^\s*Number of files:\s*([\d,]+)", re.MULTILINE),
    "totalBytes": re.compile(r"^\s*Total file size:\s*([\d,]+) bytes", re.MULTILINE),
    "transferredBytes": re.compile(
        r"^\s*Total transferred file size:\s*([\d,]+) bytes", re.MULTILINE
    ),
}


def _validate_remote_root(value: str) -> str:
    if not isinstance(value, str) or not _REMOTE_ROOT_RE.fullmatch(value):
        raise ValueError("remote_root must be an absolute POSIX path using only letters, digits, '.', '_', '-', and '/'")
    normalized = value.rstrip("/")
    parts = normalized[1:].split("/")
    if not normalized or normalized == "/" or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("remote_root must be a normalized absolute directory other than '/'")
    if PurePosixPath(normalized).is_absolute() is False:
        raise ValueError("remote_root must be absolute")
    return normalized


def _validate_remote_child(value: str, root: str, name: str) -> str:
    """Validate an optional reusable remote path as a strict child of root."""

    if not isinstance(value, str) or not _REMOTE_ROOT_RE.fullmatch(value):
        raise ValueError(f"{name} must be a normalized absolute POSIX path")
    normalized = value.rstrip("/")
    if normalized == root or not normalized.startswith(root + "/"):
        raise ValueError(f"{name} must be strictly below remote_root")
    parts = normalized[len(root) + 1 :].split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"{name} must be a normalized child of remote_root")
    if parts[0] == "runs":
        raise ValueError(f"{name} cannot be inside the reserved remote runs directory")
    return normalized


def _validate_remote_run_output_path(value: str, root: str) -> str:
    """Accept only remote_root/runs/<canonical UUID hex>/output."""

    prefix = f"{root}/runs/"
    if not isinstance(value, str) or not value.startswith(prefix):
        raise ValueError("remote_output_path must be below remote_root/runs/<32-hex-id>/output")
    if not _RUN_OUTPUT_SUFFIX_RE.fullmatch(value[len(prefix) :]):
        raise ValueError("remote_output_path must be exactly remote_root/runs/<32-hex-id>/output")
    return value


def _validate_target(value: str) -> str:
    if not isinstance(value, str) or not _SSH_TARGET_RE.fullmatch(value):
        raise ValueError("ssh_target must be a host or user@host (IPv4 transport is forced with ssh -4)")
    return value


def _validate_host_key_alias(value: str | None) -> str | None:
    if value is not None and (not isinstance(value, str) or not _HOST_KEY_ALIAS_RE.fullmatch(value)):
        raise ValueError("ssh_host_key_alias must be a hostname or IPv4 address")
    return value


def _validate_executable(value: str, name: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError(f"{name} must be a non-empty executable path")
    return value


def _validate_port(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
        raise ValueError(f"{name} must be an integer TCP port in 1..65535")
    if value in _FORBIDDEN_PORTS:
        raise ValueError(f"{name} cannot use protected port {value}")
    return value


def _validate_timeout(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{name} must be a finite non-negative number")
    return result


def _loopback_port() -> int:
    # The shared helper binds AF_INET to 127.0.0.1 and asks the OS for port 0.
    # Keep the explicit guard even though ephemeral ranges normally exclude the
    # protected application ports.
    for _ in range(32):
        port = pick_free_port()
        if port not in _FORBIDDEN_PORTS:
            return port
    raise OSError("could not allocate a non-protected IPv4 loopback port")


def _ssh_options(
    ssh_executable: str, host_key_alias: str | None, jump_host: str | None = None
) -> list[str]:
    options = [
        ssh_executable,
        "-4",
        "-T",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=15",
    ]
    if jump_host is not None:
        options.extend(("-J", jump_host))
    if host_key_alias is not None:
        options.extend(("-o", f"HostKeyAlias={host_key_alias}"))
    return options


def _rsync_ssh_command(
    ssh_executable: str, host_key_alias: str | None, jump_host: str | None = None
) -> str:
    # rsync's --rsh is parsed by a shell; quote the executable as one token.
    options = [ssh_executable, "-4", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15"]
    if jump_host is not None:
        options.extend(("-J", jump_host))
    if host_key_alias is not None:
        options.extend(("-o", f"HostKeyAlias={host_key_alias}"))
    return shlex.join(options)


def _rsync_stats(result: subprocess.CompletedProcess[str]) -> dict[str, int | None]:
    text = "\n".join((_output_text(result.stdout), _output_text(result.stderr)))
    stats: dict[str, int | None] = {}
    for name, pattern in _STAT_PATTERNS.items():
        match = pattern.search(text)
        stats[name] = int(match.group(1).replace(",", "")) if match else None
    return stats


def _output_text(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def _openapi_ready(base_url: str, tunnel: subprocess.Popen[bytes], timeout: float) -> tuple[bool, str | None, float]:
    started = time.monotonic()
    deadline = started + timeout
    last_error: str | None = None
    while True:
        code = tunnel.poll()
        if code is not None:
            return False, f"SSH tunnel exited with status {code} before AssetRipper became ready", time.monotonic() - started
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False, last_error or "timed out waiting for GET /openapi.json", time.monotonic() - started
        try:
            with urllib.request.urlopen(f"{base_url}/openapi.json", timeout=min(2.0, remaining)) as response:
                if int(response.status) == 200:
                    return True, None, time.monotonic() - started
                last_error = f"GET /openapi.json returned HTTP {response.status}"
        except urllib.error.HTTPError as exc:
            last_error = f"GET /openapi.json returned HTTP {exc.code}"
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            last_error = f"GET /openapi.json failed: {exc}"
        if tunnel.poll() is not None:
            continue
        time.sleep(min(0.25, max(0.0, deadline - time.monotonic())))


def _stop_tunnel(process: subprocess.Popen[bytes] | None) -> int | None:
    """Stop only the SSH Popen owned by this call, never a remote process."""

    if process is None:
        return None
    try:
        code = process.poll()
        if code is not None:
            return int(code)
        process.terminate()
        try:
            return int(process.wait(timeout=5))
        except subprocess.TimeoutExpired:
            process.kill()
            return int(process.wait(timeout=5))
    except (OSError, subprocess.TimeoutExpired):
        try:
            result = process.poll()
            return int(result) if result is not None else None
        except OSError:
            return None


def _error_receipt(reason: str, started: float, **fields: Any) -> dict[str, Any]:
    return {
        "schema": _SCHEMA,
        "status": "error",
        "reason": reason,
        "elapsedSeconds": round(time.monotonic() - started, 3),
        "claimBoundary": (
            "This adapter can prove transport completion and local ProjectVersion.txt presence only; "
            "it does not prove byte identity with original source, Editor import/compilation, scene "
            "completeness, gameplay equivalence, or absence of unresolved runtime assets."
        ),
        **fields,
    }


def _preloaded_session_verification_command(
    remote_root: str, remote_input: str, server_port: int
) -> tuple[str, str]:
    """Build a read-only check tying a live AssetRipper PID to a completed load."""

    pid_file = f"{remote_root}/assetripper.pid"
    log_path = f"{remote_root}/AssetRipper.log"
    command = " ; ".join(
        (
            "set -eu",
            "printf '%s\\n' AGENTDECOMPILE_VERIFY_PRELOADED_SESSION >/dev/null",
            f"test -d {shlex.quote(remote_input)}",
            f"test -s {shlex.quote(pid_file)}",
            f"pid=$(cat -- {shlex.quote(pid_file)})",
            "case \"$pid\" in ''|*[!0-9]*) echo invalid AssetRipper pid >&2; exit 40;; esac",
            "kill -0 \"$pid\"",
            "state=$(ps -p \"$pid\" -o stat=)",
            "case \"$state\" in *D*|*Z*) echo AssetRipper process is not runnable >&2; exit 41;; esac",
            "cmdline=$(tr '\\000' ' ' < \"/proc/$pid/cmdline\")",
            "printf '%s\\n' \"$cmdline\" | grep -F 'AssetRipper.GUI.Free' >/dev/null",
            f"printf '%s\\n' \"$cmdline\" | grep -F -- {shlex.quote(f'--headless --port {server_port}')} >/dev/null",
            f"grep -F -- {shlex.quote(f'Attempting to read files from {remote_input}')} {shlex.quote(log_path)} >/dev/null",
            f"grep -F -- {shlex.quote('Finished processing assets')} {shlex.quote(log_path)} >/dev/null",
            f"if grep -E -- {shlex.quote('Export.*Starting export|ExportProgress')} {shlex.quote(log_path)} >/dev/null; then echo AssetRipper export already started >&2; exit 42; fi",
            "printf 'AGENTDECOMPILE_PRELOADED_SESSION_VERIFIED\\npid=%s\\n' \"$pid\"",
        )
    )
    return command, log_path


def _parse_preloaded_session_evidence(
    stdout: str, remote_input: str, log_path: str
) -> dict[str, str] | None:
    lines = stdout.splitlines()
    if not lines or lines[0] != "AGENTDECOMPILE_PRELOADED_SESSION_VERIFIED":
        return None
    values = dict(line.split("=", 1) for line in lines[1:] if "=" in line)
    pid = values.get("pid")
    if not pid or not pid.isdecimal():
        return None
    return {"pid": pid, "inputPath": remote_input, "logPath": log_path}


def _remote_export_completion_command(
    remote_root: str, remote_input: str, remote_output: str, server_port: int
) -> tuple[str, str]:
    """Wait read-only for a terminal log marker tied to this exact export path."""

    pid_file = f"{remote_root}/assetripper.pid"
    log_path = f"{remote_root}/AssetRipper.log"
    identity_awk = r"""
function exact_path_in_line(line, path, allow_export_child, position, following, suffix) {
    position = index(line, path)
    if (position == 0) return 0
    following = substr(line, position + length(path), 1)
    if (following == "/") {
        if (!allow_export_child) return 0
        suffix = substr(line, position + length(path))
        return suffix ~ /^\/(ExportedProject|PrimaryContent)(\/|[[:space:]]|$)/
    }
    return following == "" || following !~ /[[:alnum:]_.-]/
}
{
    lower = tolower($0)
    if (!load_started && exact_path_in_line($0, input, 0) && lower ~ /attempting to read files from/)
        load_started = NR
    if (load_started && !load_finished && lower ~ /finished processing assets/)
        load_finished = NR
    if (load_finished && !export_started && exact_path_in_line($0, output, 1))
        export_started = NR
}
END {
    if (!load_started) print "MISSING_EXACT_INPUT_MARKER"
    else if (!load_finished) print "INPUT_PROCESSING_NOT_FINISHED"
    else if (!export_started) print "MISSING_EXACT_OUTPUT_MARKER"
    else print export_started
}
"""
    completion_awk = r"""
{
    lower = tolower($0)
    if (lower ~ /export/ &&
        (lower ~ /(^|[^[:alnum:]])(failed|failure|cancelled|canceled|aborted|incomplete|unsuccessful)([^[:alnum:]]|$)/ ||
         lower ~ /not[[:space:]]+(complete|completed|finished|successful)/)) {
        print "state=EXPORT_FAILED"
        exit 50
    }
    if (lower ~ /finished post[- ]export/ ||
        lower ~ /export complete([!.]|[[:space:]]|$)/ ||
        lower ~ /export completed successfully/) {
        print "state=EXPORT_COMPLETE"
        exit 0
    }
}
"""
    command = "\n".join(
        (
            "set -eu",
            f"test -d {shlex.quote(remote_input)}",
            f"test -d {shlex.quote(remote_output)}",
            f"input_real=$(cd {shlex.quote(remote_input)} && pwd -P)",
            f"output_real=$(cd {shlex.quote(remote_output)} && pwd -P)",
            f"test \"$input_real\" = {shlex.quote(remote_input)}",
            f"test \"$output_real\" = {shlex.quote(remote_output)}",
            f"test -s {shlex.quote(pid_file)}",
            f"pid=$(cat -- {shlex.quote(pid_file)})",
            "case \"$pid\" in ''|*[!0-9]*) echo invalid AssetRipper pid >&2; exit 40;; esac",
            "kill -0 \"$pid\"",
            "state=$(ps -p \"$pid\" -o stat=)",
            "case \"$state\" in *Z*) echo AssetRipper process is not live >&2; exit 41;; esac",
            "cmdline=$(tr '\\000' ' ' < \"/proc/$pid/cmdline\")",
            "printf '%s\\n' \"$cmdline\" | grep -F 'AssetRipper.GUI.Free' >/dev/null",
            f"printf '%s\\n' \"$cmdline\" | grep -F -- {shlex.quote(f'--headless --port {server_port}')} >/dev/null",
            f"test -r {shlex.quote(log_path)}",
            "start_line=$(awk -v input="
            + shlex.quote(remote_input)
            + " -v output="
            + shlex.quote(remote_output)
            + " "
            + shlex.quote(identity_awk)
            + f" {shlex.quote(log_path)})",
            "case \"$start_line\" in ''|*[!0-9]*) echo \"export session not proven: $start_line\" >&2; exit 42;; esac",
            "printf 'AGENTDECOMPILE_EXPORT_CHECK\\npid=%s\\n' \"$pid\"",
            f"tail -n +\"$start_line\" -f {shlex.quote(log_path)} | awk {shlex.quote(completion_awk)}",
        )
    )
    return command, log_path


def _parse_remote_export_completion_evidence(
    stdout: str, remote_input: str, remote_output: str, log_path: str
) -> dict[str, str] | None:
    lines = stdout.splitlines()
    if not lines or lines[0] != "AGENTDECOMPILE_EXPORT_CHECK":
        return None
    values = dict(line.split("=", 1) for line in lines[1:] if "=" in line)
    pid = values.get("pid")
    if not pid or not pid.isdecimal() or values.get("state") != "EXPORT_COMPLETE":
        return None
    return {
        "pid": pid,
        "inputPath": remote_input,
        "outputPath": remote_output,
        "logPath": log_path,
        "completion": "AssetRipper export completion marker observed after exact output path",
    }


def _wait_for_remote_export_completion(
    ssh_base: list[str],
    ssh_target: str,
    remote_root: str,
    remote_input: str,
    remote_output: str,
    server_port: int,
    timeout: float,
) -> tuple[dict[str, str] | None, str | None, float]:
    started = time.monotonic()
    command, log_path = _remote_export_completion_command(
        remote_root, remote_input, remote_output, server_port
    )
    try:
        result = subprocess.run(
            [*ssh_base, ssh_target, command],
            check=False,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=max(1.0, timeout),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"timed out or failed while waiting for remote export completion: {exc}", time.monotonic() - started

    stdout = _output_text(result.stdout)
    evidence = _parse_remote_export_completion_evidence(
        stdout, remote_input, remote_output, log_path
    )
    if result.returncode == 0 and evidence is not None:
        return evidence, None, time.monotonic() - started
    detail = _output_text(result.stderr)[-1000:]
    if "state=EXPORT_FAILED" in stdout:
        reason = "AssetRipper log reports that the attached export failed"
    else:
        reason = f"remote export completion was not proven (status {result.returncode})"
    if detail:
        reason += f": {detail}"
    return None, reason, time.monotonic() - started


def _is_remote_response_disconnect(exc: BaseException) -> bool:
    pending: list[BaseException] = [exc]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if "remote end closed connection without response" in str(current).lower():
            return True
        reason = getattr(current, "reason", None)
        if isinstance(reason, BaseException):
            pending.append(reason)
        for nested in (current.__cause__, current.__context__):
            if isinstance(nested, BaseException):
                pending.append(nested)
    return False


def export_unity_project_remote(
    install_root: Path,
    output_dir: Path,
    *,
    ssh_target: str,
    remote_root: str,
    remote_input_path: str | None = None,
    remote_output_path: str | None = None,
    reuse_loaded_session: bool = False,
    ssh_host_key_alias: str | None = None,
    ssh_jump_host: str | None = None,
    server_port: int = 18085,
    load_timeout: float = 7200,
    export_timeout: float = 14400,
    startup_timeout: float = 120,
    ssh_executable: str = "ssh",
    rsync_executable: str = "rsync",
) -> dict[str, Any]:
    """Export a Unity install with an existing remote AssetRipper service.

    Each invocation gets a fresh local destination. Normally it also gets a
    fresh remote run directory; ``remote_output_path`` instead attaches to an
    exact existing run output, verifies AssetRipper's completion log, and skips
    both load and export POSTs. In attach mode, ``remote_input_path`` may point
    to a separately stored existing game directory, as with a preloaded session.
    The remote input is checked but not modified; otherwise a fresh input directory
    is populated by rsync. No remote cleanup command is issued, and rsync is
    never given ``--delete``.
    The SSH forwarding process is the only long-lived process this function
    starts; only that process is terminated here.
    """

    started = time.monotonic()
    ssh_target = _validate_target(ssh_target)
    remote_root = _validate_remote_root(remote_root)
    attached_run_root: str | None = None
    if remote_output_path is not None:
        remote_output_path = _validate_remote_run_output_path(remote_output_path, remote_root)
        attached_run_root = str(PurePosixPath(remote_output_path).parent)
        attached_input_path = _posix_join(attached_run_root, "input")
        if remote_input_path is None:
            remote_input_path = attached_input_path
        elif remote_input_path != attached_input_path:
            remote_input_path = _validate_remote_child(remote_input_path, remote_root, "remote_input_path")
    elif remote_input_path is not None:
        remote_input_path = _validate_remote_child(remote_input_path, remote_root, "remote_input_path")
    if remote_output_path is not None and reuse_loaded_session:
        raise ValueError("remote_output_path attach mode cannot be combined with reuse_loaded_session")
    if reuse_loaded_session and remote_input_path is None:
        raise ValueError("reuse_loaded_session requires remote_input_path")
    ssh_host_key_alias = _validate_host_key_alias(ssh_host_key_alias)
    ssh_jump_host = _validate_target(ssh_jump_host) if ssh_jump_host is not None else None
    server_port = _validate_port(server_port, "server_port")
    load_timeout = _validate_timeout(load_timeout, "load_timeout")
    export_timeout = _validate_timeout(export_timeout, "export_timeout")
    startup_timeout = _validate_timeout(startup_timeout, "startup_timeout")
    ssh_executable = _validate_executable(ssh_executable, "ssh_executable")
    rsync_executable = _validate_executable(rsync_executable, "rsync_executable")

    install_root = Path(install_root).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    if remote_output_path is None and not install_root.is_dir():
        return _error_receipt(
            f"install root is not a directory: {install_root}",
            started,
            installRoot=str(install_root),
            transport="ssh-rsync-ipv4",
        )

    attempt_id = uuid.uuid4().hex
    if install_root == Path("/"):
        raise ValueError("install_root cannot be the filesystem root")
    storage_root = (output_dir / "remote-assetripper").resolve()
    if storage_root == install_root or install_root in storage_root.parents:
        raise ValueError("local remote-export output must not be inside install_root")

    remote_run_root = attached_run_root or _posix_join(remote_root, "runs", attempt_id)
    remote_input = remote_input_path or _posix_join(remote_run_root, "input")
    remote_output = remote_output_path or _posix_join(remote_run_root, "output")
    local_run_root = output_dir / "remote-assetripper" / attempt_id
    local_partial = output_dir / "remote-assetripper" / f".{attempt_id}.partial"

    receipt: dict[str, Any] = {
        "schema": _SCHEMA,
        "status": "error",
        "reason": None,
        "transport": "ssh-rsync-ipv4",
        "addressFamily": "IPv4",
        "sshTarget": ssh_target,
        "sshHostKeyAlias": ssh_host_key_alias,
        "sshJumpHost": ssh_jump_host,
        "attemptId": attempt_id,
        "installRoot": str(install_root),
        "outputDir": str(output_dir),
        "serverPort": server_port,
        "remoteRoot": remote_root,
        "remoteRunRoot": remote_run_root,
        "remoteInputPath": remote_input,
        "reusedRemoteInputPath": remote_input_path is not None,
        "reuseLoadedSession": reuse_loaded_session,
        "attachedExistingExport": remote_output_path is not None,
        "preloadedSessionVerified": False,
        "preloadedSessionEvidence": None,
        "remoteExportCompletionVerified": False,
        "remoteExportCompletionEvidence": None,
        "exportResponseLost": False,
        "exportCompletionWaitSeconds": 0.0,
        "loadSkipped": False,
        "remoteOutputPath": remote_output,
        "remoteEvidencePreserved": False,
        "remoteCleanup": "not-performed",
        "remoteInputCheckStatus": None,
        "inputStagingMode": "reuse-existing-read-only" if remote_input_path is not None else "fresh-rsync-copy",
        "localAttemptOutputDir": str(local_run_root),
        "localPartialOutputDir": str(local_partial),
        "localForwardBindHost": "127.0.0.1",
        "remoteForwardDestination": f"127.0.0.1:{server_port}",
        "loadRoute": "/LoadFolder",
        "loadStatus": None,
        "exportStatus": None,
        "mkdirStatus": None,
        "inputRsyncStatus": None,
        "outputRsyncStatus": None,
        "inputRsyncStats": {"fileCount": None, "totalBytes": None, "transferredBytes": None},
        "outputRsyncStats": {"fileCount": None, "totalBytes": None, "transferredBytes": None},
        "outputSymlinksFollowed": True,
        "hasProjectVersion": False,
        "projectVersionFile": None,
        "startupSeconds": 0.0,
        "loadSeconds": 0.0,
        "exportSeconds": 0.0,
        "inputTransferSeconds": 0.0,
        "outputTransferSeconds": 0.0,
        "elapsedSeconds": 0.0,
        "tunnelExitCode": None,
        "claimBoundary": (
            "A successful receipt proves the AssetRipper export route accepted this input, or that "
            "a PID-verified AssetRipper session and exact input/output log paths proved completion of an attached "
            "or response-disconnected export; a fresh input copy was rsynced successfully (or, for an "
            "explicitly supplied existing input path, only that the directory exists; its contents are "
            "not copied or hash-verified), and "
            "ProjectVersion.txt exists locally. It does not prove byte identity with developers' original "
            "source, Unity Editor import/compilation, scene completeness, "
            "gameplay equivalence, or absence of unresolved runtime assets."
        ),
    }

    tunnel: subprocess.Popen[bytes] | None = None
    failure: str | None = None
    transfer_timeout = max(60.0, load_timeout + export_timeout + startup_timeout)
    ssh_base = _ssh_options(ssh_executable, ssh_host_key_alias, ssh_jump_host)
    rsh = _rsync_ssh_command(ssh_executable, ssh_host_key_alias, ssh_jump_host)

    try:
        local_partial.parent.mkdir(parents=True, exist_ok=True)
        if local_run_root.exists() or local_partial.exists():
            raise FileExistsError("unique local remote-export destination already exists; refusing to overwrite")

        if remote_output_path is not None:
            mkdir_command = (
                "test -d "
                + shlex.quote(remote_input)
                + " && test -d "
                + shlex.quote(remote_output)
            )
        elif remote_input_path is not None:
            mkdir_command = (
                "umask 077 && test -d "
                + shlex.quote(remote_input)
                + " && mkdir -p -- "
                + shlex.quote(remote_output)
            )
        else:
            mkdir_command = "umask 077 && mkdir -p -- " + " ".join(
                shlex.quote(path) for path in (remote_input, remote_output)
            )
        phase_started = time.monotonic()
        mkdir_result = subprocess.run(
            [*ssh_base, ssh_target, mkdir_command],
            check=False,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=max(30.0, startup_timeout),
        )
        receipt["mkdirSeconds"] = round(time.monotonic() - phase_started, 3)
        receipt["mkdirStatus"] = mkdir_result.returncode
        receipt["remoteInputCheckStatus"] = mkdir_result.returncode if remote_input_path is not None else None
        if mkdir_result.returncode != 0:
            failure = f"remote mkdir failed with status {mkdir_result.returncode}: {_output_text(mkdir_result.stderr)[-1000:]}"
        else:
            receipt["remoteEvidencePreserved"] = True

        if failure is None and remote_input_path is None and remote_output_path is None:
            phase_started = time.monotonic()
            input_result = subprocess.run(
                [
                    rsync_executable,
                    "-a",
                    "--partial",
                    "--stats",
                    "--rsh",
                    rsh,
                    "--",
                    f"{install_root}{os.sep}",
                    f"{ssh_target}:{remote_input}/",
                ],
                check=False,
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                timeout=transfer_timeout,
            )
            receipt["inputTransferSeconds"] = round(time.monotonic() - phase_started, 3)
            receipt["inputRsyncStatus"] = input_result.returncode
            receipt["inputRsyncStats"] = _rsync_stats(input_result)
            if input_result.returncode != 0:
                failure = f"rsync input transfer failed with status {input_result.returncode}: {_output_text(input_result.stderr)[-1000:]}"
        elif failure is None:
            receipt["inputRsyncStatus"] = None
            receipt["inputTransferSeconds"] = 0.0
            receipt["inputTransferSeconds"] = 0.0

        if failure is None:
            local_port = _loopback_port()
            receipt["localForwardPort"] = local_port
            tunnel = subprocess.Popen(
                [
                    *ssh_base,
                    "-N",
                    "-o",
                    "ExitOnForwardFailure=yes",
                    "-L",
                    f"127.0.0.1:{local_port}:127.0.0.1:{server_port}",
                    ssh_target,
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            base_url = f"http://127.0.0.1:{local_port}"
            ready, ready_error, ready_seconds = _openapi_ready(base_url, tunnel, startup_timeout)
            receipt["startupSeconds"] = round(ready_seconds, 3)
            if not ready:
                failure = ready_error or "AssetRipper API did not become ready"

        if failure is None and remote_output_path is not None:
            phase_started = time.monotonic()
            evidence, wait_error, wait_seconds = _wait_for_remote_export_completion(
                ssh_base,
                ssh_target,
                remote_root,
                remote_input,
                remote_output,
                server_port,
                export_timeout,
            )
            receipt["exportCompletionWaitSeconds"] = round(wait_seconds, 3)
            receipt["exportSeconds"] = round(time.monotonic() - phase_started, 3)
            if evidence is None:
                failure = wait_error or "remote export completion was not proven"
            else:
                receipt["remoteExportCompletionVerified"] = True
                receipt["remoteExportCompletionEvidence"] = evidence
                receipt["preloadedSessionVerified"] = True
                receipt["preloadedSessionEvidence"] = {
                    "pid": evidence["pid"],
                    "inputPath": remote_input,
                    "logPath": evidence["logPath"],
                }
                receipt["loadSkipped"] = True
                receipt["exportStatus"] = "completed-by-remote-log"

        if failure is None and remote_output_path is None and reuse_loaded_session:
            verify_command, log_path = _preloaded_session_verification_command(
                remote_root, remote_input, server_port
            )
            try:
                verification = subprocess.run(
                    [*ssh_base, ssh_target, verify_command],
                    check=False,
                    capture_output=True,
                    text=True,
                    stdin=subprocess.DEVNULL,
                    timeout=max(30.0, startup_timeout),
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                failure = f"remote preloaded AssetRipper session verification failed: {exc}"
            else:
                evidence = _parse_preloaded_session_evidence(
                    _output_text(verification.stdout), remote_input, log_path
                )
                if verification.returncode != 0 or evidence is None:
                    detail = _output_text(verification.stderr)[-1000:]
                    failure = (
                        "remote preloaded AssetRipper session verification failed"
                        f" with status {verification.returncode}"
                        + (f": {detail}" if detail else "")
                    )
                else:
                    receipt["preloadedSessionVerified"] = True
                    receipt["preloadedSessionEvidence"] = evidence
                    receipt["loadSkipped"] = True

        if failure is None and remote_output_path is None and not reuse_loaded_session:
            phase_started = time.monotonic()
            try:
                receipt["loadStatus"] = _form_post(
                    f"{base_url}/LoadFolder", {"Path": remote_input}, timeout=load_timeout
                )
            except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError) as exc:
                failure = f"POST /LoadFolder failed: {exc}"
            finally:
                receipt["loadSeconds"] = round(time.monotonic() - phase_started, 3)

        if failure is None and remote_output_path is None:
            if tunnel is None or tunnel.poll() is not None:
                failure = "SSH tunnel exited before POST /Export/UnityProject"
            else:
                phase_started = time.monotonic()
                try:
                    receipt["exportStatus"] = _form_post(
                        f"{base_url}/Export/UnityProject", {"Path": remote_output}, timeout=export_timeout
                    )
                except urllib.error.HTTPError as exc:
                    failure = f"POST /Export/UnityProject failed: {exc}"
                except (urllib.error.URLError, OSError, TimeoutError) as exc:
                    if _is_remote_response_disconnect(exc):
                        receipt["exportResponseLost"] = True
                        evidence, wait_error, wait_seconds = _wait_for_remote_export_completion(
                            ssh_base,
                            ssh_target,
                            remote_root,
                            remote_input,
                            remote_output,
                            server_port,
                            max(0.0, export_timeout - (time.monotonic() - phase_started)),
                        )
                        receipt["exportCompletionWaitSeconds"] = round(wait_seconds, 3)
                        if evidence is None:
                            failure = (
                                f"POST /Export/UnityProject response was lost ({exc}); "
                                + (wait_error or "remote export completion was not proven")
                            )
                        else:
                            receipt["remoteExportCompletionVerified"] = True
                            receipt["remoteExportCompletionEvidence"] = evidence
                            receipt["exportStatus"] = "response-lost-completion-verified"
                    else:
                        failure = f"POST /Export/UnityProject failed: {exc}"
                finally:
                    receipt["exportSeconds"] = round(time.monotonic() - phase_started, 3)

        if failure is None:
            local_partial.mkdir()
            phase_started = time.monotonic()
            output_result = subprocess.run(
                [
                    rsync_executable,
                    "-aL",
                    "--partial",
                    "--stats",
                    "--rsh",
                    rsh,
                    "--",
                    f"{ssh_target}:{remote_output}/",
                    f"{local_partial}{os.sep}",
                ],
                check=False,
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                timeout=transfer_timeout,
            )
            receipt["outputTransferSeconds"] = round(time.monotonic() - phase_started, 3)
            receipt["outputRsyncStatus"] = output_result.returncode
            receipt["outputRsyncStats"] = _rsync_stats(output_result)
            if output_result.returncode != 0:
                failure = f"rsync output transfer failed with status {output_result.returncode}: {_output_text(output_result.stderr)[-1000:]}"
            else:
                os.replace(local_partial, local_run_root)
                exported_project = find_exported_project(local_run_root)
                version_file = project_version_file(exported_project) if exported_project else None
                has_version = bool(version_file and version_file.is_file())
                receipt["exportDir"] = str(local_run_root)
                receipt["exportedProject"] = str(exported_project) if exported_project else None
                receipt["projectVersionFile"] = str(version_file) if version_file else None
                receipt["hasProjectVersion"] = has_version
                if not has_version:
                    failure = "remote export was copied successfully but ProjectVersion.txt is absent"

    except subprocess.TimeoutExpired as exc:
        failure = f"{exc.cmd!r} timed out after {exc.timeout} seconds"
    except (OSError, ValueError, RuntimeError) as exc:
        failure = f"{type(exc).__name__}: {exc}"
    finally:
        receipt["tunnelExitCode"] = _stop_tunnel(tunnel)

    receipt["elapsedSeconds"] = round(time.monotonic() - started, 3)
    if failure is None:
        receipt["status"] = "complete"
        receipt["reason"] = None
    else:
        receipt["status"] = "error"
        receipt["reason"] = failure
    return receipt


def _posix_join(*parts: str) -> str:
    """Join already-validated absolute-root components without host path rules."""

    joined = PurePosixPath(parts[0]).joinpath(*parts[1:])
    return str(joined)
