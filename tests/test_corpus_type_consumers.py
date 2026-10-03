"""Task2.6 consumer regression specifications. Authored source; never run here."""
from contextlib import contextmanager
import json
import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentdecompile_recovery.corpus import build_types_header as header
from agentdecompile_recovery.corpus import ctxtypes, export_types, hookpack_v2, migrations, store
from agentdecompile_recovery.corpus.dashboard import common, react_api
from tests.test_corpus_type_schema import TYPE6, current, future, historical, snapshot

BASIS = {'toolchain_identity_hash': 'pinned:none', 'corpus_manifest_hash': 'b' * 64}
DEFINITION = 'typedef struct Layout {\n  int new;\n} Layout;\ntypedef char _sizecheck_Layout[(sizeof(Layout) == 4) ? 1 : -1];'


def api(monkeypatch, con=None, *, failure=None):
    entries, queries = [], []
    @contextmanager
    def selected():
        entries.append(con)
        if failure:
            raise common.CorpusReadError(failure)
        yield con, {'path': 'synthetic'}
    original = common.query_db
    def query(sql, params=(), *, connection=None, **kwargs):
        queries.append(connection)
        assert connection is con
        return original(sql, params, connection=connection, **kwargs)
    monkeypatch.setattr(common, 'corpus_read_snapshot', selected)
    monkeypatch.setattr(common, 'query_db', query)
    app = FastAPI()
    app.include_router(react_api.create_react_router())
    return TestClient(app), entries, queries


def get_types(client, **params):
    return client.get('/dashboard/api/workbench/types', params=params)


@pytest.mark.parametrize('installed', [False, True])
def test_types_api_distinguishes_unavailable_and_installed_empty_without_writes(monkeypatch, installed):
    con = current(installed=installed)
    before = snapshot(con)
    client, entries, queries = api(monkeypatch, con)
    response = get_types(client, slug='recipient')
    assert response.status_code == 200
    payload = response.json()
    assert payload['state'] == ('empty' if installed else 'unavailable')
    assert payload['rows'] == [] and payload['total'] == 0
    assert entries == [con] and queries == ([con, con] if installed else [])
    assert snapshot(con) == before and not con.in_transaction
    con.close()


def test_api_historical_six_column_origin_error_then_migrated_null_projection(monkeypatch):
    con = historical(shape='six')
    con.execute("INSERT INTO ghidra_type VALUES (1,'Layout','struct',4,'old-definition',1)")
    con.commit()
    client, entries, queries = api(monkeypatch, con)
    response = get_types(client)
    assert response.status_code == 503 and response.json()['ok'] is False
    assert 'origin' in response.json()['error']
    migrations.apply_pending(con)
    response = get_types(client)
    assert response.status_code == 200
    assert response.json()['rows'] == [{'slug': 'recipient', 'name': 'Layout', 'kind': 'struct',
                                       'definition': 'old-definition', 'origin': None}]
    assert response.json()['state'] == 'populated'
    assert len(entries) == 2 and queries == [con] * 4
    con.close()


def test_api_filter_paging_selected_empty_and_stabs_projection_preserved(monkeypatch):
    con = current(installed=True)
    for name, origin in [('Alpha', None), ('Beta', 'native'), ('Gamma', 'adopted:donor'), ('Other', 'unknown')]:
        con.execute('INSERT INTO ghidra_type VALUES (1,?,\'struct\',4,?,1,?)', (name, 'def-' + name, origin))
    con.execute("INSERT INTO stabs_type(binary_id,name,kind,stab,source_file,object_file) VALUES (1,'Debug','struct','debug-definition','source.cpp','object.o')")
    con.commit()
    client, entries, queries = api(monkeypatch, con)
    page = get_types(client, slug='recipient', q='a', offset=1, limit='1').json()
    assert page['total'] == 3 and page['hasMore'] is True
    assert page['rows'] == [{'slug': 'recipient', 'name': 'Beta', 'kind': 'struct', 'definition': 'def-Beta', 'origin': 'native'}]
    assert get_types(client, slug='donor').json()['state'] == 'empty'
    debug = get_types(client, source='stabs', slug='recipient').json()
    assert debug['rows'][0] == {'slug': 'recipient', 'name': 'Debug', 'kind': 'struct',
                              'definition': 'debug-definition', 'origin': 'source.cpp'}
    # Two queries per Ghidra response; STABS adds table_exists before count/page.
    assert entries == [con] * 3 and queries == [con] * 7
    con.close()


@pytest.mark.parametrize('message,status', [('Selected corpus database is unavailable', 200), ('snapshot admission failed', 503)])
def test_types_api_missing_database_and_other_admission_errors(monkeypatch, message, status):
    client, entries, queries = api(monkeypatch, failure=message)
    response = get_types(client)
    assert response.status_code == status
    assert response.json().get('state') == ('unavailable' if status == 200 else None)
    assert len(entries) == 1 and not queries


@pytest.mark.parametrize('bad', ['absent-with-rows', 'future'])
def test_corrupt_or_actual_future_refuses_api_header_definitions_hookpack_and_context_falls_back(monkeypatch, tmp_path, bad):
    con = current(installed=True)
    con.execute("INSERT INTO ghidra_type VALUES (1,'Layout','struct',4,'stored-definition',1,NULL)")
    con.commit()
    if bad == 'future': future(con)
    else:
        con.execute("UPDATE type_inventory_state SET mode='absent'")
        con.commit()
    monkeypatch.setattr(header, 'basis', lambda _con: dict(BASIS))
    monkeypatch.setattr(hookpack_v2, 'basis', lambda _con: dict(BASIS))
    before = snapshot(con)
    client, _, _ = api(monkeypatch, con)
    assert get_types(client).status_code == 503
    assert ctxtypes.load_types(con, 1) == {}
    for call in (lambda: export_types.definitions_for(con, 1, {'Layout'}),
                 lambda: header.build_header(con, 1, tmp_path / 'types.h'),
                 lambda: hookpack_v2.build_hookpack_v2(con)):
        with pytest.raises(ValueError, match='type schema required'):
            call()
    assert not (tmp_path / 'types.h').exists()
    assert snapshot(con) == before
    con.close()


def test_empty_definition_request_does_not_touch_even_an_invalid_handle():
    class NoSQL:
        def execute(self, *_args, **_kwargs):
            pytest.fail('empty request must not inspect schema or execute SQL')
    assert export_types.definitions_for(NoSQL(), 1, set()) == ('', set())


@pytest.mark.parametrize('columns', [5, 6, 7])
def test_raw_historical_projection_readers_keep_their_minimal_column_contract(columns):
    con = sqlite3.connect(':memory:')
    con.row_factory = sqlite3.Row
    ddl = TYPE6
    if columns == 5: ddl = ddl.replace(', n_fields INTEGER', '')
    if columns == 7: ddl = ddl.replace('    PRIMARY KEY', '    origin TEXT,\n    PRIMARY KEY')
    con.execute(ddl)
    con.execute("INSERT INTO ghidra_type(binary_id,name,kind,size,definition) VALUES (1,'Layout','struct',4,'  old definition  ')")
    before = snapshot(con)
    assert export_types.definitions_for(con, 1, {'Layout', 'Missing'}) == ('  old definition  \n', {'Layout'})
    assert ctxtypes.load_types(con, 1) == {'Layout': 'old definition'}
    assert snapshot(con) == before
    con.close()


@pytest.mark.parametrize('installed', [False, True])
def test_header_and_recovery_definition_fallback_preserve_absent_empty_difference(monkeypatch, tmp_path, installed):
    from agentdecompile_recovery.corpus.recover_named_ghidra import inject_data_symbols
    con = current(installed=installed)
    monkeypatch.setattr(header, 'basis', lambda _con: dict(BASIS))
    base = tmp_path / 'base.c'
    base.write_text('void use(Unknown *value) {}\n')
    if installed:
        assert export_types.definitions_for(con, 1, {'Unknown'}) == ('', set())
        assert header.build_header(con, 1, tmp_path / 'types.h')['types'] == 0
        assert inject_data_symbols(tmp_path, (con, 1)) > 0
        assert 'typedef unsigned char Unknown;' in base.read_text()
    else:
        for call in (lambda: export_types.definitions_for(con, 1, {'Unknown'}),
                     lambda: header.build_header(con, 1, tmp_path / 'types.h'),
                     lambda: inject_data_symbols(tmp_path, (con, 1))):
            with pytest.raises(sqlite3.OperationalError, match='no such table: ghidra_type'):
                call()
        assert base.read_text() == 'void use(Unknown *value) {}\n'
        assert not (tmp_path / 'types.h').exists()
    con.close()


def test_actual_header_manifest_context_recovery_and_hookpack_projection_are_byte_stable_across_migration(monkeypatch, tmp_path):
    from agentdecompile_recovery.corpus.recover_named_ghidra import inject_data_symbols
    con = historical(shape='seven-create', origin=True)
    con.execute('INSERT INTO ghidra_type VALUES (1,\'Layout\',\'struct\',4,?,1,\'unknown\')', (DEFINITION,))
    con.commit()
    monkeypatch.setattr(header, 'basis', lambda _con: dict(BASIS))
    monkeypatch.setattr(hookpack_v2, 'basis', lambda _con: dict(BASIS))
    results = []
    for version in (12, 13):
        if version == 13: migrations.apply_pending(con)
        directory = tmp_path / str(version)
        directory.mkdir()
        dest = directory / 'types.h'
        receipt = header.build_header(con, 1, dest)
        (directory / 'base.c').write_text('void use(Layout *value) {}\n')
        inject_data_symbols(directory, (con, 1))
        pack = hookpack_v2.build_hookpack_v2(con)
        entities = [e for e in pack['entities'] if e['name'] == 'Layout']
        assert entities and entities[0]['shape']['fields']['recipient'][0]['type']['kind'] == 'array'
        results.append((dest.read_bytes(), dest.with_name('types.h.manifest.json').read_bytes(),
                        (directory / 'base.c').read_bytes(), ctxtypes.load_types(con, 1), entities))
        assert receipt['types'] == 1
    assert results[0] == results[1]
    assert b'int f_new;' in results[1][0]
    assert b'typedef unsigned char Layout;' not in results[1][2]
    con.close()


@pytest.mark.parametrize('installed,reason', [(False, 'captured type definitions unavailable'),
                                             (True, 'no captured type definitions for recipient')])
def test_bundle_type_refusal_is_distinct_and_has_no_output_or_transaction_effect(monkeypatch, tmp_path, installed, reason):
    from agentdecompile_recovery.corpus import export_bundle as bundle
    from agentdecompile_recovery.corpus import divergence_report, export_lua_bindings, export_validation, readiness_report
    con = current(installed=installed)
    con.execute("INSERT INTO eval(run) VALUES ('caller')")
    before = snapshot(con)
    # Scope this fixture to actual bundle inventory classification, with unrelated
    # cave and adapter qualification supplied by isolated synthetic collaborators.
    monkeypatch.setattr(bundle, 'build_hookpack_v2', lambda *_a, **_k: {})
    monkeypatch.setattr(export_validation, 'validate_export_set', lambda *_a, **_k: None)
    monkeypatch.setattr(divergence_report, 'build_divergence_report', lambda _p: {'status': 'complete'})
    monkeypatch.setattr(export_lua_bindings, 'render_lua_bindings', lambda _p: '')
    monkeypatch.setattr(readiness_report, 'build_readiness_report', lambda _p: {})
    with pytest.raises(bundle.BundleExportError, match=reason):
        bundle.export_bundle(con, tmp_path / 'bundle')
    assert not (tmp_path / 'bundle').exists()
    assert snapshot(con) == before and con.in_transaction
    con.close()
