"""Synthetic v4 upgrade guarantees; no production corpus is opened."""
from pathlib import Path
import sqlite3

import pytest

from agentdecompile_recovery.corpus import migrations, store
from agentdecompile_recovery.corpus import match_review_schema as schema

FIXTURE = Path(__file__).parent / 'fixtures/store/legacy_schema_v0.sql'


def old_store(path, *, matches=3):
    con = sqlite3.connect(path)
    con.executescript(FIXTURE.read_text())
    con.executemany('INSERT INTO binary(id,repo_path,slug) VALUES(?,?,?)',
                    [(2, '/two', 'two'), (7, '/seven', 'seven')])
    con.executemany('INSERT INTO match(id,run,src_binary,dst_binary,status,evidence) VALUES(?,?,?,?,?,?)',
                    ((100 + n * 7, 'old', 2, 7, 'review', '{}') for n in range(matches)))
    con.commit()
    migrations.apply_pending(con, target=3)
    return con


def snapshot(con):
    return {table: (list(con.execute(f'PRAGMA table_info({table})')),
                    list(con.execute(f'SELECT * FROM {table} ORDER BY id')))
            for table in ('binary', 'match')}


def test_populated_legacy_upgrade_preserves_layout_rows_and_seeds_in_id_order(tmp_path):
    con = old_store(tmp_path / 'old.sqlite', matches=4097)
    before = snapshot(con)
    seen = []
    con.set_trace_callback(seen.append)
    # Migrations 5-9 (function_storage, typed_fields, matching_evidence,
    # pcode_channel, match_metadata) landed after this test; they're not
    # under test here, so pin to v4 -- the version this test is about.
    assert [step.version for step in migrations.apply_pending(con, target=4)] == [4]
    con.set_trace_callback(None)
    assert snapshot(con) == before
    schema.require(con)
    assert con.execute('SELECT kind,entity_id,revision FROM match_review_revision ORDER BY revision').fetchall() == (
        [('binary', 2, 1), ('binary', 7, 2)] + [('match', 100+n*7, n+3) for n in range(4097)])
    # SQL execution count stays constant with corpus size; no per-row SELECT/UPDATE seeding.
    assert len(seen) < 100
    assert con.execute('SELECT next_revision FROM match_review_control').fetchone() == (4099,)
    assert [(r['version'],r['name']) for r in migrations.ledger_rows(con)][-1] == (4,'match_review')
    con.close()


def test_allocator_survives_empty_table_and_reinstall_is_identity_stable(tmp_path):
    con = old_store(tmp_path / 'old.sqlite')
    migrations.apply_pending(con)
    before = con.execute('SELECT incarnation,next_revision FROM match_review_control').fetchone()
    con.execute('DELETE FROM match')
    con.execute("INSERT INTO match(id,status) VALUES(100,'review')")
    revision = con.execute("SELECT revision FROM match_review_revision WHERE kind='match' AND entity_id=100").fetchone()[0]
    assert revision > before[1]
    con.commit()
    identity = con.execute('SELECT * FROM match_review_control').fetchall()
    membership = con.execute('SELECT * FROM match_review_revision ORDER BY kind,entity_id').fetchall()
    con.execute('BEGIN IMMEDIATE')
    schema.install(con)
    con.commit()
    assert con.execute('SELECT * FROM match_review_control').fetchall() == identity
    assert con.execute('SELECT * FROM match_review_revision ORDER BY kind,entity_id').fetchall() == membership
    con.close()


@pytest.mark.parametrize('broken', ['version', 'ledger', 'trigger', 'trigger_body', 'table_shape', 'index'])
def test_required_schema_refuses_missing_or_corrupt_contract(tmp_path, broken):
    con = old_store(tmp_path / 'old.sqlite')
    migrations.apply_pending(con)
    if broken == 'version': con.execute('PRAGMA user_version=3')
    elif broken == 'ledger': con.execute('DROP TABLE schema_migration')
    elif broken == 'index': con.execute('DROP INDEX match_review_binary_repo_path')
    elif broken in ('trigger', 'trigger_body'):
        con.execute('DROP TRIGGER match_review_match_update')
        if broken == 'trigger_body':
            con.execute('CREATE TRIGGER match_review_match_update AFTER UPDATE ON match BEGIN SELECT 1; END')
    else: con.execute('ALTER TABLE match_review_revision ADD COLUMN ignored TEXT')
    con.commit()
    with pytest.raises(ValueError, match='review_schema_(required|corrupt)'):
        schema.require(con)
    con.close()


def test_readonly_unupgraded_store_refuses_without_schema_write(tmp_path):
    path = tmp_path / 'old.sqlite'
    old_store(path).close()
    con = store.connect(path, read_only=True)
    assert migrations.user_version(con) == 3
    with pytest.raises(ValueError, match='review_schema_required'):
        schema.require(con)
    assert not con.execute("SELECT 1 FROM sqlite_master WHERE name LIKE 'match_review_%'").fetchone()
    con.close()


def test_partial_install_refused_and_migration_rolled_back(tmp_path):
    con = old_store(tmp_path / 'old.sqlite')
    con.execute('CREATE TABLE match_review_control(singleton INTEGER)')
    con.commit()
    before = snapshot(con)
    with pytest.raises(ValueError, match='review_schema_(required|corrupt)'):
        migrations.apply_pending(con)
    assert migrations.user_version(con) == 3
    assert [r['version'] for r in migrations.ledger_rows(con)] == [1,2,3]
    assert snapshot(con) == before
    assert con.execute("SELECT name FROM sqlite_master WHERE name LIKE 'match_review_%'").fetchall() == [('match_review_control',)]
    con.close()


def test_ledger_failure_rolls_back_entire_review_migration(tmp_path):
    con = old_store(tmp_path / 'old.sqlite')
    con.execute("CREATE TRIGGER refuse_v4 BEFORE INSERT ON schema_migration WHEN NEW.version=4 BEGIN SELECT RAISE(ABORT,'ledger probe'); END")
    con.commit()
    before = snapshot(con)
    with pytest.raises(sqlite3.IntegrityError, match='ledger probe'):
        migrations.apply_pending(con)
    assert migrations.user_version(con) == 3
    assert [r['version'] for r in migrations.ledger_rows(con)] == [1,2,3]
    assert snapshot(con) == before
    assert not con.execute("SELECT 1 FROM sqlite_master WHERE name LIKE 'match_review_%'").fetchone()
    con.close()


def test_audit_is_append_only_and_survives_match_deletion(tmp_path):
    con = old_store(tmp_path / 'old.sqlite')
    migrations.apply_pending(con)
    con.execute("""INSERT INTO match_review_audit(match_id,incarnation,selection,decision,
        old_status,new_status,old_revision,new_revision,observed_token,basis_json,decided_at)
        VALUES(100,'incarnation','selection','accept','review','verify',1,2,'token','{}','time')""")
    con.commit()
    for sql in ('DELETE FROM match_review_audit', "UPDATE match_review_audit SET decision='reject'",
                'INSERT OR REPLACE INTO match_review_audit SELECT * FROM match_review_audit'):
        with pytest.raises(sqlite3.IntegrityError, match='review_audit_append_only'):
            con.execute(sql)
        con.rollback()
    con.execute('DELETE FROM match')
    con.commit()
    assert con.execute('SELECT match_id,decision FROM match_review_audit').fetchall() == [(100,'accept')]
    con.close()


@pytest.mark.parametrize('corruption', ['missing_revision', 'allocator_regressed'])
def test_reinstall_refuses_partial_control_state(tmp_path, corruption):
    con = old_store(tmp_path / 'old.sqlite')
    migrations.apply_pending(con)
    if corruption == 'missing_revision':
        con.execute("DELETE FROM match_review_revision WHERE kind='match' AND entity_id=100")
    else: con.execute('UPDATE match_review_control SET next_revision=0')
    con.commit()
    con.execute('BEGIN IMMEDIATE')
    with pytest.raises(ValueError, match='review_schema_corrupt'):
        schema.install(con)
    con.rollback()
    con.close()


def test_allocator_overflow_refuses_entity_write_atomically(tmp_path):
    con = old_store(tmp_path / 'old.sqlite')
    migrations.apply_pending(con)
    con.execute('UPDATE match_review_control SET next_revision=?', ((1 << 63)-1,))
    con.commit()
    before = snapshot(con)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO match(id,status) VALUES(999,'review')")
    con.rollback()
    assert snapshot(con) == before
    con.close()


@pytest.mark.parametrize('unique_key', ['repo_path', 'slug'])
@pytest.mark.parametrize('operation', ['INSERT', 'UPDATE'])
def test_natural_key_replace_cleans_membership_and_preserves_aba(tmp_path, unique_key, operation):
    con = old_store(tmp_path / 'old.sqlite')
    migrations.apply_pending(con)
    assert con.execute('PRAGMA recursive_triggers').fetchone() == (0,)
    old_revision = con.execute("SELECT revision FROM match_review_revision WHERE kind='binary' AND entity_id=2").fetchone()[0]
    value = '/two' if unique_key == 'repo_path' else 'two'
    if operation == 'INSERT':
        values = [9, '/nine', 'nine']
        values[1 if unique_key == 'repo_path' else 2] = value
        con.execute('INSERT OR REPLACE INTO binary(id,repo_path,slug) VALUES(?,?,?)', values)
        new_id = 9
    else:
        con.execute(f'UPDATE OR REPLACE binary SET {unique_key}=? WHERE id=7', (value,))
        new_id = 7
    assert con.execute('SELECT 1 FROM binary WHERE id=2').fetchone() is None
    assert con.execute("SELECT 1 FROM match_review_revision WHERE kind='binary' AND entity_id=2").fetchone() is None
    new_revision = con.execute("SELECT revision FROM match_review_revision WHERE kind='binary' AND entity_id=?", (new_id,)).fetchone()[0]
    assert new_revision > old_revision
    con.execute("INSERT INTO binary(id,repo_path,slug) VALUES(2,'/restored','restored')")
    assert con.execute("SELECT revision FROM match_review_revision WHERE kind='binary' AND entity_id=2").fetchone()[0] > new_revision
    con.commit()
    before = con.execute('SELECT * FROM match_review_revision ORDER BY kind,entity_id').fetchall()
    con.execute('BEGIN IMMEDIATE'); schema.install(con); con.commit()
    assert con.execute('SELECT * FROM match_review_revision ORDER BY kind,entity_id').fetchall() == before
    con.close()


@pytest.mark.parametrize('operation', ['INSERT', 'UPDATE'])
def test_ignored_natural_key_conflict_preserves_membership(tmp_path, operation):
    con = old_store(tmp_path / 'old.sqlite')
    migrations.apply_pending(con)
    before = con.execute('SELECT * FROM match_review_revision ORDER BY kind,entity_id').fetchall()
    if operation == 'INSERT':
        con.execute("INSERT OR IGNORE INTO binary(id,repo_path,slug) VALUES(9,'/two','new')")
    else:
        con.execute("UPDATE OR IGNORE binary SET slug='two' WHERE id=7")
    assert con.execute('SELECT * FROM match_review_revision ORDER BY kind,entity_id').fetchall() == before
    con.commit()
    con.execute('BEGIN IMMEDIATE'); schema.install(con); con.commit()
    con.close()


def test_replace_conflicting_with_two_different_binary_rows_cleans_both(tmp_path):
    con = old_store(tmp_path / 'old.sqlite')
    migrations.apply_pending(con)
    con.execute("INSERT OR REPLACE INTO binary(id,repo_path,slug) VALUES(9,'/two','seven')")
    assert con.execute('SELECT id FROM binary').fetchall() == [(9,)]
    assert con.execute("SELECT entity_id FROM match_review_revision WHERE kind='binary'").fetchall() == [(9,)]
    con.close()
