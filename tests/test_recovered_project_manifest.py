"""Relocatable recovered-project manifest (P2-f) on synthetic projects.

Every project tree, image and COFF object is built in-test under pytest's
tmp_path. No product binary, compiler, linker, objdump or server runs.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import struct

import pytest

from agentdecompile_recovery.corpus import coff_fixup_roundtrip as rt
from agentdecompile_recovery.corpus import mkobj
from agentdecompile_recovery.corpus import recovered_project_manifest as rpm

pytestmark = pytest.mark.unit

IMAGE_BASE = 0x00400000
SIZE_OF_IMAGE = 0x3000
TEXT = IMAGE_BASE + 0x1000
IMAGE_SHA = hashlib.sha256(bytes(range(256)) * 16).hexdigest()
TOOLCHAIN_ID = hashlib.sha256(b"synthetic toolchain identity").hexdigest()
BASIS = hashlib.sha256(b"synthetic basis").hexdigest()
I386 = mkobj.MACHINE["coff-i386"]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


IMAGE_BYTES = bytes(range(256)) * 16


def write_source(root, rel: str, text: str) -> str:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode())
    return sha(text.encode())


def project(root, *, rebuildable=True, toolchain=None, basis=BASIS, extra_units=()):
    """Two units, one pinned toolchain, placements back to back in .text."""
    toolchain = toolchain if toolchain is not None else rpm.pinned_toolchain(TOOLCHAIN_ID, compiler="synthetic-cc 1.0")
    a = write_source(root, "src/a.c", "int a(void) { return 1; }\n")
    b = write_source(root, "src/b.c", "int b(void) { return 2; }\n")
    units = [
        rpm.unit("b", source_path="src/b.c", source_sha256=b, image_sha256=IMAGE_SHA, provenance="reused", toolchain=toolchain,
                 placements=[rpm.placement("_b", TEXT + 0x20, 0x10)]),
        rpm.unit("a", source_path="src/a.c", source_sha256=a, image_sha256=IMAGE_SHA, provenance="recovered", toolchain=toolchain,
                 placements=[rpm.placement("_a", TEXT, 0x20)]),
        *extra_units,
    ]
    return rpm.build_manifest(
        project="synthetic",
        image=rpm.image_identity(IMAGE_BYTES, image_base=IMAGE_BASE, size_of_image=SIZE_OF_IMAGE),
        units=units, rebuildable=rebuildable, basis_hash=basis)


def reasons(receipt) -> list[str]:
    return [r["reason"] for r in receipt["refusals"]]


# ------------------------------------------------------------------ accepted shape


def test_valid_project_accepted_with_deterministic_receipt(tmp_path):
    manifest = project(tmp_path)
    first = rpm.validate(manifest, tmp_path, IMAGE_BYTES)
    second = rpm.validate(json.loads(rpm.dumps(manifest)), tmp_path, IMAGE_BYTES)
    assert first["verdict"] == "accepted", first["refusals"]
    assert first["schema"] == rpm.RECEIPT_SCHEMA
    assert manifest["schema"] == rpm.SCHEMA == "agentdecompile.recovered-project/v1"
    assert rpm.receipt_bytes(first) == rpm.receipt_bytes(second)
    assert first["counts"]["units"] == 2
    assert first["counts"]["placed_bytes"] == 0x30
    assert first["counts"]["provenance"] == {"placeholder": 0, "recovered": 1, "reused": 1}
    assert str(tmp_path) not in rpm.receipt_bytes(first).decode()
    # canonical order: units by id, independent of input order
    assert [u["id"] for u in manifest["units"]] == ["a", "b"]


def test_receipt_identical_after_moving_project_tree(tmp_path):
    here = tmp_path / "here"
    here.mkdir()
    manifest = project(here)
    rpm.write(manifest, here)
    there = tmp_path / "elsewhere" / "deeper"
    shutil.copytree(here, there)
    moved = rpm.load(there)
    assert rpm.receipt_bytes(rpm.validate(moved, there, IMAGE_BYTES)) == \
        rpm.receipt_bytes(rpm.validate(manifest, here, IMAGE_BYTES))
    assert (there / rpm.MANIFEST_NAME).read_bytes() == rpm.dumps(manifest)


# ------------------------------------------------------------------ refusals


def test_overlapping_placements_across_units_refused(tmp_path):
    manifest = project(tmp_path)
    manifest["units"][1]["placements"][0]["va"] = TEXT + 0x1F  # b now overlaps a by one byte
    receipt = rpm.validate(manifest, tmp_path, IMAGE_BYTES)
    assert receipt["verdict"] == "refused"
    assert reasons(receipt) == ["overlapping_placements"]


@pytest.mark.parametrize("va,size", [
    (IMAGE_BASE - 0x10, 0x10),                       # below the image
    (IMAGE_BASE + SIZE_OF_IMAGE - 0x8, 0x10),        # straddles the end
    (IMAGE_BASE + SIZE_OF_IMAGE, 0x4),               # starts at the end
])
def test_placement_outside_image_refused(tmp_path, va, size):
    manifest = project(tmp_path)
    manifest["units"][0]["placements"][0].update(va=va, size=size)
    assert reasons(rpm.validate(manifest, tmp_path, IMAGE_BYTES)) == ["placement_outside_image"]


def test_stale_image_digest_refused(tmp_path):
    manifest = project(tmp_path)
    receipt = rpm.validate(manifest, tmp_path, IMAGE_BYTES[:-1] + b"\x00")
    assert reasons(receipt) == ["stale_image_digest"]
    assert receipt["image_sha256_observed"] == sha(IMAGE_BYTES[:-1] + b"\x00")


def test_missing_source_refused(tmp_path):
    manifest = project(tmp_path)
    (tmp_path / "src" / "a.c").unlink()
    receipt = rpm.validate(manifest, tmp_path, IMAGE_BYTES)
    assert reasons(receipt) == ["missing_source"]
    assert receipt["refusals"][0]["unit"] == "a"


def test_stale_source_digest_refused(tmp_path):
    manifest = project(tmp_path)
    (tmp_path / "src" / "b.c").write_text("int b(void) { return 3; }\n")
    assert reasons(rpm.validate(manifest, tmp_path, IMAGE_BYTES)) == ["stale_source_digest"]


def test_unpinned_toolchain_refused_only_in_rebuildable_project(tmp_path):
    unpinned = rpm.unpinned_toolchain("no per-build toolchain record (U54)")
    claimed = project(tmp_path, toolchain=unpinned)
    assert reasons(rpm.validate(claimed, tmp_path, IMAGE_BYTES)) == \
        ["unpinned_toolchain_in_rebuildable_project"] * 2
    layout_only = project(tmp_path, toolchain=unpinned, rebuildable=False)
    receipt = rpm.validate(layout_only, tmp_path, IMAGE_BYTES)
    assert receipt["verdict"] == "accepted"
    assert receipt["counts"]["toolchain"] == {"pinned": 0, "unpinned": 2}


@pytest.mark.parametrize("identity", ["pinned:none", "unknown", "", "ab" * 31, "zz" * 32])
def test_fabricated_toolchain_identity_refused(tmp_path, identity):
    with pytest.raises(rpm.ManifestError) as exc:
        rpm.pinned_toolchain(identity, compiler="synthetic-cc")
    assert exc.value.reason == "toolchain_identity_invalid"
    manifest = project(tmp_path)
    manifest["units"][0]["toolchain"]["identity_sha256"] = identity  # hand-edited manifest
    assert reasons(rpm.validate(manifest, tmp_path, IMAGE_BYTES)) == ["toolchain_identity_invalid"]


def test_toolchain_state_is_never_defaulted(tmp_path):
    manifest = project(tmp_path)
    del manifest["units"][0]["toolchain"]
    manifest["units"][1]["toolchain"] = {"state": "probably"}
    assert reasons(rpm.validate(manifest, tmp_path, IMAGE_BYTES)) == ["toolchain_state_missing"] * 2
    with pytest.raises(TypeError):
        rpm.unit("x", source_path="src/a.c", source_sha256="0" * 64, image_sha256=IMAGE_SHA, provenance="recovered",
                 placements=[])  # toolchain is a required keyword


def test_unit_bound_to_another_image_refused(tmp_path):
    manifest = project(tmp_path)
    manifest["units"][1]["image_sha256"] = sha(b"a different image, e.g. a sibling DLL")
    receipt = rpm.validate(manifest, tmp_path, IMAGE_BYTES)
    assert reasons(receipt) == ["unit_image_mismatch"]
    assert receipt["refusals"][0]["unit"] == "b"
    assert all(u["image_sha256"] == manifest["image"]["sha256"] for u in project(tmp_path)["units"])


def test_duplicate_units_refused(tmp_path):
    manifest = project(tmp_path)
    manifest["units"].append(json.loads(json.dumps(manifest["units"][0])))
    manifest["units"][-1]["placements"] = []
    receipt = rpm.validate(manifest, tmp_path, IMAGE_BYTES)
    assert set(reasons(receipt)) == {"duplicate_unit", "duplicate_unit_source"}
    with pytest.raises(rpm.ManifestError) as exc:
        project(tmp_path, extra_units=[manifest["units"][0]])
    assert exc.value.reason == "duplicate_unit"


@pytest.mark.parametrize("path", ["/home/user/src/a.c", "../outside.c", "src/../../x.c", "C:\\src\\a.c", "src\\a.c", ""])
def test_non_relocatable_source_path_refused(tmp_path, path):
    manifest = project(tmp_path)
    manifest["units"][0]["source"]["path"] = path
    assert "non_relocatable_path" in reasons(rpm.validate(manifest, tmp_path, IMAGE_BYTES))


def test_absolute_path_leak_anywhere_refused(tmp_path):
    manifest = project(tmp_path)
    manifest["project"] = "/run/media/someone/Workspaces/game"
    manifest["units"][0]["toolchain"]["compiler"] = "C:\\VS\\bin\\cl.exe"
    receipt = rpm.validate(manifest, tmp_path, IMAGE_BYTES)
    assert reasons(receipt) == ["absolute_path_leak", "absolute_path_leak"]
    assert "/run/media" not in rpm.receipt_bytes(receipt).decode()


def test_msvc_style_flags_are_not_absolute_path_leaks(tmp_path):
    # RN-B-12: "/O2", "/Gy" etc. are MSVC compiler switches, not host paths.
    manifest = project(tmp_path)
    manifest["units"][0]["toolchain"]["flags"] = ["/O2", "/Gy"]
    receipt = rpm.validate(manifest, tmp_path, IMAGE_BYTES)
    assert receipt["verdict"] == "accepted", receipt["refusals"]
    # a real absolute path elsewhere in the manifest is still refused
    manifest["units"][0]["toolchain"]["compiler"] = "/home/x/y.c"
    receipt = rpm.validate(manifest, tmp_path, IMAGE_BYTES)
    assert reasons(receipt) == ["absolute_path_leak"]


def test_invalid_provenance_refused(tmp_path):
    manifest = project(tmp_path)
    manifest["units"][0]["provenance"] = "guessed"
    assert reasons(rpm.validate(manifest, tmp_path, IMAGE_BYTES)) == ["invalid_provenance"]
    with pytest.raises(rpm.ManifestError):
        rpm.unit("x", source_path="src/a.c", source_sha256="0" * 64, image_sha256=IMAGE_SHA, provenance="guessed",
                 toolchain=rpm.unpinned_toolchain("n/a"), placements=[])


def test_basis_required_for_rebuildable_claim(tmp_path):
    assert reasons(rpm.validate(project(tmp_path, basis=None), tmp_path, IMAGE_BYTES)) == \
        ["basis_unrecorded_in_rebuildable_project"]
    assert rpm.validate(project(tmp_path, basis=None, rebuildable=False), tmp_path,
                        IMAGE_BYTES)["verdict"] == "accepted"


@pytest.mark.parametrize("units_value", [[], None, "units", {"a": 1}, 5])
def test_empty_or_non_list_units_refused(tmp_path, units_value):
    # RN-B-13: an empty/missing units list, or a non-list units value,
    # must not be silently treated as an empty project.
    manifest = project(tmp_path)
    if units_value is None:
        del manifest["units"]
    else:
        manifest["units"] = units_value
    receipt = rpm.validate(manifest, tmp_path, IMAGE_BYTES)
    assert receipt["verdict"] == "refused"
    expected = "no_units" if units_value == [] or units_value is None else "invalid_units"
    assert expected in reasons(receipt)


def test_schema_mismatch_refused_without_further_checks(tmp_path):
    manifest = project(tmp_path)
    manifest["schema"] = "agentdecompile.recovered-project/v0"
    receipt = rpm.validate(manifest, tmp_path, b"other image")
    assert reasons(receipt) == ["schema_mismatch"]


def test_every_fault_reported_in_deterministic_order(tmp_path):
    manifest = project(tmp_path)
    manifest["units"][0]["provenance"] = "guessed"
    manifest["units"][1]["placements"][0]["va"] = TEXT
    (tmp_path / "src" / "b.c").unlink()
    receipt = rpm.validate(manifest, tmp_path, b"stale")
    assert reasons(receipt) == sorted(reasons(receipt))
    assert set(reasons(receipt)) == {"invalid_provenance", "missing_source", "overlapping_placements",
                                     "stale_image_digest"}


# ------------------------------------------------------------------ relocation expectations


def mkobj_receipt(va: int):
    """A synthetic region with one external call, carved by mkobj and round-tripped at ``va``."""
    code = bytearray(b"\x55\x89\xe5\xe8\0\0\0\0\x5d\xc3" + b"\x90" * 6)
    target = -0x300  # region-relative call target, outside the region
    struct.pack_into("<i", code, 4, target - 8)
    zeroed = bytearray(code)
    zeroed[4:8] = b"\0\0\0\0"
    obj = mkobj.build_object(bytes(zeroed), "_F", I386, {4: target})
    symbols = rt.mkobj_external_symbols(obj, va)
    return rt.roundtrip_region(bytes(code), obj, va, symbols, image_base=IMAGE_BASE), len(code)


def test_relocations_come_from_roundtrip_receipt(tmp_path):
    receipt, size = mkobj_receipt(TEXT + 0x100)
    assert receipt["byte_equal_at_origin"] is True
    place = rpm.placement("_F", TEXT + 0x100, size, relocation_receipt=receipt)
    assert place["relocations"] == receipt["relocations"]
    assert place["relocation_receipt_sha256"] == sha(json.dumps(receipt, sort_keys=True).encode())
    src = write_source(tmp_path, "src/f.S", "/* floor */\n")
    extra = rpm.unit("f", source_path="src/f.S", source_sha256=src, image_sha256=IMAGE_SHA, provenance="placeholder",
                     toolchain=rpm.pinned_toolchain(TOOLCHAIN_ID, compiler="synthetic-as"),
                     placements=[place])
    out = rpm.validate(project(tmp_path, extra_units=[extra]), tmp_path, IMAGE_BYTES)
    assert out["verdict"] == "accepted", out["refusals"]
    assert out["counts"]["relocations"] == 1


def test_roundtrip_receipt_must_match_placement(tmp_path):
    receipt, size = mkobj_receipt(TEXT + 0x100)
    for kwargs in ({"va": TEXT + 0x104, "size": size}, {"va": TEXT + 0x100, "size": size + 1}):
        with pytest.raises(rpm.ManifestError) as exc:
            rpm.placement("_F", kwargs["va"], kwargs["size"], relocation_receipt=receipt)
        assert exc.value.reason == "relocation_receipt_mismatch"
    refused = dict(receipt, refusal="unresolved_symbol", relocations=None)
    with pytest.raises(rpm.ManifestError) as exc:
        rpm.placement("_F", TEXT + 0x100, size, relocation_receipt=refused)
    assert exc.value.reason == "relocation_receipt_refused"
    with pytest.raises(rpm.ManifestError) as exc:
        rpm.placement("_F", TEXT + 0x100, size, relocation_receipt=dict(receipt, schema="other"))
    assert exc.value.reason == "relocation_receipt_schema"


def test_failed_roundtrip_receipt_refused_in_placement(tmp_path):
    # RN-B-14: a receipt whose byte_equal_at_origin is not True is a
    # mismatch, not a set of relocation expectations to trust.
    receipt, size = mkobj_receipt(TEXT + 0x100)
    bad = dict(receipt, byte_equal_at_origin=False)
    with pytest.raises(rpm.ManifestError) as exc:
        rpm.placement("_F", TEXT + 0x100, size, relocation_receipt=bad)
    assert exc.value.reason == "relocation_receipt_not_byte_equal"


def test_bad_relocation_expectations_refused(tmp_path):
    manifest = project(tmp_path)
    relocs = manifest["units"][0]["placements"][0]["relocations"]
    relocs[:] = [
        {"offset": 0x1E, "type": "IMAGE_REL_I386_REL32", "symbol": "EXT_x", "target": 0},   # 0x1E+4 > 0x20
        {"offset": 0x00, "type": "IMAGE_REL_I386_REL32", "symbol": "EXT_y", "target": 0},
        {"offset": 0x02, "type": "IMAGE_REL_I386_DIR32", "symbol": "EXT_z", "target": 0},   # overlaps 0x00..0x04
        {"offset": 0x08, "type": "IMAGE_REL_MADE_UP", "symbol": "EXT_w", "target": 0},
        {"offset": 0x0C, "type": "IMAGE_REL_I386_DIR32"},                                   # wrong record shape
    ]
    assert reasons(rpm.validate(manifest, tmp_path, IMAGE_BYTES)) == [
        "invalid_relocation", "overlapping_relocations", "relocation_outside_placement",
        "unknown_relocation_type"]


# ------------------------------------------------------------------ U148 shard merge


# ------------------------------------------------------------------ RN-B-15/16: type guards and overlap coverage


@pytest.mark.parametrize("bad_unit", ["not-a-dict", 5, ["nested"]])
def test_malformed_unit_refused_not_crashed(tmp_path, bad_unit):
    manifest = project(tmp_path)
    manifest["units"] = [bad_unit]
    receipt = rpm.validate(manifest, tmp_path, IMAGE_BYTES)
    assert receipt["verdict"] == "refused"
    assert "invalid_unit" in reasons(receipt)


def test_malformed_source_refused_not_crashed(tmp_path):
    manifest = project(tmp_path)
    manifest["units"][0]["source"] = ["not-a-dict"]
    receipt = rpm.validate(manifest, tmp_path, IMAGE_BYTES)
    assert receipt["verdict"] == "refused"
    assert "invalid_unit_source" in reasons(receipt)


def test_malformed_placement_refused_not_crashed(tmp_path):
    manifest = project(tmp_path)
    manifest["units"][0]["placements"] = ["not-a-dict"]
    receipt = rpm.validate(manifest, tmp_path, IMAGE_BYTES)
    assert receipt["verdict"] == "refused"
    assert "invalid_placement" in reasons(receipt)


def test_malformed_relocation_refused_not_crashed(tmp_path):
    manifest = project(tmp_path)
    manifest["units"][0]["placements"][0]["relocations"] = "not-a-list"
    receipt = rpm.validate(manifest, tmp_path, IMAGE_BYTES)
    assert receipt["verdict"] == "refused"
    assert "invalid_relocation" in reasons(receipt)


def test_every_overlapping_placement_is_reported_not_just_adjacent(tmp_path):
    # RN-B-15: A=(0,100), B=(10,5), C=(20,5) must report both B and C as
    # overlapping A, not just B against its immediate neighbor.
    manifest = project(tmp_path)
    manifest["units"][0]["placements"][0].update(va=TEXT, size=100)
    manifest["units"][1]["placements"][0].update(va=TEXT + 10, size=5)
    extra_src = write_source(tmp_path, "src/c.c", "int c(void) { return 3; }\n")
    extra = rpm.unit("c", source_path="src/c.c", source_sha256=extra_src, image_sha256=IMAGE_SHA,
                     provenance="recovered",
                     toolchain=rpm.pinned_toolchain(TOOLCHAIN_ID, compiler="synthetic-cc 1.0"),
                     placements=[rpm.placement("_c", TEXT + 20, 5)])
    manifest["units"].append(extra)
    receipt = rpm.validate(manifest, tmp_path, IMAGE_BYTES)
    overlap_refusals = [r for r in receipt["refusals"] if r["reason"] == "overlapping_placements"]
    assert len(overlap_refusals) == 2
    assert {r["unit"] for r in overlap_refusals} == {"b", "c"}


def test_non_bool_rebuildable_claim_refused(tmp_path):
    # RN-B-16: a truthy-but-not-bool rebuildable claim must not silently
    # skip the basis/toolchain checks it is supposed to trigger.
    manifest = project(tmp_path, basis=None)
    manifest["claims"]["rebuildable"] = "yes"
    receipt = rpm.validate(manifest, tmp_path, IMAGE_BYTES)
    assert receipt["verdict"] == "refused"
    assert "invalid_rebuildable_claim" in reasons(receipt)
    assert "basis_unrecorded_in_rebuildable_project" not in reasons(receipt)


def test_merge_of_shards_is_byte_identical_to_single_manifest(tmp_path):
    whole = project(tmp_path)
    shard_a = dict(whole, units=[whole["units"][0]])
    shard_b = dict(whole, units=[whole["units"][1]])
    assert rpm.dumps(rpm.merge_manifests([shard_b, shard_a])) == rpm.dumps(whole)
    assert rpm.dumps(rpm.merge_manifests([shard_a, shard_b])) == rpm.dumps(whole)


def test_merge_refuses_mismatched_headers_and_duplicate_units(tmp_path):
    whole = project(tmp_path)
    shard_a = dict(whole, units=[whole["units"][0]])
    with pytest.raises(rpm.ManifestError) as exc:
        rpm.merge_manifests([shard_a, dict(whole, units=[whole["units"][1]], basis_hash="f" * 64)])
    assert exc.value.reason == "shard_header_mismatch"
    with pytest.raises(rpm.ManifestError) as exc:
        rpm.merge_manifests([shard_a, shard_a])
    assert exc.value.reason == "duplicate_unit"
