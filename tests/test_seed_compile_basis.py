import json

import pytest

from agentdecompile_recovery.corpus import seed_validation as sv


def setup_basis(tmp_path, monkeypatch):
    wrapper = tmp_path/'compiler'
    wrapper.write_bytes(b'wrapper-v1')
    dependency = tmp_path/'header.h'
    dependency.write_bytes(b'header-v1')
    manifest = tmp_path/'closure.json'
    manifest.write_text(json.dumps({'complete':True,'files':['header.h'],'environment':['SPECIAL']}))
    monkeypatch.setattr(sv,'source_context',lambda *a:'context-v1')
    seed = sv.Seed('source','/target','1','f',1,b'X','f','int f(void){return 0;}')
    return seed, wrapper, dependency, manifest


@pytest.mark.parametrize('changed',['wrapper','context','dependency','environment','overrides'])
def test_basis_changes_for_actual_compile_inputs(tmp_path,monkeypatch,changed):
    seed, wrapper, dependency, manifest = setup_basis(tmp_path,monkeypatch)
    overrides = {'PRIVATE_OVERRIDE':'secret-value'}
    before, preamble, env = sv.compile_basis(seed,wrapper,tmp_path,manifest,overrides,coff_functions=setup_basis)
    assert before['closureComplete'] and preamble == 'context-v1'
    assert env['PRIVATE_OVERRIDE'] == 'secret-value'
    assert 'secret-value' not in json.dumps(before)
    if changed == 'wrapper': wrapper.write_bytes(b'wrapper-v2')
    if changed == 'context': monkeypatch.setattr(sv,'source_context',lambda *a:'context-v2')
    if changed == 'dependency': dependency.write_bytes(b'header-v2')
    if changed == 'environment': monkeypatch.setenv('SPECIAL','new-secret')
    if changed == 'overrides': overrides['PRIVATE_OVERRIDE']='new-secret'
    after, _, _ = sv.compile_basis(seed,wrapper,tmp_path,manifest,overrides,coff_functions=setup_basis)
    assert after['key'] != before['key']


def test_missing_or_invalid_closure_forbids_reuse(tmp_path,monkeypatch):
    seed, wrapper, dependency, manifest = setup_basis(tmp_path,monkeypatch)
    basis, _, _ = sv.compile_basis(seed,wrapper,tmp_path)
    assert not basis['closureComplete']
    manifest.write_text('{broken')
    assert not sv.compile_basis(seed,wrapper,tmp_path,manifest,coff_functions=setup_basis)[0]['closureComplete']
    row = {'compile_status':'byte_exact','comparisonPolicy':'raw-region-v1','sourceSha256':'a'*64,
           'targetSnapshot':{'sha256':'b'*64},'targetRegion':{},'compileBasis':basis}
    assert not sv.can_reuse_compile_result(row,row)
    complete = {**basis,'closureComplete':True}
    row['compileBasis'] = complete
    assert sv.can_reuse_compile_result(row,row)
    assert not sv.can_reuse_compile_result({**row,'compileBasis':{**complete,'key':'c'*64}},row)


@pytest.mark.parametrize('mutate',[False,True])
def test_audit_compiles_without_closure_but_rejects_changed_inputs(tmp_path,monkeypatch,mutate):
    seed, wrapper, dependency, manifest = setup_basis(tmp_path,monkeypatch)
    donor = tmp_path/'program'/'f.c'
    donor.parent.mkdir()
    donor.write_text(seed.payload)
    seed = sv.Seed(str(donor),'/target','401000','f',1,b'X','f',seed.payload)
    directory = tmp_path/'seeds'/'target'
    directory.mkdir(parents=True)
    (directory/'401000.c').write_bytes(b'frozen seed')
    candidates = [{'src_program':'program','src_name':'f','dst_slug':'target','dst_addr':'401000'}]
    monkeypatch.setattr(sv,'read_jsonl',lambda *a:candidates)
    monkeypatch.setattr(sv,'parse_seed',lambda _:seed)
    key = sv.reuse_key(str(donor),'/target','401000')
    monkeypatch.setattr(sv,'build_reuse_index',lambda *a:{key:[{'logical_id':1}]})
    monkeypatch.setattr(sv,'candidate_reuse_key',lambda _:key)
    monkeypatch.setattr(sv,'source_has_verified_coverage',lambda *a:True)
    calls = []
    def compile(*a,**kwargs):
        calls.append(kwargs)
        assert kwargs['frozen_preamble']=='context-v1'
        if mutate: wrapper.write_bytes(b'changed during compile')
        return {'compile_status':'byte_exact','comparisonPolicy':'raw-region-v1'}
    monkeypatch.setattr(sv,'compile_seed',compile)
    output = tmp_path/'result.jsonl'
    sv.audit(seeds_dir=tmp_path/'seeds',candidates_path=tmp_path/'candidates',reuse_path=tmp_path/'reuse',
             results_path=output,summary_path=tmp_path/'summary',compile_destinations=True,
             compiler_for=lambda _:(wrapper,{}),evidence_root=tmp_path)
    row = json.loads(output.read_text())
    assert calls and not row['compileBasis']['closureComplete']
    assert row['compile_status'] == ('compile_inputs_changed' if mutate else 'byte_exact')


def test_basis_tracks_cwd_and_selected_target_artifacts(tmp_path,monkeypatch):
    seed, wrapper, _, manifest = setup_basis(tmp_path,monkeypatch)
    first = sv.compile_basis(seed,wrapper,tmp_path,manifest,coff_functions=setup_basis)[0]
    other = tmp_path/'other'
    other.mkdir()
    monkeypatch.chdir(other)
    second = sv.compile_basis(seed,wrapper,tmp_path,manifest,coff_functions=setup_basis)[0]
    assert second['key'] != first['key']
    target = tmp_path/'source.o'
    target.write_bytes(b'original object')
    monkeypatch.setattr(sv,'source_target_artifacts',lambda *a:(target,[]))
    third = sv.compile_basis(seed,wrapper,tmp_path,manifest,coff_functions=setup_basis)[0]
    assert third['key'] != second['key']
    target.write_bytes(b'changed object')
    assert sv.compile_basis(seed,wrapper,tmp_path,manifest,coff_functions=setup_basis)[0]['key'] != third['key']


def test_configured_audit_reuses_only_unchanged_complete_basis(tmp_path,monkeypatch):
    seed, wrapper, dependency, manifest = setup_basis(tmp_path,monkeypatch)
    donor = tmp_path/'program'/'f.c'
    donor.parent.mkdir()
    donor.write_text(seed.payload)
    seed = sv.Seed(str(donor),'/target','401000','f',1,b'X','f',seed.payload)
    directory = tmp_path/'seeds'/'target'
    directory.mkdir(parents=True)
    (directory/'401000.c').write_bytes(b'frozen seed')
    raw = tmp_path/'raw'
    raw.mkdir()
    (raw/'target').write_bytes(b'Xwhole-image')
    candidates = [{'src_program':'program','src_name':'f','dst_slug':'target','dst_addr':'401000'}]
    candidate_path = tmp_path/'candidates.jsonl'
    candidate_path.write_text(json.dumps(candidates[0])+'\n')
    monkeypatch.setattr(sv,'parse_seed',lambda _:seed)
    key = sv.reuse_key(str(donor),'/target','401000')
    monkeypatch.setattr(sv,'build_reuse_index',lambda *a:{key:[{'logical_id':1}]})
    monkeypatch.setattr(sv,'candidate_reuse_key',lambda _:key)
    monkeypatch.setattr(sv,'source_has_verified_coverage',lambda *a:True)
    calls = []
    def compile(*a,**kwargs):
        calls.append(kwargs)
        assert kwargs['coff_functions'] is setup_basis
        assert kwargs['frozen_preamble'] == 'context-v1'
        return {'compile_status':'byte_exact','comparisonPolicy':'raw-region-v1'}
    monkeypatch.setattr(sv,'compile_seed',compile)
    output = tmp_path/'results.jsonl'
    ledger = output  # audit writes results_path; retry reads configured prior-results ledger
    options = dict(seeds_dir=tmp_path/'seeds',candidates_path=candidate_path,reuse_path=tmp_path/'reuse',
                   results_path=output,summary_path=tmp_path/'summary',compile_destinations=True,
                   compiler_for=lambda _:(wrapper,{}),evidence_root=tmp_path,
                   compile_input_manifest=manifest,coff_functions=setup_basis,
                   raw_dir=raw,mapper_for=lambda data:(lambda address:0,'fixture'),
                   compile_results_path=ledger,retry_failed_only=True)
    sv.audit(**options)
    first = json.loads(output.read_text())
    assert first['compileBasis']['closureComplete'] and len(calls) == 1
    assert first['targetSnapshot']['sha256']
    sv.audit(**options)
    second = json.loads(output.read_text())
    assert second['compileResultReused'] is True and len(calls) == 1
    wrapper.write_bytes(b'changed wrapper')
    sv.audit(**options)
    assert len(calls) == 2
    assert not json.loads(output.read_text()).get('compileResultReused')
    dependency.write_bytes(b'changed dependency')
    sv.audit(**options)
    assert len(calls) == 3
    options['coff_functions'] = None
    # Fresh attempt remains permitted, but absent parser cannot qualify reuse.
    monkeypatch.setattr(sv,'compile_seed',lambda *a,**k:(calls.append(k) or {'compile_status':'object_unreadable'}))
    sv.audit(**options)
    final = json.loads(output.read_text())
    assert len(calls) == 4
    assert final['compileBasis']['closureComplete'] is False
    assert final['compileBasis']['closureReason'] == 'object_parser_unavailable'
    assert not final.get('compileResultReused')
