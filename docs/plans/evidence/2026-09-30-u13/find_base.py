# Find the git commit whose src/ tree matches the most NVMe files byte-for-byte (the true sync point).
import subprocess, pathlib
WT = "/home/brunner56/ad-wt/u13-reconcile"; NV = pathlib.Path("/home/brunner56/agentdecompile-nvme")
SKIP = ("__pycache__", "node_modules", "/dist/", ".egg-info", ".pyc")
files = [p for p in (NV / "src").rglob("*") if p.is_file() and not any(s in str(p) for s in SKIP)]
rels = [str(p.relative_to(NV)) for p in files]
h = subprocess.run(["git", "-C", WT, "hash-object", "--stdin-paths"], input="\n".join(map(str, files)), capture_output=True, text=True).stdout.split()
nv = dict(zip(rels, h))
commits = subprocess.run(["git", "-C", WT, "rev-list", "--all", "--since=2026-09-08"], capture_output=True, text=True).stdout.split()
best = []
for c in commits:
    tree = subprocess.run(["git", "-C", WT, "ls-tree", "-r", c, "src"], capture_output=True, text=True).stdout
    blobs = {line.split("\t")[1]: line.split()[2] for line in tree.splitlines()}
    best.append((sum(1 for r, x in nv.items() if blobs.get(r) == x), c))
best.sort(reverse=True)
print("nvme files", len(nv), "commits scanned", len(commits))
for n, c in best[:8]:
    print(n, subprocess.run(["git", "-C", WT, "log", "-1", "--format=%h %ad %D %s", "--date=iso", c], capture_output=True, text=True).stdout.strip()[:150])
