"""Structure Tool Provider - manage-structures.

Single tool, mode = parse (C header text → struct), validate, create, add_field,
modify_field, modify_from_c, info, list, apply (apply struct at address), delete,
parse_header. Uses _collectors collect_structures / collect_structure_fields.
Structures define memory layout so the decompiler can show field names instead of offsets.
"""

from __future__ import annotations

import logging
import uuid

from typing import TYPE_CHECKING, Any, cast

from mcp import types

from agentdecompile_cli.mcp_server.providers._collectors import (
    collect_structure_fields,
    collect_structures,
)
from agentdecompile_cli.mcp_server.tool_providers import (
    FORCE_APPLY_CONFLICT_ID_KEY,
    ToolProvider,
    create_conflict_response,
    create_success_response,
    n,
)
from agentdecompile_cli.registry import Tool

if TYPE_CHECKING:
    from types import SimpleNamespace

    from ghidra.program.model.data import (  # pyright: ignore[reportMissingImports, reportMissingModuleSource, reportMissingTypeStubs]
        DataTypeManager as GhidraDataTypeManager,
        Structure as GhidraStructure,
    )
    from ghidra.util.data import DataTypeParser as GhidraDataTypeParser  # pyright: ignore[reportMissingImports, reportMissingModuleSource, reportMissingTypeStubs]

    from agentdecompile_cli.launcher import ProgramInfo

logger = logging.getLogger(__name__)


class StructureToolProvider(ToolProvider):
    HANDLERS = {"managestructures": "_handle"}

    def _find_structure(self, dtm: GhidraDataTypeManager, name: str, *, program_info: ProgramInfo | SimpleNamespace | None) -> GhidraStructure | None:
        """Return a structure by exact name, or ``None`` when not found.

        **Performance**: O(n) where n = number of structures in the data type manager.
        For programs with many structures, this may be slow. Consider caching if needed.
        """
        logger.debug("diag.enter %s", "mcp_server/providers/structures.py:StructureToolProvider._find_structure")
        assert program_info is not None
        for row in collect_structures(program_info.program):
            struct = row.get("structure")
            if struct is not None and struct.getName() == name:
                return struct
        return None

    @staticmethod
    def _new_data_type_parser(dtm: GhidraDataTypeManager) -> GhidraDataTypeParser:
        """Create a ``DataTypeParser`` configured for broad type support."""
        logger.debug("diag.enter %s", "mcp_server/providers/structures.py:StructureToolProvider._new_data_type_parser")
        from ghidra.util.data import DataTypeParser  # pyright: ignore[reportMissingModuleSource]

        return DataTypeParser(dtm, dtm, cast("Any", None), DataTypeParser.AllowedDataTypes.ALL)

    def list_tools(self) -> list[types.Tool]:
        logger.debug("diag.enter %s", "mcp_server/providers/structures.py:StructureToolProvider.list_tools")
        return [
            types.Tool(
                name=Tool.MANAGE_STRUCTURES.value,
                description="Create, list, apply, parse, and edit complex data structures (like C structs and unions) to map out memory layouts.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "programPath": {"type": "string", "description": "The active program project."},
                        "mode": {
                            "type": "string",
                            "description": "What operation to perform on the structure data.",
                            "enum": [
                                "parse",
                                "validate",
                                "create",
                                "add_field",
                                "modify_field",
                                "modify_from_c",
                                "info",
                                "list",
                                "apply",
                                "delete",
                                "parse_header",
                            ],
                        },
                        "name": {"type": "string", "description": "The EXACT name of the structure you want to interact with."},
                        "structureName": {"type": "string", "description": "Alternative parameter for name."},
                        "categoryPath": {"type": "string", "default": "/", "description": "The organizational folder path where the structure is stored."},
                        "size": {"type": "integer", "description": "The total byte size of the structure when creating an empty block."},
                        "cDefinition": {"type": "string", "description": "A block of C-code text defining a struct (e.g., 'struct foo { int a; char b; };'). Used for parse and modify_from_c."},
                        "fieldName": {"type": "string", "description": "The name of a specific member field within the struct."},
                        "fieldType": {"type": "string", "description": "The data type of the member field (e.g., 'int', 'char *', 'void *')."},
                        "fieldOffset": {"type": "integer", "description": "The exact byte offset from the start of the struct where the field begins."},
                        "fieldComment": {"type": "string", "description": "An optional explanation attached to a specific member field."},
                        "fields": {"type": "array", "items": {"type": "object"}, "description": "An array of multiple field definitions to apply at once."},
                        "addressOrSymbol": {"type": "string", "description": "The memory address where you want to drop/apply the struct template."},
                        "isUnion": {"type": "boolean", "default": False, "description": "If true, treats the object as a C-union (all fields overlap at offset 0)."},
                        "nameFilter": {"type": "string", "description": "Case-insensitive text to filter the struct list by."},
                        "query": {"type": "string", "description": "Alternative parameter for nameFilter."},
                        "filter": {"type": "string", "description": "Alternative parameter for nameFilter."},
                        "maxResults": {"type": "integer", "default": 100, "description": "Number of structure results to return. Typical values are 100–500."},
                    },
                    "required": [],
                },
            ),
        ]

    async def _handle(self, args: dict[str, Any], *, program_info: ProgramInfo | SimpleNamespace | None) -> list[types.TextContent]:
        logger.debug("diag.enter %s", "mcp_server/providers/structures.py:StructureToolProvider._handle")
        self._require_program(program_info=program_info)
        action = self._get_str(args, "mode", "action", "operation", default="list")

        dispatch = {
            "list": self._list,
            "info": self._info,
            "create": self._create,
            "addfield": self._add_field,
            "modifyfield": self._modify_field,
            "modifyfromc": self._modify_from_c,
            "parsec": self._modify_from_c,
            "parse": self._parse,
            "parseheader": self._parse_header,
            "validate": self._validate,
            "apply": self._apply,
            "delete": self._delete,
        }
        handler = self._dispatch_handler(dispatch, action, "action", program_info=program_info)
        return await handler(args)

    async def _list(self, args: dict[str, Any], *, program_info: ProgramInfo | SimpleNamespace | None) -> list[types.TextContent]:
        logger.debug("diag.enter %s", "mcp_server/providers/structures.py:StructureToolProvider._list")
        assert program_info is not None  # for type checker
        program = program_info.program
        max_results = self._get_int(args, "maxresults", "limit", default=100)
        cat_path = self._get_str(args, "categorypath", "category")
        name_filter = self._get_str(args, "namefilter", "query", "filter", "search", "pattern").strip().lower()

        results = []
        for row in collect_structures(program):
            if len(results) >= max_results:
                break
            if cat_path and str(row.get("categoryPath", "")) != cat_path:
                continue
            if name_filter and name_filter not in str(row.get("name", "")).lower():
                continue
            results.append(
                {
                    "name": row.get("name", ""),
                    "path": row.get("categoryPath", ""),
                    "length": row.get("length", 0),
                    "numComponents": row.get("numComponents", 0),
                    "isUnion": row.get("isUnion", False),
                },
            )
        return create_success_response({"action": "list", "structures": results, "count": len(results)})

    async def _info(self, args: dict[str, Any], *, program_info: ProgramInfo | SimpleNamespace | None) -> list[types.TextContent]:
        logger.debug("diag.enter %s", "mcp_server/providers/structures.py:StructureToolProvider._info")
        name = self._require_str(args, "name", "structurename", "structure", name="name")
        assert program_info is not None  # for type checker
        program = program_info.program
        dtm = program.getDataTypeManager()

        dt = self._find_structure(dtm, name, program_info=program_info)
        if dt is None:
            raise ValueError(f"Structure not found: {name}")

        fields = collect_structure_fields(dt)
        for i, field in enumerate(fields):
            if not field.get("name"):
                field["name"] = f"field_{i}"

        return create_success_response(
            {
                "action": "info",
                "name": name,
                "length": dt.getLength(),
                "numComponents": dt.getNumComponents(),
                "fields": fields,
                "description": dt.getDescription() or "",
            },
        )

    async def _create(self, args: dict[str, Any], *, program_info: ProgramInfo | SimpleNamespace | None) -> list[types.TextContent]:
        logger.debug("diag.enter %s", "mcp_server/providers/structures.py:StructureToolProvider._create")
        name = self._require_str(args, "name", "structurename", name="name")
        size = self._get_int(args, "size", default=0)
        cat_path = self._get_str(args, "categorypath", "category", default="/")
        is_union = self._get_bool(args, "isunion", default=False)

        assert program_info is not None  # for type checker
        program = program_info.program
        dtm = program.getDataTypeManager()

        if not args.get(FORCE_APPLY_CONFLICT_ID_KEY):
            existing = self._find_structure(dtm, name, program_info=program_info)
            if existing is not None:
                from agentdecompile_cli.mcp_server.conflict_store import store as conflict_store_store
                from agentdecompile_cli.mcp_server.session_context import get_current_mcp_session_id

                conflict_id = str(uuid.uuid4())
                conflict_summary = f"Create structure would overwrite existing structure with the same name:\n\nStructure **{name}** already exists."
                next_step = f'To apply this change, call `resolve-modification-conflict` with `conflictId` = "{conflict_id}" and `resolution` = "overwrite". To discard, use `resolution` = "skip".'
                program_path = args.get(n("programPath")) or getattr(program_info, "path", None) or getattr(program_info, "file_path", None)
                store_args = dict(args)
                store_args["mode"] = "create"
                conflict_store_store(
                    get_current_mcp_session_id(),
                    conflict_id,
                    tool=Tool.MANAGE_STRUCTURES.value,
                    arguments=store_args,
                    program_path=str(program_path) if program_path else None,
                    summary=conflict_summary,
                )
                return create_conflict_response(conflict_id, Tool.MANAGE_STRUCTURES.value, conflict_summary, next_step)

        from ghidra.program.model.data import CategoryPath  # pyright: ignore[reportMissingModuleSource]

        def _create_structure() -> None:
            if is_union:
                from ghidra.program.model.data import UnionDataType  # pyright: ignore[reportMissingModuleSource]

                dt = UnionDataType(CategoryPath(cat_path), name, dtm)
            else:
                from ghidra.program.model.data import StructureDataType  # pyright: ignore[reportMissingModuleSource]

                dt = StructureDataType(CategoryPath(cat_path), name, size, dtm)
            dtm.addDataType(dt, None)

        self._run_program_transaction(program, "create-structure", _create_structure)

        return create_success_response({"action": "create", "name": name, "size": size, "isUnion": is_union, "success": True})

    async def _add_field(self, args: dict[str, Any], *, program_info: ProgramInfo | SimpleNamespace | None) -> list[types.TextContent]:
        logger.debug("diag.enter %s", "mcp_server/providers/structures.py:StructureToolProvider._add_field")
        struct_name = self._require_str(args, "name", "structurename", "structure", name="name")
        assert program_info is not None  # for type checker
        program = program_info.program
        dtm = program.getDataTypeManager()

        dt = self._find_structure(dtm, struct_name, program_info=program_info)
        if dt is None:
            raise ValueError(f"Structure not found: {struct_name}")

        parser = self._new_data_type_parser(dtm)

        # Batch support
        batch = self._get_list(args, "fields")
        if batch:
            results = []

            def _batch_add_fields() -> None:
                for field in batch:
                    ni = {n(k): v for k, v in field.items()}
                    f_name = ni.get("fieldname") or ni.get("name") or f"field_{dt.getNumComponents()}"
                    f_type = ni.get("fieldtype") or ni.get("type") or "byte"
                    f_comment = ni.get("fieldcomment") or ni.get("comment") or ""
                    try:
                        fdt = parser.parse(f_type)
                        dt.add(fdt, fdt.getLength(), f_name, f_comment)
                        results.append({"name": f_name, "success": True})
                    except Exception as e:
                        results.append({"name": f_name, "success": False, "error": str(e)})

            self._run_program_transaction(program, "batch-add-fields", _batch_add_fields)
            return create_success_response({"action": "add_field", "structure": struct_name, "batch": True, "results": results})

        # Single field
        field_name = self._get_str(args, "fieldname", "field", default=f"field_{dt.getNumComponents()}")
        field_type = self._require_str(args, "fieldtype", "type", name="fieldType")
        field_comment = self._get_str(args, "fieldcomment", "comment", default="")
        fdt = parser.parse(field_type)

        def _add_field() -> None:
            dt.add(fdt, fdt.getLength(), field_name, field_comment)

        self._run_program_transaction(program, "add-field", _add_field)
        return create_success_response({"action": "add_field", "structure": struct_name, "field": field_name, "type": field_type, "success": True})

    async def _modify_field(self, args: dict[str, Any], *, program_info: ProgramInfo | SimpleNamespace | None) -> list[types.TextContent]:
        """Edit existing fields: rename, retype or re-comment.

        Single edit: ``fieldOffset`` selects the field (``fieldName`` is then its new
        name), or ``fieldName`` selects it by name when ``newFieldName`` is given.
        Batch: ``fields`` is a list of objects using the same keys per entry.
        """
        logger.debug("diag.enter %s", "mcp_server/providers/structures.py:StructureToolProvider._modify_field")
        struct_name = self._require_str(args, "name", "structurename", "structure", name="name")

        assert program_info is not None  # for type checker
        program = program_info.program
        dtm = program.getDataTypeManager()

        dt = self._find_structure(dtm, struct_name, program_info=program_info)
        if dt is None:
            raise ValueError(f"Structure not found: {struct_name}")

        parser = self._new_data_type_parser(dtm)

        raw_fields = self._get(args, "fields")
        if isinstance(raw_fields, str) and raw_fields.strip():
            import json

            try:
                raw_fields = json.loads(raw_fields)
            except json.JSONDecodeError as exc:
                raise ValueError(f"fields must be a JSON array of objects: {exc}") from exc
        if isinstance(raw_fields, dict):
            raw_fields = [raw_fields]

        if raw_fields:
            if not isinstance(raw_fields, list):
                raise ValueError("fields must be a list of objects")
            edits = [{n(k): v for k, v in item.items()} if isinstance(item, dict) else None for item in raw_fields]
        else:
            edits = [
                {
                    "fieldoffset": self._get(args, "fieldoffset", "offset"),
                    "fieldname": self._get_str(args, "fieldname", "field"),
                    "newfieldname": self._get_str(args, "newfieldname", "newname"),
                    "fieldtype": self._get_str(args, "fieldtype", "type", "newfieldtype"),
                    "fieldcomment": self._get(args, "fieldcomment", "comment"),
                },
            ]

        results: list[dict[str, Any]] = []

        def _apply_edits() -> None:
            for item in edits:
                if item is None:
                    results.append({"name": "?", "success": False, "error": "field entry must be an object"})
                    continue
                try:
                    results.append(self._apply_field_edit(dt, parser, item))
                except Exception as exc:
                    label = str(item.get("fieldname") or item.get("name") or item.get("fieldoffset") or item.get("offset") or "?")
                    results.append({"name": label, "success": False, "error": str(exc)})

        self._run_program_transaction(program, "modify-field", _apply_edits)

        if not raw_fields:
            only = results[0]
            if not only.get("success"):
                raise ValueError(f"modify_field failed on {struct_name}: {only.get('error')}")
            return create_success_response({"action": "modify_field", "structure": struct_name, **{k: v for k, v in only.items() if k != "name"}, "field": only.get("name"), "success": True})
        return create_success_response(
            {
                "action": "modify_field",
                "structure": struct_name,
                "batch": True,
                "results": results,
                "success": all(r.get("success") for r in results),
                **({} if all(r.get("success") for r in results) else {"error": "; ".join(f"{r.get('name')}: {r.get('error')}" for r in results if not r.get("success"))}),
            },
        )

    @staticmethod
    def _apply_field_edit(dt: Any, parser: Any, item: dict[str, Any]) -> dict[str, Any]:
        """Apply one normalized field edit to *dt*; return a result row or raise ``ValueError``."""
        raw_offset = item.get("fieldoffset", item.get("offset"))
        selector_name = str(item.get("fieldname") or item.get("name") or "").strip()
        new_name = str(item.get("newfieldname") or item.get("newname") or "").strip()
        new_type = str(item.get("fieldtype") or item.get("type") or item.get("newfieldtype") or "").strip()
        comment = item.get("fieldcomment", item.get("comment"))

        if raw_offset is not None and str(raw_offset).strip() != "":
            text = str(raw_offset).strip()
            offset = int(text, 16) if text.lower().startswith("0x") else int(text)
            comp = dt.getComponentAt(offset)
            if comp is None:
                raise ValueError(f"No field at offset {offset}")
            if selector_name and not new_name:
                # Offset selects; fieldName is the new name (legacy single-field form).
                new_name = selector_name
        elif selector_name:
            comp = None
            for candidate in list(dt.getDefinedComponents()):
                if str(candidate.getFieldName() or "") == selector_name:
                    comp = candidate
                    break
            if comp is None:
                raise ValueError(f"No field named {selector_name}")
        else:
            raise ValueError("Select the field with fieldOffset or fieldName")

        old_name = str(comp.getFieldName() or "")
        if not new_name and not new_type and comment is None:
            raise ValueError(f"Nothing to change for field {old_name or comp.getOffset()}: give newFieldName, fieldType or fieldComment")

        final_name = new_name or (comp.getFieldName() or None)
        final_comment = str(comment) if comment is not None else comp.getComment()
        if new_type:
            new_dt = parser.parse(new_type)
            # DataTypeComponent has no setDataType; replace the component in place.
            comp = dt.replaceAtOffset(comp.getOffset(), new_dt, new_dt.getLength(), final_name, final_comment)
        else:
            if new_name:
                comp.setFieldName(new_name)
            if comment is not None:
                comp.setComment(str(comment))
        return {
            "name": str(comp.getFieldName() or ""),
            "previousName": old_name,
            "offset": int(comp.getOffset()),
            "dataType": str(comp.getDataType().getName()),
            "success": True,
        }

    async def _modify_from_c(self, args: dict[str, Any], *, program_info: ProgramInfo | SimpleNamespace | None) -> list[types.TextContent]:
        logger.debug("diag.enter %s", "mcp_server/providers/structures.py:StructureToolProvider._modify_from_c")
        c_def = self._require_str(args, "cdefinition", "headercontent", "definition", "code", "c", name="cDefinition")
        assert program_info is not None  # for type checker
        program = program_info.program
        dtm = program.getDataTypeManager()

        try:
            from ghidra.app.util.cparser.C import CParser

            parser = CParser(dtm)

            def _parse_c_struct() -> tuple[list[Any], str]:
                from ghidra.program.model.data import DataTypeConflictHandler

                last = parser.parse(c_def)
                # CParser(dtm) does not store what it parses and parse() returns only
                # the last declaration, so resolve every composite, enum and typedef
                # it collected. Types the header only references were looked up in
                # dtm by the parser and are not in these maps, so existing program
                # types are not replaced by empty placeholders.
                parsed: list[Any] = []
                for table in (parser.getComposites(), parser.getEnums(), parser.getTypes()):
                    if table is not None:
                        parsed.extend(value for value in table.values() if value is not None)
                if not parsed and last is not None:
                    parsed.append(last)
                resolved: list[Any] = []
                seen: set[str] = set()
                for item in parsed:
                    stored = dtm.resolve(item, DataTypeConflictHandler.REPLACE_HANDLER)
                    key = str(stored.getPathName()) if hasattr(stored, "getPathName") else str(stored)
                    if key not in seen:
                        seen.add(key)
                        resolved.append(stored)
                last_name = str(last.getName()) if last is not None and hasattr(last, "getName") else ""
                return resolved, last_name

            stored_types, last_name = self._run_program_transaction(program, "parse-c-struct", _parse_c_struct)
            names = sorted(str(dt.getName()) if hasattr(dt, "getName") else str(dt) for dt in stored_types)
            payload: dict[str, Any] = {
                "action": "modify_from_c",
                "parsed": True,
                "name": last_name if last_name in names else (names[-1] if names else ""),
                "names": names,
                "count": len(names),
                "success": True,
            }
            if len(names) > 1:
                payload["batch"] = True
                payload["results"] = [{"name": name, "success": True} for name in names]
            return create_success_response(payload)
        except ImportError:
            raise ValueError("CParser not available in this environment")

    async def _parse(self, args: dict[str, Any], *, program_info: ProgramInfo | SimpleNamespace | None) -> list[types.TextContent]:
        logger.debug("diag.enter %s", "mcp_server/providers/structures.py:StructureToolProvider._parse")
        return await self._modify_from_c(args, program_info=program_info)

    async def _parse_header(self, args: dict[str, Any], *, program_info: ProgramInfo | SimpleNamespace | None) -> list[types.TextContent]:
        logger.debug("diag.enter %s", "mcp_server/providers/structures.py:StructureToolProvider._parse_header")
        return await self._modify_from_c(args, program_info=program_info)

    async def _validate(self, args: dict[str, Any], *, program_info: ProgramInfo | SimpleNamespace | None) -> list[types.TextContent]:
        logger.debug("diag.enter %s", "mcp_server/providers/structures.py:StructureToolProvider._validate")
        c_def = self._require_str(args, "cdefinition", "headercontent", "definition", "code", "c", name="cDefinition")
        assert program_info is not None  # for type checker

        scratch = None
        try:
            try:
                from jpype import JArray

                from ghidra.app.util.cparser.C import CParser
                from ghidra.program.model.data import DataTypeManager, StandAloneDataTypeManager

                # Validation must not add types to the program: parse into a throwaway manager.
                # The program's manager is passed as a read-only source so definitions that
                # use program types (DWORD, undefined4, user structs) still resolve.
                program_dtm = program_info.program.getDataTypeManager()
                scratch = StandAloneDataTypeManager("agentdecompile-validate")
                parser = CParser(scratch, False, JArray(DataTypeManager)([program_dtm]))
            except ImportError as e:
                # A broken environment is an error, not a verdict on the caller's C.
                raise ValueError("CParser not available in this environment") from e
            except Exception as e:
                raise ValueError(f"structure validation setup failed: {type(e).__name__}: {e}") from e

            try:
                dt = parser.parse(c_def)
                # Read the name while the scratch manager is still open.
                name = str(dt.getName()) if hasattr(dt, "getName") else str(dt)
                return create_success_response({"action": "validate", "valid": True, "name": name})
            except Exception as e:
                logger.debug("structure validate parse failed", exc_info=True)
                return create_success_response({"action": "validate", "valid": False, "error": str(e)})
        finally:
            if scratch is not None:
                try:
                    scratch.close()
                except Exception:
                    logger.debug("structure validate scratch close failed", exc_info=True)

    async def _apply(self, args: dict[str, Any], *, program_info: ProgramInfo | SimpleNamespace | None) -> list[types.TextContent]:
        logger.debug("diag.enter %s", "mcp_server/providers/structures.py:StructureToolProvider._apply")
        struct_name = self._require_str(args, "name", "structurename", "structure", name="name")
        addr_str = self._require_str(args, "addressorsymbol", "address", "addr", name="addressOrSymbol")
        assert program_info is not None  # for type checker
        program = program_info.program
        dtm = program.getDataTypeManager()

        dt = self._find_structure(dtm, struct_name, program_info=program_info)
        if dt is None:
            raise ValueError(f"Structure not found: {struct_name}")

        # Batch
        addr_list = self._get_list(args, "addressorsymbol", "addresses")
        if addr_list and len(addr_list) > 1:
            results = []

            def _batch_apply_struct() -> None:
                listing = self._get_listing(program, program_info=program_info)
                for a in addr_list:
                    try:
                        addr = self._resolve_address(str(a), program=program, program_info=program_info)
                        listing.clearCodeUnits(addr, addr.add(dt.getLength() - 1), False)
                        listing.createData(addr, dt)
                        results.append({"address": str(addr), "success": True})
                    except Exception as e:
                        results.append({"address": str(a), "success": False, "error": str(e)})

            self._run_program_transaction(program, "batch-apply-struct", _batch_apply_struct)
            return create_success_response({"action": "apply", "batch": True, "results": results})

        addr = self._resolve_address(addr_str, program=program, program_info=program_info)
        listing = self._get_listing(program, program_info=program_info)

        if not args.get(FORCE_APPLY_CONFLICT_ID_KEY):
            from agentdecompile_cli.mcp_utils.datatype_util import format_conflict_lines, overlapping_data_conflicts

            # clearCodeUnits below clears every code unit overlapping [addr, addr+len-1]; ask before losing defined data anywhere in it.
            conflicts = overlapping_data_conflicts(listing, addr, dt)
            if conflicts:
                from agentdecompile_cli.mcp_server.conflict_store import store as conflict_store_store
                from agentdecompile_cli.mcp_server.session_context import get_current_mcp_session_id

                conflict_id = str(uuid.uuid4())
                conflict_summary = f"Apply structure would overwrite existing data at address:\n\n```diff\n{format_conflict_lines(conflicts, prefix='(existing) ')}\n+ {struct_name}\n```"
                next_step = f'To apply this change, call `resolve-modification-conflict` with `conflictId` = "{conflict_id}" and `resolution` = "overwrite". To discard, use `resolution` = "skip".'
                program_path = args.get(n("programPath")) or getattr(program_info, "path", None) or getattr(program_info, "file_path", None)
                store_args = dict(args)
                store_args["mode"] = "apply"
                conflict_store_store(
                    get_current_mcp_session_id(),
                    conflict_id,
                    tool=Tool.MANAGE_STRUCTURES.value,
                    arguments=store_args,
                    program_path=str(program_path) if program_path else None,
                    summary=conflict_summary,
                )
                return create_conflict_response(conflict_id, Tool.MANAGE_STRUCTURES.value, conflict_summary, next_step)

        def _apply_struct() -> None:
            listing.clearCodeUnits(addr, addr.add(dt.getLength() - 1), False)
            listing.createData(addr, dt)

        self._run_program_transaction(program, "apply-struct", _apply_struct)
        return create_success_response({"action": "apply", "structure": struct_name, "address": str(addr), "success": True})

    async def _delete(self, args: dict[str, Any], *, program_info: ProgramInfo | SimpleNamespace | None) -> list[types.TextContent]:
        logger.debug("diag.enter %s", "mcp_server/providers/structures.py:StructureToolProvider._delete")
        name = self._require_str(args, "name", "structurename", name="name")
        assert program_info is not None  # for type checker
        program = program_info.program
        dtm = program.getDataTypeManager()

        dt = self._find_structure(dtm, name, program_info=program_info)
        if dt is None:
            raise ValueError(f"Structure not found: {name}")

        def _delete_structure() -> None:
            dtm.remove(dt, None)

        self._run_program_transaction(program, "delete-structure", _delete_structure)
        return create_success_response({"action": "delete", "name": name, "success": True})
