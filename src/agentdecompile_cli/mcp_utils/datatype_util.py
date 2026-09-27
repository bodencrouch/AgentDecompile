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

    For built-in and DB types other than composites, enums and typedefs this
    equals ``str(dt)`` (``AbstractDataType.toString`` / ``DataTypeDB.toString``
    return ``getDisplayName()``). Falls back to ``getName`` and then to the
    first line of ``str(dt)``.
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


def is_defined_data(data: Any) -> bool:
    """False for Ghidra's undefined placeholder data, True otherwise.

    ``Listing.getDataAt`` returns undefined data (``DefaultDataType``) where no
    code unit is defined; ``Data.isDefined()`` reports that. Objects without
    ``isDefined`` are treated as defined.
    """
    if data is None:
        return False
    is_defined = getattr(data, "isDefined", None)
    if not callable(is_defined):
        return True
    try:
        return bool(is_defined())
    except Exception:
        return True
