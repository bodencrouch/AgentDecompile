# Classify every file under NVMe src/ against git HEAD and base 64d768ca (3-way).
import subprocess, pathlib, hashlib, json, sys
WT = pathlib.Path("/home/brunner56/ad-wt/u13-reconcile"); NV = pathlib.Path("/home/brunner56/agentdecompile-nvme")
SKIP = ("__pycache__", "node_modules", "/dist/", ".egg-info", ".pyc")
def base_blob(rel):
    r = subprocess.run(["git", "-C", str(WT), "show", f"64d768ca:{rel}"], capture_output=True)
    return r.stdout if r.returncode == 0 else None
out = {}
for p in sorted((NV / "src").rglob("*")):
    rel = str(p.relative_to(NV))
    if not p.is_file() or any(s in rel for s in SKIP): continue
    nv = p.read_bytes(); g = (WT / rel).read_bytes() if (WT / rel).is_file() else None
    if g == nv: continue
    b = base_blob(rel)
    if g is None and b is None: cls = "nvme-added"
    elif g is None: cls = "git-deleted" if nv == b else "git-deleted-nvme-changed"
    elif b is None: cls = "both-added-differ"
    elif nv == b: cls = "git-only-change"
    elif g == b: cls = "nvme-only-change"
    else: cls = "both-changed"
    out.setdefault(cls, []).append(rel)
json.dump(out, open("/tmp/adplan/u13/classes.json", "w"), indent=1)
for k, v in out.items(): print(k, len(v))
for k in ("nvme-added", "nvme-only-change", "both-changed", "both-added-differ", "git-deleted-nvme-changed"):
    for r in out.get(k, []): print(f"  {k}: {r}")
