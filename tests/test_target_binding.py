import copy
import hashlib
from pathlib import Path

import pytest

from agentdecompile_recovery.corpus.coverage_evidence import target_binding


def evidence(path, raw=b'abcdef'):
    path.write_bytes(raw)
    return {'targetSnapshot':{'path':str(path),'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
                              'currentFileVerified':False},
            'targetRegion':{'address':4096,'offset':1,'size':3,'sha256':hashlib.sha256(raw[1:4]).hexdigest()}}


def test_exact_binding_expected_target_and_no_metadata_mutation(tmp_path):
    path = tmp_path/'image'
    row = evidence(path)
    before = copy.deepcopy(row)
    result = target_binding(row, expected_path=path, expected_address=4096)
    assert result['current'] and not result['semanticIdentityVerified']
    assert row == before
    assert not target_binding(row,expected_path=tmp_path/'other')['current']
    assert not target_binding(row,expected_address=4097)['current']


def test_whole_image_change_outside_region_rejected(tmp_path):
    path = tmp_path/'image'
    row = evidence(path)
    path.write_bytes(b'abcdeX')
    assert target_binding(row)['reason'] == 'target_snapshot_mismatch'


def test_cache_pins_one_read_and_fresh_invocation_rechecks(tmp_path, monkeypatch):
    path = tmp_path/'image'
    row = evidence(path)
    original = Path.read_bytes
    calls = []
    def read(self):
        calls.append(self)
        return original(self)
    monkeypatch.setattr(Path,'read_bytes',read)
    cache = {}
    assert target_binding(row,cache=cache)['current']
    path.write_bytes(b'new image')
    assert target_binding(row,cache=cache)['current']
    assert len(calls) == 1
    assert not target_binding(row,cache={})['current']


@pytest.mark.parametrize('group,key,value', [
    ('targetSnapshot','size',True),('targetSnapshot','size',0),('targetSnapshot','sha256','bad'),
    ('targetSnapshot','path',None),('targetRegion','address',True),('targetRegion','address',-1),
    ('targetRegion','offset',-1),('targetRegion','offset',1.0),('targetRegion','size',0),
    ('targetRegion','size',99),('targetRegion','sha256','f'*64),
])
def test_malformed_or_mismatching_metadata_refused(tmp_path,group,key,value):
    row = evidence(tmp_path/'image')
    row[group][key] = value
    assert not target_binding(row)['current']


def test_missing_and_unreadable_target_refused(tmp_path):
    assert not target_binding(None)['current']
    assert not target_binding({})['current']
    row = evidence(tmp_path/'image')
    (tmp_path/'image').unlink()
    assert target_binding(row)['reason'] == 'target_unreadable'
