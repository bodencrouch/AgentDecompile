# U65: decompiler timeouts become data (enrich records) or a distinct refusal (high_emit); driven with stub results.
cd /home/brunner56/ad-wt/u2-seams/src && timeout 120 /home/brunner56/agentdecompile-nvme/.venv/bin/python - <<'EOF'
import sys, types
task = types.ModuleType("ghidra.util.task"); task.TaskMonitor = types.SimpleNamespace(DUMMY=None)
for name in ("ghidra", "ghidra.util"): sys.modules.setdefault(name, types.ModuleType(name))
sys.modules["ghidra.util.task"] = task
from agentdecompile_recovery.pyghidra_enrich import PyGhidraEnrichProgram
from agentdecompile_recovery.corpus.high_emit import collect_high_facts, DecompileTimeout
class Fn:
    def getName(self): return "FUN_00401000"
    def getPrototypeString(self, a, b): return "undefined FUN_00401000(void)"
class Res:
    def __init__(self, done, timed_out): self.done, self.t = done, timed_out
    def decompileCompleted(self): return self.done
    def isTimedOut(self): return self.t
    def getErrorMessage(self): return "Decompiler process timed out" if self.t else "bad instruction"
    def getDecompiledFunction(self): return types.SimpleNamespace(getC=lambda: "int f(void){return 0;}", getSignature=lambda: "int f(void)")
def enrich(res):
    e = object.__new__(PyGhidraEnrichProgram); e.decompile_timeout = 60
    e.program = types.SimpleNamespace(getFunctionManager=lambda: types.SimpleNamespace(getFunctionAt=lambda a: Fn()))
    e._address = lambda x: x; e.decompiler = types.SimpleNamespace(decompileFunction=lambda f, t, m: res)
    return e.decompile(0x401000)
for label, res in (("complete", Res(True, False)), ("timed out", Res(False, True)), ("failed", Res(False, False))):
    r = enrich(res); print(f"enrich {label:9s}:", {k: r.get(k) for k in ("decompilationStatus", "timedOut", "decompileTimeoutSeconds", "prototypeSource", "prototype")})
for label, res in (("timed out", Res(False, True)), ("failed", Res(False, False))):
    try: collect_high_facts(None, Fn(), types.SimpleNamespace(decompileFunction=lambda f, t, m: res))
    except DecompileTimeout as e: print(f"high_emit {label}: DecompileTimeout:", e)
    except RuntimeError as e: print(f"high_emit {label}: RuntimeError:", e)
EOF
grep -n '"timedOut": bool(result.get("timedOut"))' /home/brunner56/ad-wt/u2-seams/src/agentdecompile_recovery/pyghidra_enrich.py && echo "persisted record carries timedOut"
