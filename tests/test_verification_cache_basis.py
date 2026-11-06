"""Content/provenance and bounded retry contracts; no compiler or game launch."""
import hashlib
import json
import os
from pathlib import Path

import pytest

from agentdecompile_recovery.corpus import verify_recovered_byteexact as verifier


def setup_inputs(tmp_path, monkeypatch, *, closure=True):
    source = tmp_path / 'source'
    source.mkdir()
    cfile = source / 'f.c'
    cfile.write_text('int f(void) {return 1;}')
    raw = tmp_path / 'target.bin'
    raw.write_bytes(b'abc')
    compiler = tmp_path / 'compiler.sh'
    compiler.write_text('compiler-v1')
    tool = tmp_path / 'tool.bin'
    tool.write_bytes(b'tool-v1')
    manifest = tmp_path / 'inputs.json'
    manifest.write_text(json.dumps({'complete': True, 'files': ['tool.bin']}))
    out = tmp_path / 'result.json'
    argv = ['--verified-dir', str(source), '--raw', str(raw), '--compiler', str(compiler), '--out', str(out)]
    if closure:
        argv += ['--cache-input-manifest', str(manifest)]
    calls = []
    def check(path, *args, **kwargs):
        calls.append(kwargs['source_bytes'].decode('utf-8'))
        return {'file': path.name, 'ok': True, 'reason': 'byte-exact-relocation-masked'}
    monkeypatch.setattr(verifier, 'verify_one', check)
    return argv, calls, cfile, raw, compiler, tool, out


def test_same_mtime_and_size_source_change_invalidates(tmp_path, monkeypatch):
    argv, calls, source, _, _, _, out = setup_inputs(tmp_path, monkeypatch)
    assert verifier.main(argv) == 0
    assert verifier.main(argv) == 0
    assert len(calls) == 1
    assert json.loads(out.read_text())['results'][0]['reused'] is True
    old = source.stat()
    source.write_text(source.read_text().replace('1', '2'))
    os.utime(source, ns=(old.st_atime_ns, old.st_mtime_ns))
    assert verifier.main(argv) == 0
    assert len(calls) == 2


@pytest.mark.parametrize('which', ['raw', 'wrapper', 'toolchain'])
def test_target_and_toolchain_content_changes_invalidate(tmp_path, monkeypatch, which):
    argv, calls, _, raw, wrapper, tool, _ = setup_inputs(tmp_path, monkeypatch)
    assert verifier.main(argv) == 0
    path = {'raw': raw, 'wrapper': wrapper, 'toolchain': tool}[which]
    path.write_bytes(path.read_bytes() + b'new')
    assert verifier.main(argv) == 0
    assert len(calls) == 2


def test_transient_result_cooldown_then_retry(tmp_path, monkeypatch):
    argv, _, _, _, _, _, out = setup_inputs(tmp_path, monkeypatch)
    now = [1000.0]
    monkeypatch.setattr(verifier.time, 'time', lambda: now[0])
    calls = []
    def timeout(path, *args, **kwargs):
        calls.append(path)
        return {'file': path.name, 'ok': False, 'reason': 'compile-timeout'}
    monkeypatch.setattr(verifier, 'verify_one', timeout)
    assert verifier.main(argv) == 0
    now[0] += 299
    assert verifier.main(argv) == 0
    assert len(calls) == 1
    assert json.loads(out.read_text())['byteExact'] == 0
    now[0] += 1
    assert verifier.main(argv) == 0
    assert len(calls) == 2


def test_incomplete_closure_defers_without_recompiling_or_reusing_positive(tmp_path, monkeypatch):
    argv, calls, _, _, _, _, out = setup_inputs(tmp_path, monkeypatch, closure=False)
    assert verifier.main(argv) == 0
    assert verifier.main(argv) == 2
    receipt = json.loads(out.read_text())
    assert receipt['byteExact'] == 0
    assert receipt['results'][0]['reason'] == 'cache-basis-incomplete'
    assert len(calls) == 1
    assert verifier.main(argv + ['--no-incremental']) == 0
    assert len(calls) == 2


def test_incomplete_closure_withdraws_owned_artifact_before_deferred_receipt(tmp_path, monkeypatch):
    argv, _, _, _, _, _, out = setup_inputs(tmp_path, monkeypatch, closure=False)
    bins = tmp_path / 'bins'
    argv += ['--bin-dir', str(bins)]
    calls = []

    def emit(path, raw, mapper, compiler, sizes, bin_dir, maxc_dir, **kwargs):
        calls.append(path)
        (bin_dir / '00400000.bin').write_bytes(b'abc')
        source = kwargs['source_bytes']
        return {'file': path.name, 'sourcePath': str(path.resolve()),
                'sourceSha256': hashlib.sha256(source).hexdigest(),
                'addr': '0x400000', 'size': 3, 'ok': True, 'rawEqual': True,
                'comparisonPolicy': 'raw-region-v1',
                'reason': 'byte-exact-relocation-masked'}

    monkeypatch.setattr(verifier, 'verify_one', emit)
    assert verifier.main(argv) == 0
    active = bins / '00400000.bin'
    assert active.read_bytes() == b'abc'
    assert verifier.main(argv) == 2
    assert len(calls) == 1
    assert not active.exists()
    quarantined = list((bins / '.withdrawn').iterdir())
    assert len(quarantined) == 1
    assert quarantined[0].read_bytes() == b'abc'
    receipt = json.loads(out.read_text())
    assert receipt['results'][0]['reason'] == 'cache-basis-incomplete'
    assert receipt['results'][0]['artifacts'] == []
    assert receipt['results'][0]['withdrawnArtifacts'] == [str(quarantined[0].resolve())]
    state = json.loads(Path(str(out) + '.state.json').read_text())
    assert state['entries']['f.c']['artifacts'] == []
    assert json.loads((bins / verifier._OWNER_MANIFEST).read_text())['owners'] == {}


def test_changed_source_during_compile_never_promotes(tmp_path, monkeypatch):
    argv, _, source, _, _, _, out = setup_inputs(tmp_path, monkeypatch)
    def mutate(path, *args, **kwargs):
        source.write_text('changed while compiling')
        return {'file': path.name, 'ok': True, 'reason': 'byte-exact-relocation-masked'}
    monkeypatch.setattr(verifier, 'verify_one', mutate)
    assert verifier.main(argv) == 2
    assert json.loads(out.read_text())['byteExact'] == 0


def test_function_sizes_invalidate_but_unrelated_db_write_does_not(tmp_path, monkeypatch):
    import sqlite3
    argv, calls, _, _, _, _, _ = setup_inputs(tmp_path, monkeypatch)
    db = tmp_path / 'functions.db'
    with sqlite3.connect(db) as con:
        con.execute('CREATE TABLE func(binary_id INTEGER, addr INTEGER, size INTEGER)')
        con.execute('INSERT INTO func VALUES(1, 4194304, 3)')
    argv += ['--db', str(db), '--binary-id', '1']
    assert verifier.main(argv) == 0
    with sqlite3.connect(db) as con:
        con.execute('INSERT INTO func VALUES(2, 4194304, 9)')
    assert verifier.main(argv) == 0
    assert len(calls) == 1
    with sqlite3.connect(db) as con:
        con.execute('UPDATE func SET size=4 WHERE binary_id=1')
    assert verifier.main(argv) == 0
    assert len(calls) == 2


def test_missing_manifest_dependency_withdraws_previous_positive(tmp_path, monkeypatch):
    argv, _, _, _, _, tool, out = setup_inputs(tmp_path, monkeypatch)
    bins = tmp_path / 'bins'
    argv += ['--bin-dir', str(bins)]

    calls = []
    def emit(path, raw, mapper, compiler, sizes, bin_dir, maxc_dir, **kwargs):
        calls.append(path)
        (bin_dir / '00400000.bin').write_bytes(b'abc')
        source = kwargs['source_bytes']
        return {'file': path.name, 'sourcePath': str(path.resolve()),
                'sourceSha256': hashlib.sha256(source).hexdigest(),
                'addr': '0x400000', 'size': 3, 'ok': True, 'rawEqual': True,
                'comparisonPolicy': 'raw-region-v1',
                'reason': 'byte-exact-relocation-masked'}

    monkeypatch.setattr(verifier, 'verify_one', emit)
    assert verifier.main(argv) == 0
    active = bins / '00400000.bin'
    assert active.read_bytes() == b'abc'
    tool.unlink()
    assert verifier.main(argv) == 2
    receipt = json.loads(out.read_text())
    assert receipt['current'] is False
    assert receipt['byteExact'] == 0
    assert receipt['reason'] == 'cache-basis-unavailable'
    assert not active.exists()
    quarantined = list((bins / '.withdrawn').iterdir())
    assert receipt['withdrawnArtifacts'] == [str(quarantined[0].resolve())]
    tool.write_bytes(b'tool-v1')
    assert verifier.main(argv) == 0
    assert active.read_bytes() == b'abc'
    assert len(calls) == 2
    restored = json.loads(out.read_text())['results'][0]
    assert restored['artifacts'][0]['sha256'] == verifier._digest(b'abc')
    assert verifier.main(argv) == 0
    assert len(calls) == 2
    assert json.loads(out.read_text())['results'][0]['reused'] is True


def test_emitted_artifact_change_forces_reverification(tmp_path, monkeypatch):
    argv, _, _, _, _, _, out = setup_inputs(tmp_path, monkeypatch)
    bins = tmp_path / 'bins'
    argv += ['--bin-dir', str(bins)]
    calls = []
    def emit(path, raw, mapper, compiler, sizes, bin_dir, maxc_dir, **kwargs):
        calls.append(path)
        (bin_dir / '00400000.bin').write_bytes(b'abc')
        source = kwargs['source_bytes']
        return {'file': path.name, 'sourcePath': str(path.resolve()),
                'sourceSha256': hashlib.sha256(source).hexdigest(),
                'addr': '0x400000', 'size': 3, 'ok': True, 'rawEqual': True,
                'comparisonPolicy': 'raw-region-v1',
                'reason': 'byte-exact-relocation-masked'}
    monkeypatch.setattr(verifier, 'verify_one', emit)
    assert verifier.main(argv) == 0
    (bins / '00400000.bin').write_bytes(b'wrong')
    assert verifier.main(argv) == 2
    assert len(calls) == 2
    assert (bins / '00400000.bin').read_bytes() == b'wrong'
    blocked = json.loads(out.read_text())
    assert blocked['current'] is False
    assert blocked['reason'] == 'artifact-publication-blocked'
    assert blocked['unresolvedArtifacts'][0]['reason'] == 'artifact_digest_mismatch'


def test_unowned_active_artifact_is_reported_and_never_overwritten(tmp_path, monkeypatch):
    argv, _, _, _, _, _, out = setup_inputs(tmp_path, monkeypatch)
    bins = tmp_path / 'bins'
    bins.mkdir()
    active = bins / '00400000.bin'
    active.write_bytes(b'unowned')
    argv += ['--bin-dir', str(bins)]

    def emit(path, raw, mapper, compiler, sizes, bin_dir, maxc_dir, **kwargs):
        (bin_dir / active.name).write_bytes(b'abc')
        source = kwargs['source_bytes']
        return {'file': path.name, 'sourcePath': str(path.resolve()),
                'sourceSha256': hashlib.sha256(source).hexdigest(),
                'addr': '0x400000', 'size': 3, 'ok': True, 'rawEqual': True,
                'comparisonPolicy': 'raw-region-v1',
                'reason': 'byte-exact-relocation-masked'}

    monkeypatch.setattr(verifier, 'verify_one', emit)
    assert verifier.main(argv) == 2
    assert active.read_bytes() == b'unowned'
    blocked = json.loads(out.read_text())
    assert blocked['current'] is False
    assert blocked['reason'] == 'artifact-publication-blocked'
    assert blocked['unresolvedArtifacts'][0]['reason'] == 'unowned_active_artifact'


def test_compile_nonzero_cannot_accept_leftover_object(tmp_path, monkeypatch):
    from types import SimpleNamespace
    source = tmp_path / 'f.c'
    source.write_text('// address: 0x400000 size: 3 bytes\nint f(void) {return 1;}')
    def compiler(argv, **kwargs):
        Path(argv[3]).write_bytes(b'fake-object')
        return SimpleNamespace(returncode=1, stdout='', stderr='compiler crashed')
    monkeypatch.setattr(verifier.subprocess, 'run', compiler)
    result = verifier.verify_one(source, b'abc', lambda addr, size: 0, 'fake.sh')
    assert result['ok'] is False
    assert result['reason'] == 'compile-failed'


def test_direct_verifier_output_lock_refuses_concurrent_owner(tmp_path, monkeypatch):
    import fcntl
    argv, calls, _, _, _, _, out = setup_inputs(tmp_path, monkeypatch)
    with Path(str(out) + '.verify.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert verifier.main(argv) == 2
    assert not calls


def test_checkpoint_retains_completed_batch_before_last_worker_finishes(tmp_path, monkeypatch):
    import threading
    argv, _, source, _, _, _, out = setup_inputs(tmp_path, monkeypatch)
    for index in range(50):
        (source.parent / f'{index:03}.c').write_text(f'int f{index}(void) {{return 1;}}')
    committed = threading.Event()
    write = verifier._write_json_atomic
    def checkpoint(path, value):
        write(path, value)
        if isinstance(value, dict) and len(value.get('entries', {})) >= 50:
            committed.set()
    def compile_one(path, *args, **kwargs):
        if path.name == 'f.c':
            assert committed.wait(timeout=10), 'completed batch was not checkpointed'
        return {'file': path.name, 'ok': True, 'reason': 'byte-exact-relocation-masked'}
    monkeypatch.setattr(verifier, '_write_json_atomic', checkpoint)
    monkeypatch.setattr(verifier, 'verify_one', compile_one)
    assert verifier.main(argv + ['--workers', '1']) == 0
    assert json.loads(out.read_text())['byteExact'] == 51


def test_malformed_cache_rows_do_not_promote(tmp_path, monkeypatch):
    argv, calls, _, _, _, _, out = setup_inputs(tmp_path, monkeypatch)
    Path(str(out) + '.state.json').write_text(json.dumps({'schema': verifier.CACHE_SCHEMA, 'entries': {'f.c': 'bad'}}))
    assert verifier.main(argv) == 0
    assert len(calls) == 1


def test_lock_open_failure_never_overwrites_receipt(tmp_path, monkeypatch):
    argv, _, _, _, _, _, out = setup_inputs(tmp_path, monkeypatch)
    out.write_text('prior owner receipt')
    original = Path.open
    def denied(path, *args, **kwargs):
        if str(path).endswith('.verify.lock'):
            raise PermissionError('lock inaccessible')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', denied)
    assert verifier.main(argv) == 2
    assert out.read_text() == 'prior owner receipt'


def test_input_failure_invalidates_receipt_while_lock_held(tmp_path, monkeypatch):
    import fcntl
    argv, _, _, raw, _, _, out = setup_inputs(tmp_path, monkeypatch)
    raw.unlink()
    write = verifier._write_json_atomic
    checked = []
    def inspect(path, value):
        if path == out:
            with Path(str(out) + '.verify.lock').open('a') as other:
                with pytest.raises(BlockingIOError):
                    fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
            checked.append(True)
        write(path, value)
    monkeypatch.setattr(verifier, '_write_json_atomic', inspect)
    assert verifier.main(argv) == 2
    assert checked == [True]
    assert json.loads(out.read_text())['current'] is False


def test_unsupported_flock_refuses_without_mutation(tmp_path, monkeypatch):
    import sys
    argv, _, _, _, _, _, out = setup_inputs(tmp_path, monkeypatch)
    out.write_text('untouched')
    monkeypatch.setitem(sys.modules, 'fcntl', None)
    assert verifier.main(argv) == 2
    assert out.read_text() == 'untouched'


def test_known_source_compile_diagnostic_is_not_transient(tmp_path, monkeypatch):
    from types import SimpleNamespace
    source = tmp_path / 'f.c'
    source.write_text('// address: 0x400000 size: 3 bytes\nint f(void) {broken;}')
    monkeypatch.setattr(verifier.subprocess, 'run', lambda *args, **kwargs:
                        SimpleNamespace(returncode=1, stdout='', stderr='in.c(2): error C2143: syntax error'))
    result = verifier.verify_one(source, b'abc', lambda addr, size: 0, 'fake.sh')
    assert result['reason'] == 'compile-rejected'
    assert result['failureClass'] == 'deterministic-source-rejection'
