# Selective reconciliation: start from git HEAD; accept a changed block from the merged candidate only when it
# carries at least one NVMe line that no git version of the path ever had (style-normalized). Pure deletions and
# blocks that only restore older git text are rejected. Conflict hunks resolve to git; any NVMe-novel lines
# inside them are reported for manual review.
import subprocess, pathlib, json, difflib, tempfile, re, sys
WT = pathlib.Path("/home/brunner56/ad-wt/u13-reconcile"); NV = pathlib.Path("/home/brunner56/agentdecompile-nvme")
tb = json.load(open("/tmp/adplan/u13/true_base.json"))
def g(*a): return subprocess.run(["git", "-C", str(WT), *a], capture_output=True, text=True).stdout
def norm(l): return re.sub(r"[\s;,]+", "", l.replace("'", '"'))
report = {}
for rel, v in sorted(tb.items()):
    seen = set()
    for c in set(g("log", "--format=%H", "HEAD", "--", rel).split()):
        seen.update(norm(l) for l in g("show", f"{c}:{rel}").splitlines())
    novel = lambda lines: [l for l in lines if norm(l) and norm(l) not in seen]
    head = (WT / rel).read_text(errors="replace").splitlines(keepends=True)
    base = g("show", f"{v['base']}:{rel}"); nvtext = (NV / rel).read_text(errors="replace")
    with tempfile.TemporaryDirectory() as tmp:
        o, b, t = (pathlib.Path(tmp) / n for n in "obt")
        o.write_text("".join(head)); b.write_text(base); t.write_text(nvtext)
        subprocess.run(["git", "merge-file", "--ours", str(o), str(b), str(t)])
        ours_resolved = o.read_text().splitlines(keepends=True)
        o.write_text("".join(head)); subprocess.run(["git", "merge-file", "-L", "git", "-L", "base", "-L", "nvme", str(o), str(b), str(t)])
        marked = o.read_text()
    held = []  # NVMe-novel lines inside conflict hunks (dropped by --ours)
    for m in re.finditer(r"^=======\n(.*?)^>>>>>>> nvme\n", marked, re.S | re.M):
        held += novel(m.group(1).splitlines())
    out, taken, rejected = [], 0, 0
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, head, ours_resolved, autojunk=False).get_opcodes():
        if op == "equal": out += head[i1:i2]; continue
        new = ours_resolved[j1:j2]
        if new and novel(new): out += new; taken += 1
        else: out += head[i1:i2]; rejected += 1
    (WT / rel).write_text("".join(out))
    report[rel] = {"taken_blocks": taken, "rejected_blocks": rejected, "conflict_novel_held": held}
    print(f"taken={taken:3d} rejected={rejected:3d} held_in_conflicts={len(held):3d} {rel}")
json.dump(report, open("/tmp/adplan/u13/selective.json", "w"), indent=1)
