"""Action catalog for the corpus dashboard and Swagger.

Every advertised MCP tool and every public corpus / recover / reconstruct
entrypoint is one cataloged action. The browser never sends a freeform argv.
Rows are generated from the live parsers — see introspect.py.
"""

from __future__ import annotations

import json
import os
import shlex
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agentdecompile_recovery.corpus.dashboard.common import (
    KNOWLEDGE_DB,
    live_db,
    query_db,
    runtime_project_root,
    runtime_work_dir,
)
from agentdecompile_recovery.corpus.verb_admission import UNDECLARED, VerbAdmission, from_legacy

PROGRAM_KEYS = frozenset({"programPath", "program", "binary", "path", "repo"})
ADDR_KEYS = frozenset({
    "address",
    "addressOrSymbol",
    "target",
    "function",
    "functionIdentifier",
    "identifier",
    "addr",
})
DB_KEYS = frozenset({"db"})
WORK_KEYS = frozenset({"work-dir", "work_dir", "out-dir", "out_dir", "outDir", "workspace"})
KB_KEYS = frozenset({"kb"})
REPO_KEYS = frozenset({"repo", "repo-path", "repo_path"})
# CLI flags that must be a file (PE/ELF/Mach-O), never a shared-fs repos folder.
FILE_BINARY_FIELDS = frozenset({"binary", "input"})

DANGEROUS_CORPUS = frozenset({
    "force",
    "apply",
    "llm-cleanup",
    "watch",
})

DANGEROUS_ARGV_FLAGS = frozenset({
    "--force",
    "--apply",
    "-f",
    "--llm-cleanup",
    "--watch",
})


@dataclass(frozen=True)
class FieldSpec:
    name: str
    kind: str = "str"
    required: bool = False
    flag: str | None = None
    choices: tuple[str, ...] = ()
    default: Any = None
    from_context: str | None = None
    help: str = ""
    positional: bool = False
    schema: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        default = payload.get("default")
        if isinstance(default, Path):
            payload["default"] = str(default)
        elif default is not None and not isinstance(default, (str, int, float, bool, list, tuple, dict)):
            payload["default"] = str(default)
        return payload


@dataclass(frozen=True)
class ActionSpec:
    id: str
    title: str
    group: str
    backend: str
    command: str
    summary: str = ""
    fields: tuple[FieldSpec, ...] = ()
    pages: tuple[str, ...] = ("work",)
    danger: bool = False
    mutating: bool = False
    long_running: bool = False
    identity_scope: str = ""
    ghidra_exclusive: bool = False
    # The verb's full admission declaration when it made one.  The three
    # legacy fields above are populated from it so nothing downstream breaks.
    admission: VerbAdmission | None = None

    @property
    def effective_admission(self) -> VerbAdmission:
        """The declaration, or the conservative default for an undeclared row.

        H5: the loop reads this, never the bare legacy fields, so a row that
        declared nothing is drained on pause rather than skipped.
        """
        if self.admission is not None:
            return self.admission
        if not (self.mutating or self.long_running or self.identity_scope):
            return UNDECLARED
        return from_legacy(
            mutating=self.mutating,
            long_running=self.long_running,
            identity_scope=self.identity_scope,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["fields"] = [field.to_dict() for field in self.fields]
        payload["admission"] = self.effective_admission.to_dict()
        return payload


_ACTIONS: list[ActionSpec] | None = None


def list_actions() -> list[ActionSpec]:
    global _ACTIONS
    # The in-process server may keep this catalog alive while the CLI parser
    # changes on disk. Refresh only when that parser's file identity changes,
    # so the dashboard remains parser-derived without a server restart.
    import importlib
    import threading

    refresh_lock = getattr(list_actions, "_refresh_lock", None)
    if refresh_lock is None:
        refresh_lock = threading.RLock()
        list_actions._refresh_lock = refresh_lock
    with refresh_lock:
        from agentdecompile_recovery.corpus import cli as corpus_cli

        # Action metadata lives here as well as in the parser. A live source
        # update to this module must invalidate the cached ActionSpec rows;
        # parser-only invalidation leaves the HTTP catalog advertising stale
        # fields and admission contracts after hot reload.
        catalog_stat = Path(__file__).resolve().stat()
        catalog_stamp = (catalog_stat.st_dev, catalog_stat.st_ino,
                         catalog_stat.st_size, catalog_stat.st_mtime_ns)
        previous_catalog_stamp = getattr(list_actions, "_catalog_stamp", None)
        # A request can observe the file's new stamp before its code is applied.
        # Cache ownership must follow the executing definition as well as disk.
        definition = list_actions.__code__
        if (previous_catalog_stamp != catalog_stamp
                or getattr(list_actions, "_definition_code", None) is not definition):
            if _ACTIONS is not None:
                _ACTIONS = None
            list_actions._catalog_stamp = catalog_stamp
            list_actions._definition_code = definition

        parser_path = Path(corpus_cli.__file__).resolve()
        parser_stat = parser_path.stat()
        parser_stamp = (parser_stat.st_dev, parser_stat.st_ino,
                        parser_stat.st_size, parser_stat.st_mtime_ns)
        if getattr(list_actions, "_parser_stamp", None) != parser_stamp:
            try:
                importlib.reload(corpus_cli)
            except Exception:
                if _ACTIONS is None:
                    raise
            else:
                _ACTIONS = None
    if _ACTIONS is None:
        from agentdecompile_recovery.corpus.dashboard.actions.introspect import generate_actions

        _ACTIONS = generate_actions() + [ActionSpec(
            id="review.list", title="Read candidate review", group="workbench",
            backend="match-review", command="list",
            fields=(FieldSpec("db", required=True, from_context="db"), FieldSpec("selection"),
                    FieldSpec("after_id", kind="int", default=0), FieldSpec("limit", kind="int", default=50)),
        ), ActionSpec(
            id="review.decide", title="Decide observed candidates", group="workbench",
            backend="match-review", command="decide", mutating=True, identity_scope="database",
            summary="Atomically accept or reject exact observed review bases with audit. Accept means verify, not source parity.",
            fields=(FieldSpec("db", required=True, from_context="db"), FieldSpec("selection", required=True),
                    FieldSpec("entries", kind="array", required=True, schema={"maxItems": 100})),
        ), ActionSpec(
            id="workbench.prepare", title="Prepare project", group="workbench",
            backend="preparation", command="prepare", mutating=True, long_running=True,
            summary="Automatically prepare, compare, and recover without a wall-time limit by default. Optional finite budgets and per-function attempt limits remain available. Completion is not proof.",
            fields=tuple(FieldSpec(name, from_context=name) for name in ("locator", "program", "slug")) + (
                FieldSpec("resume", kind="bool", default=False),
                FieldSpec("maxMcpToolCalls", kind="int", help="Optional nonnegative MCP tools/call cap, including prerequisites, retries and checkin. Omit for unlimited measured dispatches; resume retains spending."),
                FieldSpec("maxActionAdmissions", kind="int", help="Optional nonnegative initial action-admission allocation. Omit for unlimited accounting. Resume preserves the existing allocation and spending."),
            ),
        ), ActionSpec(
            id="workbench.merge-evidence", title="Bind compared knowledge", group="workbench",
            backend="merge-evidence", command="merge-evidence", mutating=True, identity_scope="database",
            summary="Bind accepted matches without rebuilding existing identities. Fill missing source attribution while retaining human metadata.",
            fields=(FieldSpec("db", required=True, from_context="db"), FieldSpec("run", required=True)),
        ), ActionSpec(
            id="workbench.workflow-control", title="Control workflow and scheduler", group="workbench",
            backend="workflow-control", command="workflow-control", mutating=True,
            summary="Pause, resume, stop, or adjust a preparation; control scheduler scopes; or safely reclassify a known read-only provider timeout while retaining its Ghidra reservation.",
            fields=(FieldSpec("preparation_id"), FieldSpec("operation", required=True, choices=("pause", "resume", "stop", "budget", "priority", "admission-budget", "provider-budget", "pause-scheduler-scope", "resume-scheduler-scope", "reclassify-read-only-provider", "retire-legacy-watchdog")), FieldSpec("job_id"), FieldSpec("scope"), FieldSpec("seconds", kind="int"), FieldSpec("unlimited", kind="bool"), FieldSpec("priority", kind="int"),
                    FieldSpec("maxMcpToolCalls", kind="int", help="New total MCP dispatch allocation for provider-budget; spent intents are retained."),
                    FieldSpec("maxActionAdmissions", kind="int", help="New total allocation; previously spent admissions are retained. Use unlimited=true explicitly to remove the cap."),
                    FieldSpec("expectedAllocationRevision", kind="int", help="Required current revision of the selected admission-budget or provider-budget; stale revisions are refused.")),
        ), ActionSpec(
            id="workbench.activity-snapshot", title="Read workspace activity", group="workbench",
            backend="activity-snapshot", command="activity-snapshot",
            summary="Read entity activity, progress, queue state, and receipt-backed evidence.",
            fields=(FieldSpec("locator", from_context="locator"), FieldSpec("slug", from_context="slug")),
        ), ActionSpec(
            id="workbench.resource-reconciliation-report", title="Inspect retained resource ownership", group="workbench",
            backend="resource-reconciliation-report", command="resource-reconciliation-report",
            summary="Read a job's retained ownership and missing clearance evidence without releasing resources.",
            fields=(FieldSpec("job_id", required=True),),
        ), ActionSpec(
            id="workbench.resource-reconcile", title="Reconcile committed resource release", group="workbench",
            backend="resource-reconcile", command="resource-reconcile", mutating=True,
            summary="Repair stale reservations only from an already committed same-attempt terminal local clearance receipt. Unknown work remains reserved.",
            fields=(FieldSpec("job_id", required=True),),
        ), ActionSpec(
            id="workbench.export-project-source-zip", title="Download project source ZIP", group="workbench",
            backend="project-source-archive", command="project-source-archive", long_running=True,
            admission=VerbAdmission(mutating=False, long_running=True, identity_scope="", read_only=True,
                snapshot="none", output_scope="none", drains_on_pause=True, boots_analyzer=False,
                lane="source-archive", budget_class="medium", cancel="sigterm"),
            summary="Package existing source and assembly for every recorded project member, with explicit coverage gaps. Does not regenerate, compile or verify source.",
            fields=(FieldSpec("project_id", required=True), FieldSpec("corpus_identity", required=True), FieldSpec("locator", from_context="locator")),
        ), ActionSpec(
            id="workbench.export-source-zip", title="Download binary source ZIP", group="workbench",
            backend="source-archive", command="source-archive", long_running=True,
            summary="Export whole-program decompiled C and available source witnesses with an inventory and coverage manifest. Compilation and byte verification remain separate.",
            fields=(FieldSpec("slug", required=True, from_context="slug"), FieldSpec("locator", from_context="locator"), FieldSpec("program", from_context="program")),
        ), ActionSpec(
            id="workbench.commit-signatures", title="Commit similarity signatures", group="workbench",
            backend="bsim-cli", command="commitsigs", mutating=True, danger=True, long_running=True,
            summary="Import generated BSim signature XML without opening a Ghidra project.",
            fields=(FieldSpec("bsimUrl", required=True), FieldSpec("signatureDirectory", kind="path", required=True)),
        ), ActionSpec(
            id="workbench.match-candidate", title="Compile and verify candidate", group="workbench",
            backend="matching", command="match-candidate", danger=True, long_running=True,
            summary="Compile one source draft with an operator-owned preset and compare its object with objdiff. Job completion or compile success alone is not byte proof.",
            fields=(
                FieldSpec("artifactHash", required=True, from_context="artifactHash"),
                FieldSpec("targetRevision", required=True),
                FieldSpec("function", required=True, from_context="name"),
                FieldSpec("candidateSource", required=True, schema={"maxLength": 2 * 1024 * 1024}),
                FieldSpec("compilerPreset", required=True),
            ),
        )]
        from agentdecompile_recovery.corpus import cli as corpus_cli
        parser_stat = Path(corpus_cli.__file__).resolve().stat()
        list_actions._parser_stamp = (parser_stat.st_dev, parser_stat.st_ino,
                                      parser_stat.st_size, parser_stat.st_mtime_ns)
        catalog_stat = Path(__file__).resolve().stat()
        list_actions._catalog_stamp = (catalog_stat.st_dev, catalog_stat.st_ino,
                                       catalog_stat.st_size, catalog_stat.st_mtime_ns)
    # Qualify the report's receipt-only behavior at the catalog declaration,
    # including a catalog populated before a function hot reload.
    from dataclasses import replace
    report_admission = VerbAdmission(
        mutating=False, long_running=False, identity_scope="", read_only=True,
        snapshot="none", output_scope="none", drains_on_pause=True,
        boots_analyzer=False, lane="admission", budget_class="micro", cancel="never",
    )
    return [replace(action, admission=report_admission)
            if action.backend == "resource-reconciliation-report" and action.admission != report_admission
            else action for action in _ACTIONS]


def action_by_id(action_id: str) -> ActionSpec | None:
    for action in list_actions():
        if action.id == action_id:
            return action
    return None


def env_defaults(*, root: Path | None = None, db: Path | None = None) -> dict[str, str]:
    if root is None:
        db = live_db() if db is None else db
        project_root = runtime_project_root()
        work_dir = runtime_work_dir()
    else:
        project_root = root
        if db is not None and db.parent.name == 'db' and (db.parent.parent / 'corpus_work').is_dir():
            project_root = db.parent.parent
        work_dir = project_root / 'corpus_work' if (project_root / 'corpus_work').is_dir() else project_root
    kb = KNOWLEDGE_DB
    if db is not None:
        sibling_knowledge = db.parent / "ghidra_knowledge.sqlite"
        if sibling_knowledge.is_file():
            kb = sibling_knowledge
    if kb is None:
        ghidra_kb = os.environ.get("AGENT_DECOMPILE_GHIDRA_KNOWLEDGE_DB", "").strip()
        if ghidra_kb:
            kb = Path(ghidra_kb).expanduser()
        elif project_root is not None:
            kb = project_root / "ghidra_knowledge.sqlite"
        else:
            kb = Path("ghidra_knowledge.sqlite")
    mcp = (
        os.environ.get("AGENT_DECOMPILE_MCP_URL")
        or os.environ.get("AGENT_DECOMPILE_MCP_SERVER_URL")
        or os.environ.get("AGENTDECOMPILE_MCP_SERVER_URL")
        or f"http://127.0.0.1:{os.environ.get('AGENT_DECOMPILE_PORT', '8080')}/mcp"
    )
    return {
        "db": str(db) if db else "",
        "work_dir": str(work_dir) if work_dir else "",
        "report_file": str(project_root / "recovery-report.json") if project_root else "",
        "kb": str(kb) if kb else "",
        "mcp_url": mcp,
    }


def apply_defaults(action: ActionSpec, params: dict[str, Any], context: dict[str, Any] | None = None, *, defaults: dict[str, str] | None = None, db: Path | None = None) -> dict[str, Any]:
    """Fill empty fields from page context and corpus environment."""
    merged = dict(params)
    if action.backend == "mcp-cli":
        from agentdecompile_cli.registry import normalize_identifier
        canonical = {normalize_identifier(spec.name): spec.name for spec in action.fields}
        for key, value in params.items():
            target = canonical.get(normalize_identifier(key))
            if target and target != key:
                merged.pop(key, None)
                if target not in params:
                    merged[target] = value
    ctx = dict(env_defaults() if defaults is None else defaults)
    if context:
        for key, value in context.items():
            if value not in (None, ""):
                ctx[key] = value
    # A slug is a display identifier, not a pipeline program path. Resolve it
    # from the active corpus before filling action fields, so every dashboard
    # entry point receives the same target instead of guessing from UI state.
    if ctx.get("slug") and not (ctx.get("program") or ctx.get("repo")):
        rows, _ = query_db(
            "SELECT repo_path FROM binary WHERE slug=? LIMIT 1", (str(ctx["slug"]),),
            ignore_missing=True,
            db=db,
        )
        if rows and rows[0][0]:
            ctx["program"] = str(rows[0][0])
            ctx["repo"] = str(rows[0][0])
    alias = {
        "program": ctx.get("program") or ctx.get("slug") or ctx.get("repo") or "",
        "slug": ctx.get("slug") or "",
        "addr": ctx.get("addr") or ctx.get("address") or "",
        "name": ctx.get("name") or "",
        "repo": ctx.get("repo") or ctx.get("program") or ctx.get("slug") or "",
        "db": ctx.get("db") or "",
        "work_dir": ctx.get("work_dir") or ctx.get("out_dir") or "",
        "kb": ctx.get("kb") or "",
        "report_file": ctx.get("report_file") or "",
    }
    for spec in action.fields:
        current = merged.get(spec.name)
        if current not in (None, ""):
            continue
        if spec.default not in (None, "", False, True, [], ()):
            merged[spec.name] = spec.default
            continue
        key = spec.from_context
        if key and alias.get(key):
            merged[spec.name] = alias[key]
    if ctx.get("locator"):
        merged["locator"] = ctx["locator"]
    _rewrite_file_binary_params(action, merged, ctx)
    _drop_shared_fs_project(merged)
    return merged


def _drop_shared_fs_project(merged: dict[str, Any]) -> None:
    """shared-fs repos folders are not --project for reconstruct."""
    raw = str(merged.get("project") or "").strip()
    if not raw or raw.startswith("ghidra://") or raw.lower().endswith(".gpr"):
        return
    path = Path(raw)
    if not path.is_dir():
        return
    if (path / "~index.dat").is_file() or (path / "idata").is_dir() or (path / "data").is_dir():
        return
    merged.pop("project", None)
    merged.pop("project-program", None)


def _rewrite_file_binary_params(
    action: ActionSpec, merged: dict[str, Any], ctx: dict[str, Any]
) -> None:
    """Shared-fs locators are directories. File verbs need the program PE."""
    program = str(ctx.get("program") or merged.get("program") or merged.get("from") or "").strip()
    work_dir = str(ctx.get("work_dir") or merged.get("work-dir") or merged.get("out-dir") or "").strip()
    locator = str(
        ctx.get("locator")
        or ctx.get("repo")
        or merged.get("repository")
        or merged.get("repo")
        or ""
    ).strip()
    resolved = _resolve_program_file(program, work_dir, locator)
    locator_name = Path(locator).name if locator else ""
    for spec in action.fields:
        if spec.name not in FILE_BINARY_FIELDS:
            continue
        current = merged.get(spec.name)
        path = Path(str(current)) if current not in (None, "") else None
        if path is not None and path.is_file():
            continue
        if resolved is not None:
            merged[spec.name] = str(resolved)
        elif path is not None and path.is_dir():
            # Keep the directory so validate_params can name it; do not invent a path.
            pass
    if action.id == "corpus.extract-stabs":
        ident = str(merged.get("id") or "").strip()
        if program and (not ident or ident == locator_name):
            merged["id"] = program


def _resolve_program_file(program: str, work_dir: str, locator: str) -> Path | None:
    name = (program or "").strip()
    if not name:
        return None
    roots: list[Path] = []
    if work_dir:
        roots.append(Path(work_dir) / "imports")
        roots.append(Path(work_dir))
    if locator:
        loc = Path(locator)
        if loc.is_dir():
            roots.append(loc)
    suffix = "__" + name
    for root in roots:
        exact = root / name
        if exact.is_file():
            return exact
        if not root.is_dir():
            continue
        try:
            children = list(root.iterdir())
        except OSError:
            continue
        for child in children:
            if not child.is_file():
                continue
            if child.name == name or child.name.endswith(suffix):
                return child
    return None


def validate_params(action: ActionSpec, params: dict[str, Any], *, confirm: bool = False) -> list[str]:
    errors: list[str] = []
    if action.danger and not confirm:
        errors.append(f"{action.id} changes program or corpus state; set confirm=true to run it")
    for spec in action.fields:
        value = params.get(spec.name)
        if spec.required and value in (None, "", False):
            errors.append(f"{spec.name} is required")
            continue
        if value in (None, ""):
            continue
        if spec.choices and str(value) not in spec.choices:
            errors.append(f"{spec.name} must be one of {', '.join(spec.choices)}")
        if spec.kind == "array" and not isinstance(value, list):
            errors.append(f"{spec.name} must be a JSON array")
        if spec.kind == "object" and not isinstance(value, dict):
            errors.append(f"{spec.name} must be a JSON object")
        if spec.kind == "int":
            try:
                int(value)
            except (TypeError, ValueError):
                errors.append(f"{spec.name} must be an integer")
        if spec.kind == "float":
            try:
                float(value)
            except (TypeError, ValueError):
                errors.append(f"{spec.name} must be a number")
        if spec.kind == "path" and "\x00" in str(value):
            errors.append(f"{spec.name} is not a usable path")
        if spec.name in FILE_BINARY_FIELDS and spec.kind == "path":
            try:
                as_path = Path(str(value))
            except (TypeError, ValueError):
                as_path = None
            if as_path is not None and as_path.is_dir():
                errors.append(
                    f"{spec.name} is a directory ({as_path}); pass the program PE "
                    "or Ghidra program file, not the shared-fs repos folder"
                )
        if spec.name in DANGEROUS_CORPUS and value not in (None, "", False) and not confirm:
            errors.append(f"{spec.name} is a destructive option; set confirm=true")
    argv_val = params.get("argv")
    if argv_val not in (None, ""):
        for token in shlex.split(str(argv_val)):
            flag = token.split("=", 1)[0]
            if flag in DANGEROUS_ARGV_FLAGS and not confirm:
                errors.append("argv contains destructive flags; set confirm=true")
                break
    if action.backend == "corpus-cli" and action.command == "verify-byteexact":
        from agentdecompile_recovery.corpus.verification_selection import validate_selection

        errors.extend(validate_selection(candidate=params.get("candidate"),
                                         offset=params.get("offset"), limit=params.get("limit")))
    return errors


def _cli_entry(script: str, dotted: str) -> list[str]:
    """Run this tree's package through the dashboard interpreter.

    ``shutil.which`` would pick ``~/.local/bin`` and skip workspace fixes.
    """
    module, name = dotted.split(":")
    return [
        sys.executable,
        "-c",
        (
            "import sys;"
            f"from {module} import {name} as _entry;"
            "sys.argv = [sys.argv[0]] + sys.argv[1:];"
            "raise SystemExit(_entry() if _entry.__code__.co_argcount == 0 "
            "else _entry(sys.argv[1:]))"
        ),
    ]


def _module_launcher(module: str) -> list[str]:
    return _cli_entry(
        {
            "agentdecompile_recovery.corpus.cli": "agentdecompile-corpus",
            "agentdecompile_recovery.frontdoor": "agentdecompile-reconstruct",
            "agentdecompile_recovery.cli": "agentdecompile-recover",
        }.get(module, module),
        f"{module}:main",
    )


def build_command(action: ActionSpec, params: dict[str, Any]) -> list[str]:
    """Return the exact argv that will run. Never interpolates a shell string."""
    if action.backend == "bsim-cli":
        from agentdecompile_recovery.corpus.bsim_ops import find_bsim_launcher
        launcher = find_bsim_launcher()
        if launcher is None:
            raise ValueError("Ghidra support/bsim not found; configure GHIDRA_INSTALL_DIR")
        return [str(launcher), "commitsigs", str(params["bsimUrl"]), str(params["signatureDirectory"])]
    if action.backend in {"workflow-control", "activity-snapshot", "merge-evidence", "source-archive", "project-source-archive", "matching", "resource-reconciliation-report", "resource-reconcile", "match-review"}:
        return [action.id]
    if action.backend == "preparation":
        return ["workbench.prepare"]
    if action.backend == "mcp-cli":
        arguments = {
            spec.name: params[spec.name]
            for spec in action.fields
            if spec.name in params and params[spec.name] not in (None, "")
        }
        # Dashboard jobs use jobs._mcp_executor, which calls the live MCP
        # handler directly.  Keep the durable receipt truthful without
        # advertising a CLI wrapper that the runner never executes.
        return ["mcp", action.command, json.dumps(arguments, separators=(",", ":"))]

    if action.backend == "corpus-cli":
        argv = [*_module_launcher("agentdecompile_recovery.corpus.cli"), action.command]
    elif action.backend == "recover-cli":
        argv = [*_module_launcher("agentdecompile_recovery.cli"), action.command]
    elif action.backend == "reconstruct-cli":
        argv = [*_module_launcher("agentdecompile_recovery.frontdoor")]
        if action.command:
            argv.append(action.command)
    elif action.backend == "click-cli":
        argv = [*_cli_entry("agentdecompile-cli", "agentdecompile_cli.cli:cli_entry_point")]
        if action.command:
            argv.append(action.command)
    else:
        raise ValueError(f"unknown backend {action.backend}")

    extra: list[str] = []
    for spec in action.fields:
        value = params.get(spec.name)
        if value in (None, ""):
            continue
        if spec.name == "argv":
            extra = shlex.split(str(value))
            continue
        if spec.kind == "bool":
            if value in (True, "true", "1", "yes", "on"):
                argv.append(spec.flag or f"--{spec.name}")
            elif spec.default is True:
                # argparse.BooleanOptionalAction options defaulting to true
                # need their explicit negative spelling.  Omitting the option
                # would silently leave them enabled, while serializing False
                # as a value lets argparse consume it as a positional argument.
                positive_flag = spec.flag or f"--{spec.name}"
                if positive_flag.startswith("--"):
                    argv.append(f"--no-{positive_flag[2:]}")
            continue
        if spec.positional:
            if spec.kind == "array":
                argv.extend(str(item) for item in value)
            else:
                argv.append(str(value))
            continue
        if spec.kind == "array":
            for item in value:
                argv.extend([spec.flag or f"--{spec.name}", str(item)])
            continue
        argv.extend([spec.flag or f"--{spec.name}", str(value)])
    argv.extend(extra)
    return argv
