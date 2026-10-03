"""Export Ghidra struct/union/enum definitions so decompiled C can compile.

Emitted C is ``#pragma pack(1)`` with explicit padding at every gap. Nested
composites retain inline layouts in C and typed references in field rows.
Known pointer targets are retained; unknown types retain their layout fallback.
"""

from __future__ import annotations

import json
import re
import sqlite3

from . import ghidra_env as ge

from contextlib import contextmanager
from itertools import count

from .store import TYPE_TABLE_DDL, TYPE_INDEX_SQL, require_type_schema, type_inventory_available

# Import compatibility only. Migration 13 owns installation.
SCHEMA = TYPE_TABLE_DDL.rstrip() + ";\n" + TYPE_INDEX_SQL + ";\n"
_SAVEPOINT_IDS = count()


@contextmanager
def _type_write_scope(con: sqlite3.Connection):
    """Commit success with caller work; roll back only our surviving scope."""
    owns = not con.in_transaction
    savepoint = f"type_write_{next(_SAVEPOINT_IDS)}"
    con.execute("BEGIN IMMEDIATE" if owns else f"SAVEPOINT {savepoint}")
    try:
        require_type_schema(con)
        yield
        con.commit()
    except BaseException as exc:
        if not con.in_transaction:
            raise RuntimeError(
                "type transaction ended before failure acknowledgement; "
                "durability/rollback is uncertain and caller work cannot be reconstructed"
            ) from exc
        if owns:
            con.rollback()
        else:
            con.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            con.execute(f"RELEASE SAVEPOINT {savepoint}")
        raise


def _materialize_type_inventory(con: sqlite3.Connection) -> None:
    """Called only inside an admitted type writer's operation scope."""
    con.execute("UPDATE main.type_inventory_state SET mode='installed' WHERE singleton=1")


def insert_native_types(con: sqlite3.Connection, rows) -> int:
    """Insert missing native definitions without replacing curated keys or fields."""
    require_type_schema(con)
    payload = [tuple(row) for row in rows]
    # IGNORE is for curated key collisions, not a partly accepted malformed batch.
    if any(len(row) != 6 or any(row[i] is None for i in (0, 1, 2, 4)) for row in payload):
        raise ValueError("native type batch requires six fields and non-NULL required values")
    inserted = 0
    with _type_write_scope(con):
        for row in payload:
            changed = con.execute(
                "INSERT OR IGNORE INTO main.ghidra_type"
                " (binary_id,name,kind,size,definition,n_fields) VALUES(?,?,?,?,?,?)", row,
            )
            inserted += changed.rowcount
        _materialize_type_inventory(con)
    return inserted


_PRIM = {
    "byte": "unsigned char",
    "sbyte": "signed char",
    "char": "char",
    "uchar": "unsigned char",
    "schar": "signed char",
    "word": "unsigned short",
    "sword": "short",
    "ushort": "unsigned short",
    "short": "short",
    "dword": "unsigned int",
    "sdword": "int",
    "uint": "unsigned int",
    "int": "int",
    "long": "long",
    "ulong": "unsigned long",
    "qword": "unsigned long long",
    "sqword": "long long",
    "longlong": "long long",
    "ulonglong": "unsigned long long",
    "float": "float",
    "double": "double",
    "longdouble": "long double",
    "bool": "unsigned char",
    "void": "void",
    "undefined": "unsigned char",
    "undefined1": "unsigned char",
    "undefined2": "unsigned short",
    "undefined4": "unsigned int",
    "undefined8": "unsigned long long",
    "pointer": "void *",
    "pointer32": "void *",
}

_IDENT_OK = re.compile(r"^[A-Za-z_]\w*$")


def c_ident(name: str) -> str:
    """Ghidra type names carry `::`, spaces, templates and punctuation."""
    text = re.sub(r"::", "__", str(name))
    text = re.sub(r"[^A-Za-z0-9_]+", "_", text).strip("_") or "anon"
    keywords = {"auto", "break", "case", "char", "const", "continue", "default", "do", "double",
                "else", "enum", "extern", "float", "for", "goto", "if", "inline", "int", "long",
                "register", "restrict", "return", "short", "signed", "sizeof", "static", "struct",
                "switch", "typedef", "union", "unsigned", "void", "volatile", "while", "class",
                "delete", "new", "private", "protected", "public", "template", "this", "virtual"}
    return "type_" + text if text[0].isdigit() or text in keywords else text


def describe_field_type(dt, depth: int = 0) -> dict:
    """Keep semantic type references separately from conservative C storage.

    References use original Ghidra names so namespace/name sanitization never
    merges distinct type identities. Composite references terminate recursion.
    """
    from ghidra.program.model.data import Array, Enum, Pointer, Structure, TypeDef, Union  # type: ignore

    if dt is None or depth >= 32:
        return {"kind": "unknown"}
    name = str(dt.getName())
    result = {"name": name, "size": int(dt.getLength())}
    if isinstance(dt, Pointer):
        return dict(result, kind="pointer", pointee=describe_field_type(dt.getDataType(), depth + 1))
    if isinstance(dt, TypeDef):
        return dict(result, kind="typedef", base=describe_field_type(dt.getBaseDataType(), depth + 1))
    if isinstance(dt, Array):
        return dict(result, kind="array", count=int(dt.getNumElements()),
                    element=describe_field_type(dt.getDataType(), depth + 1))
    if isinstance(dt, (Structure, Union)):
        return dict(result, kind="union" if isinstance(dt, Union) else "struct")
    if isinstance(dt, Enum):
        return dict(result, kind="enum")
    return dict(result, kind="primitive" if name.lower() in _PRIM else "unknown")


def field_rows(dt) -> list[dict]:
    """Export every component, including overlapping union/bitfield storage."""
    rows = []
    for ordinal, comp in enumerate(dt.getComponents()):
        descriptor = describe_field_type(comp.getDataType())
        effective = descriptor
        while effective.get("kind") == "typedef":
            effective = effective["base"]
        rows.append({
            "ordinal": ordinal, "offset": int(comp.getOffset()),
            "size": int(comp.getLength()),
            "name": str(comp.getFieldName() or f"field_{int(comp.getOffset()):x}"),
            "dt_kind": effective["kind"],
            "pointee_type": effective.get("pointee", {}).get("name"),
            "composite_type": effective.get("name") if effective["kind"] in {"struct", "union"} else None,
            "element_type": effective.get("element", {}).get("name"),
            "array_count": effective.get("count"), "type": descriptor,
        })
    return rows


def render_field_type(dt, depth: int = 0) -> str:
    """Render known scalars and pointers without inventing composite layouts."""
    from ghidra.program.model.data import Enum, Pointer, Structure, TypeDef, Union  # type: ignore

    if dt is None or depth >= 32:
        return ""
    if isinstance(dt, Pointer):
        target = dt.getDataType()
        while isinstance(target, TypeDef) and depth < 32:
            target = target.getBaseDataType()
            depth += 1
        if isinstance(target, (Structure, Union)):
            tag = "union" if isinstance(target, Union) else "struct"
            return f"{tag} {c_ident(target.getName())} *"
        pointee = render_field_type(target, depth + 1)
        return f"{pointee} *" if pointee else "void *"
    if isinstance(dt, TypeDef):
        return render_field_type(dt.getBaseDataType(), depth + 1)
    low = str(dt.getName()).lower()
    if low in _PRIM:
        return _PRIM[low] if low != "void" else ""
    if isinstance(dt, Enum):
        return {1: "unsigned char", 2: "unsigned short", 4: "unsigned int",
                8: "unsigned long long"}.get(int(dt.getLength()), "")
    return ""


def emit_struct(dt, depth: int = 0) -> tuple[str, int] | None:
    """Emit one struct/union as packed C with explicit gap padding."""
    from ghidra.program.model.data import Array, Structure, TypeDef, Union  # type: ignore

    if depth >= 32:
        return None
    name = c_ident(dt.getName())
    if not _IDENT_OK.match(name):
        return None
    length = int(dt.getLength() or 0)
    if length <= 0:
        return None

    is_union = isinstance(dt, Union)
    tag = "union" if is_union else "struct"
    lines = [f"typedef {tag} {name} {{"]
    if is_union:
        lines.append(f"  unsigned char _storage[0x{length:x}];")
    n_fields = 0
    cursor = 0
    seen_fields = set()
    for comp in dt.getComponents():
        off = int(comp.getOffset())
        clen = int(comp.getLength() or 0)
        if (not is_union and off < cursor) or clen <= 0 or off + clen > length:
            continue
        if not is_union and off > cursor:
            lines.append(f"  unsigned char _pad{cursor:x}[0x{off - cursor:x}];")
        fname = comp.getFieldName()
        fname = c_ident(fname) if fname else f"field_{off:x}"
        base_name = fname
        suffix = 1
        while fname in seen_fields or fname.startswith("_pad") or fname == "_storage":
            fname = f"field_{base_name}_{suffix}"
            suffix += 1
        seen_fields.add(fname)
        field_dt = comp.getDataType()
        for _ in range(32):
            if not isinstance(field_dt, TypeDef):
                break
            field_dt = field_dt.getBaseDataType()
        ctype = render_field_type(field_dt)
        nested = emit_struct(field_dt, depth + 1) if isinstance(field_dt, (Structure, Union)) else None
        if nested and int(field_dt.getLength()) == clen:
            # Inline anonymous storage avoids cross-definition ordering and
            # duplicate tag definitions; field rows retain the named link.
            body = nested[0].splitlines()[1:-2]
            lines.append(f"  {'union' if isinstance(field_dt, Union) else 'struct'} {{ /* {c_ident(field_dt.getName())} */")
            lines.extend("  " + line for line in body)
            lines.append(f"  }} {fname};")
        elif isinstance(field_dt, Array) and int(field_dt.getLength()) == clen:
            element = field_dt.getDataType()
            element_type = render_field_type(element)
            count = int(field_dt.getNumElements())
            nested_element = emit_struct(element, depth + 1) if isinstance(element, (Structure, Union)) else None
            if count > 0 and int(element.getLength()) * count == clen and nested_element:
                lines.append(f"  {'union' if isinstance(element, Union) else 'struct'} {{ /* {c_ident(element.getName())} */")
                lines.extend("  " + line for line in nested_element[0].splitlines()[1:-2])
                lines.append(f"  }} {fname}[{count}];")
            elif count > 0 and int(element.getLength()) * count == clen and element_type:
                lines.append(f"  {element_type} {fname}[{count}];")
            else:
                lines.append(f"  unsigned char {fname}[0x{clen:x}];")
        elif ctype and clen in (1, 2, 4, 8):
            lines.append(f"  {ctype} {fname};")
        else:
            lines.append(f"  unsigned char {fname}[0x{clen:x}];")
        n_fields += 1
        cursor = off + clen
    if not is_union and cursor < length:
        lines.append(f"  unsigned char _pad{cursor:x}[0x{length - cursor:x}];")
    lines.append(f"}} {name};")
    lines.append(f"typedef char _sizecheck_{name}[(sizeof({name}) == 0x{length:x}) ? 1 : -1];")
    return "\n".join(lines), n_fields


def emit_enum(dt) -> tuple[str, int] | None:
    name = c_ident(dt.getName())
    if not _IDENT_OK.match(name):
        return None
    width = {1: "unsigned char", 2: "unsigned short", 4: "unsigned int", 8: "unsigned long long"}.get(
        int(dt.getLength() or 4), "unsigned int"
    )
    lines = [f"typedef {width} {name};"]
    n = 0
    for vname in dt.getNames():
        ident = c_ident(vname)
        if not _IDENT_OK.match(ident):
            continue
        lines.append(f"#define {ident} (({name})({dt.getValue(vname)}))")
        n += 1
    return "\n".join(lines), n


def definitions_for(con: sqlite3.Connection, binary_id: int, names: set[str]) -> tuple[str, set[str]]:
    """Return emitted C for whichever of *names* this binary has a layout for."""
    if not names:
        return "", set()
    from . import migrations

    if migrations.user_version(con) >= 13 and not type_inventory_available(con):
        raise sqlite3.OperationalError("no such table: ghidra_type")
    qs = ",".join("?" * len(names))
    rows = con.execute(
        f"SELECT name, definition FROM ghidra_type WHERE binary_id=? AND name IN ({qs})",
        (binary_id, *sorted(names)),
    ).fetchall()
    out, got = [], set()
    for row in rows:
        nm = row["name"] if hasattr(row, "keys") else row[0]
        dfn = row["definition"] if hasattr(row, "keys") else row[1]
        out.append(dfn)
        got.add(nm)
    return ("\n".join(out) + "\n" if out else ""), got


def export(repo_path: str, con: sqlite3.Connection, *, open_program=None, start=None) -> dict:
    """Walk a live program's datatypes into ``ghidra_type``. Skips when no program."""
    require_type_schema(con)
    opener = open_program or ge.open_program
    starter = start or ge.start
    if starter() is False:
        return {"struct": 0, "union": 0, "enum": 0, "skipped": 0, "reason": "no-program"}

    from ghidra.program.model.data import Enum, Structure, Union  # type: ignore

    row = con.execute("SELECT id FROM binary WHERE repo_path=?", (repo_path,)).fetchone()
    if row is None:
        raise SystemExit(f"binary not in db: {repo_path}")
    binary_id = int(row["id"] if hasattr(row, "keys") else row[0])

    stats = {"struct": 0, "union": 0, "enum": 0, "skipped": 0}
    rows = []
    fields = []
    type_names: dict[str, str] = {}
    with opener(repo_path) as program:
        if program is None:
            stats["reason"] = "no-program"
            return stats
        dtm = program.getDataTypeManager()
        for dt in dtm.getAllDataTypes():
            try:
                if isinstance(dt, (Structure, Union)):
                    got = emit_struct(dt)
                    kind = "union" if isinstance(dt, Union) else "struct"
                elif isinstance(dt, Enum):
                    got = emit_enum(dt)
                    kind = "enum"
                else:
                    continue
                if got is None:
                    stats["skipped"] += 1
                    continue
                text, nf = got
                emitted_name = c_ident(dt.getName())
                original_name = str(dt.getPathName()) if hasattr(dt, "getPathName") else str(dt.getName())
                if emitted_name in type_names and type_names[emitted_name] != original_name:
                    raise ValueError(f"Type name collision after C normalization: {emitted_name}")
                type_names[emitted_name] = original_name
                if kind in {"struct", "union"}:
                    # Build all rows before appending so a malformed component
                    # cannot publish a partially described type.
                    typed_fields = field_rows(dt)
                    field_payload = [(binary_id, emitted_name, f["ordinal"],
                                   f["offset"], f["size"], f["name"], f["dt_kind"],
                                   f["pointee_type"], f["composite_type"], f["element_type"],
                                   f["array_count"], json.dumps(f["type"], sort_keys=True))
                                  for f in typed_fields]
                    fields.extend(field_payload)
                rows.append((binary_id, c_ident(dt.getName()), kind, int(dt.getLength() or 0), text, nf))
                stats[kind] += 1
            except ValueError:
                raise  # A conflicting type identity must not silently publish a partial capture.
            except Exception:
                stats["skipped"] += 1

    with _type_write_scope(con):
        con.executemany(
            "INSERT OR REPLACE INTO main.ghidra_type (binary_id, name, kind, size, definition, n_fields) VALUES (?,?,?,?,?,?)",
            rows,
        )
        # Replace fields only for successfully exported types; preserve other
        # historical evidence when an individual live datatype cannot be read.
        con.executemany("DELETE FROM main.ghidra_field WHERE binary_id=? AND type_name=?",
                        [(row[0], row[1]) for row in rows])
        con.executemany(
            "INSERT INTO main.ghidra_field (binary_id,type_name,ordinal,offset,size,name,dt_kind,"
            "pointee_type,composite_type,element_type,array_count,type_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            fields,
        )
        _materialize_type_inventory(con)
    return stats
