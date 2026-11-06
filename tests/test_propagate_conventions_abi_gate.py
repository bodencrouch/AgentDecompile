"""U70: calling-convention donors transfer only between builds that share the ABI.

The donor pool for ``derive_conventions`` must match on object format, OS family,
arch, bits, endianness and the this-passing convention. A mismatch is recorded as
``skipped_cross_abi``; a donor or recipient whose ABI facts are missing is recorded
as ``skipped_unknown_abi``. Neither case writes a row.
"""

from __future__ import annotations

import sqlite3

import pytest

from agentdecompile_recovery.corpus import propagate_conventions as pc

pytestmark = pytest.mark.unit

RECIPIENT = 1
DONOR = 2
ADDR = 0x1000
LID = 77

# Shapes copied from the live ``binary`` table (both naming schemes appear there).
WIN_PE = ("win", "Portable Executable (PE)", "x86", 32, "x86:LE:32:default")
WIN_PE_ALT = ("windows", "PE", "x86", 32, None)
MAC_MACHO = ("mac", "Mac OS X Mach-O", "x86", 32, "x86:LE:32:default")
ANDROID_ARM = ("android", "Executable and Linking Format (ELF)", "ARM", 32, "ARM:LE:32:v8")
UNKNOWN_PLATFORM_PE = (None, "Portable Executable (PE)", "x86", 32, "x86:LE:32:default")

# Body ends in ``ret 4`` so the recipient always has a popped-bytes reading.
RAW = b"\x55\x8b\xec\x90\xc2\x04\x00"


def _store(recipient, donors):
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(
        """
        CREATE TABLE binary (id INTEGER PRIMARY KEY, game TEXT, platform TEXT,
                             format TEXT, arch TEXT, bits INTEGER, language_id TEXT);
        CREATE TABLE identity (logical_id INTEGER, binary_id INTEGER, addr INTEGER);
        CREATE TABLE func (binary_id INTEGER, addr INTEGER, size INTEGER,
                           calling_convention TEXT, is_thunk INTEGER, n_instr INTEGER);
        """
    )
    con.execute("INSERT INTO binary VALUES (?,?,?,?,?,?,?)", (RECIPIENT, "K2", *recipient))
    con.execute("INSERT INTO identity VALUES (?,?,?)", (LID, RECIPIENT, ADDR))
    con.execute("INSERT INTO func VALUES (?,?,?,?,0,3)", (RECIPIENT, ADDR, len(RAW), "unknown"))
    for i, (abi, cc) in enumerate(donors):
        bid = DONOR + i
        con.execute("INSERT INTO binary VALUES (?,?,?,?,?,?,?)", (bid, "K2", *abi))
        con.execute("INSERT INTO identity VALUES (?,?,?)", (LID, bid, ADDR))
        con.execute("INSERT INTO func VALUES (?,?,?,?,0,3)", (bid, ADDR, 16, cc))
    return con


def _derive(con):
    return pc.derive_conventions(con, RECIPIENT, RAW, lambda addr: 0, game="K2")


def test_windows_to_windows_transfer_is_kept() -> None:
    out = _derive(_store(WIN_PE, [(WIN_PE, "__thiscall")]))
    assert out["rows"] == [(RECIPIENT, ADDR, "ecx", 4, 12, "same_game", "ret_imm")]
    assert "skipped_cross_abi" not in out["stats"]
    assert "skipped_unknown_abi" not in out["stats"]


def test_windows_to_windows_transfer_survives_both_naming_schemes() -> None:
    out = _derive(_store(WIN_PE, [(WIN_PE_ALT, "__thiscall")]))
    assert [r[2] for r in out["rows"]] == ["ecx"]


def test_windows_donor_into_mac_recipient_is_refused() -> None:
    out = _derive(_store(MAC_MACHO, [(WIN_PE, "__thiscall")]))
    assert out["rows"] == []
    assert out["stats"]["skipped_cross_abi"] == 1


def test_arm_elf_thiscall_label_into_windows_recipient_is_refused() -> None:
    out = _derive(_store(WIN_PE, [(ANDROID_ARM, "__thiscall")]))
    assert out["rows"] == []
    assert out["stats"]["skipped_cross_abi"] == 1


def test_donor_with_unknown_platform_is_refused() -> None:
    out = _derive(_store(WIN_PE, [(UNKNOWN_PLATFORM_PE, "__thiscall")]))
    assert out["rows"] == []
    assert out["stats"]["skipped_unknown_abi"] == 1


def test_recipient_with_unknown_platform_is_refused() -> None:
    out = _derive(_store(UNKNOWN_PLATFORM_PE, [(WIN_PE, "__thiscall")]))
    assert out["rows"] == []
    assert out["stats"]["skipped_unknown_abi"] == 1


def test_incompatible_donor_neither_hides_nor_conflicts_with_a_compatible_one() -> None:
    out = _derive(_store(WIN_PE, [(ANDROID_ARM, "__cdecl"), (WIN_PE, "__thiscall")]))
    assert [r[2] for r in out["rows"]] == ["ecx"]
    assert "class_conflict" not in out["stats"]


def test_abi_key_names_the_this_passing_convention() -> None:
    assert pc.abi_key(*WIN_PE)[-1] == "ecx"
    assert pc.abi_key(*WIN_PE) == pc.abi_key(*WIN_PE_ALT)
    assert pc.abi_key(*MAC_MACHO)[-1] == "stack"
    # ARM has no ecx/stack this-passing distinction: the fact is unknown, not guessed.
    assert pc.abi_key(*ANDROID_ARM)[-1] is None
    assert None in pc.abi_key(*UNKNOWN_PLATFORM_PE)
