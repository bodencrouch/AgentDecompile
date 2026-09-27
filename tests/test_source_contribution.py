"""Structural COFF controls plus native compiler canaries on synthetic PE targets.

These are not a live recovery/catalog or original game compiler demonstration.
"""
import json
from pathlib import Path
import struct

import pytest

from agentdecompile_recovery.corpus import source_contribution as sc
from agentdecompile_recovery.corpus.compile_link import compile_source_contribution


def pe_fixture(*, plus=False):
    raw = bytearray(0x240)
    raw[:2] = b'MZ'
    struct.pack_into('<I', raw, 0x3c, 0x80)
    raw[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<HH', raw, 0x84, 0x8664 if plus else 0x14c, 1)
    optional_size = 0xf0 if plus else 0xe0
    struct.pack_into('<H', raw, 0x94, optional_size)
    struct.pack_into('<H', raw, 0x98, 0x20b if plus else 0x10b)
    base = 0x140000000 if plus else 0x400000
    struct.pack_into('<Q' if plus else '<I', raw, 0x98 + (24 if plus else 28), base)
    section = 0x98 + optional_size
    raw[section:section + 8] = b'.text\0\0\0'
    struct.pack_into('<IIII', raw, section + 8, 0x40, 0x1000, 0x40, 0x200)
    struct.pack_into('<I', raw, section + 36, 0x60000020)
    raw[0x200:0x206] = b'\xb8\x07\0\0\0\xc3'
    raw[0x210:0x216] = b'\xb8\x09\0\0\0\xc3'
    return bytes(raw), base


def compiler_available():
    path = Path('/usr/bin/clang')
    return path.exists() and path.resolve().read_bytes()[:4] == b'\x7fELF'


def compiled_pair(tmp_path, *, plus=False, db=None, binary_id=None):
    if not compiler_available():
        pytest.skip('native clang unavailable; real compiler canary remains open')
    raw, base = pe_fixture(plus=plus)
    target = tmp_path / 'target.exe'; target.write_bytes(raw)
    observations = []
    for label, value, offset in [('A', 7, 0), ('B', 9, 16)]:
        source = tmp_path / f'{label}.c'; source.write_text(f'int {label}(void) {{ return {value}; }}\n')
        observations.append(compile_source_contribution(source=source, target=target,
            address=base + 0x1000 + offset, size=6, workspace=tmp_path / 'owned',
            compiler='/usr/bin/clang', program='synthetic', name=label, db=db, binary_id=binary_id))
    return target, observations


def minimal_coff():
    """Deterministic real-format COFF; structural parser evidence only."""
    # Section symbol + aux + one external function; empty string table.
    raw = bytearray(60 + 1 + 3 * 18 + 4)
    struct.pack_into('<HHIIIHH', raw, 0, 0x14c, 1, 0, 61, 3, 0, 0)
    raw[20:28] = b'.text\0\0\0'
    struct.pack_into('<IIIIIIHHI', raw, 28, 0, 0, 1, 60, 0, 0, 0, 0, 0x60500020)
    raw[60] = 0xc3
    raw[61:69] = b'.text\0\0\0'
    struct.pack_into('<IhHBB', raw, 69, 0, 1, 0, 3, 1)
    struct.pack_into('<I', raw, 79, 1)
    raw[97:105] = b'_A\0\0\0\0\0\0'
    struct.pack_into('<IhHBB', raw, 105, 0, 1, 0x20, 2, 0)
    struct.pack_into('<I', raw, 115, 4)
    return bytes(raw)


def test_structural_coff_span():
    parsed = sc.parse_coff(minimal_coff())
    assert parsed['bytes'] == b'\xc3'
    assert parsed['symbol']['name'] == '_A'
    assert parsed['relocations'] == []


@pytest.mark.parametrize('mutation', ['truncated', 'relocation', 'comdat', 'ltcg', 'alias', 'bounds', 'aux', 'tail'])
def test_structural_coff_refusals(mutation):
    raw = bytearray(minimal_coff())
    if mutation == 'truncated': raw = raw[:-1]
    elif mutation == 'relocation': struct.pack_into('<H', raw, 52, 1)
    elif mutation == 'comdat': struct.pack_into('<I', raw, 56, 0x60501020)
    elif mutation == 'ltcg': raw[:4] = b'\0\0\xff\xff'
    elif mutation == 'alias': struct.pack_into('<H', raw, 111, 0)
    elif mutation == 'bounds': struct.pack_into('<I', raw, 40, 300)
    elif mutation == 'aux': raw[78] = 255
    elif mutation == 'tail': raw.extend(b'unknown')
    with pytest.raises(ValueError): sc.parse_coff(bytes(raw))


@pytest.mark.parametrize('plus', [False, True])
def test_real_compiler_two_regions_and_independent_reopen(tmp_path, plus):
    target, observations = compiled_pair(tmp_path, plus=plus)
    image = sc.reconstruct(target=target, output=tmp_path / 'output.exe', observations=observations)
    result = sc.evaluate_reconstruction(image, target_path=target)
    assert result['placedCompiledRegions'] == 2
    assert result['placedCompiledBytes'] == 12
    assert result['wholeFileByteIdentical'] is True
    assert result['compilerProducedWholeImage'] is False
    assert all(sc.parse_coff(Path(o.record['object']['path']).read_bytes())['size'] == 6 for o in observations)
    assert all(o.record['argv'][1] == '-cc1' for o in observations)
    assert all(o.record['toolchain'] for o in observations)
    assert all(o.record['region']['offset'] != o.record['region']['address'] - (0x140000000 if plus else 0x400000) for o in observations)
    # Exported JSON and manually constructed capabilities cannot mint credit.
    assert sc.evaluate_reconstruction(image.record)['placedCompiledRegions'] == 0
    forged = sc.ReconstructionObservation(image.record_json, image.candidates)
    assert sc.evaluate_reconstruction(forged)['placedCompiledRegions'] == 0
    forged_compile = sc.CompileObservation(observations[0].record_json)
    assert sc.validate_compile(forged_compile)[2] == 'untrusted_imported_compile_observation'


def test_wrapper_static_object_and_preprocessor_refused(tmp_path):
    target = tmp_path / 'target.exe'; target.write_bytes(pe_fixture()[0])
    source = tmp_path / 'A.c'; source.write_text('int A(void) { return 7; }')
    wrapper = tmp_path / 'clang'; wrapper.write_text('#!/bin/sh\ncp static.obj unit.obj\n'); wrapper.chmod(0o755)
    with pytest.raises(ValueError, match='wrapper'):
        sc.compile_observation(source=source, target=target, address=0x401000, size=6,
                               workspace=tmp_path, compiler=wrapper)
    source.write_text('#include "local.h"\nint A(void) { return 7; }')
    with pytest.raises(ValueError, match='preprocessor'):
        sc.compile_observation(source=source, target=target, address=0x401000, size=6, workspace=tmp_path)


@pytest.mark.parametrize('source', [
    'extern int Other(void); int A(void){return Other();}',
    'int A(void){return 7;} int B(void){return 9;}',
    'static volatile int data=7; int A(void){return data;}',
])
def test_actual_compiler_unsupported_relocations_bodies_data(tmp_path,source):
    if not compiler_available(): pytest.skip('native clang unavailable')
    target=tmp_path/'target.exe';target.write_bytes(pe_fixture()[0])
    path=tmp_path/'A.c';path.write_text(source)
    with pytest.raises(ValueError,match='unsupported|ambiguous'):
        sc.compile_observation(source=path,target=target,address=0x401000,size=6,workspace=tmp_path/'owned')
    assert list((tmp_path/'owned').rglob('unit.obj'))
    assert not list((tmp_path/'owned').rglob('compile-observation.json'))


def test_strict_pe_region_refuses_partial_and_raw_alias_mapping():
    raw,_=pe_fixture()
    with pytest.raises(ValueError,match='unmapped'):
        sc.pe_region(raw,0x40103f,2)
    bad=bytearray(raw)
    struct.pack_into('<H',bad,0x86,2)
    bad[0x1a0:0x1a0+40]=bad[0x178:0x178+40]
    # The alias starts at a different RVA but shares the requested raw bytes.
    struct.pack_into('<I',bad,0x1a0+12,0x2000)
    with pytest.raises(ValueError,match='raw_sections_overlap'):
        sc.pe_region(bytes(bad),0x401000,6)


def test_native_elf_named_clang_cannot_copy_static_object_into_acceptance(tmp_path):
    import subprocess
    compiler = Path('/usr/bin/cc')
    if not compiler.exists(): pytest.skip('native C compiler unavailable for adversarial ELF fixture')
    # This adversarial fixture is compiled as test input only, never an accepted
    # source-contribution producer. It would write valid cached COFF if invoked.
    code = ','.join(str(b) for b in minimal_coff())
    source = tmp_path/'copier.c'
    source.write_text('#include <stdio.h>\n#include <string.h>\n'
        'int main(int n,char **v){unsigned char b[]={' + code + '};'
        'for(int i=1;i+1<n;i++)if(!strcmp(v[i],"-o")){FILE*f=fopen(v[i+1],"wb");'
        'if(!f)return 2;fwrite(b,1,sizeof b,f);fclose(f);return 0;}return 1;}')
    fake=tmp_path/'clang'
    proc=subprocess.run([str(compiler),str(source),'-o',str(fake)],capture_output=True)
    assert proc.returncode==0,proc.stderr
    assert fake.read_bytes()[:4]==b'\x7fELF'
    with pytest.raises(ValueError,match='unapproved_compiler_identity'):
        sc._toolchain(fake)


def test_changed_toolchain_closure_refuses_before_source_invocation(tmp_path, monkeypatch):
    if not compiler_available(): pytest.skip('native clang unavailable')
    original=sc.fingerprint
    def changed_dependency(path):
        record=original(path)
        if 'libLLVM' in str(path): record['sha256']='0'*64
        return record
    monkeypatch.setattr(sc,'fingerprint',changed_dependency)
    with pytest.raises(ValueError,match='unapproved_toolchain_dependency_closure'):
        sc._toolchain(Path('/usr/bin/clang'))
