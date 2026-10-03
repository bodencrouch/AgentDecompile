"""Task2.4 operation regressions AUTHORED, NOT RUN under source-only admission.

Historical declarations are independent of the current store/deletion constants.
Feature producers are pinned for writer tests; migration never invokes them.
"""
from __future__ import annotations

import ast
import sqlite3
from pathlib import Path

import pytest

from agentdecompile_recovery.corpus import decompile, delete_registry, migrations, store
from agentdecompile_recovery.corpus.match_store import Binary, _pcode_receipt, candidate_pairs

V9_LEDGER = list(enumerate((
    'baseline', 'analyzer_identity', 'basis_supersession', 'match_review',
    'function_storage', 'typed_fields', 'matching_evidence', 'pcode_channel', 'match_metadata',
), 1))
V10_LEDGER = V9_LEDGER + [(10, 'stabs_schema_ownership')]
V11_LEDGER = V10_LEDGER + [(11, 'decomp_schema_ownership')]
LEGACY_DDL = '''CREATE TABLE IF NOT EXISTS decomp (
    binary_id INTEGER NOT NULL,
    addr INTEGER NOT NULL,
    ok INTEGER,
    n_tokens INTEGER,
    n_lines INTEGER,
    max_nest INTEGER,
    n_calls INTEGER,
    n_locals INTEGER,
    n_deref INTEGER,
    n_index INTEGER,
    n_field INTEGER,
    ctrl TEXT,
    ops TEXT,
    skeleton_hash TEXT,
    PRIMARY KEY (binary_id, addr)
)'''
AST_DDL = LEGACY_DDL.replace('    PRIMARY KEY', '    ast_fingerprint TEXT,\n    PRIMARY KEY')
INDEX_DDL = 'CREATE INDEX IF NOT EXISTS ix_decomp_bin ON decomp(binary_id)'
STATE_DDL = '''CREATE TABLE decomp_schema_state (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    mode TEXT NOT NULL CHECK (mode IN ('absent', 'skeleton_hash', 'ast_fingerprint'))
)'''
FIELDS = 'binary_id,addr,ok,n_tokens,n_lines,max_nest,n_calls,n_locals,n_deref,n_index,n_field,ctrl,ops,skeleton_hash'
FEATURES = dict(n_tokens=11, n_lines=2, max_nest=1, n_calls=3, n_locals=4,
                n_deref=5, n_index=6, n_field=7, ctrl={'if': 1}, ops={'+': 2}, skeleton_hash='pinned-skeleton')


def ledger(con):
    return [tuple(row) for row in con.execute('SELECT version,name FROM main.schema_migration ORDER BY version')]


def snapshot(con):
    objects = [tuple(row) for row in con.execute('SELECT type,name,tbl_name,sql FROM main.sqlite_schema ORDER BY name,type')]
    rows = {name: [tuple(row) for row in con.execute(f'SELECT rowid,* FROM main."{name}" ORDER BY rowid')]
            for kind, name, _, _ in objects if kind == 'table' and not name.startswith('sqlite_')}
    return con.execute('PRAGMA user_version').fetchone()[0], objects, rows


def historical(path=':memory:', *, version=10, shape='legacy', index=True, populated=True):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    migrations.apply_pending(con, target=version)
    assert ledger(con) == (V9_LEDGER if version == 9 else V10_LEDGER)
    con.executemany('INSERT INTO binary(id,repo_path,slug,role) VALUES (?,?,?,?)',
                    [(1, '/a', 'a', 'unknown-role'), (2, '/b', 'b', None), (3, '/c', 'c', None)])
    if shape != 'absent':
        con.execute(AST_DDL if shape == 'ast-create' else LEGACY_DDL)
        if shape == 'ast-alter':
            con.execute('ALTER TABLE decomp ADD COLUMN ast_fingerprint TEXT')
        if index:
            con.execute(INDEX_DDL)
        if populated:
            for bid in (1, 2):
                for i, ast in enumerate((None, '', 'ASTv1:pinned', 'historical', ' ', 'ignored', None), 1):
                    addr, ok = i * 16, 1 if i < 6 else 0 if i == 6 else None
                    con.execute(f'INSERT INTO decomp({FIELDS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                                (bid, addr, ok, 9, None, 2, 3, 4, 5, 6, 7, '{}', None, 'same-skeleton'))
                    if shape.startswith('ast'):
                        con.execute('UPDATE decomp SET ast_fingerprint=? WHERE binary_id=? AND addr=?', (ast, bid, addr))
                    con.execute('INSERT INTO func(binary_id,addr,name,hash_reloc) VALUES (?,?,?,?)',
                                (bid, addr, f'FUN_{addr:x}', f'pinned-{bid}-{addr}'))
    con.commit()
    return con


def loaded(con):
    a, b = Binary(con, 1), Binary(con, 2)
    return (a.decomp, dict(a.by_skeleton), dict(a.by_pcode),
            {addr: candidate_pairs(a, b, addr, {}) for addr in a.funcs},
            _pcode_receipt(con, 1, 2), _pcode_receipt(con, 1, 1))


@pytest.fixture
def pinned(monkeypatch):
    monkeypatch.setattr(decompile, 'features', lambda code: dict(FEATURES))
    monkeypatch.setattr(decompile, 'syntax_fingerprint', lambda code: 'ASTv1:pinned-writer')


@pytest.mark.parametrize('version', [9, 10])
@pytest.mark.parametrize('shape', ['absent', 'legacy', 'ast-create', 'ast-alter'])
@pytest.mark.parametrize('populated', [False, True])
@pytest.mark.parametrize('index', [False, True])
def test_real_historical_migration_preserves_rows_nulls_selection_and_candidates(version, shape, populated, index, monkeypatch):
    con = historical(version=version, shape=shape, populated=populated, index=index)
    try:
        con.execute('CREATE TABLE unrelated(payload TEXT)')
        con.execute("INSERT INTO unrelated VALUES ('untouched')")
        con.commit()
        before = snapshot(con)
        old_fields = [tuple(r) for r in con.execute(f'SELECT rowid,{FIELDS} FROM decomp ORDER BY rowid')] if shape != 'absent' else []
        old_ast = [tuple(r) for r in con.execute('SELECT rowid,ast_fingerprint FROM decomp ORDER BY rowid')] if shape.startswith('ast') else None
        inputs = loaded(con)
        def forbidden(*_a, **_k):
            pytest.fail('schema adoption invoked a feature producer')
        monkeypatch.setattr(decompile, 'features', forbidden)
        monkeypatch.setattr(decompile, 'syntax_fingerprint', forbidden)
        migrations.apply_pending(con)
        assert ledger(con) == V11_LEDGER
        assert loaded(con) == inputs
        assert [tuple(r) for r in con.execute(f'SELECT rowid,{FIELDS} FROM decomp ORDER BY rowid')] == old_fields
        if old_ast is not None:
            # Includes unsuccessful rows excluded from Binary/receipt loading.
            assert [tuple(r) for r in con.execute('SELECT rowid,ast_fingerprint FROM decomp ORDER BY rowid')] == old_ast
        after = snapshot(con)
        for name in ('binary', 'unrelated'):
            assert after[2][name] == before[2][name]
        assert after[2]['schema_migration'][:version] == before[2]['schema_migration']
        assert con.execute('SELECT mode FROM decomp_schema_state').fetchone()[0] == (
            'absent' if shape == 'absent' else 'skeleton_hash' if shape == 'legacy' else 'ast_fingerprint')
        if shape in {'absent', 'legacy'}:
            assert not con.execute('SELECT 1 FROM decomp WHERE ast_fingerprint IS NOT NULL').fetchone()
        if populated and shape.startswith('ast'):
            assert inputs[0][16]['pcode_fingerprint'] is None
            assert inputs[0][32]['pcode_fingerprint'] == ''
            assert inputs[2] == {'ASTv1:pinned': [48], 'historical': [64], ' ': [80]}
            assert inputs[-2]['storedFingerprintRows'] == 6
            assert inputs[-1]['storedFingerprintRows'] == 3
        if populated and shape == 'legacy':
            assert inputs[2] == {'same-skeleton': [16, 32, 48, 64, 80]}
        assert _pcode_receipt(con, 1, 3).get('available', False) is False
    finally:
        con.close()


@pytest.mark.parametrize('shape', ['absent', 'legacy', 'ast-create'])
@pytest.mark.parametrize('populated', [False, True])
def test_public_status_preserves_absent_empty_success_and_other_binary(tmp_path, monkeypatch, shape, populated):
    from agentdecompile_recovery.corpus.dashboard import recovery_status as status
    path = tmp_path / 'status.sqlite'
    con = historical(path, shape=shape, populated=populated)
    monkeypatch.setattr(status, 'live_db', lambda: path)
    monkeypatch.setattr(status, 'live_root', lambda: None)
    monkeypatch.setattr(status, '_runs', lambda *_args: [])
    before = status.corpus_status(scope='all')
    migrations.apply_pending(con)
    after = status.corpus_status(scope='all')
    assert before['available'] and after['available']
    assert before['builds'] == after['builds']
    assert before['report']['by_build'] == after['report']['by_build']
    expected = None if shape == 'absent' else 5 if populated else 0
    assert [b['sourceWitnesses'] for b in after['builds']] == [expected, expected, None if shape == 'absent' else 0]
    assert after['recovery']['totals']['sourceWitnesses'] == (10 if populated and shape != 'absent' else 0)
    assert after['recovery']['sourceAvailability']['count'] is None
    assert all(row['compiles'] is None and row['byte_verified'] is None for row in after['report']['by_build'])
    assert status.recover_status(scope='all')['recovery'] == after['recovery']
    con.close()


def test_public_status_failed_and_unknown_decomp_rows_are_zero_witnesses(tmp_path, monkeypatch):
    from agentdecompile_recovery.corpus.dashboard import recovery_status as status
    path = tmp_path / 'failed-only.sqlite'
    con = historical(path, populated=False)
    con.executemany('INSERT INTO decomp(binary_id,addr,ok,skeleton_hash) VALUES (1,?,?,?)',
                    [(16, 0, 'failed'), (32, None, 'unknown')])
    con.commit()
    migrations.apply_pending(con)
    monkeypatch.setattr(status, 'live_db', lambda: path)
    monkeypatch.setattr(status, '_runs', lambda *_args: [])
    result = status.corpus_status(scope='all')
    assert result['available']
    assert [build['sourceWitnesses'] for build in result['builds']] == [0, 0, 0]
    assert result['recovery']['totals']['sourceWitnesses'] == 0
    assert result['recovery']['sourceAvailability']['count'] is None
    assert all(row['compiles'] is None and row['byte_verified'] is None for row in result['report']['by_build'])
    assert status.recover_status(scope='all')['recovery'] == result['recovery']
    con.close()


@pytest.mark.parametrize('operation', ['ensure', 'attach', 'persist'])
def test_explicit_writer_transition_is_distinct_from_migration(tmp_path, pinned, operation):
    path = tmp_path / 'transition.sqlite'
    con = historical(path)
    migrations.apply_pending(con)
    assert store.decomp_read_state(con) == 'skeleton_hash'
    assert _pcode_receipt(con, 1, 2)['available']
    if operation == 'ensure':
        decompile.ensure_decomp_columns(con)
    elif operation == 'attach':
        decompile.attach_store(path).close()
    else:
        decompile.persist_code(con, 1, 160, 'return 1;')
    assert store.decomp_read_state(con) == 'ast_fingerprint'
    assert _pcode_receipt(con, 1, 2)['available'] is False
    assert con.execute('SELECT ast_fingerprint FROM decomp WHERE addr=16').fetchone()[0] is None
    assert con.execute('SELECT skeleton_hash FROM decomp WHERE addr=16').fetchone()[0] == 'same-skeleton'
    assert not con.in_transaction
    con.close()


@pytest.mark.parametrize('code', [None, '', 'return 1;', '  \n'])
@pytest.mark.parametrize('caller_owned', [False, True])
def test_writer_exact_payload_one_key_replacement_and_success_commit(tmp_path, pinned, code, caller_owned):
    path = tmp_path / 'writer.sqlite'
    con = historical(path, shape='ast-create')
    migrations.apply_pending(con)
    before = [tuple(r) for r in con.execute('SELECT rowid,* FROM decomp WHERE binary_id<>1 OR addr<>16 ORDER BY rowid')]
    if caller_owned:
        con.execute("INSERT INTO eval(run) VALUES ('caller')")
    result = decompile.persist_code(con, 1, 16, code)
    assert result == ({'ok': 0, 'addr': 16} if not code else {'ok': 1, 'addr': 16, **FEATURES, 'ast_fingerprint': 'ASTv1:pinned-writer'})
    row = tuple(con.execute('SELECT * FROM decomp WHERE binary_id=1 AND addr=16').fetchone())
    assert row == ((1, 16, 0, *([None] * 12)) if not code else
                   (1, 16, 1, 11, 2, 1, 3, 4, 5, 6, 7, '{"if": 1}', '{"+": 2}', 'pinned-skeleton', 'ASTv1:pinned-writer'))
    assert [tuple(r) for r in con.execute('SELECT rowid,* FROM decomp WHERE binary_id<>1 OR addr<>16 ORDER BY rowid')] == before
    assert not con.in_transaction
    with sqlite3.connect(path) as observer:
        assert observer.execute('SELECT COUNT(*) FROM eval').fetchone()[0] == int(caller_owned)
        assert observer.execute('SELECT ok FROM decomp WHERE binary_id=1 AND addr=16').fetchone()[0] == bool(code)
    con.close()


class Failing:
    def __init__(self, con, prefix, *, failure=None, cleanup=False, committed=False):
        self.con, self.prefix = con, prefix
        self.failure = failure or RuntimeError('injected operation failure')
        self.cleanup, self.committed = cleanup, committed

    def __getattr__(self, name):
        return getattr(self.con, name)

    def execute(self, sql, *args):
        if self.cleanup and sql.startswith('ROLLBACK'):
            raise RuntimeError('injected cleanup failure')
        matches = sql.lstrip().startswith(self.prefix)
        if matches and sql == 'COMMIT':
            if self.committed:
                self.con.execute(sql, *args)
            raise self.failure
        result = self.con.execute(sql, *args)
        if matches:
            raise self.failure
        return result

    def commit(self):
        if self.prefix == 'COMMIT':
            if self.committed:
                self.con.commit()
            raise self.failure
        return self.con.commit()

    def rollback(self):
        if self.cleanup:
            raise RuntimeError('injected cleanup failure')
        return self.con.rollback()


@pytest.mark.parametrize('prefix', ['CREATE TABLE IF NOT EXISTS decomp', 'ALTER TABLE main.decomp',
    'CREATE INDEX IF NOT EXISTS ix_decomp_bin', 'CREATE TABLE decomp_schema_state',
    'INSERT INTO main.decomp_schema_state', 'INSERT OR IGNORE INTO schema_migration',
    'PRAGMA user_version = 11', 'COMMIT'])
@pytest.mark.parametrize('interrupt', [False, True])
def test_pending_migration_failure_rolls_back_only_eleven(prefix, interrupt):
    con = historical(shape='absent' if prefix.startswith('CREATE TABLE IF') else 'legacy', index=False)
    before = snapshot(con)
    failure = KeyboardInterrupt('injected') if interrupt else RuntimeError('injected')
    with pytest.raises(type(failure), match='injected'):
        migrations.apply_pending(Failing(con, prefix, failure=failure))
    assert snapshot(con) == before
    assert ledger(con) == V10_LEDGER
    assert not con.in_transaction
    con.close()


@pytest.mark.parametrize('prefix', ['UPDATE main.decomp_schema_state', 'INSERT OR REPLACE INTO main.decomp', 'COMMIT'])
@pytest.mark.parametrize('caller_owned', [False, True])
@pytest.mark.parametrize('interrupt', [False, True])
def test_failed_writer_preserves_state_and_surviving_caller_work(pinned, prefix, caller_owned, interrupt):
    con = historical()
    migrations.apply_pending(con)
    if caller_owned:
        con.execute("INSERT INTO eval(run) VALUES ('caller')")
    before = snapshot(con)
    failure = KeyboardInterrupt('injected') if interrupt else RuntimeError('injected')
    with pytest.raises(type(failure), match='injected'):
        decompile.persist_code(Failing(con, prefix, failure=failure), 1, 16, 'x')
    assert snapshot(con) == before
    assert con.in_transaction == caller_owned
    con.rollback()
    assert con.execute('SELECT COUNT(*) FROM eval').fetchone()[0] == 0
    con.close()


@pytest.mark.parametrize('cleanup', [False, True])
def test_cleanup_failure_and_successful_but_unacknowledged_commit_are_not_rollback(pinned, cleanup):
    con = historical()
    migrations.apply_pending(con)
    proxy = Failing(con, 'INSERT OR REPLACE INTO main.decomp' if cleanup else 'COMMIT', cleanup=cleanup, committed=not cleanup)
    with pytest.raises(RuntimeError, match='cleanup failure' if cleanup else 'durability/rollback is uncertain'):
        decompile.persist_code(proxy, 1, 16, 'x')
    if not cleanup:
        assert store.decomp_read_state(con) == 'ast_fingerprint'
        assert not con.in_transaction
    con.close()


@pytest.mark.parametrize('damage', [
    'CREATE INDEX ix_decomp_bin ON binary(slug)',
    'CREATE TABLE ix_decomp_bin(x)',
    'CREATE TRIGGER ix_decomp_bin AFTER INSERT ON binary BEGIN SELECT 1; END',
    'CREATE INDEX IX_DECOMP_BIN ON decomp(binary_id)',
    'CREATE INDEX extra_decomp ON decomp(addr)',
    'CREATE TRIGGER extra_decomp AFTER INSERT ON decomp BEGIN SELECT 1; END',
    'ALTER TABLE decomp ADD COLUMN pcode_fingerprint TEXT',
    'ALTER TABLE decomp ADD COLUMN ast_fingerprint TEXT DEFAULT NULL',
    'ALTER TABLE decomp ADD COLUMN ast_fingerprint TEXT GENERATED ALWAYS AS (skeleton_hash) VIRTUAL',
    'ALTER TABLE decomp RENAME COLUMN addr TO Addr',
    'ALTER TABLE decomp RENAME TO DeComp',
    'CREATE TABLE decomp_schema_state(singleton INTEGER,mode TEXT)',
    'ALTER TABLE schema_migration RENAME TO ScHeMa_MiGrAtIoN',
])
@pytest.mark.parametrize('caller_owned', [False, True])
def test_migration_shape_refusal_before_writes_preserves_pending_state(damage, caller_owned):
    con = historical(index=False)
    con.execute(damage)
    con.commit()
    if caller_owned:
        con.execute("INSERT INTO eval(run) VALUES ('pending')")
    before = snapshot(con)
    seen = []
    con.set_trace_callback(seen.append)
    with pytest.raises(ValueError):
        if caller_owned:
            migrations._decomp_schema_ownership(con)
        else:
            migrations.apply_pending(con)
    assert snapshot(con) == before
    assert con.in_transaction == caller_owned
    assert not any(sql.lstrip().upper().startswith(('CREATE ', 'ALTER ', 'INSERT ', 'UPDATE ', 'DELETE ')) for sql in seen)
    con.close()


@pytest.mark.parametrize('variant', ['view', 'virtual', 'default', 'pk', 'fk', 'check', 'collation', 'strict', 'without-rowid', 'type'])
def test_unrecognized_decomp_table_declaration_refuses_without_repair(variant):
    con = historical(shape='absent')
    ddl = {
        'view': 'CREATE VIEW decomp AS SELECT binary_id,addr FROM func',
        'virtual': 'CREATE VIRTUAL TABLE decomp USING fts5(skeleton_hash)',
        'default': LEGACY_DDL.replace('ok INTEGER', 'ok INTEGER DEFAULT 1'),
        'pk': LEGACY_DDL.replace('PRIMARY KEY (binary_id, addr)', 'PRIMARY KEY (addr, binary_id)'),
        'fk': LEGACY_DDL.replace('addr INTEGER NOT NULL', 'addr INTEGER NOT NULL REFERENCES func(addr)'),
        'check': LEGACY_DDL.replace('ok INTEGER', 'ok INTEGER CHECK(ok=1)'),
        'collation': LEGACY_DDL.replace('skeleton_hash TEXT', 'skeleton_hash TEXT COLLATE NOCASE'),
        'strict': LEGACY_DDL + ' STRICT',
        'without-rowid': LEGACY_DDL + ' WITHOUT ROWID',
        'type': LEGACY_DDL.replace('ok INTEGER', 'ok TEXT'),
    }[variant]
    con.execute(ddl)
    con.commit()
    # Virtual tables have hidden/shadow tables; only inspect schema at refusal.
    before = [tuple(row) for row in con.execute('SELECT * FROM main.sqlite_schema ORDER BY name')]
    with pytest.raises(ValueError):
        migrations.apply_pending(con)
    assert [tuple(row) for row in con.execute('SELECT * FROM main.sqlite_schema ORDER BY name')] == before
    assert ledger(con) == V10_LEDGER
    con.close()


@pytest.mark.parametrize('name', ['DeCoMp', 'DeCoMp_ScHeMa_StAtE', 'ScHeMa_MiGrAtIoN'])
@pytest.mark.parametrize('kind', ['TABLE', 'VIEW'])
@pytest.mark.parametrize('current', [False, True])
def test_temp_case_shadows_refuse_all_main_entrypoints_without_touching_caller(name, kind, current, pinned):
    con = historical()
    if current:
        migrations.apply_pending(con)
    con.execute(f'CREATE TEMP {kind} "{name}" ' + ('(payload TEXT)' if kind == 'TABLE' else "AS SELECT 'shadow' AS payload"))
    con.execute("INSERT INTO main.eval(run) VALUES ('caller')")
    before = snapshot(con)
    temp = [tuple(row) for row in con.execute('SELECT * FROM temp.sqlite_schema')]
    operations = [lambda: store.decomp_read_state(con), lambda: store.require_decomp_schema(con),
                  lambda: decompile.ensure_decomp_columns(con), lambda: decompile.persist_code(con, 1, 16, 'x'),
                  lambda: Binary(con, 1), lambda: _pcode_receipt(con, 1, 2)]
    if not current:
        operations.append(lambda: migrations._decomp_schema_ownership(con))
    for operation in operations:
        with pytest.raises(ValueError, match='shadowing'):
            operation()
        assert snapshot(con) == before
        assert con.in_transaction
        assert [tuple(row) for row in con.execute('SELECT * FROM temp.sqlite_schema')] == temp
    con.close()


@pytest.mark.parametrize('damage', [
    'DROP TABLE decomp', 'DROP INDEX ix_decomp_bin', 'DROP TABLE decomp_schema_state',
    'DELETE FROM decomp_schema_state',
    "UPDATE decomp_schema_state SET mode='absent'",
    "UPDATE decomp SET ast_fingerprint='' WHERE addr=16",
    'ALTER TABLE decomp_schema_state ADD COLUMN extra TEXT',
])
def test_claimed_current_damage_refuses_reader_writer_and_deletion(damage, pinned):
    con = historical()
    migrations.apply_pending(con)
    con.execute(damage)
    con.commit()
    con.execute("INSERT INTO eval(run) VALUES ('caller')")
    before = snapshot(con)
    for operation in (lambda: store.decomp_read_state(con), lambda: store.require_decomp_schema(con),
                      lambda: Binary(con, 1), lambda: _pcode_receipt(con, 1, 2),
                      lambda: decompile.ensure_decomp_columns(con), lambda: decompile.persist_code(con, 1, 16, 'x'),
                      lambda: delete_registry.remove_binary(con, slug='a')):
        with pytest.raises(ValueError):
            operation()
        assert snapshot(con) == before
        assert con.in_transaction
    con.close()


def test_v11_direct_repeat_and_v10_repeat_bind_versions_even_with_future_registry(monkeypatch):
    con = historical()
    con.execute('BEGIN IMMEDIATE')
    before = snapshot(con)
    migrations._stabs_schema_ownership(con)
    assert snapshot(con) == before
    con.rollback()
    migrations.apply_pending(con)
    monkeypatch.setattr(migrations, 'MIGRATIONS', migrations.MIGRATIONS + [migrations.Migration(12, 'future', lambda c: None)])
    monkeypatch.setattr(migrations, 'SCHEMA_VERSION', 12)
    con.execute("INSERT INTO eval(run) VALUES ('caller')")
    before = snapshot(con)
    migrations._decomp_schema_ownership(con)
    assert snapshot(con) == before
    assert con.in_transaction
    with pytest.raises(ValueError):
        migrations._stabs_schema_ownership(con)
    with pytest.raises(ValueError):
        store.require_decomp_schema(con)
    con.execute('DROP INDEX ix_decomp_bin')
    with pytest.raises(ValueError):
        migrations._decomp_schema_ownership(con)
    assert not con.execute("SELECT 1 FROM main.sqlite_schema WHERE name='ix_decomp_bin'").fetchone()
    con.close()


def test_tolerated_actual_v10_handles_refuse_writers_before_features(tmp_path, monkeypatch):
    path = tmp_path / 'busy.sqlite'
    historical(path).close()
    holder = sqlite3.connect(path)
    holder.execute('BEGIN IMMEDIATE')
    waiter = sqlite3.connect(path, timeout=0)
    readonly = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    monkeypatch.setattr(decompile, 'features', lambda *_a: pytest.fail('feature work before admission'))
    try:
        for con in (waiter, readonly):
            assert migrations.apply_pending(con) == []
            before = snapshot(con)
            for operation in (lambda: decompile.ensure_decomp_columns(con), lambda: decompile.persist_code(con, 1, 16, 'x')):
                with pytest.raises(ValueError, match='decomp schema required: observed version 10'):
                    operation()
            assert snapshot(con) == before
    finally:
        holder.close()
        waiter.close()
        readonly.close()


def test_ensure_participates_without_commit_and_absent_noop(tmp_path):
    path = tmp_path / 'ensure.sqlite'
    con = historical(path)
    migrations.apply_pending(con)
    con.execute("INSERT INTO eval(run) VALUES ('caller')")
    decompile.ensure_decomp_columns(con)
    assert store.decomp_read_state(con) == 'ast_fingerprint'
    assert con.in_transaction
    con.rollback()
    assert store.decomp_read_state(con) == 'skeleton_hash'
    assert con.execute('SELECT COUNT(*) FROM eval').fetchone()[0] == 0
    con.close()
    absent = store.connect(tmp_path / 'absent.sqlite')
    before = snapshot(absent)
    decompile.ensure_decomp_columns(absent)
    assert snapshot(absent) == before
    assert not absent.in_transaction
    absent.close()
    empty = sqlite3.connect(':memory:')
    decompile.ensure_decomp_columns(empty)
    assert empty.execute('SELECT COUNT(*) FROM sqlite_schema').fetchone()[0] == 0
    empty.close()


def test_attach_failure_closes_owned_handle_and_undoes_state(tmp_path, monkeypatch):
    con = historical(tmp_path / 'attach.sqlite')
    migrations.apply_pending(con)
    proxy = Failing(con, 'UPDATE main.decomp_schema_state')
    monkeypatch.setattr(decompile, 'connect', lambda path: proxy)
    with pytest.raises(RuntimeError, match='injected'):
        decompile.attach_store(tmp_path / 'attach.sqlite')
    with pytest.raises(sqlite3.ProgrammingError, match='closed'):
        con.execute('SELECT 1')
    with sqlite3.connect(tmp_path / 'attach.sqlite') as observer:
        assert observer.execute('SELECT mode FROM decomp_schema_state').fetchone()[0] == 'skeleton_hash'


@pytest.mark.parametrize('code', [None, '', 'x', ' \n'])
def test_independent_part_writer_keeps_payload_and_no_corpus_schema(tmp_path, pinned, code):
    path = tmp_path / 'part.sqlite'
    result = decompile.persist_part(path, '/independent', 16, code)
    assert result == ({'ok': 0, 'addr': 16} if not code else {'ok': 1, 'addr': 16, **FEATURES, 'ast_fingerprint': 'ASTv1:pinned-writer'})
    with sqlite3.connect(path) as con:
        assert [row[0] for row in con.execute("SELECT name FROM sqlite_schema WHERE type='table'")] == ['decomp_part']
        row = con.execute('SELECT * FROM decomp_part').fetchone()
        assert row[:3] == ('/independent', 16, int(bool(code)))
        if not code:
            assert row[3:] == (None,) * 12
        con.execute('ALTER TABLE decomp_part DROP COLUMN ast_fingerprint')
        decompile.ensure_decomp_columns(con)
        assert con.execute('SELECT ast_fingerprint FROM decomp_part').fetchone()[0] is None


@pytest.mark.parametrize('shape', ['corpus', 'mixed', 'raw-decomp'])
def test_part_destination_and_compatibility_dispatch_refuse_cross_domain(tmp_path, pinned, shape):
    path = tmp_path / 'mixed.sqlite'
    con = sqlite3.connect(path)
    if shape != 'raw-decomp':
        migrations.apply_pending(con)
    else:
        con.execute(LEGACY_DDL)
    if shape == 'mixed':
        con.executescript(decompile.PART_SCHEMA)
    con.commit()
    before = snapshot(con)
    with pytest.raises(ValueError):
        decompile.persist_part(path, '/p', 16, 'x')
    if shape != 'corpus':
        with pytest.raises(ValueError):
            decompile.ensure_decomp_columns(con)
    assert snapshot(con) == before
    con.close()


def test_matcher_input_v2_tracks_selector_and_selected_values_and_receipt_equality(tmp_path, monkeypatch):
    from agentdecompile_recovery.corpus.dashboard import preparation
    path = tmp_path / 'cache.sqlite'
    con = historical(path)
    migrations.apply_pending(con)
    monkeypatch.setattr(preparation, 'live_db', lambda: path)
    monkeypatch.setattr(preparation, '_directory', lambda: tmp_path)
    run = 'a' * 32
    before = preparation._matching_input_digests({'/a', '/b'})
    assert preparation._matching_input_digests({'/a', '/b'}) == before
    assert before['/a']['schema'] == 'matcher-input-v2'
    preparation.record_comparison_receipt(run, '/a', '/b', {'ok': True, 'jobId': 'job'}, before)
    assert preparation.read_comparison_receipt(run, '/a', '/b', before)
    decompile.ensure_decomp_columns(con)
    transitioned = preparation._matching_input_digests({'/a', '/b'})
    assert transitioned['/a']['digest'] != before['/a']['digest']
    assert preparation.read_comparison_receipt(run, '/a', '/b', transitioned) is None
    con.execute("UPDATE decomp SET ast_fingerprint='changed-ast' WHERE binary_id=1 AND addr=16")
    con.commit()
    changed = preparation._matching_input_digests({'/a', '/b'})
    assert changed['/a'] != transitioned['/a']
    assert changed['/b'] == transitioned['/b']
    con.execute("UPDATE binary SET variant='unrelated' WHERE id=3")
    con.commit()
    assert preparation._matching_input_digests({'/a', '/b'}) == changed
    old = {path: {**item, 'schema': 'matcher-input-v1'} for path, item in changed.items()}
    preparation.record_comparison_receipt(run, '/a', '/b', {'ok': True, 'jobId': 'old'}, old)
    assert preparation.read_comparison_receipt(run, '/a', '/b', changed) is None
    con.close()


@pytest.mark.parametrize('shape', ['absent', 'legacy', 'ast-create'])
def test_deletion_retains_global_state_even_after_last_binary(shape):
    con = historical(shape=shape)
    migrations.apply_pending(con)
    before = tuple(con.execute('SELECT rowid,* FROM decomp_schema_state').fetchone())
    for slug in ('a', 'b', 'c'):
        result = delete_registry.remove_binary(con, slug=slug)
        assert result['deleted']['binary'] == 1
        assert 'decomp_schema_state' not in result['deleted']
        assert tuple(con.execute('SELECT rowid,* FROM decomp_schema_state').fetchone()) == before
    assert con.execute('SELECT COUNT(*) FROM binary').fetchone()[0] == 0
    assert store.decomp_read_state(con) == (None if shape == 'absent' else 'skeleton_hash' if shape == 'legacy' else 'ast_fingerprint')
    con.close()


def test_failed_eleven_keeps_earlier_newly_committed_steps():
    con = sqlite3.connect(':memory:')
    with pytest.raises(RuntimeError, match='injected'):
        migrations.apply_pending(Failing(con, 'CREATE TABLE decomp_schema_state'))
    assert ledger(con) == V10_LEDGER
    assert con.execute('PRAGMA user_version').fetchone()[0] == 10
    assert not con.execute("SELECT 1 FROM sqlite_schema WHERE name IN ('decomp','decomp_schema_state','ix_decomp_bin')").fetchone()
    assert not con.in_transaction
    con.close()


@pytest.mark.parametrize('caller_owned', [False, True])
@pytest.mark.parametrize('shape', ['absent', 'legacy', 'ast-create'])
def test_pure_current_guards_never_mutate_or_commit(shape, caller_owned):
    con = historical(shape=shape)
    migrations.apply_pending(con)
    if caller_owned:
        con.execute("INSERT INTO eval(run) VALUES ('caller')")
    before = snapshot(con)
    seen = []
    con.set_trace_callback(seen.append)
    store.require_decomp_schema(con)
    assert store.decomp_read_state(con) == (None if shape == 'absent' else 'skeleton_hash' if shape == 'legacy' else 'ast_fingerprint')
    assert snapshot(con) == before
    assert con.in_transaction == caller_owned
    assert all(sql.lstrip().upper().startswith(('SELECT ', 'PRAGMA ')) for sql in seen)
    con.close()


@pytest.mark.parametrize('damage', [
    "UPDATE decomp_schema_state SET mode='unknown'",
    'UPDATE decomp_schema_state SET singleton=2',
    "INSERT INTO decomp_schema_state VALUES (2,'ast_fingerprint')",
    'ALTER TABLE decomp_schema_state RENAME TO DeCoMp_ScHeMa_StAtE',
])
def test_invalid_singleton_metadata_is_not_reconstructed(damage, pinned):
    con = historical()
    migrations.apply_pending(con)
    # Corruption is intentional; bypass CHECK enforcement only in the fixture.
    con.execute('PRAGMA ignore_check_constraints=ON')
    con.execute(damage)
    con.commit()
    con.execute('PRAGMA ignore_check_constraints=OFF')
    con.execute("INSERT INTO eval(run) VALUES ('caller')")
    before = snapshot(con)
    for operation in (lambda: store.decomp_read_state(con), lambda: store.require_decomp_schema(con),
                      lambda: migrations._decomp_schema_ownership(con),
                      lambda: decompile.persist_code(con, 1, 16, 'x'),
                      lambda: delete_registry.remove_binary(con, slug='a')):
        with pytest.raises(ValueError):
            operation()
        assert snapshot(con) == before
        assert con.in_transaction
    con.close()


def test_actual_future_twelve_is_not_admitted_by_frozen_readers_or_deletion(pinned):
    con = historical()
    future = migrations.MIGRATIONS + [migrations.Migration(12, 'future', lambda c: c.execute('CREATE TABLE future_owned(payload TEXT)'))]
    assert [step.version for step in migrations.apply_pending(con, migrations=future)] == [11, 12]
    assert ledger(con) == V11_LEDGER + [(12, 'future')]
    con.execute("INSERT INTO eval(run) VALUES ('caller')")
    before = snapshot(con)
    for operation in (lambda: store.decomp_read_state(con), lambda: store.require_decomp_schema(con),
                      lambda: Binary(con, 1), lambda: _pcode_receipt(con, 1, 2),
                      lambda: decompile.ensure_decomp_columns(con),
                      lambda: decompile.persist_code(con, 1, 16, 'x'),
                      lambda: delete_registry.remove_binary(con, slug='a')):
        with pytest.raises(ValueError):
            operation()
        assert snapshot(con) == before
        assert con.in_transaction
    con.close()


def test_current_readonly_decomp_damage_closes_without_repair(tmp_path, monkeypatch):
    path = tmp_path / 'current-damaged.sqlite'
    con = historical(path)
    migrations.apply_pending(con)
    con.execute('DELETE FROM decomp_schema_state')
    con.commit()
    before = snapshot(con)
    monkeypatch.setattr(migrations, 'apply_pending', lambda *_a, **_k: pytest.fail('read guard migrated'))
    monkeypatch.setattr(store, 'backfill_recovery_family', lambda *_a, **_k: pytest.fail('read guard backfilled'))
    with pytest.raises(store.SchemaCompatibilityError, match='decomp schema required'):
        store.connect(path, read_only=True)
    assert snapshot(con) == before
    con.close()


def test_canonical_main_alias_and_mutators_have_no_corpus_installer():
    assert decompile.MAIN_SCHEMA == store.DECOMP_TABLE_DDL + ';\n' + store.DECOMP_INDEX_SQL + ';\n'
    assert ' '.join(store.DECOMP_TABLE_DDL.split()) == ' '.join(AST_DDL.split())
    assert store.DECOMP_INDEX_SQL == INDEX_DDL
    assert store.DECOMP_COMPAT_STATE_DDL.strip() == STATE_DDL.strip()
    tree = ast.parse(Path(decompile.__file__).read_text())
    main_functions = {'persist_code', 'attach_store', 'ensure_decomp_columns', '_main_write_scope', '_materialize_main'}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in main_functions:
            for part in ast.walk(node):
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    assert not any(sql in part.value.upper() for sql in ('CREATE TABLE', 'ALTER TABLE', 'CREATE INDEX'))
                assert not (isinstance(part, ast.Attribute) and part.attr == 'executescript')
    migration_tree = ast.parse(Path(migrations.__file__).read_text())
    step = next(node for node in migration_tree.body if isinstance(node, ast.FunctionDef) and node.name == '_decomp_schema_ownership')
    names = {node.id for node in ast.walk(step) if isinstance(node, ast.Name)}
    attrs = {node.attr for node in ast.walk(step) if isinstance(node, ast.Attribute)}
    assert not ({'features', 'syntax_fingerprint', 'hashlib', 'decompile', 'extract', 'backfill_recovery_family'} & (names | attrs))


def test_migration_cleanup_failure_propagates_without_rollback_claim():
    con = historical()
    with pytest.raises(RuntimeError, match='injected cleanup failure'):
        migrations.apply_pending(Failing(con, 'ALTER TABLE main.decomp', cleanup=True))
    assert con.in_transaction
    # Fixture cleanup is separate from the failed cleanup under inspection.
    con.rollback()
    assert ledger(con) == V10_LEDGER
    con.close()


def test_migration_committed_but_unacknowledged_is_not_claimed_rolled_back():
    con = historical()
    with pytest.raises(RuntimeError, match='injected operation failure'):
        migrations.apply_pending(Failing(con, 'COMMIT', committed=True))
    assert not con.in_transaction
    assert ledger(con) == V11_LEDGER
    assert con.execute('PRAGMA user_version').fetchone()[0] == 11
    assert store.decomp_read_state(con) == 'skeleton_hash'
    con.close()


@pytest.mark.parametrize('operation', ['attach', 'persist-success', 'persist-failed'])
def test_explicit_absent_materialization_installs_logical_witness(tmp_path, pinned, operation):
    path = tmp_path / 'absent-materialize.sqlite'
    con = historical(path, shape='absent')
    migrations.apply_pending(con)
    assert store.decomp_read_state(con) is None
    assert _pcode_receipt(con, 1, 2) == {'skipped': True, 'reason': 'pcode_fingerprints_not_extracted'}
    if operation == 'attach':
        decompile.attach_store(path).close()
    else:
        decompile.persist_code(con, 1, 16, 'x' if operation == 'persist-success' else None)
    assert store.decomp_read_state(con) == 'ast_fingerprint'
    assert con.execute('SELECT COUNT(*) FROM decomp').fetchone()[0] == int(operation != 'attach')
    assert con.execute('SELECT COUNT(*) FROM decomp WHERE ok=1').fetchone()[0] == int(operation == 'persist-success')
    assert _pcode_receipt(con, 1, 2)['available'] is False
    con.close()


@pytest.mark.parametrize('name', ['DeCoMp_PaRt', 'BiNaRy', 'ScHeMa_MiGrAtIoN', 'DeCoMp'])
@pytest.mark.parametrize('kind', ['TABLE', 'VIEW'])
def test_independent_part_temp_shadows_refuse_compatibility_helper(name, kind):
    con = sqlite3.connect(':memory:')
    con.executescript(decompile.PART_SCHEMA)
    con.execute('ALTER TABLE decomp_part DROP COLUMN ast_fingerprint')
    con.execute(f'CREATE TEMP {kind} "{name}" ' + ('(payload TEXT)' if kind == 'TABLE' else "AS SELECT 'shadow' AS payload"))
    before = snapshot(con)
    temp = [tuple(row) for row in con.execute('SELECT * FROM temp.sqlite_schema')]
    with pytest.raises(ValueError, match='shadowing'):
        decompile.ensure_decomp_columns(con)
    assert snapshot(con) == before
    assert [tuple(row) for row in con.execute('SELECT * FROM temp.sqlite_schema')] == temp
    con.close()


@pytest.mark.parametrize('name', ['DeCoMp_PaRt', 'BiNaRy', 'ScHeMa_MiGrAtIoN', 'DeCoMp'])
def test_part_destination_reserved_mixed_case_refuses_before_schema_install(tmp_path, pinned, name):
    path = tmp_path / 'part-reserved.sqlite'
    con = sqlite3.connect(path)
    con.execute(f'CREATE TABLE "{name}" (payload TEXT)')
    con.execute(f"INSERT INTO \"{name}\" VALUES ('retained')")
    con.commit()
    before = snapshot(con)
    with pytest.raises(ValueError, match='unsupported decomp object spelling'):
        decompile.persist_part(path, '/p', 16, 'x')
    assert snapshot(con) == before
    con.close()


def test_writer_revalidates_after_feature_work_before_first_mutation(monkeypatch):
    con = historical()
    migrations.apply_pending(con)
    rows = [tuple(row) for row in con.execute('SELECT rowid,* FROM decomp ORDER BY rowid')]
    def changed_during_features(_code):
        # A changed destination cannot inherit the earlier admission decision.
        con.execute('DROP INDEX ix_decomp_bin')
        return dict(FEATURES)
    monkeypatch.setattr(decompile, 'features', changed_during_features)
    monkeypatch.setattr(decompile, 'syntax_fingerprint', lambda _code: 'ASTv1:pinned-writer')
    with pytest.raises(ValueError, match='missing decomp index'):
        decompile.persist_code(con, 1, 16, 'x')
    assert [tuple(row) for row in con.execute('SELECT rowid,* FROM decomp ORDER BY rowid')] == rows
    assert con.execute('SELECT mode FROM decomp_schema_state').fetchone()[0] == 'skeleton_hash'
    assert not con.in_transaction
    con.close()
