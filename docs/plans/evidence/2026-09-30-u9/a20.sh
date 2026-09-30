# U9 A20: shuffling proposal arrival changes neither the capped set nor the chosen proposal. Drives the real
# VerifierLoop._candidates (cap, independence policy, penalties, tie-break); only log reads and deadline are stubbed.
cd /home/brunner56/ad-wt/u13-reconcile/src && timeout 120 /home/brunner56/agentdecompile-nvme/.venv/bin/python - <<'EOF'
import itertools, random
from types import SimpleNamespace as NS
from agentdecompile_grid.verify import loop as L
from agentdecompile_grid.worker.records import Proposal
from agentdecompile_grid.verify.policy import PenaltyLedger, RevocationList
ok_status = next(s for s in L.ResultStatus if s.name == "OK") if hasattr(L, "ResultStatus") else None
from agentdecompile_grid.worker.records import ResultStatus
def proposal(i, seq):
    return Proposal(seq=seq, task_id="t1", kind="k", status=ResultStatus.OK, result_ref=f"ref{i:02d}", producer_key=f"prod{i}",
                    producer_lineage=(f"lin{i}",), outputs={}, elapsed_s=1.0, reason="", signer_key=f"prod{i}")
def choose(order):
    props = [proposal(i, seq) for seq, i in enumerate(order)]           # arrival order decides the seq numbers
    L.read_results = lambda *a, **k: props
    L.read_verdicts = lambda *a, **k: []
    L.deadline_for = lambda spec, deadlines: 60.0
    v = object.__new__(L.VerifierLoop)
    v.log = object(); v._served_kinds = lambda: {"k"}; v.slots = []; v.vconfig = L.VerifierConfig()
    v.config = NS(trust_unsigned_records=True, admitted_bases=None, deadlines_s={}); v.lineage_lookup = None; v.keyring = None
    v.identity = NS(key_id="verifier", invite_lineage=("vlin",), capabilities=())
    v.task_lookup = lambda tid: NS(task_id=tid, kind="k", capabilities=(), basis_hash="b", partition_key="p")
    v.revocations = RevocationList(); v.penalties = PenaltyLedger(); v._cooloff = {}; v._verdicts_local = set()
    skips = []; v._skip = skips.append
    out = v._candidates(NS(awaiting_verification=["t1"]), 0.0)
    return out[0].payload.producer_key if out else None, skips.count("over-cap")
orders = [[1, 2, 3, 4, 5], [2, 3, 4, 5, 1], [5, 4, 3, 2, 1], [3, 1, 5, 2, 4]] + [random.Random(s).sample([1, 2, 3, 4, 5], 5) for s in range(6)]
results = {tuple(o): choose(o) for o in orders}
for o, r in results.items(): print("arrival", o, "-> verified first:", r[0], "| over-cap:", r[1])
print("same decision for every arrival order:", len({r for r in results.values()}) == 1)
EOF
