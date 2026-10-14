# For each file with novel NVMe lines: base = the git version (HEAD ancestry) sharing the most lines with NVMe;
# trial 3-way merge ours=HEAD, base, theirs=NVMe. Writes merged candidates to /tmp/adplan/u13/cand/<rel>.
import subprocess, pathlib, json, difflib, tempfile
WT = "/home/brunner56/ad-wt/u13-reconcile"; NV = pathlib.Path("/home/brunner56/agentdecompile-nvme")
CAND = pathlib.Path("/tmp/adplan/u13/cand")
def g(*a): return subprocess.run(["git", "-C", WT, *a], capture_output=True, text=True).stdout
novel = json.load(open("/tmp/adplan/u13/novel.json")); out = {}
for rel, info in sorted(novel.items()):
    if not info["novel"] or not info["in_head"]: continue
    nv = (NV / rel).read_text(errors="replace"); nvl = nv.splitlines()
    best = None
    for line in g("log", "--format=%H %ad", "--date=short", "HEAD", "--", rel).splitlines()[:150]:
        c, d = line.split()
        t = g("show", f"{c}:{rel}")
        if not t: continue
        sm = difflib.SequenceMatcher(None, t.splitlines(), nvl, autojunk=False)
        score = sum(b.size for b in sm.get_matching_blocks())
        if best is None or score > best[0]: best = (score, c, d, t)
    _, c, d, base = best
    with tempfile.TemporaryDirectory() as tmp:
        o, b, th = (pathlib.Path(tmp) / n for n in "obt")
        o.write_text(pathlib.Path(WT, rel).read_text(errors="replace")); b.write_text(base); th.write_text(nv)
        r = subprocess.run(["git", "merge-file", "-L", "git-HEAD", "-L", f"base-{c[:8]}", "-L", "nvme", str(o), str(b), str(th)])
        dest = CAND / rel; dest.parent.mkdir(parents=True, exist_ok=True); dest.write_text(o.read_text())
    out[rel] = {"base": c[:8], "base_date": d, "conflicts": r.returncode, "novel": len(info["novel"])}
    print(f"conflicts={r.returncode:3d} novel={len(info['novel']):4d} base={c[:8]} {d} {rel}")
json.dump(out, open("/tmp/adplan/u13/true_base.json", "w"), indent=1)
