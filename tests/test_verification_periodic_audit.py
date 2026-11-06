"""Audit scheduling uses elapsed time, not fast no-op poll counts."""
import json
from agentdecompile_recovery.corpus import verify_periodic as periodic


def test_zero_full_every_and_elapsed_interval(tmp_path, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(periodic.time, 'time', lambda: now[0])
    calls = []
    monkeypatch.setattr(periodic.vbx, 'main', lambda argv: calls.append(list(argv)) or 0)
    argv = ['--out', str(tmp_path / 'receipt.json'), '--full-every', '0', '--full-interval-seconds', '3600']
    assert periodic.main(argv) == 0
    assert '--no-incremental' in calls[-1]
    for _ in range(8):
        now[0] += 1
        assert periodic.main(argv) == 0
        assert '--no-incremental' not in calls[-1]
    now[0] = 4600
    assert periodic.main(argv) == 0
    assert '--no-incremental' in calls[-1]


def test_failed_full_attempt_still_consumes_interval(tmp_path, monkeypatch):
    monkeypatch.setattr(periodic.time, 'time', lambda: 1000)
    calls = []
    monkeypatch.setattr(periodic.vbx, 'main', lambda argv: calls.append(list(argv)) or 2)
    argv = ['--out', str(tmp_path / 'receipt.json')]
    assert periodic.main(argv) == 2
    assert '--no-incremental' in calls[-1]
    assert periodic.main(argv) == 2
    assert '--no-incremental' not in calls[-1]
    assert periodic.main(argv + ['--force-full']) == 2
    assert '--no-incremental' in calls[-1]


def test_corrupt_audit_state_refuses_without_calling_verifier(tmp_path, monkeypatch):
    path = tmp_path / 'receipt.json.periodic-count.json'
    path.write_text('corrupt')
    calls = []
    monkeypatch.setattr(periodic.vbx, 'main', lambda argv: calls.append(argv) or 0)
    assert periodic.main(['--out', str(tmp_path / 'receipt.json')]) == 2
    assert not calls


def test_explicit_legacy_count_and_disabled_elapsed(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(periodic.vbx, 'main', lambda argv: calls.append(list(argv)) or 0)
    argv = ['--out', str(tmp_path / 'receipt.json'), '--full-every', '2', '--full-interval-seconds', '0']
    assert periodic.main(argv) == 0
    assert '--no-incremental' not in calls[-1]
    assert periodic.main(argv) == 0
    assert '--no-incremental' in calls[-1]


def test_clock_rollback_reanchors_without_full_audit_storm(tmp_path, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(periodic.time, 'time', lambda: now[0])
    calls = []
    monkeypatch.setattr(periodic.vbx, 'main', lambda argv: calls.append(list(argv)) or 0)
    argv = ['--out', str(tmp_path / 'receipt.json'), '--full-interval-seconds', '100']
    assert periodic.main(argv) == 0
    now[0] = 1
    assert periodic.main(argv) == 0
    assert '--no-incremental' not in calls[-1]
    now[0] = 101
    assert periodic.main(argv) == 0
    assert '--no-incremental' in calls[-1]


def test_unsupported_flock_refuses_before_audit_mutation(tmp_path, monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, 'fcntl', None)
    calls = []
    monkeypatch.setattr(periodic.vbx, 'main', lambda argv: calls.append(argv) or 0)
    assert periodic.main(['--out', str(tmp_path / 'receipt.json')]) == 2
    assert not calls
    assert not list(tmp_path.iterdir())
