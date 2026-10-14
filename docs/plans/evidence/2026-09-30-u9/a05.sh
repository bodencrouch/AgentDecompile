# U9 A05/FP-08: a hung receipt device leaves the coordinator responsive with exactly one outstanding probe.
R=/tmp/adplan/verify/u9/a05root; rm -rf $R; mkdir -p $R
cd $(git -C "$(dirname "$(readlink -f "$0")")" rev-parse --show-toplevel)/src && AGENT_DECOMPILE_CORPUS_ROOT=$R timeout 60 /home/brunner56/agentdecompile-nvme/.venv/bin/python - <<'EOF'
import pathlib, threading, time
from agentdecompile_recovery.corpus.dashboard.actions import jobs
hang = threading.Event(); real = pathlib.Path.write_bytes
def hung_write(self, data):
    if self.name.startswith(".health."): hang.wait(30)   # the device stops answering
    return real(self, data)
pathlib.Path.write_bytes = hung_write
t = time.monotonic(); r1 = jobs.STORE.event_store_health(); d1 = time.monotonic() - t
t = time.monotonic(); rs = [jobs.STORE.event_store_health() for _ in range(10)]; d2 = time.monotonic() - t
probes = sum(1 for th in threading.enumerate() if th.name == "job-store-probe")
print(f"first check: {d1:.1f}s -> {r1['reason']}")
print(f"10 more checks: {d2:.2f}s total -> {rs[-1]['reason'][:50]} | outstanding probe threads: {probes}")
assert d1 < 3 and d2 < 0.5 and probes == 1
hang.set(); time.sleep(0.3)
print("device recovers:", jobs.STORE.event_store_health())
EOF
