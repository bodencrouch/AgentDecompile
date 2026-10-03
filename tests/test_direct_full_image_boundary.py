"""Refusal and lookup regressions; synthetic builds do not prove recovery."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from agentdecompile_recovery.corpus import verify_direct_full_image as direct
from agentdecompile_recovery.corpus.dashboard.actions import introspect, jobs

pytestmark = pytest.mark.unit

ACTION_ID = "corpus.verify-direct-full-image"
REASON = "same_build_linked_contribution_unavailable"
MISSING_BINDINGS = [
    "source_inventory_capture",
    "effective_toolchain_identity",
    "same_build_object_image_provenance",
    "linked_region_fixups",
    "final_compiled_replacement_ownership",
    "variant_binding",
]


def _direct_fixture(tmp_path, monkeypatch, *, candidate=b"MZfixture", build=None,
                    forged=False, stale=None, local_match=True):
    target = tmp_path / "target.exe"
    target.write_bytes(b"MZfixture")
    src = tmp_path / "source"
    src.mkdir()
    raw = tmp_path / "image.raw"
    raw.write_bytes(b"fixture")
    db = tmp_path / "fixture.sqlite"
    db.write_bytes(b"fixture only; never opened")
    wrapper = tmp_path / "wrapper.sh"
    wrapper.write_text("fixture only; never executed\n")
    vcroot = tmp_path / "vcroot"
    (vcroot / "bin").mkdir(parents=True)
    (vcroot / "bin" / "link.exe").write_bytes(b"fixture")
    work = tmp_path / "work"
    calls = []
    monkeypatch.setattr(direct.time, "time_ns", lambda: 1)
    build = build if build is not None else {"ok": True, "units": 1, "failed": 0}

    def compile_tree(src_dir, output, **kwargs):
        calls.append((src_dir, output, kwargs))
        if candidate is not None:
            output.write_bytes(candidate)
            if stale == "candidate":
                os.utime(output, ns=(0, 0))
        return build

    def verify_local(argv):
        assert "--no-incremental" in argv
        out = Path(argv[argv.index("--out") + 1])
        payload = {"total": 1, "byteExact": int(local_match),
                   "results": [{"ok": local_match, "rawEqual": False, "reloc_linked": False}]}
        if forged:
            payload.update({"verified": True, "compilerProducedWholeImage": True,
                            "linkedContribution": {"status": "complete", "missingBindings": []}})
        out.write_text(json.dumps(payload))
        if stale == "objdiff":
            os.utime(out, ns=(0, 0))
        return 0 if local_match else 1

    monkeypatch.setattr(direct, "compile_and_link_tree", compile_tree)
    monkeypatch.setattr(direct, "verify_byteexact_main", verify_local)
    argv = ["--target", str(target), "--src-dir", str(src), "--raw", str(raw),
            "--db", str(db), "--binary-id", "1", "--compiler", str(wrapper),
            "--vcroot", str(vcroot), "--wineprefix", str(tmp_path / "prefix"),
            "--work-dir", str(work)]
    return argv, work, calls, build


@pytest.mark.parametrize("build", [
    {"ok": True, "units": 1, "objects": 1, "failed": 0},
    {"ok": True, "units": 2, "objects": 1, "failed": 1,
     "failures": [{"source": "missing.c", "diagnostic": "compile failed"}]},
    {"ok": True, "units": 0, "objects": 1, "failed": 0,
     "link": {"inputs": ["stub-main.obj"]}},
])
def test_equal_generic_link_and_local_counts_refuse_terminal_claim(tmp_path, monkeypatch, capsys, build):
    argv, work, calls, _ = _direct_fixture(tmp_path, monkeypatch, build=build)
    assert direct.main(argv) == 1
    receipt = json.loads((work / "receipt.json").read_text())
    assert receipt["wholeFileByteIdentical"] is True
    assert receipt["verified"] is False
    assert receipt["compilerProducedWholeImage"] is False
    assert receipt["linkedContribution"] == {
        "status": "unsupported", "reason": REASON, "missingBindings": MISSING_BINDINGS,
    }
    assert receipt["errors"] == [REASON]
    assert receipt["build"]["compileLink"] == build
    assert receipt["objdiff"]["matchedCount"] == 1
    assert calls[0][2]["entrypoint"] is True
    summary = json.loads(capsys.readouterr().out)
    assert summary["verified"] is False and summary["wholeFileByteIdentical"] is True


def test_success_shaped_json_cannot_supply_linked_authority(tmp_path, monkeypatch):
    forged_build = {"ok": True, "verified": True, "compilerProducedWholeImage": True,
                    "linkedContribution": {"status": "complete", "missingBindings": []}}
    argv, work, _, _ = _direct_fixture(tmp_path, monkeypatch, forged=True, build=forged_build)
    assert direct.main(argv) == 1
    receipt = json.loads((work / "receipt.json").read_text())
    assert receipt["build"]["compileLink"] == forged_build
    assert receipt["linkedContribution"]["status"] == "unsupported"
    assert receipt["verified"] is False and receipt["compilerProducedWholeImage"] is False


def test_direct_parser_has_no_imported_contribution_input(tmp_path, monkeypatch):
    argv, work, calls, _ = _direct_fixture(tmp_path, monkeypatch)
    with pytest.raises(SystemExit) as exc:
        direct.main(argv + ["--linked-contribution", "forged.json"])
    assert exc.value.code == 2
    assert calls == [] and not work.exists()


@pytest.mark.parametrize("options, expected", [
    ({"candidate": None}, "direct compiler/link candidate missing"),
    ({"candidate": b"different"}, "direct compiler/link candidate whole file differs from shipped target"),
    ({"stale": "candidate"}, "candidate was not written by this direct build"),
    ({"stale": "objdiff"}, "function objdiff receipt was not written by this direct build"),
    ({"local_match": False}, "objdiff receipt has 1 nonzero-difference functions"),
    ({"build": {"ok": False}}, "direct compiler/link did not produce a linked PE"),
])
def test_negative_diagnostics_survive_terminal_refusal(tmp_path, monkeypatch, options, expected):
    argv, work, _, _ = _direct_fixture(tmp_path, monkeypatch, **options)
    assert direct.main(argv) == 1
    receipt = json.loads((work / "receipt.json").read_text())
    assert expected in receipt["errors"]
    assert receipt["errors"][-1] == REASON
    assert receipt["verified"] is False and receipt["compilerProducedWholeImage"] is False


def test_existing_work_is_not_reused_or_overwritten(tmp_path, monkeypatch, capsys):
    argv, work, calls, _ = _direct_fixture(tmp_path, monkeypatch)
    work.mkdir()
    receipt = work / "receipt.json"
    receipt.write_text("existing receipt")
    assert direct.main(argv) == 1
    assert calls == [] and receipt.read_text() == "existing receipt"
    summary = json.loads(capsys.readouterr().out)
    assert summary["out"] is None and REASON in summary["errors"]
    assert any("work directory must not already exist" in error for error in summary["errors"])


def test_direct_action_metadata_does_not_qualify_external_release_or_ghidra():
    action = next(action for action in introspect.corpus_specs() if action.id == ACTION_ID)
    assert action.mutating is True and action.long_running is True
    assert action.ghidra_exclusive is False
    fields = {field.name: field.flag for field in action.fields}
    assert fields["work-dir"] == "--work-dir"
    assert fields["src-dir"] == "--src-dir"
    assert fields["binary-id"] == "--binary-id"
    assert "workDir" not in fields and "work_dir" not in fields
    assert ACTION_ID not in jobs._EXTERNAL_ACTION_CONTRACTS
    keys = jobs._resource_keys(action, {"work-dir": "/fixture/work"}, base=Path("/fixture"))
    assert "external" not in keys and "ghidra" not in keys


def _existing_job(action_id, params, root, *, status="running"):
    return jobs.JobRecord(id="fixture", action_id=action_id, title="fixture", argv=[],
                          params=params, execution_root=str(root), status=status)


@pytest.mark.parametrize("status", ["queued", "running", "cancelling"])
@pytest.mark.parametrize("alias", ["absolute", "relative", "symlink"])
def test_direct_duplicate_uses_both_work_dir_fields_and_execution_roots(tmp_path, monkeypatch, status, alias):
    root = tmp_path / "root"
    root.mkdir()
    work = root / "work"
    work.mkdir()
    link = tmp_path / "alias"
    link.symlink_to(work, target_is_directory=True)
    requested = {"absolute": str(work), "relative": "work/../work", "symlink": str(link)}[alias]
    existing = _existing_job(ACTION_ID, {"work-dir": "work"}, root, status=status)
    monkeypatch.setattr(jobs, "live_root", lambda: root)
    monkeypatch.setattr(jobs.STORE, "list", lambda **_: [existing])
    monkeypatch.chdir(tmp_path)  # Relative paths belong to executionRoot, not this cwd.
    assert jobs._active_duplicate(ACTION_ID, {"work-dir": requested}) is existing


def test_duplicate_independence_and_unrelated_legacy_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "live_root", lambda: tmp_path)
    direct_job = _existing_job(ACTION_ID, {"work-dir": "work"}, tmp_path)
    monkeypatch.setattr(jobs.STORE, "list", lambda **_: [direct_job])
    assert jobs._active_duplicate(ACTION_ID, {"work-dir": "different"}) is None
    assert jobs._active_duplicate("corpus.other", {"work-dir": "work"}) is None
    direct_job.status = "succeeded"
    assert jobs._active_duplicate(ACTION_ID, {"work-dir": "work"}) is None
    legacy = _existing_job("corpus.other", {"work_dir": str(tmp_path / "work")}, tmp_path)
    monkeypatch.setattr(jobs.STORE, "list", lambda **_: [legacy])
    assert jobs._active_duplicate("corpus.other", {"workDir": str(tmp_path / "work")}) is legacy
    assert jobs._active_duplicate("corpus.other", {"work-dir": str(tmp_path / "work")}) is None


def test_external_hint_uses_direct_hyphenated_paths_without_changing_other_actions(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    work = root / "work"
    work.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(work, target_is_directory=True)
    proc_root = tmp_path / "proc-fixture"
    proc = proc_root / "12345"
    proc.mkdir(parents=True)
    (proc / "cmdline").write_bytes(
        f"python\0-m\0agentdecompile_recovery.corpus.cli\0--db\0{root / 'db.sqlite'}\0--work-dir\0{work}\0".encode()
    )
    original_iterdir = Path.iterdir
    monkeypatch.setattr(Path, "iterdir", lambda path: iter([proc]) if path == Path("/proc") else original_iterdir(path))
    monkeypatch.setattr(jobs, "live_root", lambda: root)
    monkeypatch.setattr(jobs.os, "getpid", lambda: 99999)
    monkeypatch.chdir(tmp_path)
    for requested in ("work", str(work), str(alias)):
        hint = jobs._external_pipeline_owner(ACTION_ID, {"db": "db.sqlite", "work-dir": requested})
        assert hint is not None and hint["pid"] == "12345"
    assert jobs._external_pipeline_owner(ACTION_ID, {"db": "db.sqlite", "work-dir": "different"}) is None
    assert jobs._external_pipeline_owner("corpus.other-verify", {"db": str(root / "db.sqlite"), "work-dir": str(work)}) is None
    assert jobs._external_pipeline_owner("corpus.other-verify", {"db": str(root / "db.sqlite"), "out-dir": str(work)})["pid"] == "12345"
