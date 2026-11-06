"""Catalog reachability for objective allocations without launching a service."""
from agentdecompile_recovery.corpus.dashboard import preparation
from agentdecompile_recovery.corpus.dashboard import admission_budget
from agentdecompile_recovery.corpus.dashboard.actions import catalog, jobs


def test_prepare_catalog_forwards_initial_allocation(monkeypatch):
    calls = []
    monkeypatch.setattr(jobs, '_active_duplicate', lambda *_: None)
    monkeypatch.setattr(jobs, 'get_job', lambda *_: None)
    def submit(context, *, resume=False):
        calls.append((context, resume))
        return {'id': 'fixture', 'status': 'queued'}
    monkeypatch.setattr(preparation, 'submit', submit)
    response, status = jobs.start_job('workbench.prepare', {
        'locator': 'fixture', 'maxActionAdmissions': 0, 'resume': True,
    })
    assert status == 202 and response['run']['id'] == 'fixture'
    assert calls[0][0]['maxActionAdmissions'] == 0
    assert calls[0][1] is True


def test_allocation_revision_catalog_exposes_explicit_controls():
    action = catalog.action_by_id('workbench.workflow-control')
    fields = {field.name: field for field in action.fields}
    assert 'admission-budget' in fields['operation'].choices
    assert {'maxActionAdmissions', 'expectedAllocationRevision', 'unlimited'} <= fields.keys()
    params = catalog.apply_defaults(action, {
        'preparation_id': 'fixture', 'operation': 'admission-budget',
        'maxActionAdmissions': 3, 'expectedAllocationRevision': 1,
    })
    assert params['maxActionAdmissions'] == 3
    assert params['expectedAllocationRevision'] == 1
    assert not params.get('unlimited')


def test_revision_preserves_existing_queue_eligibility_and_control_projection(tmp_path, monkeypatch):
    monkeypatch.setattr(preparation, '_directory', lambda: tmp_path)
    run_id = 'd' * 32
    row = {'id': run_id, 'status': 'queued', 'admissionPending': True}
    admission_budget.initialize(row, 1)
    admission_budget.reserve(row, 'intent', 'basis', 'action')
    preparation._write(row)
    monkeypatch.setattr(preparation, '_WAITING', {run_id})
    revised = preparation.control({
        'preparation_id': run_id, 'operation': 'admission-budget',
        'expectedAllocationRevision': 1, 'maxActionAdmissions': 2,
    })
    assert revised['nextAction'] == 'wait_for_admission'
    assert revised['wakeCondition'] == 'admission_capacity'
    paused = preparation.control({'preparation_id': run_id, 'operation': 'pause'})
    assert paused['objectiveBudget']['consumed'] == 1
    assert 'reservations' not in paused['objectiveBudget']
    assert 'allocationHistory' not in paused['objectiveBudget']
    revised_paused = preparation.control({
        'preparation_id': run_id, 'operation': 'admission-budget',
        'expectedAllocationRevision': 2, 'maxActionAdmissions': 3,
    })
    assert revised_paused['nextAction'] == 'resume'
