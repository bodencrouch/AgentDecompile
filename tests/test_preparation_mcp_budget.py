"""Source-only fake-transport proof of the preparation MCP dispatch boundary."""
import json
import threading
from types import SimpleNamespace

import pytest

from agentdecompile_recovery.corpus.dashboard import preparation, mcp_budget, mcp_bridge
from agentdecompile_recovery.corpus.dashboard.actions import jobs, job_history
from agentdecompile_recovery.corpus.dashboard.actions.catalog import ActionSpec, FieldSpec


@pytest.fixture
def scope(tmp_path, monkeypatch):
    monkeypatch.setattr(preparation, '_directory', lambda: tmp_path)
    monkeypatch.setattr(preparation, '_read_control', lambda _: {})
    monkeypatch.setattr(jobs, 'live_root', lambda: tmp_path)
    monkeypatch.setattr(job_history, 'directory', lambda: tmp_path / 'jobs')
    monkeypatch.setattr(threading.Thread, 'start', lambda _: None)
    monkeypatch.setattr(mcp_bridge, '_ensure_initialized', lambda **_: None)
    monkeypatch.setattr(mcp_bridge, '_ACTIVE_LOCATOR', '')
    monkeypatch.setattr(mcp_bridge, '_OPENED', {})
    lease = (tmp_path / 'lease').open('w')
    row = {'id': 'e' * 32, 'actions': {}, 'status': 'blocked'}
    monkeypatch.setattr(preparation, '_LEASES', {row['id']: lease})
    monkeypatch.setattr(preparation, '_ACTIVE', {row['id']})
    mcp_budget.initialize(row, 2)
    reserve = preparation._mcp_reservation_capability(row, lease, dispatch_id="root-attempt", action_id="root-action")
    calls = []
    def rpc(method, params, **_):
        persisted = preparation._read(row['id'])['providerBudget']
        assert persisted['consumed'] == len(calls) + 1
        calls.append(params['name'])
        return {'content': [{'type': 'text', 'text': '{"success":true}'}]}
    monkeypatch.setattr(mcp_bridge, '_rpc', rpc)
    yield row, reserve, calls
    lease.close()


def action(command='list-functions', mutating=False):
    return ActionSpec(id='mcp.'+command, title='Test', group='mcp', backend='mcp-cli', command=command,
                      mutating=mutating, ghidra_exclusive=mutating,
                      fields=(FieldSpec('locator'), FieldSpec('programPath'),))


def test_real_store_primary_checkin_denial_quarantines(scope, monkeypatch):
    row, reserve, calls = scope
    spec = action('manage-comments', True)
    monkeypatch.setattr(jobs, 'action_by_id', lambda _: spec)
    monkeypatch.setattr(jobs, '_auto_checkin_enabled', lambda: True)
    store = jobs.JobStore()
    def guarded(tool):
        assert store._lock.acquire(blocking=False), 'budget callback ran under JobStore lock'
        store._lock.release()
        return reserve(tool)
    job = store.start(spec, {'locator': 'project', 'programPath': 'Demo'}, [], mcp_reserve=guarded)
    assert 'mcp_reserve' not in job.to_dict()
    assert store._jobs[job.id].mcp_reserve is guarded
    store._run(job.id, threading.Event())
    result = store.get(job.id)
    assert calls == ['open', 'manage-comments']
    assert result.status == 'failed'
    assert result.resource_disposition == 'quarantined'
    assert json.loads(result.log)['nextAction'] == 'provider_budget_exhausted'
    assert json.loads(result.log)['ownershipUnresolved'] is True
    assert store._running == 0
    store._resource_owner_handle.close()


def test_prerequisite_retry_cap_and_context_reset(scope, monkeypatch):
    row, reserve, calls = scope
    real_rpc = mcp_bridge._rpc
    def rpc(method, params, **kwargs):
        response = real_rpc(method, params, **kwargs)
        if params['name'] == 'get-function':
            return {'isError': True, 'content': [{'type':'text','text':'missing session id'}]}
        return response
    monkeypatch.setattr(mcp_bridge, '_rpc', rpc)
    code, log = jobs._mcp_executor(action('get-function'), {'locator':'project'}, threading.Event(), mcp_reserve=reserve)
    assert code == 1 and json.loads(log)['nextAction'] == 'provider_budget_exhausted'
    assert calls == ['open', 'get-function']
    monkeypatch.setattr(mcp_bridge, '_rpc', lambda *_a, **_k: {'content':[]})
    assert mcp_bridge.call_tool('independent')['ok']
    assert row['providerBudget']['consumed'] == 2


def test_intent_failure_and_stale_generation_never_dispatch(scope, monkeypatch):
    row, reserve, calls = scope
    with monkeypatch.context() as patch:
        patch.setattr(preparation, '_write', lambda _: (_ for _ in ()).throw(OSError('disk failed')))
        code, log = jobs._mcp_executor(action(), {}, threading.Event(), mcp_reserve=reserve)
    assert not calls and json.loads(log)['nextAction'] == 'provider_budget_persistence_failed'
    assert row['providerBudget']['consumed'] == 1  # conservative in-memory spent intent
    monkeypatch.setattr(preparation, '_LEASES', {row['id']: object()})
    code, log = jobs._mcp_executor(action(), {}, threading.Event(), mcp_reserve=reserve)
    assert not calls and json.loads(log)['nextAction'] == 'provider_authority_lost'
    assert row['providerBudget']['consumed'] == 1


def test_unknown_spending_restart_and_forged_params(scope, monkeypatch):
    row, reserve, calls = scope
    def uncertain(*_a, **_k):
        assert preparation._read(row['id'])['providerBudget']['consumed'] == 1
        calls.append('unknown')
        raise TimeoutError('transport lost')
    monkeypatch.setattr(mcp_bridge, '_rpc', uncertain)
    jobs._mcp_executor(action(), {'_mcp_reserve':None, 'maxMcpToolCalls':999, 'providerBudget':{'consumed':0}}, threading.Event(), mcp_reserve=reserve)
    restored = preparation._read(row['id'])
    mcp_budget.initialize(restored, 999)
    assert restored['providerBudget']['consumed'] == 1
    assert restored['providerBudget']['maxMcpToolCalls'] == 2
    assert len(restored['providerBudget']['reservations']) == 1


def test_controls_migration_projection_and_cached_noop(scope, monkeypatch):
    row, reserve, calls = scope
    monkeypatch.setattr(mcp_bridge, '_ACTIVE_LOCATOR', 'project')
    with mcp_budget.dispatch_scope(reserve):
        assert mcp_bridge.ensure_project('project')['reused']
    assert not calls and row['providerBudget']['consumed'] == 0
    reserve('first')
    preparation._write(row)
    params={'preparation_id':row['id'], 'operation':'provider-budget', 'maxMcpToolCalls':3, 'expectedAllocationRevision':1}
    with pytest.raises(ValueError, match='drain'):
        preparation.control(params)
    preparation._release_lease(row['id'])
    preparation._ACTIVE.discard(row['id'])
    revised=preparation.control(params)['providerBudget']
    assert revised['remaining'] == 2 and revised['consumed'] == 1 and revised['allocationRevision'] == 2
    assert 'reservations' not in revised and 'allocationHistory' not in revised
    with pytest.raises(ValueError, match='revision changed'):
        preparation.control(params)
    unlimited=preparation.control({**params,'maxMcpToolCalls':None,'unlimited':True,'expectedAllocationRevision':2})['providerBudget']
    assert unlimited['remaining'] is None and unlimited['consumed'] == 1
    legacy={'id':'old','actions':{'old':{}}}
    assert mcp_budget.initialize(legacy)['priorUsageUnknown']


def test_helpers_pass_private_capability_before_start(scope, monkeypatch):
    row, reserve, calls = scope
    received=[]
    monkeypatch.setattr(jobs, 'start_job', lambda *args, **kwargs: received.append(kwargs))
    jobs._start_preparation_probe({}, {}, _mcp_reserve=reserve)
    jobs._start_preparation_facts_inventory({}, {}, _mcp_reserve=reserve)
    assert all(item['_mcp_reserve'] is reserve for item in received)


@pytest.mark.parametrize('maximum', [2, 5])
def test_unknown_prior_effect_blocks_later_dispatch_without_spending(scope, monkeypatch, maximum):
    row, reserve, calls = scope
    row['providerBudget']['maxMcpToolCalls'] = maximum
    # Retain uncertainty even if a future adapter tries a subsequent dispatch.
    real_rpc=mcp_bridge._rpc
    def rpc(method, params, **kwargs):
        result=real_rpc(method, params, **kwargs)
        if len(calls) == 2:
            return {'isError':True,'content':[{'type':'text','text':json.dumps({'success':False,'error':'missing session id','ownershipUnresolved':True})}]}
        return result
    monkeypatch.setattr(mcp_bridge, '_rpc', rpc)
    def adapter(*_args, **_kwargs):
        mcp_bridge.call_tool('open')
        mcp_bridge.call_tool('get-function')
        mcp_bridge.call_tool('repair')
        pytest.fail('budget refusal must interrupt the adapter')
    monkeypatch.setattr(jobs, '_mcp_executor_in_context', adapter)
    code, log=jobs._mcp_executor(action('get-function'), {'locator':'project'}, threading.Event(), mcp_reserve=reserve)
    assert code == 1 and json.loads(log)['ownershipUnresolved'] is True
    assert json.loads(log)['nextAction'] == 'provider_ownership_unresolved'
    assert row['providerBudget']['consumed'] == 2
    assert len(calls) == 2


def test_preparation_to_store_to_bridge_and_revision_resume(scope, tmp_path, monkeypatch):
    import hashlib
    import threading
    from types import SimpleNamespace
    from agentdecompile_recovery.corpus import corpus_config, ghidra_project
    from agentdecompile_recovery.corpus.dashboard import workflow
    from agentdecompile_recovery.corpus.dashboard.actions import jobs

    directory = tmp_path / 'preparations'
    directory.mkdir()
    locator, program, fingerprint = 'local-project', 'Demo.exe', 'image-one'
    run_id = 'e' * 32
    db = tmp_path / 'corpus.sqlite'
    row = {
        'id': run_id, 'locator': locator, 'program': program, 'slug': 'demo',
        'stages': [], 'events': [], 'actions': {}, 'deadline': None,
        'checkpoints': {program: {
            'observedProgramPath': program, 'programFingerprint': fingerprint,
            'protection': {'handling': 'stored-program'}, 'executablePath': '/external/demo',
            'analysisConfirmed': True, 'needsAnalysis': False, 'factsComplete': True,
            'binaryId': 1, 'recoveryFamily': 'demo-family',
        }},
    }
    monkeypatch.setattr(preparation, '_directory', lambda: directory)
    monkeypatch.setattr(preparation, 'live_db', lambda: db)
    monkeypatch.setattr(preparation, '_read_control', lambda _id: {})
    monkeypatch.setattr(preparation, '_execution_program_bindings', lambda *_: {program: (locator, program)})
    monkeypatch.setattr(preparation, '_comparison_inventory', lambda src, dst, *_: [src, dst])
    monkeypatch.setattr(ghidra_project, 'inspect_locator', lambda _: {'ok': True, 'programs': [program]})
    monkeypatch.setattr(preparation, 'ghidra_program_path', lambda info, selected: selected)
    monkeypatch.setattr(corpus_config, 'load_match_pairs', lambda: [])
    monkeypatch.setattr(workflow, 'input_revision', lambda fields: [fields.get('src'), fields.get('dst')])
    monkeypatch.setenv('AGENT_DECOMPILE_BSIM_URL', 'file:fixture')
    bsim_identity = hashlib.sha256(json.dumps([locator, program, fingerprint]).encode()).hexdigest()[:24]
    receipt = tmp_path / 'bsim' / 'corpus' / 'programs' / bsim_identity / 'ingest.json'
    receipt.parent.mkdir(parents=True)
    receipt.write_text(json.dumps({'status': 'committed', 'url': 'file:fixture', 'programFingerprint': fingerprint}))

    def query(sql, *_):
        if 'b.func_count,b.recovery_family,p.locator' in sql:
            return [(1, 'demo', 'source', 1, 'demo-family', locator, program)], None
        return [(1, 'demo', 'source', 'demo-family', 1, 'x86', 32, locator, program)], None

    monkeypatch.setattr(preparation, 'query_db', query)
    row['maxMcpToolCalls'] = 1
    preparation._write(row)
    spec = action('custom-read')
    monkeypatch.setattr(jobs, 'action_by_id', lambda _: spec)
    store = jobs.JobStore()
    monkeypatch.setattr(jobs, 'STORE', store)
    def get_job(job_id):
        job = store._jobs.get(job_id)
        if job is not None and job.status == 'queued':
            store._run(job_id, threading.Event())
        return store.get(job_id)
    monkeypatch.setattr(jobs, 'get_job', get_job)
    observed = []
    def continuation(current, root, database, dispatch, update, **kwargs):
        first = dispatch('matching', spec.id, {}, current)
        changed = dispatch('matching', spec.id, {'changed': 'input'}, current)
        observed.append((first, changed))
    monkeypatch.setattr(workflow, 'continue_recovery', continuation)
    preparation.execute({'preparation_id':run_id}, threading.Event())
    saved = preparation._read(run_id)
    assert observed[0][0]['nextAction'] == 'provider_budget_exhausted'
    assert observed[0][1]['nextAction'] == 'provider_budget_exhausted'
    assert saved['objectiveBudget']['consumed'] == 1
    assert saved['providerBudget']['consumed'] == 1
    intent = next(iter(saved['providerBudget']['reservations'].values()))
    root_attempt = next(iter(saved['actions'].values()))
    assert intent['parentDispatchId'] == root_attempt['dispatchId']
    assert intent['actionId'] in saved['actions']
    assert any(stage.get('nextAction') == 'provider_budget_exhausted' for stage in preparation._public_run(saved)['stages'])
    preparation.control({'preparation_id':run_id, 'operation':'provider-budget', 'expectedAllocationRevision':1,'maxMcpToolCalls':3})
    with (tmp_path / 'second-lease').open('w') as lease:
        preparation._LEASES[run_id] = lease
        preparation._ACTIVE.add(run_id)
        preparation.execute({'preparation_id':run_id}, threading.Event())
    assert observed[1][0]['ok']
    assert preparation._read(run_id)['providerBudget']['consumed'] == 3


def test_real_ensure_program_nested_checkout_denial(scope, monkeypatch):
    from agentdecompile_recovery.corpus import ghidra_project
    row, reserve, calls = scope
    monkeypatch.setattr(ghidra_project, 'inspect_locator', lambda _: {'ok':True, 'kind':'local-project'})
    monkeypatch.setattr(ghidra_project, 'ghidra_program_path', lambda _info, name: name)
    monkeypatch.setattr(ghidra_project, 'ghidra_connect_args', lambda _: {})
    code, log = jobs._mcp_executor(action('list-functions'), {'locator':'project','programPath':'Demo'}, threading.Event(), mcp_reserve=reserve)
    assert calls == ['open', 'open']
    assert code == 1 and json.loads(log)['nextAction'] == 'provider_budget_exhausted'
    assert row['providerBudget']['consumed'] == 2


def test_zero_budget_initializes_transport_but_never_dispatches(scope, monkeypatch):
    row, reserve, calls = scope
    row['providerBudget']['maxMcpToolCalls'] = 0
    initialized=[]
    monkeypatch.setattr(mcp_bridge, '_ensure_initialized', lambda **_: initialized.append(True))
    code, log = jobs._mcp_executor(action(), {}, threading.Event(), mcp_reserve=reserve)
    assert initialized == [True] and not calls
    assert row['providerBudget']['consumed'] == 0
    assert json.loads(log)['wakeCondition'] == 'explicit_provider_allocation_revision'


def test_unlimited_reservations_are_unique_and_remain_spent():
    row={'id':'unlimited'}
    for _ in range(4):
        mcp_budget.reserve(row,'same-tool',dispatch_id='same-parent',action_id='same-action')
    assert len(row['providerBudget']['reservations']) == row['providerBudget']['consumed'] == 4
    assert mcp_budget.public(row)['remaining'] is None


def test_same_lease_without_active_coordinator_refuses(scope):
    row, reserve, calls = scope
    preparation._ACTIVE.discard(row['id'])
    code, log = jobs._mcp_executor(action(), {}, threading.Event(), mcp_reserve=reserve)
    assert code == 1 and not calls and row['providerBudget']['consumed'] == 0
    assert json.loads(log)['nextAction'] == 'provider_authority_lost'


def test_catalog_provider_controls():
    from agentdecompile_recovery.corpus.dashboard.actions.catalog import action_by_id
    prepare = {field.name:field for field in action_by_id('workbench.prepare').fields}
    control = {field.name:field for field in action_by_id('workbench.workflow-control').fields}
    assert prepare['maxMcpToolCalls'].kind == 'int'
    assert 'provider-budget' in control['operation'].choices
    assert control['maxMcpToolCalls'].kind == 'int'
    assert control['expectedAllocationRevision'].kind == 'int'
    assert control['unlimited'].kind == 'bool'


@pytest.mark.parametrize('envelope', ['dict', 'json-string', 'list'])
def test_nested_uncertainty_blocks_replay_and_retains_store_quarantine(scope, monkeypatch, envelope):
    row, reserve, calls = scope
    spec = ActionSpec(id='mcp.get-function', title='Read function', group='mcp',
                      backend='mcp-cli', command='get-function', mutating=False,
                      ghidra_exclusive=True, fields=(FieldSpec('locator'),))
    monkeypatch.setattr(jobs, 'action_by_id', lambda _: spec)
    real_rpc = mcp_bridge._rpc
    def rpc(method, params, **kwargs):
        result = real_rpc(method, params, **kwargs)
        if len(calls) == 2:
            nested = {'ownershipUnresolved': True}
            if envelope == 'json-string':
                nested = json.dumps(nested)
            elif envelope == 'list':
                nested = [nested]
            return {'isError': True, 'content': [{'type': 'text', 'text': json.dumps({
                'success': False, 'error': 'missing session id', 'result': nested})}]}
        return result
    monkeypatch.setattr(mcp_bridge, '_rpc', rpc)
    store = jobs.JobStore()
    job = store.start(spec, {'locator': 'project'}, [], mcp_reserve=reserve)
    store._run(job.id, threading.Event())
    result = store.get(job.id)
    assert calls == ['open', 'get-function']
    assert result.status == 'failed'
    assert 'missing session id' in result.log
    assert jobs._ownership_unresolved(result.log)
    assert 'provider_budget_exhausted' not in result.log
    assert result.resource_disposition == 'quarantined'
    assert store._ghidra_held and store._running == 0
    store._resource_owner_handle.close()



def test_normal_function_list_transport_wrappers_do_not_invent_uncertainty(scope, monkeypatch):
    row, reserve, calls = scope
    real_rpc = mcp_bridge._rpc
    payload = {'result': {'functions': [{'name': 'f', 'address': '0x1000'}]}}
    def rpc(method, params, **kwargs):
        real_rpc(method, params, **kwargs)
        return {'content': [{'type': 'text', 'text': json.dumps(payload)}]}
    monkeypatch.setattr(mcp_bridge, '_rpc', rpc)
    code, log = jobs._mcp_executor(action('list-functions'), {}, threading.Event(), mcp_reserve=reserve)
    assert code == 0 and calls == ['list-functions']
    assert 'ownershipUnresolved' not in log
    wrapped = {'parsed': payload, 'text': json.dumps(payload),
               'raw': {'content': [{'type': 'text', 'text': json.dumps(payload)}]}}
    assert mcp_bridge.ownership_metadata(wrapped) == {}
    wrapped['raw']['adapterStatus'] = {'ownershipResolved': False}
    assert mcp_bridge.ownership_metadata(wrapped)['ownershipUnresolved'] is True
    assert 'ownershipUnresolved' in jobs._ownership_note({'error': 'ownership remains unresolved'})


def test_unresolved_primary_blocks_replay_even_with_budget_remaining(scope, monkeypatch):
    row, reserve, calls = scope
    row['providerBudget']['maxMcpToolCalls'] = 5
    real_rpc = mcp_bridge._rpc
    def rpc(method, params, **kwargs):
        result = real_rpc(method, params, **kwargs)
        if len(calls) == 2:
            return {'isError': True, 'content': [{'type': 'text', 'text': json.dumps({
                'success': False, 'error': 'missing session id',
                'result': {'ownershipUnresolved': True}})}]}
        return result  # A blind replay would falsely return success.
    monkeypatch.setattr(mcp_bridge, '_rpc', rpc)
    code, log = jobs._mcp_executor(action('get-function'), {'locator': 'project'}, threading.Event(), mcp_reserve=reserve)
    assert calls == ['open', 'get-function']
    assert code == 1 and jobs._ownership_unresolved(log)
    assert row['providerBudget']['consumed'] == 2


def test_scope_uncertainty_survives_any_executor_terminal_success(scope, monkeypatch):
    row, reserve, calls = scope
    def adapter(*_args, **_kwargs):
        mcp_budget.observe({'ownershipUnresolved': True})
        return 0, '{"success":true}'
    monkeypatch.setattr(jobs, '_mcp_executor_in_context', adapter)
    code, log = jobs._mcp_executor(action(), {}, threading.Event(), mcp_reserve=reserve)
    assert code == 1 and jobs._ownership_unresolved(log)
