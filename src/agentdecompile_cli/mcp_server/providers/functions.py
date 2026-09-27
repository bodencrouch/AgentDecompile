"""Function Tool Provider - list-functions, get-functions.

- list-functions: Enumerate functions in the program with optional name-pattern filter,
  includeExternals flag, and pagination (offset/limit). Uses collect_functions from
  _collectors for a single pass over the function manager.
- get-functions: Detailed view of one or more functions. Accepts a single 'function'
  or a 'functions' array for batch. Modes: info, decompile, disassemble, calls (or
  all). Decompilation goes through the program's DecompInterface; results are
  formatted for MCP consumption.
"""

from __future__ import annotations

import difflib
import json
import logging
import re

from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from types import SimpleNamespace

    from ghidra.program.model.address import (  # pyright: ignore[reportMissingImports, reportMissingModuleSource, reportMissingTypeStubs]
        AddressSetView as GhidraAddressSetView,
    )
    from ghidra.program.model.listing import (  # pyright: ignore[reportMissingImports, reportMissingModuleSource, reportMissingTypeStubs]
        Function as GhidraFunction,
        Listing as GhidraListing,
        Program as GhidraProgram,
    )

    from agentdecompile_cli.launcher import ProgramInfo

from mcp import types

from agentdecompile_cli.mcp_server.providers._collectors import collect_functions, iter_items, make_task_monitor
from agentdecompile_cli.mcp_server.tool_providers import (
    ToolProvider,
    create_success_response,
    n,
)

logger = logging.getLogger(__name__)

_LIST_MODES = frozenset({"all", "search", "similarity", "count", "byidentifiers", "undefined"})
_LIST_ROW_KEYS = ("name", "address", "size", "isExternal", "isThunk", "parameterCount", "signature", "callingConvention")
_VERBOSE_ROW_KEYS = ("parameters", "returnType", "hasVarArgs", "tags", "comments", "callerCount", "calleeCount")
# Ghidra's auto-generated function names (SourceType.DEFAULT): FUN_00401000, thunk_FUN_00401000.
_DEFAULT_FUNCTION_NAME = re.compile(r"^(?:thunk_)?FUN_[0-9A-Fa-f]+$")


class FunctionToolProvider(ToolProvider):
    HANDLERS: ClassVar[dict[str, str]] = {
        "listfunctions": "_handle_list",
        "getfunctions": "_handle_get",
    }

    def list_tools(self) -> list[types.Tool]:
        logger.debug("diag.enter %s", "mcp_server/providers/functions.py:FunctionToolProvider.list_tools")
        return [
            types.Tool(
                name="list-functions",
                description="List functions in the current program with optional filtering and pagination.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "programPath": {"type": "string", "description": "Path to the program containing the functions."},
                        "namePattern": {"type": "string", "description": "Regex pattern used to filter function names."},
                        "pattern": {"type": "string", "description": "Alias for namePattern."},
                        "callingConvention": {"type": "string"},
                        "inline": {"type": "boolean"},
                        "minSize": {"type": "integer", "minimum": 0},
                        "maxSize": {"type": "integer", "minimum": 0},
                        "addressMin": {"type": "string"},
                        "addressMax": {"type": "string"},
                        "signaturePattern": {"type": "string", "description": "Case-insensitive regex over full function signature."},
                        "undefinedParameters": {"type": "boolean", "description": "Filter functions with at least one undefined parameter type."},
                        "includeExternals": {"type": "boolean", "default": True, "description": "Include external/imported functions."},
                        "offset": {"type": "integer", "default": 0, "description": "Pagination offset."},
                        "limit": {"type": "integer", "default": 100, "description": "Maximum functions to return."},
                    },
                    "required": [],
                },
            ),
            types.Tool(
                name="get-functions",
                description="Get detailed information, decompilation, disassembly, or call data for one or more functions.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "programPath": {"type": "string", "description": "Path to the program containing the function."},
                        "function": {"type": "string", "description": "Function name or address."},
                        "addressOrSymbol": {"type": "string", "description": "Alternative function name or address selector."},
                        "identifier": {"type": "string", "description": "Alternative function identifier."},
                        "functions": {
                            "oneOf": [
                                {"type": "string"},
                                {"type": "array", "items": {"type": "string"}},
                            ],
                            "description": "One or more function identifiers.",
                        },
                        "mode": {
                            "type": "string",
                            "default": "info",
                            "enum": ["info", "decompile", "disassemble", "calls", "all"],
                            "description": "Which function view to return.",
                        },
                        "timeout": {"type": "integer", "default": 60, "description": "Decompiler timeout in seconds."},
                        "offset": {"type": "integer", "default": 0, "description": "Pagination offset for batch results."},
                        "limit": {"type": "integer", "default": 100, "description": "Maximum results to return."},
                    },
                    "required": [],
                },
            ),
        ]

    async def _handle_list(self, args: dict[str, Any], *, program_info: ProgramInfo | SimpleNamespace | None) -> list[types.TextContent]:
        """List functions in the current program, with optional filtering and pagination.

        Modes (``mode``, default ``all``):
            all            every function passing the filters below
            search         ``all`` narrowed by ``query``/``searchString`` (required)
            similarity     every filtered function ranked by name similarity to the query
            count          the number of functions ``all`` would list under the same filters
            by_identifiers the functions named by ``identifiers`` (names or addresses)
            undefined      call targets that have no function defined yet

        Filters: ``query``/``searchString`` (case-insensitive substring, or a regex that
        matches), ``namePattern`` (regex), ``includeExternals`` (default true),
        ``filterDefaultNames`` (hide FUN_xxxx names, default false), ``filterByTag``,
        ``hasTags``, ``untagged``, ``minReferenceCount``, plus the signature, size,
        address-range and calling-convention filters. ``verbose`` adds parameters,
        return type, tags, comments and call counts to each row.
        """
        logger.debug("diag.enter %s", "mcp_server/providers/functions.py:FunctionToolProvider._handle_list")
        self._require_program(program_info=program_info)
        mode = n(self._get_str(args, "mode", default="all")) or "all"
        if mode in {"list", "list_functions", "listfunctions"}:
            mode = "all"
        if mode not in _LIST_MODES:
            raise ValueError(f"Unsupported list-functions mode: {self._get_str(args, 'mode')!r}. Use one of: all, search, similarity, count, by_identifiers, undefined.")

        program = program_info.program
        if program is None or not hasattr(program, "getFunctionManager"):
            raise ValueError("No program loaded")

        offset, max_results = self._get_pagination_params(args, default_limit=100)
        if mode == "undefined":
            return self._list_undefined_candidates(args, program, offset, max_results)

        query = self._get_str(args, "query", "searchstring").strip()
        if mode in {"search", "similarity"} and not query:
            raise ValueError(f"list-functions mode={mode} requires query (or searchString)")

        rows = self._filtered_function_rows(args, program, program_info=program_info, query=query if mode != "similarity" else "")

        if mode == "byidentifiers":
            identifiers = [str(v).strip() for v in (self._get_list(args, "identifiers", "functions") or []) if str(v).strip()]
            if not identifiers:
                raise ValueError("list-functions mode=by_identifiers requires identifiers")
            rows, not_found = self._rows_for_identifiers(identifiers, rows, program, program_info=program_info)
            paginated, _ = self._paginate_results(rows, offset, max_results)
            return self._create_paginated_response(paginated, offset, max_results, total=len(rows), mode="by_identifiers", notFound=not_found)

        if mode == "count":
            return create_success_response({"mode": "count", "count": len(rows), "total": len(rows), "results": []})

        if mode == "similarity":
            needle = query.lower()
            for row in rows:
                name = str(row.get("name", "")).lower()
                row["similarityScore"] = 1.0 if needle in name else round(difflib.SequenceMatcher(None, needle, name).ratio(), 4)
            rows.sort(key=lambda row: row["similarityScore"], reverse=True)

        paginated, _ = self._paginate_results(rows, offset, max_results)
        extra: dict[str, Any] = {"query": query} if query else {}
        return self._create_paginated_response(paginated, offset, max_results, total=len(rows), mode="list" if mode == "all" else mode, **extra)

    def _filtered_function_rows(self, args: dict[str, Any], program: Any, *, program_info: ProgramInfo | SimpleNamespace | None, query: str) -> list[dict[str, Any]]:
        pattern = self._get_str(args, "namepattern", "pattern", "filter", "regex")
        include_ext = self._get_bool(args, "includeexternals", "externals", default=True)
        pat = re.compile(pattern, re.IGNORECASE) if pattern else None

        query_lower = query.lower()
        try:
            query_regex = re.compile(query, re.IGNORECASE) if query else None
        except re.error:
            query_regex = None

        convention = self._get_str(args, "callingconvention")
        signature = self._get_str(args, "signaturepattern")
        signature_regex = re.compile(signature, re.IGNORECASE) if signature else None
        min_size = self._get_int(args, "minsize", default=None)
        max_size = self._get_int(args, "maxsize", default=None)
        if min_size is not None and min_size < 0 or max_size is not None and max_size < 0:
            raise ValueError("Function sizes cannot be negative")
        if min_size is not None and max_size is not None and min_size > max_size:
            raise ValueError("minSize cannot exceed maxSize")
        lower = self._resolve_address(self._get_str(args, "addressmin"), program=program, program_info=program_info) if self._get_str(args, "addressmin") else None
        upper = self._resolve_address(self._get_str(args, "addressmax"), program=program, program_info=program_info) if self._get_str(args, "addressmax") else None
        if lower is not None and upper is not None and lower.compareTo(upper) > 0:
            raise ValueError("addressMin cannot exceed addressMax")

        filter_default_names = self._get_bool(args, "filterdefaultnames", default=False)
        tag_filter = self._get_str(args, "filterbytag", "tag").strip().lower()
        has_tags = self._get_bool(args, "hastags", default=False)
        untagged = self._get_bool(args, "untagged", default=False)
        min_refs = self._get_int(args, "minreferencecount", default=0) or 0
        verbose = self._get_bool(args, "verbose", default=False)
        ref_mgr = program.getReferenceManager() if min_refs > 0 else None

        def matches(row):
            name = str(row.get("name", ""))
            if not include_ext and row.get("isExternal"):
                return False
            if pat and not pat.search(name):
                return False
            if query and query_lower not in name.lower() and not (query_regex and query_regex.search(name)):
                return False
            if filter_default_names and _DEFAULT_FUNCTION_NAME.match(name):
                return False
            tags = [str(t).lower() for t in row.get("tags", [])]
            if tag_filter and tag_filter not in tags:
                return False
            if has_tags and not tags:
                return False
            if untagged and tags:
                return False
            if convention and row.get("callingConvention") != convention:
                return False
            if "inline" in args and row.get("isInline", False) != self._get_bool(args, "inline"):
                return False
            if min_size is not None and row["size"] < min_size or max_size is not None and row["size"] > max_size:
                return False
            if signature_regex and not signature_regex.search(row.get("signature", "")):
                return False
            if "undefinedparameters" in args:
                undefined = any(str(p.get("type", "")).startswith("undefined") for p in row.get("parameters", []))
                if undefined != self._get_bool(args, "undefinedparameters"):
                    return False
            if lower is not None or upper is not None:
                address = program.getAddressFactory().getAddress(row["address"])
                if address is None or lower is not None and address.compareTo(lower) < 0 or upper is not None and address.compareTo(upper) > 0:
                    return False
            if ref_mgr is not None:
                address = program.getAddressFactory().getAddress(row["address"])
                if address is None or int(ref_mgr.getReferenceCountTo(address)) < min_refs:
                    return False
            return True

        out: list[dict[str, Any]] = []
        for row in collect_functions(program, include_externals=include_ext):
            if not matches(row):
                continue
            item = {key: row.get(key) for key in _LIST_ROW_KEYS}
            item["isInline"] = row.get("isInline", False)
            if verbose:
                item.update({key: row.get(key) for key in _VERBOSE_ROW_KEYS if key in row})
            out.append(item)
        return out

    def _rows_for_identifiers(self, identifiers: list[str], rows: list[dict[str, Any]], program: Any, *, program_info: ProgramInfo | SimpleNamespace | None) -> tuple[list[dict[str, Any]], list[str]]:
        def addr_key(value: str) -> str:
            return value.strip().lower().removeprefix("0x").lstrip("0")

        by_name = {str(row["name"]): row for row in rows}
        by_addr = {addr_key(str(row["address"])): row for row in rows}
        found: list[dict[str, Any]] = []
        not_found: list[str] = []
        seen: set[str] = set()
        for ident in identifiers:
            row = by_name.get(ident) or by_addr.get(addr_key(ident))
            if row is None:
                func = self._resolve_function(ident, program=program, program_info=program_info)
                if func is not None:
                    row = by_addr.get(addr_key(str(func.getEntryPoint())))
            if row is None:
                not_found.append(ident)
                continue
            if row["address"] not in seen:
                seen.add(row["address"])
                found.append(row)
        return found, not_found

    def _list_undefined_candidates(self, args: dict[str, Any], program: Any, offset: int, max_results: int) -> list[types.TextContent]:
        """Call targets without a defined function, most-referenced first."""
        min_refs = max(1, self._get_int(args, "minreferencecount", default=1) or 1)
        fm = program.getFunctionManager()
        ref_mgr = program.getReferenceManager()
        memory = program.getMemory()
        callers: dict[str, list[str]] = {}
        addresses: dict[str, Any] = {}
        for ref in iter_items(ref_mgr.getReferenceIterator(program.getMinAddress())):
            ref_type = ref.getReferenceType()
            if not ref_type.isCall():
                continue
            target = ref.getToAddress()
            if not target.isMemoryAddress() or fm.getFunctionAt(target) is not None:
                continue
            block = memory.getBlock(target)
            if block is None or not block.isExecute():
                continue
            key = str(target)
            addresses[key] = target
            callers.setdefault(key, []).append(str(ref.getFromAddress()))
        candidates = []
        for key, sources in callers.items():
            if len(sources) < min_refs:
                continue
            containing = []
            for source in sources[:5]:
                func = fm.getFunctionContaining(program.getAddressFactory().getAddress(source))
                containing.append({"fromAddress": source, "function": func.getName() if func else None})
            candidates.append({"address": key, "referenceCount": len(sources), "referencedFrom": containing})
        candidates.sort(key=lambda row: (-row["referenceCount"], row["address"]))
        paginated, _ = self._paginate_results(candidates, offset, max_results)
        return self._create_paginated_response(paginated, offset, max_results, total=len(candidates), mode="undefined", minReferenceCount=min_refs)

    @staticmethod
    def _response_to_payload(response: list[types.TextContent]) -> dict[str, Any]:
        logger.debug("diag.enter %s", "mcp_server/providers/functions.py:FunctionToolProvider._response_to_payload")
        if not response:
            return {}
        text = getattr(response[0], "text", "")
        if not text:
            return {}
        try:
            data = json.loads(text)
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    async def _handle_get(self, args: dict[str, Any], *, program_info: ProgramInfo | SimpleNamespace | None) -> list[types.TextContent]:
        """Get detailed views (info/decompile/disassemble/calls) for one or more functions. Batch via 'functions' array."""
        logger.debug("diag.enter %s", "mcp_server/providers/functions.py:FunctionToolProvider._handle_get")
        self._require_program(program_info=program_info)

        # Collect all function identifiers: 'functions' array, or single 'function' / 'addressOrSymbol' / etc.
        func_ids: list[str] = []
        raw_functions = self._get_list(args, "functions")
        if raw_functions:
            for v in raw_functions:
                if isinstance(v, str) and v.strip():
                    func_ids.append(v.strip())
        if not func_ids:
            raw_functions_str = self._get_str(args, "functions")
            if raw_functions_str and raw_functions_str.strip():
                func_ids = [raw_functions_str.strip()]
        if not func_ids:
            single = self._get_str(args, "function", "addressorsymbol", "functionidentifier", "identifier", "name", "addr", "symbol")
            if single:
                func_ids = [single.strip()]

        view: str = self._get_str(args, "mode", "view", "action", "operation", default="")
        if view.lower() == "all":
            view = ""
        max_results: int = self._get_int(args, "limit", "maxresults", default=100)
        timeout: int = self._get_int(args, "timeout", "decompiletimeout", default=60)

        program = program_info.program
        if program is None or not hasattr(program, "getFunctionManager"):
            raise ValueError("No program loaded")

        # If no function specified, list all
        if not func_ids:
            # get-functions' mode is a view (info/decompile/...), not a list-functions mode.
            list_args = {key: value for key, value in args.items() if key not in {"mode", "view", "action", "operation"}}
            return await self._handle_list(list_args, program_info=program_info)

        # Single function path (existing behavior)
        if len(func_ids) == 1:
            func_id = func_ids[0]
            target_func = self._resolve_function(func_id, program=program, program_info=program_info)
            if target_func is None:
                raise ValueError(f"Function not found: {func_id}")

            if not view:
                info_resp = await self._handle_info(args, target_func=target_func, program=program, max_results=max_results, timeout=timeout)
                calls_resp = await self._handle_calls(args, target_func=target_func, program=program, max_results=max_results, timeout=timeout)
                decompile_resp = await self._handle_decompile(args, target_func=target_func, program=program, max_results=max_results, timeout=timeout, program_info=program_info)
                disassemble_resp = await self._handle_disassemble(args, target_func=target_func, program=program, max_results=max_results, timeout=timeout, program_info=program_info)

                return create_success_response(
                    {
                        "name": target_func.getName(),
                        "address": str(target_func.getEntryPoint()),
                        "signature": str(target_func.getSignature()),
                        "view": "all",
                        "views": {
                            "info": self._response_to_payload(info_resp),
                            "calls": self._response_to_payload(calls_resp),
                            "decompile": self._response_to_payload(decompile_resp),
                            "disassemble": self._response_to_payload(disassemble_resp),
                        },
                    },
                )

            return await self._dispatch_handler(
                args,
                view,
                {
                    "info": "_handle_info",
                    "calls": "_handle_calls",
                    "decompile": "_handle_decompile",
                    "disassemble": "_handle_disassemble",
                },
                target_func=target_func,
                program=program,
                max_results=max_results,
                timeout=timeout,
                program_info=program_info,
            )

        # Batch path: multiple functions requested
        batch_results: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        for func_id in func_ids:
            try:
                target_func = self._resolve_function(func_id, program=program, program_info=program_info)
                if target_func is None:
                    errors.append({"identifier": func_id, "error": "Function not found"})
                    continue
                if not view:
                    info_resp = await self._handle_info(args, target_func=target_func, program=program, max_results=max_results, timeout=timeout)
                    calls_resp = await self._handle_calls(args, target_func=target_func, program=program, max_results=max_results, timeout=timeout)
                    decompile_resp = await self._handle_decompile(args, target_func=target_func, program=program, max_results=max_results, timeout=timeout, program_info=program_info)
                    disassemble_resp = await self._handle_disassemble(args, target_func=target_func, program=program, max_results=max_results, timeout=timeout, program_info=program_info)
                    batch_results.append(
                        {
                            "identifier": func_id,
                            "name": target_func.getName(),
                            "address": str(target_func.getEntryPoint()),
                            "signature": str(target_func.getSignature()),
                            "view": "all",
                            "views": {
                                "info": self._response_to_payload(info_resp),
                                "calls": self._response_to_payload(calls_resp),
                                "decompile": self._response_to_payload(decompile_resp),
                                "disassemble": self._response_to_payload(disassemble_resp),
                            },
                        },
                    )
                else:
                    single_resp = await self._dispatch_handler(
                        args,
                        view,
                        {
                            "info": "_handle_info",
                            "calls": "_handle_calls",
                            "decompile": "_handle_decompile",
                            "disassemble": "_handle_disassemble",
                        },
                        target_func=target_func,
                        program=program,
                        max_results=max_results,
                        timeout=timeout,
                        program_info=program_info,
                    )
                    payload = self._response_to_payload(single_resp)
                    payload["identifier"] = func_id
                    batch_results.append(payload)
            except Exception as e:
                errors.append({"identifier": func_id, "error": str(e)})

        return create_success_response(
            {
                "mode": "batch",
                "view": view or "all",
                "count": len(batch_results),
                "results": batch_results,
                "errors": errors,
            },
        )

    async def _handle_info(self, args: dict[str, Any], target_func: GhidraFunction, program: GhidraProgram, max_results: int, timeout: int) -> list[types.TextContent]:
        logger.debug("diag.enter %s", "mcp_server/providers/functions.py:FunctionToolProvider._handle_info")
        result: dict[str, Any] = {
            "name": target_func.getName(),
            "address": str(target_func.getEntryPoint()),
            "signature": str(target_func.getSignature()),
            "view": "info",
            "size": target_func.getBody().getNumAddresses() if target_func.getBody() else 0,
            "isExternal": target_func.isExternal(),
            "isThunk": target_func.isThunk(),
            "parameterCount": target_func.getParameterCount(),
            "parameters": [{"name": p.getName(), "type": str(p.getDataType()), "ordinal": p.getOrdinal()} for p in target_func.getParameters()],
            "returnType": str(target_func.getReturnType()),
            "callingConvention": target_func.getCallingConventionName(),
            "hasVarArgs": target_func.hasVarArgs(),
        }
        return create_success_response(result)

    async def _handle_calls(self, args: dict[str, Any], target_func: GhidraFunction, program: GhidraProgram, max_results: int, timeout: int) -> list[types.TextContent]:
        logger.debug("diag.enter %s", "mcp_server/providers/functions.py:FunctionToolProvider._handle_calls")
        _monitor = make_task_monitor()
        callers = [{"name": c.getName(), "address": str(c.getEntryPoint())} for c in target_func.getCallingFunctions(_monitor)]
        callees = [{"name": c.getName(), "address": str(c.getEntryPoint())} for c in target_func.getCalledFunctions(_monitor)]
        result: dict[str, Any] = {
            "name": target_func.getName(),
            "address": str(target_func.getEntryPoint()),
            "signature": str(target_func.getSignature()),
            "view": "calls",
            "callers": callers,
            "callees": callees,
            "callerCount": len(callers),
            "calleeCount": len(callees),
        }
        return create_success_response(result)

    async def _handle_decompile(self, args: dict[str, Any], target_func: GhidraFunction, program: GhidraProgram, max_results: int, timeout: int, *, program_info: ProgramInfo | SimpleNamespace | None) -> list[types.TextContent]:
        logger.debug("diag.enter %s", "mcp_server/providers/functions.py:FunctionToolProvider._handle_decompile")
        result: dict[str, Any] = {
            "name": target_func.getName(),
            "address": str(target_func.getEntryPoint()),
            "signature": str(target_func.getSignature()),
            "view": "decompile",
        }
        try:
            from ghidra.util.task import ConsoleTaskMonitor  # pyright: ignore[reportMissingModuleSource]

            from agentdecompile_cli.mcp_utils.decompiler_util import (
                acquire_decompiler_for_program,
                get_decompiled_function_from_results,
                merge_decompile_dict_keys,
                open_decompiler_for_program,
            )

            monitor = ConsoleTaskMonitor()

            session_decomp = getattr(program_info, "decompiler", None)
            with acquire_decompiler_for_program(session_decomp, program) as lease:
                decomp = lease.decompiler
                dr = decomp.decompileFunction(target_func, timeout, monitor)
                if dr and dr.decompileCompleted():
                    df = get_decompiled_function_from_results(dr)
                    if df is None:
                        raise RuntimeError("Decompilation completed but Ghidra returned no DecompiledFunction")
                    c_out = df.getC()
                    if not (c_out or "").strip():
                        raise RuntimeError("Decompilation completed but C output was empty")
                    result["decompilation"] = c_out
                else:
                    err_msg = ""
                    if dr is not None:
                        try:
                            err_msg = dr.getErrorMessage() or ""
                        except Exception:
                            err_msg = ""

                    if session_decomp is not None and lease.reused_session:
                        retry = open_decompiler_for_program(program)
                        retry_dr = retry.decompileFunction(target_func, timeout, monitor)
                        if retry_dr and retry_dr.decompileCompleted():
                            retry_df = get_decompiled_function_from_results(retry_dr)
                            if retry_df is None:
                                retry.dispose()
                                raise RuntimeError("Decompilation completed but Ghidra returned no DecompiledFunction")
                            c_retry = retry_df.getC()
                            if not (c_retry or "").strip():
                                retry.dispose()
                                raise RuntimeError("Decompilation completed but C output was empty")
                            result["decompilation"] = c_retry
                            retry.dispose()
                            return create_success_response(merge_decompile_dict_keys(result))
                        try:
                            retry_err = retry_dr.getErrorMessage() if retry_dr else ""
                        except Exception:
                            retry_err = ""
                        retry.dispose()
                        if retry_err:
                            err_msg = retry_err

                    if not err_msg:
                        try:
                            err_msg = decomp.getLastMessage() or ""
                        except Exception:
                            err_msg = ""

                    extras: list[str] = []
                    if dr is not None:
                        try:
                            if not dr.decompileCompleted():
                                extras.append("decompileCompleted=false")
                        except Exception:
                            pass
                    detail = "; ".join([p for p in [err_msg, " ".join(extras)] if p]) or "no error message from DecompInterface"
                    raise RuntimeError(f"Decompilation failed for {target_func.getName()}: {detail}")
        except Exception:
            raise

        return create_success_response(merge_decompile_dict_keys(result))

    async def _handle_disassemble(self, args: dict[str, Any], target_func: GhidraFunction, program: GhidraProgram, max_results: int, timeout: int, *, program_info: ProgramInfo | SimpleNamespace | None) -> list[types.TextContent]:
        logger.debug("diag.enter %s", "mcp_server/providers/functions.py:FunctionToolProvider._handle_disassemble")
        instructions: list[dict[str, Any]] = []
        listing: GhidraListing = self._get_listing(program, program_info=program_info)
        body: GhidraAddressSetView = target_func.getBody()
        if body:
            instr_iter = listing.getInstructions(body, True)
            while instr_iter.hasNext() and len(instructions) < max_results:
                instr = instr_iter.next()
                instructions.append(
                    {
                        "address": str(instr.getAddress()),
                        "mnemonic": instr.getMnemonicString(),
                        "operands": str(instr),
                        "bytes": " ".join(f"{b & 0xFF:02x}" for b in instr.getBytes()),
                    },
                )
        result: dict[str, Any] = {
            "name": target_func.getName(),
            "address": str(target_func.getEntryPoint()),
            "signature": str(target_func.getSignature()),
            "view": "disassemble",
            "instructions": instructions,
            "instructionCount": len(instructions),
        }
        return create_success_response(result)
