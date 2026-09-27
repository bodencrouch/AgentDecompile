"""Ghidra data type comparison and display helpers.

``str(DataType)`` is not a name. For structures and unions Ghidra's
``CompositeInternal.toString`` returns a multi-line layout dump whose first
line is the path name; typedefs print ``typedef <name> <base>``. Comparing or
displaying that string gives wrong conflict decisions and broken table cells.
Use ``same_data_type`` to decide whether an existing type matches a requested
one, and ``data_type_label`` for a one-line display name.
"""

from __future__ import annotations

from typing import Any


def _call_str(obj: Any, method: str) -> str:
    getter = getattr(obj, method, None)
    if not callable(getter):
        return ""
    try:
        value = getter()
    except Exception:
        return ""
    return "" if value is None else str(value)


def data_type_label(dt: Any) -> str:
    """One-line display name for a Ghidra DataType (``getDisplayName``).

    For types that inherit ``AbstractDataType.toString`` or
    ``DataTypeDB.toString`` this equals ``str(dt)``, since both return
    ``getDisplayName()``. It is not ``str(dt)`` for types that override
    ``toString``: composites (layout dump), typedefs, enums, function
    definitions and pointers. ``PointerDataType.toString`` returns
    ``getName()``, which can differ from its ``getDisplayName()``
    (PointerDataType.java:290 vs :856). Commit 0fff926 claimed equality for
    all non-composite, non-typedef types; that was too broad. Falls back to
    ``getName`` and then to the first line of ``str(dt)``.
    """
    if dt is None:
        return ""
    label = _call_str(dt, "getDisplayName") or _call_str(dt, "getName")
    if label:
        return label
    text = str(dt).strip()
    return text.splitlines()[0].strip() if text else ""


def same_data_type(existing_dt: Any, requested: Any) -> bool:
    """True when ``existing_dt`` is the type ``requested`` names or resolves to.

    ``requested`` may be a DataType (compared with ``existing_dt.isEquivalent``,
    invoked on the existing listing/DB type as Ghidra's javadoc advises) or a
    type name/path string (compared case-sensitively, as Ghidra does, against
    the existing type's ``getPathName``, ``getName`` and ``getDisplayName``).
    """
    if existing_dt is None or requested is None:
        return False
    if not isinstance(requested, str):
        is_equivalent = getattr(existing_dt, "isEquivalent", None)
        if callable(is_equivalent):
            try:
                if bool(is_equivalent(requested)):
                    return True
            except Exception:
                pass
        requested_path = _call_str(requested, "getPathName")
        return bool(requested_path) and requested_path == _call_str(existing_dt, "getPathName")
    wanted = requested.strip()
    if not wanted:
        return False
    return wanted in {_call_str(existing_dt, m) for m in ("getPathName", "getName", "getDisplayName")}



def _same_address(a: Any, b: Any) -> bool:
    return a is not None and b is not None and str(a) == str(b)


def overlapping_data_conflicts(listing: Any, start: Any, requested: Any) -> list[tuple[str, str]]:
    """Defined data that applying ``requested`` at ``start`` would clear, as (address, label).

    The apply sites call ``listing.clearCodeUnits(start, start + len - 1)``,
    which clears every code unit that overlaps the range, including one that
    starts before ``start``. This returns each defined data unit in that range
    (``Listing.getDefinedDataContaining`` for a unit that starts earlier, plus
    ``Listing.getDefinedData(AddressSet(start, end), True)`` for units that start
    inside it). A unit at ``start`` whose type is ``same_data_type`` as
    ``requested`` is not a conflict. Undefined placeholder data is never listed:
    both Listing calls return defined data only.
    """
    from ghidra.program.model.address import AddressSet  # pyright: ignore[reportMissingImports, reportMissingModuleSource]

    length = 1
    try:
        length = max(int(requested.getLength()), 1)
    except Exception:
        length = 1
    end = start.add(length - 1)

    units: list[Any] = []
    containing = listing.getDefinedDataContaining(start)
    if containing is not None and not _same_address(containing.getAddress(), start):
        units.append(containing)
    units.extend(listing.getDefinedData(AddressSet(start, end), True))

    conflicts: list[tuple[str, str]] = []
    for unit in units:
        unit_dt = unit.getDataType()
        if _same_address(unit.getAddress(), start) and same_data_type(unit_dt, requested):
            continue
        conflicts.append((str(unit.getAddress()), data_type_label(unit_dt)))
    return conflicts


def format_conflict_lines(conflicts: list[tuple[str, str]], prefix: str = "") -> str:
    """One ``- <prefix><address> <type>`` diff line per overlapping data unit."""
    return "\n".join(f"- {prefix}{address} {label}" for address, label in conflicts)
