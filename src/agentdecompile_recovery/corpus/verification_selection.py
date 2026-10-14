"""Pure selection policy shared by dashboard admission and byte-verifier CLIs."""

from __future__ import annotations


def validate_selection(*, candidate=None, offset=None, limit=None) -> list[str]:
    """Return selector errors without filesystem, compiler or target access.

    An explicitly supplied zero offset remains a slice selector. Empty optional
    dashboard fields are omitted just as their command builder omits them.
    """
    errors: list[str] = []
    supplied = {}
    for name, value in (("offset", offset), ("limit", limit)):
        if value is None or value == "":
            supplied[name] = False
            continue
        supplied[name] = True
        if type(value) is int:
            number = value
        elif isinstance(value, str):
            try:
                number = int(value)
            except ValueError:
                errors.append(f"--{name} must be an integer")
                continue
        else:
            errors.append(f"--{name} must be an integer")
            continue
        if name == "offset" and number < 0:
            errors.append("--offset must be nonnegative")
        if name == "limit" and number <= 0:
            errors.append("--limit must be positive")
    if candidate and (supplied["offset"] or supplied["limit"]):
        errors.append("--candidate cannot be combined with --offset or --limit")
    return errors
