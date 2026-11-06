"""Seed receipts bind the observed file, without claiming semantic identity."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from agentdecompile_recovery.corpus import seed_validation as sv


def test_reuse_requires_current_source_digest():
    row = {'seed': 'a', 'source_path': 'b', 'destination_bytes': 'c3', 'compile_status': 'byte_exact', 'comparisonPolicy': 'raw-region-v1', 'compileBasis': {'key': 'd'*64, 'closureComplete': True}}
    assert not sv.can_reuse_compile_result(row, row)
    bound = {**row, 'sourceSha256': 'a' * 64, 'targetSnapshot': {'sha256': 'b' * 64},
             'targetRegion': {'address': 0, 'offset': 0, 'size': 1, 'sha256': 'c' * 64}}
    assert sv.can_reuse_compile_result(bound, bound)
    assert not sv.can_reuse_compile_result({**bound, 'sourceSha256': 'b' * 64}, bound)


def test_failed_compiler_cannot_accept_leftover_object(tmp_path, monkeypatch):
    seed = sv.Seed('donor.c', '/target', '401000', 'f', 1, b'\xc3', 'f', 'int f(void) { return 0; }')
    monkeypatch.setattr(sv, 'source_context', lambda *a: '')
    def failed(argv, **kw):
        Path(argv[2]).write_bytes(b'leftover')
        return SimpleNamespace(returncode=1, stdout='', stderr='compiler failed')
    monkeypatch.setattr(sv.subprocess, 'run', failed)
    result = sv.compile_seed('target', seed, b'\xc3', compiler=tmp_path/'compiler', evidence_root=tmp_path,
                             coff_functions=lambda *a, **kw: pytest.fail('failed object must not be inspected'))
    assert result['compile_status'] == 'failed'


@pytest.mark.parametrize('mutate', [False, True])
def test_audit_binds_frozen_seed_and_rejects_inflight_edit(tmp_path, monkeypatch, mutate):
    donor = tmp_path/'program'/'f.c'
    donor.parent.mkdir()
    payload = 'int f(void) { return 0; }'
    donor.write_text(payload)
    seed = sv.Seed(str(donor), '/target', '401000', 'f', 1, b'\xc3', 'f', payload)
    directory = tmp_path/'seeds'/'target'
    directory.mkdir(parents=True)
    path = directory/'401000.c'
    snapshot = b'observed seed bytes\r\n'
    path.write_bytes(snapshot)
    candidates = [{'src_program': 'program', 'src_name': 'f', 'dst_slug': 'target', 'dst_addr': '401000'}]
    monkeypatch.setattr(sv, 'read_jsonl', lambda *a: candidates)
    monkeypatch.setattr(sv, 'parse_seed', lambda text: seed)
    monkeypatch.setattr(sv, 'build_reuse_index', lambda *a: {sv.reuse_key(str(donor), '/target', '401000'): [{'logical_id': 1}]})
    monkeypatch.setattr(sv, 'candidate_reuse_key', lambda row: sv.reuse_key(str(donor), '/target', '401000'))
    monkeypatch.setattr(sv, 'source_has_verified_coverage', lambda *a: True)
    def compile_observed(slug, frozen, target, **kw):
        assert frozen.payload == payload
        if mutate:
            path.write_bytes(b'changed seed')
        return {'compile_status': 'byte_exact', 'comparisonPolicy': 'raw-region-v1', 'compileBasis': {'key': 'd'*64, 'closureComplete': True}}
    monkeypatch.setattr(sv, 'compile_seed', compile_observed)
    out = tmp_path/'results.jsonl'
    sv.audit(candidates_path=tmp_path/'candidates', reuse_path=tmp_path/'reuse', seeds_dir=tmp_path/'seeds',
             results_path=out, summary_path=tmp_path/'summary.json', compile_destinations=True,
             compiler_for=lambda slug: (tmp_path/'compiler', {}), evidence_root=tmp_path)
    row = json.loads(out.read_text())
    if mutate:
        assert row['compile_status'] == 'source_changed'
        assert 'sourceSha256' not in row
    else:
        assert row['compile_status'] == 'byte_exact'
        assert row['sourceSha256'] == hashlib.sha256(snapshot).hexdigest()
