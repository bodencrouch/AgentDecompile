"""Native library discovery and ABI signature configuration."""

import ctypes as c
import ctypes.util
import os
from pathlib import Path

from . import _abi


def candidate_paths() -> list[str]:
    paths: list[str] = []
    explicit = os.environ.get("GNSDK_LIBRARY_PATH")
    if explicit:
        paths.append(explicit)
    local = Path(__file__).resolve().parent / "libgnsdk.so"
    paths.append(str(local))
    found = ctypes.util.find_library("gnsdk")
    if found:
        paths.append(found)
    return paths


def load() -> c.CDLL:
    tried = candidate_paths()
    failures: list[str] = []
    for candidate in tried:
        try:
            library = c.CDLL(candidate)
            _configure(library)
            return library
        except OSError as error:
            failures.append(f"{candidate}: {error}")
    detail = "; ".join(failures) or "no loader candidates"
    raise OSError(f"could not load libgnsdk.so; tried: {detail}")


def _configure(lib: c.CDLL) -> None:
    lib.gnsdk_version.argtypes = [c.POINTER(_abi.VersionInfo)]
    lib.gnsdk_version.restype = c.c_int32
    lib.gnsdk_capabilities.argtypes = []
    lib.gnsdk_capabilities.restype = c.c_uint64
    lib.gnsdk_init.argtypes = [c.POINTER(_abi.InitOptions)]
    lib.gnsdk_init.restype = c.c_int32
    lib.gnsdk_session_create.argtypes = [c.POINTER(_abi.SessionOptions), c.POINTER(_abi.SessionHandle)]
    lib.gnsdk_session_create.restype = c.c_int32
    lib.gnsdk_session_load_image.argtypes = [_abi.SessionHandle, c.POINTER(_abi.ImageDesc)]
    lib.gnsdk_session_load_image.restype = c.c_int32
    lib.gnsdk_decompile.argtypes = [_abi.SessionHandle, c.c_uint64, c.POINTER(_abi.DecompileOptions), c.POINTER(_abi.DecompileOut)]
    lib.gnsdk_decompile.restype = c.c_int32
    lib.gnsdk_session_destroy.argtypes = [_abi.SessionHandle]
    lib.gnsdk_session_destroy.restype = c.c_int32
    lib.gnsdk_buf_free.argtypes = [c.POINTER(_abi.Buf)]
    lib.gnsdk_buf_free.restype = None
