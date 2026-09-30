# U9 A12: disconnect after a non-idempotent action. The intent is durable before sending; after the
# disconnect the observer either reconciles it or it becomes outcome_unknown, and no second send of
# that action happens until it is reconciled. Idempotent reads and other actions are unaffected.
cd $(git -C "$(dirname "$(readlink -f "$0")")" rev-parse --show-toplevel)/src && timeout 60 /home/brunner56/agentdecompile-nvme/.venv/bin/python - <<'EOF'
import tempfile
from agentdecompile_recovery.corpus.command_ledger import CommandLedger, NON_IDEMPOTENT, IDEMPOTENT
root = tempfile.mkdtemp()
L = CommandLedger(root)
print("send give_item #1 :", L.begin("c1", "give_item", NON_IDEMPOTENT)["send"])
# connection drops; observer cannot tell
r = CommandLedger(root).after_disconnect("c1", lambda cid: None)       # a restarted coordinator
print("after disconnect  :", r["state"], "|", r["nextAction"])
b = L.begin("c2", "give_item", NON_IDEMPOTENT)
print("retry give_item   :", b["send"], "| blocked by", b["blockedBy"])
print("idempotent read   :", L.begin("c3", "read_state", IDEMPOTENT)["send"])
print("other action      :", L.begin("c4", "open_door", NON_IDEMPOTENT)["send"])
print("reused id         :", L.begin("c1", "give_item", NON_IDEMPOTENT)["send"])
L.after_disconnect("c4", lambda cid: (_ for _ in ()).throw(OSError("observer down")))
print("observer failure  :", L.get("c4")["state"])
L.reconcile("c1", "not_applied", by="operator-inspection")
print("after reconcile   :", L.begin("c5", "give_item", NON_IDEMPOTENT)["send"])
L.begin("c6", "warp", NON_IDEMPOTENT)
print("observer applied  :", L.after_disconnect("c6", lambda cid: "applied")["state"],
      "| next warp:", L.begin("c7", "warp", NON_IDEMPOTENT)["send"])
EOF
