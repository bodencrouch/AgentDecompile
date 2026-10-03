"""Task11.6a source-only specifications: NOT run or collected in this packet.

The byte fixtures intentionally are not real ELF/Python runtime qualification.
Filesystem tests exercise actual private copies when separately authorized;
simulated mount/xattr/race seams do not qualify any host enforcement mechanism.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import time

import pytest

from agentdecompile_grid.worker import native_closure_profile as native


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def records(files=None, links=None):
    files = files or {
        "usr/bin/python3.12": (b"synthetic interpreter bytes", "executable"),
        "app/native_closure_entry.py": (b"# measured entry shim fixture\n", "data"),
        "app/src/example.py": (b"VALUE = 1\n", "data"),
        "tools/objdiff": (b"synthetic checker bytes", "executable"),
        "dev/null": (b"", "data"),
    }
    dirs = {"usr/lib/python3.12/lib-dynload", "app/vendor", "work", "dev"}
    links = links or {}
    for path in [*files, *links, *dirs]:
        parts = path.split("/")
        dirs.update("/".join(parts[:i]) for i in range(1, len(parts)))
    rows = [{"path": path, "type": "directory", "permission_class": "directory"} for path in dirs]
    rows += [{"path": path, "type": "file", "permission_class": permission,
              "size": len(data), "sha256": digest(data)} for path, (data, permission) in files.items()]
    rows += [{"path": path, "type": "symlink", "permission_class": "symlink", "target": target}
             for path, target in links.items()]
    return sorted(rows, key=lambda row: row["path"].encode()), files


def documents(rows):
    inventory = canonical({"schema": native.INVENTORY_SCHEMA, "entries": rows})
    by_path = {row["path"]: row for row in rows}
    sources = [row for row in rows if row["path"].startswith(("app/src/", "app/vendor/"))]
    profile = {
        "schema": native.PROFILE_SCHEMA, "profile_id": native.PROFILE_ID,
        "root_inventory_sha256": digest(inventory),
        "implementation_source_sha256": digest(canonical({"schema": native.SOURCE_SCHEMA, "entries": sources})),
        "interpreter": {"path": "/usr/bin/python3.12", "family": "cpython-3.12",
                        "sha256": by_path["usr/bin/python3.12"]["sha256"]},
        "entrypoint": {"path": "/app/native_closure_entry.py", "sha256": by_path["app/native_closure_entry.py"]["sha256"]},
        "checker": {"id": "synthetic-owner-selected-checker", "path": "/tools/objdiff",
                    "sha256": by_path["tools/objdiff"]["sha256"]},
        "launcher": {"family": "bubblewrap", "source_version": "0.11.0", "sha256": "a" * 64},
        "policy": {"id": native.POLICY_ID, "filter_sha256": "b" * 64},
        "environment": dict(native.ENVIRONMENT),
        "environment_sha256": digest(canonical(dict(native.ENVIRONMENT))),
        "supervisor_domain": "dedicated-trusted-uid",
        "work_filesystem": {"flags": ["noexec", "nosuid", "nodev"], "max_bytes": native.MAX_TOTAL_BYTES},
    }
    return canonical(profile), inventory


def load(profile, inventory):
    return native.load_profile(profile, inventory, expected_profile_sha256=digest(profile),
                               expected_inventory_sha256=digest(inventory))


def parse_rows(rows):
    raw = canonical({"schema": native.INVENTORY_SCHEMA, "entries": rows})
    return native.validate_inventory(raw, expected_sha256=digest(raw))


def test_positive_canonical_pins_and_describe_has_no_probe(monkeypatch):
    rows, _ = records(links={"usr/bin/python-alias": "python3.12"})
    profile_bytes, inventory_bytes = documents(rows)
    profile = load(profile_bytes, inventory_bytes)
    def forbidden(*args, **kwargs):
        raise AssertionError("describe must not probe")
    monkeypatch.setattr(os, "open", forbidden)
    monkeypatch.setattr(os, "stat", forbidden)
    description = native.describe_profile(profile)
    assert profile.inventory.canonical_bytes == inventory_bytes
    assert description["root_inventory_sha256"] == digest(inventory_bytes)
    assert description["launch_available"] is False
    assert description["current_admission_available"] is False


@pytest.mark.parametrize("mutation", ["profile_pin", "inventory_pin", "source", "runtime", "entrypoint", "environment", "policy", "unknown", "missing", "bool_limit"])
def test_profile_authority_and_schema_refusals(mutation):
    rows, _ = records()
    raw, inventory = documents(rows)
    document = json.loads(raw)
    if mutation == "profile_pin":
        with pytest.raises(native.ProfileRefused, match="profile_pin_mismatch"):
            native.load_profile(raw, inventory, expected_profile_sha256="f" * 64, expected_inventory_sha256=digest(inventory))
        return
    if mutation == "inventory_pin":
        document["root_inventory_sha256"] = "f" * 64
    elif mutation == "source":
        document["implementation_source_sha256"] = "f" * 64
    elif mutation == "runtime":
        document["interpreter"]["sha256"] = "f" * 64
    elif mutation == "entrypoint":
        document["entrypoint"]["path"] = "/work/untrusted.py"
    elif mutation == "environment":
        document["environment"]["PYTHONPATH"] = "/work"
    elif mutation == "policy":
        document["policy"]["id"] = "request-selected-policy"
    elif mutation == "unknown":
        document["caps"] = {"file": 2 ** 63}
    elif mutation == "missing":
        del document["launcher"]
    elif mutation == "bool_limit":
        document["work_filesystem"]["max_bytes"] = True
    with pytest.raises(native.ProfileRefused):
        load(canonical(document), inventory)


@pytest.mark.parametrize("raw", [b'{"schema":1,"schema":2}', b'{"entries":NaN}', b'{"entries":Infinity}',
                                  b'{"entries":1.0}', b'{"entries":"\\ud800"}', b'\xff', b'{}\n'])
def test_strict_encoding_duplicates_floats_and_canonical_bytes(raw):
    with pytest.raises(native.ProfileRefused):
        native.validate_inventory(raw, expected_sha256=digest(raw))


@pytest.mark.parametrize("path", ["/escape", "../escape", "a/../b", "a//b", "a/./b", "a\\b", "a\x00b",
                                   "/".join(["a"] * 25), "é" * 257])
def test_path_refusals(path):
    with pytest.raises(native.ProfileRefused):
        parse_rows([{"path": path, "type": "directory", "permission_class": "directory"}])


@pytest.mark.parametrize("name", ["cached.pyc", "cached.pyo", "hidden.pth", "sitecustomize.py", "usercustomize.py", "pyvenv.cfg", "import.zip"])
def test_prohibited_python_loader_files(name):
    rows, _ = records()
    rows.append({"path": "app/src/" + name, "type": "file", "permission_class": "data", "size": 0, "sha256": digest(b"")})
    with pytest.raises(native.ProfileRefused):
        parse_rows(sorted(rows, key=lambda row: row["path"].encode()))


@pytest.mark.parametrize("links", [{"escape": "../outside"}, {"dangling": "missing"},
                                   {"a": "b", "b": "a"}, {"app/loop": "/app"},
                                   {"app/loop": "/"}])
def test_symlink_escape_dangling_chain_and_directory_cycle(links):
    rows, _ = records(links=links)
    with pytest.raises(native.ProfileRefused):
        parse_rows(rows)


def test_inventory_duplicates_order_caps_and_bool_size():
    rows, _ = records()
    for invalid in (rows + [rows[-1]], list(reversed(rows)), rows * (native.MAX_ENTRIES // len(rows) + 1)):
        with pytest.raises(native.ProfileRefused):
            parse_rows(invalid)
    file = {"path": "a", "type": "file", "permission_class": "data", "sha256": "a" * 64}
    for size in (True, -1, native.MAX_FILE_BYTES + 1):
        with pytest.raises(native.ProfileRefused):
            parse_rows([{**file, "size": size}])
    with pytest.raises(native.ProfileRefused):
        parse_rows([{**file, "path": str(i), "size": native.MAX_FILE_BYTES} for i in range(5)])
    oversized = b" " * (native.MAX_MANIFEST_BYTES + 1)
    with pytest.raises(native.ProfileRefused, match="limit_exceeded"):
        native.validate_inventory(oversized, expected_sha256="a" * 64)


@pytest.fixture
def donor(tmp_path):
    root = tmp_path / "donor"
    parent = tmp_path / "private"
    root.mkdir(mode=0o700)
    parent.mkdir(mode=0o700)
    rows, files = records(links={"usr/bin/python-alias": "python3.12"})
    for row in rows:
        path = root / row["path"]
        if row["type"] == "directory":
            path.mkdir(mode=0o755)
        elif row["type"] == "file":
            path.write_bytes(files[row["path"]][0])
            path.chmod(0o555 if row["permission_class"] == "executable" else 0o644)
        else:
            path.symlink_to(row["target"])
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    parent_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    handles = []
    def capture():
        try:
            result = native.capture_private(load(*documents(rows)), donor_fd=root_fd,
                                            private_parent_fd=parent_fd, absolute_deadline=time.monotonic() + 90)
        except native.CaptureFailed as exc:
            if exc.partial is not None:
                handles.append(exc.partial)
            raise
        handles.append(result)
        return result
    yield root, parent, rows, capture
    for handle in handles:
        handle.close()
    os.close(root_fd)
    os.close(parent_fd)
    # Test-owned teardown only; production deliberately retains failed captures
    # for the future helper-exit/quarantine lifecycle.
    for directory, dirs, names in os.walk(parent):
        os.chmod(directory, 0o700)


def test_actual_copy_has_distinct_frozen_inodes_and_survives_donor_change(donor):
    root, parent, rows, capture = donor
    result = capture()
    captured = parent / result.allocation_name
    for row in rows:
        source = root / row["path"]
        target = captured / row["path"]
        if row["type"] == "file":
            assert source.read_bytes() == target.read_bytes()
            assert (source.stat().st_dev, source.stat().st_ino) != (target.stat().st_dev, target.stat().st_ino)
            assert stat.S_IMODE(target.stat().st_mode) == (0o555 if row["permission_class"] == "executable" else 0o444)
        elif row["type"] == "directory":
            assert stat.S_IMODE(target.stat().st_mode) == 0o555
        else:
            assert os.readlink(target) == row["target"]
    (root / "app/src/example.py").write_bytes(b"DONOR_CHANGED\n")
    assert (captured / "app/src/example.py").read_bytes() == b"VALUE = 1\n"
    assert result.identity.inventory_sha256 == digest(documents(rows)[1])
    assert not os.get_inheritable(result.root_fd)
    assert not os.get_inheritable(result.parent_fd)


@pytest.mark.parametrize("mutation", ["torn", "extra", "missing", "hardlink", "writable_exec", "setid", "special", "link_target"])
def test_real_donor_refusals_leave_only_owned_partial(donor, mutation):
    root, parent, rows, capture = donor
    source = root / "app/src/example.py"
    if mutation == "torn":
        source.write_bytes(b"VALUE = 2\n")
    elif mutation == "extra":
        (root / "extra").write_bytes(b"extra")
    elif mutation == "missing":
        source.unlink()
    elif mutation == "hardlink":
        os.link(source, root.parent / "outside-hardlink")
    elif mutation == "writable_exec":
        (root / "tools/objdiff").chmod(0o755)
    elif mutation == "setid":
        source.chmod(0o4644)
    elif mutation == "special":
        source.unlink()
        os.mkfifo(source)
    elif mutation == "link_target":
        (root / "usr/bin/python-alias").unlink()
        (root / "usr/bin/python-alias").symlink_to("/outside")
    with pytest.raises(native.CaptureFailed) as error:
        capture()
    assert type(error.value.partial) is native.OwnedAllocation
    assert (parent / error.value.partial.allocation_name).is_dir()
    assert root.exists()


def test_real_xattr_when_filesystem_supports_user_namespace(donor):
    root, parent, rows, capture = donor
    path = root / "app/src/example.py"
    try:
        os.setxattr(path, "user.harmless", b"data")
    except OSError as error:
        pytest.skip(f"filesystem user xattrs unavailable: {error}")
    result = capture()
    assert "user.harmless" not in os.listxattr(parent / result.allocation_name / "app/src/example.py")


def test_security_xattr_refuses_without_provisioning_capabilities(donor, monkeypatch):
    root, parent, rows, capture = donor
    inode = (root / "app/src/example.py").stat().st_ino
    original = os.listxattr
    def attributes(path, **kwargs):
        if isinstance(path, int) and os.fstat(path).st_ino == inode:
            return ["security.capability"]
        return original(path, **kwargs)
    monkeypatch.setattr(os, "listxattr", attributes)
    with pytest.raises(native.CaptureFailed, match="security/capability"):
        capture()


def test_same_device_mount_crossing_refuses_at_descriptor_seam(donor, monkeypatch):
    root, parent, rows, capture = donor
    inode = (root / "app/src/example.py").stat().st_ino
    original = native._mount_id
    def mounted(fd, budget):
        actual = original(fd, budget)
        return actual + 1 if os.fstat(fd).st_ino == inode else actual
    monkeypatch.setattr(native, "_mount_id", mounted)
    with pytest.raises(native.CaptureFailed, match="mount crossing"):
        capture()


def test_mutation_during_actual_read_is_rejected(donor, monkeypatch):
    root, parent, rows, capture = donor
    path = root / "app/src/example.py"
    inode = path.stat().st_ino
    original = os.read
    changed = False
    def racing(fd, size):
        nonlocal changed
        data = original(fd, size)
        if not changed and os.fstat(fd).st_ino == inode:
            changed = True
            path.write_bytes(b"VALUE = 2\n")
        return data
    monkeypatch.setattr(os, "read", racing)
    with pytest.raises(native.CaptureFailed, match="capture_integrity_failed"):
        capture()
    assert changed


def test_exclusive_collision_does_not_adopt_or_delete_another_allocation(donor, monkeypatch):
    root, parent, rows, capture = donor
    existing = parent / ("capture-" + "a" * 32)
    existing.mkdir()
    (existing / "sentinel").write_bytes(b"keep")
    monkeypatch.setattr(native.secrets, "token_hex", lambda count: "a" * 32)
    with pytest.raises(native.CaptureFailed) as error:
        capture()
    assert error.value.partial is None
    assert (existing / "sentinel").read_bytes() == b"keep"


@pytest.mark.parametrize("deadline", [False, float("nan"), float("inf"), -1.0])
def test_deadline_refusal_precedes_allocation(deadline, monkeypatch):
    rows, _ = records()
    profile = load(*documents(rows))
    def forbidden(*args, **kwargs):
        raise AssertionError("no allocation after invalid/expired deadline")
    monkeypatch.setattr(os, "mkdir", forbidden)
    with pytest.raises(native.ProfileRefused, match="deadline_exceeded"):
        native.capture_private(profile, donor_fd=-1, private_parent_fd=-1, absolute_deadline=deadline)


def test_cooperative_timeout_after_allocation_retains_partial(donor, monkeypatch):
    root, parent, rows, capture = donor
    real_clock = time.monotonic
    real_mkdir = os.mkdir
    expired = False
    def allocate(path, *args, **kwargs):
        nonlocal expired
        result = real_mkdir(path, *args, **kwargs)
        if str(path).startswith("capture-"):
            expired = True
        return result
    monkeypatch.setattr(os, "mkdir", allocate)
    monkeypatch.setattr(native.time, "monotonic", lambda: real_clock() + (100 if expired else 0))
    with pytest.raises(native.CaptureFailed, match="deadline_exceeded") as error:
        capture()
    assert type(error.value.partial) is native.OwnedAllocation
    assert error.value.partial.root_fd == -1
    assert (parent / error.value.partial.allocation_name).is_dir()
