"""Generate ActionSpec rows from public CLI parsers and the MCP registry.

Hand-written catalogs go stale. Completeness is: every public corpus, recover,
reconstruct, and advertised MCP verb has a row.
"""

from __future__ import annotations

import argparse
from dataclasses import replace

from agentdecompile_recovery.corpus.dashboard.actions.catalog import (
    ADDR_KEYS,
    PROGRAM_KEYS,
    ActionSpec,
    FieldSpec,
)
from agentdecompile_recovery.corpus.verb_admission import VerbAdmission

_SKIP_DESTS = frozenset({"help", "version"})
_CLICK_DANGER_COMMANDS = frozenset({"init", "delete", "import"})
_CONTEXT = {
    "program": "program",
    "repo": "repo",
    "repository": "repo",
    "repo-path": "repo",
    "path": "repo",
    "binary": "repo",
    "db": "db",
    "out-dir": "work_dir",
    "out": "work_dir",
    "work-dir": "work_dir",
    "kb": "kb",
    "id": "slug",
    "from": "program",
}


def _kind(action: argparse.Action) -> str:
    if isinstance(
        action,
        (argparse._StoreTrueAction, argparse._StoreFalseAction, argparse.BooleanOptionalAction),
    ):
        return "bool"
    if isinstance(action, argparse._AppendAction) or action.nargs in ("+", "*", argparse.REMAINDER):
        return "array"
    typ = action.type
    if typ is int:
        return "int"
    if typ is float:
        return "float"
    if typ is not None and getattr(typ, "__name__", "") == "Path":
        return "path"
    return "str"


def _field(action: argparse.Action) -> FieldSpec | None:
    if action.dest in _SKIP_DESTS or action.option_strings == ["-h", "--help"]:
        return None
    if action.option_strings:
        flag = next((opt for opt in action.option_strings if opt.startswith("--")), action.option_strings[0])
        name = flag.lstrip("-")
        positional = False
    else:
        flag = None
        name = action.dest.replace("_", "-") if action.dest else "arg"
        positional = True
    default = action.default
    if default is argparse.SUPPRESS:
        default = None
    if isinstance(action, argparse._StoreFalseAction):
        default = False
    choices = tuple(str(item) for item in action.choices) if action.choices else ()
    required = bool(action.required) if not positional else action.nargs not in ("?", "*", argparse.REMAINDER)
    if positional and action.nargs == "?":
        required = False
    return FieldSpec(
        name=name,
        kind=_kind(action),
        required=required,
        flag=flag,
        choices=choices,
        default=default if default not in (None, argparse.SUPPRESS) and not callable(default) else None,
        from_context=_CONTEXT.get(name),
        help=(action.help or "")[:240],
        positional=positional,
    )


def _subparsers(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    return {}


def _fields(parser: argparse.ArgumentParser) -> tuple[FieldSpec, ...]:
    out: list[FieldSpec] = []
    seen: set[str] = set()
    for action in parser._actions:
        field = _field(action)
        if field is None or field.name in seen:
            continue
        seen.add(field.name)
        out.append(field)
    return tuple(out)


def _pages(fields: tuple[FieldSpec, ...], writes: bool) -> tuple[str, ...]:
    pages = ["work", "home"]
    names = {field.name for field in fields}
    if names & {"program", "repo", "binary", "path", "from"}:
        pages.append("binary")
    if names & {"address", "addr", "function"}:
        pages.append("function")
    if writes:
        pages.append("operations")
    return tuple(dict.fromkeys(pages))


def specs_from_argparse(
    *,
    group: str,
    backend: str,
    parser: argparse.ArgumentParser,
) -> list[ActionSpec]:
    rows: list[ActionSpec] = []
    for command, sub in _subparsers(parser).items():
        fields = _fields(sub)
        if group == "corpus" and command == "export-run-report":
            fields = tuple(replace(field, from_context="report_file", help="JSON report file; defaults to the current workspace's recovery-report.json.") if field.name == "out" else field for field in fields)
        danger = bool(getattr(sub, "danger", False))
        native_verify = group == "recover" and command == "verify-package"
        # A declared verb carries its whole VerbAdmission on the parser
        # (aliases share the object); the three legacy fields come from it.
        # An undeclared verb keeps the legacy getattr path and resolves to
        # the conservative default at admission time (H5).
        admission = getattr(sub, "admission", None)
        if not isinstance(admission, VerbAdmission):
            admission = None
        if admission is not None:
            # Keep the pre-existing verifier safety override: it performs
            # long-running native/object verification even though the
            # recover parser does not yet declare typed admission metadata.
            mutating = native_verify or admission.mutating
            long_running = native_verify or admission.long_running
            identity_scope = admission.identity_scope
        else:
            mutating = native_verify or bool(getattr(sub, "mutating", False))
            long_running = native_verify or bool(getattr(sub, "long_running", False))
            identity_scope = str(getattr(sub, "identity_scope", ""))
        rows.append(
            ActionSpec(
                id=f"{group}.{command}",
                title=command.replace("-", " "),
                group=group,
                backend=backend,
                command=command,
                summary=(sub.description or sub.epilog or getattr(sub, "help", None) or command)[:300],
                fields=fields,
                pages=_pages(fields, mutating),
                danger=danger,
                mutating=mutating,
                long_running=long_running,
                identity_scope=identity_scope,
                ghidra_exclusive=bool(getattr(sub, "ghidra_exclusive", False)),
                admission=admission,
            )
        )
    return rows


def corpus_specs() -> list[ActionSpec]:
    from agentdecompile_recovery.corpus.cli import build_parser

    return specs_from_argparse(
        group="corpus",
        backend="corpus-cli",
        parser=build_parser(),
    )


def recover_specs() -> list[ActionSpec]:
    from agentdecompile_recovery.cli import build_parser

    return specs_from_argparse(
        group="recover",
        backend="recover-cli",
        parser=build_parser(),
    )


def reconstruct_specs() -> list[ActionSpec]:
    from agentdecompile_recovery.frontdoor import (
        UPSTREAM_COMMANDS,
        build_parser,
        build_self_check_parser,
        build_upstream_status_parser,
    )

    parser = build_parser()
    fields = _fields(parser)
    rows = [
        ActionSpec(
            id="reconstruct.one-shot",
            title="Reconstruct one-shot",
            group="reconstruct",
            backend="reconstruct-cli",
            command="",
            summary="Default agentdecompile-reconstruct path: binary plus optional context.",
            fields=fields,
            pages=("binary", "operations", "work"),
            danger=bool(getattr(parser, "danger", False)),
            mutating=bool(getattr(parser, "mutating", False)),
            long_running=bool(getattr(parser, "long_running", False)),
        ),
        ActionSpec(
            id="reconstruct.corpus",
            title="Reconstruct corpus delegate",
            group="reconstruct",
            backend="reconstruct-cli",
            command="corpus",
            summary="Delegate to agentdecompile-corpus from reconstruct.",
            fields=(_f_str("argv", help="Remaining corpus argv, space-separated"),),
            pages=("work",),
            mutating=True,
            long_running=True,
        ),
        ActionSpec(
            id="reconstruct.self-check",
            title="Reconstruct self-check",
            group="reconstruct",
            backend="reconstruct-cli",
            command="self-check",
            fields=_fields(build_self_check_parser()),
            pages=("work",),
        ),
        ActionSpec(
            id="reconstruct.upstream-status",
            title="Reconstruct upstream status",
            group="reconstruct",
            backend="reconstruct-cli",
            command="upstream-status",
            fields=_fields(build_upstream_status_parser()),
            pages=("work",),
        ),
    ]
    for command in sorted(UPSTREAM_COMMANDS):
        rows.append(
            ActionSpec(
                id=f"reconstruct.{command}",
                title=command.replace("-", " "),
                group="reconstruct",
                backend="reconstruct-cli",
                command=command,
                summary=f"Reconstruct upstream command {command}.",
                fields=(_f_str("argv", help="Remaining argv, space-separated"),),
                pages=("work", "operations"),
                mutating=True,
                long_running=True,
            )
        )
    return rows


def _f_str(name: str, help: str = "") -> FieldSpec:
    return FieldSpec(name=name, kind="str", help=help)


def mcp_specs() -> list[ActionSpec]:
    from agentdecompile_cli.registry import (
        ADVERTISED_TOOLS,
        Tool,
        get_tool_metadata,
        get_tool_params,
        normalize_identifier,
    )
    from agentdecompile_cli.mcp_server.tool_providers import ToolProviderManager

    manager = ToolProviderManager()
    manager.register_all_providers()
    schemas = {tool.name: tool.inputSchema for tool in manager.list_tools()}
    out: list[ActionSpec] = []
    for name in ADVERTISED_TOOLS:
        params = get_tool_params(name)
        meta = get_tool_metadata(name)
        writes = bool(meta and meta.writes_state)
        # Only a declared resource contract may narrow the conservative MCP
        # admission. This query reads Ghidra references and may open a project.
        corpus_db_access = getattr(meta, "corpus_db_access", "unknown") if meta else "unknown"
        ghidra_session_access = getattr(meta, "ghidra_session_access", "unknown") if meta else "unknown"
        # Compatibility for a live process whose older registry module was
        # correctly rejected by in-place reload: this canonical enum is the
        # one provider tool whose read-only Ghidra/DB contract is source-audited.
        if (meta and name == Tool.GET_REFERENCES.value and not writes
                and corpus_db_access == "unknown" and ghidra_session_access == "unknown"):
            corpus_db_access, ghidra_session_access = "none", "query"
        reference_query = bool(meta and corpus_db_access == "none" and ghidra_session_access == "query")
        admission = (
            VerbAdmission(
                mutating=False,
                long_running=False,
                identity_scope="",
                read_only=True,
                snapshot="none",
                output_scope="none",
                drains_on_pause=True,
                boots_analyzer=False,
                lane="ghidra",
                budget_class="small",
                cancel="sigterm",
            )
            if reference_query else None
        )
        schema = schemas.get(name, {})
        properties = schema.get('properties', {})
        by_norm = {normalize_identifier(key): value for key, value in properties.items()}
        names = {normalize_identifier(param): param for param in params}
        for key in properties:
            names.setdefault(normalize_identifier(key), key)
        required = {normalize_identifier(key) for key in schema.get('required', [])}
        field_rows = []
        for norm, param in names.items():
            prop = by_norm.get(norm, {})
            json_type = prop.get('type')
            if not isinstance(json_type, str):
                json_type = None
            kind = {'boolean': 'bool', 'integer': 'int', 'number': 'float',
                    'array': 'array', 'object': 'object', 'string': 'str'}.get(json_type, _mcp_kind(param))
            field_rows.append(FieldSpec(
                name=param, kind=kind,
                required=norm in required or (param in {'functionIdentifier', 'code'} and name != 'status'),
                from_context=_mcp_context(param),
                choices=tuple(str(value) for value in prop.get('enum', [])),
                default=prop.get('default'), help=prop.get('description', ''),
                schema=prop,
            ))
        fields = tuple(field_rows)
        tool = Tool.from_string(name)
        danger = writes
        out.append(
            ActionSpec(
                id=f"mcp.{name}",
                title=name.replace("-", " "),
                group="mcp",
                backend="mcp-cli",
                command=name,
                summary=f"MCP tool {name}" + (f" (tier {tool.analysis_tier})" if tool else ""),
                fields=fields,
                pages=_mcp_pages(params, writes),
                danger=danger,
                mutating=writes,
                long_running=bool(meta and meta.long_running),
                identity_scope=admission.identity_scope if admission else "",
                ghidra_exclusive=reference_query,
                admission=admission,
            )
        )
    return out


def _mcp_kind(name: str) -> str:
    lowered = name.lower()
    if any(token in lowered for token in ("count", "limit", "offset", "timeout", "port", "index")):
        return "int"
    if "path" in lowered or "file" in lowered or "dir" in lowered:
        return "path"
    if lowered.startswith("include") or lowered.startswith("set") or lowered in {"force", "apply"}:
        return "bool"
    return "str"


def _mcp_context(name: str) -> str | None:
    if name in PROGRAM_KEYS:
        return "program"
    if name in ADDR_KEYS:
        return "addr"
    return None


def _mcp_pages(params: list[str], writes: bool) -> tuple[str, ...]:
    pages = ["work", "home"]
    keys = set(params)
    if keys & ADDR_KEYS:
        pages.append("function")
    if keys & PROGRAM_KEYS:
        pages.append("binary")
    if writes:
        pages.append("operations")
    return tuple(dict.fromkeys(pages))


_GUI_CLICK = frozenset({
    "current-address",
    "current-function",
    "open-in-code-browser",
    "open-all-in-code-browser",
})


def _click_root():
    from agentdecompile_cli.cli import _ensure_dynamic_commands_registered, main

    _ensure_dynamic_commands_registered()
    return main


def _click_kind(param) -> str:
    if getattr(param, "is_flag", False):
        return "bool"
    name = getattr(getattr(param, "type", None), "name", "") or ""
    if name in {"integer", "int"}:
        return "int"
    if name in {"float"}:
        return "float"
    if name in {"path"}:
        return "path"
    return "str"


def _click_fields(cmd) -> tuple[FieldSpec, ...]:
    import click

    out: list[FieldSpec] = []
    seen: set[str] = set()
    for param in getattr(cmd, "params", ()):
        if param.name in _SKIP_DESTS:
            continue
        if isinstance(param, click.Argument):
            name = (param.name or "arg").replace("_", "-")
            positional = True
            flag = None
            required = bool(param.required)
        else:
            flag = next((opt for opt in param.opts if opt.startswith("--")), param.opts[0] if param.opts else None)
            name = (flag or param.name or "opt").lstrip("-")
            positional = False
            required = bool(getattr(param, "required", False))
        if name in seen:
            continue
        seen.add(name)
        default = getattr(param, "default", None)
        if default is not None and callable(default):
            default = None
        choices = ()
        typ = getattr(param, "type", None)
        if getattr(typ, "choices", None):
            choices = tuple(str(item) for item in typ.choices)
        out.append(
            FieldSpec(
                name=name,
                kind=_click_kind(param),
                required=required,
                flag=flag,
                choices=choices,
                default=default if default not in (None, "") else None,
                from_context=_CONTEXT.get(name),
                help=(getattr(param, "help", None) or "")[:240],
                positional=positional,
            )
        )
    return tuple(out)


def click_public_names() -> list[str]:
    """Top-level public Click verbs that are not already advertised MCP tools."""
    from agentdecompile_cli.registry import ADVERTISED_TOOLS

    advertised = set(ADVERTISED_TOOLS)
    names: list[str] = []
    for name, cmd in sorted(_click_root().commands.items()):
        if getattr(cmd, "hidden", False):
            continue
        # Bridged corpus/recover/reconstruct/grid forward raw argv to argparse;
        # corpus.*, recover.* and reconstruct.* already expose them field-by-field.
        if getattr(cmd, "BRIDGED", False):
            continue
        if name in advertised or name in _GUI_CLICK:
            continue
        names.append(name)
    return names


def click_specs() -> list[ActionSpec]:
    rows: list[ActionSpec] = []
    root = _click_root()
    for name in click_public_names():
        cmd = root.commands[name]
        fields = _click_fields(cmd)
        if getattr(cmd, "commands", None):
            fields = (
                FieldSpec(
                    name="subcommand",
                    kind="str",
                    required=True,
                    positional=True,
                    help="Click subcommand under this group",
                ),
                *_click_fields(cmd),
                FieldSpec(name="argv", kind="str", help="Remaining argv, space-separated"),
            )
        rows.append(
            ActionSpec(
                id=f"cli.{name}",
                title=name.replace("-", " "),
                group="cli",
                backend="click-cli",
                command=name,
                summary=(cmd.help or cmd.short_help or name)[:300],
                fields=fields,
                pages=_pages(fields, True),
                danger=name in _CLICK_DANGER_COMMANDS,
                mutating=name not in {"alias", "tool"},
                long_running=name in {"ghidrecomp", "tool-seq", "tool-seq-file"},
            )
        )
    return rows


def public_command_ids() -> dict[str, set[str]]:
    """Expected action ids for completeness tests."""
    from agentdecompile_cli.registry import ADVERTISED_TOOLS
    from agentdecompile_recovery.corpus.cli import build_parser as corpus_parser
    from agentdecompile_recovery.cli import build_parser as recover_parser
    from agentdecompile_recovery.frontdoor import UPSTREAM_COMMANDS

    return {
        "corpus": {f"corpus.{name}" for name in _subparsers(corpus_parser())},
        "recover": {f"recover.{name}" for name in _subparsers(recover_parser())},
        "reconstruct": {
            "reconstruct.one-shot",
            "reconstruct.corpus",
            "reconstruct.self-check",
            "reconstruct.upstream-status",
            *{f"reconstruct.{name}" for name in UPSTREAM_COMMANDS},
        },
        "cli": {f"cli.{name}" for name in click_public_names()},
        "mcp": {f"mcp.{name}" for name in ADVERTISED_TOOLS},
    }


def generate_actions() -> list[ActionSpec]:
    return [*corpus_specs(), *recover_specs(), *reconstruct_specs(), *click_specs(), *mcp_specs()]
