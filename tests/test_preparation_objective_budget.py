import json
from pathlib import Path

import pytest

from agentdecompile_recovery.corpus.dashboard import preparation, admission_budget as budget


def test_migration_unknown_history_and_idempotent_ack():
    row = {'id':'objective', 'actions':{'prior':{'attempts':3}}}
    budget.initialize(row,2)
    assert row['objectiveBudget']['priorUsageUnknown']
    assert budget.reserve(row,'one','basis','action')['nextAction']=='dispatch'
    budget.acknowledge(row,'one','job')
    budget.acknowledge(row,'one','job')
    assert row['objectiveBudget']['consumed']==1
    budget.reserve(row,'two','changed','other-wrapper')
    assert budget.reserve(row,'three','new','new-wrapper')['nextAction']=='objective_budget_exhausted'
    budget.initialize(row,999)
    assert row['objectiveBudget']['maxActionAdmissions']==2


def test_unlimited_still_accounts_and_corrupt_state_refuses():
    row = {'id':'objective'}
    for number in range(5):
        budget.reserve(row,str(number),'basis','action')
    assert row['objectiveBudget']['consumed']==5
    assert row['objectiveBudget']['maxActionAdmissions'] is None
    row['objectiveBudget']['consumed']=0
    with pytest.raises(ValueError):
        budget.reserve(row,'new','basis','action')


@pytest.mark.parametrize('fail_intent', [False, True, 'ack'])
def test_real_dispatch_objective_limit_survives_changed_basis_and_resume(tmp_path, monkeypatch, fail_intent):
    """Exercise the real nested action path; all external jobs are inert fakes."""
    import hashlib
    import threading
    from types import SimpleNamespace
    from agentdecompile_recovery.corpus import corpus_config, ghidra_project
    from agentdecompile_recovery.corpus.dashboard import workflow
    from agentdecompile_recovery.corpus.dashboard.actions import jobs

    directory = tmp_path / 'preparations'
    directory.mkdir()
    locator, program, fingerprint = 'local-project', 'Demo.exe', 'image-one'
    run_id = 'b' * 32
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
    pair_fields = {'src': 'left', 'dst': 'right'}
    identity_parts = ['corpus.match-pair', pair_fields, ['left', 'right'], locator, program, 'demo', fingerprint, ['left', 'right']]
    exhausted_id = hashlib.sha256(json.dumps(identity_parts, sort_keys=True).encode()).hexdigest()
    row['maxActionAdmissions'] = 1
    preparation._write(row)
    dispatched = []
    observed = []

    def start_job(name, fields, **kwargs):
        persisted = preparation._read(run_id)
        assert persisted['objectiveBudget']['consumed'] == 1
        assert next(iter(persisted['objectiveBudget']['reservations'].values()))['status'] == 'intent'
        dispatched.append((name, dict(fields)))
        child_id = 'lost-child' if fields.get('src') == 'left' else 'healthy-child'
        return {'job': {'id': child_id, 'status': 'queued'}}, 202

    terminal = SimpleNamespace(id='healthy-child', status='ok', log='{}', error='',
                               started_at=1.0, finished_at=2.0, history_only=False, owner_unavailable=False)
    monkeypatch.setattr(jobs, 'start_job', start_job)
    monkeypatch.setattr(jobs, 'get_job', lambda _id: terminal)

    def continuation(current, root, database, action, update, **kwargs):
        first = action('matching', 'corpus.match-pair', pair_fields, current)
        changed = action('matching', 'corpus.match-pair', {'src':'new-hypothesis','dst':'right'}, current)
        wrapper = action('matching', 'corpus.other-wrapper', {'src':'other'}, current)
        observed.append((first, changed, wrapper))
    monkeypatch.setattr(workflow, 'continue_recovery', continuation)
    if fail_intent is True:
        original_write = preparation._write
        def fail_before_dispatch(value):
            if value.get('objectiveBudget', {}).get('consumed', 0):
                raise OSError('intent store unavailable')
            original_write(value)
        monkeypatch.setattr(preparation, '_write', fail_before_dispatch)
        try:
            preparation.execute({'preparation_id': run_id}, threading.Event())
        except OSError:
            pass
        assert not dispatched
        return
    if fail_intent == 'ack':
        original_write = preparation._write
        def fail_after_dispatch(value):
            if dispatched:
                raise OSError('acknowledgment store unavailable')
            original_write(value)
        monkeypatch.setattr(preparation, '_write', fail_after_dispatch)
        try:
            preparation.execute({'preparation_id': run_id}, threading.Event())
        except OSError:
            pass
        monkeypatch.setattr(preparation, '_write', original_write)
        persisted = preparation._read(run_id)
        assert persisted['objectiveBudget']['consumed'] == 1
        assert next(iter(persisted['objectiveBudget']['reservations'].values()))['status'] == 'intent'
        preparation.execute({'preparation_id': run_id}, threading.Event())
        assert len(dispatched) == 1
        assert preparation._read(run_id)['objectiveBudget']['consumed'] == 1
        return
    for _ in range(2):
        preparation.execute({'preparation_id': run_id}, threading.Event())
    assert len(dispatched) == 1
    assert all(first['ok'] and changed['nextAction']=='objective_budget_exhausted'
               and wrapper['nextAction']=='objective_budget_exhausted' for first,changed,wrapper in observed)
    saved = preparation._read(run_id)
    assert saved['objectiveBudget']['consumed'] == 1
    assert len(saved['objectiveBudget']['reservations']) == 1
    assert preparation._public_run(saved)['objectiveBudget']['consumed'] == 1



def test_competing_admissions_share_final_slot_and_independent_objective():
    import threading
    row = {'id':'shared'}
    budget.initialize(row,1)
    outcomes = []
    def attempt(number):
        with preparation._LOCK:
            outcomes.append(budget.reserve(row,str(number),'basis'+str(number),'action'))
    threads = [threading.Thread(target=attempt,args=(number,)) for number in range(2)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    assert sorted(item['nextAction'] for item in outcomes) == ['dispatch','objective_budget_exhausted']
    independent = {'id':'independent'}
    budget.initialize(independent,1)
    assert budget.reserve(independent,'new','basis','action')['nextAction']=='dispatch'


def test_allocation_control_cas_preserves_spending_and_bounds_public_receipt(tmp_path, monkeypatch):
    monkeypatch.setattr(preparation, '_directory', lambda: tmp_path)
    row = {'id':'a'*32, 'status':'blocked'}
    budget.initialize(row, 1)
    budget.reserve(row, 'intent', 'basis', 'action')
    preparation._write(row)
    params = {'preparation_id':row['id'], 'operation':'admission-budget',
              'expectedAllocationRevision':1, 'maxActionAdmissions':3}
    result = preparation.control(params)
    assert result['objectiveBudget']['allocationRevision'] == 2
    assert result['objectiveBudget']['consumed'] == 1
    assert 'reservations' not in result['objectiveBudget']
    assert 'allocationHistory' not in result['objectiveBudget']
    assert result['nextAction'] == 'resume'
    with pytest.raises(ValueError, match='revision changed'):
        preparation.control(params)
    with pytest.raises(ValueError, match='explicit unlimited'):
        preparation.control({**params, 'expectedAllocationRevision':2, 'maxActionAdmissions':None})
    result = preparation.control({**params, 'expectedAllocationRevision':2,
                                  'maxActionAdmissions':None, 'unlimited':True})
    assert result['objectiveBudget']['maxActionAdmissions'] is None
    saved = preparation._read(row['id'])
    assert saved['objectiveBudget']['reservations'] == row['objectiveBudget']['reservations']
    assert saved['objectiveBudget']['allocationRevision'] == 3


def test_allocation_control_refuses_active_and_other_owner(tmp_path, monkeypatch):
    monkeypatch.setattr(preparation, '_directory', lambda: tmp_path)
    row = {'id':'c'*32, 'status':'blocked'}
    budget.initialize(row, 1)
    preparation._write(row)
    params = {'preparation_id':row['id'], 'operation':'admission-budget',
              'expectedAllocationRevision':1, 'maxActionAdmissions':2}
    monkeypatch.setattr(preparation, '_ACTIVE', {row['id']})
    with pytest.raises(ValueError, match='Pause and drain'):
        preparation.control(params)
    monkeypatch.setattr(preparation, '_ACTIVE', set())
    with (tmp_path / (row['id']+'.lock')).open('a+') as owner:
        preparation._lock_lease(owner)
        with pytest.raises(ValueError, match='active coordinator'):
            preparation.control(params)
    assert preparation._read(row['id'])['objectiveBudget']['allocationRevision'] == 1
