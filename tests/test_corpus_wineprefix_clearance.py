"""P0.3 wine-prefix clearance probe: fake server dirs, a real lock-holder child.

No Wine is started. The "live" case uses a separate helper process because
F_GETLK never reports locks held by the calling process.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest

from agentdecompile_recovery.corpus.wineprefix_clearance import server_dir_for, wineprefix_clearance

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux-only probe")

_HOLDER = textwrap.dedent(
    """
    import fcntl, os, sys
    fd = os.open(sys.argv[1], os.O_RDWR)
    fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB, 1, 0)  # Wine: F_WRLCK, byte 0, len 1
    sys.stdout.write("ready\\n"); sys.stdout.flush()
    sys.stdin.read()
    """
)


@pytest.fixture
def layout(tmp_path):
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    root = tmp_path / "wine-root"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    return prefix, root


def _make_server_dir(prefix, root, *, lock=True, socket=False):
    sdir = server_dir_for(prefix, server_root=root)
    sdir.mkdir(mode=0o700)
    sdir.chmod(0o700)
    if lock:
        (sdir / "lock").write_bytes(b"")
        (sdir / "lock").chmod(0o600)
    if socket:
        (sdir / "socket").write_bytes(b"")  # a leftover entry is enough for the layout check
    return sdir


def test_server_dir_name_follows_wine_hex_scheme(layout):
    prefix, root = layout
    st = os.stat(prefix)
    assert server_dir_for(prefix, server_root=root) == root / f"server-{st.st_dev:x}-{st.st_ino:x}"


def test_default_root_is_tmp_wine_uid(layout):
    prefix, _ = layout
    assert str(server_dir_for(prefix).parent) == f"/tmp/.wine-{os.getuid()}"


def test_absent_server_root_is_clear(layout, tmp_path):
    prefix, _ = layout
    result = wineprefix_clearance(prefix, server_root=tmp_path / "missing-root")
    assert result["state"] == "clear"
    assert result["evidence"]["reason"] == "server_root_absent"


def test_absent_server_dir_is_clear(layout):
    prefix, root = layout
    result = wineprefix_clearance(prefix, server_root=root)
    assert result["state"] == "clear"
    assert result["evidence"]["reason"] == "server_dir_absent"
    assert "server/request.c" in result["evidence"]["source"]


def test_unlocked_lock_without_socket_is_clear(layout):
    prefix, root = layout
    _make_server_dir(prefix, root)
    result = wineprefix_clearance(prefix, server_root=root)
    assert result["state"] == "clear"
    assert result["evidence"]["reason"] == "lock_unheld"


def test_held_lock_in_other_process_is_live_then_clear_after_exit(layout):
    prefix, root = layout
    sdir = _make_server_dir(prefix, root, socket=True)
    child = subprocess.Popen([sys.executable, "-c", _HOLDER, str(sdir / "lock")],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "ready"
        before = os.stat(sdir / "lock")
        result = wineprefix_clearance(prefix, server_root=root)
        assert result["state"] == "live"
        assert result["evidence"]["reason"] == "lock_held"
        assert result["evidence"]["lockHolderPid"] == child.pid
        after = os.stat(sdir / "lock")
        assert (before.st_ino, before.st_size, before.st_mtime_ns) == (after.st_ino, after.st_size, after.st_mtime_ns)
        assert child.poll() is None  # the probe never signals the holder
    finally:
        child.stdin.close()
        child.wait(timeout=10)
    (sdir / "socket").unlink()
    assert wineprefix_clearance(prefix, server_root=root)["state"] == "clear"


def test_unlocked_lock_with_leftover_socket_is_unknown(layout):
    prefix, root = layout
    _make_server_dir(prefix, root, socket=True)
    result = wineprefix_clearance(prefix, server_root=root)
    assert result["state"] == "unknown"
    assert result["evidence"]["reason"] == "socket_without_lock_holder"


def test_server_dir_without_lock_is_unknown(layout):
    prefix, root = layout
    _make_server_dir(prefix, root, lock=False)
    assert wineprefix_clearance(prefix, server_root=root)["state"] == "unknown"


@pytest.mark.parametrize("shape", ["server_dir_is_file", "server_dir_is_symlink", "lock_is_dir",
                                   "lock_is_symlink", "server_dir_group_readable", "root_is_symlink"])
def test_malformed_layout_is_unknown(layout, tmp_path, shape):
    prefix, root = layout
    sdir = server_dir_for(prefix, server_root=root)
    target = tmp_path / "elsewhere"
    target.mkdir(mode=0o700)
    target.chmod(0o700)
    probe_root = root
    if shape == "server_dir_is_file":
        sdir.write_bytes(b"")
    elif shape == "server_dir_is_symlink":
        sdir.symlink_to(target)
    elif shape == "lock_is_dir":
        _make_server_dir(prefix, root, lock=False)
        (sdir / "lock").mkdir()
    elif shape == "lock_is_symlink":
        _make_server_dir(prefix, root, lock=False)
        (target / "real-lock").write_bytes(b"")
        (sdir / "lock").symlink_to(target / "real-lock")
    elif shape == "server_dir_group_readable":
        _make_server_dir(prefix, root)
        sdir.chmod(0o750)
    elif shape == "root_is_symlink":
        probe_root = tmp_path / "root-link"
        probe_root.symlink_to(root)
        _make_server_dir(prefix, root)
    result = wineprefix_clearance(prefix, server_root=probe_root)
    assert result["state"] == "unknown", result


def test_foreign_owner_is_unknown(layout):
    prefix, root = layout
    _make_server_dir(prefix, root)
    result = wineprefix_clearance(prefix, server_root=root, uid=os.getuid() + 1)
    assert result["state"] == "unknown"


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permission bits")
def test_missing_permission_is_unknown(layout):
    prefix, root = layout
    sdir = _make_server_dir(prefix, root)
    sdir.chmod(0o000)
    try:
        result = wineprefix_clearance(prefix, server_root=root)
    finally:
        sdir.chmod(0o700)
    assert result["state"] == "unknown"
    assert result["evidence"]["reason"] == "lock_open_failed"


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permission bits")
def test_unreadable_server_root_is_unknown(layout):
    prefix, root = layout
    _make_server_dir(prefix, root)
    root.chmod(0o000)
    try:
        result = wineprefix_clearance(prefix, server_root=root)
    finally:
        root.chmod(0o700)
    assert result["state"] == "unknown"


def test_missing_or_relative_prefix_is_unknown(tmp_path):
    assert wineprefix_clearance(tmp_path / "gone", server_root=tmp_path)["state"] == "unknown"
    assert wineprefix_clearance("relative/prefix", server_root=tmp_path)["state"] == "unknown"
