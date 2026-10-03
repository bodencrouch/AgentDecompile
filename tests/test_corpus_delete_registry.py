"""Task2.2 regressions, authored only under the source-only recovery mission.

Do not infer execution evidence from this file. Fixtures intentionally use the
real migration/optional-writer declarations, not the deletion profile's DDL.
"""
from __future__ import annotations

import ast
from pathlib import Path
import sqlite3

import pytest

from agentdecompile_recovery.corpus import delete_registry as deletion
from agentdecompile_recovery.corpus import migrations, store


FROZEN_DECOMP_DDL = """
CREATE TABLE IF NOT EXISTS decomp (
    binary_id     INTEGER NOT NULL,
    addr          INTEGER NOT NULL,
    ok            INTEGER,
    n_tokens      INTEGER,
    n_lines       INTEGER,
    max_nest      INTEGER,
    n_calls       INTEGER,
    n_locals      INTEGER,
    n_deref       INTEGER,
    n_index       INTEGER,
    n_field       INTEGER,
    ctrl          TEXT,
    ops           TEXT,
    skeleton_hash TEXT,
    ast_fingerprint TEXT,
    PRIMARY KEY (binary_id, addr)
);
CREATE INDEX IF NOT EXISTS ix_decomp_bin ON decomp(binary_id);
"""

FROZEN_CONVENTION_DDL = """
CREATE TABLE IF NOT EXISTS func_convention_derived (
    binary_id     INTEGER NOT NULL,
    addr          INTEGER NOT NULL,
    deco_class    TEXT NOT NULL,
    stack_bytes   INTEGER,
    fastcall_n    INTEGER,
    class_source  TEXT NOT NULL,
    n_source      TEXT NOT NULL,
    PRIMARY KEY (binary_id, addr)
);
"""

FROZEN_TYPE_DDL = """CREATE TABLE IF NOT EXISTS ghidra_type (
    binary_id INTEGER NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL,
    size INTEGER, definition TEXT NOT NULL, n_fields INTEGER,
    PRIMARY KEY (binary_id, name, kind)
);
CREATE INDEX IF NOT EXISTS ix_ghidra_type_bin ON ghidra_type(binary_id);
CREATE TABLE IF NOT EXISTS ghidra_type_origin (
    binary_id INTEGER NOT NULL, name TEXT NOT NULL, donor_slug TEXT NOT NULL,
    donor_game TEXT, size INTEGER, PRIMARY KEY (binary_id, name)
);
"""

OPTIONAL_DECLARATIONS = (
    ('ingest_recovered.py', 'RECOVERED_FUNCTION_DDL'),
    ('ingest_recovered.py', 'REUSE_CANDIDATE_DDL'), ('name_precedence.py', 'SCHEMA'),
)


def _writer_ddl(filename, variable):
    tree = ast.parse((Path(store.__file__).parent / filename).read_text())
    return next(ast.literal_eval(node.value) for node in tree.body
                if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == variable for target in node.targets))


def _insert(con, table, **values):
    con.execute(f"INSERT INTO {table}({','.join(values)}) VALUES({','.join('?' for _ in values)})",
                tuple(values.values()))


def _rows(con, table):
    return sorted((tuple(row) for row in con.execute(f'SELECT * FROM {table}')), key=repr)


def _snapshot(con):
    names = [row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    return {name: _rows(con, name) for name in names}


@pytest.fixture(params=[9, 10, 11, 12, 13], ids=["frozen-v9", "frozen-v10", "frozen-v11", "frozen-v12", "canonical-v13"])
def populated(tmp_path, request):
    path = tmp_path / 'corpus.sqlite'
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    migrations.apply_pending(con, target=request.param)
    if request.param < 11:
        con.executescript(FROZEN_DECOMP_DDL)
    else:
        con.execute("UPDATE decomp_schema_state SET mode='ast_fingerprint'")
    if request.param < 12:
        con.execute(FROZEN_CONVENTION_DDL)
    if request.param < 13:
        con.executescript(FROZEN_TYPE_DDL)
    else:
        con.execute("UPDATE type_inventory_state SET mode='installed'")
    for filename, variable in OPTIONAL_DECLARATIONS:
        con.executescript(_writer_ddl(filename, variable))
    con.execute('CREATE TABLE binary_source_alias (source_path TEXT PRIMARY KEY, binary_slug TEXT NOT NULL, sha256 TEXT NOT NULL)')
    con.execute('CREATE TABLE binary_content_identity (source_path TEXT PRIMARY KEY, sha256 TEXT NOT NULL)')
    con.execute('CREATE TABLE program_binding (source_path TEXT NOT NULL, locator TEXT NOT NULL, program TEXT NOT NULL, updated REAL NOT NULL, PRIMARY KEY(source_path,locator))')
    for bid, slug in ((1, 'a'), (2, 'b'), (3, 'c')):
        _insert(con, 'binary', id=bid, slug=slug, repo_path='/' + slug)
        _insert(con, 'func', binary_id=bid, addr=16, name='f')
    for lid, count in ((10, 99), (20, 7), (30, 0)):
        _insert(con, 'logical_function', id=lid, canon_key=f'key:{lid}', n_members=count, notes='historical')
    _insert(con, 'identity', logical_id=10, binary_id=1, addr=16, method='name-reference')
    for mid, dst in ((100, 2), (101, 1)):
        _insert(con, 'match', id=mid, src_binary=1, dst_binary=dst, src_addr=16, dst_addr=16, status='accepted')
    for src, dst in ((1, 2), (1, 1), (2, 2)):
        _insert(con, 'bsim_query', src_binary=src, dst_binary=dst, database_id='db', src_digest='s', dst_digest='d', state='ok', reason='observed')
        _insert(con, 'bsim_hit', src_binary=src, dst_binary=dst, src_addr=16, dst_addr=16, database_id='db', similarity=1.0, significance=1.0)
    for bid, slug in ((1, 'a'), (2, 'b')):
        _insert(con, 'calledge', binary_id=bid, caller_addr=16, callee_addr=16)
        _insert(con, 'func_param', binary_id=bid, addr=16, ordinal=0, type='int')
        _insert(con, 'ghidra_field', binary_id=bid, type_name='T', ordinal=0, offset=0, size=4, name='field', dt_kind='int', type_json='{}')
        _insert(con, 'decomp', binary_id=bid, addr=16, ok=1)
        _insert(con, 'ghidra_type', binary_id=bid, name='T', kind='struct', definition='struct T { int x; };')
        _insert(con, 'ghidra_type_origin', binary_id=bid, name='T', donor_slug='a' if bid == 2 else 'b')
        _insert(con, 'stabs_type', binary_id=bid, name='T', stab='type:T')
        _insert(con, 'binary_source_alias', source_path='/alias-' + slug, binary_slug=slug, sha256='same-digest')
    _insert(con, 'func_convention_derived', binary_id=1, addr=16, deco_class='cdecl', class_source='same_game', n_source='cross_game')
    for lid, donor in ((10, 2), (20, 2), (30, 1)):
        _insert(con, 'logical_name', logical_id=lid, name='f', from_binary_id=donor)
    for bid, name in ((1, 'shared'), (1, 'gone'), (2, 'shared'), (None, 'shared')):
        _insert(con, 'recovered_function', program='p', binary_id=bid, addr=16, name=name,
                real_c=1, path='/same-source.c', source_sha256='same-source', target_sha256='same-target')
    for name, dst in (('shared', 1), ('shared', 2), ('gone', 2), ('orphan-before-removal', 2)):
        _insert(con, 'reuse_candidate', src_program='p', src_name=name, dst_binary_id=dst,
                dst_addr=16, real_c=1, size=4, basis='proposal')
    _insert(con, 'binary_content_identity', source_path='/a', sha256='digest')
    _insert(con, 'program_binding', source_path='/a', locator='project', program='p', updated=1.0)
    _insert(con, 'eval', run='shared', metric='accuracy', value=0.5)
    _insert(con, 'basis_supersession', old_basis_hash='old', new_basis_hash='new', old_algorithm_version='1',
            new_algorithm_version='2', new_package_basis_json='{}', analyzer_version='v', binaries_restamped=2,
            receipt_sha256='receipt', recorded_at='then')
    _insert(con, 'match_review_audit', match_id=100, incarnation='0' * 32, selection='{}', decision='accept',
            old_status='pending', new_status='accepted', old_revision=1, new_revision=2,
            observed_token='token', basis_json='{}', decided_at='then')
    con.commit()
    try:
        yield con, path
    finally:
        con.close()


@pytest.mark.parametrize('foreign_keys', [0, 1])
@pytest.mark.parametrize('selector', [{'slug': 'a'}, {'repo_path': '/a'}, {'repo_path': '/a', 'slug': 'b'}])
def test_all_owned_rows_and_exact_counts_preserve_shared_evidence(populated, foreign_keys, selector):
    con, _ = populated
    con.execute(f'PRAGMA foreign_keys={foreign_keys}')
    before = _snapshot(con)
    result = store.remove_binary(con, **selector)
    expected = dict.fromkeys(deletion.DELETE_ORDER, 1)
    expected.update(reuse_candidate=2, recovered_function=2, logical_name=2, match=2, bsim_hit=2, bsim_query=2,
                    match_review_revision=3, logical_function=0, match_review_audit=0)
    assert result == {'id': 1, 'slug': 'a', 'repo_path': '/a', 'deleted': expected}
    assert not con.in_transaction
    control = _rows(con, 'match_review_control')[0]
    assert control[:2] == before['match_review_control'][0][:2]
    assert control[2] == before['match_review_control'][0][2] + 3
    assert con.execute('SELECT COUNT(*) FROM binary').fetchone()[0] == 2
    for table in ('eval', 'schema_migration', 'basis_supersession', 'binary_content_identity', 'program_binding', 'match_review_audit'):
        assert _rows(con, table) == before[table]
    assert [tuple(row) for row in con.execute('SELECT id,n_members FROM logical_function ORDER BY id')] == [(10, 0), (20, 7), (30, 0)]
    assert con.execute('SELECT notes FROM logical_function WHERE id=10').fetchone()[0] == 'historical'
    assert [row[0] for row in con.execute('SELECT logical_id FROM logical_name')] == [20]
    assert con.execute('SELECT donor_slug FROM ghidra_type_origin WHERE binary_id=2').fetchone()[0] == 'a'
    assert sorted(row[0] for row in con.execute('SELECT src_name FROM reuse_candidate')) == ['orphan-before-removal', 'shared']
    assert [row[0] for row in con.execute('SELECT binary_slug FROM binary_source_alias')] == ['b']
    assert con.execute('SELECT COUNT(*) FROM recovered_function WHERE binary_id IS NULL').fetchone()[0] == 1
    for table in ('func', 'calledge', 'func_param', 'ghidra_field', 'decomp', 'ghidra_type', 'stabs_type'):
        remaining = _rows(con, table)
        columns = [row[1] for row in con.execute(f'PRAGMA table_info({table})')]
        owner_index = columns.index('binary_id')
        assert remaining == [row for row in before[table] if row[owner_index] != 1]
    with pytest.raises(SystemExit, match='no binary matching'):
        store.remove_binary(con, slug='a')


@pytest.mark.parametrize('survivor', ['other-build', 'null-bound', 'none'])
def test_last_source_disappearance_is_scoped_to_removed_program_name(populated, survivor):
    con, _ = populated
    if survivor != 'other-build':
        con.execute('DELETE FROM recovered_function WHERE binary_id=2')
    if survivor != 'null-bound':
        con.execute('DELETE FROM recovered_function WHERE binary_id IS NULL')
    con.commit()
    result = store.remove_binary(con, slug='a')
    names = {row[0] for row in con.execute('SELECT src_name FROM reuse_candidate')}
    assert 'orphan-before-removal' in names
    assert ('shared' in names) == (survivor != 'none')
    assert result['deleted']['reuse_candidate'] == (3 if survivor == 'none' else 2)


def _refuses_unchanged(con, prefix):
    con.commit()
    before = _snapshot(con)
    writes = []
    con.set_trace_callback(lambda sql: writes.append(sql) if sql.lstrip().upper().startswith(('DELETE ', 'UPDATE ', 'INSERT ')) else None)
    try:
        with pytest.raises(deletion.BinaryDeleteUnsupported, match=prefix):
            store.remove_binary(con, slug='a')
        assert _snapshot(con) == before
        assert writes == []
        assert not con.in_transaction
    finally:
        con.set_trace_callback(None)


@pytest.mark.parametrize('method,evidence', [
    ('match:run:accepted', '{"dependencies":["0123456789abcdef:16"],"dependency_ancestry":["0123456789abcdef:32"]}'),
    ('match:run:accepted', '{"source":1,"target":2,"run":"r","witness":"{\\"component\\":true}"}'),
    ('name-disambiguated', '{"canon_key":"f","origin":"name"}'),
    ('name-reference', '{}'), ('unrelated-local-method', '{}'),
])
def test_surviving_identity_refuses_all_lineage_envelopes_and_shared_groups(populated, method, evidence):
    con, _ = populated
    for bid, lid in ((2, 10), (3, 20)):
        _insert(con, 'identity', logical_id=lid, binary_id=bid, addr=16, method=method, evidence=evidence)
    _insert(con, 'match', src_binary=2, dst_binary=3, evidence=evidence)
    _refuses_unchanged(con, 'binary_delete_dependency_unsupported:identity')


@pytest.mark.parametrize('src,dst', [(2, 3), (None, 3), (None, None), ('unknown', 3)])
def test_surviving_match_is_not_declared_independent(populated, src, dst):
    con, _ = populated
    _insert(con, 'match', src_binary=src, dst_binary=dst, evidence='{"dependencies":[]}')
    _refuses_unchanged(con, 'binary_delete_dependency_unsupported:match')


@pytest.mark.parametrize('owner', [2, None])
def test_inherited_recovered_identity_refuses_even_when_unbound(populated, owner):
    con, _ = populated
    con.execute('UPDATE recovered_function SET logical_id=10 WHERE binary_id IS ?', (owner,))
    _refuses_unchanged(con, 'binary_delete_dependency_unsupported:recovered_function')


def test_surviving_abi_without_donor_ids_refuses(populated):
    con, _ = populated
    _insert(con, 'func_convention_derived', binary_id=2, addr=16, deco_class='cdecl', class_source='same_game', n_source='cross_game')
    _refuses_unchanged(con, 'binary_delete_dependency_unsupported:func_convention_derived')


@pytest.mark.parametrize('table', sorted(deletion.OPTIONAL_TABLES))
def test_every_optional_table_can_be_absent_without_creation(populated, table):
    con, _ = populated
    # Optional dependencies must be absent together.
    for dependent, parent in [('reuse_candidate', 'recovered_function'), ('ghidra_type_origin', 'ghidra_type')]:
        if table == parent:
            con.execute(f'DROP TABLE {dependent}')
    con.execute(f'DROP TABLE {table}')
    con.commit()
    if table == 'decomp' and con.execute('PRAGMA user_version').fetchone()[0] in {11, 12, 13}:
        # The frozen v9/v10 optional set does not weaken v11 admission.
        _refuses_unchanged(con, 'binary_delete_schema_unsupported:ix_decomp_bin')
        return
    if table == 'func_convention_derived' and con.execute('PRAGMA user_version').fetchone()[0] in {12, 13}:
        _refuses_unchanged(con, 'binary_delete_schema_unsupported:func_convention_derived')
        return
    if con.execute('PRAGMA user_version').fetchone()[0] == 13 and table in {'ghidra_type', 'ghidra_type_origin'}:
        expected = 'ix_ghidra_type_bin' if table == 'ghidra_type' else table
        _refuses_unchanged(con, 'binary_delete_schema_unsupported:' + expected)
        return
    before = list(con.execute('SELECT name FROM sqlite_master ORDER BY name'))
    result = store.remove_binary(con, slug='a')
    assert list(con.execute('SELECT name FROM sqlite_master ORDER BY name')) == before
    if table in result['deleted']:
        assert result['deleted'][table] == 0


@pytest.mark.parametrize('version', [0, 8, 14])
def test_other_versions_refuse_without_migration(populated, version):
    con, _ = populated
    con.execute(f'PRAGMA user_version={version}')
    _refuses_unchanged(con, 'binary_delete_schema_unsupported:user_version')


@pytest.mark.parametrize('ddl', [
    'DROP TABLE func_param',
    "UPDATE schema_migration SET name='wrong' WHERE version=9",
    'DELETE FROM schema_migration WHERE version=1',
    'ALTER TABLE func ADD COLUMN surprise TEXT',
    'ALTER TABLE decomp ADD COLUMN surprise TEXT',
    'CREATE TABLE mystery (binary_id INTEGER)',
    'CREATE TABLE grid_match_score (task_id TEXT)',
    'CREATE TABLE recovered_function_candidate_migration (program TEXT)',
    'CREATE VIEW shadow AS SELECT * FROM binary',
    'CREATE INDEX foreign_index ON func(name)',
    'CREATE TRIGGER hidden AFTER DELETE ON func BEGIN DELETE FROM eval; END',
    'DROP TRIGGER match_review_binary_delete',
    "UPDATE identity SET logical_id=999",
    "UPDATE func SET binary_id='bad-owner' WHERE binary_id=1",
    "UPDATE func SET addr='bad-address' WHERE binary_id=1",
    'DELETE FROM match_review_revision WHERE kind=\'binary\' AND entity_id=1',
    'DELETE FROM match_review_control',
])
def test_malformed_schema_ledger_ownership_and_review_coverage_refuse(populated, ddl):
    con, _ = populated
    con.execute(ddl)
    _refuses_unchanged(con, 'binary_delete_')


@pytest.mark.parametrize('table,replacement', [
    ('decomp', 'CREATE TABLE decomp (binary_id TEXT, addr INTEGER, PRIMARY KEY(binary_id,addr))'),
    ('recovered_function', 'CREATE TABLE recovered_function (program TEXT,name TEXT,path TEXT,PRIMARY KEY(program,name,path))'),
    ('func_param', 'CREATE TABLE func_param (binary_id INTEGER NOT NULL,addr INTEGER NOT NULL,ordinal INTEGER NOT NULL,name TEXT,type TEXT,pieces_json TEXT,PRIMARY KEY(binary_id,addr,ordinal),FOREIGN KEY(binary_id,addr) REFERENCES func(binary_id,addr) ON DELETE SET NULL)'),
])
def test_legacy_keys_and_foreign_key_actions_refuse(populated, table, replacement):
    con, _ = populated
    con.execute(f'DROP TABLE {table}')
    con.execute(replacement)
    expected = 'ix_decomp_bin' if table == 'decomp' and con.execute('PRAGMA user_version').fetchone()[0] in {11, 12, 13} else table
    _refuses_unchanged(con, 'binary_delete_schema_unsupported:' + expected)


def test_modified_canonical_trigger_refuses(populated):
    con, _ = populated
    con.execute('DROP TRIGGER match_review_binary_delete')
    con.execute('CREATE TRIGGER match_review_binary_delete AFTER DELETE ON binary BEGIN DELETE FROM eval; END')
    _refuses_unchanged(con, 'binary_delete_schema_unsupported:match_review_binary_delete')


@pytest.mark.parametrize('scope', ['attached', 'temp'])
def test_attached_and_temporary_schema_objects_refuse(populated, tmp_path, scope):
    con, _ = populated
    if scope == 'attached':
        con.execute('ATTACH DATABASE ? AS foreign_store', (str(tmp_path / 'attached.sqlite'),))
    else:
        con.execute('CREATE TEMP VIEW binary AS SELECT * FROM main.binary')
    _refuses_unchanged(con, 'binary_delete_schema_unsupported:')


class FaultConnection:
    """Intercept only the chosen direct operation; real SQLite performs the rest."""
    def __init__(self, con, *, fail_write=None, commit_failure=False, mismatch=False, begin_failure=False, invalidate=False):
        self.con = con
        self.fail_write = fail_write
        self.commit_failure = commit_failure
        self.mismatch = mismatch
        self.begin_failure = begin_failure
        self.invalidate = invalidate
        self.writes = 0

    def __getattr__(self, key):
        return getattr(self.con, key)

    def execute(self, sql, parameters=()):
        upper = sql.lstrip().upper()
        if upper.startswith('BEGIN') and self.begin_failure:
            raise sqlite3.OperationalError('database is locked')
        if upper.startswith(('DELETE ', 'UPDATE ')):
            self.writes += 1
            if self.writes == self.fail_write:
                if self.invalidate:
                    self.con.rollback()
                raise sqlite3.OperationalError('injected write failure')
        cursor = self.con.execute(sql, parameters)
        if self.mismatch and upper.startswith('DELETE FROM MAIN.BINARY '):
            class WrongCount:
                rowcount = 0
            return WrongCount()
        return cursor

    def commit(self):
        if self.commit_failure:
            raise sqlite3.OperationalError('injected commit failure')
        self.con.commit()


@pytest.mark.parametrize('ordinal', range(1, 21))
@pytest.mark.parametrize('caller_owned', [False, True])
def test_failure_at_every_delete_and_logical_update_rolls_back(populated, ordinal, caller_owned):
    con, _ = populated
    if caller_owned:
        _insert(con, 'eval', run='caller', metric='before', value=1.0)
    before = _snapshot(con)
    proxy = FaultConnection(con, fail_write=ordinal)
    with pytest.raises(sqlite3.OperationalError, match='injected write failure'):
        store.remove_binary(proxy, slug='a')
    assert proxy.writes == ordinal
    assert _snapshot(con) == before
    assert con.in_transaction == caller_owned


@pytest.mark.parametrize('failure', ['commit_failure', 'mismatch', 'begin_failure'])
def test_commit_count_and_lock_failures_never_return_success(populated, failure):
    con, _ = populated
    before = _snapshot(con)
    proxy = FaultConnection(con, **{failure: True})
    with pytest.raises((sqlite3.OperationalError, deletion.BinaryDeleteUnsupported)):
        store.remove_binary(proxy, slug='a')
    assert _snapshot(con) == before
    assert not con.in_transaction


def test_canonical_trigger_execution_failure_rolls_back(populated):
    con, _ = populated
    before = _snapshot(con)
    def deny_revision_delete(action, table, _column, _db, trigger):
        if action == sqlite3.SQLITE_DELETE and table == 'match_review_revision' and trigger:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    con.set_authorizer(deny_revision_delete)
    try:
        with pytest.raises(sqlite3.DatabaseError):
            store.remove_binary(con, slug='a')
    finally:
        con.set_authorizer(None)
    assert _snapshot(con) == before


def test_success_in_caller_transaction_can_be_rolled_back(populated):
    con, _ = populated
    before = _snapshot(con)
    _insert(con, 'eval', run='caller', metric='prior', value=1.0)
    result = store.remove_binary(con, slug='a')
    assert result['deleted']['binary'] == 1 and con.in_transaction
    assert con.execute("SELECT 1 FROM eval WHERE run='caller'").fetchone()
    con.rollback()
    assert _snapshot(con) == before


def test_invalidated_outer_transaction_reports_rollback_failure(populated):
    con, _ = populated
    _insert(con, 'eval', run='caller', metric='prior', value=1.0)
    with pytest.raises(sqlite3.OperationalError, match='savepoint') as caught:
        store.remove_binary(FaultConnection(con, fail_write=2, invalidate=True), slug='a')
    assert isinstance(caught.value.__context__, sqlite3.OperationalError)
    assert not con.in_transaction


def test_snapshot_upgrade_failure_preserves_prior_caller_scope(populated):
    con, path = populated
    other = sqlite3.connect(path, timeout=0)
    con.execute('PRAGMA busy_timeout=0')
    con.execute('BEGIN')
    before = _snapshot(con)
    try:
        other.execute("INSERT INTO eval(run,metric,value) VALUES('concurrent','new',1)")
        other.commit()
        with pytest.raises(sqlite3.OperationalError, match='locked'):
            store.remove_binary(con, slug='a')
        assert con.in_transaction
        assert _snapshot(con) == before
    finally:
        con.rollback()
        other.close()


def test_missing_selector_and_target_remain_errors(populated):
    con, _ = populated
    before = _snapshot(con)
    with pytest.raises(ValueError, match='repo_path or slug'):
        store.remove_binary(con)
    with pytest.raises(SystemExit, match='no binary matching'):
        store.remove_binary(con, slug='absent')
    assert _snapshot(con) == before


def test_opener_never_creates_missing_path_or_initializes(tmp_path, monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail('initialization is forbidden on removal')
    monkeypatch.setattr(store, 'connect', forbidden)
    missing = tmp_path / 'missing' / 'corpus.sqlite'
    with pytest.raises(sqlite3.OperationalError):
        deletion.open_for_delete(missing)
    assert not missing.parent.exists()
    # Existing legacy files open as-is and are refused only inside the atomic scope.
    path = tmp_path / 'legacy.sqlite'
    sqlite3.connect(path).close()
    with deletion.open_for_delete(path) as con:
        assert con.execute('PRAGMA user_version').fetchone()[0] == 0
        assert con.execute('SELECT COUNT(*) FROM sqlite_master').fetchone()[0] == 0
        with pytest.raises(deletion.BinaryDeleteUnsupported):
            store.remove_binary(con, slug='a')
    con.close()


def test_cli_refusal_is_nonzero_without_success_json(populated, capsys, monkeypatch):
    from agentdecompile_recovery.corpus import cli
    con, path = populated
    _insert(con, 'identity', logical_id=10, binary_id=2, addr=16)
    con.commit()
    monkeypatch.setattr(store, 'connect', lambda *_a, **_k: pytest.fail('initializing connect used'))
    assert cli.main(['remove-binary', '--db', str(path), '--slug', 'a']) == 2
    captured = capsys.readouterr()
    assert captured.out == ''
    assert 'binary_delete_dependency_unsupported:identity' in captured.err


def test_http_confirmation_errors_and_cache_commit_boundary(populated, monkeypatch):
    from agentdecompile_recovery.corpus.dashboard import workbench
    con, path = populated
    monkeypatch.setattr(workbench, 'live_db', lambda: path)
    monkeypatch.setattr(workbench, '_open_store', lambda: pytest.fail('initializing opener used'))
    monkeypatch.setattr(store, 'connect', lambda *_a, **_k: pytest.fail('initializing connect used'))
    monkeypatch.setattr(workbench, '_CACHE', {'retained': 'until commit'})
    original_opener = deletion.open_for_delete
    monkeypatch.setattr(deletion, 'open_for_delete', lambda _p: pytest.fail('confirmation opened database'))
    assert workbench.remove_registered_binary('a', confirm=False)['ok'] is False
    assert workbench.remove_registered_binary(' ', confirm=True)['ok'] is False
    def fail_open(_path):
        raise sqlite3.OperationalError('open failure')
    monkeypatch.setattr(deletion, 'open_for_delete', fail_open)
    assert workbench.remove_registered_binary('a', confirm=True) == {'ok': False, 'error': 'open failure'}
    assert workbench._CACHE
    monkeypatch.setattr(deletion, 'open_for_delete', original_opener)
    _insert(con, 'identity', logical_id=10, binary_id=2, addr=16)
    con.commit()
    assert workbench.remove_registered_binary('a', confirm=True)['ok'] is False
    assert workbench._CACHE
    con.execute('DELETE FROM identity WHERE binary_id=2')
    con.commit()
    result = workbench.remove_registered_binary(' a ', confirm=True)
    assert result['ok'] is True and result['removed']['deleted']['binary'] == 1
    assert workbench._CACHE == {}
    assert con.execute('SELECT 1 FROM binary WHERE id=1').fetchone() is None


@pytest.mark.parametrize('table', sorted(deletion.MANDATORY_TABLES))
def test_every_mandatory_table_is_required(populated, table):
    con, _ = populated
    con.execute(f'DROP TABLE {table}')
    _refuses_unchanged(con, 'binary_delete_schema_unsupported:')


@pytest.mark.parametrize('parent,child', [('recovered_function', 'reuse_candidate'), ('ghidra_type', 'ghidra_type_origin')])
def test_optional_child_requires_its_recognized_parent(populated, parent, child):
    con, _ = populated
    con.execute(f'DROP TABLE {parent}')
    expected = 'ix_ghidra_type_bin' if parent == 'ghidra_type' and con.execute('PRAGMA user_version').fetchone()[0] == 13 else parent
    _refuses_unchanged(con, 'binary_delete_schema_unsupported:' + expected)


def test_known_additions_and_old_optional_layout_are_admitted(populated):
    con, _ = populated
    con.execute('ALTER TABLE binary ADD COLUMN code_func_count INTEGER')
    if con.execute('PRAGMA user_version').fetchone()[0] == 9:
        con.execute('ALTER TABLE func ADD COLUMN stabs_name TEXT')
        con.execute('ALTER TABLE func ADD COLUMN stabs_type TEXT')
        con.execute('CREATE INDEX ix_func_srcfile ON func(binary_id, source_file)')
    if con.execute('PRAGMA user_version').fetchone()[0] < 13:
        con.execute('ALTER TABLE ghidra_type ADD COLUMN origin TEXT')
    if con.execute('PRAGMA user_version').fetchone()[0] < 11:
        con.execute('ALTER TABLE decomp DROP COLUMN ast_fingerprint')
    con.commit()
    assert store.remove_binary(con, slug='a')['deleted']['binary'] == 1


def test_view_cannot_impersonate_optional_table(populated):
    con, _ = populated
    con.execute('DROP TABLE decomp')
    con.execute('CREATE VIEW decomp AS SELECT binary_id,addr FROM func')
    expected = 'ix_decomp_bin' if con.execute('PRAGMA user_version').fetchone()[0] in {11, 12, 13} else 'decomp'
    _refuses_unchanged(con, 'binary_delete_schema_unsupported:' + expected)


def test_unbound_raw_only_corpus_is_a_real_positive(populated):
    con, _ = populated
    con.execute('DELETE FROM identity')
    con.execute('DELETE FROM match')
    con.execute('DELETE FROM func_convention_derived')
    con.commit()
    result = store.remove_binary(con, slug='b')
    assert result['deleted']['binary'] == 1
    assert result['deleted']['func'] == 1
    assert con.execute('SELECT COUNT(*) FROM binary WHERE id IN (1,3)').fetchone()[0] == 2


def test_owned_scope_rolls_back_baseexception(populated):
    con, _ = populated
    before = _snapshot(con)
    class Interrupting(FaultConnection):
        def execute(self, sql, parameters=()):
            cursor = super().execute(sql, parameters)
            if sql.startswith('DELETE FROM main.recovered_function'):
                raise KeyboardInterrupt('interrupted after deletion')
            return cursor
    with pytest.raises(KeyboardInterrupt):
        store.remove_binary(Interrupting(con), slug='a')
    assert _snapshot(con) == before
    assert not con.in_transaction


def test_routes_close_owned_handles_on_refusal(populated, monkeypatch, capsys):
    from agentdecompile_recovery.corpus import cli
    from agentdecompile_recovery.corpus.dashboard import workbench
    _, path = populated
    handles = []
    original_opener = deletion.open_for_delete
    def opener(_path):
        con = original_opener(_path)
        handles.append(con)
        return con
    monkeypatch.setattr(deletion, 'open_for_delete', opener)
    monkeypatch.setattr(workbench, 'live_db', lambda: path)
    assert cli.main(['remove-binary', '--db', str(path), '--slug', 'absent']) == 2
    assert capsys.readouterr().out == ''
    assert workbench.remove_registered_binary('absent', confirm=True)['ok'] is False
    assert len(handles) == 2
    for handle in handles:
        with pytest.raises(sqlite3.ProgrammingError, match='closed'):
            handle.execute('SELECT 1')


def test_removal_never_initializes_reconstructs_or_replaces_proof(populated, monkeypatch):
    from agentdecompile_recovery.corpus import logical, migrations, propagate, cross_place_admission
    con, _ = populated
    def forbidden(*_args, **_kwargs):
        pytest.fail('deletion attempted an initialization or provenance reconstruction')
    for module, names in ((store, ('connect', 'ensure_func_columns', 'ensure_binary_columns', 'backfill_recovery_family')),
                          (migrations, ('apply_pending',)), (logical, ('build', 'resolve_ambiguous')),
                          (propagate, ('bind_identities',)), (cross_place_admission, ('identity_state', 'qualify'))):
        for name in names:
            monkeypatch.setattr(module, name, forbidden)
    assert store.remove_binary(con, slug='a')['deleted']['binary'] == 1


def test_falsely_stamped_v10_does_not_initialize_v9(populated):
    con, _ = populated
    if con.execute('PRAGMA user_version').fetchone()[0] != 9:
        pytest.skip('requires independently constructed v9')
    con.execute('PRAGMA user_version=10')
    _refuses_unchanged(con, 'binary_delete_schema_unsupported:')


@pytest.mark.parametrize('damage', [
    'ALTER TABLE func DROP COLUMN stabs_name',
    'ALTER TABLE func DROP COLUMN stabs_type',
    'DROP INDEX ix_func_srcfile',
    'DROP INDEX ix_stabs_type_bin',
    'DROP INDEX ix_stabs_type_src',
    "DELETE FROM schema_migration WHERE version=10",
    "UPDATE schema_migration SET name='wrong' WHERE version=10",
])
def test_v10_stabs_postconditions_required_without_initialization(populated, damage):
    con, _ = populated
    if con.execute('PRAGMA user_version').fetchone()[0] != 10:
        pytest.skip('v9 intentionally retains optional STABS fields/index')
    con.execute(damage)
    _refuses_unchanged(con, 'binary_delete_schema_unsupported:')


@pytest.mark.parametrize('installed', [False, True])
def test_thirteen_last_binary_deletion_retains_global_type_inventory_history(installed):
    from tests.test_corpus_type_schema import current, rows
    con = current(installed=installed)
    state = rows(con, 'type_inventory_state')
    for slug in ('recipient', 'donor', 'foreign'):
        receipt = store.remove_binary(con, slug=slug)
        assert receipt['deleted']['binary'] == 1
        assert 'type_inventory_state' not in receipt['deleted']
    assert not rows(con, 'binary')
    assert rows(con, 'type_inventory_state') == state
    assert store.type_inventory_state(con) == ('installed' if installed else 'absent')
    con.close()


@pytest.mark.parametrize('damage', ['DROP TABLE ghidra_type', 'DROP TABLE ghidra_type_origin',
    'DROP TABLE type_inventory_state', 'DELETE FROM type_inventory_state',
    'DROP INDEX ix_ghidra_type_bin',
    "INSERT INTO ghidra_type VALUES (1,'Bad','struct',4,'bad',0,NULL)"])
def test_thirteen_required_type_state_refuses_atomically_with_caller_work(damage):
    from tests.test_corpus_type_schema import current, snapshot
    con = current()
    con.execute(damage)
    con.commit()
    con.execute("INSERT INTO eval(run) VALUES ('caller')")
    before = snapshot(con)
    with pytest.raises(deletion.BinaryDeleteUnsupported):
        store.remove_binary(con, slug='recipient')
    assert snapshot(con) == before and con.in_transaction
    con.close()


def test_actual_fourteen_deletion_refuses_without_repair():
    from tests.test_corpus_type_schema import current, future, snapshot
    con = future(current())
    con.execute("INSERT INTO eval(run) VALUES ('caller')")
    before = snapshot(con)
    with pytest.raises(deletion.BinaryDeleteUnsupported, match='version'):
        store.remove_binary(con, slug='recipient')
    assert snapshot(con) == before and con.in_transaction
    con.close()
