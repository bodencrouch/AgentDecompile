import hashlib
import json

from agentdecompile_recovery.corpus import seed_validation as seeds


def test_pinned_whole_image_and_region_provenance(tmp_path):
    image = tmp_path/'image'
    image.write_bytes(b'abcdefgh')
    calls = []
    def mapper(raw):
        calls.append(raw)
        return lambda address: address - 0x1000, 'fixture'
    cache = {}
    region, evidence = seeds.target_observation('image','1001',3,cache,raw_dir=tmp_path,mapper_for=mapper)
    assert region == b'bcd'
    assert evidence['targetSnapshot']['sha256'] == hashlib.sha256(b'abcdefgh').hexdigest()
    assert evidence['targetRegion'] == {'address':4097,'offset':1,'size':3,'sha256':hashlib.sha256(b'bcd').hexdigest()}
    image.write_bytes(b'CHANGED!')
    assert seeds.destination_bytes('image','1001',3,cache,raw_dir=tmp_path,mapper_for=mapper) == b'bcd'
    assert len(calls) == 1
    assert evidence['targetSnapshot']['currentFileVerified'] is False
    assert evidence['targetSnapshot']['scope'] == 'captured-image-snapshot'
    json.dumps(evidence)
    evidence['targetSnapshot']['sha256'] = 'caller-mutated'
    assert seeds.target_observation('image','1001',3,cache,raw_dir=tmp_path,mapper_for=mapper)[1]['targetSnapshot']['sha256'] != 'caller-mutated'


def test_reuse_requires_whole_snapshot_even_if_region_unchanged(tmp_path):
    image = tmp_path/'image'
    image.write_bytes(b'SAMEold')
    mapper = lambda raw: (lambda address: address, 'fixture')
    _, first = seeds.target_observation('image','0',4,{},raw_dir=tmp_path,mapper_for=mapper)
    row = {'seed':'seed','source_path':'source','destination_bytes':b'SAME'.hex(),
           'sourceSha256':'a'*64,'compile_status':'byte_exact','comparisonPolicy':'raw-region-v1','compileBasis':{'key':'d'*64,'closureComplete':True}, **first}
    assert seeds.can_reuse_compile_result(row,dict(row))
    image.write_bytes(b'SAMEnew')
    _, second = seeds.target_observation('image','0',4,{},raw_dir=tmp_path,mapper_for=mapper)
    assert first['targetRegion'] == second['targetRegion']
    assert not seeds.can_reuse_compile_result({**row,**second},row)
    assert not seeds.can_reuse_compile_result(row,{key:value for key,value in row.items() if key!='targetSnapshot'})


def test_snapshot_hash_computed_once_per_capture(tmp_path, monkeypatch):
    raw = b'unique whole image bytes'
    (tmp_path/'image').write_bytes(raw)
    original = seeds.hashlib.sha256
    inputs = []
    def digest(value):
        inputs.append(value)
        return original(value)
    monkeypatch.setattr(seeds.hashlib,'sha256',digest)
    mapper = lambda raw: (lambda address: address, 'fixture')
    cache = {}
    for address in ('0','1','2'):
        seeds.target_observation('image',address,2,cache,raw_dir=tmp_path,mapper_for=mapper)
    assert inputs.count(raw) == 1
