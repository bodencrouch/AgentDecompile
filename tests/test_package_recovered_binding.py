import hashlib
import sqlite3

from agentdecompile_recovery.corpus import package_recovered as package


def store(source, digest, legacy=False):
    con = sqlite3.connect(':memory:')
    con.row_factory = sqlite3.Row
    con.execute('CREATE TABLE recovered_function(program,name,path,addr,binary_id,real_c' + ('' if legacy else ',source_sha256') + ')')
    values = ['demo','function',str(source),1,1,1] + ([] if legacy else [digest])
    con.execute('INSERT INTO recovered_function VALUES ('+','.join('?' for _ in values)+')',values)
    return con


def test_package_checks_and_copies_same_snapshot(tmp_path, monkeypatch):
    source = tmp_path/'source.c'
    data = b'int function(void) { return 1; }\r\n'
    source.write_bytes(data)
    con = store(source, hashlib.sha256(data).hexdigest())
    original = package.dest_for
    def mutate_after_check(*args):
        source.write_text('changed after source check')
        return original(*args)
    monkeypatch.setattr(package, 'dest_for', mutate_after_check)
    monkeypatch.setattr(package, 'is_real_c', lambda _: True)
    out = tmp_path/'out'
    result = package.package_from_store(con,out)
    assert result['files'] == 1
    assert next(out.rglob('*.c')).read_bytes() == data
    assert not result['source_binding_rejections']


def test_unbound_stale_and_old_schema_not_exported(tmp_path):
    source = tmp_path/'source.c'
    source.write_text('int function(void) { return 1; }')
    for index, con in enumerate([store(source,None), store(source,'a'*64), store(source,None,legacy=True)]):
        out = tmp_path/str(index)
        result = package.package_from_store(con,out)
        assert result['files'] == 0
        assert len(result['source_binding_rejections']) == 1
        assert not out.exists()
        if index == 2:
            assert 'source_sha256' not in [row[1] for row in con.execute('PRAGMA table_info(recovered_function)')]


def test_existing_output_files_never_overwritten(tmp_path, monkeypatch):
    source = tmp_path/'source.c'
    data = b'int function(void) { return 1; }'
    source.write_bytes(data)
    con = store(source,hashlib.sha256(data).hexdigest())
    monkeypatch.setattr(package,'is_real_c',lambda _:True)
    dest = tmp_path/'out'/'unsorted'/'demo'
    dest.mkdir(parents=True)
    (dest/'function.c').write_bytes(b'user original')
    (dest/'function_1.c').write_bytes(b'user collision')
    result = package.package_from_store(con,tmp_path/'out')
    assert result['files'] == 1
    assert (dest/'function.c').read_bytes() == b'user original'
    assert (dest/'function_1.c').read_bytes() == b'user collision'
    assert sorted(p.read_bytes() for p in dest.glob('*.c')) == sorted([data,b'user original',b'user collision'])
