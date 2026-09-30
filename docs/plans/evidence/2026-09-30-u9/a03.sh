# U9 A03: kill the compile job after N durable units. The N unit receipts survive, the unit being
# compiled leaves no object, nothing is linked, and a resumed run compiles only the remaining units.
# A changed source or compiler invalidates exactly the receipts it affects. The compiler is a stub
# that counts invocations and can stall mid-write so the whole job is SIGKILLed there.
cd $(git -C "$(dirname "$(readlink -f "$0")")" rev-parse --show-toplevel)/src && timeout 120 /home/brunner56/agentdecompile-nvme/.venv/bin/python - <<'EOF'
import os, signal, subprocess, sys, tempfile, time
from pathlib import Path
w = Path(tempfile.mkdtemp()); src = w / "src"; src.mkdir(); log = w / "calls.log"
for i in range(8): (src / f"u{i}.c").write_text(f"int f{i}(void){{return {i};}}\n")
cc = w / "stubcc"
cc.write_text(f"""#!/usr/bin/env python3
import sys, time, os
a = sys.argv[1:]
if "-c" in a:
    s, o = a[a.index("-c")+1], a[a.index("-o")+1]
    open("{log}", "a").write(os.path.basename(s) + "\\n")
    with open(o, "wb") as f:
        f.write(b"PARTIAL")
        f.flush()
        if os.path.basename(s) == os.environ.get("STALL_ON"): time.sleep(60)
        f.write(open(s, "rb").read())
else:
    o = a[a.index("-o")+1]; open(o, "wb").write(b"".join(open(p, "rb").read() for p in a[:a.index("-o")]))
""")
cc.chmod(0o755)
out = w / "out" / "image.exe"
run = f"from agentdecompile_recovery.corpus.compile_link import compile_and_link_tree as t; print(t('{src}', '{out}', compiler='{cc}', workers=1))"
p = subprocess.Popen([sys.executable, "-c", run], env={**os.environ, "STALL_ON": "u3.c"}, start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
while not log.exists() or "u3.c" not in log.read_text(): time.sleep(0.05)
time.sleep(0.3); os.killpg(p.pid, signal.SIGKILL); p.wait()
obj = w / "out" / "obj"
print("killed during u3   : receipts", sorted(r.name.split('.')[0] for r in obj.glob("*.receipt.json")))
print("objects in place   :", sorted(o.name for o in obj.glob("u*.obj")), "| image:", out.exists())
print("stray partials     :", len(list(obj.glob(".agentdecompile-*"))), "(private names, never linked)")
log.write_text("")
from agentdecompile_recovery.corpus.compile_link import compile_and_link_tree as t
r = t(src, out, compiler=str(cc), workers=1)
print("resume             : compiled", log.read_text().split(), "| reused", r["skipped"], "| linked", r["ok"])
log.write_text(""); (src / "u5.c").write_text("int f5(void){return 55;}\n")
r = t(src, out, compiler=str(cc), workers=1)
print("u5 source changed  : compiled", log.read_text().split(), "| reused", r["skipped"])
log.write_text(""); cc.write_text(cc.read_text() + "# new compiler build\n")
r = t(src, out, compiler=str(cc), workers=1)
print("compiler changed   : compiled", len(log.read_text().split()), "units | reused", r["skipped"])
EOF
