"""Synthetic actual JobStore review admission; no server or recovery subprocess."""
import json
import sqlite3
import threading

import pytest

_REAL_THREAD_START = threading.Thread.start

from agentdecompile_recovery.corpus import store as corpus_store
from agentdecompile_recovery.corpus.dashboard import common
from agentdecompile_recovery.corpus.dashboard.actions import jobs, job_history
from agentdecompile_recovery.corpus.dashboard.actions import catalog


@pytest.fixture
def review_env(tmp_path, monkeypatch):
    def controlled_start(thread):
        target = getattr(thread, '_target', None)
        if getattr(target, '__module__', '') == jobs.__name__:
            return None
        return _REAL_THREAD_START(thread)
    monkeypatch.setattr(threading.Thread, 'start', controlled_start)
    monkeypatch.setattr(common, 'live_root', lambda: tmp_path)
    monkeypatch.setattr(jobs, 'live_root', lambda: tmp_path)
    monkeypatch.setattr(job_history, 'directory', lambda: tmp_path / 'jobs')
    monkeypatch.setattr(job_history, 'owner', lambda: {'ownerPid': 1, 'ownerStart': 'synthetic'})
    monkeypatch.setattr(common, '_RUNTIME_DB_PATH', None)
    monkeypatch.setattr(common, '_REVIEW_SELECTION_GENERATION', 'synthetic-start')
    db = tmp_path / 'corpus.sqlite'
    con = corpus_store.connect(db)
    con.executemany('INSERT INTO binary(id,repo_path,slug,content_sha256) VALUES(?,?,?,?)',
                    [(1, 'donor', 'donor', 'a'), (2, 'recipient', 'recipient', 'b')])
    con.executemany('INSERT INTO match(id,run,src_binary,src_addr,dst_binary,dst_addr,score,margin,evidence,status,relation) '
                    'VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                    [(i, 'run', 1, 4096+i, 2, 8192+i, .9, .1, '{}', 'review', 'one_to_one') for i in (1,2)])
    con.commit(); con.close()
    common.set_runtime_db_path(db)
    service = jobs.JobStore()
    monkeypatch.setattr(jobs, 'STORE', service)
    yield db, service
    if service._resource_owner_handle is not None:
        service._resource_owner_handle.close()


def payload(db):
    page = common.list_match_review()
    return {'db': str(db), 'selection': page['selection'], 'entries': [
        {'matchId': row['match']['id'], 'token': row['token'], 'decision': 'accept'} for row in page['rows']]}


def run(service, response):
    job_id = response['job']['id']
    service._run(job_id, service._cancels[job_id])
    return service.get(job_id)


def state(db):
    with sqlite3.connect(db) as con:
        return (con.execute('SELECT status FROM match ORDER BY id').fetchall(),
                con.execute('SELECT count(*) FROM match_review_audit').fetchone()[0])


def test_catalog_list_and_decision_persist_audit_and_claim_sidecars(review_env):
    db, service = review_env
    response, status = jobs.start_job('review.list', {'db': str(db)})
    assert status == 202
    listing = run(service, response)
    assert listing.status == 'ok' and listing.resource_keys == {}
    page = json.loads(listing.log)
    params = {'db': str(db), 'selection': page['selection'], 'entries': [
        {'matchId': r['match']['id'], 'token': r['token'], 'decision': 'accept'} for r in page['rows']]}
    response, status = jobs.start_job('review.decide', params)
    assert status == 202 and state(db)[1] == 0
    job = run(service, response)
    assert job.status == 'ok' and json.loads(job.log)['ok']
    assert job.resource_disposition == 'released'
    assert job.resource_keys['identity'] == str(db)
    assert {v for k, v in job.resource_keys['external']} == {str(db)+s for s in ('', '-wal', '-shm', '-journal')}
    assert state(db) == ([('verify',), ('verify',)], 2)
    with sqlite3.connect(db) as con:
        assert con.execute('SELECT trusted_actor FROM match_review_audit').fetchall() == [(None,), (None,)]


def test_queued_selection_aba_never_redirects_or_writes(review_env, tmp_path):
    db, service = review_env
    response, status = jobs.start_job('review.decide', payload(db))
    assert status == 202
    other = tmp_path / 'other.sqlite'; other.write_bytes(db.read_bytes())
    common.set_runtime_db_path(other); common.set_runtime_db_path(db)
    job = run(service, response)
    assert job.status == 'failed' and json.loads(job.log)['error'] == 'context_changed'
    assert state(db)[1] == state(other)[1] == 0


def test_stale_batch_and_audit_failure_leave_no_partial_writes(review_env):
    db, service = review_env
    response, _ = jobs.start_job('review.decide', payload(db))
    with sqlite3.connect(db) as con: con.execute('UPDATE match SET score=.5 WHERE id=2')
    failed = run(service, response)
    assert json.loads(failed.log)['error'] == 'stale_basis' and state(db)[1] == 0
    response, _ = jobs.start_job('review.decide', payload(db))
    with sqlite3.connect(db) as con:
        con.execute("CREATE TRIGGER refuse_audit BEFORE INSERT ON match_review_audit BEGIN SELECT RAISE(ABORT,'no audit'); END")
    failed = run(service, response)
    assert json.loads(failed.log)['error'] == 'unavailable'
    assert state(db) == ([('review',), ('review',)], 0)


def test_cancel_before_dispatch_never_opens_write_transaction(review_env):
    db, service = review_env
    response, _ = jobs.start_job('review.decide', payload(db))
    service.cancel(response['job']['id'])
    job = run(service, response)
    assert job.status == 'cancelled' and state(db)[1] == 0


@pytest.mark.parametrize('change', ['missing', 'bool', 'duplicate', 'oversize', 'actor'])
def test_malformed_inputs_refused_before_admission(review_env, change):
    db, service = review_env; params = payload(db)
    if change == 'missing': del params['entries'][0]['token']
    elif change == 'bool': params['entries'][0]['matchId'] = True
    elif change == 'duplicate': params['entries'] = [params['entries'][0]] * 2
    elif change == 'oversize': params['entries'] *= 51
    else: params['entries'][0]['actor'] = 'forged'
    response, status = jobs.start_job('review.decide', params)
    assert status == 400 and response['ok'] is False
    assert not service._jobs and state(db)[1] == 0


def test_failed_terminal_receipt_does_not_claim_database_rollback(review_env, monkeypatch):
    db, service = review_env
    response, _ = jobs.start_job('review.decide', payload(db))
    original = service._persist_locked
    def persist(job, **kwargs):
        if job.finished_at: raise OSError('injected terminal receipt failure')
        return original(job, **kwargs)
    monkeypatch.setattr(service, '_persist_locked', persist)
    job = run(service, response)
    assert state(db)[1] == 2 and json.loads(job.log)['ok']
    assert job.resource_disposition == 'quarantined' and 'not committed' in job.log_reason


def test_existing_sidecar_alias_refused(review_env, tmp_path):
    db, service = review_env
    target = tmp_path / 'unrelated'; target.write_bytes(b'')
    (tmp_path / 'corpus.sqlite-journal').symlink_to(target)
    response, status = jobs.start_job('review.decide', payload(db))
    assert status == 400 and response['error'] == 'unsafe_database_alias'
    assert not service._jobs


def test_sidecar_reservation_prevents_dispatch(review_env, monkeypatch):
    db, service = review_env
    response, _ = jobs.start_job('review.decide', payload(db))
    service._restore_reservations_locked()
    service._external_held[('store', str(db) + '-wal')] = 'existing-owner'
    event = service._cancels[response['job']['id']]
    monkeypatch.setattr(jobs.time, 'sleep', lambda _: event.set())
    job = run(service, response)
    assert job.status == 'cancelled' and state(db)[1] == 0
    assert service._external_held[('store', str(db) + '-wal')] == 'existing-owner'


def test_cancellation_after_commit_preserves_truthful_success(review_env, monkeypatch):
    from agentdecompile_recovery.corpus.dashboard.actions import match_review as adapter
    db, service = review_env
    response, _ = jobs.start_job('review.decide', payload(db))
    event = service._cancels[response['job']['id']]
    original = adapter.decide_review
    def commit_then_cancel(*args, **kwargs):
        result = original(*args, **kwargs)
        event.set()
        return result
    monkeypatch.setattr(adapter, 'decide_review', commit_then_cancel)
    job = run(service, response)
    assert job.status == 'ok' and json.loads(job.log)['ok'] and state(db)[1] == 2
