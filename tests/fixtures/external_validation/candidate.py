"""Original canary candidate; --wrong deliberately injects a constant error."""
import json
import sys
value = json.load(sys.stdin)
result = value["x"] + value["x"] + 1
if "--wrong" in sys.argv:
    result += 1
print(json.dumps({"result": result}))
