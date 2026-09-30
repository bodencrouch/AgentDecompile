# U9 FP-19: a damaged coverage receipt quarantines only the claims it could affect; unaffected receipts still qualify.
D=/tmp/adplan/verify/u9/fp19; rm -rf $D; mkdir -p $D
cd /home/brunner56/ad-wt/u13-reconcile/src && timeout 60 /home/brunner56/agentdecompile-nvme/.venv/bin/python - <<'EOF'
import json, pathlib
from agentdecompile_recovery.corpus.ingest_recovered import load_coverage_index
D = pathlib.Path("/tmp/adplan/verify/u9/fp19")
ok = lambda f: json.dumps({"function": f, "byteExact": True})
(D / "progA.jsonl").write_text("\n".join([ok("alpha"), ok("beta"), '{"function": "alpha", "byteExact": fal', ok("gamma")]) + "\n")
(D / "progB.jsonl").write_text("\n".join([ok("delta"), ok("epsilon"), "\x00\x13garbage without a name", ok("zeta")]) + "\n")
(D / "progC.jsonl").write_text("\n".join([ok("eta"), ok("theta")]) + "\n")
q = {}; v = load_coverage_index(D, q)
print("qualifying:", sorted(v)); print("quarantined:", {k: (w["line"], w["reason"]) for k, w in sorted(q.items())})
assert ("progA", "alpha") in q and ("progA", "beta") in v and ("progA", "gamma") in v   # named damage: only alpha
assert ("progB", "delta") in q and ("progB", "epsilon") in q and ("progB", "zeta") in v  # unnamed: earlier ones held
assert ("progC", "eta") in v and ("progC", "theta") in v                                 # other ledgers unaffected
(D / "progA.jsonl").write_text((D / "progA.jsonl").read_text() + ok("alpha") + "\n")      # scoped re-verification
q2 = {}; v2 = load_coverage_index(D, q2); print("after re-verifying alpha:", ("progA", "alpha") in v2, ("progA", "alpha") in q2)
EOF
# Real ledgers, read-only: how many claims the live coverage directory would quarantine today.
cd /home/brunner56/ad-wt/u13-reconcile/src && timeout 300 /home/brunner56/agentdecompile-nvme/.venv/bin/python - <<'EOF'
from agentdecompile_recovery.corpus.ingest_recovered import load_coverage_index
d = "/home/brunner56/biodecompwarehouse/kotorxid/data/mizuchi_home/reports/coverage"
q = {}; v = load_coverage_index(d, q)
print("live coverage:", len(v), "qualifying,", len(q), "quarantined", sorted({(w['ledger'].rsplit('/', 1)[-1], w['line']) for w in q.values()})[:5])
EOF
