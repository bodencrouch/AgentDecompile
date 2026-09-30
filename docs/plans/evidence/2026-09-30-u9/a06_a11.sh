# U9 A06 (bundle launchable only after its full closure verifies; unrelated bundle runs) and A11 (behaviour receipt kept,
# combined claim refused without a correlated recording). Real runtime_bundle module; temp bundles.
B=/tmp/adplan/verify/u9/bundles; rm -rf $B; mkdir -p $B/one $B/two
cd "$(git -C "$(dirname "$(readlink -f "$0")")" rev-parse --show-toplevel)/src" && timeout 60 /home/brunner56/agentdecompile-nvme/.venv/bin/python - <<'EOF'
import hashlib, pathlib
from agentdecompile_recovery.corpus.runtime_bundle import validate, is_launchable, combine
B = pathlib.Path("/tmp/adplan/verify/u9/bundles")
def put(bundle, name, data): (B / bundle / name).write_bytes(data); return {"path": name, "sha256": hashlib.sha256(data).hexdigest()}
game = put("one", "game.exe", b"exe"); dll = put("one", "patch.dll", b"dll"); fix = {"path": "fixture.sav", "sha256": hashlib.sha256(b"save").hexdigest()}
game["requires"] = ["patch.dll"]; dll["requires"] = ["fixture.sav"]            # fixture is only reachable indirectly
m1 = {"roots": ["game.exe"], "entries": [game, dll, fix]}
print("indirect fixture not staged:", validate(B / "one", m1), "| launchable:", is_launchable(B / "one"))
other = put("two", "tool.exe", b"tool"); print("unrelated complete bundle:", validate(B / "two", {"roots": ["tool.exe"], "entries": [other]})["launchable"], is_launchable(B / "two"))
put("one", "fixture.sav", b"save"); print("after staging the fixture:", validate(B / "one", m1)["launchable"], is_launchable(B / "one"))
(B / "one/patch.dll").write_bytes(b"tampered"); print("library changed later:", validate(B / "one", m1)["problems"], "| launchable:", is_launchable(B / "one"))
oracle = {"passed": True, "attempt_id": "a1", "action_id": "open-door", "start": 10.0, "end": 12.0}
print("no recording     :", combine(oracle, None)["reason"], "| receipt kept:", combine(oracle, None)["behaviourReceipt"] is oracle)
print("other attempt    :", combine(oracle, {"attempt_id": "a0", "action_id": "open-door", "start": 0, "end": 99})["reason"])
print("short recording  :", combine(oracle, {"attempt_id": "a1", "action_id": "open-door", "start": 11, "end": 13})["reason"])
print("correlated       :", combine(oracle, {"attempt_id": "a1", "action_id": "open-door", "start": 9, "end": 13})["combined"])
EOF
