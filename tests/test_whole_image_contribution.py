from pathlib import Path
import sqlite3

import pytest

from agentdecompile_recovery.corpus import source_contribution as sc
from agentdecompile_recovery.corpus import whole_image_relink as wir
from test_source_contribution import compiled_pair, pe_fixture


def test_decisive_discard_a_fallback_b_survives(tmp_path):
    target, observations = compiled_pair(tmp_path)
    image = wir.reconstruct(target=target, output=tmp_path/'out.exe', observations=observations,
                            discard=[observations[0].record['invocation']])
    result = wir.evaluate_reconstruction(image)
    assert result['wholeFileByteIdentical'] is True
    assert [row['contributedBytes'] for row in result['candidates']] == [0, 6]
    assert result['placedCompiledRegions'] == 1
    assert next(w for w in image.record['writes'] if w['offset'] == 0x200)['origin'] == 'preserved-floor'
    assert next(w for w in image.record['writes'] if w['offset'] == 0x210)['origin'] == 'compiled-object'
    with pytest.raises(ValueError, match='unsatisfied'):
        wir.reconstruct(target=target, output=tmp_path/'refused.exe', observations=observations,
                        discard=[observations[0].record['invocation']], fallback=False)
    assert not (tmp_path/'refused.exe').exists()


def test_floor_only_and_legacy_static_bytes_get_zero_credit(tmp_path):
    target=tmp_path/'target.exe'; target.write_bytes(pe_fixture()[0])
    image=sc.reconstruct(target=target, output=tmp_path/'floor.exe')
    result=sc.evaluate_reconstruction(image)
    assert result['wholeFileByteIdentical'] is True
    assert result['placedCompiledBytes'] == 0
    db=tmp_path/'corpus.sqlite'
    with sqlite3.connect(db) as con:
        con.execute('CREATE TABLE func(binary_id INTEGER, addr INTEGER, size INTEGER)')
        con.execute('INSERT INTO func VALUES(1,?,6)', (0x401000,))
    bins=tmp_path/'bins'; bins.mkdir(); (bins/'00401000.bin').write_bytes(b'\xb8\x07\0\0\0\xc3')
    output, stats=wir.rebuild(target.read_bytes(),str(db),1,str(bins))
    assert output == target.read_bytes()
    assert stats['diagnostic_equal_artifacts'] == 1
    assert stats['substituted_byte_equal'] == stats['placedCompiledRegions'] == 0


def test_currentness_is_projected_to_candidate_and_output_region(tmp_path):
    target, observations = compiled_pair(tmp_path)
    image = sc.reconstruct(target=target, output=tmp_path/'out.exe', observations=observations)
    a_source = Path(observations[0].record['source']['path']); original = a_source.read_bytes()
    a_source.write_bytes(original + b'\n')
    assert [r['contributedBytes'] for r in sc.evaluate_reconstruction(image)['candidates']] == [0,6]
    a_source.write_bytes(original)
    assert sc.evaluate_reconstruction(image)['placedCompiledRegions'] == 2
    a_object=Path(observations[0].record['object']['path']); obj=a_object.read_bytes()
    a_object.write_bytes(obj + b'tamper')
    assert [r['contributedBytes'] for r in sc.evaluate_reconstruction(image)['candidates']] == [0,6]
    a_object.write_bytes(obj)
    output=tmp_path/'out.exe'; raw=bytearray(output.read_bytes()); raw[0x200]^=1;output.write_bytes(raw)
    result=sc.evaluate_reconstruction(image)
    assert result['wholeFileByteIdentical'] is False
    assert result['outputSnapshotCurrent'] is False
    assert [r['contributedBytes'] for r in result['candidates']] == [0,6]
    target.write_bytes(target.read_bytes()+b'tamper')
    assert sc.evaluate_reconstruction(image)['placedCompiledRegions'] == 0


def test_collision_order_and_invalid_same_address_candidate_do_not_hide_valid(tmp_path):
    target, observations = compiled_pair(tmp_path)
    source=tmp_path/'C.c'; source.write_text('int C(void) { return 7; }')
    c=sc.compile_observation(source=source,target=target,address=0x401000,size=6,workspace=tmp_path/'owned',name='C')
    source.write_text('int C(void) { return 0; }')
    forward=sc.reconstruct(target=target,output=tmp_path/'forward.exe',observations=[c,*observations])
    reverse=sc.reconstruct(target=target,output=tmp_path/'reverse.exe',observations=[*reversed(observations),c])
    f=sc.evaluate_reconstruction(forward);r=sc.evaluate_reconstruction(reverse)
    assert f['placedCompiledRegions'] == r['placedCompiledRegions'] == 2
    assert sorted(row['candidate']['name'] for row in f['candidates'] if row['accepted']) == ['A','B']
    assert forward.record['plan'] == reverse.record['plan']


def test_cache_loss_and_crash_artifacts_do_not_restore_trust(tmp_path):
    target, observations=compiled_pair(tmp_path)
    image=sc.reconstruct(target=target,output=tmp_path/'out.exe',observations=observations)
    sc._IMAGES.pop(image)
    assert sc.evaluate_reconstruction(image)['placedCompiledRegions'] == 0
    sc._COMPILES.pop(observations[0])
    assert sc.validate_compile(observations[0])[2] == 'untrusted_imported_compile_observation'
    assert sc.validate_compile(observations[1])[2] is None


def test_later_floor_overwrite_withdraws_actual_compiled_writer(tmp_path):
    target, observations=compiled_pair(tmp_path)
    image=sc.reconstruct(target=target,output=tmp_path/'out.exe',observations=observations,
                         overwrite_with_floor=[observations[0].record['invocation']])
    result=sc.evaluate_reconstruction(image)
    assert result['wholeFileByteIdentical'] is True
    assert [row['contributedBytes'] for row in result['candidates']] == [0,6]
    assert any(w['origin']=='compiled-object' and w['offset']==0x200 for w in image.record['writes'])
    assert next(w for w in image.record['finalWriters'] if w['offset']==0x200)['origin']=='preserved-floor'


def test_partial_overlaps_reject_only_affected_regions(tmp_path):
    target, observations=compiled_pair(tmp_path)
    source=tmp_path/'overlap.c';source.write_text('void Overlap(void) {}')
    overlapping=sc.compile_observation(source=source,target=target,address=0x401005,size=1,workspace=tmp_path/'owned')
    image=sc.reconstruct(target=target,output=tmp_path/'out.exe',observations=[*observations,overlapping])
    result=sc.evaluate_reconstruction(image)
    assert [row['contributedBytes'] for row in result['candidates']] == [0,6,0]
    assert result['wholeFileByteIdentical'] is True


def test_valid_collision_is_deterministic_and_snapshot_change_is_local(tmp_path):
    target, observations=compiled_pair(tmp_path)
    source=tmp_path/'C.c';source.write_text('int C(void) {return 7;}')
    c=sc.compile_observation(source=source,target=target,address=0x401000,size=6,
                            workspace=tmp_path/'owned',program='synthetic',name='C')
    first=sc.reconstruct(target=target,output=tmp_path/'first.exe',observations=[c,*observations])
    second=sc.reconstruct(target=target,output=tmp_path/'second.exe',observations=[*observations,c])
    accepted=lambda image: sorted(r['candidate']['name'] for r in sc.evaluate_reconstruction(image)['candidates'] if r['accepted'])
    assert accepted(first)==accepted(second)==['A','B']
    Path(observations[0].record['snapshot']['path']).write_bytes(b'changed')
    assert accepted(first)==['B']


def test_database_projection_ignores_unrelated_rows_but_withdraws_changed_function(tmp_path):
    raw,base=pe_fixture();target=tmp_path/'target.exe';target.write_bytes(raw)
    db=tmp_path/'corpus.sqlite'
    with sqlite3.connect(db) as con:
        con.execute('CREATE TABLE func(binary_id INTEGER,addr INTEGER,size INTEGER)')
        con.executemany('INSERT INTO func VALUES(1,?,?)',[(base+0x1000,6),(base+0x1010,6)])
    observations=[]
    for label,value,offset in [('A',7,0),('B',9,16)]:
        source=tmp_path/f'{label}.c';source.write_text(f'int {label}(void){{return {value};}}')
        observations.append(sc.compile_observation(source=source,target=target,address=base+0x1000+offset,
            size=6,workspace=tmp_path/'owned',db=db,binary_id=1,name=label))
    image=sc.reconstruct(target=target,output=tmp_path/'out.exe',observations=observations)
    with sqlite3.connect(db) as con: con.execute('INSERT INTO func VALUES(2,123,99)')
    assert sc.evaluate_reconstruction(image)['placedCompiledRegions']==2
    with sqlite3.connect(db) as con: con.execute('UPDATE func SET size=5 WHERE addr=?',(base+0x1000,))
    assert [r['contributedBytes'] for r in sc.evaluate_reconstruction(image)['candidates']]==[0,6]


def test_database_loss_is_explicit_zero_credit_not_an_exception(tmp_path):
    raw,base=pe_fixture();target=tmp_path/'target.exe';target.write_bytes(raw)
    db=tmp_path/'corpus.sqlite'
    with sqlite3.connect(db) as con:
        con.execute('CREATE TABLE func(binary_id INTEGER,addr INTEGER,size INTEGER)')
        con.execute('INSERT INTO func VALUES(1,?,6)',(base+0x1000,))
    source=tmp_path/'A.c';source.write_text('int A(void){return 7;}')
    observation=sc.compile_observation(source=source,target=target,address=base+0x1000,size=6,
        workspace=tmp_path/'owned',db=db,binary_id=1,name='A')
    image=sc.reconstruct(target=target,output=tmp_path/'out.exe',observations=[observation])
    assert sc.evaluate_reconstruction(image,db=db,binary_id=1)['placedCompiledRegions']==1
    with sqlite3.connect(db) as con: con.execute('DROP TABLE func')
    result=sc.evaluate_reconstruction(image,db=db,binary_id=1)
    assert result['placedCompiledRegions']==0
    assert 'no such table' in result['candidates'][0]['reason']
    db.unlink()
    assert sc.evaluate_reconstruction(image,db=db,binary_id=1)['placedCompiledRegions']==0
