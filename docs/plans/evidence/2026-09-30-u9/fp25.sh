# U9 FP-25: restore the job store from a backup, then receive late receipts and a user continuation.
# Newer receipts are merged once, stale/duplicate ones ignored, version gaps recorded as lost windows,
# attempt counts never go down, an active job with no word stays unknown and is not relaunched, and
# independently reconciled work proceeds. Wake cursors replay events that landed during a crash window
# and a redelivered event dispatches nothing twice.
cd $(git -C "$(dirname "$(readlink -f "$0")")" rev-parse --show-toplevel)/src && timeout 60 /home/brunner56/agentdecompile-nvme/.venv/bin/python - <<'EOF'
import tempfile
from pathlib import Path
from agentdecompile_recovery.corpus.dashboard.restore_reconcile import WakeLog, Waits, ActionOnce, reconcile_after_restore
from agentdecompile_recovery.corpus.dashboard.retry_policy import decide_retry
backup = {  # receipts as they were in the backup
  "a": {"id": "a", "status": "running", "receiptVersion": 3, "executionAttempt": 2},
  "b": {"id": "b", "status": "running", "receiptVersion": 5, "executionAttempt": 1},
  "c": {"id": "c", "status": "failed",  "receiptVersion": 4, "executionAttempt": 3},
  "d": {"id": "d", "status": "running", "receiptVersion": 2, "executionAttempt": 1},
}
late = [  # arrive after the restore, some twice, some older than the backup
  {"id": "a", "status": "ok", "receiptVersion": 4, "executionAttempt": 2},
  {"id": "a", "status": "ok", "receiptVersion": 4, "executionAttempt": 2},
  {"id": "c", "status": "failed", "receiptVersion": 2, "executionAttempt": 1},
  {"id": "d", "status": "ok", "receiptVersion": 6, "executionAttempt": 1},
  {"id": "e", "status": "ok", "receiptVersion": 3, "executionAttempt": 1},
]
merged, rep = reconcile_after_restore(backup, late)
print("accepted            :", [(r["id"], r["receiptVersion"]) for r in rep["accepted"]])
print("ignored             :", [(r["id"], r["receiptVersion"]) for r in rep["ignoredStaleOrDuplicate"]])
print("lost windows        :", [(r["id"], r["missingVersions"]) for r in rep["lostEventWindows"]])
print("c attempts kept     :", merged["c"]["executionAttempt"], "(backup 3, late receipt said 1)")
print("unknown outcome     :", rep["unknownOutcome"], "| b status", merged["b"]["status"])
prior_b = {"status": "failed", "attempts": 1, "result": {"unknownOutcome": merged["b"]["unknownOutcome"]}}
print("user continues b    :", decide_retry(prior_b)["nextAction"])
print("reconciled a        :", decide_retry({"status": "ok", "attempts": 1, "result": {"ok": True}})["nextAction"])
_, rep2 = reconcile_after_restore(backup, late, live_owner=lambda r: r["id"] == "b")
print("b with live owner   :", rep2["liveOwnerKept"], "| unknown:", rep2["unknownOutcome"])
# wake cursors across a crash window
w = Path(tempfile.mkdtemp()); log = WakeLog(w / "log"); waits = Waits(w / "waits", log); once = ActionOnce(w / "once")
waits.register("wait:match-pair", {"needs": "resource_released:ghidra-project"})
log.append("release:ghidra-project:gen7", "resource_released", {"resource": "ghidra-project"})  # lands before the sleeper subscribes
w2 = Waits(w / "waits", WakeLog(w / "log"))                                                    # coordinator restarted
r = w2.check("wait:match-pair", lambda ev: any(e["kind"] == "resource_released" for e in ev))
print("event in crash gap  :", "wake" if r["wake"] else "sleep", "| replayed", r["replayed"])
seq, new = log.append("release:ghidra-project:gen7", "resource_released", {"resource": "ghidra-project"})
print("redelivered event   : new =", new, "| sequence", seq)
print("dispatch claims     :", once.claim("dispatch:match-pair:gen7"), once.claim("dispatch:match-pair:gen7"))
print("next check          :", w2.check("wait:match-pair", lambda ev: bool(ev)))
EOF
