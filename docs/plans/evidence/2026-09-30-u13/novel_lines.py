# For each NVMe src file differing from git HEAD: lines present on NVMe that no git version of that path
# (in HEAD's ancestry) ever contained. Zero novel lines => the NVMe copy is a stale older state; keep git.
import subprocess, pathlib, json
WT = "/home/brunner56/ad-wt/u13-reconcile"; NV = pathlib.Path("/home/brunner56/agentdecompile-nvme")
SKIP = ("__pycache__", "node_modules", "/dist/", ".egg-info", ".pyc", "static/react/assets/")
def g(*a): return subprocess.run(["git", "-C", WT, *a], capture_output=True, text=True).stdout
report = {}
for p in sorted((NV / "src").rglob("*")):
    rel = str(p.relative_to(NV))
    if not p.is_file() or any(s in rel for s in SKIP): continue
    head = pathlib.Path(WT, rel)
    nv_text = p.read_text(errors="replace")
    if head.is_file() and head.read_text(errors="replace") == nv_text: continue
    seen = set()
    blobs = {g("rev-parse", f"{c}:{rel}").strip() for c in g("log", "--format=%H", "HEAD", "--", rel).split()}
    for b in blobs:
        if b: seen.update(l.strip() for l in g("cat-file", "-p", b).splitlines())
    novel = [l for l in nv_text.splitlines() if l.strip() and l.strip() not in seen]
    report[rel] = {"in_head": head.is_file(), "git_versions": len(blobs), "novel": novel}
    print(f"{len(novel):5d} novel  {'' if head.is_file() else '[not in HEAD] '}{rel}")
json.dump(report, open("/tmp/adplan/u13/novel.json", "w"), indent=1)
