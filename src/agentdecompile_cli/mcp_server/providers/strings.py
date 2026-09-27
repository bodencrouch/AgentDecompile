"""Strings Tool Provider - manage-strings, list-strings, search-strings, search-code.

  - manage-strings: mode = list (enumerate strings), search (query/regex), count.
  - list-strings: Enumerate all defined strings (minLength, pagination, optional includeReferencingFunctions).
  - search-strings: Search strings by query; delegates to manage-strings or list logic.
  - search-code: Search in decompiled/source-like code (different from raw string listing).

Uses _collectors.collect_strings for listing; optional xref lookup for referencing functions.
"""

from __future__ import annotations

import difflib
import logging
import re

from typing import TYPE_CHECKING, Any

from mcp import types

from agentdecompile_cli.mcp_server.providers._collectors import collect_strings
from agentdecompile_cli.mcp_server.providers._program_context import ghidra_tools_for_program
from agentdecompile_cli.mcp_server.tool_providers import (
    ToolProvider,
    create_success_response,
    n,
)
from agentdecompile_cli.registry import Tool

if TYPE_CHECKING:
    from types import SimpleNamespace

    from ghidra.program.model.address import Address as GhidraAddress  # pyright: ignore[reportMissingImports, reportMissingModuleSource, reportMissingTypeStubs]
    from ghidra.program.model.listing import Program as GhidraProgram  # pyright: ignore[reportMissingImports, reportMissingModuleSource, reportMissingTypeStubs]
    from ghidra.program.model.symbol import ReferenceManager as GhidraReferenceManager  # pyright: ignore[reportMissingImports, reportMissingModuleSource, reportMissingTypeStubs]

    from agentdecompile_cli.launcher import ProgramInfo

logger = logging.getLogger(__name__)

# search-code fallback caps (used when the code index is absent, e.g. --local).
_SEARCH_CODE_MAX_FUNCTIONS = 500
_SEARCH_CODE_DECOMPILE_TIMEOUT_S = 10

_STRING_MUTATING_MODES: frozenset[str] = frozenset({"create", "update", "delete"})


def normalize_string_encoding(encoding: str | None) -> str:
    """Return ``ascii`` or ``utf16`` for supported program string encodings."""
    enc = (encoding or "ascii").strip().lower()
    if enc in {"utf16", "utf-16", "unicode", "wide"}:
        return "utf16"
    return "ascii"


def encode_program_string(value: str, encoding: str) -> bytes:
    """Encode a logical string value for writing into program memory."""
    if encoding == "utf16":
        return value.encode("utf-16-le") + b"\x00\x00"
    return value.encode("utf-8") + b"\x00"


def ghidra_string_type_name(encoding: str) -> str:
    """Ghidra data-type name for a terminated string encoding."""
    return "unicode" if encoding == "utf16" else "string"


class StringToolProvider(ToolProvider):
    HANDLERS = {
        "managestrings": "_handle",
        "liststrings": "_handle_list_strings",
        "searchstrings": "_handle_search_strings",
        "searchcode": "_handle_search_code",
    }

    def list_tools(self) -> list[types.Tool]:
        logger.debug("diag.enter %s", "mcp_server/providers/strings.py:StringToolProvider.list_tools")
        return [
            types.Tool(
                name=Tool.MANAGE_STRINGS.value,
                description="Search, filter, list, create, update, delete, and measure literal text strings embedded in the compiled program's data segments.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "programPath": {"type": "string", "description": "The active program project."},
                        "mode": {
                            "type": "string",
                            "description": "What operation to perform on the text data.",
                            "enum": ["list", "search", "count", "create", "update", "delete"],
                            "default": "list",
                        },
                        "addressOrSymbol": {"type": "string", "description": "Memory address or symbol for create/update/delete."},
                        "value": {"type": "string", "description": "String content to write for create/update."},
                        "encoding": {
                            "type": "string",
                            "description": "String encoding for create/update.",
                            "enum": ["ascii", "utf16"],
                            "default": "ascii",
                        },
                        "query": {"type": "string", "description": "Search query or regex pattern to look for in the program strings."},
                        "minLength": {"type": "integer", "default": 4, "description": "Ignore any text string shorter than this number of characters."},
                        "limit": {"type": "integer", "default": 100, "description": "Number of strings to return. Typical values are 100–500."},
                        "offset": {"type": "integer", "default": 0, "description": "Pagination offset; omit unless fetching beyond the first page."},
                        "includeReferencingFunctions": {"type": "boolean", "default": False, "description": "If true, also looks up what exact function uses this string (can be slow)."},
                    },
                    "required": [],
                },
            ),
            types.Tool(
                name=Tool.LIST_STRINGS.value,
                description="Dump all recognized text strings found in the current program's memory.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "programPath": {"type": "string", "description": "The active program project."},
                        "minLength": {"type": "integer", "default": 4, "description": "Ignore any text string shorter than this number of characters."},
                        "limit": {"type": "integer", "default": 100, "description": "Number of strings to return. Typical values are 100\u2013500."},
                        "offset": {"type": "integer", "default": 0, "description": "Pagination offset; omit unless fetching beyond the first page."},
                        "includeReferencingFunctions": {"type": "boolean", "default": False, "description": "If true, identifies exactly which function references the text."},
                    },
                    "required": [],
                },
            ),
            types.Tool(
                name=Tool.SEARCH_STRINGS.value,
                description="Search the program's defined strings for a specific text pattern.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "programPath": {"type": "string", "description": "The active program project."},
                        "query": {"type": "string", "description": "The exact text or regex to find."},
                        "mode": {"type": "string", "description": "Internal routing fallback logic.", "enum": ["search", "list"], "default": "list"},
                        "limit": {"type": "integer", "default": 100, "description": "Number of strings to return. Typical values are 100–500."},
                        "offset": {"type": "integer", "default": 0, "description": "Pagination offset."},
                        "includeReferencingFunctions": {"type": "boolean", "default": False, "description": "Find referencing functions."},
                    },
                    "required": [],
                },
            ),
            types.Tool(
                name=Tool.SEARCH_CODE.value,
                description="Search function names and decompiled C for a text or regex pattern. Without a code index it decompiles up to 500 functions (overrideMaxFunctionsLimit lifts the cap).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "programPath": {"type": "string", "description": "The active program project."},
                        "binaryName": {"type": "string", "description": "Alternative parameter for programPath."},
                        "query": {"type": "string", "description": "Text or regex to find in function names and decompiled code."},
                        "searchMode": {"type": "string", "description": "How to match: semantic (code index), literal, or regex.", "enum": ["semantic", "literal", "regex"], "default": "semantic"},
                        "caseSensitive": {"type": "boolean", "default": False, "description": "Case-sensitive matching (fallback search)."},
                        "includeFullCode": {"type": "boolean", "default": False, "description": "Include the full decompiled function in each result."},
                        "previewLength": {"type": "integer", "default": 200, "description": "Snippet length around a code match."},
                        "overrideMaxFunctionsLimit": {"type": "boolean", "default": False, "description": "Scan every function instead of the first 500."},
                        "limit": {"type": "integer", "default": 100, "description": "Number of results to return. Typical values are 100–500."},
                        "offset": {"type": "integer", "default": 0, "description": "Pagination offset."},
                    },
                    "required": ["query"],
                },
            ),
        ]

    async def _handle_list_strings(self, args: dict[str, Any], *, program_info: ProgramInfo | SimpleNamespace | None) -> list[types.TextContent]:
        logger.debug("diag.enter %s", "mcp_server/providers/strings.py:StringToolProvider._handle_list_strings")
        updated = dict(args)
        updated["mode"] = "list"
        return await self._handle(updated, program_info=program_info)

    async def _handle_search_strings(self, args: dict[str, Any], *, program_info: ProgramInfo | SimpleNamespace | None) -> list[types.TextContent]:
        logger.debug("diag.enter %s", "mcp_server/providers/strings.py:StringToolProvider._handle_search_strings")
        updated = dict(args)
        if not self._get_str(updated, "mode"):
            updated["mode"] = "search"
        return await self._handle(updated, program_info=program_info)

    async def _handle_search_code(self, args: dict[str, Any], *, program_info: ProgramInfo | SimpleNamespace | None) -> list[types.TextContent]:
        logger.debug("diag.enter %s", "mcp_server/providers/strings.py:StringToolProvider._handle_search_code")
        ghidra_tools = ghidra_tools_for_program(program_info)
        self._require_program(program_info=program_info)
        query: str = self._require_str(args, "query", "pattern", "text", name="query")
        offset, limit = self._get_pagination_params(args, default_limit=10)
        mode: str = self._get_str(args, "searchmode", "mode", default="semantic")

        if ghidra_tools is not None:
            try:
                from agentdecompile_cli.models import SearchMode

                mode_norm: str = mode.strip().lower()
                search_mode = SearchMode.LITERAL if mode_norm == "literal" else SearchMode.SEMANTIC
                results = ghidra_tools.search_code(
                    query=query,
                    limit=limit,
                    offset=offset,
                    search_mode=search_mode,
                )
                if hasattr(results, "model_dump"):
                    return create_success_response(results.model_dump())
                return create_success_response({"query": query, "results": results})
            except Exception as e:
                logger.warning("search-code semantic/literal backend unavailable, using fallback search: %s", e)

        assert program_info is not None, "Program info is required for search-code"
        return create_success_response(self._search_code_fallback(args, query, mode, offset, limit, program_info=program_info))

    def _search_code_fallback(
        self,
        args: dict[str, Any],
        query: str,
        mode: str,
        offset: int,
        limit: int,
        *,
        program_info: ProgramInfo | SimpleNamespace,
    ) -> dict[str, Any]:
        """Search function names and decompiled C when the code index is unavailable.

        Scans at most ``_SEARCH_CODE_MAX_FUNCTIONS`` functions (lifted by
        overrideMaxFunctionsLimit) with a per-function decompile timeout, the
        same lease pattern search-everything uses for its decompilation scope.
        """
        logger.debug("diag.enter %s", "mcp_server/providers/strings.py:StringToolProvider._search_code_fallback")
        program = program_info.program
        fm = self._get_function_manager(program, program_info=program_info)
        case_sensitive = self._get_bool(args, "casesensitive", default=False)
        include_full_code = self._get_bool(args, "includefullcode", "fullcode", default=False)
        preview_length = self._get_int(args, "previewlength", "previewlen", "snippetlength", default=200) or 200
        no_limit = self._get_bool(args, "overridemaxfunctionslimit", "nolimit", default=False)
        max_functions = None if no_limit else _SEARCH_CODE_MAX_FUNCTIONS
        mode_norm = mode.strip().lower()
        flags = 0 if case_sensitive else re.IGNORECASE
        if mode_norm == "regex":
            try:
                pattern = re.compile(query, flags)
            except re.error as exc:
                raise ValueError(f"Invalid regex for search-code: {exc}") from exc
        else:
            pattern = re.compile(re.escape(query), flags)

        def _snippet(text: str, m: re.Match[str]) -> str:
            half = max(preview_length // 2, 20)
            start = max(m.start() - half, 0)
            end = min(m.end() + half, len(text))
            return ("..." if start else "") + text[start:end] + ("..." if end < len(text) else "")

        matches: list[dict[str, Any]] = []
        skipped = 0
        scanned = 0
        decompile_failures = 0
        scan_capped = False
        decompile_unavailable: str | None = None

        lease_cm: Any = None
        try:
            from agentdecompile_cli.mcp_server.providers._collectors import make_task_monitor
            from agentdecompile_cli.mcp_utils.decompiler_util import acquire_decompiler_for_program, get_decompiled_function_from_results

            session_decompiler: Any = None
            getter = getattr(program_info, "get_decompiler", None)
            if callable(getter):
                try:
                    session_decompiler = getter()
                except Exception:
                    session_decompiler = getattr(program_info, "decompiler", None)
            else:
                session_decompiler = getattr(program_info, "decompiler", None)
            lease_cm = acquire_decompiler_for_program(session_decompiler, program)
            monitor = make_task_monitor()
        except Exception as exc:
            decompile_unavailable = str(exc)
            lease_cm = None

        def _scan(decompiler: Any) -> None:
            nonlocal skipped, scanned, decompile_failures, scan_capped
            for func in fm.getFunctions(True):
                if len(matches) >= limit:
                    break
                if max_functions is not None and scanned >= max_functions:
                    scan_capped = True
                    break
                scanned += 1
                function_name = str(func.getName())
                name_match = pattern.search(function_name)
                code = ""
                if decompiler is not None:
                    try:
                        dr = decompiler.decompileFunction(func, _SEARCH_CODE_DECOMPILE_TIMEOUT_S, monitor)
                        if dr is not None and dr.decompileCompleted():
                            df = get_decompiled_function_from_results(dr)
                            code = str(df.getC()) if df is not None else ""
                        else:
                            decompile_failures += 1
                    except Exception:
                        decompile_failures += 1
                code_match = pattern.search(code) if code else None
                if name_match is None and code_match is None:
                    continue
                if skipped < offset:
                    skipped += 1
                    continue
                row: dict[str, Any] = {
                    "function": function_name,
                    "address": str(func.getEntryPoint()),
                    "match": "name+code" if (name_match and code_match) else ("code" if code_match else "name"),
                }
                if code_match is not None:
                    row["line"] = code.count("\n", 0, code_match.start()) + 1
                    row["snippet"] = _snippet(code, code_match)
                if include_full_code and code:
                    row["code"] = code
                matches.append(row)

        if lease_cm is not None:
            with lease_cm as lease:
                _scan(lease.decompiler)
        else:
            _scan(None)

        payload: dict[str, Any] = {
            "query": query,
            "searchMode": "regex-fallback" if mode_norm == "regex" else "literal-fallback",
            "caseSensitive": case_sensitive,
            "returnedCount": len(matches),
            "offset": offset,
            "limit": limit,
            "scannedFunctions": scanned,
            "maxFunctions": max_functions,
            "scanCapped": scan_capped,
            "decompileFailures": decompile_failures,
            "results": matches,
        }
        if decompile_unavailable is not None:
            payload["note"] = f"Decompiler unavailable; matched function names only ({decompile_unavailable})."
        elif scan_capped:
            payload["note"] = f"Stopped after {scanned} functions; pass overrideMaxFunctionsLimit=true to scan all."
        return payload

    async def _handle(self, args: dict[str, Any], *, program_info: ProgramInfo | SimpleNamespace | None) -> list[types.TextContent]:
        logger.debug("diag.enter %s", "mcp_server/providers/strings.py:StringToolProvider._handle")
        self._require_program(program_info=program_info)
        mode = self._get_str(args, "mode", default="list")
        if n(mode) in _STRING_MUTATING_MODES:
            return await self._dispatch_handler(
                args,
                mode,
                {
                    "create": "_handle_create",
                    "update": "_handle_update",
                    "delete": "_handle_delete",
                },
                program_info=program_info,
            )

        pattern = self._get_str(args, "pattern", "query", "search", "text", "regex", "searchstring", "filter")
        min_len = self._get_int(args, "minlength", "minlen", default=4)
        offset, max_results = self._get_pagination_params(args, default_limit=100)
        include_refs = self._get_bool(args, "includereferencingfunctions", "includerefs", default=False)

        # Collect strings using GhidraTools or direct API
        strings = self._collect_strings(min_len, program_info=program_info)

        return await self._dispatch_handler(
            args,
            mode,
            {
                "list": "_handle_list",
                "search": "_handle_search",
                "regex": "_handle_regex",
                "count": "_handle_count",
                "similarity": "_handle_search",
            },
            strings=strings,
            pattern=pattern,
            min_len=min_len,
            offset=offset,
            max_results=max_results,
            include_refs=include_refs,
            program_info=program_info,
        )

    def _collect_strings(self, min_len: int, *, program_info: ProgramInfo | SimpleNamespace | None) -> list[dict[str, Any]]:
        """Collect all strings from the program using GhidraTools or direct API.

        Returns empty list if string enumeration is unavailable in the current context
        (e.g., shared-server checkout without iterator support). Diagnostics are logged.
        """
        logger.debug("diag.enter %s", "mcp_server/providers/strings.py:StringToolProvider._collect_strings")
        ghidra_tools = ghidra_tools_for_program(program_info)
        assert program_info is not None, "Program info is required to collect strings"
        program = program_info.program
        strings = collect_strings(
            program,
            min_len=min_len,
            ghidra_tools=ghidra_tools,
        )

        # Add diagnostic if no strings were found - could indicate collection failure
        if not strings:
            logging.getLogger(__name__).debug(
                "String collection returned empty results. This may indicate: (1) binary contains no strings, or (2) string iterators unavailable in current program context (shared-server/proxy mode).",
            )

        return strings

    def _attach_references_to_string_results(self, strings: list[dict[str, Any]], ref_limit: int = 25, *, program_info: ProgramInfo | SimpleNamespace | None) -> None:
        """Attach referencesTo (get-references style) to each string result."""
        logger.debug("diag.enter %s", "mcp_server/providers/strings.py:StringToolProvider._attach_references_to_string_results")
        if not strings or not program_info:
            return
        try:
            program: GhidraProgram = program_info.program
            ref_mgr: GhidraReferenceManager = program.getReferenceManager()
            fm = self._get_function_manager(program, program_info=program_info)
            for s in strings:
                try:
                    addr: GhidraAddress = self._resolve_address(s.get("address"), program=program, program_info=program_info)
                    if addr is None:
                        continue
                    refs_to: list[dict[str, Any]] = []
                    for ref in ref_mgr.getReferencesTo(addr):
                        if len(refs_to) >= ref_limit:
                            break
                        from_addr = ref.getFromAddress()
                        func = fm.getFunctionContaining(from_addr)
                        refs_to.append(
                            {
                                "fromAddress": str(from_addr),
                                "toAddress": str(ref.getToAddress()),
                                "type": str(ref.getReferenceType()),
                                "function": func.getName() if func else None,
                            }
                        )
                    s["referencesTo"] = refs_to
                except Exception:
                    pass
        except Exception:
            pass

    async def _handle_list(
        self,
        args: dict[str, Any],
        strings: list[dict],
        pattern: str,
        min_len: int,
        offset: int,
        max_results: int,
        include_refs: bool,
        *, program_info: ProgramInfo | SimpleNamespace | None,
    ) -> list[types.TextContent]:
        logger.debug("diag.enter %s", "mcp_server/providers/strings.py:StringToolProvider._handle_list")
        return self._filter_strings(strings, "list", "", min_len, max_results, offset, include_refs, program_info=program_info)

    async def _handle_regex(
        self,
        args: dict[str, Any],
        strings: list[dict],
        pattern: str,
        min_len: int,
        offset: int,
        max_results: int,
        include_refs: bool,
        *, program_info: ProgramInfo | SimpleNamespace | None,
    ) -> list[types.TextContent]:
        logger.debug("diag.enter %s", "mcp_server/providers/strings.py:StringToolProvider._handle_regex")
        return self._filter_strings(strings, "regex", pattern, min_len, max_results, offset, include_refs, program_info=program_info)

    async def _handle_search(
        self,
        args: dict[str, Any],
        strings: list[dict],
        pattern: str,
        min_len: int,
        offset: int,
        max_results: int,
        include_refs: bool,
        *, program_info: ProgramInfo | SimpleNamespace | None,
    ) -> list[types.TextContent]:
        logger.debug("diag.enter %s", "mcp_server/providers/strings.py:StringToolProvider._handle_search")
        return self._filter_strings(strings, "search", pattern, min_len, max_results, offset, include_refs, program_info=program_info)

    async def _handle_count(
        self,
        args: dict[str, Any],
        strings: list[dict],
        pattern: str,
        min_len: int,
        offset: int,
        max_results: int,
        include_refs: bool,
        *, program_info: ProgramInfo | SimpleNamespace | None,
    ) -> list[types.TextContent]:
        logger.debug("diag.enter %s", "mcp_server/providers/strings.py:StringToolProvider._handle_count")
        return self._filter_strings(strings, "count", pattern, min_len, max_results, offset, include_refs, program_info=program_info)

    def _filter_strings(
        self,
        strings: list[dict[str, Any]],
        mode: str,
        pattern: str,
        min_len: int,
        max_results: int,
        offset: int,
        include_refs: bool,
        *, program_info: ProgramInfo | SimpleNamespace | None,
    ) -> list[types.TextContent]:
        """Filter and format strings based on search mode and pattern.

        Consolidates multiple string search/filtering pipelines (regex, fuzzy,
        substring) into a single method to reduce code duplication across list/search
        operations. Handles pagination separately from filtering.

        **Filtering Modes**:
        - count: Return total count only (no results)
        - search: Unified search mode (regex/literal/fuzzy heuristic)
        - literal (default): Substring match, case-insensitive

        **Performance Notes**:
        - Regex compilation happens once per call (not per-string)
        - Fuzzy mode uses SequenceMatcher scoring for ranking
        - Pagination happens after filtering to avoid over-iterating
        - Reference lookup is optional and only when explicitly requested

        Parameters
        ----------
        strings : list[dict]
            Input strings with address and value keys
        mode : str
            Filter mode: 'count', 'search', 'regex', or default (literal)
        pattern : str
            Search pattern/regex for filtering
        min_len : int
            Minimum string length to include (unused in this method; pre-filtered)
        max_results : int
            Maximum number of results to return after pagination
        offset : int
            Pagination offset
        include_refs : bool
            Whether to add referencing functions to each string result

        Returns:
        -------
        list[TextContent]
            Paginated response with filtered results
        """
        logger.debug("diag.enter %s", "mcp_server/providers/strings.py:StringToolProvider._filter_strings")
        mode_n: str = n(mode)
        total: int = len(strings)

        if mode_n == "count":
            return create_success_response({"mode": "count", "totalStrings": len(strings)})

        if mode_n in {"search", "similarity"} and pattern:
            search_text = pattern.strip()
            regex_hint = bool(re.search(r"[\[\]\\(){}|*+?^$.]", search_text))
            if regex_hint:
                try:
                    pat = re.compile(search_text, re.IGNORECASE)
                    strings = [s for s in strings if pat.search(s.get("value", ""))]
                    total = len(strings)
                    strings, has_more = self._paginate_results(strings, offset, max_results)
                    self._attach_references_to_string_results(strings, program_info=program_info)
                    return self._create_paginated_response(strings, offset, max_results, total=total, mode=mode, query=pattern)
                except re.error:
                    pass

            query_lower = search_text.lower()
            scored: list[tuple[float, dict[str, Any]]] = []
            for s in strings:
                val = str(s.get("value", ""))
                val_lower = val.lower()
                if query_lower in val_lower:
                    score = 1.0
                else:
                    score = difflib.SequenceMatcher(None, query_lower, val_lower).ratio()
                if score >= 0.6:
                    scored.append((score, s))

            scored.sort(key=lambda item: item[0], reverse=True)
            total = len(scored)
            strings = [s for _, s in scored]
            strings, has_more = self._paginate_results(strings, offset, max_results)
            self._attach_references_to_string_results(strings, program_info=program_info)
            return self._create_paginated_response(strings, offset, max_results, total=total, mode=mode, query=pattern)

        if mode_n == "regex" and pattern:
            try:
                pat = re.compile(pattern, re.IGNORECASE)
                strings = [s for s in strings if pat.search(s.get("value", ""))]
            except re.error as e:
                raise ValueError(f"Invalid regex pattern: {e.__class__}: {e}")

        elif pattern:
            p_lower = pattern.lower()
            strings = [s for s in strings if p_lower in str(s.get("value", "")).lower()]

        total: int = len(strings)

        strings, has_more = self._paginate_results(strings, offset, max_results)

        if include_refs and program_info:
            try:
                program: Any = program_info.program
                ref_mgr: Any = program.getReferenceManager()
                fm = self._get_function_manager(program, program_info=program_info)
                for s in strings:
                    try:
                        addr: Any = self._resolve_address(s["address"], program=program, program_info=program_info)
                        funcs = set()
                        ref_count = 0
                        for ref in ref_mgr.getReferencesTo(addr):
                            if ref_count >= 20:
                                break
                            ref_count += 1
                            f = fm.getFunctionContaining(ref.getFromAddress())
                            if f:
                                funcs.add(f.getName())
                        s["referencingFunctions"] = sorted(funcs)
                    except Exception:
                        pass
            except Exception:
                pass

        self._attach_references_to_string_results(strings, program_info=program_info)
        extra: dict[str, Any] = {}
        if pattern:
            extra["query"] = pattern
        return self._create_paginated_response(strings, offset, max_results, total=total, mode=mode, **extra)

    async def _handle_create(self, args: dict[str, Any], *, program_info: ProgramInfo | SimpleNamespace | None) -> list[types.TextContent]:
        return await self._handle_write_string(args, action="create", allow_existing=False, program_info=program_info)

    async def _handle_update(self, args: dict[str, Any], *, program_info: ProgramInfo | SimpleNamespace | None) -> list[types.TextContent]:
        return await self._handle_write_string(args, action="update", allow_existing=True, program_info=program_info)

    async def _handle_delete(self, args: dict[str, Any], *, program_info: ProgramInfo | SimpleNamespace | None) -> list[types.TextContent]:
        logger.debug("diag.enter %s", "mcp_server/providers/strings.py:StringToolProvider._handle_delete")
        self._require_program(program_info=program_info)
        addr_str = self._require_address_or_symbol(args)
        assert program_info is not None
        program = program_info.program
        addr = self._resolve_address(addr_str, program=program, program_info=program_info)
        listing = self._get_listing(program, program_info=program_info)
        cleared = False

        def _delete_string() -> None:
            nonlocal cleared
            data = listing.getDataAt(addr)
            if data is None:
                return
            end = addr.add(max(int(data.getLength()), 1) - 1)
            listing.clearCodeUnits(addr, end, False)
            cleared = True

        self._run_program_transaction(program, "manage-strings-delete", _delete_string)
        return create_success_response(
            {
                "action": "delete",
                "address": str(addr),
                "cleared": cleared,
                "success": True,
            },
        )

    async def _handle_write_string(self, args: dict[str, Any], *, action: str, allow_existing: bool, program_info: ProgramInfo | SimpleNamespace | None) -> list[types.TextContent]:
        logger.debug("diag.enter %s", "mcp_server/providers/strings.py:StringToolProvider._handle_write_string")
        self._require_program(program_info=program_info)
        addr_str = self._require_address_or_symbol(args)
        value = self._require_str(args, "value", "text", "string", name="value")
        encoding = normalize_string_encoding(self._get_str(args, "encoding", default="ascii"))
        assert program_info is not None
        program = program_info.program
        addr = self._resolve_address(addr_str, program=program, program_info=program_info)
        listing = self._get_listing(program, program_info=program_info)
        existing = listing.getDataAt(addr)
        if (
            existing is not None
            and not allow_existing
            and bool(getattr(existing, "isDefined", lambda: True)())
        ):
            raise ValueError(f"Address {addr} already has defined data ({existing.getDataType()}). Use mode='update' to replace.")

        raw = encode_program_string(value, encoding)
        dt_name = ghidra_string_type_name(encoding)
        from ghidra.util.data import DataTypeParser

        dtm = program.getDataTypeManager()
        parser = DataTypeParser(dtm, dtm, None, DataTypeParser.AllowedDataTypes.ALL)
        dt = parser.parse(dt_name)
        memory = self._get_memory(program, program_info=program_info)

        def _write_string() -> None:
            end = addr.add(len(raw) - 1)
            listing.clearCodeUnits(addr, end, False)
            memory.setBytes(addr, raw)
            listing.createData(addr, dt)

        self._run_program_transaction(program, f"manage-strings-{action}", _write_string)
        return create_success_response(
            {
                "action": action,
                "address": str(addr),
                "value": value,
                "encoding": encoding,
                "dataType": dt_name,
                "success": True,
            },
        )
