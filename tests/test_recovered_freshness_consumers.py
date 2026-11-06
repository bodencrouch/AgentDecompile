import hashlib
import sqlite3
from agentdecompile_recovery.corpus.coverage_evidence import source_file_binding
from agentdecompile_recovery.corpus.leftover import leftover_store_sets


def test_edited_source_no_longer_suppresses_outstanding_work(tmp_path):
    con=sqlite3.connect(':memory:');con.row_factory=sqlite3.Row
    con.execute('CREATE TABLE recovered_function(logical_id INTEGER, real_c INTEGER, path TEXT, source_sha256 TEXT)')
    source=tmp_path/'source.c';source.write_bytes(b'int f(void){return 1;}')
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    con.execute('INSERT INTO recovered_function VALUES (7,1,?,?)',(str(source),digest))
    con.execute('INSERT INTO recovered_function VALUES (7,0,?,NULL)',(str(tmp_path/'asm.c'),))
    con.execute("INSERT INTO recovered_function VALUES ('corrupt',0,'missing',NULL)")
    assert leftover_store_sets(con)==({7},{7})
    source.write_bytes(b'int f(void){return 2;}')
    assert leftover_store_sets(con)==(set(),{7})
    source.unlink()
    assert leftover_store_sets(con)==(set(),{7})
    assert con.execute('SELECT source_sha256 FROM recovered_function WHERE real_c=1').fetchone()[0]==digest


def test_old_schema_is_read_without_migrating_or_certifying():
    con=sqlite3.connect(':memory:');con.row_factory=sqlite3.Row
    con.execute('CREATE TABLE recovered_function(logical_id INTEGER, real_c INTEGER, path TEXT)')
    con.executemany('INSERT INTO recovered_function VALUES (?,?,?)',[(1,1,'missing'),(2,0,'missing')])
    assert leftover_store_sets(con)==(set(),{2})
    assert 'source_sha256' not in {r[1] for r in con.execute('PRAGMA table_info(recovered_function)')}


def test_file_binding_missing_invalid_and_unreadable_are_not_current(tmp_path):
    assert source_file_binding({'source_sha256':None})['reason']=='missing_or_invalid_source_digest'
    assert source_file_binding({'source_sha256':'a'*64,'path':str(tmp_path/'missing')})['reason']=='source_unreadable'
    assert not source_file_binding({'source_sha256':'a'*64,'path':''})['current']


def test_genproject_skips_require_current_real_source_and_latest_ledger(tmp_path):
    import json
    from agentdecompile_recovery.corpus.genproject import current_recovered_skips
    con=sqlite3.connect(':memory:');con.row_factory=sqlite3.Row
    con.execute('CREATE TABLE recovered_function(binary_id INTEGER,addr INTEGER,name TEXT,real_c INTEGER,path TEXT,source_sha256 TEXT)')
    source=tmp_path/'f.c';source.write_bytes(b'int f(void){return 1;}')
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    con.execute('INSERT INTO recovered_function VALUES (1,4096,?,1,?,?)',('F',str(source),digest))
    con.execute('INSERT INTO recovered_function VALUES (1,8192,?,0,?,?)',('Asm',str(source),digest))
    con.execute('INSERT INTO recovered_function VALUES (1,?, ?,1,?,?)',('corrupt','Bad',str(source),digest))
    ledger=tmp_path/'coverage.jsonl'
    good={'function':'G','byteExact':True,'sourceSha256':digest,'path':str(source)}
    ledger.write_text(json.dumps(good)+'\n')
    assert current_recovered_skips(con,1,ledger)==({4096},{'F','G'})
    ledger.write_text(json.dumps(good)+'\n'+json.dumps({'function':'G','byteExact':False})+'\n')
    assert current_recovered_skips(con,1,ledger)==({4096},{'F'})
    source.write_bytes(b'changed')
    assert current_recovered_skips(con,1,ledger)==(set(),set())
