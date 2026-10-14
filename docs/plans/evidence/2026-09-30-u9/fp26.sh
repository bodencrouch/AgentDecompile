# U9 FP-26: unchanged inputs suppress a repeated automatic full audit; explicit requests and changed inputs still
# run full; without a provable basis nothing is suppressed. Real verify_periodic scheduling; the compile step stubbed.
D=/tmp/adplan/verify/u9/fp26; rm -rf $D; mkdir -p $D/src
cd $(git -C "$(dirname "$(readlink -f "$0")")" rev-parse --show-toplevel)/src && timeout 60 /home/brunner56/agentdecompile-nvme/.venv/bin/python - <<'EOF'
import json, time, pathlib, io, contextlib
from agentdecompile_recovery.corpus import verify_periodic as vp
D = pathlib.Path("/tmp/adplan/verify/u9/fp26"); (D / "src/f.c").write_text("int f(void){return 1;}\n")
(D / "raw.bin").write_bytes(b"MZ" + b"\0" * 62); (D / "cc.sh").write_text("#!/bin/bash\n")
(D / "manifest.json").write_text(json.dumps({"complete": True, "files": ["cc.sh"]}))
ran = []
vp.vbx.main = lambda rest: ran.append("FULL" if "--no-incremental" in rest else "incremental") or 0
base = ["--verified-dir", str(D / "src"), "--raw", str(D / "raw.bin"), "--compiler", str(D / "cc.sh"), "--out", str(D / "out.json")]
def run(*extra, manifest=True):
    args = ["--full-interval-seconds", "0.01", *extra, *base] + (["--cache-input-manifest", str(D / "manifest.json")] if manifest else [])
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf): vp.main(args)
    time.sleep(0.05); return ran[-1], [l for l in buf.getvalue().splitlines() if "pass #" in l and "done" not in l][0].split(": ", 1)[1]
print("1 first run          :", run())
print("2 unchanged repeat   :", run())
print("3 --force-full       :", run("--force-full"))
(D / "src/f.c").write_text("int f(void){return 2;}\n")
print("4 source changed     :", run())
print("5 unchanged again    :", run())
print("6 no complete manifest:", run(manifest=False))
EOF
