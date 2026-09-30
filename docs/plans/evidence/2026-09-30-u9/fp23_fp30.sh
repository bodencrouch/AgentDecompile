# U9 FP-23 (detector_unknown quarantines only its decision path; alternates continue) and FP-30 (bounded canary rolls
# back on threshold or missing metrics; observations kept; acceptance untouched). Real control_plane module.
cd "$(git -C "$(dirname "$(readlink -f "$0")")" rev-parse --show-toplevel)/src" && timeout 60 /home/brunner56/agentdecompile-nvme/.venv/bin/python - <<'EOF'
from agentdecompile_recovery.corpus.dashboard.control_plane import DetectorSpec, classify, DecisionGate, RoutingCanary
now = 1000.0
crash = DetectorSpec("crash-detector", 2, 30.0); alt = DetectorSpec("log-crash-detector", 1, 30.0); mem = DetectorSpec("memory", 1, 30.0)
cases = {"malformed": "garbage", "timeout": {"timed_out": True}, "old schema": {"schema_version": 1, "observed_at": now, "outcome": "healthy"},
         "stale": {"schema_version": 2, "observed_at": now - 99, "outcome": "healthy"}, "odd outcome": {"schema_version": 2, "observed_at": now, "outcome": "probably fine"},
         "good": {"schema_version": 2, "observed_at": now, "outcome": "failed"}}
for k, v in cases.items(): print(f"{k:12s} ->", classify(crash, v, now=now)["detector_health"], classify(crash, v, now=now)["reason"])
gate = DecisionGate(requires={"launch": ("crash-detector",), "compile": ("memory",)}, alternates={"crash-detector": ("log-crash-detector",)})
gate.observe(classify(crash, "garbage", now=now)); gate.observe(classify(mem, {"schema_version": 1, "observed_at": now, "outcome": "healthy"}, now=now))
print("launch, crash detector unknown:", gate.decide("launch")["state"], "| unrelated compile:", gate.decide("compile")["allowed"])
gate.observe(classify(alt, {"schema_version": 1, "observed_at": now, "outcome": "healthy"}, now=now))
print("launch with qualified alternate:", gate.decide("launch"))
c = RoutingCanary("route-A", "route-B", max_attempts=10, max_duration_s=100, max_cost=5.0, max_error_rate=0.3, started_at=now)
for i in range(3): c.observe(ok=True, cost=1.0, now=now + i)
print("canary within limits:", c.state, c.route()); c.observe(ok=True, cost=3.0, now=now + 4)
print("cost exceeded:", c.state, "->", c.route(), "|", c.closed_reason, "| observations kept:", len(c.observations))
d = RoutingCanary("route-A", "route-B", 10, 100, 50, 0.3, started_at=now); d.observe(ok=True, cost=1, now=now); d.observe(ok=None, cost=None, now=now + 1)
print("metrics lost:", d.state, "->", d.route(), "|", d.closed_reason)
e = RoutingCanary("route-A", "route-B", 3, 100, 50, 0.5, started_at=now); [e.observe(ok=True, cost=1, now=now + i) for i in range(3)]
print("budget reached cleanly:", e.state, "->", e.route(), "|", e.closed_reason)
EOF
