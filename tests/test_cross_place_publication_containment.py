"""Journal write-boundary tests; all outside files are fixture-owned sentinels."""
from pathlib import Path
import pytest
from agentdecompile_recovery.corpus import cross_place_checkpoint as cp
from agentdecompile_recovery.corpus import cross_place_admission as gate


@pytest.mark.parametrize('kind',['traversal','symlink','journal'])
def test_publish_refuses_escape_before_staging_or_intent(tmp_path,kind):
    out=tmp_path/'out';out.mkdir();outside=tmp_path/'outside';outside.mkdir()
    sentinel=outside/'keep.c';sentinel.write_bytes(b'original')
    index=cp.PublicationIndex(out)
    if kind=='traversal':target=out/'..'/'outside'/'keep.c'
    elif kind=='symlink':
        (out/'alias').symlink_to(outside,target_is_directory=True);target=out/'alias'/'keep.c'
    else:target=index.root/'unrelated.json'
    with index.locked():
        with pytest.raises(ValueError,match='publication_'):
            index.publish([(target,b'changed')],[])
        assert index.state()['sequence']==0 and index.state()['pending'] is None
    assert sentinel.read_bytes()==b'original'
    assert not list(index.root.glob('publication-*'))
    assert not (index.root/'unrelated.json').exists()


@pytest.mark.parametrize('escape',['destination','staged'])
def test_retained_publication_escape_never_writes_outside_or_source(tmp_path,escape):
    out=tmp_path/'out';out.mkdir();source=out/'source.c';source.write_bytes(b'old')
    outside=tmp_path/'outside.c';outside.write_bytes(b'outside')
    index=cp.PublicationIndex(out)
    with index.locked():pass
    stage=cp.directory(index.root/'publication-fixture');staged=stage/'0';staged.write_bytes(b'new')
    target=out/'..'/'outside.c' if escape=='destination' else source
    before=gate.snapshot(outside if escape=='destination' else source)
    after={'path':str(target),'sha256':cp.hashlib.sha256(b'new').hexdigest(),'size':3}
    entry={'path':str(target),'before':before,'after':after,
           'staged':str(out/'..'/'outside.c') if escape=='staged' else str(staged)}
    row=index.state();row['pending']={'files':[entry],'bindings':[]};cp.save(index.meta,row)
    retained=index.meta.read_bytes()
    with pytest.raises(ValueError,match='publication_'):
        with cp.PublicationIndex(out).locked():pass
    assert outside.read_bytes()==b'outside' and source.read_bytes()==b'old'
    assert index.meta.read_bytes()==retained


@pytest.mark.parametrize('escape',['traversal','wrong-key'])
def test_retained_latest_path_is_checked_before_event_commit(tmp_path,escape):
    out=tmp_path/'out';out.mkdir();source=out/'one.c';source.write_text('one')
    receipt=out/'receipt.json';receipt.write_text('{}')
    outside=tmp_path/'outside.json';outside.write_text('original')
    index=cp.PublicationIndex(out)
    with index.locked():pass
    latest=(index.root/'latest'/'..'/'..'/'..'/'outside.json' if escape=='traversal'
            else index.root/'latest'/'aa'/('a'*64+'.json'))
    row=index.state();row['appendPending']={'event':{'schema':cp.SCHEMA,'sequence':1,
        'binding':{'source':gate.snapshot(source),'receipt':gate.snapshot(receipt)}},'latest':str(latest)}
    cp.save(index.meta,row);retained=index.meta.read_bytes()
    with pytest.raises(ValueError,match='publication_|append_intent_scope'):
        with cp.PublicationIndex(out).locked():pass
    assert outside.read_text()=='original' and index.meta.read_bytes()==retained
    assert not index.event_path(1).exists()


def test_parent_traversal_root_refused_before_creation(tmp_path):
    root=tmp_path/'out'/'..'/'other'
    with pytest.raises(ValueError,match='publication_parent_traversal'):cp.PublicationIndex(root)
    assert not (tmp_path/'out').exists() and not (tmp_path/'other').exists()


@pytest.mark.parametrize('escape',['destination','staged'])
def test_later_malformed_entry_is_refused_before_first_destination_changes(tmp_path,escape):
    out=tmp_path/'out';out.mkdir();first=out/'first.c';first.write_bytes(b'old first')
    second=out/'second.c';second.write_bytes(b'old second');outside=tmp_path/'outside';outside.write_bytes(b'outside')
    index=cp.PublicationIndex(out)
    with index.locked():pass
    stage=cp.directory(index.root/'publication-fixture')
    entries=[]
    for number,target in enumerate((first,second)):
        staged=stage/str(number);staged.write_bytes(b'new')
        entries.append({'path':str(target),'before':gate.snapshot(target),
            'after':{'path':str(target),'sha256':cp.hashlib.sha256(b'new').hexdigest(),'size':3},'staged':str(staged)})
    entries[1]['path' if escape=='destination' else 'staged']=str(out/'..'/'outside')
    row=index.state();row['pending']={'files':entries,'bindings':[]};cp.save(index.meta,row)
    with pytest.raises(ValueError,match='publication_'):
        with cp.PublicationIndex(out).locked():pass
    assert first.read_bytes()==b'old first' and second.read_bytes()==b'old second'
    assert outside.read_bytes()==b'outside' and index.state()['sequence']==0


@pytest.mark.parametrize('sequence',[0,-1,True])
def test_retained_append_sequence_must_be_positive_integer(tmp_path,sequence):
    out=tmp_path/'out';out.mkdir();source=out/'one.c';source.write_text('one');receipt=out/'receipt.json';receipt.write_text('{}')
    index=cp.PublicationIndex(out)
    with index.locked():pass
    name=cp.digest({'source':str(source),'receipt':str(receipt)})
    row=index.state();row['appendPending']={'event':{'schema':cp.SCHEMA,'sequence':sequence,
        'binding':{'source':gate.snapshot(source),'receipt':gate.snapshot(receipt)}},
        'latest':str(index.root/'latest'/name[:2]/(name+'.json'))}
    cp.save(index.meta,row);before=index.meta.read_bytes()
    with pytest.raises(ValueError,match='append_intent_sequence'):
        with cp.PublicationIndex(out).locked():pass
    assert index.meta.read_bytes()==before and not index.event_path(0).exists()
