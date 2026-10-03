"""Injected barrier ordering/recovery checks; not physical power-loss proof."""
import json
import os
from pathlib import Path
import pytest
from agentdecompile_recovery.corpus import cross_place_checkpoint as cp


def test_staged_names_are_synced_before_publication_intent(tmp_path, monkeypatch):
    out=tmp_path/'output';out.mkdir();source=out/'donor.c';receipt=out/'receipt.json'
    index=cp.PublicationIndex(out);events=[];real_sync=os.fsync;real_save=cp.save
    def sync(fd):
        target=Path(os.readlink(f'/proc/self/fd/{fd}'))
        if target.is_dir() and target.name.startswith('publication-'):
            events.append(('stage-barrier',tuple(sorted(p.name for p in target.iterdir()))))
        return real_sync(fd)
    def save(path,value):
        if Path(path)==index.meta and value.get('pending'):
            assert ('stage-barrier',('0','1')) in events
            events.append(('intent',None))
        return real_save(path,value)
    monkeypatch.setattr(os,'fsync',sync);monkeypatch.setattr(cp,'save',save)
    with index.locked():index.publish([(source,b'new source'),(receipt,b'{}')],[(source,receipt)])
    assert events.index(('stage-barrier',('0','1'))) < events.index(('intent',None))
    assert index.state()['pending'] is None and index.state()['sequence']==1


def test_post_replace_barrier_failure_retries_even_with_matching_new_bytes(tmp_path, monkeypatch):
    out=tmp_path/'output';out.mkdir();source=out/'donor.c';receipt=out/'receipt.json'
    source.write_bytes(b'old');receipt.write_bytes(b'old receipt')
    index=cp.PublicationIndex(out);real_replace=os.replace;real_sync=os.fsync
    replaced=[];barriers=[];fail=[True]
    def replace(before,after):
        result=real_replace(before,after)
        if Path(after)==source:replaced.append(str(after))
        return result
    def sync(fd):
        target=Path(os.readlink(f'/proc/self/fd/{fd}'))
        if target==out and replaced:
            barriers.append('attempt')
            if fail[0]:fail[0]=False;raise OSError('injected rename directory barrier')
            barriers.append('success')
        return real_sync(fd)
    monkeypatch.setattr(os,'replace',replace);monkeypatch.setattr(os,'fsync',sync)
    with pytest.raises(OSError,match='injected rename'):
        with index.locked():index.publish([(source,b'new'),(receipt,b'new receipt')],[(source,receipt)])
    assert source.read_bytes()==b'new' and receipt.read_bytes()==b'old receipt'
    assert index.state()['pending'] is not None and index.state()['sequence']==0
    with cp.PublicationIndex(out).locked():pass
    assert len(replaced)==1  # Recovery's fresh barrier cannot depend on another rename.
    assert barriers[:3]==['attempt','attempt','success']
    assert receipt.read_bytes()==b'new receipt'
    assert index.state()['pending'] is None and index.state()['sequence']==1
    event=json.loads(index.event_path(1).read_text())
    assert event['binding']['source']['sha256']==cp.hashlib.sha256(b'new').hexdigest()


def test_external_inventory_requires_exact_selected_root(tmp_path):
    out=tmp_path/'output';out.mkdir();source=tmp_path/'external';source.mkdir()
    (source/'one.c').write_text('source');receipt=tmp_path/'receipt.json';receipt.write_text('{}')
    other=tmp_path/'other';other.mkdir()
    index=cp.PublicationIndex(out)
    state=index.bootstrap(source,receipt)
    with index.locked():
        with pytest.raises(ValueError,match='import_manifest_scope'):
            index.import_manifest(state['manifest'],state['sha256'],expected_source=other)
        assert index.state()['sequence']==0
        assert index.import_manifest(state['manifest'],state['sha256'],expected_source=source)==(1,1)
        assert index.state()['sequence']==1


def test_actual_4097_names_complete_capture_after_initial_budget(tmp_path):
    out=tmp_path/'output';source=out/'donor';source.mkdir(parents=True)
    receipt=out/'receipt.json';receipt.write_text('{}')
    expected={f'f{i:04d}.c' for i in range(4097)}
    for name in expected:(source/name).write_bytes(b'source')
    index=cp.PublicationIndex(out)
    first=index.bootstrap(source,receipt)
    assert first['complete'] is False and first['budget']==8192
    second=cp.PublicationIndex(out).bootstrap(source,receipt)
    assert second['complete'] is True
    manifest=cp.read(second['manifest'])
    assert manifest['count']==4097 and len(manifest['chunks'])==33
    actual=set()
    for chunk in manifest['chunks']:
        raw=Path(chunk['path']).read_bytes()
        assert cp.hashlib.sha256(raw).hexdigest()==chunk['sha256']
        actual.update(json.loads(raw)['names'])
    assert actual==expected


def test_producer_can_publish_while_captured_chunks_persist(tmp_path, monkeypatch):
    import threading
    out=tmp_path/'output';source=out/'donor';source.mkdir(parents=True)
    (source/'old.c').write_text('old');receipt=out/'receipt.json';receipt.write_text('{}')
    entered=threading.Event();release=threading.Event();outcomes=[];real_save=cp.save
    def save(path,value):
        if Path(path).name.startswith('members-'):
            entered.set()
            if not release.wait(5):raise TimeoutError('fixture producer release')
        return real_save(path,value)
    monkeypatch.setattr(cp,'save',save)
    def capture():
        try:outcomes.append(cp.PublicationIndex(out).bootstrap(source,receipt))
        except BaseException as exc:outcomes.append(exc)
    thread=threading.Thread(target=capture);thread.start()
    try:
        assert entered.wait(5)
        producer=cp.PublicationIndex(out)
        with producer.locked():
            producer.publish([(source/'new.c',b'new')],[(source/'new.c',receipt)])
        assert producer.state()['sequence']==1
    finally:
        release.set();thread.join(10)
    assert not thread.is_alive() and len(outcomes)==1
    assert isinstance(outcomes[0],dict) and outcomes[0]['complete']
    captured=cp.read(outcomes[0]['manifest'])
    assert captured['count']==1  # Later publication has its own committed event.
