"""Expose the argparse recovery CLIs as ``agentdecompile-cli`` subcommands.

``agentdecompile-corpus`` and ``agentdecompile-recover`` stay the backing
implementation (the 8080 workbench catalog drives them). This module only
bridges them into Click:

* ``corpus`` / ``recover`` are lazy groups. The argparse module is imported
  when the group itself is invoked, never for ``agentdecompile-cli --help``.
* Every leaf forwards ``[verb, *args]`` untouched to the module's ``main`` so
  options such as ``--format``/``-f``/``--host``/``--port`` reach argparse.
* ``reconstruct`` and ``grid`` are flat passthrough leaves.

Register with :func:`register` after the root ``-f/--format`` walk, so the
walk never appends a Click option that would swallow forwarded tokens.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import sys
from typing import Any, Callable

import click

# Verbs that live in another group (or as another agentdecompile-cli command).
# They are not listed; invoking one prints the replacement and exits 2.
REDIRECTS: dict[str, dict[str, str]] = {
    "recover": {
        "list-archive": "corpus list-archive",
        "check-extraction": "corpus check-extraction",
    },
    "corpus": {},
}

_PASSTHROUGH_SETTINGS_BASE: dict[str, Any] = {
    "ignore_unknown_options": True,
    "allow_extra_args": True,
    "allow_interspersed_args": False,
}


def _run_embedded_cli(
    entrypoint: Callable[..., Any],
    args: tuple[str, ...] | list[str],
    *,
    prog: str | None = None,
) -> None:
    # Resolve at call time to avoid a circular import while cli.py registers
    # these commands at module import time.
    cli_module = importlib.import_module("agentdecompile_cli.cli")
    cli_module._run_embedded_cli(entrypoint, args, prog=prog)


def _identity_token(token: str) -> str:
    return token


def _token_normalizer() -> Callable[[str], str]:
    # Imported lazily: cli.py imports this module at its end, so a module-level
    # import of cli here would be circular when this module is imported first.
    cli_mod = sys.modules.get("agentdecompile_cli.cli")
    return getattr(cli_mod, "_identity_cli_token", _identity_token)


def _passthrough_settings() -> dict[str, Any]:
    return {**_PASSTHROUGH_SETTINGS_BASE, "token_normalize_func": _token_normalizer()}


def _mark(command: click.Command) -> click.Command:
    command.BRIDGED = True  # type: ignore[attr-defined]
    return command


def _subparsers_action(parser: argparse.ArgumentParser) -> argparse._SubParsersAction:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    raise RuntimeError(f"{parser.prog}: no subcommands")


def _build_parser(module: Any, prog: str) -> argparse.ArgumentParser:
    build = module.build_parser
    try:
        accepts_prog = "prog" in inspect.signature(build).parameters
    except (TypeError, ValueError):
        accepts_prog = False
    return build(prog=prog) if accepts_prog else build()


class LazyArgparseGroup(click.Group):
    """Click group whose leaves are the subparsers of an argparse ``build_parser``."""

    def __init__(self, name: str, module_name: str, **kwargs: Any) -> None:
        kwargs.setdefault("context_settings", {"token_normalize_func": _token_normalizer()})
        super().__init__(name=name, **kwargs)
        self.module_name = module_name
        self.redirects = REDIRECTS.get(name, {})
        self._verbs: dict[str, str] | None = None  # canonical verb -> short help
        self._all_verbs: set[str] = set()  # canonical verbs and aliases
        self.BRIDGED = True

    def _module(self) -> Any:
        return importlib.import_module(self.module_name)

    def _load(self) -> dict[str, str]:
        if self._verbs is None:
            parser = _build_parser(self._module(), f"agentdecompile-cli {self.name}")
            action = _subparsers_action(parser)
            helps = {choice.dest: choice.help or "" for choice in action._choices_actions}
            seen: set[int] = set()
            verbs: dict[str, str] = {}
            for verb, subparser in action.choices.items():
                self._all_verbs.add(verb)
                if id(subparser) in seen:
                    continue  # alias of a verb already listed
                seen.add(id(subparser))
                verbs[verb] = helps.get(verb, "")
            self._verbs = verbs
        return self._verbs

    def list_commands(self, ctx: click.Context) -> list[str]:
        return [verb for verb in self._load() if verb not in self.redirects]

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        if cmd_name in self.redirects:
            return _redirect_leaf(cmd_name, self.redirects[cmd_name])
        verbs = self._load()
        if cmd_name not in self._all_verbs:
            return None
        return _verb_leaf(self.module_name, self.name, cmd_name, verbs.get(cmd_name, ""))


def _verb_leaf(module_name: str, group: str, verb: str, short_help: str) -> click.Command:
    def _callback(args: tuple[str, ...]) -> None:
        # Resolve main at call time so patched entry points are honoured.
        entrypoint = importlib.import_module(module_name).main
        _run_embedded_cli(entrypoint, [verb, *args], prog=f"agentdecompile-cli {group}")

    command = click.Command(
        verb,
        callback=_callback,
        params=[click.Argument(["args"], nargs=-1, type=click.UNPROCESSED)],
        context_settings=_passthrough_settings(),
        add_help_option=False,
        help=short_help,
        short_help=short_help,
    )
    return _mark(command)


def _redirect_leaf(verb: str, replacement: str) -> click.Command:
    def _callback(args: tuple[str, ...]) -> None:
        click.echo(f"use: agentdecompile-cli {replacement}", err=True)
        raise SystemExit(2)

    command = click.Command(
        verb,
        callback=_callback,
        params=[click.Argument(["args"], nargs=-1, type=click.UNPROCESSED)],
        context_settings=_passthrough_settings(),
        add_help_option=False,
        hidden=True,
        help=f"Moved: use agentdecompile-cli {replacement}.",
    )
    return _mark(command)


def _flat_leaf(name: str, help_text: str, callback: Callable[[tuple[str, ...]], None]) -> click.Command:
    command = click.Command(
        name,
        callback=callback,
        params=[click.Argument(["args"], nargs=-1, type=click.UNPROCESSED)],
        context_settings=_passthrough_settings(),
        add_help_option=False,
        help=help_text,
    )
    return _mark(command)


def _reconstruct(args: tuple[str, ...]) -> None:
    from agentdecompile_recovery.frontdoor import main as reconstruct_main

    _run_embedded_cli(reconstruct_main, args)


def _grid(args: tuple[str, ...]) -> None:
    try:
        grid_cli = importlib.import_module("agentdecompile_grid.cli")
    except ImportError:
        click.echo("agentdecompile-cli grid: the agentdecompile_grid package is not installed", err=True)
        raise SystemExit(2) from None
    _run_embedded_cli(grid_cli.main, args)


def build_commands() -> list[click.Command]:
    corpus = LazyArgparseGroup(
        "corpus",
        "agentdecompile_recovery.corpus.cli",
        help="Corpus pipeline verbs (same as agentdecompile-corpus). Run `agentdecompile-cli corpus <verb> --help` for options.",
        short_help="Corpus pipeline verbs (agentdecompile-corpus).",
    )
    recover = LazyArgparseGroup(
        "recover",
        "agentdecompile_recovery.cli",
        help="Staged recovery verbs (same as agentdecompile-recover). Run `agentdecompile-cli recover <verb> --help` for options.",
        short_help="Staged recovery verbs (agentdecompile-recover).",
    )
    reconstruct = _flat_leaf(
        "reconstruct",
        "Run the integrated reconstruction front door. Pass arguments directly, for example `agentdecompile-cli reconstruct <binary>` or `agentdecompile-cli reconstruct self-check`.",
        _reconstruct,
    )
    grid = _flat_leaf(
        "grid",
        "Run the agentdecompile grid CLI (same as adgrid). All arguments are forwarded.",
        _grid,
    )
    return [corpus, recover, reconstruct, grid]


def register(root: click.Group) -> None:
    """Add the bridge commands to ``root``, replacing same-named entries."""
    for command in build_commands():
        root.add_command(command)
