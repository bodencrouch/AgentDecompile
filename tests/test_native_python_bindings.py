import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "native" / "python"))

from gnsdk.errors import Status
from gnsdk import _lib
from gnsdk.session import Session, version


def test_status_values_match_conformance_table():
    table = json.loads((ROOT / "native" / "conformance" / "status_codes.json").read_text())["status"]
    assert {f"GNSDK_{status.name}": status.value for status in Status} == table


def test_loader_reports_all_candidates(monkeypatch):
    monkeypatch.setenv("GNSDK_LIBRARY_PATH", "/definitely/not/libgnsdk.so")
    with pytest.raises(OSError, match="tried:.*definitely/not/libgnsdk.so"):
        _lib.load()


def test_shared_library_raw_image_round_trip(monkeypatch):
    library = os.environ.get("GNSDK_SHARED_LIBRARY")
    sleigh_home = os.environ.get("GNSDK_SLEIGH_HOME")
    if not library or not sleigh_home:
        pytest.skip("set GNSDK_SHARED_LIBRARY and GNSDK_SLEIGH_HOME for native integration")
    monkeypatch.setenv("GNSDK_LIBRARY_PATH", library)
    info = version()
    assert info.abi_major == 0
    # push rbp; mov rbp,rsp; xor eax,eax; pop rbp; ret
    with Session(sleigh_home, "x86:LE:64:default") as session:
        session.load_image(b"\x55\x48\x89\xe5\x31\xc0\x5d\xc3", 0x400000, "ctypes-e2e")
        assert session.decompile(0x400000, deadline_ms=5000)
