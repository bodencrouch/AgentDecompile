# U1 RC-05: per-check outcomes are kept per scope. A passing compile and an all-GREEN ReAgent
# benchmark (normalized by the real external_validation reader) set only "compile" and
# "differential_output"; arithmetic, FP/NaN, methods, globals, indirect calls and exception metadata
# stay unknown, and the ReAgent report itself stays proposal-only. A failing later check is retained.
cd $(git -C "$(dirname "$(readlink -f "$0")")" rev-parse --show-toplevel)/src && timeout 60 /home/brunner56/agentdecompile-nvme/.venv/bin/python - <<'EOF'
import json
from agentdecompile_recovery.corpus.external_validation import normalize_report
from agentdecompile_recovery.corpus.scoped_facts import FactSheet
raw = json.dumps({"schema_version": 1, "total": 2, "expectations_met": 2, "results": [
    {"name": "FUN_00401000", "matched": True, "expected_match": True, "cases_run": 40, "duration_s": 0.5, "findings": []},
    {"name": "FUN_00401000/edge", "matched": True, "expected_match": True, "cases_run": 8, "duration_s": 0.1, "findings": []}]}).encode()
report = normalize_report(raw, "reagent-benchmark")
print("ReAgent report       : proposal_only", report["proposal_only"], "| recovery_accepted", report["recovery_accepted"])
sheet = FactSheet("JadeEmpire.exe:0x401000")
sheet.ingest_compile({"ok": True, "returncode": 0})
sheet.ingest_reagent(report)
print("after GREEN + compile:", sheet.summary()["scopes"])
sheet.record("fp_nan", "failed", source="nan-propagation-probe", detail={"input": "NaN"})
sheet.record("arithmetic", "passed", source="overflow-probe")
print("after scoped probes  :", {k: v for k, v in sheet.summary()["scopes"].items() if v != "unknown"})
print("fp_nan history kept  :", sheet.history["fp_nan"])
try: sheet.record("everything", "passed", source="x")
except ValueError as e: print("unscoped claim       :", e)
EOF
