"""Site policy and adapter-key map for the hook pack exporter.

Both are data files, never core: a site's kind, whether the runtime host
must resolve it, a field's extent, and the adapter key it binds to are
decisions the host owner makes per site. The store holds none of that. The
exporter loads both here, validates them up front, and looks them up by the
final site key with a fallback to the un-suffixed key.

Everything here is a pure function of the file contents. Lists come out
sorted and de-duplicated so the pack bytes never depend on file order.

Both files may also come from an L3 data pack (:mod:`data_packs`): the
``site_policy`` and ``adapter_map`` entries of a selected
:class:`~data_packs.PackManifest`. An explicit path always wins over the
pack's entry; a pack without the entry is the same as no path.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # no import cycle: data_packs never imports this module
    from .data_packs import PackManifest

SITE_KINDS = ("call", "detour", "field", "reference")
DEFAULT_SITE_POLICY = {"kind": "detour", "required": False}

_POLICY_TOP_KEYS = {"default", "sites"}
_POLICY_DEFAULT_KEYS = {"kind", "required"}
_POLICY_SITE_KEYS = {"kind", "required", "field"}
_FIELD_KEYS = {"offset", "size"}
_MAP_TOP_KEYS = {"keys", "aliases"}


def _read_json_object(path: Path, what: str) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{what}: top level must be a JSON object")
    return data


def _reject_unknown(obj: dict, allowed: set[str], where: str) -> None:
    unknown = sorted(str(k) for k in obj if k not in allowed)
    if unknown:
        raise ValueError(f"{where}: unknown key(s) {unknown}; allowed {sorted(allowed)}")


def _check_kind(value, where: str) -> str:
    if not isinstance(value, str) or value not in SITE_KINDS:
        raise ValueError(f"{where}: kind must be one of {list(SITE_KINDS)}, got {value!r}")
    return value


def _check_required(value, where: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{where}: required must be a boolean, got {value!r}")
    return value


def _check_field(value, where: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{where}: field must be an object with offset and size")
    _reject_unknown(value, _FIELD_KEYS, f"{where}.field")
    missing = sorted(_FIELD_KEYS - set(value))
    if missing:
        raise ValueError(f"{where}.field: missing {missing}")
    out = {}
    for name in ("offset", "size"):
        v = value[name]
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise ValueError(f"{where}.field.{name}: must be a non-negative integer, got {v!r}")
        out[name] = int(v)
    return out


def file_sha256(path: Path | str | None) -> str | None:
    """Hex sha256 of a file's bytes, or None when no path is given."""
    if path is None:
        return None
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def resolve_policy_path(explicit: Path | str | None, pack: "PackManifest | None", kind: str) -> Path | None:
    """*explicit* if given, else the pack's *kind* entry, else None."""
    if explicit is not None:
        return Path(explicit)
    if pack is None:
        return None
    return pack.entry_path_or_none(kind)


def load_site_policy(path: Path | str | None, *, pack: "PackManifest | None" = None) -> dict:
    """Load and validate a site policy file.

    Shape::

        {"default": {"kind": "detour", "required": false},
         "sites": {"<site_key>": {"kind": ..., "required": ..., "field": {"offset": int, "size": int}}}}

    Returns ``{"default": {kind, required}, "sites": {key: {kind, required[, field]}}}``
    with every site entry fully resolved against the default. No path means the
    built-in default and no per-site entries. *pack* supplies its
    ``site_policy`` entry when *path* is None.
    """
    path = resolve_policy_path(path, pack, "site_policy")
    if path is None:
        return {"default": dict(DEFAULT_SITE_POLICY), "sites": {}}
    data = _read_json_object(Path(path), "site policy")
    _reject_unknown(data, _POLICY_TOP_KEYS, "site policy")

    default = dict(DEFAULT_SITE_POLICY)
    raw_default = data.get("default", {})
    if not isinstance(raw_default, dict):
        raise ValueError("site policy: default must be an object")
    _reject_unknown(raw_default, _POLICY_DEFAULT_KEYS, "site policy default")
    if "kind" in raw_default:
        default["kind"] = _check_kind(raw_default["kind"], "site policy default")
    if "required" in raw_default:
        default["required"] = _check_required(raw_default["required"], "site policy default")

    raw_sites = data.get("sites", {})
    if not isinstance(raw_sites, dict):
        raise ValueError("site policy: sites must be an object")
    sites: dict[str, dict] = {}
    for key in sorted(raw_sites):
        entry = raw_sites[key]
        where = f"site policy sites[{key!r}]"
        if not isinstance(entry, dict):
            raise ValueError(f"{where}: must be an object")
        _reject_unknown(entry, _POLICY_SITE_KEYS, where)
        resolved = {
            "kind": _check_kind(entry["kind"], where) if "kind" in entry else default["kind"],
            "required": _check_required(entry["required"], where) if "required" in entry else default["required"],
        }
        if "field" in entry:
            if resolved["kind"] != "field":
                raise ValueError(f"{where}: field is only allowed when kind is 'field' (kind is {resolved['kind']!r})")
            resolved["field"] = _check_field(entry["field"], where)
        sites[str(key)] = resolved
    return {"default": default, "sites": sites}


def load_adapter_map(path: Path | str | None, *, pack: "PackManifest | None" = None) -> dict:
    """Load and validate an adapter-key map file.

    Shape::

        {"keys": {"<site_key>": "<adapter_key>"},
         "aliases": {"<site_key>": ["<alias>", ...]}}

    Aliases come back sorted and de-duplicated. Two site keys naming the same
    adapter key is a collision and raises, listing both; nothing is last-wins.
    *pack* supplies its ``adapter_map`` entry when *path* is None.
    """
    path = resolve_policy_path(path, pack, "adapter_map")
    if path is None:
        return {"keys": {}, "aliases": {}}
    data = _read_json_object(Path(path), "adapter map")
    _reject_unknown(data, _MAP_TOP_KEYS, "adapter map")

    raw_keys = data.get("keys", {})
    if not isinstance(raw_keys, dict):
        raise ValueError("adapter map: keys must be an object")
    keys: dict[str, str] = {}
    for site_key in sorted(raw_keys):
        value = raw_keys[site_key]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"adapter map keys[{site_key!r}]: adapter key must be a non-empty string")
        keys[str(site_key)] = value.strip()
    check_adapter_key_collisions(keys, where="adapter map")

    raw_aliases = data.get("aliases", {})
    if not isinstance(raw_aliases, dict):
        raise ValueError("adapter map: aliases must be an object")
    aliases: dict[str, list[str]] = {}
    for site_key in sorted(raw_aliases):
        value = raw_aliases[site_key]
        if not isinstance(value, list) or any(not isinstance(a, str) or not a.strip() for a in value):
            raise ValueError(f"adapter map aliases[{site_key!r}]: must be a list of non-empty strings")
        aliases[str(site_key)] = sorted({a.strip() for a in value})
    return {"keys": keys, "aliases": aliases}


def check_adapter_key_collisions(assigned: dict[str, str], *, where: str) -> None:
    """Raise when two site keys in *assigned* share one adapter key."""
    owners: dict[str, list[str]] = {}
    for site_key in sorted(assigned):
        owners.setdefault(assigned[site_key], []).append(site_key)
    clashes = {k: v for k, v in owners.items() if len(v) > 1}
    if clashes:
        detail = "; ".join(f"{k!r} <- {sorted(v)}" for k, v in sorted(clashes.items()))
        raise ValueError(f"{where}: adapter key collision: {detail}")


def lookup_site(table: dict, key: str, base_key: str):
    """Entry for *key* from *table*, else for *base_key*, else None.

    *key* is the final (possibly ``__<lid>``-suffixed) site key and wins;
    *base_key* is the un-suffixed name it was derived from. Returns
    ``(matched_key, entry)`` so the caller can account for which policy key
    was consumed.
    """
    if key in table:
        return key, table[key]
    if base_key != key and base_key in table:
        return base_key, table[base_key]
    return None, None
