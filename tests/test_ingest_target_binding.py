import hashlib
import json

import pytest

from agentdecompile_recovery.corpus.coverage_evidence import bind_source
from agentdecompile_recovery.corpus.ingest_recovered import parse_recovered


def target_metadata(path, data=b'\x33\xc0\xc3', address=0x401000):
    path.write_bytes(b'prefix' + data + b'suffix')
    return {'targetSnapshot': {'path':str(path), 'size':path.stat().st_size,
                              'sha256':hashlib.sha256(path.read_bytes()).hexdigest()},
            'targetRegion': {'address':address, 'offset':6, 'size':len(data),
                             'sha256':hashlib.sha256(data).hexdigest()}}


def prepared(tmp_path, name='fn_00401000', header=''):
    recovered=tmp_path/'recovered';program=recovered/'game';program.mkdir(parents=True)
    source=program/(name+'.c');source.write_text(header+'int fn(void) {return 0;}')
    coverage=tmp_path/'coverage';coverage.mkdir()
    row=bind_source({'function':name,'byteExact':True,'size':3,'originalBytes':'33c0c3',
                     **target_metadata(tmp_path/'target.bin')},source.read_bytes())
    ledger=coverage/'game.jsonl';ledger.write_text(json.dumps(row)+'\n')
    return recovered,coverage,source,row,ledger


def test_live_target_and_source_checks_admit_exact_observation(tmp_path):
    recovered,coverage,source,row,ledger=prepared(tmp_path)
    parsed=parse_recovered(recovered,coverage)
    assert len(parsed)==1 and parsed[0]['addr']==0x401000
    assert parsed[0]['machine_code']=='33c0c3' and parsed[0]['size']==3


@pytest.mark.parametrize('change',['missing','whole_changed','region_changed','address','code','size','ledger_address'])
def test_target_changes_rejected_and_source_preserved(tmp_path,change):
    recovered,coverage,source,row,ledger=prepared(tmp_path)
    if change=='missing':row.pop('targetSnapshot')
    elif change=='whole_changed':(tmp_path/'target.bin').write_bytes(b'changed')
    elif change=='region_changed':row['targetRegion']['sha256']='0'*64
    elif change=='address':row['targetRegion']['address']+=1
    elif change=='code':row['originalBytes']='909090'
    elif change=='size':row['size']=1
    else:row['address']='00402000'
    ledger.write_text(json.dumps(row)+'\n');rejected=[]
    assert parse_recovered(recovered,coverage,rejected=rejected)==[]
    assert source.exists() and rejected[0]['binding']=='target'


def test_anonymous_name_uses_checked_region_address(tmp_path):
    recovered,coverage,*_=prepared(tmp_path,name='anonymous')
    assert parse_recovered(recovered,coverage)[0]['addr']==0x401000


def test_header_cannot_override_checked_comparison_metadata(tmp_path):
    recovered,coverage,*_=prepared(tmp_path,header='/* size: 99 bytes; original machine code: 9090 */\n')
    rejected=[]
    assert parse_recovered(recovered,coverage,rejected=rejected)==[]
    assert rejected[0]['reason']=='header_target_size_mismatch'


def test_preloaded_coverage_index_pins_observation_and_empty_is_not_absent(tmp_path):
    from agentdecompile_recovery.corpus.ingest_recovered import load_coverage_index
    recovered, coverage, source, row, ledger = prepared(tmp_path)
    snapshot = load_coverage_index(coverage)
    ledger.write_text(json.dumps({'function': row['function'], 'byteExact': False}) + '\n')
    parsed = parse_recovered(recovered, coverage, coverage_index=snapshot)
    assert len(parsed) == 1 and parsed[0]['source_sha256'] == row['sourceSha256']
    assert parse_recovered(recovered, coverage) == []
    ledger.write_text(json.dumps(row) + '\n')
    rejected = []
    assert parse_recovered(recovered, coverage, coverage_index={}, rejected=rejected) == []
    assert rejected[0]['binding'] == 'source'
    assert len(parse_recovered(recovered, coverage)) == 1
