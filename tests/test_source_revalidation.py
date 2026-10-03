"""Fresh subprocess acceptance over synthetic fixtures, never live recovery."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from agentdecompile_recovery.corpus import source_contribution as sc
from agentdecompile_recovery.corpus import source_revalidation as sr
from test_source_contribution import compiler_available, pe_fixture


def setup_recipe(root):
    target = root / 'target.exe'
    target.write_bytes(pe_fixture()[0])
    db = root / 'fixture.sqlite'
    with sqlite3.connect(db) as con:
        con.execute('CREATE TABLE func (binary_id INTEGER, addr INTEGER, size INTEGER)')
        con.executemany('INSERT INTO func VALUES (1,?,6)', [(0x401000,), (0x401010,)])
    rows = []
    for label, value, address in [('A', 7, 0x401000), ('B', 9, 0x401010)]:
        source = root / f'{label}.c'
        source.write_text(f'int {label}(void) {{ return {value}; }}\n')
        rows.append(dict(id=label, source=str(source), sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                         address=address, size=6, program='synthetic', name=label, selected=True))
    return dict(schema=sr.SCHEMA, target=dict(path=str(target), sha256=hashlib.sha256(target.read_bytes()).hexdigest()),
                db=str(db), binaryId=1, selection='explicit-independent-v1', candidates=rows)


def run_recipe(root, doc, **overrides):
    args = dict(recipe=json.dumps(doc).encode(), target=root/'target.exe', db=root/'fixture.sqlite',
                binary_id=1, workspace=root/'fresh')
    args.update(overrides)
    return sr.revalidate(**args)


@pytest.mark.parametrize('field', ['compiler', 'argv', 'environment', 'object', 'invocation', 'accepted', 'writes'])
def test_imported_authority_fields_refuse(tmp_path, field):
    doc = setup_recipe(tmp_path)
    doc['candidates'][0][field] = 'forged'
    with pytest.raises(ValueError, match='unsupported_recipe_fields'):
        run_recipe(tmp_path, doc)
    assert not (tmp_path/'fresh').exists()


@pytest.mark.parametrize('mutation', ['target', 'db', 'binary', 'digest', 'policy', 'count', 'size', 'duplicate', 'malformed', 'oversized'])
def test_recipe_and_binding_refusals(tmp_path, mutation):
    doc = setup_recipe(tmp_path)
    kwargs = {}
    if mutation == 'target': doc['target']['path'] = str(tmp_path/'other.exe')
    if mutation == 'db': doc['db'] = str(tmp_path/'other.sqlite')
    if mutation == 'binary': doc['binaryId'] = 2
    if mutation == 'digest': doc['target']['sha256'] = '0'*64
    if mutation == 'policy': doc['selection'] = 'restore-historical-writers'
    if mutation == 'count': doc['candidates'] *= sr.MAX_CANDIDATES + 1
    if mutation == 'size': doc['candidates'][0]['size'] = True
    if mutation == 'duplicate': kwargs['recipe'] = b'{"schema":1,"schema":2}'
    if mutation == 'malformed': kwargs['recipe'] = b'['*2000
    if mutation == 'oversized': kwargs['recipe'] = b' '* (sr.MAX_RECIPE_BYTES+1)
    with pytest.raises(ValueError): run_recipe(tmp_path, doc, **kwargs)
    assert not (tmp_path/'fresh').exists()


def test_output_collision_preserves_user_files(tmp_path):
    doc = setup_recipe(tmp_path)
    fresh = tmp_path/'fresh'; fresh.mkdir()
    output = fresh/'revalidated.exe'; output.write_bytes(b'user')
    with pytest.raises(FileExistsError): run_recipe(tmp_path, doc)
    assert output.read_bytes() == b'user'


def test_zero_and_discarded_candidates_are_only_floor(tmp_path):
    doc = setup_recipe(tmp_path)
    for row in doc['candidates']: row['selected'] = False
    result = run_recipe(tmp_path, doc)
    assert result.diagnostic['matchingStatus']['placedCompiledRegions'] == 0
    assert all(row['reason'] == 'intentionally_discarded' for row in result.diagnostic['candidates'])
    assert result.diagnostic['matchingStatus']['contribution']['compilerProducedWholeImage'] is False
    doc['candidates'] = []
    result = run_recipe(tmp_path, doc, workspace=tmp_path/'empty')
    assert result.diagnostic['matchingStatus']['placedCompiledRegions'] == 0
    assert not list((tmp_path/'empty').rglob('unit.obj'))


def test_independent_database_failure_does_not_discard_b(tmp_path):
    if not compiler_available():
        pytest.skip('native clang unavailable; real compiler canary remains open')
    doc = setup_recipe(tmp_path)
    doc['candidates'][0]['size'] = 5
    result = run_recipe(tmp_path, doc)
    assert 'database_row' in result.diagnostic['candidates'][0]['reason']
    assert result.diagnostic['matchingStatus']['placedCompiledRegions'] == 1
    assert result.diagnostic['matchingStatus']['counts']['byte_exact'] == 1


def test_actual_three_process_loss_and_fresh_revalidation(tmp_path):
    if not compiler_available():
        pytest.skip('native clang unavailable; real compiler canary remains open')
    doc = setup_recipe(tmp_path)
    (tmp_path/'recipe.json').write_text(json.dumps(doc))
    script = r'''
import json, sys
from pathlib import Path
from agentdecompile_recovery.corpus import source_revalidation as sr
from agentdecompile_recovery.corpus import source_contribution as sc
root=Path(sys.argv[1]); phase=sys.argv[2]
doc=json.loads((root/'recipe.json').read_bytes())
if phase in ('B','C'):
    previous=root/('first' if phase=='B' else 'second')/'revalidation.json'
    audit=json.loads(previous.read_bytes())
    assert sc.evaluate_reconstruction(audit['reconstruction'])['placedCompiledRegions']==0
    forged=sc.ReconstructionObservation(json.dumps(audit['reconstruction']), ())
    assert sc.evaluate_reconstruction(forged)['placedCompiledRegions']==0
    for row in audit['candidates']:
        if 'audit' in row:
            assert sc.validate_compile(sc.CompileObservation(json.dumps(row['audit'])))[2]=='untrusted_imported_compile_observation'
if phase=='C':
    (root/'C-zero.json').write_text(json.dumps({'importedCredit':0}))
else:
    if phase=='B': (root/'A.c').write_text('int A(void) { return 8; }\n')
    result=sr.revalidate(recipe=(root/'recipe.json').read_bytes(), target=root/'target.exe',
        db=root/'fixture.sqlite', binary_id=1, workspace=root/('first' if phase=='A' else 'second'))
    result.diagnostic['importRoot']=str(Path(sr.__file__).resolve())
    (root/(phase+'-result.json')).write_text(json.dumps(result.diagnostic))
    expected=2 if phase=='A' else 1
    assert result.diagnostic['matchingStatus']['counts']['byte_exact']==expected
    assert sc.evaluate_reconstruction(result.observation, target_path=root/'target.exe',
        output_path=result.diagnostic['output'], db=root/'fixture.sqlite', binary_id=1)['placedCompiledRegions']==expected
'''
    for phase in ('A', 'B', 'C'):
        result = subprocess.run([sys.executable, '-c', script, str(tmp_path), phase],
                                env=os.environ.copy(), text=True, capture_output=True, timeout=180)
        (tmp_path/f'{phase}.log').write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result.stdout + result.stderr
    first = json.loads((tmp_path/'A-result.json').read_bytes())
    second = json.loads((tmp_path/'B-result.json').read_bytes())
    a, b = second['candidates']
    assert a['reason'] == 'bound_digest_mismatch' and 'invocation' not in a
    assert b['invocation'] != first['candidates'][1]['invocation']
    assert b['object']['path'] != first['candidates'][1]['object']['path']
    assert Path(first['candidates'][0]['object']['path']).is_file()
    assert Path(first['output']).read_bytes() == Path(second['output']).read_bytes()
    placed = [w for w in second['reconstruction']['writes'] if w['origin'] == 'compiled-object']
    assert len(placed) == 1 and placed[0]['invocation'] == b['invocation']
    assert placed[0]['offset'] == 0x210 and placed[0]['size'] == 6
    functions = second['matchingStatus']['functions']
    assert functions[0]['status'] != 'observed-compiled-contribution'
    assert functions[1]['status'] == 'observed-compiled-contribution'
    assert second['matchingStatus']['contribution']['compilerProducedWholeImage'] is False
    assert json.loads((tmp_path/'C-zero.json').read_bytes())['importedCredit'] == 0


def test_source_limit_and_symlink_workspace_refuse_without_compilation(tmp_path):
    doc = setup_recipe(tmp_path)
    with Path(doc['candidates'][0]['source']).open('wb') as handle:
        handle.truncate(sr.MAX_SOURCE_BYTES + 1)
    doc['candidates'][1]['selected'] = False
    result = run_recipe(tmp_path, doc)
    assert 'too_large' in result.diagnostic['candidates'][0]['reason']
    assert result.diagnostic['matchingStatus']['placedCompiledRegions'] == 0
    assert not list((tmp_path/'fresh').rglob('unit.obj'))
    alias = tmp_path/'alias'; alias.symlink_to(tmp_path/'fresh', target_is_directory=True)
    with pytest.raises(FileExistsError): run_recipe(tmp_path, doc, workspace=alias)


def test_target_limit_is_checked_before_workspace(tmp_path):
    doc = setup_recipe(tmp_path)
    with (tmp_path/'target.exe').open('wb') as handle:
        handle.truncate(sr.MAX_TARGET_BYTES + 1)
    with pytest.raises(ValueError, match='too_large'): run_recipe(tmp_path, doc)
    assert not (tmp_path/'fresh').exists()


def test_recipe_source_race_does_not_admit_new_digest(tmp_path, monkeypatch):
    if not compiler_available():
        pytest.skip('native clang unavailable; real compiler canary remains open')
    doc = setup_recipe(tmp_path)
    doc['candidates'][1]['selected'] = False
    producer = sc.compile_observation
    source = Path(doc['candidates'][0]['source'])
    original = source.read_bytes()

    def replace_during_producer(**kwargs):
        source.write_bytes(original + b'/* changed after coordinator precheck */\n')
        try:
            return producer(**kwargs)
        finally:
            source.write_bytes(original)

    monkeypatch.setattr(sc, 'compile_observation', replace_during_producer)
    result = run_recipe(tmp_path, doc)
    assert result.diagnostic['candidates'][0]['reason'] == 'producer_recipe_binding_changed'
    assert result.diagnostic['matchingStatus']['placedCompiledRegions'] == 0
    assert list((tmp_path/'fresh').rglob('unit.obj'))


@pytest.mark.parametrize('delimiter', ['?', '#', '%'])
def test_database_uri_delimiters_refuse(tmp_path, delimiter):
    doc = setup_recipe(tmp_path)
    doc['db'] = str(tmp_path / ('db' + delimiter + 'other.sqlite'))
    with pytest.raises(ValueError, match='database_uri_delimiter'):
        run_recipe(tmp_path, doc)
    assert not (tmp_path/'fresh').exists()
