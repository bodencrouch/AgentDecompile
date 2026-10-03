"""Synthetic donor/recipient fixtures; no live corpus, Wine, Ghidra or services."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import struct
import sys
import threading

import pytest

from agentdecompile_recovery.corpus import cross_place as cp, cross_place_admission as gate
from agentdecompile_recovery.corpus import ghidra_bulk as bulk, store

# The ``fixture`` fixture below compiles through the exact clang-22 -cc1
# frontend ABI at a pinned absolute path (matching native_verify_contract's
# own administrator-owned compiler contract). It is not resolved via PATH on
# purpose, so an environment without that exact package installed at that
# path cannot run these tests offline. Only tests that request ``fixture``
# need this -- skip inside the fixture itself rather than module-wide so the
# handful of tests here that don't touch a real compiler keep running.
_CLANG22 = Path("/usr/bin/clang-22")


def pe(value=7, *, plus=False, offset=0):
    raw = bytearray(0x240);raw[:2] = b'MZ'
    struct.pack_into('<I', raw, 0x3c, 0x80);raw[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<HH', raw, 0x84, 0x8664 if plus else 0x14c, 1)
    size = 0xf0 if plus else 0xe0;struct.pack_into('<H', raw, 0x94, size)
    struct.pack_into('<H', raw, 0x98, 0x20b if plus else 0x10b)
    base = 0x140000000 if plus else 0x400000
    struct.pack_into('<Q' if plus else '<I', raw, 0x98 + (24 if plus else 28), base)
    section = 0x98 + size;raw[section:section+8] = b'.text\0\0\0'
    struct.pack_into('<IIII', raw, section+8, 0x40, 0x1000, 0x40, 0x200)
    struct.pack_into('<I', raw, section+36, 0x60000020)
    raw[0x200+offset:0x206+offset] = b'\xb8' + value.to_bytes(4, 'little', signed=True) + b'\xc3'
    return bytes(raw), base+0x1000+offset


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    if not _CLANG22.exists():
        pytest.skip("requires the pinned /usr/bin/clang-22 compiler (-cc1 ABI-matched frontend); not installed in this environment")
    monkeypatch.setattr(gate,'_CACHE',{})
    monkeypatch.setattr(gate,'_ATTEMPTS',{})
    root = tmp_path;out = root/'output';src = out/'donor';src.mkdir(parents=True)
    images = root/'raw';images.mkdir();db = root/'corpus.sqlite'
    con = store.connect(db)
    con.execute("INSERT INTO logical_function(id,best_name) VALUES(1,'leaf')")
    addresses = []
    for bid,slug,offset in [(1,'donor.exe',0),(2,'recipient.exe',16)]:
        raw,addr = pe(offset=offset);addresses.append(addr);(images/slug).write_bytes(raw)
        con.execute('INSERT INTO binary(id,repo_path,slug,content_sha256,arch,bits,format) VALUES(?,?,?,?,?,?,?)',
            (bid,'/'+slug,slug,gate.digest(raw),'x86',32,'pe'))
        con.execute('INSERT INTO func(binary_id,addr,name,size,is_thunk,return_type,param_count,param_types,calling_convention) VALUES(?,?,?,?,?,?,?,?,?)',
            (bid,addr,'leaf',6,0,'int',0,'[]','__cdecl'))
        con.execute('INSERT INTO identity(logical_id,binary_id,addr,confidence,method,evidence) VALUES(?,?,?,?,?,?)',
            (1,bid,addr,1.0,'fixture-candidate-link',json.dumps({'dependencies':[]})))
    con.commit()
    source = src/'leaf.c';source.write_text(f'/* address: 0x{addresses[0]:x} */\nint leaf(void) {{ return 7; }}\n')
    compiler = root/'compile.sh'
    compiler.write_text('exec /usr/bin/clang-22 -cc1 -triple i686-pc-windows-msvc -emit-obj -O1 -ffreestanding -fno-builtin -o "$2" -x c "$1"\n')
    monkeypatch.setattr(bulk,'COMPILE',compiler);monkeypatch.setattr(bulk,'OUT_DIR',out)
    monkeypatch.setattr(bulk,'_CROSS_CONFIG',{'db':str(db),'bid':1,'raw_dir':str(images)})
    obj = root/'producer.obj'
    # Actual compile producer captures generation before compiling these exact bytes.
    ok,error = bulk._compile_text(source,obj,'leaf','',source.read_text())
    assert ok,error
    binding = bulk._COMPILE_BINDINGS[str(source)]
    row = {'ok':True,'addr':hex(addresses[0]),**binding}
    receipt = bulk.write_compile_receipt(out,'donor',[f'{addresses[0]:x}'],results=[row])
    yield {'root':root,'out':out,'src':src,'source':source,'db':db,'con':con,
           'images':images,'addresses':addresses,'row':row,'receipt':receipt,'binding':binding}
    con.close()


def distribute(f, **kw):
    return cp.place_tree(f['src'],1,f['out'],f['con'],raw_dir=f['images'],**kw)


def manifests(f, state='qualified-candidates'):
    return sorted((f['out']/gate.AREA/state).glob('*/manifest.json'))


def test_actual_producer_positive_and_idempotent_preserves_floor(fixture):
    f=fixture;dest=f['out']/'recipient.exe';dest.mkdir()
    floor=dest/f'leaf_{f["addresses"][1]:08x}.c';floor.write_text('/* compile-only-asm */\noriginal floor')
    old=floor.read_bytes();result=distribute(f)
    assert result['placed']==1 and result['proposed']==0,result
    assert floor.read_bytes()==old
    p=manifests(f)[0];record=json.loads(p.read_text())
    assert record['recoveryCredit'] is False and record['handoff']['replacementAllowed'] is False
    assert record['evidence']['provider']['id']==gate.PROVIDER
    observation=record['evidence']['provider']['compileObservation']
    assert Path(observation['object']['path']).is_file()
    assert observation['source']['sha256']==hashlib.sha256(f['source'].read_bytes()).hexdigest()
    assert (p.parent/'candidate.c').read_bytes().endswith(f['source'].read_bytes())
    again=distribute(f);assert again['idempotent']==1 and again['placed']==0
    assert len(manifests(f))==1 and floor.read_bytes()==old


@pytest.mark.parametrize('change,reason',[
    ('edited','stale_source'),('wrong-tree','legacy_or_missing'),('target','binary_content_changed'),
    ('generation','stale_donor'),('null','legacy_or_null'),('variant','incompatible_leaf'),
    ('abi','incompatible_declared_abi'),('legacy','legacy_or_missing'),('unsupported','missing_compatibility_provider'),
    ('overlap','overlapping_function'),('dependency','stale_donor')])
def test_refuses_stale_or_incompatible_and_preserves_proposal(fixture,change,reason):
    f=fixture;con=f['con']
    if change=='edited':f['source'].write_text(f['source'].read_text().replace('return 7','return 8'))
    elif change=='wrong-tree':
        other=f['out']/'wrong';other.mkdir();shutil.copy2(f['source'],other/'leaf.c');f['src']=other
    elif change=='target':
        p=f['images']/'recipient.exe';p.write_bytes(p.read_bytes()+b'changed')
    elif change=='generation':con.execute("UPDATE identity SET evidence=? WHERE binary_id=1",(json.dumps({'generation':2}),));con.commit()
    elif change=='null':con.execute('UPDATE identity SET evidence=NULL WHERE binary_id=2');con.commit()
    elif change=='variant':
        raw,_=pe(value=9,offset=16);(f['images']/'recipient.exe').write_bytes(raw)
        con.execute('UPDATE binary SET content_sha256=? WHERE id=2',(gate.digest(raw),));con.commit()
    elif change=='abi':con.execute("UPDATE func SET return_type='void *' WHERE binary_id=2");con.commit()
    elif change=='legacy':f['receipt'].write_text(json.dumps({'ok':[f'{f["addresses"][0]:x}']}))
    elif change=='unsupported':
        f['source'].write_text(f'/* address: 0x{f["addresses"][0]:x} */\nint leaf(void) {{ return 3+4; }}')
        row=f['row'];row['distribution']['source']=gate.snapshot(f['source']);f['receipt'].write_text(json.dumps({'results':[row]}))
    elif change=='overlap':
        con.execute('INSERT INTO func(binary_id,addr,size) VALUES(2,?,1)',(f['addresses'][1]+1,));con.commit()
    elif change=='dependency':
        # Selected generation includes the exact dependency target rows.
        token=con.execute('SELECT content_sha256 FROM binary WHERE id=2').fetchone()[0][:16]+':'+str(f['addresses'][1])
        con.execute('UPDATE identity SET evidence=? WHERE binary_id=1',(json.dumps({'dependencies':[token]}),));con.commit()
        f['row']['distribution']=gate.capture_source_basis(con,1,f['addresses'][0],f['source'],f['source'].read_bytes(),raw_dir=f['images'])
        f['receipt'].write_text(json.dumps({'results':[f['row']]}))
        con.execute("UPDATE identity SET method='changed' WHERE binary_id=2");con.commit()
    result=distribute(f);assert result['placed']==0 and result['proposed']==1,result
    assert reason in result['results'][0]['reason']
    record=json.loads(manifests(f,'unadmitted-proposals')[0].read_text())
    assert record['state']=='unadmitted' and record['recoveryCredit'] is False


@pytest.mark.parametrize('which',['source','receipt','image'])
def test_changed_before_atomic_publication_never_visible(fixture,monkeypatch,which):
    f=fixture;original=gate.publish
    def mutate(*args):
        if which=='source':f['source'].write_text(f['source'].read_text()+'\n')
        elif which=='receipt':f['receipt'].write_text('{}')
        elif which=='identity':f['con'].execute("UPDATE identity SET method='different' WHERE binary_id=2");f['con'].commit()
        else:
            p=f['images']/'recipient.exe';p.write_bytes(p.read_bytes()+b'changed')
        return original(*args)
    monkeypatch.setattr(gate,'publish',mutate)
    result=distribute(f);assert result['placed']==0
    assert not manifests(f)
    assert not list((f['out']/gate.AREA/'qualified-candidates').glob('.pending-*'))


def test_standalone_and_bulk_use_shared_producer_gate(fixture,capsys):
    f=fixture
    assert cp.main(['--from','donor','--db',str(f['db']),'--repo','/donor.exe','--out-dir',str(f['out']),'--raw-dir',str(f['images'])])==0
    assert json.loads(capsys.readouterr().out)['placed']==1
    result=bulk.distribute_compiled_source(f['source'],f'{f["addresses"][0]:x}',f['binding'])
    assert result['placed']==1,result  # receipt path is independent provenance
    assert len(manifests(f))==2


def test_watch_refreshes_selected_byteexact_receipt_and_source(fixture,monkeypatch,capsys):
    f=fixture;chosen=f['root']/'chosen-byteexact.json';chosen.write_text(json.dumps({'results':[f['row']]}))
    f['receipt'].write_text('{}');calls=[]
    def sleep(_, cancel):
        calls.append(1)
        if len(calls)==1:chosen.write_text('{}')
        else:raise StopIteration
    monkeypatch.setattr(cp,'_watch_wait',sleep)
    with pytest.raises(StopIteration):cp.watch(f['src'],1,f['out'],f['con'],.01,raw_dir=f['images'],receipt_path=chosen)
    rows=[json.loads(r) for r in capsys.readouterr().out.splitlines()]
    assert rows[0]['placed']==1 and rows[1]['placed']==0 and rows[1]['proposed']==1


def test_no_compile_gate_is_exploration_only(fixture,monkeypatch):
    monkeypatch.setattr('agentdecompile_recovery.corpus.source_contribution.compile_observation',lambda **kw:pytest.fail('exploration compiled'))
    result=distribute(fixture,no_compile_gate=True)
    assert result['placed']==0 and result['proposed']==1
    assert result['results'][0]['reason']=='explicit_unadmitted_exploration'


@pytest.mark.parametrize('kind',['source-symlink','source-hardlink','output-symlink','receipt-alias','db-sidecar'])
def test_aliases_and_external_input_preservation(fixture,kind):
    f=fixture;original=f['source'].read_bytes()
    if kind=='source-symlink':
        p=f['root']/'real.c';f['source'].rename(p);f['source'].symlink_to(p)
    elif kind=='source-hardlink':os.link(f['source'],f['root']/'hardlink.c')
    elif kind=='output-symlink':(f['out']/gate.AREA).symlink_to(f['images'],target_is_directory=True)
    elif kind=='receipt-alias':
        area=f['out']/gate.AREA;area.mkdir();f['receipt']=area/'receipt.json';f['receipt'].write_text('{}')
    elif kind=='db-sidecar':
        p=Path(str(f['db'])+'-journal');p.symlink_to(f['source'])
    try:result=distribute(f,receipt_path=f['receipt']);assert result['placed']==0
    except (ValueError,OSError):pass
    assert f['source'].read_bytes()==original


def test_concurrent_writer_and_manifest_conflict(fixture):
    f=fixture
    with gate.output_owner(f['out'],[f['source']]):
        errors=[]
        def competing():
            try:
                with gate.output_owner(f['out'],[f['source']]): errors.append('unexpected-owner')
            except ValueError as exc: errors.append(str(exc))
        thread=threading.Thread(target=competing);thread.start();thread.join(3)
        assert errors==['candidate_output_owned']
    assert distribute(f)['placed']==1
    p=manifests(f)[0];row=json.loads(p.read_text());row['recoveryCredit']=True;p.write_text(json.dumps(row))
    result=distribute(f);assert result['placed']==0 and result['idempotent']==0
    assert result['results'][0]['reason']=='checkpoint_publication_changed'


def test_catalog_actual_guarded_child_and_output_claim(fixture,monkeypatch):
    from agentdecompile_recovery.corpus.dashboard.actions import catalog,jobs,job_history
    f=fixture;monkeypatch.setattr(catalog,'env_defaults',lambda:{})
    monkeypatch.setattr(job_history,'directory',lambda:f['root']/'jobs')
    monkeypatch.setattr(jobs,'live_root',lambda:f['root'])
    action=catalog.action_by_id('corpus.cross-place');assert action.mutating and action.long_running
    params={'from':'donor','repo':'/donor.exe','db':str(f['db']),'out-dir':str(f['out']),'raw-dir':str(f['images'])}
    job=jobs.JobRecord(id='abc123abc123',action_id=action.id,title=action.title,params=params,
        argv=catalog.build_command(action,params),execution_root=str(f['root']))
    store_=jobs.JobStore();store_._jobs[job.id]=job;store_._order.append(job.id)
    try:
        store_._run(job.id,threading.Event())
        assert job.status=='ok',job.log or job.error
        assert job.argv[1:4]==['-I','-S','-c'] and cp.command_matches(job.argv,job.params)
        assert job.resource_disposition=='released' and jobs._bound_clearance(job.to_dict())
        assert ['output',str(f['out']/gate.AREA)] in job.resource_keys['external']
        frame=json.loads(job.log)
        assert frame['event']=='cross-place-generation' and frame['status']=='complete'
        assert frame['generation']==job.cross_place_generation['generation']
        assert frame['report']['placed']==1 and frame['report']['resultCount']==1
    finally:
        if store_._resource_owner_handle:store_._resource_owner_handle.close()


def test_bulk_real_try_compile_inner_distributes_supported_exact_tu(fixture):
    f=fixture;temp=f['root']/'compile-work';temp.mkdir()
    result=bulk._try_compile_inner(f'{f["addresses"][0]:08x}','leaf','',
        'int leaf(void) { return 7; }',temp,f['src'],'/donor.exe')
    assert result['ok'] and not result['asm'],result
    assert result['distribution']['placed']==1,result
    row=result['distribution']['compileReceiptRow']
    assert row['distribution']['source']['sha256']==gate.digest(Path(row['distribution']['source']['path']).read_bytes())


def test_real_byteexact_producer_binding_is_consumed(fixture):
    from agentdecompile_recovery.corpus import verify_recovered_byteexact as verifier
    f=fixture;receipt=f['root']/'byteexact.json'
    code=verifier.main(['--verified-dir',str(f['src']),'--raw',str(f['images']/'donor.exe'),
        '--compiler',str(bulk.COMPILE),'--out',str(receipt),'--db',str(f['db']),
        '--binary-id','1','--workers','1','--no-incremental'])
    assert code==0,receipt.read_text()
    row=json.loads(receipt.read_text())['results'][0]
    assert row['ok'] and row['distribution']['source']['sha256']==gate.digest(f['source'].read_bytes()),row
    f['receipt'].write_text('{}')
    result=distribute(f,receipt_path=receipt)
    assert result['placed']==1,result


def test_watch_holds_owner_during_wait(fixture,monkeypatch):
    f=fixture;observed=[]
    def pause(_, cancel):
        def compete():
            try:
                with gate.output_owner(f['out'],[f['source']]): observed.append('unexpected')
            except ValueError as exc: observed.append(str(exc))
        thread=threading.Thread(target=compete);thread.start();thread.join(3)
        raise StopIteration
    monkeypatch.setattr(cp,'_watch_wait',pause)
    with pytest.raises(StopIteration):cp.watch(f['src'],1,f['out'],f['con'],.1,raw_dir=f['images'])
    assert observed==['candidate_output_owned']


def test_actual_catalog_watch_cancels_and_clears_owned_session(fixture,monkeypatch):
    from agentdecompile_recovery.corpus.dashboard.actions import catalog,jobs,job_history
    f=fixture;monkeypatch.setattr(catalog,'env_defaults',lambda:{})
    monkeypatch.setattr(job_history,'directory',lambda:f['root']/'watch-jobs')
    monkeypatch.setattr(jobs,'live_root',lambda:f['root'])
    action=catalog.action_by_id('corpus.cross-place');cancel=threading.Event()
    params={'from':'donor','repo':'/donor.exe','db':str(f['db']),'out-dir':str(f['out']),'raw-dir':str(f['images']),'watch':True,'interval':60}
    job=jobs.JobRecord(id='fed123fed123',action_id=action.id,title=action.title,params=params,
        argv=catalog.build_command(action,params),execution_root=str(f['root']))
    real=jobs._default_executor;observed=[]
    def execute(argv,cwd,event,**kw):
        if cp._BOOTSTRAP not in argv:
            return real(argv,cwd,event,**kw)
        observed.append(kw.get('unlimited'));publish=kw['on_output']
        def output(log):
            publish(log)
            if '"placed": 1' in log:
                assert job.id in instance._external_held.values()
                assert str(f['db']) not in instance._identity_held
                contenders=[]
                def compete():
                    try:
                        with gate.output_owner(f['out'],[f['source']]):contenders.append('unexpected')
                    except ValueError as exc:contenders.append(str(exc))
                contender=threading.Thread(target=compete);contender.start();contender.join(3)
                assert not contender.is_alive() and contenders==['candidate_output_owned']
                # Actual catalog identity writer against the synthetic corpus,
                # while the real guarded watcher is sleeping with its lease.
                writer=catalog.action_by_id('corpus.logical-build')
                args={'db':str(f['db'])}
                root=str(Path(cp.__file__).resolve().parents[2])
                argv=[sys.executable,'-I','-S','-c',
                    'import sys;sys.path.insert(0,sys.argv.pop(1));from agentdecompile_recovery.corpus.cli import main;raise SystemExit(main(sys.argv[1:]))',
                    root,'logical-build','--db',str(f['db'])]
                other=jobs.JobRecord(id='bac123bac123',action_id=writer.id,title=writer.title,
                    params=args,argv=argv,execution_root=str(f['root']))
                instance._jobs[other.id]=other;instance._order.append(other.id)
                instance._run(other.id,threading.Event())
                assert other.status=='ok',other.log or other.error
                assert job.id in instance._external_held.values()
                cancel.set()
        kw['on_output']=output
        return real(argv,cwd,event,**kw)
    monkeypatch.setattr(jobs,'_default_executor',execute)
    instance=jobs.JobStore();instance._jobs[job.id]=job;instance._order.append(job.id)
    try:
        instance._run(job.id,cancel)
        assert observed==[None]  # Each guarded generation has a finite executor lifetime.
        assert job.status=='cancelled' and job.resource_disposition=='released',job.log or job.error
        assert jobs._bound_clearance(job.to_dict())
        with gate.output_owner(f['out'],[f['source']]): pass
    finally:
        if instance._resource_owner_handle:instance._resource_owner_handle.close()


def test_recursive_dependency_generation_and_quarantine(fixture):
    f=fixture;con=f['con'];raw,addr=pe(offset=32);(f['images']/'third.exe').write_bytes(raw)
    con.execute('INSERT INTO binary(id,repo_path,slug,content_sha256) VALUES(3,?,?,?)',('/third.exe','third.exe',gate.digest(raw)))
    con.execute('INSERT INTO func(binary_id,addr,size) VALUES(3,?,6)',(addr,))
    con.execute('INSERT INTO identity(logical_id,binary_id,addr,confidence,method,evidence) VALUES(1,3,?,1,?,?)',(addr,'dependency','{}'))
    def token(bid,address):return con.execute('SELECT content_sha256 FROM binary WHERE id=?',(bid,)).fetchone()[0][:16]+':'+str(address)
    con.execute('UPDATE identity SET evidence=? WHERE binary_id=1',(json.dumps({'dependencies':[token(2,f['addresses'][1])]}),))
    con.execute('UPDATE identity SET evidence=? WHERE binary_id=2',(json.dumps({'dependencies':[token(3,addr)]}),));con.commit()
    before=gate.identity_state(con,1,f['addresses'][0])
    assert len(before['rows']['dependencies'])==2
    con.execute("UPDATE func SET name='changed' WHERE binary_id=3");con.commit()
    assert gate.identity_state(con,1,f['addresses'][0])['generation']!=before['generation']
    con.execute('UPDATE identity SET evidence=? WHERE binary_id=3',(json.dumps({'quarantine':True}),));con.commit()
    with pytest.raises(ValueError,match='quarantined'):gate.identity_state(con,1,f['addresses'][0])


@pytest.mark.parametrize('leaf',['object','snapshot','source'])
def test_live_opaque_compile_revalidated_at_publication(fixture,monkeypatch,leaf):
    f=fixture;real=gate.publish
    def corrupt(root,captured,transformed,admitted,*rest):
        assert admitted.qualified
        Path(admitted.evidence['provider']['compileObservation'][leaf]['path']).write_bytes(b'changed')
        return real(root,captured,transformed,admitted,*rest)
    monkeypatch.setattr(gate,'publish',corrupt)
    result=distribute(f)
    assert result['placed']==0 and not manifests(f)
    assert 'compile_observation_invalidated' in result['results'][0]['reason']


@pytest.mark.parametrize('field',['provider','compileObservation'])
def test_idempotence_refuses_mutated_retained_evidence(fixture,field):
    f=fixture;assert distribute(f)['placed']==1;p=manifests(f)[0];row=json.loads(p.read_text())
    if field=='provider':row['evidence']['provider']['value']=99
    else:row['evidence']['provider']['compileObservation']['returncode']=2
    p.write_text(json.dumps(row));result=distribute(f)
    assert result['placed']==0 and result['idempotent']==0
    assert result['results'][0]['reason']=='checkpoint_publication_changed'


def test_unchanged_watch_reuses_retained_publication_without_opaque_authority(fixture,monkeypatch,capsys):
    f=fixture;polls=[]
    def pause(_, cancel):
        polls.append(1)
        if len(polls)==2:raise StopIteration
    monkeypatch.setattr(cp,'_watch_wait',pause)
    with pytest.raises(StopIteration):cp.watch(f['src'],1,f['out'],f['con'],.1,raw_dir=f['images'])
    assert not gate._CACHE  # Guarded children never deserialize opaque authority into this parent.
    assert len(list((f['out']/gate.AREA/'producer-evidence').glob('qualification-*')))==1
    rows=[json.loads(r) for r in capsys.readouterr().out.splitlines()]
    assert rows[0]['placed']==1 and rows[1]['idempotent']==1
    assert rows[1]['results'][0]['evidenceState']=='reused-historical-publication'
    assert rows[1]['results'][0]['currentAcceptance'] is False


def test_forged_qualification_object_is_not_publish_authority(tmp_path):
    root=tmp_path/'owned';root.mkdir()
    fake=gate.Admission(True,'pretend',{'provider':{'id':gate.PROVIDER}})
    with pytest.raises(ValueError,match='untrusted'):
        gate.publish(root,b'int f(void){return 1;}',b'int f(void){return 1;}',fake,tmp_path/'x.c',None,lambda:None)


def test_database_sidecar_alias_rejected_before_read_connection(fixture):
    f=fixture;side=Path(str(f['db'])+'-journal');side.symlink_to(f['source'])
    original=f['source'].read_bytes()
    with pytest.raises(ValueError,match='symlink'):gate.read_database(f['db'])
    assert f['source'].read_bytes()==original


def test_catalog_sidecar_claims_and_same_job_nested_restore(fixture,monkeypatch):
    from agentdecompile_recovery.corpus.dashboard.actions import catalog,jobs,job_history
    f=fixture;monkeypatch.setattr(catalog,'env_defaults',lambda:{})
    monkeypatch.setattr(job_history,'directory',lambda:f['root']/'restore-jobs')
    monkeypatch.setattr(job_history,'owner',lambda:{'ownerPid':1,'ownerStart':'test'})
    monkeypatch.setattr(jobs,'live_root',lambda:f['root'])
    action=catalog.action_by_id('corpus.cross-place');assert not action.identity_scope
    params={'from':'donor','repo':'/donor.exe','db':str(f['db']),'out-dir':str(f['out']),'raw-dir':str(f['images'])}
    job=jobs.JobRecord(id='ded123ded123',action_id=action.id,title=action.title,params=params,
        argv=catalog.build_command(action,params),execution_root=str(f['root']))
    first=jobs.JobStore();first._jobs[job.id]=job;first._order.append(job.id);first.executor=lambda *args:(0,'{}')
    first._run(job.id,threading.Event())
    assert job.resource_disposition=='quarantined'
    assert job.resource_keys['external']==[['output',str(f['out']/gate.AREA)]]
    assert 'identity' not in job.resource_keys
    first._resource_owner_handle.close()
    second=jobs.JobStore()
    try:
        second._restore_reservations_locked()
        assert not second._identity_held
        assert second._external_held[('output',str(f['out']/gate.AREA))]==job.id
    finally:
        if second._resource_owner_handle:second._resource_owner_handle.close()


def test_supervisor_cross_place_argv_preserves_raw_and_selected_receipt(fixture):
    from types import SimpleNamespace
    from agentdecompile_recovery.corpus.recovery_orchestrator import build_specs
    f=fixture
    args=SimpleNamespace(out_dir=str(f['out']),program='donor',repo='/donor.exe',db=str(f['db']),
        kb='unused',raw=str(f['images']/'donor.exe'),binary_id=1,compiler=None,extract_raw=str(f['images']),
        cascade=False,permuter=False,verify=False,nearmiss=False,cross_place=True)
    spec=next(s for s in build_specs(args) if s['name']=='cross-place');argv=spec['argv']
    assert argv[argv.index('--raw-dir')+1]==str(f['images'])
    assert argv[argv.index('--byteexact-receipt')+1]==str(f['out']/'donor.byteexact.json')


def test_snapshot_is_coherent_and_closed_before_compiler(fixture,monkeypatch):
    from agentdecompile_recovery.corpus import source_contribution as sc
    f=fixture;con=f['con'];con.execute('PRAGMA journal_mode=WAL')
    original=gate.ObservedRows.execute;changed=[];readers=[];real=sc.compile_observation
    before=gate.identity_state(con,2,f['addresses'][1])
    def query(self,sql,args=()):
        if self.connection is not None and self.connection not in readers:readers.append(self.connection)
        result=original(self,sql,args)
        if self.connection is not None and not changed and 'FROM binary WHERE id=' in sql:
            changed.append(True)
            con.execute("UPDATE identity SET method='after-capture' WHERE binary_id=2");con.commit()
        return result
    def compile_(**kw):
        assert kw['db'] is None
        assert readers
        for reader in readers:
            with pytest.raises(sqlite3.ProgrammingError,match='closed'):reader.execute('SELECT 1')
        assert not con.in_transaction
        return real(**kw)
    monkeypatch.setattr(gate.ObservedRows,'execute',query);monkeypatch.setattr(sc,'compile_observation',compile_)
    result=distribute(f);assert result['placed']==1,result
    manifest=json.loads(manifests(f)[0].read_text())
    assert manifest['observedSnapshot']['recipientGeneration']==before['generation']
    assert manifest['observedSnapshot']['currentAcceptance'] is False
    assert gate.identity_state(con,2,f['addresses'][1])['generation']!=before['generation']
    # New pass observes the changed relevant basis rather than mixing generations.
    again=distribute(f);assert again['placed']==1,again


def test_unrelated_sql_update_does_not_recompile(fixture,monkeypatch):
    from agentdecompile_recovery.corpus import source_contribution as sc
    f=fixture;real=sc.compile_observation;calls=[]
    def compile_(**kw):calls.append(1);return real(**kw)
    monkeypatch.setattr(sc,'compile_observation',compile_)
    assert distribute(f)['placed']==1
    f['con'].execute("INSERT INTO logical_function(id,best_name) VALUES(99,'unrelated')");f['con'].commit()
    assert distribute(f)['idempotent']==1
    assert len(calls)==1


@pytest.mark.parametrize('failure,limit',[('compiler_object_not_raw_equal',1),('compiler_failed:1',2)])
def test_failed_poll_budget_and_relevant_change_wakes(fixture,monkeypatch,failure,limit):
    from agentdecompile_recovery.corpus import source_contribution as sc
    f=fixture;calls=[];clock=[100.0]
    def fail(**kw):calls.append(kw['workspace']);raise ValueError(failure)
    monkeypatch.setattr(sc,'compile_observation',fail)
    monkeypatch.setattr(gate.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(gate.time,'time',lambda:clock[0])
    for _ in range(6):
        distribute(f);clock[0]+=31
    assert len(calls)==limit
    assert len(list((f['out']/gate.AREA/'producer-evidence').glob('qualification-*')))==limit
    record=json.loads(manifests(f,'unadmitted-proposals')[0].read_text())
    assert ('incompatible_native_object' if limit==1 else 'compiler_infrastructure_unqualified') in record['reason']
    f['row']['producerAttempt']='explicit-new-evidence';f['receipt'].write_text(json.dumps({'results':[f['row']]}))
    distribute(f);assert len(calls)==limit+1


def test_unsupported_never_allocates_qualification(fixture,monkeypatch):
    from agentdecompile_recovery.corpus import source_contribution as sc
    f=fixture;f['source'].write_text(f'/* address: 0x{f["addresses"][0]:x} */\nint leaf(void) {{ return 3+4; }}')
    f['row']['distribution']['source']=gate.snapshot(f['source']);f['receipt'].write_text(json.dumps({'results':[f['row']]}))
    monkeypatch.setattr(sc,'compile_observation',lambda **kw:pytest.fail('unsupported compiled'))
    for _ in range(3):distribute(f)
    assert not list((f['out']/gate.AREA/'producer-evidence').glob('qualification-*'))


def test_selected_source_not_blocked_by_unrelated_large_fanout(fixture):
    f=fixture;con=f['con']
    # Over4096 unrelated directed links previously exhausted the per-query
    # budget before the one selected source could reach qualification.
    con.execute("INSERT INTO logical_function(id,best_name) VALUES(2,'unrelated')")
    rows=[(2,bid,0x500000+i,1.0,'unrelated','{}') for i in range(4097) for bid in (1,2)]
    con.executemany('INSERT INTO identity(logical_id,binary_id,addr,confidence,method,evidence) VALUES(?,?,?,?,?,?)',rows)
    con.commit()
    result=cp.place_tree(f['src'],1,f['out'],con,raw_dir=f['images'],source_paths=[f['source']])
    assert result['placed']==1,result
    assert list(cp.load_index(con,1,f['addresses'][0]))==[f['addresses'][0]]


@pytest.mark.parametrize('failure',['allocation','write','after-compile'])
def test_attempt_reservation_bounds_all_failure_points(fixture,monkeypatch,failure):
    from agentdecompile_recovery.corpus import source_contribution as sc
    f=fixture;clock=[100.0];allocations=[];real_temp=gate.tempfile.mkdtemp
    real_write=Path.write_bytes;real_validate=sc.validate_compile
    def allocate(*args,**kw):
        if kw.get('prefix')=='qualification-':
            allocations.append(1)
            if failure=='allocation':raise OSError('fixture allocation failed')
        return real_temp(*args,**kw)
    def write(path,data):
        if path.name=='captured.c' and failure=='write':raise OSError('fixture captured write failed')
        return real_write(path,data)
    def validate(observation):
        result=real_validate(observation)
        if failure=='after-compile':raise ValueError('inputs_changed_during_qualification')
        return result
    monkeypatch.setattr(gate.tempfile,'mkdtemp',allocate);monkeypatch.setattr(Path,'write_bytes',write)
    monkeypatch.setattr(sc,'validate_compile',validate);monkeypatch.setattr(gate.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(gate.time,'time',lambda:clock[0])
    for _ in range(6):distribute(f);clock[0]+=31
    assert len(allocations)==2
    assert len(list((f['out']/gate.AREA/'producer-evidence').glob('qualification-*'))) <=2
    assert all(attempt['count']==2 and attempt['reason'] for attempt in gate._ATTEMPTS.values())


def test_opaque_cache_is_scoped_to_database_and_owned_output(fixture,monkeypatch):
    from agentdecompile_recovery.corpus import source_contribution as sc
    f=fixture;calls=[];real=sc.compile_observation
    def compile_(**kw):calls.append(kw['workspace']);return real(**kw)
    monkeypatch.setattr(sc,'compile_observation',compile_)
    assert distribute(f)['placed']==1
    alternate=f['root']/'alternate-output'
    second=cp.place_tree(f['src'],1,alternate,f['con'],raw_dir=f['images'],receipt_path=f['receipt'])
    assert second['placed']==1 and len(calls)==2,second
    assert calls[1].is_relative_to(alternate/gate.AREA)
    other=f['root']/'other.sqlite';other_con=sqlite3.connect(other);other_con.row_factory=sqlite3.Row
    f['con'].backup(other_con)
    try:
        third=cp.place_tree(f['src'],1,alternate,other_con,raw_dir=f['images'],receipt_path=f['receipt'])
        assert third['placed']==1 and len(calls)==3,third
    finally:other_con.close()


def test_actual_native_object_mismatch_is_reused_without_recompile(fixture,monkeypatch):
    from agentdecompile_recovery.corpus import source_contribution as sc
    f=fixture;con=f['con']
    # Both images use MOV EAX,0;RET (6 bytes). The pinned real compiler emits
    # XOR EAX,EAX;RET (3 bytes). Semantic constant equality alone cannot replace
    # this provider's exact donor-object requirement.
    for bid,slug,offset in [(1,'donor.exe',0),(2,'recipient.exe',16)]:
        raw,_=pe(value=0,offset=offset);(f['images']/slug).write_bytes(raw)
        con.execute('UPDATE binary SET content_sha256=? WHERE id=?',(gate.digest(raw),bid))
    con.commit();f['source'].write_text(f['source'].read_text().replace('return 7','return 0'))
    ok,error=bulk._compile_text(f['source'],f['root']/'zero-producer.obj','leaf','',f['source'].read_text())
    assert ok,error
    row={'ok':True,**bulk._COMPILE_BINDINGS[str(f['source'])]}
    f['receipt'].write_text(json.dumps({'results':[row]}))
    calls=[];real=sc.compile_observation
    def compile_(**kw):calls.append(kw['workspace']);return real(**kw)
    monkeypatch.setattr(sc,'compile_observation',compile_)
    for _ in range(4):
        result=distribute(f)
        assert result['placed']==0 and 'incompatible_native_object:compiler_object_not_raw_equal' in result['results'][0]['reason'],result
    assert len(calls)==1
    workspaces=list((f['out']/gate.AREA/'producer-evidence').glob('qualification-*'))
    assert len(workspaces)==1
    objects=list(workspaces[0].glob('contribution-*/unit.obj'));assert len(objects)==1
    assert sc.parse_coff(objects[0].read_bytes())['bytes'] in (b'\x31\xc0\xc3',b'\x33\xc0\xc3')
    assert json.loads((workspaces[0]/'attempt.json').read_text())['attempt']==1


def test_watch_uses_exact_external_source_root(fixture,monkeypatch,capsys):
    f=fixture
    external=f['root']/'external'/'donor';external.mkdir(parents=True)
    source=external/'external.c';source.write_bytes(f['source'].read_bytes())
    ok,error=bulk._compile_text(source,f['root']/'external.obj','leaf','',source.read_text())
    assert ok,error
    row={'ok':True,**bulk._COMPILE_BINDINGS[str(source)]}
    chosen=f['root']/'external-receipt.json';chosen.write_text(json.dumps({'results':[row]}))
    def pause(interval,cancel):raise StopIteration
    monkeypatch.setattr(cp,'_watch_wait',pause)
    with pytest.raises(StopIteration):
        cp.watch(external,1,f['out'],f['con'],.01,raw_dir=f['images'],receipt_path=chosen)
    result=json.loads(capsys.readouterr().out)
    assert result['placed']==1 and result['resultCount']==1
    record=json.loads(Path(result['results'][0]['candidate'],'manifest.json').read_text())
    assert record['sourcePath']==str(source)
