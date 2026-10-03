"""Synthetic verification-seam regressions; no real whole-image producer proof.

These sources were added under a source-only mission and have not been run.
The independently held observation below exercises acceptance plumbing only.
"""
from __future__ import annotations

import copy
import hashlib
import json

import pytest

from agentdecompile_recovery.corpus import hookpack_v2
from agentdecompile_recovery.corpus.cave_discovery import discover_caves
from agentdecompile_recovery.corpus.export_bundle import BundleExportError, export_bundle
from agentdecompile_recovery.corpus.export_hookpack import export_hookpack
from agentdecompile_recovery.corpus.export_validation import ExportValidationError, validate_export_set
from agentdecompile_recovery.corpus.hookpack_v2 import (
    CaveEvidenceError, _require_json_native, build_hookpack_v2, canonical_bytes,
    read_hookpack, seal_pack,
)
from agentdecompile_recovery.corpus.store import connect

pytestmark = pytest.mark.unit


def _sha(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


@pytest.fixture
def synthetic_observation(tmp_path, monkeypatch):
    """Hold an immutable synthetic observation separately from submitted JSON."""
    image = b'\x55\x8b\xec\xc3' + b'\x90' * 16 + b'\x56\xc3'
    digest = hashlib.sha256(image).hexdigest()
    declared = {"corpus_manifest_hash": "b" * 64}
    evidence = {
        "image_sha256": digest, "complete": True,
        "decoder": {"identity": "synthetic-fixture", "revision": "1"},
        "executable_sections": [[0, len(image)]], "instructions": [[0, 4], [20, 22]],
        "relocations": [], "data_references": [], "function_ends": [4, 22],
        "anchors": [{"key": "tail", "offset": 0, "expected_bytes": image[:4].hex(),
                     "margin": 2, "required_margin": 1}],
        "qualification": {"producer_reference_sha256": "c" * 64,
                          "policy_revision": "synthetic-container-limit-64/v1", "generation": "fixture-1"},
    }
    con = connect(tmp_path / "synthetic.sqlite")
    con.execute("INSERT INTO binary(id,repo_path,slug,content_sha256,arch,bits,image_base) "
                "VALUES (1,'/synthetic','fixture',?,'i386',32,4096)", (digest,))
    monkeypatch.setattr(hookpack_v2, "basis", lambda _: copy.deepcopy(declared))
    monkeypatch.setattr("agentdecompile_recovery.corpus.export_hookpack._raw_image", lambda _: image)

    def verifier_for(submitted):
        # The test owner captures a separate immutable object before export.
        plans = discover_caves(image, build="fixture", arch="i386", evidence=submitted)
        expected = canonical_bytes({"build": "fixture", "status": "complete", "arch": "i386",
            "image_sha256": digest, "basis_sha256": _sha(declared), "evidence_sha256": _sha(submitted),
            "decoder": submitted["decoder"], "qualification": submitted["qualification"],
            "candidate_count": len(plans), "candidates_sha256": _sha(plans)})
        current = {"active": True}
        def verify(receipt):
            return current["active"] and canonical_bytes(receipt) == expected
        return verify, current

    verify, current = verifier_for(evidence)
    yield con, evidence, verify, current, verifier_for
    con.close()


def test_synthetic_positive_and_serialized_requalification(synthetic_observation, tmp_path):
    con, evidence, verify, current, _ = synthetic_observation
    pack = build_hookpack_v2(con, cave_evidence={"fixture": evidence}, verify_cave_receipt=verify)
    assert pack["cave_discovery"][0]["candidate_count"] == len(pack["caves"]) == 1
    assert pack["caves"][0]["live_allocation_allowed"] is False
    path = tmp_path / "pack.json"
    path.write_bytes(canonical_bytes(pack))
    receipt = validate_export_set(path, require_caves=True, verify_cave_receipt=verify)
    assert "independent_cave_qualification" in receipt["checked"]
    assert receipt["runtime_verification"] == "not_run"
    with pytest.raises(ExportValidationError, match="independent_cave_verifier_unavailable"):
        validate_export_set(path, require_caves=True)
    current["active"] = False
    with pytest.raises(ExportValidationError, match="independent_cave_qualification_refused"):
        validate_export_set(path, require_caves=True, verify_cave_receipt=verify)
    consistency = validate_export_set(path)
    assert consistency["scope"] == "artifact_identity_and_cross_reference_consistency"


@pytest.mark.parametrize("exclusion", ["instructions", "relocations", "data_references", "capacity"])
def test_synthetic_qualified_zero(synthetic_observation, exclusion):
    con, evidence, _, _, verifier_for = synthetic_observation
    if exclusion in ("instructions", "relocations"):
        evidence[exclusion].append([4, 20])
    elif exclusion == "data_references":
        evidence[exclusion].append(8)
    else:
        evidence["executable_sections"] = [[0, 10], [20, 22]]
    verify, _ = verifier_for(evidence)
    pack = build_hookpack_v2(con, cave_evidence={"fixture": evidence}, verify_cave_receipt=verify)
    assert pack["caves"] == []
    receipt = pack["cave_discovery"][0]
    assert receipt["status"] == "complete" and receipt["candidate_count"] == 0
    assert receipt["candidates_sha256"] == _sha([])


@pytest.mark.parametrize("result", [False, None, 1, "true", {}, [True]])
def test_non_true_refuses_without_candidates(synthetic_observation, result, tmp_path):
    con, evidence, _, _, _ = synthetic_observation
    verify = lambda _: result  # Synthetic refusal seam, never a producer.
    pack = build_hookpack_v2(con, cave_evidence={"fixture": evidence}, verify_cave_receipt=verify)
    receipt = pack["cave_discovery"][0]
    assert pack["caves"] == [] and receipt["status"] == "blocked"
    assert receipt["reason"] == "independent_cave_qualification_refused"
    assert "candidate_count" not in receipt
    out = tmp_path / "bundles"
    with pytest.raises(BundleExportError, match="cave_discovery_blocked"):
        export_bundle(con, out, cave_evidence={"fixture": evidence}, verify_cave_receipt=verify)
    assert not out.exists()


def test_missing_evidence_and_callback_stay_blocked(synthetic_observation, tmp_path):
    con, evidence, _, _, _ = synthetic_observation
    missing = build_hookpack_v2(con)
    assert missing["cave_discovery"][0]["reason"] == "complete_decode_evidence_unavailable"
    pack = build_hookpack_v2(con, cave_evidence={"fixture": evidence})
    assert pack["caves"] == []
    assert pack["cave_discovery"][0]["reason"] == "independent_cave_verifier_unavailable"
    assert "candidate_count" not in pack["cave_discovery"][0]
    out = tmp_path / "bundles"
    with pytest.raises(BundleExportError, match="independent_cave_verifier_unavailable"):
        export_bundle(con, out, cave_evidence={"fixture": evidence})
    assert not out.exists()


@pytest.mark.parametrize("field", ["producer_reference_sha256", "policy_revision", "generation", "decoder"])
def test_changed_producer_binding_refuses(synthetic_observation, field):
    con, evidence, verify, _, _ = synthetic_observation
    if field == "decoder":
        evidence["decoder"]["revision"] = "2"
    else:
        evidence["qualification"][field] = "d" * 64 if field.endswith("sha256") else "retired"
    pack = build_hookpack_v2(con, cave_evidence={"fixture": evidence}, verify_cave_receipt=verify)
    assert pack["caves"] == []
    assert pack["cave_discovery"][0]["reason"] == "independent_cave_qualification_refused"


@pytest.mark.parametrize("field", ["producer_reference_sha256", "policy_revision", "generation"])
def test_missing_qualification_refuses_before_callback(synthetic_observation, field):
    con, evidence, _, _, _ = synthetic_observation
    del evidence["qualification"][field]
    def unexpected(_):
        pytest.fail("malformed qualification must not reach verifier")
    pack = build_hookpack_v2(con, cave_evidence={"fixture": evidence}, verify_cave_receipt=unexpected)
    assert pack["caves"] == [] and pack["cave_discovery"][0]["status"] == "blocked"


@pytest.mark.parametrize("change", ["registered_hash", "image", "build", "arch"])
def test_target_refuses_before_callback(synthetic_observation, change):
    con, evidence, _, _, _ = synthetic_observation
    if change == "registered_hash":
        con.execute("UPDATE binary SET content_sha256=?", ("d" * 64,))
    else:
        evidence[{"image": "image_sha256", "build": "build", "arch": "arch"}[change]] = "wrong"
    def unexpected(_):
        pytest.fail("wrong target must not reach verifier")
    with pytest.raises(ValueError):
        build_hookpack_v2(con, cave_evidence={"fixture": evidence}, verify_cave_receipt=unexpected)


@pytest.mark.parametrize("change", ["count", "bool_count", "candidate", "resealed_candidate", "bytes", "anchor", "capacity", "basis", "missing_digest"])
def test_tampered_pack_refuses(synthetic_observation, change):
    con, evidence, verify, _, _ = synthetic_observation
    pack = build_hookpack_v2(con, cave_evidence={"fixture": evidence}, verify_cave_receipt=verify)
    receipt = pack["cave_discovery"][0]
    if change in ("count", "bool_count"):
        receipt["candidate_count"] = 2 if change == "count" else True
    elif change in ("candidate", "resealed_candidate"):
        pack["caves"][0]["offset"] += 1
        if change == "resealed_candidate":
            receipt["candidates_sha256"] = _sha(pack["caves"])
    elif change == "bytes":
        cave = pack["caves"][0]
        cave["original_bytes"] = "00" * cave["capacity"]
        cave["restoration"]["original_bytes"] = cave["original_bytes"]
    elif change == "anchor":
        pack["caves"][0]["anchor"]["value"] = "AA"
    elif change == "capacity":
        cave = pack["caves"][0]
        cave["capacity"] -= 1
        cave["original_bytes"] = cave["original_bytes"][:-2]
        cave["restoration"]["original_bytes"] = cave["original_bytes"]
    elif change == "basis":
        receipt["basis_sha256"] = "d" * 64
    else:
        del receipt["candidates_sha256"]
    pack = seal_pack(pack)
    with pytest.raises(ExportValidationError):
        validate_export_set(pack, require_caves=True, verify_cave_receipt=verify)


def test_callback_mutation_and_failure_are_distinct(synthetic_observation):
    con, evidence, _, _, _ = synthetic_observation
    def mutate(receipt):
        receipt["decoder"]["revision"] = "mutated"
        return True
    with pytest.raises(CaveEvidenceError, match="cave_verifier_input_changed"):
        build_hookpack_v2(con, cave_evidence={"fixture": evidence}, verify_cave_receipt=mutate)
    assert evidence["decoder"]["revision"] == "1"
    failure = RuntimeError("provider bug")
    def fail(_):
        raise failure
    with pytest.raises(CaveEvidenceError, match="cave_verifier_failed") as caught:
        build_hookpack_v2(con, cave_evidence={"fixture": evidence}, verify_cave_receipt=fail)
    assert caught.value.__cause__ is failure
    def unavailable(_):
        raise CaveEvidenceError("independent_cave_verifier_unavailable")
    pack = build_hookpack_v2(con, cave_evidence={"fixture": evidence}, verify_cave_receipt=unavailable)
    assert pack["cave_discovery"][0]["reason"] == "independent_cave_verifier_unavailable"


def test_scanner_uses_captured_snapshot(synthetic_observation):
    con, evidence, verify, _, _ = synthetic_observation
    initial_hash = _sha(evidence)
    def modify_original(receipt):
        evidence["decoder"]["revision"] = "later-caller-state"
        return verify(receipt)
    pack = build_hookpack_v2(con, cave_evidence={"fixture": evidence}, verify_cave_receipt=modify_original)
    assert pack["cave_discovery"][0]["evidence_sha256"] == initial_hash
    assert pack["cave_discovery"][0]["decoder"]["revision"] == "1"


def _nested(depth):
    result = []
    for _ in range(depth - 1):
        result = [result]
    return result


def test_depth_boundary_and_full_pack_wrappers():
    _require_json_native(_nested(64), build="fixture")
    with pytest.raises(CaveEvidenceError) as caught:
        _require_json_native(_nested(65), build="fixture")
    assert caught.value.code == "cave_evidence_nesting_limit_exceeded"
    assert caught.value.build == "fixture" and caught.value.details == {"limit": 64, "depth": 65}
    pack = {"format": hookpack_v2.FORMAT, "fragment": _nested(64)}
    for consume in (seal_pack, read_hookpack, validate_export_set):
        with pytest.raises(ValueError, match="cave_evidence_nesting_limit_exceeded"):
            consume(pack)


@pytest.mark.parametrize("invalid", [(1,), {1: "key"}, float("nan"), float("inf")])
def test_exact_json_native_rejections(invalid):
    with pytest.raises((ValueError, TypeError)):
        _require_json_native({"value": invalid})


def test_cycles_subclasses_shared_and_flat_arrays():
    cycle = []
    cycle.append(cycle)
    with pytest.raises(ValueError, match="cyclic_json_evidence"):
        _require_json_native(cycle)
    class JsonList(list):
        pass
    with pytest.raises(TypeError, match="non_json_native_value"):
        _require_json_native(JsonList())
    shared = [1, "two"]
    _require_json_native([shared, shared, [0] * 100_001])
    # Tuple fingerprints in generated canonical hashes remain compatible.
    assert canonical_bytes({"members": [("fixture", 1)]})


def test_parser_recursion_stable_code(tmp_path, monkeypatch):
    path = tmp_path / "pack.json"
    path.write_text('{"format":"agentdecompile.hookpack/v2"}')
    def recurse(_):
        raise RecursionError("parser depth")
    monkeypatch.setattr(hookpack_v2.json, "loads", recurse)
    with pytest.raises(CaveEvidenceError) as caught:
        read_hookpack(path)
    assert caught.value.details == {"limit": 64, "depth": None}
    with pytest.raises(ExportValidationError, match="cave_evidence_nesting_limit_exceeded"):
        validate_export_set(path)


def test_v1_never_calls_verifier(synthetic_observation, tmp_path, monkeypatch):
    con, _, _, _, _ = synthetic_observation
    monkeypatch.setattr("agentdecompile_recovery.corpus.export_hookpack.basis", hookpack_v2.basis)
    def unexpected(_):
        pytest.fail("v1 must not invoke cave authority")
    out = tmp_path / "v1.json"
    export_hookpack(con, out, format="v1", verify_cave_receipt=unexpected)
    assert json.loads(out.read_text())["format"] == "agentdecompile.hookpack/v1"
    v1 = {"format": "agentdecompile.hookpack/v1", "legacy": (1, 2)}
    assert read_hookpack(v1) == v1


@pytest.mark.parametrize("refuse_at", [3, 4])
def test_later_bundle_recheck_refuses_and_preserves_outputs(synthetic_observation, tmp_path, monkeypatch, refuse_at):
    """Synthetic exporters exercise the publication boundary, not delivery proof."""
    con, evidence, verify, _, _ = synthetic_observation
    con.execute("CREATE TABLE ghidra_type(binary_id INTEGER,name TEXT,kind TEXT,size INTEGER,definition TEXT)")
    con.execute("INSERT INTO ghidra_type VALUES (1,'SyntheticType','struct',4,'struct SyntheticType { int field; };')")
    monkeypatch.setattr("agentdecompile_recovery.corpus.export_hookpack.basis", hookpack_v2.basis)
    monkeypatch.setattr("agentdecompile_recovery.corpus.divergence_report.build_divergence_report",
                        lambda _: {"status": "complete", "pairs": []})
    monkeypatch.setattr("agentdecompile_recovery.corpus.export_lua_bindings.render_lua_bindings",
                        lambda _: "-- synthetic publication fixture\n")
    def synthetic_header(_, __, path, **kwargs):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("/* synthetic header */")
        manifest = path.with_suffix(".manifest.json")
        manifest.write_text("{}")
        return {"manifest": str(manifest)}
    monkeypatch.setattr("agentdecompile_recovery.corpus.build_types_header.build_header", synthetic_header)
    calls = []
    def retires(receipt):
        calls.append(receipt["build"])
        return verify(receipt) if len(calls) < refuse_at else False
    out = tmp_path / "bundles"
    out.mkdir()
    previous = out / "existing-artifact"
    previous.write_bytes(b"preserved")
    with pytest.raises(ExportValidationError, match="independent_cave_qualification_refused"):
        export_bundle(con, out, cave_evidence={"fixture": evidence}, verify_cave_receipt=retires)
    assert len(calls) == refuse_at
    assert list(out.iterdir()) == [previous] and previous.read_bytes() == b"preserved"
    assert con.execute("SELECT COUNT(*) FROM binary").fetchone()[0] == 1


def test_v2_exporter_forwards_verifier(synthetic_observation, tmp_path):
    con, evidence, verify, _, _ = synthetic_observation
    path = tmp_path / "pack.json"
    export_hookpack(con, path, format="v2", cave_evidence={"fixture": evidence}, verify_cave_receipt=verify)
    pack = json.loads(path.read_text())
    assert pack["cave_discovery"][0]["status"] == "complete"
    validate_export_set(pack, require_caves=True, verify_cave_receipt=verify)
