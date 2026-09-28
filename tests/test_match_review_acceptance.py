"""Synthetic transactional acceptance for the unactivated review service core."""
import json
import sqlite3
import threading

import pytest

from agentdecompile_recovery.corpus import match_review as review
from agentdecompile_recovery.corpus import match_review_schema as schema
from agentdecompile_recovery.corpus import store


@pytest.fixture
def context(tmp_path):
    path = tmp_path / 'corpus.sqlite'
    con = store.connect(path)
    con.executemany('INSERT INTO binary(id,repo_path,slug,content_sha256) VALUES(?,?,?,?)',
                    [(1,'donor','donor','a'), (2,'recipient','recipient','b')])
    con.executemany("""INSERT INTO match
        (id,run,src_binary,src_addr,dst_binary,dst_addr,score,margin,evidence,status,relation)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        [(1,'run',1,4096,2,8192,.9,.1,'{}','review','one_to_one'),
         (2,'run',1,4100,2,8200,.8,.1,'{}','review','one_to_one')])
    con.commit(); con.close()
    return review.pin_context(path, 'selection-one')


def entry(context, match_id=1, decision='accept'):
    row = next(row for row in review.list_review(context)['rows'] if row['match']['id'] == match_id)
    return {'matchId': match_id, 'token': row['token'], 'decision': decision}


def state(context):
    with sqlite3.connect(context.path) as con:
        return (con.execute('SELECT id,status FROM match ORDER BY id').fetchall(),
                con.execute('SELECT count(*) FROM match_review_audit').fetchone()[0])


def mutate(context, sql, args=()):
    with sqlite3.connect(context.path) as con:
        con.execute(sql, args)


def test_single_and_batch_decisions_persist_exact_audit(context):
    first, second = entry(context), entry(context, 2, 'reject')
    result = review.decide_review(context, [first, second], trusted_actor='verified-local-test')
    assert result['acceptance'] == 'review-decision-only'
    assert state(context) == ([(1, 'verify'), (2, 'rejected')], 2)
    with sqlite3.connect(context.path) as con:
        rows = con.execute('SELECT observed_token,basis_json,old_revision,new_revision,trusted_actor '
                           'FROM match_review_audit ORDER BY id').fetchall()
    assert [row[0] for row in rows] == [first['token'], second['token']]
    assert [json.loads(row[1])['match']['status'] for row in rows] == ['review', 'review']
    assert all(row[3] > row[2] and row[4] == 'verified-local-test' for row in rows)


@pytest.mark.parametrize('mutation', ['update_aba', 'reuse_id', 'binary_aba', 'replace_id'])
def test_identical_visible_rows_still_invalidate_prior_tokens(context, mutation):
    old = entry(context)
    with sqlite3.connect(context.path) as con:
        if mutation == 'update_aba':
            con.execute("UPDATE match SET evidence='changed' WHERE id=1")
            con.execute("UPDATE match SET evidence='{}' WHERE id=1")
        elif mutation == 'binary_aba':
            con.execute("UPDATE binary SET content_sha256='changed' WHERE id=1")
            con.execute("UPDATE binary SET content_sha256='a' WHERE id=1")
        else:
            row = con.execute('SELECT * FROM match WHERE id=1').fetchone()
            if mutation == 'reuse_id': con.execute('DELETE FROM match WHERE id=1')
            con.execute('INSERT OR REPLACE INTO match VALUES(' + ','.join('?' for _ in row) + ')', row)
    assert entry(context)['token'] != old['token']
    with pytest.raises(review.ReviewError, match='stale_basis'):
        review.decide_review(context, [old])
    assert state(context) == ([(1, 'review'), (2, 'review')], 0)


def test_one_stale_batch_member_prevents_every_write(context):
    first, second = entry(context), entry(context, 2)
    mutate(context, "UPDATE match SET score=.7 WHERE id=2")
    with pytest.raises(review.ReviewError, match='stale_basis'):
        review.decide_review(context, [first, second])
    assert state(context) == ([(1, 'review'), (2, 'review')], 0)


def test_unrelated_match_change_does_not_invalidate_current_row(context):
    first = entry(context)
    mutate(context, "UPDATE match SET evidence='new' WHERE id=2")
    assert review.decide_review(context, [first])['ok']
    assert state(context) == ([(1, 'verify'), (2, 'review')], 1)


def test_failed_audit_rolls_back_status_and_revision(context):
    old = entry(context)
    mutate(context, "CREATE TRIGGER refuse_audit BEFORE INSERT ON match_review_audit "
           "BEGIN SELECT RAISE(ABORT,'injected audit failure'); END")
    with pytest.raises(review.ReviewError, match='unavailable'):
        review.decide_review(context, [old])
    assert state(context) == ([(1, 'review'), (2, 'review')], 0)
    assert entry(context)['token'] == old['token']


def test_concurrent_opposite_decisions_have_one_winner(context):
    item = entry(context); barrier = threading.Barrier(2); results = []
    def decide(decision):
        barrier.wait(timeout=3)
        try: results.append(review.decide_review(context, [{**item, 'decision': decision}]))
        except review.ReviewError as exc: results.append(exc.result())
    workers = [threading.Thread(target=decide, args=(decision,)) for decision in ('accept', 'reject')]
    for worker in workers: worker.start()
    for worker in workers: worker.join(8)
    assert all(not worker.is_alive() for worker in workers)
    assert len(results) == 2 and sum(r['ok'] for r in results) == 1
    assert [r['error'] for r in results if not r['ok']] == ['stale_basis']
    assert state(context)[1] == 1


@pytest.mark.parametrize('change', ['boolean_id', 'overflow_id', 'duplicate', 'missing_token', 'unknown_decision', 'oversized'])
def test_malformed_requests_never_write(context, change):
    item = entry(context); items = [item]
    if change == 'boolean_id': item['matchId'] = True
    if change == 'overflow_id': item['matchId'] = 1 << 63
    if change == 'duplicate': items.append(dict(item))
    if change == 'missing_token': del item['token']
    if change == 'unknown_decision': item['decision'] = 'approve'
    if change == 'oversized': items *= 101
    with pytest.raises(review.ReviewError): review.decide_review(context, items)
    assert state(context) == ([(1, 'review'), (2, 'review')], 0)


def test_selection_and_physical_replacement_invalidate_basis(context, tmp_path):
    item = entry(context)
    changed = review.pin_context(context.path, 'selection-two')
    with pytest.raises(review.ReviewError, match='stale_basis'):
        review.decide_review(changed, [item])
    replacement = tmp_path / 'replacement.sqlite'
    replacement.write_bytes(context.path.read_bytes()); replacement.replace(context.path)
    with pytest.raises(review.ReviewError, match='context_changed'):
        review.decide_review(context, [item])


def test_missing_trigger_requires_schema_without_repairing_during_read(context):
    mutate(context, 'DROP TRIGGER match_review_match_update')
    with pytest.raises(review.ReviewError, match='review_schema_required'):
        review.list_review(context)
    with sqlite3.connect(context.path) as con:
        assert con.execute("SELECT 1 FROM sqlite_master WHERE name='match_review_match_update'").fetchone() is None


def test_schema_reinstall_preserves_incarnation_and_revisions(context):
    old = entry(context)
    with sqlite3.connect(context.path) as con:
        con.execute('BEGIN IMMEDIATE'); schema.install(con)
    assert entry(context)['token'] == old['token']


def test_pages_and_counts_share_review_snapshot(context):
    page = review.list_review(context, limit=1)
    assert page['total'] == 2 and page['nextAfterId'] == 1
    following = review.list_review(context, after_id=page['nextAfterId'], limit=1)
    assert [row['match']['id'] for row in following['rows']] == [2]
    assert following['nextAfterId'] is None


def test_page_id_overflow_is_structured_malformed_input(context):
    with pytest.raises(review.ReviewError, match='malformed_request'):
        review.list_review(context, after_id=1 << 63)


def test_rollback_failure_still_closes_connection(context, monkeypatch):
    real_connect = sqlite3.connect; closed = []
    class FailingRollback(sqlite3.Connection):
        def rollback(self):
            raise sqlite3.OperationalError('injected rollback failure')
        def close(self):
            closed.append(True)
            super().close()
    def connect(*args, **kwargs):
        return real_connect(*args, **kwargs, factory=FailingRollback)
    monkeypatch.setattr(review.sqlite3, 'connect', connect)
    with pytest.raises(review.ReviewError, match='injected_primary_error'):
        with review._transaction(context, write=True):
            raise review.ReviewError('injected_primary_error')
    assert closed == [True]
    # A second independent writer acquires the lock; cleanup did not rely on GC.
    con = real_connect(context.path, timeout=0)
    try:
        con.execute('BEGIN IMMEDIATE'); con.rollback()
    finally:
        con.close()
