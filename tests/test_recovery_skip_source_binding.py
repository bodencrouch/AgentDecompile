"""Exercise production selection functions with SQLite; no recovery imports/workers."""
import hashlib
import sqlite3

import pytest
from agentdecompile_recovery.corpus import ghidra_bulk, recover_named_ghidra


@pytest.mark.parametrize('mode', ['current', 'changed', 'missing', 'unbound', 'legacy'])
def test_both_selectors_only_skip_current_source(tmp_path, monkeypatch, mode):
    monkeypatch.setattr(recover_named_ghidra, "program_for_repo", lambda repo: "program")
    con = sqlite3.connect(':memory:')
    con.row_factory = sqlite3.Row
    con.executescript('''
    CREATE TABLE binary(id,repo_path,slug,arch,bits);
    INSERT INTO binary VALUES(1,'/target','target','x86',32);
    CREATE TABLE logical_function(id,canon_key,canon_class,source_file);
    INSERT INTO logical_function VALUES(7,'KnownFunction','KnownClass','known.cpp');
    CREATE TABLE identity(logical_id,binary_id,addr);
    INSERT INTO identity VALUES(7,1,4096);
    CREATE TABLE func(binary_id,addr,size,name,calling_convention,n_instr,is_thunk);
    INSERT INTO func VALUES(1,4096,20,'KnownFunction','cdecl',3,0);
    ''')
    con.execute('CREATE TABLE recovered_function(logical_id,binary_id,addr,real_c,path'+('' if mode == 'legacy' else ',source_sha256')+')')
    source = tmp_path/'known.c'
    content = b'int KnownFunction(void) { return 1; }'
    source.write_bytes(content)
    values = [7,1,4096,1,str(source)]
    if mode != 'legacy':
        values.append(None if mode == 'unbound' else hashlib.sha256(content).hexdigest())
    con.execute('INSERT INTO recovered_function VALUES('+','.join('?' for _ in values)+')',values)
    if mode == 'changed':
        source.write_bytes(content.replace(b'1;',b'2;'))
    elif mode == 'missing':
        source.unlink()
    lids = ghidra_bulk.logical_ids_with_real_c(con)
    candidates = recover_named_ghidra.candidates(con,'/target',10)
    assert lids == ({7} if mode == 'current' else set())
    assert [row['addr'] for row in candidates] == ([] if mode == 'current' else [4096])
