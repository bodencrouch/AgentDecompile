from pathlib import Path
from types import SimpleNamespace
import pytest
from agentdecompile_recovery.corpus import seed_validation as sv


@pytest.mark.parametrize('compiled,expected,normalized',[(b'AB','byte_exact',True),(b'ABextra','not_byte_exact',False),(b'AZ','not_byte_exact',True)])
def test_seed_exact_means_complete_raw_region(tmp_path,monkeypatch,compiled,expected,normalized):
    seed=sv.Seed('donor.c','/target','401000','f',2,b'AB','f','int f(void){return 0;}')
    monkeypatch.setattr(sv,'source_context',lambda *a:'')
    monkeypatch.setattr(sv,'source_target_artifacts',lambda *a:(None,[{'immOffset':1,'immSize':1}]))
    def compile(argv,**kwargs):
        Path(argv[2]).write_bytes(b'object')
        return SimpleNamespace(returncode=0,stdout='',stderr='')
    monkeypatch.setattr(sv.subprocess,'run',compile)
    result=sv.compile_seed('target',seed,b'AB',compiler=tmp_path/'compiler',evidence_root=tmp_path,
                           coff_functions=lambda *a,**kw:{'f':compiled})
    assert result['compile_status']==expected
    assert result['relocation_normalized_match'] is normalized
    assert result['comparisonPolicy']=='raw-region-v1'


def test_old_comparator_result_cannot_be_reused():
    row={'compile_status':'byte_exact','sourceSha256':'a'*64,'targetSnapshot':{'sha256':'b'*64},
         'targetRegion':{'address':0,'offset':0,'size':1,'sha256':'c'*64}}
    assert not sv.can_reuse_compile_result(row,row)
