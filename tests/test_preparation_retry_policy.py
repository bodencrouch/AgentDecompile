from __future__ import annotations

import json
from pathlib import Path

import pytest

from test_preparation_authority import authority_factory, resume

from agentdecompile_recovery.corpus.dashboard import preparation
from agentdecompile_recovery.corpus.dashboard.retry_policy import decide_retry, refusal_outcome
from agentdecompile_recovery.corpus.dashboard.workflow import transient_failure

pytestmark = pytest.mark.unit


def failure(attempts: int, error: str = 'connection refused') -> dict:
    return {'status': 'failed', 'attempts': attempts, 'result': {'ok': False, 'error': error}}


def test_resumed_failed_pair_never_resets_budget(authority_factory) -> None:
    run_id = 'a' * 32
    row = {'id': run_id, 'actions': {'basis-one': failure(3)}}
    authority = authority_factory(row)
    for _ in range(2):
        authority = resume(authority)
        resumed = authority.row
        prior = preparation._action_prior_for_retry('corpus.match-pair', resumed['actions']['basis-one'])
        decision = decide_retry(prior, transient=transient_failure(prior['result']))
        assert decision['nextAction'] == 'budget_exhausted'
        assert decision['attemptsSpent'] == 3
        assert decision['attemptsRemaining'] == 0
        outcome = refusal_outcome(prior, decision)
        assert '3/3' in outcome['error']
        assert outcome['previousError'] == 'connection refused'
        with preparation._guard(authority):
            preparation._remember_retry_decision(resumed, 'basis-one', 'corpus.match-pair', decision)
            preparation._write(resumed, authority=authority)
    assert preparation._read(run_id)['retryDecisions']['basis-one']['wakeCondition'] == 'changed_relevant_input_basis'


def test_transient_retry_under_limit_and_negative_result_have_distinct_eligibility() -> None:
    transient = failure(1)
    decision = decide_retry(transient, transient=transient_failure(transient['result']))
    assert (decision['nextAction'], decision['attemptsRemaining']) == ('dispatch', 2)
    deterministic = failure(1, 'unsupported target')
    assert decide_retry(deterministic, transient=transient_failure(deterministic['result']))['nextAction'] == 'wait_evidence'


@pytest.mark.parametrize('status', ['submitting', 'queued', 'running', 'interrupted', 'cancelling'])
def test_unknown_accepted_outcome_never_grants_duplicate_dispatch(status: str) -> None:
    prior = {'status': status, 'attempts': 1, 'jobId': 'accepted-job'}
    decision = decide_retry(prior, transient=True, prerequisite_recovered=True)
    assert decision['nextAction'] == 'unknown_outcome'
    assert refusal_outcome(prior, decision)['jobId'] == 'accepted-job'
    assert decide_retry(prior, owner_available=True)['nextAction'] == 'await_existing'


def test_relevant_new_basis_and_unrelated_task_can_progress_without_resetting_old() -> None:
    history = {'old-basis': failure(3)}
    old = decide_retry(history['old-basis'], transient=True)
    changed = decide_retry(history.get('changed-input-basis', {}))
    unrelated = decide_retry(history.get('independent-task', {}))
    assert old['nextAction'] == 'budget_exhausted'
    assert changed['nextAction'] == unrelated['nextAction'] == 'dispatch'
    assert history['old-basis']['attempts'] == 3


@pytest.mark.parametrize('spent, expected', [(1, 'dispatch'), (3, 'budget_exhausted')])
def test_repaired_bsim_launcher_preserves_budget(monkeypatch: pytest.MonkeyPatch, spent: int, expected: str) -> None:
    from agentdecompile_recovery.corpus import bsim_ops
    monkeypatch.setattr(bsim_ops, 'find_bsim_launcher', lambda: Path('/tool/support/bsim'))
    prior = failure(spent, 'Ghidra support/bsim not found (set GHIDRA_INSTALL_DIR)')
    prior['result']['data'] = {'returncode': 127, 'error': prior['result']['error']}
    observed = preparation._action_prior_for_retry('corpus.bsim-createdatabase', prior)
    decision = decide_retry(observed, prerequisite_recovered=bool(observed.get('retryPrerequisiteRecovered')))
    assert observed['attempts'] == spent
    assert decision['nextAction'] == expected
    assert 'retryPrerequisiteRecovered' not in prior


def test_decision_is_pure_and_invalid_accounting_refuses_dispatch() -> None:
    prior = failure(1)
    before = json.dumps(prior, sort_keys=True)
    assert decide_retry(prior, transient=True) == decide_retry(prior, transient=True)
    assert json.dumps(prior, sort_keys=True) == before
    assert decide_retry({'status': 'failed', 'attempts': 'corrupt'}, transient=True)['nextAction'] == 'unknown_outcome'


def test_public_projection_retains_blocked_decision_when_other_stage_runs() -> None:
    row = {'id': 'a' * 32, 'stages': [{'key': 'analysis', 'status': 'running'}]}
    decision = decide_retry(failure(3), transient=True)
    preparation._remember_retry_decision(row, 'failed-pair', 'corpus.match-pair', decision)
    public = preparation._public_run(row, live_jobs=[])
    assert public['retryDecisions']['failed-pair']['nextAction'] == 'budget_exhausted'
    assert public['stages'][0]['status'] == 'running'


@pytest.mark.parametrize('switch_workspace', [False, True])
@pytest.mark.parametrize('prior_status,spent,expected', [('failed', 3, 'budget_exhausted'), ('queued', 1, 'unknown_outcome'), ('interrupted', 1, 'unknown_outcome'), ('typed-reconciled', 1, 'unknown_outcome'), ('typed-terminal', 0, 'unknown_outcome')])
def test_preparation_execute_preserves_refusal_and_keeps_independent_work_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, prior_status: str, spent: int, expected: str, authority_factory, switch_workspace) -> None:
    """Exercise the real nested action path; all external jobs are inert fakes."""
    import hashlib
    import threading
    from types import SimpleNamespace
    from agentdecompile_recovery.corpus import corpus_config, ghidra_project
    from agentdecompile_recovery.corpus.dashboard import workflow
    from agentdecompile_recovery.corpus.dashboard.actions import jobs

    directory = tmp_path / 'preparations'
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
    monkeypatch.setattr(preparation, 'live_db', lambda: db)
    monkeypatch.setattr(preparation, '_read_control', lambda _id, **_: {})
    route_calls = []
    def bindings(*_, root=None, db=None):
        route_calls.append((root, db))
        assert root == tmp_path and db == tmp_path / 'corpus.sqlite'
        return {program: (locator, program)}
    monkeypatch.setattr(preparation, '_execution_program_bindings', bindings)
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

    def query(sql, *_, **kwargs):
        assert kwargs.get('db') == db
        if 'b.func_count,b.recovery_family,p.locator' in sql:
            return [(1, 'demo', 'source', 1, 'demo-family', locator, program)], None
        return [(1, 'demo', 'source', 'demo-family', 1, 'x86', 32, locator, program)], None

    monkeypatch.setattr(preparation, 'query_db', query)
    pair_fields = {'src': 'left', 'dst': 'right'}
    identity_parts = ['corpus.match-pair', pair_fields, ['left', 'right'], locator, program, 'demo', fingerprint, ['left', 'right']]
    exhausted_id = hashlib.sha256(json.dumps(identity_parts, sort_keys=True).encode()).hexdigest()
    if prior_status != 'typed-terminal':
        row['actions'][exhausted_id] = {**failure(spent), 'status': 'queued' if prior_status == 'typed-reconciled' else prior_status, 'jobId': 'lost-child'}
    authority = authority_factory(row)
    dispatched = []
    observed = []

    def start_job(name, fields, **kwargs):
        dispatched.append((name, dict(fields)))
        child_id = 'lost-child' if fields.get('src') == 'left' else 'healthy-child'
        return {'job': {'id': child_id, 'status': 'queued'}}, 202

    terminal = SimpleNamespace(id='healthy-child', status='ok', log='{}', error='',
                               started_at=1.0, finished_at=2.0, history_only=False, owner_unavailable=False)
    monkeypatch.setattr(jobs, 'start_job', start_job)
    quarantined = jobs.JobRecord(id='lost-child', action_id='corpus.match-pair', title='Quarantined', argv=[],
                                 status='ok', log='{"success":true,"ownershipResolved":true}\nlate metadata omitted',
                                 started_at=1.0, finished_at=2.0, resource_disposition='quarantined')
    monkeypatch.setattr(jobs, 'get_job', lambda _id: (quarantined if prior_status.startswith('typed-') else None) if _id == 'lost-child' else terminal)

    def continuation(current, root, database, action, update, **kwargs):
        refused = action('matching', 'corpus.match-pair', pair_fields, current)
        healthy = action('matching', 'corpus.match-pair', {'src': 'other', 'dst': 'right'}, current)
        observed.append((refused, healthy))

    monkeypatch.setattr(workflow, 'continue_recovery', continuation)
    other_root = tmp_path / 'other-workspace'
    other_root.mkdir()
    other_state = other_root / 'unrelated-control.json'
    other_state.write_text('{"priority":17}')
    other_before = other_state.read_bytes()
    for iteration in range(2):
        if iteration:
            authority = resume(authority)
        with monkeypatch.context() as patch:
            if switch_workspace:
                patch.setattr(preparation, 'live_root', lambda: other_root)
                patch.setattr(preparation, 'live_db', lambda: other_root / 'corpus.sqlite')
            preparation.execute({'preparation_id': run_id}, threading.Event(), authority=authority)
    assert len(route_calls) == 2
    assert other_state.read_bytes() == other_before
    assert not (other_root / 'preparations').exists()
    assert len(observed) == 2, preparation._read(run_id)
    assert all(refused['nextAction'] == expected and healthy['ok'] for refused, healthy in observed)
    expected_dispatches = [('corpus.match-pair', {'src': 'other', 'dst': 'right', '_preparationUnlimited': True, 'progress_json': True})]
    if prior_status == 'typed-terminal':
        expected_dispatches.insert(0, ('corpus.match-pair', {'src': 'left', 'dst': 'right', '_preparationUnlimited': True, 'progress_json': True}))
    assert dispatched == expected_dispatches
    saved = preparation._read(run_id)
    assert saved['actions'][exhausted_id]['attempts'] == (1 if prior_status == 'typed-terminal' else spent)
    assert preparation._public_run(saved)['retryDecisions'][exhausted_id]['nextAction'] == expected


@pytest.mark.parametrize('flag', ['ownershipUnresolved', 'unknownOutcome'])
def test_unknown_terminal_wrapper_does_not_become_retryable(flag: str) -> None:
    prior = failure(1)
    prior['result'][flag] = True
    assert decide_retry(prior, transient=True, prerequisite_recovered=True)['nextAction'] == 'unknown_outcome'


def test_successful_last_attempt_can_reuse_result_without_more_spending() -> None:
    prior = {'status': 'ok', 'attempts': 3, 'result': {'ok': True}}
    assert decide_retry(prior)['nextAction'] == 'reuse_result'


def test_prefixed_and_nested_terminal_logs_keep_ownership_warning() -> None:
    for raw in ['notice\n{"ownershipResolved":false}', 'notice\n{"ownershipResolved":false,"result":"{}"}']:
        data = preparation._decode_job_output(raw)
        assert preparation._unresolved_job_ownership(data)
    assert preparation._decode_job_output('malformed output') is None
    assert preparation._unresolved_job_ownership(None, {'ownershipUnresolved': True})
    assert not preparation._unresolved_job_ownership({'ownershipResolved': True}, {'ownershipUnresolved': True})


def test_unrelated_kb_touch_does_not_change_matching_retry_revision(tmp_path: Path) -> None:
    kb = tmp_path / 'knowledge.sqlite'
    kb.write_bytes(b'initial')
    fields = {'src': 'left', 'dst': 'right', 'kb': str(kb)}
    before = preparation._retry_input_revision('corpus.match-pair', fields)
    kb.write_bytes(b'unrelated program inventory changed')
    assert preparation._retry_input_revision('corpus.match-pair', fields) == before
    assert preparation._retry_input_revision('mcp.execute-script', fields) != before


def test_legacy_kb_based_attempts_are_carried_once_then_new_semantic_basis_is_eligible() -> None:
    fields = {'src': 'left', 'dst': 'right', 'kb': 'shared-kb'}
    history = {
        'old-kb-revision-1': {**failure(1), 'action': 'corpus.match-pair', 'params': fields},
        'old-kb-revision-2': {**failure(2), 'action': 'corpus.match-pair', 'params': fields},
    }
    migrated = preparation._matching_retry_prior(history, 'semantic-one', fields)
    assert migrated['attempts'] == 3
    assert decide_retry(migrated, transient=True)['nextAction'] == 'budget_exhausted'
    history['semantic-one'] = {**migrated, 'retryBasis': [{'digest': 'one'}]}
    assert preparation._matching_retry_prior(history, 'semantic-two', fields) == {}
    assert history['old-kb-revision-1']['attempts'] == 1
