# U9 A14: a writer whose process never reached a terminal state (lease expired, owner possibly alive) quarantines its
# resource: the next writer on it waits for clearance, a disjoint writer proceeds. Real JobStore; injected executor.
R=/tmp/adplan/verify/u9/a14root; rm -rf $R; mkdir -p $R
cd "$(git -C "$(dirname "$(readlink -f "$0")")" rev-parse --show-toplevel)/src" && AGENT_DECOMPILE_CORPUS_ROOT=$R AGENTDECOMPILE_RESOURCE_ADMISSION=off timeout 120 /home/brunner56/agentdecompile-nvme/.venv/bin/python - <<'EOF'
import time, os, pathlib
from agentdecompile_recovery.corpus.dashboard.actions import jobs
R = pathlib.Path(os.environ["AGENT_DECOMPILE_CORPUS_ROOT"]); X, Y = str(R / "x.sqlite"), str(R / "y.sqlite")
for p in (X, Y): pathlib.Path(p).write_bytes(b"")
first = {"done": False}
def executor(argv, cwd, cancel):
    if X in argv and not first["done"]:
        first["done"] = True
        return 124, "[process did not reach a terminal state; ownership remains unresolved]\n"
    return 0, "ok"
jobs.STORE.executor = executor
a = jobs.start_job("corpus.logical-build", {"db": X}, confirm=True)[0]["job"]["id"]; time.sleep(1.0)
b = jobs.start_job("corpus.logical-build", {"db": X}, confirm=True)[0]["job"]["id"]
c = jobs.start_job("corpus.logical-build", {"db": Y}, confirm=True)[0]["job"]["id"]; time.sleep(1.5)
g = jobs.get_job
print("unresolved writer A:", g(a).status, "| disposition:", g(a).resource_disposition)
print("next writer on X   :", g(b).status, "| disjoint writer on Y:", g(c).status)
EOF
