"""Shared helpers for the corpus dashboard.

ROOT and DB_PATH come from AgentDecompile environment variables when set,
falling back to the same ``./agentdecompile_projects`` default as the rest
of the corpus tooling (see ``corpus_env``). There is no kotorxid repo
default and no db/kotorxid.sqlite fallback.
"""

from __future__ import annotations

import html
import json
import os
import socket
import sqlite3
import time
from pathlib import Path

from .. import corpus_env as _corpus_env

_UNSET_ROOT = _corpus_env.corpus_work_dir()
_UNSET_EXTERNAL = _corpus_env.external_recovery_root()


def _env_root() -> Path | None:
    raw = (
        os.environ.get("AGENT_DECOMPILE_CORPUS_ROOT")
        or os.environ.get("AGENT_DECOMPILE_CORPUS_WORK_DIR")
        or ""
    ).strip()
    if not raw or "\x00" in raw:
        return None
    try:
        return Path(raw).expanduser()
    except (OSError, RuntimeError, ValueError):
        return None


def _env_path_optional(name: str) -> Path | None:
    raw = os.environ.get(name)
    if raw is None or not raw.strip() or "\x00" in raw:
        return None
    try:
        path = Path(raw.strip()).expanduser()
    except (OSError, RuntimeError, ValueError):
        return None
    if path.is_absolute():
        return path
    root = _env_root()
    return (root / path) if root is not None else path


def _env_host(name: str, default: str) -> str:
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = raw.strip()
    if not value or any(ord(char) < 32 for char in value):
        return default
    return value


def _env_port(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        value = int(str(raw).strip(), 10)
    except (AttributeError, TypeError, ValueError):
        return default
    return value if 1 <= value <= 65535 else default


def _env_paths(name: str, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        values = json.loads(raw)
    except (TypeError, ValueError):
        return default
    if not isinstance(values, list):
        return default
    out = []
    for value in values:
        if not isinstance(value, str):
            return default
        value = value.strip()
        if not value or "\x00" in value:
            return default
        out.append(value)
    return tuple(dict.fromkeys(out))


ROOT = _env_root() or _corpus_env.corpus_work_dir()
DB_PATH = _env_path_optional("AGENT_DECOMPILE_CORPUS_DB") or _corpus_env.corpus_db_path()
KNOWLEDGE_DB = _env_path_optional("AGENT_DECOMPILE_KNOWLEDGE_DB")
MIZUCHI_R = _env_path_optional("AGENT_DECOMPILE_EXTERNAL_RECOVERY_ROOT") or _corpus_env.external_recovery_root()
GHIDRA_SERVER_HOST = _env_host("AGENT_DECOMPILE_GHIDRA_SERVER_HOST", "127.0.0.1")
GHIDRA_SERVER_PORT = _env_port("AGENT_DECOMPILE_GHIDRA_SERVER_PORT", 0)
DRM_EXCLUDED = _env_paths("AGENT_DECOMPILE_EXCLUDED_REPO_PATHS", ())
_DEFAULT_DRM_EXCLUDED = ()


def live_root() -> Path | None:
    return _env_root() or ROOT


_RUNTIME_DB_PATH: Path | None = None


def _runtime_db_selection_path() -> Path | None:
    root = live_root()
    return root / "workbench-corpus-db.json" if root is not None else None


def _saved_runtime_db_path() -> Path | None:
    path = _runtime_db_selection_path()
    if path is None or not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get("path")
        candidate = Path(str(value)).expanduser()
        return candidate if candidate.is_file() else None
    except (OSError, TypeError, ValueError):
        return None


def set_runtime_db_path(path: Path | str | None) -> None:
    """Select a corpus db for this running server, overriding env/default.

    Used by the frontend's "pick an existing db" flow when no db exists at
    the env-var/default location yet.
    """
    global _RUNTIME_DB_PATH
    _RUNTIME_DB_PATH = Path(path).expanduser() if path else None
    selection = _runtime_db_selection_path()
    if selection is None:
        return
    try:
        if _RUNTIME_DB_PATH is None:
            selection.unlink(missing_ok=True)
        else:
            temporary = selection.with_suffix(".tmp")
            temporary.write_text(json.dumps({"path": str(_RUNTIME_DB_PATH)}), encoding="utf-8")
            temporary.replace(selection)
    except OSError:
        # The active in-memory selection remains valid even if its workspace
        # cannot retain a preference across a server restart.
        pass


def find_candidate_dbs() -> list[Path]:
    """Scan conventional locations for an existing corpus sqlite file."""
    seen: dict[str, Path] = {}
    search_dirs = [Path("agentdecompile_projects"), Path.cwd(), Path.home() / "agentdecompile_projects"]
    for directory in search_dirs:
        try:
            if not directory.is_dir():
                continue
            for pattern in ("*.db", "*.sqlite", "*.sqlite3"):
                for candidate in directory.glob(pattern):
                    if candidate.is_file():
                        seen.setdefault(str(candidate.resolve()), candidate)
        except OSError:
            continue
    return sorted(seen.values(), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)


def live_db() -> Path | None:
    if _RUNTIME_DB_PATH is not None:
        return _RUNTIME_DB_PATH
    saved = _saved_runtime_db_path()
    if saved is not None:
        return saved
    return _env_path_optional("AGENT_DECOMPILE_CORPUS_DB") or DB_PATH


def runtime_project_root() -> Path | None:
    """Return the project owning the selected runtime database when known."""
    database = live_db()
    if database is not None and database.parent.name == "db":
        candidate = database.parent.parent
        if (candidate / "corpus_work").is_dir():
            return candidate
    return live_root()


def runtime_work_dir() -> Path | None:
    """Return the recovery workspace paired with the selected runtime db."""
    project = runtime_project_root()
    if project is not None and (project / "corpus_work").is_dir():
        return project / "corpus_work"
    return project


def as_root() -> Path:
    """Join target for artifact paths. Never a kotorxid checkout default."""
    return live_root() or ROOT or _UNSET_ROOT


def as_external() -> Path:
    current = _env_path_optional("AGENT_DECOMPILE_EXTERNAL_RECOVERY_ROOT")
    return current or MIZUCHI_R or _UNSET_EXTERNAL


def esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def fnum(value) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "-"


def fpct(part, whole) -> str:
    try:
        part, whole = float(part), float(whole)
    except (TypeError, ValueError):
        return "-"
    if whole <= 0:
        return "-"
    return f"{part / whole * 100:.2f}%"


def parse_address(value):
    """Parse an address from a route, query string, or database value.

    Canonical URLs use ``0x``-prefixed hexadecimal.  Older dashboard links
    emitted zero-padded 8- or 16-character hexadecimal without the prefix, so
    those forms remain accepted.  Short digit-only strings are decimal for
    query-string compatibility; other hexadecimal strings must contain an
    ``a``-``f`` digit or carry the prefix.
    """
    if value is None:
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    text = str(value).strip().lower().replace("_", "")
    if not text:
        return None
    try:
        if text.startswith("0x"):
            parsed = int(text[2:], 16)
        elif len(text) in (8, 16) and all(c in "0123456789abcdef" for c in text):
            parsed = int(text, 16)
        elif text.isdigit():
            parsed = int(text, 10)
        elif all(c in "0123456789abcdef" for c in text):
            parsed = int(text, 16)
        else:
            return None
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def format_address(value, bits=32) -> str:
    """Return the one unambiguous address spelling used by dashboard URLs."""
    parsed = parse_address(value)
    if parsed is None:
        return "?"
    width = 16 if (bits or 32) > 32 else 8
    return f"0x{parsed:0{width}x}"


def count_link(n, href, unit: str | None = None, title: str | None = None) -> str:
    """Render a count as the control that opens the set it counts."""
    attr = f' title="{esc(title)}"' if title else ""
    tail = f' <span class="unit">{esc(unit)}</span>' if unit else ""
    if n is None:
        return f'<span class="cnt none"{attr}>not attempted</span>{tail}'
    text = fnum(n)
    if not href:
        return f'<span class="cnt"{attr}>{text}</span>{tail}'
    return f'<a class="cnt" href="{esc(href)}"{attr}>{text}</a>{tail}'


def rel(path: Path | None) -> str:
    if path is None:
        return "unset"
    root = live_root() or ROOT
    if root is None:
        return str(path)
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def load_json(path: Path):
    """Return (data, error_message). Never raises."""
    try:
        if path is None or not path.exists():
            label = rel(path) if path is not None else "unset"
            return None, f"not available yet ({label} missing)"
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            return json.load(fh), None
    except Exception as exc:  # noqa: BLE001
        return None, f"could not read {getattr(path, 'name', path)}: {exc}"


def load_jsonl(path: Path, limit: int | None = None):
    """Return (rows, error_message) for a newline-delimited JSON file."""
    try:
        if path is None or not path.exists():
            label = rel(path) if path is not None else "unset"
            return [], f"not available yet ({label} missing)"
        rows = []
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
                if limit and len(rows) >= limit:
                    break
        return rows, None
    except Exception as exc:  # noqa: BLE001
        return [], f"could not read {getattr(path, 'name', path)}: {exc}"


def ago(ts: float | None) -> str:
    if not ts:
        return "never"
    delta = max(0, int(time.time() - ts))
    if delta < 60:
        return f"{delta}s ago"
    if delta < 3600:
        return f"{delta // 60}m {delta % 60}s ago"
    return f"{delta // 3600}h {(delta % 3600) // 60}m ago"


def missing(msg: str) -> str:
    return f'<p class="miss">{esc(msg)}</p>'


def panel(inner: str, title: str = "") -> str:
    head = f'<h2 style="margin-top:0">{esc(title)}</h2>' if title else ""
    return f'<div class="panel">{head}{inner}</div>'


def table(headers: list[str], rows: list[list[str]], numeric: set[int] | None = None) -> str:
    """Build a table. `numeric` holds column indices to right-align."""
    numeric = numeric or set()
    head = "".join(
        f'<th class="num">{esc(h)}</th>' if i in numeric else f"<th>{esc(h)}</th>"
        for i, h in enumerate(headers)
    )
    body = []
    for r in rows:
        cells = "".join(
            f'<td class="num">{c}</td>' if i in numeric else f"<td>{c}</td>"
            for i, c in enumerate(r)
        )
        body.append(f"<tr>{cells}</tr>")
    return (f'<div class="tablewrap"><table><thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')


def kv(pairs: list[tuple[str, str]]) -> str:
    items = "".join(f"<div>{esc(k)}</div><div>{v}</div>" for k, v in pairs)
    return f'<div class="kv">{items}</div>'


def tag(text: str, kind: str = "") -> str:
    return f'<span class="tag {kind}">{esc(text)}</span>'


def table_exists(name: str, db: Path | None = None) -> bool:
    """True when *name* is a table in the target database."""
    rows, err = query_db(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
        db=db,
        ignore_missing=False,
    )
    return bool(rows) and err is None


def query_db(
    sql: str,
    params: tuple = (),
    db: Path | None = None,
    *,
    ignore_missing: bool = False,
):
    """Run a read-only query. Returns (rows, error). Never raises.

    Panels must query with an indexed WHERE or an aggregate over a small table,
    never `SELECT *` over `func`. Per-binary counts come from `binary.func_count`.

    When ``ignore_missing`` is true, a missing database file or absent table
    returns ``([], None)`` instead of an error — for optional schema the
    pipeline has not populated yet.
    """
    target = db if db is not None else live_db()
    if target is None:
        return [], "AGENT_DECOMPILE_CORPUS_DB is unset"
    if not target.exists():
        if ignore_missing:
            return [], None
        return [], f"not available yet ({rel(target)} missing)"
    try:
        con = sqlite3.connect(f"file:{target}?mode=ro", uri=True, timeout=10)
        con.execute("PRAGMA query_only = ON")
        rows = con.execute(sql, params).fetchall()
        con.close()
        return rows, None
    except sqlite3.Error as exc:
        message = str(exc)
        if ignore_missing and "no such table" in message.lower():
            return [], None
        return [], f"query failed: {exc}"


def tcp_up(host: str, port: int, timeout: float = 1.5) -> bool:
    if not port:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def procs_by_cwd() -> dict[str, list[tuple[int, str]]]:
    """Map process cwd -> [(pid, cmdline)]. Silently skips unreadable pids."""
    out: dict[str, list[tuple[int, str]]] = {}
    try:
        pids = os.listdir("/proc")
    except OSError:
        return out
    for pid in pids:
        if not pid.isdigit():
            continue
        try:
            cwd = os.readlink(f"/proc/{pid}/cwd")
        except OSError:
            continue
        cmd = ""
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as fh:
                cmd = fh.read().replace(b"\x00", b" ").decode("utf-8", "replace").strip()
        except OSError:
            pass
        out.setdefault(cwd, []).append((int(pid), cmd or "?"))
    return out


def tail_lines(path: Path, nlines: int = 25, nbytes: int = 1 << 20) -> list[str]:
    """Last lines of a possibly-huge log, read from the end only."""
    try:
        with path.open("rb") as fh:
            size = fh.seek(0, os.SEEK_END)
            fh.seek(max(0, size - nbytes))
            data = fh.read()
        text = data.decode("utf-8", "replace")
        return [ln.rstrip() for ln in text.splitlines() if ln.strip()][-nlines:]
    except OSError:
        return []


def page_window(offset=0, limit='all') -> tuple[int, int | None]:
    """Start index and optional cap. None cap means every remaining row."""
    start = max(0, int(offset or 0))
    if limit in (None, '', 'all', 'All'):
        return 0, None
    try:
        count = int(limit)
    except (TypeError, ValueError):
        return 0, None
    if count <= 0:
        return 0, None
    return start, count
