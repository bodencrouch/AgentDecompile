"""Probe provenance regressions; fake Program observations, no JVM or backend."""
import ast
import json
import sys
import time
from pathlib import Path
from types import ModuleType, SimpleNamespace

SOURCE = Path(__file__).parents[1] / 'src/agentdecompile_recovery/corpus/dashboard/preparation.py'


def helpers():
    tree = ast.parse(SOURCE.read_text())
    names = {'_same_program_path', '_discard_unverified_probe', '_accept_probe', '_decode_job_output', '_inventory_identity_matches'}
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    namespace = {'Any': object, 'time': time, 'json': json}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), 'exec'), namespace)
    return namespace


def test_probe_observes_program_instead_of_injected_request(monkeypatch):
    tree = ast.parse(SOURCE.read_text())
    code = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == '_ANALYSIS_PROBE' for t in node.targets))
    framework = ModuleType('ghidra.framework')
    framework.Application = SimpleNamespace(getApplicationVersion=lambda: 'test')
    monkeypatch.setitem(sys.modules, 'ghidra', ModuleType('ghidra'))
    monkeypatch.setitem(sys.modules, 'ghidra.framework', framework)
    program = SimpleNamespace(getDomainFile=lambda: SimpleNamespace(getPathname=lambda: '/JadeEmpire'),
        getName=lambda: 'JadeEmpire', getExecutableMD5=lambda: 'ab' * 16,
        getExecutableSHA256=lambda: 'cd' * 32, getExecutablePath=lambda: '/real/JadeEmpire.exe',
        getLanguageID=lambda: 'x86', getFunctionManager=lambda: SimpleNamespace(getFunctionCount=lambda: 16186))
    scope = {'currentProgram': program, 'programPath': '/K1/game.exe'}
    exec(code, scope)
    payload = json.loads(scope['__result__'])
    assert payload['programPath'] == '/JadeEmpire'
    assert payload['requestedProgramPath'] == '/K1/game.exe'
    assert payload['programName'] == 'JadeEmpire'
    assert payload['executableMD5'] == 'ab' * 16
    assert not helpers()['_accept_probe']({}, '/K1/game.exe', payload)


def test_wrapper_path_cannot_overwrite_observation():
    result = helpers()['_decode_job_output'](json.dumps({'executedProgram': {'path': '/K1/game.exe'},
        'result': json.dumps({'identityVersion': 2, 'programPath': '/JadeEmpire'})}))
    assert result['programPath'] == '/JadeEmpire'
    assert result['invocationProgramPath'] == '/K1/game.exe'


def test_failed_new_probe_invalidates_previously_matching_checkpoint():
    checkpoint = {'probeIdentityVersion': 2, 'observedProgramPath': '/K1/game.exe', 'analysisConfirmed': True}
    assert not helpers()['_accept_probe'](checkpoint, '/K1/game.exe', {'identityVersion': 2, 'programPath': '/JadeEmpire'})
    assert 'analysisConfirmed' not in checkpoint
    assert checkpoint['probeMismatch']['observedProgramPath'] == '/JadeEmpire'


def test_legacy_receipt_requires_observation_but_preserves_evidence():
    checkpoint = {'observedProgramPath': '/K1/game.exe', 'analysisConfirmed': True,
                  'workflow': {'status': 'partial'}, 'protection': {'handling': 'blocked'}}
    assert helpers()['_discard_unverified_probe'](checkpoint, '/K1/game.exe')
    assert 'workflow' not in checkpoint
    assert checkpoint['legacyProbeEvidence']['workflow'] == {'status': 'partial'}
    assert checkpoint['legacyProbeEvidence']['analysisConfirmed'] is True
    assert checkpoint['legacyProbeEvidence']['protection'] == {'handling': 'blocked'}
    assert checkpoint['analysisConfirmed'] is False


def test_request_only_and_unproven_snapshot_fail_closed():
    accept = helpers()['_accept_probe']
    assert not accept({}, '/K1/game.exe', {'programPath': '/K1/game.exe'})
    assert not accept({}, '/K1/game.exe', {'identityVersion': 2, 'programPath': '/Untitled',
        'requestedProgramPath': '/K1/game.exe', 'executableMD5': 'ab' * 16})
    assert accept({}, '/K1/game.exe', {'identityVersion': 2, 'programPath': '/K1/game.exe'})


def test_inventory_maps_preserve_binding_columns():
    tree = ast.parse(SOURCE.read_text())
    maps = [node for node in ast.walk(tree) if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id in {'inventory_by_binding', 'inventory_by_source'} for t in node.targets)]
    record = (8, 'K1', '/repos/K1/game.exe', 24242, '', '/repos', '/K1/game.exe')
    scope = {'inventory_rows': [record], 'Path': Path}
    exec(compile(ast.Module(body=maps, type_ignores=[]), str(SOURCE), 'exec'), scope)
    assert scope['inventory_by_binding'][('/repos', 'K1/game.exe')] == record
    assert scope['inventory_by_source']['/repos/K1/game.exe'] == record


def test_missing_observation_cannot_keep_prior_acceptance():
    checkpoint = {'probeIdentityVersion': 2, 'observedProgramPath': '/K1/game.exe', 'analysisConfirmed': True}
    assert not helpers()['_accept_probe'](checkpoint, '/K1/game.exe', {})
    assert 'analysisConfirmed' not in checkpoint


def test_fresh_probe_cannot_reactivate_legacy_wrong_object_fingerprint():
    api = helpers()
    checkpoint = {'observedProgramPath': '/K1/game.exe', 'programFingerprint': 'jade-md5',
        'bsimComplete': True, 'bsimFingerprint': 'jade-md5', 'factsComplete': True,
        'knowledgeComplete': True, 'workflow': {'status': 'completed'}}
    api['_discard_unverified_probe'](checkpoint, '/K1/game.exe')
    assert api['_accept_probe'](checkpoint, '/K1/game.exe', {'identityVersion': 2,
        'programPath': '/K1/game.exe', 'executableMD5': 'k1-md5', 'needsAnalysis': False})
    assert checkpoint['programFingerprint'] == 'k1-md5'
    assert checkpoint['needsAnalysis'] is False
    for field in ('bsimComplete', 'bsimFingerprint', 'factsComplete', 'knowledgeComplete', 'workflow'):
        assert field not in checkpoint
    assert checkpoint['legacyProbeEvidence']['programFingerprint'] == 'jade-md5'


def test_rejected_probe_preserves_prior_evidence_and_rejection_payload():
    checkpoint = {'probeIdentityVersion': 2, 'observedProgramPath': '/K1/game.exe',
        'programFingerprint': 'old-md5', 'workflow': {'status': 'completed'}}
    payload = {'identityVersion': 2, 'programPath': '/Other', 'executableMD5': 'other-md5'}
    assert not helpers()['_accept_probe'](checkpoint, '/K1/game.exe', payload)
    assert checkpoint['probeEvidenceHistory'][0]['workflow'] == {'status': 'completed'}
    assert checkpoint['probeMismatch']['payload'] == payload
    assert 'workflow' not in checkpoint
    assert 'programFingerprint' not in checkpoint


def test_same_path_changed_bytes_quarantines_prior_acceptance():
    checkpoint = {'probeIdentityVersion': 2, 'observedProgramPath': '/K1/game.exe',
        'programFingerprint': 'old-md5', 'bsimComplete': True}
    assert helpers()['_accept_probe'](checkpoint, '/K1/game.exe', {'identityVersion': 2,
        'programPath': '/K1/game.exe', 'executableMD5': 'new-md5', 'needsAnalysis': False})
    assert checkpoint['programFingerprint'] == 'new-md5'
    assert 'bsimComplete' not in checkpoint
    assert checkpoint['probeEvidenceHistory'][0]['programFingerprint'] == 'old-md5'


def test_inventory_reuse_requires_consistent_valid_hashes():
    matches = helpers()['_inventory_identity_matches']
    md5, sha = 'ab' * 16, 'cd' * 32
    row = (8, 'K1', '/repos/K1/game.exe', 24242, '', '/repos', '/K1/game.exe', md5, sha)
    assert matches({'executableMD5': md5, 'executableSHA256': sha}, row)
    assert matches({'executableMD5': md5}, row)
    assert matches({'executableSHA256': sha}, row)
    assert not matches({'executableMD5': md5, 'executableSHA256': 'ef' * 32}, row)
    assert not matches({'executableMD5': 'ef' * 16, 'executableSHA256': sha}, row)
    assert not matches({}, row)
    assert not matches({'executableMD5': 'invalid'}, row)
    assert not matches({'executableMD5': md5}, row[:7] + (None, None))


def test_blocked_inventory_cannot_reenter_matching_candidates_by_path():
    tree = ast.parse(SOURCE.read_text())
    names = {'prepared_ids', 'prepared_sources', 'candidates'}
    nodes = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id in names for t in n.targets)]
    program = '/repos/K1/game.exe'
    scope = {'programs': [program], 'protection_blocked': {program},
        'row': {'checkpoints': {program: {'analysisConfirmed': True, 'factsComplete': True,
              'binaryId': 8, 'unverifiedInventory': {'reason': 'hash mismatch'}}}},
        'records': [(8, 'K1', program)], 'existing_by_source': {program: (8, 'K1', program)}}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), 'exec'), scope)
    assert scope['prepared_ids'] == set()
    assert scope['prepared_sources'] == set()
    assert scope['candidates'] == []


def test_rejected_endpoint_cannot_enter_explicit_pairs_through_valid_peer():
    import textwrap
    source = SOURCE.read_text()
    start = source.index('        rejected_sources = set()')
    end = source.index("        row['comparisonTargets']", start)
    scope = {'row': {'checkpoints': {'/K1/bad.exe': {'unverifiedInventory': {'repoPath': '/stored/bad.exe'}}}},
        'protection_blocked': {'/K1/bad.exe'}, 'locator': '/repos', 'Path': Path,
        'unique_pairs': {('good', 'bad'): ('/stored/good.exe', '/stored/bad.exe', 'explicit'),
                         ('good', 'other'): ('/stored/good.exe', '/stored/other.exe', 'explicit')},
        'excluded_pairs': []}
    exec(textwrap.dedent(source[start:end]), scope)
    assert scope['pairs'] == [('/stored/good.exe', '/stored/other.exe', 'explicit')]
    assert scope['excluded_pairs'][0]['target'] == '/stored/bad.exe'
