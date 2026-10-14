"""Capability wake mechanics with real local signatures; no recovery backend."""
import copy
import json
import threading
import time
from types import SimpleNamespace

import pytest

from agentdecompile_grid.config import GridConfig
from agentdecompile_grid.log.signing import Ed25519Signer
from agentdecompile_grid.objects.local import LocalDirStore
from agentdecompile_grid.verify.policy import RevocationList
from agentdecompile_recovery.corpus.dashboard import capability_continuation as caps
from agentdecompile_recovery.corpus.dashboard import preparation as prep, protection


@pytest.fixture
def accepted(tmp_path, monkeypatch):
    grid = tmp_path / 'grid'
    monkeypatch.setenv('ADGRID_HOME', str(grid))
    monkeypatch.delenv('ADGRID_CONFIG', raising=False)
    config = GridConfig.load(env={'ADGRID_HOME': str(grid)})
    monkeypatch.setattr(GridConfig, 'load', classmethod(lambda cls: config))
    signers = [Ed25519Signer.generate(tmp_path / name) for name in ('producer', 'reviewer')]
    trusted = grid / 'keys' / 'trusted'
    trusted.mkdir(parents=True)
    for index, signer in enumerate(signers):
        (trusted / f'{index}.pub').write_bytes(signer.public_bytes)
    store = LocalDirStore.from_config(config)
    RevocationList().save(store)
    source = tmp_path / 'input.exe'
    source.write_bytes(b'owned fixture, not an executable')
    tool = tmp_path / 'upx'
    tool.write_bytes(b'owned fixture handler')
    monkeypatch.setattr(protection.shutil, 'which', lambda name: str(tool) if name == 'upx' else None)
    evidence = tmp_path / 'qualified.json'
    evidence.write_text('{"scope":"unit fixture only"}')
    manifest = protection.capability_manifest('UPX')
    claim = {'policy': caps.POLICY, 'outcome': 'accepted', 'capability': 'protection:UPX',
             'preparationId': 'a' * 32, 'program': '/program', 'inputSha256': caps.digest_file(source),
             'revision': manifest['revision'], 'artifacts': manifest['artifacts'],
             'evidence': [{'path': str(evidence), 'sha256': caps.digest_file(evidence)}],
             'expiresAt': time.time() + 600}
    def sign(claim):
        return {'claim': claim, **{role: {'key': signer.key_id,
                'signature': signer.sign(caps.attestation_bytes(claim, role))}
                for role, signer in zip(('producer', 'reviewer'), signers)}}
    directory = tmp_path / 'preparations'
    directory.mkdir()
    monkeypatch.setattr(prep, '_directory', lambda: directory)
    monkeypatch.setattr(prep, '_read_control', lambda key: {})
    monkeypatch.setattr(prep, '_ACTIVE', set())
    monkeypatch.setattr(prep, '_WAITING', set())
    monkeypatch.setattr(prep, '_LEASES', {})
    row = {'id': 'a' * 32, 'status': 'blocked', 'locator': '/fixture/project.gpr',
           'program': '', 'slug': '', 'actions': {}, 'checkpoints': {}, 'events': [], 'stages': []}
    observed = {'handling': 'blocked', 'sourceSha256': claim['inputSha256'],
                'detection': {'protector': 'UPX'}, 'capabilityRevision': '0' * 64}
    checkpoint = {'protection': observed, 'executablePath': str(source), 'analysisConfirmed': True,
                  'factsComplete': True, 'blockedRequirement': caps.blocked_requirement(row, '/program', observed)}
    row['checkpoints']['/program'] = checkpoint
    prep._write(row)
    return SimpleNamespace(envelope=sign(claim), sign=sign, signers=signers, row=row, source=source,
                           tool=tool, evidence=evidence, directory=directory, store=store, trusted=trusted)


def test_verified_publication_deduplicates_and_retains_signed_evidence(accepted):
    a = accepted
    key = caps.publish(a.directory, a.envelope)
    assert caps.publish(a.directory, a.envelope) == key
    assert len(list((a.directory / 'capabilities').glob('*.json'))) == 1
    assert caps.verify(caps.read_event(a.directory, key)) == a.envelope['claim']


@pytest.mark.parametrize('failure', ['signature', 'self-review', 'untrusted', 'revoked', 'artifact', 'evidence', 'expiry'])
def test_acceptance_fails_closed(accepted, failure):
    a = accepted
    envelope = copy.deepcopy(a.envelope)
    if failure == 'signature':
        envelope['claim']['program'] = '/other'
    elif failure == 'self-review':
        envelope['reviewer'] = {'key': a.signers[0].key_id,
            'signature': a.signers[0].sign(caps.attestation_bytes(envelope['claim'], 'reviewer'))}
    elif failure == 'untrusted':
        (a.trusted / '1.pub').unlink()
    elif failure == 'revoked':
        RevocationList({a.signers[1].key_id: {'reason': 'unit revocation'}}).save(a.store)
    elif failure == 'artifact':
        a.tool.write_bytes(b'changed handler')
    elif failure == 'evidence':
        a.evidence.write_text('changed qualification')
    else:
        envelope['claim']['expiresAt'] = 0
        envelope = a.sign(envelope['claim'])
    with pytest.raises(ValueError):
        caps.publish(a.directory, envelope)
    assert not (a.directory / 'capabilities').exists()


def test_input_and_unchanged_basis_do_not_wake(accepted):
    a = accepted
    caps.check_wait(a.row, '/program', a.envelope['claim'])
    a.row['checkpoints']['/program']['blockedRequirement']['observedRevision'] = a.envelope['claim']['revision']
    with pytest.raises(ValueError, match='unchanged'):
        caps.check_wait(a.row, '/program', a.envelope['claim'])
    a.row['checkpoints']['/program']['blockedRequirement']['observedRevision'] = '0' * 64
    a.source.write_bytes(b'changed input')
    with pytest.raises(ValueError, match='bytes changed'):
        caps.check_wait(a.row, '/program', a.envelope['claim'])


@pytest.mark.parametrize('failure', ['pause', 'stop', 'deadline', 'unknown-effect', 'budget'])
def test_admission_refusal_is_durable_and_replay_remains_available(accepted, monkeypatch, failure):
    a = accepted
    key = caps.publish(a.directory, a.envelope)
    if failure in ('pause', 'stop'):
        monkeypatch.setattr(prep, '_read_control', lambda key: {'operation': failure})
    elif failure == 'deadline':
        a.row['deadline'] = time.time() - 1
    elif failure == 'unknown-effect':
        a.row['actions'] = {'old': {'status': 'failed', 'result': {'unknownOutcome': True}}}
    else:
        prep.admission_budget.initialize(a.row, 0)
    assert not prep._apply_capability_event(a.row, key)
    stored = prep._read(a.row['id'])
    assert stored['capabilityContinuation']['state'] == 'refused'
    assert key not in stored.get('capabilityEvents', {})
    assert stored['checkpoints']['/program']['analysisConfirmed']


def test_reconciliation_uses_submit_then_persisted_event_cursor(accepted, monkeypatch):
    a = accepted
    key = caps.publish(a.directory, a.envelope)
    calls = []
    def submit(context, **kwargs):
        calls.append((context, kwargs))
        row = prep._read(a.row['id'])
        assert prep._apply_capability_event(row, context['_capabilityEvent'])
        prep._write(row)
    monkeypatch.setattr(prep, 'submit', submit)
    prep._collect_capability_admissions()
    prep._collect_capability_admissions()
    assert len(calls) == 1
    assert calls[0][1] == {'resume': True, '_admit': True}
    assert calls[0][0]['_capabilityEvent'] == key


def test_handler_attempt_preserves_other_checkpoints_and_spending(accepted, monkeypatch):
    a = accepted
    key = caps.publish(a.directory, a.envelope)
    assert prep._apply_capability_event(a.row, key)
    checkpoint = a.row['checkpoints']['/program']
    old = copy.deepcopy(checkpoint['protection'])
    calls = []
    def handler(path, output, **kwargs):
        calls.append(kwargs)
        assert prep._read(a.row['id'])['capabilityEvents'][key]['state'] == 'handler-intent'
        return {**old, 'capabilityRevision': a.envelope['claim']['revision'], 'reason': 'still blocked'}
    monkeypatch.setattr(protection, 'prepare_protected_binary', handler)
    monkeypatch.setattr(prep, 'live_root', lambda: a.directory.parent)
    prep._refresh_protection_capability(a.row, '/program', checkpoint)
    assert checkpoint['protectionHistory'] == [old]
    assert checkpoint['analysisConfirmed'] and checkpoint['factsComplete']
    assert a.row['objectiveBudget']['consumed'] == 1
    assert checkpoint['blockedRequirement']['observedRevision'] == a.envelope['claim']['revision']
    assert len(calls) == 1
    assert calls[0]['expected_source_sha256'] == a.envelope['claim']['inputSha256']
    with pytest.raises(ValueError, match='unchanged'):
        caps.check_wait(a.row, '/program', a.envelope['claim'])


def test_crash_after_handler_intent_does_not_repeat_effect(accepted, monkeypatch):
    a = accepted
    key = caps.publish(a.directory, a.envelope)
    assert prep._apply_capability_event(a.row, key)
    a.row['capabilityEvents'][key]['state'] = 'handler-intent'
    monkeypatch.setattr(protection, 'prepare_protected_binary', lambda *a, **k: pytest.fail('repeated unknown effect'))
    checkpoint = a.row['checkpoints']['/program']
    prep._refresh_protection_capability(a.row, '/program', checkpoint)
    assert checkpoint['blockedRequirement']['state'] == 'refused'
    assert 'unknown' in checkpoint['blockedRequirement']['reason']


def test_catalog_publisher_executes_signed_acceptance_in_durable_job(accepted, monkeypatch):
    from agentdecompile_recovery.corpus.dashboard.actions import catalog, jobs, job_history
    from agentdecompile_recovery.corpus.dashboard.actions.openapi import model_for
    a = accepted
    action = catalog.action_by_id('workbench.publish-capability')
    assert action is not None and action.mutating
    schema = model_for(action).model_json_schema()
    assert schema['properties']['envelope']['anyOf'][0]['type'] == 'object'
    assert catalog.validate_params(action, {'envelope': a.envelope}, confirm=False)
    monkeypatch.setattr(threading.Thread, 'start', lambda self: None)
    monkeypatch.setattr(jobs, 'live_root', lambda: a.directory.parent)
    monkeypatch.setattr(job_history, 'directory', lambda: a.directory.parent / 'jobs')
    monkeypatch.setattr(prep, '_start_admission_worker', lambda: None)
    service = jobs.JobStore()
    try:
        job = service.start(action, {'envelope': a.envelope}, catalog.build_command(action, {'envelope': a.envelope}))
        service._run(job.id, service._cancels[job.id])
        finished = service.get(job.id)
        assert finished.status == 'ok', finished.log
        result = json.loads(finished.log)
        assert result['status'] == 'accepted-for-reconciliation'
        assert caps.read_event(a.directory, result['eventId']) == a.envelope
    finally:
        if service._resource_owner_handle is not None:
            service._resource_owner_handle.close()


def test_unpacked_image_retains_explicit_binding_prerequisite(accepted, monkeypatch):
    a = accepted
    key = caps.publish(a.directory, a.envelope)
    assert prep._apply_capability_event(a.row, key)
    checkpoint = a.row['checkpoints']['/program']
    monkeypatch.setattr(protection, 'prepare_protected_binary', lambda *args, **kwargs: {
        'handling': 'unpacked', 'analysisPath': '/derived.exe', 'derivedSha256': 'd' * 64})
    monkeypatch.setattr(prep, 'live_root', lambda: a.directory.parent)
    prep._refresh_protection_capability(a.row, '/program', checkpoint)
    assert checkpoint['blockedRequirement']['capability'] == 'derived-image-binding'
    assert checkpoint['blockedRequirement']['nextAction'] == 'bind_verified_derived_image'
    assert checkpoint['analysisConfirmed'] and checkpoint['factsComplete']  # retained original evidence only
    assert prep._protection_blocks_analysis(checkpoint['protection'])


def test_real_submit_retries_known_predispatch_failure_once(accepted, monkeypatch):
    import hashlib
    from agentdecompile_recovery.corpus.dashboard.actions import jobs, job_history
    a = accepted
    monkeypatch.setattr(prep, 'live_db', lambda: '/fixture/db')
    monkeypatch.setattr(prep, '_project_context', lambda context: context)
    monkeypatch.setattr(prep, 'list_runs', lambda: [])
    monkeypatch.setattr(prep, '_merge_legacy_contexts', lambda *args: None)
    monkeypatch.setattr(prep, '_inventory_request', lambda key: {})
    monkeypatch.setattr(threading.Thread, 'start', lambda self: None)
    monkeypatch.setattr(jobs, 'live_root', lambda: a.directory.parent)
    monkeypatch.setattr(job_history, 'directory', lambda: a.directory.parent / 'jobs')
    identity = hashlib.sha256(json.dumps(['/fixture/db', a.row['locator'], '', '']).encode()).hexdigest()[:32]
    a.row['id'] = identity
    a.row['checkpoints']['/program']['blockedRequirement']['preparationId'] = identity
    claim = dict(a.envelope['claim'], preparationId=identity)
    prep._write(a.row)
    key = caps.publish(a.directory, a.sign(claim))
    service = jobs.JobStore()
    monkeypatch.setattr(jobs, 'STORE', service)
    original = service._persist_locked
    calls = []
    def fail_first(job, **kwargs):
        calls.append(job.id)
        if len(calls) == 1:
            raise OSError('temporary persistence failure')
        return original(job, **kwargs)
    monkeypatch.setattr(service, '_persist_locked', fail_first)
    try:
        prep._collect_capability_admissions()
        row = prep._read(identity)
        assert row['capabilityEvents'][key]['state'] == 'admission-retry'
        assert row['capabilityEvents'][key]['knownNotDispatched']
        count = len(calls)
        prep._collect_capability_admissions()
        assert len(calls) == count  # backoff survives re-observation
        row['capabilityEvents'][key]['retryAfter'] = 0
        prep._write(row)
        prep._collect_capability_admissions()
        row = prep._read(identity)
        assert row['status'] == 'queued' and row['jobId']
        assert row['capabilityEvents'][key]['state'] == 'admission-intent'
        count = len(calls)
        prep._collect_capability_admissions()
        assert len(calls) == count
    finally:
        prep._ACTIVE.discard(identity)
        prep._release_lease(identity)
        if service._resource_owner_handle is not None:
            service._resource_owner_handle.close()
