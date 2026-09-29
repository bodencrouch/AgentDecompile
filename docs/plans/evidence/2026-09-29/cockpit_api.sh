# Cockpit API check: isolated FastAPI app, real corpus DB read-only, MyBook source tree.
DB=/home/brunner56/agentdecompile-nvme/AIO/databases/kotorxid.sqlite
cd /run/media/brunner56/MyBook/Workspaces/ai-projects/AgentDecompile
AGENTDECOMPILE_COCKPIT_DB=$DB PYTHONPATH=src timeout 300 /home/brunner56/agentdecompile-nvme/.venv/bin/python - <<'EOF'
import time, json
from fastapi import FastAPI
from fastapi.testclient import TestClient
from agentdecompile_recovery.corpus.dashboard.cockpit import create_cockpit_router
app = FastAPI(); app.include_router(create_cockpit_router()); c = TestClient(app)
t=time.time(); r=c.get("/dashboard/api/cockpit/summary"); s=r.json(); t1=time.time()-t
print("summary", r.status_code, s.get("ok"), f"{t1:.2f}s", s.get("error"))
print(" totals", s.get("totals")); print(" programs", [(p["id"],p["label"],p["n"],len(p["builds"])) for p in s.get("programs",[])][:8])
print(" tiers", s.get("tiers")); print(" methods", (s.get("match_methods") or [])[:6]); print(" activity", len(s.get("activity") or []))
t=time.time(); r2=c.get("/dashboard/api/cockpit/summary"); print(" cached", f"{time.time()-t:.3f}s")
if s.get("programs"):
    pid=s["programs"][0]["id"]
    t=time.time(); r=c.get(f"/dashboard/api/cockpit/program/{pid}/cells"); cj=r.json(); print("cells", r.status_code, cj.get("ok"), f"{time.time()-t:.2f}s", "n",cj.get("n"), "len state",len(cj.get("state","")), "edges",len(cj.get("edges",[])), "names",len(cj.get("names",{})), cj.get("error"))
    from collections import Counter; print(" state mix", Counter(cj.get("state","")), "tier mix", Counter(cj.get("tier","")))
    idx = next((int(k) for k in cj.get("names",{})), 0)
    r=c.get("/dashboard/api/cockpit/function", params={"program_id":pid,"index":idx}); f=r.json()
    print("function", r.status_code, f.get("ok"), f.get("name"), f.get("tier_name"), "instances",len(f.get("instances",[])), "absent",len(f.get("absent",[])), "callers",len(f.get("callers",[])), "callees",len(f.get("callees",[])), "recovered",len(f.get("recovered",[])), f.get("error"))
    print("bad program", c.get("/dashboard/api/cockpit/program/nope/cells").json())
    print("bad addr", c.get("/dashboard/api/cockpit/function", params={"binary_id":1,"addr":"zz"}).json())
print("page", c.get("/dashboard/cockpit").status_code, c.get("/dashboard/cockpit").text[:90])
print("traversal", c.get("/dashboard/cockpit/..%2F..%2Fcockpit.py").status_code)
EOF
