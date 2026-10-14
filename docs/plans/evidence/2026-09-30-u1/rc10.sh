# U1 RC-10 (and the outcome half of D24): every in-scope source function of a pair match ends in one
# explicit outcome (matched/inlined/ambiguous/unsupported/budget_limited/absent); nothing is forced to
# match and nothing claims an exhaustive negative. Part 1 runs the real store matcher on a scratch copy
# of the live store (read-only source; placeholder content hashes on builds 30 and 28 only; the copy
# is deleted). Part 2 drives the outcome rules for inline and budget cases the real pair did not hit.
cd $(git -C "$(dirname "$(readlink -f "$0")")" rev-parse --show-toplevel)/src && timeout 900 /home/brunner56/agentdecompile-nvme/.venv/bin/python - <<'EOF'
import sqlite3, hashlib, os, tempfile
from agentdecompile_recovery.corpus.match_store import match_binaries
from agentdecompile_recovery.corpus.match_outcomes import terminal_outcomes
scratch = tempfile.mktemp(suffix=".sqlite", dir="/tmp")
try:
    src = sqlite3.connect("file:/home/brunner56/biodecompwarehouse/kotorxid/db/kotorxid.sqlite?mode=ro", uri=True)
    dst = sqlite3.connect(scratch); src.backup(dst); src.close()
    for bid in (30, 28):
        dst.execute("update binary set content_sha256=? where id=?", (hashlib.sha256(f"scratch-{bid}".encode()).hexdigest(), bid))
    dst.commit(); dst.row_factory = sqlite3.Row
    r = match_binaries(dst, 30, 28, rounds=3); o = r["outcomes"]
    print("real pair 30->28   :", o["counts"], "| exhaustive", o["exhaustive"])
    print("  one outcome each :", set(o["rows"]) == set(r["src"].funcs), "| matched == mapping:", o["counts"]["matched"] == len(r["mapping"]))
    r = match_binaries(dst, 30, 28, rounds=3, restrict_src={a for a in list(r["src"].funcs)[:50]})
    print("  restricted scope :", len(r["outcomes"]["rows"]), "rows")
finally:
    os.path.exists(scratch) and os.remove(scratch)
funcs = {a: {"n_instr": 20} for a in (1, 2, 3, 4)} | {5: {"n_instr": 20, "is_thunk": True}}
results = {1: {"dst": 10, "kind": "fuzzy"}, 2: {"dst": 20, "kind": "fold"}, 3: {"dst": 30, "kind": "fuzzy", "score": 0.4}}
print("synthetic, budget  :", {a: row["outcome"] for a, row in terminal_outcomes(funcs, {1: 10}, results, budget_limited=True)["rows"].items()})
print("synthetic, settled :", {a: row["outcome"] for a, row in terminal_outcomes(funcs, {1: 10}, results)["rows"].items()})
EOF
