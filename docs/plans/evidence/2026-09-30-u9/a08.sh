# U9 A08: restart the coordinator during a retry wait. The persisted action record keeps the
# consumed budget, the next eligibility time and the dispatch id; the resumed run waits out the
# rest of the backoff instead of launching at once, and a live owner still blocks a second launch.
cd $(git -C "$(dirname "$(readlink -f "$0")")" rev-parse --show-toplevel)/src && timeout 60 /home/brunner56/agentdecompile-nvme/.venv/bin/python - <<'EOF'
import json, inspect
from agentdecompile_recovery.corpus.dashboard import preparation
from agentdecompile_recovery.corpus.dashboard.workflow import transient_failure
from agentdecompile_recovery.corpus.dashboard.retry_policy import decide_retry, remaining_backoff
t0 = 1_000_000.0
failed = {"dispatchId": "d-1", "jobId": "job-1", "status": "failed", "attempts": 1,
          "result": {"ok": False, "error": "HTTP 503 Service Unavailable: database is locked"},
          "nextEligibleAt": t0 + 4, "retryDelay": 4}
prior = json.loads(json.dumps(failed))            # what a restarted coordinator reads back
d = decide_retry(prior, transient=transient_failure(prior["result"]))
print("after restart     :", d["nextAction"], "spent", d["attemptsSpent"], "remaining", d["attemptsRemaining"])
print("wait at t0+1      :", remaining_backoff(prior, t0 + 1))
print("wait at t0+5      :", remaining_backoff(prior, t0 + 5))
print("clock rolled back :", remaining_backoff(prior, t0 - 3600), "(capped at the recorded delay)")
print("dispatch id kept  :", prior["dispatchId"])
running = {**prior, "status": "running"}
print("live owner        :", decide_retry(running, owner_available=True)["nextAction"])
print("owner unknown     :", decide_retry(running, owner_available=False)["nextAction"])
src = inspect.getsource(preparation)
print("persists wait     :", "nextEligibleAt=time.time() + delay" in src, "| honours on resume:", "remaining_backoff(prior, time.time())" in src)
EOF
