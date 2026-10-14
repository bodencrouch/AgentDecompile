# U9 A09/FP-05: a writer holding a database's mutation channel does not block status reads or independent work;
# the conflicting writer waits, then runs. Real JobStore admission loop with an injected executor; temp root.
R=/tmp/adplan/verify/u9/fp05root; rm -rf $R; mkdir -p $R
cd $(git -C "$(dirname "$(readlink -f "$0")")" rev-parse --show-toplevel)/src && AGENT_DECOMPILE_CORPUS_ROOT=$R AGENTDECOMPILE_RESOURCE_ADMISSION=off timeout 120 /home/brunner56/agentdecompile-nvme/.venv/bin/python - <<'EOF'
import threading, time, os, pathlib
from agentdecompile_recovery.corpus.dashboard.actions import jobs
R = pathlib.Path(os.environ["AGENT_DECOMPILE_CORPUS_ROOT"]); X, Y = str(R / "x.sqlite"), str(R / "y.sqlite")
for p in (X, Y): pathlib.Path(p).write_bytes(b"")
release = threading.Event()
def executor(argv, cwd, cancel):
    if X in argv and "HOLD" in os.environ.get("PHASE", ""):
        release.wait(20)
    return 0, "ok"
jobs.STORE.executor = executor
os.environ["PHASE"] = "HOLD"
a, _ = jobs.start_job("corpus.logical-build", {"db": X}, confirm=True); time.sleep(0.5)
os.environ["PHASE"] = ""
b, _ = jobs.start_job("corpus.logical-build", {"db": X}, confirm=True)
c, _ = jobs.start_job("corpus.stages", {}, confirm=True)
d, _ = jobs.start_job("corpus.logical-build", {"db": Y}, confirm=True)
time.sleep(2)
st = lambda r: jobs.get_job(r["job"]["id"]).status
print("while A holds X:", {"A writer X": st(a), "B writer X": st(b), "C status read": st(c), "D writer Y": st(d)})
assert st(a) == "running" and st(b) == "queued" and st(c) == "ok" and st(d) == "ok"
release.set(); time.sleep(2)
print("after A ends   :", {"A": st(a), "B": st(b)})
assert st(b) == "ok"
EOF
