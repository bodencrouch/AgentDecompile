"""Real HTTP handlers exercised in process against synthetic admitted jobs."""
import asyncio
import json

from starlette.requests import Request

from agentdecompile_recovery.corpus.dashboard.router import create_dashboard_router
from agentdecompile_recovery.corpus.dashboard import common
from test_match_review_catalog import review_env, state, run


def handler(path):
    return next(route.endpoint for route in create_dashboard_router().routes if route.path == path)


def request(body=None, query=b''):
    raw = json.dumps(body).encode() if body is not None else b''
    async def receive():
        return {'type': 'http.request', 'body': raw, 'more_body': False}
    return Request({'type': 'http', 'method': 'POST', 'path': '/', 'query_string': query,
                    'headers': []}, receive)


def call(path, req):
    response = asyncio.run(handler(path)(req))
    return response.status_code, json.loads(response.body)


def test_http_list_submit_poll_catalog_parity(review_env):
    db, service = review_env
    status, page = call('/dashboard/api/workbench/match-review', request(query=b'limit=1'))
    assert status == 200 and page['total'] == 2 and page['nextAfterId'] == 1
    row = page['rows'][0]
    status, pending = call('/dashboard/api/workbench/match-decide', request({
        'match_id': row['match']['id'], 'token': row['token'], 'decision': 'accept', 'selection': page['selection']}))
    assert status == 202 and pending['pending'] and pending['job_id'] == pending['job']['id']
    assert state(db)[1] == 0
    terminal = run(service, pending)
    assert terminal.status == 'ok' and state(db)[1] == 1
    status, stale = call('/dashboard/api/workbench/match-decide', request({
        'match_id': 1, 'token': row['token'], 'decision': 'reject', 'selection': page['selection']}))
    assert status == 202
    assert json.loads(run(service, stale).log)['error'] == 'stale_basis'


def test_http_requires_exact_observed_rows_and_returns_structured_errors(review_env):
    db, service = review_env
    status, result = call('/dashboard/api/workbench/match-decide-batch', request({'match_ids': [1], 'decision': 'accept'}))
    assert status == 400 and result['error'] == 'malformed_request'
    status, result = call('/dashboard/api/workbench/match-review', request(query=b'after_id=true'))
    assert status == 400 and result['error'] == 'malformed_request'
    assert state(db)[1] == 0 and not service._jobs


def test_http_selection_aba_refuses_submission(review_env):
    db, service = review_env; page = common.list_match_review(); row = page['rows'][0]
    common.set_runtime_db_path(db)
    status, result = call('/dashboard/api/workbench/match-decide', request({
        'match_id': 1, 'token': row['token'], 'decision': 'accept', 'selection': page['selection']}))
    assert status == 409 and result['refreshRequired']
    assert state(db)[1] == 0


def test_http_request_bound_applies_before_job_admission(review_env):
    status, result = call('/dashboard/api/workbench/match-decide', request({'junk': 'x' * (128 * 1024)}))
    assert status == 413 and result['error'] == 'request_too_large'


def test_http_legacy_schema_refusal_is_service_consistent(review_env):
    import sqlite3
    db, service = review_env
    with sqlite3.connect(db) as con: con.execute('DROP TRIGGER match_review_match_update')
    status, result = call('/dashboard/api/workbench/match-review', request())
    assert status == 503 and result['error'] == 'review_schema_required'
    assert not service._jobs
