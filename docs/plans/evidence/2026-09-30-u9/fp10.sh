# U9 FP-10: 100 tasks waiting on a crashed provider share one recovery probe; healing is bounded; a probe that raises
# frees its slot; recovery closes the breaker. Real _mcp_executor and ProviderBreaker; provider calls stubbed.
cd "$(git -C "$(dirname "$(readlink -f "$0")")" rev-parse --show-toplevel)/src" && timeout 120 /home/brunner56/agentdecompile-nvme/.venv/bin/python - <<'EOF'
import threading, time, json
from agentdecompile_recovery.corpus.dashboard.actions import jobs, catalog
from agentdecompile_recovery.corpus.dashboard.provider_breaker import breaker_for
from agentdecompile_recovery.corpus.dashboard.workflow import transient_failure
action = next(a for a in catalog.list_actions() if a.backend == "mcp-cli")
state = {"up": False, "calls": 0, "raise": False}
def provider(action, params, cancel, **kw):
    state["calls"] += 1
    if state["raise"]: raise RuntimeError("probe blew up before observing the provider")
    return (0, "ok") if state["up"] else (1, "ConnectionRefusedError: [Errno 111] Connection refused")
jobs._mcp_executor_in_context = provider
b = breaker_for("mcp"); b.cooldown_s, b.max_probes = 0.3, 3
print("first call sees the crash:", jobs._mcp_executor(action, {}, threading.Event())[0], b.status()["state"])
out = []; threads = [threading.Thread(target=lambda: out.append(jobs._mcp_executor(action, {}, threading.Event()))) for _ in range(100)]
before = state["calls"]; [t.start() for t in threads]; [t.join() for t in threads]
refused = [json.loads(l) for c, l in out if l.startswith("{")]
print("100 waiting tasks -> provider calls:", state["calls"] - before, "| told to wait:", len(refused),
      "| retryable:", all(transient_failure(r) for r in refused))
time.sleep(0.35); state["raise"] = True
try: jobs._mcp_executor(action, {}, threading.Event())
except RuntimeError: pass
print("probe raised -> state:", b.status()["state"], "(slot freed, not counted:", b.status()["failedProbes"], "failed probes)")
state["raise"] = False
for _ in range(3): time.sleep(0.35); jobs._mcp_executor(action, {}, threading.Event())
print("after 3 failed probes:", b.status()["state"], "|", json.loads(jobs._mcp_executor(action, {}, threading.Event())[1])["error"][:60])
b.reset(); state["up"] = True
print("operator reset, provider back:", jobs._mcp_executor(action, {}, threading.Event())[0], b.status()["state"])
EOF
