"""Read-only activity projection: historical evidence never becomes acceptance."""
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from agentdecompile_recovery.corpus.dashboard import claim_projection as cp

SHA = 'a' * 64

@pytest.fixture
def fixture(tmp_path):
    source = tmp_path / 'candidate.c'
    source.write_text('int Foo(void) { return 0; }')
    row = dict(program='target.exe', name='Foo', binary_id=7, addr=0x401000,
               path=str(source), source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
               target_sha256=SHA, size=3, machine_code='33c0c3',
               semantic_status='accepted-target-pe-export', semantic_reason='accepted_unique_nonforwarded_export')
    witness = {'schema':'agentdecompile.target-symbol-witness.v1','claimScope':'target-pe-export-name-at-va-v1',
        'target':{'sha256':SHA,'binaryId':7,'format':'pe','imageBase':0x400000},
        'claim':{'address':0x401000,'name':'Foo'},
        'witness':{'source':'embedded-pe-export-directory','forwarded':False,'nameRva':0x2100,'rva':0x1000,'va':0x401000,'name':'Foo'}}
    row['semantic_evidence'] = json.dumps(witness)
    db = tmp_path / 'corpus.sqlite'
    con = sqlite3.connect(db)
    con.execute('CREATE TABLE recovered_function (' + ','.join(cp._FIELDS) + ')')
    con.execute('INSERT INTO recovered_function VALUES (' + ','.join('?' for _ in cp._FIELDS) + ')', tuple(row[k] for k in cp._FIELDS))
    con.commit(); con.close()
    binary = {'kind':'binary','id':7,'binaryIds':[7],'slug':'target','aliasSlugs':['target'],'sha256':SHA,
              'projectBindings':[{'locator':'project','program':'target.exe'}]}
    def read(**kw):
        options = dict(db=db,slug='target',locator='project',program='target.exe',source_roots=(tmp_path,))
        options.update(kw)
        return cp.project_claims(binary, **options)
    def insert(**updates):
        record = {**row, **updates}
        with sqlite3.connect(db) as con:
            con.execute('INSERT INTO recovered_function VALUES (' + ','.join('?' for _ in cp._FIELDS) + ')',tuple(record[k] for k in cp._FIELDS))
    return source, row, db, binary, read, insert


def test_independent_historical_claims_and_mutation(fixture):
    source,row,db,binary,read,insert=fixture
    original = db.read_bytes()
    result=read(); candidate=result['candidates'][0]
    assert [c['state'] for c in candidate['claims']] == ['recorded','recorded','unavailable']
    assert all(c['accepted'] is False for c in candidate['claims'])
    assert 'comparison and compiler execution not revalidated' in candidate['claims'][0]['summary']
    assert candidate['claims'][0]['label'] == 'Recorded region bytes'
    source.write_text('int Foo(void) { return 1; }')
    candidate=read()['candidates'][0]
    assert candidate['sourceState'] == 'stale'
    assert candidate['claims'][0]['state'] == 'stale'
    assert candidate['claims'][0]['reason'] == 'source_digest_mismatch'
    assert candidate['claims'][1]['state'] == 'recorded'
    assert db.read_bytes() == original


def test_wrong_binary_same_address_and_flags_do_not_promote(fixture):
    _,row,db,binary,read,insert=fixture
    insert(target_sha256='b'*64, name='Wrong')
    insert(binary_id=8, name='OtherTarget')
    insert(name='Flags', semantic_evidence=json.dumps({'accepted':True,'verified':True}),semantic_status='accepted-target-pe-export')
    result=read()
    assert len(result['candidates']) == 3
    wrong=next(c for c in result['candidates'] if c['candidate']['name']=='Wrong')
    assert [c['state'] for c in wrong['claims']] == ['unknown','unknown','unavailable']
    assert wrong['claims'][0]['reason'] == 'candidate_target_digest_mismatch'
    flags=next(c for c in result['candidates'] if c['candidate']['name']=='Flags')
    assert flags['claims'][1]['state']=='unknown'
    assert all(not claim['accepted'] for c in result['candidates'] for claim in c['claims'])


def test_multiple_candidates_malformed_sibling_and_bound(fixture):
    _,row,db,binary,read,insert=fixture
    insert(name=b'blob-malformed'); insert(name='Second',source_sha256='b'*64)
    result=read()
    assert result['omittedMalformed']==1
    assert len(result['candidates'])==2
    assert len({c['id'] for c in result['candidates']})==2
    assert read(limit=1)['truncated'] is True
    assert read(limit=1)['limit']==1
    assert cp._bound_target(binary,'wrong','target.exe','target')=='selected_program_binding_mismatch'
    assert cp._bound_target(binary,'project','target.exe','wrong')=='selected_slug_mismatch'


def test_missing_legacy_schema_is_unavailable_without_writes(fixture,tmp_path):
    *_, read, insert=fixture
    db=tmp_path/'legacy.sqlite'
    with sqlite3.connect(db) as con: con.execute('CREATE TABLE recovered_function (addr)')
    before=db.read_bytes()
    assert read(db=db)['reason']=='recorded_candidate_schema_unavailable'
    assert before==db.read_bytes()
    missing=tmp_path/'missing.sqlite'
    assert read(db=missing)['reason']=='candidate_read_unavailable'
    assert not missing.exists()


def test_oversized_source_and_semantic_json_preserve_sibling(fixture,monkeypatch):
    _,row,db,binary,read,insert=fixture
    insert(name='HugeWitness',semantic_evidence='x'*(cp.MAX_EVIDENCE_BYTES+1))
    result=read(); assert len(result['candidates'])==2
    assert next(c for c in result['candidates'] if c['candidate']['name']=='HugeWitness')['claims'][1]['state']=='unknown'
    monkeypatch.setattr(cp,'MAX_SOURCE_BYTES',1)
    result=read(); assert result['observationLimited'] is True
    assert result['candidates'][0]['sourceReason']=='source_exceeds_observation_limit'


def test_source_drift_during_read_withdraws_current(fixture,monkeypatch):
    source,row,db,binary,read,insert=fixture
    original=cp.os.fstat; calls=0
    def drift(fd):
        nonlocal calls
        calls+=1
        if calls==2: source.write_text('changed after observation')
        return original(fd)
    monkeypatch.setattr(cp.os,'fstat',drift)
    candidate=read()['candidates'][0]
    assert candidate['sourceReason']=='source_changed_during_observation'
    assert candidate['claims'][0]['state']=='unknown'
    assert candidate['claims'][1]['state']=='recorded'


def test_server_discovered_receipts_are_references_not_candidate_proof(fixture,tmp_path,monkeypatch):
    from agentdecompile_recovery.corpus.dashboard import pages
    _,row,db,binary,read,insert=fixture
    receipt=tmp_path/'reports'/'recorded.json';receipt.parent.mkdir();receipt.write_text('{"accepted":true}')
    monkeypatch.setattr(pages,'_resolve_artifact',lambda raw:(tmp_path/raw,None))
    base=dict(targetSha256=SHA,binaryId=7,addresses=['0x00401000'],path='reports/recorded.json',href='https://evil.invalid')
    result=read(root=tmp_path,references=[{**base,'targetSha256':'b'*64},{**base,'path':'../escape'},base])
    links=result['candidates'][0]['receipts']
    assert len(links)==1 and links[0]['href']=='/dashboard/artifact?p=reports%2Frecorded.json'
    assert links[0]['candidateBound'] is False
    assert result['candidates'][0]['claims'][2]['state']=='unavailable'


def test_actual_activity_builder_attaches_exact_target_only_and_declines_ambiguity(fixture,tmp_path,monkeypatch):
    from agentdecompile_recovery.corpus.dashboard import entity_activity as activity, common, activity_receipts
    from agentdecompile_recovery.corpus.dashboard.actions import jobs
    _,row,db,binary,read,insert=fixture
    binaries=[binary]
    monkeypatch.setattr(activity,'_library',lambda:{'ok':True,'binaries':binaries})
    monkeypatch.setattr(activity,'_read_runs',lambda:[])
    monkeypatch.setattr(activity,'query_db',lambda *args,**kwargs:([],None))
    monkeypatch.setattr(activity,'live_root',lambda:tmp_path)
    monkeypatch.setattr(jobs,'list_jobs',lambda **kwargs:[])
    monkeypatch.setattr(common,'live_db',lambda:db)
    monkeypatch.setattr(common,'runtime_work_dir',lambda:tmp_path)
    monkeypatch.setattr(activity_receipts,'recorded_receipts',lambda *args:[])
    with sqlite3.connect(':memory:') as con:
        snapshot=activity._build(con,'project','target','target.exe')
        projected=[entity for entity in snapshot['entities'] if entity.get('claimProjection')]
        assert {entity['kind'] for entity in projected}=={'binary','function'}
        assert all(entity['claimProjection']['candidates'][0]['targetSha256']==SHA for entity in projected)
        binaries.append({**binary,'id':8,'binaryIds':[8],'sha256':'b'*64})
        ambiguous=activity._build(con,'project','target','target.exe')
        assert not any(entity.get('claimProjection') for entity in ambiguous['entities'])
