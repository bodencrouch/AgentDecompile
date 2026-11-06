import hashlib
import json
import sqlite3

from agentdecompile_recovery.corpus import ingest_recovered as ingest


def connection():
    con = sqlite3.connect(':memory:')
    con.row_factory = sqlite3.Row
    return con


def observed_target(tmp_path):
    target = tmp_path / 'target.bin'
    data = bytes.fromhex('c3')
    target.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    return {'targetSnapshot': {'path': str(target), 'size': len(data), 'sha256': digest},
            'targetRegion': {'address': 4198400, 'offset': 0, 'size': len(data), 'sha256': digest}}


def test_additive_migration_keeps_old_binding_unknown(tmp_path):
    con = connection()
    con.executescript('''
        CREATE TABLE recovered_function (
            program TEXT NOT NULL,
            binary_id INTEGER,
            addr INTEGER,
            name TEXT NOT NULL,
            size INTEGER,
            convention TEXT,
            machine_code TEXT,
            real_c INTEGER NOT NULL,
            logical_id INTEGER,
            path TEXT NOT NULL,
            evidence TEXT,
            PRIMARY KEY (program, name)
        );
    ''')
    source = tmp_path / 'old.c'
    source.write_text('int old(void) { return 1; }')
    con.execute('INSERT INTO recovered_function(program,name,real_c,path) VALUES (?,?,?,?)',
                ('demo', 'old', 1, str(source)))
    ingest.ensure_recovered_schema(con)
    ingest.ensure_recovered_schema(con)
    assert con.execute('SELECT source_sha256 FROM recovered_function').fetchone()[0] is None


def test_parsed_observation_digest_persists_without_rehash_at_insert(tmp_path, monkeypatch):
    recovered = tmp_path/'source'/'demo'
    recovered.mkdir(parents=True)
    coverage = tmp_path/'coverage'
    coverage.mkdir()
    source = recovered/'function_00401000.c'
    original = b'int function_00401000(void) { return 1; }\n'
    source.write_bytes(original)
    digest = hashlib.sha256(original).hexdigest()
    (coverage/'demo.jsonl').write_text(json.dumps({'function':source.stem, 'byteExact':True,
                                                'sourceSha256':digest, 'size':1, 'originalBytes':'c3',**observed_target(tmp_path)})+'\n')
    parsed = ingest.parse_recovered(recovered.parent, coverage)
    assert parsed[0]['source_sha256'] == digest
    source.write_text('changed after observation')
    con = connection()
    con.executescript('CREATE TABLE identity(method TEXT); CREATE TABLE logical_function(canon_key TEXT); CREATE TABLE binary(id INTEGER,repo_path TEXT);')
    monkeypatch.setattr(ingest, 'parse_recovered', lambda *a, **k: parsed)
    monkeypatch.setattr(ingest, 'recovery_identity_indexes', lambda *a: ({}, {}))
    monkeypatch.setattr(ingest, 'logical_from_indexes', lambda *a: None)
    monkeypatch.setattr(ingest, 'print_summary', lambda *a: {})
    ingest.ingest(con, recovered_dir=recovered.parent, coverage_dir=coverage, out_dir=tmp_path/'out')
    assert con.execute('SELECT source_sha256 FROM recovered_function').fetchone()[0] == digest
    assert digest != hashlib.sha256(source.read_bytes()).hexdigest()


def test_seed_insertion_preserves_observed_digest_and_leaves_absent_null(tmp_path):
    con = connection()
    base = dict(program='demo',binary_id=1,addr=1,name='bound',size=1,convention=None,
                machine_code='c3',real_c=1,logical_id=1,path=str(tmp_path/'absent.c'),evidence='observed')
    digest = 'a'*64
    ingest.apply_seed_promotions(con, [{**base,'source_sha256':digest}, {**base,'name':'legacy'}])
    assert dict(con.execute('SELECT name,source_sha256 FROM recovered_function')) == {'bound':digest,'legacy':None}
