# U52: relocation-table presence from real images, a stripped-flag copy, the backfill pass and the basis disclosure.
W=/tmp/adplan/verify/u2seams; cd /home/brunner56/ad-wt/u2-seams/src
timeout 300 /home/brunner56/agentdecompile-nvme/.venv/bin/python - <<'EOF'
import struct, sqlite3, shutil, json, os, subprocess, sys
from agentdecompile_recovery.corpus.reloc_presence import relocation_table
imgs = {"nwloader.exe": "/home/brunner56/biodecompwarehouse/repos/NWN2/nwloader.exe",
        "nwn2server.exe": "/home/brunner56/biodecompwarehouse/repos/NWN2/nwn2server.exe", "ls (ELF)": "/usr/bin/ls"}
for k, p in imgs.items(): print(f"{k:16s}", relocation_table(open(p, "rb").read()))
raw = bytearray(open(imgs["nwloader.exe"], "rb").read()); pe = struct.unpack_from("<I", raw, 0x3C)[0]
struct.pack_into("<H", raw, pe + 4 + 18, struct.unpack_from("<H", raw, pe + 22)[0] | 1)
print("stripped copy   ", relocation_table(bytes(raw)))
print("xbe-like bytes  ", relocation_table(b"XBEH" + b"\0" * 64))
# Backfill pass on a one-build temp store; the raw image is supplied through the configured extract path.
db = "/tmp/adplan/verify/u2seams/store.sqlite"; shutil.copy("/tmp/adplan/verify/u2/fixture.canonical.sqlite", db)
con = sqlite3.connect(db); con.execute("DELETE FROM binary WHERE id != 30"); con.commit(); con.close()
env = {**os.environ, "AGENT_DECOMPILE_EXTRACT_RAW": imgs["nwloader.exe"], "PYTHONPATH": os.getcwd()}
for run in (1, 2):
    out = subprocess.run([sys.executable, "-m", "agentdecompile_recovery.corpus.cli", "backfill", "--db", db, "--pass", "reloc_table",
                          "--receipts", "/tmp/adplan/verify/u2seams/receipts"] + ([] if run == 1 else []), capture_output=True, text=True, env=env)
    print(f"backfill run {run}:", json.loads(out.stdout)["passes"]["reloc_table"]["counts"] if out.returncode == 0 else out.stderr[-400:])
con = sqlite3.connect(db); print("row:", con.execute("SELECT slug, reloc_table_present, reloc_table_reason FROM binary").fetchall())
from agentdecompile_recovery.corpus.determinism_basis import masking_inputs, BASIS_HASH_EXCLUDED
print("masking_inputs:", masking_inputs(con), "| excluded from basis_hash:", "masking_inputs" in BASIS_HASH_EXCLUDED)
con.execute("UPDATE binary SET reloc_table_present=0 WHERE id=30"); print("if stripped:", masking_inputs(con))
EOF
