# U9 FP-27: an entitlement denial before start is external-action-required, not a failure or a retry; a restored
# entitlement makes it eligible again; real failures keep their old handling. Real classifier + decide_retry.
cd /home/brunner56/ad-wt/u13-reconcile/src && timeout 60 /home/brunner56/agentdecompile-nvme/.venv/bin/python - <<'EOF'
from agentdecompile_recovery.corpus.dashboard.workflow import external_action_required, transient_failure
from agentdecompile_recovery.corpus.dashboard.retry_policy import decide_retry
denied = {"status": "failed", "attempts": 1, "result": {"error": "CI job not started: organization is not entitled to hosted runners (HTTP 402 Payment Required)"}}
compile_fail = {"status": "failed", "attempts": 1, "result": {"error": "error C2143: syntax error: missing ';'"}}
d = decide_retry(denied, transient=transient_failure(denied["result"]), external_action=external_action_required(denied["result"]))
print("entitlement denial :", d["nextAction"], "| wake:", d["wakeCondition"])
r = decide_retry(denied, external_action=True, external_restored=True); print("entitlement restored:", r["nextAction"])
c = decide_retry(compile_fail, transient=transient_failure(compile_fail["result"]), external_action=external_action_required(compile_fail["result"]))
print("real compile failure:", c["nextAction"], "| classified external:", external_action_required(compile_fail["result"]))
EOF
