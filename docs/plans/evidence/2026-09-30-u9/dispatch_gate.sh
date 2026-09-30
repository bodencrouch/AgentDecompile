# U9 wiring: real subprocess peak measurement through _default_executor, then the start_job gate.
cd /home/brunner56/ad-wt/u9-admission/src && rm -rf /tmp/adplan/verify/u9/profiles && AGENTDECOMPILE_RESOURCE_PROFILES=/tmp/adplan/verify/u9/profiles/p.json timeout 300 /home/brunner56/agentdecompile-nvme/.venv/bin/python - <<'EOF'
import sys, threading, pathlib, json, os
from agentdecompile_recovery.corpus.dashboard.actions import jobs
from agentdecompile_recovery.corpus.dashboard import resource_admission as ra
peaks = []
code, log = jobs._default_executor([sys.executable, "-c", "import time; b = bytearray(300*1024*1024); b[::4096] = b'x'*len(b[::4096]); time.sleep(2.5); print('done')"],
                                   pathlib.Path("/tmp"), threading.Event(), on_peak=peaks.append, timeout_seconds=60)
print("child exit", code, "| measured peak MiB", round(peaks[0] / 2**20) if peaks else None)
assert code == 0 and peaks and 290 * 2**20 < peaks[0] < 600 * 2**20
jobs._record_peak("demo.small")(peaks[0])
store = ra.default_profile_store(); store.record("demo.huge", 200 * 2**30)
print("stored profiles:", json.load(open(os.environ["AGENTDECOMPILE_RESOURCE_PROFILES"]))["peaks"].keys())
print("gate small:", jobs._admission_refusal("demo.small"))
r = jobs._admission_refusal("demo.huge"); print("gate huge:", r["error"], "| need GiB", round(r["admission"]["needBytes"]/2**30), "| swap role", r["admission"]["basis"]["swap_role"])
print("gate unmeasured:", jobs._admission_refusal("demo.never"))
os.environ["AGENTDECOMPILE_RESOURCE_ADMISSION"] = "off"; print("gate off, huge:", jobs._admission_refusal("demo.huge"))
EOF
