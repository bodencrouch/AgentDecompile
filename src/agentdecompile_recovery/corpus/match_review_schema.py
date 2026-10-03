"""Match-review control plane; installed only by an owned schema migration.

UUIDs and audit times are control-plane metadata, not recovery determinism inputs.
This module does not migrate a database on import or during review reads.
"""
from __future__ import annotations

import sqlite3
import uuid

TABLES = {
    'match_review_control', 'match_review_revision', 'match_review_audit',
}
SCHEMA_VERSION = 4
MIGRATION_NAME = 'match_review'
TRIGGERS = {f'match_review_{table}_{event}' for table in ('match', 'binary')
            for event in ('insert', 'update', 'delete')} | {
                'match_review_audit_insert', 'match_review_audit_update', 'match_review_audit_delete'}


TABLE_SQL = {
    'match_review_control': """CREATE TABLE IF NOT EXISTS match_review_control (
        singleton INTEGER PRIMARY KEY CHECK(singleton=1),
        incarnation TEXT NOT NULL,
        next_revision INTEGER NOT NULL CHECK(typeof(next_revision)='integer' AND next_revision>=0)
    )""",
    'match_review_revision': """CREATE TABLE IF NOT EXISTS match_review_revision (
        kind TEXT NOT NULL CHECK(kind IN ('match','binary')),
        entity_id INTEGER NOT NULL,
        revision INTEGER NOT NULL CHECK(typeof(revision)='integer' AND revision>0),
        binary_repo_path TEXT,
        binary_slug TEXT,
        PRIMARY KEY(kind,entity_id)
    )""",
    'match_review_audit': """CREATE TABLE IF NOT EXISTS match_review_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id INTEGER NOT NULL,
        incarnation TEXT NOT NULL,
        selection TEXT NOT NULL,
        decision TEXT NOT NULL CHECK(decision IN ('accept','reject')),
        old_status TEXT NOT NULL,
        new_status TEXT NOT NULL,
        old_revision INTEGER NOT NULL,
        new_revision INTEGER NOT NULL,
        observed_token TEXT NOT NULL,
        basis_json TEXT NOT NULL,
        trusted_actor TEXT,
        decided_at TEXT NOT NULL
    )""",
}


# Keep the old natural keys in the control row: REPLACE can implicitly delete
# a different binary ID without running DELETE triggers. These indexes make
# cleanup proportional to the conflicting keys, not the corpus population.
INDEX_SQL = {
    f'match_review_binary_{key}': f"""CREATE INDEX IF NOT EXISTS match_review_binary_{key}
        ON match_review_revision(binary_{key}) WHERE kind='binary'"""
    for key in ('repo_path', 'slug')
}


def _trigger_sql() -> dict[str, str]:
    result = {}
    for table in ('binary', 'match'):
        for event in ('insert', 'update', 'delete'):
            name = f'match_review_{table}_{event}'
            remove = (f"DELETE FROM match_review_revision WHERE kind='{table}' AND entity_id=OLD.id;"
                      if event in ('update', 'delete') else '')
            key_columns = ',binary_repo_path,binary_slug' if table == 'binary' else ''
            key_values = ',NEW.repo_path,NEW.slug' if table == 'binary' else ''
            cleanup = ''
            if table == 'binary' and event != 'delete':
                # AFTER timing is essential: BEFORE cleanup would also persist
                # for INSERT/UPDATE OR IGNORE, wrongly removing live membership.
                cleanup = ''.join(f"""DELETE FROM match_review_revision
                    WHERE kind='binary' AND binary_{key}=NEW.{key} AND entity_id<>NEW.id
                    AND NOT EXISTS(SELECT 1 FROM binary WHERE id=entity_id);"""
                    for key in ('repo_path', 'slug'))
            insert = (f"INSERT OR REPLACE INTO match_review_revision(kind,entity_id,revision{key_columns}) "
                      f"SELECT '{table}',NEW.id,next_revision{key_values} FROM match_review_control WHERE singleton=1;"
                      if event != 'delete' else '')
            result[name] = f"""CREATE TRIGGER IF NOT EXISTS {name} AFTER {event.upper()} ON {table}
                BEGIN
                    UPDATE match_review_control SET next_revision=next_revision+1 WHERE singleton=1;
                    {cleanup}
                    {remove}
                    {insert}
                END"""
    for event in ('update', 'delete'):
        name = f'match_review_audit_{event}'
        result[name] = f"""CREATE TRIGGER IF NOT EXISTS {name} BEFORE {event.upper()} ON match_review_audit
            BEGIN SELECT RAISE(ABORT, 'review_audit_append_only'); END"""
    result['match_review_audit_insert'] = """CREATE TRIGGER IF NOT EXISTS match_review_audit_insert
        BEFORE INSERT ON match_review_audit
        WHEN EXISTS(SELECT 1 FROM match_review_audit WHERE id=NEW.id)
        BEGIN SELECT RAISE(ABORT, 'review_audit_append_only'); END"""
    return result


TRIGGER_SQL = _trigger_sql()


def _normalized(sql: str) -> str:
    # sqlite_master omits IF NOT EXISTS from stored DDL.
    return ' '.join(sql.replace('IF NOT EXISTS ', '').split()).rstrip(';')


def _require_objects(con: sqlite3.Connection) -> None:
    objects = {row[0]: (row[1], row[2]) for row in con.execute(
        "SELECT name,type,sql FROM sqlite_master WHERE name LIKE 'match_review_%'")}
    for kind, statements in (('table', TABLE_SQL), ('index', INDEX_SQL), ('trigger', TRIGGER_SQL)):
        for name, expected in statements.items():
            if name not in objects:
                raise ValueError('review_schema_required')
            actual_kind, actual = objects[name]
            if actual_kind != kind or not actual or _normalized(actual) != _normalized(expected):
                raise ValueError('review_schema_corrupt')
    rows = con.execute('SELECT singleton,incarnation,next_revision FROM match_review_control').fetchall()
    if len(rows) != 1:
        raise ValueError('review_schema_corrupt')
    singleton, incarnation, revision = rows[0]
    if (singleton != 1 or not isinstance(incarnation, str) or len(incarnation) != 32
            or any(c not in '0123456789abcdef' for c in incarnation)
            or type(revision) is not int or revision < 0):
        raise ValueError('review_schema_corrupt')


def install(con: sqlite3.Connection) -> None:
    """Install in the migration transaction without modifying recovery layouts.

    Ordered window allocation seeds all IDs in SQL with constant Python memory.
    SQLite can spill its window work to temporary storage. Existing complete
    installations are validated and retained; partial installations are refused,
    never silently repaired with fresh revisions or a new incarnation.
    """
    if not con.in_transaction:
        raise ValueError('review_schema_requires_migration_transaction')
    if con.execute("SELECT 1 FROM sqlite_master WHERE name LIKE 'match_review_%' LIMIT 1").fetchone():
        _require_objects(con)
        for table in ('binary', 'match'):
            if con.execute(f"""SELECT 1 FROM {table} AS entity
                LEFT JOIN match_review_revision AS r ON r.kind=? AND r.entity_id=entity.id
                WHERE r.entity_id IS NULL LIMIT 1""", (table,)).fetchone():
                raise ValueError('review_schema_corrupt')
            if con.execute(f"""SELECT 1 FROM match_review_revision AS r
                LEFT JOIN {table} AS entity ON entity.id=r.entity_id
                WHERE r.kind=? AND (entity.id IS NULL OR r.revision >
                    (SELECT next_revision FROM match_review_control WHERE singleton=1)) LIMIT 1""",
                (table,)).fetchone():
                raise ValueError('review_schema_corrupt')
        return
    for sql in TABLE_SQL.values():
        con.execute(sql)
    for sql in INDEX_SQL.values():
        con.execute(sql)
    con.execute('INSERT INTO match_review_control VALUES(1,?,0)', (uuid.uuid4().hex,))
    for table in ('binary', 'match'):
        key_columns = ',binary_repo_path,binary_slug' if table == 'binary' else ''
        key_values = ',repo_path,slug' if table == 'binary' else ''
        con.execute(f"""INSERT INTO match_review_revision(kind,entity_id,revision{key_columns})
            SELECT ?, id, (SELECT next_revision FROM match_review_control WHERE singleton=1)
                         + ROW_NUMBER() OVER (ORDER BY id){key_values}
            FROM {table}""", (table,))
        con.execute("""UPDATE match_review_control SET next_revision = next_revision +
            (SELECT count(*) FROM match_review_revision WHERE kind=?) WHERE singleton=1""", (table,))
    for sql in TRIGGER_SQL.values():
        con.execute(sql)
    _require_objects(con)


def require(con: sqlite3.Connection) -> None:
    """Refuse unupgraded/read-only legacy stores without attempting repair."""
    if con.execute('PRAGMA user_version').fetchone()[0] < SCHEMA_VERSION:
        raise ValueError('review_schema_required')
    if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migration'").fetchone():
        raise ValueError('review_schema_required')
    try:
        ledger = con.execute('SELECT name FROM schema_migration WHERE version=?', (SCHEMA_VERSION,)).fetchone()
    except sqlite3.Error as exc:
        raise ValueError('review_schema_corrupt') from exc
    if ledger is None or ledger[0] != MIGRATION_NAME:
        raise ValueError('review_schema_required')
    _require_objects(con)
