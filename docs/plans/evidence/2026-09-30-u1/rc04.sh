# U1 RC-04: inline, fold, split, clone and unroll correspondences keep their relation, range and
# multiplicity in `match`, never claim identity, and never become an `identity` row. Only one_to_one
# matches bind. Real pair nwloader.exe -> nwserver.exe (builds 30 -> 26) on a scratch copy of the
# live store (read-only source, placeholder hashes on 30 and 26 only; copy deleted). That pair yields
# no block-level hits, so three crafted hits (inline, fold with two folded sources, split) for real
# unmatched functions are injected at the block_inline seam; persistence and binding are real.
cd $(git -C "$(dirname "$(readlink -f "$0")")" rev-parse --show-toplevel)/src && timeout 1200 /home/brunner56/agentdecompile-nvme/.venv/bin/python - <<'EOF'
import sqlite3, hashlib, os, tempfile, json
from agentdecompile_recovery.corpus import propagate
scratch = tempfile.mktemp(suffix=".sqlite", dir="/tmp")
try:
    src = sqlite3.connect("file:/home/brunner56/biodecompwarehouse/kotorxid/db/kotorxid.sqlite?mode=ro", uri=True)
    con = sqlite3.connect(scratch); src.backup(con); src.close()
    for bid in (30, 26):
        con.execute("update binary set content_sha256=? where id=?", (hashlib.sha256(f"scratch-{bid}".encode()).hexdigest(), bid))
    con.commit(); con.row_factory = sqlite3.Row
    paths = {r["id"]: r["path"] for r in con.execute("select id, repo_path as path from binary where id in (30, 26)")}
    from agentdecompile_recovery.corpus import match_store
    real = match_store.leftover_inlines
    def crafted(missing, survivors):
        m, h = sorted(missing, key=lambda f: f["addr"]), sorted(survivors, key=lambda f: f["addr"])
        hit = lambda f, host, kind, **extra: {"missing_id": f["addr"], "host_id": host["addr"], "kind": kind, "block_count": 3,
                                              "src_end": f["addr"] + 16, "dst_end": host["addr"] + 64, **extra}
        return [hit(m[0], h[0], "inline"), hit(m[1], h[1], "fold", folded_missing_ids=[m[1]["addr"], m[2]["addr"]]),
                hit(m[3], h[2], "split", fragments=[{"start": h[2]["addr"], "end": h[2]["addr"] + 32}])]
    match_store.leftover_inlines = crafted
    propagate.run_pair(con, paths[30], paths[26], "rc04", "rc04")
    match_store.leftover_inlines = real
    rel = dict(con.execute("select relation, count(*) from match where run='rc04' group by relation").fetchall())
    print("match rows by relation   :", rel)
    non = con.execute("select evidence, src_end, dst_end, status from match where run='rc04' and relation!='one_to_one'").fetchall()
    claims = sum(json.loads(r["evidence"]).get("identity_claim") is not False for r in non)
    print("non-1:1 rows             :", len(non), "| claiming identity:", claims, "| statuses:", sorted({r["status"] for r in non}),
          "| with ranges:", sum(r["src_end"] is not None for r in non))
    folded = [json.loads(r["evidence"]).get("folded_missing_ids") for r in non if json.loads(r["evidence"]).get("folded_missing_ids")]
    print("folded multiplicity kept :", len(folded), "rows, e.g.", folded[:1])
    propagate.bind_identities(con, "rc04")
    bad = con.execute("""select count(*) from identity i join match m on m.dst_binary=i.binary_id and m.dst_addr=i.addr
                         where m.run='rc04' and m.relation!='one_to_one' and i.method like 'match:rc04:%'
                         and not exists (select 1 from match m2 where m2.run='rc04' and m2.relation='one_to_one'
                                          and m2.dst_binary=i.binary_id and m2.dst_addr=i.addr)""").fetchone()[0]
    print("identity rows from non-1:1 evidence:", bad, "| identity rows bound by this run:",
          con.execute("select count(*) from identity where method like 'match:rc04:%'").fetchone()[0])
finally:
    os.path.exists(scratch) and os.remove(scratch)
EOF
