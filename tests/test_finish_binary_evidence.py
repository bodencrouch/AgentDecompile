import hashlib
import json
import struct
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentdecompile_recovery.corpus import finish_binary as finish


def fixture(tmp_path):
    raw = bytearray(0x204)
    raw[:2] = b'MZ'
    struct.pack_into('<I', raw, 0x3c, 0x80)
    raw[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<H', raw, 0x86, 1)
    struct.pack_into('<H', raw, 0x94, 0xe0)
    struct.pack_into('<H', raw, 0x98, 0x10b)
    struct.pack_into('<I', raw, 0x98 + 28, 0x400000)
    struct.pack_into('<IIII', raw, 0x178 + 8, 4, 0x1000, 4, 0x200)
    raw[0x200:] = b'\x90\xc3\x90\xc3'
    target = tmp_path / 'target.exe'
    target.write_bytes(raw)
    source = tmp_path / 'function.c'
    source.write_text('int recovered(void) { return 1; }\n')
    row = {'file': source.name, 'sourcePath': str(source), 'sourceSha256': hashlib.sha256(source.read_bytes()).hexdigest(),
           'ok': True, 'rawEqual': True, 'comparisonPolicy': 'raw-region-v1',
           'addr': '0x401000', 'size': 2,
           'targetSnapshot': {'path': str(target), 'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw)},
           'targetRegion': {'address': 0x401000, 'offset': 0x200, 'size': 2, 'sha256': hashlib.sha256(raw[0x200:0x202]).hexdigest()}}
    return target, source, row


def receipt(tmp_path, rows, name='receipt.json'):
    path = tmp_path / name
    path.write_text(json.dumps({'results': rows}))
    return str(path)


def test_current_raw_observation_then_negative_withdrawal(tmp_path):
    target, source, row = fixture(tmp_path)
    positive = receipt(tmp_path, [row])
    assert list(finish.load_byte_exact([positive], target_path=target, expected_sizes={0x401000: 2})) == [0x401000]
    negative = receipt(tmp_path, [{'file': source.name, 'sourcePath': str(source), 'ok': False}], 'negative.json')
    assert finish.load_byte_exact([positive, negative], target_path=target) == {}


def test_negative_alternate_source_does_not_withdraw_valid_candidate(tmp_path):
    target, source_a, row = fixture(tmp_path)
    source_b = tmp_path / 'alternate.c'
    source_b.write_text('int alternate(void) { return 2; }\n')
    positive = receipt(tmp_path, [row])
    negative_b = receipt(tmp_path, [{
        'file': source_b.name,
        'sourcePath': str(source_b),
        'addr': '0x401000',
        'ok': False,
        'rawEqual': False,
    }], 'negative-b.json')
    assert finish.load_byte_exact(
        [positive, negative_b], target_path=target, expected_sizes={0x401000: 2}
    ) == {0x401000: 'current-source-target-raw-local-observation'}


def test_masked_or_stale_sources_never_count(tmp_path):
    target, source, row = fixture(tmp_path)
    for update in ({'rawEqual': False}, {'rawEqual': 'true'}, {'comparisonPolicy': None}, {'ok': 1}):
        assert finish.load_byte_exact([receipt(tmp_path, [{**row, **update}])], target_path=target) == {}
    positive = receipt(tmp_path, [row])
    source.write_text('int recovered(void) { return 2; }\n')
    assert finish.load_byte_exact([positive], target_path=target) == {}


def test_wrong_target_size_mapping_and_unbound_legacy_refuse(tmp_path):
    target, _, row = fixture(tmp_path)
    positive = receipt(tmp_path, [row])
    assert finish.load_byte_exact([positive], target_path=target, expected_sizes={0x401000: 3}) == {}
    assert finish.load_byte_exact([positive]) == {}
    wrong = {**row, 'addr': '0x401002', 'targetRegion': {**row['targetRegion'], 'address': 0x401002}}
    assert finish.load_byte_exact([receipt(tmp_path, [wrong])], target_path=target) == {}
    target.write_bytes(target.read_bytes() + b'changed')
    assert finish.load_byte_exact([positive], target_path=target) == {}


def test_malformed_receipt_does_not_erase_independent_valid_evidence(tmp_path):
    target, _, row = fixture(tmp_path)
    invalid = tmp_path / 'broken.json'
    invalid.write_text('{')
    rejected = []
    result = finish.load_byte_exact([str(invalid), receipt(tmp_path, [None, row])], target_path=target, rejected=rejected)
    assert 0x401000 in result
    assert {r['reason'] for r in rejected} == {'receipt_unreadable', 'invalid_result'}


def test_pe_mapping_rejects_unbacked_or_ambiguous_regions(tmp_path):
    target, _, _ = fixture(tmp_path)
    raw = bytearray(target.read_bytes())
    assert finish._file_region_offset(raw, 0x401000, 2) == 0x200
    assert finish._file_region_offset(raw, 0x401003, 2) is None
    assert finish._file_region_offset(b'raw-dump', 0x400000, 2) is None
    struct.pack_into('<H', raw, 0x86, 2)
    raw[0x1a0:0x1c8] = raw[0x178:0x1a0]
    assert finish._file_region_offset(raw, 0x401000, 2) is None
    assert finish._file_region_offset is finish.file_region_offset


@pytest.mark.parametrize('masked_only', [False, True])
def test_real_producer_receipt_to_reconciliation_report(tmp_path, monkeypatch, masked_only):
    from agentdecompile_recovery.corpus import verify_recovered_byteexact as verifier
    target, source, _ = fixture(tmp_path)
    source.write_text('// address: 0x401000\n// size: 4 bytes\nint recovered(void) { return 1; }\n')
    wrapper = tmp_path / 'compiler.sh'
    wrapper.write_text('inert compiler fixture')
    def compile(command, **kwargs):
        Path(command[3]).write_bytes(b'object')
        return SimpleNamespace(returncode=0, stdout='', stderr='')
    monkeypatch.setattr(verifier.subprocess, 'run', compile)
    monkeypatch.setattr(verifier, 'text_bytes_and_relocs', lambda _: (b'\0'*4, [0]) if masked_only else (target.read_bytes()[0x200:], []))
    observed = tmp_path / 'observed.json'
    bins = tmp_path / 'bins'
    assert verifier.main(['--verified-dir', str(tmp_path), '--raw', str(target),
                          '--compiler', str(wrapper), '--out', str(observed), '--workers', '1',
                          '--bin-dir', str(bins)]) == 0
    artifact = bins / '00401000.bin'
    assert artifact.exists() is not masked_only
    produced = json.loads(observed.read_text())['results'][0]
    assert produced['reloc_linked'] is False
    assert produced['artifactsCurrent'] is not masked_only
    assert produced['artifacts'] == ([] if masked_only else [{
        'path': str(artifact.resolve()),
        'sha256': hashlib.sha256(target.read_bytes()[0x200:]).hexdigest(),
        'channel': 'raw-exact',
        'address': 0x401000,
        'ownerSourcePath': str(source.resolve()),
        'ownerSourceSha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'ownerBasis': produced['basis'],
    }])
    db = tmp_path / 'corpus.sqlite'
    with sqlite3.connect(db) as con:
        con.execute('CREATE TABLE func(binary_id INTEGER, addr INTEGER, size INTEGER)')
        con.execute('INSERT INTO func VALUES (1, 4198400, 4)')
    report = tmp_path / 'report.json'
    monkeypatch.setattr(sys, 'argv', ['finish', '--receipts', str(observed), '--target', str(target),
                                    '--db', str(db), '--binary-id', '1', '--out', str(report)])
    assert finish.main() == 0
    result = json.loads(report.read_text())
    assert result['rawLocalObservedC'] == (0 if masked_only else 1)
    assert result['byteExactRecoveredC'] == result['rawLocalObservedC']
    assert result['exactPlacementHashEqual'] is None
    assert result['semanticIdentityVerified'] is False
    assert result['linkedSourceContributionVerified'] is False
    assert result['wholeImageByteIdentical'] is False
