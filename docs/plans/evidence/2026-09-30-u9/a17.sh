# U9 A17: an input change between verification and commit -> 'stale' refusal with the report retained. Real commit().
cd /home/brunner56/ad-wt/u13-reconcile/src && timeout 60 /home/brunner56/agentdecompile-nvme/.venv/bin/python - <<'EOF'
from agentdecompile_recovery.corpus import recipient_acceptance as ra
sha = "a" * 64; dep = ra.identity_dependency(sha, 0x401000)
proposal = {"proposalId": "p1", "producer": "prod", "claimKind": "identity", "candidateSha256": "b" * 64,
            "recipient": {"binarySha256": sha, "address": 0x401000, "variant": "v"}, "rootSets": [[dep]], "policyRevision": "r1"}
verification = {"verifier": "ver", "scope": proposal["recipient"], "outcome": "pass", "reportSha256": "c" * 64}
_, rec = ra.commit((), proposal, verification, lambda deps: {d: 1 for d in deps})
print("stable inputs:", rec["kind"], rec["outcome"])
calls = {"n": 0}
def moving(deps):
    calls["n"] += 1; return {d: calls["n"] for d in deps}   # generation changes between read and recheck
ledger, rec2 = ra.commit((), proposal, verification, moving)
print("input changed during verification:", rec2["kind"], rec2["outcome"], rec2["reasonCodes"], "| report kept:", rec2["reportSha256"] == "c" * 64, "| records:", len(ledger))
EOF
# Policy half of A17 and FP-21 policy activation gate.
cd /home/brunner56/ad-wt/u13-reconcile/src && timeout 60 /home/brunner56/agentdecompile-nvme/.venv/bin/python - <<'EOF'
from agentdecompile_recovery.corpus import recipient_acceptance as ra
sha = "a" * 64; dep = ra.identity_dependency(sha, 0x401000)
proposal = {"proposalId": "p1", "producer": "prod", "claimKind": "identity", "candidateSha256": "b" * 64,
            "recipient": {"binarySha256": sha, "address": 0x401000, "variant": "v"}, "rootSets": [[dep]], "policyRevision": "r1"}
verification = {"verifier": "ver", "scope": proposal["recipient"], "outcome": "pass", "reportSha256": "c" * 64}
stable = lambda deps: {d: 1 for d in deps}
print("policy unchanged:", ra.commit((), proposal, verification, stable, active_policy=lambda: "r1")[1]["outcome"])
r = ra.commit((), proposal, verification, stable, active_policy=lambda: "r2")[1]
print("policy changed during verification:", r["kind"], r["outcome"], r["reasonCodes"], "| report kept:", r["reportSha256"] == "c" * 64)
false_label = {"proposalId": "false-label", "labelMatches": False}; good = {"proposalId": "good", "labelMatches": True}
bad_policy = lambda s: True; sound_policy = lambda s: s["labelMatches"]
print("bad policy activation:", ra.policy_activation_check(bad_policy, [false_label], [good]))
print("sound policy activation:", ra.policy_activation_check(sound_policy, [false_label], [good]))
EOF
