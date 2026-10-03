"""STABS v10 regressions authored under source-only constraints; not executed.

Use real SQLite and the canonical runner when execution is authorized. Version 9
fixtures stop the actual registry at 9; they never downgrade a v10 schema stamp.
"""
from __future__ import annotations

import ast
from pathlib import Path
import sqlite3

import pytest

from agentdecompile_recovery.corpus import delete_registry, migrations, store
from agentdecompile_recovery.corpus import stabs_link

V9_LEDGER = list(enumerate((
    'baseline', 'analyzer_identity', 'basis_supersession', 'match_review',
    'function_storage', 'typed_fields', 'matching_evidence', 'pcode_channel',
    'match_metadata',
), 1))
V10_LEDGER = V9_LEDGER + [(10, 'stabs_schema_ownership')]
V11_LEDGER = V10_LEDGER + [(11, 'decomp_schema_ownership')]
V12_LEDGER = V11_LEDGER + [(12, 'convention_schema_ownership')]
V13_LEDGER = V12_LEDGER + [(13, 'type_schema_ownership')]


def _v9(path=':memory:'):
    con = sqlite3.connect(path)
    migrations.apply_pending(con, target=9)
    assert _ledger(con) == V9_LEDGER
    con.executemany('INSERT INTO binary(id,repo_path,slug,role) VALUES (?,?,?,?)',
                    [(1, '/a', 'a', 'future-role'), (2, '/b', 'b', None)])
    con.executemany('INSERT INTO func(id,binary_id,addr,source_file,object_file) VALUES (?,?,?,?,?)',
                    [(1, 1, 16, 'known.cpp', 'known.o'), (2, 2, 32, None, None)])
    con.executemany('INSERT INTO stabs_type(id,binary_id,name,stab,source_file) VALUES (?,?,?,?,?)',
                    [(41, 1, 'Known', 't1', 'known.cpp'), (42, 2, 'Unknown', 't2', None)])
    con.commit()
    return con


def _ledger(con):
    return [tuple(r) for r in con.execute('SELECT version,name FROM main.schema_migration ORDER BY version')]


def _snapshot(con):
    objects = list(con.execute('SELECT type,name,tbl_name,sql FROM main.sqlite_schema ORDER BY name'))
    rows = {name: sorted(con.execute(f'SELECT * FROM main."{name}"'), key=repr)
            for kind, name, _, _ in objects if kind == 'table' and not name.startswith('sqlite_')}
    return con.execute('PRAGMA user_version').fetchone()[0], objects, rows


def _mutations(statements):
    return [s for s in statements if s.lstrip().upper().startswith(
        ('CREATE ', 'ALTER ', 'DROP ', 'INSERT ', 'DELETE ', 'UPDATE ', 'BEGIN ', 'COMMIT', 'SAVEPOINT '))]


@pytest.mark.parametrize('columns', [(), ('stabs_name',), ('stabs_type',), ('stabs_name', 'stabs_type')])
@pytest.mark.parametrize('source_index', [False, True])
def test_actual_v9_variants_preserve_values_nulls_ids_and_other_binary(columns, source_index):
    con = _v9()
    try:
        for name in columns:
            con.execute(f'ALTER TABLE func ADD COLUMN {name} TEXT')
            con.execute(f'UPDATE func SET {name}=? WHERE binary_id=1', ('retained:' + name,))
        if source_index:
            con.execute(store.STABS_FUNC_INDEX_SQL)
        con.execute('ALTER TABLE func ADD COLUMN unrelated_extension TEXT')
        con.execute("UPDATE func SET unrelated_extension='preserve' WHERE binary_id=2")
        con.commit()
        old = _snapshot(con)
        assert [s.version for s in migrations.apply_pending(con, target=10)] == [10]
        assert _ledger(con) == V10_LEDGER
        store._require_stabs_shape(con, complete=True)
        assert list(con.execute('SELECT * FROM stabs_type ORDER BY id')) == old[2]['stabs_type']
        assert list(con.execute('SELECT * FROM binary ORDER BY id')) == old[2]['binary']
        new_columns = [r[1] for r in con.execute('PRAGMA table_info(func)')]
        old_columns = [name for name in new_columns if name not in {'stabs_name', 'stabs_type'} - set(columns)]
        assert list(con.execute('SELECT ' + ','.join(old_columns) + ' FROM func ORDER BY id')) == old[2]['func']
        for name in {'stabs_name', 'stabs_type'} - set(columns):
            assert list(con.execute(f'SELECT {name} FROM func')) == [(None,), (None,)]
        seen = []
        con.set_trace_callback(seen.append)
        assert migrations.apply_pending(con, target=10) == []
        assert _mutations(seen) == []
        con.set_trace_callback(None)
        with pytest.raises(delete_registry.BinaryDeleteUnsupported, match='schema_unsupported:func'):
            store.remove_binary(con, slug='a')
    finally:
        con.close()


@pytest.mark.parametrize('missing', ['ix_stabs_type_bin', 'ix_stabs_type_src', 'both'])
def test_v10_recreates_only_missing_declared_indexes(missing):
    con = _v9()
    try:
        for name in store.STABS_INDEX_SQL:
            if missing in {name, 'both'}:
                con.execute(f'DROP INDEX {name}')
        before = list(con.execute('SELECT * FROM stabs_type ORDER BY id'))
        migrations.apply_pending(con, target=10)
        assert _ledger(con) == V10_LEDGER
        store._require_stabs_shape(con, complete=True)
        assert list(con.execute('SELECT * FROM stabs_type ORDER BY id')) == before
    finally:
        con.close()


@pytest.mark.parametrize('ddl', [
    'ALTER TABLE func ADD COLUMN stabs_name INTEGER',
    "ALTER TABLE func ADD COLUMN stabs_type TEXT DEFAULT 'invented'",
    "ALTER TABLE func ADD COLUMN stabs_name TEXT NOT NULL DEFAULT ''",
    'ALTER TABLE func ADD COLUMN stabs_name TEXT GENERATED ALWAYS AS (source_file) VIRTUAL',
    'ALTER TABLE func DROP COLUMN source_file',
    'ALTER TABLE func DROP COLUMN object_file',
    'DROP TABLE stabs_type',
    'CREATE INDEX ix_func_srcfile ON binary(slug)',
    'CREATE TABLE ix_func_srcfile(x)',
    'CREATE INDEX extra_stabs ON stabs_type(name)',
    'CREATE TRIGGER extra_stabs AFTER INSERT ON stabs_type BEGIN SELECT 1; END',
    'CREATE TRIGGER ix_stabs_type_bin AFTER INSERT ON stabs_type BEGIN SELECT 1; END',
    'CREATE TRIGGER ix_func_srcfile AFTER INSERT ON binary BEGIN SELECT 1; END',
    'CREATE TEMP TABLE func(x)',
    'CREATE TEMP TABLE stabs_type(x)',
    'CREATE TEMP TABLE schema_migration(x)',
    'DROP TABLE schema_migration',
    'ALTER TABLE schema_migration RENAME COLUMN basis_hash TO other',
    "UPDATE schema_migration SET name='wrong' WHERE version=9",
    'DELETE FROM schema_migration WHERE version=4',
])
def test_v9_damage_refuses_before_migration_ddl_and_preserves_prior_state(ddl):
    con = _v9()
    try:
        con.execute(ddl)
        con.commit()
        before = _snapshot(con)
        seen = []
        con.set_trace_callback(seen.append)
        with pytest.raises(ValueError):
            migrations.apply_pending(con)
        assert _snapshot(con) == before
        assert not con.in_transaction
        assert not any(s.lstrip().upper().startswith(('ALTER ', 'CREATE ', 'INSERT ', 'UPDATE ', 'DELETE ')) for s in seen)
    finally:
        con.close()


@pytest.mark.parametrize('variant', ['unique', 'fk', 'check', 'default', 'extra', 'view', 'virtual', 'index', 'pk-column'])
def test_unrecognized_stabs_table_or_column_declaration_refuses(variant):
    con = _v9()
    try:
        if variant == 'pk-column':
            con.execute('DROP TABLE func')
            con.execute('CREATE TABLE func(binary_id INTEGER NOT NULL, source_file TEXT, object_file TEXT, stabs_name TEXT PRIMARY KEY)')
        elif variant == 'index':
            con.execute('DROP INDEX ix_stabs_type_bin')
            con.execute('CREATE INDEX ix_stabs_type_bin ON stabs_type(kind,binary_id)')
        else:
            con.execute('DROP TABLE stabs_type')
            if variant == 'view':
                con.execute('CREATE VIEW stabs_type AS SELECT id,binary_id,name FROM func')
            elif variant == 'virtual':
                con.execute('CREATE VIRTUAL TABLE stabs_type USING fts5(name,stab)')
            else:
                ddl = store.STABS_TYPE_DDL
                if variant == 'unique':
                    ddl = ddl.replace('UNIQUE(binary_id, source_file, name, kind, stab, func_addr)', 'UNIQUE(binary_id, name)')
                elif variant == 'fk':
                    ddl = ddl.replace('binary_id INTEGER NOT NULL', 'binary_id INTEGER NOT NULL REFERENCES binary(id)')
                elif variant == 'check':
                    ddl = ddl.replace('kind TEXT', "kind TEXT CHECK(kind='struct')")
                elif variant == 'default':
                    ddl = ddl.replace('source_file TEXT', "source_file TEXT DEFAULT 'unknown'")
                elif variant == 'extra':
                    ddl = ddl.replace('func_addr INTEGER,', 'func_addr INTEGER, extension TEXT,')
                con.execute(ddl)
        con.commit()
        before = _snapshot(con)
        with pytest.raises(ValueError):
            migrations.apply_pending(con)
        assert _snapshot(con) == before
    finally:
        con.close()


class _FailingStep:
    """Run real SQL, then inject a step failure; failed COMMIT never becomes durable."""
    def __init__(self, con, prefix, failure):
        self.con, self.prefix, self.failure = con, prefix, failure

    def __getattr__(self, name):
        return getattr(self.con, name)

    def execute(self, sql, *args):
        matches = sql.startswith(self.prefix)
        if matches and sql == 'COMMIT':
            raise self.failure  # A successful COMMIT cannot subsequently roll back.
        result = self.con.execute(sql, *args)
        if matches:
            raise self.failure
        return result


@pytest.mark.parametrize('prefix', [
    'ALTER TABLE main.func ADD COLUMN stabs_name',
    'ALTER TABLE main.func ADD COLUMN stabs_type',
    'CREATE INDEX IF NOT EXISTS ix_stabs_type_bin',
    'CREATE INDEX IF NOT EXISTS ix_stabs_type_src',
    'CREATE INDEX IF NOT EXISTS ix_func_srcfile',
    'INSERT OR IGNORE INTO schema_migration', 'PRAGMA user_version = 10', 'COMMIT',
])
@pytest.mark.parametrize('failure', [RuntimeError('injected'), KeyboardInterrupt('injected')])
def test_each_pending_step_failure_rolls_back_ddl_data_and_ledger(prefix, failure):
    con = _v9()
    try:
        con.execute('DROP INDEX ix_stabs_type_bin')
        con.execute('DROP INDEX ix_stabs_type_src')
        before = _snapshot(con)
        with pytest.raises(type(failure), match='injected'):
            migrations.apply_pending(_FailingStep(con, prefix, failure))
        assert not con.in_transaction
        assert _snapshot(con) == before
        assert _ledger(con) == V9_LEDGER
    finally:
        con.close()


def test_failed_v10_keeps_newly_committed_v1_through_v9():
    con = sqlite3.connect(':memory:')
    try:
        with pytest.raises(KeyboardInterrupt):
            migrations.apply_pending(_FailingStep(con, 'ALTER TABLE main.func ADD COLUMN stabs_type', KeyboardInterrupt()))
        assert con.execute('PRAGMA user_version').fetchone()[0] == 9
        assert _ledger(con) == V9_LEDGER
        assert not {'stabs_name', 'stabs_type'} & {r[1] for r in con.execute('PRAGMA table_info(func)')}
    finally:
        con.close()


def test_lock_tolerated_v9_and_readonly_v9_still_refuse_every_stabs_writer(tmp_path):
    path = tmp_path / 'locked.sqlite'
    _v9(path).close()
    holder = sqlite3.connect(path)
    waiter = sqlite3.connect(path, timeout=0)
    readonly = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        holder.execute('BEGIN IMMEDIATE')
        for con in (waiter, readonly):
            assert migrations.apply_pending(con) == []
            seen = []
            con.set_trace_callback(seen.append)
            for operation in (
                lambda: stabs_link.ensure_columns(con),
                lambda: stabs_link.replace_stabs_types(con, 1, []),
                lambda: stabs_link.apply_manifest_records(con, 1, []),
                lambda: stabs_link.propagate_source_files(con, donor_rows=[]),
            ):
                with pytest.raises(ValueError, match='STABS schema required: observed version 9'):
                    operation()
            assert _mutations(seen) == []
            assert con.execute('SELECT COUNT(*) FROM temp.sqlite_schema').fetchone()[0] == 0
        holder.rollback()
        assert [s.version for s in migrations.apply_pending(waiter)] == [10, 11, 12, 13]
        stabs_link.ensure_columns(waiter)
    finally:
        holder.close()
        waiter.close()
        readonly.close()


@pytest.mark.parametrize('version', [0, 8, 11, 12, 13, 14])
def test_direct_migration_body_refuses_other_versions_without_writes(version):
    con = _v9()
    try:
        if version in {11, 12, 13}:
            migrations.apply_pending(con, target=version)
            assert _ledger(con) == {11: V11_LEDGER, 12: V12_LEDGER, 13: V13_LEDGER}[version]
        elif version == 14:
            future = migrations.MIGRATIONS + [migrations.Migration(14, 'future', lambda c: None)]
            migrations.apply_pending(con, migrations=future)
            assert _ledger(con) == V13_LEDGER + [(14, 'future')]
        else:
            # Explicit corrupt stamps remain negative fixtures, not history.
            con.execute(f'PRAGMA user_version={version}')
        con.execute('BEGIN IMMEDIATE')
        before = _snapshot(con)
        with pytest.raises(ValueError):
            migrations._stabs_schema_ownership(con)
        assert _snapshot(con) == before
        assert con.in_transaction
    finally:
        con.rollback()
        con.close()


def test_direct_repeated_v10_body_is_readonly_and_requires_complete_schema():
    con = _v9()
    try:
        migrations.apply_pending(con, target=10)
        con.execute('BEGIN IMMEDIATE')
        seen = []
        con.set_trace_callback(seen.append)
        migrations._stabs_schema_ownership(con)
        assert _mutations(seen) == []
        con.execute('DROP INDEX ix_func_srcfile')
        seen.clear()
        with pytest.raises(ValueError, match='missing or unsupported STABS index'):
            migrations._stabs_schema_ownership(con)
        assert _mutations(seen) == []
    finally:
        con.rollback()
        con.close()


def test_stabs_schema_aliases_and_writer_sources_have_no_persistent_installer():
    assert stabs_link.STABS_TYPE_DDL is store.STABS_TYPE_DDL
    assert stabs_link.ADD_COLUMNS is store.STABS_FUNC_COLUMNS
    tree = ast.parse(Path(stabs_link.__file__).read_text())
    names = {'ensure_columns', 'replace_stabs_types', 'apply_manifest_records', 'propagate_source_files'}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            literals = [part.value.upper() for part in ast.walk(node)
                        if isinstance(part, ast.Constant) and isinstance(part.value, str)]
            assert not any('ALTER TABLE' in value or 'CREATE INDEX' in value or 'CREATE TABLE' in value for value in literals)
            if node.name == 'ensure_columns':
                assert not any(isinstance(part, ast.Attribute) and part.attr == 'commit' for part in ast.walk(node))


_MIXED_TEMP_SHADOWS = [('func', 'FuNc'), ('stabs_type', 'StAbS_TyPe'),
                       ('schema_migration', 'ScHeMa_MiGrAtIoN')]


def _mixed_temp_shadow(con, canonical, spelling, kind):
    # Keep observable contents in the shadow, not an empty incompatible shell.
    if kind == 'table':
        con.execute(f'CREATE TEMP TABLE "{spelling}" AS SELECT * FROM main.{canonical}')
    else:
        con.execute(f'CREATE TEMP VIEW "{spelling}" AS SELECT * FROM main.{canonical}')


def _temp_snapshot(con):
    objects = list(con.execute('SELECT type,name,tbl_name,sql FROM temp.sqlite_schema ORDER BY name'))
    rows = {name: sorted(con.execute(f'SELECT * FROM temp."{name}"'), key=repr)
            for kind, name, _, _ in objects if kind in {'table', 'view'}}
    return objects, rows


@pytest.mark.parametrize('canonical,spelling', _MIXED_TEMP_SHADOWS)
@pytest.mark.parametrize('kind', ['table', 'view'])
@pytest.mark.parametrize('caller_owned', [False, True])
def test_mixed_case_temp_shadow_refuses_actual_v9_before_any_migration_ddl(canonical, spelling, kind, caller_owned):
    con = _v9()
    try:
        _mixed_temp_shadow(con, canonical, spelling, kind)
        con.commit()
        if caller_owned:
            con.execute("INSERT INTO main.eval(run,metric) VALUES ('caller','pending')")
        before = _snapshot(con), _temp_snapshot(con)
        seen = []
        con.set_trace_callback(seen.append)
        with pytest.raises(ValueError, match='shadowing'):
            if caller_owned:
                migrations._stabs_schema_ownership(con)
            else:
                migrations.apply_pending(con)
        assert con.in_transaction is caller_owned
        assert (_snapshot(con), _temp_snapshot(con)) == before
        assert _ledger(con) == V9_LEDGER
        assert not any(sql.lstrip().upper().startswith(
            ('CREATE ', 'ALTER ', 'DROP ', 'INSERT ', 'UPDATE ', 'DELETE ')) for sql in seen)
    finally:
        con.close()


@pytest.mark.parametrize('canonical,spelling', _MIXED_TEMP_SHADOWS)
@pytest.mark.parametrize('kind', ['table', 'view'])
@pytest.mark.parametrize('operation', ['ensure', 'replace', 'manifest', 'propagate', 'link'])
def test_mixed_case_temp_shadow_refuses_current_direct_writers_and_keeps_caller_work(canonical, spelling, kind, operation):
    con = _v9()
    try:
        migrations.apply_pending(con)
        _mixed_temp_shadow(con, canonical, spelling, kind)
        con.commit()
        con.execute("INSERT INTO main.eval(run,metric) VALUES ('caller','pending')")
        operations = {
            'ensure': lambda: stabs_link.ensure_columns(con),
            'replace': lambda: stabs_link.replace_stabs_types(con, 1, [{'name': 'New', 'stab': 'new'}]),
            'manifest': lambda: stabs_link.apply_manifest_records(con, 1, [
                {'addr': 16, 'action': 'attach_stabs', 'stabs_name': 'New'}]),
            'propagate': lambda: stabs_link.propagate_source_files(con, donor_rows=[]),
            # Path sentinels make any premature filesystem access fail; the
            # public link must refuse at admission before inspecting either.
            'link': lambda: stabs_link.link(con, raw_dir=None, manifest_dir=None),
        }
        before = _snapshot(con), _temp_snapshot(con)
        seen = []
        con.set_trace_callback(seen.append)
        with pytest.raises(ValueError, match='STABS schema required.*shadowing'):
            operations[operation]()
        assert con.in_transaction
        assert (_snapshot(con), _temp_snapshot(con)) == before
        assert _ledger(con) == V13_LEDGER
        assert con.execute('SELECT run,metric FROM main.eval').fetchall() == [('caller', 'pending')]
        assert _mutations(seen) == []
        assert not any(sql.lstrip().upper().startswith(('ROLLBACK', 'RELEASE ', 'PRAGMA TEMP_STORE')) for sql in seen)
        con.rollback()
        assert con.execute('SELECT COUNT(*) FROM main.eval').fetchone()[0] == 0
    finally:
        con.close()


@pytest.mark.parametrize('ddl', [
    'CREATE INDEX IX_FUNC_SRCFILE ON func(binary_id,source_file)',
    'CREATE TRIGGER IX_STABS_TYPE_BIN AFTER INSERT ON stabs_type BEGIN SELECT 1; END',
    'ALTER TABLE func ADD COLUMN StAbS_NaMe TEXT',
    'ALTER TABLE func ADD COLUMN StAbS_TyPe TEXT',
])
def test_mixed_case_reserved_main_names_refuse_before_v10_ddl(ddl):
    con = _v9()
    try:
        con.execute(ddl)
        con.commit()
        before = _snapshot(con)
        seen = []
        con.set_trace_callback(seen.append)
        with pytest.raises(ValueError, match='unsupported STABS .*spelling'):
            migrations.apply_pending(con)
        assert _snapshot(con) == before
        assert not any(sql.lstrip().upper().startswith(
            ('CREATE ', 'ALTER ', 'INSERT ', 'UPDATE ', 'DELETE ')) for sql in seen)
    finally:
        con.close()
