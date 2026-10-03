# Static cockpit serving check via isolated app (no port), MyBook source tree.
cd /run/media/brunner56/MyBook/Workspaces/ai-projects/AgentDecompile
AGENTDECOMPILE_COCKPIT_DB=/home/brunner56/agentdecompile-nvme/AIO/databases/kotorxid.sqlite PYTHONPATH=src timeout 120 /home/brunner56/agentdecompile-nvme/.venv/bin/python - <<'EOF' 2>&1 | grep -v Deprecat
import re
from fastapi import FastAPI
from fastapi.testclient import TestClient
from agentdecompile_recovery.corpus.dashboard.cockpit import create_cockpit_router
c = TestClient(FastAPI(routes=create_cockpit_router().routes))
r = c.get("/dashboard/cockpit"); print("page", r.status_code, r.headers.get("content-type"), "CSP" if "content-security-policy" in r.headers else "noCSP", "real" if 'id="ck-canvas"' in r.text else "placeholder")
for src in re.findall(r'(?:src|href)="(/dashboard/cockpit/[^"]+)"', r.text):
    a = c.get(src); print(" asset", src, a.status_code, a.headers.get("content-type"), len(a.content))
print("slash", c.get("/dashboard/cockpit/").status_code, "missing", c.get("/dashboard/cockpit/nope.js").status_code, "traversal", c.get("/dashboard/cockpit/../cockpit.py").status_code, c.get("/dashboard/cockpit/%2e%2e/cockpit.py").status_code)
js = c.get("/dashboard/cockpit/cockpit.js").text
ids_js = set(re.findall(r'\$\("([\w-]+)"\)', js)); ids_html = set(re.findall(r'id="([\w-]+)"', r.text))
print("ids used by JS but absent in HTML:", sorted(ids_js - ids_html) or "none")
EOF
