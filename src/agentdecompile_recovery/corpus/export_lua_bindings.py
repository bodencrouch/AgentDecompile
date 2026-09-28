"""Generate deterministic, address-free Lua bindings from a v2 hook pack.

The host supplies an operation adapter to ``module.bind(host, build)``. Adapter
methods use ``host:resolve(entity_key, build)`` and return a resolution record
with ``status``, ``value`` and ``members_tried``. Other methods receive that
resolved value: ``entry``, ``handle``, ``get_field``, ``set_field``, ``call`` and
``hook``. No generated module opens a corpus or manufactures runtime evidence.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

ABI_CONFIDENCE_THRESHOLD = 0.9


def _lua(value) -> str:
    """Encode only the deliberately selected descriptor data, never the pack."""
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            raise ValueError("non-finite Lua descriptor value")
        return repr(value)
    if isinstance(value, str):
        # Lua supports decimal byte escapes; avoid JSON's unsupported \\u escape.
        return '"' + ''.join(chr(b) if 32 <= b < 127 and b not in (34, 92)
                              else '\\%03d' % b for b in value.encode('utf-8')) + '"'
    if isinstance(value, list):
        return "{" + ",".join(_lua(item) for item in value) + "}"
    if isinstance(value, dict):
        return "{" + ",".join("[" + _lua(str(key)) + "]=" + _lua(value[key])
                               for key in sorted(value)) + "}"
    raise ValueError(f"unsupported Lua descriptor type: {type(value).__name__}")


def _confidence(abi: dict) -> float:
    value = abi.get("confidence", 0)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        return 0.0
    return float(value)


def _field_type(value: dict) -> dict:
    """Keep semantic type data without copying arbitrary pack fields."""
    if not isinstance(value, dict):
        return {"kind": "unknown"}
    result = {key: value[key] for key in ("name", "kind", "size", "count") if key in value}
    for key in ("pointee", "base", "element"):
        if key in value:
            result[key] = _field_type(value[key])
    return result


def _descriptors(pack: dict, threshold: float) -> dict:
    result = {}
    for entity in sorted(pack["entities"], key=lambda item: item["key"]):
        key = entity["key"]
        if key in result:
            raise ValueError(f"duplicate Lua entity key: {key}")
        fields = {}
        for build, rows in sorted((entity.get("shape", {}).get("fields") or {}).items()):
            fields[build] = {}
            for row in sorted(rows, key=lambda item: (str(item.get("name", "")), int(item.get("ordinal", 0)))):
                name = str(row.get("name") or "")
                if not name or name in fields[build]:
                    raise ValueError(f"empty or duplicate Lua field name: {key}/{build}/{name}")
                # Host resolves field layout using pack metadata. No offset,
                # address, or pointer literal is copied to generated source.
                fields[build][name] = {"name": name, "type": _field_type(row.get("type", {"kind": row.get("dt_kind", "unknown")})),
                                       "pointee_type": row.get("pointee_type"),
                                       "composite_type": row.get("composite_type"),
                                       "element_type": row.get("element_type"),
                                       "array_count": row.get("array_count")}
        calls = {}
        for instance in sorted(entity.get("instances", []), key=lambda item: str(item.get("build", ""))):
            build = str(instance.get("build") or "")
            abi = instance.get("abi") or entity.get("abi") or {}
            confidence = _confidence(abi)
            convention = abi.get("convention", abi.get("callingConvention", abi.get("calling_convention")))
            callable_kind = entity.get("kind") in ("function", "class_ctor", "library_fn")
            eligible = callable_kind and confidence >= threshold and convention not in (None, "", "unknown", "__unknown")
            if build in calls:
                calls[build] = {"eligible": False, "confidence": min(confidence, calls[build]["confidence"]),
                                "reason": "ambiguous_instance", "convention": None}
                continue
            calls[build] = {"eligible": eligible, "confidence": confidence,
                            "reason": None if eligible else "insufficient_abi" if callable_kind else "not_callable",
                            "convention": convention}
        result[key] = {"kind": entity["kind"], "status": entity.get("status", {}),
                       "fields": fields, "calls": calls, "abi_threshold": threshold}
    return result


_RUNTIME = r'''
local M = {}
local function fail(status, entity, members, reason)
  error({status=status or "unresolved", entity=entity,
         members_tried=members or {}, reason=reason}, 0)
end
local function copy(value)
  if type(value) ~= "table" then return value end
  local out = {}
  for k,v in pairs(value) do out[k] = copy(v) end
  return out
end
function M.describe() return copy(descriptors) end
function M.bind(host, build)
  if type(host) ~= "table" or type(build) ~= "string" then
    fail("unresolved", "module", {}, "host_and_build_required")
  end
  local bound = {entities={}, roots={}}
  function bound.describe() return copy(descriptors) end
  for key,descriptor in pairs(descriptors) do
    local entity, info = key, descriptor
    local function resolve()
      local status = info.status[build] or "unresolved"
      if status ~= "resolved" then fail(status, entity, {}, "pack_member_not_resolved") end
      if type(host.resolve) ~= "function" then fail("unresolved", entity, {}, "resolver_unavailable") end
      local resolution = host:resolve(entity, build)
      if type(resolution) ~= "table" then fail("unresolved", entity, {}, "invalid_resolution") end
      if resolution.status ~= "resolved" then
        fail(resolution.status, entity, resolution.members_tried, resolution.reason)
      end
      if resolution.value == nil then fail("unresolved", entity, resolution.members_tried, "missing_value") end
      return resolution
    end
    local function operate(operation, ...)
      local resolution = resolve()
      if type(host[operation]) ~= "function" then
        fail("unresolved", entity, resolution.members_tried, "operation_unavailable:" .. operation)
      end
      local function checked(...)
        local first = ...
        if type(first) == "table" and first.status and first.status ~= "resolved" then
          fail(first.status, entity, first.members_tried or resolution.members_tried, first.reason)
        end
        return ...
      end
      return checked(host[operation](host, resolution.value, ...))
    end
    local item = {fields={}}
    function item.describe() return copy(info) end
    function item.entry(...) return operate("entry", ...) end
    function item.handle(...) return operate("handle", ...) end
    local call = info.calls[build]
    if call and call.eligible then
      function item.call(...) return operate("call", entity, build, ...) end
    end
    if info.kind == "function" or info.kind == "library_fn" or info.kind == "vtable"
       or info.kind == "call_site" or info.kind == "patch_point" then
      function item.hook(...) return operate("hook", entity, build, ...) end
    end
    for name,field in pairs(info.fields[build] or {}) do
      local fieldName, fieldType = name, copy(field)
      item.fields[name] = {
        get=function(...) return operate("get_field", fieldName, copy(fieldType), ...) end,
        set=function(value, ...) return operate("set_field", fieldName, copy(fieldType), value, ...) end
      }
    end
    bound.entities[entity] = item
    if info.kind == "global" or info.kind == "data_root" or info.kind == "singleton"
       or info.kind == "global_data" then bound.roots[entity] = item end
  end
  return bound
end
return M
'''


def render_lua_bindings(pack: dict, *, abi_threshold: float = ABI_CONFIDENCE_THRESHOLD) -> str:
    """Return module text; all metadata originates in the validated pack."""
    from .hookpack_v2 import read_hookpack
    if isinstance(abi_threshold, bool) or not isinstance(abi_threshold, (int, float)) or not 0 <= abi_threshold <= 1:
        raise ValueError("ABI confidence threshold must be between zero and one")
    pack = read_hookpack(pack)
    if pack["format"] != "agentdecompile.hookpack/v2":
        raise ValueError("Lua bindings require a v2 hook pack")
    return ("-- Generated from agentdecompile.hookpack/v2. No runtime readiness is implied.\n"
            "local descriptors = " + _lua(_descriptors(pack, abi_threshold)) + "\n" + _RUNTIME)


def export_lua_bindings(pack: Path | dict, out: Path | str, *, abi_threshold: float = ABI_CONFIDENCE_THRESHOLD) -> dict:
    """Write one require-able module, without reading a database or live process."""
    from .hookpack_v2 import read_hookpack
    value = read_hookpack(pack)
    text = render_lua_bindings(value, abi_threshold=abi_threshold)
    payload = text.encode("utf-8")
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return {"format": "agentdecompile.lua-bindings/v1", "out": str(target),
            "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload),
            "entities": len(value["entities"]), "abi_threshold": abi_threshold,
            "runtime_verification": "not_run"}
