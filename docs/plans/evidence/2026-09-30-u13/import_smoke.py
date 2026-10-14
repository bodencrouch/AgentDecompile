# Import every module under src/{agentdecompile_recovery,agentdecompile_cli}; print module<TAB>status. Run with cwd=<tree>/src.
import importlib, pathlib, sys, traceback, os, io, contextlib
os.environ.setdefault("AGENTDECOMPILE_NO_GHIDRA", "1")
sys.path.insert(0, os.getcwd())
for pkg in ("agentdecompile_recovery", "agentdecompile_cli"):
    for p in sorted(pathlib.Path(pkg).rglob("*.py")):
        if "__pycache__" in p.parts or "tests" in p.parts: continue
        mod = ".".join(p.with_suffix("").parts)
        if mod.endswith(".__main__"): continue
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                importlib.import_module(mod.removesuffix(".__init__"))
            print(f"{mod}\tok")
        except BaseException as e:
            print(f"{mod}\t{type(e).__name__}: {str(e)[:160]}")
