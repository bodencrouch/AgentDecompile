"""Shared helpers for the corpus dashboard.

ROOT and DB_PATH come from AgentDecompile environment variables when set,
falling back to the same ``./agentdecompile_projects`` default as the rest
of the corpus tooling (see ``corpus_env``). There is no kotorxid repo
default and no db/kotorxid.sqlite fallback.
"""

from __future__ import annotations

import html
import hashlib
import json
import os
import re
import socket
import sqlite3
import time
import threading
import uuid
from contextlib import contextmanager
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
_REVIEW_SELECTION_LOCK = threading.RLock()
_REVIEW_SELECTION_GENERATION = uuid.uuid4().hex


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


def _set_runtime_db_path(path: Path | str | None) -> None:
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


def set_runtime_db_path(path: Path | str | None) -> None:
    """Serialize selection changes with review transactions; every selection invalidates."""
    global _REVIEW_SELECTION_GENERATION
    with _REVIEW_SELECTION_LOCK:
        _set_runtime_db_path(path)
        _REVIEW_SELECTION_GENERATION = uuid.uuid4().hex


@contextmanager
def match_review_context(expected_selection: str = "", database=None):
    """Pin once and hold selection through the complete review operation."""
    from ..match_review import pin_context, ReviewError
    with _REVIEW_SELECTION_LOCK:
        selected = live_db()
        if selected is None:
            raise ReviewError('unavailable')
        try:
            context = pin_context(selected, _REVIEW_SELECTION_GENERATION)
            if database is not None and Path(database).resolve(strict=True) != context.path:
                raise ReviewError('context_changed')
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            if isinstance(exc, ReviewError):
                raise
            raise ReviewError('unavailable') from exc
        if expected_selection and expected_selection != context.selection:
            raise ReviewError('context_changed')
        yield context


def review_error_status(error):
    code = error.code if hasattr(error, 'code') else str(error)
    if code in {'stale_basis', 'context_changed'}:
        return 409
    if code in {'unavailable', 'busy', 'schema_required', 'review_schema_required', 'review_schema_corrupt'}:
        return 503
    return 400


def list_match_review(*, after_id=0, limit=50, selection='', database=None):
    from ..match_review import list_review
    with match_review_context(selection, database) as context:
        return list_review(context, after_id=after_id, limit=limit)


def find_candidate_dbs() -> list[Path]:
    """Scan conventional locations for an existing corpus sqlite file."""
    seen: dict[str, Path] = {}
    search_dirs = [_corpus_env.DEFAULT_PROJECT_ROOT, Path.cwd(), Path.home() / "agentdecompile_projects"]
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


def corpus_file_identity(database: Path | None) -> dict:
    """Compatibility projection of the authoritative validated corpus identity."""
    try:
        binding = resolve_corpus_binding(database)
        return {key: binding[key] for key in ("identity", "path", "size", "database_uuid")}
    except (CorpusBindingError, OSError, RuntimeError, TypeError, ValueError):
        return {"identity": "", "path": str(database or "")}


class CorpusBindingError(ValueError):
    """A selected corpus cannot be proven to be the requested recovery context."""


def _selected_corpus_path(database: Path | str | None) -> tuple[Path, str]:
    """Resolve only an explicit selection; never search for a plausible database."""
    if database is not None and str(database).strip():
        return Path(database).expanduser(), "request"
    if _RUNTIME_DB_PATH is not None:
        return _RUNTIME_DB_PATH.expanduser(), "runtime selection"

    selection = _runtime_db_selection_path()
    if selection is not None and selection.exists():
        try:
            saved = json.loads(selection.read_text(encoding="utf-8"))
            raw = saved.get("path") if isinstance(saved, dict) else None
        except (OSError, TypeError, ValueError) as exc:
            raise CorpusBindingError(
                f"Saved corpus selection is unreadable at {selection}; explicitly select a corpus database again."
            ) from exc
        if not isinstance(raw, str) or not raw.strip():
            raise CorpusBindingError(
                f"Saved corpus selection at {selection} has no database path; explicitly select a corpus database."
            )
        return Path(raw).expanduser(), "saved selection"

    configured = [
        (name, os.environ.get(name, "").strip())
        for name in ("AGENT_DECOMPILE_COCKPIT_DB", "AGENT_DECOMPILE_CORPUS_DB")
        if os.environ.get(name, "").strip()
    ]
    distinct = {value for _, value in configured}
    if len(distinct) > 1:
        names = ", ".join(name for name, _ in configured)
        raise CorpusBindingError(
            f"Conflicting corpus database settings ({names}); choose one database in the dashboard or configure one path."
        )
    if configured:
        name, value = configured[0]
        return Path(value).expanduser(), name
    raise CorpusBindingError(
        "No corpus database is selected. Choose an existing corpus database in the dashboard; "
        "no database will be created or guessed."
    )


def resolve_corpus_binding(
    database: Path | str | None = None,
    *,
    program_id: str | None = None,
    binary_sha256: str | None = None,
    output_root: Path | str | None = None,
    expected_identity: str | None = None,
) -> dict:
    """Validate and identify one corpus/program binding using read-only SQLite access.

    This is the common identity boundary for Cockpit and dashboard action context.
    A database must be explicitly selected by request, runtime preference, or a
    documented DB environment variable. It is never found by directory scan and
    resolution never creates or mutates a database.
    """
    selected, source = _selected_corpus_path(database)
    try:
        canonical = selected.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise CorpusBindingError(
            f"Selected corpus database does not exist or cannot be resolved: {selected}. "
            "Choose an existing database in the dashboard."
        ) from exc
    if not canonical.is_file():
        raise CorpusBindingError(f"Selected corpus path is not a regular file: {canonical}.")
    try:
        stat = canonical.stat()
    except OSError as exc:
        raise CorpusBindingError(f"Cannot inspect selected corpus database: {canonical}: {exc}") from exc
    if stat.st_size <= 0:
        raise CorpusBindingError(
            f"Selected corpus database is empty (0 bytes): {canonical}. Choose a populated corpus database."
        )

    connection = None
    try:
        # Use the corpus store's authoritative, read-only schema admission;
        # unlike the writer path this neither migrates nor creates anything.
        from ..store import connect as connect_corpus

        connection = connect_corpus(canonical, read_only=True)
        connection.execute("PRAGMA query_only=ON")
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        columns = {
            table: {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}
            for table in ("binary", "func")
        }

        program_ids: list[str] = []
        binary_hash: str | None = None
        binary_match: tuple[int, str, str | None] | None = None
        if program_id or binary_sha256:
            binary_columns = columns["binary"]
            if binary_sha256:
                hash_column = next((name for name in ("content_sha256", "sha256") if name in binary_columns), None)
                if hash_column is None:
                    raise CorpusBindingError(
                        f"Cannot bind binary SHA-256 in {canonical}: the binary table has no content hash column."
                    )
                matches = connection.execute(
                    f'SELECT id, slug, {hash_column}, '
                    f'{"game" if "game" in binary_columns else "NULL"} '
                    f'FROM binary WHERE lower({hash_column})=lower(?)',
                    (binary_sha256.strip(),),
                ).fetchall()
                if len(matches) != 1:
                    state = "not found" if not matches else "ambiguous"
                    raise CorpusBindingError(
                        f"Binary SHA-256 binding is {state} in selected corpus {canonical}; "
                        "select a unique recorded binary with the expected content hash."
                    )
                binary_hash = str(matches[0][2]).lower()
                binary_match = (int(matches[0][0]), str(matches[0][1]),
                                str(matches[0][3]) if matches[0][3] not in (None, "") else None)
            if program_id or binary_match is not None:
                # Cockpit's project identity is derived from game when present,
                # otherwise from the concrete binary slug. Match that contract
                # without allowing a fuzzy name or first-row fallback.
                game_col = "game" if "game" in binary_columns else None
                query = (f'SELECT b.id, b.slug, {"b.game" if game_col else "NULL"} FROM binary b '
                         'WHERE EXISTS (SELECT 1 FROM func f WHERE f.binary_id=b.id)')
                rows = connection.execute(query).fetchall()
                groups: dict[tuple[str, str], list[tuple[int, str]]] = {}
                for bid, slug, game in rows:
                    key = ("game", str(game)) if game not in (None, "") else ("binary", str(slug))
                    groups.setdefault(key, []).append((int(bid), str(slug)))
                used: set[str] = set()
                pid_by_key: dict[tuple[str, str], str] = {}
                for key in sorted(groups, key=lambda item: (item[0] != "game", item[1])):
                    label = key[1]
                    base = re.sub(r"[^A-Za-z0-9]+", "-", str(label)).strip("-").lower() or "program"
                    candidate, suffix = base, 2
                    while candidate in used:
                        candidate, suffix = f"{base}-{suffix}", suffix + 1
                    used.add(candidate)
                    program_ids.append(candidate)
                    pid_by_key[key] = candidate
                if not program_id and binary_match is not None:
                    _, slug, game = binary_match
                    program_id = pid_by_key.get(("game", game) if game is not None else ("binary", slug))
                if program_id not in program_ids:
                    raise CorpusBindingError(
                        f"Program {program_id!r} is not present in selected corpus {canonical}. "
                        "Choose a program from this database before starting recovery."
                    )
                if binary_match is not None:
                    _bid, slug, game = binary_match
                    key = ("game", game) if game is not None else ("binary", slug)
                    expected_program = pid_by_key.get(key)
                    if expected_program != program_id:
                        raise CorpusBindingError(
                            f"Selected program {program_id!r} does not contain the requested binary SHA-256. "
                            "Select the matching program and binary together."
                        )
        application_id = int(connection.execute("PRAGMA application_id").fetchone()[0])
        user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        database_uuid = None
        for table in ("corpus_meta", "corpus_metadata", "metadata"):
            if table not in tables:
                continue
            cols = {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}
            if {"key", "value"}.issubset(cols):
                row = connection.execute(
                    f'SELECT value FROM "{table}" WHERE lower(key) IN (\'corpus_uuid\', \'database_uuid\', \'uuid\') LIMIT 1'
                ).fetchone()
                if row and row[0]:
                    database_uuid = str(row[0])
                    break
    except CorpusBindingError:
        raise
    except (sqlite3.Error, ValueError, OSError) as exc:
        raise CorpusBindingError(
            f"Selected database is unreadable or not admitted by the current corpus schema: {canonical}: {exc}"
        ) from exc
    finally:
        if connection is not None:
            connection.close()

    try:
        current_stat = canonical.stat()
    except OSError as exc:
        raise CorpusBindingError(f"Selected corpus database disappeared during validation: {canonical}") from exc
    if (current_stat.st_dev, current_stat.st_ino) != (stat.st_dev, stat.st_ino):
        raise CorpusBindingError(
            f"Selected corpus database was replaced during validation: {canonical}; reselect it before continuing."
        )

    identity_payload = [str(canonical), stat.st_dev, stat.st_ino, application_id, user_version, database_uuid]
    identity = hashlib.sha256(json.dumps(identity_payload, separators=(",", ":")).encode()).hexdigest()
    if expected_identity and expected_identity != identity:
        raise CorpusBindingError(
            f"Selected corpus identity changed for {canonical}; reselect the current database before continuing."
        )
    root = Path(output_root).expanduser() if output_root is not None else runtime_work_dir(canonical)
    if root is not None:
        root = root.resolve()
    return {
        "identity": identity,
        "path": str(canonical),
        "size": stat.st_size,
        "database_uuid": database_uuid,
        "application_id": application_id,
        "user_version": user_version,
        "selection_source": source,
        "program_id": program_id,
        "binary_sha256": binary_hash,
        "output_root": str(root) if root is not None else None,
    }


class CorpusReadError(Exception):
    def __init__(self, message: str, status: int = 503):
        super().__init__(message)
        self.status = status


@contextmanager
def corpus_read_snapshot(expected_identity: str = ""):
    """One selected database and one read snapshot for a logical response."""
    database = live_db()
    corpus = corpus_file_identity(database)
    if not corpus["identity"]:
        raise CorpusReadError("Selected corpus database is unavailable")
    if expected_identity and expected_identity != corpus["identity"]:
        raise CorpusReadError("Corpus database changed; explicitly select an identity from the current corpus", 409)
    connection = None
    try:
        connection = sqlite3.connect(Path(corpus["path"]).as_uri() + "?mode=ro", uri=True, timeout=10)
        connection.execute("PRAGMA query_only = ON")
        connection.execute("BEGIN")
        connection.execute("SELECT name FROM sqlite_master LIMIT 1").fetchall()
        if corpus_file_identity(database) != corpus:
            raise CorpusReadError("Corpus database was replaced while opening it", 409)
        yield connection, corpus
        if corpus_file_identity(live_db()) != corpus:
            raise CorpusReadError("Corpus database changed while reading; retry from the current corpus", 409)
    except sqlite3.Error as exc:
        raise CorpusReadError(f"Corpus read failed: {exc}") from exc
    finally:
        if connection is not None:
            connection.close()


def runtime_project_root(database: Path | str | None = None) -> Path | None:
    """Return the project owning the selected runtime database when known."""
    database = Path(database).expanduser() if database is not None else live_db()
    if database is not None and database.parent.name == "db":
        candidate = database.parent.parent
        if (candidate / "corpus_work").is_dir():
            return candidate
    return live_root()


def runtime_work_dir(database: Path | str | None = None) -> Path | None:
    """Return the recovery workspace paired with the selected runtime db."""
    project = runtime_project_root(database)
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


def table_exists(name: str, db: Path | None = None, *, connection: sqlite3.Connection | None = None) -> bool:
    """True when *name* is a table in the target database."""
    rows, err = query_db(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
        db=db,
        ignore_missing=False,
        connection=connection,
    )
    return bool(rows) and err is None


def query_db(
    sql: str,
    params: tuple = (),
    db: Path | None = None,
    *,
    ignore_missing: bool = False,
    connection: sqlite3.Connection | None = None,
):
    """Run a read-only query. Returns (rows, error). Never raises.

    Panels must query with an indexed WHERE or an aggregate over a small table,
    never `SELECT *` over `func`. Per-binary counts come from `binary.func_count`.

    When ``ignore_missing`` is true, a missing database file or absent table
    returns ``([], None)`` instead of an error — for optional schema the
    pipeline has not populated yet.
    """
    if connection is not None:
        try:
            return connection.execute(sql, params).fetchall(), None
        except sqlite3.Error as exc:
            if ignore_missing and "no such table" in str(exc).lower():
                return [], None
            return [], f"query failed: {exc}"
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
