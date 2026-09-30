# U9 FP-12: long units' deadlines follow distinct completed checkpoints, never PID liveness or chatter; hard cap holds.
cd $(git -C "$(dirname "$(readlink -f "$0")")" rev-parse --show-toplevel)/src && timeout 120 /home/brunner56/agentdecompile-nvme/.venv/bin/python - <<'EOF'
import sys, threading, pathlib, time, os
from agentdecompile_recovery.corpus.dashboard.actions import jobs
def run(code, **kw):
    t = time.monotonic()
    rc, log = jobs._default_executor([sys.executable, "-u", "-c", code], pathlib.Path("/tmp"), threading.Event(), timeout_seconds=2, **kw)
    marks = [l for l in log.splitlines() if l.startswith("[timed out")]; return rc, round(time.monotonic() - t, 1), (marks or (log.strip().splitlines() or [""])[-1:])[0][:120]
advancing = "import json,time\nfor i in range(6):\n    print(json.dumps({'event':'unit-progress','completed':i+1,'total':6}),flush=True); time.sleep(1)\nprint('finished')"
stuck = "import json,time\nfor i in range(8):\n    print(json.dumps({'event':'unit-progress','completed':1,'total':6}),flush=True); print('still alive',flush=True); time.sleep(1)"
print("advancing, checkpointed :", run(advancing, checkpointed=True))
print("repeating, checkpointed :", run(stuck, checkpointed=True))
print("advancing, plain 2 s    :", run(advancing))
os.environ["AGENT_DECOMPILE_JOB_MAX_SECONDS"] = "3"
print("advancing, 3 s hard cap :", run(advancing, checkpointed=True))
EOF
