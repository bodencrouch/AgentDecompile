"""Original canary oracle: one JSON request, one observable result."""
import json
import sys
value = json.load(sys.stdin)
print(json.dumps({"result": value["x"] * 2 + 1}))
