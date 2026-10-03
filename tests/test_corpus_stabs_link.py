from __future__ import annotations

import sqlite3

import pytest

from agentdecompile_recovery.corpus import migrations, store
from agentdecompile_recovery.corpus.stabs_link import (
    apply_manifest_records,
    ensure_columns,
    propagate_source_files,
    replace_stabs_types,
    select_slices,
)


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    migrations.apply_pending(con)
    ensure_columns(con)
    con.executemany(
        "INSERT INTO binary(id, repo_path, slug, platform) VALUES (?,?,?,?)",
        [(1, "one", "one", "mac"), (2, "two", "two", "win")],
    )
    return con


def test_preserves_existing_logical_attribution_and_uses_one_donor_pair() -> None:
    con = _connect()
    con.executemany(
        "INSERT INTO logical_function(id, source_file, object_file) VALUES (?,?,?)",
        [(1, "reviewed.cpp", "reviewed.o"), (2, None, None)],
    )
    con.executemany(
        "INSERT INTO func(binary_id, addr, source_file, object_file) VALUES (?,?,?,?)",
        [
            (1, 0x10, "old.cpp", "old.o"),
            (1, 0x20, "first.cpp", "first.o"),
            (2, 0x20, "second.cpp", "second.o"),
            (2, 0x21, None, None),
        ],
    )
    con.executemany(
        "INSERT INTO identity(logical_id, binary_id, addr, confidence) VALUES (?,?,?,?)",
        [(1, 1, 0x10, 1.0), (2, 1, 0x20, 1.0), (2, 2, 0x20, 1.0), (2, 2, 0x21, 1.0)],
    )
    con.commit()

    propagate_source_files(con)

    rows = {
        r["id"]: (r["source_file"], r["object_file"])
        for r in con.execute("SELECT id, source_file, object_file FROM logical_function")
    }
    assert rows[1] == ("reviewed.cpp", "reviewed.o")
    assert rows[2] in {("first.cpp", "first.o"), ("second.cpp", "second.o")}
    propagated = con.execute(
        "SELECT source_file, object_file FROM func WHERE binary_id=2 AND addr=?",
        (0x21,),
    ).fetchone()
    assert tuple(propagated) == rows[2]


def test_type_refresh_is_idempotent_with_nullable_fields() -> None:
    con = _connect()
    duplicated = [
        {
            "source_file": None,
            "object_file": None,
            "name": "CThing",
            "kind": None,
            "stab": "CThing:t(0,1)",
            "func_addr": None,
        },
        {
            "source_file": None,
            "object_file": None,
            "name": "CThing",
            "kind": None,
            "stab": "CThing:t(0,1)",
            "func_addr": None,
        },
    ]
    replace_stabs_types(con, 1, duplicated)
    replace_stabs_types(con, 1, duplicated)
    count = con.execute("SELECT COUNT(*) FROM stabs_type WHERE binary_id=1").fetchone()[0]
    assert count == 1
    replace_stabs_types(con, 1, [{**duplicated[0], "stab": "CThing:t(0,2)"}])
    stabs = con.execute("SELECT stab FROM stabs_type WHERE binary_id=1").fetchall()
    assert [row[0] for row in stabs] == ["CThing:t(0,2)"]


def test_selects_only_the_binary_architecture_from_a_fat_image() -> None:
    parsed = {
        "slices": [
            {"arch": "i386", "stabs": {"types": [{"name": "X86"}]}},
            {"arch": "ppc", "stabs": {"types": [{"name": "PPC"}]}},
        ]
    }
    selected = select_slices(parsed, "i386")
    assert [item["arch"] for item in selected] == ["i386"]


def test_manifest_application_preserves_existing_function_attribution() -> None:
    con = _connect()
    con.executemany(
        "INSERT INTO func(binary_id, addr, source_file, object_file) VALUES (?,?,?,?)",
        [(1, 0x10, "reviewed.cpp", "reviewed.o"), (1, 0x20, None, "stale.o")],
    )
    records = [
        {
            "addr": 0x10,
            "action": "keep_human_attach_metadata",
            "source_file": "compiler.cpp",
            "object_file": "compiler.o",
            "stabs_name": "CompilerName",
            "stabs_type": "F(0,1)",
        },
        {
            "addr": 0x20,
            "action": "attach_stabs",
            "source_file": "fresh.cpp",
            "object_file": "fresh.o",
            "stabs_name": "FreshName",
            "stabs_type": "F(0,2)",
        },
    ]
    assert apply_manifest_records(con, 1, records) == 2
    rows = {
        row["addr"]: tuple(row)[1:]
        for row in con.execute(
            "SELECT addr, source_file, object_file, stabs_name, stabs_type "
            "FROM func WHERE binary_id=1 ORDER BY addr"
        )
    }
    assert rows[0x10] == ("reviewed.cpp", "reviewed.o", "CompilerName", "F(0,1)")
    assert rows[0x20] == ("fresh.cpp", "fresh.o", "FreshName", "F(0,2)")


def test_manifest_donors_scope_propagation_to_reachable_identities() -> None:
    con = _connect()
    con.executemany(
        "INSERT INTO logical_function(id, source_file, object_file) VALUES (?,?,?)",
        [(1, None, None), (2, "unrelated.cpp", "unrelated.o")],
    )
    con.executemany(
        "INSERT INTO func(binary_id, addr, source_file, object_file) VALUES (?,?,?,?)",
        [(1, 0x10, "donor.cpp", "donor.o"), (2, 0x20, None, None), (2, 0x30, None, None)],
    )
    con.executemany(
        "INSERT INTO identity(logical_id, binary_id, addr, confidence) VALUES (?,?,?,?)",
        [(1, 1, 0x10, 1.0), (1, 2, 0x20, 1.0), (2, 2, 0x30, 1.0)],
    )
    con.commit()
    pushed = propagate_source_files(
        con,
        donor_rows=[{"binary_id": 1, "addr": 0x10, "source_file": "donor.cpp", "object_file": "donor.o"}],
    )
    assert pushed == 1
    propagated = con.execute(
        "SELECT source_file, object_file FROM func WHERE binary_id=2 AND addr=?",
        (0x20,),
    ).fetchone()
    unrelated = con.execute("SELECT source_file FROM func WHERE binary_id=2 AND addr=?", (0x30,)).fetchone()[0]
    assert tuple(propagated) == ("donor.cpp", "donor.o")
    assert unrelated is None


@pytest.mark.parametrize('current', [False, True])
def test_ensure_columns_keeps_caller_work_on_success_and_refusal(current):
    con = sqlite3.connect(':memory:')
    try:
        migrations.apply_pending(con, target=10 if current else 9)
        con.execute("INSERT INTO binary(repo_path,slug) VALUES ('/pending','pending')")
        seen = []
        con.set_trace_callback(seen.append)
        if current:
            ensure_columns(con)
        else:
            with pytest.raises(ValueError, match='STABS schema required'):
                ensure_columns(con)
        assert con.in_transaction
        assert con.execute('SELECT slug FROM binary').fetchone()[0] == 'pending'
        assert not any(s.upper().startswith(('COMMIT', 'ROLLBACK', 'ALTER ', 'CREATE ')) for s in seen)
        con.rollback()
        assert con.execute('SELECT COUNT(*) FROM binary').fetchone()[0] == 0
    finally:
        con.close()


def test_raw_unledgered_handle_is_refused_without_installation():
    con = sqlite3.connect(':memory:')
    try:
        con.executescript(store.SCHEMA)
        con.execute("INSERT INTO binary(repo_path,slug) VALUES ('/pending','pending')")
        before = list(con.execute('SELECT type,name,sql FROM sqlite_master'))
        with pytest.raises(ValueError, match='STABS schema required: observed version 0'):
            ensure_columns(con)
        assert list(con.execute('SELECT type,name,sql FROM sqlite_master')) == before
        assert con.in_transaction
        assert con.execute('SELECT slug FROM binary').fetchone()[0] == 'pending'
    finally:
        con.close()


class _TypeFailure:
    def __init__(self, con, failure):
        self.con, self.failure = con, failure

    def __getattr__(self, name):
        return getattr(self.con, name)

    def executemany(self, sql, values):
        result = self.con.executemany(sql, values)
        if self.failure == 'interrupt':
            raise KeyboardInterrupt('after inserts')
        return result

    def commit(self):
        if self.failure == 'commit':
            raise sqlite3.OperationalError('commit refused before durability')
        self.con.commit()


def _seed_types(con):
    con.executemany('INSERT INTO stabs_type(binary_id,name,stab) VALUES (?,?,?)',
                    [(1, 'Old', 'old'), (2, 'Survivor', 'untouched')])
    con.commit()
    return [tuple(r) for r in con.execute('SELECT * FROM stabs_type ORDER BY id')]


@pytest.mark.parametrize('caller_owned', [False, True])
def test_replacement_success_preserves_other_binary_and_transaction_owner(caller_owned):
    con = _connect()
    try:
        before = _seed_types(con)
        if caller_owned:
            con.execute("INSERT INTO eval(run,metric) VALUES ('caller','pending')")
        payload = [{'name': 'New', 'stab': 'new', 'kind': None}]
        assert replace_stabs_types(con, 1, payload + payload) == 1
        assert con.in_transaction is caller_owned
        assert [tuple(r) for r in con.execute('SELECT * FROM stabs_type WHERE binary_id=2')] == [before[1]]
        assert con.execute('SELECT stab FROM stabs_type WHERE binary_id=1').fetchone()[0] == 'new'
        if caller_owned:
            con.rollback()
            assert [tuple(r) for r in con.execute('SELECT * FROM stabs_type ORDER BY id')] == before
            assert con.execute('SELECT COUNT(*) FROM eval').fetchone()[0] == 0
        else:
            con.rollback()
            assert con.execute('SELECT stab FROM stabs_type WHERE binary_id=1').fetchone()[0] == 'new'
    finally:
        con.close()


@pytest.mark.parametrize('caller_owned', [False, True])
@pytest.mark.parametrize('failure', ['insert', 'interrupt', 'commit'])
def test_replacement_failures_restore_types_without_committing_caller_work(caller_owned, failure):
    if caller_owned and failure == 'commit':
        pytest.skip('caller-owned operation has no commit; success case checks provisional result')
    con = _connect()
    try:
        before = _seed_types(con)
        if caller_owned:
            con.execute("INSERT INTO eval(run,metric) VALUES ('caller','pending')")
        payload = [{'name': 'New', 'stab': None if failure == 'insert' else 'new'}]
        expected = {'insert': sqlite3.IntegrityError, 'interrupt': KeyboardInterrupt,
                    'commit': sqlite3.OperationalError}[failure]
        with pytest.raises(expected):
            replace_stabs_types(_TypeFailure(con, failure), 1, payload)
        assert con.in_transaction is caller_owned
        assert [tuple(r) for r in con.execute('SELECT * FROM stabs_type ORDER BY id')] == before
        assert con.execute('SELECT COUNT(*) FROM eval').fetchone()[0] == int(caller_owned)
    finally:
        con.close()


def test_rollback_failure_is_reported_not_success():
    con = _connect()
    _seed_types(con)

    class BrokenRollback(_TypeFailure):
        def rollback(self):
            raise RuntimeError('rollback failed')

    try:
        with pytest.raises(RuntimeError, match='rollback failed') as caught:
            replace_stabs_types(BrokenRollback(con, 'interrupt'), 1, [{'name': 'New', 'stab': 'new'}])
        assert isinstance(caught.value.__context__, KeyboardInterrupt)
        assert con.in_transaction
    finally:
        con.rollback()
        con.close()


def test_manifest_commit_false_keeps_caller_ownership_and_unknown_actions_untouched():
    con = _connect()
    try:
        con.execute('INSERT INTO func(binary_id,addr) VALUES (1,16)')
        con.commit()
        con.execute("INSERT INTO eval(run,metric) VALUES ('caller','pending')")
        assert apply_manifest_records(con, 1, [
            {'addr': 16, 'action': 'attach_stabs', 'source_file': 'new.cpp', 'stabs_name': 'New'},
            {'addr': 16, 'action': 'unknown', 'source_file': 'bad.cpp'},
        ], commit=False) == 1
        assert con.in_transaction
        assert con.execute('SELECT source_file FROM func').fetchone()[0] == 'new.cpp'
        con.rollback()
        assert con.execute('SELECT source_file FROM func').fetchone()[0] is None
        assert con.execute('SELECT COUNT(*) FROM eval').fetchone()[0] == 0
    finally:
        con.close()


@pytest.mark.parametrize('failure', ['savepoint', 'release', 'rollback'])
def test_caller_savepoint_failures_never_commit_or_erase_outer_work(failure):
    con = _connect()
    before = _seed_types(con)
    con.execute("INSERT INTO eval(run,metric) VALUES ('caller','pending')")

    class SavepointFailure(_TypeFailure):
        failed = False

        def execute(self, sql, *args):
            target = {'savepoint': 'SAVEPOINT ', 'release': 'RELEASE SAVEPOINT ',
                      'rollback': 'ROLLBACK TO SAVEPOINT '}[failure]
            if sql.startswith(target) and not self.failed:
                self.failed = True
                raise RuntimeError('injected ' + failure)
            return self.con.execute(sql, *args)

    try:
        proxy = SavepointFailure(con, 'interrupt' if failure == 'rollback' else 'none')
        with pytest.raises(RuntimeError, match='injected ' + failure) as caught:
            replace_stabs_types(proxy, 1, [{'name': 'New', 'stab': 'new'}])
        assert con.in_transaction
        assert con.execute('SELECT COUNT(*) FROM eval').fetchone()[0] == 1
        if failure == 'rollback':
            assert isinstance(caught.value.__context__, KeyboardInterrupt)
        else:
            assert [tuple(r) for r in con.execute('SELECT * FROM stabs_type ORDER BY id')] == before
    finally:
        con.rollback()
        con.close()
