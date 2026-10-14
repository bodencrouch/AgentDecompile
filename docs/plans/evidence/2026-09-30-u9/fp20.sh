# U9 FP-20: an interrupted migration leaves the previous consistent version and finalizes once; an older writer is
# refused on a newer store while read-only access remains. Real store.connect / migrations.apply_pending; temp files.
D=/tmp/adplan/verify/u9/fp20; rm -rf $D; mkdir -p $D
cd $(git -C "$(dirname "$(readlink -f "$0")")" rev-parse --show-toplevel)/src && timeout 120 /home/brunner56/agentdecompile-nvme/.venv/bin/python - <<'EOF'
import sqlite3, dataclasses
from agentdecompile_recovery.corpus import store, migrations as M
db = "/tmp/adplan/verify/u9/fp20/s.sqlite"
con = store.connect(db); v0 = M.user_version(con); print("fresh store at version", v0, "== code", M.SCHEMA_VERSION)
# Interrupted migration: a new step that dies half-way.
calls = {"n": 0}
def half(con):
    calls["n"] += 1
    con.execute("CREATE TABLE extra(x)")
    if calls["n"] == 1: raise KeyboardInterrupt("power cut mid-migration")
step = dataclasses.replace(M.MIGRATIONS[-1], version=v0 + 1, name="extra", fn=half)
try: M.apply_pending(con, migrations=M.MIGRATIONS + [step])
except KeyboardInterrupt: pass
print("after interruption: version", M.user_version(con), "| extra table:", bool(con.execute("select 1 from sqlite_master where name='extra'").fetchone()))
applied = M.apply_pending(con, migrations=M.MIGRATIONS + [step]); again = M.apply_pending(con, migrations=M.MIGRATIONS + [step])
print("resume applied:", [a.name for a in applied], "| second run applied:", [a.name for a in again], "| version", M.user_version(con))
con.close()
try: store.connect(db); print("older writer on newer store: ACCEPTED (bad)")
except store.SchemaTooNewError as e: print("older writer refused:", str(e)[:80])
ro = store.connect(db, read_only=True); print("read-only view still available:", ro.execute("select count(*) from binary").fetchone()[0] == 0)
EOF
