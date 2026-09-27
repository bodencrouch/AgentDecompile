import hashlib
import json
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest
from agentdecompile_recovery.corpus import verify_recovered_byteexact as verifier


def pe_image(*, virtual_size=4, raw_size=4, payload=b'\x90\xc3\x90\xc3', trailing=b''):
    raw = bytearray(0x200 + len(payload) + len(trailing))
    raw[:2] = b'MZ'
    struct.pack_into('<I', raw, 0x3c, 0x80)
    raw[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<H', raw, 0x86, 1)
    struct.pack_into('<H', raw, 0x94, 0xe0)
    struct.pack_into('<H', raw, 0x98, 0x10b)
    struct.pack_into('<I', raw, 0x98 + 28, 0x400000)
    struct.pack_into('<IIII', raw, 0x178 + 8, virtual_size, 0x1000, raw_size, 0x200)
    raw[0x200:0x200 + len(payload)] = payload
    raw[0x200 + len(payload):] = trailing
    return bytes(raw)


@pytest.mark.parametrize('source,raw,offset', [
    ('// original machine code: 90', b'\x90', 0),
    ('// address: 0x400000\n// original machine code: 91', b'\x90', 0),
    ('// address: 0x400000\n// size: 2 bytes\n// original machine code: 90', b'\x90\x90', 0),
    ('// address: 0x400000\n// size: 1 bytes', b'\x90', -1),
    ('// address: 0x400000\n// original machine code: 9', b'\x90', 0),
    ('// address: 0x400000\n// original machine code: 90zz', b'\x90', 0),
])
def test_parse_rejects_uncorroborated_target(source, raw, offset):
    assert verifier._parse(source, raw, lambda _address, _size:offset) is None


def test_parse_matches_actual_target_and_refuses_conflicting_db_size():
    source = '// address: 0x400000\n// original machine code: 9091'
    assert verifier._parse(source,b'\x90\x91',lambda _address, _size:0)==(0x400000,2,b'\x90\x91')
    assert verifier._parse(source,b'\x90\x91',lambda _address, _size:0,{0x400000:1}) is None


@pytest.mark.parametrize('compiled,relocations,raw_equal,masked', [
    (b'\x90\x91\x92\x93', [], True, True),
    (b'\x00\x00\x00\x00', [0], False, True),
    (b'\x90\x91\x92\x93\x94', [], False, False),
])
def test_observed_source_and_target_have_distinct_raw_and_masked_facts(tmp_path,monkeypatch,compiled,relocations,raw_equal,masked):
    source = b'// address: 0x400000\n// size: 4 bytes\nvoid F_00400000() {}\n'
    cfile=tmp_path/'function.c'; cfile.write_bytes(source)
    raw=b'\x90\x91\x92\x93'
    snapshot={'path':str(tmp_path/'target'), 'size':4, 'sha256':hashlib.sha256(raw).hexdigest()}
    def compile(command,**kwargs):
        assert Path(command[2]).read_bytes()==(verifier._PREAMBLE.encode()+source)
        Path(command[3]).write_bytes(b'object')
        cfile.write_text('changed after compile snapshot')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(verifier.subprocess,'run',compile)
    monkeypatch.setattr(verifier,'text_bytes_and_relocs',lambda _:(compiled,relocations))
    output=tmp_path/'bin';output.mkdir()
    result=verifier.verify_one(cfile,raw,lambda _address, _size:0,'inert',bin_dir=output,target_snapshot=snapshot)
    assert result['rawEqual'] is raw_equal
    assert result['ok'] is masked
    assert result['sourceSha256']==hashlib.sha256(source).hexdigest()
    assert result['sourcePath']==str(cfile)
    assert result['targetRegion']=={'address':0x400000,'offset':0,'size':4,'sha256':hashlib.sha256(raw).hexdigest()}
    assert result['targetSnapshot']==snapshot
    assert result['comparisonPolicy']=='raw-region-v1'
    assert bool(list(output.glob('*.bin'))) is raw_equal
    assert result['reloc_linked'] is False


def test_strict_utf8_and_invalid_relocation_refuse(tmp_path):
    source=tmp_path/'bad.c';source.write_bytes(b'\xff')
    assert verifier.verify_one(source,b'',lambda _:0,'unused')['reason']=='invalid-source-encoding'
    with pytest.raises(ValueError):
        verifier.masked_diff_count(b'1234',b'1234',[-1])


def test_producer_requires_one_complete_file_backed_pe_region(tmp_path, monkeypatch):
    raw = bytearray(pe_image(virtual_size=0x1000, raw_size=4, trailing=b'\xaa\xbb'))
    target = tmp_path / 'target.exe'
    target.write_bytes(raw)
    source = tmp_path / 'virtual_only.c'
    source.write_text('// address: 0x401004\n// size: 2 bytes\n// original machine code: aabb\nint recovered(void) { return 1; }\n')
    compiler = tmp_path / 'compiler.sh'
    compiler.write_text('inert compiler fixture')
    monkeypatch.setattr(verifier.subprocess, 'run', lambda *_args, **_kwargs: pytest.fail('virtual-only input compiled'))
    output = tmp_path / 'receipt.json'
    bins = tmp_path / 'bins'
    assert verifier.main(['--verified-dir', str(tmp_path), '--raw', str(target),
                          '--compiler', str(compiler), '--out', str(output),
                          '--bin-dir', str(bins), '--workers', '1']) == 0
    result = json.loads(output.read_text())['results'][0]
    assert result['reason'] == 'unparsed-header'
    assert list(bins.glob('*.bin')) == []
    assert verifier.file_region_offset(raw, 0x401003, 2) is None

    struct.pack_into('<H', raw, 0x86, 2)
    raw.extend(b'\0' * max(0, 0x1c8 - len(raw)))
    raw[0x1a0:0x1c8] = raw[0x178:0x1a0]
    assert verifier.file_region_offset(raw, 0x401000, 2) is None

    partial = bytearray(pe_image())
    partial.extend(b'\x11\x22\x33\x44')
    struct.pack_into('<H', partial, 0x86, 2)
    partial[0x1a0:0x1c8] = partial[0x178:0x1a0]
    struct.pack_into('<I', partial, 0x1a0 + 12, 0x1002)
    struct.pack_into('<I', partial, 0x1a0 + 20, 0x204)
    assert verifier.file_region_offset(partial, 0x401000, 4) is None


@pytest.mark.parametrize('outcome', [
    'negative', 'invalidation', 'withdrawal_failure', 'owner_conflict',
])
def test_negative_publication_quarantines_owned_exact_bin_first(tmp_path, monkeypatch, outcome):
    raw = pe_image()
    target = tmp_path / 'target.exe'
    target.write_bytes(raw)
    source = tmp_path / 'function.c'
    source.write_text('// address: 0x401000\n// size: 4 bytes\nint recovered(void) { return 1; }\n')
    compiler = tmp_path / 'compiler.sh'
    compiler.write_text('inert compiler fixture')
    compiled = [raw[0x200:0x204]]
    compile_calls = 0

    def compile(command, **_kwargs):
        nonlocal compile_calls
        compile_calls += 1
        Path(command[3]).write_bytes(b'object')
        if outcome == 'invalidation' and compile_calls == 2:
            source.write_text('// address: 0x401000\n// size: 4 bytes\nint recovered(void) { return 2; }\n')
        return SimpleNamespace(returncode=0, stdout='', stderr='')

    monkeypatch.setattr(verifier.subprocess, 'run', compile)
    monkeypatch.setattr(verifier, 'text_bytes_and_relocs', lambda _object: (compiled[-1], []))
    output = tmp_path / 'receipt.json'
    bins = tmp_path / 'bins'
    arguments = ['--verified-dir', str(tmp_path), '--raw', str(target), '--compiler', str(compiler),
                 '--out', str(output), '--bin-dir', str(bins), '--workers', '1', '--no-incremental']
    assert verifier.main(arguments) == 0
    exact = bins / '00401000.bin'
    assert exact.read_bytes() == raw[0x200:0x204]
    owners = json.loads((bins / verifier._OWNER_MANIFEST).read_text())['owners']
    assert owners[exact.name]['sourcePath'] == str(source.resolve())
    assert owners[exact.name]['sourceSha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert owners[exact.name]['address'] == 0x401000

    if outcome in {'negative', 'withdrawal_failure'}:
        compiled.append(b'FAIL')
    if outcome == 'withdrawal_failure':
        exact.write_bytes(b'TAMPERED')
    if outcome == 'owner_conflict':
        manifest_path = bins / verifier._OWNER_MANIFEST
        manifest = json.loads(manifest_path.read_text())
        manifest['owners'][exact.name]['sourcePath'] = str(tmp_path / 'unrelated.c')
        manifest_path.write_text(json.dumps(manifest))
    original_write = verifier._write_json_atomic
    receipt_observed = []

    def observe_publication(path, value):
        if path == output:
            receipt_observed.append(not exact.exists())
        original_write(path, value)

    monkeypatch.setattr(verifier, '_write_json_atomic', observe_publication)
    assert verifier.main(arguments) == (0 if outcome == 'negative' else 2)
    if outcome in {'withdrawal_failure', 'owner_conflict'}:
        assert receipt_observed == [False]
        assert exact.read_bytes() == (b'TAMPERED' if outcome == 'withdrawal_failure' else raw[0x200:0x204])
        assert not (bins / '.withdrawn').exists()
        blocked = json.loads(output.read_text())
        assert blocked['current'] is False
        assert blocked['reason'] == 'artifact-publication-blocked'
        assert blocked['unresolvedArtifacts'][0]['reason'] == (
            'artifact_digest_mismatch' if outcome == 'withdrawal_failure' else 'artifact_owner_mismatch'
        )
        return
    assert receipt_observed == [True]
    assert not exact.exists()
    quarantined = list((bins / '.withdrawn').iterdir())
    assert len(quarantined) == 1
    assert quarantined[0].read_bytes() == raw[0x200:0x204]
    result = json.loads(output.read_text())['results'][0]
    assert result['reason'] == ('mismatch' if outcome == 'negative' else 'inputs-changed-during-verification')
    if outcome == 'negative':
        assert result['rawEqual'] is False
    assert result['artifacts'] == []
    assert result['withdrawnArtifacts'] == [str(quarantined[0].resolve())]


def test_publication_race_never_overwrites_new_active_path(tmp_path, monkeypatch):
    raw = pe_image()
    target = tmp_path / 'target.exe'
    target.write_bytes(raw)
    source = tmp_path / 'function.c'
    source.write_text('// address: 0x401000\n// size: 4 bytes\nint recovered(void) { return 1; }\n')
    compiler = tmp_path / 'compiler.sh'
    compiler.write_text('inert compiler fixture')

    def compile(command, **_kwargs):
        Path(command[3]).write_bytes(b'object')
        return SimpleNamespace(returncode=0, stdout='', stderr='')

    monkeypatch.setattr(verifier.subprocess, 'run', compile)
    monkeypatch.setattr(verifier, 'text_bytes_and_relocs', lambda _object: (raw[0x200:0x204], []))
    real_link = verifier.os.link

    def race_link(staged, destination):
        Path(destination).write_bytes(b'RACER')
        return real_link(staged, destination)

    monkeypatch.setattr(verifier.os, 'link', race_link)
    output = tmp_path / 'receipt.json'
    bins = tmp_path / 'bins'
    assert verifier.main(['--verified-dir', str(tmp_path), '--raw', str(target),
                          '--compiler', str(compiler), '--out', str(output),
                          '--bin-dir', str(bins), '--workers', '1']) == 2
    artifact = bins / '00401000.bin'
    assert artifact.read_bytes() == b'RACER'
    blocked = json.loads(output.read_text())
    assert blocked['current'] is False
    assert blocked['reason'] == 'artifact-publication-blocked'
    assert blocked['unresolvedArtifacts'][0]['reason'] == 'active_artifact_publish_race'


def test_durable_manifest_withdraws_after_cache_state_loss_and_unparsed_source(tmp_path, monkeypatch):
    raw = pe_image()
    target = tmp_path / 'target.exe'
    target.write_bytes(raw)
    source = tmp_path / 'function.c'
    source.write_text('// address: 0x401000\n// size: 4 bytes\nint recovered(void) { return 1; }\n')
    compiler = tmp_path / 'compiler.sh'
    compiler.write_text('inert compiler fixture')
    compile_calls = 0

    def compile(command, **_kwargs):
        nonlocal compile_calls
        compile_calls += 1
        Path(command[3]).write_bytes(b'object')
        return SimpleNamespace(returncode=0, stdout='', stderr='')

    monkeypatch.setattr(verifier.subprocess, 'run', compile)
    monkeypatch.setattr(verifier, 'text_bytes_and_relocs', lambda _object: (raw[0x200:0x204], []))
    output = tmp_path / 'receipt.json'
    bins = tmp_path / 'bins'
    arguments = ['--verified-dir', str(tmp_path), '--raw', str(target), '--compiler', str(compiler),
                 '--out', str(output), '--bin-dir', str(bins), '--workers', '1', '--no-incremental']
    assert verifier.main(arguments) == 0
    active = bins / '00401000.bin'
    assert active.read_bytes() == raw[0x200:0x204]
    Path(str(output) + '.state.json').unlink()
    source.write_text('int recovered(void) { return 2; }\n')
    assert verifier.main(arguments) == 0
    assert compile_calls == 1
    assert not active.exists()
    quarantined = list((bins / '.withdrawn').iterdir())
    assert len(quarantined) == 1
    result = json.loads(output.read_text())['results'][0]
    assert result['reason'] == 'unparsed-header'
    assert result['artifacts'] == []
    assert result['withdrawnArtifacts'] == [str(quarantined[0].resolve())]
    assert json.loads((bins / verifier._OWNER_MANIFEST).read_text())['owners'] == {}
