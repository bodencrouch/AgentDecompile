import pytest
from agentdecompile_recovery.corpus.seed_validation import destination_bytes


def mapper(raw):
    return (lambda address: address), 'fixture'


def test_same_slug_different_root_never_shares_snapshot(tmp_path):
    a=tmp_path/'a';b=tmp_path/'b';a.mkdir();b.mkdir()
    (a/'image').write_bytes(b'ABCD');(b/'image').write_bytes(b'WXYZ');cache={}
    assert destination_bytes('image','1',2,cache,raw_dir=a,mapper_for=mapper)==b'BC'
    assert destination_bytes('image','1',2,cache,raw_dir=b,mapper_for=mapper)==b'XY'
    assert len(cache)==2


def test_mapper_provider_is_part_of_snapshot_identity(tmp_path):
    (tmp_path/'image').write_bytes(b'ABCD');cache={}
    other=lambda raw: (lambda address: address+1, 'fixture')
    assert destination_bytes('image','0',1,cache,raw_dir=tmp_path,mapper_for=mapper)==b'A'
    assert destination_bytes('image','0',1,cache,raw_dir=tmp_path,mapper_for=other)==b'B'


@pytest.mark.parametrize('offset,size',[(-1,1),(True,1),(None,1),(0,-1),(0,0),(0,True),(3,2)])
def test_invalid_regions_cannot_be_successful_python_slices(tmp_path,offset,size):
    (tmp_path/'image').write_bytes(b'ABCD')
    with pytest.raises(ValueError):
        destination_bytes('image','0',size,{},raw_dir=tmp_path,mapper_for=lambda raw:(lambda address:offset,'fixture'))


def test_snapshot_reuse_is_explicit_and_new_cache_observes_changed_image(tmp_path):
    image=tmp_path/'image';image.write_bytes(b'ABCD');cache={}
    assert destination_bytes('image','0',1,cache,raw_dir=tmp_path,mapper_for=mapper)==b'A'
    image.write_bytes(b'WXYZ')
    assert destination_bytes('image','0',1,cache,raw_dir=tmp_path,mapper_for=mapper)==b'A'
    assert destination_bytes('image','0',1,{},raw_dir=tmp_path,mapper_for=mapper)==b'W'
