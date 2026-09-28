"""Path helpers for corpus writers.

Every path defaults under ``./agentdecompile_projects`` (the same default
project root the server and CLI already use) so the corpus tooling works
out of the box. Callers pass a Path argument, or set the documented
environment variable, only to deviate from that default.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Default project root shared with the server/CLI ``agentdecompile_projects`` default.
DEFAULT_PROJECT_ROOT = Path("agentdecompile_projects")


class MissingCorpusPath(ValueError):
    """Raised when a corpus path was neither passed, configured, nor defaultable."""


def env_path(name: str) -> Path | None:
    value = (os.environ.get(name) or "").strip()
    return Path(value) if value else None


def require_env_path(name: str, default: Path | None = None) -> Path:
    path = env_path(name)
    if path is not None:
        return path
    if default is not None:
        return default
    raise MissingCorpusPath(f"{name} is required")


def project_workspace(*, path: Path | str | None = None) -> Path:
    if path is not None:
        return Path(path)
    return require_env_path("AGENT_DECOMPILE_PROJECT_PATH", DEFAULT_PROJECT_ROOT)


def corpus_db_path(*, path: Path | str | None = None) -> Path:
    if path is not None:
        return Path(path)
    return require_env_path("AGENT_DECOMPILE_CORPUS_DB", DEFAULT_PROJECT_ROOT / "corpus.db")


def corpus_work_dir(*, path: Path | str | None = None) -> Path:
    if path is not None:
        return Path(path)
    return require_env_path("AGENT_DECOMPILE_CORPUS_WORK_DIR", DEFAULT_PROJECT_ROOT / "corpus_work")


def external_recovery_root(*, path: Path | str | None = None) -> Path:
    if path is not None:
        return Path(path)
    return require_env_path("AGENT_DECOMPILE_EXTERNAL_RECOVERY_ROOT", DEFAULT_PROJECT_ROOT / "external_recovery")


def knowledge_db_path(*, path: Path | str | None = None) -> Path | None:
    if path is not None:
        return Path(path)
    return env_path("AGENT_DECOMPILE_GHIDRA_KNOWLEDGE_DB")


def recovered_source_root(*, path: Path | str | None = None) -> Path:
    if path is not None:
        return Path(path)
    return external_recovery_root() / "recovered-source"
