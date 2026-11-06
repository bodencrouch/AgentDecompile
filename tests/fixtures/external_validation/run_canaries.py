"""Run explicit installed provider CLIs on original fixtures in private scratch.

Usage: /usr/bin/python3 run_canaries.py VENV_BIN NEW_SCRATCH_DIRECTORY
No installation, model provider, live backend, or recovery action is invoked.
"""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys

bin_dir = Path(sys.argv[1]).resolve()
root = Path(sys.argv[2]).resolve()
root.mkdir(parents=True, exist_ok=False)
fixtures = Path(__file__).resolve().parent
for name in ("reference.py", "candidate.py", "benchmark.json", "re-agent.yaml",
             "source-positive", "source-negative", "snapshot"):
    source, dest = fixtures / name, root / name
    if source.is_dir():
        shutil.copytree(source, dest)
    else:
        shutil.copyfile(source, dest)
commands = [
    ("reagent-version", [str(bin_dir / "re-agent"), "--version"], 0),
    ("reccmp-version", [str(bin_dir / "reccmp-decomplint"), "--version"], 0),
    ("benchmark", [str(bin_dir / "re-agent"), "benchmark", "--manifest", "benchmark.json", "--output", "benchmark-report.json"], 0),
    ("plan", [str(bin_dir / "re-agent"), "--config", "re-agent.yaml", "plan", "--address", "0x401000", "--max-depth", "0", "--max-functions", "1", "--output", "plan-report.json"], 0),
    ("lint-positive", [str(bin_dir / "reccmp-decomplint"), "--target", "CANARY", "--warnfail", "source-positive"], 0),
    ("lint-negative", [str(bin_dir / "reccmp-decomplint"), "--target", "CANARY", "--warnfail", "source-negative"], 1),
]
results = []
for name, argv, expected_exit in commands:
    process = subprocess.run(argv, cwd=root, text=True, capture_output=True, timeout=30)
    (root / f"{name}.stdout").write_text(process.stdout)
    (root / f"{name}.stderr").write_text(process.stderr)
    results.append({"name": name, "argv": argv, "cwd": str(root), "exit": process.returncode,
                    "expected_exit": expected_exit, "expectation_met": process.returncode == expected_exit})
reports = {}
for name in ("benchmark-report.json", "plan-report.json"):
    path = root / name
    if path.exists():
        reports[name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "data": json.loads(path.read_text())}
benchmark = reports.get("benchmark-report.json", {}).get("data", {})
plan = reports.get("plan-report.json", {}).get("data", {})
rows = benchmark.get("results", [])
content_checks = {
    "benchmark_positive_observed": len(rows) == 2 and rows[0].get("matched") is True and rows[0].get("cases_run") == 3,
    "benchmark_negative_detected": len(rows) == 2 and rows[1].get("matched") is False and rows[1].get("expected_match") is False and rows[1].get("cases_run") == 1,
    "snapshot_decompile_consumed": plan.get("evidence", {}).get("00401000", {}).get("decompile", {}).get("decompiled") == "int canary(int value) { return value * 2 + 1; }",
    "snapshot_bounded_selection": len(plan.get("functions", [])) == 1 and plan.get("max_functions") == 1 and plan.get("max_depth") == 0,
    "negative_annotation_diagnostic": "duplicate_offset" in (root / "lint-negative.stdout").read_text(),
}
receipt = {"content_checks": content_checks, "scope": "synthetic provider interoperability only", "commands": results, "reports": reports}
(root / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt, indent=2))
sys.exit(0 if all(item["expectation_met"] for item in results) and all(content_checks.values()) else 1)
