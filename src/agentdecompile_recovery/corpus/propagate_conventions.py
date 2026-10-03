"""Recover calling-convention decoration for functions Ghidra left as ``unknown``.

Two sources: the terminating ``ret``/``ret imm16``, and same-game identity
donors collapsed to the ecx-vs-stack decoration class. Ambiguous cases are skipped.

A donor counts only when its build shares the recipient's ABI facts (U70): object
format, OS family, arch, bits, endianness and the this-passing convention. A
mismatch is refused as ``skipped_cross_abi``; missing facts on either side are
refused as ``skipped_unknown_abi`` and never assumed.
"""

from __future__ import annotations

import collections
import sqlite3
from contextlib import contextmanager
from itertools import count
from pathlib import Path

from .store import CONVENTION_TABLE_DDL, require_convention_schema

DECORATION_CLASS = {
    "__thiscall": "ecx",
    "__fastcall": "ecx",
    "__stdcall": "stack",
    "__cdecl": "stack",
}

_FORMAT_FAMILY = {
    "portable executable (pe)": "pe",
    "pe": "pe",
    "executable and linking format (elf)": "elf",
    "elf": "elf",
    "mac os x mach-o": "macho",
    "macho": "macho",
    "xbox executable format (xbe)": "xbe",
    "xbe": "xbe",
}
_OS_FAMILY = {
    "win": "windows",
    "windows": "windows",
    "mac": "macos",
    "macos": "macos",
    "ios": "ios",
    "linux": "linux",
    "android": "android",
    "xbox": "xbox",
}
_ARCH = {"x86": "x86", "x86_64": "x86", "amd64": "x86", "arm": "arm", "aarch64": "aarch64"}
# Where ``this`` travels on x86-32, by object format. This is a rule, not a measured
# fact: MSVC-built PE/XBE pass it in ECX, GCC/Clang ELF and Mach-O push it on the
# stack. A MinGW PE would break it; an explicit ``binary.this_kind`` (U69) overrides.
# Other arches have no ecx-vs-stack distinction, so the fact stays unknown.
_X86_32_THIS = {"pe": "ecx", "xbe": "ecx", "elf": "stack", "macho": "stack"}

AbiKey = tuple  # (format, os, arch, bits, endian, this_kind); None marks an unknown fact


def abi_key(platform, fmt, arch, bits, language_id, this_kind=None) -> AbiKey:
    """Normalise one ``binary`` row to the ABI facts a convention donor must share."""
    fam = _FORMAT_FAMILY.get(str(fmt or "").strip().lower())
    os_family = _OS_FAMILY.get(str(platform or "").strip().lower())
    raw_arch = str(arch or "").strip().lower()
    norm_arch = _ARCH.get(raw_arch)
    width = int(bits) if bits else (64 if raw_arch in ("x86_64", "amd64", "aarch64") else None)
    parts = str(language_id or "").split(":")
    if len(parts) > 1 and parts[1] in ("LE", "BE"):
        endian = parts[1]
    else:
        endian = "LE" if norm_arch == "x86" else None
    if this_kind in ("ecx", "stack"):
        this = this_kind
    elif (norm_arch, width) == ("x86", 32):
        this = _X86_32_THIS.get(fam)
    else:
        this = None
    return (fam, os_family, norm_arch, width, endian, this)


def abi_verdict(recipient: AbiKey | None, donor: AbiKey | None) -> str:
    """``match``, ``cross`` (a known fact differs) or ``unknown`` (a fact is missing)."""
    if recipient is None or None in recipient:
        return "unknown"
    if donor is None:
        return "unknown"
    if any(d is not None and d != r for d, r in zip(donor, recipient)):
        return "cross"
    return "unknown" if None in donor else "match"


def binary_abis(con: sqlite3.Connection) -> dict[int, AbiKey]:
    cols = {r[1] for r in con.execute("PRAGMA table_info(binary)")}
    this_col = "this_kind" if "this_kind" in cols else "NULL"
    return {
        r[0]: abi_key(r[1], r[2], r[3], r[4], r[5], r[6])
        for r in con.execute(
            f"SELECT id, platform, format, arch, bits, language_id, {this_col} FROM binary"
        )
    }


# Import compatibility only; migration 12 owns installation.
SCHEMA = CONVENTION_TABLE_DDL
_SAVEPOINT_IDS = count()


@contextmanager
def _convention_write_scope(con: sqlite3.Connection):
    """Commit success, including caller work; undo only our surviving scope."""
    owns = not con.in_transaction
    savepoint = f"convention_write_{next(_SAVEPOINT_IDS)}"
    # A failed scope creation grants no cleanup ownership over caller work.
    con.execute("BEGIN IMMEDIATE" if owns else f"SAVEPOINT {savepoint}")
    try:
        require_convention_schema(con)
        yield
        con.commit()
    except BaseException as exc:
        if not con.in_transaction:
            raise RuntimeError(
                "convention transaction ended before failure acknowledgement; "
                "durability/rollback is uncertain and caller work cannot be reconstructed"
            ) from exc
        if owns:
            con.rollback()
        else:
            con.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            con.execute(f"RELEASE SAVEPOINT {savepoint}")
        raise



def popped_bytes(body: bytes) -> tuple[int, str] | tuple[None, None]:
    """Stack bytes the callee pops, read off the terminating instruction."""
    buf = body.rstrip(b"\xcc")
    if len(buf) >= 3 and buf[-3] == 0xC2:
        return int.from_bytes(buf[-2:], "little"), "ret_imm"
    if buf and buf[-1] == 0xC3:
        return 0, "ret_zero"
    return None, None


def donor_classes(
    con: sqlite3.Connection,
) -> tuple[dict[int, list[tuple[str, str, int]]], dict[int, dict[int, int]]]:
    """Per logical id: ``(decoration class, game, donor binary id)``."""
    bins = {r["id"]: r["game"] for r in con.execute("SELECT id, game FROM binary")}
    ident: dict[int, dict[int, int]] = collections.defaultdict(dict)
    for row in con.execute("SELECT logical_id, binary_id, addr FROM identity"):
        ident[row["binary_id"]][row["addr"]] = row["logical_id"]
    out: dict[int, list[tuple[str, str]]] = collections.defaultdict(list)
    for row in con.execute(
        "SELECT binary_id, addr, calling_convention FROM func"
        " WHERE calling_convention IS NOT NULL AND calling_convention<>'unknown'"
    ):
        lid = ident.get(row["binary_id"], {}).get(row["addr"])
        cls = DECORATION_CLASS.get(row["calling_convention"])
        if lid is not None and cls:
            out[lid].append((cls, bins.get(row["binary_id"]) or "", row["binary_id"]))
    return out, ident


def derive_conventions(
    con: sqlite3.Connection,
    binary_id: int,
    raw: bytes,
    mapper,
    *,
    game: str | None = None,
    cross_game: bool = False,
    apply_rows: bool = False,
) -> dict:
    """Derive decoration class + stack bytes. *raw* and *mapper* are caller-supplied."""
    if apply_rows:
        require_convention_schema(con)
    donors, ident = donor_classes(con)
    abis = binary_abis(con)
    mine_abi = abis.get(binary_id)
    mine = ident.get(binary_id, {})
    stats = collections.Counter()
    rows = []
    for row in con.execute(
        "SELECT addr, size, calling_convention FROM func"
        " WHERE binary_id=? AND is_thunk=0 AND n_instr>=1 AND size>0",
        (binary_id,),
    ):
        cc = row["calling_convention"]
        if cc and cc != "unknown":
            stats["already_known"] += 1
            continue
        addr, size = int(row["addr"]), int(row["size"])
        off = mapper(addr)
        n, nsrc = popped_bytes(raw[off : off + size]) if off is not None and off + size <= len(raw) else (None, None)

        lid = mine.get(addr)
        cls = None
        csrc = ""
        if lid is not None:
            ds = []
            refused = set()
            for d in donors.get(lid, []):
                verdict = abi_verdict(mine_abi, abis.get(d[2]))
                if verdict == "match":
                    ds.append(d)
                else:
                    refused.add(verdict)
                    stats[f"donor_refused_{verdict}_abi"] += 1
            if refused and not ds:
                stats["skipped_unknown_abi" if "unknown" in refused else "skipped_cross_abi"] += 1
                continue
            same = [d for d in ds if d[1] == game]
            pool = same if same else (ds if cross_game else [])
            classes = {d[0] for d in pool}
            if len(classes) == 1:
                cls = classes.pop()
                csrc = "same_game" if same else "cross_game"
            elif len(classes) > 1:
                stats["class_conflict"] += 1

        if cls is None and n is None:
            stats["undetermined"] += 1
            continue
        if cls is None:
            stats["N_only_class_unknown"] += 1
            continue
        if n is None:
            if cls == "stack":
                stats["stack_no_N_needed"] += 1
            else:
                stats["ecx_but_N_unknown"] += 1
            continue

        stats[f"determined_{cls}"] += 1
        rows.append((binary_id, addr, cls, n, 8 + n if cls == "ecx" else None, csrc, nsrc))

    if apply_rows:
        with _convention_write_scope(con):
            con.executemany(
                "INSERT OR REPLACE INTO main.func_convention_derived"
                " (binary_id, addr, deco_class, stack_bytes, fastcall_n, class_source, n_source)"
                " VALUES (?,?,?,?,?,?,?)",
                rows,
            )
    return {"stats": dict(stats), "rows": rows, "applied": apply_rows}


def load_raw(raw_path: Path | str) -> bytes:
    return Path(raw_path).read_bytes()
