# U9 A15/A16/FP-13/FP-14 scenarios against resource_admission (pure decisions + ledger + live probe).
cd $(git -C "$(dirname "$(readlink -f "$0")")" rev-parse --show-toplevel)/src && rm -rf /tmp/adplan/verify/u9/ledger && /home/brunner56/agentdecompile-nvme/.venv/bin/python - <<'EOF'
from agentdecompile_recovery.corpus.dashboard.resource_admission import *
G = 1024**3; P = AdmissionPolicy(class_concurrency={"ghidra": 1})
# A15/FP-13 case 1: near-full swap, qualified small task -> admitted on the complete basis.
h1 = HostState(mem_total=31*G, mem_available=6*G, swap_total=42*G, swap_free=int(0.01*G), pressure_full_avg10=0.1, pressure_full_avg60=0.1)
d1 = decide(ResourceProfile(peak_bytes=1*G), h1, task_class="decompile", policy=P)
print("A15.1 near-full swap, small qualified:", d1.outcome, "|", d1.reason, "| swap role", d1.basis["swap_role"]); assert d1.outcome == "admit"
# A15/FP-13 case 2: spare swap, overloaded class -> refused despite swap capacity (three overload forms).
h2 = HostState(mem_total=31*G, mem_available=20*G, swap_total=42*G, swap_free=40*G)
for label, kw in [("class at concurrency limit", dict(running_in_class=1)),]:
    d = decide(ResourceProfile(peak_bytes=2*G), h2, task_class="ghidra", policy=P, **kw); print("A15.2", label, ":", d.outcome, "|", d.reason); assert d.outcome == "refuse"
d = decide(ResourceProfile(peak_bytes=2*G), HostState(**{**h2.__dict__, "recent_limit_events": 2}), task_class="x", policy=P); print("A15.2 limit events:", d.outcome, "|", d.reason); assert d.outcome == "refuse"
d = decide(ResourceProfile(peak_bytes=30*G), h2, task_class="x", policy=P); print("A15.2 need > RAM, swap spare:", d.outcome, "|", d.reason); assert d.outcome == "refuse"
d = decide(ResourceProfile(peak_bytes=1*G), HostState(**{**h2.__dict__, "pressure_full_avg10": 7, "pressure_full_avg60": 2}), task_class="x", policy=P); print("A15.2 rising pressure:", d.outcome); assert d.outcome == "refuse"
print("unknown profile:", decide(ResourceProfile(peak_bytes=None), h2, task_class="x").outcome)
print("enforcement missing:", decide(ResourceProfile(peak_bytes=G, enforcement_required=True), h2, task_class="x").outcome)
# A16/FP-14: large capped-age task among small high-priority work.
now = 100_000.0; Q = AdmissionPolicy(aging_interval_s=60, aging_cap=5)
big = Task("big", "compile", ResourceProfile(peak_bytes=10*G), capability_priority=0, ready_since=now-3600)
smalls = [Task(f"s{i}", "compile", ResourceProfile(peak_bytes=3*G), capability_priority=9, ready_since=now-30) for i in range(4)]
tight = HostState(mem_total=31*G, mem_available=14*G)  # big needs 13 GiB (10 * 1.25 + 0.5)
p = plan([*smalls, big], tight, now, policy=Q)
print("A16 ordinary rank without aging:", [t.task_id for t in rank([*smalls, big], now-3600+1, Q)][:2])
print("A16 plan:", "dispatch", p.dispatch, "reservation", p.reservation, "refused", {k: v[:40] for k, v in p.refused.items()})
assert p.dispatch[0] == "big", "capped-age reservation must win ahead of ordinary priority"
roomy_wait = HostState(mem_total=31*G, mem_available=int(13.5*G))  # big (need 13 GiB) fits, one small would not also fit
p2 = plan([*smalls, big], HostState(mem_total=31*G, mem_available=9*G), now, policy=Q)
print("A16 big cannot fit yet:", "dispatch", p2.dispatch, "reservation", p2.reservation, "backfill_blocked", p2.backfill_blocked)
assert p2.reservation == "big" and not p2.dispatch, "backfill must not consume the reservation's capacity"
p3 = plan([*smalls, Task("tiny", "compile", ResourceProfile(peak_bytes=int(0.2*G)), 9, now-5), big], HostState(mem_total=31*G, mem_available=int(14.5*G)), now, policy=Q)
print("A16 safe backfill beyond reservation:", p3.dispatch); assert "big" in p3.dispatch
# Urgent override: recorded, visible, age not reset.
L = AgingLedger("/tmp/adplan/verify/u9/ledger/aging.json"); L.mark_ready("big", now-3600)
L.record_override(Override("o1", "operator", "policy:urgent-v1", "hotfix build", "big", now+600, "reschedule after o1 expiry"))
p4 = plan([*smalls, big], tight, now, overrides=L.overrides(), policy=Q)
print("A16 override:", "reservation", p4.reservation, "deferred_by", [o["override_id"] for o in p4.deferred_by], "big age credit", aging_credit(big, now, Q))
assert p4.deferred_by and aging_credit(big, now, Q) == Q.aging_cap
# Restart: a fresh ledger object keeps ready_since and override history.
L2 = AgingLedger("/tmp/adplan/verify/u9/ledger/aging.json"); L2.mark_ready("big", now)  # re-marking must not reset age
print("restart: ready_since kept", L2.ready_since("big") == now-3600, "| overrides", len(L2.overrides()))
assert L2.ready_since("big") == now-3600
try: L2.record_override(Override("o2", "", "", "", "big", now, "")); print("override without authority: ACCEPTED (bad)")
except ValueError as e: print("override without authority refused:", e)
live = probe_host(scratch_dir="/tmp")
print("live probe: avail %.1f GiB, swap used %.0f%%, psi full avg10 %.2f, enforcement %s" % (live.mem_available/G, 100*(1-live.swap_free/max(1,live.swap_total)), live.pressure_full_avg10, live.enforcement_available))
print("live decide 1 GiB task:", decide(ResourceProfile(peak_bytes=G), live, task_class="x").outcome)
EOF
