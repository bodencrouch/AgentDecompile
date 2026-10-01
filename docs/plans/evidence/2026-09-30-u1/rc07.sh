# U1 RC-07: the same evidence in shuffled discovery order yields the same accepted state, and a tie
# stays unresolved. Before the fix, two sources scoring equally for one destination were settled by
# source id (L1 always won). Part 1: list matcher, every permutation of the inputs. Part 2: store
# matcher on a scratch copy of the live store (read-only source, placeholder hashes on 30 and 28,
# copy deleted), run twice. The ingest-order half is the U2 harness (2026-09-29/u2_harness.sh).
cd $(git -C "$(dirname "$(readlink -f "$0")")" rev-parse --show-toplevel)/src && timeout 900 /home/brunner56/agentdecompile-nvme/.venv/bin/python - <<'EOF'
import itertools, sqlite3, hashlib, os, tempfile
from agentdecompile_recovery.corpus.match_engine import match_binaries as list_match
from agentdecompile_recovery.corpus.match_store import match_binaries
def fn(i, addr, extra=()):
    return {"id": i, "addr": addr, "n_instr": 30, "n_blocks": 5, "n_edges": 6, "size": 120, "hash_raw": f"h{addr}",
            "mnemonic_hist": {"mov": 10, "call": 2, "ret": 1}, "strings": ["shared str", *extra], "consts": [0x1234]}
L = [fn("L1", 0x1000), fn("L2", 0x2000), fn("L3", 0x3000, ["only in L3"])]
R = [fn("R1", 0x9000), fn("R3", 0xA000, ["only in L3"])]
states = set()
for perm in itertools.permutations(L):
    for rperm in itertools.permutations(R):
        states.add(tuple(sorted((r["left_id"], r["right_id"], r["status"]) for r in list_match(list(perm), list(rperm), tier="review"))))
print("list matcher, 12 orders  :", len(states), "distinct accepted state(s):", sorted(states))
scratch = tempfile.mktemp(suffix=".sqlite", dir="/tmp")
try:
    src = sqlite3.connect("file:/home/brunner56/biodecompwarehouse/kotorxid/db/kotorxid.sqlite?mode=ro", uri=True)
    dst = sqlite3.connect(scratch); src.backup(dst); src.close()
    for bid in (30, 28):
        dst.execute("update binary set content_sha256=? where id=?", (hashlib.sha256(f"scratch-{bid}".encode()).hexdigest(), bid))
    dst.commit(); dst.row_factory = sqlite3.Row
    runs = [match_binaries(dst, 30, 28, rounds=3) for _ in range(2)]
    tied = [a for a, r in runs[0]["results"].items() if r.get("ambiguity") == "tied_sources"]
    print("store matcher, 2 runs    : same mapping", runs[0]["mapping"] == runs[1]["mapping"],
          "| matched", len(runs[0]["mapping"]), "| tied sources held back", len(tied),
          "| any tied source mapped:", any(a in runs[0]["mapping"] for a in tied))
    print("  outcomes               :", runs[0]["outcomes"]["counts"])
finally:
    os.path.exists(scratch) and os.remove(scratch)
EOF
