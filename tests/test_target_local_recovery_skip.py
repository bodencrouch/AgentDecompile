"""A donor is useful evidence, never an automatic recipient completion claim."""
import hashlib
import sqlite3
from agentdecompile_recovery.corpus.ghidra_bulk import current_recovered_addresses


def test_shared_logical_identity_cannot_suppress_other_binary(tmp_path):
    con=sqlite3.connect(':memory:')
    con.execute('CREATE TABLE recovered_function(binary_id,addr,logical_id,real_c,path,source_sha256)')
    donor=tmp_path/'donor.c';donor.write_bytes(b'int donor(void){return 1;}')
    digest=hashlib.sha256(donor.read_bytes()).hexdigest()
    con.execute('INSERT INTO recovered_function VALUES (1,4096,7,1,?,?)',(str(donor),digest))
    assert current_recovered_addresses(con,1)=={4096}
    assert current_recovered_addresses(con,2)==set()
    # Only a separately recorded recipient observation can cover its address.
    recipient=tmp_path/'recipient.c';recipient.write_bytes(b'int recipient(void){return 2;}')
    con.execute('INSERT INTO recovered_function VALUES (2,8192,7,1,?,?)',(str(recipient),hashlib.sha256(recipient.read_bytes()).hexdigest()))
    assert current_recovered_addresses(con,2)=={8192}
    recipient.write_bytes(b'changed')
    assert current_recovered_addresses(con,2)==set()
    assert current_recovered_addresses(con,1)=={4096}


def test_legacy_and_bad_address_are_not_target_proof(tmp_path):
    con=sqlite3.connect(':memory:')
    con.execute('CREATE TABLE recovered_function(binary_id,addr,real_c,path)')
    con.execute("INSERT INTO recovered_function VALUES(1,4096,1,'old.c')")
    assert current_recovered_addresses(con,1)==set()
    con.execute('ALTER TABLE recovered_function ADD COLUMN source_sha256')
    source=tmp_path/'x.c';source.write_bytes(b'int x;')
    con.execute('INSERT INTO recovered_function VALUES(1,?,1,?,?)',('bad',str(source),hashlib.sha256(source.read_bytes()).hexdigest()))
    assert current_recovered_addresses(con,1)==set()


def test_recipient_filename_does_not_authenticate_different_body(tmp_path):
    from agentdecompile_recovery.corpus.ghidra_bulk import current_source_at_address, should_queue
    con=sqlite3.connect(':memory:')
    con.execute('CREATE TABLE recovered_function(binary_id,addr,real_c,path,source_sha256)')
    observed=tmp_path/'observed.c';observed.write_bytes(b'int f(void){return 1;}')
    digest=hashlib.sha256(observed.read_bytes()).hexdigest()
    con.execute('INSERT INTO recovered_function VALUES (1,4096,1,?,?)',(str(observed),digest))
    local=tmp_path/'F_00001000.c';local.write_bytes(b'int f(void){return 2;}')
    assert not current_source_at_address(con,1,4096,local)
    assert should_queue('unverified-c','skip-existing')
    local.write_bytes(observed.read_bytes())
    assert current_source_at_address(con,1,4096,local)
    assert not current_source_at_address(con,2,4096,local)
