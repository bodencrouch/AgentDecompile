# U9 FP-18: sole job-event store unavailable -> unsafe dispatch refused; failed receipts retried, never dropped;
# acceptance resumes only after the backlog flushes. Temp live root; no real job is launched.
R=/tmp/adplan/verify/u9/fp18root; chmod -R u+w $R 2>/dev/null; rm -rf $R; mkdir -p $R
cd /home/brunner56/ad-wt/u13-reconcile/src && AGENT_DECOMPILE_CORPUS_ROOT=$R AGENTDECOMPILE_RESOURCE_ADMISSION=off timeout 120 /home/brunner56/agentdecompile-nvme/.venv/bin/python - <<'EOF'
import os, time, pathlib
from agentdecompile_recovery.corpus.dashboard.actions import jobs, catalog
R = pathlib.Path(os.environ["AGENT_DECOMPILE_CORPUS_ROOT"]); store_dir = R / "workbench-jobs"
print("healthy store:", jobs.STORE.event_store_health())
mut = next(a for a in catalog.list_actions() if a.mutating and not any(f.required for f in a.fields) and a.backend == "reconstruct-cli")
ro = next(a for a in catalog.list_actions() if not (a.mutating or a.identity_scope or a.long_running) and a.backend == "corpus-cli")
store_dir.mkdir(exist_ok=True); os.chmod(store_dir, 0o500)
print("read-only store:", jobs.STORE.event_store_health()["reason"])
body, code = jobs.start_job(mut.id, {}, confirm=True)
print(f"mutating {mut.id}:", code, body.get("wakeCondition"), "|", body.get("error", "")[:70])
print(f"action {ro.id} (catalog: not mutating, identity-scoped or long-running) is not gated:", not (ro.mutating or ro.identity_scope or ro.long_running))
# A failed background flush keeps the receipt and blocks unsafe acceptance until it lands.
with jobs.STORE._persist_lock:
    jobs.STORE._receipt_versions["feedfacecafe"] = 1
    jobs.STORE._persist_pending["feedfacecafe"] = {"id": "feedfacecafe", "receiptVersion": 1, "status": "running"}
jobs.STORE._persist_wake.set(); time.sleep(0.5)
print("after failed flush:", jobs.STORE.event_store_health()["reason"][:60], "| still queued:", "feedfacecafe" in jobs.STORE._persist_pending)
os.chmod(store_dir, 0o700); time.sleep(3)
print("after recovery:", jobs.STORE.event_store_health(), "| receipt on disk:", (store_dir / "feedfacecafe.json").is_file())
EOF
