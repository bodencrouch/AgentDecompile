"""Validated, target-bound native operation contracts for hook-pack export.

An operation contract names what a runtime adapter may do.  It deliberately
does not turn a hook site, a symbol label, or a compiled profile into proof that
the operation is currently callable.  The exporter only serializes a contract
when every named adapter role has one byte-bound instance on the exact target
image.  Runtime lifetime, thread and independent-observer checks remain the
consumer's admission boundary.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


FORMAT = "agentdecompile.operation-contract/v1"
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_REQUIRED_OPERATION_KEYS = {
    "id", "target", "adapter", "roles", "abi", "units", "thread",
    "lifetime", "inverse", "observations",
}
_TARGET_KEYS = {"slug", "sha256"}
_ABI_KEYS = {"calling_convention", "pointer_width"}


def _text(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{where}: must be a non-empty string")
    return value.strip()


def _unknown(value: dict, allowed: set[str], where: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"{where}: unknown key(s) {unknown}")


def load_operation_contract(path: Path | str | None) -> list[dict]:
    """Load canonical operation declarations, or no declarations when absent.

    The intentionally small schema binds an operation ID to one exact target,
    named adapter roles, ABI, units, thread/lifetime limits, an inverse, and
    independent observations.  It is not a generic native-call language.
    """
    if path is None:
        return []
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {"format", "operations"}:
        raise ValueError("operation contract: expected exactly format and operations")
    if raw["format"] != FORMAT:
        raise ValueError(f"operation contract: format must be {FORMAT!r}")
    if not isinstance(raw["operations"], list) or not raw["operations"]:
        raise ValueError("operation contract: operations must be a non-empty list")
    out: list[dict] = []
    ids: set[str] = set()
    for index, item in enumerate(raw["operations"]):
        where = f"operation contract operations[{index}]"
        if not isinstance(item, dict):
            raise ValueError(f"{where}: must be an object")
        _unknown(item, _REQUIRED_OPERATION_KEYS, where)
        missing = sorted(_REQUIRED_OPERATION_KEYS - set(item))
        if missing:
            raise ValueError(f"{where}: missing {missing}")
        operation_id = _text(item["id"], f"{where}.id")
        if operation_id in ids:
            raise ValueError(f"operation contract: duplicate operation id {operation_id!r}")
        ids.add(operation_id)
        target = item["target"]
        if not isinstance(target, dict):
            raise ValueError(f"{where}.target: must be an object")
        _unknown(target, _TARGET_KEYS, f"{where}.target")
        if set(target) != _TARGET_KEYS:
            raise ValueError(f"{where}.target: requires slug and sha256")
        target_sha = _text(target["sha256"], f"{where}.target.sha256").lower()
        if not _SHA256.fullmatch(target_sha):
            raise ValueError(f"{where}.target.sha256: must be lower-case SHA-256")
        roles = item["roles"]
        if not isinstance(roles, dict) or not roles:
            raise ValueError(f"{where}.roles: must be a non-empty object")
        normalized_roles = {str(role): _text(key, f"{where}.roles[{role!r}]") for role, key in roles.items()}
        if any(not role.strip() for role in normalized_roles):
            raise ValueError(f"{where}.roles: role names must be non-empty")
        if len(set(normalized_roles.values())) != len(normalized_roles):
            raise ValueError(f"{where}.roles: adapter keys must be unique")
        abi = item["abi"]
        if not isinstance(abi, dict):
            raise ValueError(f"{where}.abi: must be an object")
        _unknown(abi, _ABI_KEYS, f"{where}.abi")
        if set(abi) != _ABI_KEYS or isinstance(abi["pointer_width"], bool) or abi["pointer_width"] not in (4, 8):
            raise ValueError(f"{where}.abi: requires calling_convention and pointer_width 4 or 8")
        normalized = {
            "id": operation_id,
            "target": {"slug": _text(target["slug"], f"{where}.target.slug"), "sha256": target_sha},
            "adapter": _text(item["adapter"], f"{where}.adapter"),
            "roles": dict(sorted(normalized_roles.items())),
            "abi": {"calling_convention": _text(abi["calling_convention"], f"{where}.abi.calling_convention"), "pointer_width": abi["pointer_width"]},
            "units": _text(item["units"], f"{where}.units"),
            "thread": _text(item["thread"], f"{where}.thread"),
            "lifetime": _text(item["lifetime"], f"{where}.lifetime"),
            "inverse": _text(item["inverse"], f"{where}.inverse"),
            "observations": _text(item["observations"], f"{where}.observations"),
        }
        out.append(normalized)
    return sorted(out, key=lambda operation: operation["id"])


def bind_operations(operations: list[dict], *, binaries: dict[str, dict], sites: dict[str, dict], raw_images: dict[str, bytes | None]) -> list[dict]:
    """Return exportable operations after resolving exact target roles.

    A database digest alone is deliberately insufficient here: the raw image
    used to obtain a role's bytes must exist and hash to the declaration's
    selected SHA-256.  Each requested adapter key must map to exactly one site
    and carry a byte-bound instance for that selected build.
    """
    emitted: list[dict] = []
    for operation in operations:
        target = operation["target"]
        slug, expected_sha = target["slug"], target["sha256"]
        binary = binaries.get(slug)
        if binary is None:
            raise ValueError(f"operation {operation['id']!r}: selected target slug {slug!r} is absent from the pack")
        image = raw_images.get(slug)
        if image is None:
            raise ValueError(f"operation {operation['id']!r}: selected target {slug!r} has no readable raw image")
        actual_sha = hashlib.sha256(image).hexdigest()
        if actual_sha != expected_sha:
            raise ValueError(f"operation {operation['id']!r}: selected target raw-image SHA-256 does not match contract")
        if binary.get("sha256") != expected_sha:
            raise ValueError(f"operation {operation['id']!r}: selected target store/pack SHA-256 does not match contract")
        by_adapter: dict[str, list[tuple[str, dict]]] = {}
        for site_name, site in sites.items():
            key = site.get("adapter_key")
            if isinstance(key, str):
                by_adapter.setdefault(key, []).append((site_name, site))
        roles: dict[str, dict] = {}
        for role, adapter_key in operation["roles"].items():
            matches = by_adapter.get(adapter_key, [])
            if len(matches) != 1:
                raise ValueError(f"operation {operation['id']!r}: adapter key {adapter_key!r} for role {role!r} must resolve exactly once")
            site_name, site = matches[0]
            instances = [row for row in site.get("instances", []) if row.get("binary") == slug and row.get("expected_bytes")]
            if len(instances) != 1:
                raise ValueError(f"operation {operation['id']!r}: role {role!r} lacks one byte-bound selected-target instance")
            instance = instances[0]
            roles[role] = {"site": site_name, "adapter_key": adapter_key, "logical_id": site["logical_id"], "addr": instance["addr"], "expected_bytes": instance["expected_bytes"]}
        emitted.append({**operation, "roles": dict(sorted(roles.items())), "target": {**target, "raw_image_sha256": actual_sha}})
    return emitted
