"""Task2.5 historical/admission/transaction regressions, AUTHORED NOT RUN.

Fixtures use actual runner prefixes and independently frozen historical SQL.
No assertion in this file is an execution receipt or ABI/recovery acceptance.
"""
from __future__ import annotations

import ast
import sqlite3
from pathlib import Path

import pytest

from agentdecompile_recovery.corpus import delete_registry, migrations, store
from agentdecompile_recovery.corpus import propagate_conventions as pc

HISTORICAL_DDL = '''CREATE TABLE IF NOT EXISTS func_convention_derived (
    binary_id INTEGER NOT NULL,
    addr INTEGER NOT NULL,
    deco_class TEXT NOT NULL,
    stack_bytes INTEGER,
    fastcall_n INTEGER,
    class_source TEXT NOT NULL,
    n_source TEXT NOT NULL,
    PRIMARY KEY (binary_id, addr)
)'''
OLD_ROWS = [(1, 16, 'unknown-class', None, None, 'old-source', 'unknown-source'),
            (2, 32, 'stack', 0, None, 'same_game', 'ret_zero')]
RAW = b'\xc2\x08\x00'


def rows(con, table):
    definition = con.execute("SELECT sql FROM main.sqlite_schema WHERE name=?", (table,)).fetchone()
    if definition and 'WITHOUT ROWID' in (definition[0] or '').upper():
        # Malformed-shape negatives must reach admission, including FTS shadow
        # tables. Only rowid-bearing history asserts preserved rowid identity.
        return sorted((tuple(r) for r in con.execute(f'SELECT * FROM main."{table}"')), key=repr)
    return [tuple(r) for r in con.execute(f'SELECT rowid,* FROM main."{table}" ORDER BY rowid')]


def snapshot(con):
    objects = [tuple(r) for r in con.execute('SELECT type,name,tbl_name,sql FROM main.sqlite_schema ORDER BY name,type')]
    return (migrations.user_version(con), objects,
            {name: rows(con, name) for kind, name, _, _ in objects
             if kind == 'table' and not name.startswith('sqlite_')})


def historical(path=':memory:', *, shape='absent', version=11):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    migrations.apply_pending(con, target=version)
    if shape != 'absent':
        con.execute(HISTORICAL_DDL)
        if shape == 'populated':
            con.executemany('INSERT INTO func_convention_derived VALUES (?,?,?,?,?,?,?)', OLD_ROWS)
    con.commit()
    return con


def current(path=':memory:'):
    con = historical(path)
    migrations.apply_pending(con)
    for bid in (1, 2):
        con.execute("INSERT INTO binary(id,repo_path,slug,game,platform,format,arch,bits,language_id)"
                    " VALUES (?,?,?,'test','win','pe','x86',32,'x86:LE:32:default')",
                    (bid, f'/{bid}', str(bid)))
    con.execute('INSERT INTO logical_function(id) VALUES (91)')
    for bid, cc in ((1, 'unknown'), (2, '__thiscall')):
        for addr in (16, 32):
            con.execute('INSERT INTO func(binary_id,addr,size,is_thunk,n_instr,calling_convention)'
                        ' VALUES (?,?,3,0,1,?)', (bid, addr, cc))
            con.execute('INSERT INTO identity(logical_id,binary_id,addr) VALUES (91,?,?)', (bid, addr))
    con.commit()
    return con


def derive(con, *, apply=True, mapper=lambda _addr: 0):
    return pc.derive_conventions(con, 1, RAW, mapper, game='test', apply_rows=apply)


def assert_read_only(statements):
    assert not any(sql.lstrip().upper().startswith((
        'BEGIN', 'SAVEPOINT', 'RELEASE', 'ROLLBACK', 'COMMIT', 'CREATE',
        'ALTER', 'DROP', 'INSERT', 'UPDATE', 'DELETE',
    )) for sql in statements)


@pytest.mark.parametrize('shape', ['absent', 'empty', 'populated'])
@pytest.mark.parametrize('mode', ['absent', 'skeleton_hash', 'ast_fingerprint'])
def test_eleven_to_twelve_preserves_every_old_value_rowid_and_mode(shape, mode):
    con = historical(shape=shape)
    con.execute('ALTER TABLE binary ADD COLUMN unrelated TEXT')
    con.execute('CREATE TABLE extension(payload TEXT)')
    con.execute("INSERT INTO extension VALUES ('untouched')")
    con.execute('UPDATE schema_migration SET basis_hash=NULL')
    con.execute('UPDATE decomp_schema_state SET mode=?', (mode,))
    if mode != 'absent':
        con.execute('INSERT INTO decomp(binary_id,addr,ok,skeleton_hash,ast_fingerprint) VALUES (1,16,1,?,?)',
                    ('old-skeleton', '' if mode == 'ast_fingerprint' else None))
    con.commit()
    before = snapshot(con)
    assert [step.version for step in migrations.apply_pending(con)] == [12]
    after = snapshot(con)
    for name, old in before[2].items():
        assert (after[2][name][:11] if name == 'schema_migration' else after[2][name]) == old
    assert rows(con, 'func_convention_derived') == before[2].get('func_convention_derived', [])
    assert store.decomp_read_state(con) == (None if mode == 'absent' else mode)
    assert tuple(con.execute('SELECT version,name FROM schema_migration ORDER BY version DESC').fetchone()) == (
        12, 'convention_schema_ownership')
    store.require_convention_schema(con)
    con.close()


@pytest.mark.parametrize('shape', ['absent', 'empty', 'populated'])
def test_nonapplying_raw_and_canonical_results_ignore_stored_conventions(shape):
    canonical = current()
    raw = sqlite3.connect(':memory:')
    raw.row_factory = sqlite3.Row
    # Raw ABI computation retains its minimal, unledgered public shape.
    for table in ('binary', 'func', 'identity'):
        cursor = canonical.execute(f'SELECT * FROM {table}')
        columns = [entry[0] for entry in cursor.description]
        raw.execute(f'CREATE TABLE {table} ({",".join(columns)})')
        raw.executemany(f'INSERT INTO {table} VALUES ({",".join("?" for _ in columns)})',
                        [tuple(row) for row in cursor])
    if shape != 'absent':
        raw.execute(HISTORICAL_DDL)
        if shape == 'populated':
            raw.executemany('INSERT INTO func_convention_derived VALUES (?,?,?,?,?,?,?)', OLD_ROWS)
    before = snapshot(raw)
    traced = []
    raw.set_trace_callback(traced.append)
    result = derive(raw, apply=False)
    assert result == derive(canonical, apply=False)
    assert result['applied'] is False
    assert result['rows'] == [(1, addr, 'ecx', 8, 16, 'same_game', 'ret_imm') for addr in (16, 32)]
    assert_read_only(traced)
    assert snapshot(raw) == before and raw.in_transaction
    with pytest.raises(ValueError, match='convention schema required: observed version 0'):
        derive(raw, mapper=lambda _a: pytest.fail('mapper ran before admission'))
    assert snapshot(raw) == before and raw.in_transaction
    raw.close()
    canonical.close()


@pytest.mark.parametrize('caller', [False, True])
@pytest.mark.parametrize('output', ['rows', 'empty', 'cross-abi'])
def test_success_commits_selected_keys_and_caller_work_even_with_zero_rows(tmp_path, caller, output):
    path = tmp_path / 'write.sqlite'
    con = current(path)
    con.executemany('INSERT INTO func_convention_derived VALUES (?,?,?,?,?,?,?)',
                    OLD_ROWS + [(1, 99, 'other', None, None, 'old', 'old')])
    if output == 'empty':
        con.execute('DELETE FROM func WHERE binary_id=1')
    elif output == 'cross-abi':
        con.execute("UPDATE binary SET platform='mac',format='macho' WHERE id=2")
    con.commit()
    preserved = [r for r in rows(con, 'func_convention_derived') if r[1] != 1 or r[2] not in (16, 32)]
    if caller:
        con.execute("INSERT INTO eval(run) VALUES ('caller')")
    expected = derive(con, apply=False)
    result = derive(con)
    assert result == {**expected, 'applied': True}
    assert bool(result['rows']) == (output == 'rows')
    assert not con.in_transaction
    observed = sqlite3.connect(path)
    assert observed.execute("SELECT COUNT(*) FROM eval WHERE run='caller'").fetchone()[0] == int(caller)
    assert [r for r in rows(observed, 'func_convention_derived') if r[1] != 1 or r[2] not in (16, 32)] == preserved
    for row in result['rows']:
        assert tuple(observed.execute('SELECT * FROM func_convention_derived WHERE binary_id=? AND addr=?', row[:2]).fetchone()) == row
    observed.close()
    con.close()


# Each table variant pairs with the exact declaration admitted above.
BAD_DDL = [
    HISTORICAL_DDL.replace('deco_class TEXT NOT NULL', "deco_class TEXT NOT NULL DEFAULT 'ecx'"),
    HISTORICAL_DDL.replace('stack_bytes INTEGER', 'stack_bytes TEXT'),
    HISTORICAL_DDL.replace('addr INTEGER NOT NULL', 'addr INTEGER'),
    HISTORICAL_DDL.replace('PRIMARY KEY (binary_id, addr)', 'PRIMARY KEY (addr, binary_id)'),
    HISTORICAL_DDL.replace('deco_class TEXT NOT NULL', 'deco_class TEXT NOT NULL CHECK(length(deco_class)>0)'),
    HISTORICAL_DDL.replace('stack_bytes INTEGER,\n    fastcall_n INTEGER', 'fastcall_n INTEGER,\n    stack_bytes INTEGER'),
    HISTORICAL_DDL.replace('stack_bytes INTEGER', 'stack_bytes INTEGER GENERATED ALWAYS AS (addr) VIRTUAL'),
    HISTORICAL_DDL.replace('PRIMARY KEY (binary_id, addr)', 'extra TEXT, PRIMARY KEY (binary_id, addr)'),
    HISTORICAL_DDL + ' STRICT',
    HISTORICAL_DDL + ' WITHOUT ROWID',
    'CREATE VIEW func_convention_derived AS SELECT 1 AS binary_id',
    'CREATE VIRTUAL TABLE func_convention_derived USING fts5(payload)',
]


@pytest.mark.parametrize('ddl', BAD_DDL)
@pytest.mark.parametrize('version', [11, 12])
def test_unknown_shapes_refuse_without_repair(ddl, version):
    con = historical()
    if version == 12:
        migrations.apply_pending(con)
        con.execute('DROP TABLE func_convention_derived')
    con.execute(ddl)
    con.commit()
    before = snapshot(con)
    if version == 11:
        with pytest.raises(ValueError, match='convention'):
            migrations.apply_pending(con)
    else:
        con.execute("INSERT INTO eval(run) VALUES ('caller')")
        before = snapshot(con)
        with pytest.raises(ValueError, match='convention schema required'):
            derive(con, mapper=lambda _a: pytest.fail('mapper before shape guard'))
        assert con.in_transaction
    assert snapshot(con) == before
    con.close()


@pytest.mark.parametrize('ddl', [
    'CREATE INDEX extra ON func_convention_derived(addr)',
    'CREATE TRIGGER extra AFTER INSERT ON func_convention_derived BEGIN SELECT 1; END',
    'CREATE TRIGGER func_convention_derived AFTER INSERT ON eval BEGIN SELECT 1; END',
    'ALTER TABLE func_convention_derived RENAME TO FuNc_CoNvEnTiOn_DeRiVeD',
])
def test_local_objects_and_reserved_spelling_refuse(ddl):
    con = historical(shape='empty')
    if ddl.startswith('ALTER TABLE func_convention_derived RENAME'):
        con.execute('ALTER TABLE func_convention_derived RENAME TO intermediate_convention')
        con.execute('ALTER TABLE intermediate_convention RENAME TO FuNc_CoNvEnTiOn_DeRiVeD')
    else:
        con.execute(ddl)
    con.commit()
    before = snapshot(con)
    with pytest.raises(ValueError, match='convention'):
        migrations.apply_pending(con)
    assert snapshot(con) == before
    con.close()


@pytest.mark.parametrize('name', ['binary', 'func', 'identity', 'schema_migration', 'func_convention_derived'])
@pytest.mark.parametrize('kind', ['TABLE', 'VIEW'])
@pytest.mark.parametrize('version', [11, 12])
def test_mixed_case_temp_input_shadows_refuse_before_reads(name, kind, version):
    con = historical(shape='empty') if version == 11 else current()
    spelling = name.upper()
    con.execute(f'CREATE TEMP {kind} {spelling} ' + ('(payload TEXT)' if kind == 'TABLE' else 'AS SELECT 1 AS payload'))
    con.commit()
    if version == 11:
        before = snapshot(con)
        with pytest.raises(ValueError, match='shadowing convention'):
            migrations.apply_pending(con)
    else:
        con.execute("INSERT INTO eval(run) VALUES ('caller')")
        before = snapshot(con)
        with pytest.raises(ValueError, match='shadowing convention'):
            derive(con, mapper=lambda _a: pytest.fail('mapper before shadow guard'))
        assert con.in_transaction
    assert snapshot(con) == before
    con.close()


@pytest.mark.parametrize('damage', [
    'DROP TABLE func_convention_derived',
    "UPDATE schema_migration SET name='wrong' WHERE version=12",
    'DELETE FROM schema_migration WHERE version=1',
    'DROP TABLE schema_migration',
    'ALTER TABLE identity RENAME TO IdEnTiTy',
])
def test_current_guard_refuses_without_touching_pending_work(damage):
    con = current()
    if damage.startswith('ALTER TABLE identity RENAME'):
        con.execute('ALTER TABLE identity RENAME TO intermediate_identity')
        con.execute('ALTER TABLE intermediate_identity RENAME TO IdEnTiTy')
    else:
        con.execute(damage)
    con.execute("INSERT INTO eval(run) VALUES ('caller')")
    before = snapshot(con)
    trace = []
    con.set_trace_callback(trace.append)
    with pytest.raises(ValueError, match='convention schema required.*observed version 12.*supported version 12'):
        derive(con, mapper=lambda _a: pytest.fail('mapper before guard'))
    assert_read_only(trace)
    assert snapshot(con) == before and con.in_transaction
    con.close()


def test_pure_guard_success_preserves_pending_work_and_unrelated_extensions():
    con = current()
    con.execute('ALTER TABLE binary ADD COLUMN this_kind TEXT')
    con.execute('CREATE TABLE extension(payload TEXT)')
    con.execute("INSERT INTO extension VALUES ('pending')")
    before = snapshot(con)
    trace = []
    con.set_trace_callback(trace.append)
    store.require_convention_schema(con)
    assert_read_only(trace)
    assert snapshot(con) == before and con.in_transaction
    con.close()


class Fault:
    def __init__(self, con, *, prefix='', insert=0, after=False, committed=False,
                 interrupt=False, cleanup='', lost=False):
        self.con = con
        self.prefix, self.insert = prefix, insert
        self.after, self.committed = after, committed
        self.cleanup, self.lost = cleanup, lost
        self.failure = KeyboardInterrupt('injected') if interrupt else RuntimeError('injected')

    def __getattr__(self, name):
        return getattr(self.con, name)

    def execute(self, sql, *args):
        if self.cleanup and sql.startswith(self.cleanup):
            raise RuntimeError('cleanup failed')
        hit = bool(self.prefix and sql.strip().startswith(self.prefix))
        if hit and not self.after and not (self.committed and sql == 'COMMIT'):
            raise self.failure
        result = self.con.execute(sql, *args)
        if hit:
            raise self.failure
        return result

    def executemany(self, sql, values):
        for index, row in enumerate(values, 1):
            self.con.execute(sql, row)
            if index == self.insert:
                if self.lost:
                    self.con.rollback()
                raise self.failure

    def commit(self):
        if self.prefix == 'COMMIT':
            if self.committed:
                self.con.commit()
            raise self.failure
        self.con.commit()

    def rollback(self):
        if self.cleanup == 'ROLLBACK':
            raise RuntimeError('cleanup failed')
        self.con.rollback()


@pytest.mark.parametrize('prefix', ['CREATE TABLE IF NOT EXISTS func_convention_derived',
    'INSERT OR IGNORE INTO schema_migration', 'PRAGMA user_version = 12', 'COMMIT'])
@pytest.mark.parametrize('interrupt', [False, True])
def test_migration_failure_rolls_back_only_pending_twelve(prefix, interrupt):
    con = sqlite3.connect(':memory:')
    # Fail only step12, allowing the same actual runner to freshly commit1–11.
    fault = Fault(con, prefix=prefix, after=prefix != 'COMMIT', interrupt=interrupt)
    original_execute = fault.execute
    pending_twelve = False
    def execute(sql, *args):
        nonlocal pending_twelve
        if sql.strip().startswith('CREATE TABLE IF NOT EXISTS func_convention_derived'):
            pending_twelve = True
        if not pending_twelve:
            return con.execute(sql, *args)
        return original_execute(sql, *args)
    fault.execute = execute
    with pytest.raises(KeyboardInterrupt if interrupt else RuntimeError, match='injected'):
        migrations.apply_pending(fault)
    assert migrations.user_version(con) == 11
    assert len(rows(con, 'schema_migration')) == 11
    assert not con.execute("SELECT 1 FROM sqlite_schema WHERE name='func_convention_derived'").fetchone()
    assert not con.in_transaction
    assert store.decomp_read_state(con) is None
    con.close()


@pytest.mark.parametrize('caller', [False, True])
@pytest.mark.parametrize('failure', ['first', 'later', 'commit', 'interrupt'])
def test_write_failure_preserves_surviving_caller_scope(caller, failure):
    con = current()
    if caller:
        con.execute("INSERT INTO eval(run) VALUES ('caller')")
    before = snapshot(con)
    proxy = Fault(con, insert=1 if failure == 'first' else 2 if failure != 'commit' else 0,
                  prefix='COMMIT' if failure == 'commit' else '', interrupt=failure == 'interrupt')
    with pytest.raises(KeyboardInterrupt if failure == 'interrupt' else RuntimeError, match='injected'):
        derive(proxy)
    assert snapshot(con) == before and con.in_transaction == caller
    con.rollback()
    assert not rows(con, 'eval')
    con.close()


@pytest.mark.parametrize('caller', [False, True])
def test_mapper_failure_precedes_scope_and_keeps_caller_work(caller):
    con = current()
    if caller:
        con.execute("INSERT INTO eval(run) VALUES ('caller')")
    before = snapshot(con)
    def fail(_addr):
        raise RuntimeError('mapper failed')
    with pytest.raises(RuntimeError, match='mapper failed'):
        derive(con, mapper=fail)
    assert snapshot(con) == before and con.in_transaction == caller
    con.close()


def test_schema_changed_by_mapper_is_revalidated_before_insertion():
    con = current()
    con.execute("INSERT INTO eval(run) VALUES ('caller')")
    changed = False
    def mutate(_addr):
        nonlocal changed
        if not changed:
            con.execute('CREATE INDEX injected ON func_convention_derived(addr)')
            changed = True
        return 0
    with pytest.raises(ValueError, match='undeclared convention object injected'):
        derive(con, mapper=mutate)
    assert con.in_transaction and not rows(con, 'func_convention_derived')
    assert len(rows(con, 'eval')) == 1
    # Callback side effects precede our scope and are not silently reconstructed.
    assert con.execute("SELECT 1 FROM sqlite_schema WHERE name='injected'").fetchone()
    con.close()


@pytest.mark.parametrize('caller', [False, True])
def test_scope_creation_failure_has_no_cleanup_ownership(caller):
    con = current()
    if caller:
        con.execute("INSERT INTO eval(run) VALUES ('caller')")
    before = snapshot(con)
    proxy = Fault(con, prefix='SAVEPOINT' if caller else 'BEGIN IMMEDIATE', cleanup='ROLLBACK')
    with pytest.raises(RuntimeError, match='injected'):
        derive(proxy)
    assert snapshot(con) == before and con.in_transaction == caller
    con.close()


@pytest.mark.parametrize('cleanup', ['ROLLBACK', 'ROLLBACK TO', 'RELEASE'])
def test_cleanup_failure_propagates_without_successful_rollback_claim(cleanup):
    con = current()
    if cleanup != 'ROLLBACK':
        con.execute("INSERT INTO eval(run) VALUES ('caller')")
    with pytest.raises(RuntimeError, match='cleanup failed'):
        derive(Fault(con, insert=1, cleanup=cleanup))
    assert con.in_transaction
    con.rollback()
    con.close()


@pytest.mark.parametrize('committed', [False, True])
def test_lost_transaction_and_commit_acknowledgement_report_uncertainty(tmp_path, committed):
    path = tmp_path / 'uncertain.sqlite'
    con = current(path)
    con.execute("INSERT INTO eval(run) VALUES ('caller')")
    proxy = Fault(con, prefix='COMMIT' if committed else '', committed=committed,
                  insert=0 if committed else 1, lost=not committed)
    with pytest.raises(RuntimeError, match='durability/rollback is uncertain'):
        derive(proxy)
    assert not con.in_transaction
    other = sqlite3.connect(path)
    assert len(rows(other, 'eval')) == int(committed)
    assert len(rows(other, 'func_convention_derived')) == (2 if committed else 0)
    other.close()
    con.close()


def test_actual_older_lock_and_readonly_handles_refuse_before_computation(tmp_path):
    path = tmp_path / 'eleven.sqlite'
    historical(path).close()
    holder = sqlite3.connect(path)
    waiter = sqlite3.connect(path, timeout=0)
    readonly = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    holder.execute('BEGIN IMMEDIATE')
    try:
        for con in (waiter, readonly):
            assert migrations.apply_pending(con) == []
            trace = []
            con.set_trace_callback(trace.append)
            with pytest.raises(ValueError, match='convention schema required: observed version 11'):
                derive(con, mapper=lambda _a: pytest.fail('old handle mapper'))
            assert_read_only(trace)
        holder.rollback()
        assert [step.version for step in migrations.apply_pending(waiter)] == [12]
        store.require_convention_schema(waiter)
    finally:
        holder.close()
        waiter.close()
        readonly.close()


@pytest.mark.parametrize('version', [10, 11, 12])
def test_direct_repeats_bind_own_version_under_future_registry(monkeypatch, version):
    con = sqlite3.connect(':memory:')
    migrations.apply_pending(con, target=version)
    future = migrations.MIGRATIONS + [migrations.Migration(13, 'future', lambda _c: None)]
    monkeypatch.setattr(migrations, 'MIGRATIONS', future)
    monkeypatch.setattr(migrations, 'SCHEMA_VERSION', 13)
    con.execute("INSERT INTO eval(run) VALUES ('caller')")
    before = snapshot(con)
    {10: migrations._stabs_schema_ownership, 11: migrations._decomp_schema_ownership,
     12: migrations._convention_schema_ownership}[version](con)
    assert snapshot(con) == before and con.in_transaction
    if version == 12:
        con.execute('DROP TABLE func_convention_derived')
        before = snapshot(con)
        with pytest.raises(ValueError, match='missing convention'):
            migrations._convention_schema_ownership(con)
        assert snapshot(con) == before
    con.close()


def test_actual_future_thirteen_refuses_guard_and_frozen_delete_without_writes():
    con = current()
    future = migrations.MIGRATIONS + [migrations.Migration(13, 'future', lambda _c: None)]
    assert [step.version for step in migrations.apply_pending(con, migrations=future)] == [13]
    con.execute("INSERT INTO eval(run) VALUES ('caller')")
    before = snapshot(con)
    for operation in (lambda: derive(con), lambda: delete_registry.remove_binary(con, slug='1')):
        with pytest.raises(ValueError):
            operation()
        assert snapshot(con) == before and con.in_transaction
    con.close()


def test_writer_source_has_no_schema_installation_and_keeps_public_signature():
    tree = ast.parse(Path(pc.__file__).read_text())
    names = {'derive_conventions', '_convention_write_scope'}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            for part in ast.walk(node):
                assert not (isinstance(part, ast.Attribute) and part.attr == 'executescript')
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    assert not any(token in part.value.upper() for token in ('CREATE TABLE', 'ALTER TABLE', 'CREATE INDEX'))
    assert pc.SCHEMA == store.CONVENTION_TABLE_DDL


@pytest.mark.parametrize('version', [11, 12])
def test_arbitrary_temp_trigger_on_conventions_refuses_before_side_effects(version):
    con = historical(shape='populated') if version == 11 else current()
    if version == 12:
        con.executemany('INSERT INTO func_convention_derived VALUES (?,?,?,?,?,?,?)', OLD_ROWS)
    con.execute("CREATE TEMP TRIGGER side_effect AFTER INSERT ON main.func_convention_derived "
                "BEGIN DELETE FROM func_convention_derived WHERE binary_id <> NEW.binary_id; END")
    con.commit()
    before = snapshot(con)
    if version == 11:
        with pytest.raises(ValueError, match='shadowing convention'):
            migrations.apply_pending(con)
    else:
        con.execute("INSERT INTO eval(run) VALUES ('caller')")
        before = snapshot(con)
        trace = []
        con.set_trace_callback(trace.append)
        with pytest.raises(ValueError, match='shadowing convention'):
            derive(con, mapper=lambda _a: pytest.fail('mapper before TEMP trigger guard'))
        assert_read_only(trace)
        assert con.in_transaction
    assert snapshot(con) == before
    assert any(row[1] == 2 for row in rows(con, 'func_convention_derived'))
    con.close()


def test_unrelated_temp_scratch_remains_allowed():
    con = current()
    con.execute('CREATE TEMP TABLE unrelated_scratch(payload TEXT)')
    con.execute('CREATE TEMP TRIGGER unrelated_trigger AFTER INSERT ON unrelated_scratch BEGIN SELECT 1; END')
    con.execute("INSERT INTO unrelated_scratch VALUES ('pending')")
    store.require_convention_schema(con)
    assert derive(con)['applied']
    assert tuple(con.execute('SELECT * FROM unrelated_scratch').fetchone()) == ('pending',)
    con.close()


@pytest.mark.parametrize('version', [9, 10, 11, 12])
@pytest.mark.parametrize('shape', ['absent', 'empty', 'populated'])
def test_actual_deletion_profiles_keep_historical_optional_storage(version, shape):
    con = historical(version=version, shape=shape) if version < 12 else current()
    if version == 12:
        con.execute('DELETE FROM identity')
        con.execute('DELETE FROM func')
        con.execute('DELETE FROM binary')
        if shape == 'absent':
            con.execute('DROP TABLE func_convention_derived')
        elif shape == 'populated':
            con.executemany('INSERT INTO func_convention_derived VALUES (?,?,?,?,?,?,?)', OLD_ROWS)
    con.execute("INSERT INTO binary(id,repo_path,slug) VALUES (1,'/one','one')")
    if shape == 'populated':
        # Remove the surviving ambiguous dependency for this positive case.
        con.execute('DELETE FROM func_convention_derived WHERE binary_id=2')
    con.commit()
    state = rows(con, 'decomp_schema_state') if version >= 11 else None
    before = snapshot(con)
    if version == 12 and shape == 'absent':
        with pytest.raises(delete_registry.BinaryDeleteUnsupported, match='func_convention_derived'):
            delete_registry.remove_binary(con, slug='one')
        assert snapshot(con) == before
    else:
        receipt = delete_registry.remove_binary(con, slug='one')
        assert receipt['deleted']['binary'] == 1
        assert receipt['deleted']['func_convention_derived'] == int(shape == 'populated')
        if state is not None:
            assert rows(con, 'decomp_schema_state') == state
    con.close()


@pytest.mark.parametrize('prefix', ['CREATE TABLE IF NOT EXISTS func_convention_derived', 'COMMIT'])
def test_migration_cleanup_and_lost_commit_acknowledgement_are_not_rollback_claims(prefix):
    con = historical()
    proxy = Fault(con, prefix=prefix, after=prefix != 'COMMIT',
                  committed=prefix == 'COMMIT', cleanup='ROLLBACK' if prefix != 'COMMIT' else '')
    with pytest.raises(RuntimeError, match='injected' if prefix == 'COMMIT' else 'cleanup failed'):
        migrations.apply_pending(proxy)
    if prefix == 'COMMIT':
        assert not con.in_transaction and migrations.user_version(con) == 12
        store.require_convention_schema(con)
    else:
        assert con.in_transaction
        con.rollback()
        assert migrations.user_version(con) == 11
    con.close()
