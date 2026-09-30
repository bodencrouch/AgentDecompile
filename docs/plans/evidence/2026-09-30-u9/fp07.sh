# U9 FP-07: a report from an expired generation is rejected even with matching content. Real consume_report + Ledger.
A=/tmp/adplan/verify/u9/fp07area; rm -rf $A; mkdir -p $A
cd $(git -C "$(dirname "$(readlink -f "$0")")" rev-parse --show-toplevel)/src && timeout 60 /home/brunner56/agentdecompile-nvme/.venv/bin/python - <<'EOF'
import json
from agentdecompile_recovery.corpus.cross_place_checkpoint import Ledger, consume_report
L = Ledger("/tmp/adplan/verify/u9/fp07area"); rep = L.root / "reports/worker-results.jsonl"; rep.parent.mkdir(parents=True, exist_ok=True)
def write(token): rep.write_text(json.dumps({"schema": "cross-place-result/v1", "token": token, "area": str(L.area), "kind": "worker"}) + "\n")
write("old-generation")
for label, summary_token, current in (("old worker's own summary, current generation new", "old-generation", "new-generation"),
                                      ("forged current token over the old file", "new-generation", "new-generation")):
    try: consume_report(L, {"completeResults": {"path": str(rep), "token": summary_token}}, current); print(label, "-> ACCEPTED (bad)")
    except (ValueError, KeyError) as e: print(label, "-> rejected:", e)
print("old file retained for inspection:", rep.is_file())
EOF
