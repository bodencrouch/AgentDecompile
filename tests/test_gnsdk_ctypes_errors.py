"""Dependency-free checks for the native Python ``gnsdk`` ctypes consumer."""

from __future__ import annotations

import ctypes as c
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

NATIVE_PYTHON = Path(__file__).resolve().parents[1] / "native" / "python"
if str(NATIVE_PYTHON) not in sys.path:
    sys.path.insert(0, str(NATIVE_PYTHON))

from gnsdk import _abi, _lib  # noqa: E402
from gnsdk.errors import GnsdkError, Status  # noqa: E402
from gnsdk.session import Session, version  # noqa: E402

pytestmark = pytest.mark.unit


class Fn:
    def __init__(self, impl):
        self.impl = impl
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self.impl(*args)


class FakeLib(SimpleNamespace):
    pass


def fake_library(*, abi_major: int = _abi.ABI_MAJOR, create_status: int = Status.OK) -> FakeLib:
    lib = FakeLib()

    def gnsdk_version(ptr):
        info = ptr._obj
        info.abi_major = abi_major
        info.abi_minor = 1
        info.abi_patch = 0
        info.ghidra_version = b"12.1.3"
        info.source = b"Ghidra_12.1.3_build"
        return Status.OK

    def gnsdk_session_create(_options, out):
        if create_status == Status.OK:
            out._obj.value = 0x1234
        return create_status

    lib.gnsdk_version = Fn(gnsdk_version)
    lib.gnsdk_capabilities = Fn(lambda: 1)
    lib.gnsdk_init = Fn(lambda _options: Status.OK)
    lib.gnsdk_session_create = Fn(gnsdk_session_create)
    lib.gnsdk_session_load_image = Fn(lambda _handle, _desc: Status.OK)
    lib.gnsdk_decompile = Fn(lambda _handle, _addr, _options, _out: Status.ENGINE_FAILURE)
    lib.gnsdk_session_destroy = Fn(lambda _handle: Status.OK)
    lib.gnsdk_buf_free = Fn(lambda _buf: None)
    return lib


def test_loader_error_lists_every_path_tried(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    explicit = tmp_path / "missing-libgnsdk.so"
    monkeypatch.setenv("GNSDK_LIBRARY_PATH", str(explicit))
    monkeypatch.setattr(_lib.ctypes.util, "find_library", lambda _name: "/also/missing/libgnsdk.so")
    with pytest.raises(OSError) as caught:
        _lib.load()
    message = str(caught.value)
    assert str(explicit) in message
    assert "libgnsdk.so" in message
    assert "/also/missing/libgnsdk.so" in message


def test_gnsdk_error_uses_status_names() -> None:
    assert "TIMEOUT (11)" in str(GnsdkError(Status.TIMEOUT, "decompile"))
    assert "UNKNOWN_STATUS (9999)" in str(GnsdkError(9999, "mystery"))


def test_session_refuses_abi_major_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("gnsdk.session.load", lambda: fake_library(abi_major=_abi.ABI_MAJOR + 1))
    with pytest.raises(RuntimeError, match="ABI major mismatch"):
        Session("/native/sleigh-home", "x86:LE:64:default")


def test_session_create_status_raises_named_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("gnsdk.session.load", lambda: fake_library(create_status=Status.INVALID_ARGUMENT))
    with pytest.raises(GnsdkError, match="gnsdk_session_create: INVALID_ARGUMENT"):
        Session("/native/sleigh-home", "bad")


def test_version_decodes_source_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("gnsdk.session.load", lambda: fake_library())
    observed = version()
    assert observed.abi_major == _abi.ABI_MAJOR
    assert observed.ghidra_version == "12.1.3"
    assert observed.source.startswith("Ghidra_12.1.3_build")


def test_struct_size_helper_sets_ctypes_size() -> None:
    options = _abi.sized(_abi.DecompileOptions())
    assert options.struct_size == c.sizeof(_abi.DecompileOptions)
