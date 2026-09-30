# U2 determinism evidence: git-tree cascade harness on a real 2-build fixture (tmpfs; corpus opened read-only).
# Images are corroborated against binary.md5 before their sha256 becomes content_sha256.
set -e
W=/tmp/adplan/verify/u2; SRC=/home/brunner56/biodecompwarehouse/kotorxid/db/kotorxid.sqlite
rm -f $W/fixture*.sqlite
/home/brunner56/agentdecompile-nvme/.venv/bin/python - "$SRC" "$W/fixture.sqlite" <<'EOF'
import sqlite3, sys, hashlib
IMAGES = {30: "/home/brunner56/biodecompwarehouse/repos/NWN2/nwloader.exe",
          26: "/home/brunner56/biodecompwarehouse/repos/NWN2/nwn2server.exe"}
src = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True); dst = sqlite3.connect(sys.argv[2])
ids = ",".join(map(str, IMAGES))
sys.path.insert(0, "$(git -C "$(dirname "$(readlink -f "$0")")" rev-parse --show-toplevel)/src")
from agentdecompile_recovery.corpus import store as git_store
dst.close(); dst = git_store.connect(sys.argv[2])   # git-tree schema, not the live one
for t in ("binary", "func", "calledge"):
    live = [r[1] for r in src.execute(f"pragma table_info({t})")]
    mine = {r[1] for r in dst.execute(f"pragma table_info({t})")}
    c = [x for x in live if x in mine]
    print(t, "live-only columns dropped:", [x for x in live if x not in mine])
    key = "id" if t == "binary" else "binary_id"
    rows = src.execute(f"select {','.join(c)} from {t} where {key} in ({ids})").fetchall()
    dst.executemany(f"insert into {t} ({','.join(c)}) values ({','.join('?'*len(c))})", rows); print(t, len(rows))
for bid, path in IMAGES.items():
    raw = open(path, "rb").read()
    md5 = src.execute("select md5 from binary where id=?", (bid,)).fetchone()[0]
    assert hashlib.md5(raw).hexdigest() == md5, (bid, path)
    dst.execute("update binary set content_sha256=? where id=?", (hashlib.sha256(raw).hexdigest(), bid))
dst.commit(); print("md5-corroborated content_sha256 set for", sorted(IMAGES))
EOF
cd $(git -C "$(dirname "$(readlink -f "$0")")" rev-parse --show-toplevel)
PYTHONPATH=src nice -n 10 timeout 1500 /usr/bin/time -f 'maxrss_kb=%M elapsed=%e' /home/brunner56/agentdecompile-nvme/.venv/bin/python -m agentdecompile_recovery.corpus.determinism_harness $W/fixture.sqlite --json > $W/result.json
python3 - <<'EOF'
import json; d = json.load(open("/tmp/adplan/verify/u2/result.json")); print("identical", d["identical"])
for s, r in d["seeds"].items():
    print(" seed", s, "identical", r.get("identical"), "cascade", {k: (v if not isinstance(v, dict) else {kk: vv for kk, vv in v.items() if not isinstance(vv, (dict, list))}) for k, v in (r.get("cascades") or {}).get("canonical", {}).items()} if s == list(d["seeds"])[0] else "")
    for run, tabs in (r.get("tables") or {}).items():
        print("   ", run, {t: (v.get("identical"), v.get("rows"), v.get("first_diff")) for t, v in tabs.items()})
EOF
# Export half: hook pack from two temp copies of the cascaded store, byte-compared (the source's verify_export).
cd $(git -C "$(dirname "$(readlink -f "$0")")" rev-parse --show-toplevel)
PYTHONPATH=src timeout 600 /home/brunner56/agentdecompile-nvme/.venv/bin/python -m agentdecompile_recovery.corpus.cli verify-determinism --db $W/fixture.canonical.sqlite
# Analyzer basis is absent in the live rows: stamp a temp copy through the source's own labelled backfill, then export twice.
cp $W/fixture.canonical.sqlite $W/export.sqlite
PYTHONPATH=src timeout 600 /home/brunner56/agentdecompile-nvme/.venv/bin/python -m agentdecompile_recovery.corpus.cli backfill --db $W/export.sqlite --pass analyzer_identity --receipts $W/receipts
PYTHONPATH=src timeout 600 /home/brunner56/agentdecompile-nvme/.venv/bin/python -m agentdecompile_recovery.corpus.cli verify-determinism --db $W/export.sqlite
# Synthetic tie-break fixture shipped by the source (built to expose the rowid tie seed 7 hides), every SHUFFLE_SEED.
rm -f $W/synthetic*.sqlite
PYTHONPATH=src timeout 600 /home/brunner56/agentdecompile-nvme/.venv/bin/python -m agentdecompile_recovery.corpus.determinism_harness $W/synthetic.sqlite --build-fixture --json > $W/synthetic.json
