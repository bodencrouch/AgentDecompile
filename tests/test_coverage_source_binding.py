import hashlib
import json
from agentdecompile_recovery.corpus.coverage_evidence import bind_source, source_binding
from agentdecompile_recovery.corpus.ingest_recovered import parse_recovered, load_coverage_index


def observed_target(tmp_path):
    target = tmp_path / 'target.bin'
    data = bytes.fromhex('b001c3')
    target.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    return {'targetSnapshot': {'path': str(target), 'size': len(data), 'sha256': digest},
            'targetRegion': {'address': 4198400, 'offset': 0, 'size': len(data), 'sha256': digest}}


def test_same_filename_edit_cannot_inherit_success(tmp_path):
    recovered=tmp_path/'recovered'; program=recovered/'game';program.mkdir(parents=True)
    source=program/'F_00401000.c';source.write_bytes(b'int F_00401000(void) { return 1; }\n')
    coverage=tmp_path/'coverage';coverage.mkdir()
    row=bind_source({'function':source.stem,'byteExact':True,'size':3,'originalBytes':'b001c3',**observed_target(tmp_path)},source.read_bytes())
    (coverage/'game.jsonl').write_text(json.dumps(row)+'\n')
    assert len(parse_recovered(recovered,coverage))==1
    source.write_bytes(b'int F_00401000(void) { return 2; }\n')
    rejected=[]
    assert parse_recovered(recovered,coverage,rejected=rejected)==[]
    assert rejected[0]['reason']=='source_digest_mismatch'
    assert source.exists() # candidate preserved, historical ledger preserved
    assert json.loads((coverage/'game.jsonl').read_text())==row


def test_unbound_legacy_observation_is_not_current(tmp_path):
    root=tmp_path/'source';(root/'game').mkdir(parents=True)
    (root/'game/F.c').write_text('int F(void) { return 1; }')
    coverage=tmp_path/'coverage';coverage.mkdir()
    (coverage/'game.jsonl').write_text(json.dumps({'function':'F','byteExact':True})+'\n')
    assert parse_recovered(root,coverage)==[]


def test_latest_negative_withdraws_old_positive(tmp_path):
    rows=[{'function':'F','byteExact':True},{'function':'F','byteExact':False}]
    (tmp_path/'game.jsonl').write_text('\n'.join(map(json.dumps,rows)))
    assert load_coverage_index(tmp_path)=={}


def test_hash_binding_does_not_upgrade_scientific_verdict():
    row=bind_source({'byteExact':False,'provenance_verified':False},b'candidate')
    assert source_binding(row,b'candidate')['current']
    assert row['byteExact'] is False and row['provenance_verified'] is False
    assert not source_binding(row,b'edited')['current']
    for digest in (None,True,'x'*64,{},'A'*64):
        assert not source_binding({'sourceSha256':digest},b'candidate')['current']
