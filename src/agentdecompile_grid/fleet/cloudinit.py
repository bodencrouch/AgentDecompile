"""Render user-data whose only step is the identical join command with a fleet invite.

Templates are data: a ``#cloud-config`` document as a dict (``CLOUD_CONFIG_TEMPLATE``) and a
``bash`` bootstrap as text (``BASH_TEMPLATE``), both with ``$variable`` placeholders substituted
into every string leaf (``string.Template``; nothing else is interpolated, every value is
shell-quoted).  The invite travels in the environment (``ADGRID_INVITE=...``), never in argv,
so it does not show in ``ps`` on the rendered host; the join command reads it from there.

The cloud-config YAML is emitted by a small emitter for exactly the shapes the template uses
(maps, lists, scalars) so no YAML library is needed; strings are JSON-quoted, which YAML accepts.

Acceptance tests named for the final verification phase (U129):
  * ``test_user_data_single_step``: ``render_user_data`` yields ``#cloud-config`` whose
    ``runcmd`` has exactly one entry and that entry contains the join command; ``validate``
    refuses a template with two steps by name.
  * ``test_invite_not_in_argv``: the rendered command passes the invite through the environment
    and the argv of ``sh -s`` carries only flags.
  * ``test_bash_bootstrap_equivalent``: the bash rendering runs the same join command as the
    cloud-config rendering for the same arguments.
  * ``test_variables_quoted``: an invite url or lane name with shell metacharacters renders
    quoted and the command still has one step.
"""
from __future__ import annotations

import json
import shlex
from string import Template
from typing import Any, Mapping, Sequence

from .. import __version__
from ..core import GridError
from ..worker.identity import ROLES, split_fabric_url

DEFAULT_PACKAGE_SPEC = f"agentdecompile-grid=={__version__}"
FORMATS = ("cloud-config", "bash")
INSTALLERS = ("curl", "uvx")

CLOUD_CONFIG_TEMPLATE: Mapping[str, Any] = {
    "runcmd": ["$join_command"],       # string form: cloud-init runs it from its runcmd script, so the env assignment never lands in any argv
}

BASH_TEMPLATE = """#!/bin/sh
# adgrid fleet bootstrap — the only step is the join command (design §1.4).
set -eu
$join_command
"""


class TemplateError(GridError):
    """The template does not render to a single join step."""


def join_command(invite_url: str, *, role: str = "fleet", lanes: Sequence[str] = (), cores: int | None = None, idle_only: bool = False, installer: str = "curl",
                 join_sh_url: str | None = None, package_spec: str = DEFAULT_PACKAGE_SPEC, extra_flags: Sequence[str] = (), invite_via: str = "env") -> str:
    """The one command every donor class runs (design §1.3), with the invite in the environment."""
    if role not in ROLES:
        raise TemplateError(f"unknown role {role!r}; known: {ROLES}")
    if installer not in INSTALLERS:
        raise TemplateError(f"unknown installer {installer!r}; known: {INSTALLERS}")
    if invite_via not in ("env", "argv"):
        raise TemplateError("invite_via must be env or argv")
    fabric_url, _ = split_fabric_url(invite_url)
    flags: list[str] = ["--role", role]
    if lanes:
        flags += ["--lanes", ",".join(lanes)]
    if cores is not None:
        flags += ["--cores", str(int(cores))]
    if idle_only:
        flags.append("--idle-only")
    flags += list(extra_flags)
    quoted_flags = " ".join(shlex.quote(f) for f in flags)
    argv_invite = f" {shlex.quote(invite_url)}" if invite_via == "argv" else ""
    env_prefix = f"ADGRID_INVITE={shlex.quote(invite_url)} " if invite_via == "env" else ""
    if installer == "curl":
        script_url = join_sh_url or f"{fabric_url.rsplit('/g/', 1)[0]}/join.sh"
        return f"{env_prefix}sh -c {shlex.quote(f'curl -fsSL {shlex.quote(script_url)} | sh -s --{argv_invite} {quoted_flags}')}"
    return f"{env_prefix}uvx {shlex.quote(package_spec)} join{argv_invite} {quoted_flags}"


def substitute(template: Any, variables: Mapping[str, str]) -> Any:
    """Substitute ``$name`` placeholders in every string leaf; unknown names are an error by name."""
    if isinstance(template, str):
        try:
            return Template(template).substitute(variables)
        except KeyError as exc:
            raise TemplateError(f"template names an unknown variable {exc.args[0]!r}; known: {sorted(variables)}") from exc
    if isinstance(template, Mapping):
        return {str(k): substitute(v, variables) for k, v in template.items()}
    if isinstance(template, (list, tuple)):
        return [substitute(v, variables) for v in template]
    return template


def emit_yaml(value: Any, indent: int = 0) -> str:
    """A YAML emitter for maps, lists and scalars (strings JSON-quoted)."""
    pad = " " * indent
    if isinstance(value, Mapping):
        if not value:
            return f"{pad}{{}}\n"
        out = []
        for k, v in value.items():
            key = json.dumps(str(k))
            if isinstance(v, (Mapping, list, tuple)) and v:
                out.append(f"{pad}{key}:\n{emit_yaml(v, indent + 2)}")
            else:
                out.append(f"{pad}{key}: {_scalar(v)}\n")
        return "".join(out)
    if isinstance(value, (list, tuple)):
        if not value:
            return f"{pad}[]\n"
        out = []
        for v in value:
            if isinstance(v, (Mapping, list, tuple)) and v:
                nested = emit_yaml(v, indent + 2)
                out.append(f"{pad}- {nested[indent + 2:]}")
            else:
                out.append(f"{pad}- {_scalar(v)}\n")
        return "".join(out)
    return f"{pad}{_scalar(value)}\n"


def _scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return json.dumps(value)
    if isinstance(value, (Mapping, list, tuple)) and not value:
        return "{}" if isinstance(value, Mapping) else "[]"
    return json.dumps(str(value), ensure_ascii=False)


def render_cloud_config(template: Mapping[str, Any], variables: Mapping[str, str]) -> str:
    rendered = substitute(template, variables)
    validate_cloud_config(rendered)
    return "#cloud-config\n" + emit_yaml(rendered)


def validate_cloud_config(rendered: Mapping[str, Any]) -> None:
    runcmd = rendered.get("runcmd")
    if not isinstance(runcmd, list) or len(runcmd) != 1:
        raise TemplateError(f"user-data must have exactly one runcmd step (the join command); got {len(runcmd) if isinstance(runcmd, list) else 'none'}")
    forbidden = [k for k in rendered if k in ("bootcmd", "users", "ssh_authorized_keys", "write_files")]
    if forbidden:
        raise TemplateError(f"user-data must not add steps beyond the join command: {forbidden}")


def render_user_data(invite_url: str, *, role: str = "fleet", lanes: Sequence[str] = (), cores: int | None = None, idle_only: bool = False, format: str = "cloud-config",
                     installer: str = "curl", join_sh_url: str | None = None, package_spec: str = DEFAULT_PACKAGE_SPEC, extra_flags: Sequence[str] = (),
                     template: Mapping[str, Any] | str | None = None, invite_via: str = "env") -> str:
    """User-data (cloud-config) or a plain bash bootstrap running the identical join command."""
    if format not in FORMATS:
        raise TemplateError(f"unknown user-data format {format!r}; known: {FORMATS}")
    command = join_command(invite_url, role=role, lanes=lanes, cores=cores, idle_only=idle_only, installer=installer, join_sh_url=join_sh_url, package_spec=package_spec, extra_flags=extra_flags, invite_via=invite_via)
    variables = {"join_command": command, "role": role, "lanes": ",".join(lanes), "package_spec": package_spec, "version": __version__}
    if format == "bash":
        text = template if isinstance(template, str) else BASH_TEMPLATE
        rendered = substitute(text, variables)
        if rendered.count("ADGRID_INVITE=" if invite_via == "env" else " join") < 1:
            raise TemplateError("bash template dropped the join command")
        return rendered
    if template is not None and not isinstance(template, Mapping):
        raise TemplateError("cloud-config template must be a mapping")
    return render_cloud_config(template or CLOUD_CONFIG_TEMPLATE, variables)


def is_cloud_config(user_data: str) -> bool:
    return user_data.lstrip().startswith("#cloud-config")


__all__ = ["BASH_TEMPLATE", "CLOUD_CONFIG_TEMPLATE", "DEFAULT_PACKAGE_SPEC", "FORMATS", "INSTALLERS", "TemplateError", "emit_yaml", "is_cloud_config", "join_command", "render_cloud_config", "render_user_data", "substitute", "validate_cloud_config"]
