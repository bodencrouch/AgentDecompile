"""Transport failures must not authorize another remote writer."""
import importlib.util
from pathlib import Path
import sys
import types

import pytest


@pytest.fixture
def bridge():
    path = Path(__file__).resolve().parents[1] / 'src/agentdecompile_recovery/corpus/dashboard/mcp_bridge.py'
    spec = importlib.util.spec_from_file_location('ownership_bridge', path)
    module = importlib.util.module_from_spec(spec)
    # KTD10 added a @dataclass (_PeerSession) to mcp_bridge; dataclass's
    # ClassVar/InitVar detection looks the defining module up in sys.modules,
    # so a module loaded via exec_module without being registered there first
    # crashes. Register it under its own name before executing, per the usual
    # importlib.util idiom.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def test_dispatched_timeout_preserves_unknown(bridge, monkeypatch):
    monkeypatch.setattr(bridge, '_ensure_initialized', lambda **kw: None)
    def timeout(*args, **kw):
        raise TimeoutError('response lost after dispatch')
    monkeypatch.setattr(bridge, '_rpc', timeout)
    result = bridge._call_tool('execute-script', {'script': 'mutation'})
    assert result['ok'] is False
    assert result['ownershipResolved'] is False
    assert result['ownershipUnresolved'] is True
    assert result['error'] == 'response lost after dispatch'


def test_initialization_failure_does_not_claim_tool_dispatch(bridge, monkeypatch):
    def timeout(**kw):
        raise TimeoutError('initialization unavailable')
    monkeypatch.setattr(bridge, '_ensure_initialized', timeout)
    monkeypatch.setattr(bridge, '_rpc', lambda *a, **kw: pytest.fail('must not dispatch'))
    result = bridge._call_tool('execute-script')
    assert not result['ok']
    assert 'ownershipUnresolved' not in result


def test_explicit_remote_uncertainty_survives_envelope(bridge, monkeypatch):
    monkeypatch.setattr(bridge, '_ensure_initialized', lambda **kw: None)
    monkeypatch.setattr(bridge, '_rpc', lambda *a, **kw: {'content': [{'type': 'text', 'text': '{"success":false,"ownershipResolved":false}'}]})
    assert bridge._call_tool('execute-script')['ownershipResolved'] is False


def test_confirmed_tool_rejection_does_not_invent_uncertainty(bridge, monkeypatch):
    monkeypatch.setattr(bridge, '_ensure_initialized', lambda **kw: None)
    monkeypatch.setattr(bridge, '_rpc', lambda *a, **kw: {'isError': True, 'content': [{'type': 'text', 'text': 'invalid arguments'}]})
    result = bridge._call_tool('execute-script')
    assert not result['ok']
    assert 'ownershipUnresolved' not in result


@pytest.mark.parametrize('kind', ['binary', 'local-project', 'shared-project'])
def test_uncertain_acquisition_stops_follow_on_checkout(bridge, monkeypatch, kind):
    project = types.ModuleType('agentdecompile_recovery.corpus.ghidra_project')
    project.classify_locator = lambda loc: {'ok': True, 'kind': kind}
    project.inspect_locator = project.classify_locator
    project.ghidra_program_path = lambda info, name: name
    project.ghidra_connect_args = lambda info: {'path': '/fixture'}
    project.parse_shared_locator = project.classify_locator
    project.shared_defaults = lambda: {}
    monkeypatch.setitem(sys.modules, project.__name__, project)
    calls = []
    def uncertain(*a, **kw):
        calls.append(a)
        return {'ok': False, 'error': 'lost response', 'ownershipResolved': False, 'ownershipUnresolved': True}
    monkeypatch.setattr(bridge, 'call_tool', uncertain)
    monkeypatch.setattr(bridge, 'ensure_project', uncertain)
    result = bridge.ensure_program('/fixture', 'program', inspected={'ok': True, 'kind': kind}, include_inventory=False)
    assert result['ownershipResolved'] is False
    assert len(calls) == 1
    # KTD10: _OPENED moved onto the per-peer _PeerSession; legacy callers
    # (no program_context) read/write _LEGACY_SESSION.opened.
    assert not bridge._LEGACY_SESSION.opened
