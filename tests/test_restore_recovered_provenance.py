import hashlib
import json
import sqlite3

from agentdecompile_recovery.corpus.restore_recovered_tree import restore


def setup(tmp_path, *, digest=None, legacy=False):
    con = sqlite3.connect(':memory:')
    con.row_factory = sqlite3.Row
    con.execute('CREATE TABLE recovered_function(program TEXT, name TEXT, size INTEGER, convention TEXT, real_c INTEGER, path TEXT, machine_code TEXT' + ('' if legacy else ',source_sha256 TEXT') + ')')
    values = ['demo', 'fn', 4, 'cdecl', 1, None, '90c3']
    if not legacy:
        values.append(digest)
    con.execute('INSERT INTO recovered_function VALUES (' + ','.join('?' for _ in values) + ')',values)
    package=tmp_path/'package';package.mkdir()
    source=package/'fn.c';source.write_bytes(b'int fn() {return 1;}  \r\n')
    return con,source,dict(recovered_dir=tmp_path/'recovered',coverage_dir=tmp_path/'coverage',package_dir=package)


def ledger(args):
    return json.loads((args['coverage_dir']/'demo.jsonl').read_text())


def test_matching_producer_digest_retained_without_verdict_upgrade(tmp_path):
    data=b'int fn() {return 1;}  \r\n'
    digest=hashlib.sha256(data).hexdigest()
    con,source,args=setup(tmp_path,digest=digest)
    report=restore(con,**args)
    assert report['bodies_restored']==1
    assert (args['recovered_dir']/'demo/fn.c').read_bytes()==data
    row=ledger(args)
    assert row['sourceSha256']==digest and row['sourceBinding']['current'] is True
    assert row['byteExact'] is False and row['matched'] is False
    assert row['verificationState']=='unverified' and row['reused'] is True


def test_legacy_schema_restores_without_minting_digest(tmp_path):
    con,source,args=setup(tmp_path,legacy=True)
    restore(con,**args)
    row=ledger(args)
    assert 'sourceSha256' not in row and row['byteExact'] is False
    assert row['sourceBinding']['reason']=='missing_or_invalid_source_digest'
    assert 'source_sha256' not in {r[1] for r in con.execute('PRAGMA table_info(recovered_function)')}


def test_changed_existing_file_never_overwritten_or_rebound(tmp_path):
    digest=hashlib.sha256(b'old').hexdigest()
    con,source,args=setup(tmp_path,digest=digest)
    dest=args['recovered_dir']/'demo/fn.c';dest.parent.mkdir(parents=True);dest.write_bytes(b'user work')
    report=restore(con,**args)
    assert report['bodies_kept']==1 and dest.read_bytes()==b'user work'
    row=ledger(args)
    assert 'sourceSha256' not in row and row['recordedSourceSha256']==digest
    assert row['sourceBinding']['reason']=='source_digest_mismatch'


def test_digest_selects_correct_same_name_package(tmp_path):
    data=b'correct\r\n';digest=hashlib.sha256(data).hexdigest()
    con,source,args=setup(tmp_path,digest=digest)
    other=args['package_dir']/'nested';other.mkdir();(other/'fn.c').write_bytes(data)
    restore(con,**args)
    assert (args['recovered_dir']/'demo/fn.c').read_bytes()==data
    assert ledger(args)['sourceSha256']==digest


def test_dry_run_does_not_modify_tree_or_database(tmp_path):
    con,source,args=setup(tmp_path,legacy=True)
    before=con.total_changes
    restore(con,**args,dry_run=True)
    assert not args['recovered_dir'].exists() and not args['coverage_dir'].exists()
    assert con.total_changes==before
