"""One targeted-AI policy: server CLI > environment > dashboard > off.

Server exports preserve provenance; children inherit the decision at launch.
Use ``targeted_ai_environment`` at admission to snapshot at launch instead.
Changing a shell's environment cannot change an already running server: live
updates must update its process environment (or use the dashboard setting).
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, MutableMapping

AI_ENV = "AGENT_DECOMPILE_TARGETED_AI_ENABLED"
_STATE_ENV = "AGENT_DECOMPILE_TARGETED_AI_STATE"
WORK_DIR_ENV = "AGENT_DECOMPILE_CORPUS_WORK_DIR"
ROOT_ENV = "AGENT_DECOMPILE_CORPUS_ROOT"
_POLICY_LOCK = threading.RLock()


class TargetedAIConfigError(ValueError):
    """Invalid AI configuration; callers must not proceed with AI enabled."""


@dataclass(frozen=True)
class TargetedAIState:
    enabled: bool
    source: str


_JOB_STATE: ContextVar[TargetedAIState | None] = ContextVar("targeted_ai_job", default=None)


@contextmanager
def targeted_ai_job(state: TargetedAIState | None = None):
    """Capture one policy for synchronous job work; nested jobs retain it."""
    captured = _JOB_STATE.get() or state or resolve_targeted_ai()
    token = _JOB_STATE.set(captured)
    try:
        yield captured
    finally:
        _JOB_STATE.reset(token)


def _boolean(value: object, source: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise TargetedAIConfigError(f"{source} must be true/false, yes/no, on/off or 1/0; targeted AI was not enabled.")


def _settings_path(work_dir: str | Path | None, environ: Mapping[str, str]) -> Path | None:
    raw = work_dir if work_dir is not None else (environ.get(ROOT_ENV, "").strip() or environ.get(WORK_DIR_ENV, "").strip())
    return Path(raw).expanduser() / "ai-settings.json" if raw else None


def read_targeted_ai_settings(work_dir: str | Path | None = None, *, environ: Mapping[str, str] | None = None) -> dict[str, bool]:
    """Read fresh; missing settings mean default off, malformed settings fail closed."""
    path = _settings_path(work_dir, os.environ if environ is None else environ)
    if path is None:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TargetedAIConfigError(f"Cannot read AI settings at {path}: {exc}. Repair the file or save a valid dashboard setting.") from exc
    if not isinstance(data, dict) or type(data.get("enabled")) is not bool:
        raise TargetedAIConfigError(f"AI settings at {path} must contain an enabled boolean; save true or false through the dashboard.")
    return {"enabled": data["enabled"]}


def write_targeted_ai_settings(enabled: bool, work_dir: str | Path | None = None) -> None:
    """Replace settings atomically so readers never see a partially written file."""
    if type(enabled) is not bool:
        raise TargetedAIConfigError("Dashboard AI setting 'enabled' must be a JSON boolean.")
    path = _settings_path(work_dir, os.environ)
    if path is None:
        raise TargetedAIConfigError(f"Set {WORK_DIR_ENV} before saving dashboard AI settings.")
    temporary: str | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=".ai-settings-", delete=False) as stream:
            temporary = stream.name
            json.dump({"enabled": enabled}, stream)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError as exc:
        raise TargetedAIConfigError(f"Cannot save AI settings at {path}: {exc}") from exc
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


def _provenance(environ: Mapping[str, str]) -> dict:
    raw = environ.get(_STATE_ENV)
    if not raw:
        return {}
    try:
        state = json.loads(raw)
        if (not isinstance(state, dict) or type(state.get("owner_pid")) is not int
                or type(state.get("enabled")) is not bool
                or state.get("source") not in {"cli", "env", "dashboard", "default"}
                or state.get("kind") not in {"server", "snapshot"}):
            raise ValueError("invalid provenance fields")
        return state
    except (ValueError, TypeError) as exc:
        raise TargetedAIConfigError(f"Invalid {_STATE_ENV}; remove the stale provenance and configure targeted AI again.") from exc


def _export(environ: MutableMapping[str, str], state: TargetedAIState, kind: str) -> None:
    with _POLICY_LOCK:
        environ[AI_ENV] = "1" if state.enabled else "0"
        # This single record is the child launch decision. A child never mixes
        # its fields with a dashboard file or a second environment value.
        environ[_STATE_ENV] = json.dumps({"owner_pid": os.getpid(), "enabled": state.enabled, "source": state.source, "kind": kind})


def resolve_targeted_ai(*, cli_enabled: bool | None = None, environ: Mapping[str, str] | None = None, work_dir: str | Path | None = None) -> TargetedAIState:
    with _POLICY_LOCK:
        return _resolve_targeted_ai(cli_enabled=cli_enabled, environ=environ, work_dir=work_dir)


def _resolve_targeted_ai(*, cli_enabled: bool | None = None, environ: Mapping[str, str] | None = None, work_dir: str | Path | None = None) -> TargetedAIState:
    """Resolve policy without allowing a generated env value to mask settings.

    A child inherits the encoded server decision at launch even if first policy
    use occurs later. Dashboard writes refresh that record for future children.
    """
    env = os.environ if environ is None else environ
    if cli_enabled is not None:
        if type(cli_enabled) is not bool:
            raise TargetedAIConfigError("Targeted AI CLI override must be a boolean.")
        return TargetedAIState(cli_enabled, "cli")
    captured = _JOB_STATE.get()
    if captured is not None and environ is None and work_dir is None:
        return captured
    previous = _provenance(env)
    if previous and previous["owner_pid"] != os.getpid():
        result = TargetedAIState(previous["enabled"], previous["source"])
        if environ is None:
            _export(os.environ, result, "snapshot")
        return result
    if previous.get("kind") == "snapshot" or previous.get("source") == "cli":
        return TargetedAIState(previous["enabled"], previous["source"])
    raw = env.get(AI_ENV)
    synthetic = previous and raw == ("1" if previous["enabled"] else "0") and previous["source"] != "env"
    if raw is not None and not synthetic:
        result = TargetedAIState(_boolean(raw, AI_ENV), "env")
    else:
        dashboard = read_targeted_ai_settings(work_dir, environ=env)
        result = TargetedAIState(dashboard["enabled"], "dashboard") if dashboard else TargetedAIState(False, "default")
    return result


def configure_targeted_ai(cli_enabled: bool | None = None) -> TargetedAIState:
    """Called once by either server entry point, before child work can start."""
    state = resolve_targeted_ai(cli_enabled=cli_enabled)
    _export(os.environ, state, "server")
    return state


def save_targeted_ai_settings(enabled: bool) -> TargetedAIState:
    """Save and publish the future-job decision without changing active scopes."""
    with _POLICY_LOCK:
        write_targeted_ai_settings(enabled)
        state = _resolve_targeted_ai(environ=os.environ)
        _export(os.environ, state, "server")
        return state


def targeted_ai_environment(environ: Mapping[str, str] | None = None, *, work_dir: str | Path | None = None) -> dict[str, str]:
    """Return a fresh child environment containing an immutable policy snapshot."""
    result = dict(os.environ if environ is None else environ)
    state = resolve_targeted_ai(work_dir=work_dir) if environ is None else resolve_targeted_ai(environ=result, work_dir=work_dir)
    _export(result, state, "snapshot")
    return result
