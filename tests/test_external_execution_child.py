"""One synthetic guarded child run through a real venv (--without-pip) and a fake provider.

The provider is a fake ReAgent entry module that writes a valid benchmark report, reads
the candidate and dumps the environment it actually received. No real ReAgent, reccmp,
Wine or network is involved.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from agentdecompile_recovery.corpus import external_execution as ee
from agentdecompile_recovery.corpus.external_validation import SCHEMA_BASELINES, normalize_report
from tests._external_execution_fakes import make_provider, reagent_params, sha

FAKE_ENTRY = '''
import json, os, sys

def main():
    args = sys.argv[1:]
    assert args[0] == "benchmark", args
    manifest = json.load(open(args[args.index("--manifest") + 1]))
    output = args[args.index("--output") + 1]
    results = []
    for row in manifest["benchmarks"]:
        consumed = open(row["candidate"][-1], "rb").read()
        results.append({"name": row["name"], "matched": True, "expected_match": True,
                        "cases_run": 1, "findings": ["candidate bytes %d" % len(consumed)],
                        "duration_s": 0.0})
    with open("provider-env.json", "w") as f:
        json.dump({"environ": dict(os.environ), "argv0": sys.argv[0], "cwd": os.getcwd(),
                   "flags_isolated": sys.flags.isolated, "no_site": sys.flags.no_site}, f)
    with open(output, "w") as f:
        json.dump({"schema_version": 1, "results": results, "total": len(results),
                   "expectations_met": len(results)}, f)
    return 0
'''


def test_guarded_main_runs_fake_provider_and_rehashes_inputs(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-leak")
    venv = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(venv)], check=True, timeout=120)
    make_provider(venv, "reagent-benchmark", entry_source=FAKE_ENTRY)
    params = reagent_params(tmp_path, venv=venv)
    frozen = ee.freeze_parameters(params, "reagent-benchmark")

    argv = ee.guarded_command(frozen)
    assert ee.command_matches(argv, frozen)
    child = subprocess.run(argv, capture_output=True, text=True, timeout=300,
                           env={**os.environ, "ANTHROPIC_API_KEY": "must-not-leak"})
    assert child.returncode == 0, child.stderr

    report_dir = Path(frozen["report-dir"])
    execution = json.loads((report_dir / "execution.json").read_text())
    assert execution["schema"] == "agentdecompile.external-execution/v1"
    assert execution["execution_state"] == "completed" and execution["refusal"] is None
    assert execution["pin"] == {**execution["pin"], "commit": SCHEMA_BASELINES["reagent-benchmark"],
                                "verified": True}
    # Three-phase input identities: freeze, before the run, after the run.
    phases = execution["inputs"]
    assert phases["freeze"] == phases["before"] == phases["after"]
    assert phases["after"]["candidate"] == sha(Path(frozen["candidate"]).read_bytes())
    assert set(phases["after"]) >= {"manifest", "candidate", "inputs-dir"}

    raw = (report_dir / "report.json").read_bytes()
    assert execution["raw_report_sha256"] == sha(raw)
    normalized = json.loads((report_dir / "normalized.json").read_text())
    assert normalized["normalized"] == normalize_report(raw, "reagent-benchmark")
    assert normalized["provenance_verified"] is True
    assert normalized["recovery_accepted"] is False
    assert normalize_report(raw, "reagent-benchmark")["checks"][0]["findings"] == [
        f"candidate bytes {len(Path(frozen['candidate']).read_bytes())}"]

    # The environment the provider actually saw is the recorded allowlist, nothing more.
    seen = json.loads((report_dir / "work" / "provider-env.json").read_text())
    assert "ANTHROPIC_API_KEY" not in seen["environ"]
    assert seen["environ"]["HOME"] != os.environ.get("HOME")
    assert seen["environ"]["HOME"].startswith(str(report_dir))
    assert set(seen["environ"]) <= ee.ENV_ALLOWLIST | {"LC_CTYPE"}
    assert execution["env"] == {k: v for k, v in seen["environ"].items() if k in execution["env"]}
    assert seen["argv0"] == "re-agent" and seen["flags_isolated"] == 1 and seen["no_site"] == 0
    assert seen["cwd"] == str(report_dir / "work")
    assert execution["process"]["returncode"] == 0
    assert execution["streams"]["stdout"]["sha256"] == sha((report_dir / "stdout.log").read_bytes())
