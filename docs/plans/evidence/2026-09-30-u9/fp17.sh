# U9 FP-17 pieces: find a launch's owner by dispatch id, prove absence from a readable job store,
# and resume under the same reservation without a second charge. Temp live root only.
R=/tmp/adplan/verify/u9/fp17root; rm -rf $R; mkdir -p $R/workbench-jobs
cd /home/brunner56/ad-wt/u9-admission/src && AGENT_DECOMPILE_CORPUS_ROOT=$R timeout 120 /home/brunner56/agentdecompile-nvme/.venv/bin/python - <<'EOF'
import json, os, pathlib
from agentdecompile_recovery.corpus.dashboard import preparation as P, admission_budget as B
R = pathlib.Path(os.environ["AGENT_DECOMPILE_CORPUS_ROOT"])
print("absence provable with job store:", P._dispatch_absence_provable())
print("unknown dispatch -> owner:", P._job_for_dispatch("d" * 32))
# A launch that did start before the crash left a persisted job receipt carrying its dispatch id.
(R / "workbench-jobs" / "abc123def456.json").write_text(json.dumps({"id": "abc123def456", "actionId": "corpus.report", "status": "running", "params": {"_dispatchId": "e" * 32}}))
import agentdecompile_recovery.corpus.dashboard.actions.job_history as H; H._RECORDS_CACHE = None
print("started dispatch -> owner:", P._job_for_dispatch("e" * 32))
# Budget: the intent charged once; resuming the same dispatch id is idempotent.
row = {"id": "run1"}; B.initialize(row, 5)
print("first reserve:", B.reserve(row, "e" * 32, "act1", "corpus.report")["nextAction"], "consumed", row["objectiveBudget"]["consumed"])
print("resume same dispatch:", B.reserve(row, "e" * 32, "act1", "corpus.report")["nextAction"], "consumed", row["objectiveBudget"]["consumed"])
try: B.reserve(row, "e" * 32, "other-action", "x"); print("identity mismatch accepted (bad)")
except ValueError as e: print("same dispatch id, different action refused:", e)
EOF
echo "--- without a job store the absence claim is withheld:"
cd /home/brunner56/ad-wt/u9-admission/src && env -u AGENT_DECOMPILE_CORPUS_ROOT -u AGENT_DECOMPILE_CORPUS_WORK_DIR timeout 120 /home/brunner56/agentdecompile-nvme/.venv/bin/python -c "
from agentdecompile_recovery.corpus.dashboard import common, preparation as P
common.ROOT = None
print('absence provable:', P._dispatch_absence_provable())"
