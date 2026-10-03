"""Selected matrix regression sources; execution is deferred by the mission."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import sqlite3
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from agentdecompile_recovery.corpus.objdiff_report import build_report
from agentdecompile_recovery.corpus.dashboard import progress_reports
from agentdecompile_recovery.corpus.dashboard.common import CorpusReadError
from agentdecompile_recovery.corpus.dashboard.router import create_dashboard_router

pytestmark = pytest.mark.unit
HASH_A, HASH_B, SOURCE = 'a' * 64, 'b' * 64, 'c' * 64


@pytest.fixture
def corpus():
    # Deliberately omit constraints so refusal cases can represent legacy data.
    con = sqlite3.connect(':memory:')
    con.executescript('''
        CREATE TABLE binary (id INTEGER,slug TEXT,content_sha256 TEXT);
        CREATE TABLE func (binary_id INTEGER,addr INTEGER,name TEXT,size INTEGER,ranges INTEGER);
        CREATE TABLE logical_function (id INTEGER,canon_key TEXT);
        CREATE TABLE identity (logical_id INTEGER,binary_id INTEGER,addr INTEGER);
        CREATE TABLE recovered_function (binary_id INTEGER,addr INTEGER,source_sha256 TEXT,target_sha256 TEXT,real_c INTEGER);
    ''')
    con.executemany('INSERT INTO binary VALUES (?,?,?)', [(1, 'build-a', HASH_A), (2, 'build-b', HASH_B)])
    con.executemany('INSERT INTO logical_function VALUES (?,?)', [(7, 'RecordedRoot'), (8, 'OtherRoot'), (9, 'EmptyRoot')])
    con.executemany('INSERT INTO func VALUES (?,?,?,?,?)', [
        (1, 100, 'first', 20, 1), (1, 110, 'split', 20, 1),
        (1, 300, 'unrelated', 30, 1), (2, 500, 'second', 40, 1)])
    con.executemany('INSERT INTO identity VALUES (?,?,?)', [(7, 1, 100), (7, 1, 110), (8, 1, 300), (7, 2, 500)])
    con.executemany('INSERT INTO recovered_function VALUES (?,?,?,?,?)', [
        (1, 100, SOURCE, HASH_A, 1), (1, 300, SOURCE, HASH_A, 1),
        (2, 500, SOURCE, HASH_B, 1), (1, 110, SOURCE, HASH_B, 1)])
    yield con
    con.close()


def selected(con, build=1, logical_id=7, **kwargs):
    return build_report(con, build, version=HASH_A if build == 1 else HASH_B,
                        logical_id=logical_id, **kwargs)


def projection(report):
    return progress_reports.logical_tier_projection(report, corpus_identity='corpus-one')


def test_selected_members_across_builds_keep_provider_unavailable(corpus):
    first, second = selected(corpus), selected(corpus, build=2)
    assert [unit['address'] for unit in first['units']] == ['0x64', '0x6e']
    assert [unit['address'] for unit in second['units']] == ['0x1f4']
    for report, count in [(first, 2), (second, 1)]:
        matrix = projection(report)
        assert report['selection_scope'] == matrix['selection_scope'] == {'kind': 'logical_function', 'logical_id': 7}
        assert len(matrix['rows']) == 1
        row = matrix['rows'][0]
        assert row['stable_key'] == 'RecordedRoot'
        assert row['physical_members'] == len(row['member_keys']) == count
        assert report['accounting']['inventory_count'] == report['measures']['total_functions'] == count
        assert matrix['unbound'] is None and matrix['unbound_status'] == 'not_requested'
        assert matrix['provider']['status'] == 'not_connected'
        assert row['verified']['functions'] is None and row['verified']['bytes'] is None
    # Target-bound source from build B at address 110 cannot classify build A.
    assert [unit['tier'] for unit in first['units']] == ['advisory-ghidra', 'unclassified']


def test_recorded_empty_root_is_zero_but_absent_root_refuses(corpus):
    matrix = projection(selected(corpus, logical_id=9))
    row = matrix['rows'][0]
    assert (row['logical_id'], row['stable_key'], row['physical_members']) == (9, 'EmptyRoot', 0)
    assert row['member_keys'] == [] and row['advisory']['functions'] == row['unclassified']['functions'] == 0
    assert row['verified']['functions'] is None
    with pytest.raises(ValueError, match='logical_function_not_found'):
        selected(corpus, logical_id=10)
    corpus.execute('UPDATE logical_function SET canon_key=NULL WHERE id=9')
    assert projection(selected(corpus, logical_id=9))['rows'][0]['stable_key'] == 'logical:9'


class ReadSpy:
    def __init__(self, con):
        self.con, self.reads = con, []

    def execute(self, sql, parameters=()):
        cursor = self.con.execute(sql, parameters)
        reads = self.reads

        class Cursor:
            def fetchall(self):
                rows = cursor.fetchall()
                reads.append((sql, tuple(parameters), rows))
                return rows

            def fetchone(self):
                row = cursor.fetchone()
                reads.append((sql, tuple(parameters), [] if row is None else [row]))
                return row

            def __iter__(self):
                return iter(self.fetchall())

        return Cursor()


def test_selected_sql_limits_fetched_functions_claims_and_candidates(corpus):
    spy = ReadSpy(corpus)
    selected(spy)
    physical = [(sql, args, rows) for sql, args, rows in spy.reads if 'FROM func f ' in sql]
    claims = [(sql, args, rows) for sql, args, rows in spy.reads if 'FROM identity i ' in sql]
    candidates = [(sql, args, rows) for sql, args, rows in spy.reads if 'FROM recovered_function r ' in sql]
    assert len(physical) == len(claims) == len(candidates) == 1
    assert all('EXISTS (SELECT 1 FROM identity s WHERE s.logical_id=?' in sql for sql, _, _ in physical + claims + candidates)
    assert physical[0][1] == claims[0][1] == (1, 7, 1)
    assert candidates[0][1] == (1, HASH_A, 7, 1)
    assert [row[0] for row in physical[0][2]] == [100, 110]
    assert [row[2] for row in claims[0][2]] == [100, 110]
    assert [row[0] for row in candidates[0][2]] == [100]
    # No selected-mode physical/candidate query may read the entire build.
    assert not any('FROM func WHERE' in sql or 'FROM recovered_function WHERE' in sql for sql, _, _ in spy.reads)


def test_default_and_explicit_none_preserve_whole_report_and_digest(corpus):
    report = build_report(corpus, 1, version=HASH_A)
    assert report == build_report(corpus, 1, version=HASH_A, logical_id=None)
    assert 'selection_scope' not in report and 'selection_root' not in report
    assert report['measures']['total_functions'] == 3
    matrix = projection(report)
    assert 'selection_scope' not in matrix and 'unbound_status' not in matrix
    assert [row['logical_id'] for row in matrix['rows']] == [7, 8]
    assert matrix['unbound']['physical_members'] == 0
    assert selected(corpus)['report_sha256'] != report['report_sha256']
    scoped = selected(corpus)
    payload = {key: value for key, value in scoped.items() if key != 'report_sha256'}
    canonical = (json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()
    assert scoped['report_sha256'] == hashlib.sha256(canonical).hexdigest()


def test_unknown_and_multirange_extents_stay_unknown_and_unions_stay_independent(corpus):
    known = selected(corpus)
    assert known['accounting']['inventory_byte_union'] == 30  # Overlapping sizes sum to 40.
    assert known['accounting']['byte_unions']['candidate_source'] == 20
    assert known['accounting']['byte_unions']['unclassified'] == 20
    corpus.execute('UPDATE func SET ranges=2 WHERE binary_id=1 AND addr=100')
    corpus.execute('UPDATE func SET size=NULL WHERE binary_id=1 AND addr=110')
    report = selected(corpus)
    row = projection(report)['rows'][0]
    assert row['unknown_extent_members'] == 2
    assert row['advisory']['bytes'] is None and row['unclassified']['bytes'] is None
    assert report['measures']['total_code'] is None and report['measures']['matched_percent'] is None
    assert report['tiers']['advisory-ghidra']['bytes'] is None
    assert report['accounting']['byte_accounting'] == 'incomplete'
    assert report['accounting']['inventory_byte_union'] == 0
    assert all(assignment['extent'] is None for assignment in report['assignments'])
    assert all(unit['measures']['total_code'] is None and unit['measures']['matched_percent'] is None
               for unit in report['units'])


def test_receipt_classification_is_reused_but_does_not_connect_matrix_provider(corpus):
    receipt = {'addr': 100, 'target_sha256': HASH_A, 'source_sha256': SOURCE,
               'version': HASH_A, 'status': 'accepted', 'claim': 'byte_exact_source'}
    report = selected(corpus, receipts=[receipt], verify_receipt=lambda _: True)
    assert report['units'][0]['tier'] == 'verified-byte-exact'
    assert projection(report)['rows'][0]['verified'] == {
        'status': 'unavailable', 'functions': None, 'bytes': None, 'member_keys': [f'{HASH_A}:64']}
    wrong = {**receipt, 'version': HASH_B}
    assert selected(corpus, receipts=[wrong], verify_receipt=lambda _: True)['units'][0]['tier'] == 'advisory-ghidra'
    with pytest.raises(ValueError, match='selected_report_version_mismatch'):
        build_report(corpus, 1, version=HASH_B, logical_id=7)
    corpus.execute('UPDATE func SET ranges=2 WHERE binary_id=1 AND addr=100')
    unknown = selected(corpus, receipts=[receipt], verify_receipt=lambda _: True)
    assert unknown['units'][0]['tier'] == 'verified-byte-exact'
    assert unknown['units'][0]['measures']['matched_code'] is None
    assert unknown['measures']['matched_code'] is None
    assert unknown['tiers']['verified-byte-exact']['bytes'] is None


@pytest.mark.parametrize('case', ['scope_null', 'scope_bool', 'root_malformed', 'foreign_member', 'duplicate_member', 'inventory_count'])
def test_projection_refuses_mixed_scopes_and_unreconciled_inventory(corpus, case):
    report = selected(corpus)
    if case == 'scope_null':
        report['selection_scope'] = None
    elif case == 'scope_bool':
        report['selection_scope']['logical_id'] = True
    elif case == 'root_malformed':
        report['selection_root'] = []
    elif case == 'foreign_member':
        report['units'][0]['logical_id'] = 8
    elif case == 'duplicate_member':
        report['units'].append(report['units'][0])
    else:
        report['accounting']['inventory_count'] += 1
    with pytest.raises(ValueError):
        projection(report)


def test_malformed_recorded_root_refuses_even_when_membership_is_empty(corpus):
    corpus.execute('UPDATE logical_function SET canon_key=? WHERE id=9', (b'opaque',))
    with pytest.raises(ValueError, match='logical_function_root_malformed'):
        selected(corpus, logical_id=9)


def test_maximum_safe_selected_root_is_allowed(corpus):
    corpus.execute('INSERT INTO logical_function VALUES (?,?)', (9007199254740991, 'SafeMax'))
    assert projection(selected(corpus, logical_id=9007199254740991))['rows'][0]['physical_members'] == 0


@pytest.mark.parametrize('logical_id', [True, False, 0, -1, 9007199254740992, '7', 7.0])
def test_internal_filter_requires_exact_safe_positive_int(corpus, logical_id):
    with pytest.raises(ValueError, match='logical_id_invalid'):
        selected(corpus, logical_id=logical_id)
    assert progress_reports.progress_report(slug='build-a', logical_id=logical_id)['status'] == 'unavailable'


@pytest.mark.parametrize('table', ['binary', 'func', 'identity', 'logical_function', 'recovered_function'])
def test_malformed_present_schema_refuses(corpus, table):
    corpus.execute(f'DROP TABLE {table}')
    corpus.execute(f'CREATE TABLE {table} (unused TEXT)')
    with pytest.raises(ValueError, match='selected_report_schema_invalid:' + table):
        selected(corpus)


@pytest.mark.parametrize('table', ['binary', 'func', 'identity', 'logical_function'])
def test_missing_required_table_refuses(corpus, table):
    corpus.execute(f'DROP TABLE {table}')
    with pytest.raises(ValueError, match='selected_report_table_required:' + table):
        selected(corpus)


def test_absent_optional_source_table_is_unclassified_but_view_refuses(corpus):
    corpus.execute('DROP TABLE recovered_function')
    assert all(unit['tier'] == 'unclassified' for unit in selected(corpus)['units'])
    corpus.execute('CREATE VIEW recovered_function AS SELECT 1 AS binary_id')
    with pytest.raises(ValueError, match='selected_report_table_required:recovered_function'):
        selected(corpus)


@pytest.mark.parametrize('mutation,reason', [
    ('INSERT INTO logical_function VALUES (7,"RecordedRoot")', 'logical_function_root_ambiguous'),
    ('INSERT INTO logical_function VALUES (7,"ConflictingRoot")', 'logical_function_root_ambiguous'),
    ('INSERT INTO identity VALUES (7,1,100)', 'selected_membership_malformed_or_duplicate'),
    ('INSERT INTO identity VALUES (8,1,100)', 'selected_identity_conflicting_or_duplicate'),
    ('INSERT INTO identity VALUES (7,1,999)', 'selected_membership_function_mismatch'),
    ('INSERT INTO identity VALUES (7,1,-1)', 'selected_membership_malformed_or_duplicate'),
    ('INSERT INTO identity VALUES (7,1,100.5)', 'selected_membership_malformed_or_duplicate'),
    ('INSERT INTO identity VALUES (7,1,"bad")', 'selected_membership_malformed_or_duplicate'),
    ('INSERT INTO func VALUES (1,100,"duplicate",20,1)', 'selected_membership_function_mismatch'),
    ('INSERT INTO binary VALUES (1,"duplicate-build",' + repr(HASH_A) + ')', 'selected_binary_ambiguous_or_malformed'),
])
def test_duplicate_conflicting_or_malformed_selection_refuses(corpus, mutation, reason):
    corpus.execute(mutation)
    with pytest.raises(ValueError, match=reason):
        selected(corpus)


def install_snapshot(monkeypatch, con):
    @contextmanager
    def snapshot(expected):
        if expected and expected != 'corpus-one':
            raise CorpusReadError('Corpus database changed')
        try:
            yield con, {'identity': 'corpus-one', 'path': 'test-only'}
        except sqlite3.Error as exc:
            raise CorpusReadError(f'Corpus read failed: {exc}') from exc
    monkeypatch.setattr(progress_reports, 'corpus_read_snapshot', snapshot)


def test_progress_selected_basis_and_fresh_advisory_reads(corpus, monkeypatch):
    install_snapshot(monkeypatch, corpus)
    args = {'slug': 'build-a', 'version': HASH_A, 'corpus_identity': 'corpus-one', 'logical_id': 7}
    before = progress_reports.progress_report(**args)
    assert before['ok'] and before['matrix_projection']['rows'][0]['advisory']['functions'] == 1
    corpus.execute('INSERT INTO recovered_function VALUES (?,?,?,?,1)', (1, 110, SOURCE, HASH_A))
    after = progress_reports.progress_report(**args)
    assert after['matrix_projection']['rows'][0]['advisory']['functions'] == 2
    assert after['report']['report_sha256'] != before['report']['report_sha256']
    corpus.execute('DELETE FROM identity WHERE binary_id=1 AND addr=110')
    assert progress_reports.progress_report(**args)['matrix_projection']['rows'][0]['physical_members'] == 1
    assert progress_reports.progress_report(**{**args, 'version': HASH_B})['status'] == 'stale'
    assert progress_reports.progress_report(**{**args, 'corpus_identity': 'other'})['status'] == 'unavailable'
    assert not progress_reports.progress_report(**{**args, 'slug': 'absent'})['ok']
    assert progress_reports.progress_report(**{**args, 'logical_id': 999})['status'] == 'unavailable'
    for missing in ['slug', 'version', 'corpus_identity']:
        assert progress_reports.progress_report(**{**args, missing: ''})['status'] == 'unavailable'


def test_sqlite_errors_and_deadline_refuse_without_whole_report_fallback(corpus, monkeypatch):
    install_snapshot(monkeypatch, corpus)
    corpus.execute('DROP TABLE func')
    result = progress_reports.progress_report(slug='build-a', version=HASH_A,
        corpus_identity='corpus-one', logical_id=7)
    assert result['status'] == 'unavailable' and 'selected_report_table_required:func' in result['error']
    monkeypatch.setattr(progress_reports, 'time', SimpleNamespace(monotonic=iter([0, 10]).__next__))

    class Interrupted:
        def set_progress_handler(self, callback, frequency):
            assert frequency == 1000 and callback() == 1

        def execute(self, *_args):
            raise sqlite3.OperationalError('interrupted')
    install_snapshot(monkeypatch, Interrupted())
    result = progress_reports.progress_report(slug='build-a', version=HASH_A,
        corpus_identity='corpus-one', logical_id=7)
    assert result['status'] == 'unavailable' and 'interrupted' in result['error']


@pytest.mark.parametrize('query', ['', 'logicalId=7', 'logicalId=9007199254740991'])
def test_http_absence_or_canonical_filter_forwarded(monkeypatch, query):
    seen = []
    monkeypatch.setattr(progress_reports, 'progress_report', lambda **kwargs: seen.append(kwargs) or {'ok': True})
    app = FastAPI()
    app.include_router(create_dashboard_router())
    response = TestClient(app).get('/dashboard/api/workbench/progress-report?slug=build-a&version=' + HASH_A + '&corpusIdentity=corpus-one&' + query)
    assert response.status_code == 200
    assert seen == [{'slug': 'build-a', 'version': HASH_A, 'corpus_identity': 'corpus-one',
                     'logical_id': None if not query else int(query.split('=')[1])}]


@pytest.mark.parametrize('query', ['logicalId=', 'logicalId=7&logicalId=7', 'logicalId=7&logicalId=',
    'logicalId=%2B7', 'logicalId=-7', 'logicalId=07', 'logicalId=0', 'logicalId=7.0',
    'logicalId=%207', 'logicalId=7%20', 'logicalId=7%0A', 'logicalId=abc', 'logicalId=9007199254740992'])
def test_http_invalid_filter_never_falls_back_unfiltered(monkeypatch, query):
    def forbidden(**_kwargs):
        raise AssertionError('invalid HTTP filter reached report builder')
    monkeypatch.setattr(progress_reports, 'progress_report', forbidden)
    app = FastAPI()
    app.include_router(create_dashboard_router())
    response = TestClient(app).get('/dashboard/api/workbench/progress-report?' + query)
    assert response.status_code == 503
    assert response.json() == {'ok': False, 'status': 'unavailable', 'error': 'logical_id_invalid'}
