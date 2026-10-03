"""Shared helpers for collecting program-level and project-level metadata.

Used by:
- ``providers/project.py`` to enrich ``open-project`` responses with per-program
  details (function count, tags, bookmarks, versioning/checkout info).
- ``tool_providers.py`` base ``call_tool()`` to inject a concise
  ``projectContext`` block into every data-returning tool response.
"""

from __future__ import annotations

import logging
import re
import time

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agentdecompile_cli.context import ProgramInfo

from agentdecompile_cli.mcp_server.session_context import (
    SESSION_CONTEXTS,
    SessionContext,
    is_shared_server_handle,
)
from agentdecompile_cli.registry import classify_static_action, normalize_identifier

logger = logging.getLogger(__name__)


def _dedupe_program_keys(keys: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for key in keys:
        normalized = str(key).strip()
        if not normalized:
            continue
        dedupe_key = normalized.lower()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        unique.append(normalized)
    return unique


def _collect_project_inventory_program_keys(session: SessionContext) -> list[str]:
    project_binaries = getattr(session, "project_binaries", []) or []
    inventory_keys = [
        str(item.get("path") or item.get("programPath") or item.get("name") or "")
        for item in project_binaries
        if isinstance(item, dict)
    ]
    return _dedupe_program_keys(inventory_keys)


# ---------------------------------------------------------------------------
# Per-program summary (rich detail for open-project)
# ---------------------------------------------------------------------------


def collect_program_summary(program_info: ProgramInfo) -> dict[str, Any]:
    """Collect a rich metadata summary for a single loaded program.

    All Ghidra API calls are wrapped in try/except so the summary degrades
    gracefully when a program is partially loaded or an API is unavailable.
    """
    program = getattr(program_info, "program", None)
    if program is None:
        return {"name": getattr(program_info, "name", "unknown")}

    summary: dict[str, Any] = {"name": getattr(program_info, "name", "") or ""}

    # --- Function count ---
    try:
        fm = program.getFunctionManager()
        summary["functionCount"] = int(fm.getFunctionCount())
    except Exception:
        pass

    # --- Function tags ---
    try:
        fm = program.getFunctionManager()
        tag_mgr = fm.getFunctionTagManager()
        all_tags = tag_mgr.getAllFunctionTags()
        tags: list[dict[str, Any]] = []
        if all_tags:
            for tag in all_tags:
                tag_name = str(tag.getName())
                try:
                    use_count = int(tag_mgr.getUseCount(tag))
                except Exception:
                    use_count = 0
                tags.append({"name": tag_name, "useCount": use_count})
        summary["functionTags"] = tags
    except Exception:
        pass

    # --- Bookmarks ---
    try:
        bm = program.getBookmarkManager()
        summary["bookmarkCount"] = int(bm.getBookmarkCount())
        bm_types = bm.getBookmarkTypes()
        if bm_types:
            type_counts: dict[str, int] = {}
            for bt in bm_types:
                type_str = str(bt.getTypeString()) if hasattr(bt, "getTypeString") else str(bt)
                try:
                    type_counts[type_str] = int(bm.getBookmarkCount(type_str))
                except Exception:
                    type_counts[type_str] = 0
            summary["bookmarksByType"] = type_counts
    except Exception:
        pass

    # --- Listing stats ---
    try:
        listing = program.getListing()
        summary["instructionCount"] = int(listing.getNumInstructions())
    except Exception:
        pass

    try:
        listing = program.getListing()
        # getCommentAddressCount can vary by Ghidra version
        if hasattr(listing, "getCommentAddressIterator"):
            # Count PRE comments as a proxy if getCommentAddressCount is absent
            pass
    except Exception:
        pass

    # --- Language / Compiler ---
    try:
        summary["languageId"] = str(program.getLanguageID())
    except Exception:
        pass

    try:
        summary["compilerSpec"] = str(program.getCompilerSpec().getCompilerSpecID())
    except Exception:
        pass

    # --- Program metadata (selective) ---
    _METADATA_KEYS = (
        "Executable Format",
        "Compiler",
        "Created With Ghidra Version",
        "Date Created",
        "Executable Location",
        "Executable MD5",
        "Executable SHA256",
    )
    try:
        raw_meta = program.getMetadata()
        if raw_meta:
            picked: dict[str, str] = {}
            for key in _METADATA_KEYS:
                val = raw_meta.get(key)
                if val is not None:
                    picked[key] = str(val)
            if picked:
                summary["metadata"] = picked
    except Exception:
        pass

    # --- DomainFile versioning/checkout ---
    try:
        df = program.getDomainFile()
        if df is not None:
            versioning: dict[str, Any] = {}
            try:
                versioning["isVersioned"] = bool(df.isVersioned())
            except Exception:
                pass
            try:
                versioning["isCheckedOut"] = bool(df.isCheckedOut())
            except Exception:
                pass
            try:
                versioning["isCheckedOutExclusive"] = bool(df.isCheckedOutExclusive())
            except Exception:
                pass
            try:
                versioning["modifiedSinceCheckout"] = bool(df.modifiedSinceCheckout())
            except Exception:
                pass
            try:
                versioning["canCheckout"] = bool(df.canCheckout())
            except Exception:
                pass
            try:
                versioning["canCheckin"] = bool(df.canCheckin())
            except Exception:
                pass
            try:
                versioning["currentVersion"] = int(df.getVersion())
            except Exception:
                pass
            try:
                versioning["latestVersion"] = int(df.getLatestVersion())
            except Exception:
                pass
            try:
                last_mod_ms = df.getLastModifiedTime()
                if last_mod_ms:
                    versioning["lastModified"] = time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(last_mod_ms / 1000.0)
                    )
            except Exception:
                pass
            try:
                versioning["fileSize"] = int(df.length())
            except Exception:
                pass

            # Checkout status detail
            if versioning.get("isCheckedOut"):
                try:
                    status = df.getCheckoutStatus()
                    if status is not None:
                        versioning["checkoutUser"] = str(status.getUser()) if hasattr(status, "getUser") else None
                        try:
                            versioning["checkoutVersion"] = int(status.getCheckoutVersion())
                        except Exception:
                            pass
                except Exception:
                    pass

            if versioning:
                summary["versioning"] = versioning
    except Exception:
        pass

    return summary


# ---------------------------------------------------------------------------
# Compact project context (injected into every tool response)
# ---------------------------------------------------------------------------


def _analysis_complete_for_info(program_info: Any) -> bool | None:
    if program_info is None:
        return None
    if hasattr(program_info, "analysis_complete"):
        try:
            return bool(program_info.analysis_complete)
        except Exception:
            pass
    value = getattr(program_info, "ghidra_analysis_complete", None)
    if value is None:
        return None
    return bool(value)


def _resolve_domain_file(program_info: Any) -> Any | None:
    df = getattr(program_info, "domain_file", None)
    if df is not None:
        return df
    program = getattr(program_info, "program", None)
    if program is None:
        return None
    try:
        return program.getDomainFile()
    except Exception:
        return None


def _domain_file_checkout_flags(df: Any) -> tuple[bool, bool, bool] | None:
    try:
        return (
            bool(df.isCheckedOut()),
            bool(df.modifiedSinceCheckout()),
            bool(df.canCheckin()),
        )
    except Exception:
        return None


def _compact_checkout_summary(
    open_programs: dict[str, Any],
    *,
    is_shared: bool,
) -> dict[str, Any] | None:
    if not is_shared or not open_programs:
        return None

    checked_out = 0
    modified = 0
    can_checkin = 0
    programs: list[dict[str, Any]] = []

    for path, info in open_programs.items():
        df = _resolve_domain_file(info)
        if df is None:
            continue
        flags = _domain_file_checkout_flags(df)
        if flags is None:
            continue

        is_checked_out, is_modified, can_ci = flags
        entry: dict[str, Any] = {"program": str(path)}
        if is_checked_out:
            checked_out += 1
            entry["isCheckedOut"] = True
        if is_modified:
            modified += 1
            entry["modifiedSinceCheckout"] = True
        if can_ci:
            can_checkin += 1
            entry["canCheckin"] = True
        if len(entry) > 1:
            programs.append(entry)

    if checked_out == 0 and modified == 0 and can_checkin == 0:
        return None

    summary: dict[str, Any] = {
        "checkedOutCount": checked_out,
        "modifiedCount": modified,
        "canCheckinCount": can_checkin,
    }
    if programs:
        summary["programs"] = programs
    return summary


def collect_project_context(session_id: str) -> dict[str, Any] | None:
    """Build a compact project-context dict for the given session.

    Returns ``None`` if no project/programs are loaded (so the caller can
    skip injection).
    """
    session: SessionContext = SESSION_CONTEXTS.get_or_create(session_id)
    handle = session.project_handle
    open_programs = session.open_programs or {}
    active_key = session.active_program_key

    if not handle and not open_programs:
        project_inventory = _collect_project_inventory_program_keys(session)
        if not project_inventory:
            return None
    else:
        project_inventory = _collect_project_inventory_program_keys(session)

    open_program_keys = _dedupe_program_keys(list(open_programs.keys()))

    ctx: dict[str, Any] = {}

    # --- Mode and path ---
    is_shared = is_shared_server_handle(handle)
    if handle:
        mode = str(handle.get("mode", "unknown"))
        ctx["mode"] = mode
        if is_shared:
            ctx["serverHost"] = handle.get("server_host") or handle.get("serverHost")
            ctx["serverPort"] = handle.get("server_port") or handle.get("serverPort")
            ctx["repository"] = handle.get("repository") or handle.get("repository_name")
        path = handle.get("path") or handle.get("gpr_path")
        if path:
            ctx["projectPath"] = str(path)
        project_name = handle.get("projectName") or handle.get("project_name")
        if project_name:
            ctx["projectName"] = str(project_name)

    # --- Programs ---
    project_program_count = len(project_inventory) or len(open_program_keys)
    ctx["programCount"] = project_program_count
    ctx["projectProgramCount"] = project_program_count
    ctx["openProgramCount"] = len(open_program_keys)
    if open_program_keys:
        ctx["openPrograms"] = open_program_keys
    if active_key:
        ctx["activeProgram"] = active_key

    analysis_by_program: dict[str, bool] = {}
    for key in open_program_keys:
        complete = _analysis_complete_for_info(open_programs.get(key))
        if complete is not None:
            analysis_by_program[key] = complete
    if len(analysis_by_program) > 1:
        ctx["analysisByProgram"] = analysis_by_program
    if active_key in analysis_by_program:
        ctx["analysisComplete"] = analysis_by_program[active_key]

    checkout_summary = _compact_checkout_summary(open_programs, is_shared=is_shared)
    if checkout_summary:
        ctx["checkoutSummary"] = checkout_summary

    return ctx


# Tools that should NOT receive the projectContext injection
# (their response is meta/administrative, not program data).
_SKIP_CONTEXT_TOOLS: frozenset[str] = frozenset({
    "debuginfo",
    "listtools",
})


def collect_target_project_context(session_id: str, program_info: Any) -> dict[str, Any] | None:
    """Bind evidence context to its resolved program, not the session's last open tab."""
    context = collect_project_context(session_id) or {}
    domain_file = _resolve_domain_file(program_info)
    if domain_file is None:
        return {"scope": "target-program", "projectPath": None, "activeProgram": str(getattr(program_info, "path", "") or getattr(program_info, "name", "")), "contextUnavailable": "Program has no domain file"}
    # Never retain project identity/counts from a different session-active project.
    for key in ("projectPath", "projectName", "repository", "serverHost", "serverPort", "mode", "programCount", "projectProgramCount", "checkoutSummary", "analysisComplete"):
        context.pop(key, None)
    context["scope"] = "target-program"
    context["activeProgram"] = str(domain_file.getPathname())
    complete = _analysis_complete_for_info(program_info)
    if complete is not None:
        context["analysisComplete"] = complete
    try:
        shared = domain_file.getSharedProjectURL(None)
        if shared is not None:
            from urllib.parse import urlsplit, unquote
            url = urlsplit(str(shared))
            context.update(mode="shared-server", serverHost=url.hostname, serverPort=url.port, repository=unquote(url.path.strip("/").split("/", 1)[0]), programUrl=str(shared))
        else:
            locator = domain_file.getProjectLocator()
            if locator is not None:
                context.update(mode="local-gpr", projectPath=str(locator.getMarkerFile().getAbsolutePath()), projectName=str(locator.getName()))
    except Exception as exc:
        context["contextUnavailable"] = "Target project locator unavailable: " + type(exc).__name__
    return context


def attach_project_context_to_payload(
    payload: dict[str, Any],
    session_id: str,
    *,
    tool_name_normalized: str = "",
    target_program_info: Any = None,
) -> None:
    """Attach ``projectContext`` to an error or ad-hoc JSON payload when absent."""
    if tool_name_normalized in _SKIP_CONTEXT_TOOLS:
        return
    if "projectContext" in payload:
        return
    ctx = collect_target_project_context(session_id, target_program_info) if target_program_info is not None else collect_project_context(session_id)
    if ctx is not None:
        payload["projectContext"] = ctx


def inject_project_context(
    response_text: str,
    session_id: str,
    *,
    tool_name_normalized: str = "",
    target_program_info: Any = None,
) -> str:
    """Parse a JSON tool response, inject ``projectContext``, re-serialize.

    Returns the original ``response_text`` unchanged if:
    - The response is not valid JSON.
    - The response already has a ``projectContext`` key.
    - No project/programs are loaded.
    - The tool is in the skip-list.
    """
    if tool_name_normalized in _SKIP_CONTEXT_TOOLS:
        return response_text

    import json as _json

    try:
        data = _json.loads(response_text)
    except Exception:
        return response_text

    if not isinstance(data, dict):
        return response_text

    if "projectContext" in data:
        return response_text

    attach_project_context_to_payload(
        data,
        session_id,
        tool_name_normalized=tool_name_normalized,
        target_program_info=target_program_info,
    )
    if "projectContext" not in data:
        return response_text
    return _json.dumps(data)


# Tools whose successful responses should carry uiVisibility / guiHint.
# Keep aligned with _AUTO_CHECKIN_TRIGGER_TOOLS in tool_providers.py.
_MUTATING_UI_HINT_TOOLS: frozenset[str] = frozenset(
    {
        "managesymbols",
        "managefunction",
        "managecomments",
        "managestructures",
        "manageenums",
        "managedatatypes",
        "applydatatype",
        "managebookmarks",
        "managefunctiontags",
        "managestrings",
        "matchfunction",
        "resolvemodificationconflict",
    }
)

# Multi-mode tools: only attach UI hints / auto-checkin when payload action is mutating.
_MUTATING_TOOL_ACTIONS: dict[str, frozenset[str]] = {
    "managefunction": frozenset({"rename", "setprototype", "setcallingconvention", "setreturntype", "renamevariable", "setvariabletype", "changedatatypes", "delete", "create", "setproperties", "setstorage"}),
    "manageenums": frozenset(
        {
            "create",
            "addmember",
            "editmember",
            "removemember",
            "delete",
        },
    ),
    "managestrings": frozenset({"create", "update", "delete"}),
    "managedatatypes": frozenset({"create", "update", "delete", "apply"}),
    "managefunctiontags": frozenset({"add", "remove", "set"}),
}


def payload_has_mutating_action(tool_name_normalized: str, payload: dict[str, Any]) -> bool:
    """Return True when a multi-mode tool response represents a state mutation."""
    allowed = _MUTATING_TOOL_ACTIONS.get(tool_name_normalized)
    if allowed is None:
        return True
    action_raw = payload.get("action")
    if action_raw in (None, ""):
        return False
    return normalize_identifier(str(action_raw)) in allowed


def _is_successful_mutation_payload(payload: dict[str, Any]) -> bool:
    if payload.get("success") is False:
        return False
    if payload.get("modificationConflict") is True:
        return False
    error_value = payload.get("error")
    if error_value not in (None, "", False):
        return False
    return True


def build_ui_visibility(session_id: str, *, auto_checkin_enabled: bool, target_shared: bool | None = None) -> dict[str, Any]:
    """Structured UI visibility metadata for mutating tool responses."""
    session: SessionContext = SESSION_CONTEXTS.get_or_create(session_id)
    handle = session.project_handle
    is_shared = is_shared_server_handle(handle) if target_shared is None else target_shared
    return {
        "liveInCodeBrowser": False,
        "codeBrowserSync": "reload-or-checkout",
        "runtime": "headless-mcp",
        "persistence": "shared-checkin" if is_shared else "local-save",
        "autoCheckinEnabled": auto_checkin_enabled,
    }


def build_gui_hint(session_id: str, *, auto_checkin_enabled: bool, target_shared: bool | None = None) -> str:
    """Human-readable hint for agents about GUI visibility after mutations."""
    session: SessionContext = SESSION_CONTEXTS.get_or_create(session_id)
    is_shared = is_shared_server_handle(session.project_handle) if target_shared is None else target_shared
    parts = [
        "Mutation applied in the headless MCP session (separate JVM from CodeBrowser).",
    ]
    if is_shared:
        parts.append(
            "On shared server: check in or sync, then reload or checkout in CodeBrowser to view changes.",
        )
    else:
        parts.append(
            "On local project: changes save to the .gpr; reload the program in CodeBrowser to view.",
        )
    if auto_checkin_enabled:
        parts.append("Auto-checkin is enabled — persistence runs automatically after modifying tools.")
    else:
        parts.append("Call checkin-program to persist before viewing in CodeBrowser.")
    return " ".join(parts)


def attach_ui_hints_to_payload(
    payload: dict[str, Any],
    session_id: str,
    *,
    tool_name_normalized: str = "",
    auto_checkin_enabled: bool = False,
) -> None:
    """Attach ``uiVisibility`` and ``guiHint`` when this is a successful mutating tool."""
    if tool_name_normalized in _SKIP_CONTEXT_TOOLS:
        return
    if tool_name_normalized not in _MUTATING_UI_HINT_TOOLS:
        return
    if not payload_has_mutating_action(tool_name_normalized, payload):
        return
    if "uiVisibility" in payload or "guiHint" in payload:
        return
    if not _is_successful_mutation_payload(payload):
        return
    context = payload.get("projectContext") or {}
    target_shared = context.get("mode") == "shared-server" if context.get("scope") == "target-program" and context.get("mode") else None
    payload["uiVisibility"] = build_ui_visibility(session_id, auto_checkin_enabled=auto_checkin_enabled, target_shared=target_shared)
    payload["guiHint"] = build_gui_hint(session_id, auto_checkin_enabled=auto_checkin_enabled, target_shared=target_shared)


def inject_ui_hints(
    response_text: str,
    session_id: str,
    *,
    tool_name_normalized: str = "",
    auto_checkin_enabled: bool = False,
) -> str:
    """Parse JSON tool response and inject UI hint fields for mutating tools."""
    if tool_name_normalized in _SKIP_CONTEXT_TOOLS:
        return response_text

    import json as _json

    try:
        data = _json.loads(response_text)
    except Exception:
        return response_text

    if not isinstance(data, dict):
        return response_text

    attach_ui_hints_to_payload(
        data,
        session_id,
        tool_name_normalized=tool_name_normalized,
        auto_checkin_enabled=auto_checkin_enabled,
    )
    if "uiVisibility" not in data and "guiHint" not in data:
        return response_text
    return _json.dumps(data)


def summarize_auto_checkin_result(
    checkin_payload: dict[str, Any],
    *,
    exception: str | None = None,
) -> dict[str, Any]:
    """Compact auto-checkin outcome for attachment to a mutating tool response."""
    if exception:
        return {
            "performed": True,
            "success": False,
            "hint": f"Auto check-in failed: {exception}",
            "error": exception,
        }

    results_raw = checkin_payload.get("results")
    results: list[dict[str, Any]] = [r for r in results_raw if isinstance(r, dict)] if isinstance(results_raw, list) else []
    succeeded = sum(1 for entry in results if entry.get("success"))
    failed = len(results) - succeeded
    aggregate_ok = checkin_payload.get("success", True) is not False and failed == 0

    summary: dict[str, Any] = {
        "performed": True,
        "success": aggregate_ok,
        "mode": checkin_payload.get("mode", "checkin_all"),
        "count": checkin_payload.get("count", len(results)),
        "succeededCount": succeeded,
        "failedCount": failed,
    }
    if results:
        summary["results"] = [
            {
                "programPath": entry.get("programPath"),
                "success": entry.get("success"),
                "mode": entry.get("mode"),
                "error": entry.get("error"),
            }
            for entry in results[:10]
        ]
    error_value = checkin_payload.get("error")
    if error_value:
        summary["error"] = error_value

    if aggregate_ok:
        if succeeded == 0 and not results:
            summary["hint"] = "Auto check-in ran; no open programs required persistence."
        else:
            summary["hint"] = f"Auto check-in completed for {succeeded} program(s)."
    else:
        summary["hint"] = (
            f"Auto check-in had {failed} failure(s); review autoCheckin.results "
            "or resolve checkout issues before reloading CodeBrowser."
        )
    return summary


def attach_auto_checkin_to_payload(
    parent_payload: dict[str, Any],
    checkin_payload: dict[str, Any] | None,
    *,
    exception: str | None = None,
) -> None:
    """Merge silent auto-checkin outcome into the mutating tool JSON response."""
    if exception:
        parent_payload["autoCheckin"] = summarize_auto_checkin_result({}, exception=exception)
    elif isinstance(checkin_payload, dict):
        parent_payload["autoCheckin"] = summarize_auto_checkin_result(checkin_payload)
    else:
        return

    hint = parent_payload.get("autoCheckin", {}).get("hint") if isinstance(parent_payload.get("autoCheckin"), dict) else None
    if hint:
        existing = parent_payload.get("guiHint")
        if existing:
            parent_payload["guiHint"] = f"{existing} {hint}"
        else:
            parent_payload["guiHint"] = str(hint)


# This source check covers declarative action inventories and literal call sites.
# Dynamic catalog dispatch is the expert surface, not an inferred routine action.
# It deliberately does not claim whole-program JavaScript/data-flow verification.
def _static_js_tokens(source: str) -> list[tuple[int, int, str]]:
    """Lex strings/comments, descending into interpolated template expressions."""
    tokens: list[tuple[int, int, str]] = []

    def scan(index: int, interpolation: bool = False) -> int:
        depth = 0
        while index < len(source):
            start = index
            ch = source[index]
            if source.startswith("//", index):
                end = source.find("\n", index)
                index = len(source) if end < 0 else end
                tokens.append((start, index, "comment"))
            elif source.startswith("/*", index):
                end = source.find("*/", index + 2)
                index = len(source) if end < 0 else end + 2
                tokens.append((start, index, "comment"))
            elif ch in "\"'":
                index += 1
                while index < len(source):
                    if source[index] == "\\":
                        index += 2
                    elif source[index] == ch:
                        index += 1
                        break
                    else:
                        index += 1
                tokens.append((start, index, "string"))
            elif ch == "`":
                index += 1
                interpolated = False
                while index < len(source):
                    if source[index] == "\\":
                        index += 2
                    elif source[index] == "`":
                        index += 1
                        if not interpolated:
                            tokens.append((start, index, "string"))
                        break
                    elif source.startswith("${", index):
                        interpolated = True
                        index = scan(index + 2, True)
                    else:
                        index += 1
            elif ch == "/" and source[:index].rstrip()[-1:] in "(=,:!&|?[{":
                # Regex literal contents are not JS strings or comments.
                index += 1
                in_class = False
                while index < len(source):
                    current = source[index]
                    index += 1
                    if current == "\\":
                        index += 1
                    elif current == "[":
                        in_class = True
                    elif current == "]":
                        in_class = False
                    elif current == "/" and not in_class:
                        break
            else:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    if interpolation and depth == 0:
                        return index + 1
                    depth -= 1
                index += 1
        return index

    scan(0)
    return sorted(tokens)


_STATIC_ACTION_ID = re.compile(r"(?:mcp|corpus|recover|workbench|review)\.[a-z][a-z0-9-]*\Z")
_STATIC_MODE = re.compile(r"(?:operation|mode|action)\s*:\s*['\"]([^'\"]+)['\"]")
_WORKFLOW_CONTROL_GUARD = re.compile(
    r'if\s*\(\s*\[\s*"pause"\s*,\s*"resume"\s*,\s*"stop"\s*\]'
    r'\.indexOf\(operation\)\s*===\s*-1\s*\)\s*return(?:\s+Promise\.resolve\(null\))?\s*;'
)


def static_surface_action_violations(source: str) -> list[dict[str, Any]]:
    """Find routine pipeline controls using backend action/mode ownership (R7).

    History-label object keys and equality comparisons describe actions; they do
    not offer actions. Other action literals are checked regardless of widget or
    handler names. No per-file or per-action suppression exceptions are accepted.
    Comments are erased before checking; dynamic workflow modes require a local
    finite guard. Runtime catalog rows remain available only in the expert dock.
    """
    tokens = _static_js_tokens(source)
    clean = list(source)
    for start, end, kind in tokens:
        if kind == "comment":
            clean[start:end] = ["\n" if ch == "\n" else " " for ch in source[start:end]]
    code = "".join(clean)
    structural = list(code)
    for token_start, token_end, token_kind in tokens:
        if token_kind == "string":
            structural[token_start:token_end] = [" " for _ in range(token_end - token_start)]
    structure = "".join(structural)
    violations: list[dict[str, Any]] = []
    for start, end, kind in tokens:
        if kind != "string":
            continue
        action_id = source[start + 1:end - 1]
        if not _STATIC_ACTION_ID.fullmatch(action_id):
            continue
        before, after = code[:start].rstrip(), code[end:].lstrip()
        if before.endswith(("===", "!==", "==", "!=")) or after.startswith(("===", "!==", "==", "!=")):
            continue
        if before.endswith("+") or after.startswith("+"):
            continue  # String/path fragments are not complete action IDs.
        if after.startswith(":"):
            continue  # Object key: historical labels, not action values.
        # Literal argument object, when present. Missing mode fails closed for
        # mixed tools such as manage-workflow; it is not assumed to be read-only.
        params: dict[str, Any] = {}
        if after.startswith(","):
            argument = after[1:].lstrip()
            if argument.startswith("{"):
                found = _STATIC_MODE.search(argument.split("}", 1)[0])
                if found:
                    params["operation"] = found.group(1)
        if action_id == "workbench.workflow-control" and not params:
            # Only a guard in the enclosing helper may prove a dynamic mode.
            # Prove the declaration is still open; a previously closed helper
            # cannot lend its guard to a following callback. Require a leading
            # guard and reject nested callbacks or reassignment we cannot prove.
            functions = list(re.finditer(r"\bfunction\s+\w+\s*\([^)]*\)\s*\{", structure[:start]))
            if functions:
                body_start = functions[-1].end()
                body = code[body_start:start]
                syntax = structure[body_start:start]
                depth, enclosed = 1, True
                for char in syntax:
                    depth += (char == "{") - (char == "}")
                    if depth <= 0:
                        enclosed = False
                        break
                guard = _WORKFLOW_CONTROL_GUARD.match(body.lstrip())
                uncertain = re.search(r"=>|\bfunction\b|\boperation\s*(?:=(?!=)|\+=|-=|\+\+|--)", syntax)
                if enclosed and guard and not uncertain:
                    params["operation"] = "pause"  # representative of the finite set
        ownership = classify_static_action(action_id, params)
        if ownership in {"pipeline", "expert-only"}:
            violations.append({
                "line": source.count("\n", 0, start) + 1,
                "action": action_id,
                "classification": ownership,
                "message": "Routine controls cannot offer this action/mode; use the expert catalog.",
            })
    # A catalog fallback bypasses the explicit routine inventory. Keeping this
    # check structural avoids an allowlist of today's catalog contents.
    preferred = re.search(r"function\s+preferredActions\([^)]*\)\s*\{([\s\S]*?)\n  \}", code)
    if preferred and re.search(r"return\s+catalog\s*(?:\.|;)", preferred.group(1)):
        violations.append({
            "line": code.count("\n", 0, preferred.start()) + 1,
            "action": "catalog fallback",
            "classification": "expert-only",
            "message": "Routine actions must use their explicit inventory, not the full catalog.",
        })
    return violations
