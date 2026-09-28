from pathlib import Path
import hashlib
import json
import sqlite3
import pytest
from agentdecompile_recovery.corpus.export_reagent_snapshot import export_reagent_snapshot

@pytest.fixture
def cache(tmp_path):
    path = tmp_path / 'cache.sqlite'
    with sqlite3.connect(path) as con:
        con.execute('CREATE TABLE func_knowledge(program TEXT, entry_hex TEXT, name TEXT, signature TEXT, calling_convention TEXT, decompiled TEXT, asm TEXT, PRIMARY KEY(program,entry_hex))')
        con.execute('INSERT INTO func_knowledge VALUES (?,?,?,?,?,?,?)', ('owned-fixture', '00401000', 'canary', 'int canary(int x)', '__cdecl', 'int canary(int x) { return x + 1; }', '00401000 RET'))
    return path

def export(cache, tmp_path, addresses=('0x401000',), **kw):
    return export_reagent_snapshot(knowledge_db=cache, program='owned-fixture', addresses=addresses, output_dir=tmp_path/'snapshot', **kw)

def test_snapshot_preserves_cached_evidence_and_explicit_identity_gap(cache, tmp_path):
    before = hashlib.sha256(cache.read_bytes()).hexdigest()
    manifest = export(cache, tmp_path)
    payload = json.loads((tmp_path/'snapshot/00401000.json').read_text())
    assert payload['decompiled'] == 'int canary(int x) { return x + 1; }'
    assert payload['assembly'] == ['00401000 RET']
    assert payload['signature'] == 'int canary(int x)'
    assert payload['calling_convention'] == '__cdecl'
    assert not {'callers', 'callees', 'cfg', 'pcode'} & payload.keys()
    assert any('Original binary identity' in gap['reason'] for gap in payload['gaps'])
    assert manifest['binary_binding']['state'] == 'unverified'
    assert hashlib.sha256(cache.read_bytes()).hexdigest() == before
    assert json.loads((tmp_path/'snapshot/manifest.json').read_text()) == manifest
    for name, digest in manifest['files'].items():
        assert hashlib.sha256((tmp_path/'snapshot'/name).read_bytes()).hexdigest() == digest

def test_missing_row_retained_as_gap(cache, tmp_path):
    manifest = export(cache, tmp_path, addresses=['401000', '402000'])
    assert manifest['rows'][1] == {'address':'00402000', 'state':'missing'}
    assert not (tmp_path/'snapshot/00402000.json').exists()
    assert any(gap['function']=='00402000' for gap in manifest['gaps'])

def test_missing_code_not_fabricated(cache, tmp_path):
    with sqlite3.connect(cache) as con:
        con.execute('UPDATE func_knowledge SET decompiled=NULL, asm=NULL')
    export(cache, tmp_path)
    payload=json.loads((tmp_path/'snapshot/00401000.json').read_text())
    assert 'decompiled' not in payload and 'assembly' not in payload
    assert any('decompiled source is unavailable' in gap['reason'] for gap in payload['gaps'])

@pytest.mark.parametrize('addresses,max_functions',[([],100),(['401000','0x401000'],100),(['401000','402000'],1),(['../escape'],100),([-1],100),([True],100)])
def test_invalid_selection_does_not_publish(cache,tmp_path,addresses,max_functions):
    with pytest.raises(ValueError): export(cache,tmp_path,addresses,max_functions=max_functions)
    assert not (tmp_path/'snapshot').exists()

def test_existing_output_not_overwritten(cache,tmp_path):
    destination=tmp_path/'snapshot';destination.mkdir();(destination/'owned').write_text('keep')
    with pytest.raises(FileExistsError):export(cache,tmp_path)
    assert (destination/'owned').read_text()=='keep'

def test_changed_row_changes_content_identity(cache,tmp_path):
    first=export(cache,tmp_path)
    with sqlite3.connect(cache) as con:con.execute("UPDATE func_knowledge SET decompiled='changed'")
    second=export_reagent_snapshot(knowledge_db=cache,program='owned-fixture',addresses=['401000'],output_dir=tmp_path/'changed')
    assert first['materialized_rows_sha256'] != second['materialized_rows_sha256']

def test_write_failure_leaves_no_published_manifest(cache,tmp_path,monkeypatch):
    from agentdecompile_recovery.corpus import export_reagent_snapshot as module
    original=module._write
    def fail(path,data):
        if path.name=='_index.json': raise OSError('injected write failure')
        return original(path,data)
    monkeypatch.setattr(module,'_write',fail)
    with pytest.raises(OSError):export(cache,tmp_path)
    assert not (tmp_path/'snapshot/manifest.json').exists()


def test_public_cli_and_catalog_export_and_reject_invalid_selection(cache, tmp_path, capsys):
    from agentdecompile_recovery.corpus.cli import main
    from agentdecompile_recovery.corpus.dashboard.actions.introspect import corpus_specs

    action = next(spec for spec in corpus_specs() if spec.id == 'corpus.export-reagent-snapshot')
    assert action.mutating is True
    assert action.ghidra_exclusive is False
    destination = tmp_path / 'cli-snapshot'
    argv = ['export-reagent-snapshot', '--kb', str(cache), '--program', 'owned-fixture',
            '--address', '00401000', '--destination', str(destination), '--max-functions', '1']
    assert main(argv) == 0
    emitted = json.loads(capsys.readouterr().out)
    assert emitted == json.loads((destination / 'manifest.json').read_text())
    assert emitted['selected_addresses'] == ['00401000']
    assert emitted['binary_binding']['state'] == 'unverified'
    assert json.loads((destination / '00401000.json').read_text())['decompiled'] == 'int canary(int x) { return x + 1; }'

    invalid = tmp_path / 'invalid-cli-snapshot'
    assert main(['export-reagent-snapshot', '--kb', str(cache), '--program', 'owned-fixture',
                 '--address', 'not-hex', '--destination', str(invalid)]) == 2
    rejected = json.loads(capsys.readouterr().out)
    assert rejected['ok'] is False
    assert rejected['recovery_accepted'] is False
    assert not invalid.exists()
