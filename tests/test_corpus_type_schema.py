"""Task2.6 regression specifications: AUTHORED, NOT RUN.

Real historical runner prefixes, independently frozen DDL, and actual writers.
Synthetic producer/syscall faults establish fixture intent, not runtime evidence.
"""
from __future__ import annotations

import sqlite3
import sys
from contextlib import contextmanager
from types import ModuleType, SimpleNamespace

import pytest

from agentdecompile_recovery.corpus import export_types as et
from agentdecompile_recovery.corpus import migrations, propagate_types as pt, store

TYPE6 = '''CREATE TABLE IF NOT EXISTS ghidra_type (
    binary_id INTEGER NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL,
    size INTEGER, definition TEXT NOT NULL, n_fields INTEGER,
    PRIMARY KEY (binary_id, name, kind)
)'''
TYPE7 = TYPE6.replace('    PRIMARY KEY', '    origin TEXT,\n    PRIMARY KEY')
ORIGIN = '''CREATE TABLE IF NOT EXISTS ghidra_type_origin (
    binary_id INTEGER NOT NULL, name TEXT NOT NULL, donor_slug TEXT NOT NULL,
    donor_game TEXT, size INTEGER, PRIMARY KEY (binary_id, name)
)'''
INDEX = 'CREATE INDEX IF NOT EXISTS ix_ghidra_type_bin ON ghidra_type(binary_id)'
LEDGER12 = list(enumerate(('baseline', 'analyzer_identity', 'basis_supersession', 'match_review',
    'function_storage', 'typed_fields', 'matching_evidence', 'pcode_channel', 'match_metadata',
    'stabs_schema_ownership', 'decomp_schema_ownership', 'convention_schema_ownership'), 1))
LEDGER13 = LEDGER12 + [(13, 'type_schema_ownership')]
FIELD_JSON = '{"kind":"array","count":2,"element":{"kind":"pointer","target":"Nested"}}'
FIELD = (1, 'Layout', 0, 4, 8, 'items', 'array', None, None, 'Nested *', 2, FIELD_JSON)
NATIVE = [(1, 'Layout', 'struct', 12, 'struct Layout { int field; };', 1),
          (1, 'Second', 'union', 4, 'union Second { int field; };', 1)]
ADOPTIONS = [(1, 'Layout', 'struct Layout { int field; };', 12, 'donor', 'game', 'same_game'),
             (1, 'Second', 'union Second { int field; };', 4, 'donor', 'game', 'same_game')]


def rows(con, table):
    ddl = con.execute('SELECT sql FROM main.sqlite_schema WHERE name=?', (table,)).fetchone()
    if ddl and 'WITHOUT ROWID' in (ddl[0] or '').upper():
        return sorted((tuple(r) for r in con.execute(f'SELECT * FROM main."{table}"')), key=repr)
    return [tuple(r) for r in con.execute(f'SELECT rowid,* FROM main."{table}" ORDER BY rowid')]


def snapshot(con):
    objects = [tuple(r) for r in con.execute('SELECT type,name,tbl_name,sql FROM main.sqlite_schema ORDER BY name,type')]
    return migrations.user_version(con), objects, {name: rows(con, name) for kind, name, _, _ in objects
                                                if kind == 'table' and not name.startswith('sqlite_')}


def ledger(con):
    return [tuple(r) for r in con.execute('SELECT version,name FROM schema_migration ORDER BY version')]


def historical(path=':memory:', *, shape='absent', origin=False, index=True, populated=False):
    con = sqlite3.connect(path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    migrations.apply_pending(con, target=12)
    assert ledger(con) == LEDGER12
    for bid, slug, game in ((1, 'recipient', 'game'), (2, 'donor', 'game'), (3, 'foreign', 'other')):
        con.execute('INSERT INTO binary(id,repo_path,slug,game,content_sha256,language_id) VALUES (?,?,?,?,?,?)',
                    (bid, '/' + slug, slug, game, str(bid) * 64, 'x86:LE:32:default'))
    if shape != 'absent':
        con.execute(TYPE7 if shape == 'seven-create' else TYPE6)
        if shape == 'seven-alter':
            con.execute('ALTER TABLE ghidra_type ADD COLUMN origin TEXT')
        if index:
            con.execute(INDEX)
        if populated:
            for i, provenance in enumerate((None, 'native', 'adopted:old', '', 'unknown-origin')):
                con.execute('INSERT INTO ghidra_type(binary_id,name,kind,size,definition,n_fields) VALUES (?,?,?,?,?,?)',
                            (1, 'Layout' if i == 0 else f'Type{i}', 'struct', 12 + i, f'definition-{i}', None))
                if shape.startswith('seven'):
                    con.execute('UPDATE ghidra_type SET origin=? WHERE name=?',
                                (provenance, 'Layout' if i == 0 else f'Type{i}'))
            con.execute("INSERT INTO ghidra_type(binary_id,name,kind,size,definition,n_fields) VALUES (1,'Layout','union',12,'union-old',1)")
    if origin:
        con.execute(ORIGIN)
        if populated:
            con.execute("INSERT INTO ghidra_type_origin VALUES (1,'Layout','unknown-donor',NULL,NULL)")
    con.execute('INSERT INTO ghidra_field VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', FIELD)
    con.commit()
    return con


def current(path=':memory:', *, installed=False):
    con = historical(path, shape='seven-create' if installed else 'absent')
    migrations.apply_pending(con)
    assert ledger(con) == LEDGER13
    return con


def future(con):
    registry = migrations.MIGRATIONS + [migrations.Migration(14, 'future_type_probe', lambda _c: None)]
    migrations.apply_pending(con, migrations=registry)
    return con


def assert_read_only(trace):
    assert not any(sql.lstrip().upper().startswith(('BEGIN', 'SAVEPOINT', 'RELEASE', 'COMMIT',
        'ROLLBACK', 'CREATE', 'ALTER', 'DROP', 'INSERT', 'UPDATE', 'DELETE')) for sql in trace)


@pytest.mark.parametrize('shape', ['absent', 'six', 'seven-create', 'seven-alter'])
@pytest.mark.parametrize('origin', [False, True])
@pytest.mark.parametrize('index', [False, True])
@pytest.mark.parametrize('populated', [False, True])
def test_actual_twelve_adoption_preserves_rows_fields_origins_and_installation_history(shape, origin, index, populated):
    con = historical(shape=shape, origin=origin, index=index, populated=populated)
    con.execute('ALTER TABLE binary ADD COLUMN unrelated TEXT')
    con.execute('CREATE TABLE extension(payload TEXT)')
    con.execute("INSERT INTO extension VALUES ('keep')")
    con.execute("UPDATE schema_migration SET basis_hash=CASE WHEN version % 2 = 0 THEN NULL ELSE 'historical-basis' END")
    con.commit()
    before = snapshot(con)
    if shape == 'absent' and origin:
        with pytest.raises(ValueError, match='type origin without parent'):
            migrations.apply_pending(con)
        assert snapshot(con) == before
    else:
        assert [step.version for step in migrations.apply_pending(con)] == [13]
        after = snapshot(con)
        assert ledger(con) == LEDGER13
        for name, old in before[2].items():
            actual = after[2][name]
            if name == 'schema_migration':
                actual = actual[:12]
            elif name == 'ghidra_type' and shape == 'six':
                assert all(r[-1] is None for r in actual)
                actual = [r[:-1] for r in actual]
            assert actual == old, name
        assert store.type_inventory_state(con) == ('absent' if shape == 'absent' else 'installed')
        assert rows(con, 'ghidra_field') == before[2]['ghidra_field']
        assert store.decomp_read_state(con) is None
        store.require_convention_schema(con)
        store.require_type_schema(con)
    con.close()


@pytest.mark.parametrize('mode', ['absent', 'skeleton_hash', 'ast_fingerprint'])
def test_type_migration_preserves_existing_decomp_selector_and_witness(mode):
    con = historical()
    con.execute('UPDATE decomp_schema_state SET mode=?', (mode,))
    if mode != 'absent':
        con.execute('INSERT INTO decomp(binary_id,addr,ok,skeleton_hash,ast_fingerprint) VALUES (1,16,1,?,?)',
                    ('old', '' if mode == 'ast_fingerprint' else None))
    con.commit()
    before = rows(con, 'decomp'), rows(con, 'decomp_schema_state')
    migrations.apply_pending(con)
    assert (rows(con, 'decomp'), rows(con, 'decomp_schema_state')) == before
    assert store.decomp_read_state(con) == (None if mode == 'absent' else mode)
    con.close()


BAD_TYPES = [TYPE6.replace('size INTEGER', 'size TEXT'),
    TYPE6.replace('size INTEGER', 'size INTEGER DEFAULT 0'),
    TYPE6.replace('name TEXT NOT NULL', 'name TEXT NOT NULL COLLATE NOCASE'),
    TYPE6.replace('PRIMARY KEY (binary_id, name, kind)', 'PRIMARY KEY (binary_id, name)'),
    TYPE6.replace('size INTEGER, definition TEXT NOT NULL', 'definition TEXT NOT NULL, size INTEGER'),
    TYPE6.replace('size INTEGER', 'size INTEGER GENERATED ALWAYS AS (binary_id) VIRTUAL'),
    TYPE6.replace('n_fields INTEGER', 'n_fields INTEGER, extra TEXT'),
    TYPE6 + ' STRICT', TYPE6 + ' WITHOUT ROWID',
    'CREATE VIEW ghidra_type AS SELECT 1 AS binary_id',
    'CREATE VIRTUAL TABLE ghidra_type USING fts5(payload)']


@pytest.mark.parametrize('ddl', BAD_TYPES)
def test_unknown_pre13_shapes_refuse_before_migration_without_repair(ddl):
    con = historical()
    con.execute(ddl)
    con.commit()
    before = snapshot(con)
    with pytest.raises(ValueError, match='type'):
        migrations.apply_pending(con)
    assert snapshot(con) == before and not con.in_transaction
    con.close()


@pytest.mark.parametrize('damage', [
    'DROP TABLE ghidra_field', 'ALTER TABLE ghidra_field ADD COLUMN extra TEXT',
    'CREATE TABLE type_inventory_state(singleton INTEGER,mode TEXT)',
    'CREATE INDEX ix_ghidra_type_bin ON binary(slug)',
    'CREATE INDEX extra_type_index ON ghidra_type(name)',
    'CREATE TRIGGER extra_field_trigger AFTER INSERT ON ghidra_field BEGIN SELECT 1; END',
    'CREATE TEMP TRIGGER side_effect AFTER INSERT ON main.ghidra_type BEGIN DELETE FROM ghidra_field; END',
])
def test_field_dependency_and_reserved_objects_refuse_adoption(damage):
    con = historical(shape='six', index=False)
    con.execute(damage)
    con.commit()
    before = snapshot(con)
    with pytest.raises(ValueError, match='type'):
        migrations.apply_pending(con)
    assert snapshot(con) == before
    con.close()


@pytest.mark.parametrize('name', ['binary', 'schema_migration', 'ghidra_type', 'ghidra_type_origin',
                                  'ghidra_field', 'type_inventory_state', 'ix_ghidra_type_bin'])
@pytest.mark.parametrize('kind', ['TABLE', 'VIEW'])
def test_mixed_case_temp_reserved_names_refuse_before_planning_and_preserve_pending(name, kind, monkeypatch):
    con = current()
    con.execute(f'CREATE TEMP {kind} {name.upper()} ' + ('(value TEXT)' if kind == 'TABLE' else 'AS SELECT 1 AS value'))
    con.commit()
    con.execute("INSERT INTO eval(run) VALUES ('caller')")
    before = snapshot(con)
    monkeypatch.setattr(pt, '_targets', lambda *_a, **_k: pytest.fail('config before admission'))
    with pytest.raises(ValueError, match='shadowing type'):
        pt.plan_adoptions(con)
    assert snapshot(con) == before and con.in_transaction
    con.close()


@pytest.mark.parametrize('damage', ['DELETE FROM type_inventory_state', 'DROP TABLE ghidra_type_origin',
    'DROP INDEX ix_ghidra_type_bin', "UPDATE schema_migration SET name='wrong' WHERE version=13",
    "INSERT INTO ghidra_type(binary_id,name,kind,definition) VALUES (1,'bad','struct','bad')",
    "INSERT INTO ghidra_type_origin VALUES (1,'bad','old',NULL,NULL)"])
def test_current_shape_or_state_corruption_never_materializes_or_runs_producer(damage):
    con = current()
    con.execute(damage)
    con.execute("INSERT INTO eval(run) VALUES ('caller')")
    before = snapshot(con)
    trace = []
    con.set_trace_callback(trace.append)
    with pytest.raises(ValueError, match='type schema required: observed version 13'):
        et.export('/recipient', con, start=lambda: pytest.fail('producer before guard'))
    assert_read_only(trace)
    assert snapshot(con) == before and con.in_transaction
    con.close()


def test_current_guard_and_planner_are_pure_with_unrelated_extensions_and_scratch():
    con = current()
    con.execute('CREATE TEMP TABLE scratch(value TEXT)')
    con.execute('CREATE TABLE extension(value TEXT)')
    con.execute("INSERT INTO extension VALUES ('pending')")
    before = snapshot(con)
    trace = []
    con.set_trace_callback(trace.append)
    store.require_type_schema(con)
    result = pt.plan_adoptions(con, targets=['/recipient', '/donor'])
    assert result == {'stats': {}, 'adopted': [], 'binaries': [
        {'repo_path': '/recipient', 'slug': 'recipient', 'native': 0, 'adopt': 0, 'after': 0},
        {'repo_path': '/donor', 'slug': 'donor', 'native': 0, 'adopt': 0, 'after': 0}]}
    assert_read_only(trace)
    assert snapshot(con) == before and con.in_transaction
    con.close()


def test_planner_preserves_null_native_filter_and_exact_selected_donor_payload():
    con = current(installed=True)
    for name, origin in [('Null', None), ('Native', 'native'), ('Adopted', 'adopted:old'), ('Unknown', 'unknown'), ('Empty', '')]:
        con.execute('INSERT INTO ghidra_type VALUES (2,?,\'struct\',4,?,1,?)', (name, f'def-{name}', origin))
    con.commit()
    before = snapshot(con)
    plan = pt.plan_adoptions(con, targets=['/recipient', '/donor'])
    assert sorted(plan['adopted']) == [(1, name, f'def-{name}', 4, 'donor', 'game', 'same_game') for name in ('Native', 'Null')]
    assert plan['stats'] == {'adopted_same_game': 2, 'already_native': 2}
    assert snapshot(con) == before and not con.in_transaction
    con.close()


class Fault:
    def __init__(self, con, prefix, *, occurrence=1, after=True, interrupt=False, cleanup='', committed=False, lost=False):
        self.con, self.prefix, self.occurrence = con, prefix, occurrence
        self.after, self.cleanup, self.committed, self.lost = after, cleanup, committed, lost
        self.count = 0
        self.failure = KeyboardInterrupt('injected') if interrupt else RuntimeError('injected')

    def __getattr__(self, name):
        return getattr(self.con, name)

    def execute(self, sql, *args):
        if self.cleanup and sql.strip().startswith(self.cleanup):
            raise RuntimeError('cleanup failed')
        statement = sql.strip()
        hit = statement.startswith(self.prefix)
        if hit and self.prefix.endswith('ghidra_type') and statement[len(self.prefix):].startswith('_'):
            hit = False
        if hit:
            self.count += 1
        fault = hit and self.count == self.occurrence
        if fault and not self.after and not (sql == 'COMMIT' and self.committed):
            raise self.failure
        result = self.con.execute(sql, *args)
        if fault:
            if self.lost:
                self.con.rollback()
            raise self.failure
        return result

    def executemany(self, sql, payload):
        for row in payload:
            self.execute(sql, row)

    def commit(self):
        if self.prefix == 'COMMIT':
            if self.committed:
                self.con.commit()
            raise self.failure
        return self.con.commit()

    def rollback(self):
        if self.cleanup == 'ROLLBACK':
            raise RuntimeError('cleanup failed')
        return self.con.rollback()


@pytest.fixture
def capture_model(monkeypatch):
    """Synthetic Ghidra producer objects; actual export persistence is exercised."""
    class Structure:
        def __init__(self, name='Layout'):
            self.name = name
        def getName(self): return self.name
        def getPathName(self): return '/' + self.name
        def getLength(self): return 12
    class Union: pass
    class Enum: pass
    for name in ('ghidra', 'ghidra.program', 'ghidra.program.model', 'ghidra.program.model.data'):
        module = ModuleType(name)
        monkeypatch.setitem(sys.modules, name, module)
    data = sys.modules['ghidra.program.model.data']
    data.Structure, data.Union, data.Enum = Structure, Union, Enum
    monkeypatch.setattr(et, 'emit_struct', lambda dt: (f'struct {dt.name} {{ int field; }};', 1))
    monkeypatch.setattr(et, 'field_rows', lambda _dt: [{'ordinal': 0, 'offset': 4, 'size': 8,
        'name': 'items', 'dt_kind': 'array', 'pointee_type': None, 'composite_type': None,
        'element_type': 'Nested *', 'array_count': 2, 'type': {'kind': 'array', 'count': 2}}])
    items = [Structure(), Structure('Second')]
    @contextmanager
    def opener(_path):
        yield SimpleNamespace(getDataTypeManager=lambda: SimpleNamespace(getAllDataTypes=lambda: iter(items)))
    return items, opener


def operate(kind, con, capture_model=None):
    if kind == 'native':
        return et.insert_native_types(con, NATIVE)
    if kind == 'adoption':
        return pt.apply_adoptions(con, ADOPTIONS)
    return et.export('/recipient', con, start=lambda: True, open_program=capture_model[1])


@pytest.mark.parametrize('kind', ['native', 'adoption', 'export'])
@pytest.mark.parametrize('caller', [False, True])
def test_actual_writer_success_materializes_and_commits_caller_durably(tmp_path, kind, caller, capture_model):
    path = tmp_path / 'writer.sqlite'
    con = current(path)
    if caller:
        con.execute("INSERT INTO eval(run) VALUES ('caller')")
    unaffected = rows(con, 'binary'), rows(con, 'decomp_schema_state')
    operate(kind, con, capture_model)
    assert not con.in_transaction
    other = sqlite3.connect(path)
    assert other.execute('SELECT mode FROM type_inventory_state').fetchone()[0] == 'installed'
    assert other.execute('SELECT COUNT(*) FROM ghidra_type').fetchone()[0] == 2
    assert other.execute("SELECT COUNT(*) FROM eval WHERE run='caller'").fetchone()[0] == int(caller)
    assert (rows(other, 'binary'), rows(other, 'decomp_schema_state')) == unaffected
    other.close()
    con.close()


@pytest.mark.parametrize('kind', ['native', 'adoption', 'export'])
def test_empty_success_materializes_but_no_program_does_not(kind, capture_model):
    con = current()
    before = snapshot(con)
    assert et.export('/recipient', con, start=lambda: False)['reason'] == 'no-program'
    assert snapshot(con) == before
    con.execute("INSERT INTO eval(run) VALUES ('caller')")
    if kind == 'native': et.insert_native_types(con, [])
    elif kind == 'adoption': pt.apply_adoptions(con, [])
    else:
        capture_model[0].clear()
        operate(kind, con, capture_model)
    assert store.type_inventory_state(con) == 'installed'
    assert not con.in_transaction and not rows(con, 'ghidra_type')
    assert len(rows(con, 'eval')) == 1
    con.close()


def test_native_ignore_and_export_replace_keep_distinct_origin_and_field_semantics(capture_model):
    con = current(installed=True)
    con.execute("INSERT INTO ghidra_type VALUES (1,'Layout','struct',99,'curated',7,'unknown-origin')")
    con.execute("INSERT INTO ghidra_type_origin VALUES (1,'Layout','historic-donor','old',99)")
    con.execute("INSERT INTO ghidra_type VALUES (2,'Other','struct',8,'unaffected',NULL,'native')")
    con.commit()
    origins, fields = rows(con, 'ghidra_type_origin'), rows(con, 'ghidra_field')
    assert et.insert_native_types(con, NATIVE) == 1
    assert tuple(con.execute("SELECT size,definition,origin FROM ghidra_type WHERE name='Layout'").fetchone()) == (99, 'curated', 'unknown-origin')
    assert rows(con, 'ghidra_type_origin') == origins and rows(con, 'ghidra_field') == fields
    operate('export', con, capture_model)
    assert tuple(con.execute("SELECT size,definition,origin FROM ghidra_type WHERE name='Layout'").fetchone()) == (12, 'struct Layout { int field; };', None)
    assert rows(con, 'ghidra_type_origin') == origins
    assert tuple(con.execute("SELECT definition,origin FROM ghidra_type WHERE binary_id=2").fetchone()) == ('unaffected', 'native')
    assert tuple(con.execute("SELECT offset,size,name,dt_kind,element_type,array_count,type_json FROM ghidra_field WHERE type_name='Layout'").fetchone()) == (4, 8, 'items', 'array', 'Nested *', 2, '{"count": 2, "kind": "array"}')
    con.close()


@pytest.mark.parametrize('kind,prefix', [
    ('native', 'INSERT OR IGNORE INTO main.ghidra_type'),
    ('adoption', 'INSERT OR REPLACE INTO main.ghidra_type'),
    ('adoption', 'INSERT OR REPLACE INTO main.ghidra_type_origin'),
    ('export', 'INSERT OR REPLACE INTO main.ghidra_type'),
    ('export', 'DELETE FROM main.ghidra_field'), ('export', 'INSERT INTO main.ghidra_field'),
    ('native', 'UPDATE main.type_inventory_state'), ('adoption', 'COMMIT'), ('export', 'COMMIT'),
])
@pytest.mark.parametrize('caller', [False, True])
@pytest.mark.parametrize('interrupt', [False, True])
def test_writer_failure_undoes_owned_rows_state_and_fields_only(kind, prefix, caller, interrupt, capture_model):
    con = current()
    if caller: con.execute("INSERT INTO eval(run) VALUES ('caller')")
    before = snapshot(con)
    with pytest.raises(KeyboardInterrupt if interrupt else RuntimeError, match='injected'):
        operate(kind, Fault(con, prefix, occurrence=2 if prefix.startswith('INSERT') else 1, interrupt=interrupt), capture_model)
    assert snapshot(con) == before and con.in_transaction == caller
    con.rollback()
    assert not rows(con, 'eval')
    con.close()


@pytest.mark.parametrize('prefix', ['CREATE TABLE IF NOT EXISTS ghidra_type', 'ALTER TABLE main.ghidra_type',
    'CREATE TABLE IF NOT EXISTS ghidra_type_origin', 'CREATE INDEX IF NOT EXISTS ix_ghidra_type_bin',
    'CREATE TABLE type_inventory_state', 'INSERT INTO main.type_inventory_state',
    'INSERT OR IGNORE INTO schema_migration', 'PRAGMA user_version = 13', 'COMMIT'])
def test_pending_thirteen_rolls_back_without_changing_twelve(prefix):
    con = historical(shape='six' if prefix.startswith('ALTER') else 'absent')
    before = snapshot(con)
    proxy = Fault(con, prefix, after=prefix != 'COMMIT')
    with pytest.raises(RuntimeError, match='injected'):
        migrations.apply_pending(proxy)
    assert snapshot(con) == before and not con.in_transaction
    assert ledger(con) == LEDGER12
    con.close()


def test_fresh_runner_retains_committed_one_through_twelve_when_thirteen_fails():
    con = sqlite3.connect(':memory:')
    with pytest.raises(RuntimeError, match='injected'):
        migrations.apply_pending(Fault(con, 'CREATE TABLE type_inventory_state'))
    assert ledger(con) == LEDGER12 and migrations.user_version(con) == 12
    assert not con.execute("SELECT 1 FROM sqlite_schema WHERE name='ghidra_type'").fetchone()
    assert not con.in_transaction
    con.close()


@pytest.mark.parametrize('caller', [False, True])
def test_scope_creation_failure_and_schema_change_during_payload_staging(caller):
    con = current()
    if caller: con.execute("INSERT INTO eval(run) VALUES ('caller')")
    before = snapshot(con)
    with pytest.raises(RuntimeError, match='injected'):
        et.insert_native_types(Fault(con, 'SAVEPOINT' if caller else 'BEGIN IMMEDIATE', after=False, cleanup='ROLLBACK'), NATIVE)
    assert snapshot(con) == before and con.in_transaction == caller
    def payload():
        con.execute('CREATE INDEX late_change ON ghidra_type(name)')
        yield NATIVE[0]
    with pytest.raises(ValueError, match='undeclared type object late_change'):
        et.insert_native_types(con, payload())
    assert not rows(con, 'ghidra_type')
    assert con.in_transaction == caller
    con.close()


@pytest.mark.parametrize('cleanup', ['ROLLBACK', 'ROLLBACK TO', 'RELEASE'])
def test_cleanup_failure_does_not_claim_successful_rollback(cleanup):
    con = current()
    if cleanup != 'ROLLBACK': con.execute("INSERT INTO eval(run) VALUES ('caller')")
    with pytest.raises(RuntimeError, match='cleanup failed'):
        et.insert_native_types(Fault(con, 'INSERT OR IGNORE INTO main.ghidra_type', cleanup=cleanup), NATIVE)
    assert con.in_transaction
    con.rollback()
    con.close()


@pytest.mark.parametrize('committed', [False, True])
def test_lost_transaction_and_commit_acknowledgement_are_explicitly_uncertain(tmp_path, committed):
    path = tmp_path / 'uncertain.sqlite'
    con = current(path)
    con.execute("INSERT INTO eval(run) VALUES ('caller')")
    proxy = Fault(con, 'COMMIT' if committed else 'INSERT OR IGNORE INTO main.ghidra_type',
                  committed=committed, lost=not committed)
    with pytest.raises(RuntimeError, match='durability/rollback is uncertain'):
        et.insert_native_types(proxy, NATIVE)
    assert not con.in_transaction
    other = sqlite3.connect(path)
    assert len(rows(other, 'eval')) == int(committed)
    assert len(rows(other, 'ghidra_type')) == (2 if committed else 0)
    other.close()
    con.close()


@pytest.mark.parametrize('payload', [[NATIVE[0], (1, 'Bad')], [NATIVE[0], (1, 'Bad', 'struct', 4, None, 0)]])
def test_native_invalid_batch_never_partially_accepts_or_commits(payload):
    con = current()
    con.execute("INSERT INTO eval(run) VALUES ('caller')")
    before = snapshot(con)
    with pytest.raises(ValueError, match='native type batch'):
        et.insert_native_types(con, payload)
    assert snapshot(con) == before and con.in_transaction
    con.close()


def test_actual_old_tolerated_and_future_handles_refuse_before_producers(tmp_path):
    path = tmp_path / 'old.sqlite'
    historical(path).close()
    holder = sqlite3.connect(path)
    holder.execute('BEGIN IMMEDIATE')
    waiter = sqlite3.connect(path, timeout=0)
    readonly = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        for con in (waiter, readonly):
            assert migrations.apply_pending(con) == []
            for operation in (lambda: pt.plan_adoptions(con), lambda: pt.apply_adoptions(con, []),
                              lambda: et.insert_native_types(con, []),
                              lambda: et.export('/recipient', con, start=lambda: pytest.fail('premature producer'))):
                with pytest.raises(ValueError, match='type schema required.*version 12'):
                    operation()
        holder.rollback()
        assert [step.version for step in migrations.apply_pending(waiter)] == [13]
    finally:
        holder.close(); waiter.close(); readonly.close()
    con = future(current())
    before = snapshot(con)
    with pytest.raises(ValueError, match='type schema required.*version 14'):
        et.insert_native_types(con, NATIVE)
    assert snapshot(con) == before
    con.close()


@pytest.mark.parametrize('version', [10, 11, 12, 13])
def test_direct_repeat_remains_frozen_under_future_registry(monkeypatch, version):
    con = sqlite3.connect(':memory:')
    migrations.apply_pending(con, target=version)
    monkeypatch.setattr(migrations, 'MIGRATIONS', migrations.MIGRATIONS + [migrations.Migration(14, 'future_type_probe', lambda _c: None)])
    monkeypatch.setattr(migrations, 'SCHEMA_VERSION', 14)
    con.execute("INSERT INTO eval(run) VALUES ('caller')")
    before = snapshot(con)
    {10: migrations._stabs_schema_ownership, 11: migrations._decomp_schema_ownership,
     12: migrations._convention_schema_ownership, 13: migrations._type_schema_ownership}[version](con)
    assert snapshot(con) == before and con.in_transaction
    if version == 13:
        con.execute('DELETE FROM type_inventory_state')
        before = snapshot(con)
        with pytest.raises(ValueError, match='singleton'):
            migrations._type_schema_ownership(con)
        assert snapshot(con) == before
    con.close()


def test_adoption_notes_selected_keys_and_unaffected_cross_kind_rows():
    con = current(installed=True)
    con.execute("INSERT INTO ghidra_type VALUES (1,'Layout','union',19,'keep-union',2,'native')")
    con.execute("INSERT INTO ghidra_type VALUES (3,'Layout','struct',19,'keep-other',2,'unknown')")
    con.commit()
    fields = rows(con, 'ghidra_field')
    assert pt.apply_adoptions(con, ADOPTIONS) == 2
    for bid, name, definition, size, donor, game, kind in ADOPTIONS:
        note = (f'/* layout adopted from {donor} ({kind}); this binary had no\n'
                f'   definition of its own, and every donor agreed on size 0x{size:x}. */\n')
        assert tuple(con.execute("SELECT size,definition,n_fields,origin FROM ghidra_type WHERE binary_id=? AND name=? AND kind='struct'", (bid, name)).fetchone()) == (size, note + definition, 0, 'adopted:donor')
        assert tuple(con.execute('SELECT donor_slug,donor_game,size FROM ghidra_type_origin WHERE binary_id=? AND name=?', (bid, name)).fetchone()) == (donor, game, size)
    assert rows(con, 'ghidra_field') == fields
    assert [r[0] for r in con.execute("SELECT definition FROM ghidra_type WHERE kind='union' OR binary_id=3 ORDER BY binary_id")] == ['keep-union', 'keep-other']
    con.close()


@pytest.mark.parametrize('caller', [False, True])
@pytest.mark.parametrize('failure', ['cancel', 'collision', 'field-mapping', 'generator'])
def test_capture_or_payload_failure_before_scope_preserves_caller(caller, failure, capture_model, monkeypatch):
    con = current()
    if caller: con.execute("INSERT INTO eval(run) VALUES ('caller')")
    before = snapshot(con)
    if failure == 'generator':
        def broken():
            yield NATIVE[0]
            raise ValueError('capture aborted')
        action = lambda: et.insert_native_types(con, broken())
    else:
        original = et.emit_struct
        count = []
        def broken(dt):
            count.append(dt)
            if len(count) == 2:
                raise KeyboardInterrupt('cancelled') if failure == 'cancel' else ValueError('capture aborted')
            return original(dt)
        if failure == 'collision':
            first, second = capture_model[0]
            second.name = first.name
            second.getPathName = lambda: '/other/Layout'
        elif failure == 'field-mapping':
            monkeypatch.setattr(et, 'field_rows', lambda _dt: (_ for _ in ()).throw(ValueError('capture aborted')))
        else:
            monkeypatch.setattr(et, 'emit_struct', broken)
        action = lambda: operate('export', con, capture_model)
    with pytest.raises(KeyboardInterrupt if failure == 'cancel' else ValueError):
        action()
    assert snapshot(con) == before and con.in_transaction == caller
    con.close()


def test_opened_missing_program_does_not_materialize_or_commit(capture_model):
    con = current()
    con.execute("INSERT INTO eval(run) VALUES ('caller')")
    before = snapshot(con)
    @contextmanager
    def missing(_path):
        yield None
    assert et.export('/recipient', con, open_program=missing, start=lambda: True)['reason'] == 'no-program'
    assert snapshot(con) == before and con.in_transaction
    con.close()


@pytest.mark.parametrize('first', [True, False])
def test_native_first_and_later_constraint_failure_preserve_only_caller(first):
    con = current()
    con.execute("INSERT INTO eval(run) VALUES ('caller')")
    before = snapshot(con)
    with pytest.raises(RuntimeError, match='injected'):
        et.insert_native_types(Fault(con, 'INSERT OR IGNORE INTO main.ghidra_type', occurrence=1 if first else 2), NATIVE)
    assert snapshot(con) == before and con.in_transaction
    con.close()


def test_pending_migration_cleanup_failure_and_committed_ack_are_not_rollback_evidence(tmp_path):
    con = historical()
    proxy = Fault(con, 'CREATE TABLE type_inventory_state', cleanup='ROLLBACK')
    with pytest.raises(RuntimeError, match='cleanup failed'):
        migrations.apply_pending(proxy)
    assert con.in_transaction
    con.rollback()
    assert ledger(con) == LEDGER12
    con.close()
    path = tmp_path / 'ack.sqlite'
    con = historical(path)
    with pytest.raises(RuntimeError, match='injected'):
        migrations.apply_pending(Fault(con, 'COMMIT', committed=True))
    # Runner intentionally retains its established exception behavior. The
    # exception is not proof of rollback: a separate reader sees durable13.
    other = sqlite3.connect(path)
    assert ledger(other) == LEDGER13 and migrations.user_version(other) == 13
    assert not con.in_transaction
    other.close()
    con.close()


def test_attached_substitute_never_satisfies_main_type_admission():
    con = current()
    con.execute('DROP TABLE ghidra_type_origin')
    con.execute("ATTACH DATABASE ':memory:' AS substitute")
    con.execute(ORIGIN.replace('ghidra_type_origin', 'substitute.ghidra_type_origin'))
    con.execute("INSERT INTO eval(run) VALUES ('caller')")
    before = snapshot(con)
    with pytest.raises(ValueError, match='ghidra_type_origin'):
        pt.plan_adoptions(con, targets=['/recipient'])
    assert snapshot(con) == before and con.in_transaction
    con.close()


@pytest.mark.parametrize('cross_game', [False, True])
def test_planner_same_game_preference_size_conflict_and_donor_order_preserve_counters(cross_game):
    con = current(installed=True)
    for bid, name, size in [(3, 'Shared', 4), (3, 'Conflict', 8), (3, 'OnlyForeign', 7),
                            (2, 'Shared', 4), (2, 'Conflict', 4)]:
        con.execute('INSERT INTO ghidra_type VALUES (?,?,\'struct\',?,?,0,NULL)', (bid, name, size, f'def-{bid}-{name}'))
    con.commit()
    before = snapshot(con)
    plan = pt.plan_adoptions(con, targets=['/foreign', '/donor', '/recipient'], cross_game=cross_game)
    expected = [(1, 'Shared', 'def-2-Shared', 4, 'donor', 'game', 'same_game')]
    if cross_game:
        expected = [(2, 'OnlyForeign', 'def-3-OnlyForeign', 7, 'foreign', 'other', 'cross_game'),
                    *expected, (1, 'OnlyForeign', 'def-3-OnlyForeign', 7, 'foreign', 'other', 'cross_game')]
    assert sorted(plan['adopted']) == sorted(expected)
    assert [row[0] for row in plan['adopted']] == ([2, 1, 1] if cross_game else [1])
    assert plan['stats'] == {'already_native': 5, 'skipped_size_conflict': 1,
                            'adopted_same_game': 1,
                            ('adopted_cross_game' if cross_game else 'skipped_cross_game'): 2}
    assert snapshot(con) == before
    con.close()


@pytest.mark.parametrize('owner', ['ghidra_type', 'ghidra_type_origin', 'ghidra_field', 'type_inventory_state'])
def test_arbitrary_temp_owner_trigger_refuses_before_selected_or_unrelated_changes(owner):
    con = current(installed=True)
    con.execute("INSERT INTO ghidra_type VALUES (3,'Unrelated','struct',4,'keep',0,'native')")
    con.execute(f'CREATE TEMP TRIGGER side_effect AFTER INSERT ON main.{owner} BEGIN DELETE FROM ghidra_type WHERE binary_id=3; END')
    con.commit()
    con.execute("INSERT INTO eval(run) VALUES ('caller')")
    before = snapshot(con)
    for action in (lambda: et.insert_native_types(con, NATIVE), lambda: pt.apply_adoptions(con, ADOPTIONS)):
        with pytest.raises(ValueError, match='shadowing type temp object'):
            action()
        assert snapshot(con) == before and con.in_transaction
    con.close()


@pytest.mark.parametrize('singleton,mode', [(2, 'installed'), (1, 'unexpected'), (2, 'absent')])
def test_invalid_state_values_refuse_without_cleanup_or_normalization(singleton, mode):
    con = current()
    con.execute('PRAGMA ignore_check_constraints=ON')
    con.execute('DELETE FROM type_inventory_state')
    con.execute('INSERT INTO type_inventory_state VALUES (?,?)', (singleton, mode))
    before = snapshot(con)
    with pytest.raises(ValueError, match='singleton'):
        store.require_type_schema(con)
    assert snapshot(con) == before and con.in_transaction
    con.close()


def test_unledgered_raw_type_handle_refuses_before_config_capture_or_payload(monkeypatch):
    con = sqlite3.connect(':memory:')
    con.execute(TYPE6)
    con.execute('CREATE TABLE eval(run TEXT)')
    con.execute("INSERT INTO eval VALUES ('pending')")
    before = snapshot(con)
    monkeypatch.setattr(pt, '_targets', lambda *_a, **_k: pytest.fail('config before guard'))
    class Unreadable:
        def __iter__(self): pytest.fail('payload before guard')
    for action in (lambda: pt.plan_adoptions(con), lambda: pt.apply_adoptions(con, Unreadable()),
                   lambda: et.insert_native_types(con, Unreadable()),
                   lambda: et.export('/unused', con, start=lambda: pytest.fail('capture before guard'))):
        with pytest.raises(ValueError, match='type schema required: observed version 0'):
            action()
        assert snapshot(con) == before and con.in_transaction
    con.close()
