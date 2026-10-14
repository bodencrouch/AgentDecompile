# U9 A16/FP-14 at runtime: the real JobStore queue honours a capped-age reservation; backfill that would delay it
# waits; a task that fits beside it runs. Simulated host capacity; injected executor; temp root and profiles.
R=/tmp/adplan/verify/u9/a16root; rm -rf $R; mkdir -p $R
cd $(git -C "$(dirname "$(readlink -f "$0")")" rev-parse --show-toplevel)/src && AGENT_DECOMPILE_CORPUS_ROOT=$R AGENTDECOMPILE_RESOURCE_PROFILES=$R/profiles.json \
  AGENTDECOMPILE_AGING_INTERVAL_S=0.5 AGENTDECOMPILE_AGING_CAP=2 timeout 120 /home/brunner56/agentdecompile-nvme/.venv/bin/python - <<'EOF'
import threading, time, os, pathlib
from agentdecompile_recovery.corpus.dashboard import resource_admission as ra
from agentdecompile_recovery.corpus.dashboard.actions import jobs
G = 1024**3; R = pathlib.Path(os.environ["AGENT_DECOMPILE_CORPUS_ROOT"])
ra._HOST_CACHE = (time.monotonic() + 3600, ra.HostState(mem_total=31*G, mem_available=14*G))  # fixed simulated host
store = ra.default_profile_store()
store.record("corpus.logical-build", 10*G)     # big: need 13 GiB
store.record("corpus.propagate-source", 3*G)   # small: need 4.25 GiB
store.record("corpus.stages", int(0.1*G))      # tiny: need 0.625 GiB
gates = {}
def executor(argv, cwd, cancel):
    key = next((a for a in argv if a.endswith(".sqlite")), "stages")
    gates.setdefault(key, threading.Event()).wait(30); return 0, "ok"
jobs.STORE.executor = executor
def db(name): p = R / f"{name}.sqlite"; p.write_bytes(b""); return str(p)
def start(action, name=None): return jobs.start_job(action, {"db": db(name)} if name else {}, confirm=True)[0]["job"]["id"]
st = lambda j: jobs.get_job(j).status
f1, f2 = start("corpus.propagate-source", "f1"), start("corpus.propagate-source", "f2"); time.sleep(0.5)
big = start("corpus.logical-build", "big"); time.sleep(1.5)   # queued past its age cap
s = start("corpus.propagate-source", "s"); time.sleep(0.8)
print("reservation held:", {"fillers": [st(f1), st(f2)], "big": st(big), "small": st(s)}, "|", jobs.get_job(s).admission_wait[:70])
assert st(big) == "queued" and st(s) == "queued" and "reservation" in jobs.get_job(s).admission_wait
for k in (db("f1"), db("f2")): gates.setdefault(k, threading.Event()).set()
time.sleep(1.2)
print("fillers done    :", {"big": st(big), "small": st(s)}, "|", jobs.get_job(s).admission_wait[:60])
assert st(big) == "running" and st(s) == "queued"
tiny = start("corpus.stages"); gates.setdefault("stages", threading.Event()).set(); time.sleep(1.0)
print("tiny, small now holds the reservation:", st(tiny), "|", jobs.get_job(tiny).admission_wait[:60])
assert st(tiny) == "queued" and "reservation" in jobs.get_job(tiny).admission_wait   # backfill that would delay the holder waits
ra._HOST_CACHE = (time.monotonic() + 3600, ra.HostState(mem_total=31*G, mem_available=int(18.5*G)))
time.sleep(1.2)
print("more capacity   :", {"small (holder)": st(s), "tiny": st(tiny)})
assert st(s) == "running" and st(tiny) == "ok"                                        # holder first, backfill that fits
for e in gates.values(): e.set()
for k in (db("big"), db("s")): gates.setdefault(k, threading.Event()).set()
time.sleep(1.5); print("drained         :", {"big": st(big), "small": st(s)})
store.record("corpus.remove-binary", 64*G)
print("never-feasible start refusal:", jobs._admission_refusal("corpus.remove-binary")["nextAction"])
EOF
