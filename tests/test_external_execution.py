"""Unit semantics of the guarded external-execution adapter (P1.3 step 1).

Synthetic only: fake dist-info, hand-built PE/PDB bytes, fake Wine scripts. No real
reccmp, ReAgent or Wine runs here.
"""
from __future__ import annotations

import copy
import json
import os
import pwd
import sqlite3
import sys
from pathlib import Path

import pytest

from agentdecompile_recovery.corpus import external_execution as ee
from agentdecompile_recovery.corpus.external_validation import (
    SCHEMA_BASELINES, bind_execution, normalize_report)
from tests._external_execution_fakes import (
    GUID, make_prefix, make_provider, make_wine, pdb_with_info, pe_with_codeview,
    reagent_params, reccmp_params, sha, site_packages, write)

FIXTURES = Path(__file__).parent / "fixtures" / "external_validation" / "observed-2026-09-22"


def refusal(excinfo) -> str:
    return excinfo.value.code


# --- pins -----------------------------------------------------------------------

def test_pins_equal_schema_baselines():
    assert {k: v["commit"] for k, v in ee.PINS.items()} == SCHEMA_BASELINES
    assert ee.PINS["reccmp-compare"]["archive_sha256"].startswith("6801afde")
    assert ee.PINS["reagent-benchmark"]["archive_sha256"].startswith("65c22a9d")


# --- refusal codes: one trigger per code ------------------------------------------

def _freeze_reccmp(tmp, **change):
    params = reccmp_params(tmp)
    params.update(change)
    return ee.freeze_parameters(params, "reccmp-compare")


def _freeze_reagent(tmp, **kw):
    return ee.freeze_parameters(reagent_params(tmp, **kw), "reagent-benchmark")


def _wine_unavailable(tmp):
    _freeze_reccmp(tmp, wine=str(tmp / "missing" / "wine"))


def _winepath_unavailable(tmp):
    _freeze_reccmp(tmp, wine=str(make_wine(tmp / "w", winepath=False)))


def _wineserver_unavailable(tmp):
    _freeze_reccmp(tmp, wine=str(make_wine(tmp / "w", wineserver=False)))


def _cvdump_unavailable(tmp):
    _freeze_reccmp(tmp, cvdump=str(tmp / "missing-cvdump.exe"))


def _wineprefix_uninitialized(tmp):
    _freeze_reccmp(tmp, wineprefix=str(make_prefix(tmp / "p", initialized=False)))


def _wineprefix_default_refused(tmp):
    # Refused on the path alone; nothing reads or creates the real ~/.wine.
    _freeze_reccmp(tmp, wineprefix=os.path.join(pwd.getpwuid(os.getuid()).pw_dir, ".wine"))


def _provider_unpinned(tmp):
    ee.verify_provider(make_provider(tmp / "v", "reagent-benchmark", commit="0" * 40), "reagent-benchmark")


def _provider_record_mismatch(tmp):
    venv = make_provider(tmp / "v", "reagent-benchmark")
    (site_packages(venv) / "fake_reagent_benchmark" / "cli.py").write_text("def main():\n    return 1\n")
    ee.verify_provider(venv, "reagent-benchmark")


def _provider_entry_point_missing(tmp):
    ee.verify_provider(make_provider(tmp / "v", "reagent-benchmark", entry_point=False), "reagent-benchmark")


def _provider_interpreter_unavailable(tmp):
    ee.verify_provider(make_provider(tmp / "v", "reagent-benchmark", interpreter=False), "reagent-benchmark")


def _provider_implementation_changed(tmp):
    frozen = _freeze_reagent(tmp)
    Path(frozen["provider-venv"], "bin", "python").write_bytes(b"#!another interpreter\n")
    ee.reverify_provider(frozen)


def _input_hash_mismatch(tmp):
    params = reagent_params(tmp)
    params["candidate-sha256"] = "0" * 64
    ee.freeze_parameters(params, "reagent-benchmark")


def _input_changed_during_run(tmp):
    frozen = _freeze_reagent(tmp)
    before = ee.input_identities(frozen)
    Path(frozen["candidate"]).write_bytes(b"rewritten mid-run\n")
    ee.compare_identities(before, ee.input_identities(frozen), "input_changed_during_run")


def _project_hash_mismatch(tmp):
    params = reccmp_params(tmp, project_sha="f" * 64)
    ee.freeze_parameters(params, "reccmp-compare")


def _reccmp_target_unknown(tmp):
    _freeze_reccmp(tmp, **{"reccmp-target": "NOPE"})


def _pdb_rebuild_mismatch(tmp):
    params = reccmp_params(tmp, pdb_age=2)
    ee.freeze_parameters(params, "reccmp-compare")


def _slug_md5_mismatch(tmp):
    db = tmp / "corpus.sqlite"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE binary (id INTEGER PRIMARY KEY, slug TEXT UNIQUE NOT NULL, md5 TEXT)")
    con.execute("INSERT INTO binary (slug, md5) VALUES ('orig', 'deadbeef')")
    con.commit()
    con.close()
    _freeze_reccmp(tmp, db=str(db), **{"binary-slug": "orig"})


def _report_dir_exists(tmp):
    params = reagent_params(tmp)
    Path(params["report-dir"]).mkdir(parents=True)
    ee.freeze_parameters(params, "reagent-benchmark")


def _report_dir_parent_missing(tmp):
    params = reagent_params(tmp)
    params["report-dir"] = str(tmp / "absent" / "report")
    ee.freeze_parameters(params, "reagent-benchmark")


def _symlink_external_resource(tmp):
    params = reagent_params(tmp)
    link = tmp / "in" / "candidate-link.c"
    link.symlink_to(params["candidate"])
    params["candidate"] = str(link)
    ee.freeze_parameters(params, "reagent-benchmark")


def _output_aliases_input(tmp):
    params = reagent_params(tmp)
    params["report-dir"] = str(Path(params["inputs-dir"]) / "report")
    ee.freeze_parameters(params, "reagent-benchmark")


def _manifest_invalid(tmp):
    _freeze_reagent(tmp, rows=[{"name": "no-candidate", "reference": [os.path.realpath(sys.executable)]}])


def _manifest_shell_command(tmp):
    _freeze_reagent(tmp, rows=[{"name": "shell", "reference": "python ref.py", "candidate": "python cand.py"}])


def _candidate_not_consumed(tmp):
    tool = os.path.realpath(sys.executable)
    _freeze_reagent(tmp, rows=[{"name": "ignores", "reference": [tool, "-V"], "candidate": [tool, "-V"]}])


def _manifest_timeout_exceeds_action(tmp):
    params = reagent_params(tmp)
    data = json.loads(Path(params["manifest"]).read_text())
    data["benchmarks"][0]["timeout_s"] = 10_000
    Path(params["manifest"]).write_text(json.dumps(data))
    params["manifest-sha256"] = sha(Path(params["manifest"]).read_bytes())
    ee.freeze_parameters(params, "reagent-benchmark")


REFUSAL_CASES = {
    "wine_unavailable": _wine_unavailable, "winepath_unavailable": _winepath_unavailable,
    "wineserver_unavailable": _wineserver_unavailable, "cvdump_unavailable": _cvdump_unavailable,
    "wineprefix_uninitialized": _wineprefix_uninitialized,
    "wineprefix_default_refused": _wineprefix_default_refused,
    "provider_unpinned": _provider_unpinned, "provider_record_mismatch": _provider_record_mismatch,
    "provider_entry_point_missing": _provider_entry_point_missing,
    "provider_interpreter_unavailable": _provider_interpreter_unavailable,
    "provider_implementation_changed": _provider_implementation_changed,
    "input_hash_mismatch:candidate": _input_hash_mismatch,
    "input_changed_during_run:candidate": _input_changed_during_run,
    "project_hash_mismatch": _project_hash_mismatch, "reccmp_target_unknown": _reccmp_target_unknown,
    "pdb_rebuild_mismatch": _pdb_rebuild_mismatch, "slug_md5_mismatch": _slug_md5_mismatch,
    "report_dir_exists": _report_dir_exists, "report_dir_parent_missing": _report_dir_parent_missing,
    "symlink_external_resource": _symlink_external_resource,
    "output_aliases_input": _output_aliases_input, "manifest_invalid": _manifest_invalid,
    "manifest_shell_command": _manifest_shell_command,
    "candidate_not_consumed": _candidate_not_consumed,
    "manifest_timeout_exceeds_action": _manifest_timeout_exceeds_action,
}


def test_every_refusal_code_has_a_trigger():
    assert {code.split(":")[0] for code in REFUSAL_CASES} == set(ee.REFUSAL_CODES)


@pytest.mark.parametrize("code", sorted(REFUSAL_CASES))
def test_refusal_code(code, tmp_path):
    with pytest.raises(ee.Refusal) as excinfo:
        REFUSAL_CASES[code](tmp_path)
    assert refusal(excinfo) == code


# --- provider pin failures -----------------------------------------------------------

@pytest.mark.parametrize("change", [{"commit": "1" * 40}, {"archive": "2" * 64}, {"version": "9.9.9"}])
def test_fake_dist_info_pin_failures(change, tmp_path):
    venv = make_provider(tmp_path / "v", "reccmp-compare", **change)
    with pytest.raises(ee.Refusal) as excinfo:
        ee.verify_provider(venv, "reccmp-compare")
    assert refusal(excinfo) == "provider_unpinned"


def test_record_row_for_missing_file_is_a_mismatch(tmp_path):
    venv = make_provider(tmp_path / "v", "reccmp-compare")
    (site_packages(venv) / "fake_reccmp_compare" / "__init__.py").unlink()
    with pytest.raises(ee.Refusal) as excinfo:
        ee.verify_provider(venv, "reccmp-compare")
    assert refusal(excinfo) == "provider_record_mismatch"


def test_verified_provider_identity(tmp_path):
    venv = make_provider(tmp_path / "v", "reccmp-compare")
    identity = ee.verify_provider(venv, "reccmp-compare")
    assert identity["commit"] == SCHEMA_BASELINES["reccmp-compare"]
    assert identity["entry_point"] == "fake_reccmp_compare.cli:main"
    assert identity["script"] == "reccmp-reccmp"
    assert identity["interpreter_sha256"] == sha(b"#!fake interpreter\n")
    assert identity["verified"] is True


def test_venv_interpreter_symlink_is_recorded_not_refused(tmp_path):
    venv = make_provider(tmp_path / "v", "reagent-benchmark", interpreter=False)
    (venv / "bin").mkdir(parents=True, exist_ok=True)
    (venv / "bin" / "python").symlink_to(os.path.realpath(sys.executable))
    identity = ee.verify_provider(venv, "reagent-benchmark")
    assert identity["interpreter"] == os.path.realpath(sys.executable)


def test_symlinked_venv_directory_refused(tmp_path):
    venv = make_provider(tmp_path / "v", "reagent-benchmark")
    link = tmp_path / "venv-link"
    link.symlink_to(venv)
    params = reagent_params(tmp_path, venv=link)
    with pytest.raises(ee.Refusal) as excinfo:
        ee.freeze_parameters(params, "reagent-benchmark")
    assert refusal(excinfo) == "symlink_external_resource"


def test_symlinked_parent_of_input_refused(tmp_path):
    params = reagent_params(tmp_path)
    alias = tmp_path / "alias"
    alias.symlink_to(tmp_path / "in")
    params["candidate"] = str(alias / "candidate.c")
    with pytest.raises(ee.Refusal) as excinfo:
        ee.freeze_parameters(params, "reagent-benchmark")
    assert refusal(excinfo) == "symlink_external_resource"


def test_symlink_inside_input_tree_refused(tmp_path):
    params = reagent_params(tmp_path)
    (Path(params["inputs-dir"]) / "escape").symlink_to("/etc/hostname")
    with pytest.raises(ee.Refusal) as excinfo:
        ee.freeze_parameters(params, "reagent-benchmark")
    assert refusal(excinfo) == "symlink_external_resource"


# --- PE / PDB -----------------------------------------------------------------------

def test_pdb_matches_rebuild_positive(tmp_path):
    pe = write(tmp_path / "r.exe", pe_with_codeview())
    pdb = write(tmp_path / "r.pdb", pdb_with_info())
    assert ee.pdb_matches_rebuild(pe, pdb) == {"guid": GUID.hex(), "age": 1}


@pytest.mark.parametrize("pe_kw,pdb_kw", [({"guid": bytes(16)}, {}), ({}, {"age": 7})])
def test_pdb_guid_or_age_mismatch(pe_kw, pdb_kw, tmp_path):
    pe = write(tmp_path / "r.exe", pe_with_codeview(**pe_kw))
    pdb = write(tmp_path / "r.pdb", pdb_with_info(**pdb_kw))
    with pytest.raises(ee.Refusal) as excinfo:
        ee.pdb_matches_rebuild(pe, pdb)
    assert refusal(excinfo) == "pdb_rebuild_mismatch"


@pytest.mark.parametrize("pe,pdb", [(b"MZ", pdb_with_info()), (pe_with_codeview(), b"not a pdb"),
                                    (pe_with_codeview()[:0x210], pdb_with_info()),
                                    (pe_with_codeview(), pdb_with_info()[:1024])],
                         ids=["pe-dos-stub-only", "pdb-foreign-bytes", "pe-truncated", "pdb-truncated"])
def test_truncated_or_foreign_pe_pdb_refused(pe, pdb, tmp_path):
    with pytest.raises(ee.Refusal) as excinfo:
        ee.pdb_matches_rebuild(write(tmp_path / "r.exe", pe), write(tmp_path / "r.pdb", pdb))
    assert refusal(excinfo) == "pdb_rebuild_mismatch"


# --- generated reccmp yml -----------------------------------------------------------

def test_generated_reccmp_yml(tmp_path):
    frozen = _freeze_reccmp(tmp_path)
    workdir = tmp_path / "gen"
    workdir.mkdir()
    written = ee.write_reccmp_config(frozen, workdir)
    assert sorted(p.name for p in written) == ["reccmp-build.yml", "reccmp-user.yml"]
    # JSON is a YAML 1.2 subset; the child needs no YAML library.
    user = json.loads((workdir / "reccmp-user.yml").read_text())
    build = json.loads((workdir / "reccmp-build.yml").read_text())
    assert user == {"targets": {"CANARY": {"path": frozen["original"]}}}
    assert build == {"project": frozen["project-dir"],
                     "targets": {"CANARY": {"path": frozen["rebuild"], "pdb": frozen["pdb"]}}}
    assert all(Path(p).is_absolute() for p in (frozen["original"], frozen["rebuild"], frozen["pdb"]))


def test_reccmp_argv_uses_frozen_report_dir(tmp_path):
    frozen = _freeze_reccmp(tmp_path)
    argv, cwd = ee.provider_invocation(frozen)
    report = frozen["report-dir"]
    assert argv[:3] == [str(Path(frozen["provider-venv"]) / "bin" / "python"), "-I", "-c"]
    assert "-S" not in argv
    assert argv[4:] == ["--target", "CANARY", "--json", f"{report}/report.json", "--silent"]
    assert cwd == f"{report}/reccmp"


# --- environment allowlist ---------------------------------------------------------

def test_env_allowlist_drops_host_home_and_keys(tmp_path, monkeypatch):
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY",
                "SSH_AUTH_SOCK", "PYTHONPATH", "LD_PRELOAD"):
        monkeypatch.setenv(key, "secret")
    host_home = os.environ.get("HOME", "")
    frozen = _freeze_reccmp(tmp_path)
    env = ee.child_environment(frozen)
    assert set(env) <= ee.ENV_ALLOWLIST
    assert env["HOME"].startswith(frozen["report-dir"])
    assert env["HOME"] != host_home
    assert env["WINEPREFIX"] == frozen["wineprefix"]
    assert not any(v == "secret" for v in env.values())
    assert not any(k.endswith(("_KEY", "_TOKEN", "_SECRET")) for k in env)


def test_reagent_env_carries_no_wine(tmp_path):
    env = ee.child_environment(_freeze_reagent(tmp_path))
    assert "WINEPREFIX" not in env and set(env) <= ee.ENV_ALLOWLIST


# --- guarded command round trip ------------------------------------------------------

def test_guarded_command_round_trip(tmp_path):
    frozen = _freeze_reagent(tmp_path)
    argv = ee.guarded_command(frozen)
    assert argv[:4] == [sys.executable, "-I", "-S", "-c"]
    assert argv[4] == ee._BOOTSTRAP
    assert ee.command_matches(argv, frozen)
    assert json.loads(argv[-1])["implementation"] == ee.implementation_identity()
    tampered = {**frozen, "timeout": frozen["timeout"] + 1}
    assert not ee.command_matches(argv, tampered)
    assert not ee.command_matches(argv[:-1] + ["{not json"], frozen)
    assert not ee.command_matches([], frozen)


def test_guarded_main_refuses_changed_implementation(tmp_path):
    frozen = _freeze_reagent(tmp_path)
    payload = json.loads(ee.guarded_command(frozen)[-1])
    payload["implementation"] = {"elsewhere.py": "0" * 64}
    with pytest.raises(ValueError, match="external_execution_implementation_changed"):
        ee.guarded_main(json.dumps(payload))


def test_implementation_identity_covers_both_modules():
    names = {Path(p).name for p in ee.implementation_identity()}
    assert names == {"external_execution.py", "external_validation.py"}


# --- manifest -------------------------------------------------------------------------

def test_manifest_records_argv0_hashes(tmp_path):
    frozen = _freeze_reagent(tmp_path)
    rows = frozen["manifest-rows"]
    tool = os.path.realpath(sys.executable)
    assert rows[0]["reference_argv0"] == {"path": tool, "sha256": sha(Path(tool).read_bytes())}
    assert rows[0]["consumes_candidate"] is True


@pytest.mark.parametrize("argv0", ["/bin/sh", "/usr/bin/bash", "/usr/bin/env"])
def test_manifest_shell_argv0_refused(argv0, tmp_path):
    rows = [{"name": "s", "reference": [argv0, "-c", "x"], "candidate": [argv0, "-c", "x"]}]
    with pytest.raises(ee.Refusal) as excinfo:
        ee.validate_benchmark_manifest(write(tmp_path / "m.json", json.dumps({"benchmarks": rows})),
                                       str(tmp_path / "c.c"), timeout=60)
    assert refusal(excinfo) == "manifest_shell_command"


def test_manifest_relative_argv0_refused(tmp_path):
    rows = [{"name": "r", "reference": ["python3", "a"], "candidate": ["python3", str(tmp_path / "c.c")]}]
    with pytest.raises(ee.Refusal) as excinfo:
        ee.validate_benchmark_manifest(write(tmp_path / "m.json", json.dumps({"benchmarks": rows})),
                                       str(tmp_path / "c.c"), timeout=60)
    assert refusal(excinfo) == "manifest_invalid"


# --- wine shutdown ----------------------------------------------------------------------

def test_wine_shutdown_kills_and_waits_on_the_frozen_prefix(tmp_path):
    log = tmp_path / "wineserver.log"
    wine = make_wine(tmp_path, log=log)
    prefix = make_prefix(tmp_path)
    result = ee.wine_shutdown(str(Path(wine).parent / "wineserver"), str(prefix),
                              {"PATH": "/usr/bin:/bin", "WINEPREFIX": str(prefix)})
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert calls == [[["-k"], str(prefix)], [["-w"], str(prefix)]]
    assert [step["returncode"] for step in result] == [0, 0]


# --- execution_state mapping ----------------------------------------------------------

@pytest.mark.parametrize("kw,state", [
    ({"returncode": 0, "report_valid": True}, "completed"),
    ({"returncode": 0, "report_valid": False}, "invalid_output"),
    ({"returncode": 3, "report_valid": True}, "crashed"),
    ({"returncode": -9, "report_valid": False}, "crashed"),
    ({"returncode": None, "timed_out": True}, "timed_out"),
    ({"refusal": "wine_unavailable"}, "unavailable"),
    ({"refusal": "wineprefix_uninitialized"}, "unavailable"),
    ({"refusal": "provider_interpreter_unavailable"}, "unavailable"),
    ({"refusal": "provider_unpinned"}, "unsupported"),
    ({"refusal": "provider_implementation_changed"}, "unsupported"),
    ({"refusal": "pdb_rebuild_mismatch"}, "unsupported"),
    ({"refusal": "input_changed_during_run:candidate", "returncode": 0, "report_valid": True}, "invalid_output"),
])
def test_execution_state_mapping(kw, state):
    assert ee.execution_state(**kw) == state
    assert state in ee.EXECUTION_STATES


# --- bind_execution --------------------------------------------------------------------

def _execution(raw: bytes, **change):
    phase = {"candidate": "a" * 64}
    execution = {"schema": ee.SCHEMA, "provider": "reagent-benchmark", "execution_state": "completed",
                 "pin": {"commit": SCHEMA_BASELINES["reagent-benchmark"], "verified": True},
                 "inputs": {"freeze": dict(phase), "before": dict(phase), "after": dict(phase)},
                 "raw_report_sha256": sha(raw)}
    execution.update(change)
    return execution


def test_bind_execution_leaves_normalized_unchanged():
    raw = (FIXTURES / "benchmark-report.json").read_bytes()
    normalized = normalize_report(raw, "reagent-benchmark")
    pristine = copy.deepcopy(normalized)
    bound = bind_execution(normalized, _execution(raw))
    assert normalized == pristine
    assert bound["normalized"] == normalize_report(raw, "reagent-benchmark")
    assert bound["provenance_verified"] is True
    assert bound["provider_revision"] == SCHEMA_BASELINES["reagent-benchmark"]
    assert bound["proposal_only"] is True and bound["recovery_accepted"] is False


@pytest.mark.parametrize("change", [
    {"pin": {"commit": SCHEMA_BASELINES["reagent-benchmark"], "verified": False}},
    {"pin": {"commit": "0" * 40, "verified": True}},
    {"inputs": {"freeze": {"c": "a"}, "before": {"c": "a"}, "after": {"c": "b"}}},
    {"inputs": {"freeze": {"c": "a"}, "before": {"c": "b"}, "after": {"c": "b"}}},
    {"raw_report_sha256": "0" * 64},
    {"execution_state": "crashed"},
    {"provider": "reccmp-compare"},
])
def test_bind_execution_withholds_provenance(change):
    raw = (FIXTURES / "benchmark-report.json").read_bytes()
    normalized = normalize_report(raw, "reagent-benchmark")
    bound = bind_execution(normalized, _execution(raw, **change))
    assert bound["provenance_verified"] is False
    assert bound["proposal_only"] is True and bound["recovery_accepted"] is False
    assert bound["normalized"] == normalize_report(raw, "reagent-benchmark")
