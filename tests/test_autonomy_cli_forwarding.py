"""Public CLI/catalog reachability for supervision and cache controls; no workers."""
from agentdecompile_recovery.corpus import cli
from agentdecompile_recovery.corpus.dashboard.actions.introspect import corpus_specs


def test_supervision_controls_reach_executor(monkeypatch):
    from agentdecompile_recovery.corpus import recovery_orchestrator
    calls = []
    monkeypatch.setattr(recovery_orchestrator, 'main', lambda args: calls.append(args) or 0)
    args = ['recovery-orchestrator', '--program', 'fixture', '--repo', 'repo', '--db', '/tmp/db',
            '--out-dir', '/tmp/work', '--kb', '/tmp/kb', '--raw', '/tmp/raw', '--binary-id', '1',
            '--input-basis', 'fixture-v1', '--max-failed-exits', '2', '--nearmiss-workers', '1',
            '--backoff', '9', '--success-backoff', '15', '--stagger', '0', '--status']
    assert cli.main(args) == 0
    forwarded = calls[0]
    for flag, value in [('--input-basis', 'fixture-v1'), ('--max-failed-exits', '2'),
                        ('--backoff', '9.0'), ('--success-backoff', '15.0'),
                        ('--cascade-workers', '1'), ('--verify-workers', '1')]:
        assert forwarded[forwarded.index(flag)+1] == value
    assert '--status' in forwarded


def test_periodic_controls_reach_executor(monkeypatch):
    from agentdecompile_recovery.corpus import verify_periodic
    calls = []
    monkeypatch.setattr(verify_periodic, 'main', lambda args: calls.append(args) or 0)
    assert cli.main(['verify-periodic', '--verified-dir', '/tmp/source', '--raw', '/tmp/raw',
                     '--db', '/tmp/db', '--binary-id', '1', '--out', '/tmp/report',
                     '--compiler', '/tmp/compiler', '--cache-input-manifest', '/tmp/closure.json',
                     '--full-interval-seconds', '600', '--transient-retry-seconds', '90',
                     '--force-full']) == 0
    argv = calls[0]
    assert argv[argv.index('--full-every')+1] == '0'
    assert argv[argv.index('--full-interval-seconds')+1] == '600.0'
    assert argv[argv.index('--transient-retry-seconds')+1] == '90.0'
    assert argv[argv.index('--cache-input-manifest')+1] == '/tmp/closure.json'
    assert '--force-full' in argv


def test_catalog_exposes_same_controls():
    specs = {s.id: s for s in corpus_specs()}
    supervision = {f.name: f for f in specs['corpus.recovery-orchestrator'].fields}
    assert {'input-basis', 'max-failed-exits', 'status', 'once', 'nearmiss-workers'} <= supervision.keys()
    assert supervision['cascade-workers'].default == 1
    for action in ['corpus.verify-byteexact', 'corpus.verify-periodic']:
        fields = {f.name for f in specs[action].fields}
        assert {'cache-input-manifest', 'transient-retry-seconds'} <= fields


def test_catalog_supervisor_declares_mutation_and_resource_scope():
    action = {s.id: s for s in corpus_specs()}['corpus.recovery-orchestrator']
    assert action.mutating and action.long_running
    assert action.identity_scope == 'database'
    assert action.ghidra_exclusive
