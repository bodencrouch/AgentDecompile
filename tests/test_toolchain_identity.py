"""Per-build toolchain identity (P2-e, U54/U62).

Every tool here is a fake shell script in tmp that prints a version. No
real compiler, linker, assembler or Wine runs.
"""

from __future__ import annotations

import re
import stat
from pathlib import Path

import pytest

from agentdecompile_recovery.corpus import toolchain_identity as ti

HEX64 = re.compile(r"[0-9a-f]{64}")


def _script(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _native(tmp: Path, *, cc_version: str = "fakecc 1.0", cc_body: str = 'cat "$1" > "$2"; printf OBJ >> "$2"\n') -> dict:
    # "--version" prints the version; "<src> <out>" compiles.
    cc = _script(tmp / "bin" / "fakecc",
                 f'if [ "$1" = "--version" ]; then echo "{cc_version}"; exit 0; fi\n' + cc_body)
    ld = _script(tmp / "bin" / "fakeld", 'echo "fakeld 2.0" 1>&2\n')
    asm = _script(tmp / "bin" / "fakeas", 'echo "fakeas 3.0"\n')
    return {
        "compiler": ti.ToolSpec(path=cc, version_args=("--version",), flags=("-O2", "-c")),
        "linker": ti.ToolSpec(path=ld, version_args=("--version",), flags=("-static",)),
        "assembler": ti.ToolSpec(path=asm, version_args=("--version",)),
    }


def test_pinned_identity_is_64_hex_and_deterministic(tmp_path):
    tools = _native(tmp_path)
    a = ti.capture(tools, env={})
    b = ti.capture(tools, env={})
    assert a["state"] == "pinned"
    assert HEX64.fullmatch(a["identity_sha256"])
    assert a == b
    assert ti.canonical_bytes(a) == ti.canonical_bytes(b)
    assert ti.verify(a) is True


def test_identity_moves_with_binary_version_flags_and_env(tmp_path):
    base = ti.capture(_native(tmp_path / "a"), env={})["identity_sha256"]

    other_version = ti.capture(_native(tmp_path / "b", cc_version="fakecc 1.1"), env={})
    assert other_version["identity_sha256"] != base

    tools = _native(tmp_path / "c")
    tools["compiler"] = ti.ToolSpec(path=tools["compiler"].path, version_args=("--version",),
                                    flags=("-O1", "-c"))
    assert ti.capture(tools, env={})["identity_sha256"] != base

    # Same version text, different bytes: the exe hash moves the identity.
    tools = _native(tmp_path / "d")
    tools["compiler"].path.write_text(tools["compiler"].path.read_text() + "# patched\n")
    assert ti.capture(tools, env={})["identity_sha256"] != base

    assert ti.capture(_native(tmp_path / "e"), env={"CFLAGS": "-g"})["identity_sha256"] != base
    # Irrelevant env does not.
    assert ti.capture(_native(tmp_path / "f"), env={"HOME": "/x", "PWD": "/y"})["identity_sha256"] == base


def test_identity_is_relocatable_across_install_roots(tmp_path):
    a = ti.capture(_native(tmp_path / "one"), env={"INCLUDE": str(tmp_path / "one" / "inc")},
                   roots={"TOOLROOT": tmp_path / "one"})
    b = ti.capture(_native(tmp_path / "two" / "deeper"),
                   env={"INCLUDE": str(tmp_path / "two" / "deeper" / "inc")},
                   roots={"TOOLROOT": tmp_path / "two" / "deeper"})
    assert a["state"] == b["state"] == "pinned"
    assert a["identity_sha256"] == b["identity_sha256"]
    assert a["env"]["INCLUDE"] == "$TOOLROOT/inc"
    assert str(tmp_path) not in ti.canonical_bytes({k: a[k] for k in ("identity_sha256", "components", "env")}).decode()


def test_unused_role_is_explicit_and_hashed(tmp_path):
    tools = _native(tmp_path)
    with_asm = ti.capture(tools, env={})
    tools["assembler"] = None
    without = ti.capture(tools, env={})
    assert without["state"] == "pinned"
    assert without["components"]["assembler"] == {"role": "assembler", "used": False}
    assert without["identity_sha256"] != with_asm["identity_sha256"]


@pytest.mark.parametrize(
    "mutate, reason",
    [
        (lambda t, tmp: t.pop("compiler"), "compiler_role_missing"),
        (lambda t, tmp: t.__setitem__("compiler", ti.ToolSpec(path=tmp / "nope" / "cc")), "compiler_executable_missing"),
        (lambda t, tmp: t.__setitem__("linker", ti.ToolSpec(path=_script(tmp / "bin" / "badld", "exit 3\n"))),
         "linker_version_probe_failed"),
        (lambda t, tmp: t.__setitem__("compiler", ti.ToolSpec(
            path=_script(tmp / "bin" / "flaky", 'date +%s%N\n'), version_args=())),
         "compiler_version_output_unstable"),
    ],
)
def test_unpinned_never_fabricates(tmp_path, mutate, reason):
    tools = _native(tmp_path)
    mutate(tools, tmp_path)
    rec = ti.capture(tools, env={})
    assert rec["state"] == "unpinned"
    assert rec["reason"].startswith(reason)
    assert "identity_sha256" not in rec
    assert ti.verify(rec) is False


def test_timeout_is_unpinned_not_raised(tmp_path):
    tools = _native(tmp_path)
    tools["compiler"] = ti.ToolSpec(path=_script(tmp_path / "bin" / "slow", "sleep 5\necho x\n"))
    rec = ti.capture(tools, env={}, timeout=0.3)
    assert rec["state"] == "unpinned"
    assert rec["reason"].startswith("compiler_version_probe_failed")


def test_tampered_record_fails_verify(tmp_path):
    rec = ti.capture(_native(tmp_path), env={})
    rec["components"]["compiler"]["flags"] = ["-O0"]
    assert ti.verify(rec) is False
    assert ti.verify({"state": "pinned", "identity_sha256": "pinned:none"}) is False


# --- Wine-hosted MSVC ---------------------------------------------------------


def _wine_layout(tmp: Path, prefix_name: str = "pfx") -> tuple[Path, Path, dict]:
    prefix = tmp / prefix_name
    vc = prefix / "drive_c" / "VC7"
    for name, banner in (("cl.exe", "Microsoft 32-bit C/C++ Optimizing Compiler Version 13.10.3077"),
                         ("link.exe", "Microsoft Incremental Linker Version 7.10.3077"),
                         ("ml.exe", "Microsoft Macro Assembler Version 7.10.3077")):
        p = vc / "bin" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"MZ fake " + banner.encode())
    # The fake wine prints the banner embedded in the "exe" to stderr, as cl does.
    wine = _script(tmp / "wine-bin" / "wine",
                   'if [ "$1" = "--version" ]; then echo "wine-9.0"; exit 0; fi\n'
                   'tail -c +9 "$1" 1>&2; echo 1>&2; exit 2\n')
    tools = {
        "compiler": ti.ToolSpec(path=vc / "bin" / "cl.exe", flags=("/nologo", "/c", "/O2")),
        "linker": ti.ToolSpec(path=vc / "bin" / "link.exe", flags=("/NODEFAULTLIB",)),
        "assembler": ti.ToolSpec(path=vc / "bin" / "ml.exe"),
    }
    return prefix, wine, tools


def test_wine_msvc_records_prefix_relative_path_and_exe_hash(tmp_path):
    prefix, wine, tools = _wine_layout(tmp_path)
    rec = ti.capture(tools, env={"WINEPREFIX": str(prefix)}, wine=ti.WineHost(prefix=prefix, wine=wine))
    assert rec["state"] == "pinned", rec
    cl = rec["components"]["compiler"]
    assert cl["prefix_relative_path"] == "drive_c/VC7/bin/cl.exe"
    assert cl["exe_sha256"] == ti.sha256_file(tools["compiler"].path)
    assert rec["host"]["kind"] == "wine"
    assert HEX64.fullmatch(rec["host"]["wine_version_sha256"])
    # Nonzero exit with a banner is how cl answers; it is still a stable probe.
    assert "13.10.3077" in cl["version_text"]
    assert ti.verify(rec)


def test_wine_identity_is_the_same_under_a_moved_prefix(tmp_path):
    p1, w1, t1 = _wine_layout(tmp_path / "a", "prefix-a")
    p2, w2, t2 = _wine_layout(tmp_path / "b" / "c", "prefix-b")
    r1 = ti.capture(t1, env={"LIB": "Z:" + str(p1 / "drive_c" / "VC7" / "lib").replace("/", "\\")},
                    wine=ti.WineHost(prefix=p1, wine=w1))
    r2 = ti.capture(t2, env={"LIB": "Z:" + str(p2 / "drive_c" / "VC7" / "lib").replace("/", "\\")},
                    wine=ti.WineHost(prefix=p2, wine=w2))
    assert r1["identity_sha256"] == r2["identity_sha256"]
    assert r1["env"]["LIB"] == "$WINEPREFIX\\drive_c\\VC7\\lib"


def test_wine_exe_outside_prefix_is_unpinned(tmp_path):
    prefix, wine, tools = _wine_layout(tmp_path)
    stray = tmp_path / "elsewhere" / "cl.exe"
    stray.parent.mkdir()
    stray.write_bytes(tools["compiler"].path.read_bytes())
    tools["compiler"] = ti.ToolSpec(path=stray)
    rec = ti.capture(tools, env={}, wine=ti.WineHost(prefix=prefix, wine=wine))
    assert rec["state"] == "unpinned"
    assert rec["reason"].startswith("compiler_outside_wine_prefix")


def test_wine_cl_env_injection_moves_identity(tmp_path):
    prefix, wine, tools = _wine_layout(tmp_path)
    host = ti.WineHost(prefix=prefix, wine=wine)
    plain = ti.capture(tools, env={}, wine=host)
    injected = ti.capture(tools, env={"CL": "/Od"}, wine=host)
    assert plain["identity_sha256"] != injected["identity_sha256"]


# --- manifest adapter ---------------------------------------------------------


def test_manifest_toolchain_shape(tmp_path):
    rec = ti.capture(_native(tmp_path), env={})
    m = ti.manifest_toolchain(rec)
    assert m["state"] == "pinned" and m["identity_sha256"] == rec["identity_sha256"]
    assert m["flags"] == ["-O2", "-c"]
    tools = _native(tmp_path / "x")
    tools.pop("linker")
    un = ti.manifest_toolchain(ti.capture(tools, env={}))
    assert un == {"state": "unpinned", "reason": un["reason"]} and un["reason"].startswith("linker_role_missing")


# --- group + calibration ------------------------------------------------------


def test_group_single_identity_or_named_refusal(tmp_path):
    a = ti.capture(_native(tmp_path / "a"), env={})
    b = ti.capture(_native(tmp_path / "b"), env={})
    c = ti.capture(_native(tmp_path / "c", cc_version="fakecc 9"), env={})
    g = ti.group({"u1": a, "u2": b})
    assert g == {"state": "pinned", "identity_sha256": a["identity_sha256"], "members": ["u1", "u2"]}
    mixed = ti.group({"u1": a, "u3": c})
    assert mixed["state"] == "unpinned" and mixed["reason"].startswith("mixed_toolchain_identity")
    assert a["identity_sha256"] in mixed["reason"] and c["identity_sha256"] in mixed["reason"]
    tools = _native(tmp_path / "d")
    tools.pop("compiler")
    un = ti.group({"u1": a, "u4": ti.capture(tools, env={})})
    assert un["state"] == "unpinned" and "u4" in un["reason"]
    assert ti.group({})["reason"] == "group_empty"


def _cc(rec: dict) -> str:
    return rec["locations"]["compiler"]


def test_calibration_repeatable_object(tmp_path):
    rec = ti.capture(_native(tmp_path), env={})
    argv = [_cc(rec), "{src}", "{out}"]
    cal = ti.calibrate(rec, argv=argv, probe_source="int f(void){return 1;}\n")
    assert cal["state"] == "calibrated", cal
    assert cal["identity_sha256"] == rec["identity_sha256"]
    assert HEX64.fullmatch(cal["object_sha256"]) and cal["runs"] == 2
    again = ti.calibrate(rec, argv=argv, probe_source="int f(void){return 1;}\n",
                         expected_object_sha256=cal["object_sha256"])
    assert again["state"] == "calibrated"
    wrong = ti.calibrate(rec, argv=argv, probe_source="int f(void){return 1;}\n",
                         expected_object_sha256="0" * 64)
    assert wrong["state"] == "uncalibrated" and wrong["reason"].startswith("object_differs_from_expected")


def test_calibration_refuses_unbound_unstable_failed_or_unpinned(tmp_path):
    rec = ti.capture(_native(tmp_path / "ok"), env={})
    other = _script(tmp_path / "other" / "cc", 'cat "$1" > "$2"\n')
    r = ti.calibrate(rec, argv=[str(other), "{src}", "{out}"], probe_source="x")
    assert r["state"] == "uncalibrated" and r["reason"].startswith("probe_argv_not_bound")
    rec = ti.capture(_native(tmp_path / "u", cc_body='date +%s%N > "$2"\n'), env={})
    r = ti.calibrate(rec, argv=[_cc(rec), "{src}", "{out}"], probe_source="x")
    assert r["state"] == "uncalibrated" and r["reason"].startswith("object_nondeterministic")
    rec = ti.capture(_native(tmp_path / "f", cc_body="exit 1\n"), env={})
    r = ti.calibrate(rec, argv=[_cc(rec), "{src}", "{out}"], probe_source="x")
    assert r["state"] == "uncalibrated" and r["reason"].startswith("probe_compile_failed")
    tools = _native(tmp_path / "n")
    tools.pop("compiler")
    r = ti.calibrate(ti.capture(tools, env={}), argv=["true"], probe_source="x")
    assert r["state"] == "uncalibrated" and r["reason"].startswith("toolchain_unpinned")
    assert r["identity_sha256"] is None


def test_coff_timestamp_normalizer_masks_only_the_stamp():
    header = bytearray(20)
    header[0:2] = (0x014C).to_bytes(2, "little")
    header[4:8] = (0x12345678).to_bytes(4, "little")
    a = bytes(header) + b"body"
    header[4:8] = (0x9ABCDEF0).to_bytes(4, "little")
    b = bytes(header) + b"body"
    assert ti.coff_timestamp_normalizer(a) == ti.coff_timestamp_normalizer(b)
    assert ti.coff_timestamp_normalizer(b"\x00\x00" + b"x" * 30) == b"\x00\x00" + b"x" * 30


def test_calibration_with_normalizer_accepts_stamped_objects(tmp_path):
    # Writes an i386 COFF header whose TimeDateStamp comes from the nanosecond clock.
    body = ('printf "\\114\\001\\000\\000" > "$2"; date +%N | head -c 4 >> "$2"; '
            'printf "0123456789ab" >> "$2"; cat "$1" >> "$2"\n')
    rec = ti.capture(_native(tmp_path, cc_body=body), env={})
    argv = [_cc(rec), "{src}", "{out}"]
    raw = ti.calibrate(rec, argv=argv, probe_source="int x;\n", runs=3)
    norm = ti.calibrate(rec, argv=argv, probe_source="int x;\n", runs=3,
                        normalize=ti.coff_timestamp_normalizer)
    assert raw["state"] == "uncalibrated"
    assert norm["state"] == "calibrated" and norm["normalizer"] == "coff_timestamp"
