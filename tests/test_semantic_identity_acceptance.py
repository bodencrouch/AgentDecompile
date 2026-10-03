"""Embedded export identity through real ingestion, persistence and consumers."""
import hashlib
import json
import sqlite3
import struct
from pathlib import Path

import pytest

from agentdecompile_recovery.corpus.coverage_evidence import bind_source
from agentdecompile_recovery.corpus.ingest_recovered import (
    ensure_recovered_schema,
    ingest,
    prune_unverified,
)
from agentdecompile_recovery.corpus.export_run_report import build
from agentdecompile_recovery.corpus.package_recovered import package_from_store
from agentdecompile_recovery.corpus.semantic_identity import ACCEPTED, LOCAL_ONLY, observe_target, evaluate_candidate
from agentdecompile_recovery.inventory import build_binary_inventory
from agentdecompile_recovery.targets import identify_binary


def pe_image(*, plus=False, names=None, mutation=None):
    """Two identical bodies, a forwarder, and every original name-table row."""
    blob = bytearray(0x800)
    base = 0x140000000 if plus else 0x400000
    blob[:2] = b'MZ'
    def u16(off, value): struct.pack_into('<H', blob, off, value)
    def u32(off, value): struct.pack_into('<I', blob, off, value)
    u32(0x3c, 0x80)
    blob[0x80:0x84] = b'PE\0\0'
    u16(0x84, 0x8664 if plus else 0x14c)
    u16(0x86, 2)
    optional = 0x98
    optional_size = 0xf0 if plus else 0xe0
    u16(0x94, optional_size)
    u16(optional, 0x20b if plus else 0x10b)
    u32(optional + 16, 0x1000)
    if plus: struct.pack_into('<Q', blob, optional + 24, base)
    else: u32(optional + 28, base)
    u32(optional + 32, 0x1000)
    u32(optional + 36, 0x200)
    u32(optional + 56, 0x3000)
    u32(optional + 60, 0x200)
    u32(optional + (108 if plus else 92), 16)
    directory = optional + (112 if plus else 96)
    u32(directory, 0x2000)
    u32(directory + 4, 0x400)
    section = optional + optional_size
    for off, name, va, raw, size, flags in [(section, b'.text', 0x1000, 0x200, 0x200, 0x60000020),
                                          (section + 40, b'.edata', 0x2000, 0x400, 0x400, 0x40000040)]:
        blob[off:off+len(name)] = name
        for delta, value in [(8,size),(12,va),(16,size),(20,raw),(36,flags)]: u32(off+delta,value)
    blob[0x200:0x203] = blob[0x220:0x223] = b'\x33\xc0\xc3'
    names = [('Foo', 0), ('Bar', 1), ('Forwarded', 2)] if names is None else names
    for delta, value in [(16,1),(20,3),(24,len(names)),(28,0x2040),(32,0x2060),(36,0x2090)]: u32(0x400+delta,value)
    for index, rva in enumerate([0x1000,0x1020,0x2180]): u32(0x440+index*4,rva)
    cursor = 0x500
    for index,(name,ordinal) in enumerate(names):
        data = name.encode('ascii') + b'\0'
        blob[cursor:cursor+len(data)] = data
        u32(0x460+index*4, cursor-0x400+0x2000)
        u16(0x490+index*2,ordinal)
        cursor += len(data)
    blob[0x580:0x58b] = b'other.Func\0'
    if mutation == 'no_exports': u32(directory,0); u32(directory+4,0)
    elif mutation == 'truncated_functions': u32(0x400+28,0x23fc)
    elif mutation == 'truncated_names': u32(0x400+32,0x23fc)
    elif mutation == 'truncated_ordinals': u32(0x400+36,0x23ff)
    elif mutation == 'invalid_ordinal': u16(0x490+2,99)
    elif mutation == 'unterminated': u32(0x460+4,0x23f0); blob[0x7f0:] = b'X'*16
    elif mutation == 'virtual_tail': u32(section+40+8,0x800); u32(0x460+4,0x2400)
    elif mutation == 'overlap': u32(section+12,0x2000)
    elif mutation == 'short_optional': u16(0x94,80)
    elif mutation == 'truncated_image': del blob[0x700:]
    elif mutation == 'zero_named_function': u32(0x440+4,0)
    elif mutation == 'forwarder_unterminated': u32(0x440+8,0x23f0); blob[0x7f0:]=b'Y'*16
    elif mutation == 'nonpe': blob[:4] = b'data'
    return bytes(blob), base


def prepared(tmp_path, *, plus=False, names=None, mutation=None, corpus_digest=True):
    raw = tmp_path/'raw'; raw.mkdir()
    target = raw/'fixture'
    blob,base = pe_image(plus=plus,names=names,mutation=mutation)
    target.write_bytes(blob)
    digest = hashlib.sha256(blob).hexdigest()
    con = sqlite3.connect(':memory:'); con.row_factory = sqlite3.Row
    con.executescript('''CREATE TABLE binary(id INTEGER,repo_path TEXT,slug TEXT,content_sha256 TEXT);
    CREATE TABLE identity(logical_id INTEGER,binary_id INTEGER,addr INTEGER,method TEXT);
    CREATE TABLE logical_function(id INTEGER,canon_key TEXT);
    CREATE TABLE func(binary_id INTEGER,addr INTEGER,name TEXT,canon_key TEXT,
        size INTEGER,is_thunk INTEGER,source TEXT,canon_class TEXT,n_instr INTEGER);''')
    con.execute('INSERT INTO binary VALUES (1,?,?,?)',('/fixture','fixture',digest if corpus_digest else None))
    con.execute("INSERT INTO logical_function VALUES (9,'untrusted-logical')")
    for addr in [base+0x1000,base+0x1020,base+0x2180]:
        con.execute("INSERT INTO identity VALUES (9,1,?,'name-unique')",(addr,))
    (tmp_path/'recovered').mkdir(); (tmp_path/'coverage').mkdir()
    return con,target,blob,base,digest


def ordinary(tmp_path, target, blob, base, name, rva, *, program='ordinary', offset=None, corrupt=None):
    folder = tmp_path/'recovered'/program; folder.mkdir(exist_ok=True)
    source = folder/f'{name}.c'; source.write_text('int candidate(void) { return 0; }\n')
    offset = (0x200+rva-0x1000 if rva < 0x2000 else 0x400+rva-0x2000) if offset is None else offset
    data = blob[offset:offset+3]
    row = bind_source({'function':name,'byteExact':True,'size':3,'originalBytes':data.hex(),
                       'targetSnapshot':{'path':str(target),'size':len(blob),'sha256':hashlib.sha256(blob).hexdigest()},
                       'targetRegion':{'address':base+rva,'offset':offset,'size':3,'sha256':hashlib.sha256(data).hexdigest()}},source.read_bytes())
    if corrupt == 'source': row['sourceSha256']='a'*64
    elif corrupt == 'bytes': row['originalBytes']='909090'
    elif corrupt == 'target': row['targetSnapshot']['sha256']='a'*64
    with (tmp_path/'coverage'/f'{program}.jsonl').open('a') as stream: stream.write(json.dumps(row)+'\n')
    return source,row


def run_ingress(tmp_path, con, *, mapping=None, **kwargs):
    return ingest(con,recovered_dir=tmp_path/'recovered',coverage_dir=tmp_path/'coverage',out_dir=tmp_path/'summary',
                  raw_dir=tmp_path/'raw',program_to_repo=mapping or {'ordinary':'/fixture','other':'/fixture'},**kwargs)


def persisted(con): return [dict(row) for row in con.execute('SELECT * FROM recovered_function ORDER BY program,name')]

def plugin(report, program, name):
    return next(row for row in report['results'] if row['promptPath']==f'{program}/{name}')['postMatchPhase']['pluginResults'][0]


@pytest.mark.parametrize('plus',[False,True], ids=['PE32','PE32plus'])
def test_real_ingestion_foo_false_foo_and_independent_bar_survive(tmp_path,plus):
    con,target,blob,base,digest = prepared(tmp_path,plus=plus)
    ordinary(tmp_path,target,blob,base,'Foo',0x1000)
    ordinary(tmp_path,target,blob,base,'Foo',0x1020,program='other')
    ordinary(tmp_path,target,blob,base,'Bar',0x1020)
    summary=run_ingress(tmp_path,con)
    rows={(r['program'],r['name']):r for r in persisted(con)}
    assert len(rows)==3
    assert rows['ordinary','Foo']['semantic_status']==rows['ordinary','Bar']['semantic_status']==ACCEPTED
    wrong=rows['other','Foo']; assert wrong['semantic_status']==LOCAL_ONLY
    assert wrong['semantic_reason']=='target_export_address_mismatch' and wrong['logical_id']==9
    evidence=json.loads(rows['ordinary','Foo']['semantic_evidence'])
    assert evidence['target']['sha256']==digest
    assert evidence['witness']['va']==evidence['target']['imageBase']+evidence['witness']['rva']==base+0x1000
    assert evidence['claimScope']=='target-pe-export-name-at-va-v1'
    assert evidence['witness']['source']=='embedded-pe-export-directory'
    assert not any(value in json.dumps(evidence) for value in ['Ghidra','identity.method','is_authentic_symbol','static_status'])
    report=build(con)
    assert plugin(report,'ordinary','Foo')['status']=='success'
    assert plugin(report,'ordinary','Bar')['status']=='success'
    assert plugin(report,'other','Foo')['status']=='skipped'
    assert 'advisory' in plugin(report,'other','Foo')['output']
    out=tmp_path/'package'; packed=package_from_store(con,out)
    assert (packed['named_files'],packed['target_local_files'],packed['files'])==(2,1,3)
    assert sorted(p.name for p in out.rglob('*.c'))==sorted(['Foo.c','Bar.c',f'sub_{base+0x1020:08x}.c'])
    assert summary['recovered_named_target_exports']==2


@pytest.mark.parametrize('plus',[False,True])
@pytest.mark.parametrize('name,names,rva,reason',[
    ('Alias',[('Foo',0),('Alias',0),('Bar',1)],0x1000,'accepted_unique_nonforwarded_export'),
    ('ordinal_12',[('ordinal_12',0)],0x1000,'accepted_unique_nonforwarded_export'),
    ('ordinal_2',[('Foo',0)],0x1020,'target_export_missing'),
    ('Foo',[('Foo',0),('Foo',1)],0x1000,'target_export_ambiguous'),
    ('Foo',[('Foo',0),('Foo',0)],0x1000,'target_export_ambiguous'),
    ('Foo',[('Foo',0),('Foo',2)],0x1000,'target_export_ambiguous'),
    ('Forwarded',None,0x2180,'target_export_forwarded'),
    ('foo',None,0x1000,'target_export_missing'),
])
def test_complete_named_rows_and_exact_matching(tmp_path,plus,name,names,rva,reason):
    con,target,blob,base,_=prepared(tmp_path,plus=plus,names=names)
    ordinary(tmp_path,target,blob,base,name,rva)
    run_ingress(tmp_path,con)
    row=persisted(con)[0]
    assert row['semantic_reason']==reason
    assert row['semantic_status']==(ACCEPTED if reason.startswith('accepted') else LOCAL_ONLY)
    package=package_from_store(con,tmp_path/'package')
    assert package['files']==1
    assert package['named_files']==int(row['semantic_status']==ACCEPTED)


@pytest.mark.parametrize('plus',[False,True])
@pytest.mark.parametrize('mutation',['truncated_functions','truncated_names','truncated_ordinals','invalid_ordinal',
                                    'unterminated','virtual_tail','overlap','short_optional','truncated_image',
                                    'zero_named_function','forwarder_unterminated'])
def test_malformed_tables_cannot_certify_unique_name(tmp_path,plus,mutation):
    con,target,blob,base,_=prepared(tmp_path,plus=plus,mutation=mutation)
    ordinary(tmp_path,target,blob,base,'Foo',0x1000)
    run_ingress(tmp_path,con)
    row=persisted(con)[0]
    assert row['semantic_status']==LOCAL_ONLY
    assert row['semantic_reason']=='malformed_target_inventory'
    assert package_from_store(con,tmp_path/'package')['target_local_files']==1


@pytest.mark.parametrize('mutation,corpus_digest,reason',[
    ('no_exports',True,'target_export_missing'),('nonpe',True,'unsupported_target_format'),
    (None,False,'missing_corpus_target_digest')])
def test_unavailable_witness_retains_address_local_source(tmp_path,mutation,corpus_digest,reason):
    con,target,blob,base,_=prepared(tmp_path,mutation=mutation,corpus_digest=corpus_digest)
    ordinary(tmp_path,target,blob,base,'Foo',0x1000)
    run_ingress(tmp_path,con)
    assert persisted(con)[0]['semantic_reason']==reason
    assert package_from_store(con,tmp_path/'package')['target_local_files']==1


def test_changed_corpus_target_with_valid_old_candidate_remains_local(tmp_path):
    con,target,blob,base,_=prepared(tmp_path)
    original=tmp_path/'original'; original.write_bytes(blob)
    ordinary(tmp_path,original,blob,base,'Foo',0x1000)
    target.write_bytes(blob+b'changed')
    run_ingress(tmp_path,con)
    assert persisted(con)[0]['semantic_reason']=='corpus_target_digest_mismatch'
    assert package_from_store(con,tmp_path/'package')['target_local_files']==1


def test_candidate_target_digest_must_equal_independently_observed_corpus_target(tmp_path):
    con,target,blob,base,_=prepared(tmp_path)
    other=tmp_path/'other'; altered=blob+b'different'; other.write_bytes(altered)
    ordinary(tmp_path,other,altered,base,'Foo',0x1000)
    run_ingress(tmp_path,con)
    assert persisted(con)[0]['semantic_reason']=='candidate_target_digest_mismatch'


def test_aliases_remain_visible_in_exploratory_inventory(tmp_path):
    _,target,_,_,_=prepared(tmp_path,names=[('Foo',0),('Alias',0)])
    result=build_binary_inventory(identify_binary(target))
    assert {r['name'] for r in result['exports']} >= {'Foo','Alias'}


def test_frozen_snapshot_and_later_inventory_digest_describe_actual_parsed_bytes(tmp_path):
    _,target,blob,_,digest=prepared(tmp_path)
    frozen=identify_binary(target,retain_snapshot=True)
    earlier=identify_binary(target)
    changed,_=pe_image(names=[('Changed',0)])
    target.write_bytes(changed)
    pinned=build_binary_inventory(frozen)
    current=build_binary_inventory(earlier)
    assert pinned['target']['sha256']==digest and any(r['name']=='Foo' for r in pinned['exportObservation']['exports'])
    assert current['target']['sha256']==hashlib.sha256(changed).hexdigest()!=digest
    assert any(r['name']=='Changed' for r in current['exportObservation']['exports'])


@pytest.mark.parametrize('corrupt',['source','bytes','target'])
def test_named_export_cannot_bypass_existing_local_admission(tmp_path,corrupt):
    con,target,blob,base,_=prepared(tmp_path)
    ordinary(tmp_path,target,blob,base,'Foo',0x1000,corrupt=corrupt)
    run_ingress(tmp_path,con)
    assert persisted(con)==[]


def test_wrong_recorded_offset_cannot_assert_export_name_even_with_identical_bytes(tmp_path):
    con,target,blob,base,_=prepared(tmp_path)
    ordinary(tmp_path,target,blob,base,'Foo',0x1000,offset=0x220)
    run_ingress(tmp_path,con)
    assert persisted(con)[0]['semantic_reason']=='candidate_target_region_mismatch'


@pytest.mark.parametrize('name,rva,reason',[('Foo',0x1000,'accepted_unique_nonforwarded_export'),
                                         ('Foo',0x1020,'target_export_address_mismatch'),
                                         ('Bar',0x1020,'accepted_unique_nonforwarded_export')])
def test_seed_and_ordinary_share_ingress_without_program_mapping(tmp_path,name,rva,reason):
    con,target,blob,base,_=prepared(tmp_path)
    source,observation=ordinary(tmp_path,target,blob,base,name,rva)
    seed=tmp_path/'seed.c'; seed.write_bytes(source.read_bytes())
    seed_row={**observation,'static_status':'identity_linked','compile_status':'byte_exact','real_c':True,
              'comparisonPolicy':'raw-region-v1','dst_slug':'fixture','dst_addr':f'{base+rva:x}',
              'source_path':str(source),'logical_ids':[9],'seed':str(seed),'source_name':name,
              'dst_name':'UntrustedReplacementName','destination_bytes':observation['originalBytes']}
    results=tmp_path/'seeds.jsonl'; results.write_text(json.dumps(seed_row)+'\n')
    reuse=tmp_path/'reuse.jsonl'; reuse.write_text('')
    run_ingress(tmp_path,con,seed_results=results,reuse_candidates=reuse)
    rows=persisted(con)
    assert len(rows)==2 and {r['binary_id'] for r in rows}=={1}
    assert {r['name'] for r in rows}=={name}
    assert {r['semantic_reason'] for r in rows}=={reason}
    report=build(con)
    assert plugin(report,'fixture',name)['status']==('success' if reason.startswith('accepted') else 'skipped')
    package=package_from_store(con,tmp_path/'package')
    assert package['files']==2 and package['named_files']==(2 if reason.startswith('accepted') else 0)


def test_schema_migration_leaves_old_rows_unverified_and_package_address_named(tmp_path):
    con=sqlite3.connect(':memory:'); con.row_factory=sqlite3.Row
    con.executescript('CREATE TABLE recovered_function(program,name,addr,size,convention,real_c,logical_id,path,evidence,machine_code,binary_id,source_sha256)')
    source=tmp_path/'old.c'; data=b'int old(void) { return 0; }'; source.write_bytes(data)
    con.execute('INSERT INTO recovered_function VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                ('legacy','WrongName',0x401000,3,None,1,9,str(source),None,'33c0c3',1,hashlib.sha256(data).hexdigest()))
    ensure_recovered_schema(con)
    row=persisted(con)[0]
    assert all(row[k] is None for k in ['semantic_status','semantic_reason','semantic_evidence','target_sha256'])
    assert plugin(build(con),'legacy','WrongName')['status']=='skipped'
    assert package_from_store(con,tmp_path/'package')['target_local_files']==1
    assert next((tmp_path/'package').rglob('*.c')).name=='sub_00401000.c'


def test_consumers_report_recorded_scope_without_claiming_current_target(tmp_path):
    con,target,blob,base,_=prepared(tmp_path)
    ordinary(tmp_path,target,blob,base,'Foo',0x1000)
    run_ingress(tmp_path,con)
    target.unlink()
    identity=plugin(build(con),'ordinary','Foo')
    assert identity['status']=='success' and 'not rechecked' in identity['output']
    packed=package_from_store(con,tmp_path/'package')
    assert packed['named_files']==1 and 'not rechecked' in packed['named_claim']


@pytest.mark.parametrize('field,value',[('semantic_evidence','{}'),('semantic_evidence','invalid'),
                                       ('target_sha256','a'*64),('name','FalseName'),('addr',0x401020)])
def test_consumers_refuse_incoherent_or_status_only_witness(tmp_path,field,value):
    con,target,blob,base,_=prepared(tmp_path)
    ordinary(tmp_path,target,blob,base,'Foo',0x1000)
    run_ingress(tmp_path,con)
    con.execute(f'UPDATE recovered_function SET {field}=?',(value,))
    assert build(con)['results'][0]['postMatchPhase']['pluginResults'][0]['status']=='skipped'
    packed=package_from_store(con,tmp_path/'package')
    assert packed['named_files']==0 and packed['target_local_files']==1


def test_package_collision_names_are_deterministic_and_preserve_user_bytes(tmp_path):
    con,target,blob,base,_=prepared(tmp_path)
    ordinary(tmp_path,target,blob,base,'Foo',0x1020)
    run_ingress(tmp_path,con)
    for dirname in ['first','second']:
        folder=tmp_path/dirname/'unsorted'/'ordinary'; folder.mkdir(parents=True)
        for name in ['sub_00401020.c','sub_00401020_401020.c']:
            (folder/name).write_bytes(b'user-owned')
        packed=package_from_store(con,tmp_path/dirname)
        assert packed['target_local_files']==1
        assert (folder/'sub_00401020_401020_1.c').is_file()
        assert (folder/'sub_00401020.c').read_bytes()==b'user-owned'
        assert (folder/'sub_00401020_401020.c').read_bytes()==b'user-owned'


@pytest.mark.parametrize('ordinary_rva,seed_rva',[(0x1000,0x1020),(0x1020,0x1000)])
def test_same_program_same_name_seed_and_ordinary_do_not_overwrite_each_other(tmp_path,ordinary_rva,seed_rva):
    con,target,blob,base,_=prepared(tmp_path)
    source,observation=ordinary(tmp_path,target,blob,base,'Foo',ordinary_rva,program='fixture')
    seed=tmp_path/'seed.c'; seed.write_bytes(source.read_bytes())
    seed_row={**observation,'static_status':'identity_linked','compile_status':'byte_exact','real_c':True,
              'comparisonPolicy':'raw-region-v1','dst_slug':'fixture','dst_addr':f'{base+seed_rva:x}',
              'source_path':str(source),'logical_ids':[9],'seed':str(seed),'source_name':'Foo',
              'dst_name':'Foo','destination_bytes':'33c0c3',
              'targetRegion':{**observation['targetRegion'],'address':base+seed_rva,'offset':0x200+seed_rva-0x1000}}
    results=tmp_path/'seeds.jsonl'; results.write_text(json.dumps(seed_row)+'\n')
    reuse=tmp_path/'reuse.jsonl'; reuse.write_text('')
    run_ingress(tmp_path,con,mapping={'fixture':'/fixture'},seed_results=results,reuse_candidates=reuse)
    rows={r['addr']:r for r in persisted(con)}
    assert len(rows)==2 and {r['program'] for r in rows.values()}=={'fixture'}
    assert {r['name'] for r in rows.values()}=={'Foo'}
    assert rows[base+0x1000]['semantic_status']==ACCEPTED
    assert rows[base+0x1020]['semantic_status']==LOCAL_ONLY
    assert rows[base+0x1020]['semantic_reason']=='target_export_address_mismatch'
    report=build(con)
    statuses={r['provenance']['address']:r['postMatchPhase']['pluginResults'][0]['status'] for r in report['results']}
    assert statuses=={base+0x1000:'success',base+0x1020:'skipped'}
    packed=package_from_store(con,tmp_path/'package')
    assert (packed['files'],packed['named_files'],packed['target_local_files'])==(2,1,1)
    assert sorted(p.name for p in (tmp_path/'package').rglob('*.c'))==['Foo.c','sub_00401020.c']


def test_legacy_candidate_key_migration_preserves_all_data_indexes_and_triggers(tmp_path):
    from agentdecompile_recovery.corpus.ingest_recovered import RECOVERED_SCHEMA
    con=sqlite3.connect(':memory:'); con.row_factory=sqlite3.Row
    con.executescript(RECOVERED_SCHEMA.replace('PRIMARY KEY (program, name, binary_id, addr, path, source_sha256)','PRIMARY KEY (program, name)'))
    con.execute('ALTER TABLE recovered_function ADD COLUMN custom_note TEXT DEFAULT "user default"')
    con.execute('CREATE INDEX ix_user_note ON recovered_function(custom_note)')
    con.execute('CREATE TABLE user_audit(note TEXT)')
    con.execute('CREATE TRIGGER recovered_user_trigger AFTER INSERT ON recovered_function BEGIN INSERT INTO user_audit VALUES (NEW.name); END')
    con.execute("INSERT INTO recovered_function(program,name,binary_id,addr,real_c,path,custom_note) VALUES ('same','Foo',1,4198400,1,'old.c','preserved')")
    con.execute("INSERT INTO recovered_function(program,name,real_c,path) VALUES ('legacy','Unknown',1,'unknown.c')")
    before=[tuple(row) for row in con.execute('SELECT * FROM recovered_function ORDER BY program')]
    ensure_recovered_schema(con); ensure_recovered_schema(con)
    assert [tuple(row) for row in con.execute('SELECT * FROM recovered_function ORDER BY program')]==before
    assert {row[1] for row in con.execute('PRAGMA index_list(recovered_function)')} >= {'ix_user_note','ix_recovered_logical'}
    assert con.execute("SELECT count(*) FROM user_audit").fetchone()[0]==2
    con.execute("INSERT INTO recovered_function(program,name,binary_id,addr,real_c,path) VALUES ('same','Foo',1,4198432,1,'local.c')")
    con.execute("INSERT INTO recovered_function(program,name,binary_id,addr,real_c,path) VALUES ('same','Foo',2,4198400,1,'other-binary.c')")
    assert con.execute("SELECT count(*) FROM recovered_function WHERE name='Foo'").fetchone()[0]==3
    assert con.execute("SELECT count(*) FROM user_audit").fetchone()[0]==4
    assert all(row[0] is None for row in con.execute('SELECT semantic_status FROM recovered_function'))


def test_report_created_historical_table_can_later_ingest(tmp_path):
    con,target,blob,base,_=prepared(tmp_path)
    assert build(con)['results']==[]  # creates the historical report-only schema
    assert 'binary_id' not in {r[1] for r in con.execute('PRAGMA table_info(recovered_function)')}
    ordinary(tmp_path,target,blob,base,'Foo',0x1000)
    run_ingress(tmp_path,con)
    assert persisted(con)[0]['binary_id']==1
    assert persisted(con)[0]['semantic_status']==ACCEPTED
    assert plugin(build(con),'ordinary','Foo')['status']=='success'
    assert package_from_store(con,tmp_path/'package')['named_files']==1


@pytest.mark.parametrize('order',[(0x1000,0x1020),(0x1020,0x1000)])
def test_two_seed_candidates_with_same_program_and_name_survive_both_orders(tmp_path,order):
    con,target,blob,base,_=prepared(tmp_path)
    source,observation=ordinary(tmp_path,target,blob,base,'Foo',0x1000)
    (tmp_path/'coverage'/'ordinary.jsonl').unlink()  # this case admits only seeds
    seeds=[]
    for rva in order:
        seed=tmp_path/f'seed-{rva}.c'; seed.write_bytes(source.read_bytes())
        seeds.append({**observation,'static_status':'identity_linked','compile_status':'byte_exact','real_c':True,
                      'comparisonPolicy':'raw-region-v1','dst_slug':'fixture','dst_addr':f'{base+rva:x}',
                      'source_path':str(source),'logical_ids':[9],'seed':str(seed),'source_name':'Foo',
                      'destination_bytes':'33c0c3',
                      'targetRegion':{**observation['targetRegion'],'address':base+rva,'offset':0x200+rva-0x1000}})
    results=tmp_path/'seeds.jsonl'; results.write_text(''.join(json.dumps(row)+'\n' for row in seeds))
    reuse=tmp_path/'reuse.jsonl'; reuse.write_text('')
    run_ingress(tmp_path,con,seed_results=results,reuse_candidates=reuse)
    rows={r['addr']:r for r in persisted(con)}
    assert len(rows)==2 and rows[base+0x1000]['semantic_status']==ACCEPTED
    assert rows[base+0x1020]['semantic_status']==LOCAL_ONLY
    report=build(con)
    assert [r['provenance']['address'] for r in report['results']]==[base+0x1000,base+0x1020]
    assert [r['postMatchPhase']['pluginResults'][0]['status'] for r in report['results']]==['success','skipped']
    packed=package_from_store(con,tmp_path/'package')
    assert (packed['files'],packed['named_files'],packed['target_local_files'])==(2,1,1)
    assert sorted(p.name for p in (tmp_path/'package').rglob('*.c'))==['Foo.c','sub_00401020.c']


def test_distinct_source_provenance_at_same_address_cannot_overwrite_witness(tmp_path):
    con,target,blob,base,_=prepared(tmp_path)
    source,observation=ordinary(tmp_path,target,blob,base,'Foo',0x1000,program='fixture')
    seed=tmp_path/'different-source.c'; seed.write_text('int other_candidate(void) { return 0; }\n')
    seed_row=bind_source({**observation,'static_status':'identity_linked','compile_status':'byte_exact','real_c':True,
                         'comparisonPolicy':'raw-region-v1','dst_slug':'fixture','dst_addr':f'{base+0x1000:x}',
                         'source_path':str(source),'logical_ids':[9],'seed':str(seed),'source_name':'Foo',
                         'destination_bytes':'33c0c3','targetRegion':{**observation['targetRegion'],'offset':0x220}},seed.read_bytes())
    results=tmp_path/'seeds.jsonl'; results.write_text(json.dumps(seed_row)+'\n')
    reuse=tmp_path/'reuse.jsonl'; reuse.write_text('')
    run_ingress(tmp_path,con,mapping={'fixture':'/fixture'},seed_results=results,reuse_candidates=reuse)
    rows=persisted(con)
    assert len(rows)==2 and {r['addr'] for r in rows}=={base+0x1000}
    assert {r['path'] for r in rows}=={str(source),str(seed)}
    assert {r['semantic_status'] for r in rows}=={ACCEPTED,LOCAL_ONLY}
    packed=package_from_store(con,tmp_path/'package')
    assert (packed['files'],packed['named_files'],packed['target_local_files'])==(2,1,1)


def test_prune_uses_full_candidate_identity_and_preserves_shared_reuse_rows(tmp_path):
    con=sqlite3.connect(':memory:')
    ensure_recovered_schema(con)
    rows=[
        ('fixture','Foo',1,0x401000,'first.c','a'*64),
        ('fixture','Foo',1,0x401020,'second.c','b'*64),
        ('fixture','Bar',1,0x401020,'bar.c','c'*64),
    ]
    con.executemany(
        'INSERT INTO recovered_function(program,name,binary_id,addr,path,source_sha256,real_c) '
        'VALUES (?,?,?,?,?,?,1)', rows)
    con.executemany(
        'INSERT INTO reuse_candidate(src_program,src_name,dst_binary_id,dst_addr,size,real_c,basis) '
        "VALUES (?,?,2,?,3,1,'test')",
        [('fixture','Foo',0x501000),('fixture','Bar',0x501020)])
    retained=[dict(zip(
        ('program','name','binary_id','addr','path','source_sha256'), row))
        for row in rows[1:]
    ]

    assert prune_unverified(con,retained)==(1,2)
    assert [tuple(row) for row in con.execute(
        'SELECT name,addr,path FROM recovered_function ORDER BY name,addr')
    ]==[('Bar',0x401020,'bar.c'),('Foo',0x401020,'second.c')]
    assert {row[0] for row in con.execute('SELECT src_name FROM reuse_candidate')}=={'Foo','Bar'}

    assert prune_unverified(con,[retained[1]])==(1,1)
    assert [tuple(row) for row in con.execute(
        'SELECT name,addr,path FROM recovered_function')
    ]==[('Bar',0x401020,'bar.c')]
    assert [row[0] for row in con.execute('SELECT src_name FROM reuse_candidate')]==['Bar']
