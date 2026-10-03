"""Specified source regressions; execution requires separate authorization."""
import hashlib
import json
import os
import sqlite3
import sys

import pytest

from agentdecompile_recovery.corpus import package_authoritative as package
from agentdecompile_recovery.corpus.coverage_evidence import bind_source
from agentdecompile_recovery.corpus.ingest_recovered import parse_recovered


def basis(tmp_path):
    workspace = tmp_path / 'corpus'
    (workspace / 'scripts').mkdir(parents=True)
    (workspace / 'scripts' / 'programs.txt').write_text('synthetic/game.exe\n')
    asm = workspace / 'output' / 'kotor_reconstructed' / 'src' / 'demo'
    asm.mkdir(parents=True)
    (asm / 'functions.s').write_text('F_00401000:\n.byte 0x33,0xc0,0xc3\n')
    (workspace / 'db').mkdir()
    database = workspace / 'db' / 'kotorxid.sqlite'
    with sqlite3.connect(database) as con:
        con.executescript('''
            CREATE TABLE binary(id, repo_path, slug, arch, bits, format);
            CREATE TABLE func(binary_id, addr, size, name, source_file, n_instr);
            INSERT INTO binary VALUES(1,'synthetic/game.exe','demo','x86',32,'pe');
            INSERT INTO func VALUES(1,4198400,3,'canonicalFn','original.c',2);
            INSERT INTO func VALUES(1,4202496,3,'otherFn','other.c',2);
        ''')
    recovered = tmp_path / 'recovered'
    (recovered / 'game').mkdir(parents=True)
    coverage = tmp_path / 'coverage'
    coverage.mkdir()
    config = tmp_path / 'config'
    config.mkdir()
    (config / 'maps.json').write_text(json.dumps({'leaf_to_repo': {'game': 'synthetic/game.exe'}}))
    target = tmp_path / 'target.bin'
    target.write_bytes(b'prefix\x33\xc0\xc3suffix')
    return {'workspace': workspace, 'recovered_dir': recovered, 'coverage_dir': coverage,
            'config_dir': config}


def observed(inputs, name='anonymous', body=b'int fn(void) { return 0; }\r\n', address=0x401000):
    source = inputs['recovered_dir'] / 'game' / (name + '.c')
    source.write_bytes(body)
    target = inputs['workspace'].parent / 'target.bin'
    machine = b'\x33\xc0\xc3'
    row = bind_source({
        'function': name, 'byteExact': True, 'comparisonScope': 'local-function',
        'size': 3, 'originalBytes': machine.hex(),
        'targetSnapshot': {'path': str(target), 'size': len(target.read_bytes()),
                           'sha256': hashlib.sha256(target.read_bytes()).hexdigest()},
        'targetRegion': {'address': address, 'offset': 6, 'size': 3,
                         'sha256': hashlib.sha256(machine).hexdigest()},
    }, body)
    ledger = inputs['coverage_dir'] / 'game.jsonl'
    with ledger.open('a') as stream:
        stream.write(json.dumps(row) + '\n')
    return source, row, ledger


def manifest(inputs, out=None):
    destination = out or inputs['workspace'] / 'output' / 'kotor_authoritative'
    return json.loads((destination / 'metadata' / 'selection.json').read_text()), destination


def test_explicit_basis_copies_bound_bytes_and_keeps_counts_and_scopes(tmp_path, monkeypatch):
    inputs = basis(tmp_path)
    source, row, ledger = observed(inputs)
    database = inputs['workspace'] / 'db' / 'kotorxid.sqlite'
    original_db, original_ledger = database.read_bytes(), ledger.read_bytes()
    # Explicit config must take precedence over unrelated environment configuration.
    monkeypatch.setenv('AGENT_DECOMPILE_CORPUS_CONFIG_DIR', str(tmp_path / 'unrelated'))
    result = package.build(**inputs)
    selection, out = manifest(inputs)
    item = selection['verified_c']['demo'][0]
    assert result['verified_c'] == selection['binaries'][0]['verified_c_count'] == 1
    assert selection['binaries'][0]['local_readable_c_selection_count'] == 1
    assert len(list(out.rglob('*.c'))) == 1
    assert (out / item['path']).read_bytes() == source.read_bytes()
    assert item['sha256'] == item['source_sha256'] == row['sourceSha256']
    assert item['coverage'] == row and item['address'] == '0x00401000'
    assert item['address_basis'] == 'checked-target-region'
    asm = out / 'src' / 'demo' / 'asm'
    assert asm.is_symlink() and not os.path.isabs(os.readlink(asm))
    assert database.read_bytes() == original_db and ledger.read_bytes() == original_ledger
    assert selection['independent_acceptance']['status'] == 'unavailable'
    assert item['independent_acceptance']['address_mapping'] == 'unverified'
    assert 'no C acceptance credit' in selection['assembler_scope']
    readme = (out / 'README.md').read_text()
    assert 'historical local-function' in readme and 'not independently accepted source' in readme
    assert 'whole-image acceptance' in readme and 'portable-recipe' in readme


@pytest.mark.parametrize('missing', ['workspace', 'recovered_dir', 'coverage_dir'])
def test_build_requires_explicit_inputs(tmp_path, missing):
    inputs = basis(tmp_path)
    inputs.pop(missing)
    with pytest.raises(TypeError):
        package.build(**inputs)
    assert not (tmp_path / 'corpus' / 'output' / 'kotor_authoritative').exists()


def test_module_route_refuses_out_only(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['package_authoritative', '--out', str(tmp_path / 'out')])
    with pytest.raises(SystemExit) as refusal:
        package.main()
    assert refusal.value.code == 2 and not (tmp_path / 'out').exists()


@pytest.mark.parametrize('missing', ['database', 'programs', 'asm', 'recovered', 'coverage'])
def test_missing_basis_refuses_before_output_or_input_mutation(tmp_path, missing):
    inputs = basis(tmp_path)
    database = inputs['workspace'] / 'db' / 'kotorxid.sqlite'
    original_db = database.read_bytes()
    paths = {'database': database, 'programs': inputs['workspace'] / 'scripts' / 'programs.txt',
             'asm': inputs['workspace'] / 'output' / 'kotor_reconstructed' / 'src' / 'demo',
             'recovered': inputs['recovered_dir'], 'coverage': inputs['coverage_dir']}
    path = paths[missing]
    if missing == 'asm':
        (path / 'functions.s').unlink()
    elif missing == 'recovered':
        (path / 'game').rmdir()
    path.rmdir() if path.is_dir() else path.unlink()
    with pytest.raises(SystemExit):
        package.build(**inputs)
    assert not (inputs['workspace'] / 'output' / 'kotor_authoritative').exists()
    if missing == 'database':
        assert not database.exists()
    else:
        assert database.read_bytes() == original_db


def test_incompatible_database_is_read_only_refusal(tmp_path):
    inputs = basis(tmp_path)
    database = inputs['workspace'] / 'db' / 'kotorxid.sqlite'
    with sqlite3.connect(database) as con:
        con.execute('DROP TABLE func')
    before = database.read_bytes()
    with pytest.raises(SystemExit, match='incompatible canonical database'):
        package.build(**inputs)
    assert database.read_bytes() == before
    assert not (inputs['workspace'] / 'output' / 'kotor_authoritative').exists()


def test_empty_admitted_ledger_is_visible_zero_local_c(tmp_path):
    inputs = basis(tmp_path)
    assert package.build(**inputs)['verified_c'] == 0
    selection, _ = manifest(inputs)
    assert selection['verified_c'] == {} and selection['binaries'][0]['verified_c_count'] == 0
    assert selection['independent_acceptance']['status'] == 'unavailable'


def test_bound_shim_refused_while_real_c_survives(tmp_path):
    inputs = basis(tmp_path)
    observed(inputs)
    observed(inputs, name='shim', body=b'void shim(void) { _emit 0xc3; }', address=0x402000)
    rows = parse_recovered(inputs['recovered_dir'], inputs['coverage_dir'])
    assert next(row for row in rows if row['name'] == 'shim')['real_c'] == 0
    result = package.build(**inputs)
    selection, _ = manifest(inputs)
    assert result['verified_c'] == 1
    assert any(row['reason'] == 'not_readable_c' for row in selection['rejected_candidates'])


@pytest.mark.parametrize('change', ['legacy', 'stale', 'withdrawn', 'target'])
def test_parser_refusals_retained_and_legacy_bytes_do_not_rescue(tmp_path, change):
    inputs = basis(tmp_path)
    source, row, ledger = observed(inputs)
    if change == 'legacy':
        row = {'function': 'anonymous', 'byteExact': True, 'originalBytes': '33c0c3'}
        ledger.write_text(json.dumps(row) + '\n')
    elif change == 'stale':
        source.write_bytes(b'int edited(void) { return 1; }')
    elif change == 'withdrawn':
        with ledger.open('a') as stream:
            stream.write(json.dumps({'function': 'anonymous', 'byteExact': False}) + '\n')
    else:
        (inputs['workspace'].parent / 'target.bin').write_bytes(b'changed target')
    extracted = inputs['workspace'] / 'extract' / 'funcbytes'
    extracted.mkdir(parents=True)
    (extracted / 'demo.jsonl').write_text(json.dumps({'a': 0x401000, 'b': '33c0c3'}) + '\n')
    before_source, before_ledger = source.read_bytes(), ledger.read_bytes()
    assert package.build(**inputs)['verified_c'] == 0
    selection, _ = manifest(inputs)
    assert len(selection['rejected_candidates']) == 1
    refusal = selection['rejected_candidates'][0]
    assert refusal['path'] == str(source) and refusal['binding'] in {'source', 'target'}
    assert refusal['reason'] and source.read_bytes() == before_source and ledger.read_bytes() == before_ledger
    if change != 'withdrawn':
        assert refusal['coverage'] == row


@pytest.mark.parametrize('hint', ['header', 'symbol'])
def test_conflicting_hint_cannot_override_checked_address(tmp_path, hint):
    inputs = basis(tmp_path)
    body = b'/* address: 0x00402000 */\nint fn(void) {return 0;}' if hint == 'header' else b'int fn(void) {return 0;}'
    source, row, ledger = observed(inputs, body=body)
    if hint == 'symbol':
        row['symbol'] = 'F_00402000'
        ledger.write_text(json.dumps(row) + '\n')
    assert package.build(**inputs)['verified_c'] == 0
    selection, _ = manifest(inputs)
    assert selection['rejected_candidates'][0]['reason'] == hint + '_target_address_mismatch'


def test_duplicate_checked_addresses_are_explicit_refusals(tmp_path):
    inputs = basis(tmp_path)
    observed(inputs)
    observed(inputs, name='second')
    assert package.build(**inputs)['verified_c'] == 1
    selection, _ = manifest(inputs)
    assert selection['rejected_candidates'][0]['reason'] == 'duplicate selected address'


@pytest.mark.parametrize('when', ['after_parser', 'after_snapshot'])
def test_source_mutation_obeys_snapshot_boundary(tmp_path, monkeypatch, when):
    inputs = basis(tmp_path)
    source, row, _ = observed(inputs)
    original = source.read_bytes()
    name = 'parse_recovered' if when == 'after_parser' else '_source_snapshot'
    operation = getattr(package, name)
    def mutate(*args, **kwargs):
        result = operation(*args, **kwargs)
        source.write_bytes(b'int changed(void) {return 42;}')
        return result
    monkeypatch.setattr(package, name, mutate)
    result = package.build(**inputs)
    selection, out = manifest(inputs)
    if when == 'after_parser':
        assert result['verified_c'] == 0
        assert selection['rejected_candidates'][0]['reason'] == 'source_digest_mismatch'
    else:
        assert result['verified_c'] == 1
        item = selection['verified_c']['demo'][0]
        assert (out / item['path']).read_bytes() == original
        assert item['sha256'] == hashlib.sha256(original).hexdigest() == row['sourceSha256']


def test_ledger_edit_does_not_replace_pinned_observation(tmp_path, monkeypatch):
    inputs = basis(tmp_path)
    _, row, ledger = observed(inputs)
    original = package.parse_recovered
    def replace_ledger(*args, **kwargs):
        ledger.write_text(json.dumps({'function': 'anonymous', 'byteExact': False}) + '\n')
        return original(*args, **kwargs)
    monkeypatch.setattr(package, 'parse_recovered', replace_ledger)
    assert package.build(**inputs)['verified_c'] == 1
    selection, _ = manifest(inputs)
    assert selection['verified_c']['demo'][0]['coverage'] == row


def test_different_observation_cannot_be_attached_by_name(tmp_path, monkeypatch):
    inputs = basis(tmp_path)
    observed(inputs)
    original = package.parse_recovered
    def changed_candidate(*args, **kwargs):
        rows = original(*args, **kwargs)
        rows[0]['target_sha256'] = '0' * 64
        return rows
    monkeypatch.setattr(package, 'parse_recovered', changed_candidate)
    assert package.build(**inputs)['verified_c'] == 0
    selection, _ = manifest(inputs)
    assert selection['rejected_candidates'][0]['reason'] == 'candidate_observation_mismatch'


@pytest.mark.parametrize('existing', ['tree', 'dangling_symlink'])
def test_existing_output_preserved(tmp_path, existing):
    inputs = basis(tmp_path)
    out = tmp_path / 'existing'
    if existing == 'tree':
        out.mkdir()
        (out / 'user.txt').write_bytes(b'user original')
    else:
        out.symlink_to(tmp_path / 'absent')
    with pytest.raises(SystemExit, match='refusing to overwrite'):
        package.build(out, **inputs)
    if existing == 'tree':
        assert (out / 'user.txt').read_bytes() == b'user original'
    else:
        assert out.is_symlink() and not (tmp_path / 'absent').exists()
