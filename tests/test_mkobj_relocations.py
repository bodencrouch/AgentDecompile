"""mkobj relocation types per machine, and fail-closed call-target discovery.

objdump is faked at the ``subprocess.run`` boundary with listings in its
``-D -w -z -b binary`` shape, so no objdump runs. The objects are checked by
``coff_fixup_roundtrip``: placed at their origin they must reproduce the
region, and placed elsewhere every external rel32 must keep its absolute
target.
"""

from __future__ import annotations

import struct
import subprocess
from pathlib import Path

import pytest

from agentdecompile_recovery.corpus import coff_fixup_roundtrip as rt
from agentdecompile_recovery.corpus import mkobj
from agentdecompile_recovery.corpus.cli import main as corpus_main

pytestmark = pytest.mark.unit

I386 = mkobj.MACHINE["coff-i386"]
AMD64 = mkobj.MACHINE["coff-x86-64"]
ORIGIN_32 = 0x00401000
ORIGIN_64 = 0x140001000


def listing(insns: list[tuple[int, bytes, str]]) -> str:
    """objdump -D -w -z -b binary output for ``insns`` = [(offset, raw, text)]."""
    lines = ["", "x.bin:     file format binary", "", "",
             "Disassembly of section .data:", "", "0000000000000000 <.data>:"]
    for off, raw, text in insns:
        hexes = " ".join(f"{b:02x}" for b in raw)
        lines.append(f"{off:4x}:\t{hexes.ljust(21)}\t{text}")
    return "\n".join(lines) + "\n"


class FakeObjdump:
    def __init__(self, stdout: str = "", returncode: int = 0, missing: bool = False):
        self.stdout, self.returncode, self.missing = stdout, returncode, missing
        self.calls: list[list[str]] = []

    def __call__(self, argv, *args, **kwargs):
        self.calls.append(list(argv))
        if self.missing:
            raise FileNotFoundError(2, "No such file or directory", argv[0])
        return subprocess.CompletedProcess(argv, self.returncode, self.stdout, "objdump: error")


def region_file(tmp_path: Path, code: bytes) -> Path:
    raw = tmp_path / "raw.bin"
    raw.write_bytes(b"\x90" * 8 + code + b"\x90" * 8)
    return raw


def make(tmp_path: Path, code: bytes, fmt: str) -> Path:
    return mkobj.write_object(binary=region_file(tmp_path, code), offset=8, size=len(code),
                              name="F", output=tmp_path / "f.o", format=fmt)


# push; call +0x2000 (region-relative); pop; ret
CALL_OUT = b"\x55\xe8" + struct.pack("<i", 0x2000 - 6) + b"\x5d\xc3"


def call_out_listing(mnemonic: str, ret: str) -> str:
    return listing([(0, b"\x55", "push   %ebp"), (1, CALL_OUT[1:6], f"{mnemonic}   0x2000"),
                    (6, b"\x5d", "pop    %ebp"), (7, b"\xc3", ret)])


# ------------------------------------------------------------ relocation type


def test_build_object_writes_amd64_rel32_type() -> None:
    obj = mkobj.build_object(b"\xe8\0\0\0\0\xc3", "F", AMD64, {1: 0x40})
    parsed = rt.parse_object(obj)
    assert [r["type"] for r in parsed["relocations"]] == [0x0004]
    placed = rt.place(obj, ORIGIN_64, rt.mkobj_external_symbols(obj, ORIGIN_64))
    assert placed[1:5] == struct.pack("<i", 0x40 - 5)


def test_build_object_keeps_i386_rel32_type() -> None:
    obj = mkobj.build_object(b"\xe8\0\0\0\0\xc3", "_F", I386, {1: 0x40})
    assert [r["type"] for r in rt.parse_object(obj)["relocations"]] == [0x0014]


# ------------------------------------------------------------ decoder pipeline


@pytest.mark.parametrize("mnemonic,ret", [("call", "ret"), ("callq", "retq")])
def test_amd64_object_roundtrips_and_stays_relocatable(tmp_path, monkeypatch, mnemonic, ret) -> None:
    fake = FakeObjdump(call_out_listing(mnemonic, ret))
    monkeypatch.setattr(mkobj.subprocess, "run", fake)
    obj = make(tmp_path, CALL_OUT, "coff-x86-64").read_bytes()
    assert fake.calls and "i386:x86-64" in fake.calls[0]
    symbols = rt.mkobj_external_symbols(obj, ORIGIN_64)
    receipt = rt.roundtrip_region(CALL_OUT, obj, ORIGIN_64, symbols)
    assert receipt["refusal"] is None
    assert receipt["machine"] == "amd64"
    assert receipt["relocation_count"] == 1
    assert receipt["relocations"][0]["type"] == "IMAGE_REL_AMD64_REL32"
    assert receipt["byte_equal_at_origin"] is True
    moved = rt.check_replacement(CALL_OUT, obj, ORIGIN_64, symbols, rel32_sites=[2], delta=0x5000)
    assert moved["relocatable"] is True


def test_i386_backward_call_roundtrips(tmp_path, monkeypatch) -> None:
    code = b"\xe8" + struct.pack("<i", -0x105) + b"\xc3"
    monkeypatch.setattr(mkobj.subprocess, "run", FakeObjdump(listing(
        [(0, code[:5], "call   0xffffff00"), (5, b"\xc3", "ret")])))
    obj = make(tmp_path, code, "coff-i386").read_bytes()
    symbols = rt.mkobj_external_symbols(obj, ORIGIN_32)
    receipt = rt.roundtrip_region(code, obj, ORIGIN_32, symbols)
    assert receipt["relocation_count"] == 1 and receipt["byte_equal_at_origin"] is True
    assert rt.check_replacement(code, obj, ORIGIN_32, symbols, rel32_sites=[1], delta=-0x800)["relocatable"]


def test_internal_call_gets_no_relocation(tmp_path, monkeypatch) -> None:
    code = b"\xe8\x00\x00\x00\x00\xc3"
    monkeypatch.setattr(mkobj.subprocess, "run", FakeObjdump(listing(
        [(0, code[:5], "call   0x5"), (5, b"\xc3", "ret")])))
    obj = make(tmp_path, code, "coff-i386").read_bytes()
    assert rt.parse_object(obj)["relocations"] == []


# ------------------------------------------------------------ fail closed


@pytest.mark.parametrize("fmt", ["coff-i386", "coff-x86-64"])
def test_missing_objdump_refuses_instead_of_zero_relocations(tmp_path, monkeypatch, fmt) -> None:
    monkeypatch.setattr(mkobj.subprocess, "run", FakeObjdump(missing=True))
    with pytest.raises(ValueError, match="call_target_discovery_unavailable"):
        make(tmp_path, CALL_OUT, fmt)
    assert not (tmp_path / "f.o").exists()


def test_objdump_nonzero_exit_refuses(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mkobj.subprocess, "run", FakeObjdump(call_out_listing("call", "ret"), returncode=1))
    with pytest.raises(ValueError, match="call_target_discovery_unavailable"):
        make(tmp_path, CALL_OUT, "coff-i386")
    assert not (tmp_path / "f.o").exists()


def test_objdump_listing_that_does_not_cover_the_region_refuses(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mkobj.subprocess, "run", FakeObjdump(listing([(0, b"\x55", "push   %ebp")])))
    with pytest.raises(ValueError, match="decode_incomplete"):
        make(tmp_path, CALL_OUT, "coff-i386")


def test_undecodable_bytes_refuse(tmp_path, monkeypatch) -> None:
    code = b"\xe8\xff\xc3"
    monkeypatch.setattr(mkobj.subprocess, "run", FakeObjdump(listing(
        [(0, b"\xe8", "(bad)"), (1, b"\xff", "(bad)"), (2, b"\xc3", "ret")])))
    with pytest.raises(ValueError, match="undecodable_instruction"):
        make(tmp_path, code, "coff-i386")


def test_external_short_jump_refuses(tmp_path, monkeypatch) -> None:
    code = b"\x90\xeb\x7f"
    monkeypatch.setattr(mkobj.subprocess, "run", FakeObjdump(listing(
        [(0, b"\x90", "nop"), (1, b"\xeb\x7f", "jmp    0x82")])))
    with pytest.raises(ValueError, match="external_branch_unrelocatable"):
        make(tmp_path, code, "coff-i386")


def test_amd64_external_rip_relative_operand_refuses(tmp_path, monkeypatch) -> None:
    code = b"\x48\x8b\x05" + struct.pack("<i", 0x1000) + b"\xc3"
    monkeypatch.setattr(mkobj.subprocess, "run", FakeObjdump(listing(
        [(0, code[:7], "mov    0x1000(%rip),%rax        # 0x1007"), (7, b"\xc3", "ret")])))
    with pytest.raises(ValueError, match="rip_relative_unsupported"):
        make(tmp_path, code, "coff-x86-64")


def test_region_without_branch_or_rip_bytes_needs_no_decoder(tmp_path, monkeypatch) -> None:
    fake = FakeObjdump(missing=True)
    monkeypatch.setattr(mkobj.subprocess, "run", fake)
    for fmt in ("coff-i386", "coff-x86-64"):
        obj = make(tmp_path, b"\x55\x5d\xc3", fmt).read_bytes()
        assert rt.parse_object(obj)["relocations"] == []
    assert fake.calls == []


# ------------------------------------------------------------ callers see it


def test_main_and_corpus_cli_return_2_with_reason(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(mkobj.subprocess, "run", FakeObjdump(missing=True))
    raw = region_file(tmp_path, CALL_OUT)
    out = tmp_path / "cli.o"
    argv = ["--binary", str(raw), "--offset", "8", "--size", str(len(CALL_OUT)),
            "--name", "F", "-o", str(out), "--format", "coff-x86-64"]
    assert mkobj.main(argv) == 2
    assert "call_target_discovery_unavailable" in capsys.readouterr().err
    assert corpus_main(["mkobj", *argv]) == 2
    assert "call_target_discovery_unavailable" in capsys.readouterr().err
    assert not out.exists()
