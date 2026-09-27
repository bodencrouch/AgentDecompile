import hashlib
from types import SimpleNamespace

import pytest

from agentdecompile_recovery.corpus import recover_named_ghidra as named
from agentdecompile_recovery.corpus import verify_legacy_recovered as legacy


def observation_for(target):
    return {
        'targetSnapshot': {'sha256': hashlib.sha256(b'image' + target).hexdigest(),
                           'size': len(target) + 5, 'path': '/fixture/image.bin',
                           'kind': 'fixture', 'observation': 'invocation-pinned',
                           'scope': 'captured-image-snapshot', 'currentFileVerified': False},
        'targetRegion': {'address': 0x401000, 'offset': 5, 'size': len(target),
                         'sha256': hashlib.sha256(target).hexdigest()},
    }


def test_legacy_binding_captures_precompile_source(tmp_path, monkeypatch):
    source = tmp_path / 'test_00401000.c'
    original = b'/* size: 1 bytes */\nint F_00401000(void) { return 1; }\n'
    source.write_bytes(original)
    monkeypatch.setattr(legacy, 'target_observation', lambda *a, **k: (b'X', observation_for(b'X')))
    monkeypatch.setattr(legacy, 'address_named_function', lambda *a: 'F_00401000')
    monkeypatch.setattr(legacy, 'select_object_symbol', lambda *a: ('F_00401000', b'X'))
    def compile(argv, **kwargs):
        from pathlib import Path
        assert 'return 1' in Path(argv[1]).read_text()
        source.write_text('changed during compile')
        Path(argv[2]).write_bytes(b'object')
        return SimpleNamespace(stdout='', stderr='', returncode=0)
    monkeypatch.setattr(legacy.subprocess, 'run', compile)
    result = legacy.compile_current_source(source, '', 'demo', {}, {}, compiler=tmp_path/'compiler',
                                          raw_dir=tmp_path, mapper_for=None, coff_functions=lambda *a, **k: {})
    row = legacy.coverage_row(result)
    assert row['sourceSha256'] == hashlib.sha256(original).hexdigest()
    assert row['comparisonScope'] == 'local-function'
    assert row['targetSnapshot'] == result['targetSnapshot'] == observation_for(b'X')['targetSnapshot']
    assert row['targetRegion'] == result['targetRegion'] == observation_for(b'X')['targetRegion']
    assert row['targetSnapshot']['currentFileVerified'] is False
    assert row['originalBytesSha256'] == hashlib.sha256(b'X').hexdigest()
    assert row['sourceSha256'] != hashlib.sha256(source.read_bytes()).hexdigest()


@pytest.mark.parametrize('mode', ['exact', 'masked', 'prefix', 'permuter-unbound'])
def test_named_only_binds_exact_persisted_candidate(tmp_path, monkeypatch, mode):
    built = tmp_path / 'built'
    built.mkdir()
    (built / 'function.txt').write_text('function_name')
    (built / 'base.c').write_text('int function_name(void) { return 1; }\n')
    target = b'\xe8\x01\x02\x03\x04'
    monkeypatch.setattr(named, 'knowledge_c', lambda *a: ('function_name', 'int function_name(void) { return 1; }'))
    monkeypatch.setattr(named, 'is_real_c', lambda _: True)
    monkeypatch.setattr(named, 'target_observation', lambda *a, **k: (target, observation_for(target)))
    monkeypatch.setattr(named, 'prepare_context', lambda *a: None)
    monkeypatch.setattr(named.ph, 'WORK', tmp_path)
    monkeypatch.setattr(named.ph, 'build_case', lambda *a: built)
    monkeypatch.setattr(named.ph, 'PERMUTER', tmp_path)
    monkeypatch.setattr(named.ph, 'evaluate', lambda *a: {'byte_exact': True})
    monkeypatch.setattr(named, 'RECOVERED', tmp_path/'recovered')
    receipts = []
    monkeypatch.setattr(named, 'merge_coverage', lambda program, row: receipts.append(row))
    compiled_snapshots = []
    def compile(candidate, *args):
        compiled_snapshots.append(candidate.read_bytes())
        (built/'base.c').write_text('changed while compiler ran')
        if mode == 'exact':
            return target
        if mode == 'masked':
            return b'\xe8\x09\x09\x09\x09'
        if mode == 'prefix':
            return target + b'extra'
        return b'wrong'
    monkeypatch.setattr(named, 'compiled_bytes_timeout', compile)
    case = {'program': 'demo', 'addr': 0x401000, 'slug': 'demo', 'size': len(target),
            'repo_path': '/demo', 'name': 'function_name', 'convention': 'cdecl', 'canon_key': 'function_name'}
    result = named.evaluate_one(case, 'vc8', 1 if mode == 'permuter-unbound' else 0, {})
    assert result['targetSnapshot'] == observation_for(target)['targetSnapshot']
    assert result['targetRegion'] == observation_for(target)['targetRegion']
    if mode == 'exact':
        from pathlib import Path
        persisted = Path(result['path']).read_bytes()
        assert result['accepted']
        assert compiled_snapshots[-1] == persisted
        assert receipts[0]['sourceSha256'] == hashlib.sha256(persisted).hexdigest()
        assert receipts[0]['originalBytesSha256'] == hashlib.sha256(target).hexdigest()
        assert receipts[0]['comparisonScope'] == 'local-function'
        assert receipts[0]['targetSnapshot'] == result['targetSnapshot']
        assert receipts[0]['targetRegion'] == result['targetRegion']
        assert receipts[0]['targetSnapshot']['currentFileVerified'] is False
    else:
        assert not result['accepted']
        assert not result['byte_exact']
        assert not receipts
        if mode == 'masked':
            assert result['masked_match']



def test_nonzero_compiler_exit_with_object_is_rejected_by_both_producers(tmp_path, monkeypatch):
    import subprocess
    from pathlib import Path
    source = tmp_path / 'test_00401000.c'
    source.write_text('/* size: 1 bytes */\nint F_00401000(void) { return 1; }\n')
    monkeypatch.setattr(legacy, 'target_observation', lambda *a, **k: (b'X', observation_for(b'X')))
    monkeypatch.setattr(legacy, 'address_named_function', lambda *a: 'F_00401000')
    def compiler_failure(argv, **kwargs):
        Path(argv[2]).write_bytes(b'object exists despite failure')
        return SimpleNamespace(stdout='', stderr='compiler failed', returncode=1)
    monkeypatch.setattr(subprocess, 'run', compiler_failure)
    def unexpected_parse(*args, **kwargs):
        pytest.fail('failed compiler output must not be parsed or accepted')
    result = legacy.compile_current_source(source, '', 'demo', {}, {}, compiler=tmp_path/'compiler',
                                          raw_dir=tmp_path, mapper_for=None, coff_functions=unexpected_parse)
    assert result['status'] == 'compile_failed'
    assert result['targetSnapshot'] == observation_for(b'X')['targetSnapshot']
    with pytest.raises(ValueError, match='byte-exact'):
        legacy.coverage_row(result)
    monkeypatch.setattr(named.ph, 'COMPILERS', {'fake': tmp_path/'compiler'})
    assert named.compiled_bytes_timeout(source, 'F_00401000', 'fake') is None
