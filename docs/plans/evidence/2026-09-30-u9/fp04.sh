# U9 FP-04: a prefix initialized once is reused by every consumer without another setup; a fresh
# prefix raced by four consumers (processes) is set up exactly once; a failed or timed-out setup is
# recorded and not retried until reset; a prefix initialized before this module is adopted without
# running anything; ~/.wine is refused. Wine is a stub that counts wineboot runs.
cd $(git -C "$(dirname "$(readlink -f "$0")")" rev-parse --show-toplevel)/src && timeout 120 /home/brunner56/agentdecompile-nvme/.venv/bin/python - <<'EOF'
import os, sys, subprocess, tempfile
from pathlib import Path
from agentdecompile_recovery.corpus import wine_prefix as wp
w = Path(tempfile.mkdtemp()); log = w / "wineboot.log"
def stub(name, body):
    p = w / name; p.write_text("#!/bin/sh\n" + body); p.chmod(0o755); return str(p)
good = stub("wine", f'echo run >> {log}; sleep 1; touch "$WINEPREFIX/system.reg"\n')
bad = stub("wine-bad", f'echo run >> {log}; exit 3\n')
slow = stub("wine-slow", f'echo run >> {log}; sleep 30\n')
runs = lambda: len(log.read_text().split()) if log.exists() else 0
prefix = w / "prefixes" / "kotor"
code = f"from agentdecompile_recovery.corpus import wine_prefix as wp; print(wp.ensure_prefix('{prefix}', '{good}')['state'])"
procs = [subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True) for _ in range(4)]
print("4 racing consumers :", sorted(p.communicate()[0].strip() for p in procs), "| wineboot runs", runs())
for who in ("recorder", "live driver"):
    print(f"{who:<19}:", wp.ensure_prefix(prefix, good)["state"], "| wineboot runs", runs())
b = w / "prefixes" / "broken"; log.write_text("")
print("failed setup       :", wp.ensure_prefix(b, bad)["state"], "| again:", wp.ensure_prefix(b, bad)["state"], "| runs", runs())
wp.reset_failure(b); wp.ensure_prefix(b, good)
print("after reset        :", wp.state(b), "| runs", runs())
s = w / "prefixes" / "stuck"; log.write_text("")
r = wp.ensure_prefix(s, slow, timeout=1)
print("timed-out setup    :", r["state"], "|", r["detail"][:28], "| again:", wp.ensure_prefix(s, slow, timeout=1)["state"], "| runs", runs())
old = w / "prefixes" / "preexisting"; old.mkdir(); (old / "system.reg").write_text("WINE REGISTRY"); log.write_text("")
print("pre-existing prefix:", [wp.ensure_prefix(old, good)["state"] for _ in range(3)], "| runs", runs(), "| adopted", wp._marker(old)["adopted"])
print("default ~/.wine    :", wp.ensure_prefix(Path.home() / ".wine", good)["state"])
EOF
