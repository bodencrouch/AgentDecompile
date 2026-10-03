"""G4 lifecycle-owner record and fail-closed reconciliation (synthetic only).

These cases never read the host process table, launch a game, or start Wine.
Process observations are injected; ``observe_process`` is exercised against a
fake ``/proc`` tree under ``tmp_path``.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from agentdecompile_recovery import runtime_lifecycle as L

pytestmark = pytest.mark.unit

H = {c: c * 64 for c in "abcdef"}
OWNER = {"pid": 4100, "start": "900100", "session": 4100}
OTHER = {"pid": 5200, "start": "900200", "session": 5200}
GAME = {"pid": 4300, "start": "900300", "session": 4100}
NOW = 1_000.0


def manifest(**overrides):
    base = {
        "id": "kotor.k1.model-scale.v1",
        "operation_contract_sha256": H["a"],
        "target_sha256": H["b"],
        "deployed_script_sha256": H["c"],
        "fixture_sha256": H["d"],
        "runtime_sha256": H["e"],
        "staging": {"deployed_script": "lua/scale.lua", "fixture": "saves/fixture.sav",
                    "runtime_artifact": "kotorphasor.dll"},
    }
    base.update(overrides)
    return base


def record(state="prepared", owner=OWNER, processes=(), generation=1, **kw):
    return L.build_owner_record(
        manifest=kw.pop("manifest", manifest()), staged_bundle="/nvme/stage/k1-op",
        staged_tree_sha256=kw.pop("tree", H["f"]), owner=owner, fixture_sha256=kw.pop("fixture", H["d"]),
        generation=generation, created_at=NOW - 10, processes=list(processes), state=state)


def observe(*alive, unreadable=(), candidates=(), tree=H["f"]):
    entries = [dict(identity) for identity in alive] + [{"pid": pid, "readable": False} for pid in unreadable]
    return {"observed_at": NOW, "processes": entries, "candidates": [dict(c) for c in candidates],
            "staged_tree_sha256": tree}


def run(rec, obs, *, requester=OTHER, man=None, attempt=0):
    return L.reconcile(rec, manifest=man or manifest(), requester=requester, observation=obs,
                       now=NOW, attempt=attempt, wake_bound_seconds=120.0, max_attempts=3)


def test_manifest_digest_uses_kotorphasor_canonical_form_and_record_keeps_content():
    m = manifest()
    expected = hashlib.sha256(json.dumps(m, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert L.manifest_sha256(m) == expected
    rec = record()
    assert rec["format"] == L.OWNER_FORMAT
    assert rec["manifest"] == m and rec["manifest_sha256"] == expected
    tampered = json.loads(json.dumps(rec))
    tampered["manifest"]["runtime_sha256"] = H["a"]
    with pytest.raises(L.LifecycleError, match="manifest"):
        L.validate_owner_record(tampered)


def test_owner_record_refuses_unbound_fixture_mutable_tree_or_incomplete_identity():
    for bad in ({"fixture": H["a"]}, {"tree": "F" * 64}, {"owner": {"pid": 1, "start": "1"}},
                {"manifest": {**manifest(), "extra": 1}}, {"manifest": manifest(fixture_sha256="xyz")}):
        with pytest.raises(L.LifecycleError):
            record(**bad)


def test_load_refuses_duplicate_fields_and_unreadable_records(tmp_path):
    path = tmp_path / "owner.json"
    text = json.dumps(record(), sort_keys=True)
    path.write_text(text[:-1] + ', "state": "released"}')
    with pytest.raises(L.LifecycleError, match="duplicate"):
        L.load_owner_record(path)
    path.write_text("{")
    with pytest.raises(L.LifecycleError):
        L.load_owner_record(path)


def test_no_prior_owner_and_no_candidates_admits_generation_one():
    result = run(None, observe(OTHER))
    assert result["decision"] == "admit" and result["generation"] == 1
    assert result["reason"] is None and result["wake"] is None


def test_unattributed_same_name_process_is_unknown_not_a_kill_target():
    stray = {"pid": 7000, "start": "901000", "session": 7000}
    result = run(None, observe(OTHER, stray, candidates=[stray]))
    assert (result["decision"], result["reason"]) == ("blocked", "unknown")
    assert {"process_exit": {"pid": 7000, "start": "901000"}} in result["wake"]["reevaluate_when"]["any_of"]
    assert result["wake"]["not_after"] == NOW + 120.0


def test_unreadable_owner_identity_is_unknown_never_absent():
    result = run(record(), observe(OTHER, unreadable=[OWNER["pid"]]))
    assert (result["decision"], result["reason"]) == ("blocked", "unknown")


def test_live_foreign_owner_is_competing_with_bounded_wake():
    rec = record()
    result = run(rec, observe(OWNER, OTHER))
    assert (result["decision"], result["reason"]) == ("blocked", "competing")
    any_of = result["wake"]["reevaluate_when"]["any_of"]
    assert {"process_exit": {"pid": OWNER["pid"], "start": OWNER["start"]}} in any_of
    assert {"record_changes_from": L.record_sha256(rec)} in any_of
    assert result["wake"]["attempt"] == 1 and result["wake"]["max_attempts"] == 3


def test_dead_owner_with_surviving_game_is_stale_and_names_the_survivor():
    rec = record(processes=[{"role": "game", **GAME}])
    result = run(rec, observe(OTHER, GAME, candidates=[GAME]))
    assert (result["decision"], result["reason"]) == ("blocked", "stale")
    assert {"process_exit": {"pid": GAME["pid"], "start": GAME["start"]}} in result["wake"]["reevaluate_when"]["any_of"]


def test_pid_reuse_does_not_count_as_the_recorded_owner():
    reused = {**OWNER, "start": "999999"}
    result = run(record(), observe(OTHER, reused))
    assert result["reason"] == "stale"


def test_quarantined_record_never_self_clears():
    result = run(record(state="quarantined", generation=2), observe(OTHER))
    assert (result["decision"], result["reason"]) == ("blocked", "stale")


def test_released_record_admits_successor_generation():
    rec = record(state="released", generation=4)
    result = run(rec, observe(OTHER))
    assert result["decision"] == "admit" and result["generation"] == 5


def test_same_owner_resume_requires_same_manifest_and_unchanged_staging():
    rec = record(state="running", processes=[{"role": "game", **GAME}])
    ok = run(rec, observe(OWNER, GAME, candidates=[GAME]), requester=OWNER)
    assert ok["decision"] == "admit" and ok["generation"] == 1
    drift = run(rec, observe(OWNER, GAME, candidates=[GAME], tree=H["a"]), requester=OWNER)
    assert (drift["decision"], drift["reason"]) == ("blocked", "staging_drift")
    other = run(rec, observe(OWNER), requester=OWNER, man=manifest(runtime_sha256=H["a"]))
    assert (other["decision"], other["reason"]) == ("blocked", "manifest_mismatch")


def test_malformed_record_file_becomes_recorded_unknown(tmp_path):
    path = tmp_path / "owner.json"
    path.write_text('{"format": "x"}')
    result = L.reconcile_file(path, manifest=manifest(), requester=OTHER, observation=observe(OTHER),
                              now=NOW, attempt=0, wake_bound_seconds=60.0, max_attempts=2)
    assert (result["decision"], result["reason"]) == ("blocked", "unknown")
    changed = {"record_changes_from": hashlib.sha256(path.read_bytes()).hexdigest()}
    assert changed in result["wake"]["reevaluate_when"]["any_of"]


def test_exhausted_attempts_are_terminal_without_wake():
    result = run(record(), observe(OWNER, OTHER), attempt=3)
    assert result["decision"] == "blocked" and result["terminal"] is True and result["wake"] is None


def test_blocked_results_name_no_path_launch_or_repair():
    rec = record(processes=[{"role": "game", **GAME}])
    results = [
        run(None, observe(OTHER, candidates=[{"pid": 9, "start": "9", "session": 9}])),
        run(rec, observe(OWNER, OTHER)),
        run(rec, observe(OTHER, GAME, candidates=[GAME])),
        run(rec, observe(OWNER, tree=H["a"]), requester=OWNER),
        run(rec, observe(OTHER), attempt=5),
    ]
    for result in results:
        assert result["decision"] == "blocked" and result["format"] == L.RESULT_FORMAT
        text = json.dumps({k: v for k, v in result.items() if k != "format"}, sort_keys=True)
        assert "/" not in text and "\\" not in text
        for word in ("launch", "command", "argv", "repair", "path", "kill", "delete", "retry_with"):
            assert word not in text.lower(), (word, result["reason"])


def test_record_result_is_content_addressed_and_exclusive(tmp_path):
    result = run(record(), observe(OWNER, OTHER))
    first = L.record_result(tmp_path, result)
    second = L.record_result(tmp_path, result)
    assert first == second and first.name == hashlib.sha256(first.read_bytes()).hexdigest() + ".json"
    assert json.loads(first.read_text()) == result
    assert [p.name for p in tmp_path.iterdir()] == [first.name]


def test_observe_process_reads_start_and_session_from_fake_proc(tmp_path):
    fields = ["S", "1", "4242", "4242"] + ["0"] * 15 + ["123456"] + ["0"] * 10
    (tmp_path / "4242").mkdir()
    (tmp_path / "4242" / "stat").write_text("4242 (odd ) name) " + " ".join(fields) + "\n")
    assert L.observe_process(4242, proc_root=tmp_path) == {"pid": 4242, "start": "123456", "session": 4242}
    assert L.observe_process(4343, proc_root=tmp_path) is None


def test_wake_bounds_must_be_finite_and_positive():
    for bound, attempts in ((0.0, 3), (-1.0, 3), (float("inf"), 3), (60.0, 0), (60.0, True)):
        with pytest.raises(L.LifecycleError):
            L.reconcile(None, manifest=manifest(), requester=OTHER, observation=observe(OTHER), now=NOW,
                        attempt=0, wake_bound_seconds=bound, max_attempts=attempts)
