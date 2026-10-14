# U1 RC-01: unchanged regions with external code fixups, carved from a real md5-verified image
# (Jade Empire, build 1), become objects only when the independent COFF fixup reader places them back
# at their origin byte-for-byte. Corrupting one reconstructed relocation target makes the same
# check refuse, and nothing is written. Function extents come from the live store, opened read-only.
# objdump lives on the host (linuxbrew); this shell is a distrobox, so forward to it.
SHIM=$(mktemp -d); printf '#!/bin/sh\nexec host-spawn /home/linuxbrew/.linuxbrew/bin/objdump "$@"\n' > $SHIM/objdump; chmod +x $SHIM/objdump
command -v objdump >/dev/null || export PATH=$SHIM:$PATH
cd $(git -C "$(dirname "$(readlink -f "$0")")" rev-parse --show-toplevel)/src && timeout 300 /home/brunner56/agentdecompile-nvme/.venv/bin/python - <<'EOF'
import sqlite3, tempfile, pathlib
from agentdecompile_recovery.corpus import mkobj
from agentdecompile_recovery.corpus.export_hookpack import _file_offset
image_path = "/home/brunner56/biodecompwarehouse/kotorxid/output/binaries/JE__JadeEmpire.exe/artifacts/raw_image"
image = pathlib.Path(image_path).read_bytes()
con = sqlite3.connect("file:/home/brunner56/biodecompwarehouse/kotorxid/db/kotorxid.sqlite?mode=ro", uri=True)
funcs = con.execute("select addr,size from func where binary_id=1 and size between 64 and 2048 and is_thunk=0 order by addr limit 120").fetchall()
out = pathlib.Path(tempfile.mkdtemp())
ok = refused = 0; with_relocs = 0; reasons = {}
for addr, size in funcs:
    off = _file_offset(image, addr)
    if off is None: continue
    try:
        mkobj.write_object(binary=image_path, offset=off, size=size, name=f"f{addr:x}", output=out / f"{addr:x}.obj")
    except mkobj.MkobjRefusal as exc:
        reasons[str(exc).split(":")[1].strip()] = reasons.get(str(exc).split(":")[1].strip(), 0) + 1; continue
    ok += 1
    if mkobj.find_call_targets(image[off:off+size], 0x14C): with_relocs += 1
print(f"real regions written : {ok} (with external rel32 fixups: {with_relocs}); refused by mkobj's own scan: {sum(reasons.values())} {reasons}")
# corrupt one reconstructed target: shift one call's target by one byte inside build_object
real_build = mkobj.build_object
def corrupt(code, symbol, machine, call_targets=None):
    targets = dict(call_targets or {})
    if targets:
        k = sorted(targets)[0]; targets[k] += 1
    return real_build(code, symbol, machine, targets)
mkobj.build_object = corrupt
caught = written = 0
for addr, size in funcs:
    off = _file_offset(image, addr)
    if off is None or not mkobj.find_call_targets(image[off:off+size], 0x14C): continue
    dest = out / f"bad-{addr:x}.obj"
    try:
        mkobj.write_object(binary=image_path, offset=off, size=size, name=f"b{addr:x}", output=dest)
    except mkobj.MkobjRefusal as exc:
        if "roundtrip_mismatch" in str(exc): caught += 1
    written += dest.exists()
    if caught >= 25: break
mkobj.build_object = real_build
print(f"corrupted addend     : {caught} regions refused as roundtrip_mismatch, objects written: {written}")
EOF
