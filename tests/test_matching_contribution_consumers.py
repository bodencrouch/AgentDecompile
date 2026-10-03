import json
from pathlib import Path
import sqlite3

import pytest

from agentdecompile_recovery.corpus import matching_status, finish_binary
from agentdecompile_recovery.corpus.dashboard import byte_parity
from test_source_contribution import pe_fixture, compiled_pair, compiler_available
from agentdecompile_recovery.corpus import source_contribution as sc


def corpus_fixture(db, *, binary_id=1, raw=None):
    raw = pe_fixture()[0] if raw is None else raw
    with sqlite3.connect(db) as con:
        con.execute('CREATE TABLE binary(id INTEGER,content_sha256 TEXT)')
        con.execute('INSERT INTO binary VALUES(?,?)', (binary_id, sc.digest(raw)))
        con.execute('CREATE TABLE func(binary_id INTEGER,addr INTEGER,size INTEGER)')
        con.executemany('INSERT INTO func VALUES(?,?,?)',
                        [(binary_id, 0x401000, 6), (binary_id, 0x401010, 6)])


def other_image():
    raw = bytearray(pe_fixture()[0])
    raw[-1] ^= 1  # Outside both spans: same function bytes, different complete image.
    return bytes(raw)


def assert_consumers(image, target, output, db, binary_id, root, monkeypatch, expected):
    report = root / 'report.json'
    assert matching_status.main(['--target', str(target), '--db', str(db),
        '--binary-id', str(binary_id), '--src-dir', str(root), '--out-report', str(report)],
        reconstruction_observation=image) == 0
    state = json.loads(report.read_text())
    assert state['counts']['byte_exact'] == state['placedCompiledRegions'] == expected
    assert state['placedCompiledBytes'] == 6 * expected
    monkeypatch.setattr(byte_parity, '_TARGET', str(target))
    monkeypatch.setattr(byte_parity, '_REBUILT', str(output))
    dashboard = byte_parity.byte_parity_state(reconstruction_observation=image, db=db, binary_id=binary_id)
    assert dashboard['qualifiedCorpusFunctions'] == dashboard['byteExactRecoveredC'] == expected
    assert dashboard['wholeFileByteIdentical'] is True
    assert dashboard['compilerProducedWholeImage'] is False
    assert all(not row['semanticIdentityVerified'] for row in
               dashboard['qualifiedFunctionContribution']['candidates'])
    return dashboard


def test_status_legacy_floor_and_ok_never_count_as_contribution(tmp_path):
    target=tmp_path/'target.exe';target.write_bytes(pe_fixture()[0])
    db=tmp_path/'corpus.sqlite'
    with sqlite3.connect(db) as con:
        con.execute('CREATE TABLE func(binary_id INTEGER,addr INTEGER,size INTEGER)')
        con.execute('INSERT INTO func VALUES(1,?,6)',(0x401000,))
    (tmp_path/'A_00401000.c').write_text('int A(void){return 7;}')
    receipts=tmp_path/'receipts.json';receipts.write_text(json.dumps({'results':[{'addr':'0x401000','ok':True}]}))
    floor=tmp_path/'floor.json';floor.write_text('[4198400]')
    report=tmp_path/'report.json'
    assert matching_status.main(['--target',str(target),'--db',str(db),'--binary-id','1',
        '--src-dir',str(tmp_path),'--receipts',str(receipts),'--byte-exact-floor',str(floor),
        '--out-report',str(report)]) == 0
    state=json.loads(report.read_text())
    assert state['placedCompiledRegions'] == state['rawLocalObservedC'] == state['counts']['byte_exact'] == 0
    assert state['historicalFloorDiagnostic'] == 1
    assert state['wholeFileByteIdentical'] is None
    assert state['variants']['byte_accurate']['exact_placement_hash_equal'] is None


def test_dashboard_rejects_legacy_totals_and_terminal_booleans(tmp_path,monkeypatch):
    target=tmp_path/'target.exe';target.write_bytes(pe_fixture()[0])
    report=tmp_path/'report.json';report.write_text(json.dumps({'totalFunctions':100,'byteExactRecoveredC':70,'rawLocalObservedC':3}))
    variants=tmp_path/'variants.json';variants.write_text(json.dumps({'code_total':100,'variants':{'byte_accurate':{'c':90}}}))
    receipt=tmp_path/'terminal.json';receipt.write_text(json.dumps({'schema':'agentdecompile.full-image-compiler-objdiff-receipt.v1',
        'verified':True,'compilerProducedWholeImage':True,'wholeFileByteIdentical':True,'target':sc.fingerprint(target)}))
    monkeypatch.setenv(byte_parity._REPORT_ENV,str(report));monkeypatch.setenv(byte_parity._VARIANTS_ENV,str(variants))
    monkeypatch.setenv(byte_parity._FULL_IMAGE_RECEIPT_ENV,str(receipt))
    monkeypatch.setattr(byte_parity,'_TARGET',str(target));monkeypatch.setattr(byte_parity,'_REBUILT',str(target))
    monkeypatch.setattr(byte_parity,'_text_permuter_closed_count',lambda:20)
    state=byte_parity.byte_parity_state()
    assert state['placedCompiledRegions'] == state['byteExactRecoveredC'] == 0
    assert state['rawLocalObservedC'] == 3
    assert state['compilerProducedWholeImage'] is False
    assert state['variants']['byteAccurate']['c'] == 0
    assert finish_binary.contribution_state()['placedCompiledRegions'] == 0


def test_explicit_live_observation_reaches_finish_and_dashboard(tmp_path,monkeypatch):
    target,observations=compiled_pair(tmp_path)
    output=tmp_path/'out.exe';image=sc.reconstruct(target=target,output=output,observations=observations)
    assert finish_binary.contribution_state(image,target_path=target)['placedCompiledRegions'] == 2
    monkeypatch.setattr(byte_parity,'_TARGET',str(target));monkeypatch.setattr(byte_parity,'_REBUILT',str(output))
    state=byte_parity.byte_parity_state(reconstruction_observation=image)
    assert state['placedCompiledRegions'] == 2
    assert state['placedCompiledBytes'] == 12
    assert state['byteExactRecoveredC'] == state['qualifiedCorpusFunctions'] == 0
    assert state['wholeFileByteIdentical'] is True
    assert state['compilerProducedWholeImage'] is False


def test_selected_corpus_requires_exact_producer_row_and_size(tmp_path):
    target,observations=compiled_pair(tmp_path)
    image=sc.reconstruct(target=target,output=tmp_path/'out.exe',observations=observations)
    db=tmp_path/'different.sqlite'
    with sqlite3.connect(db) as con:
        con.execute('CREATE TABLE func(binary_id INTEGER,addr INTEGER,size INTEGER)')
        con.execute('INSERT INTO func VALUES(9,?,32)',(0x401000,))
    result=sc.evaluate_reconstruction(image,db=db,binary_id=9)
    assert result['placedCompiledRegions']==0
    report=tmp_path/'report.json'
    assert matching_status.main(['--target',str(target),'--db',str(db),'--binary-id','9',
        '--src-dir',str(tmp_path),'--out-report',str(report)],reconstruction_observation=image)==0
    state=json.loads(report.read_text())
    assert state['counts']['byte_exact']==state['placedCompiledRegions']==state['placedCompiledBytes']==0
    assert state['variants']['byte_accurate']['c']==0


def test_qualified_dashboard_and_watch_use_selected_corpus_denominator(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from agentdecompile_recovery import corpus
    from agentdecompile_recovery.corpus import matching_watch
    db=tmp_path/'corpus.sqlite'
    corpus_fixture(db)
    with sqlite3.connect(db) as con:
        con.executemany('INSERT INTO func VALUES(1,?,?)',[(0x401020,1),(0x401021,1)])
    target,observations=compiled_pair(tmp_path,db=db,binary_id=1)
    output=tmp_path/'out.exe';image=sc.reconstruct(target=target,output=output,observations=observations)
    monkeypatch.setattr(byte_parity,'_TARGET',str(target));monkeypatch.setattr(byte_parity,'_REBUILT',str(output))
    state=byte_parity.byte_parity_state(reconstruction_observation=image,db=db,binary_id=1)
    assert state['placedCompiledRegions']==state['qualifiedCorpusFunctions']==2
    assert state['totalFunctions']==4 and state['coveragePct']==50
    progress=[]
    monkeypatch.setattr(corpus,'discord_notify',SimpleNamespace(announce_progress=lambda **kwargs:progress.append(kwargs),
        load_settings=lambda:{'last_corpus_report':float('inf')}),raising=False)
    monkeypatch.setattr(corpus,'corpus_report',SimpleNamespace(),raising=False)
    args=SimpleNamespace(target=target,db=db,binary_id=1,src_dir=tmp_path,receipts=None,func_bytes=None,
        out_exe=output,out_manifest=None,out_report=None,byte_exact_floor=None,reconstruction_observation=image)
    stats=matching_watch.one_pass(args)
    assert stats['functions']==4 and stats['placedCompiledRegions']==2
    assert progress==[{'program':tmp_path.name,'byte_exact':2,'total':4,'byte_identical':False,'min_delta':1}]


def test_matching_and_dashboard_require_bound_complete_target_content(tmp_path, monkeypatch):
    db = tmp_path / 'corpus.sqlite'
    corpus_fixture(db)
    target, observations = compiled_pair(tmp_path, db=db, binary_id=1)
    assert all(obs.record['selectedRow']['binarySha256'] == sc.digest(target.read_bytes())
               for obs in observations)
    output = tmp_path / 'out.exe'
    image = sc.reconstruct(target=target, output=output, observations=observations)
    state = assert_consumers(image, target, output, db, 1, tmp_path, monkeypatch, 2)
    assert state['placedCompiledRegions'] == 2 and state['placedCompiledBytes'] == 12


def test_equal_spans_wrong_selected_image_refuses_before_compiler(tmp_path, monkeypatch):
    db = tmp_path / 'corpus.sqlite'
    corpus_fixture(db, raw=other_image())
    target = tmp_path / 'target.exe'; target.write_bytes(pe_fixture()[0])
    source = tmp_path / 'A.c'; source.write_text('int A(void){return 7;}')

    def forbidden_toolchain(*args):
        pytest.fail('selected image must refuse before any compiler/toolchain invocation')

    monkeypatch.setattr(sc, '_toolchain', forbidden_toolchain)
    with pytest.raises(ValueError, match='^selected_binary_content_mismatch$'):
        sc.compile_observation(source=source, target=target, address=0x401000, size=6,
                               workspace=tmp_path / 'owned', db=db, binary_id=1)
    assert not (tmp_path / 'owned').exists()
    assert source.is_file() and target.read_bytes() == pe_fixture()[0]


@pytest.mark.parametrize('case', ['missing_table', 'missing_column', 'missing_row', 'duplicate_row',
                                 'null', 'empty', 'uppercase', 'malformed', 'unreadable_sqlite'])
def test_unknown_selected_identity_refuses_and_anonymous_evidence_survives(tmp_path, monkeypatch, case):
    db = tmp_path / 'corpus.sqlite'
    corpus_fixture(db)
    with sqlite3.connect(db) as con:
        if case == 'missing_table': con.execute('DROP TABLE binary')
        elif case == 'missing_column': con.execute('ALTER TABLE binary RENAME COLUMN content_sha256 TO old_digest')
        elif case == 'missing_row': con.execute('DELETE FROM binary')
        elif case == 'duplicate_row': con.execute('INSERT INTO binary SELECT * FROM binary')
        elif case in ('null', 'empty', 'uppercase', 'malformed'):
            values = {'null': None, 'empty': '', 'uppercase': sc.digest(pe_fixture()[0]).upper(), 'malformed': 'wrong'}
            con.execute('UPDATE binary SET content_sha256=?', (values[case],))
    if case == 'unreadable_sqlite': db.write_bytes(b'not sqlite')
    before = db.read_bytes()
    target, observations = compiled_pair(tmp_path)  # Genuine independent standalone evidence.
    output = tmp_path / 'out.exe'
    image = sc.reconstruct(target=target, output=output, observations=observations)

    def forbidden_toolchain(*args):
        pytest.fail('unknown selected identity must refuse before compiler invocation')

    monkeypatch.setattr(sc, '_toolchain', forbidden_toolchain)
    with pytest.raises(ValueError, match='^missing_or_invalid_selected_binary_content_identity$'):
        sc.compile_observation(source=tmp_path / 'A.c', target=target, address=0x401000, size=6,
                               workspace=tmp_path / 'refused', db=db, binary_id=1)
    qualified = sc.evaluate_reconstruction(image, db=db, binary_id=1)
    assert qualified['placedCompiledRegions'] == qualified['placedCompiledBytes'] == 0
    assert all('missing_or_invalid_selected_binary_content_identity' in row['reason']
               for row in qualified['candidates'])
    monkeypatch.setattr(byte_parity, '_TARGET', str(target))
    monkeypatch.setattr(byte_parity, '_REBUILT', str(output))
    dashboard = byte_parity.byte_parity_state(reconstruction_observation=image, db=db, binary_id=1)
    assert dashboard['qualifiedCorpusFunctions'] == 0
    assert dashboard['placedCompiledRegions'] == 2 and dashboard['placedCompiledBytes'] == 12
    assert dashboard['wholeFileByteIdentical'] is True
    assert db.read_bytes() == before  # No digest backfill or candidate deletion.
    assert all(Path(obs.record['object']['path']).is_file() for obs in observations)


def test_missing_expected_digest_and_function_extent_refuse(tmp_path):
    db = tmp_path / 'corpus.sqlite'
    corpus_fixture(db)
    for expected in (None, '', 'INVALID'):
        with pytest.raises(ValueError, match='missing_or_invalid_selected_binary_content_identity'):
            sc._db_row(db, 1, 0x401000, 6, target_sha256=expected)
    assert sc._db_row(None, 1, 0x401000, 6) is None
    for address, size in ((0x401000, 5), (0x401020, 6)):
        with pytest.raises(ValueError, match='selected_database_row_changed_or_ambiguous'):
            sc._db_row(db, 1, address, size, target_sha256=sc.digest(pe_fixture()[0]))
    with sqlite3.connect(db) as con:
        con.execute('INSERT INTO func VALUES(1,?,6)', (0x401000,))
    with pytest.raises(ValueError, match='selected_database_row_changed_or_ambiguous'):
        sc._db_row(db, 1, 0x401000, 6, target_sha256=sc.digest(pe_fixture()[0]))
    with sqlite3.connect(db) as con:
        con.execute('DROP TABLE func')
    with pytest.raises(ValueError, match='selected_database_row_changed_or_ambiguous'):
        sc._db_row(db, 1, 0x401000, 6, target_sha256=sc.digest(pe_fixture()[0]))


def test_selected_content_changes_before_publication_refuse_capability(tmp_path, monkeypatch):
    if not compiler_available():
        pytest.skip('native clang unavailable; publication-race canary remains open')
    db = tmp_path / 'corpus.sqlite'
    corpus_fixture(db)
    target = tmp_path / 'target.exe'; target.write_bytes(pe_fixture()[0])
    source = tmp_path / 'A.c'; source.write_text('int A(void){return 7;}')
    original = sc.parse_coff
    before = set(sc._COMPILES)

    def change_selected_content(raw):
        parsed = original(raw)  # Keep the genuine compiler/object observation intact.
        with sqlite3.connect(db) as con:
            con.execute('UPDATE binary SET content_sha256=? WHERE id=1', (sc.digest(other_image()),))
        return parsed

    monkeypatch.setattr(sc, 'parse_coff', change_selected_content)
    with pytest.raises(ValueError, match='^selected_binary_content_mismatch$'):
        sc.compile_observation(source=source, target=target, address=0x401000, size=6,
                               workspace=tmp_path / 'owned', db=db, binary_id=1)
    assert set(sc._COMPILES) == before
    assert list((tmp_path / 'owned').rglob('unit.obj'))
    assert not list((tmp_path / 'owned').rglob('compile-observation.json'))


def test_selected_content_withdraws_credit_but_independent_binary_survives(tmp_path, monkeypatch):
    db = tmp_path / 'corpus.sqlite'
    corpus_fixture(db)
    with sqlite3.connect(db) as con:
        con.execute('INSERT INTO binary VALUES(2,?)', (sc.digest(pe_fixture()[0]),))
        con.execute('INSERT INTO func SELECT 2,addr,size FROM func WHERE binary_id=1')
    target, observations = compiled_pair(tmp_path, db=db, binary_id=1)
    output = tmp_path / 'out.exe'
    image = sc.reconstruct(target=target, output=output, observations=observations)
    independent = tmp_path / 'independent'; independent.mkdir()
    other_target, other_observations = compiled_pair(independent, db=db, binary_id=2)
    other_output = independent / 'out.exe'
    other = sc.reconstruct(target=other_target, output=other_output, observations=other_observations)
    with sqlite3.connect(db) as con:
        con.execute('UPDATE binary SET content_sha256=? WHERE id=1', (sc.digest(other_image()),))
    assert all(sc.validate_compile(obs)[2] == 'selected_binary_content_mismatch' for obs in observations)
    assert_consumers(image, target, output, db, 1, tmp_path, monkeypatch, 0)
    assert all(sc.validate_compile(obs)[2] is None for obs in other_observations)
    assert_consumers(other, other_target, other_output, db, 2, independent, monkeypatch, 2)


def test_unrelated_database_edits_preserve_selected_contribution(tmp_path, monkeypatch):
    db = tmp_path / 'corpus.sqlite'
    corpus_fixture(db)
    target, observations = compiled_pair(tmp_path, db=db, binary_id=1)
    output = tmp_path / 'out.exe'
    image = sc.reconstruct(target=target, output=output, observations=observations)
    with sqlite3.connect(db) as con:
        con.execute('INSERT INTO binary VALUES(2,?)', (sc.digest(other_image()),))
        con.execute('UPDATE binary SET content_sha256=NULL WHERE id=2')
        con.execute('INSERT INTO func VALUES(2,?,32)', (0x401000,))
        con.execute('UPDATE func SET size=24 WHERE binary_id=2')
        con.execute('INSERT INTO func VALUES(1,?,1)', (0x401020,))
    assert all(sc.validate_compile(obs)[2] is None for obs in observations)
    assert_consumers(image, target, output, db, 1, tmp_path, monkeypatch, 2)


@pytest.mark.parametrize('case', ['same_filename_source_edit', 'discarded', 'floor_overwritten'])
def test_correct_physical_binding_preserves_existing_contribution_gates(tmp_path, monkeypatch, case):
    db = tmp_path / 'corpus.sqlite'
    corpus_fixture(db)
    target, observations = compiled_pair(tmp_path, db=db, binary_id=1)
    invocation = observations[0].record['invocation']
    options = {'discard': (invocation,)} if case == 'discarded' else {}
    if case == 'floor_overwritten': options['overwrite_with_floor'] = (invocation,)
    output = tmp_path / 'out.exe'
    image = sc.reconstruct(target=target, output=output, observations=observations, **options)
    if case == 'same_filename_source_edit':
        source = Path(observations[0].record['source']['path'])
        source.write_text('int A(void){return 8;}')
        assert sc.validate_compile(observations[0])[2] == 'source_changed'
    state = assert_consumers(image, target, output, db, 1, tmp_path, monkeypatch, 1)
    accepted = [row for row in state['qualifiedFunctionContribution']['candidates'] if row['accepted']]
    assert accepted[0]['invocation'] == observations[1].record['invocation']
    assert sc.evaluate_reconstruction(image.record, db=db, binary_id=1)['placedCompiledRegions'] == 0
    forged = sc.ReconstructionObservation(image.record_json, image.candidates)
    assert sc.evaluate_reconstruction(forged, db=db, binary_id=1)['placedCompiledRegions'] == 0
