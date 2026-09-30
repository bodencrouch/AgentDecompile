# U9 FP-09/A04: a deterministic compile failure is cached durably; a new process (fresh Ledger) cannot retry it,
# while a changed candidate (different content key) is eligible. Real cross_place_checkpoint.Ledger, temp area.
A=/tmp/adplan/verify/u9/fp09area; rm -rf $A; mkdir -p $A
cd $(git -C "$(dirname "$(readlink -f "$0")")" rev-parse --show-toplevel)/src && timeout 60 /home/brunner56/agentdecompile-nvme/.venv/bin/python - <<'EOF'
import hashlib, subprocess, sys
from agentdecompile_recovery.corpus.cross_place_checkpoint import Ledger
area = "/tmp/adplan/verify/u9/fp09area"
key = hashlib.sha256(b"candidate-A basis").hexdigest(); changed = hashlib.sha256(b"candidate-A' basis").hexdigest()
L = Ledger(area); ok, row = L.reserve(key, 2, 0.0); print("first attempt reserved:", ok)
L.outcome(key, state="deterministic", reason="incompatible_native_object:compiler_object_not_raw_equal")
code = f"""
from agentdecompile_recovery.corpus.cross_place_checkpoint import Ledger
L = Ledger({area!r}); ok, row = L.reserve({key!r}, 2, 0.0); print("new process, same candidate:", ok, row["state"], row["reason"][:40])
ok2, _ = L.reserve({changed!r}, 2, 0.0); print("new process, changed candidate:", ok2)
"""
out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True); print(out.stdout.strip() or out.stderr[-400:])
EOF
