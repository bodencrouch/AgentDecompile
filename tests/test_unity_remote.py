"""Offline tests for the remote AssetRipper transport adapter."""

from __future__ import annotations

import os
import shlex
import subprocess

from pathlib import Path

import pytest

from agentdecompile_recovery import unity_remote
from agentdecompile_recovery.cli import build_parser, unity_config_kwargs

pytestmark = pytest.mark.unit


_RSYNC_STATS = """Number of files: 12 (reg: 8, dir: 4)
Total file size: 1,234 bytes
Total transferred file size: 987 bytes
"""


class _Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _Tunnel:
    def __init__(self, argv, **_kwargs):
        self.argv = argv
        self.returncode = None
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None):
        del timeout
        return self.returncode


def _fake_transport(
    monkeypatch,
    *,
    tunnel_type=_Tunnel,
    version_file=True,
    output_status=0,
    mkdir_status=0,
    verify_status=0,
):
    commands = []
    tunnels = []
    openapi_requests = []

    def fake_run(argv, **kwargs):
        commands.append((argv, kwargs))
        if argv[0] == "ssh":
            if "AGENTDECOMPILE_VERIFY_PRELOADED_SESSION" in argv[-1]:
                stdout = (
                    "AGENTDECOMPILE_PRELOADED_SESSION_VERIFIED\n"
                    "pid=3366680\n"
                    "input=/root/Workspaces/tvs-assetripper-full-20261003/input\n"
                    "log=/root/Workspaces/tvs-assetripper-full-20261003/AssetRipper.log\n"
                )
                return subprocess.CompletedProcess(
                    argv,
                    verify_status,
                    stdout if verify_status == 0 else "",
                    "preloaded session verification failed",
                )
            return subprocess.CompletedProcess(argv, mkdir_status, "", "mkdir failed")
        assert argv[0] == "rsync"
        if "/runs/" in argv[-2] and "/output/" in argv[-2]:
            local_dest = Path(argv[-1].rstrip(os.sep))
            project = local_dest / "ExportedProject" / "ProjectSettings"
            if version_file:
                project.mkdir(parents=True)
                (project / "ProjectVersion.txt").write_text(
                    "m_EditorVersion: 2022.3.62f2\n", encoding="utf-8"
                )
            return subprocess.CompletedProcess(argv, output_status, _RSYNC_STATS, "")
        return subprocess.CompletedProcess(argv, 0, _RSYNC_STATS, "")

    def fake_popen(argv, **kwargs):
        process = tunnel_type(argv, **kwargs)
        tunnels.append(process)
        return process

    posts = []

    def fake_post(url, fields, *, timeout):
        posts.append((url, fields, timeout))
        return 302

    def fake_urlopen(url, **kwargs):
        openapi_requests.append((url, kwargs))
        return _Response()

    monkeypatch.setattr(unity_remote.subprocess, "run", fake_run)
    monkeypatch.setattr(unity_remote.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(unity_remote.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(unity_remote, "_form_post", fake_post)
    monkeypatch.setattr(unity_remote, "pick_free_port", lambda: 43127)
    return commands, tunnels, posts, openapi_requests


def _call(
    tmp_path: Path,
    install: Path,
    output: Path,
    *,
    reuse_loaded_session: bool = False,
) -> dict:
    return unity_remote.export_unity_project_remote(
        install,
        output,
        ssh_target="root@100.94.174.206",
        remote_root="/srv/tvs",
        ssh_host_key_alias="100.94.174.206",
        server_port=18085,
        load_timeout=10,
        export_timeout=20,
        startup_timeout=2,
        reuse_loaded_session=reuse_loaded_session,
    )


def test_remote_export_uses_ipv4_loopback_forward_and_isolated_paths(tmp_path, monkeypatch):
    install = tmp_path / "game with spaces"
    install.mkdir()
    (install / "globalgamemanagers").write_bytes(b"game")
    output = tmp_path / "recovered"
    commands, tunnels, posts, openapi_requests = _fake_transport(monkeypatch)

    receipt = _call(tmp_path, install, output)

    assert receipt["status"] == "complete"
    assert receipt["transport"] == "ssh-rsync-ipv4"
    assert receipt["addressFamily"] == "IPv4"
    assert receipt["hasProjectVersion"] is True
    assert Path(receipt["projectVersionFile"]).is_file()
    assert receipt["exportDir"] == receipt["localAttemptOutputDir"]
    assert receipt["exportedProject"] == str(
        Path(receipt["localAttemptOutputDir"]) / "ExportedProject"
    )
    assert receipt["inputRsyncStatus"] == 0
    assert receipt["outputRsyncStatus"] == 0
    assert receipt["inputRsyncStats"] == {
        "fileCount": 12,
        "totalBytes": 1234,
        "transferredBytes": 987,
    }
    assert receipt["remoteEvidencePreserved"] is True
    assert receipt["remoteCleanup"] == "not-performed"
    assert receipt["remoteInputPath"].startswith(receipt["remoteRunRoot"] + "/")
    assert receipt["remoteOutputPath"].startswith(receipt["remoteRunRoot"] + "/")
    assert receipt["localAttemptOutputDir"].startswith(str(output.resolve()))

    tunnel_argv = tunnels[0].argv
    assert "-4" in tunnel_argv
    assert "HostKeyAlias=100.94.174.206" in tunnel_argv
    forward = tunnel_argv[tunnel_argv.index("-L") + 1]
    assert forward == f"127.0.0.1:{receipt['localForwardPort']}:127.0.0.1:18085"
    assert receipt["localForwardPort"] not in {5174, 8080}
    assert tunnels[0].terminated is True
    assert tunnels[0].killed is False

    assert [url.rsplit("/", 1)[-1] for url, _fields, _timeout in posts] == [
        "LoadFolder",
        "UnityProject",
    ]
    assert posts[0][1] == {"Path": receipt["remoteInputPath"]}
    assert posts[1][1] == {"Path": receipt["remoteOutputPath"]}
    assert openapi_requests[0][0] == "http://127.0.0.1:43127/openapi.json"
    rsync_commands = [argv for argv, _kwargs in commands if argv[0] == "rsync"]
    assert len(rsync_commands) == 2
    assert "-a" in rsync_commands[0]
    assert "-aL" in rsync_commands[1]
    assert all("-4" in shlex.split(argv[argv.index("--rsh") + 1]) for argv in rsync_commands)
    assert all(
        "HostKeyAlias=100.94.174.206" in shlex.split(argv[argv.index("--rsh") + 1])
        for argv in rsync_commands
    )
    assert all("--delete" not in argv for argv, _kwargs in commands)
    assert all(kwargs.get("shell") is not True for _argv, kwargs in commands)


def test_tunnel_death_is_reported_and_not_mistaken_for_a_remote_service_failure(
    tmp_path, monkeypatch
):
    class DeadTunnel(_Tunnel):
        def __init__(self, argv, **kwargs):
            super().__init__(argv, **kwargs)
            self.returncode = 255

        def terminate(self):
            pytest.fail("an already-exited SSH process must not be terminated")

    install = tmp_path / "game"
    install.mkdir()
    commands, tunnels, posts, _openapi_requests = _fake_transport(
        monkeypatch, tunnel_type=DeadTunnel
    )

    receipt = _call(tmp_path, install, tmp_path / "out")

    assert receipt["status"] == "error"
    assert "SSH tunnel exited" in receipt["reason"]
    assert receipt["tunnelExitCode"] == 255
    assert posts == []
    assert receipt["remoteEvidencePreserved"] is True
    assert len(commands) == 2  # mkdir and input rsync only
    assert tunnels[0].terminated is False


def test_failed_output_transfer_keeps_local_partial_and_remote_evidence(
    tmp_path, monkeypatch
):
    install = tmp_path / "game"
    install.mkdir()
    _commands, tunnels, _posts, _openapi_requests = _fake_transport(
        monkeypatch, output_status=23
    )

    receipt = _call(tmp_path, install, tmp_path / "out")

    assert receipt["status"] == "error"
    assert receipt["outputRsyncStatus"] == 23
    assert Path(receipt["localPartialOutputDir"]).is_dir()
    assert receipt["remoteEvidencePreserved"] is True
    assert receipt["remoteCleanup"] == "not-performed"
    assert tunnels[0].terminated is True


def test_missing_project_version_is_not_reported_as_complete(tmp_path, monkeypatch):
    install = tmp_path / "game"
    install.mkdir()
    _fake_transport(monkeypatch, version_file=False)

    receipt = _call(tmp_path, install, tmp_path / "out")

    assert receipt["status"] == "error"
    assert receipt["outputRsyncStatus"] == 0
    assert receipt["hasProjectVersion"] is False
    assert "ProjectVersion.txt is absent" in receipt["reason"]
    assert Path(receipt["localAttemptOutputDir"]).is_dir()


def test_reuses_existing_remote_input_path_under_configured_root(tmp_path, monkeypatch):
    install = tmp_path / "game"
    install.mkdir()
    commands, _tunnels, _posts, _openapi_requests = _fake_transport(monkeypatch)

    receipt = unity_remote.export_unity_project_remote(
        install,
        tmp_path / "out",
        ssh_target="root@100.94.174.206",
        remote_root="/root/Workspaces/tvs-assetripper-full-20261003",
        remote_input_path="/root/Workspaces/tvs-assetripper-full-20261003/input",
        ssh_host_key_alias="100.94.174.206",
        server_port=18085,
        load_timeout=10,
        export_timeout=20,
        startup_timeout=2,
    )

    assert receipt["status"] == "complete"
    assert receipt["remoteInputPath"] == "/root/Workspaces/tvs-assetripper-full-20261003/input"
    assert receipt["reusedRemoteInputPath"] is True
    assert receipt["remoteInputCheckStatus"] == 0
    assert receipt["inputStagingMode"] == "reuse-existing-read-only"
    assert receipt["inputRsyncStatus"] is None
    assert receipt["remoteOutputPath"].startswith(receipt["remoteRunRoot"] + "/")
    ssh_commands = [argv for argv, _kwargs in commands if argv[0] == "ssh"]
    assert len(ssh_commands) == 1
    assert "test -d -- " not in ssh_commands[0][-1]
    assert f"test -d {shlex.quote(receipt['remoteInputPath'])}" in ssh_commands[0][-1]
    rsync_commands = [argv for argv, _kwargs in commands if argv[0] == "rsync"]
    assert len(rsync_commands) == 1  # only pull the export; never rewrite reused input


def test_reuses_verified_loaded_assetripper_session_without_loading_twice(
    tmp_path, monkeypatch
):
    install = tmp_path / "game"
    install.mkdir()
    commands, tunnels, posts, _openapi_requests = _fake_transport(monkeypatch)

    receipt = unity_remote.export_unity_project_remote(
        install,
        tmp_path / "out",
        ssh_target="root@149.130.219.117",
        remote_root="/root/Workspaces/tvs-assetripper-full-20261003",
        remote_input_path="/root/Workspaces/tvs-assetripper-full-20261003/input",
        ssh_host_key_alias="100.94.174.206",
        server_port=18085,
        load_timeout=10,
        export_timeout=20,
        startup_timeout=2,
        reuse_loaded_session=True,
    )

    assert receipt["status"] == "complete"
    assert receipt["reuseLoadedSession"] is True
    assert receipt["preloadedSessionVerified"] is True
    assert receipt["preloadedSessionEvidence"] == {
        "pid": "3366680",
        "inputPath": "/root/Workspaces/tvs-assetripper-full-20261003/input",
        "logPath": "/root/Workspaces/tvs-assetripper-full-20261003/AssetRipper.log",
    }
    assert receipt["loadSkipped"] is True
    assert receipt["loadStatus"] is None
    assert [url.rsplit("/", 1)[-1] for url, _fields, _timeout in posts] == [
        "UnityProject"
    ]
    assert posts[0][1] == {"Path": receipt["remoteOutputPath"]}
    ssh_commands = [argv[-1] for argv, _kwargs in commands if argv[0] == "ssh"]
    assert len(ssh_commands) == 2  # isolated run setup plus preloaded-session proof
    verification = next(
        command
        for command in ssh_commands
        if "AGENTDECOMPILE_VERIFY_PRELOADED_SESSION" in command
    )
    assert "3366680" not in verification  # pid is read from the remote pid file
    assert "Finished processing assets" in verification
    assert "Attempting to read files from" in verification
    assert "test -d /root/Workspaces/tvs-assetripper-full-20261003/input" in verification
    assert "test -d --" not in verification
    assert "--headless --port 18085" in verification
    assert len(tunnels) == 1 and tunnels[0].terminated is True


def test_preloaded_session_verification_failure_never_exports(
    tmp_path, monkeypatch
):
    install = tmp_path / "game"
    install.mkdir()
    _commands, tunnels, posts, _openapi_requests = _fake_transport(
        monkeypatch, verify_status=1
    )

    receipt = unity_remote.export_unity_project_remote(
        install,
        tmp_path / "out",
        ssh_target="root@149.130.219.117",
        remote_root="/root/Workspaces/tvs-assetripper-full-20261003",
        remote_input_path="/root/Workspaces/tvs-assetripper-full-20261003/input",
        ssh_host_key_alias="100.94.174.206",
        server_port=18085,
        reuse_loaded_session=True,
    )

    assert receipt["status"] == "error"
    assert "preloaded AssetRipper session verification failed" in receipt["reason"]
    assert receipt["preloadedSessionVerified"] is False
    assert receipt["remoteEvidencePreserved"] is True
    assert posts == []
    assert len(tunnels) == 1 and tunnels[0].terminated is True


def test_loaded_session_reuse_requires_an_explicit_remote_input_path(
    tmp_path,
):
    install = tmp_path / "game"
    install.mkdir()

    with pytest.raises(ValueError, match="requires remote_input_path"):
        unity_remote.export_unity_project_remote(
            install,
            tmp_path / "out",
            ssh_target="root@host",
            remote_root="/srv/tvs",
            reuse_loaded_session=True,
        )


def test_remote_input_path_outside_root_is_rejected(tmp_path):
    install = tmp_path / "game"
    install.mkdir()

    with pytest.raises(ValueError, match="strictly below remote_root"):
        unity_remote.export_unity_project_remote(
            install,
            tmp_path / "out",
            ssh_target="root@host",
            remote_root="/srv/tvs",
            remote_input_path="/srv/other/input",
        )


def test_remote_input_path_cannot_overlap_reserved_run_outputs(tmp_path):
    install = tmp_path / "game"
    install.mkdir()

    with pytest.raises(ValueError, match="reserved remote runs directory"):
        unity_remote.export_unity_project_remote(
            install,
            tmp_path / "out",
            ssh_target="root@host",
            remote_root="/srv/tvs",
            remote_input_path="/srv/tvs/runs/input",
        )


def test_failed_remote_directory_setup_does_not_claim_remote_evidence(
    tmp_path, monkeypatch
):
    install = tmp_path / "game"
    install.mkdir()
    _fake_transport(monkeypatch, mkdir_status=1)

    receipt = _call(tmp_path, install, tmp_path / "out")

    assert receipt["status"] == "error"
    assert receipt["mkdirStatus"] == 1
    assert receipt["remoteEvidencePreserved"] is False


@pytest.mark.parametrize(
    ("ssh_target", "remote_root", "server_port"),
    [
        ("root@2001:db8::1", "/srv/tvs", 18085),
        ("root@host;touch /tmp/pwned", "/srv/tvs", 18085),
        ("root@host", "/srv/tvs/../../tmp", 18085),
        ("root@host", "/srv/tvs", 8080),
        ("root@host", "/srv/tvs", 5174),
    ],
)
def test_rejects_ipv6_shell_metacharacters_traversal_and_protected_ports(
    tmp_path, ssh_target, remote_root, server_port
):
    install = tmp_path / "game"
    install.mkdir()

    with pytest.raises(ValueError):
        unity_remote.export_unity_project_remote(
            install,
            tmp_path / "out",
            ssh_target=ssh_target,
            remote_root=remote_root,
            server_port=server_port,
        )


def test_host_key_alias_rejects_shell_metacharacters(tmp_path):
    install = tmp_path / "game"
    install.mkdir()

    with pytest.raises(ValueError, match="hostname or IPv4 address"):
        unity_remote.export_unity_project_remote(
            install,
            tmp_path / "out",
            ssh_target="root@host",
            remote_root="/srv/tvs",
            ssh_host_key_alias="100.94.174.206;touch",
        )


def test_refuses_local_output_nested_in_the_game_input(tmp_path):
    install = tmp_path / "game"
    install.mkdir()

    with pytest.raises(ValueError, match="must not be inside install_root"):
        unity_remote.export_unity_project_remote(
            install,
            install / "recovered",
            ssh_target="root@host",
            remote_root="/srv/tvs",
        )


def test_recovery_cli_exposes_remote_ipv4_options(tmp_path):
    args = build_parser().parse_args(
        [
            "recover",
            str(tmp_path / "game"),
            "--unity-only",
            "--unity-project-out",
            str(tmp_path / "project"),
            "--unity-assetripper-remote-host",
            "root@149.130.219.117",
            "--unity-assetripper-remote-root",
            "/root/Workspaces/tvs-assetripper-full-20261003",
            "--unity-assetripper-remote-input",
            "/root/Workspaces/tvs-assetripper-full-20261003/input",
            "--unity-assetripper-remote-reuse-loaded",
            "--unity-assetripper-remote-port",
            "18085",
            "--unity-assetripper-ssh-host-key-alias",
            "100.94.174.206",
        ]
    )

    config = unity_config_kwargs(args)

    assert config["unity_only"] is True
    assert config["unity_assetripper_remote_host"] == "root@149.130.219.117"
    assert config["unity_assetripper_remote_root"] == "/root/Workspaces/tvs-assetripper-full-20261003"
    assert config["unity_assetripper_remote_input"] == "/root/Workspaces/tvs-assetripper-full-20261003/input"
    assert config["unity_assetripper_remote_input"] == (
        "preloaded-session::/root/Workspaces/tvs-assetripper-full-20261003/input"
    )
    assert config["unity_assetripper_remote_port"] == 18085
    assert config["unity_assetripper_ssh_host_key_alias"] == "100.94.174.206"
