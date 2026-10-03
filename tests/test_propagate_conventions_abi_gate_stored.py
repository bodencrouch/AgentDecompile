"""U70: the ABI gate also holds for stored rows and for the K2 shapes seen live.

The defect was stored ``func_convention_derived`` rows (K2 Mac, binary 19), so one
test drives ``apply_rows=True``. The others pin the XBE-into-PE refusal, which is
the one rule that can drop K2 Windows rows, and a Mach-O-to-Mach-O transfer, which
shows the gate compares ABI facts rather than favouring Windows.
"""

from __future__ import annotations

import sqlite3

import pytest

from agentdecompile_recovery.corpus import migrations
from agentdecompile_recovery.corpus import propagate_conventions as pc

pytestmark = pytest.mark.unit

RECIPIENT = 1
DONOR = 2
ADDR = 0x2000
LID = 91
RAW = b"\x55\x8b\xec\x90\xc2\x08\x00"  # ends in ``ret 8``

WIN_PE = ("win", "Portable Executable (PE)", "x86", 32, "x86:LE:32:default")
XBOX_XBE = ("xbox", "Xbox Executable Format (XBE)", "x86", 32, "x86:LE:32:default")
MAC_MACHO = ("mac", "Mac OS X Mach-O", "x86", 32, "x86:LE:32:default")


def _store(recipient, donor, cc, *, canonical=False):
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    if canonical:
        migrations.apply_pending(con)
        for bid, facts in ((RECIPIENT, recipient), (DONOR, donor)):
            con.execute(
                "INSERT INTO binary(id,repo_path,slug,game,platform,format,arch,bits,language_id)"
                " VALUES (?,?,?,'K2',?,?,?,?,?)", (bid, f'/{bid}', str(bid), *facts))
        con.execute("INSERT INTO logical_function(id) VALUES (?)", (LID,))
        for bid, conv in ((RECIPIENT, "unknown"), (DONOR, cc)):
            con.execute("INSERT INTO identity(logical_id,binary_id,addr) VALUES (?,?,?)", (LID, bid, ADDR))
            con.execute("INSERT INTO func(binary_id,addr,size,calling_convention,is_thunk,n_instr)"
                        " VALUES (?,?,?,?,0,3)", (bid, ADDR, len(RAW), conv))
    else:
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
        con.execute("INSERT INTO binary VALUES (?,?,?,?,?,?,?)", (DONOR, "K2", *donor))
        for bid, conv in ((RECIPIENT, "unknown"), (DONOR, cc)):
            con.execute("INSERT INTO identity VALUES (?,?,?)", (LID, bid, ADDR))
            con.execute("INSERT INTO func VALUES (?,?,?,?,0,3)", (bid, ADDR, len(RAW), conv))
    return con


def _derive(con, **kw):
    return pc.derive_conventions(con, RECIPIENT, RAW, lambda addr: 0, game="K2", **kw)


def test_refused_transfer_writes_no_stored_row() -> None:
    con = _store(MAC_MACHO, WIN_PE, "__thiscall", canonical=True)
    out = _derive(con, apply_rows=True)
    assert out["stats"]["skipped_cross_abi"] == 1
    assert con.execute("SELECT COUNT(*) FROM func_convention_derived").fetchone()[0] == 0


def test_windows_transfer_is_stored() -> None:
    con = _store(WIN_PE, WIN_PE, "__thiscall", canonical=True)
    _derive(con, apply_rows=True)
    stored = con.execute(
        "SELECT deco_class, stack_bytes, fastcall_n, class_source FROM func_convention_derived"
    ).fetchall()
    assert [tuple(r) for r in stored] == [("ecx", 8, 16, "same_game")]


def test_xbe_donor_into_pe_recipient_is_refused() -> None:
    out = _derive(_store(WIN_PE, XBOX_XBE, "__thiscall"))
    assert out["rows"] == []
    assert out["stats"]["skipped_cross_abi"] == 1


def test_macho_to_macho_transfer_is_kept() -> None:
    out = _derive(_store(MAC_MACHO, MAC_MACHO, "__cdecl"))
    assert [r[2] for r in out["rows"]] == ["stack"]
    assert "skipped_cross_abi" not in out["stats"]
