# U61: auto-parameter capture and one canonical `this` across dynamic and custom storage (stub Ghidra objects).
cd /home/brunner56/ad-wt/u2-seams/src && timeout 120 /home/brunner56/agentdecompile-nvme/.venv/bin/python - <<'EOF'
from types import SimpleNamespace as NS
from agentdecompile_cli.mcp_server.providers.guide_function import canonical_this, _is_auto
def addr(reg=None, stack=None): return NS(isStackAddress=lambda: stack is not None, isRegisterAddress=lambda: reg is not None, getOffset=lambda: stack or 0, __str__=lambda self=None: reg or f"Stack[{stack}]")
class Addr:
    def __init__(s, reg=None, stack=None): s.reg, s.stack = reg, stack
    def isStackAddress(s): return s.stack is not None
    def isRegisterAddress(s): return s.reg is not None
    def getOffset(s): return s.stack or 0
    def __str__(s): return s.reg or f"Stack[{s.stack}]"
def storage(reg=None, stack=None, size=4): return NS(getVarnodes=lambda: [NS(getAddress=lambda: Addr(reg, stack), getSize=lambda: size)])
def param(name, dtype, auto, reg=None, stack=None):
    return NS(getName=lambda: name, getDataType=lambda: dtype, isAutoParameter=lambda: auto, getVariableStorage=lambda: storage(reg, stack))
program = NS(getRegister=lambda a, size: NS(getName=lambda: str(a)))
def func(params, custom, conv): return NS(getParameters=lambda: params, hasCustomVariableStorage=lambda: custom, getCallingConventionName=lambda: conv)
dyn = func([param("this", "CFoo *", True, reg="ECX"), param("count", "int", False, stack=4)], False, "__thiscall")
cus = func([param("this", "CFoo *", False, reg="ECX"), param("count", "int", False, stack=4)], True, "__thiscall")
a, b = canonical_this(program, dyn), canonical_this(program, cus)
print("dynamic :", a["thisParameter"], a["canonicalArguments"])
print("custom  :", b["thisParameter"], b["canonicalArguments"])
strip = lambda t: {k: v for k, v in t.items() if k != "source"}
assert strip(a["thisParameter"]) == strip(b["thisParameter"]) and a["canonicalArguments"] == b["canonicalArguments"]
print("same canonical this and args across modes: True")
plain = canonical_this(program, func([param("count", "int", False, stack=4)], False, "__cdecl"))
print("plain function this:", plain["thisParameter"], "| args", len(plain["canonicalArguments"]))
fake = canonical_this(program, func([param("this", "int", False, stack=4)], True, "__cdecl"))
print("custom, named this but cdecl:", fake["thisParameter"])
EOF
