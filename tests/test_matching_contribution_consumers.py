import json
import sqlite3

from agentdecompile_recovery.corpus import matching_status, finish_binary
from agentdecompile_recovery.corpus.dashboard import byte_parity
from test_source_contribution import pe_fixture, compiled_pair
from agentdecompile_recovery.corpus import source_contribution as sc


def test_status_legacy_floor_and_ok_never_count_as_contribution(tmp_path):
    target=tmp_path/'target.exe';target.write_bytes(pe_fixture()[0])
    db=tmp_path/'corpus.sqlite'
    with sqlite3.connect(db) as con:
        con.execute('CREATE TABLE func(binary_id INTEGER,addr INTEGER,size INTEGER)')
        con.execute('INSERT INTO func VALUES(1,?,6)',(0x401000,))
    (tmp_path/'A_00401000.c').write_text('int A(void){return 7;}')
    receipts=tmp_path/'receipts.json';receipts.write_text(json.dumps({'results':[{'addr':'0x401000','ok':True}]}))
    floor=tmp_path/'floor.json';floor.write_text('[4198400]')
    report=tmp_path/'report.json'
    assert matching_status.main(['--target',str(target),'--db',str(db),'--binary-id','1',
        '--src-dir',str(tmp_path),'--receipts',str(receipts),'--byte-exact-floor',str(floor),
        '--out-report',str(report)]) == 0
    state=json.loads(report.read_text())
    assert state['placedCompiledRegions'] == state['rawLocalObservedC'] == state['counts']['byte_exact'] == 0
    assert state['historicalFloorDiagnostic'] == 1
    assert state['wholeFileByteIdentical'] is None
    assert state['variants']['byte_accurate']['exact_placement_hash_equal'] is None


def test_dashboard_rejects_legacy_totals_and_terminal_booleans(tmp_path,monkeypatch):
    target=tmp_path/'target.exe';target.write_bytes(pe_fixture()[0])
    report=tmp_path/'report.json';report.write_text(json.dumps({'totalFunctions':100,'byteExactRecoveredC':70,'rawLocalObservedC':3}))
    variants=tmp_path/'variants.json';variants.write_text(json.dumps({'code_total':100,'variants':{'byte_accurate':{'c':90}}}))
    receipt=tmp_path/'terminal.json';receipt.write_text(json.dumps({'schema':'agentdecompile.full-image-compiler-objdiff-receipt.v1',
        'verified':True,'compilerProducedWholeImage':True,'wholeFileByteIdentical':True,'target':sc.fingerprint(target)}))
    monkeypatch.setenv(byte_parity._REPORT_ENV,str(report));monkeypatch.setenv(byte_parity._VARIANTS_ENV,str(variants))
    monkeypatch.setenv(byte_parity._FULL_IMAGE_RECEIPT_ENV,str(receipt))
    monkeypatch.setattr(byte_parity,'_TARGET',str(target));monkeypatch.setattr(byte_parity,'_REBUILT',str(target))
    monkeypatch.setattr(byte_parity,'_text_permuter_closed_count',lambda:20)
    state=byte_parity.byte_parity_state()
    assert state['placedCompiledRegions'] == state['byteExactRecoveredC'] == 0
    assert state['rawLocalObservedC'] == 3
    assert state['compilerProducedWholeImage'] is False
    assert state['variants']['byteAccurate']['c'] == 0
    assert finish_binary.contribution_state()['placedCompiledRegions'] == 0


def test_explicit_live_observation_reaches_finish_and_dashboard(tmp_path,monkeypatch):
    target,observations=compiled_pair(tmp_path)
    output=tmp_path/'out.exe';image=sc.reconstruct(target=target,output=output,observations=observations)
    assert finish_binary.contribution_state(image,target_path=target)['placedCompiledRegions'] == 2
    monkeypatch.setattr(byte_parity,'_TARGET',str(target));monkeypatch.setattr(byte_parity,'_REBUILT',str(output))
    state=byte_parity.byte_parity_state(reconstruction_observation=image)
    assert state['placedCompiledRegions'] == 2
    assert state['placedCompiledBytes'] == 12
    assert state['byteExactRecoveredC'] == state['qualifiedCorpusFunctions'] == 0
    assert state['wholeFileByteIdentical'] is True
    assert state['compilerProducedWholeImage'] is False


def test_selected_corpus_requires_exact_producer_row_and_size(tmp_path):
    target,observations=compiled_pair(tmp_path)
    image=sc.reconstruct(target=target,output=tmp_path/'out.exe',observations=observations)
    db=tmp_path/'different.sqlite'
    with sqlite3.connect(db) as con:
        con.execute('CREATE TABLE func(binary_id INTEGER,addr INTEGER,size INTEGER)')
        con.execute('INSERT INTO func VALUES(9,?,32)',(0x401000,))
    result=sc.evaluate_reconstruction(image,db=db,binary_id=9)
    assert result['placedCompiledRegions']==0
    report=tmp_path/'report.json'
    assert matching_status.main(['--target',str(target),'--db',str(db),'--binary-id','9',
        '--src-dir',str(tmp_path),'--out-report',str(report)],reconstruction_observation=image)==0
    state=json.loads(report.read_text())
    assert state['counts']['byte_exact']==state['placedCompiledRegions']==state['placedCompiledBytes']==0
    assert state['variants']['byte_accurate']['c']==0


def test_qualified_dashboard_and_watch_use_selected_corpus_denominator(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from agentdecompile_recovery import corpus
    from agentdecompile_recovery.corpus import matching_watch
    db=tmp_path/'corpus.sqlite'
    with sqlite3.connect(db) as con:
        con.execute('CREATE TABLE func(binary_id INTEGER,addr INTEGER,size INTEGER)')
        con.executemany('INSERT INTO func VALUES(1,?,?)',[(0x401000,6),(0x401010,6),(0x401020,1),(0x401021,1)])
    target,observations=compiled_pair(tmp_path,db=db,binary_id=1)
    output=tmp_path/'out.exe';image=sc.reconstruct(target=target,output=output,observations=observations)
    monkeypatch.setattr(byte_parity,'_TARGET',str(target));monkeypatch.setattr(byte_parity,'_REBUILT',str(output))
    state=byte_parity.byte_parity_state(reconstruction_observation=image,db=db,binary_id=1)
    assert state['placedCompiledRegions']==state['qualifiedCorpusFunctions']==2
    assert state['totalFunctions']==4 and state['coveragePct']==50
    progress=[]
    monkeypatch.setattr(corpus,'discord_notify',SimpleNamespace(announce_progress=lambda **kwargs:progress.append(kwargs),
        load_settings=lambda:{'last_corpus_report':float('inf')}),raising=False)
    monkeypatch.setattr(corpus,'corpus_report',SimpleNamespace(),raising=False)
    args=SimpleNamespace(target=target,db=db,binary_id=1,src_dir=tmp_path,receipts=None,func_bytes=None,
        out_exe=output,out_manifest=None,out_report=None,byte_exact_floor=None,reconstruction_observation=image)
    stats=matching_watch.one_pass(args)
    assert stats['functions']==4 and stats['placedCompiledRegions']==2
    assert progress==[{'program':tmp_path.name,'byte_exact':2,'total':4,'byte_identical':False,'min_delta':1}]
