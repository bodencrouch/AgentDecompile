"""Thread-confined session wrapper for the gnsdk ABI."""

import ctypes as c
from dataclasses import dataclass
from typing import Optional

from . import _abi
from ._lib import load
from .errors import GnsdkError, Status


@dataclass(frozen=True)
class Version:
    abi_major: int
    abi_minor: int
    abi_patch: int
    ghidra_version: str
    source: str


def _text(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("utf-8", "replace")


def _check(status: int, operation: str, allowed: tuple[int, ...] = ()) -> int:
    if status == Status.OK or status in allowed:
        return status
    raise GnsdkError(status, operation)


class Session:
    """One non-thread-safe, raw-image gnsdk session; use as a context manager."""

    def __init__(self, sleigh_home: str, language: str):
        self._lib = load()
        info = _abi.sized(_abi.VersionInfo())
        _check(self._lib.gnsdk_version(c.byref(info)), "gnsdk_version")
        if info.abi_major != _abi.ABI_MAJOR:
            raise RuntimeError(f"gnsdk ABI major mismatch: Python {_abi.ABI_MAJOR}, library {info.abi_major}")
        init = _abi.sized(_abi.InitOptions())
        init.sleigh_home = sleigh_home.encode()
        _check(self._lib.gnsdk_init(c.byref(init)), "gnsdk_init")
        options = _abi.sized(_abi.SessionOptions())
        options.language_id = language.encode()
        self._handle = _abi.SessionHandle()
        _check(self._lib.gnsdk_session_create(c.byref(options), c.byref(self._handle)), "gnsdk_session_create")

    def __enter__(self) -> "Session":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._handle.value:
            _check(self._lib.gnsdk_session_destroy(self._handle), "gnsdk_session_destroy")
            self._handle = _abi.SessionHandle()

    def load_image(self, image: bytes, base: int, name: Optional[str] = None) -> None:
        if not image:
            raise ValueError("image must not be empty")
        storage = (c.c_uint8 * len(image)).from_buffer_copy(image)
        desc = _abi.sized(_abi.ImageDesc())
        desc.bytes = c.cast(storage, c.POINTER(c.c_uint8))
        desc.len = len(image)
        desc.base = base
        desc.name = name.encode() if name else None
        _check(self._lib.gnsdk_session_load_image(self._handle, c.byref(desc)), "gnsdk_session_load_image")

    def decompile(self, address: int, *, deadline_ms: int = 0, tokens: bool = False) -> str:
        options = _abi.sized(_abi.DecompileOptions())
        options.deadline_ms = deadline_ms
        options.want_tokens = int(tokens)
        result = _abi.sized(_abi.DecompileOut())
        status = self._lib.gnsdk_decompile(self._handle, address, c.byref(options), c.byref(result))
        try:
            _check(status, "gnsdk_decompile", (Status.OK_WARNINGS, Status.PARTIAL_UNSUPPORTED))
            return c.string_at(result.c_text.data, result.c_text.len).decode("utf-8", "replace") if result.c_text.data else ""
        finally:
            self._lib.gnsdk_buf_free(c.byref(result.c_text))
            self._lib.gnsdk_buf_free(c.byref(result.tokens))
            self._lib.gnsdk_buf_free(c.byref(result.warnings))


def capabilities() -> int:
    return int(load().gnsdk_capabilities())


def version() -> Version:
    lib = load()
    info = _abi.sized(_abi.VersionInfo())
    _check(lib.gnsdk_version(c.byref(info)), "gnsdk_version")
    return Version(info.abi_major, info.abi_minor, info.abi_patch, _text(bytes(info.ghidra_version)), _text(bytes(info.source)))
